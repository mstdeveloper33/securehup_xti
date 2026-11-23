"""Identity for P02 implementation, installers, manifests and acceptance scripts."""
import hashlib
from pathlib import Path
import subprocess


def identity():
    root = Path(__file__).resolve().parents[1]
    paths = set((root / 'src').rglob('*.py'))
    paths.update((root / 'requirements').glob('*.txt'))
    paths.update(root / name for name in ('pyproject.toml', 'constraints/brand.txt', 'setup',
        'scripts/setup_brand.py', 'scripts/verify_brand_install.py', 'scripts/check-content-delivery.py',
        'scripts/check-content-live.py', 'scripts/content_acceptance_identity.py'))
    value = hashlib.sha256()
    for path in sorted(paths):
        value.update((str(path.relative_to(root)) + '\0' + hashlib.sha256(path.read_bytes()).hexdigest() + '\n').encode())
    from xti import __version__
    return {'base_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True,
        text=True, check=True, timeout=10).stdout.strip(), 'runtime_version': __version__,
        'source_sha256': value.hexdigest(), 'source_files': len(paths),
        'scope': 'src_python_and_p02_installation_manifests_acceptance'}
