"""Non-secret source identity for local, uncommitted acceptance evidence."""
import hashlib
from pathlib import Path
import subprocess


def identity():
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / 'src').rglob('*.py'))
    files += [root / 'scripts' / name for name in (
        'setup_code.py', 'check-code-delivery.py', 'check-code-live.py', 'code_acceptance_identity.py')]
    fingerprint = hashlib.sha256()
    for path in files:
        fingerprint.update((str(path.relative_to(root)) + '\0' + hashlib.sha256(path.read_bytes()).hexdigest() + '\n').encode())
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    from xti import __version__
    return {'base_commit': commit, 'runtime_version': __version__, 'source_sha256': fingerprint.hexdigest(),
            'source_files': len(files), 'scope': 'working_tree_src_python_and_code_acceptance_scripts'}
