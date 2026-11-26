"""Accumulated abuse-contact history remains paged and duplicate-free."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_abuse_contacts import SQLiteAbuseContactRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.application.abuse_contacts import AbuseContactService
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.domain.abuse_contact_contract import PREFIX
from tests.test_abuse_contacts import Sources, _success


NOW = datetime(2026, 11, 25, 13, tzinfo=timezone.utc)


class AbuseContactCapacityTests(unittest.TestCase):
    def test_250_unchanged_runs_are_retained_paged_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "xti.db"
            storage = SQLiteAssetRepository(path); storage.initialize()
            cases = CaseService(
                SQLiteCaseRepository(path),
                CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(path)),
                clock=lambda: NOW,
            )
            case = cases.create(
                "Accumulated contact history", summary="Bounded history acceptance.",
                reason="Contact history pagination is measured.",
            ).case
            asset, _ = storage.add("capacity.example")
            finding_id = str(uuid4())
            with storage._connection() as connection, connection:
                connection.execute(
                    "INSERT INTO findings (id,asset_id,asset_value,domain,rule_version,reasons,status,created_at,last_seen_at) "
                    "VALUES (?,?,?,?,?,?,'suspicious',?,?)",
                    (finding_id, asset.id, asset.value, "capacity-login.example", "contact/capacity",
                     json.dumps(["capacity"]), NOW.isoformat(), NOW.isoformat()),
                )
            evidence = cases.add_evidence(
                case.id, "finding", finding_id,
                reason="Capacity domain evidence is linked.",
            ).evidence
            source = Sources(*(
                _success(observed_at=NOW.isoformat(), subject="capacity-login.example")
                for _ in range(250)
            ))
            service = AbuseContactService(
                SQLiteAbuseContactRepository(path), source, clock=lambda: NOW,
            )
            watch = service.execute(
                PREFIX + "watch.add", case_id=case.id, evidence_link_id=evidence.id,
                subject_kind="domain", subject_value="capacity-login.example",
                interval_seconds=300, include_whois=False, actor="capacity-test",
                reason="Accumulated unchanged runs are retained.",
                idempotency_key="capacity:watch",
            )
            for index in range(250):
                run = service.execute(
                    PREFIX + "refresh", watch_id=watch["id"], expected_revision=1,
                    force=True, timeout_seconds=60,
                    idempotency_key=f"capacity:run:{index}",
                )
                self.assertEqual(run["added_count"], 1 if index == 0 else 0)
                self.assertEqual(run["unchanged_count"], 0 if index == 0 else 1)
            seen = []
            for offset in range(0, 250, 50):
                page = service.execute(
                    PREFIX + "runs", watch_id=watch["id"], offset=offset, limit=50,
                )
                self.assertEqual(page["total_count"], 250)
                seen.extend(item["id"] for item in page["items"])
            self.assertEqual(len(seen), 250)
            self.assertEqual(len(set(seen)), 250)
            candidates = service.execute(
                PREFIX + "candidates", watch_id=watch["id"], offset=0, limit=50,
            )
            self.assertEqual(candidates["total_count"], 1)
            self.assertEqual(storage.inspect()["action_contact_run_count"], 250)


if __name__ == "__main__":
    unittest.main()
