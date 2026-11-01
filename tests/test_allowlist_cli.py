"""Public terminal workflow for exact-domain false-positive exceptions."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class AllowlistCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.project = Path(__file__).resolve().parents[1]
        self.run_ok("init")
        self.run_ok("assets", "add", "example.com")

    def run_cli(self, *arguments, as_json=True):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self.project / "src")
        command = [
            sys.executable, "-m", "xti", "--data-dir", str(self.data),
        ]
        if as_json:
            command.append("--json")
        return subprocess.run(
            [*command, *arguments], text=True, capture_output=True, check=False,
            timeout=20, env=environment, cwd=self.project,
        )

    def run_ok(self, *arguments, as_json=True):
        result = self.run_cli(*arguments, as_json=as_json)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        if not as_json:
            return result.stdout
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        return payload["data"]

    def run_error(self, *arguments):
        result = self.run_cli(*arguments)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        payload = json.loads(result.stderr)
        self.assertFalse(payload["ok"])
        return payload["error"]

    def write_source(self, name, text="example-support.net\n"):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def import_source(self, name):
        return self.run_ok("import", "domains", str(self.write_source(name)))

    def dump(self):
        with closing(sqlite3.connect(self.data / "xti.db")) as connection:
            return tuple(connection.iterdump())

    def test_add_list_show_revoke_and_reactivate_keep_one_identity_and_history(self):
        added = self.run_ok(
            "allowlist", "add", "example.com", "example-support.net",
            "--reason", "Doğrulanmış iş ortağı.",
        )
        self.assertTrue(added["active"])
        entry_id = added["id"]
        repeated = self.run_ok(
            "allowlist", "add", "example.com", "example-support.net",
            "--reason", "Tekrar ekleme.",
        )
        self.assertEqual(repeated, added)
        listing = self.run_ok("allowlist", "list")["entries"]
        self.assertEqual(listing, [added])
        shown = self.run_ok("allowlist", "show", entry_id)
        self.assertEqual(shown["entry"], added)
        self.assertEqual([event["action"] for event in shown["events"]], ["added"])

        revoked = self.run_ok(
            "allowlist", "revoke", entry_id, "--reason", "Tekrar incelenecek.",
        )
        self.assertFalse(revoked["active"])
        self.assertEqual(self.run_ok("allowlist", "list")["entries"], [])
        self.assertEqual(self.run_ok("allowlist", "list", "--all")["entries"], [revoked])

        reactivated = self.run_ok(
            "allowlist", "add", "example.com", "example-support.net",
            "--reason", "Yeniden doğrulandı.",
        )
        self.assertEqual(reactivated["id"], entry_id)
        shown = self.run_ok("allowlist", "show", entry_id)
        self.assertEqual(
            [event["action"] for event in shown["events"]],
            ["added", "revoked", "reactivated"],
        )
        output = self.run_ok("allowlist", "show", entry_id, as_json=False)
        self.assertIn("İşlem geçmişi", output)
        self.assertIn("Yeniden etkin", output)

    def test_add_from_finding_suppresses_new_links_until_revoked(self):
        first = self.import_source("first.txt")
        self.assertEqual(first["findings_created"], 1)
        findings = self.run_ok("findings", "list")["findings"]
        finding_id = findings[0]["id"]
        entry = self.run_ok(
            "allowlist", "add-finding", finding_id,
            "--reason", "Meşru kampanya alanı.",
        )

        second_path = self.write_source("second.txt", "# independent source\nexample-support.net\n")
        second = self.run_ok("import", "domains", str(second_path))
        self.assertEqual(second["observations_created"], 1)
        self.assertEqual(second["findings_suppressed"], 1)
        details = self.run_ok("findings", "show", finding_id)
        self.assertEqual(len(details["observations"]), 1)

        self.run_ok(
            "allowlist", "revoke", entry["id"],
            "--reason", "İstisna artık geçerli değil.",
        )
        repeated = self.run_ok("import", "domains", str(self.root / "second.txt"))
        self.assertEqual(repeated["observations_existing"], 1)
        self.assertEqual(repeated["findings_existing"], 1)
        details = self.run_ok("findings", "show", finding_id)
        self.assertEqual(len(details["observations"]), 2)

    def test_temporary_exception_expires_and_can_be_reactivated_with_same_identity(self):
        entry = self.run_ok(
            "allowlist", "add", "example.com", "example-support.net",
            "--reason", "Bir günlük kampanya.", "--expires-in-days", "1",
        )
        self.assertTrue(entry["active"])
        self.assertFalse(entry["expired"])
        self.assertFalse(entry["revoked"])
        self.assertIsNotNone(entry["expires_at"])

        with closing(sqlite3.connect(self.data / "xti.db")) as connection:
            connection.execute(
                "UPDATE allowlist_entries SET expires_at = '2000-01-01T00:00:00+00:00' "
                "WHERE id = ?", (entry["id"],),
            )
            connection.commit()
        self.assertEqual(self.run_ok("allowlist", "list")["entries"], [])
        expired = self.run_ok("allowlist", "list", "--all")["entries"][0]
        self.assertFalse(expired["active"])
        self.assertTrue(expired["expired"])
        self.assertFalse(expired["revoked"])
        output = self.run_ok("allowlist", "show", entry["id"], as_json=False)
        self.assertIn("Süresi doldu", output)

        imported = self.import_source("after-expiry.txt")
        self.assertEqual((imported["findings_created"], imported["findings_suppressed"]), (1, 0))
        reactivated = self.run_ok(
            "allowlist", "add", "example.com", "example-support.net",
            "--reason", "Tekrar geçici onaylandı.", "--expires-in-days", "2",
        )
        self.assertEqual(reactivated["id"], entry["id"])
        shown = self.run_ok("allowlist", "show", entry["id"])
        self.assertEqual(
            [event["action"] for event in shown["events"]],
            ["added", "reactivated"],
        )

    def test_invalid_or_broad_commands_do_not_change_database(self):
        attempts = (
            ("allowlist", "add", "example.com", "unrelated.org", "--reason", "İlgisiz."),
            ("allowlist", "add", "example.com", "*.example.net", "--reason", "Geniş."),
            ("allowlist", "add", "missing.com", "example-support.net", "--reason", "Yok."),
            ("allowlist", "show", "missing"),
            ("allowlist", "revoke", "missing", "--reason", "Yok."),
            ("allowlist", "list", "--limit", "0"),
            ("allowlist", "add", "example.com", "example-support.net",
             "--reason", "Süre hatası.", "--expires-in-days", "0"),
        )
        before = self.dump()
        for arguments in attempts:
            with self.subTest(arguments=arguments):
                self.run_error(*arguments)
                self.assertEqual(self.dump(), before)


if __name__ == "__main__":
    unittest.main()
