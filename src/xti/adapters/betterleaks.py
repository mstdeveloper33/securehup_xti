"""Pinned offline secret detector. Raw output/body never leaves this adapter."""
import hashlib
import json
import os
from pathlib import Path
import platform
import selectors
import signal
import stat
import subprocess
import tempfile
import time

from xti.domain.betterleaks_pin import ARCHIVES, VERSION
from xti.domain.code_exposure import CodeExposureError, MAX_FILE_BYTES, text, integer


def target_platform():
    system = platform.system().lower()
    machine = {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'x64', 'amd64': 'x64'}.get(platform.machine().lower())
    target = f'{system}_{machine}'
    if target not in ARCHIVES: raise CodeExposureError('unsupported_platform', 'Betterleaks bu sistem için sabitlenmedi.')
    return target


def install_directory():
    return Path(__file__).resolve().parents[3] / '.tools' / 'betterleaks' / VERSION / target_platform()


class BetterleaksScanner:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else install_directory()
        self._verified = False

    def status(self):
        try:
            binary = self.directory / 'betterleaks'
            receipt = self.directory / 'receipt.json'
            for path in (self.directory, binary, receipt):
                info = path.lstat()
                if (stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_mode & 0o022): raise ValueError('permissions')
            if not binary.is_file() or not receipt.is_file() or receipt.stat().st_size > 2048:
                raise ValueError('files')
            data = json.loads(receipt.read_text())
            if (data['version'] != VERSION or data['target'] != target_platform()
                    or data['archive_sha256'] != ARCHIVES[data['target']]
                    or binary.stat().st_size > 80 * 1024 * 1024): raise ValueError('pin')
            with binary.open('rb') as stream:
                h = hashlib.sha256()
                while chunk := stream.read(1024 * 1024): h.update(chunk)
            if h.hexdigest() != data['binary_sha256']: raise ValueError('checksum')
            self._verified = True
            return {'tool': 'betterleaks', 'version': VERSION, 'state': 'ready', 'validation': False}
        except FileNotFoundError:
            return {'tool': 'betterleaks', 'version': VERSION, 'state': 'not_installed', 'setup': './scripts/setup-code'}
        except (ValueError, KeyError, TypeError, OSError):
            return {'tool': 'betterleaks', 'version': VERSION, 'state': 'invalid_installation', 'setup': './scripts/setup-code --check'}

    def scan(self, content, *, seconds=10):
        body = content.encode()
        if len(body) > MAX_FILE_BYTES: raise CodeExposureError('scan_limit', 'Dosya inceleme sınırını aşıyor.')
        if not self._verified and self.status()['state'] != 'ready':
            raise CodeExposureError('scanner_unavailable', 'Betterleaks kurulumu hazır değil; secret kontrolü yapılmadı.')
        command = [str(self.directory / 'betterleaks'), 'stdin', '--no-banner', '--no-color',
                   '--redact=100', '--log-level', 'error', '--report-format', 'json', '--report-path', '-',
                   '--timeout', str(max(1, int(seconds))), '--max-archive-depth', '0', '--max-decode-depth', '0',
                   '--ignore-gitleaks-allow', '--exit-code', '23', '--validation=false', '--unsafe-auto-load-config=false']
        deadline = time.monotonic() + max(0.01, min(seconds, 30))
        output = bytearray()
        with tempfile.TemporaryDirectory(prefix='xti-code-scan-') as temporary:
            process = subprocess.Popen(command, cwd=temporary, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TMPDIR': temporary},
                start_new_session=True)
            try:
                with selectors.DefaultSelector() as poller:
                    for stream in (process.stdin, process.stdout): os.set_blocking(stream.fileno(), False)
                    poller.register(process.stdin, selectors.EVENT_WRITE)
                    poller.register(process.stdout, selectors.EVENT_READ)
                    position = 0
                    while poller.get_map():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0: raise CodeExposureError('scanner_timeout', 'Secret incelemesi süre sınırına ulaştı.')
                        for key, _ in poller.select(min(remaining, .1)):
                            if key.fileobj is process.stdin:
                                if position >= len(body):
                                    poller.unregister(process.stdin); process.stdin.close()
                                else:
                                    try: position += os.write(process.stdin.fileno(), body[position:position + 16384])
                                    except BrokenPipeError:
                                        poller.unregister(process.stdin); process.stdin.close()
                            else:
                                chunk = os.read(process.stdout.fileno(), 65536)
                                if not chunk: poller.unregister(process.stdout)
                                else:
                                    output.extend(chunk)
                                    if len(output) > 4 * 1024 * 1024:
                                        raise CodeExposureError('scanner_output_limit', 'Secret inceleme çıktısı sınırı aştı.')
                code = process.wait(timeout=max(.01, deadline - time.monotonic()))
                if code not in (0, 23): raise ValueError('execution')
                report = json.loads(output or b'[]')
                if not isinstance(report, list) or len(report) > 1000: raise ValueError('report')
                results = []
                for row in report:
                    # Whitelist, even if an upstream release accidentally stops redacting.
                    results.append({'rule': text(row['RuleID'], maximum=100),
                                    'line': integer(row['StartLine'], 1, MAX_FILE_BYTES)})
                return results
            except CodeExposureError:
                raise
            except (ValueError, TypeError, KeyError, OSError, subprocess.TimeoutExpired):
                raise CodeExposureError('scanner_failed', 'Secret incelemesi tamamlanamadı; araç çıktısı saklanmadı.') from None
            finally:
                if process.poll() is None:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                process.wait()
                for stream in (process.stdin, process.stdout): stream.close()
