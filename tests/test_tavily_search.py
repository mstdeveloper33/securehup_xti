"""Bounded Tavily transport, single-credit request controls and private credentials."""

from dataclasses import replace
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import tempfile
import traceback
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from xti.adapters.tavily_search import (
    TAVILY_SEARCH_URL, TavilySearchSource, default_tavily_key_path,
    load_tavily_api_key, save_tavily_api_key,
)
from xti.domain.assets import ValidationError
from xti.domain.mentions import MentionRequest, build_query, company_target
from xti.ports.discovery import SourceError


KEY = "tvly-test-" + "x" * 32
OTHER_KEY = "tvly-test-" + "y" * 32
REQUEST = MentionRequest(company_target("Example Company", ("example.com",)), "general", 5)


def reply(**changes):
    value = {
        "query": build_query(REQUEST.target),
        "request_id": "request-123",
        "usage": {"credits": 1},
        "results": [{"url": "https://publisher.example/article", "title": "Example Company notice",
                     "content": "A short report about example.com", "score": 0.81,
                     "published_date": "Tue, 11 Nov 2026 17:00:00 GMT"}],
    }
    value.update(changes)
    return value


class Response(BytesIO):
    def __init__(self, value=None, *, body=None, code=200, url=TAVILY_SEARCH_URL, headers=None):
        if body is None:
            body = json.dumps(value if value is not None else reply()).encode()
        super().__init__(body)
        self.code, self.url = code, url
        self.headers = headers if headers is not None else {
            "Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(body)),
        }

    def getcode(self):
        return self.code

    def geturl(self):
        return self.url


class TavilyHttpTests(unittest.TestCase):
    def test_one_post_uses_basic_search_and_explicitly_disables_cost_expansion(self):
        opener = Mock(return_value=Response())
        result = TavilySearchSource(KEY, opener=opener).fetch(REQUEST)
        self.assertEqual(opener.call_count, 1)
        outgoing = opener.call_args.args[0]
        self.assertEqual(outgoing.full_url, TAVILY_SEARCH_URL)
        self.assertEqual(outgoing.get_method(), "POST")
        self.assertEqual(outgoing.get_header("Authorization"), "Bearer " + KEY)
        self.assertEqual(outgoing.get_header("Accept-encoding"), "identity")
        body = json.loads(outgoing.data)
        self.assertEqual(body, {
            "query": build_query(REQUEST.target), "topic": "general", "max_results": 5,
            "search_depth": "basic", "auto_parameters": False,
            "include_answer": False, "include_raw_content": False, "include_images": False,
            "include_published_date": True, "include_usage": True,
        })
        self.assertNotIn(KEY, outgoing.data.decode())
        self.assertEqual(result.request_id, "request-123")
        self.assertEqual(result.credits, 1)
        self.assertEqual(result.hits[0].score, 0.81)
        self.assertEqual(result.hits[0].published_at, "Tue, 11 Nov 2026 17:00:00 GMT")

    def test_news_topic_is_forwarded_and_result_pages_are_never_opened(self):
        response = reply()
        response["results"][0]["url"] = "https://publisher.example/a"
        response["results"][0]["raw_content"] = "Ignored full page content"
        response["answer"] = "Ignored generated answer"
        opener = Mock(return_value=Response(response))
        result = TavilySearchSource(KEY, opener=opener).fetch(replace(REQUEST, topic="news"))
        self.assertEqual(json.loads(opener.call_args.args[0].data)["topic"], "news")
        self.assertEqual(opener.call_count, 1)
        self.assertNotIn("Ignored", repr(result))

    def test_empty_valid_results_preserve_unknown_usage_and_dates(self):
        empty = reply(results=[], usage=None, request_id=None)
        result = TavilySearchSource(KEY, opener=Mock(return_value=Response(empty))).fetch(REQUEST)
        self.assertEqual(result.hits, ())
        self.assertIsNone(result.credits)
        item = reply()
        item["results"][0].pop("published_date")
        item["results"][0].pop("score")
        result = TavilySearchSource(KEY, opener=Mock(return_value=Response(item))).fetch(REQUEST)
        self.assertIsNone(result.hits[0].published_at)
        self.assertIsNone(result.hits[0].score)

    def test_untrusted_text_is_printable_and_summary_truncation_is_explicit(self):
        value = reply()
        value["results"][0]["title"] = " Example\nCompany\x1b notice "
        value["results"][0]["content"] = "x" * 2001
        result = TavilySearchSource(KEY, opener=Mock(return_value=Response(value))).fetch(REQUEST)
        self.assertEqual(result.hits[0].title, "Example Company notice")
        self.assertEqual(len(result.hits[0].summary), 2000)
        self.assertTrue(result.hits[0].summary_truncated)

    def test_invalid_key_and_request_fail_before_network(self):
        opener = Mock()
        for key in (None, "", "tiny", KEY + "\n", KEY + "\rHeader: bad", "ş" * 32, "x" * 513):
            with self.subTest(key_type=type(key).__name__), self.assertRaises(ValidationError):
                TavilySearchSource(key, opener=opener)
        for request in (None, replace(REQUEST, topic="invalid"), replace(REQUEST, max_results=21),
                        replace(REQUEST, max_results=True)):
            with self.subTest(request=request), self.assertRaises(ValidationError):
                TavilySearchSource(KEY, opener=opener).fetch(request)
        opener.assert_not_called()

    def test_credentials_cannot_enter_queries_or_returned_evidence(self):
        opener = Mock()
        with self.assertRaises(ValidationError):
            TavilySearchSource(KEY, opener=opener).fetch(MentionRequest(company_target(KEY), "general", 5))
        opener.assert_not_called()
        for field in ("title", "content", "published_date", "url"):
            value = reply()
            value["results"][0][field] = "https://publisher.example/" + KEY if field == "url" else KEY
            with self.subTest(field=field), self.assertRaises(SourceError) as caught:
                TavilySearchSource(KEY, opener=Mock(return_value=Response(value))).fetch(REQUEST)
            self.assertNotIn(KEY, "".join(traceback.format_exception(caught.exception)))
        with self.assertRaises(SourceError):
            TavilySearchSource(KEY, opener=Mock(return_value=Response(reply(request_id=KEY)))).fetch(REQUEST)

    def test_source_errors_are_safe_and_never_retried(self):
        for code in (301, 302, 400, 401, 402, 403, 422, 429, 432, 433, 434, 500):
            with self.subTest(code=code):
                error = HTTPError(TAVILY_SEARCH_URL, code, KEY, {}, BytesIO(KEY.encode()))
                opener = Mock(side_effect=error)
                with self.assertRaises(SourceError) as caught:
                    TavilySearchSource(KEY, opener=opener).fetch(REQUEST)
                self.assertEqual(opener.call_count, 1)
                self.assertNotIn(KEY, "".join(traceback.format_exception(caught.exception)))
        for error in (URLError(KEY), TimeoutError(KEY), OSError(KEY)):
            opener = Mock(side_effect=error)
            with self.assertRaises(SourceError) as caught:
                TavilySearchSource(KEY, opener=opener).fetch(REQUEST)
            self.assertIn("bilinmiyor", str(caught.exception))
            self.assertNotIn(KEY, "".join(traceback.format_exception(caught.exception)))
            self.assertEqual(opener.call_count, 1)

    def test_redirect_handler_and_proxy_policy_prevent_secret_forwarding(self):
        factory = Mock()
        with patch("xti.adapters.tavily_search.build_opener", factory):
            TavilySearchSource(KEY)
        proxy, redirect = factory.call_args.args
        self.assertEqual(proxy.proxies, {})
        self.assertIsNone(redirect.redirect_request(None, None, 302, "Moved", {}, "https://other.invalid/"))

    def test_unexpected_http_shapes_do_not_become_empty_success(self):
        responses = [Response(code=302), Response(url="https://other.invalid/"),
            Response(headers={"Content-Type": "text/html"}),
            Response(headers={"Content-Type": "application/json", "Content-Encoding": "gzip"}),
            Response(headers={"Content-Type": "application/json", "Content-Length": "invalid"}),
            Response(headers={"Content-Type": "application/json", "Content-Length": "0"}),
            Response(headers={"Content-Type": "application/json", "Content-Length": "2"}),
            Response(headers={"Content-Type": "application/json", "Content-Length": "3000000"})]
        for response in responses:
            with self.subTest(headers=response.headers), self.assertRaises(SourceError):
                TavilySearchSource(KEY, opener=Mock(return_value=response)).fetch(REQUEST)

    def test_oversized_body_and_read_deadline_fail_without_second_request(self):
        opener = Mock(return_value=Response(headers={"Content-Type": "application/json"}))
        with patch("xti.adapters.tavily_search.MAX_RESPONSE_BYTES", 20), self.assertRaises(SourceError):
            TavilySearchSource(KEY, opener=opener).fetch(REQUEST)
        self.assertEqual(opener.call_count, 1)
        for times in ([0, 46], [0, 1, 46]):
            opener = Mock(return_value=Response())
            with self.assertRaisesRegex(SourceError, "süresi"):
                TavilySearchSource(KEY, opener=opener, monotonic=Mock(side_effect=times)).fetch(REQUEST)
            self.assertEqual(opener.call_count, 1)

    def test_malformed_json_and_invalid_results_fail_as_whole_response(self):
        bodies = [b"", b"<html>blocked</html>", b"\xff", b"[]", b"{}",
                  b'{"query":"x","query":"x"}', b"[" * 1100 + b"]" * 1100]
        values = [reply(query="a different company"), reply(results=None), reply(results=[None]),
                  reply(results=[reply()["results"][0]] * 6), reply(usage={}),
                  reply(usage={"credits": True}), reply(usage={"credits": -1}),
                  reply(usage={"credits": 1.5}), reply(request_id="x" * 129)]
        for field, values_for_field in {
            "url": ["file:///tmp/private", "http://user:password@example.com/", "javascript:bad", None],
            "title": ["", "x" * 501, None],
            "score": [True, float("nan"), float("inf"), -0.1, 1.1, "0.9"],
            "published_date": ["x" * 129, 123],
        }.items():
            for invalid in values_for_field:
                value = reply()
                value["results"][0][field] = invalid
                values.append(value)
        duplicate = reply()
        duplicate["results"].append(dict(duplicate["results"][0]))
        values.append(duplicate)
        bodies.extend(json.dumps(value).encode() for value in values)
        for body in bodies:
            with self.subTest(body=body[:75]), self.assertRaises(SourceError):
                TavilySearchSource(KEY, opener=Mock(return_value=Response(body=body))).fetch(REQUEST)


class TavilyKeyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def private_file(self, content=KEY, name="tavily.key"):
        path = self.root / name
        path.write_text(content + "\n", encoding="utf-8")
        path.chmod(0o600)
        return path

    def test_explicit_file_then_environment_then_default_configuration(self):
        explicit = self.private_file()
        default = self.private_file(OTHER_KEY, name="default.key")
        with patch.dict(os.environ, {"TAVILY_API_KEY": OTHER_KEY}), \
             patch("xti.adapters.tavily_search.default_tavily_key_path", return_value=default):
            self.assertEqual(load_tavily_api_key(explicit), KEY)
            self.assertEqual(load_tavily_api_key(), OTHER_KEY)
        with patch.dict(os.environ, {}, clear=True), \
             patch("xti.adapters.tavily_search.default_tavily_key_path", return_value=default):
            self.assertEqual(load_tavily_api_key(), OTHER_KEY)
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}), self.assertRaises(ValidationError):
            load_tavily_api_key()

    def test_default_path_uses_absolute_xdg_or_user_home(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root)}):
            self.assertEqual(default_tavily_key_path(), self.root / "xti/tavily.key")
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "relative"}), \
             patch("xti.adapters.tavily_search.Path.home", return_value=self.root):
            self.assertEqual(default_tavily_key_path(), self.root / ".config/xti/tavily.key")

    def test_reader_rejects_shared_files_symlinks_fifo_and_invalid_content(self):
        target = self.private_file()
        target.chmod(0o644)
        with self.assertRaisesRegex(ValidationError, "chmod 600"):
            load_tavily_api_key(target)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
        target.chmod(0o600)
        link = self.root / "link"
        link.symlink_to(target)
        with self.assertRaises(ValidationError):
            load_tavily_api_key(link)
        fifo = self.root / "fifo"
        os.mkfifo(fifo, 0o600)
        with self.assertRaises(ValidationError):
            load_tavily_api_key(fifo)
        for content in ("", KEY + "\nother", KEY + "\r", "ş" * 32, "x" * 514):
            target.write_text(content, encoding="utf-8")
            with self.subTest(size=len(content)), self.assertRaises(ValidationError):
                load_tavily_api_key(target)
        with self.assertRaises(ValidationError):
            load_tavily_api_key(self.root / "missing")

    def test_save_is_private_complete_and_never_overwrites_existing_files(self):
        target = self.root / "config" / "xti" / "tavily.key"
        self.assertEqual(save_tavily_api_key(KEY, target), target)
        self.assertEqual(target.read_text(), KEY + "\n")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        inode = target.stat().st_ino
        with self.assertRaisesRegex(ValidationError, "üzerine yazılmadı"):
            save_tavily_api_key(OTHER_KEY, target)
        self.assertEqual(target.read_text(), KEY + "\n")
        self.assertEqual(target.stat().st_ino, inode)
        self.assertEqual(list(target.parent.iterdir()), [target])

    def test_save_rejects_symlink_parent_and_never_publishes_partial_key(self):
        target = self.private_file()
        link = self.root / "link"
        link.symlink_to(target)
        with self.assertRaises(ValidationError):
            save_tavily_api_key(OTHER_KEY, link)
        self.assertEqual(target.read_text(), KEY + "\n")
        parent_link = self.root / "parent-link"
        parent_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValidationError):
            save_tavily_api_key(KEY, parent_link / "new.key")
        self.assertFalse((self.root / "new.key").exists())
        broken_target = self.root / "broken.key"
        with patch("xti.adapters.tavily_search.os.fsync", side_effect=OSError(KEY)), \
             self.assertRaises(ValidationError) as caught:
            save_tavily_api_key(KEY, broken_target)
        self.assertNotIn(KEY, "".join(traceback.format_exception(caught.exception)))
        self.assertFalse(broken_target.exists())
        self.assertEqual(list(self.root.glob(".tavily-key-*")), [])

    def test_missing_key_error_does_not_disclose_private_path_or_value(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": KEY + "\n"}), \
             self.assertRaises(ValidationError) as caught:
            load_tavily_api_key()
        self.assertNotIn(KEY, str(caught.exception))
        with self.assertRaises(ValidationError) as caught:
            load_tavily_api_key(self.root / KEY)
        self.assertNotIn(KEY, "".join(traceback.format_exception(caught.exception)))


if __name__ == "__main__":
    unittest.main()
