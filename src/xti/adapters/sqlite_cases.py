"""SQLite case lifecycle with current state and one append-only activity stream."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.cases import (
    CASE_ACTIVITY_TYPES,
    PUBLIC_NOTICE_CASE_TYPES, validate_public_notice_case_payload,
    Case,
    CaseActivity,
    CaseDetails,
    CaseEvidence,
    CaseEvidenceMutation,
    CaseEvidenceSnapshot,
    CaseMutation,
    CaseTask,
    CaseTaskMutation,
    canonical_snapshot,
    normalize_case_evidence_id,
    normalize_case_evidence_link_id,
    normalize_case_evidence_type,
    normalize_case_id,
    normalize_case_note,
    normalize_case_note_kind,
    normalize_case_priority,
    normalize_case_reason,
    normalize_case_resolution,
    normalize_case_status,
    normalize_case_summary,
    normalize_case_task_id,
    normalize_case_task_status,
    normalize_case_task_title,
    normalize_case_title,
)


_MAX_ACTIVITY = 100_000


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid UUID")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("non-canonical UUID")
    return normalized


def _time(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc).isoformat()


def _optional_time(value: object) -> str | None:
    return None if value is None else _time(value)


def _latest(first: str, second: str) -> str:
    return max(datetime.fromisoformat(first), datetime.fromisoformat(second)).isoformat()


class SQLiteCaseRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _case(row) -> Case:
        try:
            record = Case(
                id=_uuid(row[0]), title=normalize_case_title(row[1]),
                summary=normalize_case_summary(row[2]), status=normalize_case_status(row[3]),
                priority=normalize_case_priority(row[4]),
                resolution=(
                    normalize_case_resolution(row[5]) if row[5] is not None else None
                ),
                created_at=_time(row[6]), updated_at=_time(row[7]),
                closed_at=_optional_time(row[8]),
            )
            if datetime.fromisoformat(record.updated_at) < datetime.fromisoformat(record.created_at):
                raise ValueError("time regression")
            if record.status in {"resolved", "closed"} and record.resolution is None:
                raise ValueError("resolution missing")
            if record.status not in {"resolved", "closed"} and record.resolution is not None:
                raise ValueError("unexpected resolution")
            if (record.status == "closed") != (record.closed_at is not None):
                raise ValueError("closed timestamp mismatch")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Vaka kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _evidence(row) -> CaseEvidence:
        try:
            snapshot_json = row[6]
            if (
                not isinstance(snapshot_json, str)
                or hashlib.sha256(snapshot_json.encode("ascii")).hexdigest() != row[7]
                or not isinstance(json.loads(snapshot_json), dict)
            ):
                raise ValueError("invalid snapshot")
            record = CaseEvidence(
                id=_uuid(row[0]), case_id=_uuid(row[1]),
                evidence_type=normalize_case_evidence_type(row[2]),
                evidence_id=normalize_case_evidence_id(row[3]),
                display_value=row[4], source_reference=row[5],
                snapshot_json=snapshot_json, snapshot_sha256=row[7], active=bool(row[8]),
                added_reason=normalize_case_reason(row[9]), added_at=_time(row[10]),
                updated_at=_time(row[11]),
                removed_reason=(normalize_case_reason(row[12]) if row[12] else None),
                removed_at=_optional_time(row[13]),
            )
            if (
                type(row[8]) is not int or row[8] not in {0, 1}
                or not isinstance(record.display_value, str)
                or not 1 <= len(record.display_value) <= 1000
                or not isinstance(record.source_reference, str)
                or not 1 <= len(record.source_reference) <= 500
                or record.active == (record.removed_at is not None)
                or record.active == (record.removed_reason is not None)
            ):
                raise ValueError("invalid evidence")
            if record.evidence_type == 'research_group':
                from xti.domain.group_ledger import validate_case_payload
                payload = validate_case_payload(json.loads(snapshot_json))
                command = 'groups current ' if payload['version'] == 2 else 'groups show '
                if record.evidence_id != payload['group']['id'] or record.source_reference != command + record.evidence_id:
                    raise ValueError('Group evidence reference differs')
            if record.evidence_type == 'social_discovery':
                from xti.domain.social_tracking import validate_case_snapshot, case_id
                payload = validate_case_snapshot(json.loads(snapshot_json))
                if record.evidence_id != case_id(payload['discovery_id'], payload['profile']['url']):
                    raise ValueError('Social evidence reference differs')
                if record.source_reference != 'brand review-show ' + payload['discovery_id'] + ' --url ' + payload['profile']['url']:
                    raise ValueError('Social source reference differs')
            if record.evidence_type == 'relationship_review':
                from xti.domain.relationship_notifications import validate_snapshot
                validate_snapshot(json.loads(snapshot_json))
                if record.source_reference != 'relationships notification-show ' + record.evidence_id:
                    raise ValueError('Relationship notification reference differs')
            if record.evidence_type in PUBLIC_NOTICE_CASE_TYPES:
                payload = json.loads(snapshot_json)
                validate_public_notice_case_payload(record.evidence_type, record.evidence_id, payload)
                command = 'notices watch-run-show' if record.evidence_type == 'public_notice_watch' else 'notices run-show'
                if record.source_reference != f"{command} {payload['selection']['run_id']}":
                    raise ValueError('Public notice source reference differs')
            return record
        except (UnicodeError, TypeError, ValueError, KeyError, AttributeError, ValidationError, json.JSONDecodeError) as error:
            raise StorageError("Vaka kanıt bağı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _task(row) -> CaseTask:
        try:
            return CaseTask(
                id=_uuid(row[0]), case_id=_uuid(row[1]),
                title=normalize_case_task_title(row[2]),
                status=normalize_case_task_status(row[3]), due_at=_optional_time(row[4]),
                reason=normalize_case_reason(row[5]), created_at=_time(row[6]),
                updated_at=_time(row[7]),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Vaka görevi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _activity(row) -> CaseActivity:
        try:
            if (
                type(row[0]) is not int
                or row[0] <= 0
                or row[3] not in CASE_ACTIVITY_TYPES
                or not isinstance(row[5], str)
                or not 1 <= len(row[5]) <= 8000
                or any(not character.isprintable() for character in row[5])
                or not isinstance(row[6], str)
                or not 1 <= len(row[6]) <= 2000
                or any(not character.isprintable() for character in row[6])
            ):
                raise ValueError("invalid activity")
            snapshot_json = row[7]
            if (
                not isinstance(snapshot_json, str)
                or hashlib.sha256(snapshot_json.encode("ascii")).hexdigest() != row[8]
                or not isinstance(json.loads(snapshot_json), dict)
            ):
                raise ValueError("invalid activity snapshot")
            return CaseActivity(
                sequence=row[0], id=_uuid(row[1]), case_id=_uuid(row[2]),
                activity_type=row[3], reference_id=(
                    _uuid(row[4]) if row[4] is not None else None
                ), summary=row[5], reason=row[6], snapshot_sha256=row[8],
                recorded_at=_time(row[9]),
            )
        except (UnicodeError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StorageError("Vaka zaman çizelgesi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _case_row(connection, case_id: str):
        return connection.execute(
            "SELECT id, title, summary, status, priority, resolution, created_at, "
            "updated_at, closed_at FROM cases WHERE id = ?", (case_id,),
        ).fetchone()

    @classmethod
    def _get_case(cls, connection, case_id: str) -> Case:
        row = cls._case_row(connection, case_id)
        if row is None:
            raise ValidationError("Vaka bulunamadı.")
        return cls._case(row)

    @staticmethod
    def _case_payload(record: Case) -> dict:
        return {
            "kind": "case", "id": record.id, "title": record.title,
            "summary": record.summary, "status": record.status,
            "priority": record.priority, "resolution": record.resolution,
            "created_at": record.created_at, "updated_at": record.updated_at,
            "closed_at": record.closed_at,
        }

    @staticmethod
    def _insert_activity(
        connection, *, case_id: str, activity_type: str,
        reference_id: str | None, summary: str, reason: str,
        payload: dict, recorded_at: str,
    ) -> CaseActivity:
        snapshot_json, digest = canonical_snapshot(payload)
        activity_id = str(uuid4())
        cursor = connection.execute(
            "INSERT INTO case_activities "
            "(id, case_id, activity_type, reference_id, summary, reason, "
            "snapshot_json, snapshot_sha256, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                activity_id, case_id, activity_type, reference_id,
                summary, reason, snapshot_json, digest, recorded_at,
            ),
        )
        return CaseActivity(
            sequence=cursor.lastrowid, id=activity_id, case_id=case_id,
            activity_type=activity_type, reference_id=reference_id,
            summary=summary, reason=reason, snapshot_sha256=digest,
            recorded_at=recorded_at,
        )

    @staticmethod
    def _recorded(value: str) -> str:
        try:
            return _time(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Vaka işlem zamanı geçersiz.") from error

    def create(
        self, *, title: str, summary: str, priority: str, reason: str, recorded_at: str,
    ) -> CaseMutation:
        title, summary = normalize_case_title(title), normalize_case_summary(summary)
        priority, reason = normalize_case_priority(priority), normalize_case_reason(reason)
        recorded_at = self._recorded(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                case_id = str(uuid4())
                connection.execute(
                    "INSERT INTO cases (id, title, summary, status, priority, resolution, "
                    "created_at, updated_at, closed_at) "
                    "VALUES (?, ?, ?, 'open', ?, NULL, ?, ?, NULL)",
                    (case_id, title, summary, priority, recorded_at, recorded_at),
                )
                record = self._get_case(connection, case_id)
                self._insert_activity(
                    connection, case_id=case_id, activity_type="case_created",
                    reference_id=None, summary=title, reason=reason,
                    payload=self._case_payload(record), recorded_at=recorded_at,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseMutation("created", True, record)

    def update(
        self, case_id: str, *, title: str | None, summary: str | None,
        priority: str | None, reason: str, recorded_at: str,
    ) -> CaseMutation:
        case_id, reason, recorded_at = (
            normalize_case_id(case_id), normalize_case_reason(reason), self._recorded(recorded_at)
        )
        if title is not None:
            title = normalize_case_title(title)
        if summary is not None:
            summary = normalize_case_summary(summary)
        if priority is not None:
            priority = normalize_case_priority(priority)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._get_case(connection, case_id)
                requested = (
                    title if title is not None else current.title,
                    summary if summary is not None else current.summary,
                    priority if priority is not None else current.priority,
                )
                if requested == (current.title, current.summary, current.priority):
                    record, action, changed = current, "unchanged", False
                else:
                    updated_at = _latest(current.updated_at, recorded_at)
                    connection.execute(
                        "UPDATE cases SET title=?, summary=?, priority=?, updated_at=? "
                        "WHERE id=?", (*requested, updated_at, case_id),
                    )
                    record = self._get_case(connection, case_id)
                    self._insert_activity(
                        connection, case_id=case_id, activity_type="case_updated",
                        reference_id=None, summary=record.title, reason=reason,
                        payload=self._case_payload(record), recorded_at=recorded_at,
                    )
                    action, changed = "updated", True
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseMutation(action, changed, record)

    def set_status(
        self, case_id: str, *, status: str, resolution: str | None,
        reason: str, recorded_at: str,
    ) -> CaseMutation:
        case_id, status = normalize_case_id(case_id), normalize_case_status(status)
        reason, recorded_at = normalize_case_reason(reason), self._recorded(recorded_at)
        if status in {"resolved", "closed"}:
            if resolution is None:
                raise ValidationError("Çözülen veya kapanan vaka için sonuç gerekli.")
            resolution = normalize_case_resolution(resolution)
        elif resolution is not None:
            raise ValidationError("Açık vaka durumunda sonuç açıklaması kullanılamaz.")
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._get_case(connection, case_id)
                if status == "closed":
                    open_tasks = connection.execute(
                        "SELECT COUNT(*) FROM case_tasks WHERE case_id=? AND status='open'",
                        (case_id,),
                    ).fetchone()[0]
                    if open_tasks:
                        raise ValidationError(
                            "Açık görevleri tamamlamadan veya iptal etmeden vaka kapatılamaz."
                        )
                if current.status == status and current.resolution == resolution:
                    record, action, changed = current, "unchanged", False
                else:
                    updated_at = _latest(current.updated_at, recorded_at)
                    closed_at = updated_at if status == "closed" else None
                    connection.execute(
                        "UPDATE cases SET status=?, resolution=?, updated_at=?, closed_at=? "
                        "WHERE id=?", (status, resolution, updated_at, closed_at, case_id),
                    )
                    record = self._get_case(connection, case_id)
                    self._insert_activity(
                        connection, case_id=case_id, activity_type="status_changed",
                        reference_id=None, summary=f"{current.status} → {status}",
                        reason=reason, payload=self._case_payload(record),
                        recorded_at=recorded_at,
                    )
                    action, changed = "status_changed", True
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseMutation(action, changed, record)

    def add_note(
        self, case_id: str, *, kind: str, body: str, recorded_at: str,
    ) -> CaseActivity:
        case_id, kind = normalize_case_id(case_id), normalize_case_note_kind(kind)
        body, recorded_at = normalize_case_note(body), self._recorded(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._get_case(connection, case_id)
                activity = self._insert_activity(
                    connection, case_id=case_id, activity_type="note_added",
                    reference_id=None, summary=body, reason=kind,
                    payload={"kind": kind, "body": body}, recorded_at=recorded_at,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return activity

    @staticmethod
    def _evidence_row(connection, link_id: str):
        return connection.execute(
            "SELECT id, case_id, evidence_type, evidence_id, display_value, "
            "source_reference, snapshot_json, snapshot_sha256, active, added_reason, "
            "added_at, updated_at, removed_reason, removed_at FROM case_evidence WHERE id=?",
            (link_id,),
        ).fetchone()

    def add_evidence(
        self, case_id: str, *, snapshot: CaseEvidenceSnapshot,
        reason: str, recorded_at: str,
    ) -> CaseEvidenceMutation:
        case_id, reason, recorded_at = (
            normalize_case_id(case_id), normalize_case_reason(reason), self._recorded(recorded_at)
        )
        evidence_type = normalize_case_evidence_type(snapshot.evidence_type)
        evidence_id = normalize_case_evidence_id(snapshot.evidence_id)
        try:
            snapshot_payload = json.loads(snapshot.snapshot_json)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValidationError(
                "Kanıt anlık görüntüsü geçerli JSON içermiyor."
            ) from error
        if not isinstance(snapshot_payload, dict):
            raise ValidationError("Kanıt anlık görüntüsü JSON nesnesi olmalı.")
        canonical_json, digest = canonical_snapshot(snapshot_payload)
        if canonical_json != snapshot.snapshot_json or digest != snapshot.snapshot_sha256:
            raise ValidationError("Kanıt anlık görüntüsü bütünlük kontrolünden geçemedi.")
        if (
            not isinstance(snapshot.display_value, str)
            or not 1 <= len(snapshot.display_value) <= 1000
            or any(not char.isprintable() for char in snapshot.display_value)
            or not isinstance(snapshot.source_reference, str)
            or not 1 <= len(snapshot.source_reference) <= 500
            or any(not char.isprintable() for char in snapshot.source_reference)
        ):
            raise ValidationError("Kanıt görünür özeti geçersiz.")
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                case = self._get_case(connection, case_id)
                if case.status == "closed":
                    raise ValidationError("Kapalı vakaya kanıt eklemek için önce vakayı yeniden açın.")
                read_case_evidence_links(connection)
                if evidence_type == 'research_group':
                    from xti.adapters.sqlite_groups import case_snapshot
                    if case_snapshot(connection, evidence_id) != snapshot:
                        raise ValidationError('Grup vaka kanıtı seçili firma kaydıyla uyuşmuyor.')
                if evidence_type == 'social_discovery':
                    from xti.adapters.sqlite_social_tracking import case_snapshot
                    if case_snapshot(connection, self._storage.path, evidence_id) != snapshot:
                        raise ValidationError('Sosyal vaka kanıtı seçili firma kaydıyla uyuşmuyor.')
                if evidence_type == 'relationship_review':
                    from xti.adapters.sqlite_relationship_notifications import case_snapshot
                    if case_snapshot(connection, evidence_id) != snapshot:
                        raise ValidationError('İlişki vaka kanıtı seçili firma bildirimiyle uyuşmuyor.')
                if evidence_type in PUBLIC_NOTICE_CASE_TYPES:
                    from xti.adapters.sqlite_case_evidence import read_public_notice_case_snapshot
                    expected = read_public_notice_case_snapshot(connection, evidence_type, evidence_id)
                    if expected != snapshot:
                        raise ValidationError("Kamu olay vaka kanıtı seçili tarihî kaynakla uyuşmuyor.")
                row = connection.execute(
                    "SELECT id, case_id, evidence_type, evidence_id, display_value, "
                    "source_reference, snapshot_json, snapshot_sha256, active, added_reason, "
                    "added_at, updated_at, removed_reason, removed_at FROM case_evidence "
                    "WHERE case_id=? AND evidence_type=? AND evidence_id=?",
                    (case_id, evidence_type, evidence_id),
                ).fetchone()
                if row is None:
                    link_id, action, activity_type = str(uuid4()), "added", "evidence_added"
                    connection.execute(
                        "INSERT INTO case_evidence "
                        "(id, case_id, evidence_type, evidence_id, display_value, "
                        "source_reference, snapshot_json, snapshot_sha256, active, "
                        "added_reason, added_at, updated_at, removed_reason, removed_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, NULL, NULL)",
                        (
                            link_id, case_id, evidence_type, evidence_id,
                            snapshot.display_value, snapshot.source_reference,
                            snapshot.snapshot_json, snapshot.snapshot_sha256,
                            reason, recorded_at, recorded_at,
                        ),
                    )
                    changed = True
                else:
                    current = self._evidence(row)
                    link_id = current.id
                    if current.active and current.snapshot_sha256 == snapshot.snapshot_sha256:
                        evidence, action, changed = current, "unchanged", False
                        connection.commit()
                        return CaseEvidenceMutation(action, changed, evidence)
                    action = "refreshed" if current.active else "reactivated"
                    activity_type = (
                        "evidence_refreshed" if current.active else "evidence_reactivated"
                    )
                    connection.execute(
                        "UPDATE case_evidence SET display_value=?, source_reference=?, "
                        "snapshot_json=?, snapshot_sha256=?, active=1, added_reason=?, "
                        "updated_at=?, removed_reason=NULL, removed_at=NULL WHERE id=?",
                        (
                            snapshot.display_value, snapshot.source_reference,
                            snapshot.snapshot_json, snapshot.snapshot_sha256, reason,
                            _latest(current.updated_at, recorded_at), link_id,
                        ),
                    )
                    changed = True
                evidence = self._evidence(self._evidence_row(connection, link_id))
                self._insert_activity(
                    connection, case_id=case_id, activity_type=activity_type,
                    reference_id=link_id, summary=evidence.display_value, reason=reason,
                    payload={
                        "kind": "case_evidence", "action": action,
                        "link_id": link_id, "evidence_type": evidence_type,
                        "evidence_id": evidence_id,
                        "source_reference": evidence.source_reference,
                        "snapshot_json": evidence.snapshot_json,
                        "snapshot_sha256": evidence.snapshot_sha256,
                    },
                    recorded_at=recorded_at,
                )
                read_case_evidence_links(connection)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseEvidenceMutation(action, changed, evidence)

    def remove_evidence(
        self, case_id: str, evidence_link_id: str, *, reason: str, recorded_at: str,
    ) -> CaseEvidenceMutation:
        case_id, evidence_link_id = (
            normalize_case_id(case_id), normalize_case_evidence_link_id(evidence_link_id)
        )
        reason, recorded_at = normalize_case_reason(reason), self._recorded(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                case = self._get_case(connection, case_id)
                read_case_evidence_links(connection)
                if case.status == "closed":
                    raise ValidationError("Kapalı vakadan kanıt çıkarmak için önce vakayı açın.")
                row = self._evidence_row(connection, evidence_link_id)
                if row is None:
                    raise ValidationError("Vaka kanıt bağı bulunamadı.")
                current = self._evidence(row)
                if current.case_id != case_id:
                    raise ValidationError("Kanıt bağı bu vakaya ait değil.")
                if not current.active:
                    evidence, action, changed = current, "unchanged", False
                else:
                    updated_at = _latest(current.updated_at, recorded_at)
                    connection.execute(
                        "UPDATE case_evidence SET active=0, updated_at=?, removed_reason=?, "
                        "removed_at=? WHERE id=?",
                        (updated_at, reason, recorded_at, current.id),
                    )
                    evidence = self._evidence(self._evidence_row(connection, current.id))
                    self._insert_activity(
                        connection, case_id=case_id, activity_type="evidence_removed",
                        reference_id=current.id, summary=current.display_value, reason=reason,
                        payload={
                            "kind": "case_evidence", "action": "removed",
                            "link_id": current.id, "evidence_type": current.evidence_type,
                            "evidence_id": current.evidence_id,
                            "snapshot_json": current.snapshot_json,
                            "snapshot_sha256": current.snapshot_sha256,
                        }, recorded_at=recorded_at,
                    )
                    action, changed = "removed", True
                read_case_evidence_links(connection)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseEvidenceMutation(action, changed, evidence)

    @staticmethod
    def _task_row(connection, task_id: str):
        return connection.execute(
            "SELECT id, case_id, title, status, due_at, reason, created_at, updated_at "
            "FROM case_tasks WHERE id=?", (task_id,),
        ).fetchone()

    def add_task(
        self, case_id: str, *, title: str, due_at: str | None,
        reason: str, recorded_at: str,
    ) -> CaseTaskMutation:
        case_id, title = normalize_case_id(case_id), normalize_case_task_title(title)
        reason, recorded_at = normalize_case_reason(reason), self._recorded(recorded_at)
        due_at = _optional_time(due_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                case = self._get_case(connection, case_id)
                if case.status == "closed":
                    raise ValidationError("Kapalı vakaya görev eklemek için önce vakayı açın.")
                task_id = str(uuid4())
                connection.execute(
                    "INSERT INTO case_tasks "
                    "(id, case_id, title, status, due_at, reason, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'open', ?, ?, ?, ?)",
                    (task_id, case_id, title, due_at, reason, recorded_at, recorded_at),
                )
                task = self._task(self._task_row(connection, task_id))
                self._insert_activity(
                    connection, case_id=case_id, activity_type="task_added",
                    reference_id=task_id, summary=title, reason=reason,
                    payload={
                        "kind": "case_task", "id": task.id, "title": task.title,
                        "status": task.status, "due_at": task.due_at,
                    }, recorded_at=recorded_at,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseTaskMutation("added", True, task)

    def update_task(
        self, case_id: str, task_id: str, *, status: str,
        reason: str, recorded_at: str,
    ) -> CaseTaskMutation:
        case_id, task_id = normalize_case_id(case_id), normalize_case_task_id(task_id)
        status, reason = normalize_case_task_status(status), normalize_case_reason(reason)
        recorded_at = self._recorded(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                case = self._get_case(connection, case_id)
                if case.status == "closed":
                    raise ValidationError("Kapalı vaka görevini değiştirmek için önce vakayı açın.")
                row = self._task_row(connection, task_id)
                if row is None:
                    raise ValidationError("Vaka görevi bulunamadı.")
                current = self._task(row)
                if current.case_id != case_id:
                    raise ValidationError("Görev bu vakaya ait değil.")
                if current.status == status:
                    task, action, changed = current, "unchanged", False
                else:
                    updated_at = _latest(current.updated_at, recorded_at)
                    connection.execute(
                        "UPDATE case_tasks SET status=?, reason=?, updated_at=? WHERE id=?",
                        (status, reason, updated_at, task_id),
                    )
                    task = self._task(self._task_row(connection, task_id))
                    self._insert_activity(
                        connection, case_id=case_id, activity_type="task_updated",
                        reference_id=task_id, summary=f"{task.title}: {current.status} → {status}",
                        reason=reason, payload={
                            "kind": "case_task", "id": task.id, "title": task.title,
                            "status": task.status, "due_at": task.due_at,
                        }, recorded_at=recorded_at,
                    )
                    action, changed = "updated", True
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseTaskMutation(action, changed, task)

    def list(
        self, *, status: str | None, priority: str | None, limit: int,
    ) -> tuple[Case, ...]:
        if status is not None:
            status = normalize_case_status(status)
        if priority is not None:
            priority = normalize_case_priority(priority)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Vaka liste sınırı 1–500 arasında olmalı.")
        clauses, values = [], []
        if status is not None:
            clauses.append("status=?")
            values.append(status)
        if priority is not None:
            clauses.append("priority=?")
            values.append(priority)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT id, title, summary, status, priority, resolution, created_at, "
                f"updated_at, closed_at FROM cases{where} "
                "ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
                "WHEN 'medium' THEN 2 ELSE 3 END, updated_at DESC, id LIMIT ?",
                (*values, limit),
            ).fetchall()
        return tuple(self._case(row) for row in rows)

    def evidence_show(self, case_id: str, evidence_link_id: str) -> CaseEvidence:
        case_id = normalize_case_id(case_id)
        evidence_link_id = normalize_case_evidence_link_id(evidence_link_id)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            self._get_case(connection, case_id)
            links = read_case_evidence_links(connection)
            result = next((link for link in links if link.id == evidence_link_id and link.case_id == case_id), None)
            if result is None:
                raise ValidationError("Bu vakaya ait kanıt bağı bulunamadı.")
            return result

    def show(
        self, case_id: str, *, evidence_limit: int, task_limit: int,
        activity_limit: int,
    ) -> CaseDetails:
        case_id = normalize_case_id(case_id)
        for value, maximum, label in (
            (evidence_limit, 500, "Kanıt"), (task_limit, 500, "Görev"),
            (activity_limit, 1000, "Zaman çizelgesi"),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValidationError(f"{label} sınırı 1–{maximum} arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            record = self._get_case(connection, case_id)
            read_case_evidence_links(connection)
            evidence_count, active_evidence_count = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(active), 0) FROM case_evidence WHERE case_id=?",
                (case_id,),
            ).fetchone()
            evidence_rows = connection.execute(
                "SELECT id, case_id, evidence_type, evidence_id, display_value, "
                "source_reference, snapshot_json, snapshot_sha256, active, added_reason, "
                "added_at, updated_at, removed_reason, removed_at FROM case_evidence "
                "WHERE case_id=? ORDER BY active DESC, updated_at DESC, id LIMIT ?",
                (case_id, evidence_limit),
            ).fetchall()
            task_count, open_task_count = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(status='open'), 0) FROM case_tasks WHERE case_id=?",
                (case_id,),
            ).fetchone()
            task_rows = connection.execute(
                "SELECT id, case_id, title, status, due_at, reason, created_at, updated_at "
                "FROM case_tasks WHERE case_id=? ORDER BY CASE status WHEN 'open' THEN 0 "
                "WHEN 'done' THEN 1 ELSE 2 END, due_at IS NULL, due_at, created_at, id LIMIT ?",
                (case_id, task_limit),
            ).fetchall()
            activity_count = connection.execute(
                "SELECT COUNT(*) FROM case_activities WHERE case_id=?", (case_id,),
            ).fetchone()[0]
            if activity_count > _MAX_ACTIVITY:
                connection.rollback()
                raise StorageError("Vaka zaman çizelgesi 100.000 olay sınırını aşıyor.")
            activity_rows = connection.execute(
                "SELECT sequence, id, case_id, activity_type, reference_id, summary, "
                "reason, snapshot_json, snapshot_sha256, recorded_at FROM "
                "case_activities WHERE case_id=? ORDER BY sequence DESC LIMIT ?",
                (case_id, activity_limit),
            ).fetchall()
            first = connection.execute(
                "SELECT activity_type FROM case_activities WHERE case_id=? "
                "ORDER BY sequence LIMIT 1", (case_id,),
            ).fetchone()
            lifecycle_row = connection.execute(
                "SELECT sequence, id, case_id, activity_type, reference_id, summary, "
                "reason, snapshot_json, snapshot_sha256, recorded_at FROM "
                "case_activities WHERE case_id=? AND activity_type IN "
                "('case_created', 'case_updated', 'status_changed') "
                "ORDER BY sequence DESC LIMIT 1",
                (case_id,),
            ).fetchone()
            connection.rollback()
        if first != ("case_created",):
            raise StorageError("Vaka başlangıç olayı eksik; işlem durduruldu.")
        if lifecycle_row is None:
            raise StorageError("Vaka yaşam döngüsü kanıtı eksik; işlem durduruldu.")
        lifecycle = self._activity(lifecycle_row)
        expected_snapshot, _ = canonical_snapshot(self._case_payload(record))
        if lifecycle_row[7] != expected_snapshot or lifecycle.case_id != case_id:
            raise StorageError("Vaka güncel durumu zaman çizelgesiyle uyuşmuyor.")
        evidence = tuple(self._evidence(row) for row in evidence_rows)
        tasks = tuple(self._task(row) for row in task_rows)
        activities = tuple(reversed(tuple(self._activity(row) for row in activity_rows)))
        if any(item.case_id != case_id for item in (*evidence, *tasks, *activities)):
            raise StorageError("Vaka kayıt bağlantısı bozuk; işlem durduruldu.")
        return CaseDetails(
            case=record, evidence=evidence, tasks=tasks, activities=activities,
            total_evidence_count=evidence_count,
            active_evidence_count=active_evidence_count,
            total_task_count=task_count, open_task_count=open_task_count,
            total_activity_count=activity_count,
        )



def _case_evidence_rows(connection, query):
    rows = connection.execute(query).fetchmany(50_001)
    if len(rows) > 50_000:
        raise StorageError("Vaka kanıt geçmişi güvenli okuma sınırını aşıyor.")
    return rows


_CASE_COLUMNS = 'id, case_id, evidence_type, evidence_id, display_value, source_reference, snapshot_json, snapshot_sha256, active, added_reason, added_at, updated_at, removed_reason, removed_at'


def read_case_evidence_links(connection):
    """Replay immutable link activities before any organization filtering.

    A mutable evidence_id/case_id/active column cannot manufacture membership.
    Private case contents are validated here but never copied to the report.
    """
    try:
        links = {link.id: link for link in (
            SQLiteCaseRepository._evidence(row)
            for row in _case_evidence_rows(connection, f"SELECT {_CASE_COLUMNS} FROM case_evidence ORDER BY id")
        )}
        histories = {identifier: [] for identifier in links}
        rows = _case_evidence_rows(connection,
                     "SELECT sequence,id,case_id,activity_type,reference_id,summary,reason,"
                     "snapshot_json,snapshot_sha256,recorded_at FROM case_activities "
                     "WHERE activity_type IN ('evidence_added','evidence_refreshed',"
                     "'evidence_reactivated','evidence_removed') ORDER BY sequence")
        for row in rows:
            activity = SQLiteCaseRepository._activity(row)
            payload = json.loads(row[7])
            if canonical_snapshot(payload)[0] != row[7]:
                raise ValueError("Noncanonical evidence activity")
            link = links.get(activity.reference_id)
            action = activity.activity_type.removeprefix('evidence_')
            keys = {'kind', 'action', 'link_id', 'evidence_type', 'evidence_id',
                    'snapshot_json', 'snapshot_sha256'}
            if action != 'removed':
                keys.add('source_reference')
            if (link is None or activity.case_id != link.case_id or set(payload) != keys
                    or payload['kind'] != 'case_evidence' or payload['action'] != action
                    or payload['link_id'] != link.id or payload['evidence_type'] != link.evidence_type
                    or payload['evidence_id'] != link.evidence_id):
                raise ValueError("Evidence activity identity mismatch")
            frozen = json.loads(payload['snapshot_json'])
            if not isinstance(frozen, dict) or canonical_snapshot(frozen) != (
                payload['snapshot_json'], payload['snapshot_sha256'],
            ):
                raise ValueError("Evidence activity snapshot mismatch")
            histories[link.id].append((activity, payload))
        for identifier, link in links.items():
            history = histories[identifier]
            if not history or history[0][0].activity_type != 'evidence_added':
                raise ValueError("Missing evidence addition")
            active, last_payload, last_source, last_summary = False, None, None, None
            added_reason, removed_reason, removed_at = None, None, None
            first_at = history[0][0].recorded_at
            updated_at = first_at
            for index, (activity, payload) in enumerate(history):
                action = payload['action']
                if (action == 'added' and index != 0
                        or action in {'refreshed', 'removed'} and not active
                        or action == 'reactivated' and active):
                    raise ValueError("Invalid evidence lifecycle transition")
                if action == 'removed':
                    if (payload['snapshot_json'] != last_payload['snapshot_json']
                            or payload['snapshot_sha256'] != last_payload['snapshot_sha256']
                            or activity.summary != last_summary):
                        raise ValueError("Removal rewrites frozen evidence")
                    active, removed_reason, removed_at = False, activity.reason, activity.recorded_at
                else:
                    if (action == 'refreshed'
                            and payload['snapshot_sha256'] == last_payload['snapshot_sha256']):
                        raise ValueError("Unchanged evidence cannot be refreshed")
                    active, removed_reason, removed_at = True, None, None
                    last_source, last_summary = payload['source_reference'], activity.summary
                    added_reason = activity.reason
                last_payload = payload
                updated_at = max((updated_at, activity.recorded_at), key=datetime.fromisoformat)
            if (link.active != active or link.snapshot_json != last_payload['snapshot_json']
                    or link.snapshot_sha256 != last_payload['snapshot_sha256']
                    or link.source_reference != last_source or link.display_value != last_summary
                    or link.added_reason != added_reason or link.added_at != first_at
                    or link.updated_at != updated_at or link.removed_reason != removed_reason
                    or link.removed_at != removed_at):
                raise ValueError("Evidence link differs from its activity history")
        return tuple(links.values())
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError, ValidationError) as error:
        raise StorageError("Vaka kanıt bağı zaman çizelgesiyle uyuşmuyor; kayıtlar değiştirilmedi.") from error

