import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from prediction.database import ObservationStore
from prediction.features import DataUnavailable
from prediction.models import ModelRegistry, DEFAULT_ROOT
from prediction.service import ForecastService, META

load_dotenv(Path(__file__).resolve().parent / '.env', override=False)

def create_app(service=None):
    app = Flask(__name__)
    if service is None:
        registry, error = None, None
        try:
            registry = ModelRegistry(os.getenv('MODEL_DIR',str(DEFAULT_ROOT)))
        except Exception:
            logging.exception('Model validation failed')
            error = 'Model artifacts missing or incompatible; run scripts/validate_models.py'
        service = ForecastService(ObservationStore(),registry,error)
    app.extensions['forecast_service'] = service

    @app.get('/')
    @app.get('/prediction.html')
    def page():
        return render_template('prediction.html',
            mandalay_url=os.getenv('MANDALAY_DASHBOARD_URL','https://mandalay-aqi-dashboard-bk49.onrender.com/'),
            vadodara_url=os.getenv('VADODARA_DASHBOARD_URL','https://aiot-public-dashboard-2.onrender.com/'))

    @app.get('/precautions.html')
    def precautions():
        return render_template('precautions.html',
            mandalay_url=os.getenv('MANDALAY_DASHBOARD_URL','https://mandalay-aqi-dashboard-bk49.onrender.com/'),
            vadodara_url=os.getenv('VADODARA_DASHBOARD_URL','https://aiot-public-dashboard-2.onrender.com/'))

    @app.errorhandler(DataUnavailable)
    def unavailable(exc):
        return jsonify(**META,status='unavailable',error=str(exc)),503

    @app.get('/api/health')
    def health():
        try:
            service.snapshot()
            db_status = service.source_error or 'reachable'
        except DataUnavailable as exc:
            db_status = str(exc)
        healthy = db_status == 'reachable' and service.registry is not None
        return jsonify(**META,status='ok' if healthy else 'unavailable',
            database=db_status,models_loaded=len(service.registry.models) if service.registry else 0),200 if healthy else 503

    @app.get('/api/latest')
    def latest():
        return jsonify(**META,data=service.latest())

    @app.get('/api/prediction')
    @app.get('/api/forecast')
    def prediction():
        return jsonify(service.forecast())

    @app.get('/api/prediction/status')
    def status():
        try:
            result = service.forecast()
            return jsonify(**META,status='ready' if not result['stale'] else 'stale',models_loaded=24,feature_count=result['feature_count'],
                           forecast_origin=result['forecast_origin'],generated_at=result['generated_at'],
                           model_version=result['model_version'],cached=result['cached'],warnings=result['warnings'])
        except DataUnavailable as exc:
            return jsonify(**META,status='unavailable',models_loaded=len(service.registry.models) if service.registry else 0,
                           error=str(exc)),503

    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store' if response.is_json else 'no-cache'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'none'"
        return response
    return app

if __name__ == '__main__':
    create_app().run(host='127.0.0.1',port=int(os.getenv('PORT','8000')))
