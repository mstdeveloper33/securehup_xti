"""Public terminal acceptance for P06 action and IOC interchange commands."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.interfaces.cli import main


class ActionabilityCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.database = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.database)
        self.storage.initialize()
        now = datetime.now(timezone.utc) - timedelta(minutes=2)
        cases = CaseService(
            SQLiteCaseRepository(self.database),
            CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.database)),
            clock=lambda: now,
        )
        self.case = cases.create(
            "CLI actionability acceptance",
            summary="P06 public terminal route acceptance.",
            reason="Public terminal contract is verified.",
        ).case
        asset, _ = self.storage.add("example.com")
        finding_id = str(uuid4())
        with self.storage._connection() as connection, connection:
            connection.execute(
                "INSERT INTO findings "
                "(id,asset_id,asset_value,domain,rule_version,reasons,status,created_at,last_seen_at) "
                "VALUES (?,?,?,?,?,?,'suspicious',?,?)",
                (finding_id, asset.id, asset.value, "example-login.test", "p06/cli",
                 json.dumps(["acceptance"]), now.isoformat(), now.isoformat()),
            )
        self.evidence = cases.add_evidence(
            self.case.id, "finding", finding_id,
            reason="CLI takedown acceptance evidence.",
        ).evidence

    def cli(self, *arguments):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        result = json.loads(stdout.getvalue())
        self.assertIs(result["ok"], True)
        return result["data"]

    def test_runbook_package_and_takedown_public_commands(self):
        capabilities = self.cli("action", "capabilities")
        self.assertFalse(capabilities["external_connectors"])
        plan = self.cli("action", "runbook-plan", self.case.id)
        applied = self.cli(
            "action", "runbook-apply", self.case.id,
            "--expected-plan-sha256", plan["plan_sha256"],
            "--idempotency-key", "cli:runbook:1",
            "--reason", "CLI plan is applied atomically.",
        )
        self.assertGreater(len(applied["created_task_ids"]), 0)
        destination = self.root / "package"
        package = self.cli("action", "package-create", self.case.id, str(destination))
        self.assertEqual(
            self.cli("action", "package-verify", str(destination))["manifest_sha256"],
            package["manifest_sha256"],
        )
        draft = self.cli(
            "action", "takedown-create", self.case.id, self.evidence.id,
            "--target-kind", "registrar", "--target", "example-login.test",
            "--recipient", "abuse@example.test",
            "--requested-action", "Review the defensive abuse report.",
            "--grounds", "A human analyst linked the evidence to this case.",
            "--actor", "analyst@example.test", "--idempotency-key", "cli:takedown:1",
        )
        approved = self.cli(
            "action", "takedown-approve", draft["request"]["id"],
            "--expected-revision", "0", "--actor", "owner@example.test",
            "--reason", "Authorized owner reviewed and approved the draft.",
        )
        self.assertEqual(approved["request"]["state"], "approved")
        self.assertEqual(len(self.cli("action", "takedown-list")["records"]), 1)

    def test_ioc_bulk_preview_import_and_export_public_commands(self):
        source = self.root / "indicators.json"
        observed_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        source.write_text(json.dumps({
            "format": "xti-ioc-assertions", "version": 1,
            "records": [{
                "indicator_type": "domain", "value": "bad.example",
                "source_name": "analyst", "source_reference": "case:cli",
                "confidence": 70, "valid_from": None, "valid_until": None,
                "description": "Human-reviewed local IOC assertion.",
                "observed_at": observed_at,
            }],
        }))
        preview = self.cli("ioc", "bulk-preview", str(source), "--format", "json")
        imported = self.cli(
            "ioc", "bulk-import", str(source), "--format", "json",
            "--expected-content-sha256", preview["content_sha256"],
            "--idempotency-key", "cli:ioc:1", "--import-source", "manual-file",
            "--import-reference", "indicators.json",
        )
        self.assertEqual((imported["record_count"], imported["added_count"]), (1, 1))
        destination = self.root / "indicators.csv"
        exported = self.cli("ioc", "bulk-export", str(destination), "--format", "csv")
        self.assertEqual(exported["artifact"]["record_count"], 1)
        self.assertTrue(destination.is_file())


if __name__ == "__main__":
    unittest.main()
