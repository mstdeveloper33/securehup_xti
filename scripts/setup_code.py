"""Install one checksum-pinned native detector without executing repository content."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from xti.adapters.betterleaks import BetterleaksScanner, install_directory, target_platform
from xti.domain.betterleaks_pin import ARCHIVES, VERSION, archive_url


def install(directory=None, fetch=None):
    destination = Path(directory) if directory else install_directory()
    if destination.exists() or destination.is_symlink():
        state = BetterleaksScanner(destination).status()
        if state['state'] != 'ready': raise ValueError('Mevcut kurulum geçersiz; üzerine yazılmadı.')
        return state
    target = target_platform()
    if fetch is None:
        def fetch(url):
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'XTI-code-setup/1'}), timeout=60) as response:
                return response.read(48 * 1024 * 1024 + 1)
    blob = fetch(archive_url(target))
    if len(blob) > 48 * 1024 * 1024 or hashlib.sha256(blob).hexdigest() != ARCHIVES[target]:
        raise ValueError('İndirilen Betterleaks arşivi sabit SHA256 ile uyuşmuyor.')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.parent.is_symlink() or destination.parent.stat().st_mode & 0o022:
        raise ValueError('Araç dizini başkalarınca yazılabilir olmamalı.')
    with tempfile.TemporaryDirectory(prefix='.code-install-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'ready'; staged.mkdir(mode=0o700)
        with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as archive:
            for name, maximum in (('betterleaks', 80 * 1024 * 1024), ('LICENSE', 128 * 1024)):
                matches = [m for m in archive.getmembers() if m.name == name]
                if len(matches) != 1 or not matches[0].isfile() or not 0 < matches[0].size <= maximum:
                    raise ValueError('Araç arşivindeki dosya biçimi geçersiz.')
                content = archive.extractfile(matches[0]).read(maximum + 1)
                if len(content) != matches[0].size: raise ValueError('Eksik araç dosyası.')
                path = staged / name
                with path.open('xb') as stream: stream.write(content); stream.flush(); os.fsync(stream.fileno())
                path.chmod(0o700 if name == 'betterleaks' else 0o600)
        receipt = {'version': VERSION, 'target': target, 'archive_sha256': ARCHIVES[target],
                   'binary_sha256': hashlib.sha256((staged / 'betterleaks').read_bytes()).hexdigest()}
        (staged / 'receipt.json').write_text(json.dumps(receipt)); (staged / 'receipt.json').chmod(0o600)
        # Single atomic directory publication. A competing completed installation is never overwritten.
        os.rename(staged, destination)
    return BetterleaksScanner(destination).status()


def main():
    parser = argparse.ArgumentParser(description='Betterleaks sabit sürümünü kur veya doğrula.')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        state = BetterleaksScanner().status() if args.check else install()
        print(json.dumps(state, ensure_ascii=False))
        return 0 if state['state'] == 'ready' else 1
    except (ValueError, OSError, tarfile.TarError):
        print('Betterleaks kurulamadı; mevcut kurulum korunuyor. Ağ, izin ve sabit sürüm arşivini kontrol edin.', file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
