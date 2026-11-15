"""Offline acceptance examples for conservative cross-source candidate rules."""

from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
import json
import unittest

from xti.domain.assets import ValidationError
from xti.domain.event_candidate_rules import (
    NAME_VARIANT_WINDOW_HOURS,
    candidate_for,
    cosmetic_name_key,
    evidence_for,
    website_domain,
)
from xti.domain.event_candidates import EventSourceSnapshot
from xti.domain.public_notices import PublicNotice, PublicNoticeRun, notice_sha256
from xti.domain.ransomlook_ransomware import (
    RANSOMLOOK_SOURCE_NAME,
    RANSOMLOOK_SOURCE_URL,
    RansomLookClaim,
    RansomLookClaimRun,
    ransomlook_claim_state_sha256,
)
from xti.domain.ransomware_claims import (
    RANSOMWARE_SOURCE_NAME,
    RANSOMWARE_SOURCE_URL,
    RansomwareClaim,
    RansomwareClaimRun,
    ransomware_claim_state_sha256,
)
from xti.domain.ransomware_source_comparison import compare_ransomware_source_claims


DISCOVERED = "2026-11-10T12:00:00+00:00"
FETCHED = "2026-11-14T12:00:00+00:00"
FINISHED = "2026-11-14T12:00:01+00:00"


def _id(group, victim, discovered):
    value = json.dumps([group, victim, discovered], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def tc_claim(victim="Alpha Ltd", *, group="Sample Group", discovered=DISCOVERED,
             website="https://alpha.example/path", **updates):
    value = RansomwareClaim(
        id=_id(group, victim, discovered), group=group, victim=victim,
        country="TR", sector=None, discovered_at=discovered, status="listed",
        website=website, last_seen_at=None, delisted_at=None, first_party=None,
        source_post_available=True,
    )
    return replace(value, **updates)


def rl_claim(victim="Alpha Ltd", *, group="Sample Group", discovered=DISCOVERED):
    return RansomLookClaim(_id(group, victim, discovered), group, victim, discovered)


def notice(*, domain="alpha.example", **updates):
    value = PublicNotice(
        id="Alpha", title="Alpha Ltd", domain=domain, breach_date="2026-11-10",
        added_at=DISCOVERED, modified_at=DISCOVERED, pwn_count=10,
        data_classes=("Email addresses",), is_verified=True, is_fabricated=False,
        is_sensitive=False, is_retired=False, is_spam_list=False, is_malware=False,
        is_stealer_log=False, source_attribution=None,
        source_url="https://haveibeenpwned.com/api/v3/breach/Alpha",
    )
    return replace(value, **updates)


def source(record, *, run_id=None):
    common = dict(
        sequence=1, status="complete", started_at=FETCHED, finished_at=FINISHED,
        fetched_at=FETCHED, content_sha256="a" * 64, added_count=1, updated_count=0,
        unchanged_count=0, removed_count=0, error=None,
    )
    if isinstance(record, RansomwareClaim):
        key = "threatcluster"
        run = RansomwareClaimRun(
            id=run_id or key + "-run", source_name=RANSOMWARE_SOURCE_NAME,
            source_url=RANSOMWARE_SOURCE_URL, generated_at=FETCHED, window_days=7,
            source_record_count=1, claim_count=1, **common,
        )
    elif isinstance(record, RansomLookClaim):
        key = "ransomlook"
        run = RansomLookClaimRun(
            id=run_id or key + "-run", source_name=RANSOMLOOK_SOURCE_NAME,
            source_url=RANSOMLOOK_SOURCE_URL, window_days=7,
            source_record_count=1, claim_count=1, **common,
        )
    else:
        key = "hibp"
        run = PublicNoticeRun(
            id=run_id or key + "-run", snapshot_sha256="b" * 64, notice_count=1, **common,
        )
    return EventSourceSnapshot(key, run, run, (record,))


def evidence(record, *, run_id=None):
    return evidence_for(source(record, run_id=run_id), record)


def pair(tc=None, rl=None):
    return candidate_for(evidence(tc or tc_claim()), evidence(rl or rl_claim()))


class WebsiteDomainTests(unittest.TestCase):
    def test_exact_host_only_without_parent_www_idna_or_psl_expansion(self):
        valid = {
            "EXAMPLE.COM.": "example.com",
            "HTTP://WWW.Example.COM:443/path?q=value#fragment": "www.example.com",
            "https://customer.host.example/path": "customer.host.example",
            "https://xn--exmple-cua.com": "xn--exmple-cua.com",
        }
        for value, expected in valid.items():
            with self.subTest(value=value):
                self.assertEqual(website_domain(value), expected)

    def test_unsafe_local_and_malformed_websites_supply_no_domain_anchor(self):
        values = (
            None, "", 42, " example.com", "example.com ", "https://example.com\n",
            "example.com/path", "example.com:443", "//example.com", "https:example.com",
            "ftp://example.com", "javascript://example.com", "http:///example.com",
            "https://user@example.com", "https://user:pass@example.com",
            "https://example.com@evil.example", "https://example.com\\@evil.example",
            "http://127.0.0.1", "192.168.1.1", "http://[::1]", "http://[broken",
            "https://localhost", "localhost.localdomain", "http://host.internal",
            "http://host.localhost", "http://host.lan", "http://host.home",
            "https://host.home.arpa", "https://test.onion", "test.onion",
            "https://example.com:", "https://example.com:0", "https://example.com:65536",
            "https://example.com:bad", "https://exämple.com", "https://%65xample.com",
            "https://example.com/%ZZ", "https://example.com/a b", "https://exam_ple.com",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertIsNone(website_domain(value))


class EventEvidenceTests(unittest.TestCase):
    def test_source_qualified_identity_original_records_and_existing_state_hashes(self):
        tc, rl, hibp = tc_claim(), rl_claim(), notice()
        self.assertEqual(tc.id, rl.id)  # Real source parsers use the same tuple hash.
        for record, key, record_type, state_hash, url in (
            (tc, "threatcluster", "ransomware_claim", ransomware_claim_state_sha256(tc), RANSOMWARE_SOURCE_URL),
            (rl, "ransomlook", "ransomware_claim", ransomlook_claim_state_sha256(rl), RANSOMLOOK_SOURCE_URL),
            (hibp, "hibp", "public_breach_notice", notice_sha256(hibp), hibp.source_url),
        ):
            with self.subTest(key=key):
                result = evidence(record)
                self.assertIs(result.record, record)
                self.assertEqual((result.source_key, result.record_id), (key, record.id))
                self.assertEqual(result.record_type, record_type)
                self.assertEqual(result.state_sha256, state_hash)
                self.assertEqual(result.source_url, url)
        self.assertIsNone(evidence(rl).domain)

    def test_typed_dates_retain_source_meaning_and_collection_time(self):
        hibp = {value.field: value for value in evidence(notice()).dates}
        tc = {value.field: value for value in evidence(tc_claim(last_seen_at=FETCHED)).dates}
        self.assertEqual(hibp["breach_date"].value, "2026-11-10")
        self.assertEqual(hibp["added_at"].value, DISCOVERED)
        self.assertEqual(hibp["modified_at"].value, DISCOVERED)
        self.assertNotEqual(hibp["breach_date"].meaning, tc["discovered_at"].meaning)
        self.assertNotEqual(hibp["added_at"].meaning, tc["discovered_at"].meaning)
        self.assertEqual(tc["last_seen_at"].value, FETCHED)
        for values in (hibp, tc):
            self.assertEqual(values["fetched_at"].value, FETCHED)
            self.assertEqual(values["finished_at"].value, FINISHED)

    def test_missing_failed_or_incorrect_source_evidence_fails_closed(self):
        record = tc_claim()
        good = source(record)
        invalid = (
            replace(good, successful_run=None),
            replace(good, source_key="other"),
            replace(good, source_key="ransomlook"),
            replace(good, successful_run=replace(good.successful_run, status="failed")),
            replace(good, successful_run=replace(good.successful_run, fetched_at=None)),
            replace(good, successful_run=source(rl_claim()).successful_run),
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    evidence_for(value, record)


class EventCandidateRuleTests(unittest.TestCase):
    def test_legacy_comparison_identity_and_strong_exact_candidate_are_preserved(self):
        tc, rl = tc_claim(), rl_claim()
        legacy = compare_ransomware_source_claims(tc, rl)
        result = pair(tc, rl)
        self.assertEqual(result.kind, "possible_same_event")
        self.assertEqual((result.basis, result.legacy_comparison_id), (legacy.basis, legacy.id))
        self.assertEqual(result.discovery_gap_hours, 0)
        self.assertIsNone(result.legacy_review)
        self.assertIn("bağımsız doğrulama", " ".join(result.cautions))
        self.assertIn("aynı adlı farklı kuruluşlar", " ".join(result.cautions))
        self.assertIn("domain eşitliği doğrulanmadı", " ".join(result.cautions))

    def test_canonical_order_and_pair_identity_include_source_namespace(self):
        tc, rl = evidence(tc_claim()), evidence(rl_claim())
        forward, backward = candidate_for(tc, rl), candidate_for(rl, tc)
        self.assertEqual(forward, backward)
        self.assertEqual(forward.left.source_key, "ransomlook")
        self.assertEqual(forward.right.source_key, "threatcluster")
        self.assertEqual(forward.left.record_id, forward.right.record_id)
        self.assertNotEqual(forward.id, forward.left.record_id)
        self.assertNotEqual(forward.id, forward.legacy_comparison_id)
        self.assertIsNone(candidate_for(tc, tc))

    def test_refresh_keeps_pair_id_and_changes_proof_while_state_hash_stays_stable(self):
        tc, rl = tc_claim(), rl_claim()
        original = pair(tc, rl)
        refreshed = candidate_for(evidence(tc, run_id="new-tc-run"), evidence(rl))
        self.assertEqual(original.id, refreshed.id)
        self.assertNotEqual(original.evidence_sha256, refreshed.evidence_sha256)
        self.assertEqual(original.right.state_sha256, refreshed.right.state_sha256)

    def test_nonidentity_source_updates_change_proof_without_changing_pair_id(self):
        tc = tc_claim()
        original = pair(tc)
        updated = pair(replace(tc, website="other.example", country="GB"))
        self.assertEqual(original.id, updated.id)
        self.assertEqual(original.legacy_comparison_id, updated.legacy_comparison_id)
        self.assertNotEqual(original.evidence_sha256, updated.evidence_sha256)

    def test_same_name_group_old_repeat_is_context_with_explicit_date_conflict(self):
        result = pair(rl=rl_claim(discovered="2024-11-10T12:00:00+00:00"))
        self.assertEqual(result.kind, "organization_context")
        self.assertEqual(result.basis, "organization_group")
        self.assertIsNotNone(result.legacy_comparison_id)
        self.assertIn("72 saati aşıyor", " ".join(result.cautions))
        self.assertIn("ayrı olay", " ".join(result.cautions))

    def test_exact_time_different_groups_is_only_context(self):
        result = pair(rl=rl_claim(group="Another Group"))
        self.assertEqual(result.kind, "organization_context")
        self.assertEqual(result.basis, "organization_time")
        self.assertIn("Grup adları farklı", " ".join(result.cautions))
        self.assertIsNone(pair(rl=rl_claim(group="Another Group", discovered=FETCHED)))

    def test_punctuation_variant_adds_a_pair_without_changing_old_rule_or_review_id(self):
        tc, rl = tc_claim("ALPHA, AŞ"), rl_claim("alpha aş")
        self.assertIsNone(compare_ransomware_source_claims(tc, rl))
        result = pair(tc, rl)
        self.assertEqual(result.kind, "possible_same_event")
        self.assertEqual(result.basis, "organization_name_variant_group_time")
        self.assertIsNone(result.legacy_comparison_id)
        self.assertEqual(cosmetic_name_key("ＡＬＰＨＡ， AŞ"), cosmetic_name_key("alpha aş"))
        self.assertIn("hiçbir sözcük çıkarılmadı", " ".join(result.reasons))

    def test_name_normalization_never_drops_legal_words_or_transliterates(self):
        for first, second in (
            ("Alpha Ltd", "Alpha"), ("Alpha Limited", "Alpha Ltd"),
            ("Alpha AŞ", "Alpha AS"), ("Işık", "Isik"),
            ("İnci", "inci"), ("АО Alpha", "AO Alpha"),
            ("AlphaBeta", "Alpha Beta"), ("Alpha + Co", "Alpha Co"),
        ):
            with self.subTest(first=first, second=second):
                self.assertNotEqual(cosmetic_name_key(first), cosmetic_name_key(second))
                self.assertIsNone(pair(tc_claim(first), rl_claim(second)))
        self.assertIsNone(pair(tc_claim("..."), rl_claim("---")))

    def test_cosmetic_variant_requires_same_group_and_at_most_72_hours(self):
        self.assertEqual(NAME_VARIANT_WINDOW_HOURS, 72)
        tc = tc_claim("Alpha, Ltd")
        at_limit = datetime.fromisoformat(DISCOVERED) + timedelta(hours=72)
        result = pair(tc, rl_claim(discovered=at_limit.isoformat()))
        self.assertEqual(result.discovery_gap_hours, 72)
        self.assertEqual(result.kind, "possible_same_event")
        self.assertIsNone(pair(tc, rl_claim(discovered=(at_limit + timedelta(microseconds=1)).isoformat())))
        self.assertIsNone(pair(tc, rl_claim(group="Other Group")))
        earlier = datetime.fromisoformat(DISCOVERED) - timedelta(hours=72)
        self.assertIsNotNone(pair(tc, rl_claim(discovered=earlier.isoformat())))

    def test_different_named_companies_do_not_match_on_group_time_or_similar_name(self):
        for name in ("Beta Ltd", "Alfa Ltd", "Alpha Ltd Global", "Alpha"):
            with self.subTest(name=name):
                self.assertIsNone(pair(rl=rl_claim(name)))

    def test_exact_domain_only_produces_organization_context_even_with_same_day_name(self):
        tc, hibp = evidence(tc_claim()), evidence(notice())
        result = candidate_for(tc, hibp)
        self.assertEqual(result.kind, "organization_context")
        self.assertEqual(result.basis, "exact_domain_context")
        self.assertIsNone(result.discovery_gap_hours)
        self.assertIsNone(result.legacy_comparison_id)
        self.assertEqual(result.left.source_key, "hibp")
        self.assertIn("aynı anlamda değildir", " ".join(result.cautions))
        self.assertEqual(candidate_for(hibp, tc), result)

    def test_same_name_different_domain_and_parent_or_www_boundary_never_link(self):
        for domain in (
            "other.example", "notalpha.example", "alpha.example.evil.com",
            "www.alpha.example", "sub.alpha.example", "xn--alpha-2nf.example", None,
        ):
            with self.subTest(domain=domain):
                self.assertIsNone(candidate_for(evidence(tc_claim()), evidence(notice(domain=domain))))
        self.assertIsNone(candidate_for(evidence(tc_claim(website="sub.alpha.example")), evidence(notice())))
        self.assertIsNone(candidate_for(evidence(tc_claim(website="https://private.local")), evidence(notice(domain="private.local"))))

    def test_years_apart_domain_context_remains_context_and_dates_are_not_replaced(self):
        old = notice(breach_date="2011-02-03", title="A different event title")
        result = candidate_for(evidence(tc_claim()), evidence(old))
        self.assertEqual(result.kind, "organization_context")
        self.assertIsNone(result.discovery_gap_hours)
        self.assertIn("bir yıldan uzun", " ".join(result.cautions))
        self.assertIn("başlığı farklı", " ".join(result.cautions))
        self.assertEqual(result.left.record.breach_date, "2011-02-03")
        self.assertEqual(result.left.record.added_at, DISCOVERED)

    def test_no_transitive_or_name_only_ransomlook_hibp_candidate(self):
        tc, rl, hibp = evidence(tc_claim()), evidence(rl_claim()), evidence(notice())
        self.assertIsNotNone(candidate_for(tc, rl))
        self.assertIsNotNone(candidate_for(tc, hibp))
        self.assertIsNone(candidate_for(rl, hibp))
        self.assertIsNone(candidate_for(hibp, rl))


if __name__ == "__main__":
    unittest.main()
