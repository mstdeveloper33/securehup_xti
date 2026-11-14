"""Explicit organization links with atomic lifecycle and existing-target audits."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.organizations import (
    ORGANIZATION_ACTIONS, ORGANIZATION_LINK_ACTIONS, ORGANIZATION_TARGET_KINDS,
    Organization, OrganizationDetails, OrganizationEvent, OrganizationLink,
    OrganizationLinkDetails, OrganizationLinkEvent, OrganizationLinkMutation,
    OrganizationLinkView, OrganizationMutation, OrganizationPage,
    OrganizationTargetReference, OrganizationTargetSummary,
    decide_organization_change, decide_organization_link_change,
    normalize_organization_id, normalize_organization_name,
    normalize_organization_reason, normalize_organization_target,
)


_MAX_ORGANIZATIONS = 10_000
_MAX_LINKS = 50_000
_MAX_EVENTS = 100_000
_ORG = "id, name_key, display_name, revision, active, created_at, updated_at"
_EVENT = "sequence, id, organization_id, action, revision, name_key, display_name, reason, recorded_at"
_LINK = (
    "id, organization_id, target_kind, target_value, asset_id, username_watch_id, "
    "ransomware_watch_id, ransomlook_watch_id, revision, active, reason, created_at, updated_at"
)
_LINK_EVENT = "sequence, id, link_id, organization_id, action, revision, target_kind, target_value, reason, recorded_at"


def _time(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValidationError("Kuruluş kayıt zamanı geçersiz.")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone")
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError) as error:
        raise ValidationError("Kuruluş kayıt zamanı saat dilimli olmalı.") from error


def _positive(value):
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError("invalid revision or sequence")
    return value


def _active(value):
    if type(value) is not int or value not in {0, 1}:
        raise ValueError("invalid activity")
    return bool(value)


def _ordered(earlier, later):
    return datetime.fromisoformat(earlier) <= datetime.fromisoformat(later)


def _window(offset, limit):
    if type(offset) is not int or not 0 <= offset <= 1_000_000:
        raise ValidationError("Kuruluş görünüm başlangıcı geçersiz.")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValidationError("Kuruluş görünüm sınırı 1–500 arasında olmalı.")


@dataclass(frozen=True, slots=True)
class _StoredLink:
    link: OrganizationLink
    target_id: str


@dataclass
class _State:
    organizations: dict[str, Organization]
    events: tuple[OrganizationEvent, ...]
    links: dict[str, _StoredLink]
    link_events: tuple[OrganizationLinkEvent, ...]
    targets: dict[OrganizationTargetReference, tuple[str, OrganizationTargetSummary]]
    watch_registries: dict


class SQLiteOrganizationRepository:
    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _organization(row):
        try:
            name_key, display = normalize_organization_name(row[2])
            created, updated = _time(row[5]), _time(row[6])
            if (row[1], row[2], row[5], row[6]) != (name_key, display, created, updated) or not _ordered(created, updated):
                raise ValueError("noncanonical organization")
            return Organization(normalize_organization_id(row[0]), name_key, display,
                                _positive(row[3]), _active(row[4]), created, updated)
        except (ValueError, TypeError, OverflowError) as error:
            raise StorageError("Kuruluş kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row):
        try:
            name_key, display = normalize_organization_name(row[6])
            reason, recorded = normalize_organization_reason(row[7]), _time(row[8])
            if row[3] not in ORGANIZATION_ACTIONS or (row[5], row[6], row[7], row[8]) != (name_key, display, reason, recorded):
                raise ValueError("noncanonical event")
            return OrganizationEvent(_positive(row[0]), normalize_organization_id(row[1]),
                normalize_organization_id(row[2]), row[3], _positive(row[4]), name_key, display, reason, recorded)
        except (ValueError, TypeError, OverflowError) as error:
            raise StorageError("Kuruluş geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _link(row):
        try:
            target = normalize_organization_target(row[2], row[3])
            target_index = ORGANIZATION_TARGET_KINDS.index(target.kind)
            foreign_ids = row[4:8]
            target_id = normalize_organization_id(foreign_ids[target_index])
            reason, created, updated = normalize_organization_reason(row[10]), _time(row[11]), _time(row[12])
            if (
                target.value != row[3] or sum(value is not None for value in foreign_ids) != 1
                or (target.kind != "domain" and target_id != target.value)
                or (reason, created, updated) != (row[10], row[11], row[12])
                or not _ordered(created, updated)
            ):
                raise ValueError("noncanonical link")
            link = OrganizationLink(normalize_organization_id(row[0]), normalize_organization_id(row[1]),
                target, _positive(row[8]), _active(row[9]), reason, created, updated)
            return _StoredLink(link, target_id)
        except (ValueError, TypeError, OverflowError) as error:
            raise StorageError("Kuruluş bağlantısı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _link_event(row):
        try:
            target = normalize_organization_target(row[6], row[7])
            reason, recorded = normalize_organization_reason(row[8]), _time(row[9])
            if row[4] not in ORGANIZATION_LINK_ACTIONS or (target.value, reason, recorded) != (row[7], row[8], row[9]):
                raise ValueError("noncanonical link event")
            return OrganizationLinkEvent(_positive(row[0]), normalize_organization_id(row[1]),
                normalize_organization_id(row[2]), normalize_organization_id(row[3]), row[4],
                _positive(row[5]), target, reason, recorded)
        except (ValueError, TypeError, OverflowError) as error:
            raise StorageError("Kuruluş bağlantı geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _resolve_target(connection, reference, state):
        if reference in state.targets:
            return state.targets[reference]
        if reference.kind == "domain":
            row = connection.execute("SELECT id, value, created_at FROM assets WHERE value=?", (reference.value,)).fetchone()
            if row is None:
                raise ValidationError("Domain önce assets add ile kaydedilmeli.")
            try:
                target_id = normalize_organization_id(row[0])
                if normalize_domain(row[1]) != row[1] or _time(row[2]) != row[2]:
                    raise ValueError("invalid asset")
            except (ValueError, TypeError, OverflowError) as error:
                raise StorageError("Kuruluş hedef domain kaydı bozuk.") from error
            summary = OrganizationTargetSummary(reference, row[1], "asset", True)
        else:
            registries = {
                "username-watch": SQLiteBrandUsernameWatchRepository,
                "ransomware-watch": SQLiteRansomwareWatchRepository,
                "ransomlook-watch": SQLiteRansomLookWatchRepository,
            }
            if reference.kind not in state.watch_registries:
                state.watch_registries[reference.kind] = registries[reference.kind]._audit(connection)[0]
            watch = state.watch_registries[reference.kind].get(reference.value)
            if watch is None:
                raise ValidationError("Seçilen türde kayıtlı izleme bulunamadı.")
            target_id = watch.id
            source = watch.source_key if reference.kind == "username-watch" else (
                "threatcluster" if reference.kind == "ransomware-watch" else "ransomlook"
            )
            summary = OrganizationTargetSummary(reference, watch.display_name, source, watch.active)
        state.targets[reference] = (target_id, summary)
        return target_id, summary

    @classmethod
    def _audit(cls, connection):
        specs = (
            ("organizations", _ORG, "id", _MAX_ORGANIZATIONS, cls._organization),
            ("organization_events", _EVENT, "sequence", _MAX_EVENTS, cls._event),
            ("organization_links", _LINK, "id", _MAX_LINKS, cls._link),
            ("organization_link_events", _LINK_EVENT, "sequence", _MAX_EVENTS, cls._link_event),
        )
        loaded = []
        for table, columns, ordering, maximum, loader in specs:
            rows = connection.execute(f"SELECT {columns} FROM {table} ORDER BY {ordering} LIMIT ?", (maximum + 1,)).fetchall()
            if len(rows) > maximum:
                raise StorageError("Kuruluş geçmişi güvenli okuma sınırını aşıyor.")
            loaded.append(tuple(loader(row) for row in rows))
        organizations = {item.id: item for item in loaded[0]}
        links = {item.link.id: item for item in loaded[2]}
        state = _State(organizations, loaded[1], links, loaded[3], {}, {})
        histories = {key: [] for key in organizations}
        link_histories = {key: [] for key in links}
        for event in state.events:
            if event.organization_id not in histories:
                raise StorageError("Kuruluş geçmişinde kopuk bağlantı var.")
            histories[event.organization_id].append(event)
        for event in state.link_events:
            if event.link_id not in link_histories:
                raise StorageError("Kuruluş bağlantı geçmişinde kopuk kayıt var.")
            link_histories[event.link_id].append(event)
        try:
            for organization in organizations.values():
                previous = None
                for revision, event in enumerate(histories[organization.id], 1):
                    operation = {"added": "add", "renamed": "rename", "revoked": "revoke", "reactivated": "reactivate"}[event.action]
                    decision = decide_organization_change(previous, operation, name=event.display_name)
                    if (
                        event.revision != revision or event.action != decision.action
                        or (event.name_key, event.display_name) != (decision.name_key, decision.display_name)
                        or (previous is not None and not _ordered(previous.updated_at, event.recorded_at))
                    ):
                        raise ValueError("organization lifecycle")
                    previous = Organization(organization.id, event.name_key, event.display_name,
                        revision, decision.active, previous.created_at if previous else event.recorded_at, event.recorded_at)
                if previous != organization:
                    raise ValueError("organization current state")
            for stored in links.values():
                link = stored.link
                organization = organizations.get(link.organization_id)
                if organization is None or not _ordered(organization.created_at, link.created_at):
                    raise ValueError("link organization")
                previous = None
                for revision, event in enumerate(link_histories[link.id], 1):
                    if event.organization_id != link.organization_id or event.target != link.target:
                        raise ValueError("link event identity")
                    decision = decide_organization_link_change(previous, link_requested=event.action != "revoked",
                        reason=event.reason, organization_active=True, target_active=True)
                    if event.revision != revision or decision.action != event.action or (
                        previous is not None and not _ordered(previous.updated_at, event.recorded_at)
                    ):
                        raise ValueError("link lifecycle")
                    previous = OrganizationLink(link.id, link.organization_id, link.target, revision,
                        decision.active, decision.reason, previous.created_at if previous else event.recorded_at, event.recorded_at)
                if previous != link:
                    raise ValueError("link current state")
                target_id, _summary = cls._resolve_target(connection, link.target, state)
                if target_id != stored.target_id:
                    raise ValueError("link target foreign key")
        except (ValueError, TypeError, OverflowError) as error:
            raise StorageError("Kuruluş veya bağlantı geçmişi mevcut kayıtla uyuşmuyor.") from error
        return state

    @contextmanager
    def _write(self):
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                state = self._audit(connection)
                yield connection, state
                self._audit(connection)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _check_time(recorded_at, previous_at):
        if not _ordered(previous_at, recorded_at):
            raise ValidationError("Kuruluş kayıt zamanı son değişiklikten önce olamaz.")

    @staticmethod
    def _organization_by_id(state, organization_id):
        if organization_id not in state.organizations:
            raise ValidationError("Kuruluş bulunamadı.")
        return state.organizations[organization_id]

    @staticmethod
    def _link_by_id(state, organization_id, link_id):
        if link_id not in state.links or state.links[link_id].link.organization_id != organization_id:
            raise ValidationError("Bu kuruluşa ait bağlantı bulunamadı.")
        return state.links[link_id]

    @staticmethod
    def _append_event(connection, record, action, reason):
        connection.execute(
            "INSERT INTO organization_events (id, organization_id, action, revision, name_key, display_name, reason, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid4()), record.id, action, record.revision, record.name_key, record.display_name, reason, record.updated_at),
        )

    @staticmethod
    def _append_link_event(connection, record, action):
        connection.execute(
            "INSERT INTO organization_link_events (id, link_id, organization_id, action, revision, target_kind, target_value, reason, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid4()), record.id, record.organization_id, action, record.revision,
             record.target.kind, record.target.value, record.reason, record.updated_at),
        )

    def _change_organization(self, operation, organization_id, *, name_key=None, display_name=None, reason, recorded_at):
        reason, recorded_at = normalize_organization_reason(reason), _time(recorded_at)
        if operation in {"add", "rename"}:
            normalized_key, display_name = normalize_organization_name(display_name)
            if name_key != normalized_key:
                raise ValidationError("Kuruluş adı anahtarı geçersiz.")
        if organization_id is not None:
            organization_id = normalize_organization_id(organization_id)
        with self._write() as (connection, state):
            previous = (next((item for item in state.organizations.values() if item.name_key == name_key), None)
                        if operation == "add" else self._organization_by_id(state, organization_id))
            if previous is not None:
                self._check_time(recorded_at, previous.updated_at)
            decision = decide_organization_change(previous, operation, name=display_name)
            if decision.action == "unchanged":
                return OrganizationMutation("unchanged", previous)
            if any(item.name_key == decision.name_key and (previous is None or item.id != previous.id)
                   for item in state.organizations.values()):
                raise ValidationError("Bu kuruluş adı zaten kayıtlı.")
            if len(state.events) >= _MAX_EVENTS or (previous is None and len(state.organizations) >= _MAX_ORGANIZATIONS):
                raise StorageError("Kuruluş geçmişi güvenli kayıt sınırına ulaştı.")
            record = Organization(previous.id if previous else str(uuid4()), decision.name_key, decision.display_name,
                previous.revision + 1 if previous else 1, decision.active,
                previous.created_at if previous else recorded_at, recorded_at)
            if previous is None:
                connection.execute(f"INSERT INTO organizations ({_ORG}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (record.id, record.name_key, record.display_name, record.revision, int(record.active), record.created_at, recorded_at))
            else:
                connection.execute("UPDATE organizations SET name_key=?, display_name=?, revision=?, active=?, updated_at=? WHERE id=?",
                    (record.name_key, record.display_name, record.revision, int(record.active), recorded_at, record.id))
            self._append_event(connection, record, decision.action, reason)
            return OrganizationMutation(decision.action, record)

    def add(self, *, name_key, display_name, reason, recorded_at):
        return self._change_organization("add", None, name_key=name_key, display_name=display_name, reason=reason, recorded_at=recorded_at)

    def rename(self, organization_id, *, name_key, display_name, reason, recorded_at):
        return self._change_organization("rename", organization_id, name_key=name_key, display_name=display_name, reason=reason, recorded_at=recorded_at)

    def revoke(self, organization_id, *, reason, recorded_at):
        return self._change_organization("revoke", organization_id, reason=reason, recorded_at=recorded_at)

    def reactivate(self, organization_id, *, reason, recorded_at):
        return self._change_organization("reactivate", organization_id, reason=reason, recorded_at=recorded_at)

    def link(self, organization_id, target, *, reason, recorded_at):
        organization_id = normalize_organization_id(organization_id)
        if not isinstance(target, OrganizationTargetReference) or normalize_organization_target(target.kind, target.value) != target:
            raise ValidationError("Geçerli kanonik kuruluş hedefi gerekli.")
        reason, recorded_at = normalize_organization_reason(reason), _time(recorded_at)
        with self._write() as (connection, state):
            organization = self._organization_by_id(state, organization_id)
            target_id, summary = self._resolve_target(connection, target, state)
            previous = next((stored.link for stored in state.links.values()
                             if stored.link.organization_id == organization_id and stored.link.target == target), None)
            self._check_time(recorded_at, organization.updated_at)
            if previous is not None:
                self._check_time(recorded_at, previous.updated_at)
            decision = decide_organization_link_change(previous, link_requested=True, reason=reason,
                organization_active=organization.active, target_active=summary.active)
            if decision.action == "unchanged":
                return OrganizationLinkMutation("unchanged", previous)
            if len(state.link_events) >= _MAX_EVENTS or (previous is None and len(state.links) >= _MAX_LINKS):
                raise StorageError("Kuruluş bağlantı geçmişi güvenli kayıt sınırına ulaştı.")
            record = OrganizationLink(previous.id if previous else str(uuid4()), organization_id, target,
                previous.revision + 1 if previous else 1, True, reason,
                previous.created_at if previous else recorded_at, recorded_at)
            if previous is None:
                foreign_ids = [None] * 4
                foreign_ids[ORGANIZATION_TARGET_KINDS.index(target.kind)] = target_id
                connection.execute(f"INSERT INTO organization_links ({_LINK}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (record.id, organization_id, target.kind, target.value, *foreign_ids, record.revision,
                     1, reason, record.created_at, recorded_at))
            else:
                connection.execute("UPDATE organization_links SET revision=?, active=1, reason=?, updated_at=? WHERE id=?",
                    (record.revision, reason, recorded_at, record.id))
            self._append_link_event(connection, record, decision.action)
            return OrganizationLinkMutation(decision.action, record)

    def unlink(self, organization_id, link_id, *, reason, recorded_at):
        organization_id, link_id = normalize_organization_id(organization_id), normalize_organization_id(link_id)
        reason, recorded_at = normalize_organization_reason(reason), _time(recorded_at)
        with self._write() as (connection, state):
            organization = self._organization_by_id(state, organization_id)
            previous = self._link_by_id(state, organization_id, link_id).link
            self._check_time(recorded_at, previous.updated_at)
            summary = state.targets[previous.target][1]
            decision = decide_organization_link_change(previous, link_requested=False, reason=reason,
                organization_active=organization.active, target_active=summary.active)
            if decision.action == "unchanged":
                return OrganizationLinkMutation("unchanged", previous)
            if len(state.link_events) >= _MAX_EVENTS:
                raise StorageError("Kuruluş bağlantı geçmişi güvenli kayıt sınırına ulaştı.")
            record = OrganizationLink(previous.id, previous.organization_id, previous.target,
                previous.revision + 1, False, reason, previous.created_at, recorded_at)
            connection.execute("UPDATE organization_links SET revision=?, active=0, reason=?, updated_at=? WHERE id=?",
                (record.revision, reason, recorded_at, record.id))
            self._append_link_event(connection, record, decision.action)
            return OrganizationLinkMutation(decision.action, record)

    def list(self, *, active_only=True, offset=0, limit=100):
        _window(offset, limit)
        if type(active_only) is not bool:
            raise ValidationError("Kuruluş etkinlik filtresi geçersiz.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            state = self._audit(connection)
            records = sorted((item for item in state.organizations.values() if not active_only or item.active),
                             key=lambda item: (item.name_key, item.id))
            return OrganizationPage(tuple(records[offset:offset + limit]), len(records), offset, limit)

    def show(self, organization_id, *, active_links_only=False, link_offset=0, link_limit=100, event_limit=50):
        organization_id = normalize_organization_id(organization_id)
        _window(link_offset, link_limit)
        _window(0, event_limit)
        if type(active_links_only) is not bool:
            raise ValidationError("Bağlantı etkinlik filtresi geçersiz.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            state = self._audit(connection)
            organization = self._organization_by_id(state, organization_id)
            events = tuple(event for event in reversed(state.events) if event.organization_id == organization_id)
            links = sorted((stored.link for stored in state.links.values() if stored.link.organization_id == organization_id
                            and (not active_links_only or stored.link.active)), key=lambda item: (item.target.kind, item.target.value, item.id))
            views = tuple(OrganizationLinkView(link, state.targets[link.target][1]) for link in links[link_offset:link_offset + link_limit])
            return OrganizationDetails(organization, events[:event_limit], len(events), views, len(links), link_offset, link_limit)

    def show_link(self, organization_id, link_id, *, event_limit=50):
        organization_id, link_id = normalize_organization_id(organization_id), normalize_organization_id(link_id)
        _window(0, event_limit)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            state = self._audit(connection)
            self._organization_by_id(state, organization_id)
            link = self._link_by_id(state, organization_id, link_id).link
            events = tuple(event for event in reversed(state.link_events) if event.link_id == link_id)
            return OrganizationLinkDetails(OrganizationLinkView(link, state.targets[link.target][1]), events[:event_limit], len(events))
