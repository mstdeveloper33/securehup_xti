from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.content_credentials import load_credential, save_credential
from xti.adapters.content_bluesky import collect_bluesky, parse_search_response, search_queries
from xti.adapters.content_discord import collect_discord
from xti.adapters.content_http import ContentHTTP
from xti.adapters.content_sources import PublicContentSources, parse_feed, _window
from xti.domain.content_monitoring import ContentDocument, ContentError, source_definition
from xti.domain.assets import ValidationError


class ContentHTTPTests(unittest.TestCase):
    def test_private_dns_never_connects_and_redirect_never_leaks_token(self):
        calls = []
        def reject(host, seconds): raise ContentError('unsafe_target', 'Controlled private DNS')
        client = ContentHTTP(resolve=reject, connect=lambda *args: calls.append(args))
        result = client.get('https://feed.example/rss', seconds=5, max_operations=2)
        self.assertEqual(result['status'], 'unsafe_target'); self.assertEqual(calls, [])
        class Response:
            status = 302
            def getheader(self, key, default=''): return 'https://other.example/rss' if key == 'Location' else default
        class Connection:
            def __init__(self, *args): pass
            def request(self, *args, **kwargs): calls.append(kwargs['headers'])
            def getresponse(self): return Response()
            def close(self): pass
        client = ContentHTTP(resolve=lambda *a: '93.184.216.34', connect=Connection)
        result = client.get('https://discord.com/api/v10/users/@me', seconds=5, max_operations=3, headers={'Authorization': 'Bot controlled-fixture'})
        self.assertEqual(result['status'], 'unsafe_redirect'); self.assertEqual(len(calls), 1)
        self.assertNotIn('controlled-fixture', repr(result))

    def test_rate_limit_preserves_request_evidence_without_body(self):
        class Response:
            status = 429
            def getheader(self, key, default=''): return '120' if key == 'Retry-After' else default
        class Connection:
            def __init__(self, *args): pass
            def request(self, *args, **kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass
        client = ContentHTTP(resolve=lambda *a: '93.184.216.34', connect=Connection)
        result = client.get('https://feed.example/rss', seconds=5, max_operations=3)
        self.assertEqual(result['status'], 'rate_limited'); self.assertEqual(result['retry_after_seconds'], 120)
        self.assertEqual(result['attempts'][0]['http_status'], 429)
        self.assertIn('started_at', result['attempts'][0]); self.assertEqual(result['body'], b'')

    def test_private_credential_files_are_workspace_scoped_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            first, second = Path(root) / 'a', Path(root) / 'b'
            value = {'token': 'fixture-' + 'a' * 30}
            path = save_credential('discord', 'default', value, directory=first)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(load_credential('discord', directory=first), value)
            self.assertIsNone(load_credential('discord', directory=second))
            with self.assertRaises(ValidationError): save_credential('discord', 'default', value, directory=first)
            path.chmod(0o644)
            with self.assertRaises(ValidationError): load_credential('discord', directory=first)
            path.chmod(0o600)
            link = first / 'discord-link.key'; link.symlink_to(path)
            with self.assertRaises(ValidationError): load_credential('discord', 'link', directory=first)


class ContentWindowTests(unittest.TestCase):
    def test_bounded_window_resumes_and_revisits_for_edits(self):
        documents = [ContentDocument(str(i), '', 'Title', str(i)) for i in range(5)]
        seen = []
        first = _window(documents, {}, 2, lambda d: seen.append(d.native_id))
        second = _window(documents, first['checkpoint'], 2, lambda d: seen.append(d.native_id))
        last = _window(documents, second['checkpoint'], 2, lambda d: seen.append(d.native_id))
        self.assertEqual(seen, ['0', '1', '2', '3', '4']); self.assertEqual(last['status'], 'complete')
        self.assertTrue(last['checkpoint']['baseline_complete'])
        again = []; _window(documents, last['checkpoint'], 2, lambda d: again.append(d.native_id))
        self.assertEqual(again, ['0', '1'])

    def test_missing_channel_credentials_are_not_empty_success(self):
        source = {'id': 'fixture', 'revision': 1, 'definition': source_definition({'provider': 'telegram', 'locator': 'example'})}
        sources = PublicContentSources(Path('/unused.db'), credentials=lambda *a: None)
        with patch('socket.socket.connect', side_effect=AssertionError('No network')):
            result = sources.collect(source, {}, {'seconds': 5, 'max_operations': 10, 'max_items': 10}, lambda d: self.fail('No document'))
        self.assertEqual(result['status'], 'missing_credentials'); self.assertEqual(result['operations'], 0)

    def test_rss_and_atom_use_real_pinned_parser_when_installed(self):
        from xti.adapters.content_sources import _version
        if _version('feedparser', '6.0.14') != 'ready': self.skipTest('Pinned feedparser absent in core-only environment')
        fixtures = [
            b'<rss version="2.0"><channel><title>Fixture</title><link>https://news.example/</link><description>Fixture</description>'
            b'<item><guid>first</guid><title>Example &amp; partners</title><link>https://news.example/1</link><description>example.com &lt;b&gt;update&lt;/b&gt;</description></item></channel></rss>',
            b'<feed xmlns="http://www.w3.org/2005/Atom"><id>urn:fixture</id><title>Fixture</title><updated>2026-11-21T00:00:00Z</updated><entry><id>first</id><title>Example &amp; partners</title><updated>2026-11-21T00:00:00Z</updated><link href="https://news.example/1"/><summary>example.com update</summary></entry></feed>',
        ]
        for body in fixtures:
            rows, skipped = parse_feed(body, 'https://news.example/rss')
            self.assertEqual(skipped, 0); self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].content, 'example.com update')
            self.assertEqual(rows[0].title, 'Example & partners')
        with self.assertRaises(ContentError): parse_feed(b'<!DOCTYPE foo [<!ENTITY test "foo">]><rss/>', 'https://news.example/rss')


class BlueskySourceTests(unittest.TestCase):
    TARGETS = (
        {'kind': 'company', 'id': 'a', 'name': 'Example Corp', 'domains': ['example.com'], 'aliases': ['Example']},
        {'kind': 'supplier', 'id': 'b', 'name': 'Supplier One', 'domains': ['supplier.example'], 'aliases': []},
    )

    @staticmethod
    def post(identifier, text):
        return {
            'uri': 'at://did:plc:abcdefghijklmnopqrstuvwx/app.bsky.feed.post/' + identifier,
            'cid': 'fixture',
            'author': {'did': 'did:plc:abcdefghijklmnopqrstuvwx', 'handle': 'fixture.example'},
            'record': {'$type': 'app.bsky.feed.post', 'text': text, 'createdAt': '2026-11-23T10:00:00Z'},
            'indexedAt': '2026-11-23T10:00:01Z',
        }

    def test_queries_are_fair_deduplicated_and_never_include_secrets_in_checkpoint(self):
        queries = search_queries(self.TARGETS)
        self.assertEqual(queries[:2], ('"Example Corp"', '"Supplier One"'))
        self.assertEqual(queries[2:4], ('example.com', 'supplier.example'))
        self.assertEqual(queries[4], 'Example')

    def test_parser_keeps_only_text_and_canonical_post_reference(self):
        body = json.dumps({'posts': [self.post('3fixture', 'Example Corp update')],
                           'cursor': 'provider-cursor', 'hitsTotal': 7}).encode()
        documents, skipped, metadata = parse_search_response(body, historical=True)
        self.assertEqual(skipped, 0); self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].content, 'Example Corp update')
        self.assertEqual(documents[0].title, 'Bluesky gönderisi')
        self.assertTrue(documents[0].historical)
        self.assertEqual(documents[0].url,
            'https://bsky.app/profile/did:plc:abcdefghijklmnopqrstuvwx/post/3fixture')
        self.assertTrue(metadata['cursor_present']); self.assertEqual(metadata['reported_hits'], 7)
        self.assertNotIn('fixture.example', repr(documents))

    def test_bounded_query_cycle_resumes_and_baseline_is_silent(self):
        class HTTP:
            def __init__(self): self.calls = []
            def get(self, url, **kwargs):
                self.calls.append(url)
                body = json.dumps({'posts': [BlueskySourceTests.post(str(len(self.calls)), 'Example Corp update')]}).encode()
                return {'status': 'complete', 'body': body, 'attempts': [{'http_status': 200}]}
        http, first_documents = HTTP(), []
        definition = source_definition({'provider': 'bluesky'})
        first = collect_bluesky(definition, {}, {'seconds': 30, 'max_operations': 1, 'max_items': 20},
                                 first_documents.append, targets=self.TARGETS, http=http)
        self.assertEqual(first['status'], 'partial'); self.assertEqual(first['queries_completed'], 1)
        self.assertEqual(first['checkpoint']['query_index'], 1)
        self.assertTrue(first_documents[0].historical)
        checkpoint = first['checkpoint']
        while not checkpoint['baseline_complete']:
            documents = []
            result = collect_bluesky(definition, checkpoint,
                {'seconds': 30, 'max_operations': 1, 'max_items': 20}, documents.append,
                targets=self.TARGETS, http=http)
            self.assertTrue(all(item.historical for item in documents))
            checkpoint = result['checkpoint']
        current = []
        result = collect_bluesky(definition, checkpoint,
            {'seconds': 30, 'max_operations': 1, 'max_items': 20}, current.append,
            targets=self.TARGETS, http=http)
        self.assertFalse(current[0].historical)
        self.assertNotIn('Example Corp', repr(result['checkpoint']))

    def test_rate_limit_is_cooldown_not_empty_success(self):
        class HTTP:
            def get(self, url, **kwargs):
                return {'status': 'rate_limited', 'body': b'', 'attempts': [{'http_status': 429}],
                        'retry_after_seconds': 120}
        result = collect_bluesky(source_definition({'provider': 'bluesky'}), {},
            {'seconds': 30, 'max_operations': 5, 'max_items': 20}, lambda _: self.fail(),
            targets=self.TARGETS, http=HTTP())
        self.assertEqual(result['status'], 'rate_limited')
        self.assertEqual(result['last_error'], 'rate_limited')
        self.assertIn('retry_at', result['checkpoint'])

    def test_official_cached_endpoint_can_fail_over_once_to_official_appview(self):
        class HTTP:
            def __init__(self): self.calls = []
            def get(self, url, **kwargs):
                self.calls.append(url)
                if url.startswith('https://public.api.bsky.app/'):
                    return {'status': 'access_denied', 'body': b'', 'attempts': [{'http_status': 403}]}
                return {'status': 'complete', 'body': json.dumps({'posts': [
                    BlueskySourceTests.post('3fallback', 'Example Corp update')]}).encode(),
                    'attempts': [{'http_status': 200}]}
        http, rows = HTTP(), []
        result = collect_bluesky(source_definition({'provider': 'bluesky'}), {},
            {'seconds': 30, 'max_operations': 4, 'max_items': 10}, rows.append,
            targets=({'kind': 'company', 'id': 'a', 'name': 'Example Corp', 'domains': [], 'aliases': []},),
            http=http)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['operations'], 2)
        self.assertTrue(result['endpoint_fallback_used'])
        self.assertEqual(result['checkpoint']['endpoint'], 'api')
        self.assertEqual(len(http.calls), 2)
        self.assertTrue(http.calls[1].startswith('https://api.bsky.app/'))

    def test_language_filter_and_target_identity_are_part_of_collection_scope(self):
        class HTTP:
            def __init__(self): self.calls = []
            def get(self, url, **kwargs):
                self.calls.append(url)
                return {'status': 'complete', 'body': json.dumps({'posts': [
                    BlueskySourceTests.post('3scope', 'Example Corp update')]}).encode(),
                    'attempts': [{'http_status': 200}]}
        http, first_rows = HTTP(), []
        definition = source_definition({'provider': 'bluesky', 'language': 'tr'})
        first_target = {'kind': 'company', 'id': 'first', 'name': 'Example Corp', 'domains': [], 'aliases': []}
        first = collect_bluesky(definition, {}, {'seconds': 30, 'max_operations': 2, 'max_items': 10},
            first_rows.append, targets=(first_target,), http=http)
        self.assertIn('lang=tr', http.calls[0]); self.assertTrue(first['checkpoint']['baseline_complete'])
        second_rows = []
        replacement = {**first_target, 'id': 'replacement'}
        second = collect_bluesky(definition, first['checkpoint'],
            {'seconds': 30, 'max_operations': 2, 'max_items': 10}, second_rows.append,
            targets=(replacement,), http=http)
        self.assertTrue(second['scope_reset'])
        self.assertTrue(second_rows[0].historical)

    def test_public_dispatch_never_requests_credentials(self):
        class HTTP:
            def get(self, url, **kwargs):
                return {'status': 'complete', 'body': json.dumps({'posts': [
                    BlueskySourceTests.post('3dispatch', 'Example Corp update')]}).encode(),
                    'attempts': [{'http_status': 200}]}
        source = {'id': 'fixture', 'revision': 1, 'definition': source_definition({'provider': 'bluesky'})}
        rows = []
        result = PublicContentSources(Path('/unused.db'), http=HTTP(),
            credentials=lambda *args: self.fail('Public Bluesky must not load credentials')).collect(
                source, {}, {'seconds': 30, 'max_operations': 5, 'max_items': 10}, rows.append,
                targets=(self.TARGETS[0],))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(rows), 1)

    def test_malformed_or_media_only_response_is_not_successful_empty(self):
        with self.assertRaises(ContentError):
            parse_search_response(b'{"posts":"wrong"}', historical=False)
        post = self.post('3media', ''); post['record']['embed'] = {'$type': 'app.bsky.embed.images'}
        documents, skipped, metadata = parse_search_response(
            json.dumps({'posts': [post]}).encode(), historical=False)
        self.assertEqual(documents, [])
        self.assertEqual(skipped, 1)
        self.assertEqual(metadata['unsupported_items'], 1)
        class HTTP:
            def get(self, url, **kwargs):
                return {'status': 'complete', 'body': json.dumps({'posts': [post]}).encode(),
                        'attempts': [{'http_status': 200}]}
        result = collect_bluesky(source_definition({'provider': 'bluesky'}), {},
            {'seconds': 30, 'max_operations': 2, 'max_items': 10}, lambda _: self.fail(),
            targets=({'kind': 'company', 'id': 'a', 'name': 'Example', 'domains': [], 'aliases': []},),
            http=HTTP())
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['unsupported_items'], 1)
        malformed = self.post('3bad', 'text'); malformed['record']['createdAt'] = 'not-a-date'
        with self.assertRaises(ContentError):
            parse_search_response(json.dumps({'posts': [malformed]}).encode(), historical=False)


class DiscordTests(unittest.TestCase):
    def fixture(self, *, flags=1 << 19, permissions=(1 << 10) | (1 << 16), rows=None):
        guild, channel, bot = '123456789', '223456789', '323456789'
        data = [{'id': bot, 'bot': True}, {'flags': flags}, {'id': channel, 'guild_id': guild, 'type': 0, 'permission_overwrites': []},
                {'roles': []}, [{'id': guild, 'permissions': str(permissions)}], rows or []]
        class HTTP:
            def __init__(self): self.calls = []
            def get(self, url, **kwargs):
                self.calls.append(url)
                return {'status': 'complete', 'body': json.dumps(data.pop(0)).encode(), 'attempts': [{'http_status': 200}]}
        return HTTP(), {'locator': guild + '/' + channel}

    def test_content_permission_absence_is_not_empty_success(self):
        http, definition = self.fixture(flags=0)
        result = collect_discord(definition, {'token': 'fixture'}, {}, {'seconds': 5, 'max_operations': 10, 'max_items': 10}, lambda d: self.fail(), http=http)
        self.assertEqual(result['status'], 'content_permission_missing'); self.assertEqual(len(http.calls), 2)

    def test_history_permission_absence_blocks_before_read(self):
        http, definition = self.fixture(permissions=1 << 10)
        result = collect_discord(definition, {'token': 'fixture'}, {}, {'seconds': 5, 'max_operations': 10, 'max_items': 10}, lambda d: self.fail(), http=http)
        self.assertEqual(result['status'], 'history_permission_missing'); self.assertEqual(len(http.calls), 5)

    def test_empty_success_only_after_permissions_and_message_scope_verified(self):
        http, definition = self.fixture()
        result = collect_discord(definition, {'token': 'fixture'}, {}, {'seconds': 5, 'max_operations': 10, 'max_items': 10}, lambda d: self.fail(), http=http)
        self.assertEqual(result['status'], 'complete'); self.assertEqual(result['items'], 0)
        self.assertEqual(len(http.calls), 6); self.assertTrue(result['checkpoint']['baseline_complete'])
        self.assertTrue(all(url.startswith('https://discord.com/api/v10/') for url in http.calls))

    def test_text_message_has_no_author_profile_or_attachment_content(self):
        row = {'id': '423456789', 'channel_id': '223456789', 'content': 'example.com news',
               'timestamp': '2026-11-21T00:00:00Z', 'edited_timestamp': None, 'author': {'username': 'private-author'},
               'attachments': [{'url': 'https://files.example/secret'}]}
        http, definition = self.fixture(rows=[row]); documents = []
        result = collect_discord(definition, {'token': 'fixture'}, {}, {'seconds': 5, 'max_operations': 10, 'max_items': 10}, documents.append, http=http)
        self.assertEqual(result['status'], 'complete'); self.assertEqual(documents[0].content, 'example.com news')
        self.assertNotIn('private-author', repr(documents)); self.assertFalse(result['attachments_checked'])


if __name__ == '__main__': unittest.main()
