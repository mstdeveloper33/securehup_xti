"""P07 terminal, read-only engine and company-scoped platform acceptance."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.domain.engine import EngineContractError, parse_engine_request
from xti.domain.organizations import normalize_organization_target
from xti.domain.platform_engine import parse_platform_request
from xti.interfaces.cli import main
from xti.interfaces.engine import make_engine_service
from xti.interfaces.platform_engine import execute_platform_request


class UnifiedMonitoringContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        company_root = self.root / "companies"
        self.alpha = provision_company_workspace(company_root, "alpha")
        self.beta = provision_company_workspace(company_root, "beta")
        storage = SQLiteAssetRepository(self.alpha.database)
        storage.initialize()
        SQLiteAssetRepository(self.beta.database).initialize()
        storage.add("example.com")
        organizations = SQLiteOrganizationRepository(self.alpha.database)
        self.organization = organizations.add(
            name_key="example corp", display_name="Example Corp",
            reason="P07 contract fixture", recorded_at="2026-11-22T10:00:00+00:00",
        ).organization
        organizations.link(
            self.organization.id, normalize_organization_target("domain", "example.com"),
            reason="P07 explicit scope", recorded_at="2026-11-22T10:01:00+00:00",
        )
        self.local_data = self.root / "local-data"
        local_storage = SQLiteAssetRepository(self.local_data / "xti.db")
        local_storage.initialize()
        local_storage.add("example.com")
        local_organizations = SQLiteOrganizationRepository(self.local_data / "xti.db")
        self.local_organization = local_organizations.add(
            name_key="local corp", display_name="Local Corp",
            reason="P07 CLI fixture", recorded_at="2026-11-22T10:00:00+00:00",
        ).organization
        local_organizations.link(
            self.local_organization.id, normalize_organization_target("domain", "example.com"),
            reason="P07 local scope", recorded_at="2026-11-22T10:01:00+00:00",
        )
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("P07 must stay offline")))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("P07 must stay offline")))

    @staticmethod
    def request(operation, parameters):
        return {"contract_version": 1, "request_id": "p07:request",
                "operation": operation, "parameters": parameters}

    def policy_parameters(self, workspace_id):
        return {
            "name": "Platform unified watch", "organization_id": self.organization.id,
            "subjects": [{"kind": "domain", "value": "example.com"}],
            "record_kinds": ["domain"], "match_modes": ["exact", "prefix"],
            "notify_on": ["added", "updated"], "minimum_change_count": 1,
            "priority": "high", "interval_seconds": 300, "max_matches": 100,
            "include_inactive": False, "actor": "platform-analyst",
            "reason": "Company-scoped P07 policy acceptance.",
            "idempotency_key": "p07-platform-policy",
            "expected_workspace_id": workspace_id,
        }

    def test_engine_read_and_platform_write_are_versioned_and_company_isolated(self):
        capability_request = parse_engine_request(self.request("monitoring.capabilities", {}))
        capability = make_engine_service(
            self.alpha.database, operation=capability_request.operation,
        ).execute(capability_request)
        self.assertTrue(capability["stored_evidence_only"])
        self.assertFalse(capability["network_access"])

        wrong = parse_platform_request(self.request(
            "monitoring.policy.add", self.policy_parameters(self.beta.workspace_id),
        ))
        with self.assertRaisesRegex(EngineContractError, "güncel firma"):
            execute_platform_request(self.alpha, wrong)
        correct = parse_platform_request(self.request(
            "monitoring.policy.add", self.policy_parameters(self.alpha.workspace_id),
        ))
        policy = execute_platform_request(self.alpha, correct)
        self.assertEqual(policy["organization"]["id"], self.organization.id)

        read = parse_engine_request(self.request("monitoring.policy.show", {"identifier": policy["id"]}))
        self.assertEqual(execute_platform_request(self.alpha, read)["id"], policy["id"])
        with self.assertRaisesRegex(Exception, "bulunamadı"):
            execute_platform_request(self.beta, read)

        run = parse_platform_request(self.request("monitoring.run", {
            "identifier": policy["id"], "expected_revision": policy["revision"],
            "force": False, "idempotency_key": "p07-platform-baseline",
            "expected_workspace_id": self.alpha.workspace_id,
        }))
        completed = execute_platform_request(self.alpha, run)
        self.assertTrue(completed["report"]["silent_baseline"])
        matches = parse_engine_request(self.request("monitoring.run.matches", {
            "identifier": completed["id"], "offset": 0, "limit": 100,
        }))
        self.assertEqual(execute_platform_request(self.alpha, matches)["total_count"], 1)
        changes = parse_engine_request(self.request("monitoring.run.changes", {
            "identifier": completed["id"], "offset": 0, "limit": 100,
        }))
        self.assertEqual(execute_platform_request(self.alpha, changes)["total_count"], 1)

    def test_terminal_commands_create_and_run_a_silent_baseline(self):
        def invoke(*arguments):
            output, error = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = main(["--data-dir", str(self.local_data), "--json", *arguments])
            self.assertEqual((code, error.getvalue()), (0, ""), error.getvalue())
            response = json.loads(output.getvalue())
            self.assertTrue(response["ok"], response)
            return response["data"]

        policy = invoke(
            "monitoring", "policy-add", "--name", "CLI unified watch",
            "--organization", self.local_organization.id, "--domain", "example.com",
            "--record-kind", "domain", "--actor", "cli-analyst",
            "--reason", "CLI üzerinden P07 politikası oluşturuluyor.",
            "--idempotency-key", "p07-cli-policy",
        )
        baseline = invoke(
            "monitoring", "run", policy["id"], "--expected-revision", "1",
            "--idempotency-key", "p07-cli-baseline",
        )
        self.assertTrue(baseline["report"]["silent_baseline"])
        self.assertIsNone(baseline["alert_id"])
        self.assertEqual(invoke(
            "monitoring", "run-matches", baseline["id"], "--limit", "1",
        )["total_count"], 1)
        self.assertEqual(invoke(
            "monitoring", "run-changes", baseline["id"], "--limit", "1",
        )["total_count"], 1)

    def test_contract_rejects_unknown_fields_and_missing_workspace_fence(self):
        with self.assertRaises(EngineContractError):
            parse_platform_request(self.request("monitoring.policy.add", {
                key: value for key, value in self.policy_parameters(self.alpha.workspace_id).items()
                if key != "expected_workspace_id"
            }))
        with self.assertRaises(EngineContractError):
            parse_engine_request(self.request("monitoring.capabilities", {"network": True}))


if __name__ == "__main__":
    unittest.main()
