"""Explicit passive collection ordering, scope and independent source results."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from uuid import uuid4

from xti.application.collection import CollectionService
from xti.domain.assets import ValidationError
from xti.domain.collection import (
    COLLECTION_TASK_IDS, DEFAULT_COLLECTION_TASKS, CollectionTask, CollectionWatchTarget,
)
from xti.domain.cti_feeds import CTI_FEED_POLICIES, CtiFeedRun
from xti.domain.discovery import ScanResult
from xti.domain.findings import ImportSummary
from xti.domain.jobs import ScanAttempt, ScanJob
from xti.domain.public_notices import (
    PublicNoticeChange, PublicNoticeRefreshReport, PublicNoticeRun, PublicNoticeStatus, notice_sha256,
)
from xti.domain.surface import SurfaceDiscoveryResult
from xti.ports.jobs import WorkerBusyError
from tests.test_public_notices import feed as notice_feed, item as notice_item


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


class FakeLock:
    def __init__(self):
        self.entries = 0
        self.active = False
        self.busy = False

    @contextmanager
    def acquire(self):
        if self.active or self.busy:
            raise WorkerBusyError("İşlem kilitli.")
        self.entries += 1
        self.active = True
        try:
            yield
        finally:
            self.active = False


class ScanPreflight:
    def __init__(self):
        self.calls = []
        self.error = None

    def validate_targets(self, targets, *, typos):
        self.calls.append((targets, typos))
        if self.error:
            raise self.error
        return tuple(targets)


class FakeJobs:
    def __init__(self, lock, mutations):
        self.lock = lock
        self.mutations = mutations
        self.discoveries = {name: ScanPreflight() for name in ("crt.sh", "urlscan")}
        self.outcomes = {"crt.sh": "complete", "urlscan": "complete"}
        self.queued = {}
        self.results = []
        self.transform = lambda attempt: attempt

    def enqueue(self, domains, *, typos, provider):
        assert self.lock.active
        job = ScanJob(
            f"job-{len(self.queued) + 1}", tuple(domains), typos, provider,
            "rule-test", "queued", NOW.isoformat(), NOW.isoformat(), 0,
        )
        self.queued[job.id] = job
        self.mutations.append(("enqueue", provider))
        return job

    def run(self, *args, **kwargs):
        raise AssertionError("Collection must use the already-owned lock.")

    def run_owned(self, job_id, *, progress):
        assert self.lock.active
        job = self.queued[job_id]
        status = self.outcomes[job.provider]
        if isinstance(status, BaseException):
            raise status
        self.mutations.append(("scan", job.provider))
        result = ScanResult(
            job.targets, NOW.isoformat(), NOW.isoformat(), status, (),
            ImportSummary(0, 0, 0, 0, 0, 0), (),
        )
        attempt = ScanAttempt(
            f"attempt-{job.id}", job.id, 1, status,
            NOW.isoformat(), NOW.isoformat(), None, None, (), result,
        )
        self.results.append(attempt)
        return self.transform(attempt)


class FakeDiscovery:
    def __init__(self, provider, lock, mutations):
        self.source = SimpleNamespace(provider=provider)
        self.lock = lock
        self.mutations = mutations
        self.preparations = []
        self.outcome = "complete"
        self.error = None
        self.results = []

    def list(self, domain, *, status, limit):
        self.preparations.append((domain, status, limit))
        if self.error:
            raise self.error
        return ()

    def discover(self, domain):
        assert self.lock.active
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        self.mutations.append(("discovery", self.source.provider))
        result = SurfaceDiscoveryResult(
            asset_value=domain, started_at=NOW.isoformat(), finished_at=NOW.isoformat(),
            status=self.outcome, source_url="https://example.invalid/archive", record_count=0,
            skipped_names=0, ignored_names=0, warnings=(), candidates_created=0,
            candidates_existing=0, evidence_created=0, evidence_existing=0,
            candidate_domains=(), error="Kaynak kapalı." if self.outcome == "failed" else None,
            run_id=f"discovery-{self.source.provider}-{len(self.results) + 1}",
            provider=self.source.provider,
        )
        self.results.append(result)
        return result


class FakeFeed:
    def __init__(self, name, lock, mutations):
        self.name = name
        self.source = object()
        self.lock = lock
        self.mutations = mutations
        self.preparations = []
        self.outcome = "complete"
        self.error = None
        self.results = []

    def status(self, *, run_limit):
        self.preparations.append(run_limit)
        if self.error:
            raise self.error
        return SimpleNamespace(source_name=CTI_FEED_POLICIES[self.name].source_name)

    def sync(self):
        assert self.lock.active
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        self.mutations.append(("ioc", self.name))
        result = CtiFeedRun(
            id=f"feed-{self.name}-{len(self.results) + 1}", sequence=len(self.results) + 1,
            source_name=CTI_FEED_POLICIES[self.name].source_name, status=self.outcome,
            source_url="https://example.invalid/feed", content_sha256=None,
            started_at=NOW.isoformat(), finished_at=NOW.isoformat(),
            source_record_count=0, indicator_count=0, added_count=0, observed_count=0,
            updated_count=0, unchanged_count=0, reactivated_count=0, revoked_count=0,
            error="Kaynak kapalı." if self.outcome == "failed" else None,
        )
        self.results.append(result)
        return result


class FakePublicNotices:
    def __init__(self, lock, mutations):
        self.source = object()
        self.lock, self.mutations = lock, mutations
        self.preparations, self.results = [], []
        self.error = None
        self.outcome = "complete"
        self.status_transform = lambda value: value
        self.result_transform = lambda value: value

    def status(self, *, run_limit):
        self.preparations.append((run_limit, self.lock.active))
        if self.error:
            raise self.error
        return self.status_transform(PublicNoticeStatus(None, None, (), 0))

    def refresh(self):
        assert self.lock.active
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        self.mutations.append(("public_notice", "hibp"))
        complete = self.outcome == "complete"
        identifier = str(uuid4())
        records = notice_feed(notice_item(), notice_item("Other", "other.example")).notices
        run = PublicNoticeRun(
            sequence=len(self.results) + 1, id=identifier, status=self.outcome,
            started_at=NOW.isoformat(), finished_at=NOW.isoformat(),
            fetched_at=NOW.isoformat() if complete else None,
            content_sha256="0" * 64 if complete else None,
            snapshot_sha256="1" * 64 if complete else None,
            notice_count=2 if complete else 0, added_count=2 if complete else 0,
            updated_count=0, unchanged_count=0, removed_count=0,
            error=None if complete else "Katalog alınamadı.",
        )
        changes = tuple(PublicNoticeChange(identifier, "added", value, notice_sha256(value)) for value in records) if complete else ()
        result = PublicNoticeRefreshReport(run, changes, len(changes), complete)
        self.results.append(result)
        return self.result_transform(result)


class FakeAnalysis:
    def __init__(self, mutations):
        self.mutations = mutations
        self.calls = []
        self.fail_at = None
        self.result_domain = "example.com"

    def show(self, domain, *, stale_after_hours, finding_limit):
        self.calls.append((domain, stale_after_hours, finding_limit))
        if domain != "example.com":
            raise ValidationError("Adres kayıtlı değil.")
        if self.fail_at == len(self.calls):
            raise ValidationError("Yerel kanıt bozuk.")
        return SimpleNamespace(asset_value=self.result_domain, observed_mutations=len(self.mutations))


class CollectionServiceTests(unittest.TestCase):
    def setUp(self):
        self.mutations = []
        self.lock = FakeLock()
        self.jobs = FakeJobs(self.lock, self.mutations)
        self.discoveries = {
            name: FakeDiscovery(name, self.lock, self.mutations)
            for name in ("crt.sh", "theharvester")
        }
        self.feeds = {
            name: FakeFeed(name, self.lock, self.mutations)
            for name in ("feodo", "certpl")
        }
        self.analysis = FakeAnalysis(self.mutations)
        self.notices = FakePublicNotices(self.lock, self.mutations)
        self.service = CollectionService(
            self.jobs, self.discoveries, self.feeds, self.analysis, clock=lambda: NOW,
            public_notices=self.notices,
        )

    def test_plan_is_read_only_and_defaults_do_not_prepare_optional_sources(self):
        plan = self.service.plan("EXAMPLE.COM")
        self.assertEqual(plan.asset_value, "example.com")
        self.assertEqual(tuple(task.id for task in plan.tasks), DEFAULT_COLLECTION_TASKS)
        self.assertEqual(self.mutations, [])
        self.assertEqual(self.lock.entries, 0)
        self.assertEqual(self.discoveries["theharvester"].preparations, [])
        self.assertTrue(all(not feed.preparations for feed in self.feeds.values()))
        self.assertEqual(self.notices.preparations, [])

    def test_defaults_use_one_lock_keep_run_ids_and_analyze_after_collection(self):
        result = self.service.run("EXAMPLE.COM", finding_limit=3, stale_after_hours=48)
        self.assertEqual(result.status, "complete")
        self.assertEqual(tuple(step.task.id for step in result.steps), DEFAULT_COLLECTION_TASKS)
        self.assertEqual(self.lock.entries, 1)
        self.assertFalse(self.lock.active)
        self.assertEqual(self.mutations, [
            ("enqueue", "crt.sh"), ("scan", "crt.sh"),
            ("enqueue", "urlscan"), ("scan", "urlscan"), ("discovery", "crt.sh"),
        ])
        self.assertIs(result.steps[0].attempt, self.jobs.results[0])
        self.assertIs(result.steps[2].discovery, self.discoveries["crt.sh"].results[0])
        self.assertEqual(result.steps[0].attempt.id, "attempt-job-1")
        self.assertEqual(result.analysis.observed_mutations, len(self.mutations))
        self.assertEqual(self.analysis.calls, [("example.com", 48, 3)] * 3)

    def test_explicit_selection_replaces_defaults_and_uses_fixed_order(self):
        result = self.service.run(
            "example.com", tasks=("ioc-certpl", "discover-theharvester", "ioc-feodo"),
        )
        self.assertEqual(
            tuple(step.task.id for step in result.steps),
            ("discover-theharvester", "ioc-feodo", "ioc-certpl"),
        )
        self.assertEqual(self.mutations, [
            ("discovery", "theharvester"), ("ioc", "feodo"), ("ioc", "certpl"),
        ])
        self.assertTrue(all(not scan.calls for scan in self.jobs.discoveries.values()))
        self.assertEqual(self.discoveries["crt.sh"].preparations, [])
        self.assertEqual(result.steps[1].feed.source_name, "feodo-tracker")
        self.assertEqual(result.steps[2].feed.source_name, "certpl-warning-list")

    def test_source_failures_do_not_skip_independent_sources(self):
        self.jobs.outcomes["crt.sh"] = "failed"
        self.discoveries["theharvester"].outcome = "partial"
        self.feeds["feodo"].outcome = "failed"
        result = self.service.run("example.com", tasks=COLLECTION_TASK_IDS)
        self.assertEqual(result.status, "partial")
        self.assertEqual(
            tuple(step.status for step in result.steps),
            ("failed", "complete", "complete", "partial", "failed", "complete", "complete"),
        )
        self.assertEqual(len(result.steps), 7)
        self.assertIs(result.steps[4].feed, self.feeds["feodo"].results[0])

    def test_all_failed_is_failed_even_when_final_analysis_is_available(self):
        self.jobs.outcomes = {name: "failed" for name in self.jobs.outcomes}
        self.discoveries["crt.sh"].outcome = "failed"
        result = self.service.run("example.com")
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.steps), 3)
        self.assertEqual(result.analysis.asset_value, "example.com")

    def test_explicit_public_catalog_preflights_twice_and_preserves_shared_source_result(self):
        result = self.service.run("example.com", tasks=("notices-hibp",))
        self.assertEqual(result.status, "complete")
        self.assertEqual(self.notices.preparations, [(1, False), (1, True)])
        self.assertEqual(self.mutations, [("public_notice", "hibp")])
        self.assertIs(result.steps[0].public_notices, self.notices.results[0])
        self.assertTrue(any("domainin bulgu sayısı değildir" in note for note in result.plan.notes))
        self.assertEqual(result.steps[0].public_notices.run.notice_count, 2)

    def test_public_source_failure_keeps_result_failed_and_lock_released(self):
        self.notices.outcome = "failed"
        result = self.service.run("example.com", tasks=("notices-hibp",))
        self.assertEqual((result.status, result.steps[0].status), ("failed", "failed"))
        self.assertEqual(result.steps[0].public_notices.run.error, "Katalog alınamadı.")
        self.assertFalse(self.lock.active)

    def test_public_history_damage_prevents_earlier_independent_source_requests(self):
        self.notices.error = ValidationError("Katalog geçmişi bozuk.")
        with self.assertRaisesRegex(ValidationError, "Katalog geçmişi"):
            self.service.run("example.com", tasks=("scan-crtsh", "notices-hibp"))
        self.assertEqual((self.mutations, self.lock.entries), ([], 0))

    def test_wrong_public_source_preflight_is_rejected_before_writes(self):
        self.notices.status_transform = lambda value: replace(value, source_url="https://other.example")
        with self.assertRaises(ValidationError):
            self.service.run("example.com", tasks=("notices-hibp",))
        self.assertEqual((self.mutations, self.lock.entries), ([], 0))

    def test_wrong_public_result_contract_stops_following_sources(self):
        self.notices.result_transform = lambda value: replace(value, license="unknown")
        with self.assertRaisesRegex(ValidationError, "geçersiz toplama sonucu"):
            self.service.run("example.com", tasks=("notices-hibp",))
        self.assertEqual(len(self.notices.results), 1)
        self.assertFalse(self.lock.active)

    def test_single_partial_source_is_not_complete(self):
        self.discoveries["theharvester"].outcome = "partial"
        result = self.service.run("example.com", tasks=("discover-theharvester",))
        self.assertEqual(result.status, "partial")

    def test_bad_selection_and_limits_fail_before_preflight_or_writes(self):
        options = (
            {"tasks": ()}, {"tasks": ("scan-crtsh", "scan-crtsh")},
            {"tasks": ("unknown",)}, {"tasks": "scan-crtsh"},
            {"tasks": (True,)}, {"tasks": COLLECTION_TASK_IDS + ("ioc-feodo",)},
            {"typos": 1}, {"tasks": ("ioc-feodo",), "typos": True},
            {"finding_limit": True}, {"finding_limit": 0}, {"finding_limit": 51},
            {"stale_after_hours": False}, {"stale_after_hours": 0},
            {"stale_after_hours": 8761},
            {"watch_item_limit": True}, {"watch_item_limit": 0},
            {"watch_item_limit": 501}, {"username_watch_ids": "watch"},
            {"ransomware_watch_ids": ("invalid id",)},
            {"ransomlook_watch_ids": ("watch", "watch")},
        )
        for option in options:
            with self.subTest(option=option), self.assertRaises(ValidationError):
                self.service.run("example.com", **option)
        self.assertEqual(self.analysis.calls, [])
        self.assertEqual(self.lock.entries, 0)
        self.assertEqual(self.mutations, [])

    def test_unknown_domain_and_missing_selected_source_fail_without_mutation(self):
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            self.service.run("unknown.example")
        del self.service.discoveries["theharvester"]
        with self.assertRaisesRegex(ValidationError, "yapılandırılmamış"):
            self.service.run("example.com", tasks=("scan-crtsh", "discover-theharvester"))
        self.assertEqual(self.lock.entries, 0)
        self.assertEqual(self.mutations, [])

    def test_late_selected_preflight_failure_prevents_earlier_work(self):
        self.feeds["certpl"].error = ValidationError("IOC geçmişi bozuk.")
        with self.assertRaisesRegex(ValidationError, "IOC geçmişi"):
            self.service.run("example.com", tasks=COLLECTION_TASK_IDS)
        self.assertEqual(self.lock.entries, 0)
        self.assertEqual(self.mutations, [])
        self.assertEqual(self.jobs.queued, {})

    def test_post_lock_preflight_rechecks_evidence_before_enqueue(self):
        self.analysis.fail_at = 2
        with self.assertRaisesRegex(ValidationError, "kanıt bozuk"):
            self.service.run("example.com")
        self.assertEqual(self.lock.entries, 1)
        self.assertFalse(self.lock.active)
        self.assertEqual(self.mutations, [])

    def test_watch_preflight_failure_prevents_all_base_work(self):
        watches = Mock()
        watches.plan.side_effect = ValidationError("İzleme geri çekilmiş.")
        self.service.watch_collection = watches
        with self.assertRaisesRegex(ValidationError, "geri çekilmiş"):
            self.service.run(
                "example.com", username_watch_ids=("00000000-0000-4000-8000-000000000001",),
            )
        watches.run.assert_not_called()
        self.assertEqual(self.mutations, [])
        self.assertEqual(self.lock.entries, 0)

    def test_selected_watch_is_revalidated_under_same_lock_before_first_write(self):
        watch_id = "00000000-0000-4000-8000-000000000001"
        task = CollectionTask(
            f"username-watch:{watch_id}", "username_watch", "sherlock", "Sherlock izlemesi",
            (CollectionWatchTarget(watch_id, "Örnek", "samplebrand", "username", "exact", ("GitHub",)),),
        )
        observations = []

        def prepare(**options):
            observations.append((self.lock.active, options))
            if self.lock.active:
                raise ValidationError("İzleme tanımı değişti.")
            return (task,)

        watches = Mock()
        watches.plan.side_effect = prepare
        self.service.watch_collection = watches
        with self.assertRaisesRegex(ValidationError, "tanımı değişti"):
            self.service.run("example.com", username_watch_ids=(watch_id,), watch_item_limit=7)
        self.assertEqual([item[0] for item in observations], [False, True])
        self.assertTrue(all(item[1]["username_watch_ids"] == (watch_id,) for item in observations))
        self.assertTrue(all(item[1]["item_limit"] == 7 for item in observations))
        watches.run.assert_not_called()
        self.assertEqual(self.mutations, [])
        self.assertFalse(self.lock.active)

    def test_watch_storage_failure_keeps_finished_base_work_and_releases_lock(self):
        watch_id = "00000000-0000-4000-8000-000000000001"
        task = CollectionTask(
            f"username-watch:{watch_id}", "username_watch", "maigret", "Maigret izlemesi",
            (CollectionWatchTarget(watch_id, "Örnek", "samplebrand", "username", "exact", ("GitHub",)),),
        )
        watches = Mock()
        watches.plan.return_value = (task,)

        def fail(*args, **kwargs):
            self.assertTrue(self.lock.active)
            raise OSError("watch storage unavailable")

        watches.run.side_effect = fail
        self.service.watch_collection = watches
        with self.assertRaisesRegex(OSError, "storage"):
            self.service.run("example.com", username_watch_ids=(watch_id,))
        self.assertEqual(len(self.jobs.results), 2)
        self.assertEqual(len(self.discoveries["crt.sh"].results), 1)
        self.assertEqual(self.lock.entries, 1)
        self.assertFalse(self.lock.active)

    def test_busy_lock_does_not_create_queued_work(self):
        self.lock.busy = True
        with self.assertRaises(WorkerBusyError):
            self.service.run("example.com")
        self.assertEqual(self.jobs.queued, {})
        self.assertEqual(self.mutations, [])

    def test_storage_failure_stops_following_work_and_keeps_completed_source(self):
        self.discoveries["crt.sh"].outcome = OSError("storage unavailable")
        with self.assertRaises(OSError):
            self.service.run("example.com", tasks=COLLECTION_TASK_IDS)
        self.assertEqual(len(self.jobs.results), 2)
        self.assertEqual(self.discoveries["theharvester"].results, [])
        self.assertTrue(all(not feed.results for feed in self.feeds.values()))
        self.assertFalse(self.lock.active)

    def test_interrupt_keeps_finished_steps_and_stops_remaining_sources(self):
        self.jobs.outcomes["urlscan"] = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.service.run("example.com")
        self.assertEqual(len(self.jobs.results), 1)
        self.assertEqual(self.discoveries["crt.sh"].results, [])
        self.assertFalse(self.lock.active)

    def test_wrong_source_or_target_is_rejected_before_misleading_result(self):
        self.discoveries["theharvester"].source.provider = "crt.sh"
        with self.assertRaisesRegex(ValidationError, "görevle uyuşmuyor"):
            self.service.run("example.com", tasks=("discover-theharvester",))
        self.assertEqual(self.mutations, [])
        self.jobs.transform = lambda attempt: replace(
            attempt, result=replace(attempt.result, targets=("other.example",)),
        )
        with self.assertRaisesRegex(ValidationError, "geçersiz toplama sonucu"):
            self.service.run("example.com")
        self.assertEqual(len(self.jobs.results), 1)
        self.assertEqual(self.discoveries["crt.sh"].results, [])

    def test_invalid_and_backward_clocks_never_fabricate_completion(self):
        self.service.clock = lambda: NOW.replace(tzinfo=None)
        with self.assertRaisesRegex(ValidationError, "saat dilimi"):
            self.service.run("example.com")
        self.assertEqual(self.mutations, [])
        ticks = iter((NOW, NOW - timedelta(seconds=1)))
        self.service.clock = lambda: next(ticks)
        with self.assertRaisesRegex(ValidationError, "başlangıçtan önce"):
            self.service.run("example.com")
        self.assertEqual(len(self.jobs.results), 2)
        self.assertFalse(self.lock.active)


if __name__ == "__main__":
    unittest.main()
