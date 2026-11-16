"""Saved company results preserve membership, evidence and source outcome."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_company_content import SQLiteCompanyContentRepository
from xti.adapters.sqlite_mention_groups import SQLiteMentionGroupRepository
from xti.adapters.sqlite_mention_notifications import SQLiteMentionNotificationBridge
from xti.adapters.sqlite_mention_targets import SQLiteMentionTargetRepository
from xti.adapters.sqlite_mentions import SQLiteMentionRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.company_content import CompanyContentService
from xti.application.mention_groups import MentionGroupService
from xti.domain.assets import ValidationError
from xti.domain.mention_groups import MentionGroupDefinition
from xti.domain.mentions import MentionHit, MentionRequest, MentionResponse, MentionTarget, build_query, company_target


class CompanyContentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        self.organizations = SQLiteOrganizationRepository(self.path)
        self.organization = self.organizations.add(name_key="example", display_name="Example",
            reason="Explicit company", recorded_at=self.tick()).organization
        self.suppliers = SQLiteSupplierRepository(self.path)
        self.supplier = self.suppliers.add(name_key="supplier", display_name="Supplier", primary_domain="supplier.test",
            relationship_type="software", criticality="high", reason="Explicit supplier", recorded_at=self.tick()).supplier
        self.sources = SQLiteMentionRepository(self.path)
        self.groups = SQLiteMentionGroupRepository(self.path)
        self.targets = SQLiteMentionTargetRepository(self.path)
        self.repository = SQLiteCompanyContentRepository(self.path)
        self.service = CompanyContentService(self.repository, clock=lambda: self.now)
        self.source = Mock()
        self.source.fetch.side_effect = lambda request: MentionResponse(build_query(request.target), None,
            (self.hit(request.target.name, path=request.target.id),), 1)
        self.group_service = MentionGroupService(self.groups, self.sources, self.targets,
            LocalExecutionLock(self.path), notifications=SQLiteMentionNotificationBridge(self.path),
            source_factory=lambda: self.source, clock=lambda: self.now)
        self.addCleanup(patch.stopall)
        patch("socket.socket.connect", side_effect=AssertionError("Content read must stay local")).start()
        patch("socket.getaddrinfo", side_effect=AssertionError("Content read must stay local")).start()
        patch("xti.adapters.tavily_search.load_tavily_api_key", side_effect=AssertionError("No key read")).start()

    def tick(self):
        self.now += timedelta(seconds=1)
        return self.now.isoformat()

    @staticmethod
    def hit(title="Example news", *, path="article", summary="Available publisher excerpt"):
        return MentionHit("https://publisher.test/" + path, title, summary, "2026-11-15", .8)

    def request(self, *, supplier=False):
        target = self.targets.resolve("supplier" if supplier else "organization",
                                      self.supplier.id if supplier else self.organization.id)
        return MentionRequest(target, "news", 10)

    def apply(self, *hits, request=None):
        request = request or self.request()
        at = self.tick()
        return self.sources.apply(request, MentionResponse(build_query(request.target), None, tuple(hits), 1),
                                  started_at=at, finished_at=at)

    def show(self, **options):
        return self.service.show(self.organization.id, **options)

    def group(self):
        self.tick()
        return self.group_service.save("Explicit suppliers", MentionGroupDefinition(self.organization.id,
            (self.supplier.id,), interval_hours=1))

    def test_uncollected_is_not_successful_empty_and_read_does_not_write(self):
        before = self.path.read_bytes()
        result = self.show()
        self.assertEqual(result["state"], "not_checked")
        scope, = result["scopes"]["items"]
        self.assertEqual(scope["source_status"], "uncollected")
        self.assertIsNone(scope["latest_success_result_count"])
        self.assertEqual(result["sections"]["content"]["total_count"], 0)
        self.assertEqual(result["consistency"], "single_read_snapshot")
        self.assertEqual(self.path.read_bytes(), before)

    def test_structured_content_preserves_title_excerpt_link_date_and_visible_match(self):
        run = self.apply(replace(self.hit("Example [bold] news", summary="literal <script> excerpt"), summary_truncated=True))
        result = self.show()
        item, = result["sections"]["content"]["items"]
        self.assertEqual(item["title"], "Example [bold] news")
        self.assertEqual(item["available_excerpt"], "literal <script> excerpt")
        self.assertEqual(item["source_url"], "https://publisher.test/article")
        self.assertEqual(item["published_at"], "2026-11-15")
        self.assertEqual(item["source_run_id"], run.id)
        self.assertEqual(item["match_status"], "visible_match")
        self.assertEqual(item["match_fields"], ["title"])
        self.assertTrue(item["candidate"])
        self.assertTrue(item["excerpt_truncated"])
        self.assertEqual(result["state"], "content_found")
        json.dumps(result, allow_nan=False)

    def test_provider_candidate_and_missing_excerpt_are_explicit(self):
        self.apply(replace(self.hit("Unrelated provider candidate", summary=""), published_at=None))
        item, = self.show()["sections"]["content"]["items"]
        self.assertEqual(item["match_status"], "provider_candidate")
        self.assertEqual(item["matched_terms"], [])
        self.assertEqual(item["excerpt_status"], "unavailable")
        self.assertIsNone(item["available_excerpt"])
        self.assertIsNone(item["published_at"])

    def test_successful_empty_preserves_previous_content_and_failure_preserves_success(self):
        first = self.apply(self.hit())
        empty = self.apply()
        result = self.show()
        self.assertEqual(result["state"], "no_content")
        scope, = result["scopes"]["items"]
        self.assertEqual((scope["source_status"], scope["latest_success_result_count"]), ("empty", 0))
        item, = result["sections"]["content"]["items"]
        self.assertEqual((item["status"], item["source_run_id"]), ("retained_candidate", first.id))
        at = self.tick()
        failed = self.sources.record_failure(self.request(), error="Provider unavailable", started_at=at, finished_at=at)
        result = self.show()
        self.assertEqual(result["state"], "check_failed")
        scope, = result["scopes"]["items"]
        self.assertEqual(scope["latest_attempt"]["id"], failed.id)
        self.assertEqual(scope["latest_success"]["id"], empty.id)
        self.assertEqual(scope["source_status"], "error")
        self.assertEqual(result["sections"]["content"]["total_count"], 1)

    def test_stale_empty_and_future_clock_are_not_fresh_no_content(self):
        self.apply()
        self.now += timedelta(days=2)
        self.assertEqual(self.show()["state"], "stale")
        self.now -= timedelta(days=3)
        self.assertEqual(self.show()["state"], "outcome_unknown")

    def test_unresolved_attempt_never_looks_like_successful_empty(self):
        self.apply()
        snapshot = self.repository.read(self.organization.id, observed_at=self.now.isoformat(),
            stale_after_hours=24, offset=0, limit=50)
        scope, = snapshot.scopes
        for status in ("reserved", "unknown"):
            attempt = replace(scope.coverage.latest_attempt, status=status, source_run_id=None)
            changed_scope = replace(scope, coverage=replace(scope.coverage, latest_attempt=attempt))
            repository = Mock()
            repository.read.return_value = replace(snapshot, scopes=(changed_scope,))
            result = CompanyContentService(repository, clock=lambda: self.now).show(self.organization.id)
            with self.subTest(status=status):
                self.assertEqual(result["state"], "outcome_unknown")
                self.assertEqual(result["scopes"]["items"][0]["source_status"], status)

    def test_exact_identity_excludes_same_name_company_other_organization_and_unselected_supplier(self):
        self.apply(self.hit())
        self.apply(self.hit(path="company"), request=replace(self.request(), target=company_target("Example")))
        self.apply(self.hit(path="other"), request=replace(self.request(),
            target=MentionTarget("organization", str(uuid4()), "Example", ())))
        self.apply(self.hit(path="supplier"), request=self.request(supplier=True))
        self.assertEqual(self.show()["sections"]["content"]["total_count"], 1)

    def test_pagination_totals_and_overall_state_do_not_depend_on_scope_page(self):
        self.group()
        self.apply(self.hit(path="one"), self.hit(path="two"))
        result = self.show(scope_limit=1, limit=1)
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["scopes"]["total_count"], 2)
        self.assertTrue(result["scopes"]["has_more"])
        self.assertEqual(result["sections"]["content"]["total_count"], 2)
        self.assertTrue(result["sections"]["content"]["has_more"])
        second = self.show(scope_offset=1, scope_limit=1, offset=1, limit=1)
        self.assertEqual(second["state"], "partial")
        self.assertEqual(second["sections"]["content"]["total_count"], 2)
        self.assertFalse(second["sections"]["content"]["has_more"])
        self.assertNotEqual(result["sections"]["content"]["items"][0]["id"],
                            second["sections"]["content"]["items"][0]["id"])
        beyond = self.show(scope_offset=100, offset=100, limit=1)
        self.assertEqual(beyond["state"], "partial")
        self.assertEqual(beyond["scopes"]["total_count"], 2)
        self.assertEqual(beyond["sections"]["content"]["items"], [])

    def test_renamed_organization_keeps_previous_definition_historical(self):
        first = self.apply(self.hit())
        self.organizations.rename(self.organization.id, name_key="new example", display_name="New Example",
            reason="Explicit rename", recorded_at=self.tick())
        result = self.show()
        self.assertEqual(result["state"], "not_checked")
        self.assertEqual(result["sections"]["content"]["total_count"], 0)
        item, = result["sections"]["historical_content"]["items"]
        self.assertEqual(item["target"]["name"], "Example")
        self.assertEqual(item["scope_status"], "old_definition")
        self.assertEqual(item["source_run_id"], first.id)

    def test_removed_supplier_uses_exact_old_receipt_not_later_shared_record(self):
        group = self.group()
        run = self.group_service.run(group.id)["run"]
        source_id = next(item.result_run_id for item in run.attempts if item.request.target.kind == "supplier")
        self.tick()
        self.group_service.save(group.name, replace(group.definition, supplier_ids=()))
        self.apply(self.hit("Unrelated later update", path=self.supplier.id), request=self.request(supplier=True))
        result = self.show()
        item, = result["sections"]["historical_content"]["items"]
        self.assertEqual(item["title"], "Supplier")
        self.assertEqual(item["source_run_id"], source_id)
        self.assertEqual(item["scope_status"], "inactive_relationship")
        self.assertEqual(self.sources.run_show(source_id).response.hits[0].title, "Supplier")

    def test_inactive_organization_cannot_report_current_success(self):
        self.apply(self.hit())
        self.organizations.revoke(self.organization.id, reason="Stopped", recorded_at=self.tick())
        result = self.show()
        self.assertEqual(result["state"], "inactive")
        self.assertEqual(result["sections"]["content"]["total_count"], 0)
        self.assertEqual(result["sections"]["historical_content"]["total_count"], 1)

    def test_repository_owns_one_readonly_connection(self):
        self.apply(self.hit())
        original = self.repository.storage._connection
        connections = []

        @contextmanager
        def record_connection(*, readonly=False):
            connections.append(readonly)
            with original(readonly=readonly) as connection:
                yield connection

        with patch.object(self.repository.storage, "_connection", record_connection):
            self.show()
        self.assertEqual(connections, [True])

    def test_corrupt_source_evidence_is_rejected_without_changing_data(self):
        self.apply(self.hit())
        with self.storage._connection() as connection:
            connection.execute("UPDATE mentions_runs SET payload_sha256=?", ("0" * 64,))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.show()
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_arguments_and_naive_clock_fail_before_repository_read(self):
        repository = Mock()
        service = CompanyContentService(repository, clock=lambda: self.now)
        for options in ({"scope_offset": True}, {"scope_limit": 101}, {"offset": -1},
                        {"limit": False}, {"limit": 501}, {"stale_after_hours": 0}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                service.show(self.organization.id, **options)
        with self.assertRaises(ValidationError):
            service.show("not-a-uuid")
        with self.assertRaises(ValidationError):
            CompanyContentService(repository, clock=lambda: datetime(2026, 1, 1)).show(self.organization.id)
        repository.read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
