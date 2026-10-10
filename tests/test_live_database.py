"""Optional read-only test; no disposable database and no schema/record writes."""
import os
import pytest
from app import create_app

@pytest.mark.skipif(os.getenv('RUN_LIVE_DATABASE_TESTS')!='1',reason='Set RUN_LIVE_DATABASE_TESTS=1 for a read-only existing-database integration check')
def test_live_existing_database():
    client=create_app().test_client()
    assert client.get('/api/health').status_code==200
    latest=client.get('/api/latest')
    assert latest.status_code==200
    prediction=client.get('/api/prediction')
    assert prediction.status_code==200,prediction.get_json()
    result=prediction.get_json()
    assert len(result['forecasts'])==24
    assert result['feature_count']==198
    assert result['current']['cpcb_aqi']==latest.get_json()['data']['cpcb_aqi']
