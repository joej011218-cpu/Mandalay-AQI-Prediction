"""Validate all trusted artifacts without training or modifying them."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prediction.models import ModelRegistry, DEFAULT_ROOT

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    registry=ModelRegistry(os.getenv('MODEL_DIR',str(DEFAULT_ROOT)))
    result={'status':'validated','models':registry.report,'feature_count':len(registry.columns),
            'feature_columns':registry.columns,'aqi_standard':'Indian CPCB AQI',
            'runtime_warnings':sorted(set(registry.warnings)),
            'note':'Metadata and booster compatibility validation; real-input inference tested separately.'}
    if args.output: args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'models_loaded':len(registry.models),'feature_count':len(registry.columns),
                      'horizons':list(registry.models),'warning_count':len(registry.warnings)}))
