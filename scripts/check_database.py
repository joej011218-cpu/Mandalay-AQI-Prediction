"""Read-only check of existing database and real 24-horizon forecast."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app

if __name__ == '__main__':
    client=create_app().test_client()
    failed=False
    for path in ['/api/health','/api/latest','/api/prediction/status','/api/prediction']:
        response=client.get(path)
        data=response.get_json()
        print(json.dumps({'endpoint':path,'http_status':response.status_code,
                          'status':data.get('status'),'error':data.get('error'),
                          'models_loaded':data.get('models_loaded'),
                          'forecast_origin':data.get('forecast_origin'),
                          'forecast_count':len(data.get('forecasts',[]))}))
        failed |= response.status_code != 200
    sys.exit(1 if failed else 0)
