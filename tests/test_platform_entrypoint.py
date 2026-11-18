"""Cold-process platform dispatch keeps the full parser's scope fences."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from xti.interfaces.cli import main as full_main
from xti.interfaces.entrypoint import main


class PlatformEntrypointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.args = ['platform', 'request', '--root', str(self.root / 'companies'), '--company', 'missing']

    def invoke(self, function, args):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', StringIO('{}')):
            try:
                code = function(args)
            except SystemExit as error:
                code = error.code
        return code, out.getvalue(), err.getvalue()

    def test_root_flag_abbreviations_and_invalid_syntax_preserve_protocol_and_scope(self):
        for args in (
            self.args, ['--json', *self.args], ['--j', *self.args],
            ['--data-dir', str(self.root / 'private'), *self.args],
            ['--data=' + str(self.root / 'private'), *self.args],
            ['--d', 'platform', *self.args], ['--json=yes', *self.args],
            ['--unknown', *self.args], [*self.args, '--json'],
            ['platform'], ['platform', 'request'], ['platform', 'invalid'],
            ['--', *self.args], ['--data-dir', 'platform', 'doctor'],
        ):
            with self.subTest(args=args):
                self.assertEqual(self.invoke(main, args), self.invoke(full_main, args))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_help_and_version_match_existing_cli(self):
        for args in (['--version'], ['--help'], ['platform', '--help'], ['platform', 'request', '--help']):
            with self.subTest(args=args):
                self.assertEqual(self.invoke(main, args), self.invoke(full_main, args))

    def test_platform_read_is_cold_and_does_not_load_terminal_collectors(self):
        # A real fresh interpreter, not a sys.modules check in a warmed suite.
        program = '''
import json,sys
from unittest.mock import patch
from xti.interfaces.entrypoint import main
with patch("socket.socket.connect", side_effect=AssertionError("no network")), patch("socket.getaddrinfo", side_effect=AssertionError("no DNS")):
    code = main(sys.argv[1:])
assert code == 0
assert "xti.interfaces.cli" not in sys.modules
assert "xti.adapters.maigret_username" not in sys.modules
assert "xti.adapters.nmap_scan" not in sys.modules
'''
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'),
                           PYTHONDONTWRITEBYTECODE='1', XTI_DATA_DIR=str(self.root / 'trap'))
        provision = ['platform', 'provision', '--root', str(self.root / 'companies'), '--company', 'alpha']
        self.assertEqual(self.invoke(main, provision)[0], 0)
        request = ['platform', 'request', '--root', str(self.root / 'companies'), '--company', 'alpha', '--describe']
        result = subprocess.run([sys.executable, '-c', program, *request], env=environment,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['scope']['company_id'], 'alpha')
        self.assertFalse((self.root / 'trap').exists())
