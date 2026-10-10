"""Load only user-trusted joblib artifacts. Never fit or retrain."""
from pathlib import Path
import hashlib
import json
import warnings
import joblib
import numpy as np
import xgboost
from .cpcb import VERSION

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / 'models/XGB_Mandalay_CPCB_Delta24_2026'

class ModelRegistry:
    def __init__(self, root=DEFAULT_ROOT):
        self.root = Path(root)
        self.models = {}
        self.columns = None
        self.report = []
        self.warnings = []
        version_hash = hashlib.sha256()
        manifest = json.loads((self.root / 'training_manifest.json').read_text())
        if manifest['aqi_standard'] != 'Indian CPCB AQI' or manifest['calculation_version'] != VERSION:
            raise ValueError('Training manifest is not the expected CPCB methodology')
        folders = sorted(self.root.glob('horizon_*h'))
        if {p.name for p in folders} != {f'horizon_{h:02d}h' for h in range(1,25)}:
            raise ValueError('Exactly horizons +1 through +24 are required')
        for h in range(1,25):
            folder = self.root / f'horizon_{h:02d}h'
            config = joblib.load(folder / 'model_config.joblib')
            columns = list(joblib.load(folder / 'feature_columns.joblib'))
            expected = {'model':'XGBoost_DeltaOnly', 'aqi_type':'Indian CPCB AQI',
                        'calculation_version':VERSION, 'forecast_horizon':h,
                        'co_training_unit':'mg/m3', 'other_pollutant_unit':'ug/m3',
                        'timestamp_timezone':'Asia/Yangon', 'features_include_current_hour':True,
                        'target':'Future CPCB AQI - Current CPCB AQI',
                        'final_prediction':'Current CPCB AQI + Predicted Delta'}
            if any(config.get(k) != v for k,v in expected.items()):
                raise ValueError(f'Horizon {h}: incompatible model metadata')
            if columns != manifest['feature_columns'] or len(set(columns)) != len(columns) or len(columns) != 198 or config['expected_feature_count'] != len(columns):
                raise ValueError(f'Horizon {h}: incompatible feature columns')
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                model = joblib.load(folder / 'xgboost_delta_model.joblib')
            self.warnings.extend(str(w.message) for w in caught)
            if not isinstance(model, xgboost.XGBRegressor):
                raise ValueError(f'Horizon {h}: expected XGBRegressor')
            booster = model.get_booster()
            if model.n_features_in_ != len(columns) or booster.feature_names != columns:
                raise ValueError(f'Horizon {h}: booster feature names/count/order mismatch')
            if json.loads(booster.save_config())['learner']['objective']['name'] != 'reg:squarederror':
                raise ValueError(f'Horizon {h}: incompatible objective')
            model.set_params(n_jobs=1)
            self.models[h] = model
            self.columns = columns
            self.report.append({'horizon':h, 'features':len(columns), 'validated':True,
                                'model_sha256':hashlib.sha256((folder/'xgboost_delta_model.joblib').read_bytes()).hexdigest()})
            for name in ('xgboost_delta_model.joblib','model_config.joblib','feature_columns.joblib'):
                version_hash.update((folder/name).read_bytes())
        self.version = version_hash.hexdigest()

    def predict(self, frame):
        if frame.columns.tolist() != self.columns or frame.shape != (1,len(self.columns)) or not np.isfinite(frame.to_numpy()).all():
            raise ValueError('Prediction input must contain one finite row with the exact feature order')
        values = {h:float(m.predict(frame)[0]) for h,m in self.models.items()}
        if not all(np.isfinite(v) for v in values.values()):
            raise ValueError('Model returned a nonfinite delta')
        return values
