"""Bounded second-source preview and its offline acceptance gate."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from xti.adapters.ransomlook_ransomware import (
    MAX_RESPONSE_BYTES,
    SOURCE_URL,
    RansomLookRansomwareSource,
    parse_ransomlook_ransomware_response,
)
from xti.application.ransomlook_ransomware import RansomLookClaimService
from xti.application.ransomware_source_evaluation import (
    RansomwareSourceEvaluationService,
)
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)


def post(
    title="Example Holding", *, group="example-group",
    discovered="2026-10-30T18:00:00Z", **extra,
):
    return {
        "group_name": group, "post_title": title,
        "discovered": discovered, **extra,
    }


def content(records=None, **extra):
    payload = {"posts": [post()] if records is None else records, **extra}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


class Response:
    def __init__(self, body, *, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = {
            "Content-Type": "application/json",
            "Content-Encoding": "identity",
            "Content-Length": str(len(body)),
            **(headers or {}),
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self, limit=-1):
        return self.body if limit < 0 else self.body[:limit]


class RansomLookRansomwareTests(unittest.TestCase):
    def test_gate_selects_only_ransomlook_and_keeps_blockers_visible(self):
        report = RansomwareSourceEvaluationService().report()
        self.assertEqual(report.profile_version, "public-ransomware-source-gate-v1")
        self.assertEqual(report.selected_identifier, "ransomlook-public-posts")
        selected = [item for item in report.candidates if item.decision == "selected"]
        self.assertEqual(len(selected), 1)
        self.assertTrue(all(
            criterion.passed for criterion in selected[0].criteria if criterion.required
        ))
        candidates = {item.identifier: item for item in report.candidates}
        self.assertEqual(
            candidates["ransomwatch-archive"].decision,
            "rejected_for_current_feed",
        )
        self.assertEqual(candidates["darkfield-observer"].decision, "deferred")
        for candidate in report.candidates:
            self.assertTrue(candidate.reference_urls)
            self.assertTrue(all(
                url.startswith("https://") for url in candidate.reference_urls
            ))

    def test_parser_keeps_only_minimal_claim_fields_and_sorts_newest_first(self):
        feed = parse_ransomlook_ransomware_response(content([
            post(" Older   Name ", discovered="2026-10-29T18:00:00Z"),
            post("Newest", group="second-group"),
        ]), fetched_at=NOW)
        self.assertEqual((feed.window_days, feed.source_record_count), (7, 2))
        self.assertEqual([claim.victim for claim in feed.claims], ["Newest", "Older Name"])
        self.assertEqual(len(feed.content_sha256), 64)
        self.assertEqual(
            set(feed.claims[0].__dataclass_fields__),
            {"id", "group", "victim", "discovered_at"},
        )
        self.assertNotIn("onion", repr(feed).lower())

    def test_parser_rejects_schema_drift_duplicates_bad_times_and_oversize(self):
        base = {"posts": [post()]}
        fixtures = []
        changed = deepcopy(base)
        changed["unexpected"] = True
        fixtures.append(changed)
        changed = deepcopy(base)
        changed["posts"][0]["unexpected"] = True
        fixtures.append(changed)
        fixtures.append({"posts": [post(), post()]})
        fixtures.append({"posts": [post(discovered="2026-10-20T00:00:00Z")]})
        fixtures.append({"posts": [post(discovered="2026-10-31T00:00:00Z")]})
        fixtures.append({"posts": [post(group="bad\nname")]})
        for value in fixtures:
            with self.subTest(value=value), self.assertRaises(SourceError):
                parse_ransomlook_ransomware_response(
                    json.dumps(value).encode(), fetched_at=NOW,
                )
        with self.assertRaises(SourceError):
            parse_ransomlook_ransomware_response(
                b"x" * (MAX_RESPONSE_BYTES + 1), fetched_at=NOW,
            )
        with self.assertRaises(SourceError):
            parse_ransomlook_ransomware_response(
                b'{"posts":[],"posts":[]}', fetched_at=NOW,
            )

    def test_transport_is_fixed_bounded_and_hides_remote_detail(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(content())

        feed = RansomLookRansomwareSource(
            opener=opener, clock=lambda: NOW,
        ).fetch()
        self.assertEqual(feed.source_record_count, 1)
        request, timeout = calls[0]
        self.assertEqual((request.full_url, timeout), (SOURCE_URL, 30))
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        bad = (
            Response(content(), status=500),
            Response(content(), headers={"Content-Type": "text/html"}),
            Response(content(), headers={"Content-Encoding": "gzip"}),
            Response(content(), headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)}),
        )
        for response in bad:
            with self.subTest(headers=response.headers), self.assertRaises(SourceError):
                RansomLookRansomwareSource(
                    opener=lambda *args, value=response, **kwargs: value,
                    clock=lambda: NOW,
                ).fetch()
        with self.assertRaisesRegex(SourceError, "sonuç üretilmedi") as raised:
            RansomLookRansomwareSource(
                opener=lambda *args, **kwargs: (_ for _ in ()).throw(
                    URLError("private remote detail"),
                ),
                clock=lambda: NOW,
            ).fetch()
        self.assertNotIn("private remote detail", str(raised.exception))

    def test_service_filters_locally_and_validates_limits(self):
        feed = parse_ransomlook_ransomware_response(content([
            post("Example Holding"),
            post("Other", group="example-group", discovered="2026-10-29T18:00:00Z"),
            post("Unrelated", group="other-group", discovered="2026-10-28T18:00:00Z"),
        ]), fetched_at=NOW)

        class Source:
            def fetch(self):
                return feed

        service = RansomLookClaimService(Source())
        report = service.recent("example", limit=1)
        self.assertEqual((report.matched_count, report.displayed_count), (2, 1))
        self.assertTrue(report.has_more)
        for limit in (0, 101, True):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                service.recent(limit=limit)

    def test_cli_preview_and_gate_need_no_database_and_do_not_expose_onion(self):
        feed = parse_ransomlook_ransomware_response(content(), fetched_at=NOW)
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "not-created"

            def invoke(*arguments, as_json=True):
                stdout, stderr = StringIO(), StringIO()
                argv = ["--data-dir", str(data)]
                if as_json:
                    argv.append("--json")
                with (
                    patch(
                        "xti.interfaces.cli.RansomLookRansomwareSource.fetch",
                        return_value=feed,
                    ),
                    redirect_stdout(stdout), redirect_stderr(stderr),
                ):
                    code = main([*argv, "ransomware", *arguments])
                return code, stdout.getvalue(), stderr.getvalue()

            code, output, error = invoke(
                "recent", "Example", "--source", "ransomlook", "--limit", "10",
            )
            payload = json.loads(output)
            self.assertEqual((code, error, payload["data"]["matched_count"]), (0, "", 1))
            self.assertNotIn("onion", output.lower())
            code, output, error = invoke("source-evaluation", as_json=False)
            self.assertEqual((code, error), (0, ""))
            self.assertIn("RansomLook public posts API | seçildi", output)
            self.assertIn("RansomWatch", output)
            code, output, error = invoke(
                "recent", "--source", "ransomlook", "--status", "listed",
            )
            self.assertEqual(code, 2)
            self.assertEqual(output, "")
            self.assertIn(
                "durumu sağlamaz", json.loads(error)["error"]["message"],
            )
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()
