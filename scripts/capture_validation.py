"""Save nonsecret real inference evidence and inspect the existing schema read-only."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg2
from app import create_app

if __name__ == '__main__':
    app=create_app()
    service=app.extensions['forecast_service']
    client=app.test_client()
    checks=[]
    for endpoint in ['/api/health','/api/latest','/api/prediction/status','/api/prediction']:
        response=client.get(endpoint)
        checks.append({'endpoint':endpoint,'http_status':response.status_code})
        if response.status_code != 200:
            print('Validation unavailable; no successful report written')
            sys.exit(1)
    forecast=service.forecast()
    url=service.store.url.replace('postgresql+psycopg://','postgresql://',1).replace('postgresql+psycopg2://','postgresql://',1)
    with psycopg2.connect(url,connect_timeout=8,options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute('SHOW transaction_read_only')
            readonly=cur.fetchone()[0]
            assert readonly=='on'
            cur.execute('''SELECT table_name,column_name,data_type,is_nullable
                           FROM information_schema.columns
                           WHERE table_schema='public' AND table_name IN
                           ('mandalay_readings','mandalay_cpcb_aqi','mandalay_source_observations')
                           ORDER BY table_name,ordinal_position''')
            schema=[dict(zip(['table','column','type','nullable'],r)) for r in cur.fetchall()]
    report={'database_integration':'tested successfully, existing PostgreSQL',
            'transaction_read_only':readonly,'endpoints':checks,
            'observations_retrieved':len(service.snapshot()),'schema':schema,
            'forecast':forecast}
    Path('docs/live_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'transaction_read_only':readonly,'observations':len(service.snapshot()),
                      'current_cpcb_aqi':forecast['current']['cpcb_aqi'],
                      'origin':forecast['forecast_origin'],
                      'summary':{str(r['horizon']):round(r['predicted_cpcb_aqi'],2) for r in forecast['forecasts'] if r['horizon'] in [1,6,12,24]}}))
