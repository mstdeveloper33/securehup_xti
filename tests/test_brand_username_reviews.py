"""Exact-state, append-only social profile decision tests."""

from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.maigret_username import INTEGRATION_PROFILE
from xti.adapters.sherlock_username import (
    INTEGRATION_PROFILE as SHERLOCK_INTEGRATION_PROFILE,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_reviews import (
    SQLiteBrandUsernameReviewRepository,
)
from xti.adapters.sqlite_brand_username_watches import (
    SQLiteBrandUsernameWatchRepository,
)
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.application.brand_username_reviews import BrandUsernameReviewService
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.domain.assets import ValidationError
from xti.domain.brand_username import BrandProfileMatch, BrandUsernamePreview
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


class FakeSource:
    source_name = "Maigret"
    source_version = "0.6.6"
    integration_profile = INTEGRATION_PROFILE

    def __init__(self, *responses):
        self.responses = list(responses)

    def preview(self, username, *, platforms, request_timeout):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        matches = tuple(
            BrandProfileMatch(platform, url, "found_unverified")
            for platform, url in response.items()
        )
        return BrandUsernamePreview(
            username=username,
            source=self.source_name,
            source_version=self.source_version,
            integration_profile=self.integration_profile,
            checked_at=NOW.isoformat(),
            requested_platforms=platforms,
            matches=matches,
            unreported_platforms=tuple(
                platform for platform in platforms if platform not in response
            ),
            notes=("Sahiplik kanıtı değildir.",),
        )


class FakeSherlockSource(FakeSource):
    source_name = "Sherlock"
    source_version = "0.16.2"
    integration_profile = SHERLOCK_INTEGRATION_PROFILE


def github(username="samplebrand", *, alternate=False):
    host = "www.github.com" if alternate else "github.com"
    suffix = "/" if alternate else ""
    return f"https://{host}/{username}{suffix}"


class BrandUsernameReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.watch_repository = SQLiteBrandUsernameWatchRepository(self.path)
        self.review_repository = SQLiteBrandUsernameReviewRepository(self.path)

    def watch_service(self, source):
        return BrandUsernameWatchService(
            self.watch_repository,
            source,
            clock=lambda: NOW + timedelta(minutes=10),
        )

    def review_service(self, minute=20):
        return BrandUsernameReviewService(
            self.review_repository,
            clock=lambda: NOW + timedelta(minutes=minute),
        )

    def create_found(self, *responses):
        service = self.watch_service(FakeSource(*responses))
        watch = service.add(
            "Örnek Marka", "samplebrand", platforms=("GitHub", "Reddit"),
        ).watch
        report = service.run(watch.id)
        return service, watch, report

    def test_decision_is_decorated_idempotent_and_append_only(self):
        _, watch, report = self.create_found({"GitHub": github()})
        reviews = self.review_service()
        first = reviews.decide(
            watch.id,
            "GitHub",
            decision="known_official",
            reason="Kuruluşun resmî sitesinden bağlantı veriliyor",
        )
        self.assertEqual(first.action, "recorded")
        self.assertEqual(first.details.candidate.profile_url, github())
        self.assertEqual(first.details.total_event_count, 1)

        unchanged = reviews.decide(
            watch.id,
            "GitHub",
            decision="known_official",
            reason="Kuruluşun resmî sitesinden bağlantı veriliyor",
        )
        self.assertEqual(unchanged.action, "unchanged")
        updated = self.review_service(30).decide(
            watch.id,
            "GitHub",
            decision="uncertain",
            reason="Resmî bağlantı kaldırılmış; yeniden doğrulanmalı",
        )
        self.assertEqual((updated.action, updated.details.total_event_count), ("updated", 2))
        decorated = reviews.decorate(report)
        github_item = next(item for item in decorated.items if item.platform == "GitHub")
        self.assertEqual(github_item.current_review.decision, "uncertain")
        self.assertIsNone(next(
            item for item in decorated.items if item.platform == "Reddit"
        ).current_review)
        inspection = SQLiteAssetRepository(self.path).inspect()
        self.assertEqual(
            (
                inspection["brand_username_review_candidate_count"],
                inspection["brand_username_review_event_count"],
            ),
            (1, 2),
        )

    def test_sherlock_profile_can_receive_the_same_exact_state_review(self):
        service = self.watch_service(FakeSherlockSource({
            "Carrd": "https://samplebrand.carrd.co/",
        }))
        watch = service.add(
            "Sherlock marka", "samplebrand", platforms=("Carrd",),
            source_key="sherlock",
        ).watch
        report = service.run(watch.id)

        decision = self.review_service().decide(
            watch.id,
            "Carrd",
            decision="uncertain",
            reason="Açık profil bulundu; marka sahipliği henüz doğrulanmadı.",
        )
        decorated = self.review_service().decorate(report)

        self.assertEqual(decision.details.candidate.platform, "Carrd")
        self.assertEqual(decorated.items[0].current_review.decision, "uncertain")

    def test_changed_profile_address_gets_new_unreviewed_candidate(self):
        service, watch, old_report = self.create_found(
            {"GitHub": github()},
            {"GitHub": github(alternate=True)},
        )
        reviews = self.review_service()
        old = reviews.decide(
            watch.id,
            "GitHub",
            decision="known_official",
            reason="Eski adres kuruluş tarafından doğrulandı",
        )
        new_report = service.run(watch.id)
        decorated = reviews.decorate(new_report)
        item = next(value for value in decorated.items if value.platform == "GitHub")
        self.assertEqual(item.action, "changed")
        self.assertIsNone(item.current_review)
        current = self.review_repository.current_candidate(watch.id, "GitHub")
        self.assertNotEqual(current.id, old.details.candidate.id)
        self.assertEqual(current.profile_url, github(alternate=True))
        old_decorated = reviews.decorate(old_report)
        self.assertEqual(
            next(value for value in old_decorated.items if value.platform == "GitHub")
            .current_review.decision,
            "known_official",
        )

    def test_failure_does_not_erase_candidate_but_unreported_and_new_definition_block(self):
        service, watch, _ = self.create_found(
            {"GitHub": github()},
            SourceError("geçici hata"),
            {},
        )
        failed = service.run(watch.id)
        self.assertEqual(failed.run.status, "failed")
        recorded = self.review_service().decide(
            watch.id,
            "GitHub",
            decision="uncertain",
            reason="Kaynak hatasından önceki son başarılı profildir",
        )
        self.assertEqual(recorded.action, "recorded")
        service.run(watch.id)
        with self.assertRaisesRegex(ValidationError, "raporlanmadı"):
            self.review_service().decide(
                watch.id, "GitHub", decision="uncertain", reason="Kontrol gerekli",
            )
        service.add("Örnek Marka", "otherbrand", platforms=("GitHub",))
        with self.assertRaisesRegex(ValidationError, "başarılı çalışma yok"):
            self.review_service().decide(
                watch.id, "GitHub", decision="uncertain", reason="Kontrol gerekli",
            )

    def test_corrupt_frozen_evidence_fails_closed(self):
        _, watch, _ = self.create_found({"GitHub": github()})
        mutation = self.review_service().decide(
            watch.id,
            "GitHub",
            decision="possible_impersonation",
            reason="Kuruluş bu profili tanımadığını bildirdi",
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE brand_username_review_events SET candidate_json='{}' "
                "WHERE candidate_id=?",
                (mutation.details.candidate.id,),
            )
        with self.assertRaises(StorageError):
            self.review_service().show(mutation.details.candidate.id)

    def test_possible_impersonation_creates_one_historical_inbox_notice(self):
        _, watch, _ = self.create_found({"GitHub": github()})
        reviews = self.review_service()
        uncertain = reviews.decide(
            watch.id,
            "GitHub",
            decision="uncertain",
            reason="İlk incelemede yeterli bağ bulunamadı",
        )
        self.assertIsNone(uncertain.notification_id)
        self.assertFalse(uncertain.notification_created)
        self.assertEqual(SQLiteInboxRepository(self.path).list().total_count, 0)

        possible = self.review_service(30).decide(
            watch.id,
            "GitHub",
            decision="possible_impersonation",
            reason="Marka bu profili tanımadığını bildirdi",
        )
        self.assertTrue(possible.notification_created)
        self.assertIsNotNone(possible.notification_id)
        page = SQLiteInboxRepository(self.path).list()
        self.assertEqual((page.total_count, page.unread_count), (1, 1))
        inspection = SQLiteAssetRepository(self.path).inspect()
        self.assertEqual(
            (
                inspection["notification_count"],
                inspection["unread_notification_count"],
                inspection["brand_username_review_notification_count"],
            ),
            (1, 1, 1),
        )
        evidence = page.items[0].brand_profile_review
        self.assertEqual(evidence.trigger.reason, "Marka bu profili tanımadığını bildirdi")
        self.assertEqual(evidence.current.decision, "possible_impersonation")

        repeated = self.review_service(40).decide(
            watch.id,
            "GitHub",
            decision="possible_impersonation",
            reason="Marka bu profili tanımadığını bildirdi",
        )
        self.assertEqual(repeated.action, "unchanged")
        self.assertFalse(repeated.notification_created)
        self.assertEqual(repeated.notification_id, possible.notification_id)

        official = self.review_service(50).decide(
            watch.id,
            "GitHub",
            decision="known_official",
            reason="Marka daha sonra resmî bağlantıyı doğruladı",
        )
        self.assertEqual(official.notification_id, possible.notification_id)
        self.assertFalse(official.notification_created)
        details = SQLiteInboxRepository(self.path).get(possible.notification_id)
        self.assertEqual(details.brand_profile_review.trigger.decision, "possible_impersonation")
        self.assertEqual(details.brand_profile_review.current.decision, "known_official")
        self.assertEqual(SQLiteInboxRepository(self.path).list().total_count, 1)
        marked = SQLiteInboxRepository(self.path).mark(
            (possible.notification_id,), True,
            (NOW + timedelta(minutes=60)).isoformat(),
        )
        self.assertEqual(marked.changed_count, 1)
        self.assertEqual(SQLiteInboxRepository(self.path).list().unread_count, 0)
        self.assertEqual(
            reviews.show(possible.details.candidate.id).current.decision,
            "known_official",
        )

    def test_changed_profile_can_create_a_distinct_notice(self):
        service, watch, _ = self.create_found(
            {"GitHub": github()},
            {"GitHub": github(alternate=True)},
        )
        first = self.review_service().decide(
            watch.id,
            "GitHub",
            decision="possible_impersonation",
            reason="İlk profil marka tarafından tanınmıyor",
        )
        service.run(watch.id)
        second = self.review_service(30).decide(
            watch.id,
            "GitHub",
            decision="possible_impersonation",
            reason="Yeni profil adresi de marka tarafından tanınmıyor",
        )
        self.assertNotEqual(first.notification_id, second.notification_id)
        page = SQLiteInboxRepository(self.path).list()
        self.assertEqual((page.total_count, page.unread_count), (2, 2))

    def test_notification_failure_rolls_back_review_event(self):
        _, watch, _ = self.create_found({"GitHub": github()})
        with patch(
            "xti.adapters.sqlite_brand_username_reviews.next_notification_sequence",
            side_effect=StorageError("controlled notification failure"),
        ):
            with self.assertRaises(StorageError):
                self.review_service().decide(
                    watch.id,
                    "GitHub",
                    decision="possible_impersonation",
                    reason="Bildirimle atomik yazılmalı",
                )
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM brand_username_review_events"
            ).fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM brand_username_review_notifications"
            ).fetchone()[0], 0)

    def test_notification_rejects_a_non_impersonation_trigger_event(self):
        _, watch, _ = self.create_found({"GitHub": github()})
        official = self.review_service().decide(
            watch.id,
            "GitHub",
            decision="known_official",
            reason="Önce resmî profil olarak değerlendirildi",
        )
        possible = self.review_service(30).decide(
            watch.id,
            "GitHub",
            decision="possible_impersonation",
            reason="Yeni kanıt sonrası olası taklit sayıldı",
        )
        official_event_id = official.details.events[-1].id
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE brand_username_review_notifications SET review_event_id=? "
                "WHERE id=?",
                (official_event_id, possible.notification_id),
            )
        with self.assertRaises(StorageError):
            SQLiteInboxRepository(self.path).list()

    def test_cli_review_and_show_explain_scope(self):
        service, watch, report = self.create_found({"GitHub": github()})
        values = ["--data-dir", self.temp.name]
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                *values,
                "brand", "watch-review", watch.id, "GitHub",
                "--decision", "known_official",
                "--reason", "Kuruluşun ana sitesinde bu profil bağlantısı var",
            ]), 0)
        self.assertIn("yalnız bu tam profil adresi", output.getvalue())
        candidate = self.review_repository.current_candidate(watch.id, "GitHub")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                *values, "brand", "watch-review-show", candidate.id,
            ]), 0)
        self.assertIn("otomatik alarm değildir", output.getvalue())
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                *values, "brand", "watch-run-show", report.run.id,
            ]), 0)
        self.assertIn("kullanıcı kararı: resmî", output.getvalue())

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                *values,
                "brand", "watch-review", watch.id, "GitHub",
                "--decision", "possible_impersonation",
                "--reason", "Yeni insan incelemesi olası taklit işareti verdi",
            ]), 0)
        self.assertIn("Ortak yerel kutuya bildirim eklendi", output.getvalue())
        inbox = SQLiteInboxRepository(self.path).list()
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                *values, "inbox", "show", inbox.items[0].notification.id,
            ]), 0)
        self.assertIn("Tam profil: https://github.com/samplebrand", output.getvalue())
        self.assertIn("tarihsel bildirimi silmez", output.getvalue())


if __name__ == "__main__":
    unittest.main()
