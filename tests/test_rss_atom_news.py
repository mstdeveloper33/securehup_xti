"""Real pinned parser with synthetic publisher feeds; no test network access."""

from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from xti.adapters.rss_atom_news import RssAtomNewsSource, parse_news_feed
from xti.domain.assets import ValidationError
from xti.domain.news import article_json, articles_json, articles_from_json, news_source
from xti.ports.discovery import SourceError


NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


def rss_item(identifier="entry-1", title="Example company notice", summary="Publisher summary", date=True):
    published = "<pubDate>Sat, 14 Nov 2026 15:30:00 +0300</pubDate>" if date else ""
    return (f'<item><guid isPermaLink="false">{identifier}</guid><title>{title}</title>'
            f'<link>https://example.com/news/{identifier}</link><description><![CDATA[{summary}]]></description>'
            f'{published}</item>')


def rss(*items):
    return ('<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel>'
            '<title>Example publisher</title><link>https://example.com/</link><description>News</description>'
            + ''.join(items) + '</channel></rss>').encode()


ATOM = b'''<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://example.com/">
  <id>urn:example:feed</id><title>Example publisher</title><updated>2026-11-15T10:00:00Z</updated>
  <entry><id>urn:example:one</id><title type="html">Company &amp;lt;b&amp;gt;news&amp;lt;/b&amp;gt;</title>
    <link rel="alternate" href="/article/1"/><summary type="html">A &lt;strong&gt;short&lt;/strong&gt; summary</summary>
    <published>2026-11-14T15:00:00+03:00</published><updated>2026-11-15T10:00:00Z</updated>
  </entry>
</feed>'''


def parse(body, source="cisa"):
    return parse_news_feed(body, source_key=source, fetched_at=NOW)


class Response(BytesIO):
    def __init__(self, body, *, headers=None, code=200, url=None):
        super().__init__(body)
        self.headers = headers if headers is not None else {
            "Content-Type": "application/rss+xml", "Content-Length": str(len(body)),
        }
        self.code, self.url = code, url or news_source("cisa").url

    def getcode(self):
        return self.code

    def geturl(self):
        return self.url


class NewsParsingTests(unittest.TestCase):
    def test_rss_preserves_native_identity_dates_and_publisher_attribution(self):
        feed = parse(rss(rss_item()))
        article = feed.articles[0]
        self.assertEqual(article.source_entry_id, "entry-1")
        self.assertEqual(article.published_at, "2026-11-14T12:30:00+00:00")
        self.assertEqual(article.published_raw, "Sat, 14 Nov 2026 15:30:00 +0300")
        self.assertIsNone(article.updated_at)
        self.assertIsNone(article.updated_raw)
        self.assertEqual(feed.fetched_at, NOW.isoformat())
        self.assertEqual(article.source_key, "cisa")
        self.assertEqual(article.url, "https://example.com/news/entry-1")

    def test_atom_relative_links_and_distinct_published_updated_dates(self):
        article = parse(ATOM).articles[0]
        self.assertEqual(article.source_entry_id, "urn:example:one")
        self.assertEqual(article.url, "https://example.com/article/1")
        self.assertEqual(article.summary, "A short summary")
        self.assertEqual(article.published_at, "2026-11-14T12:00:00+00:00")
        self.assertEqual(article.updated_at, "2026-11-15T10:00:00+00:00")

    def test_only_stream_input_reaches_parser_and_no_file_url_or_enclosure_is_opened(self):
        import feedparser
        wrapped = Mock(wraps=feedparser.parse)
        body = rss(rss_item(summary='<img src="http://127.0.0.1/private">Text')).replace(
            b'</item>', b'<enclosure url="file:///etc/passwd" type="text/plain" length="100"/></item>')
        with patch('xti.adapters.rss_atom_news._parser', return_value=type('Parser', (), {'parse': wrapped})), \
             patch('builtins.open', side_effect=AssertionError('Unexpected file read')), \
             patch('socket.socket', side_effect=AssertionError('Unexpected network')):
            article = parse(body).articles[0]
        self.assertIsInstance(wrapped.call_args.args[0], BytesIO)
        self.assertEqual(article.summary, 'Text')
        self.assertNotIn('127.0.0.1', article_json(article))
        self.assertNotIn('/etc/passwd', article_json(article))

    def test_missing_and_unparseable_dates_remain_unknown_instead_of_collection_time(self):
        body = rss(rss_item(date=False))
        article = parse(body).articles[0]
        self.assertIsNone(article.published_at)
        self.assertIsNone(article.published_raw)
        article = parse(body.replace(b'</item>', b'<pubDate>unknown publisher date</pubDate></item>')).articles[0]
        self.assertIsNone(article.published_at)
        self.assertEqual(article.published_raw, 'unknown publisher date')

    def test_summaries_are_plain_bounded_and_explicit_about_truncation(self):
        article = parse(rss(rss_item(summary='<p>Hello</p><script>private script text</script><p>World</p>'))).articles[0]
        self.assertEqual(article.summary, 'Hello World')
        long = parse(rss(rss_item(summary='x' * 2001))).articles[0]
        self.assertEqual(len(long.summary), 2000)
        self.assertTrue(long.summary_truncated)
        self.assertFalse(article.summary_truncated)

    def test_duplicate_reordered_and_source_qualified_identities(self):
        a, b = rss_item('a'), rss_item('b')
        first = parse(rss(a, b))
        reordered = parse(rss(b, a, a))
        self.assertEqual(first.articles, reordered.articles)
        self.assertNotEqual(first.content_sha256, reordered.content_sha256)
        other = parse(rss(a), source='ncsc')
        self.assertNotEqual(first.articles[0].id, other.articles[0].id)
        with self.assertRaises(SourceError):
            parse(rss(a, rss_item('a', title='Different article')))

    def test_missing_guid_uses_article_url_and_valid_empty_feed_is_successful(self):
        body = rss(rss_item()).replace(b'<guid isPermaLink="false">entry-1</guid>', b'')
        article = parse(body).articles[0]
        self.assertEqual(article.source_entry_id, article.url)
        self.assertEqual(parse(rss()).articles, ())

    def test_malformed_html_dtd_entities_and_oversized_fields_fail_closed(self):
        invalid = [b'<html><body>Blocked</body></html>', b'<rss version="2.0"/>',
            b'<?xml version="1.0" encoding="x-unknown-encoding"?><rss version="2.0"><channel/></rss>',
            rss(rss_item())[:-10], rss(rss_item(title='x' * 501)),
            rss(rss_item()).replace(b'https://example.com/news/entry-1', b'javascript:alert(1)'),
            b'<!DOCTYPE rss [<!ENTITY a "EXPANDED">]><rss version="2.0"><channel/></rss>',
            '<!DOCTYPE rss [<!ENTITY a "EXPANDED">]><rss version="2.0"><channel/></rss>'.encode('utf-16')]
        for body in invalid:
            with self.subTest(body=body[:60]), self.assertRaises(SourceError):
                parse(body)
        with patch('xti.adapters.rss_atom_news.MAX_FEED_ARTICLES', 1), self.assertRaises(SourceError):
            parse(rss(rss_item('a'), rss_item('b')))

    def test_canonical_snapshot_validates_identity_scope_and_all_metadata(self):
        feed = parse(rss(rss_item()))
        payload = articles_json('cisa', feed.articles)
        self.assertEqual(articles_from_json(payload), ('cisa', feed.articles))
        for content in (payload.replace('"policy":', '"policy":"bad","policy":'),
                        payload.replace('"summary_truncated":false', '"summary_truncated":0'),
                        payload.replace('"source_key":"cisa"', '"source_key":"ncsc"'),
                        '[' * 1100 + '0' + ']' * 1100):
            with self.assertRaises(ValidationError):
                articles_from_json(content)
        with self.assertRaises(ValidationError):
            article_json(replace(feed.articles[0], id='f' * 64))


class NewsHttpTests(unittest.TestCase):
    def test_fixed_https_get_with_no_auth_query_redirect_or_article_fetch(self):
        opener = Mock(return_value=Response(rss(rss_item())))
        feed = RssAtomNewsSource(opener=opener, clock=lambda: NOW).fetch('cisa')
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, news_source('cisa').url)
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(opener.call_count, 1)
        self.assertNotIn('Authorization', request.headers)
        self.assertEqual(feed.articles[0].source_key, 'cisa')

    def test_unknown_source_and_missing_parser_do_not_open_network(self):
        opener = Mock()
        with self.assertRaises(ValidationError):
            RssAtomNewsSource(opener=opener).fetch('https://private.invalid/')
        with patch('xti.adapters.rss_atom_news.version', return_value='0.0'), self.assertRaises(SourceError):
            RssAtomNewsSource(opener=opener).fetch('cisa')
        opener.assert_not_called()

    def test_redirect_wrong_type_truncation_compression_and_size_are_failures(self):
        body = rss(rss_item())
        responses = [Response(body, code=302), Response(body, url='https://other.invalid/'),
            Response(body, headers={'Content-Type': 'text/html'}),
            Response(body, headers={'Content-Type': 'text/xml', 'Content-Encoding': 'gzip'}),
            Response(body, headers={'Content-Type': 'text/xml', 'Content-Length': str(len(body) + 1)}),
            Response(body, headers={'Content-Type': 'text/xml', 'Content-Length': 'invalid'})]
        for response in responses:
            with self.subTest(headers=response.headers), self.assertRaises(SourceError):
                RssAtomNewsSource(opener=Mock(return_value=response), clock=lambda: NOW).fetch('cisa')
        with patch('xti.adapters.rss_atom_news.MAX_RESPONSE_BYTES', 20), self.assertRaises(SourceError):
            RssAtomNewsSource(opener=Mock(return_value=Response(body,
                headers={'Content-Type': 'text/xml'}))).fetch('cisa')

    def test_outages_429_and_read_deadline_hide_raw_details_and_do_not_retry(self):
        for error in (URLError('private secret'), HTTPError(news_source('cisa').url, 429, 'private secret', {}, None)):
            opener = Mock(side_effect=error)
            with self.assertRaises(SourceError) as caught:
                RssAtomNewsSource(opener=opener).fetch('cisa')
            self.assertNotIn('private secret', str(caught.exception))
            self.assertEqual(opener.call_count, 1)
        with self.assertRaisesRegex(SourceError, 'süresi'):
            RssAtomNewsSource(opener=Mock(return_value=Response(rss())),
                             monotonic=Mock(side_effect=[0, 46])).fetch('cisa')


if __name__ == '__main__':
    unittest.main()
