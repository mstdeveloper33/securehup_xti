"""Organization reports use explicit membership and immutable local evidence."""

from contextlib import closing, contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_organization_report import SQLiteOrganizationReportRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.sqlite_organization_scope import read_organization_scope
from xti.adapters.schema import SCHEMA_VERSION
from xti.application.organization_report import OrganizationReportService
from xti.domain.assets import ValidationError
from xti.domain.cases import canonical_snapshot
from xti.domain.organization_report import report_freshness
from xti.domain.public_notices import PublicNotice, PublicNoticeFeed
from xti.interfaces.organization_report import organization_report_lines
from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixtures
from tests.test_discovery import batch, document
from tests.test_surface import result as web_result


class OrganizationReportTests(unittest.TestCase):
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files
    add_social = fixtures.CollectionWatchCLITests.add_social
    add_tc = fixtures.CollectionWatchCLITests.add_tc
    add_rl = fixtures.CollectionWatchCLITests.add_rl

    def setUp(self):
        fixtures.CollectionWatchCLITests.setUp(self)
        self.service = OrganizationReportService(SQLiteOrganizationReportRepository(self.database))
        self.organization = self.result("organizations", "add", "Example group")["organization"]

    def link(self, kind="domain", value="example.com", organization=None):
        return self.result("organizations", "link", (organization or self.organization)["id"],
                           "--kind", kind, "--value", value)["link"]

    def report(self, **options):
        return self.service.show(self.organization["id"], **options)

    @staticmethod
    def section(target, kind):
        return next(section for section in target.sections if section.kind == kind)

    def collect(self, *options):
        self.crt.responses["%example%"] = batch(
            document("example-support.net", 1), document("example-help.net", 2),
        )
        self.crt.responses["%.example.com"] = batch(document("portal.example.com", 3))
        return self.result("collect", "example.com", *options)

    def test_empty_group_and_missing_checks_are_not_source_failures(self):
        report = self.report()
        self.assertEqual((report.total_target_count, report.targets), (0, ()))
        self.link()
        report = self.report()
        self.assertEqual(len(report.targets), 1)
        target = report.targets[0]
        self.assertTrue(all(section.total_count == 0 for section in target.sections))
        self.assertTrue(all(item.latest_attempt is None and item.freshness == "never" for item in target.coverage))

    def test_domain_records_have_real_counts_paging_and_review_state(self):
        self.link()
        self.collect()
        finding = self.result("findings", "list")["findings"][0]
        self.result("findings", "review", finding["id"], "--decision", "dismissed", "--reason", "Meşru adres.")
        first = self.report(item_limit=1)
        second = self.report(item_limit=1, item_offset=1)
        page = self.section(first.targets[0], "findings")
        self.assertEqual(page.total_count, 2)
        self.assertTrue(page.has_more)
        second_page = self.section(second.targets[0], "findings")
        self.assertEqual(second_page.total_count, 2)
        self.assertFalse(second_page.has_more)
        records = (*page.items, *second_page.items)
        self.assertEqual({item.value for item in records}, {"example-help.net", "example-support.net"})
        self.assertEqual(next(item.status for item in records if item.id == finding["id"]), "dismissed")
        self.assertEqual(self.section(first.targets[0], "surface_candidates").total_count, 1)
        self.assertTrue(all(item.navigation[0].arguments == ("findings", "show", item.id) for item in records))

    def test_all_selected_watch_sources_preserve_identity_and_readonly_snapshot(self):
        social, tc, rl = self.add_social(), self.add_tc(), self.add_rl()
        for kind, value in (("domain", "example.com"), ("username-watch", social.id),
                            ("ransomware-watch", tc.id), ("ransomlook-watch", rl.id)):
            self.link(kind, value)
        self.maigret.responses.append({"GitHub": fixtures.github()})
        self.collect("--username-watch", social.id, "--ransomware-watch", tc.id, "--ransomlook-watch", rl.id)
        before = self.files()
        with patch.object(SQLiteAssetRepository, "initialize", side_effect=AssertionError("No migration")):
            report = self.report()
        self.assertEqual(self.files(), before)
        self.assertEqual(report.total_target_count, 4)
        self.assertTrue(report.stored_data_only)
        targets = {item.membership.link.target.kind: item for item in report.targets}
        for kind, source in (("ransomware-watch", "threatcluster"), ("ransomlook-watch", "ransomlook")):
            claims = self.section(targets[kind], "claims")
            self.assertEqual(claims.total_count, 1)
            self.assertEqual(claims.items[0].source, source)
            self.assertEqual(self.section(targets[kind], "notifications").total_count, 0)
            self.assertTrue(targets[kind].coverage[0].latest_success.is_baseline)
        self.assertEqual(self.section(targets["username-watch"], "profiles").total_count, 2)

    def test_revoked_links_and_targets_never_contribute_evidence(self):
        domain_link = self.link()
        watch = self.add_social()
        self.link("username-watch", watch.id)
        self.result("organizations", "unlink", self.organization["id"], domain_link["id"], "--reason", "Kapsam dışı.")
        self.social.revoke(watch.id, reason="İzleme kapatıldı.")
        report = self.report()
        self.assertEqual(report.total_target_count, 0)
        self.assertEqual(len(report.scope.links), 2)
        self.assertEqual(report.scope.excluded_link_count, 2)
        self.assertTrue(any(view.link.active and not view.target.active for view in report.scope.links))

    def test_revoked_organization_preserves_links_but_has_no_current_targets(self):
        self.link()
        self.collect()
        self.result("organizations", "revoke", self.organization["id"], "--reason", "Grup kapatıldı.")
        report = self.report()
        self.assertFalse(report.scope.organization.active)
        self.assertTrue(report.scope.links[0].link.active)
        self.assertEqual(report.targets, ())
        self.assertEqual(report.scope.excluded_link_count, 1)

    def test_group_names_do_not_select_other_group_targets(self):
        self.link()
        other = self.result("organizations", "add", "Example Holding")["organization"]
        watch = self.add_rl()
        self.link("ransomlook-watch", watch.id, other)
        self.collect("--ransomlook-watch", watch.id)
        payload = json.dumps(asdict(self.report()))
        self.assertNotIn(watch.id, payload)
        self.assertNotIn(other["id"], payload)
        self.assertEqual(self.report().total_target_count, 1)

    def test_social_error_preserves_review_and_changed_definition_has_no_current_profiles(self):
        watch = self.add_social()
        self.link("username-watch", watch.id)
        self.maigret.responses.extend(({"GitHub": fixtures.github()}, SourceError("Geçici kaynak hatası.")))
        first = self.social.run(watch.id)
        self.result("brand", "watch-review", watch.id, "GitHub", "--decision", "possible_impersonation", "--reason", "İnsan incelemesinin gerekçesi.")
        self.social.run(watch.id)
        report = self.report()
        target = report.targets[0]
        self.assertEqual(target.coverage[0].latest_attempt.status, "failed")
        self.assertEqual(target.coverage[0].latest_success.id, first.run.id)
        profiles = self.section(target, "profiles")
        self.assertTrue(any("İnsan kararı: possible_impersonation" in item.details for item in profiles.items))
        notices = self.section(target, "notifications")
        self.assertEqual(notices.total_count, 1)
        self.assertEqual(notices.items[0].definition_sha256, first.run.definition_sha256)
        self.social.add(watch.display_name, "changedbrand", platforms=watch.platforms)
        changed = self.report().targets[0]
        self.assertIsNone(changed.coverage[0].latest_success)
        self.assertFalse(changed.coverage[0].latest_attempt.definition_matches_current)
        self.assertEqual(self.section(changed, "profiles").total_count, 0)
        old_notice = self.section(changed, "notifications").items[0]
        self.assertEqual(old_notice.definition_sha256, first.run.definition_sha256)
        self.assertNotEqual(old_notice.definition_sha256, dict(changed.current_definition)["definition_sha256"])

    def test_ransomware_change_notice_keeps_source_run_and_feed_failure_is_separate(self):
        tc, rl = self.add_tc(), self.add_rl()
        self.link("ransomware-watch", tc.id)
        self.link("ransomlook-watch", rl.id)
        arguments = ("collect", "example.com", "--task", "discover-crtsh", "--ransomware-watch", tc.id, "--ransomlook-watch", rl.id)
        self.result(*arguments)
        self.ransomlook.value = fixtures.ransomlook_feed([fixtures.post(), fixtures.post(group="other")])
        self.threatcluster.value = fixtures.threatcluster_feed([fixtures.claim(), fixtures.claim(group="other")])
        self.result(*arguments)
        previous = {target.membership.link.target.kind: target for target in self.report().targets}
        self.ransomlook.value = SourceError("RansomLook erişim hatası.")
        self.threatcluster.value = SourceError("ThreatCluster erişim hatası.")
        self.result(*arguments, expected_code=3)
        report = self.report()
        for target in report.targets:
            kind = target.membership.link.target.kind
            watch_coverage, feed_coverage = target.coverage
            self.assertEqual(feed_coverage.latest_attempt.status, "failed")
            self.assertEqual(feed_coverage.latest_success.status, "complete")
            self.assertEqual(watch_coverage.latest_success.id, previous[kind].coverage[0].latest_success.id)
            notice = self.section(target, "notifications").items[0]
            self.assertEqual(notice.run_id, watch_coverage.latest_success.id)
            self.assertEqual(notice.source_run_id, watch_coverage.latest_success.source_run_id)
            self.assertEqual(self.section(target, "claims").total_count, 2)

    def case_evidence_fixture(self):
        self.link()
        self.collect()
        findings = self.result("findings", "list")["findings"]
        case = self.result("cases", "create", "Private case title", "--summary", "Private case content",
                           "--reason", "Analistin açık bağlantısı.")["case"]
        result = self.result("cases", "evidence-add", case["id"], "--type", "finding",
                             "--evidence-id", findings[0]["id"], "--reason", "Tam kimlik bağlantısı.")
        return case, findings, result["evidence"]

    def test_case_pointer_corruption_cannot_rebind_existing_frozen_evidence(self):
        case, findings, link = self.case_evidence_fixture()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE case_evidence SET evidence_id=? WHERE id=?", (findings[1]["id"], link["id"]))
        before = self.files()
        with self.assertRaisesRegex(StorageError, "kanıt bağı"):
            self.report()
        self.assertEqual(self.files(), before)

    def test_case_id_corruption_is_detected_without_filtering_history_by_forged_case(self):
        case, findings, link = self.case_evidence_fixture()
        other = self.result("cases", "create", "Other private case", "--summary", "Unrelated case content",
                            "--reason", "Başka bir vaka.")["case"]
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE case_evidence SET case_id=? WHERE id=?", (other["id"], link["id"]))
        with self.assertRaisesRegex(StorageError, "kanıt bağı"):
            self.report()

    def test_evidence_flag_corruption_cannot_silently_hide_a_current_case_link(self):
        case, findings, link = self.case_evidence_fixture()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE case_evidence SET active=0,removed_reason=?,removed_at=? WHERE id=?",
                               ("Uydurulmuş kaldırma.", link["updated_at"], link["id"]))
        with self.assertRaisesRegex(StorageError, "kanıt bağı"):
            self.report()

    def test_rehashed_activity_payload_still_has_to_match_link_identity(self):
        case, findings, link = self.case_evidence_fixture()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            identifier, raw = connection.execute(
                "SELECT id,snapshot_json FROM case_activities WHERE reference_id=?", (link["id"],),
            ).fetchone()
            payload = json.loads(raw)
            payload["evidence_id"] = findings[1]["id"]
            encoded, digest = canonical_snapshot(payload)
            connection.execute("UPDATE case_activities SET snapshot_json=?,snapshot_sha256=? WHERE id=?",
                               (encoded, digest, identifier))
        with self.assertRaisesRegex(StorageError, "kanıt bağı"):
            self.report()

    def test_valid_evidence_refresh_remove_reactivate_replays_and_missing_transition_fails(self):
        case, findings, link = self.case_evidence_fixture()
        self.result("findings", "review", findings[0]["id"], "--decision", "dismissed", "--reason", "İnsan değerlendirmesi.")
        refreshed = self.result("cases", "evidence-add", case["id"], "--type", "finding",
                                "--evidence-id", findings[0]["id"], "--reason", "Yeni incelemeyi kaydet.")
        self.assertEqual(refreshed["action"], "refreshed")
        self.assertEqual(self.section(self.report().targets[0], "case_links").total_count, 1)
        self.result("cases", "evidence-remove", case["id"], link["id"], "--reason", "Bağlantıyı geri çek.")
        self.assertEqual(self.section(self.report().targets[0], "case_links").total_count, 0)
        reactivated = self.result("cases", "evidence-add", case["id"], "--type", "finding",
                                  "--evidence-id", findings[0]["id"], "--reason", "Bağlantıyı yeniden aç.")
        self.assertEqual(reactivated["action"], "reactivated")
        report = self.report()
        self.assertEqual(self.section(report.targets[0], "case_links").total_count, 1)
        serialized = json.dumps(asdict(report))
        self.assertNotIn(case["title"], serialized)
        self.assertNotIn(case["summary"], serialized)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("DELETE FROM case_activities WHERE reference_id=? AND activity_type='evidence_removed'", (link["id"],))
        with self.assertRaisesRegex(StorageError, "kanıt bağı"):
            self.report()

    def test_case_links_use_exact_evidence_and_never_copy_case_content(self):
        self.link()
        self.collect()
        finding = self.result("findings", "list")["findings"][0]
        case = self.result("cases", "create", "PRIVATE OTHER ORGANIZATION", "--summary", "UNRELATED SECRET CONTENT", "--reason", "Analist incelemesi.")["case"]
        other = self.result("cases", "create", "Unlinked case", "--summary", "Unlinked", "--reason", "Analist incelemesi.")["case"]
        self.result("cases", "evidence-add", case["id"], "--type", "finding", "--evidence-id", finding["id"], "--reason", "Tam kanıt kimliği bağlantısı.")
        report = self.report()
        links = self.section(report.targets[0], "case_links")
        self.assertEqual(links.total_count, 1)
        self.assertEqual(links.items[0].value, case["id"])
        payload = json.dumps(asdict(report))
        for forbidden in (case["title"], case["summary"], other["id"]):
            self.assertNotIn(forbidden, payload)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE cases SET priority='critical' WHERE id=?", (case["id"],))
            connection.commit()
        with self.assertRaises(StorageError):
            self.report()

    def test_surface_failure_does_not_replace_last_success_or_hide_evidence(self):
        self.link()
        asset = SQLiteAssetRepository(self.database).list()[0]
        surface = SQLiteSurfaceRepository(self.database)
        now = datetime.now(timezone.utc)
        surface.activate(asset.id, asset.value, "Yetkili kontrol.", now.isoformat())
        success = surface.append_check(asset.id, web_result())
        failed = surface.append_check(asset.id, replace(web_result(), dns_status="failed", addresses=(),
                                                       connected_address=None, tls_status="not_checked", http_status="not_checked", http_status_code=None,
                                                       errors=("DNS sorgusu tamamlanmadı.",)))
        report = self.report()
        target = report.targets[0]
        web = next(item for item in target.coverage if item.family == "surface" and item.source == "web")
        self.assertEqual(web.latest_attempt.id, failed.id)
        self.assertEqual(web.latest_attempt.status, "failed")
        self.assertEqual(web.latest_success.id, success.id)
        self.assertEqual(target.surface.latest_check.id, failed.id)
        rendered = "\n".join(organization_report_lines(report))
        self.assertIn(success.id, rendered)
        self.assertIn(failed.id, rendered)

    def test_target_paging_and_terminal_escaping(self):
        self.link()
        watch = self.add_rl()
        self.link("ransomlook-watch", watch.id)
        report = self.report(target_limit=1)
        self.assertEqual((report.total_target_count, len(report.targets), report.has_more_targets), (2, 1, True))
        page = self.report(target_limit=1, target_offset=1)
        self.assertEqual((page.total_target_count, len(page.targets), page.has_more_targets), (2, 1, False))
        target = report.targets[0]
        modified = replace(report, targets=(replace(target, notes=("untrusted\x1b[31m\ntext",)),))
        rendered = "\n".join(organization_report_lines(modified))
        self.assertNotIn("\x1b", rendered)
        self.assertIn("\\u001b[31m\\u000atext", rendered)

    def test_single_read_snapshot_retains_evidence_during_concurrent_write(self):
        self.link()
        self.collect()
        finding = self.result("findings", "list")["findings"][0]
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        reads, statements = [], []
        repository = self.service.repository
        original_connection = repository._storage._connection

        @contextmanager
        def tracked_connection(*, readonly=False):
            reads.append(readonly)
            with original_connection(readonly=readonly) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        def concurrent_update(connection, identifier):
            scope = read_organization_scope(connection, identifier)
            with closing(sqlite3.connect(self.database)) as writer:
                writer.execute("UPDATE findings SET status='dismissed' WHERE id=?", (finding["id"],))
                writer.commit()
            return scope

        with patch.object(repository._storage, "_connection", tracked_connection), patch(
            "xti.adapters.sqlite_organization_report.read_organization_scope", side_effect=concurrent_update,
        ):
            report = self.report()
        record = next(item for item in self.section(report.targets[0], "findings").items if item.id == finding["id"])
        self.assertEqual(record.status, finding["status"])
        self.assertEqual(reads, [True])
        self.assertEqual(sum(query == "BEGIN" for query in statements), 1)
        self.assertFalse(any(query.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER"} for query in statements))

    def test_public_catalog_exact_scope_flags_license_and_failure_preserve_baseline(self):
        self.link()
        repository = SQLitePublicNoticeRepository(self.database)
        timestamp = datetime.now(timezone.utc).isoformat()
        def record(identifier, domain):
            return PublicNotice(identifier, identifier, domain, "2025-01-02",
                                "2025-02-03T00:00:00+00:00", "2025-02-03T00:00:00+00:00", 42,
                                ("Email addresses",), False, True, False, False, False, False, True,
                                "Public contributor", f"https://haveibeenpwned.com/api/v3/breach/{identifier}")
        records = (record("ExactOne", "example.com"), record("ExactTwo", "example.com"),
                   record("ExampleHolding", "different.example"), record("Subdomain", "sub.example.com"), record("MissingDomain", None))
        saved = repository.apply(PublicNoticeFeed(timestamp, "a" * 64, records), started_at=timestamp, finished_at=timestamp)
        failure = repository.record_failure(started_at=timestamp, finished_at=timestamp, error="Kamu kaynağına erişilemedi.")
        before = self.files()
        report = self.report(item_limit=1)
        target = report.targets[0]
        coverage = next(item for item in target.coverage if item.family == "public-notices")
        self.assertEqual(coverage.latest_attempt.id, failure.id)
        self.assertEqual(coverage.latest_success.id, saved.run.id)
        page = self.section(target, "public_notices")
        self.assertEqual((page.total_count, len(page.items), page.has_more), (2, 1, True))
        second = self.section(self.report(item_offset=1, item_limit=1).targets[0], "public_notices")
        self.assertEqual({page.items[0].id, second.items[0].id}, {"ExactOne", "ExactTwo"})
        self.assertTrue(page.items[0].public_notice.is_fabricated)
        self.assertFalse(page.items[0].public_notice.is_verified)
        self.assertTrue(page.items[0].public_notice.is_stealer_log)
        text = "\n".join(organization_report_lines(report))
        self.assertIn("https://haveibeenpwned.com", text)
        self.assertIn("CC BY 4.0", text)
        for identifier in ("ExampleHolding", "Subdomain", "MissingDomain"):
            self.assertNotIn(identifier, json.dumps(asdict(report)))
        self.assertEqual(self.files(), before)

    def test_public_catalog_only_failure_is_distinct_from_never_fetched_and_corruption(self):
        self.link()
        coverage = next(item for item in self.report().targets[0].coverage if item.family == "public-notices")
        self.assertIsNone(coverage.latest_attempt)
        repository = SQLitePublicNoticeRepository(self.database)
        timestamp = datetime.now(timezone.utc).isoformat()
        repository.record_failure(started_at=timestamp, finished_at=timestamp, error="İlk kaynak denemesi başarısız.")
        target = self.report().targets[0]
        coverage = next(item for item in target.coverage if item.family == "public-notices")
        self.assertEqual(coverage.latest_attempt.status, "failed")
        self.assertIsNone(coverage.latest_success)
        self.assertEqual(self.section(target, "public_notices").total_count, 0)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE public_notice_runs SET error='ALTERED'")
            connection.commit()
        with self.assertRaises(StorageError):
            self.report()

    def test_old_schema_is_not_migrated_by_readonly_report(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION - 1}")
        before = self.files()
        with self.assertRaises(StorageError):
            self.report()
        self.assertEqual(self.files(), before)

    def test_limits_and_unknown_ids_do_not_write(self):
        before = self.files()
        for options in ({"item_limit": 0}, {"target_limit": True}, {"item_offset": -1}, {"stale_after_hours": 8761}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                self.report(**options)
        with self.assertRaises((ValidationError, StorageError)):
            self.service.show(str(uuid4()))
        self.assertEqual(self.files(), before)

    def test_missing_database_and_corrupted_link_are_errors_not_empty_reports(self):
        missing = self.data / "absent" / "never.db"
        service = OrganizationReportService(SQLiteOrganizationReportRepository(missing))
        with self.assertRaises(StorageError):
            service.show(self.organization["id"])
        self.assertFalse(missing.parent.exists())
        self.link()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE organization_links SET reason='silently altered'")
            connection.commit()
        before = self.files()
        with self.assertRaises(StorageError):
            self.report()
        self.assertEqual(self.files(), before)


class OrganizationReportTimeTests(unittest.TestCase):
    def test_age_boundary_future_and_invalid_timestamps(self):
        now = datetime(2026, 11, 14, tzinfo=timezone.utc)
        self.assertEqual(report_freshness(None, now.isoformat(), 24), "never")
        self.assertEqual(report_freshness(now.isoformat(), now.isoformat(), 24), "current")
        self.assertEqual(report_freshness((now - timedelta(hours=24)).isoformat(), now.isoformat(), 24), "stale")
        self.assertEqual(report_freshness((now + timedelta(seconds=1)).isoformat(), now.isoformat(), 24), "clock_error")
        with self.assertRaises(ValidationError):
            report_freshness("2026-11-14", now.isoformat(), 24)
