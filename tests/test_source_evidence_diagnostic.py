"""Diagnostic evidence must distinguish transport failure, backoff and success."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError


class Response(io.BytesIO):
    def __init__(self, body):
        super().__init__(body)
        self.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(body)),
                        'Set-Cookie': 'must-not-be-recorded'}

    def getcode(self):
        return 200


class SourceEvidenceDiagnosticTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('source_evidence_diagnostic',
            Path(__file__).resolve().parents[1] / 'scripts/check-source-evidence.py')
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.output = Path(root.name) / 'evidence.json'

    def run_diagnostic(self, side_effect):
        with patch('sys.argv', ['check-source-evidence.py', '--domain', 'example.com', '--output', str(self.output)]), \
                patch.object(self.helper.subprocess, 'check_output', side_effect=['a' * 40, '']), \
                patch.object(self.helper.platform, 'platform', return_value='controlled-test'), \
                patch.object(self.helper, 'build_opener') as factory, redirect_stdout(io.StringIO()):
            factory.return_value.open.side_effect = side_effect
            self.helper.main()
            return json.loads(self.output.read_text()), factory.return_value.open.call_count

    def test_exact_response_evidence_without_body_or_sensitive_headers_and_private_file(self):
        body = b'[{"id":1,"name_value":"example.com"}]'
        old = os.umask(0o002)
        try:
            result, count = self.run_diagnostic(lambda *args, **kwargs: Response(body))
        finally:
            os.umask(old)
        self.assertEqual(count, 2)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result['adapter_result']['status'], 'success')
        self.assertEqual(result['direct_result']['record_count'], 1)
        for row in result['adapter_attempts'] + result['direct_attempts']:
            self.assertEqual(row['method'], 'GET')
            self.assertEqual(row['url'], result['request_url'])
            self.assertEqual(row['http_status'], 200)
            self.assertEqual(row['bytes_read'], len(body))
            self.assertEqual(row['body_sha256'], hashlib.sha256(body).hexdigest())
            self.assertTrue(row['body_complete'])
            self.assertLessEqual(row['started_at'], row['finished_at'])
        self.assertNotIn('must-not-be-recorded', self.output.read_text())
        self.assertNotIn('name_value', self.output.read_text())

    def test_rate_limit_preserves_retry_after_and_skips_independent_probe(self):
        error = HTTPError('https://crt.sh/', 429, 'Too many requests',
                          {'Retry-After': '120', 'Set-Cookie': 'private'}, None)
        result, count = self.run_diagnostic(error)
        self.assertEqual(count, 1)
        self.assertEqual(result['adapter_result']['status'], 'failed')
        self.assertEqual(result['direct_result']['status'], 'skipped_provider_backoff')
        self.assertEqual(result['adapter_attempts'][0]['http_status'], 429)
        self.assertEqual(result['adapter_attempts'][0]['headers'], {'Retry-After': '120'})
        self.assertEqual(result['direct_attempts'], [])

    def test_network_failure_is_not_reported_as_http_failure_or_empty_success(self):
        result, count = self.run_diagnostic(URLError('DNS unavailable'))
        self.assertEqual(count, 2)
        self.assertEqual(result['adapter_result']['status'], 'failed')
        self.assertEqual(result['direct_result']['status'], 'failed')
        for row in result['adapter_attempts'] + result['direct_attempts']:
            self.assertIsNone(row['http_status'])
            self.assertEqual(row['exception_type'], 'URLError')
            self.assertNotIn('body_sha256', row)

    def test_existing_evidence_is_not_overwritten_or_followed_by_network_request(self):
        self.output.write_text('preserve original evidence')
        with patch('sys.argv', ['check-source-evidence.py', '--output', str(self.output)]), \
                patch.object(self.helper, 'build_opener') as factory:
            with self.assertRaises(FileExistsError):
                self.helper.main()
            factory.assert_not_called()
        self.assertEqual(self.output.read_text(), 'preserve original evidence')
