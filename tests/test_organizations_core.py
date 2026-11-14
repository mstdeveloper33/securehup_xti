"""Explicit grouping rules and application boundary, without a storage adapter."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock

from xti.application.organizations import OrganizationService
from xti.domain.assets import ValidationError
from xti.domain.organizations import (
    ORGANIZATION_TARGET_KINDS, Organization, OrganizationLink,
    OrganizationLinkView, OrganizationTargetSummary,
    decide_organization_change, decide_organization_link_change,
    normalize_organization_name, normalize_organization_target,
    organization_link_effective,
)
from xti.ports.organizations import OrganizationRepository


ORG_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ID = "22222222-2222-4222-8222-222222222222"
LINK_ID = "33333333-3333-4333-8333-333333333333"
NOW = "2026-11-14T12:00:00+00:00"
ORG = Organization(ORG_ID, "example", "Example", 1, True, NOW, NOW)
TARGET = normalize_organization_target("domain", "example.com")
LINK = OrganizationLink(LINK_ID, ORG_ID, TARGET, 1, True, "Kullanıcı seçimi.", NOW, NOW)


class RecordingLock:
    def __init__(self):
        self.calls = 0
        self.held = False

    @contextmanager
    def acquire(self):
        self.calls += 1
        self.held = True
        try:
            yield
        finally:
            self.held = False


class OrganizationRuleTests(unittest.TestCase):
    def test_only_explicit_supported_target_references_are_accepted(self):
        self.assertEqual(normalize_organization_target("domain", " EXAMPLE.COM. "), TARGET)
        for kind in ORGANIZATION_TARGET_KINDS[1:]:
            self.assertEqual(normalize_organization_target(kind, OTHER_ID).value, OTHER_ID)
        for kind, value in (
            ("person", "Example"), ("domain", "https://example.com"),
            ("username-watch", "example"), ("ransomlook-watch", "example.com"),
        ):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                normalize_organization_target(kind, value)

    def test_names_reject_terminal_controls_and_normalize_identity(self):
        self.assertEqual(normalize_organization_name("  Ｅxample  Group "), ("example group", "Example Group"))
        for value in ("x", "first\nsecond", "escape\x1b[31m", "rtl\u202ename", "a" * 201):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize_organization_name(value)

    def test_organization_lifecycle_requires_explicit_reactivation(self):
        self.assertEqual(decide_organization_change(None, "add", name="Example").action, "added")
        self.assertEqual(decide_organization_change(ORG, "add", name="EXAMPLE").action, "unchanged")
        renamed = decide_organization_change(ORG, "rename", name="Example Group")
        self.assertEqual((renamed.action, renamed.name_key, renamed.active), ("renamed", "example group", True))
        revoked = decide_organization_change(ORG, "revoke")
        self.assertEqual((revoked.action, revoked.active), ("revoked", False))
        inactive = replace(ORG, active=False)
        self.assertEqual(decide_organization_change(inactive, "revoke").action, "unchanged")
        with self.assertRaises(ValidationError):
            decide_organization_change(inactive, "add", name="Example")
        self.assertEqual(decide_organization_change(inactive, "reactivate").action, "reactivated")

    def test_link_lifecycle_keeps_identity_and_allows_revocation_after_target_shutdown(self):
        options = dict(link_requested=True, reason=LINK.reason, organization_active=True, target_active=True)
        self.assertEqual(decide_organization_link_change(None, **options).action, "linked")
        self.assertEqual(decide_organization_link_change(LINK, **options).action, "unchanged")
        self.assertEqual(decide_organization_link_change(LINK, **{**options, "reason": "Yeni kullanıcı gerekçesi."}).action, "updated")
        self.assertEqual(decide_organization_link_change(replace(LINK, active=False), **options).action, "reactivated")
        for key in ("organization_active", "target_active"):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                decide_organization_link_change(LINK, **{**options, key: False})
        revoked = decide_organization_link_change(LINK, **{
            **options, "link_requested": False, "organization_active": False, "target_active": False,
        })
        self.assertEqual((revoked.action, revoked.active), ("revoked", False))

    def test_effective_link_requires_three_active_states_and_exact_identity(self):
        summary = OrganizationTargetSummary(TARGET, "example.com", "asset", True)
        view = OrganizationLinkView(LINK, summary)
        self.assertTrue(organization_link_effective(ORG, view))
        self.assertFalse(organization_link_effective(replace(ORG, active=False), view))
        self.assertFalse(organization_link_effective(ORG, replace(view, link=replace(LINK, active=False))))
        self.assertFalse(organization_link_effective(ORG, replace(view, target=replace(summary, active=False))))
        with self.assertRaises(ValidationError):
            organization_link_effective(replace(ORG, id=OTHER_ID), view)
        with self.assertRaises(ValidationError):
            organization_link_effective(ORG, replace(view, target=replace(
                summary, reference=normalize_organization_target("domain", "other.example"),
            )))


class OrganizationServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=OrganizationRepository)
        self.lock = RecordingLock()
        self.service = OrganizationService(self.repository, self.lock, clock=lambda: datetime(
            2026, 11, 14, 15, tzinfo=timezone(timedelta(hours=3)),
        ))

    def test_every_mutation_holds_shared_lock_and_passes_canonical_utc(self):
        def mutation(*args, **kwargs):
            self.assertTrue(self.lock.held)
            self.assertEqual(kwargs["recorded_at"], NOW)
            return "accepted"
        for name in ("add", "rename", "revoke", "reactivate", "link", "unlink"):
            getattr(self.repository, name).side_effect = mutation
        self.service.add("Example", reason=LINK.reason)
        self.service.rename(ORG_ID, "Example Group", reason=LINK.reason)
        self.service.revoke(ORG_ID, reason=LINK.reason)
        self.service.reactivate(ORG_ID, reason=LINK.reason)
        self.service.link(ORG_ID, kind="domain", value="EXAMPLE.COM.", reason=LINK.reason)
        self.service.unlink(ORG_ID, LINK_ID, reason=LINK.reason)
        self.assertEqual(self.repository.link.call_args.args, (ORG_ID, TARGET))
        self.assertEqual(self.lock.calls, 6)
        self.assertFalse(self.lock.held)

    def test_invalid_input_never_reaches_repository_or_lock(self):
        for operation in (
            lambda: self.service.add("a\nb", reason=LINK.reason),
            lambda: self.service.rename("not-id", "Example", reason=LINK.reason),
            lambda: self.service.link(ORG_ID, kind="username-watch", value="username", reason=LINK.reason),
            lambda: self.service.unlink(ORG_ID, "not-id", reason=LINK.reason),
            lambda: self.service.revoke(ORG_ID, reason="x"),
            lambda: self.service.list(active_only=1),
            lambda: self.service.show(ORG_ID, link_offset=True),
            lambda: self.service.show_link(ORG_ID, LINK_ID, event_limit=0),
        ):
            with self.assertRaises(ValidationError):
                operation()
        self.assertEqual(self.repository.method_calls, [])
        self.assertEqual(self.lock.calls, 0)

    def test_atomic_repository_rejection_propagates_and_releases_lock(self):
        self.repository.link.side_effect = ValidationError("Hedef kayıt geri çekilmiş.")
        with self.assertRaisesRegex(ValidationError, "geri çekilmiş"):
            self.service.link(ORG_ID, kind="domain", value="example.com", reason=LINK.reason)
        self.assertFalse(self.lock.held)
        self.assertEqual(len(self.repository.method_calls), 1)

    def test_timestamp_is_sampled_after_waiting_for_shared_lock(self):
        def clock():
            self.assertTrue(self.lock.held)
            return datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
        self.service.clock = clock
        self.service.add("Example", reason=LINK.reason)
        self.assertEqual(self.repository.add.call_args.kwargs["recorded_at"], NOW)

    def test_reads_support_paging_and_never_acquire_execution_lock(self):
        self.service.list(active_only=False, offset=500, limit=500)
        self.service.show(ORG_ID, link_offset=100, link_limit=100, event_limit=10)
        self.service.show_link(ORG_ID, LINK_ID, event_limit=20)
        self.repository.list.assert_called_once_with(active_only=False, offset=500, limit=500)
        self.assertEqual(self.lock.calls, 0)


if __name__ == "__main__":
    unittest.main()
