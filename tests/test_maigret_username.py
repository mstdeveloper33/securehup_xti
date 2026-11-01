"""Bounded integration tests for the optional upstream Maigret CLI."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.maigret_username import (
    MAX_REPORT_BYTES,
    INTEGRATION_PROFILE,
    MaigretUsernameSource,
    _write_scoped_database,
    parse_maigret_ndjson,
)
from xti.application.brand_username import BrandUsernamePreviewService
from xti.domain.assets import ValidationError
from xti.domain.brand_username import BrandProfileMatch, BrandUsernamePreview
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def result(platform="GitHub", username="samplebrand", url=None):
    profile_url = url or f"https://www.github.com/{username}"
    return {
        "username": username,
        "url_user": profile_url,
        "status": {
            "username": username,
            "site_name": platform,
            "url": profile_url,
            "status": "Claimed",
            "ids": {"discarded": "personal profile field"},
            "tags": ["discarded"],
        },
        "site": {"name": platform, "discarded": True},
        "response_text": "discarded raw response",
        "sitename": platform,
    }


def ndjson(*items):
    return "".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
        for item in items
    ).encode()


def database_fixture(path: Path) -> str:
    payload = json.dumps(
        {
            "sites": {
                "GitHub": {
                    "url": "https://github.com/{username}",
                    "urlMain": "https://github.com",
                    "urlProbe": "https://api.github.com/users/{username}",
                },
                "Reddit": {
                    "url": "https://www.reddit.com/user/{username}",
                    "urlMain": "https://www.reddit.com",
                },
            },
            "engines": {},
            "tags": [],
        },
        separators=(",", ":"),
    ).encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


class MaigretUsernameTests(unittest.TestCase):
    def test_locator_keeps_virtual_environment_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            bin_directory = Path(temporary) / "bin"
            bin_directory.mkdir()
            executable = bin_directory / "maigret"
            executable.write_text("", encoding="utf-8")
            executable.chmod(0o700)
            with patch(
                "xti.adapters.maigret_username.sys.executable",
                str(bin_directory / "python"),
            ):
                self.assertEqual(
                    MaigretUsernameSource._locate_executable(),
                    str(executable),
                )

    def test_service_validates_username_platforms_and_timeout_before_source(self):
        class Source:
            def __init__(self):
                self.calls = []

            def preview(self, username, *, platforms, request_timeout):
                self.calls.append((username, platforms, request_timeout))
                return "ok"

        source = Source()
        service = BrandUsernamePreviewService(source)
        self.assertEqual(
            service.preview(" Sample.Brand ", platforms=("GitHub",), request_timeout=5),
            "ok",
        )
        self.assertEqual(source.calls, [("Sample.Brand", ("GitHub",), 5)])
        invalid = (
            ("-danger", ("GitHub",), 10),
            ("a", ("GitHub",), 10),
            ("valid", (), 10),
            ("valid", ("GitHub", "GitHub"), 10),
            ("valid", ("Unknown",), 10),
            ("valid", ("GitHub",), 31),
        )
        for username, platforms, timeout in invalid:
            with self.subTest(value=(username, platforms, timeout)):
                with self.assertRaises(ValidationError):
                    service.preview(
                        username,
                        platforms=platforms,
                        request_timeout=timeout,
                    )
        self.assertEqual(len(source.calls), 1)

    def test_parser_keeps_only_minimal_claims_in_requested_order(self):
        youtube = result(
            "YouTube",
            url="https://www.youtube.com/@samplebrand",
        )
        matches = parse_maigret_ndjson(
            ndjson(youtube, result()),
            username="samplebrand",
            platforms=("GitHub", "Reddit", "YouTube"),
        )
        self.assertEqual(
            [(item.platform, item.status) for item in matches],
            [("GitHub", "found_unverified"), ("YouTube", "found_unverified")],
        )
        self.assertEqual(
            set(matches[0].__dataclass_fields__),
            {"platform", "profile_url", "status"},
        )
        self.assertNotIn("personal profile field", repr(matches))
        self.assertNotIn("raw response", repr(matches))

    def test_parser_rejects_unselected_duplicate_mismatch_and_unsafe_output(self):
        fixtures = (
            ndjson(result("Reddit")),
            ndjson(result(), result()),
            ndjson(result(username="other")),
            ndjson(result(url="http://www.github.com/samplebrand")),
            ndjson(result(url="https://github.com.evil.example/samplebrand")),
            b'{"sitename":"GitHub","sitename":"GitHub"}\n',
            b"x" * (MAX_REPORT_BYTES + 1),
        )
        for payload in fixtures:
            with self.subTest(payload=payload[:80]), self.assertRaises(SourceError):
                parse_maigret_ndjson(
                    payload,
                    username="samplebrand",
                    platforms=("GitHub",),
                )

    def test_adapter_runs_pinned_cli_with_safe_flags_and_discards_extra_data(self):
        calls = []
        temporary_paths = []
        with tempfile.TemporaryDirectory() as fixtures:
            database = Path(fixtures) / "data.json"
            database_hash = database_fixture(database)

            def runner(command, *, cwd, env, **kwargs):
                calls.append((command, cwd, env, kwargs))
                temporary_paths.append(Path(cwd))
                if command[-1] == "--version":
                    return subprocess.CompletedProcess(
                        command, 0, "maigret 0.6.6\nPython: 3.13.3\n", "",
                    )
                settings = json.loads((Path(cwd) / "settings.json").read_text())
                self.assertFalse(settings["recursive_search"])
                self.assertFalse(settings["info_extracting"])
                self.assertTrue(settings["no_autoupdate"])
                self.assertIsNone(settings["proxy_url"])
                self.assertFalse(settings["cloudflare_bypass"]["enabled"])
                scoped = json.loads((Path(cwd) / "scoped-sites.json").read_text())
                self.assertEqual(set(scoped["sites"]), {"GitHub", "Reddit"})
                reports = Path(cwd) / "reports"
                reports.mkdir()
                (reports / "report_samplebrand_ndjson.json").write_bytes(
                    ndjson(result())
                )
                return subprocess.CompletedProcess(command, 0, "bounded output", "")

            source = MaigretUsernameSource(
                runner=runner,
                executable_locator=lambda: "/safe/maigret",
                database_locator=lambda: database,
                database_sha256=database_hash,
                clock=lambda: NOW,
            )
            preview = source.preview(
                "samplebrand",
                platforms=("GitHub", "Reddit"),
                request_timeout=10,
            )
        self.assertEqual(preview.integration_profile, INTEGRATION_PROFILE)
        self.assertEqual(preview.checked_at, NOW.isoformat())
        self.assertEqual(
            preview.matches,
            (
                BrandProfileMatch(
                    platform="GitHub",
                    profile_url="https://www.github.com/samplebrand",
                    status="found_unverified",
                ),
            ),
        )
        self.assertEqual(preview.unreported_platforms, ("Reddit",))
        command = calls[1][0]
        for flag in (
            "--json", "--site", "--no-recursion", "--no-extracting",
            "--no-autoupdate", "--no-color", "--no-progressbar",
        ):
            self.assertIn(flag, command)
        for forbidden in (
            "--ai", "--proxy", "--tor-proxy", "--with-domains",
            "--cloudflare-bypass", "--enrich", "--permute",
        ):
            self.assertNotIn(forbidden, command)
        self.assertNotIn("OPENAI_API_KEY", calls[1][2])
        self.assertTrue(all(not path.exists() for path in temporary_paths))

    def test_scoped_database_rejects_tampering_and_external_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            target = Path(directory) / "scoped.json"
            expected = database_fixture(source)
            _write_scoped_database(
                source,
                target,
                platforms=("GitHub",),
                expected_sha256=expected,
            )
            self.assertEqual(set(json.loads(target.read_text())["sites"]), {"GitHub"})
            with self.assertRaisesRegex(SourceError, "incelenen sürüm"):
                _write_scoped_database(
                    source,
                    target,
                    platforms=("GitHub",),
                    expected_sha256="0" * 64,
                )
            hostile = json.loads(source.read_text())
            hostile["sites"]["GitHub"]["url"] = "https://evil.example/{username}"
            payload = json.dumps(hostile, separators=(",", ":")).encode()
            source.write_bytes(payload)
            with self.assertRaisesRegex(SourceError, "izinli platform dışında"):
                _write_scoped_database(
                    source,
                    target,
                    platforms=("GitHub",),
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                )

    def test_missing_wrong_version_failure_and_timeout_are_safe(self):
        with self.assertRaisesRegex(SourceError, "setup-brand"):
            MaigretUsernameSource(
                executable_locator=lambda: None,
            ).preview(
                "samplebrand", platforms=("GitHub",), request_timeout=10,
            )

        def wrong_version(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, "maigret 9.9.9\n", "")

        with self.assertRaisesRegex(SourceError, "0.6.6 gerekiyor"):
            MaigretUsernameSource(
                runner=wrong_version,
                executable_locator=lambda: "/safe/maigret",
            ).preview(
                "samplebrand", platforms=("GitHub",), request_timeout=10,
            )

        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        with self.assertRaisesRegex(SourceError, "süre sınırında"):
            MaigretUsernameSource(
                runner=timeout,
                executable_locator=lambda: "/safe/maigret",
            ).preview(
                "samplebrand", platforms=("GitHub",), request_timeout=10,
            )

    def test_cli_terminal_and_json_are_write_free_and_explain_uncertainty(self):
        preview = BrandUsernamePreview(
            username="samplebrand",
            source="Maigret",
            source_version="0.6.6",
            integration_profile=INTEGRATION_PROFILE,
            checked_at=NOW.isoformat(),
            requested_platforms=("GitHub", "Reddit"),
            matches=(
                BrandProfileMatch(
                    "GitHub",
                    "https://www.github.com/samplebrand",
                    "found_unverified",
                ),
            ),
            unreported_platforms=("Reddit",),
            notes=("Aynı kullanıcı adı sahiplik veya taklit kanıtı değildir.",),
        )
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "not-created"
            for as_json in (False, True):
                argv = ["--data-dir", str(data)]
                if as_json:
                    argv.append("--json")
                stdout, stderr = StringIO(), StringIO()
                with (
                    patch(
                        "xti.interfaces.cli.MaigretUsernameSource.preview",
                        return_value=preview,
                    ),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    code = main([
                        *argv,
                        "brand", "username-preview", "samplebrand",
                        "--site", "GitHub", "--site", "Reddit",
                    ])
                self.assertEqual((code, stderr.getvalue()), (0, ""))
                if as_json:
                    payload = json.loads(stdout.getvalue())
                    self.assertEqual(payload["data"]["matches"][0]["platform"], "GitHub")
                else:
                    self.assertIn("bulundu, doğrulanmadı", stdout.getvalue())
                    self.assertIn("Raporlanmayan platform: 1", stdout.getvalue())
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()
