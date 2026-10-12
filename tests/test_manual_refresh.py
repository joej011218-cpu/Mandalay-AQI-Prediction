import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Event
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest

import app as web
from prediction.features import DataUnavailable
from prediction.models import ModelRegistry
from prediction.service import ForecastService, RefreshLimited
from prediction import source_refresh


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 10, 8, 30, tzinfo=timezone.utc).astimezone(tz)


@pytest.fixture(scope='module')
def registry():
    return ModelRegistry()


@pytest.fixture
def service(registry, monkeypatch):
    rows = json.loads((Path(__file__).parent / 'fixtures/mandalay_real_history.json').read_text())['data']
    store = Mock()
    store.fetch.return_value = copy.deepcopy(rows)
    service = ForecastService(store, registry)
    monkeypatch.setattr('prediction.service.datetime', Clock)
    return service


def next_observation(service):
    rows = copy.deepcopy(service.store.fetch.return_value)
    row = copy.deepcopy(rows[-1])
    row['timestamp'] = (pd.Timestamp(row['timestamp']) + pd.Timedelta(hours=1)).isoformat()
    row['stored_cpcb_aqi'] = None
    rows.append(row)
    service.store.fetch.return_value = rows[-192:]


def test_refresh_runs_real_24_models_then_reuses_unchanged_inputs(service, monkeypatch):
    predict = Mock(wraps=service.registry.predict)
    monkeypatch.setattr(service.registry, 'predict', predict)
    before = service.forecast()
    assert predict.call_count == 1
    collector = Mock(side_effect=lambda: next_observation(service))
    result = service.refresh(collector)
    assert result['manual_refresh']['status'] == 'updated'
    assert len(result['forecasts']) == 24 and predict.call_count == 2
    assert all(pd.Timestamp(item['timestamp']) == pd.Timestamp(result['forecast_origin']) + pd.Timedelta(hours=item['horizon'])
               for item in result['forecasts'])
    assert result['forecast_origin'] != before['forecast_origin']
    assert result['generated_at'].endswith('+06:30')
    cooldown = service.refresh(collector)
    assert cooldown['manual_refresh']['status'] == 'cooldown'
    assert collector.call_count == 1 and predict.call_count == 2
    service._refresh_after = 0
    unchanged = service.refresh(Mock())
    assert unchanged['manual_refresh']['status'] == 'unchanged'
    assert unchanged['generated_at'] == result['generated_at'] and predict.call_count == 2


def test_same_origin_provider_corrections_update_cache(service, monkeypatch):
    before = service.forecast()
    changed = copy.deepcopy(service.store.fetch.return_value)
    changed[-2]['pm2_5'] += 1
    changed[-1]['stored_cpcb_aqi'] = None
    service.store.fetch.return_value = changed
    predict = Mock(wraps=service.registry.predict)
    monkeypatch.setattr(service.registry, 'predict', predict)
    result = service.refresh(Mock())
    assert result['forecast_origin'] == before['forecast_origin']
    assert not result['cached'] and predict.call_count == 1


@pytest.mark.parametrize('failure', ['collector', 'database', 'inference'])
def test_failure_preserves_successful_forecast_and_rate_limit(service, monkeypatch, failure):
    before = service.forecast()
    collector = Mock()
    if failure == 'collector':
        collector.side_effect = DataUnavailable('source unavailable')
    elif failure == 'database':
        service.store.fetch.side_effect = DataUnavailable('database unavailable')
    else:
        next_observation(service)
        monkeypatch.setattr(service.registry, 'predict', Mock(side_effect=RuntimeError('inference failed')))
    with pytest.raises(DataUnavailable):
        service.refresh(collector)
    after = service.refresh(collector)
    assert after['forecasts'] == before['forecasts']
    assert after['generated_at'] == before['generated_at']
    assert after['manual_refresh']['status'] == 'cooldown' and collector.call_count == 1
    assert service.forecast()['forecasts'] == before['forecasts']


def test_simultaneous_manual_and_automatic_requests_share_inference_lock(service):
    service.forecast()
    next_observation(service)
    entered, release = Event(), Event()
    def collector():
        entered.set()
        assert release.wait(10)
    with ThreadPoolExecutor(max_workers=2) as pool:
        refreshing = pool.submit(service.refresh, collector)
        try:
            assert entered.wait(5)
            with pytest.raises(RefreshLimited):
                service.refresh(Mock(side_effect=AssertionError('duplicate collector')))
            automatic = pool.submit(service.forecast)
        finally:
            release.set()
        manual_result, auto_result = refreshing.result(), automatic.result()
    assert manual_result['generated_at'] == auto_result['generated_at']
    assert manual_result['forecasts'] == auto_result['forecasts'] and auto_result['cached']


def test_automatic_gets_do_not_call_collector_and_update_for_new_source(service, monkeypatch):
    collector = Mock()
    monkeypatch.setattr(web, 'refresh_source', collector)
    client = web.create_app(service).test_client()
    first = client.get('/api/prediction').json
    next_observation(service)
    service._expires = 0
    second = client.get('/api/prediction').json
    assert first['forecast_origin'] != second['forecast_origin']
    collector.assert_not_called()


def test_refresh_http_success_rate_limit_and_sanitized_errors(service, monkeypatch):
    collector = Mock()
    monkeypatch.setattr(web, 'refresh_source', collector)
    client = web.create_app(service).test_client()
    response = client.post('/api/prediction/refresh')
    assert response.status_code == 200 and len(response.json['forecasts']) == 24
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.post('/api/prediction/refresh').json['manual_refresh']['status'] == 'cooldown'
    service._refresh_after = 0
    collector.side_effect = RuntimeError('secret-token')
    response = client.post('/api/prediction/refresh')
    assert response.status_code == 500 and b'secret-token' not in response.data
    service._refresh_after = 0
    collector.side_effect = DataUnavailable('secret-token')
    assert client.post('/api/prediction/refresh').status_code == 503
    service._forecast_lock.acquire()
    try:
        response = client.post('/api/prediction/refresh')
        assert response.status_code == 429 and response.headers['Retry-After'] == '5'
    finally:
        service._forecast_lock.release()
    assert 'DASHBOARD_REFRESH_TOKEN' not in client.get('/prediction.html').text


def test_source_client_sends_token_only_to_fixed_https_endpoint(monkeypatch):
    monkeypatch.setenv('DASHBOARD_REFRESH_TOKEN', 'private-test-token')
    response = Mock(status=200)
    response.read.return_value = b'{"status":"ok","imported":172}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    monkeypatch.setattr(source_refresh, 'build_opener', Mock(return_value=opener))
    source_refresh.refresh_source()
    request = opener.open.call_args.args[0]
    assert request.full_url == source_refresh.REFRESH_URL and request.method == 'POST'
    assert request.headers['Authorization'] == 'Bearer private-test-token'
    assert opener.open.call_args.kwargs['timeout'] == 85
    assert source_refresh.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example') is None


def test_button_api_through_source_client_to_real_inference(service, monkeypatch):
    monkeypatch.setenv('DASHBOARD_REFRESH_TOKEN', 'private-test-token')
    before = service.forecast()
    response = Mock(status=200)
    response.read.return_value = b'{"status":"ok","imported":172}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    def collect(request, timeout):
        assert request.headers['Authorization'] == 'Bearer private-test-token'
        next_observation(service)
        return response
    opener = Mock()
    opener.open.side_effect = collect
    monkeypatch.setattr(source_refresh, 'build_opener', Mock(return_value=opener))
    result = web.create_app(service).test_client().post('/api/prediction/refresh')
    assert result.status_code == 200 and result.json['manual_refresh']['status'] == 'updated'
    assert len(result.json['forecasts']) == 24
    assert result.json['forecast_origin'] != before['forecast_origin']
    assert b'private-test-token' not in result.data
    opener.open.assert_called_once()


def test_incomplete_corrected_history_is_an_error_and_keeps_previous_forecast(service):
    before = service.forecast()
    changed = copy.deepcopy(service.store.fetch.return_value)
    changed[-1]['pm2_5'] = None
    changed[-1]['stored_cpcb_aqi'] = None
    service.store.fetch.return_value = changed
    with pytest.raises(DataUnavailable):
        service.refresh(Mock())
    assert service.forecast()['forecasts'] == before['forecasts']


@pytest.mark.parametrize('body,status', [(b'{}',200), (b'{}',202), (b'x'*4097,200),
    (b'<html>error</html>',200), (b'{"status":"ok","imported":true}',200)])
def test_source_client_rejects_invalid_or_async_success(monkeypatch, body, status):
    monkeypatch.setenv('DASHBOARD_REFRESH_TOKEN', 'private-test-token')
    response = Mock(status=status)
    response.read.return_value = body
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    monkeypatch.setattr(source_refresh, 'build_opener', Mock(return_value=opener))
    with pytest.raises(DataUnavailable) as error:
        source_refresh.refresh_source()
    assert 'private-test-token' not in str(error.value)


@pytest.mark.parametrize('failure', [URLError('private-test-token'), HTTPError('https://example',401,'private-test-token',{},None), TimeoutError('private-test-token')])
def test_source_client_redacts_network_failures(monkeypatch, failure):
    monkeypatch.setenv('DASHBOARD_REFRESH_TOKEN', 'private-test-token')
    opener = Mock()
    opener.open.side_effect = failure
    monkeypatch.setattr(source_refresh, 'build_opener', Mock(return_value=opener))
    with pytest.raises(DataUnavailable) as error:
        source_refresh.refresh_source()
    assert 'private-test-token' not in str(error.value)


def test_missing_token_is_explicit_and_never_calls_network(monkeypatch):
    monkeypatch.delenv('DASHBOARD_REFRESH_TOKEN', raising=False)
    opener = Mock()
    monkeypatch.setattr(source_refresh, 'build_opener', opener)
    with pytest.raises(DataUnavailable, match='not configured'):
        source_refresh.refresh_source()
    opener.assert_not_called()


@pytest.mark.parametrize('code', list(source_refresh.SourceRefreshError.REASONS))
def test_http_reports_fixed_safe_source_failure_reason(service, monkeypatch, code, caplog):
    error = source_refresh.SourceRefreshError(code)
    monkeypatch.setattr(web, 'refresh_source', Mock(side_effect=error))
    response = web.create_app(service).test_client().post('/api/prediction/refresh')
    assert response.status_code == error.http_status
    assert response.json == {'error': str(error), 'error_code': code}
    assert code in caplog.text


@pytest.mark.parametrize('origin', ['2026-10-10T23:00:00+06:30', '2026-12-31T23:00:00+06:30'])
def test_real_model_targets_cross_midnight_and_year_without_generation_time_shift(service, monkeypatch, origin):
    rows = copy.deepcopy(service.store.fetch.return_value)
    delta = pd.Timestamp(origin) - pd.Timestamp(rows[-1]['timestamp'])
    for row in rows:
        row['timestamp'] = (pd.Timestamp(row['timestamp']) + delta).isoformat()
    service.store.fetch.return_value = rows
    class GenerationClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (pd.Timestamp(origin) + pd.Timedelta(minutes=6)).to_pydatetime().astimezone(tz)
    monkeypatch.setattr('prediction.service.datetime', GenerationClock)
    result = service.forecast()
    assert pd.Timestamp(result['forecasts'][0]['timestamp']) == pd.Timestamp(origin) + pd.Timedelta(hours=1)
    assert pd.Timestamp(result['forecasts'][-1]['timestamp']) == pd.Timestamp(origin) + pd.Timedelta(hours=24)
    assert pd.Timestamp(result['generated_at']).minute == 6
    assert all(pd.Timestamp(item['timestamp']).minute == 0 for item in result['forecasts'])
