"""Exact content affiliation, historical evidence and complete offline reports."""

from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mention_groups import SQLiteMentionGroupRepository
from xti.adapters.sqlite_mention_notifications import SQLiteMentionNotificationBridge
from xti.adapters.sqlite_mention_targets import SQLiteMentionTargetRepository
from xti.adapters.sqlite_mentions import SQLiteMentionRepository
from xti.adapters.sqlite_organization_report import SQLiteOrganizationReportRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.mention_groups import MentionGroupService
from xti.application.organization_report import OrganizationReportService
from xti.domain.assets import ValidationError
from xti.domain.mention_groups import MentionGroupDefinition
from xti.domain.mentions import MentionHit, MentionRequest, MentionResponse, MentionTarget, build_query, company_target
from xti.domain.organization_export import export_record_count, validate_complete_export
from xti.domain.organizations import OrganizationTargetReference
from xti.interfaces.html_organization_report import HtmlOrganizationReportRenderer
from xti.interfaces.organization_report import organization_report_lines
from tests.test_organization_export import ParsedHtml


class OrganizationContentReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
        self.organizations = SQLiteOrganizationRepository(self.path)
        self.organization = self.organizations.add(name_key="example", display_name="Example",
            reason="Explicit test organization", recorded_at=self.tick()).organization
        self.suppliers = SQLiteSupplierRepository(self.path)
        self.supplier = self.suppliers.add(name_key="supplier", display_name="Supplier", primary_domain="supplier.test",
            relationship_type="software", criticality="high", reason="Explicit supplier", recorded_at=self.tick()).supplier
        self.sources = SQLiteMentionRepository(self.path)
        self.groups = SQLiteMentionGroupRepository(self.path)
        self.targets = SQLiteMentionTargetRepository(self.path)
        self.repository = SQLiteOrganizationReportRepository(self.path)
        self.service = OrganizationReportService(self.repository, clock=lambda: self.now)
        self.source = Mock()
        self.source.fetch.side_effect = lambda request: MentionResponse(build_query(request.target), None,
            (self.hit(request.target.name, path=request.target.id),), 1)
        self.group_service = MentionGroupService(self.groups, self.sources, self.targets,
            LocalExecutionLock(self.path), notifications=SQLiteMentionNotificationBridge(self.path),
            source_factory=lambda: self.source, clock=lambda: self.now)
        self.addCleanup(patch.stopall)
        patch("socket.socket.connect", side_effect=AssertionError("Report must not collect")).start()
        patch("socket.getaddrinfo", side_effect=AssertionError("Report must not resolve targets")).start()

    def tick(self):
        self.now += timedelta(seconds=1)
        return self.now.isoformat()

    @staticmethod
    def hit(title="Example news", *, path="article", summary="Public content"):
        return MentionHit("https://publisher.test/" + path, title, summary, "2026-11-15", .8)

    def request(self, *, supplier=False, **changes):
        target = self.targets.resolve("supplier" if supplier else "organization",
                                      self.supplier.id if supplier else self.organization.id)
        return replace(MentionRequest(target, "news", 10), **changes)

    def apply(self, *hits, request=None):
        request = request or self.request()
        at = self.tick()
        return self.sources.apply(request, MentionResponse(build_query(request.target), None, tuple(hits), 1),
                                  started_at=at, finished_at=at)

    def group(self, *, name="Explicit group", supplier=True, organization=None, **changes):
        self.tick()
        definition = MentionGroupDefinition((organization or self.organization).id,
            (self.supplier.id,) if supplier else (), interval_hours=1)
        return self.group_service.save(name, replace(definition, **changes))

    def report(self, **options):
        return self.service.show(self.organization.id, **options)

    def complete(self):
        return self.repository.read_complete(self.organization.id, observed_at=self.now.isoformat(), stale_after_hours=24)

    @staticmethod
    def page(report, kind="content"):
        return next(page for page in report.content.sections if page.kind == kind)

    def test_empty_current_scope_is_not_a_successful_empty_query(self):
        report = self.report()
        self.assertEqual(report.total_target_count, 0)
        scope, = report.content.scopes
        self.assertEqual(scope.target.id, self.organization.id)
        self.assertIsNone(scope.request)
        self.assertIsNone(scope.latest_success_result_count)
        self.assertEqual(scope.coverage.freshness, "never")
        self.assertEqual(self.page(report).total_count, 0)

    def test_exact_organization_id_excludes_company_same_name_and_unrelated_supplier(self):
        expected = self.apply(self.hit())
        self.apply(self.hit(path="company"), request=replace(self.request(), target=company_target("Example")))
        self.apply(self.hit(path="same-name-other-id"), request=replace(self.request(),
            target=MentionTarget("organization", str(uuid4()), "Example", ())))
        self.apply(self.hit("Example supplier article", path="supplier"), request=self.request(supplier=True))
        report = self.report()
        self.assertEqual(self.page(report).total_count, 1)
        self.assertEqual(self.page(report).items[0].source_run_id, expected.id)
        self.assertEqual(self.page(report, "historical_content").total_count, 0)

    def test_active_explicit_groups_deduplicate_supplier_records_and_include_no_search_scope(self):
        one = self.group()
        two = self.group(name="Second group")
        self.apply(self.hit("Supplier announcement"), request=self.request(supplier=True))
        report = self.report()
        self.assertEqual(self.page(report).total_count, 1)
        supplier = next(scope for scope in report.content.scopes if scope.target.kind == "supplier")
        self.assertEqual(set(supplier.current_group_ids), {one.id, two.id})
        organization = next(scope for scope in report.content.scopes if scope.target.kind == "organization")
        self.assertEqual(organization.coverage.freshness, "never")

    def test_empty_success_failure_and_stale_source_preserve_prior_evidence(self):
        initial = self.apply(self.hit())
        empty = self.apply()
        at = self.tick()
        failed = self.sources.record_failure(self.request(), error="Source unavailable",
            started_at=at, finished_at=at)
        self.now += timedelta(days=2)
        report = self.report()
        scope, = report.content.scopes
        self.assertEqual(scope.coverage.latest_attempt.id, failed.id)
        self.assertEqual(scope.coverage.latest_attempt.error, "Source unavailable")
        self.assertEqual(scope.coverage.latest_success.id, empty.id)
        self.assertEqual(scope.coverage.latest_success.status, "empty")
        self.assertEqual(scope.latest_success_result_count, 0)
        self.assertEqual(scope.coverage.freshness, "stale")
        record, = self.page(report).items
        self.assertEqual((record.status, record.source_run_id), ("retained_candidate", initial.id))
        self.assertIn("başarılı, boş sonuç", "\n".join(organization_report_lines(report)))

    def test_name_change_splits_old_scope_and_uncollected_current_scope(self):
        initial = self.apply(self.hit())
        self.organizations.rename(self.organization.id, name_key="new example", display_name="New Example",
            reason="Renamed company", recorded_at=self.tick())
        report = self.report()
        self.assertEqual({item.scope_status for item in report.content.scopes}, {"current", "old_definition"})
        current = next(item for item in report.content.scopes if item.scope_status == "current")
        self.assertEqual(current.target.name, "New Example")
        self.assertEqual(current.coverage.freshness, "never")
        self.assertEqual(self.page(report).total_count, 0)
        self.assertEqual(self.page(report, "historical_content").items[0].source_run_id, initial.id)
        self.apply(self.hit("New Example news"))
        self.assertEqual(self.page(self.report()).total_count, 1)
        self.assertEqual(self.page(self.report(), "historical_content").total_count, 1)

    def test_domain_membership_change_does_not_relabel_old_query_current(self):
        self.apply(self.hit())
        self.storage.add("example.test")
        self.organizations.link(self.organization.id, OrganizationTargetReference("domain", "example.test"),
            reason="Explicit domain", recorded_at=self.tick())
        report = self.report()
        old = next(item for item in report.content.scopes if item.request is not None)
        self.assertEqual(old.scope_status, "old_definition")
        current = next(item for item in report.content.scopes if item.request is None)
        self.assertEqual(current.target.domains, ("example.test",))

    def test_removed_supplier_keeps_only_frozen_own_group_source_not_later_shared_update(self):
        group = self.group()
        run = self.group_service.run(group.id)["run"]
        source_id = next(a.result_run_id for a in run.attempts if a.request.target.kind == "supplier")
        self.tick()
        self.group_service.save(group.name, replace(group.definition, supplier_ids=()))
        self.apply(self.hit("Unrelated later supplier update", path=self.supplier.id), request=self.request(supplier=True))
        report = self.report()
        historic, = self.page(report, "historical_content").items
        self.assertEqual(historic.source_run_id, source_id)
        self.assertFalse(any("Unrelated later" in detail for detail in historic.details))
        old = next(item for item in report.content.scopes if item.target.kind == "supplier")
        self.assertEqual(old.scope_status, "inactive_relationship")
        self.assertEqual(old.current_group_ids, ())
        self.assertEqual(self.sources.run_show(source_id).response.hits[0].title, "Supplier")

    def test_disabled_group_and_revoked_supplier_are_not_current_content(self):
        group = self.group()
        self.group_service.run(group.id)
        self.groups.disable(group.id, reason="Monitoring stopped", recorded_at=self.tick())
        report = self.report()
        self.assertEqual(self.page(report).total_count, 1)
        self.assertEqual(self.page(report, "historical_content").total_count, 1)
        self.tick()
        self.group_service.save(group.name, group.definition)
        self.suppliers.revoke(self.supplier.id, reason="Relationship ended", recorded_at=self.tick())
        report = self.report()
        old = next(item for item in report.content.scopes if item.target.kind == "supplier")
        self.assertEqual(old.scope_status, "inactive_target")
        self.assertEqual(self.page(report, "historical_content").total_count, 1)

    def test_group_organization_change_does_not_move_historical_supplier_evidence(self):
        group = self.group()
        self.group_service.run(group.id)
        other = self.organizations.add(name_key="another", display_name="Another", reason="Another organization",
            recorded_at=self.tick()).organization
        self.tick()
        self.group_service.save(group.name, replace(group.definition, organization_id=other.id))
        report = self.report()
        self.assertEqual(self.page(report).total_count, 1)
        self.assertEqual(self.page(report, "historical_content").total_count, 1)
        self.assertEqual(next(scope for scope in report.content.scopes if scope.target.kind == "supplier").scope_status,
                         "inactive_relationship")

    def test_query_configuration_change_is_historical_with_uncollected_current_target(self):
        group = self.group()
        self.group_service.run(group.id)
        self.tick()
        self.group_service.save(group.name, replace(group.definition, max_results=5))
        report = self.report()
        self.assertEqual(self.page(report).total_count, 0)
        self.assertEqual(self.page(report, "historical_content").total_count, 2)
        self.assertEqual({scope.scope_status for scope in report.content.scopes}, {"current", "old_request"})
        self.assertTrue(all(scope.coverage.freshness == "never" for scope in report.content.scopes if scope.scope_status == "current"))
        self.assertEqual({scope.request.max_results for scope in report.content.scopes if scope.scope_status == "current"}, {5})

    def test_large_current_domain_scope_remains_readable_without_constructing_invalid_query(self):
        self.group(supplier=False)
        self.apply(self.hit())
        for index in range(11):
            domain = f"example{index}.test"
            self.storage.add(domain)
            self.organizations.link(self.organization.id, OrganizationTargetReference("domain", domain),
                reason="Explicit domain", recorded_at=self.tick())
        report = self.report(target_limit=1)
        self.assertEqual(report.total_target_count, 11)
        current, = report.content.scopes
        self.assertEqual(len(current.target.domains), 11)
        self.assertEqual(current.coverage.freshness, "never")
        self.assertIsNone(current.request)
        self.assertTrue(any("sınırlarını aşıyor" in note for note in current.notes))
        self.assertEqual(self.page(report, "historical_content").total_count, 1)

    def test_direct_organization_query_stays_distinct_from_group_query_settings(self):
        self.group(supplier=False, max_results=5)
        direct = self.apply(self.hit(), request=self.request(max_results=10))
        report = self.report()
        self.assertEqual(self.page(report).total_count, 1)
        self.assertEqual(self.page(report).items[0].source_run_id, direct.id)
        self.assertEqual({scope.request.max_results for scope in report.content.scopes}, {5, 10})
        self.assertTrue(all(scope.scope_status == "current" for scope in report.content.scopes))

    def test_pending_and_unknown_attempts_are_not_success_or_empty(self):
        group = self.group()
        requests = (self.request(), self.request(supplier=True))
        run = self.groups.begin(group.id, requests, started_at=self.tick())
        self.groups.reserve_attempt(run.id, 0, started_at=self.tick())
        self.groups.recover(run.id, recorded_at=self.tick())
        report = self.report()
        organization = next(scope for scope in report.content.scopes if scope.target.kind == "organization")
        supplier = next(scope for scope in report.content.scopes if scope.target.kind == "supplier")
        self.assertEqual(organization.coverage.latest_attempt.status, "unknown")
        self.assertEqual(organization.coverage.freshness, "never")
        self.assertIsNone(organization.latest_success_result_count)
        self.assertIsNone(supplier.coverage.latest_attempt)
        self.assertTrue(any("kaynak çağrısı yapılmadı" in note for note in supplier.coverage.notes))

    def test_revoked_organization_keeps_source_readable_in_historical_section(self):
        self.apply(self.hit())
        self.organizations.revoke(self.organization.id, reason="Organization retired", recorded_at=self.tick())
        report = self.report()
        self.assertEqual(self.page(report).total_count, 0)
        self.assertEqual(self.page(report, "historical_content").total_count, 1)
        self.assertEqual(report.content.scopes[0].scope_status, "inactive_organization")

    def test_real_counts_and_complete_export_include_all_current_and_historical_pages(self):
        self.apply(self.hit(path="old-one"), self.hit(path="old-two"))
        self.organizations.rename(self.organization.id, name_key="renamed", display_name="Renamed",
            reason="Name change", recorded_at=self.tick())
        self.apply(self.hit("Renamed one", path="new-one"), self.hit("Renamed two", path="new-two"))
        first = self.report(target_limit=1, item_limit=1)
        second = self.report(target_offset=1, target_limit=1, item_offset=1, item_limit=1)
        self.assertEqual(first.content.total_scope_count, 2)
        self.assertTrue(first.content.has_more_scopes)
        self.assertFalse(second.content.has_more_scopes)
        for kind in ("content", "historical_content"):
            self.assertEqual(self.page(first, kind).total_count, 2)
            self.assertTrue(self.page(first, kind).has_more)
            self.assertFalse(self.page(second, kind).has_more)
            self.assertNotEqual(self.page(first, kind).items, self.page(second, kind).items)
        complete = self.complete()
        validate_complete_export(complete, self.organization.id)
        self.assertEqual(export_record_count(complete), 6)
        self.assertEqual(sum(len(page.items) for page in complete.report.content.sections), 4)
        for change in (replace(complete.report.content, scopes=complete.report.content.scopes[:1]),
                       replace(complete.report.content, organization_id=str(uuid4())),
                       replace(complete.report.content, sections=complete.report.content.sections[:1]),
                       replace(complete.report.content, sections=(replace(complete.report.content.sections[0],
                           items=complete.report.content.sections[0].items[:1]), complete.report.content.sections[1]))):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                validate_complete_export(replace(complete, report=replace(complete.report, content=change)), self.organization.id)

    def test_complete_export_rejects_current_historical_rebinding_and_wrong_target_identity(self):
        self.apply(self.hit())
        complete = self.complete()
        content = complete.report.content
        scope, = content.scopes
        current, historical = content.sections
        malformed = (
            replace(content, scopes=(replace(scope, target=replace(scope.target, id=str(uuid4()))),)),
            replace(content, sections=(replace(current, items=(), total_count=0),
                replace(historical, items=current.items, total_count=1))),
            replace(content, sections=(replace(current, items=(replace(current.items[0], definition_sha256="0" * 64),)), historical)),
            replace(content, scopes=(replace(scope, retained_record_count=2),)),
            replace(content, scopes=(scope, scope), total_scope_count=2),
        )
        for changed in malformed:
            with self.subTest(changed=changed), self.assertRaises(ValidationError):
                validate_complete_export(replace(complete, report=replace(complete.report, content=changed)), self.organization.id)

    def test_report_and_export_reuse_one_readonly_transaction_and_preserve_database(self):
        self.apply(self.hit())
        before = self.path.read_bytes()
        connection_factory = self.repository._storage._connection
        transactions = []
        @contextmanager
        def observed(*args, **kwargs):
            self.assertEqual(kwargs, {"readonly": True})
            with connection_factory(*args, **kwargs) as connection:
                statements = []
                connection.set_trace_callback(statements.append)
                yield connection
                transactions.append(statements)
        with patch.object(self.repository._storage, "_connection", observed):
            self.report()
            self.complete()
        self.assertEqual(len(transactions), 2)
        self.assertTrue(all(sum(sql == "BEGIN" for sql in trace) == 1 for trace in transactions))
        self.assertFalse(any(sql.startswith(("INSERT", "UPDATE", "DELETE")) for trace in transactions for sql in trace))
        self.assertEqual(self.path.read_bytes(), before)

    def test_html_escapes_external_content_and_preserves_source_navigation(self):
        self.apply(self.hit('Example <script>alert("x")</script>', summary='<img src="https://bad.test/x" onerror="evil()">'))
        snapshot = self.complete()
        html = "".join(HtmlOrganizationReportRenderer().render(snapshot))
        parsed = ParsedHtml(html)
        self.assertNotIn("script", parsed.tags)
        self.assertNotIn("img", parsed.tags)
        self.assertIn('Example <script>alert("x")</script>', " ".join(parsed.text))
        self.assertIn("https://publisher.test/article", parsed.hrefs)
        self.assertIn("mentions run-show", " ".join(parsed.text))
        self.assertIn("doğrulanmış tehdit veya ihlal değildir", " ".join(parsed.text))

    def test_renderer_keeps_unsafe_links_and_terminal_controls_inert(self):
        self.apply(self.hit())
        snapshot = self.complete()
        content = snapshot.report.content
        current, historical = content.sections
        record, = current.items
        record = replace(record, value="javascript:alert(1)", details=("External \x1b[31m title",))
        scopes = (replace(content.scopes[0], target=replace(content.scopes[0].target, name="Example \x1b[2J")),)
        changed = replace(snapshot, report=replace(snapshot.report, content=replace(content, scopes=scopes,
            sections=(replace(current, items=(record,)), historical))))
        parsed = ParsedHtml("".join(HtmlOrganizationReportRenderer().render(changed)))
        self.assertNotIn("javascript:alert(1)", parsed.hrefs)
        self.assertIn("javascript:alert(1)", " ".join(parsed.text))
        terminal = "\n".join(organization_report_lines(changed.report))
        self.assertNotIn("\x1b", terminal)
        self.assertIn("\\u001b[31m", terminal)
        self.assertIn("\\u001b[2J", terminal)

    def test_corrupted_content_ledger_stops_report_without_writes(self):
        self.apply(self.hit())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE mentions_runs SET request_key=?", ("0" * 64,))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.report()
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
