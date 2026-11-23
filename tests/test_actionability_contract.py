"""Read-only engine and company-scoped platform contracts for P06."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.domain.assets import ValidationError
from xti.domain.engine import EngineContractError, parse_engine_request
from xti.domain.platform_engine import parse_platform_request
from xti.interfaces.engine import make_engine_service
from xti.interfaces.platform_engine import execute_platform_request


NOW = datetime(2026, 11, 22, 10, tzinfo=timezone.utc)


class ActionabilityContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve() / "companies"
        self.a = provision_company_workspace(root, "company-a")
        self.b = provision_company_workspace(root, "company-b")
        SQLiteAssetRepository(self.a.database).initialize()
        SQLiteAssetRepository(self.b.database).initialize()
        cases = CaseService(
            SQLiteCaseRepository(self.a.database),
            CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.a.database)),
            clock=lambda: NOW,
        )
        self.case = cases.create(
            "Company A defensive case", summary="Company A scoped evidence review.",
            reason="Platform contract acceptance.",
        ).case

    @staticmethod
    def request(operation, parameters):
        return {"contract_version": 1, "request_id": "p06:request", "operation": operation, "parameters": parameters}

    def test_engine_reads_capability_and_runbook_without_writing(self):
        capability = parse_engine_request(self.request("action.capabilities", {}))
        self.assertFalse(make_engine_service(self.a.database, operation=capability.operation).execute(capability)["takedown"]["automatic_submission"])
        request = parse_engine_request(self.request("action.runbook.plan", {"case_id": self.case.id}))
        before = self.a.database.read_bytes()
        result = make_engine_service(self.a.database, operation=request.operation).execute(request)
        self.assertEqual(result["case_id"], self.case.id)
        self.assertEqual(self.a.database.read_bytes(), before)

    def test_platform_write_has_workspace_fence_and_company_isolation(self):
        plan_request = parse_platform_request(self.request("action.runbook.plan", {"case_id": self.case.id}))
        plan = execute_platform_request(self.a, plan_request)
        with self.assertRaises(ValidationError):
            execute_platform_request(self.b, plan_request)
        wrong = parse_platform_request(self.request("action.runbook.apply", {
            "case_id": self.case.id, "expected_plan_sha256": plan["plan_sha256"],
            "idempotency_key": "platform:p06:1", "reason": "Company-scoped plan apply.",
            "expected_workspace_id": self.b.workspace_id,
        }))
        with self.assertRaisesRegex(EngineContractError, "güncel firma"):
            execute_platform_request(self.a, wrong)
        correct = parse_platform_request(self.request("action.runbook.apply", {
            "case_id": self.case.id, "expected_plan_sha256": plan["plan_sha256"],
            "idempotency_key": "platform:p06:1", "reason": "Company-scoped plan apply.",
            "expected_workspace_id": self.a.workspace_id,
        }))
        applied = execute_platform_request(self.a, correct)
        self.assertEqual(applied["case_id"], self.case.id)
        self.assertGreater(len(applied["created_task_ids"]), 0)

    def test_contract_rejects_unknown_fields_and_missing_workspace_fence(self):
        invalid = (
            self.request("action.runbook.plan", {"case_id": self.case.id, "path": "/tmp/x"}),
            self.request("action.runbook.apply", {
                "case_id": self.case.id, "expected_plan_sha256": "0" * 64,
                "idempotency_key": "x", "reason": "missing workspace",
            }),
        )
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(EngineContractError):
                parse_platform_request(request)


if __name__ == "__main__":
    unittest.main()
