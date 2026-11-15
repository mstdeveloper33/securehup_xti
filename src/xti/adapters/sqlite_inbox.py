"""Local inbox views and explicit read state, independent of threat decisions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_vulnerability_notifications import (
    SQLiteVulnerabilityNotificationRepository,
)
from xti.adapters.sqlite_cti_saved_searches import SQLiteCtiSavedSearchRepository
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.adapters.sqlite_public_notice_watches import SQLitePublicNoticeWatchRepository
from xti.adapters.sqlite_supplier_watches import SQLiteSupplierWatchRepository
from xti.adapters.sqlite_brand_username_reviews import (
    SQLiteBrandUsernameReviewRepository,
)
from xti.domain.assets import ValidationError
from xti.domain.inbox import (
    InboxDetails,
    InboxItem,
    InboxPage,
    MarkResult,
    Notification,
    SurfaceChangeEvidence,
    SurfacePortChange,
)


_EXISTING_NOTIFICATIONS = (
    "SELECT sequence, id, finding_id, NULL AS candidate_id, NULL AS evidence_id, "
    "NULL AS evidence_type, NULL AS exposure_id, NULL AS cti_run_id, "
    "NULL AS ransomware_run_id, NULL AS brand_candidate_id, "
    "event_type, origin, created_at, read_at, NULL AS ransomlook_run_id, "
    "NULL AS public_notice_watch_run_id, NULL AS supplier_watch_run_id FROM notifications UNION ALL "
    "SELECT sequence, id, NULL AS finding_id, candidate_id, NULL AS evidence_id, "
    "NULL AS evidence_type, NULL AS exposure_id, NULL AS cti_run_id, "
    "NULL AS ransomware_run_id, NULL AS brand_candidate_id, "
    "event_type, origin, created_at, read_at, NULL AS ransomlook_run_id, "
    "NULL AS public_notice_watch_run_id, NULL AS supplier_watch_run_id "
    "FROM surface_candidate_notifications UNION ALL "
    "SELECT sequence, id, NULL AS finding_id, NULL AS candidate_id, "
    "COALESCE(surface_check_id, mail_check_id, service_check_id) AS evidence_id, "
    "CASE WHEN surface_check_id IS NOT NULL THEN 'surface' "
    "WHEN mail_check_id IS NOT NULL THEN 'mail' ELSE 'service' END AS evidence_type, "
    "NULL AS exposure_id, NULL AS cti_run_id, NULL AS ransomware_run_id, "
    "NULL AS brand_candidate_id, "
    "event_type, origin, created_at, read_at, NULL AS ransomlook_run_id, "
    "NULL AS public_notice_watch_run_id, NULL AS supplier_watch_run_id "
    "FROM surface_change_notifications UNION ALL "
    "SELECT sequence, id, NULL AS finding_id, NULL AS candidate_id, NULL AS evidence_id, "
    "NULL AS evidence_type, exposure_id, NULL AS cti_run_id, "
    "NULL AS ransomware_run_id, NULL AS brand_candidate_id, "
    "event_type, origin, created_at, read_at, NULL AS ransomlook_run_id, "
    "NULL AS public_notice_watch_run_id, NULL AS supplier_watch_run_id "
    "FROM vulnerability_change_notifications UNION ALL "
    "SELECT sequence, id, NULL AS finding_id, NULL AS candidate_id, NULL AS evidence_id, "
    "NULL AS evidence_type, NULL AS exposure_id, run_id AS cti_run_id, "
    "NULL AS ransomware_run_id, NULL AS brand_candidate_id, "
    "event_type, origin, created_at, read_at, NULL AS ransomlook_run_id, "
    "NULL AS public_notice_watch_run_id, NULL AS supplier_watch_run_id "
    "FROM cti_saved_search_notifications UNION ALL "
    "SELECT sequence, id, NULL AS finding_id, NULL AS candidate_id, NULL AS evidence_id, "
    "NULL AS evidence_type, NULL AS exposure_id, NULL AS cti_run_id, "
    "run_id AS ransomware_run_id, NULL AS brand_candidate_id, "
    "event_type, origin, created_at, read_at, NULL AS ransomlook_run_id, "
    "NULL AS public_notice_watch_run_id, NULL AS supplier_watch_run_id "
    "FROM ransomware_watch_notifications UNION ALL "
    "SELECT sequence, id, NULL AS finding_id, NULL AS candidate_id, "
    "NULL AS evidence_id, NULL AS evidence_type, NULL AS exposure_id, "
    "NULL AS cti_run_id, NULL AS ransomware_run_id, "
    "candidate_id AS brand_candidate_id, event_type, origin, created_at, read_at, NULL AS ransomlook_run_id, "
    "NULL AS public_notice_watch_run_id, NULL AS supplier_watch_run_id "
    "FROM brand_username_review_notifications UNION ALL "
    "SELECT sequence, id, NULL AS finding_id, NULL AS candidate_id, NULL AS evidence_id, "
    "NULL AS evidence_type, NULL AS exposure_id, NULL AS cti_run_id, "
    "NULL AS ransomware_run_id, NULL AS brand_candidate_id, "
    "event_type, origin, created_at, read_at, run_id AS ransomlook_run_id, "
    "NULL AS public_notice_watch_run_id, NULL AS supplier_watch_run_id FROM ransomlook_watch_notifications UNION ALL "
    "SELECT sequence, id, NULL AS finding_id, NULL AS candidate_id, NULL AS evidence_id, "
    "NULL AS evidence_type, NULL AS exposure_id, NULL AS cti_run_id, "
    "NULL AS ransomware_run_id, NULL AS brand_candidate_id, "
    "event_type, origin, created_at, read_at, NULL AS ransomlook_run_id, "
    "run_id AS public_notice_watch_run_id, NULL AS supplier_watch_run_id FROM public_notice_watch_notifications UNION ALL "
    "SELECT sequence, id, NULL AS finding_id, NULL AS candidate_id, NULL AS evidence_id, "
    "NULL AS evidence_type, NULL AS exposure_id, NULL AS cti_run_id, "
    "NULL AS ransomware_run_id, NULL AS brand_candidate_id, "
    "event_type, origin, created_at, read_at, NULL AS ransomlook_run_id, "
    "NULL AS public_notice_watch_run_id, run_id AS supplier_watch_run_id FROM supplier_watch_notifications"
)
_COMBINED_NOTIFICATIONS = (
    "SELECT *, NULL AS global_search_run_id FROM (" + _EXISTING_NOTIFICATIONS + ") UNION ALL "
    "SELECT sequence, id, NULL AS finding_id, NULL AS candidate_id, NULL AS evidence_id, "
    "NULL AS evidence_type, NULL AS exposure_id, NULL AS cti_run_id, "
    "NULL AS ransomware_run_id, NULL AS brand_candidate_id, event_type, origin, created_at, read_at, "
    "NULL AS ransomlook_run_id, NULL AS public_notice_watch_run_id, NULL AS supplier_watch_run_id, "
    "run_id AS global_search_run_id FROM global_saved_search_notifications"
)
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)
_MAX_SEQUENCE = 2**63 - 1


def _identifier(value) -> str:
    if not isinstance(value, str) or not value or len(value) > 64 or not value.isprintable():
        raise ValueError("Invalid inbox identifier")
    return value


def _timestamp(value) -> str:
    if not isinstance(value, str) or len(value) > 64 or _TIMESTAMP.fullmatch(value) is None:
        raise ValueError("Invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp requires timezone")
    # Normalize incoming write times. Stored read times may predate creation
    # when the wall clock regresses; read state must still reflect the action.
    return parsed.astimezone(timezone.utc).isoformat()


def _validate_list(status: str, limit: int, before: int | None) -> None:
    if not isinstance(status, str) or status not in {"all", "read", "unread"}:
        raise ValidationError("Bildirim filtresi all, read veya unread olmalı.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError("Bildirim liste sınırı 1–100 arasında olmalı.")
    if before is not None and (type(before) is not int or not 1 <= before <= _MAX_SEQUENCE):
        raise ValidationError("Geçerli bir bildirim sayfa sınırı gerekli.")


class SQLiteInboxRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _validate_sequences(connection: sqlite3.Connection) -> None:
        duplicate = connection.execute(
            "SELECT sequence FROM (" + _COMBINED_NOTIFICATIONS + ") "
            "GROUP BY sequence HAVING COUNT(*) > 1 LIMIT 1"
        ).fetchone()
        if duplicate is not None:
            raise StorageError("Bildirim sırası çakışıyor; işlem durduruldu.")

    @staticmethod
    def _notification(row) -> Notification:
        try:
            (
                sequence, identifier, finding_id, candidate_id,
                evidence_id, evidence_type, exposure_id, cti_run_id, ransomware_run_id,
                brand_candidate_id, event_type, origin, created, read_at, ransomlook_run_id,
                public_notice_watch_run_id, supplier_watch_run_id, global_search_run_id,
            ) = row
            if type(sequence) is not int or not 1 <= sequence <= _MAX_SEQUENCE:
                raise ValueError("Invalid notification sequence")
            _identifier(identifier)
            subjects = sum(
                value is not None
                for value in (
                    finding_id, candidate_id, evidence_id, exposure_id,
                    cti_run_id, ransomware_run_id, brand_candidate_id, ransomlook_run_id,
                    public_notice_watch_run_id, supplier_watch_run_id, global_search_run_id,
                )
            )
            if subjects != 1:
                raise ValueError("Notification must have exactly one subject")
            if finding_id is not None:
                _identifier(finding_id)
            if candidate_id is not None:
                _identifier(candidate_id)
            if evidence_id is not None:
                _identifier(evidence_id)
            if exposure_id is not None:
                _identifier(exposure_id)
            if cti_run_id is not None:
                _identifier(cti_run_id)
            if ransomware_run_id is not None:
                _identifier(ransomware_run_id)
            if ransomlook_run_id is not None:
                _identifier(ransomlook_run_id)
            if public_notice_watch_run_id is not None:
                _identifier(public_notice_watch_run_id)
            if supplier_watch_run_id is not None:
                _identifier(supplier_watch_run_id)
            if global_search_run_id is not None:
                _identifier(global_search_run_id)
            if brand_candidate_id is not None:
                _identifier(brand_candidate_id)
            if (
                finding_id is not None
                and (event_type != "finding_created" or origin not in {"new", "existing"})
            ) or (
                candidate_id is not None
                and (event_type != "surface_candidate_discovered" or origin != "new")
            ) or (
                evidence_id is not None
                and (
                    evidence_type not in {"surface", "mail", "service"}
                    or event_type != "surface_evidence_changed"
                    or origin != "new"
                )
            ) or (
                exposure_id is not None
                and (event_type != "vulnerability_review_required" or origin != "new")
            ) or (
                cti_run_id is not None
                and (event_type != "cti_saved_search_changed" or origin != "new")
            ) or (
                ransomware_run_id is not None
                and (event_type != "ransomware_watch_changed" or origin != "new")
            ) or (
                ransomlook_run_id is not None
                and (event_type != "ransomlook_watch_changed" or origin != "new")
            ) or (
                public_notice_watch_run_id is not None
                and (event_type != "public_notice_watch_changed" or origin != "new")
            ) or (
                supplier_watch_run_id is not None
                and (event_type != "supplier_watch_changed" or origin != "new")
            ) or (
                global_search_run_id is not None
                and (event_type != "global_saved_search_changed" or origin != "new")
            ) or (
                brand_candidate_id is not None
                and (
                    event_type != "social_profile_possible_impersonation"
                    or origin != "new"
                )
            ):
                raise ValueError("Invalid notification event")
            if evidence_id is None and evidence_type is not None:
                raise ValueError("Evidence type without evidence")
            _timestamp(created)
            if read_at is not None:
                _timestamp(read_at)
            return Notification(
                sequence, identifier, finding_id, event_type, origin, created, read_at,
                candidate_id, evidence_id, evidence_type, exposure_id, cti_run_id,
                ransomware_run_id, brand_candidate_id, ransomlook_run_id,
                public_notice_watch_run_id, supplier_watch_run_id, global_search_run_id,
            )
        except (ValueError, TypeError, OverflowError) as error:
            raise StorageError(
                "Bildirim kaydı beklenen biçimde değil; işlem durduruldu."
            ) from error

    @staticmethod
    def _change_evidence(
        connection: sqlite3.Connection, evidence_type: str, check_id: str,
    ) -> SurfaceChangeEvidence:
        if evidence_type == "surface":
            row = connection.execute(
                "SELECT c.id, c.asset_id, s.asset_value, c.result, c.state_sha256, "
                "c.change, c.recorded_at FROM surface_checks c "
                "JOIN surface_scopes s ON s.asset_id = c.asset_id WHERE c.id = ?",
                (check_id,),
            ).fetchone()
            check = SQLiteSurfaceRepository._check(row, row[2]) if row is not None else None
            if check is not None:
                evidence = SurfaceChangeEvidence(
                    "surface", check.id, check.asset_id, check.asset_value,
                    check.change.changed_fields, check.recorded_at,
                    check.change.added_addresses, check.change.removed_addresses,
                )
        elif evidence_type == "mail":
            row = connection.execute(
                "SELECT c.id, c.asset_id, s.asset_value, c.result, c.state_sha256, "
                "c.change, c.recorded_at FROM surface_mail_checks c "
                "JOIN surface_scopes s ON s.asset_id = c.asset_id WHERE c.id = ?",
                (check_id,),
            ).fetchone()
            check = SQLiteSurfaceMailRepository._check(row, row[2]) if row is not None else None
            if check is not None:
                evidence = SurfaceChangeEvidence(
                    "mail", check.id, check.asset_id, check.asset_value,
                    check.change.changed_fields, check.recorded_at,
                )
        elif evidence_type == "service":
            row = connection.execute(
                "SELECT c.id, c.asset_id, s.asset_value, c.authorization_reason, "
                "c.result, c.state_sha256, c.change, c.recorded_at "
                "FROM surface_service_checks c "
                "JOIN surface_scopes s ON s.asset_id = c.asset_id WHERE c.id = ?",
                (check_id,),
            ).fetchone()
            check = (
                SQLiteSurfaceServiceScanRepository._check(row, row[2])
                if row is not None
                else None
            )
            if check is not None:
                evidence = SurfaceChangeEvidence(
                    "service", check.id, check.asset_id, check.asset_value,
                    check.change.changed_fields, check.recorded_at,
                    port_changes=tuple(
                        SurfacePortChange(item.port, item.before, item.after)
                        for item in check.change.transitions
                    ),
                )
        else:
            raise StorageError("Bildirim kanıt türü geçersiz; işlem durduruldu.")
        if check is None or check.change.kind != "changed":
            raise StorageError("Değişiklik bildiriminin kanıtı bulunamadı veya geçersiz.")
        return evidence

    @classmethod
    def _get(cls, connection: sqlite3.Connection, identifier: str) -> Notification:
        rows = connection.execute(
            "SELECT * FROM (" + _COMBINED_NOTIFICATIONS + ") WHERE id = ?", (identifier,),
        ).fetchall()
        if not rows:
            raise ValidationError("Bildirim bulunamadı. Kimliği bildirim listesinden kontrol et.")
        if len(rows) != 1:
            raise StorageError(
                "Bildirim kimliği birden çok kayıtla eşleşiyor; işlem durduruldu."
            )
        return cls._notification(rows[0])

    def list(self, status: str = "unread", limit: int = 20, before: int | None = None) -> InboxPage:
        _validate_list(status, limit, before)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            self._validate_sequences(connection)
            finding_total, finding_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) FROM notifications"
            ).fetchone()
            candidate_total, candidate_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) "
                "FROM surface_candidate_notifications"
            ).fetchone()
            change_total, change_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) "
                "FROM surface_change_notifications"
            ).fetchone()
            vulnerability_total, vulnerability_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) "
                "FROM vulnerability_change_notifications"
            ).fetchone()
            cti_total, cti_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) "
                "FROM cti_saved_search_notifications"
            ).fetchone()
            ransomware_total, ransomware_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) "
                "FROM ransomware_watch_notifications"
            ).fetchone()
            brand_total, brand_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) "
                "FROM brand_username_review_notifications"
            ).fetchone()
            ransomlook_total, ransomlook_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) "
                "FROM ransomlook_watch_notifications"
            ).fetchone()
            public_notice_total, public_notice_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) "
                "FROM public_notice_watch_notifications"
            ).fetchone()
            supplier_total, supplier_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) "
                "FROM supplier_watch_notifications"
            ).fetchone()
            global_search_total, global_search_unread = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(read_at IS NULL), 0) "
                "FROM global_saved_search_notifications"
            ).fetchone()
            total = (
                finding_total + candidate_total + change_total + vulnerability_total
                + cti_total + ransomware_total + brand_total + ransomlook_total
                + public_notice_total + supplier_total
                + global_search_total
            )
            unread = (
                finding_unread + candidate_unread + change_unread
                + vulnerability_unread + cti_unread + ransomware_unread
                + brand_unread + ransomlook_unread + public_notice_unread + supplier_unread
                + global_search_unread
            )
            matching = (
                total if status == "all"
                else unread if status == "unread"
                else total - unread
            )
            conditions = []
            parameters = []
            if status != "all":
                conditions.append("read_at IS " + ("NULL" if status == "unread" else "NOT NULL"))
            if before is not None:
                conditions.append("sequence < ?")
                parameters.append(before)
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            rows = connection.execute(
                "SELECT * FROM (" + _COMBINED_NOTIFICATIONS + ")" + where +
                " ORDER BY sequence DESC LIMIT ?", (*parameters, limit + 1),
            ).fetchall()
            notifications = tuple(self._notification(row) for row in rows[:limit])
            public_notice_ids = tuple(
                notice.id for notice in notifications
                if notice.public_notice_watch_run_id is not None
            )
            public_notice_evidence = (
                SQLitePublicNoticeWatchRepository.notification_evidences(connection, public_notice_ids)
                if public_notice_ids else {}
            )
            supplier_ids = tuple(
                notice.id for notice in notifications if notice.supplier_watch_run_id is not None
            )
            supplier_evidence = (
                SQLiteSupplierWatchRepository.notification_evidences(connection, supplier_ids)
                if supplier_ids else {}
            )
            global_search_ids = tuple(
                notice.id for notice in notifications if notice.global_search_run_id is not None
            )
            global_search_evidence = (
                SQLiteGlobalSavedSearchRepository.notification_evidences(connection, global_search_ids)
                if global_search_ids else {}
            )
            items = []
            for notification in notifications:
                if notification.finding_id is not None:
                    items.append(InboxItem(
                        notification,
                        SQLiteFindingRepository._get(connection, notification.finding_id),
                    ))
                elif notification.candidate_id is not None:
                    candidate_row = SQLiteSurfaceCandidateRepository._candidate_row(
                        connection, notification.candidate_id,
                    )
                    if candidate_row is None:
                        raise StorageError("Alt alan adı bildiriminin adayı bulunamadı.")
                    items.append(InboxItem(
                        notification, None,
                        SQLiteSurfaceCandidateRepository._candidate(candidate_row),
                    ))
                elif notification.evidence_id is not None:
                    evidence = self._change_evidence(
                        connection, notification.evidence_type, notification.evidence_id,
                    )
                    items.append(InboxItem(notification, None, None, evidence))
                elif notification.exposure_id is not None:
                    vulnerability = SQLiteVulnerabilityNotificationRepository.evidence(
                        connection, notification.id,
                    )
                    items.append(InboxItem(
                        notification, None, None, None, vulnerability,
                    ))
                elif notification.cti_run_id is not None:
                    cti_change = SQLiteCtiSavedSearchRepository.notification_evidence(
                        connection, notification.id,
                    )
                    items.append(InboxItem(
                        notification, None, None, None, None, cti_change,
                    ))
                elif notification.ransomware_run_id is not None:
                    ransomware_change = SQLiteRansomwareWatchRepository.notification_evidence(
                        connection, notification.id,
                    )
                    items.append(InboxItem(
                        notification, None, None, None, None, None, ransomware_change,
                    ))
                elif notification.ransomlook_run_id is not None:
                    items.append(InboxItem(
                        notification, None, ransomlook_change=SQLiteRansomLookWatchRepository.notification_evidence(
                            connection, notification.id,
                        ),
                    ))
                elif notification.public_notice_watch_run_id is not None:
                    items.append(InboxItem(
                        notification, None,
                        public_notice_change=public_notice_evidence[notification.id],
                    ))
                elif notification.supplier_watch_run_id is not None:
                    items.append(InboxItem(
                        notification, None, supplier_change=supplier_evidence[notification.id],
                    ))
                elif notification.global_search_run_id is not None:
                    items.append(InboxItem(
                        notification, None, global_search_change=global_search_evidence[notification.id],
                    ))
                else:
                    brand_review = (
                        SQLiteBrandUsernameReviewRepository.notification_evidence(
                            connection, notification.id,
                        )
                    )
                    items.append(InboxItem(
                        notification, None, None, None, None, None, None,
                        brand_review,
                    ))
            items = tuple(items)
            next_before = items[-1].notification.sequence if len(rows) > limit else None
            connection.rollback()
        return InboxPage(items, next_before, total, unread, matching)

    def get(self, notification_id: str) -> InboxDetails:
        try:
            _identifier(notification_id)
        except ValueError as error:
            raise ValidationError("Geçerli bir bildirim kimliği gerekli.") from error
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            self._validate_sequences(connection)
            notification = self._get(connection, notification_id)
            if notification.finding_id is not None:
                result = InboxDetails(
                    notification,
                    SQLiteFindingRepository._details(connection, notification.finding_id),
                )
            elif notification.candidate_id is not None:
                result = InboxDetails(
                    notification, None,
                    SQLiteSurfaceCandidateRepository._details(
                        connection, notification.candidate_id, source_limit=100,
                    ),
                )
            elif notification.evidence_id is not None:
                result = InboxDetails(
                    notification, None, None,
                    self._change_evidence(
                        connection, notification.evidence_type, notification.evidence_id,
                    ),
                )
            elif notification.exposure_id is not None:
                result = InboxDetails(
                    notification, None, None, None,
                    SQLiteVulnerabilityNotificationRepository.evidence(
                        connection, notification.id,
                    ),
                )
            elif notification.cti_run_id is not None:
                result = InboxDetails(
                    notification, None, None, None, None,
                    SQLiteCtiSavedSearchRepository.notification_evidence(
                        connection, notification.id,
                    ),
                )
            elif notification.ransomware_run_id is not None:
                result = InboxDetails(
                    notification, None, None, None, None, None,
                    SQLiteRansomwareWatchRepository.notification_evidence(
                        connection, notification.id,
                    ),
                )
            elif notification.ransomlook_run_id is not None:
                result = InboxDetails(
                    notification, None, ransomlook_change=SQLiteRansomLookWatchRepository.notification_evidence(
                        connection, notification.id,
                    ),
                )
            elif notification.public_notice_watch_run_id is not None:
                result = InboxDetails(
                    notification, None,
                    public_notice_change=SQLitePublicNoticeWatchRepository.notification_evidence(
                        connection, notification.id,
                    ),
                )
            elif notification.supplier_watch_run_id is not None:
                result = InboxDetails(
                    notification, None,
                    supplier_change=SQLiteSupplierWatchRepository.notification_evidence(
                        connection, notification.id,
                    ),
                )
            elif notification.global_search_run_id is not None:
                result = InboxDetails(
                    notification, None,
                    global_search_change=SQLiteGlobalSavedSearchRepository.notification_evidence(
                        connection, notification.id,
                    ),
                )
            else:
                result = InboxDetails(
                    notification, None, None, None, None, None, None,
                    SQLiteBrandUsernameReviewRepository.notification_evidence(
                        connection, notification.id,
                    ),
                )
            connection.rollback()
        return result

    @staticmethod
    def _mark_rows(
        connection: sqlite3.Connection, identifiers: tuple[str, ...],
        read: bool, now: str,
    ) -> int:
        changed = 0
        for identifier in identifiers:
            notification = SQLiteInboxRepository._get(connection, identifier)
            table = (
                "notifications" if notification.finding_id is not None
                else "surface_candidate_notifications"
                if notification.candidate_id is not None
                else "surface_change_notifications"
                if notification.evidence_id is not None
                else "vulnerability_change_notifications"
                if notification.exposure_id is not None
                else "cti_saved_search_notifications"
                if notification.cti_run_id is not None
                else "ransomware_watch_notifications"
                if notification.ransomware_run_id is not None
                else "ransomlook_watch_notifications"
                if notification.ransomlook_run_id is not None
                else "public_notice_watch_notifications"
                if notification.public_notice_watch_run_id is not None
                else "supplier_watch_notifications"
                if notification.supplier_watch_run_id is not None
                else "global_saved_search_notifications"
                if notification.global_search_run_id is not None
                else "brand_username_review_notifications"
            )
            # Table names are fixed above; only values are external input.
            if read:
                cursor = connection.execute(
                    f"UPDATE {table} SET read_at = ? WHERE id = ? AND read_at IS NULL",
                    (now, identifier),
                )
            else:
                cursor = connection.execute(
                    f"UPDATE {table} SET read_at = NULL WHERE id = ? AND read_at IS NOT NULL",
                    (identifier,),
                )
            changed += cursor.rowcount
        return changed

    def mark(self, ids: Sequence[str], read: bool, now: str) -> MarkResult:
        try:
            if (not isinstance(ids, Sequence) or isinstance(ids, (str, bytes))
                    or not 1 <= len(ids) <= 100 or type(read) is not bool):
                raise ValueError("Invalid mark request")
            identifiers = tuple(dict.fromkeys(_identifier(value) for value in ids))
            now = _timestamp(now)
        except (ValueError, TypeError, OverflowError) as error:
            raise ValidationError(
                "Okundu işlemi için 1–100 geçerli bildirim kimliği ve zaman gerekli."
            ) from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_sequences(connection)
                # Validate the entire batch before changing even the first row.
                selected = tuple(self._get(connection, identifier) for identifier in identifiers)
                public_notice_ids = tuple(
                    notice.id for notice in selected
                    if notice.public_notice_watch_run_id is not None
                )
                if public_notice_ids:
                    SQLitePublicNoticeWatchRepository.notification_evidences(connection, public_notice_ids)
                supplier_ids = tuple(
                    notice.id for notice in selected if notice.supplier_watch_run_id is not None
                )
                if supplier_ids:
                    SQLiteSupplierWatchRepository.notification_evidences(connection, supplier_ids)
                global_search_ids = tuple(
                    notice.id for notice in selected if notice.global_search_run_id is not None
                )
                if global_search_ids:
                    SQLiteGlobalSavedSearchRepository.notification_evidences(connection, global_search_ids)
                for notification in selected:
                    if notification.ransomlook_run_id is not None:
                        SQLiteRansomLookWatchRepository.notification_evidence(connection, notification.id)
                changed = self._mark_rows(connection, identifiers, read, now)
                notifications = tuple(
                    self._get(connection, identifier) for identifier in identifiers
                )
                if changed:
                    connection.commit()
                else:
                    connection.rollback()
                return MarkResult(notifications, changed)
            except BaseException:
                connection.rollback()
                raise
