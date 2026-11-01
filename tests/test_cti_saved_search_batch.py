"""All active CTI watches can be refreshed once without silent truncation."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_cti_saved_searches import SQLiteCtiSavedSearchRepository
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.application.cti_saved_search_batch import CtiSavedSearchBatchService
from xti.application.cti_saved_searches import CtiSavedSearchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 30, 18, tzinfo=timezone.utc)


class CtiSavedSearchBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.clock_value = NOW
        self.saved = CtiSavedSearchService(
            SQLiteCtiSavedSearchRepository(self.path), clock=lambda: self.clock_value,
        )
        self.knowledge = CtiKnowledgeService(
            SQLiteCtiKnowledgeRepository(self.path), clock=lambda: self.clock_value,
        )

    def entity(self, name, source):
        return self.knowledge.add_entity(
            "malware", name, aliases=(), source_name=source,
            source_reference=f"local:{source}", confidence=70,
            description="Toplu kayıtlı CTI arama kabul testi kaydı.",
        )

    def batch(self, **values):
        return CtiSavedSearchBatchService(
            self.saved, clock=lambda: self.clock_value,
        ).run(**values)

    def test_all_active_searches_run_in_stable_name_order_and_revoked_is_skipped(self):
        zeta = self.saved.add("Zeta watch", "Beta", kind="entity")
        alpha = self.saved.add("Alpha watch", "Alpha", kind="entity")
        revoked = self.saved.add("Revoked watch", "Gamma", kind="entity")
        self.saved.revoke(revoked.saved_search.id, reason="Bu arama kapsam dışı bırakıldı.")
        self.entity("Alpha RAT", "alpha")
        self.entity("Beta RAT", "beta")

        report = self.batch(max_searches=10, item_limit=10)

        self.assertEqual((report.planned_search_count, report.completed_search_count), (2, 2))
        self.assertEqual([item.display_name for item in report.items],
                         ["Alpha watch", "Zeta watch"])
        self.assertEqual((report.total_count, report.added_count), (2, 2))
        self.assertEqual(self.saved.show(alpha.saved_search.id).total_run_count, 1)
        self.assertEqual(self.saved.show(zeta.saved_search.id).total_run_count, 1)
        self.assertEqual(self.saved.show(revoked.saved_search.id).total_run_count, 0)

    def test_second_batch_only_notifies_the_search_with_a_meaningful_change(self):
        alpha = self.saved.add("Alpha watch", "Alpha")
        beta = self.saved.add("Beta watch", "Beta")
        self.entity("Alpha RAT", "alpha-one")
        self.entity("Beta RAT", "beta-one")
        first = self.batch()
        self.assertEqual(first.notification_count, 0)

        self.clock_value += timedelta(minutes=1)
        self.entity("Alpha Loader", "alpha-two")
        second = self.batch()

        self.assertEqual(second.notification_count, 1)
        by_id = {item.saved_search_id: item for item in second.items}
        self.assertIsNotNone(by_id[alpha.saved_search.id].notification_id)
        self.assertIsNone(by_id[beta.saved_search.id].notification_id)
        self.assertEqual(by_id[alpha.saved_search.id].added_count, 1)

    def test_overflow_and_invalid_limits_fail_before_any_run(self):
        first = self.saved.add("Alpha watch", "Alpha")
        second = self.saved.add("Beta watch", "Beta")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValidationError, "tamamı toplu sınıra sığmıyor"):
            self.batch(max_searches=1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.saved.show(first.saved_search.id).total_run_count, 0)
        self.assertEqual(self.saved.show(second.saved_search.id).total_run_count, 0)
        for values in ((0, 100), (501, 100), (1, 0), (1, 501)):
            with self.assertRaises(ValidationError):
                CtiSavedSearchBatchService.validate_limits(*values)

    def test_empty_batch_is_successful_and_has_no_invented_work(self):
        report = self.batch()
        self.assertEqual((report.planned_search_count, report.completed_search_count), (0, 0))
        self.assertEqual((report.total_count, report.notification_count, report.items), (0, 0, ()))

    def test_later_failure_keeps_completed_run_and_does_not_start_following_work(self):
        first = self.saved.add("Alpha watch", "Alpha")
        second = self.saved.add("Beta watch", "Beta")
        third = self.saved.add("Gamma watch", "Gamma")
        self.entity("Alpha RAT", "alpha")
        original_run = self.saved.run
        calls = 0

        def fail_second(saved_search_id, *, item_limit=100):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise StorageError("İkinci arama için kontrollü kayıt hatası.")
            return original_run(saved_search_id, item_limit=item_limit)

        self.saved.run = fail_second
        with self.assertRaises(StorageError):
            self.batch()
        self.assertEqual(self.saved.show(first.saved_search.id).total_run_count, 1)
        self.assertEqual(self.saved.show(second.saved_search.id).total_run_count, 0)
        self.assertEqual(self.saved.show(third.saved_search.id).total_run_count, 0)

    def call_cli(self, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_runs_all_once_and_returns_bounded_json_report(self):
        self.clock_value = datetime.now(timezone.utc)
        watch = self.saved.add("Alpha watch", "Alpha")
        self.entity("Alpha RAT", "alpha")
        code, output, error = self.call_cli(
            "cti", "watch-run-all", "--search-limit", "5", "--item-limit", "10",
        )
        self.assertEqual((code, error), (0, ""))
        data = json.loads(output)["data"]
        self.assertEqual((data["planned_search_count"], data["completed_search_count"]),
                         (1, 1))
        self.assertEqual(data["items"][0]["saved_search_id"], watch.saved_search.id)
        self.assertEqual(self.saved.show(watch.saved_search.id).total_run_count, 1)


if __name__ == "__main__":
    unittest.main()
