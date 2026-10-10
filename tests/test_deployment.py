"""Deployment must reject incomplete or changed pretrained delivery."""
import json
from pathlib import Path
import pytest
from scripts.check_deployment import verify, ROOT


def test_real_model_delivery():
    result = verify()
    assert result['artifacts'] == 74
    assert result['counts']['xgboost_delta_model.joblib'] == 24


@pytest.mark.parametrize('failure', ['missing', 'changed'])
def test_invalid_delivery_fails(tmp_path, failure):
    bundle = tmp_path / 'models'
    bundle.mkdir()
    artifact = bundle / 'model.joblib'
    artifact.write_bytes(b'changed')
    (tmp_path / 'deployment-models.json').write_text(json.dumps({
        'model_directory': 'models', 'files': {'model.joblib': {
            'bytes': 8, 'sha256': 'invalid'}}}))
    if failure == 'missing':
        artifact.unlink()
    with pytest.raises(ValueError, match='inventory|checksum'):
        verify(tmp_path)
