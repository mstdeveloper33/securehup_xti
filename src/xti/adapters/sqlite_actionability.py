"""Atomic SQLite persistence for P06 defensive action workflows."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.domain.actionability import (
    RunbookApplication, RunbookPlan, TakedownDetails, TakedownEvent,
    TakedownRequest, build_runbook, canonical, next_takedown_state,
    normalize_actor, normalize_external_reference, normalize_key,
    normalize_reason, normalize_recipient, normalize_requested_action,
    normalize_runbook_step, normalize_sha256,
    normalize_runbook_id, normalize_takedown_id, normalize_target,
    normalize_target_kind,
    runbook_payload, takedown_draft,
)
from xti.domain.assets import ValidationError
from xti.domain.cases import CaseDetails, normalize_case_id, normalize_case_task_title
from xti.domain.abuse_contacts import normalize_candidate_id


_EVIDENCE_COLUMNS = (
    "id, case_id, evidence_type, evidence_id, display_value, source_reference, "
    "snapshot_json, snapshot_sha256, active, added_reason, added_at, updated_at, "
    "removed_reason, removed_at"
)
_TAKEDOWN_COLUMNS = (
    "id, case_id, evidence_link_id, target_kind, target_value, recipient, "
    "requested_action, grounds, state, revision, evidence_sha256, draft_json, "
    "draft_sha256, approved_by, approved_at, external_reference, created_at, updated_at"
)
_EVENT_COLUMNS = (
    "sequence, id, request_id, revision, action, state, actor, reason, "
    "external_reference, snapshot_sha256, snapshot_json, recorded_at"
)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("uuid required")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("noncanonical uuid")
    return normalized


def _time(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("timestamp required")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    normalized = parsed.astimezone(timezone.utc).isoformat()
    if normalized != value:
        raise ValueError("noncanonical timestamp")
    return normalized


def _sha(value: object) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ValueError("invalid sha256")
    return value


def _optional(value: object, validator):
    return None if value is None else validator(value)


class SQLiteActionabilityRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _complete_plan(connection, case_id: str) -> RunbookPlan:
        record = SQLiteCaseRepository._get_case(connection, normalize_case_id(case_id))
        count = connection.execute(
            "SELECT COUNT(*) FROM case_evidence WHERE case_id=?", (case_id,),
        ).fetchone()[0]
        if count > 50_000:
            raise ValidationError(
                "Runbook için vaka kanıtı 50.000 kayıt sınırını aşıyor; kapsam daraltılmadan işlem yapılmadı."
            )
        rows = connection.execute(
            f"SELECT {_EVIDENCE_COLUMNS} FROM case_evidence WHERE case_id=? "
            "ORDER BY active DESC, updated_at DESC, id", (case_id,),
        ).fetchall()
        evidence = tuple(SQLiteCaseRepository._evidence(row) for row in rows)
        if any(item.case_id != case_id for item in evidence):
            raise StorageError("Runbook vaka kanıt bağı bozuk; işlem durduruldu.")
        details = CaseDetails(
            case=record, evidence=evidence, tasks=(), activities=(),
            total_evidence_count=count,
            active_evidence_count=sum(item.active for item in evidence),
            total_task_count=0, open_task_count=0, total_activity_count=0,
        )
        return build_runbook(details)

    def runbook_plan(self, case_id: str) -> RunbookPlan:
        case_id = normalize_case_id(case_id)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            result = self._complete_plan(connection, case_id)
            connection.rollback()
        return result

    @staticmethod
    def _runbook(connection, runbook_id: str, *, replayed: bool) -> RunbookApplication:
        row = connection.execute(
            "SELECT id, case_id, template_id, template_version, case_snapshot_sha256, "
            "plan_json, plan_sha256, idempotency_key, reason, created_at "
            "FROM action_runbooks WHERE id=?", (runbook_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Runbook uygulaması bulunamadı.")
        try:
            plan = json.loads(row[5])
            encoded, digest = canonical(plan)
            if encoded != row[5] or digest != row[6] or plan.get("case_id") != row[1]:
                raise ValueError("plan mismatch")
            reason = normalize_reason(row[8])
            if not isinstance(plan.get("steps"), list) or not 1 <= len(plan["steps"]) <= 100:
                raise ValueError("step count")
            steps = tuple(normalize_runbook_step(item) for item in plan["steps"])
            if runbook_payload(RunbookPlan(
                row[1], row[2], row[3], row[4], row[6], steps, (),
            )) != plan:
                raise ValueError("plan fields")
            task_rows = connection.execute(
                "SELECT ordinal,code,title,rationale,case_task_id "
                "FROM action_runbook_items WHERE runbook_id=? ORDER BY ordinal",
                (row[0],),
            ).fetchall()
            if len(task_rows) != len(plan.get("steps", ())):
                raise ValueError("item mismatch")
            for ordinal, (stored, step) in enumerate(zip(task_rows, steps, strict=True), 1):
                if stored[:4] != (ordinal, step.code, step.title, step.rationale):
                    raise ValueError("runbook item mismatch")
            return RunbookApplication(
                id=_uuid(row[0]), case_id=normalize_case_id(row[1]),
                template_id=row[2], template_version=row[3],
                case_snapshot_sha256=_sha(row[4]), plan_sha256=_sha(row[6]),
                idempotency_key=normalize_key(row[7]), reason=reason, steps=steps,
                created_task_ids=tuple(_uuid(item[4]) for item in task_rows),
                created_at=_time(row[9]), replayed=replayed,
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError, ValidationError) as error:
            raise StorageError("Runbook uygulama kaydı bozuk; işlem durduruldu.") from error

    def apply_runbook(
        self, case_id: str, *, expected_plan_sha256: str, idempotency_key: str,
        reason: str, recorded_at: str,
    ) -> RunbookApplication:
        case_id = normalize_case_id(case_id)
        expected_plan_sha256 = normalize_sha256(
            expected_plan_sha256, "Beklenen runbook plan SHA-256 değeri",
        )
        idempotency_key = normalize_key(idempotency_key)
        reason, recorded_at = normalize_reason(reason), _time(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                replay = connection.execute(
                    "SELECT id, case_id, plan_sha256, reason FROM action_runbooks "
                    "WHERE idempotency_key=?", (idempotency_key,),
                ).fetchone()
                if replay is not None:
                    if replay[1:] != (case_id, expected_plan_sha256, reason):
                        raise ValidationError(
                            "Runbook tekrar anahtarı farklı bir istek için daha önce kullanılmış."
                        )
                    result = self._runbook(connection, replay[0], replayed=True)
                    connection.rollback()
                    return result
                plan = self._complete_plan(connection, case_id)
                if plan.plan_sha256 != expected_plan_sha256:
                    raise ValidationError(
                        "Runbook planı değişmiş; güncel plan özetini kullanın."
                    )
                expected_payload = runbook_payload(plan)
                encoded, digest = canonical(expected_payload)
                if digest != expected_plan_sha256:
                    raise StorageError("Runbook plan özeti içerikle uyuşmuyor; işlem durduruldu.")
                case = SQLiteCaseRepository._get_case(connection, case_id)
                if case.status == "closed":
                    raise ValidationError("Kapalı vakaya runbook uygulamak için önce vakayı açın.")
                runbook_id = str(uuid4())
                connection.execute(
                    "INSERT INTO action_runbooks "
                    "(id,case_id,template_id,template_version,case_snapshot_sha256,"
                    "plan_json,plan_sha256,idempotency_key,reason,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (runbook_id, plan.case_id, plan.template_id, plan.template_version,
                     plan.case_snapshot_sha256, encoded, plan.plan_sha256,
                     idempotency_key, reason, recorded_at),
                )
                for ordinal, step in enumerate(plan.steps, 1):
                    task_id = str(uuid4())
                    title = normalize_case_task_title(step.title)
                    connection.execute(
                        "INSERT INTO case_tasks "
                        "(id,case_id,title,status,due_at,reason,created_at,updated_at) "
                        "VALUES (?, ?, ?, 'open', NULL, ?, ?, ?)",
                        (task_id, plan.case_id, title, reason, recorded_at, recorded_at),
                    )
                    connection.execute(
                        "INSERT INTO action_runbook_items "
                        "(id,runbook_id,ordinal,code,title,rationale,case_task_id) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (str(uuid4()), runbook_id, ordinal, step.code, title,
                         step.rationale, task_id),
                    )
                    SQLiteCaseRepository._insert_activity(
                        connection, case_id=plan.case_id, activity_type="task_added",
                        reference_id=task_id, summary=title, reason=reason,
                        payload={
                            "kind": "case_task", "id": task_id, "title": title,
                            "status": "open", "due_at": None,
                            "runbook_id": runbook_id, "runbook_step": step.code,
                        }, recorded_at=recorded_at,
                    )
                result = self._runbook(connection, runbook_id, replayed=False)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def runbook_show(self, runbook_id: str) -> RunbookApplication:
        runbook_id = normalize_runbook_id(runbook_id)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            result = self._runbook(connection, runbook_id, replayed=False)
            connection.rollback()
        return result

    @staticmethod
    def _takedown(row) -> TakedownRequest:
        try:
            draft = json.loads(row[11])
            encoded, digest = canonical(draft)
            if encoded != row[11] or digest != row[12]:
                raise ValueError("draft mismatch")
            record = TakedownRequest(
                id=_uuid(row[0]), case_id=normalize_case_id(row[1]),
                evidence_link_id=_uuid(row[2]), target_kind=row[3],
                target_value=normalize_target(row[4]), recipient=normalize_recipient(row[5]),
                requested_action=normalize_requested_action(row[6]),
                grounds=normalize_reason(row[7]), state=row[8], revision=row[9],
                evidence_sha256=_sha(row[10]), draft_sha256=_sha(row[12]),
                approved_by=_optional(row[13], normalize_actor),
                approved_at=_optional(row[14], _time),
                external_reference=_optional(row[15], normalize_external_reference),
                created_at=_time(row[16]), updated_at=_time(row[17]),
            )
            if (normalize_target_kind(record.target_kind) != record.target_kind
                    or type(record.revision) is not int or record.revision < 0
                    or draft.get("case_id") != record.case_id
                    or draft.get("evidence_link_id") != record.evidence_link_id
                    or draft.get("evidence_sha256") != record.evidence_sha256
                    or draft.get("target_kind") != record.target_kind
                    or draft.get("target_value") != record.target_value
                    or draft.get("recipient") != record.recipient
                    or draft.get("requested_action") != record.requested_action
                    or draft.get("grounds") != record.grounds
                    or (record.state == "draft" and record.approved_by is not None)
                    or (record.state in {"approved", "submitted", "acknowledged", "resolved", "rejected"}
                        and record.approved_by is None)):
                raise ValueError("state mismatch")
            return record
        except (TypeError, ValueError, KeyError, json.JSONDecodeError, ValidationError) as error:
            raise StorageError("Takedown kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row) -> TakedownEvent:
        try:
            payload = json.loads(row[10])
            encoded, digest = canonical(payload)
            if encoded != row[10] or digest != row[9]:
                raise ValueError("event snapshot mismatch")
            event = TakedownEvent(
                sequence=row[0], id=_uuid(row[1]), request_id=_uuid(row[2]),
                revision=row[3], action=row[4], state=row[5],
                actor=normalize_actor(row[6]), reason=normalize_reason(row[7]),
                external_reference=_optional(row[8], normalize_external_reference),
                snapshot_sha256=_sha(row[9]), recorded_at=_time(row[11]),
            )
            if type(event.sequence) is not int or event.sequence <= 0:
                raise ValueError("sequence")
            return event
        except (TypeError, ValueError, json.JSONDecodeError, ValidationError) as error:
            raise StorageError("Takedown olay kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _request_payload(record: TakedownRequest) -> dict:
        return {
            "id": record.id, "case_id": record.case_id,
            "evidence_link_id": record.evidence_link_id,
            "target_kind": record.target_kind, "target_value": record.target_value,
            "recipient": record.recipient, "requested_action": record.requested_action,
            "grounds": record.grounds, "state": record.state,
            "revision": record.revision, "evidence_sha256": record.evidence_sha256,
            "draft_sha256": record.draft_sha256, "approved_by": record.approved_by,
            "approved_at": record.approved_at,
            "external_reference": record.external_reference,
            "created_at": record.created_at, "updated_at": record.updated_at,
        }

    @classmethod
    def _snapshot(cls, record: TakedownRequest) -> tuple[str, str]:
        return canonical(cls._request_payload(record))

    @classmethod
    def _details(cls, connection, request_id: str) -> TakedownDetails:
        row = connection.execute(
            f"SELECT {_TAKEDOWN_COLUMNS} FROM action_takedowns WHERE id=?",
            (request_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Takedown kaydı bulunamadı.")
        record = cls._takedown(row)
        draft = json.loads(row[11])
        rows = connection.execute(
            f"SELECT {_EVENT_COLUMNS} FROM action_takedown_events "
            "WHERE request_id=? ORDER BY revision", (request_id,),
        ).fetchall()
        events = tuple(cls._event(item) for item in rows)
        if (not events or events[0].revision != 0 or events[0].action != "draft"
                or tuple(item.revision for item in events) != tuple(range(len(events)))
                or events[-1].revision != record.revision
                or events[-1].state != record.state):
            raise StorageError("Takedown olay zinciri bozuk; işlem durduruldu.")
        previous_state = None
        previous_snapshot_sha256 = None
        approved_by = None
        approved_at = None
        request_keys = set(cls._request_payload(record))
        for event, raw in zip(events, rows, strict=True):
            payload = json.loads(raw[10])
            if (not isinstance(payload, dict) or set(payload) != {
                    "kind", "version", "previous_event_sha256", "event", "request",
            } or payload["kind"] != "takedown_event_snapshot"
                    or payload["version"] != 1
                    or payload["previous_event_sha256"] != previous_snapshot_sha256):
                raise StorageError("Takedown olay anlık görüntüsü bozuk; işlem durduruldu.")
            event_payload = payload["event"]
            expected_event = {
                "request_id": event.request_id, "revision": event.revision,
                "action": event.action, "state": event.state,
                "actor": event.actor, "reason": event.reason,
                "external_reference": event.external_reference,
                "recorded_at": event.recorded_at,
            }
            request_payload = payload["request"]
            if (event_payload != expected_event or not isinstance(request_payload, dict)
                    or set(request_payload) != request_keys):
                raise StorageError("Takedown olay anlık görüntüsü bozuk; işlem durduruldu.")
            if previous_state is None:
                if event.action != "draft" or event.state != "draft":
                    raise StorageError("Takedown başlangıç olayı bozuk; işlem durduruldu.")
            else:
                try:
                    expected_state = next_takedown_state(previous_state, event.action)
                except ValidationError as error:
                    raise StorageError(
                        "Takedown durum geçiş zinciri bozuk; işlem durduruldu."
                    ) from error
                if expected_state != event.state:
                    raise StorageError(
                        "Takedown durum geçiş zinciri bozuk; işlem durduruldu."
                    )
            if event.action == "approve":
                approved_by, approved_at = event.actor, event.recorded_at
            expected_request = {
                "id": record.id, "case_id": record.case_id,
                "evidence_link_id": record.evidence_link_id,
                "target_kind": record.target_kind, "target_value": record.target_value,
                "recipient": record.recipient,
                "requested_action": record.requested_action,
                "grounds": record.grounds, "state": event.state,
                "revision": event.revision,
                "evidence_sha256": record.evidence_sha256,
                "draft_sha256": record.draft_sha256,
                "approved_by": approved_by, "approved_at": approved_at,
                "external_reference": event.external_reference,
                "created_at": record.created_at, "updated_at": event.recorded_at,
            }
            if request_payload != expected_request:
                raise StorageError("Takedown olay anlık görüntüsü bozuk; işlem durduruldu.")
            previous_state = event.state
            previous_snapshot_sha256 = event.snapshot_sha256
        if payload["request"] != cls._request_payload(record):
            raise StorageError("Takedown güncel durumu olay zinciriyle uyuşmuyor.")
        binding_row = connection.execute(
            "SELECT id,takedown_id,candidate_id,candidate_evidence_sha256,review_revision,recorded_at "
            "FROM action_contact_takedown_links WHERE takedown_id=?", (request_id,),
        ).fetchone()
        binding = None
        if binding_row is not None:
            binding = {
                "id": _uuid(binding_row[0]), "takedown_id": _uuid(binding_row[1]),
                "candidate_id": normalize_candidate_id(binding_row[2]),
                "candidate_evidence_sha256": _sha(binding_row[3]),
                "review_revision": binding_row[4], "recorded_at": _time(binding_row[5]),
            }
            draft_binding = draft.get("contact_binding")
            if (
                not isinstance(draft_binding, dict)
                or draft_binding.get("candidate_id") != binding["candidate_id"]
                or draft_binding.get("candidate_evidence_sha256") != binding["candidate_evidence_sha256"]
                or draft_binding.get("review_revision") != binding["review_revision"]
            ):
                raise StorageError("Takedown iletişim adayı bağı taslakla uyuşmuyor.")
        elif draft.get("contact_binding") is not None:
            raise StorageError("Takedown iletişim adayı bağı bulunamadı.")
        return TakedownDetails(record, events, draft, binding)

    @staticmethod
    def _approved_contact(connection, candidate_id: str, case_id: str,
                          evidence_link_id: str) -> tuple[str, str, str, dict]:
        candidate_id = normalize_candidate_id(candidate_id)
        row = connection.execute(
            "SELECT c.id,c.watch_id,c.contact_value,c.routing_kind,c.source_key,"
            "c.source_reference,c.confidence,c.active,c.observation_revision,"
            "c.review_revision,c.evidence_sha256,w.case_id,w.evidence_link_id,"
            "w.subject_kind,w.subject_value "
            "FROM action_contact_candidates c JOIN action_contact_watches w ON w.id=c.watch_id "
            "WHERE c.id=?", (candidate_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Takedown için seçilen abuse iletişim adayı bulunamadı.")
        if row[11] != case_id or row[12] != evidence_link_id:
            raise ValidationError("Abuse iletişim adayı bu vaka kanıtına ait değil.")
        if not row[7]:
            raise ValidationError("Pasif abuse iletişim adayı takedown alıcısı olamaz.")
        review = connection.execute(
            "SELECT revision,observation_revision,decision,actor,reason,evidence_sha256,recorded_at "
            "FROM action_contact_reviews WHERE candidate_id=? ORDER BY revision DESC LIMIT 1",
            (candidate_id,),
        ).fetchone()
        if (
            review is None or review[0] != row[9] or review[1] != row[8]
            or review[2] != "approved" or review[5] != row[10]
        ):
            raise ValidationError(
                "Abuse iletişim adayı güncel kanıt üzerinde approved insan kararı taşımıyor."
            )
        binding = {
            "kind": "reviewed_abuse_contact", "version": 1,
            "candidate_id": candidate_id, "watch_id": _uuid(row[1]),
            "candidate_evidence_sha256": _sha(row[10]),
            "observation_revision": row[8], "review_revision": review[0],
            "source_key": row[4], "source_reference": row[5],
            "confidence": row[6], "approved_by": review[3],
            "approved_at": _time(review[6]),
            "limitations": [
                "Kaynak iletişim adresi sağlar; ihlal veya hukuki yetki hükmü vermez.",
                "Adres değişirse bu insan kararı ve takedown taslağı yeniden hazırlanmalıdır.",
            ],
        }
        return row[3], row[14], row[2], binding

    @classmethod
    def _insert_event(
        cls, connection, record: TakedownRequest, *, action: str,
        actor: str, reason: str, external_reference: str | None,
        recorded_at: str,
    ) -> None:
        previous = connection.execute(
            "SELECT revision,snapshot_sha256 FROM action_takedown_events "
            "WHERE request_id=? ORDER BY revision DESC LIMIT 1", (record.id,),
        ).fetchone()
        if ((record.revision == 0 and previous is not None)
                or (record.revision > 0 and (
                    previous is None or previous[0] != record.revision - 1
                ))):
            raise StorageError("Takedown olay zinciri yeni olayı kabul etmiyor.")
        previous_sha256 = None if previous is None else _sha(previous[1])
        snapshot_json, snapshot_sha = canonical({
            "kind": "takedown_event_snapshot", "version": 1,
            "previous_event_sha256": previous_sha256,
            "event": {
                "request_id": record.id, "revision": record.revision,
                "action": action, "state": record.state,
                "actor": actor, "reason": reason,
                "external_reference": external_reference,
                "recorded_at": recorded_at,
            },
            "request": cls._request_payload(record),
        })
        connection.execute(
            "INSERT INTO action_takedown_events "
            "(id,request_id,revision,action,state,actor,reason,external_reference,"
            "snapshot_sha256,snapshot_json,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), record.id, record.revision, action, record.state, actor,
             reason, external_reference, snapshot_sha, snapshot_json, recorded_at),
        )

    def create_takedown(
        self, case_id: str, evidence_link_id: str, *, target_kind: str | None,
        target_value: str | None, recipient: str | None, requested_action: str,
        grounds: str, idempotency_key: str, actor: str,
        recorded_at: str, contact_candidate_id: str | None = None,
    ) -> TakedownDetails:
        case_id, evidence_link_id = normalize_case_id(case_id), _uuid(evidence_link_id)
        idempotency_key, actor = normalize_key(idempotency_key), normalize_actor(actor)
        if contact_candidate_id is None:
            target_kind = normalize_target_kind(target_kind)
            target_value = normalize_target(target_value)
            recipient = normalize_recipient(recipient)
        else:
            contact_candidate_id = normalize_candidate_id(contact_candidate_id)
            if any(value is not None for value in (target_kind, target_value, recipient)):
                raise ValidationError("İletişim adaylı takedown ham hedef veya alıcı kabul etmez.")
        requested_action = normalize_requested_action(requested_action)
        grounds = normalize_reason(grounds)
        recorded_at = _time(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                replay = connection.execute(
                    "SELECT id FROM action_takedowns WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if replay is not None:
                    result = self._details(connection, replay[0])
                    base_matches = (
                        result.request.case_id == case_id
                        and result.request.evidence_link_id == evidence_link_id
                        and result.request.requested_action == requested_action
                        and result.request.grounds == grounds
                    )
                    if contact_candidate_id is None:
                        route_matches = (
                            result.request.target_kind, result.request.target_value,
                            result.request.recipient,
                        ) == (target_kind, target_value, recipient) and result.contact_binding is None
                    else:
                        route_matches = bool(
                            result.contact_binding
                            and result.contact_binding["candidate_id"] == contact_candidate_id
                        )
                    if not base_matches or not route_matches:
                        raise ValidationError(
                            "Takedown tekrar anahtarı farklı bir taslak için daha önce kullanılmış."
                        )
                    if result.events[0].actor != actor:
                        raise ValidationError(
                            "Takedown tekrar anahtarı farklı bir aktör için daha önce kullanılmış."
                        )
                    connection.rollback()
                    return result
                case = SQLiteCaseRepository._get_case(connection, case_id)
                if case.status == "closed":
                    raise ValidationError("Kapalı vakada takedown taslağı oluşturulamaz.")
                evidence_row = connection.execute(
                    f"SELECT {_EVIDENCE_COLUMNS} FROM case_evidence WHERE id=?",
                    (evidence_link_id,),
                ).fetchone()
                if evidence_row is None:
                    raise ValidationError("Takedown için vaka kanıtı bulunamadı.")
                evidence = SQLiteCaseRepository._evidence(evidence_row)
                binding = None
                if contact_candidate_id is not None:
                    target_kind, target_value, recipient, binding = self._approved_contact(
                        connection, contact_candidate_id, case_id, evidence_link_id,
                    )
                draft, draft_sha = takedown_draft(
                    case_id, evidence, target_kind=target_kind,
                    target_value=target_value, recipient=recipient,
                    requested_action=requested_action, grounds=grounds,
                    contact_binding=binding,
                )
                draft_json, _ = canonical(draft)
                request_id = str(uuid4())
                connection.execute(
                    "INSERT INTO action_takedowns "
                    "(id,case_id,evidence_link_id,target_kind,target_value,recipient,"
                    "requested_action,grounds,state,revision,evidence_sha256,draft_json,"
                    "draft_sha256,idempotency_key,approved_by,approved_at,external_reference,"
                    "created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,'draft',0,?,?,?,?,NULL,NULL,NULL,?,?)",
                    (request_id, case_id, evidence_link_id, draft["target_kind"],
                     draft["target_value"], draft["recipient"], draft["requested_action"],
                     draft["grounds"], evidence.snapshot_sha256, draft_json, draft_sha,
                     idempotency_key, recorded_at, recorded_at),
                )
                record_row = connection.execute(
                    f"SELECT {_TAKEDOWN_COLUMNS} FROM action_takedowns WHERE id=?",
                    (request_id,),
                ).fetchone()
                record = self._takedown(record_row)
                if binding is not None:
                    connection.execute(
                        "INSERT INTO action_contact_takedown_links "
                        "(id,takedown_id,candidate_id,candidate_evidence_sha256,review_revision,recorded_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (str(uuid4()), request_id, binding["candidate_id"],
                         binding["candidate_evidence_sha256"], binding["review_revision"],
                         recorded_at),
                    )
                self._insert_event(
                    connection, record, action="draft", actor=actor,
                    reason=draft["grounds"], external_reference=None,
                    recorded_at=recorded_at,
                )
                result = self._details(connection, request_id)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def transition_takedown(
        self, request_id: str, *, action: str, expected_revision: int,
        actor: str, reason: str, external_reference: str | None,
        recorded_at: str,
    ) -> TakedownDetails:
        request_id = normalize_takedown_id(request_id)
        actor, reason, recorded_at = normalize_actor(actor), normalize_reason(reason), _time(recorded_at)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValidationError("Beklenen takedown sürümü sıfır veya daha büyük olmalı.")
        if action not in {"approve", "submit", "acknowledge", "resolve", "reject", "cancel"}:
            raise ValidationError("Takedown işlemi desteklenmiyor.")
        if external_reference is not None:
            external_reference = normalize_external_reference(external_reference)
        if action == "submit" and external_reference is None:
            raise ValidationError("Gönderildi işareti için dış başvuru referansı gerekli.")
        if action in {"approve", "cancel"} and external_reference is not None:
            raise ValidationError("Bu takedown geçişinde dış başvuru referansı kullanılmaz.")
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._details(connection, request_id).request
                if current.revision != expected_revision:
                    raise ValidationError("Takedown kaydı değişmiş; güncel sürümü yeniden alın.")
                if action in {"approve", "submit"}:
                    case = SQLiteCaseRepository._get_case(connection, current.case_id)
                    if case.status == "closed":
                        raise ValidationError(
                            "Kapalı vakada takedown onayı veya gönderim kaydı yapılamaz."
                        )
                if action in {"approve", "submit"}:
                    evidence_row = connection.execute(
                        f"SELECT {_EVIDENCE_COLUMNS} FROM case_evidence WHERE id=?",
                        (current.evidence_link_id,),
                    ).fetchone()
                    if evidence_row is None:
                        raise StorageError(
                            "Takedown kanıt bağı bulunamadı; onay güvenli biçimde durduruldu."
                        )
                    evidence = SQLiteCaseRepository._evidence(evidence_row)
                    if (not evidence.active or evidence.case_id != current.case_id
                            or evidence.snapshot_sha256 != current.evidence_sha256):
                        raise ValidationError(
                            "Takedown kanıtı artık etkin veya güncel değil; yeni taslak hazırlayın."
                        )
                    link = connection.execute(
                        "SELECT candidate_id,candidate_evidence_sha256,review_revision "
                        "FROM action_contact_takedown_links WHERE takedown_id=?", (request_id,),
                    ).fetchone()
                    if link is not None:
                        _kind, _target, _recipient, binding = self._approved_contact(
                            connection, link[0], current.case_id, current.evidence_link_id,
                        )
                        if (
                            binding["candidate_evidence_sha256"] != link[1]
                            or binding["review_revision"] != link[2]
                            or current.recipient != _recipient
                        ):
                            raise ValidationError(
                                "Takedown abuse iletişim adayı değişti; yeni taslak hazırlayın."
                            )
                state = next_takedown_state(current.state, action)
                revision = current.revision + 1
                approved_by = actor if action == "approve" else current.approved_by
                approved_at = recorded_at if action == "approve" else current.approved_at
                reference = external_reference or current.external_reference
                connection.execute(
                    "UPDATE action_takedowns SET state=?,revision=?,approved_by=?,"
                    "approved_at=?,external_reference=?,updated_at=? WHERE id=?",
                    (state, revision, approved_by, approved_at, reference,
                     recorded_at, request_id),
                )
                row = connection.execute(
                    f"SELECT {_TAKEDOWN_COLUMNS} FROM action_takedowns WHERE id=?",
                    (request_id,),
                ).fetchone()
                record = self._takedown(row)
                self._insert_event(
                    connection, record, action=action, actor=actor, reason=reason,
                    external_reference=reference, recorded_at=recorded_at,
                )
                result = self._details(connection, request_id)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def takedown_show(self, request_id: str) -> TakedownDetails:
        request_id = normalize_takedown_id(request_id)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            result = self._details(connection, request_id)
            connection.rollback()
        return result

    def takedown_list(
        self, *, case_id: str | None, state: str | None,
        offset: int, limit: int,
    ) -> tuple[TakedownRequest, ...]:
        if case_id is not None:
            case_id = normalize_case_id(case_id)
        if state is not None and state not in {
            "draft", "approved", "submitted", "acknowledged", "resolved", "rejected", "cancelled",
        }:
            raise ValidationError("Takedown durum filtresi geçersiz.")
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Takedown sayfalama değerleri geçersiz.")
        clauses, values = [], []
        if case_id is not None:
            clauses.append("case_id=?"); values.append(case_id)
        if state is not None:
            clauses.append("state=?"); values.append(state)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                f"SELECT {_TAKEDOWN_COLUMNS} FROM action_takedowns{where} "
                "ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",
                (*values, limit, offset),
            ).fetchall()
            records = tuple(self._details(connection, row[0]).request for row in rows)
            connection.rollback()
        return records
