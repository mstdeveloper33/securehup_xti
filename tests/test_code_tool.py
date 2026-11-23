from contextlib import redirect_stderr
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.betterleaks import BetterleaksScanner, target_platform
from xti.domain.betterleaks_pin import ARCHIVES, VERSION
from xti.domain.code_exposure import CodeExposureError

ROOT = Path(__file__).resolve().parents[1]


class CodeToolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def detector(self, program):
        directory = self.root / 'tool'; directory.mkdir(mode=0o700)
        binary = directory / 'betterleaks'
        binary.write_text('#!' + sys.executable + '\n' + program)
        binary.chmod(0o700)
        (directory / 'receipt.json').write_text(json.dumps({'version': VERSION, 'target': target_platform(),
            'archive_sha256': ARCHIVES[target_platform()], 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}))
        (directory / 'receipt.json').chmod(0o600)
        return BetterleaksScanner(directory)

    def test_raw_tool_fields_and_environment_never_escape(self):
        scanner = self.detector('''import json,sys,os
assert '--validation=false' in sys.argv
assert '--unsafe-auto-load-config=false' in sys.argv
assert '--ignore-gitleaks-allow' in sys.argv
assert '--redact=100' in sys.argv
assert 'GITLEAKS_CONFIG' not in os.environ and 'XTI_GITHUB_TOKEN' not in os.environ
content=sys.stdin.read()
print(json.dumps([{'RuleID':'fixture','StartLine':1,'Secret':content,'Match':content}]))
sys.exit(23)
''')
        with patch.dict(os.environ, {'GITLEAKS_CONFIG': '/untrusted/config', 'XTI_GITHUB_TOKEN': 'never-pass-to-scanner'}):
            result = scanner.scan('fake-private-body', seconds=5)
        self.assertEqual(result, [{'rule': 'fixture', 'line': 1}])
        self.assertNotIn('fake-private', json.dumps(result))

    def test_timeout_kills_process_and_output_is_not_relayed(self):
        scanner = self.detector('import time\ntime.sleep(60)\n')
        with self.assertRaises(CodeExposureError) as raised: scanner.scan('fixture', seconds=.05)
        self.assertEqual(raised.exception.code, 'scanner_timeout')

    def test_untrusted_output_size_is_bounded_and_process_reaped(self):
        scanner = self.detector("import sys\nsys.stdout.write('x' * (5*1024*1024))\n")
        with self.assertRaises(CodeExposureError) as raised: scanner.scan('fixture', seconds=5)
        self.assertEqual(raised.exception.code, 'scanner_output_limit')

    def test_binary_change_or_symlink_fails_readiness(self):
        scanner = self.detector('print("[]")\n')
        self.assertEqual(scanner.status()['state'], 'ready')
        (scanner.directory / 'betterleaks').write_text('changed')
        self.assertEqual(scanner.status()['state'], 'invalid_installation')

    def test_installer_checks_archive_and_does_not_extract_extra_paths(self):
        spec = importlib.util.spec_from_file_location('xti_test_setup_code', ROOT / 'scripts/setup_code.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        target = self.root / 'managed'
        content = io.BytesIO()
        with tarfile.open(fileobj=content, mode='w:gz') as tar:
            for name, body in [('betterleaks', b'controlled binary'), ('LICENSE', b'MIT fixture'), ('../escape', b'no')]:
                member = tarfile.TarInfo(name); member.size = len(body); tar.addfile(member, io.BytesIO(body))
        blob = content.getvalue()
        with self.assertRaises(ValueError): module.install(target, fetch=lambda _: blob)
        self.assertFalse(target.exists())
        with patch.dict(ARCHIVES, {target_platform(): hashlib.sha256(blob).hexdigest()}):
            self.assertEqual(module.install(target, fetch=lambda _: blob)['state'], 'ready')
            self.assertEqual(module.install(target, fetch=lambda _: self.fail('second download'))['state'], 'ready')
        self.assertFalse((self.root / 'escape').exists())
        self.assertEqual((target / 'betterleaks').stat().st_mode & 0o777, 0o700)

    def test_installed_real_tool_synthetic_positive_and_negative(self):
        scanner = BetterleaksScanner()
        if scanner.status()['state'] != 'ready': self.skipTest('Pinned native detector not installed in this test environment')
        token = 'ghp_' + 'aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5'
        self.assertIn('github-pat', [r['rule'] for r in scanner.scan('api_key="' + token + '"', seconds=10)])
        self.assertEqual(scanner.scan('example.com\nAPI_KEY = os.environ["API_KEY"]', seconds=10), [])


if __name__ == '__main__': unittest.main()
