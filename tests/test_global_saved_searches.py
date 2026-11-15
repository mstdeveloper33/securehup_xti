"""Stable identities, frozen evidence and effect-free validation of local watches."""

from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from xti.application.global_saved_searches import GlobalSavedSearchService
from xti.application.global_saved_search_monitor import GlobalSavedSearchMonitor
from xti.domain.assets import ValidationError
from xti.domain.engine import reference_for_result
from xti.domain.global_search import GlobalSearchCoverage, GlobalSearchResult
from xti.domain.global_saved_searches import (
    GLOBAL_SEARCH_WATCH_VERSION, GlobalSavedSearch, GlobalSavedSearchSnapshot,
    GlobalSavedSearchRun, canonical_json, definition_json, definition_from_json,
    difference, difference_sha256, make_match, parse_canonical_json,
    snapshot_json, snapshot_from_json, text_sha256, validate_snapshot_scope,
)
from xti.domain.organization_report import ReportNavigation


ID = "11111111-1111-4111-8111-111111111111"
SECOND = "22222222-2222-4222-8222-222222222222"
AT = "2026-11-15T12:00:00+00:00"
LATER = "2026-11-15T13:00:00+00:00"


def search(**changes):
    value = GlobalSavedSearch(ID, "example watch", "Example Watch", "example",
                              ("domain",), False, True, 1, AT, AT)
    return replace(value, **changes)


def result(**changes):
    value = GlobalSearchResult("domain", "registered_domain", ID, "example.com",
                               "domain", "example.com", "prefix", "registered", True,
                               AT, "local-assets", navigation=(ReportNavigation("Domain", ("analyze", "example.com")),))
    return replace(value, **changes)


def identity(values):
    return tuple(value for key in sorted(values) for value in (key, values[key]))


def match(value=None, *, semantic=None):
    value = value or result()
    return make_match(value, identity(reference_for_result(value).to_dict()), semantic or {})


def snapshot(*matches):
    kinds = sorted({item.result.kind for item in matches}) or ["domain"]
    return GlobalSavedSearchSnapshot(tuple(matches), tuple(GlobalSearchCoverage(
        kind, "test", sum(item.result.kind == kind for item in matches),
        sum(item.result.kind == kind for item in matches)) for kind in kinds))


class GlobalSavedSearchEvidenceTests(unittest.TestCase):
    def test_full_definition_retains_historical_query_scope_and_revision(self):
        original = search()
        encoded = definition_json(original)
        self.assertEqual(definition_from_json(encoded), original)
        changed = search(query="other", kinds=("ransomware",), revision=2, updated_at=LATER)
        self.assertNotEqual(definition_json(changed), encoded)
        self.assertEqual(definition_from_json(encoded).query, "example")
        invalid = asdict(original)
        invalid["include_inactive"] = 1
        with self.assertRaises(ValueError):
            definition_from_json(canonical_json({"rule_version": GLOBAL_SEARCH_WATCH_VERSION, "search": invalid}))
        with self.assertRaises(ValueError):
            definition_from_json(encoded.replace(GLOBAL_SEARCH_WATCH_VERSION, "unknown-policy"))

    def test_collection_provenance_changes_do_not_become_semantic_changes(self):
        old = match()
        new = match(result(recorded_at=LATER, source_run_id=SECOND,
                           navigation=(ReportNavigation("Other detail", ("status",)),)))
        self.assertEqual(old.key, new.key)
        self.assertEqual(old.state_sha256, new.state_sha256)
        self.assertNotEqual(snapshot_json(snapshot(old)), snapshot_json(snapshot(new)))
        delta = difference(snapshot(old), snapshot(new))
        self.assertEqual([item.action for item in delta], ["unchanged"])
        self.assertEqual(delta[0].before.result.recorded_at, AT)
        self.assertEqual(delta[0].after.result.recorded_at, LATER)

    def test_sources_with_same_raw_id_remain_separate(self):
        tc = result(kind="ransomware", record_type="ransomware_claim", record_id="a" * 64,
                    source="threatcluster", status="source_claim")
        rl = replace(tc, source="ransomlook")
        before, after = snapshot(match(tc)), snapshot(match(tc), match(rl))
        self.assertEqual({item.action for item in difference(before, after)}, {"unchanged", "added"})
        self.assertNotEqual(match(tc).key, match(rl).key)
        bad_identity = reference_for_result(tc).to_dict()
        bad_identity["namespace"] = "ransomlook"
        with self.assertRaises(ValueError):
            make_match(tc, identity(bad_identity), {})

    def test_social_refresh_retains_logical_profile_and_human_decision_changes_it(self):
        value = result(kind="social", record_type="social_profile", source="Sherlock",
                       status="found_unverified", source_run_id=ID)
        stable = {"kind": "social", "record_type": "social_profile", "namespace": "sherlock",
                  "watch_id": ID, "definition_sha256": "a" * 64, "platform": "Example"}
        state = {"source_key": "sherlock", "watch_id": ID, "definition_sha256": "a" * 64,
                 "platform": "Example", "review": None}
        first = make_match(value, identity(stable), state)
        fresh = make_match(replace(value, record_id=SECOND, source_run_id=SECOND, recorded_at=LATER), identity(stable), state)
        self.assertEqual((first.key, first.state_sha256), (fresh.key, fresh.state_sha256))
        reviewed = make_match(fresh.result, identity(stable), {**state, "review": {"decision": "legitimate", "reason": "Owned profile"}})
        self.assertEqual(difference(snapshot(first), snapshot(reviewed))[0].action, "updated")
        with self.assertRaises(ValueError):
            make_match(value, identity(stable), {**state, "watch_id": SECOND})

    def test_complete_difference_preserves_removed_and_changed_evidence(self):
        a, b = match(), match(result(record_id=SECOND))
        changed = match(result(status="reviewed"))
        items = difference(snapshot(a, b), snapshot(changed))
        self.assertEqual([item.action for item in items], ["updated", "removed"])
        self.assertEqual(items[0].before.result.status, "registered")
        self.assertEqual(items[0].after.result.status, "reviewed")
        self.assertIsNone(items[1].after)
        self.assertEqual(items[1].before.result.record_id, SECOND)
        self.assertNotEqual(difference_sha256(items), difference_sha256(difference(None, snapshot(changed))))
        self.assertEqual(difference(snapshot(), snapshot()), ())

    def test_snapshot_roundtrip_rejects_hidden_tampering_and_incomplete_coverage(self):
        original = snapshot(match())
        encoded = snapshot_json(original)
        self.assertEqual(snapshot_from_json(encoded), original)
        altered = parse_canonical_json(encoded)
        altered["matches"][0]["result"]["status"] = "forged"
        # Even a new enclosing content hash cannot replace the typed semantic state.
        rewritten = canonical_json(altered)
        self.assertNotEqual(text_sha256(rewritten), text_sha256(encoded))
        with self.assertRaises(ValueError):
            snapshot_from_json(rewritten)
        altered = parse_canonical_json(encoded)
        altered["coverage"][0]["matched_count"] = 0
        with self.assertRaises(ValueError):
            snapshot_from_json(canonical_json(altered))
        with self.assertRaises(ValueError):
            snapshot_json(snapshot(match(), match()))
        with patch("xti.domain.global_saved_searches.MAX_WATCH_MATCHES", 0), self.assertRaises(ValueError):
            snapshot_json(original)
        with patch("xti.domain.global_saved_searches.MAX_WATCH_SNAPSHOT_BYTES", 8), self.assertRaises(ValueError):
            snapshot_json(original)

    def test_frozen_results_must_belong_to_the_historical_query_and_scope(self):
        value = snapshot(match())
        validate_snapshot_scope(value, search())
        for definition in (search(query="no match"), search(kinds=("case",))):
            with self.subTest(definition=definition), self.assertRaises(ValueError):
                validate_snapshot_scope(value, definition)
        with self.assertRaises(ValueError):
            validate_snapshot_scope(snapshot(match(result(current=False))), search())
        validate_snapshot_scope(snapshot(match(result(current=False))), search(include_inactive=True))

    def test_noncanonical_duplicate_and_deep_json_fail_closed(self):
        for value in ('{"a":1,"a":2}', '{"a": NaN}', '{ "a":1}', '[' * 1100 + '0' + ']' * 1100):
            with self.subTest(value=value[:30]), self.assertRaises(ValueError):
                parse_canonical_json(value)


class Lock:
    def __init__(self):
        self.held, self.acquisitions = False, 0

    @contextmanager
    def acquire(self):
        if self.held:
            raise AssertionError("Nested writer lock")
        self.held, self.acquisitions = True, self.acquisitions + 1
        try:
            yield
        finally:
            self.held = False


class GlobalSavedSearchServiceTests(unittest.TestCase):
    def setUp(self):
        self.repo, self.lock = Mock(), Lock()
        self.service = GlobalSavedSearchService(self.repo, self.lock,
            clock=lambda: datetime.fromisoformat(AT))

    def test_invalid_queries_ids_windows_and_clocks_have_no_effects(self):
        operations = (
            lambda: self.service.add("ok", "x"), lambda: self.service.add("ok", "query", kinds=["unknown"]),
            lambda: self.service.add("ok", "query", include_inactive=1),
            lambda: self.service.run("not-a-uuid"), lambda: self.service.run(ID, limit=0),
            lambda: self.service.show(ID, event_offset=-1), lambda: self.service.list(active_only=1),
            lambda: self.service.disable(ID, reason="\x1b[31m"),
        )
        for operation in operations:
            with self.assertRaises(ValidationError):
                operation()
        self.assertEqual(self.repo.mock_calls, [])
        self.assertEqual(self.lock.acquisitions, 0)
        self.service.clock = lambda: datetime(2026, 11, 15)
        with self.assertRaises(ValidationError):
            self.service.run(ID)
        self.assertEqual(self.repo.mock_calls, [])
        self.assertEqual(self.lock.acquisitions, 1)
        self.assertFalse(self.lock.held)

    def test_reads_do_not_lock_and_failed_write_releases_lock(self):
        self.service.list()
        self.service.show(ID)
        self.service.show_run(ID)
        self.assertEqual(self.lock.acquisitions, 0)
        def fail(*args, **kwargs):
            self.assertTrue(self.lock.held)
            raise RuntimeError("Controlled failure")
        self.repo.run.side_effect = fail
        with self.assertRaises(RuntimeError):
            self.service.run(ID)
        self.assertFalse(self.lock.held)

    def test_monitor_releases_lock_between_cycles_and_keeps_only_summaries(self):
        self.repo.details.return_value = SimpleNamespace(saved_search=search())
        calls = []
        def run(*args, **kwargs):
            self.assertTrue(self.lock.held)
            calls.append(kwargs)
            value = GlobalSavedSearchRun(len(calls), ID, ID, ID, "a" * 64,
                None if len(calls) == 1 else ID, AT, 1, 1 if len(calls) == 1 else 0,
                0, 0 if len(calls) == 1 else 1, 0, "b" * 64)
            return SimpleNamespace(run=value, notification_id=None, items=(object(),))
        self.repo.run.side_effect = run
        now = [0.0]
        def sleep(seconds):
            self.assertFalse(self.lock.held)
            now[0] += seconds
        monitor = GlobalSavedSearchMonitor(self.service, monotonic=lambda: now[0], sleeper=sleep)
        report = monitor.run(ID, cycles=3, interval_seconds=2, duration_seconds=20)
        self.assertEqual((report.completed_cycles, report.elapsed_seconds, report.stop_reason), (3, 4.0, "cycles"))
        self.assertEqual(self.lock.acquisitions, 3)
        self.assertTrue(all(not hasattr(cycle, "items") for cycle in report.runs))

    def test_monitor_deadline_prevents_next_cycle_and_invalid_clock_fails(self):
        self.repo.details.return_value = SimpleNamespace(saved_search=search())
        run = GlobalSavedSearchRun(1, ID, ID, ID, "a" * 64, None, AT, 0, 0, 0, 0, 0, "b" * 64)
        self.repo.run.return_value = SimpleNamespace(run=run, notification_id=None)
        now = [0.0]
        def sleep(seconds):
            now[0] += seconds
        monitor = GlobalSavedSearchMonitor(self.service, monotonic=lambda: now[0], sleeper=sleep)
        report = monitor.run(ID, cycles=10, interval_seconds=2, duration_seconds=3)
        self.assertEqual((report.completed_cycles, report.stop_reason, report.elapsed_seconds), (2, "duration", 3.0))
        for ticks in ((float("nan"),), (10.0, 9.0)):
            with self.subTest(ticks=ticks), self.assertRaises(ValidationError):
                GlobalSavedSearchMonitor(self.service, monotonic=Mock(side_effect=ticks)).run(ID)
        self.repo.reset_mock()
        with self.assertRaises(ValidationError):
            monitor.run(ID, cycles=True)
        self.assertEqual(self.repo.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
