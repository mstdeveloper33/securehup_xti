"""P08 terminal, engine/platform contract and workspace isolation acceptance."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.domain.engine import EngineContractError, parse_engine_request
from xti.domain.platform_engine import parse_platform_request
from xti.interfaces.cli import main
from xti.interfaces.engine import make_engine_service
from xti.interfaces.platform_engine import execute_platform_request


class DataRetentionContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve() / "companies"
        self.alpha = provision_company_workspace(root, "alpha")
        self.beta = provision_company_workspace(root, "beta")
        SQLiteAssetRepository(self.alpha.database).initialize()
        SQLiteAssetRepository(self.beta.database).initialize()
        self.organization = SQLiteOrganizationRepository(self.alpha.database).add(
            name_key="alpha organization", display_name="Alpha Organization",
            reason="P08 platform fixture", recorded_at="2026-11-22T10:00:00+00:00",
        ).organization

    @staticmethod
    def request(operation, parameters):
        return {"contract_version": 1, "request_id": "p08:request",
                "operation": operation, "parameters": parameters}

    def parameters(self, workspace_id):
        return {
            "name": "Alpha retention", "organization_id": self.organization.id,
            "families": ["unified_monitoring_runs", "telemetry_records"],
            "archive_after_days": 90,
            "batch_limit": 100, "purpose": "Security monitoring retention",
            "retention_basis": "Organization-approved policy",
            "actor": "platform-privacy", "reason": "P08 platform policy acceptance.",
            "idempotency_key": "p08-platform-policy",
            "expected_workspace_id": workspace_id,
        }

    def test_engine_reads_platform_writes_and_workspace_isolation(self):
        request = parse_engine_request(self.request("retention.capabilities", {}))
        capability = make_engine_service(
            self.alpha.database, operation=request.operation,
        ).execute(request)
        self.assertFalse(capability["automatic_delete"])
        self.assertTrue(capability["case_evidence_auto_protected"])
        self.assertEqual(
            capability["managed_families"],
            ["unified_monitoring_runs", "telemetry_records"],
        )

        wrong = parse_platform_request(self.request(
            "retention.policy.add", self.parameters(self.beta.workspace_id),
        ))
        with self.assertRaisesRegex(EngineContractError, "güncel firma"):
            execute_platform_request(self.alpha, wrong)
        correct = parse_platform_request(self.request(
            "retention.policy.add", self.parameters(self.alpha.workspace_id),
        ))
        policy = execute_platform_request(self.alpha, correct)
        self.assertEqual(policy["organization"]["id"], self.organization.id)
        self.assertEqual(
            policy["definition"]["families"],
            ["telemetry_records", "unified_monitoring_runs"],
        )

        read = parse_engine_request(self.request(
            "retention.policy.show", {"identifier": policy["id"]},
        ))
        self.assertEqual(execute_platform_request(self.alpha, read)["id"], policy["id"])
        with self.assertRaisesRegex(Exception, "bulunamadı"):
            execute_platform_request(self.beta, read)

    def test_contract_rejects_unknown_fields_and_missing_workspace_fence(self):
        with self.assertRaises(EngineContractError):
            parse_platform_request(self.request("retention.policy.add", {
                key: value for key, value in self.parameters(self.alpha.workspace_id).items()
                if key != "expected_workspace_id"
            }))
        with self.assertRaises(EngineContractError):
            parse_engine_request(self.request("retention.capabilities", {"network": True}))

    def test_terminal_creates_reads_and_plans_an_organization_policy(self):
        def invoke(*arguments):
            output, error = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = main([
                    "--data-dir", str(self.alpha.data_dir), "--json", *arguments,
                ])
            self.assertEqual((code, error.getvalue()), (0, ""), error.getvalue())
            response = json.loads(output.getvalue())
            self.assertTrue(response["ok"], response)
            return response["data"]

        policy = invoke(
            "retention", "policy-add", "--name", "CLI retention",
            "--organization", self.organization.id,
            "--archive-after-days", "90", "--batch-limit", "100",
            "--actor", "cli-privacy", "--reason", "P08 CLI acceptance.",
            "--idempotency-key", "p08-cli-policy",
        )
        self.assertEqual(policy["definition"]["families"], ["unified_monitoring_runs"])
        self.assertEqual(invoke("retention", "policy-show", policy["id"])["id"], policy["id"])
        plan = invoke("retention", "plan", policy["id"])
        self.assertEqual((plan["selected_count"], plan["logical_record_delete"]), (0, False))


if __name__ == "__main__":
    unittest.main()
