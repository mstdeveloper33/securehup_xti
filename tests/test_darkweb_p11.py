"""P11 aggregate exposure and minimized underground-source acceptance."""

from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from xti.adapters.darkweb_monitoring_inputs import SQLiteDarkwebInputs
from xti.adapters.darkweb_monitoring_schema import (
    DEFINITIONS as DARKWEB_DEFINITIONS, V99_DEFINITIONS, V99_DDL,
)
from xti.adapters.lunar_domain_exposure import (
    BASE as LUNAR_BASE, LunarDomainExposureError, LunarDomainExposureSource,
    SOURCE_REFERENCE as LUNAR_REFERENCE,
)
from xti.adapters.ail_intake_file import read_ail_envelope
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_darkweb_monitoring import (
    SQLiteDarkwebRepository, company_in, source_run_in,
)
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.application.darkweb_monitoring import DarkwebService
from xti.domain.darkweb_monitoring import DarkwebError, PREFIX
from xti.domain.darkweb_source_intake import lunar_record
from xti.domain.organizations import normalize_organization_target
from tests.test_darkweb_monitoring import AT


class Response(BytesIO):
    def __init__(self, body: bytes, url: str):
        super().__init__(body)
        self.url = url
        self.code = 200
        self.headers = {
            "Content-Type": "application/json", "Content-Length": str(len(body)),
        }

    def getcode(self):
        return self.code

    def geturl(self):
        return self.url


def lunar_payload(*, status="REPORT_READY", total=3):
    report = None
    if status == "REPORT_READY":
        report = {
            "domain": "example.com", "generated_at": "2026-11-21T12:00:00",
            "period": {"from": "2025-11-01", "to": "2026-10-31"},
            "summary": {
                "total_events": total, "infostealer_events": 1 if total else 0,
                "data_breach_events": total - 1 if total else 0,
                "employee_events": 1 if total else 0,
                "client_events": total - 1 if total else 0,
                "first_seen": "2026-01-02" if total else None,
                "last_seen": "2026-10-03" if total else None,
            },
            "top_login_urls": [{"url": "https://private.example/login", "events": total}],
        }
    return {
        "requestUuid": "request-one", "domain": "example.com",
        "periodFrom": "2025-11-01", "periodTo": "2026-10-31",
        "status": status, "report": report,
    }


class LunarBoundaryTests(unittest.TestCase):
    def source(self, payload):
        url = LUNAR_BASE + "?domain=example.com"
        opener = Mock()
        opener.open.return_value = Response(json.dumps(payload).encode(), url)
        return LunarDomainExposureSource(
            opener=opener,
            now=lambda: datetime(2026, 11, 21, 12, tzinfo=timezone.utc),
            monotonic=Mock(return_value=0),
        ), opener

    def test_complete_response_keeps_only_aggregate_metrics(self):
        source, opener = self.source(lunar_payload())
        result = source.fetch("example.com")
        self.assertEqual((result["status"], len(result["records"])), ("complete", 1))
        record = result["records"][0]
        self.assertEqual(record["body"]["total_events"], 3)
        encoded = json.dumps(result)
        self.assertNotIn("private.example", encoded)
        self.assertNotIn("top_login_urls", encoded)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, LUNAR_BASE + "?domain=example.com")
        self.assertNotIn("Authorization", request.headers)

    def test_generating_report_is_pending_not_empty_success(self):
        source, _ = self.source(lunar_payload(status="GENERATING_REPORT"))
        result = source.fetch("example.com")
        self.assertEqual((result["status"], result["records"]), ("pending", []))

    def test_scope_and_inconsistent_totals_fail_closed(self):
        crossed = lunar_payload()
        crossed["report"]["domain"] = "other.example"
        source, _ = self.source(crossed)
        with self.assertRaises(LunarDomainExposureError) as caught:
            source.fetch("example.com")
        self.assertEqual(caught.exception.code, "source_invalid")
        malformed = lunar_payload()
        malformed["report"]["summary"]["total_events"] = 99
        source, _ = self.source(malformed)
        with self.assertRaises(LunarDomainExposureError):
            source.fetch("example.com")


class FakeLunar:
    def __init__(self):
        self.calls = 0
        self.status = "complete"
        self.total = 3
        self.error = None

    def fetch(self, domain):
        self.calls += 1
        if self.error:
            raise self.error
        if self.status == "pending":
            return {
                "provider": "lunar_domain", "mode": "snapshot", "status": "pending",
                "domain": domain, "source_url": LUNAR_BASE,
                "source_reference": LUNAR_REFERENCE, "fetched_at": AT,
                "content_sha256": "d" * 64, "records": [],
            }
        summary = {
            "total_events": self.total,
            "infostealer_events": 1 if self.total else 0,
            "data_breach_events": self.total - 1 if self.total else 0,
            "employee_events": 1 if self.total else 0,
            "client_events": self.total - 1 if self.total else 0,
            "first_seen": "2026-01-02" if self.total else None,
            "last_seen": "2026-10-03" if self.total else None,
        }
        return {
            "provider": "lunar_domain", "mode": "snapshot", "status": "complete",
            "domain": domain, "source_url": LUNAR_BASE,
            "source_reference": LUNAR_REFERENCE, "fetched_at": AT,
            "content_sha256": "e" * 64,
            "records": [lunar_record(domain, "2025-11-01", "2026-10-31", summary)],
        }


def ail_batch(*, match_value="example.com", claim_type="data_leak"):
    return {
        "contract_version": 1, "source": "ail-framework", "ail_version": "7.1",
        "ail_commit": "4b94304bcd4d3d08b9e0c0772be4773e6bbbd350",
        "connector_version": "xti-ail-1",
        "records": [{
            "object_reference_sha256": "b" * 64, "evidence_sha256": "c" * 64,
            "object_type": "item", "object_subtype": "paste", "network": "tor",
            "observed_at": AT, "match_kind": "domain", "match_value": match_value,
            "claim_type": claim_type,
        }],
    }


class P11StorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        storage = SQLiteAssetRepository(self.path)
        storage.initialize()
        storage.add("example.com")
        organizations = SQLiteOrganizationRepository(self.path)
        self.organization = organizations.add(
            name_key="example corp", display_name="Example Corp",
            reason="P11 acceptance scope", recorded_at=AT,
        ).organization
        organizations.link(
            self.organization.id, normalize_organization_target("domain", "example.com"),
            reason="P11 exact domain", recorded_at=AT,
        )
        self.lunar = FakeLunar()
        self.repository = SQLiteDarkwebRepository(self.path)
        self.service = DarkwebService(
            self.repository, SQLiteDarkwebInputs(self.path),
            domain_exposure_source=self.lunar, now=lambda: AT,
        )
        self.profile = self.service.execute(
            PREFIX + "profile.add", name="P11 sources",
            organization_id=self.organization.id,
            sources=["lunar_domain", "ail_tracker"], interval_seconds=900,
            idempotency_key="p11-profile",
        )

    def refresh_lunar(self, key="lunar-one"):
        return self.service.execute(
            PREFIX + "lunar.refresh", identifier=self.profile["id"],
            domain="example.com", expected_revision=1, idempotency_key=key,
        )

    def import_ail(self, batch=None, key="ail-one"):
        batch = batch or ail_batch()
        preview = self.service.execute(
            PREFIX + "ail.preview", identifier=self.profile["id"], batch=batch,
        )
        result = self.service.execute(
            PREFIX + "ail.import", identifier=self.profile["id"], expected_revision=1,
            expected_content_sha256=preview["content_sha256"], batch=batch,
            idempotency_key=key,
        )
        return preview, result

    def test_end_to_end_sources_feed_existing_review_and_company_lifecycle(self):
        lunar = self.refresh_lunar()
        preview, ail = self.import_ail()
        self.assertEqual((lunar["status"], ail["status"]), ("complete", "complete"))
        self.assertEqual(preview["record_count"], 1)
        run = self.service.execute(
            PREFIX + "run", identifier=self.profile["id"], expected_revision=1,
            force=True, idempotency_key="analysis-one",
        )
        self.assertEqual(run["report"]["counts"]["domain_exposure"], 1)
        self.assertEqual(run["report"]["counts"]["underground_mention"], 1)
        findings = self.service.execute(PREFIX + "findings", profile_id=self.profile["id"])
        self.assertEqual({item["kind"] for item in findings["items"]}, {
            "domain_exposure", "underground_mention",
        })
        finding = findings["items"][0]
        review = self.service.execute(
            PREFIX + "review", identifier=finding["id"], evidence_id=finding["evidence_id"],
            expected_revision=0, expected_observation_revision=1,
            decision="uncertain", reason="Kaynak iddiası insan incelemesi bekliyor.",
            idempotency_key="p11-review",
        )
        self.assertEqual(review["decision"], "uncertain")
        with SQLiteAssetRepository(self.path)._connection(readonly=True) as connection:
            company = company_in(connection, self.organization.id)
        self.assertEqual(company["profiles"]["items"][0]["external_source_status"]
                         ["lunar_domain"]["status"], "complete")

    def test_pending_and_failure_preserve_last_complete_snapshot(self):
        complete = self.refresh_lunar()
        self.lunar.status = "pending"
        pending = self.refresh_lunar("lunar-pending")
        self.assertEqual(pending["status"], "pending")
        plan = self.repository.plan(self.profile["id"])
        snapshot = SQLiteDarkwebInputs(self.path).capture(plan, AT)
        lunar = next(item for item in snapshot["sources"] if item["key"] == "lunar_domain")
        self.assertEqual(lunar["latest_status"], "pending")
        self.assertTrue(lunar["successful_snapshot_available"])
        self.assertEqual(len(lunar["records"]), 1)
        self.lunar.error = LunarDomainExposureError("source_unavailable", "private detail")
        with self.assertRaises(DarkwebError) as caught:
            self.refresh_lunar("lunar-failed")
        self.assertEqual(caught.exception.code, "source_unavailable")
        runs = self.service.execute(
            PREFIX + "source.runs", profile_id=self.profile["id"], provider="lunar_domain",
        )["items"]
        self.assertEqual([row["status"] for row in runs], ["complete", "pending", "failed"])
        self.assertEqual(complete["snapshot_sha256"], runs[1]["snapshot_sha256"])

    def test_zero_events_are_complete_without_a_finding_and_replay_is_free(self):
        self.lunar.total = 0
        complete = self.refresh_lunar()
        replay = self.refresh_lunar()
        self.assertEqual((complete["status"], replay["replayed"], self.lunar.calls),
                         ("complete", True, 1))
        run = self.service.execute(
            PREFIX + "run", identifier=self.profile["id"], expected_revision=1,
            force=True, idempotency_key="zero-analysis",
        )
        self.assertEqual(run["report"]["counts"]["domain_exposure"], 0)

    def test_ail_scope_and_minimization_reject_raw_or_cross_company_input(self):
        before = self.path.read_bytes()
        crossed = ail_batch(match_value="other.example")
        with self.assertRaisesRegex(Exception, "kuruluş kapsamına"):
            self.service.execute(PREFIX + "ail.preview", identifier=self.profile["id"], batch=crossed)
        raw = ail_batch()
        raw["records"][0]["excerpt"] = "alice@example.com:secret"
        with self.assertRaisesRegex(Exception, "alanları"):
            self.service.execute(PREFIX + "ail.preview", identifier=self.profile["id"], batch=raw)
        self.assertEqual(self.path.read_bytes(), before)
        self.import_ail()
        encoded = self.path.read_bytes()
        self.assertNotIn(b".onion", encoded)
        self.assertNotIn(b"alice@example.com", encoded)

    def test_source_chain_detects_tampering(self):
        run = self.refresh_lunar()
        with SQLiteAssetRepository(self.path)._connection() as connection, connection:
            connection.execute(
                "UPDATE darkweb_source_runs SET record_count=99 WHERE id=?", (run["id"],),
            )
        with self.repository.connection() as connection, self.assertRaises(StorageError):
            source_run_in(connection, run["id"])

    def test_interrupted_source_run_is_explicitly_recovered(self):
        values = {
            "identifier": self.profile["id"], "domain": "example.com",
            "expected_revision": 1, "idempotency_key": "reserved-lunar",
        }
        plan = self.repository.source_plan(
            self.profile["id"], "lunar_domain", "example.com",
        )
        run, replayed = self.repository.reserve_source(
            PREFIX + "lunar.refresh", values, plan, {
                "provider": "lunar_domain", "mode": "snapshot",
                "target": "example.com", "source_reference": LUNAR_REFERENCE,
            }, AT,
        )
        self.assertFalse(replayed)
        recovered = self.service.execute(
            PREFIX + "recover", identifier=run["id"],
            idempotency_key="recover-reserved-lunar",
        )
        self.assertEqual((recovered["status"], recovered["error_code"]),
                         ("interrupted", "explicit_operator_recovery"))
        self.refresh_lunar("after-recovery")

    def test_bounded_file_reader_accepts_regular_file_and_rejects_symlink(self):
        envelope = self.path.parent / "ail-envelope.json"
        envelope.write_text(json.dumps(ail_batch()), encoding="utf-8")
        self.assertEqual(read_ail_envelope(envelope)["source"], "ail-framework")
        link = self.path.parent / "ail-envelope-link.json"
        link.symlink_to(envelope)
        with self.assertRaisesRegex(Exception, "güvenli"):
            read_ail_envelope(link)


class P11MigrationTests(unittest.TestCase):
    def test_legacy_version_accepts_only_empty_exact_staged_p11_tables(self):
        from xti.adapters.schema import SchemaError, validate_schema
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "xti.db"
            SQLiteAssetRepository(path).initialize()
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("PRAGMA user_version=99")
                self.assertEqual(validate_schema(connection, allow_legacy=True), 99)
                connection.execute(
                    "INSERT INTO darkweb_source_changes "
                    "(id,run_id,record_id,action,created_at) VALUES (?,?,?,?,?)",
                    ("future-change", "future-run", "future-record", "added", AT),
                )
                with self.assertRaisesRegex(SchemaError, "P11 dark web kayıtları boş"):
                    validate_schema(connection, allow_legacy=True)

    def test_schema99_to_100_is_atomic_and_preserves_profile_identity(self):
        from xti.adapters.schema import SCHEMA_VERSION, validate_schema
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "data" / "xti.db"
            storage = SQLiteAssetRepository(path)
            storage.initialize()
            organization = SQLiteOrganizationRepository(path).add(
                name_key="legacy p11", display_name="Legacy P11",
                reason="schema99 fixture", recorded_at=AT,
            ).organization
            repository = SQLiteDarkwebRepository(path)
            profile = repository.mutate(PREFIX + "profile.add", {
                "name": "Legacy profile", "organization_id": organization.id,
                "sources": ["ransomlook"], "interval_seconds": 900,
                "idempotency_key": "legacy-profile",
            }, AT)
            with closing(sqlite3.connect(path)) as connection, connection:
                for table in V99_DEFINITIONS:
                    columns = ["sequence", *(name for name, _ in V99_DEFINITIONS[table])]
                    names = ",".join(columns)
                    connection.execute(
                        f"CREATE TEMP TABLE old_{table} AS SELECT {names} FROM {table} ORDER BY sequence"
                    )
                for table in reversed(tuple(DARKWEB_DEFINITIONS)):
                    connection.execute("DROP TABLE " + table)
                for statement in V99_DDL:
                    connection.execute(statement)
                for table in V99_DEFINITIONS:
                    columns = ["sequence", *(name for name, _ in V99_DEFINITIONS[table])]
                    names = ",".join(columns)
                    connection.execute(
                        f"INSERT INTO {table} ({names}) SELECT {names} FROM old_{table} ORDER BY sequence"
                    )
                connection.execute("PRAGMA user_version=99")
                self.assertEqual(validate_schema(connection, allow_legacy=True), 99)
            before = path.read_bytes()

            from xti.adapters.darkweb_monitoring_schema import migrate_v100
            def interrupted(connection):
                migrate_v100(connection)
                raise KeyboardInterrupt("controlled schema100 interruption")

            with patch("xti.adapters.sqlite.migrate_darkweb_p11_schema", side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    storage.migrate()
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(storage.migrate()["to_version"], SCHEMA_VERSION)
            with storage._connection(readonly=True) as connection:
                self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
                row = connection.execute(
                    "SELECT sequence,id FROM darkweb_profiles WHERE id=?", (profile["id"],),
                ).fetchone()
                self.assertEqual(row, (1, profile["id"]))
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM darkweb_source_runs"
                ).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
