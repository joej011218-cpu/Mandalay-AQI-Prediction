import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest
from app import create_app
from prediction.models import ModelRegistry
from prediction.database import ObservationStore, QUERY
from prediction.features import inference_row, prepare, DataUnavailable
from prediction.service import ForecastService

FIXTURES=Path(__file__).parent/'fixtures'
@pytest.fixture(scope='session')
def rows():
    return json.loads((FIXTURES/'mandalay_real_history.json').read_text())['data']
@pytest.fixture(scope='session')
def registry():
    return ModelRegistry()

class FixedClock(datetime):
    @classmethod
    def now(cls,tz=None):
        return datetime(2026,10,10,7,30,tzinfo=timezone.utc).astimezone(tz)

class FixtureStore:
    def __init__(self,rows): self.rows=rows
    def fetch(self): return self.rows

@pytest.fixture
def service(rows,registry):
    return ForecastService(FixtureStore(rows),registry,cache_seconds=0)


def test_all_models_and_exact_order(registry):
    assert list(registry.models)==list(range(1,25))
    assert len(registry.columns)==198
    assert all(m.n_features_in_==198 for m in registry.models.values())

def test_original_training_feature_parity(rows,registry):
    golden=json.loads((FIXTURES/'original_training_features.json').read_text())
    current,x=inference_row(rows,registry.columns)
    assert current.aqi==golden['current_cpcb_aqi']==68
    assert x.columns.tolist()==list(golden['features'])
    np.testing.assert_allclose(x.iloc[0].to_numpy(),np.array(list(golden['features'].values()),dtype='float32'),rtol=0,atol=0)
    assert current.co==0.281
    assert current.pm25==8.6

def test_real_inference_all_horizons(rows,registry):
    current,x=inference_row(rows,registry.columns)
    deltas=registry.predict(x)
    assert len(deltas)==24 and all(np.isfinite(list(deltas.values())))
    with pytest.raises(ValueError): registry.predict(x[x.columns[::-1]])

def test_complete_api(service):
    with patch('prediction.service.datetime',FixedClock):
        client=create_app(service).test_client()
        for path in ['/api/health','/api/latest','/api/prediction/status','/api/prediction','/','/prediction.html','/static/app.js']:
            assert client.get(path).status_code==200
        result=client.get('/api/prediction').get_json()
        assert len(result['forecasts'])==24
        assert result['current']['cpcb_aqi']==68
        assert result['forecasts'][23]['timestamp']=='2026-10-11T13:00:00+06:30'
        for f in result['forecasts']:
            assert f['raw_predicted_cpcb_aqi']==68+f['predicted_delta']
            assert f['predicted_cpcb_aqi']==np.clip(f['raw_predicted_cpcb_aqi'],0,500)
        assert 'us_aqi' not in json.dumps(result)

def test_missing_history_never_filled(rows,registry):
    with pytest.raises(DataUnavailable,match='Incomplete history'):
        inference_row(rows[-168:],registry.columns)
    with pytest.raises(DataUnavailable,match='192 hourly slots'):
        inference_row(rows[-183:],registry.columns)
    broken=copy.deepcopy(rows);broken[-2]['pm2_5']=None
    with pytest.raises(DataUnavailable): inference_row(broken,registry.columns)
    broken=copy.deepcopy(rows);del broken[-24]
    with pytest.raises(DataUnavailable): inference_row(broken,registry.columns)

def test_timestamp_and_duplicate_rejection(rows,registry):
    broken=copy.deepcopy(rows);broken[-1]['timestamp']='2026-10-10T13:00:00'
    with pytest.raises(DataUnavailable,match='timezone'): inference_row(broken,registry.columns)
    with pytest.raises(DataUnavailable,match='Duplicate'): inference_row(rows+[rows[-1]],registry.columns)
    broken=copy.deepcopy(rows);broken[-1]['timestamp']='2026-10-10T13:30:00+06:30'
    with pytest.raises(DataUnavailable,match='whole-hour'): inference_row(broken,registry.columns)

def test_stale_forecast_is_explicit_on_cold_start(service):
    service.max_age_hours=0.1
    with patch('prediction.service.datetime',FixedClock):
        response=create_app(service).test_client().get('/api/prediction')
        assert response.status_code==200
        result=response.get_json()
        assert result['status']=='stale' and result['stale']
        assert result['forecast_origin']=='2026-10-10T13:00:00+06:30'
        assert result['warnings'] and not result['cached']

def test_stored_aqi_mismatch(rows,registry):
    broken=copy.deepcopy(rows);broken[-1]['stored_cpcb_aqi']=99
    service=ForecastService(FixtureStore(broken),registry)
    with patch('prediction.service.datetime',FixedClock):
        with pytest.raises(DataUnavailable,match='differs'): service.latest()

def test_severe_band_no_invented_numeric_aqi(rows,registry):
    broken=copy.deepcopy(rows)
    for r in broken[-24:]: r['pm2_5']=1000.
    broken[-1]['stored_cpcb_aqi']=None
    service=ForecastService(FixtureStore(broken),registry)
    with patch('prediction.service.datetime',FixedClock):
        assert service.latest()['category']=='Severe'
        with pytest.raises(DataUnavailable,match='numeric CPCB'): service.forecast()

def test_database_config_and_missing_models_are_explicit():
    with pytest.raises(DataUnavailable,match='DATABASE_URL'): ObservationStore('').fetch()
    service=ForecastService(FixtureStore([]),None,'Models unavailable')
    client=create_app(service).test_client()
    assert client.get('/api/prediction/status').status_code==503

def test_database_transactions_are_readonly(rows):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,query,args):
            assert query==QUERY and args==(191,)
        def fetchall(self): return rows
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def set_session(self,**kwargs): assert kwargs=={'readonly':True}
        def cursor(self,**kwargs): return Cursor()
    with patch('prediction.database.psycopg2.connect',return_value=Connection()) as connect:
        assert ObservationStore('postgresql://example/database').fetch()==rows
        assert 'default_transaction_read_only=on' in connect.call_args.kwargs['options']

def test_forecast_cache_key_origin_and_model_version(service):
    with patch('prediction.service.datetime',FixedClock),patch.object(service.registry,'predict',wraps=service.registry.predict) as predict:
        first=service.forecast();second=service.forecast()
        assert predict.call_count==1
        assert second['cached'] is True and first['cached'] is False
        assert second['generated_at']==first['generated_at']
        assert second['model_version']==service.registry.version
        with patch.object(service.registry,'version','test-new-model-version'):
            changed=service.forecast()
            assert predict.call_count==2 and changed['model_version']=='test-new-model-version'


def test_retained_forecast_is_labeled_stale(service):
    with patch('prediction.service.datetime',FixedClock):
        first=service.forecast()
        service.max_age_hours=0.1
        result=service.forecast()
        assert result['status']=='stale' and result['stale']
        assert result['warnings']
        assert result['generated_at']==first['generated_at']
        assert result['forecasts']==first['forecasts']


def test_database_outage_retains_previous_success(service):
    with patch('prediction.service.datetime',FixedClock):
        first=service.forecast()
        with patch.object(service.store,'fetch',side_effect=DataUnavailable('Database unavailable')):
            result=service.forecast()
            assert result['status']=='stale' and result['warnings']
            assert result['generated_at']==first['generated_at']
            client=create_app(service).test_client()
            assert client.get('/api/health').status_code==503
            assert client.get('/api/latest').get_json()['data']['data_cache_fallback']


def test_new_origin_regenerates_only_once(rows,registry):
    # Use a second genuine hourly origin from the real fixture, not invented readings.
    initial=copy.deepcopy(rows[:-1])
    # Earlier origin needs an additional real history slot from the same saved public export.
    older=json.loads((FIXTURES/'mandalay_previous_origin.json').read_text())['data']
    store=FixtureStore(older)
    service=ForecastService(store,registry,cache_seconds=0)
    with patch('prediction.service.datetime',FixedClock),patch.object(registry,'predict',wraps=registry.predict) as predict:
        first=service.forecast()
        store.rows=rows
        second=service.forecast();service.forecast()
        assert first['forecast_origin']!=second['forecast_origin']
        assert predict.call_count==2


def test_original_ui_routes_and_public_readonly(service):
    client=create_app(service).test_client()
    page=client.get('/prediction.html').get_data(as_text=True)
    assert 'Mandalay 24-Hour AQI Prediction' in page
    assert 'forecastSummary' in page and 'forecastChart' in page
    assert '/static/vendor/chart.umd.min.js' in page
    assert 'https://aiot-public-dashboard-2.onrender.com/' in page
    assert 'Green' not in page
    precautions=client.get('/precautions.html')
    assert precautions.status_code==200
    assert precautions.get_data(as_text=True).count('class="card"')==6
    with patch('prediction.service.datetime',FixedClock):
        assert client.get('/api/forecast').status_code==200
    for endpoint in ['/api/latest','/api/prediction','/api/refresh']:
        assert client.post(endpoint).status_code in (404,405)

def test_invalid_new_observation_retains_original_forecast(rows,registry):
    older=json.loads((FIXTURES/'mandalay_previous_origin.json').read_text())['data']
    store=FixtureStore(older);service=ForecastService(store,registry,cache_seconds=0)
    with patch('prediction.service.datetime',FixedClock):
        first=service.forecast()
        broken=copy.deepcopy(rows);broken[-1]['pm2_5']=None
        # A missing latest feature must not be synthesized from the prior hour.
        store.rows=broken
        result=service.forecast()
        assert result['stale']
        assert result['forecast_origin']==first['forecast_origin']
        assert result['generated_at']==first['generated_at']
        assert result['latest_observation']['timestamp']!=first['forecast_origin']


def test_forecast_cache_singleflight(service):
    from concurrent.futures import ThreadPoolExecutor
    with patch('prediction.service.datetime',FixedClock),patch.object(service.registry,'predict',wraps=service.registry.predict) as predict:
        with ThreadPoolExecutor(max_workers=4) as executor:
            results=list(executor.map(lambda _:service.forecast(),range(4)))
        assert predict.call_count==1
        assert len({r['generated_at'] for r in results})==1


def test_render_and_original_styles_are_preserved():
    import re
    base=Path(__file__).parents[1]
    original=(base/'reference_ui/prediction.html').read_text()
    original_css=re.search(r'<style>(.*?)</style>',original,re.S).group(1)
    assert (base/'static/style.css').read_text().startswith(original_css)
    precautions=(base/'reference_ui/precautions.html').read_text()
    assert (base/'static/precautions.css').read_text().strip()==re.search(r'<style>(.*?)</style>',precautions,re.S).group(1).strip()
    render=(base/'render.yaml').read_text()
    assert 'gunicorn wsgi:app --bind 0.0.0.0:$PORT' in render
    assert 'databases:' not in render and 'refresh-data' not in render
    for c in ['#4E9F3D','#A8C43A','#E8C547','#E8823C','#D8453B','#7A2A2A']:
        assert c in (base/'templates/precautions.html').read_text()


@pytest.mark.parametrize('kind',['us_aqi','horizon','feature_order'])
def test_incompatible_artifact_configuration_rejected(registry,kind):
    import joblib
    real_load=joblib.load
    def altered(path):
        result=real_load(path)
        if Path(path).parent.name=='horizon_01h':
            if Path(path).name=='model_config.joblib':
                result=dict(result)
                if kind=='us_aqi': result['aqi_type']='US AQI'
                if kind=='horizon': result['forecast_horizon']=24
            if Path(path).name=='feature_columns.joblib' and kind=='feature_order': result=list(reversed(result))
        return result
    with patch('prediction.models.joblib.load',side_effect=altered):
        with pytest.raises(ValueError,match='incompatible'):ModelRegistry()

def test_model_inference_failure_is_a_clear_public_error(service):
    with patch('prediction.service.datetime',FixedClock),patch.object(service.registry,'predict',side_effect=ValueError('incompatible input')):
        response=create_app(service).test_client().get('/api/prediction')
        assert response.status_code==503
        assert 'inference failed' in response.get_json()['error']
