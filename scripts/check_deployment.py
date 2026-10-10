"""Verify the immutable model delivery inventory; never train or download models."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT, require_staged=False):
    inventory = json.loads((root / 'deployment-models.json').read_text())
    directory = root / inventory['model_directory']
    expected = inventory['files']
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual != set(expected):
        raise ValueError('Model bundle differs from deployment inventory')
    for name, metadata in expected.items():
        data = (directory / name).read_bytes()
        if len(data) != metadata['bytes'] or hashlib.sha256(data).hexdigest() != metadata['sha256']:
            raise ValueError(f'Model artifact checksum mismatch: {name}')
        if len(data) >= 100 * 1024 * 1024:
            raise ValueError(f'Model artifact exceeds GitHub file limit: {name}')
        if require_staged:
            relative = (Path(inventory['model_directory']) / name).as_posix()
            staged = subprocess.run(['git', 'show', ':' + relative], cwd=root,
                                    capture_output=True, check=False)
            if staged.returncode or hashlib.sha256(staged.stdout).hexdigest() != metadata['sha256']:
                raise ValueError(f'Model artifact missing or different in Git index: {name}')
    counts = {name: sum(Path(p).name == name for p in expected) for name in
              ('xgboost_delta_model.joblib', 'model_config.joblib', 'feature_columns.joblib')}
    if set(counts.values()) != {24}:
        raise ValueError(f'Incomplete 24-horizon bundle: {counts}')
    return {'artifacts': len(expected), 'total_bytes': sum(m['bytes'] for m in expected.values()),
            'largest_bytes': max(m['bytes'] for m in expected.values()),
            'counts': counts, 'git_index_verified': require_staged}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--require-staged', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(require_staged=args.require_staged)))
