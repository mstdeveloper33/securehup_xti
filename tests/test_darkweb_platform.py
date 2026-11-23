"""P05 company isolation and JSON/source-job integration acceptance."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_darkweb_monitoring import SQLiteDarkwebRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.application.darkweb_monitoring import DarkwebService
from xti.domain.organizations import normalize_organization_target
from xti.interfaces.cli import main
from tests.test_darkweb_monitoring import AT, CredentialSource, FrozenInputs, Secrets


class DarkwebPlatformTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "platform"
        self.inputs = FrozenInputs()
        self.credential_source = CredentialSource()

        def make(database, **unused):
            return DarkwebService(
                SQLiteDarkwebRepository(database), self.inputs,
                self.credential_source, Secrets(), now=lambda: AT,
            )

        self.enterContext(patch(
            "xti.interfaces.darkweb_monitoring.make_darkweb_service", side_effect=make,
        ))
        self.enterContext(patch(
            "socket.socket.connect", side_effect=AssertionError("P05 stored analysis must not use network"),
        ))
        self.assertEqual(self.invoke(action="provision")[0], 0)
        self.assertEqual(self.invoke(action="provision", company="beta")[0], 0)
        self.alpha = resolve_company_workspace(self.root, "alpha")
        self.beta = resolve_company_workspace(self.root, "beta")
        storage = SQLiteAssetRepository(self.alpha.database)
        storage.add("example.com")
        organizations = SQLiteOrganizationRepository(self.alpha.database)
        self.organization = organizations.add(
            name_key="example corp", display_name="Example Corp",
            reason="P05 platform fixture", recorded_at=AT,
        ).organization
        organizations.link(
            self.organization.id, normalize_organization_target("domain", "example.com"),
            reason="P05 explicit domain", recorded_at=AT,
        )

    def invoke(self, operation="darkweb.capabilities", values=None, *, company="alpha",
               action="request", extra=()):
        request = {
            "contract_version": 1, "request_id": "p05-platform",
            "operation": operation, "parameters": values or {},
        }
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error), patch(
                "sys.stdin", StringIO(json.dumps(request))):
            code = main([
                "platform", action, "--root", str(self.root), "--company", company, *extra,
            ])
        self.assertEqual(error.getvalue(), "")
        return code, json.loads(output.getvalue())

    def profile(self):
        code, response = self.invoke("darkweb.profile.add", {
            "name": "Platform dark web", "organization_id": self.organization.id,
            "sources": ["ransomlook", "xposedornot_domain"], "interval_seconds": 900,
            "idempotency_key": "profile", "expected_workspace_id": self.alpha.workspace_id,
        })
        self.assertEqual(code, 0, response)
        return response["data"]

    def test_manifest_and_company_scope_are_explicit_and_isolated(self):
        code, described = self.invoke(extra=("--describe",))
        self.assertEqual(code, 0, described)
        self.assertIn("darkweb.capabilities", described["data"]["operations"])
        self.assertIn("darkweb.profile.add", described["data"]["operations"])
        self.assertIn("darkweb.credential.refresh", described["data"]["request_network_operations"])
        self.assertEqual(described["data"]["source_jobs"]["execution_version"], 12)
        self.assertIn("darkweb-monitor", described["data"]["source_jobs"]["sources"])
        profile = self.profile()
        code, hidden = self.invoke(
            "darkweb.profile.show", {"identifier": profile["id"]}, company="beta",
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(hidden["error"]["code"], "not_found")
        code, fenced = self.invoke("darkweb.credential.refresh", {
            "identifier": profile["id"], "domain": "example.com", "idempotency_key": "wrong",
            "expected_workspace_id": "00000000-0000-0000-0000-000000000000",
        })
        self.assertNotEqual(code, 0)
        self.assertEqual(fenced["error"]["code"], "scope_mismatch")
        self.assertEqual(self.credential_source.calls, 0)

    def test_platform_credential_refresh_returns_only_masked_evidence(self):
        profile = self.profile()
        code, response = self.invoke("darkweb.credential.refresh", {
            "identifier": profile["id"], "domain": "example.com",
            "idempotency_key": "credential", "expected_workspace_id": self.alpha.workspace_id,
        })
        self.assertEqual(code, 0, response)
        self.assertEqual(response["data"]["account_count"], 1)
        encoded = json.dumps(response)
        self.assertNotIn("alice.private", encoded)
        self.assertNotIn("a" * 32, encoded)
        self.assertEqual(self.credential_source.calls, 1)

    def test_shared_queue_runs_stored_analysis_and_preserves_receipt(self):
        profile = self.profile()
        plan = self.invoke("darkweb.plan", {"identifier": profile["id"]})[1]["data"]
        options = {
            "indicator_type": "sha256", "value": plan["queue_scope_sha256"],
            "sources": ["darkweb-monitor"], "darkweb_profile_id": profile["id"],
            "darkweb_profile_revision": 1, "darkweb_force": True,
        }
        code, planned = self.invoke("sources.plan", options)
        self.assertEqual(code, 0, planned)
        self.assertEqual(planned["data"]["maximum_external_requests"], 0)
        code, submitted = self.invoke("sources.jobs.submit", {
            **planned["data"]["plan"], "plan_sha256": planned["data"]["plan_sha256"],
            "idempotency_key": "darkweb-job", "expected_workspace_id": self.alpha.workspace_id,
        })
        self.assertEqual(code, 0, submitted)
        job_id = submitted["data"]["job_id"]
        code, completed = self.invoke(action="worker", extra=("--job-id", job_id))
        self.assertEqual(code, 0, completed)
        self.assertEqual(completed["data"]["status"], "complete")
        self.assertEqual(completed["data"]["execution"]["requests"]["attempts"], 0)
        receipt = completed["data"]["steps"][0]["receipt"]
        self.assertEqual(receipt["kind"], "darkweb_monitor_run")
        run = self.invoke("darkweb.run.show", {"identifier": receipt["run_id"]})[1]
        self.assertEqual(run["data"]["status"], "complete")
        self.assertIsNone(self.invoke(action="worker", extra=("--job-id", job_id))[1]["data"])

    def test_backup_restore_keeps_darkweb_evidence_and_rotates_workspace_scope(self):
        profile = self.profile()
        run = self.invoke("darkweb.run", {
            "identifier": profile["id"], "expected_revision": 1, "force": True,
            "idempotency_key": "run", "expected_workspace_id": self.alpha.workspace_id,
        })[1]["data"]
        from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
        backup = self.root.parent / "backup"
        backup_platform_workspace(self.alpha, backup)
        restored_root = self.root.parent / "restored"
        restore_platform_workspace(restored_root, "alpha", backup)
        restored = resolve_company_workspace(restored_root, "alpha")
        self.assertNotEqual(restored.workspace_id, self.alpha.workspace_id)
        saved = SQLiteDarkwebRepository(restored.database).read(
            "darkweb.run.show", {"identifier": run["id"]},
        )
        self.assertEqual(saved["status"], "complete")
        self.assertEqual(saved["report"]["policy"], "darkweb-monitoring-v1")


if __name__ == "__main__":
    unittest.main()
