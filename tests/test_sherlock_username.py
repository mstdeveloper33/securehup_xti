"""Bounded integration tests for the optional upstream Sherlock library."""

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

from xti.adapters.sherlock_username import (
    INTEGRATION_PROFILE,
    MAX_REPORT_BYTES,
    SherlockUsernameSource,
    _write_scoped_database,
    parse_sherlock_ndjson,
)
from xti.application.brand_username import SherlockUsernamePreviewService
from xti.domain.assets import ValidationError
from xti.domain.brand_username import BrandProfileMatch, BrandUsernamePreview
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 31, 20, tzinfo=timezone.utc)


def result(
    platform="Carrd",
    username="samplebrand",
    *,
    status="Claimed",
    profile_url="https://samplebrand.carrd.co/",
):
    return {
        "username": username,
        "platform": platform,
        "profile_url": profile_url if status == "Claimed" else None,
        "status": status,
    }


def ndjson(*items):
    return "".join(
        json.dumps(item, ensure_ascii=True, separators=(",", ":")) + "\n"
        for item in items
    ).encode()


def database_fixture(path: Path) -> str:
    payload = json.dumps({
        "$schema": "https://example.invalid/sherlock.schema.json",
        "Carrd": {
            "errorType": "status_code",
            "url": "https://{}.carrd.co/",
            "urlMain": "https://carrd.co/",
            "username_claimed": "blue",
        },
        "Rumble": {
            "errorType": "status_code",
            "url": "https://rumble.com/user/{}",
            "urlMain": "https://rumble.com/",
            "username_claimed": "John",
        },
    }, separators=(",", ":")).encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


class SherlockUsernameTests(unittest.TestCase):
    def test_service_validates_source_platforms_before_source(self):
        class Source:
            def __init__(self):
                self.calls = []

            def preview(self, username, *, platforms, request_timeout):
                self.calls.append((username, platforms, request_timeout))
                return "ok"

        source = Source()
        service = SherlockUsernamePreviewService(source)
        self.assertEqual(
            service.preview(
                " Sample.Brand ",
                platforms=("Carrd", "Rumble"),
                request_timeout=5,
            ),
            "ok",
        )
        self.assertEqual(
            source.calls,
            [("Sample.Brand", ("Carrd", "Rumble"), 5)],
        )
        invalid = (
            ("-danger", ("Carrd",), 10),
            ("a", ("Carrd",), 10),
            ("valid", (), 10),
            ("valid", ("Carrd", "Carrd"), 10),
            ("valid", ("GitHub",), 10),
            ("valid", ("Carrd",), 31),
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

    def test_parser_keeps_only_claimed_minimal_results_in_requested_order(self):
        matches = parse_sherlock_ndjson(
            ndjson(
                result("Rumble", status="Available"),
                result(),
            ),
            username="samplebrand",
            platforms=("Carrd", "Rumble"),
        )
        self.assertEqual(
            matches,
            (
                BrandProfileMatch(
                    platform="Carrd",
                    profile_url="https://samplebrand.carrd.co/",
                    status="found_unverified",
                ),
            ),
        )
        self.assertEqual(
            set(matches[0].__dataclass_fields__),
            {"platform", "profile_url", "status"},
        )

    def test_parser_rejects_partial_duplicate_mismatch_and_unsafe_output(self):
        fixtures = (
            ndjson(result()),
            ndjson(result(), result()),
            ndjson(result(username="other"), result("Rumble", status="Available")),
            ndjson(
                result(profile_url="http://samplebrand.carrd.co/"),
                result("Rumble", status="Available"),
            ),
            ndjson(
                result(profile_url="https://carrd.co.evil.example/samplebrand"),
                result("Rumble", status="Available"),
            ),
            ndjson(
                result(profile_url="https://samplebrand.carrd.co:444/"),
                result("Rumble", status="Available"),
            ),
            ndjson(
                result(status="Unexpected"),
                result("Rumble", status="Available"),
            ),
            b'{"platform":"Carrd","platform":"Carrd"}\n',
            b"x" * (MAX_REPORT_BYTES + 1),
        )
        for payload in fixtures:
            with self.subTest(payload=payload[:80]), self.assertRaises(SourceError):
                parse_sherlock_ndjson(
                    payload,
                    username="samplebrand",
                    platforms=("Carrd", "Rumble"),
                )

    def test_adapter_uses_library_worker_local_scope_and_safe_environment(self):
        calls = []
        temporary_paths = []
        with tempfile.TemporaryDirectory() as fixtures:
            database = Path(fixtures) / "data.json"
            database_hash = database_fixture(database)

            def runner(command, *, cwd, env, **kwargs):
                calls.append((command, cwd, env, kwargs))
                temporary_paths.append(Path(cwd))
                self.assertEqual(
                    command[1:3],
                    ["-m", "xti.adapters.sherlock_username_worker"],
                )
                scoped_path = Path(command[command.index("--database") + 1])
                report_path = Path(command[command.index("--report") + 1])
                scoped = json.loads(scoped_path.read_text())
                self.assertEqual(tuple(scoped), ("Carrd", "Rumble"))
                self.assertNotIn("$schema", scoped)
                report_path.write_bytes(ndjson(
                    result(),
                    result("Rumble", status="Unknown"),
                ))
                report_path.chmod(0o600)
                return subprocess.CompletedProcess(command, 0, "", "")

            source = SherlockUsernameSource(
                runner=runner,
                python_locator=lambda: "/safe/python",
                version_locator=lambda: "0.16.2",
                database_locator=lambda: database,
                database_sha256=database_hash,
                clock=lambda: NOW,
            )
            preview = source.preview(
                "samplebrand",
                platforms=("Carrd", "Rumble"),
                request_timeout=10,
            )
        self.assertEqual(preview.integration_profile, INTEGRATION_PROFILE)
        self.assertEqual(preview.checked_at, NOW.isoformat())
        self.assertEqual(len(preview.matches), 1)
        self.assertEqual(preview.unreported_platforms, ("Rumble",))
        self.assertNotIn("OPENAI_API_KEY", calls[0][2])
        self.assertEqual(calls[0][2]["NO_PROXY"], "*")
        self.assertNotIn("sherlock", Path(calls[0][0][0]).name.lower())
        self.assertTrue(all(not path.exists() for path in temporary_paths))

    def test_scoped_database_rejects_tampering_unknown_and_external_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            target = Path(directory) / "scoped.json"
            expected = database_fixture(source)
            _write_scoped_database(
                source,
                target,
                platforms=("Carrd",),
                expected_sha256=expected,
            )
            self.assertEqual(tuple(json.loads(target.read_text())), ("Carrd",))
            with self.assertRaisesRegex(SourceError, "incelenen sürüm"):
                _write_scoped_database(
                    source,
                    target,
                    platforms=("Carrd",),
                    expected_sha256="0" * 64,
                )
            with self.assertRaisesRegex(SourceError, "desteklenmiyor"):
                _write_scoped_database(
                    source,
                    target,
                    platforms=("Unknown",),
                    expected_sha256=expected,
                )
            hostile = json.loads(source.read_text())
            hostile["Carrd"]["url"] = "https://evil.example/{}/"
            payload = json.dumps(hostile, separators=(",", ":")).encode()
            source.write_bytes(payload)
            with self.assertRaisesRegex(SourceError, "izinli platform dışında"):
                _write_scoped_database(
                    source,
                    target,
                    platforms=("Carrd",),
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                )

    def test_missing_wrong_version_failure_and_timeout_are_safe(self):
        with self.assertRaisesRegex(SourceError, "setup-brand"):
            SherlockUsernameSource(
                python_locator=lambda: None,
                version_locator=lambda: None,
            ).preview(
                "samplebrand", platforms=("Carrd",), request_timeout=10,
            )
        with self.assertRaisesRegex(SourceError, "0.16.2 gerekiyor"):
            SherlockUsernameSource(
                python_locator=lambda: "/safe/python",
                version_locator=lambda: "9.9.9",
            ).preview(
                "samplebrand", platforms=("Carrd",), request_timeout=10,
            )

        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "data.json"
            database_hash = database_fixture(database)
            with self.assertRaisesRegex(SourceError, "süre sınırında"):
                SherlockUsernameSource(
                    runner=timeout,
                    python_locator=lambda: "/safe/python",
                    version_locator=lambda: "0.16.2",
                    database_locator=lambda: database,
                    database_sha256=database_hash,
                ).preview(
                    "samplebrand", platforms=("Carrd",), request_timeout=10,
                )

    def test_cli_selects_sherlock_and_remains_write_free(self):
        preview = BrandUsernamePreview(
            username="samplebrand",
            source="Sherlock",
            source_version="0.16.2",
            integration_profile=INTEGRATION_PROFILE,
            checked_at=NOW.isoformat(),
            requested_platforms=("Carrd", "Rumble"),
            matches=(BrandProfileMatch(
                "Carrd",
                "https://samplebrand.carrd.co/",
                "found_unverified",
            ),),
            unreported_platforms=("Rumble",),
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
                        "xti.interfaces.cli.SherlockUsernameSource.preview",
                        return_value=preview,
                    ) as source,
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    code = main([
                        *argv,
                        "brand", "username-preview", "samplebrand",
                        "--source", "sherlock",
                        "--site", "Carrd", "--site", "Rumble",
                    ])
                self.assertEqual((code, stderr.getvalue()), (0, ""))
                source.assert_called_once_with(
                    "samplebrand",
                    platforms=("Carrd", "Rumble"),
                    request_timeout=10,
                )
                if as_json:
                    payload = json.loads(stdout.getvalue())
                    self.assertEqual(payload["data"]["source"], "Sherlock")
                else:
                    self.assertIn("Kaynak: Sherlock 0.16.2", stdout.getvalue())
            self.assertFalse(data.exists())

    def test_cli_rejects_cross_source_platform_before_source(self):
        with patch(
            "xti.interfaces.cli.SherlockUsernameSource.preview",
        ) as source, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            code = main([
                "brand", "username-preview", "samplebrand",
                "--source", "sherlock", "--site", "GitHub",
            ])
        self.assertEqual(code, 2)
        source.assert_not_called()


if __name__ == "__main__":
    unittest.main()
