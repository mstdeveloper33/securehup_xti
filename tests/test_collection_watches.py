"""Saved-watch selection and fresh source execution in temporary real stores."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.application.collection_watches import CollectionWatchService
from xti.application.ransomlook_ransomware import RansomLookClaimHistoryService
from xti.application.ransomlook_watches import RansomLookWatchService
from xti.application.ransomware_claims import RansomwareClaimHistoryService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.domain.assets import ValidationError
from xti.ports.discovery import SourceError
from tests.test_brand_username_watches import FakeSource, FakeSherlockSource, NOW, github
from tests.test_ransomware_watch_refresh import MutableSource, feed
from tests.test_ransomlook_watches import snapshot
from tests.test_ransomlook_ransomware import post
from tests.test_threatcluster_ransomware import claim


class CollectionWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.clock = lambda: NOW + timedelta(minutes=10)
        self.maigret = FakeSource({"GitHub": github()}, {"GitHub": github()})
        self.sherlock = FakeSherlockSource({"Carrd": "https://samplebrand.carrd.co/"})
        self.username = BrandUsernameWatchService(
            SQLiteBrandUsernameWatchRepository(self.path),
            {"maigret": self.maigret, "sherlock": self.sherlock}, clock=self.clock,
        )
        self.tc_source = MutableSource(feed([claim("Example Holding", website="example.com")]))
        self.rl_source = MutableSource(snapshot([post("Example Holding")], minute=0))
        self.tc_claims = SQLiteRansomwareClaimRepository(self.path)
        self.rl_claims = SQLiteRansomLookClaimRepository(self.path)
        self.tc_history = RansomwareClaimHistoryService(self.tc_claims, self.tc_source, clock=self.clock)
        self.rl_history = RansomLookClaimHistoryService(self.rl_claims, self.rl_source, clock=self.clock)
        self.tc = RansomwareWatchService(
            SQLiteRansomwareWatchRepository(self.path), self.tc_claims, clock=self.clock,
        )
        self.rl = RansomLookWatchService(
            SQLiteRansomLookWatchRepository(self.path), self.rl_claims, clock=self.clock,
        )
        self.service = CollectionWatchService(
            self.username,
            {"threatcluster": self.tc_history, "ransomlook": self.rl_history},
            {"threatcluster": self.tc, "ransomlook": self.rl},
        )

    def add_social(self, source="maigret"):
        return self.username.add(
            f"Example {source}", "samplebrand", source_key=source,
            platforms=("GitHub",) if source == "maigret" else ("Carrd",),
        ).watch

    def add_ransomware(self):
        tc = self.tc.add("Example TC", "Example Holding", kind="organization").watch
        rl = self.rl.add("Example RL", "Example Holding", kind="organization").watch
        return tc, rl

    def test_empty_selection_never_requires_or_reads_any_service(self):
        self.assertEqual(CollectionWatchService().plan(), ())
        with patch.object(self.username, "show") as show:
            self.assertEqual(self.service.plan(), ())
            show.assert_not_called()

    def test_invalid_duplicate_or_overflow_selection_fails_before_storage(self):
        first = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        invalid = (
            {"username_watch_ids": first},
            {"username_watch_ids": (first, first)},
            {"ransomware_watch_ids": ("not-an-id",)},
            {"ransomlook_watch_ids": (first.upper(),)},
            {"username_watch_ids": tuple(str(uuid4()) for _ in range(26)),
             "ransomware_watch_ids": tuple(str(uuid4()) for _ in range(25))},
            {"item_limit": 0}, {"item_limit": True}, {"item_limit": 501},
        )
        with patch.object(self.username, "show") as show, patch.object(self.tc_history, "status") as status:
            for kwargs in invalid:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                    self.service.plan(**kwargs)
            show.assert_not_called()
            status.assert_not_called()

    def test_plan_is_read_only_deterministic_and_keeps_explicit_metadata(self):
        social = [self.add_social(), self.add_social("sherlock")]
        tc, rl = self.add_ransomware()
        before = self.path.read_bytes()
        tasks = self.service.plan(
            username_watch_ids=tuple(item.id for item in reversed(social)),
            ransomware_watch_ids=(tc.id,), ransomlook_watch_ids=(rl.id,),
        )
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual([task.watches[0].watch_id for task in tasks[:2]], sorted(item.id for item in social))
        self.assertEqual([task.source for task in tasks[2:]], ["threatcluster", "ransomlook"])
        self.assertEqual((tasks[2].watches[0].query, tasks[3].watches[0].kind),
                         ("Example Holding", "organization"))
        self.assertEqual((self.tc_source.calls, self.rl_source.calls, self.maigret.calls), (0, 0, []))

    def test_unselected_services_are_not_read_or_required(self):
        watch = self.add_social()
        service = CollectionWatchService(self.username)
        with patch.object(self.tc_history, "status", side_effect=AssertionError("unselected")):
            task, = service.plan(username_watch_ids=(watch.id,))
            self.assertEqual(service.run(task).status, "complete")
        self.assertEqual(self.sherlock.calls, [])

    def test_missing_revoked_or_unconfigured_watch_rejected_before_source(self):
        tc, rl = self.add_ransomware()
        social = self.add_social()
        self.tc.revoke(tc.id, reason="No longer tracked")
        self.rl.revoke(rl.id, reason="No longer tracked")
        self.username.revoke(social.id, reason="No longer tracked")
        for field, value in (
            ("username_watch_ids", social.id), ("ransomware_watch_ids", tc.id),
            ("ransomlook_watch_ids", rl.id), ("ransomlook_watch_ids", str(uuid4())),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.service.plan(**{field: (value,)})
        self.assertEqual((self.tc_source.calls, self.rl_source.calls, self.maigret.calls), (0, 0, []))

    def test_social_failure_preserves_prior_success_and_other_source_is_independent(self):
        first = self.add_social()
        second = self.add_social("sherlock")
        first_task = self.service.plan(username_watch_ids=(first.id,))[0]
        baseline = self.service.run(first_task)
        self.maigret.responses = [SourceError("Source unavailable")]
        failed = self.service.run(first_task)
        other = self.service.run(self.service.plan(username_watch_ids=(second.id,))[0])
        self.assertTrue(baseline.username.is_baseline)
        self.assertEqual((failed.status, other.status), ("failed", "complete"))
        self.assertEqual(self.username.show(first.id).total_run_count, 2)
        self.assertEqual(self.username.show_run(baseline.username.run.id).run.found_count, 1)
        self.assertEqual((failed.username.run.source_name, other.username.run.source_name), ("Maigret", "Sherlock"))

    def test_each_ransomware_source_refreshes_once_for_only_selected_watches(self):
        tc, rl = self.add_ransomware()
        domain = self.tc.add("Example domain", "example.com", kind="domain").watch
        excluded = self.tc.add("Excluded", "Other Company", kind="organization").watch
        tasks = self.service.plan(ransomware_watch_ids=(domain.id, tc.id), ransomlook_watch_ids=(rl.id,))
        results = [self.service.run(task) for task in tasks]
        self.assertEqual([result.status for result in results], ["complete", "complete"])
        self.assertEqual((self.tc_source.calls, self.rl_source.calls), (1, 1))
        self.assertEqual([len(result.ransomware.watches) for result in results], [2, 1])
        for result in results:
            self.assertTrue(all(report.is_baseline for report in result.ransomware.watches))
            self.assertEqual({report.run.source_run_id for report in result.ransomware.watches},
                             {result.ransomware.refresh.run.id})
            self.assertEqual(result.ransomware.skipped_watch_ids, ())
        self.assertEqual(self.tc.show(excluded.id).total_run_count, 0)
        repeated = self.service.run(tasks[0])
        self.assertTrue(all(report.run.added_count == 0 for report in repeated.ransomware.watches))
        self.assertTrue(all(report.notification_id is None for report in repeated.ransomware.watches))

    def test_failed_refresh_skips_all_selected_watches_and_keeps_previous_snapshot(self):
        tc, rl = self.add_ransomware()
        tasks = self.service.plan(ransomware_watch_ids=(tc.id,), ransomlook_watch_ids=(rl.id,))
        for task, source, watches, claims in (
            (tasks[0], self.tc_source, self.tc, self.tc_claims),
            (tasks[1], self.rl_source, self.rl, self.rl_claims),
        ):
            with self.subTest(source=task.source):
                baseline = self.service.run(task)
                source.value = SourceError("Public source unavailable")
                failed = self.service.run(task)
                self.assertEqual(failed.status, "failed")
                self.assertEqual(failed.ransomware.watches, ())
                self.assertEqual(failed.ransomware.skipped_watch_ids, (task.watches[0].watch_id,))
                self.assertEqual(watches.show(task.watches[0].watch_id).total_run_count, 1)
                self.assertEqual(claims.latest_snapshot().run.id, baseline.ransomware.refresh.run.id)

    def test_definition_change_after_plan_stops_before_refresh_or_social_request(self):
        social = self.add_social()
        tc, _ = self.add_ransomware()
        social_task, tc_task = self.service.plan(username_watch_ids=(social.id,), ransomware_watch_ids=(tc.id,))
        self.username.add(social.display_name, "changedbrand", platforms=("GitHub",))
        self.tc.add(tc.display_name, "Changed Company", kind="organization")
        for task in (social_task, tc_task):
            with self.subTest(kind=task.kind), self.assertRaisesRegex(ValidationError, "değişti"):
                self.service.run(task)
        self.assertEqual((self.maigret.calls, self.tc_source.calls), ([], 0))

    def test_watch_definition_changed_during_refresh_is_not_evaluated(self):
        tc, rl = self.add_ransomware()
        for field, watch, watches, history in (
            ("ransomware_watch_ids", tc, self.tc, self.tc_history),
            ("ransomlook_watch_ids", rl, self.rl, self.rl_history),
        ):
            task, = self.service.plan(**{field: (watch.id,)})
            original = history.refresh

            def refresh(**kwargs):
                report = original(**kwargs)
                watches.add(watch.display_name, "Changed Company", kind="organization")
                return report

            with self.subTest(source=task.source), patch.object(history, "refresh", side_effect=refresh):
                with self.assertRaisesRegex(ValidationError, "tanımı kaynak yenilenirken değişti"):
                    self.service.run(task)
            self.assertEqual(watches.show(watch.id).total_run_count, 0)
            self.assertEqual(history.status().latest_run.status, "complete")

    def test_ransomlook_expected_source_id_is_checked_before_any_watch_write(self):
        _, watch = self.add_ransomware()
        refresh = self.rl_history.refresh()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValidationError, "beklenen yenilemeyle"):
            self.rl.run(watch.id, expected_source_run_id=str(uuid4()))
        self.assertEqual(self.path.read_bytes(), before)
        result = self.rl.run(watch.id, expected_source_run_id=refresh.run.id)
        self.assertEqual(result.run.source_run_id, refresh.run.id)

    def test_wrong_refresh_source_and_watch_identity_are_not_accepted(self):
        tc, _ = self.add_ransomware()
        task, = self.service.plan(ransomware_watch_ids=(tc.id,))
        actual = self.tc_history.refresh()
        wrong = replace(actual, run=replace(actual.run, source_name="Other source"))
        with patch.object(self.tc_history, "refresh", return_value=wrong):
            with self.assertRaisesRegex(ValidationError, "geçersiz toplama sonucu"):
                self.service.run(task)
        self.assertEqual(self.tc.show(tc.id).total_run_count, 0)
        valid = self.service.run(task).ransomware.watches[0]
        wrong_watch = replace(valid, run=replace(valid.run, watch_id=str(uuid4())))
        with patch.object(self.tc_history, "refresh", return_value=actual), patch.object(self.tc, "run", return_value=wrong_watch):
            with self.assertRaisesRegex(ValidationError, "uyuşmuyor"):
                self.service.run(task)

    def test_wrong_requested_watch_identity_is_rejected_before_source_access(self):
        social = self.add_social()
        tc, rl = self.add_ransomware()
        for field, watch, service in (
            ("username_watch_ids", social, self.username),
            ("ransomware_watch_ids", tc, self.tc),
            ("ransomlook_watch_ids", rl, self.rl),
        ):
            details = service.show(watch.id)
            incorrect = replace(details, watch=replace(watch, id=str(uuid4())))
            with self.subTest(field=field), patch.object(service, "show", return_value=incorrect):
                with self.assertRaisesRegex(ValidationError, "seçilen kimlikle uyuşmuyor"):
                    self.service.plan(**{field: (watch.id,)})
        self.assertEqual((self.maigret.calls, self.tc_source.calls, self.rl_source.calls), ([], 0, 0))

    def test_social_result_source_mismatch_is_rejected(self):
        watch = self.add_social()
        task, = self.service.plan(username_watch_ids=(watch.id,))
        baseline = self.service.run(task).username
        wrong = replace(baseline, run=replace(baseline.run, source_name="Sherlock"))
        with patch.object(self.username, "run", return_value=wrong):
            with self.assertRaisesRegex(ValidationError, "geçersiz toplama sonucu"):
                self.service.run(task)

    def test_later_watch_change_keeps_prior_commit_but_stops_remaining_work(self):
        first = self.tc.add("First watch", "Example Holding", kind="organization").watch
        second = self.tc.add("Second watch", "Example Holding", kind="organization").watch
        task, = self.service.plan(ransomware_watch_ids=(first.id, second.id))
        ordered = {watch.id: watch for watch in (first, second)}
        earlier, later = (ordered[target.watch_id] for target in task.watches)
        original = self.tc.run

        def run(watch_id, **kwargs):
            report = original(watch_id, **kwargs)
            self.tc.add(later.display_name, "Changed Company", kind="organization")
            return report

        with patch.object(self.tc, "run", side_effect=run):
            with self.assertRaisesRegex(ValidationError, "tanımı kaynak yenilenirken değişti"):
                self.service.run(task)
        self.assertEqual(self.tc.show(earlier.id).total_run_count, 1)
        self.assertEqual(self.tc.show(later.id).total_run_count, 0)
        self.assertEqual(self.tc_source.calls, 1)
