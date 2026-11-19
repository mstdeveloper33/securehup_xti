"""Provider protocol and hostile responses without paid requests or real network."""
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from xti.adapters.brightdata_credentials import load_key, save_key, daily_limit
from xti.adapters.brightdata_social import BrightDataSocialProvider, DATASET, MAX_BYTES, NoRedirects, ProviderError
from xti.domain.assets import ValidationError

KEY = 'brightdata-test-' + 'x' * 32
SNAPSHOT = 'sd_test_collection'
URL = 'https://linkedin.com/company/acme'
DOMAIN = 'acme.example'
AT = '2026-11-19T12:00:00+00:00'


def raw_record(**changes):
    return {'url': URL, 'id': 'acme', 'company_id': '12345', 'name': 'Acme',
            'website': 'https://acme.example/', 'about': 'Public company description.', **changes}


class Response(BytesIO):
    def __init__(self, value=None, *, body=None, status=200, headers=None, url=None):
        body = body if body is not None else json.dumps(value).encode()
        super().__init__(body)
        self.status, self.url = status, url
        self.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(body)), **(headers or {})}

    def geturl(self): return self.url


class HttpTests(unittest.TestCase):
    def provider(self, *responses):
        queue = list(responses)
        self.requests = []
        def open_request(request, timeout):
            self.requests.append(request)
            result = queue.pop(0)
            if isinstance(result, BaseException): raise result
            if result.url is None: result.url = request.full_url
            return result
        self.opener = Mock(open=Mock(side_effect=open_request))
        return BrightDataSocialProvider(key_loader=lambda: KEY, opener=self.opener, clock=lambda: AT)

    def progress(self, status='ready', **changes):
        return Response({'snapshot_id': SNAPSHOT, 'dataset_id': DATASET, 'status': status, **changes})

    def test_submit_has_fixed_endpoint_one_post_and_bounded_input_without_extra_products(self):
        provider = self.provider(Response({'snapshot_id': SNAPSHOT}))
        self.assertEqual(provider.submit([URL]), SNAPSHOT)
        request = self.requests[0]
        parsed = urlsplit(request.full_url)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ('https', 'api.brightdata.com', '/datasets/v3/trigger'))
        self.assertEqual(parse_qs(parsed.query), {'dataset_id': [DATASET], 'format': ['json'],
            'include_errors': ['true'], 'notify': ['false'], 'limit_multiple_results': ['1'],
            'custom_output_fields': ['url|id|company_id|name|website|about']})
        self.assertEqual(json.loads(request.data), {'input': [{'url': URL}], 'limit_per_input': 1})
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + KEY)
        self.assertNotIn(KEY, request.full_url + request.data.decode())
        self.assertEqual(self.opener.open.call_count, 1)

    def test_pending_refresh_uses_only_one_get(self):
        provider = self.provider(self.progress('running'))
        state = provider.collect(SNAPSHOT, [URL], DOMAIN)
        self.assertEqual(state['status'], 'pending')
        self.assertEqual([r.get_method() for r in self.requests], ['GET'])

    def test_ready_refresh_binds_record_and_domain_without_claiming_ownership(self):
        provider = self.provider(self.progress(), Response([raw_record(employees=[{'name': 'Do not retain'}])]))
        state = provider.collect(SNAPSHOT, [URL], DOMAIN)
        self.assertEqual(state['status'], 'complete')
        row = state['profiles'][0]
        self.assertEqual(row['state'], 'provider_supported')
        self.assertEqual(row['brand_relation'], 'provider_website_matches_domain')
        self.assertNotIn('employees', row['evidence'])
        self.assertNotIn('Do not retain', json.dumps(state))
        self.assertEqual([r.get_method() for r in self.requests], ['GET', 'GET'])
        self.assertEqual(parse_qs(urlsplit(self.requests[-1].full_url).query), {'format': ['json']})

    def test_numeric_input_can_bind_to_slug_only_with_matching_provider_company_id(self):
        target = 'https://linkedin.com/company/12345'
        provider = self.provider(self.progress(), Response([raw_record(url='https://tr.linkedin.com/company/acme')]))
        result = provider.collect(SNAPSHOT, [target], DOMAIN)
        self.assertEqual(result['profiles'][0]['state'], 'provider_supported')
        self.assertEqual(result['profiles'][0]['url'], target)

    def test_record_without_url_uses_explicit_provider_id_and_records_that_basis(self):
        provider = self.provider(self.progress(), Response([raw_record(url=None)]))
        row = provider.collect(SNAPSHOT, [URL], DOMAIN)['profiles'][0]
        self.assertEqual(row['state'], 'provider_supported')
        self.assertEqual(row['evidence']['url_basis'], 'provider_id')

    def test_numeric_and_named_aliases_can_share_exact_provider_identity(self):
        numeric = 'https://linkedin.com/company/12345'
        records = [raw_record(timestamp='first'), raw_record(timestamp='second')]
        state = self.provider(self.progress(), Response(records)).collect(SNAPSHOT, [numeric, URL], DOMAIN)
        self.assertEqual(state['status'], 'complete')
        self.assertEqual([r['evidence']['url'] for r in state['profiles']], [URL, URL])
        self.assertEqual(state['profiles'][0]['evidence']['record_sha256'], state['profiles'][1]['evidence']['record_sha256'])
        with self.assertRaises(ProviderError):
            self.provider(self.progress(), Response([raw_record(), raw_record(name='Different')])).collect(SNAPSHOT, [numeric, URL], DOMAIN)

    def test_input_binding_does_not_hide_different_profile_or_promote_domain_match(self):
        provider = self.provider(self.progress(), Response([raw_record(url='https://linkedin.com/company/other',
            id='other', company_id='987', input={'url': URL})]))
        result = provider.collect(SNAPSHOT, [URL], DOMAIN)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['profiles'][0]['state'], 'conflicting')
        self.assertEqual(result['profiles'][0]['brand_relation'], 'unverified')

    def test_empty_or_per_record_error_is_unknown_not_account_absence(self):
        for value in ([], [{'error': 'not found', 'input': {'url': URL}}]):
            with self.subTest(value=value):
                state = self.provider(self.progress(), Response(value)).collect(SNAPSHOT, [URL], DOMAIN)
                self.assertEqual(state['status'], 'partial')
                self.assertEqual(state['profiles'][0]['state'], 'unresolved')

    def test_source_failed_or_canceled_never_downloads_or_restarts(self):
        for status in ('failed', 'canceled'):
            with self.subTest(status=status):
                state = self.provider(self.progress(status)).collect(SNAPSHOT, [URL], DOMAIN)
                self.assertEqual(state['status'], 'failed')
                self.assertEqual(len(self.requests), 1)

    def test_dataset_snapshot_mismatch_and_unknown_status_rejected(self):
        for changes in ({'dataset_id': 'other'}, {'snapshot_id': 'sd_other'}, {'status': 'unknown'}):
            with self.subTest(changes=changes), self.assertRaises(ProviderError):
                self.provider(self.progress(**changes)).collect(SNAPSHOT, [URL], DOMAIN)
            self.assertEqual(len(self.requests), 1)

    def test_http_errors_are_sanitized_and_never_retried(self):
        for code, expected in ((401, 'auth_error'), (403, 'auth_error'), (429, 'rate_limited'),
                               (302, 'provider_unavailable'), (503, 'provider_unavailable')):
            with self.subTest(code=code):
                error = HTTPError('https://api.brightdata.com/', code, KEY, {}, BytesIO(KEY.encode()))
                with self.assertRaises(ProviderError) as raised:
                    self.provider(error).submit([URL])
                self.assertEqual(str(raised.exception), expected)
                self.assertEqual(len(self.requests), 1)
        with self.assertRaises(ProviderError) as raised:
            self.provider(URLError(KEY)).submit([URL])
        self.assertEqual(str(raised.exception), 'transport_error')

    def test_host_redirect_size_encoding_json_and_secret_reflection_rejected(self):
        for response in (
            Response({'snapshot_id': SNAPSHOT}, url='https://other.example/'),
            Response({}, headers={'Content-Length': str(MAX_BYTES + 1)}),
            Response({}, headers={'Content-Length': '1'}),
            Response({}, headers={'Content-Type': 'text/html'}),
            Response({}, headers={'Content-Encoding': 'gzip'}),
            Response(body=b'{"snapshot_id":"sd_a","snapshot_id":"sd_b"}'),
            Response(body=b'{"snapshot_id":NaN}'),
            Response(body=b'[' * 2000 + b']' * 2000),
            Response({'snapshot_id': SNAPSHOT, 'secret': KEY}),
            Response(body=('{"secret":"' + ''.join('\\u%04x' % ord(c) for c in KEY) + '"}').encode()),
        ):
            with self.subTest(response=response), self.assertRaises(ProviderError) as raised:
                self.provider(response).submit([URL])
            self.assertNotIn(KEY, str(raised.exception))
        self.assertIsNone(NoRedirects().redirect_request(None, None, 302, '', {}, 'https://other.example'))

    def test_unbound_duplicate_or_invalid_provider_records_are_rejected(self):
        for records in ([raw_record(url='https://evil.example/company/acme')],
                        [raw_record(url='https://linkedin.com/in/acme')],
                        [raw_record(id='')], [raw_record(website='https://user:pass@example.com')],
                        [raw_record(name=12)], [raw_record(), raw_record()],
                        [raw_record(url='https://linkedin.com/company/other', id='other', company_id='987')]):
            with self.subTest(records=records), self.assertRaises(ProviderError):
                self.provider(self.progress(), Response(records)).collect(SNAPSHOT, [URL], DOMAIN)

    def test_invalid_snapshot_or_targets_never_contact_api(self):
        provider = self.provider()
        for value in ('../secret', 'sd_a?token=secret', '', 'https://evil.example'):
            with self.subTest(value=value), self.assertRaises(ValidationError): provider.collect(value, [URL], DOMAIN)
        for targets in ([], [URL, URL], ['https://linkedin.com/in/person'], ['https://localhost/company/a']):
            with self.subTest(targets=targets), self.assertRaises(ValidationError): provider.submit(targets)
        self.assertEqual(self.requests, [])

    def test_undeclared_body_size_and_total_read_deadline_are_enforced(self):
        oversized = Response(body=b' ' * (MAX_BYTES + 1), headers={'Content-Length': None})
        with self.assertRaises(ProviderError) as error:
            self.provider(oversized).submit([URL])
        self.assertEqual(error.exception.code, 'invalid_response')
        provider = self.provider(Response({'snapshot_id': SNAPSHOT}))
        provider._monotonic = Mock(side_effect=[0, 0, 21])
        with self.assertRaises(ProviderError) as error: provider.submit([URL])
        self.assertEqual(error.exception.code, 'transport_error')
        self.assertEqual(len(self.requests), 1)


class CredentialTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.enterContext(patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.root)}, clear=True))

    def test_private_atomic_save_load_and_no_overwrite_under_permissive_umask(self):
        previous = os.umask(0o002)
        try: path = save_key(KEY)
        finally: os.umask(previous)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(load_key(), KEY)
        with self.assertRaises(ValidationError): save_key('other-' + KEY)
        self.assertEqual(load_key(), KEY)
        self.assertEqual(list(path.parent.glob('.brightdata-*')), [])

    def test_environment_precedence_missing_invalid_and_symlink_permissions(self):
        with self.assertRaises(ValidationError): load_key()
        path = save_key(KEY)
        with patch.dict(os.environ, {'BRIGHTDATA_API_KEY': 'other-' + KEY}):
            self.assertEqual(load_key(), 'other-' + KEY)
            self.assertEqual(load_key(path), KEY)
        link = self.root / 'link'; link.symlink_to(path)
        with self.assertRaises(ValidationError): load_key(link)
        path.chmod(0o644)
        with self.assertRaises(ValidationError): load_key(path)
        for value in ('', 'short', KEY + '\n', KEY + ' '):
            with patch.dict(os.environ, {'BRIGHTDATA_API_KEY': value}), self.assertRaises(ValidationError): load_key()

    def test_admin_limit_validates_without_network_or_account_access(self):
        self.assertEqual(daily_limit(), 50)
        for value in ('0', '-1', '1.5', '50001', 'true'):
            with patch.dict(os.environ, {'XTI_BRIGHTDATA_DAILY_PROFILE_LIMIT': value}), self.assertRaises(ValidationError): daily_limit()

    def test_temporary_name_collision_never_deletes_an_existing_file(self):
        destination = self.root / 'xti' / 'brightdata.key'
        destination.parent.mkdir(mode=0o700)
        foreign = destination.parent / '.brightdata-collision'
        foreign.write_text('preserve me')
        with patch('xti.adapters.brightdata_credentials.secrets.token_hex', return_value='collision'), self.assertRaises(ValidationError):
            save_key(KEY)
        self.assertEqual(foreign.read_text(), 'preserve me')
        self.assertFalse(destination.exists())
