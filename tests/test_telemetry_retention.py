"""P08/P12 telemetry retention, holds, isolation, archive and restore acceptance."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from xti.adapters.retention_payloads import MARKER
from xti.adapters import data_retention_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_data_retention import SQLiteDataRetentionRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_telemetry import SQLiteTelemetryRepository
from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.application.data_retention import DataRetentionService
from xti.application.telemetry import TelemetryService
from xti.domain.data_retention import PREFIX as RETENTION_PREFIX, TELEMETRY_FAMILY
from xti.domain.telemetry import PREFIX as TELEMETRY_PREFIX


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value.isoformat()

    def advance(self, seconds=60):
        self.value += timedelta(seconds=seconds)


def record(native_id: str, domain: str, suffix: str = "initial") -> dict:
    # Repetitive, valid normalized evidence makes compression behavior
    # deterministic without storing any sensitive or raw sensor material.
    attributes = [
        {"name": "sensor_name", "value": ("authorized-telemetry-" + suffix + "-") * 18}
        for _index in range(80)
    ]
    return {
        "native_id": native_id, "kind": "dns_query",
        "event_at": "2026-01-01T08:00:00+00:00",
        "summary": f"Authorized sinkhole observation {suffix} for {domain}",
        "outcome": "observed", "src_ip": "192.0.2.25", "dst_ip": "192.0.2.53",
        "src_port": 5353, "dst_port": 53, "protocol": "udp", "domain": domain,
        "url": None, "hashes": {},
        "indicators": [{"type": "domain", "value": domain}],
        "attributes": attributes, "tags": ["authorized-sinkhole"],
    }


class TelemetryRetentionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path); self.storage.initialize()
        organizations = SQLiteOrganizationRepository(self.path)
        self.alpha = organizations.add(
            name_key="alpha", display_name="Alpha",
            reason="Telemetry retention alpha", recorded_at="2026-01-01T07:00:00+00:00",
        ).organization
        self.beta = organizations.add(
            name_key="beta", display_name="Beta",
            reason="Telemetry retention beta", recorded_at="2026-01-01T07:01:00+00:00",
        ).organization
        self.telemetry_clock = Clock(datetime(2026, 1, 1, 9, tzinfo=timezone.utc))
        self.telemetry = TelemetryService(
            SQLiteTelemetryRepository(self.path), now=self.telemetry_clock,
        )
        self.alpha_source = self._source(self.alpha.id, "alpha-source")
        self.beta_source = self._source(self.beta.id, "beta-source")
        self.eligible = self._ingest(
            self.alpha_source, record("alpha:eligible", "eligible.alpha.test"), "ingest-eligible",
        )
        self.held = self._ingest(
            self.alpha_source, record("alpha:held", "held.alpha.test"), "ingest-held",
        )
        self.case_linked = self._ingest(
            self.alpha_source, record("alpha:case", "case.alpha.test"), "ingest-case",
        )
        self.beta_record = self._ingest(
            self.beta_source, record("beta:isolated", "isolated.beta.test"), "ingest-beta",
        )

        cases = CaseService(
            SQLiteCaseRepository(self.path),
            CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.path)),
            clock=lambda: self.telemetry_clock.value,
        )
        case = cases.create(
            "Protected telemetry", summary="Active telemetry evidence stays hot.",
            priority="high", reason="P08/P12 case protection acceptance.",
        ).case
        cases.add_evidence(
            case.id, "telemetry", self.case_linked["id"],
            reason="Active case automatically protects normalized telemetry.",
        )

        self.retention_clock = Clock(datetime(2026, 11, 23, 10, tzinfo=timezone.utc))
        self.retention = DataRetentionService(
            SQLiteDataRetentionRepository(self.path), now=self.retention_clock,
        )
        self.policy = self.retention.execute(
            RETENTION_PREFIX + "policy.add", name="Telemetry retention",
            organization_id=self.alpha.id, families=[TELEMETRY_FAMILY],
            archive_after_days=90, batch_limit=100,
            purpose="Bounded normalized telemetry lifecycle",
            retention_basis="Organization-approved telemetry policy",
            actor="privacy@example.test", reason="P08/P12 telemetry policy acceptance.",
            idempotency_key="telemetry-retention-policy",
        )
        self.hold = self.retention.execute(
            RETENTION_PREFIX + "hold.add", organization_id=self.alpha.id,
            family=TELEMETRY_FAMILY, record_id=self.held["id"], kind="investigation",
            actor="analyst@example.test", reason="Keep this telemetry body hot.",
            idempotency_key="telemetry-hold",
        )

    def _source(self, organization_id, key):
        return self.telemetry.execute(
            TELEMETRY_PREFIX + "source.add", name=key,
            organization_id=organization_id, source_kind="sinkhole",
            input_format="xti-sensor-v1", description="Controlled telemetry retention source",
            idempotency_key=key,
        )["source"]

    def _ingest(self, source, value, key):
        self.telemetry.execute(
            TELEMETRY_PREFIX + "ingest", source_id=source["id"],
            expected_revision=source["revision"], records=[value], idempotency_key=key,
        )
        return self.telemetry.execute(
            TELEMETRY_PREFIX + "records", organization_id=source["organization_id"],
            after=0, limit=500,
        )["items"][-1]

    def test_lossless_multi_generation_archive_hold_case_isolation_and_restore(self):
        before = self.telemetry.execute(
            TELEMETRY_PREFIX + "record.get", identifier=self.eligible["id"],
        )
        plan = self.retention.execute(
            RETENTION_PREFIX + "plan", identifier=self.policy["id"],
        )
        self.assertEqual(plan["families"], [TELEMETRY_FAMILY])
        self.assertEqual(plan["selected_count"], 1, plan)
        self.assertEqual(plan["explicit_hold_count"], 1)
        self.assertEqual(plan["case_protected_count"], 1)
        self.assertEqual(plan["items"][0]["record_id"], self.eligible["id"])

        archived = self.retention.execute(
            RETENTION_PREFIX + "apply", identifier=self.policy["id"],
            expected_revision=self.policy["revision"], token=plan["token"],
            actor="privacy@example.test", reason="Archive eligible telemetry losslessly.",
            idempotency_key="telemetry-archive-one",
        )
        self.assertEqual((archived["status"], archived["receipt"]["changed_count"]), ("complete", 1))
        self.assertEqual(archived["receipt"]["items"][0]["family"], TELEMETRY_FAMILY)
        self.assertIsNotNone(archived["receipt"]["backup_name"])
        with self.storage._connection(readonly=True) as connection:
            bodies = connection.execute(
                "SELECT r.body_json,v.body_json FROM telemetry_records r "
                "JOIN telemetry_record_versions v ON v.record_id=r.id WHERE r.id=?",
                (self.eligible["id"],),
            ).fetchone()
            self.assertTrue(all(value.startswith(MARKER + ":") for value in bodies))
            for untouched in (self.held["id"], self.case_linked["id"], self.beta_record["id"]):
                self.assertFalse(connection.execute(
                    "SELECT body_json FROM telemetry_records WHERE id=?", (untouched,),
                ).fetchone()[0].startswith(MARKER + ":"))
        after = self.telemetry.execute(
            TELEMETRY_PREFIX + "record.get", identifier=self.eligible["id"],
        )
        self.assertEqual(after["body"], before["body"])
        self.assertEqual(after["versions"]["items"][0]["body"], before["versions"]["items"][0]["body"])

        # A later revision remains valid: the first archive keeps revision 1,
        # while a second generation archives the new current body and revision 2.
        self.telemetry_clock.advance()
        self.telemetry.execute(
            TELEMETRY_PREFIX + "ingest", source_id=self.alpha_source["id"],
            expected_revision=self.alpha_source["revision"],
            records=[record("alpha:eligible", "eligible.alpha.test", "updated")],
            idempotency_key="ingest-eligible-update",
        )
        updated = self.telemetry.execute(
            TELEMETRY_PREFIX + "record.get", identifier=self.eligible["id"],
        )
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(len(updated["versions"]["items"]), 2)
        plan_two = self.retention.execute(
            RETENTION_PREFIX + "plan", identifier=self.policy["id"],
        )
        self.assertEqual(plan_two["selected_count"], 1, plan_two)
        archive_two = self.retention.execute(
            RETENTION_PREFIX + "apply", identifier=self.policy["id"],
            expected_revision=self.policy["revision"], token=plan_two["token"],
            actor="privacy@example.test", reason="Archive second telemetry generation.",
            idempotency_key="telemetry-archive-two",
        )
        self.assertEqual(archive_two["receipt"]["changed_count"], 1)
        self.assertEqual(self.telemetry.execute(
            TELEMETRY_PREFIX + "record.get", identifier=self.eligible["id"],
        )["body"], updated["body"])

        restored_one = self.retention.execute(
            RETENTION_PREFIX + "restore", identifier=archived["id"],
            actor="privacy@example.test", reason="Restore first telemetry generation.",
            idempotency_key="telemetry-restore-one",
        )
        self.assertEqual(restored_one["receipt"]["changed_count"], 1)
        restored_two = self.retention.execute(
            RETENTION_PREFIX + "restore", identifier=archive_two["id"],
            actor="privacy@example.test", reason="Restore second telemetry generation.",
            idempotency_key="telemetry-restore-two",
        )
        self.assertEqual(restored_two["receipt"]["changed_count"], 1)
        with self.storage._connection(readonly=True) as connection:
            values = connection.execute(
                "SELECT body_json FROM telemetry_record_versions WHERE record_id=? ORDER BY revision",
                (self.eligible["id"],),
            ).fetchall()
            self.assertTrue(all(not row[0].startswith(MARKER + ":") for row in values))
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM retention_archive_items WHERE active=1 AND family=?",
                (TELEMETRY_FAMILY,),
            ).fetchone()[0], 0)
        final = self.telemetry.execute(
            TELEMETRY_PREFIX + "record.get", identifier=self.eligible["id"],
        )
        self.assertEqual(final["body"], updated["body"])

    def test_archive_tamper_and_cross_organization_hold_fail_closed(self):
        with self.assertRaisesRegex(Exception, "bu kuruluşta"):
            self.retention.execute(
                RETENTION_PREFIX + "hold.add", organization_id=self.alpha.id,
                family=TELEMETRY_FAMILY, record_id=self.beta_record["id"], kind="legal",
                actor="legal@example.test", reason="Cross-organization hold must fail.",
                idempotency_key="cross-org-hold",
            )
        plan = self.retention.execute(RETENTION_PREFIX + "plan", identifier=self.policy["id"])
        archived = self.retention.execute(
            RETENTION_PREFIX + "apply", identifier=self.policy["id"],
            expected_revision=self.policy["revision"], token=plan["token"],
            actor="privacy@example.test", reason="Tamper acceptance archive.",
            idempotency_key="telemetry-tamper-archive",
        )
        with self.storage._connection() as connection, connection:
            row = connection.execute(
                "SELECT id,report_body FROM retention_archive_items "
                "WHERE archive_run_id=? AND family=?", (archived["id"], TELEMETRY_FAMILY),
            ).fetchone()
            original = row[1]
            connection.execute(
                "UPDATE retention_archive_items SET report_body=? WHERE id=?",
                (original + b"tampered", row[0]),
            )
        with self.assertRaises(StorageError):
            self.telemetry.execute(
                TELEMETRY_PREFIX + "record.get", identifier=self.eligible["id"],
            )
        with self.storage._connection() as connection, connection:
            connection.execute(
                "UPDATE retention_archive_items SET report_body=? WHERE id=?", (original, row[0]),
            )
        self.assertEqual(self.telemetry.execute(
            TELEMETRY_PREFIX + "record.get", identifier=self.eligible["id"],
        )["id"], self.eligible["id"])


class TelemetryRetentionMigrationTests(unittest.TestCase):
    def test_schema98_policy_hold_and_audit_survive_widening_with_backup(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "legacy.db"
        storage = SQLiteAssetRepository(path); storage.initialize()
        organization = SQLiteOrganizationRepository(path).add(
            name_key="legacy retention", display_name="Legacy Retention",
            reason="Schema98 migration fixture", recorded_at="2026-11-22T08:00:00+00:00",
        ).organization
        service = DataRetentionService(
            SQLiteDataRetentionRepository(path),
            now=Clock(datetime(2026, 11, 22, 9, tzinfo=timezone.utc)),
        )
        policy = service.execute(
            RETENTION_PREFIX + "policy.add", name="Legacy monitoring retention",
            organization_id=organization.id, families=["unified_monitoring_runs"],
            archive_after_days=90, batch_limit=100,
            purpose="Legacy policy preservation",
            retention_basis="Legacy approved policy", actor="migration",
            reason="Create schema98 policy row.", idempotency_key="legacy-policy",
        )
        hold = service.execute(
            RETENTION_PREFIX + "hold.add", organization_id=organization.id,
            family="unified_monitoring_runs", kind="legal", actor="migration",
            reason="Create schema98 wildcard hold.", idempotency_key="legacy-hold",
        )

        # Recreate the exact schema98 table declarations while retaining rows;
        # this is a controlled migration fixture, not production downgrade code.
        with storage._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            names = ("retention_holds", "retention_hold_events", "retention_archive_items")
            for name in names:
                connection.execute(f"CREATE TEMP TABLE fixture_{name} AS SELECT * FROM {name}")
            connection.execute("DROP TABLE retention_hold_events")
            connection.execute("DROP TABLE retention_holds")
            connection.execute("DROP TABLE retention_archive_items")
            wanted = set(names) | {
                "retention_holds_scope_active", "retention_hold_events_hold_revision",
                "retention_archive_run_sequence",
            }
            for statement in data_retention_schema.V97_DDL:
                if statement.split()[2] in wanted:
                    connection.execute(statement)
            for name in names:
                columns = ["sequence"] + [
                    column for column, _declaration
                    in data_retention_schema.V97_DEFINITIONS[name]
                ]
                joined = ",".join(columns)
                connection.execute(
                    f"INSERT INTO {name} ({joined}) SELECT {joined} "
                    f"FROM fixture_{name} ORDER BY sequence"
                )
                connection.execute(f"DROP TABLE temp.fixture_{name}")
            connection.execute("PRAGMA user_version=98")
            connection.commit()

        result = storage.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (98, SCHEMA_VERSION))
        self.assertTrue(Path(result["backup"]).is_file())
        with storage._connection(readonly=True) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute(
                "SELECT id FROM retention_policies WHERE id=?", (policy["id"],),
            ).fetchone()[0], policy["id"])
            self.assertEqual(connection.execute(
                "SELECT id FROM retention_holds WHERE id=?", (hold["id"],),
            ).fetchone()[0], hold["id"])
            self.assertGreaterEqual(connection.execute(
                "SELECT COUNT(*) FROM retention_audit_events",
            ).fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
