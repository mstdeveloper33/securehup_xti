"""Read-only engine and company-scoped platform contracts for abuse contacts."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.domain.abuse_contacts import AbuseContactError
from xti.domain.engine import EngineContractError, parse_engine_request
from xti.domain.platform_engine import parse_platform_request
from xti.interfaces.engine import make_engine_service
from xti.interfaces.platform_engine import execute_platform_request


NOW = datetime(2026, 11, 25, 11, tzinfo=timezone.utc)


class AbuseContactContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve() / "companies"
        self.alpha = provision_company_workspace(root, "alpha")
        self.beta = provision_company_workspace(root, "beta")
        self.alpha_storage = SQLiteAssetRepository(self.alpha.database)
        self.alpha_storage.initialize(); SQLiteAssetRepository(self.beta.database).initialize()
        cases = CaseService(
            SQLiteCaseRepository(self.alpha.database),
            CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.alpha.database)),
            clock=lambda: NOW,
        )
        self.case = cases.create(
            "Alpha taklit domain vakası", summary="Firma alanına bağlı iletişim kabulü.",
            reason="Platform abuse iletişim sözleşmesi sınanıyor.",
        ).case
        asset, _ = self.alpha_storage.add("alpha.example")
        finding_id = str(uuid4())
        with self.alpha_storage._connection() as connection, connection:
            connection.execute(
                "INSERT INTO findings (id,asset_id,asset_value,domain,rule_version,reasons,status,created_at,last_seen_at) "
                "VALUES (?,?,?,?,?,?,'suspicious',?,?)",
                (finding_id, asset.id, asset.value, "alpha-login.example", "contact/contract",
                 json.dumps(["marka benzerliği"]), NOW.isoformat(), NOW.isoformat()),
            )
        self.evidence = cases.add_evidence(
            self.case.id, "finding", finding_id,
            reason="Firma kapsamındaki domain kanıtı bağlandı.",
        ).evidence

    @staticmethod
    def request(operation, parameters, request_id="contact:request"):
        return {
            "contract_version": 1, "request_id": request_id,
            "operation": operation, "parameters": parameters,
        }

    def test_engine_exposes_contact_reads_without_writing(self):
        request = parse_engine_request(self.request("action.contact.capabilities", {}))
        before = self.alpha.database.read_bytes()
        result = make_engine_service(
            self.alpha.database, operation=request.operation,
        ).execute(request)
        self.assertTrue(result["review"]["required_for_takedown"])
        self.assertIsInstance(result["sources"]["whois"]["available"], bool)
        self.assertFalse(result["automatic_submission"])
        self.assertEqual(self.alpha.database.read_bytes(), before)

    def test_platform_write_is_workspace_fenced_and_company_isolated(self):
        parameters = {
            "case_id": self.case.id, "evidence_link_id": self.evidence.id,
            "subject_kind": "domain", "subject_value": "alpha-login.example",
            "interval_seconds": 3600, "include_whois": False,
            "actor": "analyst@alpha.example",
            "reason": "Firma kapsamındaki taklit domain için iletişim rotası izlenecek.",
            "idempotency_key": "alpha:contact:watch",
            "expected_workspace_id": self.alpha.workspace_id,
        }
        added = execute_platform_request(
            self.alpha,
            parse_platform_request(self.request("action.contact.watch.add", parameters)),
        )
        self.assertEqual(added["subject_value"], "alpha-login.example")
        listed = execute_platform_request(
            self.alpha,
            parse_platform_request(self.request("action.contact.watches", {
                "case_id": self.case.id, "offset": 0, "limit": 50,
            })),
        )
        self.assertEqual(listed["total_count"], 1)
        with self.assertRaisesRegex(AbuseContactError, "bulunamadı"):
            execute_platform_request(
                self.beta,
                parse_platform_request(self.request("action.contact.watch.show", {
                    "watch_id": added["id"],
                })),
            )
        wrong = dict(parameters)
        wrong["idempotency_key"] = "alpha:contact:wrong-workspace"
        wrong["expected_workspace_id"] = self.beta.workspace_id
        with self.assertRaisesRegex(EngineContractError, "güncel firma"):
            execute_platform_request(
                self.alpha,
                parse_platform_request(self.request("action.contact.watch.add", wrong)),
            )

    def test_platform_contract_rejects_unknown_fields_and_missing_fence(self):
        requests = (
            self.request("action.contact.plan", {
                "case_id": self.case.id, "evidence_link_id": self.evidence.id,
                "subject_kind": "domain", "subject_value": "alpha-login.example",
                "path": "/tmp/forbidden",
            }),
            self.request("action.contact.watch.add", {
                "case_id": self.case.id, "evidence_link_id": self.evidence.id,
                "subject_kind": "domain", "subject_value": "alpha-login.example",
                "interval_seconds": 3600, "include_whois": False,
                "actor": "analyst@alpha.example", "reason": "Eksik workspace fence.",
                "idempotency_key": "missing-fence",
            }),
        )
        for request in requests:
            with self.subTest(request=request), self.assertRaises(EngineContractError):
                parse_platform_request(request)


if __name__ == "__main__":
    unittest.main()
