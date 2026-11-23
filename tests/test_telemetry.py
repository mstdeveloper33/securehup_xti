"""P12 normalized sensor/sandbox telemetry lifecycle and safety acceptance."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from xti.adapters.engine_records import SQLiteEngineRecordRepository
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_global_search import SQLiteGlobalSearchRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_telemetry import SQLiteTelemetryRepository
from xti.adapters.sqlite_unified_monitoring import SQLiteUnifiedMonitoringRepository
from xti.adapters.telemetry_files import preview_file_payload
from xti.adapters.unified_monitoring_inputs import SQLiteUnifiedMonitoringInputs
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.application.global_search import GlobalSearchService
from xti.application.inbox import InboxService
from xti.application.telemetry import TelemetryService
from xti.application.unified_monitoring import UnifiedMonitoringService
from xti.domain.assets import ValidationError
from xti.domain.engine import reference_for_result
from xti.domain.telemetry import PREFIX, TelemetryError, normalize_record
from xti.domain.unified_monitoring import PREFIX as MONITORING_PREFIX


class Clock:
    def __init__(self):
        self.value = datetime(2026, 11, 23, 8, tzinfo=timezone.utc)

    def __call__(self):
        return self.value.isoformat()

    def advance(self, seconds=60):
        self.value += timedelta(seconds=seconds)


def sensor_record(native_id="sinkhole:event-1", domain="securehup.example", *, summary=None):
    return {
        "native_id": native_id, "kind": "dns_query",
        "event_at": "2026-11-23T07:59:00+00:00",
        "summary": summary or f"Sinkhole DNS observation for {domain}",
        "outcome": "observed", "src_ip": "192.0.2.25",
        "dst_ip": "192.0.2.53", "src_port": 5353, "dst_port": 53,
        "protocol": "udp", "domain": domain, "url": None, "hashes": {},
        "indicators": [{"type": "domain", "value": domain}],
        "attributes": [{"name": "query_type", "value": "A"}],
        "tags": ["authorized-sinkhole"],
    }


class TelemetryAdapterTests(unittest.TestCase):
    def test_cowrie_adapter_omits_credentials_commands_messages_and_raw_event(self):
        rows = [
            {
                "eventid": "cowrie.session.connect", "timestamp": "2026-11-23T08:00:00Z",
                "session": "session-1", "src_ip": "198.51.100.4", "dst_ip": "192.0.2.4",
                "src_port": 50000, "dst_port": 22, "username": "admin-secret",
                "password": "password-secret", "input": "cat /etc/shadow",
                "message": "message-secret",
            },
            {
                "eventid": "cowrie.login.failed", "timestamp": "2026-11-23T08:01:00Z",
                "session": "session-1", "src_ip": "198.51.100.4", "dst_ip": "192.0.2.4",
                "src_port": 50000, "dst_port": 22, "username": "root-secret",
                "password": "guess-secret",
            },
            {
                "eventid": "cowrie.command.input", "timestamp": "2026-11-23T08:02:00Z",
                "session": "session-1", "src_ip": "198.51.100.4",
                "input": "curl secret.example/payload",
            },
        ]
        payload = "\n".join(json.dumps(row) for row in rows).encode()
        preview = preview_file_payload(payload, input_format="cowrie-jsonl")
        self.assertEqual((preview.input_count, preview.record_count, preview.ignored_count), (3, 2, 1))
        self.assertEqual(preview.ignored_reasons, ({"reason": "cowrie.command.input", "count": 1},))
        stored = json.dumps([asdict(item) for item in preview.records], sort_keys=True)
        for secret in (
            "admin-secret", "password-secret", "cat /etc/shadow", "message-secret",
            "root-secret", "guess-secret", "curl secret.example/payload",
        ):
            self.assertNotIn(secret, stored)
        self.assertEqual({item.kind for item in preview.records}, {"connection", "authentication"})

    def test_source_adapters_never_persist_url_credentials(self):
        rows = [
            {
                "eventid": "cowrie.session.connect", "timestamp": "2026-11-23T08:00:00Z",
                "session": "session-1", "src_ip": "198.51.100.4", "dst_ip": "192.0.2.4",
                "src_port": 50000, "dst_port": 22,
            },
            {
                "eventid": "cowrie.session.file_download", "timestamp": "2026-11-23T08:01:00Z",
                "session": "session-1", "src_ip": "198.51.100.4", "dst_ip": "192.0.2.4",
                "url": "https://user:password@malware.example/payload",
            },
        ]
        cowrie = preview_file_payload(
            "\n".join(json.dumps(row) for row in rows).encode(), input_format="cowrie-jsonl",
        )
        self.assertEqual((cowrie.record_count, cowrie.ignored_count), (1, 1))
        self.assertEqual(cowrie.ignored_reasons, ({"reason": "unsafe_file_download", "count": 1},))
        self.assertNotIn("password", json.dumps([asdict(item) for item in cowrie.records]))

        report = {
            "info": {"id": 43, "ended": "2026-11-23T08:00:00Z"},
            "target": {"file": {"sha256": "a" * 64}},
            "network": {"http": [
                {"uri": "https://user:password@malware.example/payload"},
                {"uri": "https://safe.example/payload"},
            ]},
        }
        cape = preview_file_payload(json.dumps(report).encode(), input_format="cape-report-v1")
        self.assertEqual(cape.records[0].indicators, (
            {"type": "url", "value": "https://safe.example/payload"},
        ))

    def test_cape_adapter_keeps_bounded_summary_and_never_raw_artifacts(self):
        report = {
            "info": {"id": 42, "ended": "2026-11-23T08:00:00Z", "score": 8.5},
            "target": {"file": {
                "name": "sample.exe", "sha256": "a" * 64,
                "sha1": "b" * 40, "md5": "c" * 32,
            }},
            "signatures": [{"name": "network_beacon", "description": "Periodic traffic", "severity": 3}],
            "network": {
                "domains": [{"domain": "malware.example", "ip": "198.51.100.8"}],
                "hosts": ["2001:db8::8"],
                "http": [{"uri": "https://malware.example/a"}],
            },
            "behavior": {"summary": {"files": ["one", "two"], "keys": ["one"]}},
            "memory": "RAW-MEMORY-SECRET", "pcap": "RAW-PCAP-SECRET",
        }
        preview = preview_file_payload(json.dumps(report).encode(), input_format="cape-report-v1")
        self.assertEqual((preview.record_count, preview.records[0].kind), (1, "sandbox_analysis"))
        record = asdict(preview.records[0])
        encoded = json.dumps(record, sort_keys=True)
        self.assertNotIn("RAW-MEMORY-SECRET", encoded)
        self.assertNotIn("RAW-PCAP-SECRET", encoded)
        self.assertEqual(record["hashes"]["sha256"], "a" * 64)
        self.assertEqual({item["value"] for item in record["indicators"]}, {
            "198.51.100.8", "2001:db8::8", "https://malware.example/a", "malware.example",
        })
        missing_id = dict(report); missing_id["info"] = {"ended": "2026-11-23T08:00:00Z"}
        with self.assertRaisesRegex(ValidationError, "analiz kimliği"):
            preview_file_payload(json.dumps(missing_id).encode(), input_format="cape-report-v1")

    def test_generic_contract_rejects_unknown_or_sensitive_attribute_names(self):
        value = sensor_record()
        value["attributes"] = [{"name": "password", "value": "must-not-persist"}]
        with self.assertRaisesRegex(ValidationError, "güvenli XTI v1 kataloğu"):
            normalize_record(value)


class TelemetryLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path); self.storage.initialize()
        self.organizations = SQLiteOrganizationRepository(self.path)
        self.organization = self.organizations.add(
            name_key="securehup", display_name="SecureHup",
            reason="P12 controlled organization", recorded_at="2026-11-23T07:50:00+00:00",
        ).organization
        self.clock = Clock()
        self.repository = SQLiteTelemetryRepository(self.path)
        self.service = TelemetryService(self.repository, now=self.clock)
        self.source = self.service.execute(
            PREFIX + "source.add", name="Authorized sinkhole",
            organization_id=self.organization.id, source_kind="sinkhole",
            input_format="xti-sensor-v1", description="Controlled P12 sinkhole stream",
            idempotency_key="source-one",
        )["source"]

    def ingest(self, record, key):
        return self.service.execute(
            PREFIX + "ingest", source_id=self.source["id"],
            expected_revision=self.source["revision"], records=[record],
            idempotency_key=key,
        )

    def first_record(self):
        return self.service.execute(
            PREFIX + "records", organization_id=self.organization.id,
            after=0, limit=50,
        )["items"][0]

    def test_versioned_idempotent_lifecycle_search_engine_case_and_monitoring(self):
        source_replay = self.service.execute(
            PREFIX + "source.add", name="Authorized sinkhole",
            organization_id=self.organization.id, source_kind="sinkhole",
            input_format="xti-sensor-v1", description="Controlled P12 sinkhole stream",
            idempotency_key="source-one",
        )
        self.assertTrue(source_replay["replayed"])
        first = self.ingest(sensor_record(), "ingest-one")
        replay = self.ingest(sensor_record(), "ingest-one")
        self.assertEqual((first["added_count"], replay["id"], replay["replayed"]), (1, first["id"], True))
        record = self.first_record()
        reviewed = self.service.execute(
            PREFIX + "review", identifier=record["id"], expected_revision=1,
            decision="suspicious", reason="Sinkhole IOC requires analyst follow-up.",
            actor="analyst@example.test", idempotency_key="review-one",
        )
        self.assertEqual(reviewed["review"]["record_revision"], 1)
        self.clock.advance()
        changed = sensor_record(summary="Updated sinkhole DNS observation for securehup.example")
        update = self.ingest(changed, "ingest-two")
        self.assertEqual(update["updated_count"], 1)
        record = self.first_record()
        self.assertEqual(record["revision"], 2)
        self.assertTrue(record["needs_review"])
        self.assertEqual(record["review"]["decision"], "suspicious")

        search = GlobalSearchService(SQLiteGlobalSearchRepository(self.path)).search(
            "securehup.example", kinds=("telemetry",), include_inactive=False,
            offset=0, limit=50,
        )
        self.assertEqual((search.total_match_count, search.results[0].record_id), (1, record["id"]))
        detail = SQLiteEngineRecordRepository(self.path).get(reference_for_result(search.results[0]))
        self.assertEqual(detail["record"]["revision"], 2)
        self.assertEqual(detail["sections"]["versions"]["total_count"], 2)
        self.assertEqual(detail["sections"]["reviews"]["total_count"], 1)

        cases = CaseService(
            SQLiteCaseRepository(self.path),
            CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.path)),
            clock=lambda: self.clock.value,
        )
        case = cases.create(
            "Sinkhole telemetri incelemesi",
            summary="Normalize sinkhole kaydı insan incelemesine bağlanıyor.",
            priority="high", reason="P12 vaka kanıtı kabulü.",
        ).case
        linked = cases.add_evidence(
            case.id, "telemetry", record["id"], reason="Güncel normalize telemetri donduruldu.",
        ).evidence
        self.assertEqual(linked.evidence_type, "telemetry")
        self.assertEqual(cases.show(case.id).active_evidence_count, 1)

        monitoring = UnifiedMonitoringService(
            SQLiteUnifiedMonitoringRepository(self.path),
            SQLiteUnifiedMonitoringInputs(self.path), now=self.clock,
        )
        policy = monitoring.execute(
            MONITORING_PREFIX + "policy.add", name="P12 telemetry watch",
            organization_id=self.organization.id,
            subjects=[{"kind": "keyword", "value": "securehup.example"}],
            record_kinds=["telemetry"], match_modes=["exact", "prefix", "contains"],
            notify_on=["added", "updated"], minimum_change_count=1,
            priority="high", interval_seconds=300, max_matches=100,
            actor="analyst", reason="Normalize telemetri değişikliklerini izle.",
            idempotency_key="monitor-policy",
        )
        baseline = monitoring.execute(
            MONITORING_PREFIX + "run", identifier=policy["id"],
            expected_revision=policy["revision"], force=True,
            idempotency_key="monitor-baseline",
        )
        self.assertTrue(baseline["report"]["silent_baseline"])
        self.clock.advance()
        self.ingest(sensor_record("sinkhole:event-2"), "ingest-three")
        changed_run = monitoring.execute(
            MONITORING_PREFIX + "run", identifier=policy["id"],
            expected_revision=policy["revision"], force=True,
            idempotency_key="monitor-change",
        )
        self.assertIsNotNone(changed_run["alert_id"])
        inbox = InboxService(SQLiteInboxRepository(self.path)).list()
        self.assertEqual(inbox.total_count, 1)
        self.assertEqual(inbox.items[0].notification.monitoring_alert_id, changed_run["alert_id"])

    def test_interrupted_import_recovery_is_explicit_and_preserves_existing_records(self):
        preview = preview_file_payload(
            (json.dumps({"format": "xti-sensor-record", "version": 1,
                         "record": sensor_record()}) + "\n").encode(),
            input_format="xti-sensor-v1",
        )
        run, replayed = self.repository.reserve(
            self.source["id"], 1, preview, "reserved-only", self.clock(),
        )
        self.assertFalse(replayed)
        self.assertEqual(run["status"], "running")
        recovered = self.service.execute(
            PREFIX + "recover", source_id=self.source["id"],
            reason="Controlled interrupted import recovery.",
            idempotency_key="recover-one",
        )
        self.assertEqual((recovered["recovered_count"], recovered["run_ids"]), (1, [run["id"]]))
        stored = self.service.execute(PREFIX + "run.get", identifier=run["id"])
        self.assertEqual((stored["status"], stored["error_code"]), ("interrupted", "recovered"))
        with self.assertRaisesRegex(TelemetryError, "tamamlanabilir"):
            self.repository.finish(run["id"], preview.records, self.clock())

    def test_record_corruption_fails_closed(self):
        self.ingest(sensor_record(), "ingest-one")
        record = self.first_record()
        with self.storage._connection() as connection, connection:
            connection.execute(
                "UPDATE telemetry_records SET body_json='{}' WHERE id=?", (record["id"],),
            )
        with self.assertRaises(StorageError):
            self.service.execute(PREFIX + "record.get", identifier=record["id"])


if __name__ == "__main__":
    unittest.main()
