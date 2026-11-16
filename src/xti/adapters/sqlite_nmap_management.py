"""Transactional Nmap target inventory and immutable dry-run plans."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.nmap_management import (
    NMAP_TARGET_ACTIONS,
    ManagedNmapPlan,
    ManagedNmapPlanDefinition,
    ManagedNmapPlanMutation,
    NmapTargetDefinition,
    NmapTargetScope,
    NmapTargetScopeDetails,
    NmapTargetScopeEvent,
    NmapTargetScopeMutation,
    canonical_managed_plan_json,
    canonical_target_definition_json,
    managed_plan_sha256,
    normalize_authorization_reason,
    normalize_lifecycle_reason,
    normalize_managed_plan_definition,
    normalize_target_definition,
    normalize_target_name,
    parse_managed_plan_json,
    parse_target_definition_json,
    target_definition_sha256,
    target_name_key,
)


_MAX_TARGET_SCOPES = 10_000
_MAX_TARGET_EVENTS = 100_000
_MAX_PLANS = 100_000
_TARGET_COLUMNS = (
    "id, asset_id, name_key, display_name, revision, definition_json, "
    "definition_sha256, active, authorization_reason, created_at, updated_at"
)
_EVENT_COLUMNS = (
    "sequence, id, target_scope_id, action, revision, display_name, definition_json, "
    "definition_sha256, reason, recorded_at"
)
_PLAN_COLUMNS = (
    "sequence, id, asset_id, target_scope_id, target_scope_revision, "
    "target_definition_sha256, definition_json, plan_sha256, created_at"
)


def _time(value: object) -> str:
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 64:
            raise ValueError("invalid timestamp")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("Nmap yönetim zamanı saat dilimi bilgili olmalı.") from error


def _positive(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError("invalid positive integer")
    return value


def _limit(value: object, maximum: int = 500) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValidationError(f"Nmap sonuç sınırı 1–{maximum} arasında olmalı.")
    return value


class SQLiteNmapManagementRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _target(row, asset_values: dict[str, str]) -> NmapTargetScope:
        try:
            target_id = normalize_knowledge_id(row[0], field="Nmap hedef kapsamı kimliği")
            asset_id = normalize_knowledge_id(row[1], field="Nmap varlık kimliği")
            display_name = normalize_target_name(row[3])
            definition = parse_target_definition_json(row[5])
            authorization_reason = normalize_authorization_reason(row[8])
            created_at, updated_at = _time(row[9]), _time(row[10])
            if (
                asset_id not in asset_values or row[2] != target_name_key(display_name)
                or row[3] != display_name
                or row[6] != target_definition_sha256(definition)
                or type(row[7]) is not int or row[7] not in {0, 1}
                or authorization_reason != row[8]
                or created_at != row[9] or updated_at != row[10]
                or datetime.fromisoformat(created_at) > datetime.fromisoformat(updated_at)
            ):
                raise ValueError("non-canonical target scope")
            return NmapTargetScope(
                target_id, asset_id, asset_values[asset_id], row[2], display_name,
                _positive(row[4]), definition, row[6], bool(row[7]),
                authorization_reason, created_at, updated_at,
            )
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageError("Nmap hedef kapsamı kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row) -> NmapTargetScopeEvent:
        try:
            action = row[3]
            definition = parse_target_definition_json(row[6])
            display_name = normalize_target_name(row[5])
            recorded_at = _time(row[9])
            if action not in NMAP_TARGET_ACTIONS or row[5] != display_name:
                raise ValueError("invalid target event")
            reason = (
                normalize_lifecycle_reason(row[8]) if action == "revoked"
                else normalize_authorization_reason(row[8])
            )
            if (
                reason != row[8] or row[7] != target_definition_sha256(definition)
                or recorded_at != row[9]
            ):
                raise ValueError("non-canonical target event")
            return NmapTargetScopeEvent(
                _positive(row[0]),
                normalize_knowledge_id(row[1], field="Nmap hedef olayı kimliği"),
                normalize_knowledge_id(row[2], field="Nmap hedef kapsamı kimliği"),
                action, _positive(row[4]), display_name, definition, row[7], reason,
                recorded_at,
            )
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageError("Nmap hedef kapsamı geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _plan(row, targets, event_lookup) -> ManagedNmapPlan:
        try:
            _positive(row[0])
            plan_id = normalize_knowledge_id(row[1], field="Nmap plan kimliği")
            asset_id = normalize_knowledge_id(row[2], field="Nmap varlık kimliği")
            target_id = normalize_knowledge_id(row[3], field="Nmap hedef kapsamı kimliği")
            revision = _positive(row[4])
            definition = parse_managed_plan_json(row[6])
            created_at = _time(row[8])
            target = targets.get(target_id)
            event = event_lookup.get((target_id, revision))
            if (
                target is None or event is None or target.asset_id != asset_id
                or definition.target_scope_id != target_id
                or definition.target_scope_revision != revision
                or definition.target_definition != event.definition
                or definition.target_definition_sha256 != event.definition_sha256
                or row[5] != event.definition_sha256
                or row[7] != managed_plan_sha256(definition)
                or created_at != row[8]
                or datetime.fromisoformat(created_at) < datetime.fromisoformat(event.recorded_at)
            ):
                raise ValueError("non-canonical managed plan")
            return ManagedNmapPlan(
                plan_id, asset_id, target.asset_value, event.display_name,
                definition, row[7], created_at,
            )
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageError("Yönetilen Nmap plan kaydı bozuk; işlem durduruldu.") from error

    @classmethod
    def _audit(cls, connection):
        try:
            asset_values = {
                normalize_knowledge_id(asset_id, field="Nmap varlık kimliği"):
                    normalize_domain(asset_value)
                for asset_id, asset_value in connection.execute(
                    "SELECT asset_id, asset_value FROM surface_scopes ORDER BY asset_id"
                ).fetchall()
            }
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageError(
                "Nmap dış yüzey bağlantısı bozuk; işlem durduruldu."
            ) from error
        target_rows = connection.execute(
            f"SELECT {_TARGET_COLUMNS} FROM surface_nmap_target_scopes ORDER BY id LIMIT ?",
            (_MAX_TARGET_SCOPES + 1,),
        ).fetchall()
        event_rows = connection.execute(
            f"SELECT {_EVENT_COLUMNS} FROM surface_nmap_target_scope_events "
            "ORDER BY sequence LIMIT ?", (_MAX_TARGET_EVENTS + 1,),
        ).fetchall()
        plan_rows = connection.execute(
            f"SELECT {_PLAN_COLUMNS} FROM surface_nmap_plans ORDER BY sequence LIMIT ?",
            (_MAX_PLANS + 1,),
        ).fetchall()
        if (
            len(target_rows) > _MAX_TARGET_SCOPES
            or len(event_rows) > _MAX_TARGET_EVENTS or len(plan_rows) > _MAX_PLANS
        ):
            raise StorageError("Nmap yönetim geçmişi güvenli okuma sınırını aşıyor.")
        targets = {target.id: target for target in (
            cls._target(row, asset_values) for row in target_rows
        )}
        events = tuple(cls._event(row) for row in event_rows)
        histories: dict[str, list[NmapTargetScopeEvent]] = {key: [] for key in targets}
        for event in events:
            if event.target_scope_id not in histories:
                raise StorageError("Nmap hedef geçmişinde kopuk bağlantı bulundu.")
            histories[event.target_scope_id].append(event)
        event_lookup = {}
        for target in targets.values():
            history = histories[target.id]
            active = False
            previous = None
            authorization_reason = None
            for revision, event in enumerate(history, 1):
                event_lookup[(target.id, event.revision)] = event
                invalid = (
                    event.revision != revision
                    or target_name_key(event.display_name) != target.name_key
                    or (previous is None and event.action != "added")
                    or (previous is not None and event.action == "added")
                )
                if previous is not None:
                    invalid = invalid or (
                        datetime.fromisoformat(event.recorded_at)
                        < datetime.fromisoformat(previous.recorded_at)
                        or (active and event.action not in {"updated", "revoked"})
                        or (not active and event.action != "reactivated")
                        or (
                            event.action == "revoked"
                            and (
                                event.display_name != previous.display_name
                                or event.definition != previous.definition
                            )
                        )
                        or (
                            event.action == "updated"
                            and event.display_name == previous.display_name
                            and event.definition == previous.definition
                            and event.reason == authorization_reason
                        )
                    )
                if invalid:
                    raise StorageError("Nmap hedef yaşam döngüsü bozuk; işlem durduruldu.")
                if event.action != "revoked":
                    authorization_reason = event.reason
                active = event.action != "revoked"
                previous = event
            if (
                previous is None or authorization_reason is None
                or target.revision != previous.revision
                or target.display_name != previous.display_name
                or target.definition != previous.definition
                or target.definition_sha256 != previous.definition_sha256
                or target.active != active
                or target.authorization_reason != authorization_reason
                or target.created_at != history[0].recorded_at
                or target.updated_at != previous.recorded_at
            ):
                raise StorageError("Nmap hedef güncel kaydı geçmişiyle uyuşmuyor.")
        plans = tuple(cls._plan(row, targets, event_lookup) for row in plan_rows)
        return targets, events, plans

    @staticmethod
    def _surface(connection, asset_id: str, asset_value: str, *, active: bool) -> None:
        row = connection.execute(
            "SELECT asset_value, active FROM surface_scopes WHERE asset_id=?", (asset_id,),
        ).fetchone()
        if row is None or row[0] != asset_value or (active and row[1] != 1):
            raise ValidationError("Etkin ve kayıtlı dış yüzey kapsamı bulunamadı.")

    @staticmethod
    def _find(targets, asset_id: str, name_key: str) -> NmapTargetScope:
        for target in targets.values():
            if target.asset_id == asset_id and target.name_key == name_key:
                return target
        raise ValidationError("Nmap hedef kapsamı bulunamadı.")

    @staticmethod
    def _check_time(previous: NmapTargetScope, recorded_at: str) -> None:
        if datetime.fromisoformat(recorded_at) < datetime.fromisoformat(previous.updated_at):
            raise ValidationError("Nmap kayıt zamanı son değişiklikten önce olamaz.")

    @staticmethod
    def _append_event(connection, target: NmapTargetScope, action: str, reason: str) -> None:
        connection.execute(
            "INSERT INTO surface_nmap_target_scope_events "
            "(id, target_scope_id, action, revision, display_name, definition_json, "
            "definition_sha256, reason, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()), target.id, action, target.revision, target.display_name,
                canonical_target_definition_json(target.definition), target.definition_sha256,
                reason, target.updated_at,
            ),
        )

    def save_target(
        self,
        asset_id: str,
        asset_value: str,
        display_name: str,
        definition: NmapTargetDefinition,
        authorization_reason: str,
        *,
        recorded_at: str,
    ) -> NmapTargetScopeMutation:
        asset_id = normalize_knowledge_id(asset_id, field="Nmap varlık kimliği")
        asset_value = normalize_domain(asset_value)
        display_name = normalize_target_name(display_name)
        name_key = target_name_key(display_name)
        definition = normalize_target_definition(definition)
        authorization_reason = normalize_authorization_reason(authorization_reason)
        recorded_at = _time(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                targets, events, _plans = self._audit(connection)
                self._surface(connection, asset_id, asset_value, active=True)
                previous = next((
                    target for target in targets.values()
                    if target.asset_id == asset_id and target.name_key == name_key
                ), None)
                if previous is not None:
                    self._check_time(previous, recorded_at)
                    if (
                        previous.active and previous.display_name == display_name
                        and previous.definition == definition
                        and previous.authorization_reason == authorization_reason
                    ):
                        connection.commit()
                        return NmapTargetScopeMutation("unchanged", previous)
                if (
                    len(events) >= _MAX_TARGET_EVENTS
                    or (previous is None and len(targets) >= _MAX_TARGET_SCOPES)
                ):
                    raise StorageError("Nmap hedef kapsamı kayıt sınırına ulaştı.")
                target = NmapTargetScope(
                    previous.id if previous else str(uuid4()), asset_id, asset_value,
                    name_key, display_name, previous.revision + 1 if previous else 1,
                    definition, target_definition_sha256(definition), True,
                    authorization_reason, previous.created_at if previous else recorded_at,
                    recorded_at,
                )
                action = "added" if previous is None else "updated" if previous.active else "reactivated"
                if previous is None:
                    connection.execute(
                        f"INSERT INTO surface_nmap_target_scopes ({_TARGET_COLUMNS}) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                        (
                            target.id, target.asset_id, target.name_key, target.display_name,
                            target.revision, canonical_target_definition_json(target.definition),
                            target.definition_sha256, target.authorization_reason,
                            target.created_at, target.updated_at,
                        ),
                    )
                else:
                    connection.execute(
                        "UPDATE surface_nmap_target_scopes SET display_name=?, revision=?, "
                        "definition_json=?, definition_sha256=?, active=1, "
                        "authorization_reason=?, updated_at=? WHERE id=?",
                        (
                            target.display_name, target.revision,
                            canonical_target_definition_json(target.definition),
                            target.definition_sha256, target.authorization_reason,
                            target.updated_at, target.id,
                        ),
                    )
                self._append_event(connection, target, action, authorization_reason)
                self._audit(connection)
                connection.commit()
                return NmapTargetScopeMutation(action, target)
            except BaseException:
                connection.rollback()
                raise

    def revoke_target(
        self,
        asset_id: str,
        name: str,
        *,
        reason: str,
        recorded_at: str,
    ) -> NmapTargetScopeMutation:
        asset_id = normalize_knowledge_id(asset_id, field="Nmap varlık kimliği")
        name_key = target_name_key(name)
        reason = normalize_lifecycle_reason(reason)
        recorded_at = _time(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                targets, events, _plans = self._audit(connection)
                previous = self._find(targets, asset_id, name_key)
                self._check_time(previous, recorded_at)
                if not previous.active:
                    connection.commit()
                    return NmapTargetScopeMutation("unchanged", previous)
                if len(events) >= _MAX_TARGET_EVENTS:
                    raise StorageError("Nmap hedef kapsamı geçmişi kayıt sınırına ulaştı.")
                target = NmapTargetScope(
                    previous.id, previous.asset_id, previous.asset_value, previous.name_key,
                    previous.display_name, previous.revision + 1, previous.definition,
                    previous.definition_sha256, False, previous.authorization_reason,
                    previous.created_at, recorded_at,
                )
                connection.execute(
                    "UPDATE surface_nmap_target_scopes SET revision=?, active=0, updated_at=? "
                    "WHERE id=?", (target.revision, recorded_at, target.id),
                )
                self._append_event(connection, target, "revoked", reason)
                self._audit(connection)
                connection.commit()
                return NmapTargetScopeMutation("revoked", target)
            except BaseException:
                connection.rollback()
                raise

    def get_target(self, asset_id: str, name: str) -> NmapTargetScope:
        asset_id = normalize_knowledge_id(asset_id, field="Nmap varlık kimliği")
        name_key = target_name_key(name)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            targets, _events, _plans = self._audit(connection)
            return self._find(targets, asset_id, name_key)

    def list_targets(
        self, asset_id: str, *, active_only: bool = True, limit: int = 100,
    ) -> tuple[NmapTargetScope, ...]:
        asset_id = normalize_knowledge_id(asset_id, field="Nmap varlık kimliği")
        limit = _limit(limit)
        if type(active_only) is not bool:
            raise ValidationError("Nmap hedef etkinlik filtresi geçersiz.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            targets, _events, _plans = self._audit(connection)
            return tuple(sorted(
                (
                    target for target in targets.values()
                    if target.asset_id == asset_id and (target.active or not active_only)
                ),
                key=lambda target: (target.name_key, target.id),
            )[:limit])

    def target_details(
        self, asset_id: str, name: str, *, event_limit: int = 50,
    ) -> NmapTargetScopeDetails:
        asset_id = normalize_knowledge_id(asset_id, field="Nmap varlık kimliği")
        name_key = target_name_key(name)
        event_limit = _limit(event_limit)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            targets, events, plans = self._audit(connection)
            target = self._find(targets, asset_id, name_key)
            history = tuple(
                event for event in reversed(events) if event.target_scope_id == target.id
            )
            return NmapTargetScopeDetails(
                target, history[:event_limit], len(history),
                sum(plan.definition.target_scope_id == target.id for plan in plans),
            )

    def save_plan(
        self,
        asset_id: str,
        asset_value: str,
        definition: ManagedNmapPlanDefinition,
        *,
        recorded_at: str,
    ) -> ManagedNmapPlanMutation:
        asset_id = normalize_knowledge_id(asset_id, field="Nmap varlık kimliği")
        asset_value = normalize_domain(asset_value)
        definition = normalize_managed_plan_definition(definition)
        recorded_at = _time(recorded_at)
        plan_hash = managed_plan_sha256(definition)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                targets, _events, plans = self._audit(connection)
                self._surface(connection, asset_id, asset_value, active=True)
                target = targets.get(definition.target_scope_id)
                if (
                    target is None or target.asset_id != asset_id or not target.active
                    or target.revision != definition.target_scope_revision
                    or target.definition != definition.target_definition
                    or target.definition_sha256 != definition.target_definition_sha256
                ):
                    raise ValidationError(
                        "Nmap planı güncel ve etkin hedef kapsamıyla uyuşmuyor."
                    )
                previous = next((
                    plan for plan in plans
                    if plan.asset_id == asset_id and plan.plan_sha256 == plan_hash
                ), None)
                if previous is not None:
                    connection.commit()
                    return ManagedNmapPlanMutation("unchanged", previous)
                if len(plans) >= _MAX_PLANS:
                    raise StorageError("Yönetilen Nmap plan kayıt sınırına ulaştı.")
                plan = ManagedNmapPlan(
                    str(uuid4()), asset_id, asset_value, target.display_name,
                    definition, plan_hash, recorded_at,
                )
                connection.execute(
                    "INSERT INTO surface_nmap_plans "
                    "(id, asset_id, target_scope_id, target_scope_revision, "
                    "target_definition_sha256, definition_json, plan_sha256, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        plan.id, plan.asset_id, definition.target_scope_id,
                        definition.target_scope_revision,
                        definition.target_definition_sha256,
                        canonical_managed_plan_json(definition), plan.plan_sha256,
                        plan.created_at,
                    ),
                )
                self._audit(connection)
                connection.commit()
                return ManagedNmapPlanMutation("created", plan)
            except BaseException:
                connection.rollback()
                raise

    def get_plan(self, asset_id: str, plan_id: str) -> ManagedNmapPlan:
        asset_id = normalize_knowledge_id(asset_id, field="Nmap varlık kimliği")
        plan_id = normalize_knowledge_id(plan_id, field="Nmap plan kimliği")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            _targets, _events, plans = self._audit(connection)
            for plan in plans:
                if plan.asset_id == asset_id and plan.id == plan_id:
                    return plan
            raise ValidationError("Yönetilen Nmap planı bulunamadı.")

    def list_plans(
        self, asset_id: str, *, limit: int = 100,
    ) -> tuple[ManagedNmapPlan, ...]:
        asset_id = normalize_knowledge_id(asset_id, field="Nmap varlık kimliği")
        limit = _limit(limit)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            _targets, _events, plans = self._audit(connection)
            return tuple(
                plan for plan in reversed(plans) if plan.asset_id == asset_id
            )[:limit]
