"""Explicit Canonical Ubuntu OSV package version comparison."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.ubuntu_osv import UbuntuOsvAdvisorySource, parse_ubuntu_osv_response
from xti.application.ubuntu_package_match import UbuntuPackageMatchService
from xti.domain.assets import ValidationError
from xti.domain.debian_version import compare_debian_versions, parse_debian_version
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


CVE = "CVE-2025-6491"


def payload(*, fixed="8.4.5-1ubuntu1.1", withdrawn=None, package="php8.4"):
    events = [{"introduced": "0"}]
    if fixed is not None:
        events.append({"fixed": fixed})
    value = {
        "schema_version": "1.7.0",
        "id": f"UBUNTU-{CVE}",
        "aliases": [],
        "upstream": [CVE],
        "modified": "2026-10-20T18:00:00Z",
        "published": "2025-07-13T22:15:00Z",
        "details": "Ubuntu package vulnerability",
        "affected": [{
            "package": {
                "ecosystem": "Ubuntu:24.04:LTS", "name": package,
                "purl": "pkg:deb/ubuntu/php8.4@8.4.5-1ubuntu1",
            },
            "versions": ["8.4.5-1ubuntu1"],
            "ranges": [{"type": "ECOSYSTEM", "events": events}],
        }],
        "references": [{
            "type": "ADVISORY", "url": "https://ubuntu.com/security/notices/USN-7648-1",
        }],
    }
    if withdrawn is not None:
        value["withdrawn"] = withdrawn
    return json.dumps(value, separators=(",", ":")).encode()


class FakeSource:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def fetch(self, cve_id):
        self.calls.append(cve_id)
        return self.snapshot


class UbuntuPackageMatchTests(unittest.TestCase):
    def test_debian_comparison_covers_epoch_revision_numeric_and_tilde(self):
        cases = (
            ("1.0~rc1-1", "1.0-1", -1),
            ("1.0-1", "1.0-1ubuntu1", -1),
            ("1:1.0-1", "2.0-99", 1),
            ("1.01-1", "1.1-1", 0),
            ("1.0", "1.0-0", 0),
            ("1.0+git1-1", "1.0-1", 1),
            ("2:0.9-0ubuntu1", "2:0.9-0ubuntu1", 0),
        )
        for left, right, expected in cases:
            with self.subTest(left=left, right=right):
                self.assertEqual(compare_debian_versions(left, right), expected)
                self.assertEqual(compare_debian_versions(right, left), -expected)
        policy_order = ("1.0~~", "1.0~~a", "1.0~", "1.0", "1.0a")
        for earlier, later in zip(policy_order, policy_order[1:]):
            self.assertEqual(compare_debian_versions(earlier, later), -1)
        self.assertEqual(parse_debian_version(" 1.0 ").value, "1.0")
        for invalid in ("", "x:y:1", "1.0-", "1.0_1", "-1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    parse_debian_version(invalid)

    def test_exact_match_distinguishes_before_equal_and_after_fixed_boundary(self):
        snapshot = parse_ubuntu_osv_response(payload(), CVE)
        for version, status, comparison in (
            ("8.4.5-1ubuntu1", "before_fixed_boundary", -1),
            ("8.4.5-1ubuntu1.1", "at_fixed_boundary", 0),
            ("8.4.5-1ubuntu1.2", "after_fixed_boundary", 1),
        ):
            with self.subTest(version=version):
                report = UbuntuPackageMatchService(FakeSource(snapshot)).match(
                    CVE, ecosystem="Ubuntu:24.04:LTS",
                    source_package="php8.4", installed_version=version,
                )
                self.assertEqual((report.status, report.version_comparison),
                                 (status, comparison))
                self.assertEqual(report.fixed_version, "8.4.5-1ubuntu1.1")
                self.assertEqual(report.affected_versions_count, 1)

    def test_not_listed_no_fix_and_withdrawn_remain_distinct(self):
        normal = parse_ubuntu_osv_response(payload(), CVE)
        not_listed = UbuntuPackageMatchService(FakeSource(normal)).match(
            CVE, ecosystem="Ubuntu:24.04:LTS", source_package="openssl",
            installed_version="3.0.13-0ubuntu3.6",
        )
        self.assertEqual(not_listed.status, "not_listed")
        self.assertIn("tek başına güvenli", not_listed.notes[1])

        no_fix = parse_ubuntu_osv_response(payload(fixed=None), CVE)
        listed = UbuntuPackageMatchService(FakeSource(no_fix)).match(
            CVE, ecosystem="Ubuntu:24.04:LTS", source_package="php8.4",
            installed_version="8.4.5-1ubuntu1",
        )
        self.assertEqual(listed.status, "listed_without_fixed_boundary")
        self.assertIsNone(listed.version_comparison)

        withdrawn = parse_ubuntu_osv_response(
            payload(withdrawn="2026-10-20T18:00:00Z"), CVE,
        )
        report = UbuntuPackageMatchService(FakeSource(withdrawn)).match(
            CVE, ecosystem="Ubuntu:24.04:LTS", source_package="php8.4",
            installed_version="8.4.5-1ubuntu1",
        )
        self.assertEqual(report.status, "record_withdrawn")

    def test_invalid_input_prevents_network_and_ambiguous_source_fails_closed(self):
        snapshot = parse_ubuntu_osv_response(payload(), CVE)
        source = FakeSource(snapshot)
        service = UbuntuPackageMatchService(source)
        for kwargs in (
            {"ecosystem": "Debian:12", "source_package": "php8.4", "installed_version": "1"},
            {"ecosystem": "Ubuntu:24.04:LTS", "source_package": "PHP 8", "installed_version": "1"},
            {"ecosystem": "Ubuntu:24.04:LTS", "source_package": "php8.4", "installed_version": "1_0"},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValidationError):
                    service.match(CVE, **kwargs)
        self.assertEqual(source.calls, [])
        with self.assertRaises(ValidationError):
            service.match(
                CVE, ecosystem="Ubuntu:24.04:LTS", source_package="php8.4",
                installed_version="1", reference_limit=0,
            )
        self.assertEqual(source.calls, [])

        duplicate = json.loads(payload())
        duplicate["affected"].append(duplicate["affected"][0])
        ambiguous = parse_ubuntu_osv_response(json.dumps(duplicate).encode(), CVE)
        with self.assertRaisesRegex(SourceError, "birden fazla"):
            UbuntuPackageMatchService(FakeSource(ambiguous)).match(
                CVE, ecosystem="Ubuntu:24.04:LTS", source_package="php8.4",
                installed_version="8.4.5-1ubuntu1",
            )

    def test_noncanonical_ubuntu_range_fails_closed(self):
        fixtures = []
        introduced = json.loads(payload())
        introduced["affected"][0]["ranges"][0]["events"][0] = {"introduced": "1.0"}
        fixtures.append(introduced)
        last = json.loads(payload(fixed=None))
        last["affected"][0]["ranges"][0]["events"].append({"last_affected": "8.4.5"})
        fixtures.append(last)
        multiple_fixed = json.loads(payload())
        multiple_fixed["affected"][0]["ranges"][0]["events"].append(
            {"fixed": "8.4.5-1ubuntu1.2"},
        )
        fixtures.append(multiple_fixed)
        multiple_ranges = json.loads(payload())
        multiple_ranges["affected"][0]["ranges"].append(
            {"type": "ECOSYSTEM", "events": [{"introduced": "0"}]},
        )
        fixtures.append(multiple_ranges)
        reversed_events = json.loads(payload())
        reversed_events["affected"][0]["ranges"][0]["events"].reverse()
        fixtures.append(reversed_events)
        for value in fixtures:
            with self.subTest(events=value["affected"][0]["ranges"][0]["events"]):
                snapshot = parse_ubuntu_osv_response(json.dumps(value).encode(), CVE)
                with self.assertRaisesRegex(SourceError, "güvenli Debian"):
                    UbuntuPackageMatchService(FakeSource(snapshot)).match(
                        CVE, ecosystem="Ubuntu:24.04:LTS", source_package="php8.4",
                        installed_version="8.4.5-1ubuntu1",
                    )

    def test_terminal_json_is_write_free_and_clear_about_candidate_scope(self):
        snapshot = parse_ubuntu_osv_response(payload(), CVE)
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "missing"
            stdout, stderr = StringIO(), StringIO()
            with patch.object(UbuntuOsvAdvisorySource, "fetch", return_value=snapshot):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([
                        "--data-dir", str(data), "--json", "vuln", "ubuntu-match", CVE,
                        "--ecosystem", "Ubuntu:24.04:LTS", "--source-package", "php8.4",
                        "--version", "8.4.5-1ubuntu1",
                    ])
            self.assertEqual((code, stderr.getvalue()), (0, ""))
            result = json.loads(stdout.getvalue())["data"]
            self.assertEqual(result["status"], "before_fixed_boundary")
            self.assertEqual(result["version_comparison"], -1)
            self.assertEqual(result["total_advisory_reference_count"], 1)
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()
