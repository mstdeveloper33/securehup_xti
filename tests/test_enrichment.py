"""Bounded checks, retained decisions and explainable review ordering."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from xti.application.enrichment import FindingEnrichmentService, ReviewQueueService
from xti.domain.assets import ValidationError
from xti.domain.enrichment import Assessment, EnrichedFinding, ProbeResult
from xti.domain.findings import Finding, FindingDetails, Review
from xti.domain.priority import CHECK_MAX_AGE, assess_priority, evidence_freshness


NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def finding(identifier="one", *, domain="example-login.net", asset="example.com", status="new", age=10):
    return Finding(
        id=identifier, asset_id="asset-" + asset, asset_value=asset, domain=domain,
        rule_version="domain-rules-v1", reasons=("İzlenen ada ek sözcük eklenmiş.",),
        status=status, created_at=(NOW - timedelta(days=age)).isoformat(),
        last_seen_at=NOW.isoformat(),
    )


def result(domain="example-login.net", *, at=NOW, **changes):
    return replace(ProbeResult(
        domain=domain, started_at=(at - timedelta(seconds=1)).isoformat(),
        finished_at=at.isoformat(), policy_version="target-probe-v1",
        dns_status="resolved", addresses=("93.184.215.14",), tls_status="valid",
        http_status="responded", http_status_code=200, connected_address="93.184.215.14",
        errors=(), notes=(),
    ), **changes)


def assessment(record=None, identifier="one"):
    return Assessment("check-" + identifier, identifier, record or result())


class MemoryFindings:
    def __init__(self, records):
        self.records = {record.id: FindingDetails(record, (), ()) for record in records}

    def list_findings(self, status=None):
        return [details.finding for details in self.records.values() if status is None or details.finding.status == status]

    def get_finding(self, finding_id):
        if finding_id not in self.records:
            raise ValidationError("Bulgu bulunamadı.")
        return self.records[finding_id]


class MemoryAssessments:
    def __init__(self, findings, records=()):
        self.findings = findings
        self.records = list(records)
        self.append_count = 0
        self.fail_after = None

    def append(self, finding_id, record):
        if self.fail_after is not None and self.append_count >= self.fail_after:
            raise RuntimeError("Kayıt alanı kullanılamıyor.")
        self.append_count += 1
        saved = Assessment("saved-" + str(self.append_count), finding_id, record)
        self.records.append(saved)
        return saved

    def list(self, finding_id):
        return tuple(record for record in self.records if record.finding_id == finding_id)

    def latest_by_finding(self):
        return {record.finding_id: record for record in self.records}

    def details(self, finding_id):
        return EnrichedFinding(self.findings.get_finding(finding_id), self.list(finding_id))


class FakeProbe:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def check(self, domain):
        self.calls.append(domain)
        response = self.responses.get(domain, result(domain))
        if isinstance(response, BaseException):
            raise response
        return response


class PriorityTests(unittest.TestCase):
    def test_no_check_keeps_candidate_for_review_with_unknown_access(self):
        priority = assess_priority(finding(), None, now=NOW)
        self.assertEqual((priority.level, priority.freshness), ("review", "unchecked"))
        self.assertTrue(any("bilinmiyor" in reason for reason in priority.reasons))
        self.assertEqual(priority.calculated_at, NOW.isoformat())
        self.assertTrue(priority.rule_version)

    def test_valid_web_response_advances_review_without_verdict(self):
        for code in (200, 301, 403, 404, 405, 500):
            with self.subTest(code=code):
                priority = assess_priority(finding(), assessment(result(http_status_code=code)), now=NOW)
                self.assertEqual((priority.level, priority.freshness), ("soon", "current"))
                self.assertTrue(any(f"HTTP {code}" in reason for reason in priority.reasons))
                self.assertTrue(any("phishing doğrulaması" in reason for reason in priority.reasons))

    def test_tls_or_dns_alone_is_not_a_verified_web_response(self):
        for changes in (
            {"http_status": "failed", "http_status_code": None},
            {"tls_status": "failed"}, {"dns_status": "failed"},
            {"http_status_code": True}, {"http_status_code": 999},
            {"domain": "other.net"},
        ):
            with self.subTest(changes=changes):
                priority = assess_priority(finding(), assessment(result(**changes)), now=NOW)
                self.assertEqual(priority.level, "review")

    def test_no_address_failures_and_blocked_network_never_close_finding(self):
        for state in ("no_address", "nxdomain", "failed", "blocked"):
            candidate = finding(status="uncertain")
            priority = assess_priority(candidate, assessment(result(
                dns_status=state, addresses=(), tls_status="not_checked", http_status="not_checked",
                http_status_code=None, connected_address=None, errors=("Kontrol tamamlanamadı.",),
            )), now=NOW)
            self.assertEqual((priority.level, priority.freshness), ("review", "current"))
            self.assertEqual(candidate.status, "uncertain")

    def test_suspicious_human_decision_stays_first_with_stale_failed_check(self):
        priority = assess_priority(finding(status="suspicious"), assessment(result(
            at=NOW - timedelta(days=2), http_status="failed", http_status_code=None,
        )), now=NOW)
        self.assertEqual((priority.level, priority.freshness), ("soon", "stale"))
        self.assertTrue(any("kullanıcı tarafından" in reason for reason in priority.reasons))

    def test_dismissed_decision_stays_archived_even_if_response_is_current(self):
        candidate = finding(status="dismissed")
        priority = assess_priority(candidate, assessment(), now=NOW)
        self.assertEqual((priority.level, priority.freshness), ("archived", "current"))
        self.assertEqual(candidate.status, "dismissed")

    def test_old_reachable_result_is_not_current_after_six_hours(self):
        saved = assessment(result(at=NOW - CHECK_MAX_AGE))
        self.assertEqual(evidence_freshness(saved, now=NOW), "stale")
        self.assertEqual(assess_priority(finding(), saved, now=NOW).level, "review")
        almost = assessment(result(at=NOW - CHECK_MAX_AGE + timedelta(microseconds=1)))
        self.assertEqual(evidence_freshness(almost, now=NOW), "current")

    def test_malformed_naive_future_and_reversed_times_are_unknown(self):
        for changes in (
            {"finished_at": "invalid"}, {"started_at": "invalid"},
            {"finished_at": "2026-10-28T12:00:00"},
            {"finished_at": "2026-10-28T12:00:01+00:00"},
            {"started_at": "2026-10-28T12:00:01+00:00"},
        ):
            with self.subTest(changes=changes):
                saved = assessment(result(**changes))
                priority = assess_priority(finding(), saved, now=NOW)
                self.assertEqual((priority.level, priority.freshness), ("review", "clock_error"))
        self.assertEqual(evidence_freshness(assessment(), now=NOW.replace(tzinfo=None)), "clock_error")

    def test_explicit_time_zone_offsets_compare_as_the_same_instant(self):
        saved = assessment(result(
            started_at="2026-10-28T14:59:59+03:00", finished_at="2026-10-28T15:00:00+03:00",
        ))
        self.assertEqual(evidence_freshness(saved, now=NOW), "current")


class EnrichmentServiceTests(unittest.TestCase):
    def setUp(self):
        self.findings = MemoryFindings([finding()])
        self.assessments = MemoryAssessments(self.findings)
        self.probe = FakeProbe()
        self.service = FindingEnrichmentService(self.findings, self.assessments, self.probe, lambda: NOW)

    def test_explicit_refresh_appends_even_when_previous_check_is_current(self):
        first = self.service.check("one")
        second = self.service.check("one")
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(self.assessments.list("one"), (first, second))
        self.assertEqual(self.probe.calls, ["example-login.net"] * 2)

    def test_explicit_refresh_preserves_dismissed_status_and_review_history(self):
        review = Review("review", "one", "dismissed", "Meşru alan adı.", NOW.isoformat())
        before = FindingDetails(finding(status="dismissed"), (), (review,))
        self.findings.records["one"] = before
        self.service.check("one")
        self.assertEqual(self.findings.get_finding("one"), before)

    def test_current_attempt_is_reused_without_network(self):
        self.assessments.records.append(assessment())
        batch = self.service.check_pending()
        self.assertEqual((batch.assessments, batch.skipped_fresh, batch.remaining), ((), 1, 0))
        self.assertEqual(self.probe.calls, [])
        self.assertEqual(self.assessments.append_count, 0)

    def test_recent_failure_also_prevents_repeated_automatic_requests(self):
        self.assessments.records.append(assessment(result(
            dns_status="failed", addresses=(), tls_status="not_checked", http_status="not_checked",
            http_status_code=None, connected_address=None, errors=("DNS isteği zaman aşımına uğradı.",),
        )))
        self.assertEqual(self.service.check_pending().skipped_fresh, 1)
        self.assertEqual(self.probe.calls, [])
        self.assertEqual(self.service.check("one").result.http_status, "responded")
        self.assertEqual(len(self.probe.calls), 1)

    def test_latest_inserted_attempt_controls_freshness_not_maximum_timestamp(self):
        self.assessments.records.extend([
            assessment(), assessment(result(at=NOW - timedelta(days=1))),
        ])
        batch = self.service.check_pending()
        self.assertEqual((len(batch.assessments), batch.skipped_fresh), (1, 0))

    def test_old_unchecked_findings_then_oldest_stale_checks_are_selected(self):
        self.findings.records = MemoryFindings([
            finding("stale-recent", domain="example-recent.net", age=30),
            finding("unchecked-new", domain="example-new.net", age=2),
            finding("stale-old", domain="example-old.net", age=1),
            finding("unchecked-old", domain="example-first.net", age=10),
        ]).records
        self.assessments.records.extend([
            assessment(result("example-recent.net", at=NOW - timedelta(hours=7)), "stale-recent"),
            assessment(result("example-old.net", at=NOW - timedelta(days=1)), "stale-old"),
        ])
        batch = self.service.check_pending(limit=3)
        self.assertEqual([item.finding_id for item in batch.assessments], ["unchecked-old", "unchecked-new", "stale-old"])
        self.assertEqual(batch.remaining, 1)

    def test_bad_or_future_check_time_does_not_suppress_a_refresh(self):
        for changes in ({"finished_at": "broken"}, {"finished_at": (NOW + timedelta(days=1)).isoformat()}):
            with self.subTest(changes=changes):
                self.assessments.records = [assessment(result(**changes))]
                self.assertEqual(len(self.service.check_pending().assessments), 1)
        self.assertEqual(len(self.probe.calls), 2)

    def test_batch_ignores_dismissed_and_uses_exact_normalized_asset_selection(self):
        self.findings.records = MemoryFindings([
            finding(), finding("closed", domain="example-closed.net", status="dismissed"),
            finding("other", domain="other-login.net", asset="other.com"),
            finding("sub", domain="example-sub.net", asset="sub.example.com"),
        ]).records
        batch = self.service.check_pending(domains=["EXAMPLE.COM."])
        self.assertEqual([item.finding_id for item in batch.assessments], ["one"])
        self.assertEqual(self.probe.calls, ["example-login.net"])
        self.assertEqual(batch.remaining, 0)

    def test_no_matching_candidates_does_not_contact_a_target(self):
        batch = self.service.check_pending(domains=["absent.com"])
        self.assertEqual((batch.assessments, batch.skipped_fresh, batch.remaining), ((), 0, 0))
        self.assertEqual(self.probe.calls, [])

    def test_shared_candidate_domain_is_contacted_once_with_separate_assessments(self):
        self.findings.records = MemoryFindings([
            finding("first"), finding("second", asset="other.com"),
        ]).records
        progress = []
        batch = self.service.check_pending(progress=progress.append)
        self.assertEqual(self.probe.calls, ["example-login.net"])
        self.assertEqual([item.finding_id for item in batch.assessments], ["first", "second"])
        self.assertEqual(batch.assessments[0].result, batch.assessments[1].result)
        self.assertNotEqual(batch.assessments[0].id, batch.assessments[1].id)
        self.assertEqual(progress, ["Hedef kontrol ediliyor: example-login.net"])

    def test_invalid_limits_domains_and_ids_fail_before_network_or_writes(self):
        for limit in (0, 21, True, "1", 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                self.service.check_pending(limit=limit)
        for domains in ([], ["example.com"] * 6, "example.com", ["https://example.com"], [None], ["xn--example.com"]):
            with self.subTest(domains=domains), self.assertRaises(ValidationError):
                self.service.check_pending(domains=domains)
        for identifier in ("", None, 123, "x" * 65, "id\x1b", "missing"):
            with self.subTest(identifier=identifier), self.assertRaises(ValidationError):
                self.service.check(identifier)
        self.assertEqual(self.probe.calls, [])
        self.assertEqual(self.assessments.records, [])

    def test_probe_domain_mismatch_or_wrong_return_type_is_never_recorded(self):
        for response in (result("unrelated.net"), None):
            self.probe.responses["example-login.net"] = response
            with self.assertRaises(ValidationError):
                self.service.check("one")
        self.assertEqual(self.assessments.records, [])

    def test_probe_error_or_interrupt_keeps_completed_records_and_stops_batch(self):
        self.findings.records = MemoryFindings([
            finding("first", domain="example-first.net"),
            finding("second", domain="example-second.net"),
            finding("third", domain="example-third.net"),
        ]).records
        for error in (RuntimeError("Beklenmedik hata."), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                self.assessments.records = []
                self.probe.calls = []
                self.probe.responses["example-second.net"] = error
                with self.assertRaises(type(error)):
                    self.service.check_pending()
                self.assertEqual([item.finding_id for item in self.assessments.records], ["first"])
                self.assertEqual(self.probe.calls, ["example-first.net", "example-second.net"])

    def test_storage_error_keeps_completed_records_and_no_later_requests(self):
        self.findings.records = MemoryFindings([
            finding("first", domain="example-first.net"),
            finding("second", domain="example-second.net"),
            finding("third", domain="example-third.net"),
        ]).records
        self.assessments.fail_after = 1
        with self.assertRaises(RuntimeError):
            self.service.check_pending()
        self.assertEqual([item.finding_id for item in self.assessments.records], ["first"])
        self.assertEqual(self.probe.calls, ["example-first.net", "example-second.net"])


class ReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.findings = MemoryFindings([
            finding("closed", status="dismissed", age=30),
            finding("fresh", domain="example-fresh.net", age=1),
            finding("old", domain="example-old.net", age=10),
            finding("human", status="suspicious", domain="example-human.net", age=2),
        ])
        self.assessments = MemoryAssessments(self.findings, [assessment(result("example-fresh.net"), "fresh")])
        self.queue = ReviewQueueService(self.findings, self.assessments, lambda: NOW)

    def test_queue_prioritizes_human_and_recent_response_then_old_candidates(self):
        items = self.queue.list()
        self.assertEqual([item.finding.id for item in items], ["human", "fresh", "old"])
        self.assertEqual([item.priority.level for item in items], ["soon", "soon", "review"])
        self.assertEqual(len(self.assessments.records), 1)
        self.assertEqual(self.assessments.append_count, 0)

    def test_closed_items_are_explicitly_optional_and_last(self):
        items = self.queue.list(include_dismissed=True)
        self.assertEqual(items[-1].finding.id, "closed")
        self.assertEqual(items[-1].priority.level, "archived")
        self.assertEqual(len(self.queue.list(limit=1)), 1)

    def test_age_is_recomputed_when_queue_is_read_without_mutating_evidence(self):
        later = ReviewQueueService(self.findings, self.assessments, lambda: NOW + CHECK_MAX_AGE)
        items = later.list()
        self.assertEqual([item.finding.id for item in items], ["human", "old", "fresh"])
        self.assertEqual(items[-1].priority.freshness, "stale")
        self.assertEqual(len(self.assessments.records), 1)
        self.assertEqual(self.assessments.append_count, 0)

    def test_show_returns_all_saved_checks_and_decisions_without_writes(self):
        self.assessments.records.append(assessment(result("example-fresh.net", at=NOW - timedelta(days=1)), "fresh"))
        shown = self.queue.show("fresh")
        self.assertEqual(shown.assessments, tuple(self.assessments.records))
        self.assertEqual(shown.details, self.findings.get_finding("fresh"))
        self.assertEqual(self.assessments.append_count, 0)

    def test_same_creation_time_orders_deterministically_by_id(self):
        self.findings.records = MemoryFindings([finding("z"), finding("b"), finding("a")]).records
        self.assertEqual([item.finding.id for item in self.queue.list()], ["a", "b", "z"])

    def test_invalid_queue_arguments_and_missing_details_raise_validation(self):
        for limit in (0, 501, False, "5", 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                self.queue.list(limit=limit)
        with self.assertRaises(ValidationError):
            self.queue.list(include_dismissed="yes")
        for identifier in ("", None, "missing", "id\n"):
            with self.subTest(identifier=identifier), self.assertRaises(ValidationError):
                self.queue.show(identifier)
        self.assertEqual(self.assessments.append_count, 0)


if __name__ == "__main__":
    unittest.main()
