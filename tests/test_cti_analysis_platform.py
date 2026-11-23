from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.sqlite_cti_analysis import SQLiteCtiAnalysisRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.application.cti_analysis import CtiAnalysisService
from xti.interfaces.cli import main
from tests.test_cti_analysis import AT, FrozenInputs, labelled_snapshot


class CtiAnalysisPlatformTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "platform"

        def make(database):
            return CtiAnalysisService(SQLiteCtiAnalysisRepository(database),
                FrozenInputs(labelled_snapshot()))

        self.enterContext(patch("xti.interfaces.cti_analysis.make_cti_analysis_service",
                                side_effect=make))
        self.enterContext(patch("socket.socket.connect",
                                side_effect=AssertionError("P04 must not use network")))
        self.assertEqual(self.invoke(action="provision")[0], 0)
        self.assertEqual(self.invoke(action="provision", company="beta")[0], 0)
        self.alpha = resolve_company_workspace(self.root, "alpha")
        self.beta = resolve_company_workspace(self.root, "beta")
        self.organization = SQLiteOrganizationRepository(self.alpha.database).add(
            name_key="example corp", display_name="Example Corp", reason="P04 platform fixture",
            recorded_at=AT.isoformat()).organization

    def invoke(self, operation="cti.analysis.capabilities", values=None, *,
               company="alpha", action="request", extra=()):
        request = {"contract_version": 1, "request_id": "p04-platform",
                   "operation": operation, "parameters": values or {}}
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error), patch(
                "sys.stdin", StringIO(json.dumps(request))):
            code = main(["platform", action, "--root", str(self.root),
                         "--company", company, *extra])
        self.assertEqual(error.getvalue(), "")
        return code, json.loads(output.getvalue())

    def profile(self):
        code, response = self.invoke("cti.analysis.profile.add", {
            "name": "Platform CTI", "organization_id": self.organization.id,
            "idempotency_key": "profile",
            "expected_workspace_id": self.alpha.workspace_id})
        self.assertEqual(code, 0, response)
        return response["data"]

    def test_company_scope_fence_and_read_isolation(self):
        profile = self.profile()
        code, response = self.invoke("cti.analysis.run", {"identifier": profile["id"],
            "expected_revision": 1, "force": True, "idempotency_key": "run",
            "expected_workspace_id": "00000000-0000-0000-0000-000000000000"})
        self.assertNotEqual(code, 0); self.assertEqual(response["error"]["code"], "scope_mismatch")
        code, response = self.invoke("cti.analysis.run", {"identifier": profile["id"],
            "expected_revision": 1, "force": True, "idempotency_key": "run",
            "expected_workspace_id": self.alpha.workspace_id})
        self.assertEqual(code, 0, response)
        candidate = self.invoke("cti.analysis.candidates", {"profile_id": profile["id"]})[1]["data"]["items"][0]
        code, hidden = self.invoke("cti.analysis.candidate.show",
                                   {"identifier": candidate["id"]}, company="beta")
        self.assertNotEqual(code, 0); self.assertEqual(hidden["error"]["code"], "not_found")

    def test_shared_queue_executes_network_free_analysis_and_preserves_receipt(self):
        profile = self.profile()
        plan = self.invoke("cti.analysis.plan", {"identifier": profile["id"]})[1]["data"]
        options = {"indicator_type": "sha256", "value": plan["queue_scope_sha256"],
            "sources": ["cti-analysis"], "analysis_profile_id": profile["id"],
            "analysis_profile_revision": 1, "analysis_force": True}
        code, planned = self.invoke("sources.plan", options)
        self.assertEqual(code, 0, planned)
        self.assertEqual(planned["data"]["maximum_external_requests"], 0)
        self.assertFalse(planned["data"]["disclosure"][0]["target_sent"])
        code, submitted = self.invoke("sources.jobs.submit", {
            **planned["data"]["plan"], "plan_sha256": planned["data"]["plan_sha256"],
            "idempotency_key": "analysis-job", "expected_workspace_id": self.alpha.workspace_id})
        self.assertEqual(code, 0, submitted)
        job_id = submitted["data"]["job_id"]
        code, completed = self.invoke(action="worker", extra=("--job-id", job_id))
        self.assertEqual(code, 0, completed)
        self.assertEqual(completed["data"]["status"], "complete")
        self.assertEqual(completed["data"]["execution"]["requests"]["attempts"], 0)
        receipt = completed["data"]["steps"][0]["receipt"]
        self.assertEqual(receipt["kind"], "cti_analysis_run")
        code, stored = self.invoke("cti.analysis.run.show", {"identifier": receipt["run_id"]})
        self.assertEqual(code, 0, stored)
        self.assertEqual(stored["data"]["status"], "complete")
        # A second worker call cannot execute the completed job again.
        self.assertIsNone(self.invoke(action="worker", extra=("--job-id", job_id))[1]["data"])

    def test_backup_restore_keeps_analysis_and_rotates_workspace_scope(self):
        profile = self.profile()
        run = self.invoke("cti.analysis.run", {"identifier": profile["id"],
            "expected_revision": 1, "force": True, "idempotency_key": "run",
            "expected_workspace_id": self.alpha.workspace_id})[1]["data"]
        from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
        backup = self.root.parent / "backup"
        backup_platform_workspace(self.alpha, backup)
        restored_root = self.root.parent / "restored"
        restore_platform_workspace(restored_root, "alpha", backup)
        restored = resolve_company_workspace(restored_root, "alpha")
        self.assertNotEqual(restored.workspace_id, self.alpha.workspace_id)
        saved = SQLiteCtiAnalysisRepository(restored.database).read(
            "cti.analysis.run.show", {"identifier": run["id"]})
        self.assertEqual(saved["status"], "complete")
        self.assertEqual(saved["report"]["policy"], "cti-analysis-v1")


if __name__ == "__main__":
    unittest.main()
