"""Atomic SQLite history for bounded social username watches."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.brand_username import (
    ALL_PLATFORM_HOSTS,
    BRAND_USERNAME_SOURCE_NAMES,
    MAIGRET_PLATFORM_HOSTS,
    SHERLOCK_PLATFORM_HOSTS,
    BrandProfileMatch,
    BrandUsernamePreview,
    normalize_brand_username,
)
from xti.domain.brand_username_watches import (
    ITEM_ACTIONS,
    ITEM_STATUSES,
    RUN_STATUSES,
    WATCH_ACTIONS,
    BrandUsernameWatch,
    BrandUsernameWatchDetails,
    BrandUsernameWatchEvent,
    BrandUsernameWatchMutation,
    BrandUsernameWatchRun,
    BrandUsernameWatchRunItem,
    BrandUsernameWatchRunReport,
    BrandUsernameWatchSummary,
    brand_watch_definition_sha256,
    brand_watch_item_state_sha256,
    brand_watch_name_key,
    normalize_brand_watch_name,
)
from xti.domain.cti_indicators import normalize_assertion_reason, normalize_cti_timestamp


_WATCH_SELECT = (
    "id, name_key, display_name, username, platforms_json, active, created_at, "
    "updated_at, source_key"
)
_EVENT_SELECT = "id, watch_id, action, definition_sha256, reason, recorded_at"
_RUN_SELECT = (
    "sequence, id, watch_id, status, source_name, source_version, integration_profile, "
    "username, platforms_json, definition_sha256, previous_complete_run_id, checked_at, "
    "recorded_at, platform_count, found_count, newly_found_count, changed_count, "
    "unchanged_found_count, no_longer_reported_count, unreported_count, result_sha256, error"
)
_ITEM_SELECT = (
    "id, run_id, platform, profile_url, result_status, action, state_sha256"
)
_MAX_WATCHES = 10_000
_MAX_EVENTS = 100_000
_MAX_RUNS = 100_000
_MAX_ITEMS = 1_000_000
_ITEM_ACTION_ORDER = (
    "newly_found",
    "changed",
    "no_longer_reported",
    "unchanged_found",
    "unchanged_unreported",
    "baseline_found",
    "baseline_unreported",
)
_FOUND_ACTIONS = frozenset({
    "baseline_found", "newly_found", "changed", "unchanged_found",
})
_UNREPORTED_ACTIONS = frozenset({
    "baseline_unreported", "no_longer_reported", "unchanged_unreported",
})


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    normalized = str(UUID(value))
    if value != normalized:
        raise ValueError("Non-canonical UUID")
    return normalized


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    normalized = normalize_cti_timestamp(value, field=field)
    if value != normalized:
        raise ValueError("Non-canonical timestamp")
    return normalized


def _sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("Invalid SHA-256")
    return value


def _visible_text(value: object, *, field: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(not character.isprintable() for character in value)
    ):
        raise ValueError(f"Invalid {field}")
    return value


def _platforms(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or len(value) > 1000:
        raise ValueError("Invalid platforms")
    parsed = json.loads(value)
    if (
        not isinstance(parsed, list)
        or not parsed
        or any(not isinstance(item, str) for item in parsed)
    ):
        raise ValueError("Invalid platforms")
    platforms = tuple(parsed)
    if (
        len(set(platforms)) != len(platforms)
        or any(item not in ALL_PLATFORM_HOSTS for item in platforms)
    ):
        raise ValueError("Non-canonical platforms")
    return platforms


def _platforms_json(platforms: tuple[str, ...]) -> str:
    return json.dumps(list(platforms), ensure_ascii=True, separators=(",", ":"))


def _profile_url(platform: str, value: object) -> str:
    url = _visible_text(value, field="profile URL", maximum=2048)
    parsed = urlsplit(url)
    hostname = parsed.hostname.rstrip(".").lower() if parsed.hostname else ""
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or not any(
            hostname == allowed or hostname.endswith(f".{allowed}")
            for allowed in ALL_PLATFORM_HOSTS[platform]
        )
    ):
        raise ValueError("Invalid profile URL")
    return url


def _result_sha(items: tuple[BrandUsernameWatchRunItem, ...] | list) -> str:
    payload = [
        {"platform": item.platform, "state_sha256": item.state_sha256}
        for item in sorted(items, key=lambda value: value.platform)
    ]
    canonical = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class SQLiteBrandUsernameWatchRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _definition(watch: BrandUsernameWatch) -> str:
        return brand_watch_definition_sha256(
            username=watch.username,
            platforms=watch.platforms,
        )

    @classmethod
    def _watch(cls, row) -> BrandUsernameWatch:
        try:
            watch_id = _uuid(row[0])
            display_name = normalize_brand_watch_name(row[2])
            username = normalize_brand_username(row[3])
            platforms = _platforms(row[4])
            source_key = row[8]
            source_platforms = {
                "maigret": MAIGRET_PLATFORM_HOSTS,
                "sherlock": SHERLOCK_PLATFORM_HOSTS,
            }.get(source_key)
            if (
                source_platforms is None
                or any(item not in source_platforms for item in platforms)
                or platforms != tuple(
                    item for item in source_platforms if item in platforms
                )
            ):
                raise ValueError("Invalid source platforms")
            if type(row[5]) is not int or row[5] not in {0, 1}:
                raise ValueError("Invalid activity")
            watch = BrandUsernameWatch(
                id=watch_id,
                name_key=brand_watch_name_key(display_name),
                display_name=display_name,
                username=username,
                platforms=platforms,
                source_key=source_key,
                active=bool(row[5]),
                created_at=_timestamp(row[6], field="Marka izleme oluşturma zamanı"),
                updated_at=_timestamp(row[7], field="Marka izleme güncelleme zamanı"),
            )
            if row[1] != watch.name_key:
                raise ValueError("Non-canonical name key")
            if datetime.fromisoformat(watch.created_at) > datetime.fromisoformat(
                watch.updated_at
            ):
                raise ValueError("Reversed watch time")
            return watch
        except (
            TypeError,
            ValueError,
            ValidationError,
            OverflowError,
            json.JSONDecodeError,
        ) as error:
            raise StorageError(
                "Sosyal kullanıcı adı izleme tanımı bozuk; işlem durduruldu."
            ) from error

    @classmethod
    def _event(cls, row, watches) -> BrandUsernameWatchEvent:
        try:
            event_id, watch_id = _uuid(row[0]), _uuid(row[1])
            if watch_id not in watches or row[2] not in WATCH_ACTIONS:
                raise ValueError("Invalid event")
            reason = row[4]
            if row[2] == "revoked":
                reason = normalize_assertion_reason(reason)
            elif reason != "":
                raise ValueError("Unexpected reason")
            return BrandUsernameWatchEvent(
                event_id,
                watch_id,
                row[2],
                _sha256(row[3]),
                reason,
                _timestamp(row[5], field="Marka izleme olay zamanı"),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError(
                "Sosyal kullanıcı adı izleme geçmişi bozuk; işlem durduruldu."
            ) from error

    @staticmethod
    def _run(row, watches) -> BrandUsernameWatchRun:
        try:
            if type(row[0]) is not int or row[0] < 1:
                raise ValueError("Invalid sequence")
            run_id, watch_id = _uuid(row[1]), _uuid(row[2])
            if watch_id not in watches or row[3] not in RUN_STATUSES:
                raise ValueError("Invalid run")
            if row[4] != BRAND_USERNAME_SOURCE_NAMES[watches[watch_id].source_key]:
                raise ValueError("Invalid run source")
            username = normalize_brand_username(row[7])
            platforms = _platforms(row[8])
            definition = _sha256(row[9])
            if definition != brand_watch_definition_sha256(
                username=username, platforms=platforms,
            ):
                raise ValueError("Invalid definition")
            previous = _uuid(row[10]) if row[10] is not None else None
            checked_at = (
                _timestamp(row[11], field="Marka kaynak kontrol zamanı")
                if row[11] is not None else None
            )
            counts = row[13:20]
            if any(type(value) is not int or value < 0 for value in counts):
                raise ValueError("Invalid counts")
            result_sha = _sha256(row[20]) if row[20] is not None else None
            error = row[21]
            if row[3] == "complete":
                if checked_at is None or result_sha is None or error is not None:
                    raise ValueError("Invalid complete run")
                if counts[0] != len(platforms) or counts[1] + counts[6] != counts[0]:
                    raise ValueError("Inconsistent complete counts")
            else:
                if (
                    checked_at is not None
                    or result_sha is not None
                    or counts[0] != len(platforms)
                    or any(counts[1:])
                ):
                    raise ValueError("Invalid failed run")
                error = _visible_text(error, field="source error", maximum=500)
            return BrandUsernameWatchRun(
                sequence=row[0],
                id=run_id,
                watch_id=watch_id,
                status=row[3],
                source_name=_visible_text(row[4], field="source name", maximum=100),
                source_version=_visible_text(row[5], field="source version", maximum=100),
                integration_profile=_visible_text(
                    row[6], field="integration profile", maximum=200,
                ),
                username=username,
                platforms=platforms,
                definition_sha256=definition,
                previous_complete_run_id=previous,
                checked_at=checked_at,
                recorded_at=_timestamp(row[12], field="Marka izleme kayıt zamanı"),
                platform_count=counts[0],
                found_count=counts[1],
                newly_found_count=counts[2],
                changed_count=counts[3],
                unchanged_found_count=counts[4],
                no_longer_reported_count=counts[5],
                unreported_count=counts[6],
                result_sha256=result_sha,
                error=error,
            )
        except (
            TypeError,
            ValueError,
            ValidationError,
            OverflowError,
            json.JSONDecodeError,
        ) as error:
            raise StorageError(
                "Sosyal kullanıcı adı izleme çalışması bozuk; işlem durduruldu."
            ) from error

    @staticmethod
    def _item(row, runs) -> BrandUsernameWatchRunItem:
        try:
            item_id, run_id = _uuid(row[0]), _uuid(row[1])
            run = runs.get(run_id)
            if run is None or run.status != "complete":
                raise ValueError("Missing complete run")
            platform = row[2]
            if platform not in run.platforms or row[4] not in ITEM_STATUSES:
                raise ValueError("Invalid platform status")
            if row[5] not in ITEM_ACTIONS:
                raise ValueError("Invalid action")
            if (
                row[4] == "found_unverified" and row[5] not in _FOUND_ACTIONS
            ) or (
                row[4] == "unreported" and row[5] not in _UNREPORTED_ACTIONS
            ):
                raise ValueError("Action and status disagree")
            profile_url = row[3]
            if row[4] == "found_unverified":
                profile_url = _profile_url(platform, profile_url)
            elif profile_url is not None:
                raise ValueError("Unexpected profile URL")
            state = _sha256(row[6])
            if state != brand_watch_item_state_sha256(
                platform=platform,
                status=row[4],
                profile_url=profile_url,
            ):
                raise ValueError("Invalid state")
            return BrandUsernameWatchRunItem(
                item_id,
                run_id,
                platform,
                profile_url,
                row[4],
                row[5],
                state,
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError(
                "Sosyal kullanıcı adı izleme sonucu bozuk; işlem durduruldu."
            ) from error

    @classmethod
    def _audit(cls, connection):
        watch_rows = connection.execute(
            f"SELECT {_WATCH_SELECT} FROM brand_username_watches ORDER BY id LIMIT ?",
            (_MAX_WATCHES + 1,),
        ).fetchall()
        if len(watch_rows) > _MAX_WATCHES:
            raise StorageError("Sosyal kullanıcı adı izleme sayısı güvenli sınırı aşıyor.")
        watches = {watch.id: watch for watch in map(cls._watch, watch_rows)}

        event_rows = connection.execute(
            f"SELECT {_EVENT_SELECT} FROM brand_username_watch_events ORDER BY rowid LIMIT ?",
            (_MAX_EVENTS + 1,),
        ).fetchall()
        if len(event_rows) > _MAX_EVENTS:
            raise StorageError("Sosyal kullanıcı adı izleme olayı sınırı aşıyor.")
        events = tuple(cls._event(row, watches) for row in event_rows)
        by_watch_events = {key: [] for key in watches}
        for event in events:
            by_watch_events[event.watch_id].append(event)
        for watch in watches.values():
            history = by_watch_events[watch.id]
            if (
                not history
                or history[0].action != "added"
                or history[-1].definition_sha256 != cls._definition(watch)
                or (watch.active and history[-1].action == "revoked")
                or (not watch.active and history[-1].action != "revoked")
                or history[0].recorded_at != watch.created_at
                or history[-1].recorded_at != watch.updated_at
                or any(
                    datetime.fromisoformat(left.recorded_at)
                    > datetime.fromisoformat(right.recorded_at)
                    for left, right in zip(history, history[1:])
                )
            ):
                raise StorageError(
                    "Sosyal kullanıcı adı izleme yaşam döngüsü bozuk."
                )

        run_rows = connection.execute(
            f"SELECT {_RUN_SELECT} FROM brand_username_watch_runs ORDER BY sequence LIMIT ?",
            (_MAX_RUNS + 1,),
        ).fetchall()
        if len(run_rows) > _MAX_RUNS:
            raise StorageError("Sosyal kullanıcı adı izleme çalışma sınırı aşıyor.")
        runs = {run.id: run for run in (cls._run(row, watches) for row in run_rows)}
        latest_complete = {}
        for run in sorted(runs.values(), key=lambda value: value.sequence):
            if run.definition_sha256 not in {
                event.definition_sha256 for event in by_watch_events[run.watch_id]
            }:
                raise StorageError("Sosyal kullanıcı adı çalışma tanımı bozuk.")
            key = (run.watch_id, run.definition_sha256)
            expected_previous = latest_complete.get(key)
            if run.previous_complete_run_id != expected_previous:
                raise StorageError("Sosyal kullanıcı adı çalışma zinciri bozuk.")
            if run.status == "complete":
                latest_complete[key] = run.id

        item_rows = connection.execute(
            f"SELECT {_ITEM_SELECT} FROM brand_username_watch_run_items "
            "ORDER BY run_id, platform LIMIT ?",
            (_MAX_ITEMS + 1,),
        ).fetchall()
        if len(item_rows) > _MAX_ITEMS:
            raise StorageError("Sosyal kullanıcı adı sonuç sınırı aşıyor.")
        items = tuple(cls._item(row, runs) for row in item_rows)
        by_run = {key: [] for key in runs}
        for item in items:
            by_run[item.run_id].append(item)
        for run in runs.values():
            selected = tuple(by_run[run.id])
            if run.status == "failed":
                if selected:
                    raise StorageError("Başarısız sosyal izleme çalışması sonuç içeriyor.")
                continue
            actions = {action: 0 for action in ITEM_ACTIONS}
            statuses = {status: 0 for status in ITEM_STATUSES}
            for item in selected:
                actions[item.action] += 1
                statuses[item.status] += 1
            if (
                len(selected) != run.platform_count
                or {item.platform for item in selected} != set(run.platforms)
                or statuses["found_unverified"] != run.found_count
                or statuses["unreported"] != run.unreported_count
                or _result_sha(selected) != run.result_sha256
            ):
                raise StorageError("Sosyal kullanıcı adı çalışma özeti bozuk.")
            if run.previous_complete_run_id is None:
                if (
                    run.newly_found_count
                    or run.changed_count
                    or run.unchanged_found_count
                    or run.no_longer_reported_count
                    or actions["baseline_found"] != run.found_count
                    or actions["baseline_unreported"] != run.unreported_count
                    or any(
                        actions[action]
                        for action in ITEM_ACTIONS
                        if action not in {"baseline_found", "baseline_unreported"}
                    )
                ):
                    raise StorageError("Sosyal kullanıcı adı başlangıç özeti bozuk.")
            elif (
                actions["newly_found"] != run.newly_found_count
                or actions["changed"] != run.changed_count
                or actions["unchanged_found"] != run.unchanged_found_count
                or actions["no_longer_reported"] != run.no_longer_reported_count
                or actions["baseline_found"]
                or actions["baseline_unreported"]
                or run.found_count != (
                    run.newly_found_count
                    + run.changed_count
                    + run.unchanged_found_count
                )
                or run.unreported_count != (
                    run.no_longer_reported_count
                    + actions["unchanged_unreported"]
                )
            ):
                raise StorageError("Sosyal kullanıcı adı fark özeti bozuk.")
        return watches, events, runs, items

    def upsert(self, **values) -> BrandUsernameWatchMutation:
        platforms = tuple(values["platforms"])
        platforms_json = _platforms_json(platforms)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._audit(connection)
                row = connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM brand_username_watches WHERE name_key=?",
                    (values["name_key"],),
                ).fetchone()
                if row is None:
                    watch_id, action = str(uuid4()), "added"
                    connection.execute(
                        "INSERT INTO brand_username_watches VALUES "
                        "(?, ?, ?, ?, ?, 1, ?, ?, ?)",
                        (
                            watch_id,
                            values["name_key"],
                            values["display_name"],
                            values["username"],
                            platforms_json,
                            values["recorded_at"],
                            values["recorded_at"],
                            values["source_key"],
                        ),
                    )
                else:
                    old = self._watch(row)
                    if old.source_key != values["source_key"]:
                        raise ValidationError(
                            "İzleme kaynağı değiştirilemez; farklı bir izleme adı kullanın."
                        )
                    same = (
                        old.display_name == values["display_name"]
                        and old.username == values["username"]
                        and old.platforms == platforms
                    )
                    if same and old.active:
                        connection.commit()
                        return BrandUsernameWatchMutation("unchanged", old)
                    watch_id = old.id
                    action = "reactivated" if not old.active else "updated"
                    connection.execute(
                        "UPDATE brand_username_watches SET display_name=?, username=?, "
                        "platforms_json=?, active=1, updated_at=? WHERE id=?",
                        (
                            values["display_name"],
                            values["username"],
                            platforms_json,
                            values["recorded_at"],
                            watch_id,
                        ),
                    )
                watch = self._watch(connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM brand_username_watches WHERE id=?",
                    (watch_id,),
                ).fetchone())
                connection.execute(
                    "INSERT INTO brand_username_watch_events VALUES (?, ?, ?, ?, '', ?)",
                    (
                        str(uuid4()),
                        watch.id,
                        action,
                        self._definition(watch),
                        values["recorded_at"],
                    ),
                )
                connection.commit()
                return BrandUsernameWatchMutation(action, watch)
            except BaseException:
                connection.rollback()
                raise

    def revoke(self, watch_id, *, reason, recorded_at):
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._audit(connection)
                row = connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM brand_username_watches WHERE id=?",
                    (watch_id,),
                ).fetchone()
                if row is None:
                    raise ValidationError("Sosyal kullanıcı adı izlemesi bulunamadı.")
                watch = self._watch(row)
                if not watch.active:
                    connection.commit()
                    return BrandUsernameWatchMutation("unchanged", watch)
                connection.execute(
                    "UPDATE brand_username_watches SET active=0, updated_at=? WHERE id=?",
                    (recorded_at, watch.id),
                )
                connection.execute(
                    "INSERT INTO brand_username_watch_events VALUES "
                    "(?, ?, 'revoked', ?, ?, ?)",
                    (
                        str(uuid4()),
                        watch.id,
                        self._definition(watch),
                        reason,
                        recorded_at,
                    ),
                )
                updated = self._watch(connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM brand_username_watches WHERE id=?",
                    (watch.id,),
                ).fetchone())
                connection.commit()
                return BrandUsernameWatchMutation("revoked", updated)
            except BaseException:
                connection.rollback()
                raise

    def get(self, watch_id):
        with self._storage._connection(readonly=True) as connection:
            watches, _, _, _ = self._audit(connection)
        watch = watches.get(watch_id)
        if watch is None:
            raise ValidationError("Sosyal kullanıcı adı izlemesi bulunamadı.")
        return watch

    def list(self, *, active_only, limit):
        with self._storage._connection(readonly=True) as connection:
            watches, _, runs, _ = self._audit(connection)
        selected = sorted(
            (watch for watch in watches.values() if not active_only or watch.active),
            key=lambda watch: (watch.name_key, watch.id),
        )[:limit]
        return tuple(
            BrandUsernameWatchSummary(
                watch,
                len(history := [run for run in runs.values() if run.watch_id == watch.id]),
                max(history, key=lambda run: run.sequence) if history else None,
            )
            for watch in selected
        )

    def details(self, watch_id, *, event_limit, run_limit):
        with self._storage._connection(readonly=True) as connection:
            watches, events, runs, _ = self._audit(connection)
        watch = watches.get(watch_id)
        if watch is None:
            raise ValidationError("Sosyal kullanıcı adı izlemesi bulunamadı.")
        selected_events = list(reversed([
            event for event in events if event.watch_id == watch.id
        ]))
        selected_runs = sorted(
            (run for run in runs.values() if run.watch_id == watch.id),
            key=lambda run: run.sequence,
            reverse=True,
        )
        return BrandUsernameWatchDetails(
            watch,
            tuple(selected_events[:event_limit]),
            tuple(selected_runs[:run_limit]),
            len(selected_events),
            len(selected_runs),
        )

    @staticmethod
    def _previous_complete(runs, watch_id, definition):
        history = [
            run for run in runs.values()
            if run.watch_id == watch_id
            and run.status == "complete"
            and run.definition_sha256 == definition
        ]
        return max(history, key=lambda run: run.sequence) if history else None

    @staticmethod
    def _insert_item(connection, item: BrandUsernameWatchRunItem) -> None:
        connection.execute(
            "INSERT INTO brand_username_watch_run_items VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.run_id,
                item.platform,
                item.profile_url,
                item.status,
                item.action,
                item.state_sha256,
            ),
        )

    @staticmethod
    def _preview_states(preview, watch):
        if (
            not isinstance(preview, BrandUsernamePreview)
            or preview.source != BRAND_USERNAME_SOURCE_NAMES[watch.source_key]
            or preview.username != watch.username
            or preview.requested_platforms != watch.platforms
            or not isinstance(preview.matches, tuple)
            or not isinstance(preview.unreported_platforms, tuple)
            or any(not isinstance(item, BrandProfileMatch) for item in preview.matches)
        ):
            raise StorageError("Sosyal kullanıcı adı kaynak sonucu izlemeyle uyuşmuyor.")
        matches = {item.platform: item for item in preview.matches}
        if (
            len(matches) != len(preview.matches)
            or not set(matches).issubset(watch.platforms)
        ):
            raise StorageError("Sosyal kullanıcı adı kaynak platformları tutarsız.")
        unreported = tuple(item for item in watch.platforms if item not in matches)
        if preview.unreported_platforms != unreported:
            raise StorageError("Sosyal kullanıcı adı kaynak kapsamı tutarsız.")
        states = {}
        for platform in watch.platforms:
            match = matches.get(platform)
            if match is None:
                states[platform] = ("unreported", None)
            elif match.status == "found_unverified":
                try:
                    profile_url = _profile_url(platform, match.profile_url)
                except ValueError as error:
                    raise StorageError(
                        "Sosyal kullanıcı adı kaynak profil adresi geçersiz."
                    ) from error
                states[platform] = ("found_unverified", profile_url)
            else:
                raise StorageError("Sosyal kullanıcı adı kaynak durumu geçersiz.")
        return states

    def record_preview(
        self,
        watch_id,
        *,
        expected_definition_sha256,
        preview,
        recorded_at,
        item_limit,
    ):
        if not isinstance(preview, BrandUsernamePreview):
            raise StorageError("Sosyal kullanıcı adı kaynak sonucu geçersiz.")
        if type(item_limit) is not int or not 1 <= item_limit <= 500:
            raise ValidationError("Sonuç sınırı 1–500 arasında olmalı.")
        try:
            checked_at = _timestamp(
                preview.checked_at, field="Marka kaynak kontrol zamanı",
            )
            recorded_at = _timestamp(recorded_at, field="Marka izleme kayıt zamanı")
            source_name = _visible_text(
                preview.source, field="source name", maximum=100,
            )
            source_version = _visible_text(
                preview.source_version, field="source version", maximum=100,
            )
            integration_profile = _visible_text(
                preview.integration_profile,
                field="integration profile",
                maximum=200,
            )
        except (ValueError, ValidationError) as error:
            raise StorageError(
                "Sosyal kullanıcı adı kaynak üst bilgisi geçersiz."
            ) from error
        if datetime.fromisoformat(checked_at) > datetime.fromisoformat(recorded_at):
            raise ValidationError("Kaynak kontrol zamanı kayıt zamanından sonra olamaz.")
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                watches, _, runs, all_items = self._audit(connection)
                watch = watches.get(watch_id)
                if watch is None or not watch.active:
                    raise ValidationError("Etkin sosyal kullanıcı adı izlemesi bulunamadı.")
                definition = self._definition(watch)
                if definition != expected_definition_sha256:
                    raise StorageError(
                        "Sosyal kullanıcı adı izleme tanımı çalışma sırasında değişti."
                    )
                if source_name != BRAND_USERNAME_SOURCE_NAMES[watch.source_key]:
                    raise StorageError(
                        "Sosyal kullanıcı adı kaynağı izleme tanımıyla uyuşmuyor."
                    )
                states = self._preview_states(preview, watch)
                previous = self._previous_complete(runs, watch.id, definition)
                previous_items = {
                    item.platform: item for item in all_items
                    if previous is not None and item.run_id == previous.id
                }
                run_id = str(uuid4())
                items = []
                for platform in watch.platforms:
                    status, profile_url = states[platform]
                    prior = previous_items.get(platform)
                    if previous is None:
                        action = (
                            "baseline_found"
                            if status == "found_unverified"
                            else "baseline_unreported"
                        )
                    elif status == "found_unverified" and prior.status == "unreported":
                        action = "newly_found"
                    elif status == "found_unverified" and prior.profile_url != profile_url:
                        action = "changed"
                    elif status == "found_unverified":
                        action = "unchanged_found"
                    elif prior.status == "found_unverified":
                        action = "no_longer_reported"
                    else:
                        action = "unchanged_unreported"
                    items.append(BrandUsernameWatchRunItem(
                        str(uuid4()),
                        run_id,
                        platform,
                        profile_url,
                        status,
                        action,
                        brand_watch_item_state_sha256(
                            platform=platform,
                            status=status,
                            profile_url=profile_url,
                        ),
                    ))
                counts = {action: 0 for action in ITEM_ACTIONS}
                for item in items:
                    counts[item.action] += 1
                found = sum(item.status == "found_unverified" for item in items)
                unreported = len(items) - found
                result_sha = _result_sha(items)
                cursor = connection.execute(
                    "INSERT INTO brand_username_watch_runs "
                    "(id, watch_id, status, source_name, source_version, "
                    "integration_profile, username, platforms_json, definition_sha256, "
                    "previous_complete_run_id, checked_at, recorded_at, platform_count, "
                    "found_count, newly_found_count, changed_count, unchanged_found_count, "
                    "no_longer_reported_count, unreported_count, result_sha256, error) "
                    "VALUES (?, ?, 'complete', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, NULL)",
                    (
                        run_id,
                        watch.id,
                        source_name,
                        source_version,
                        integration_profile,
                        watch.username,
                        _platforms_json(watch.platforms),
                        definition,
                        previous.id if previous else None,
                        checked_at,
                        recorded_at,
                        len(items),
                        found,
                        counts["newly_found"],
                        counts["changed"],
                        counts["unchanged_found"],
                        counts["no_longer_reported"],
                        unreported,
                        result_sha,
                    ),
                )
                for item in items:
                    self._insert_item(connection, item)
                run = BrandUsernameWatchRun(
                    cursor.lastrowid,
                    run_id,
                    watch.id,
                    "complete",
                    source_name,
                    source_version,
                    integration_profile,
                    watch.username,
                    watch.platforms,
                    definition,
                    previous.id if previous else None,
                    checked_at,
                    recorded_at,
                    len(items),
                    found,
                    counts["newly_found"],
                    counts["changed"],
                    counts["unchanged_found"],
                    counts["no_longer_reported"],
                    unreported,
                    result_sha,
                    None,
                )
                connection.commit()
                attention = (
                    0 if previous is None else
                    run.newly_found_count
                    + run.changed_count
                    + run.no_longer_reported_count
                )
                return BrandUsernameWatchRunReport(
                    watch,
                    run,
                    tuple(items[:item_limit]),
                    len(items),
                    attention,
                    previous is None,
                    preview,
                )
            except BaseException:
                connection.rollback()
                raise

    def record_failure(
        self,
        watch_id,
        *,
        expected_definition_sha256,
        source_name,
        source_version,
        integration_profile,
        error,
        recorded_at,
    ):
        error = _visible_text(error, field="source error", maximum=500)
        source_name = _visible_text(source_name, field="source name", maximum=100)
        source_version = _visible_text(
            source_version, field="source version", maximum=100,
        )
        integration_profile = _visible_text(
            integration_profile, field="integration profile", maximum=200,
        )
        recorded_at = _timestamp(recorded_at, field="Marka izleme kayıt zamanı")
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                watches, _, runs, _ = self._audit(connection)
                watch = watches.get(watch_id)
                if watch is None or not watch.active:
                    raise ValidationError("Etkin sosyal kullanıcı adı izlemesi bulunamadı.")
                definition = self._definition(watch)
                if definition != expected_definition_sha256:
                    raise StorageError(
                        "Sosyal kullanıcı adı izleme tanımı çalışma sırasında değişti."
                    )
                if source_name != BRAND_USERNAME_SOURCE_NAMES[watch.source_key]:
                    raise StorageError(
                        "Sosyal kullanıcı adı kaynağı izleme tanımıyla uyuşmuyor."
                    )
                previous = self._previous_complete(runs, watch.id, definition)
                run_id = str(uuid4())
                cursor = connection.execute(
                    "INSERT INTO brand_username_watch_runs "
                    "(id, watch_id, status, source_name, source_version, "
                    "integration_profile, username, platforms_json, definition_sha256, "
                    "previous_complete_run_id, checked_at, recorded_at, platform_count, "
                    "found_count, newly_found_count, changed_count, unchanged_found_count, "
                    "no_longer_reported_count, unreported_count, result_sha256, error) "
                    "VALUES (?, ?, 'failed', ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 0, 0, "
                    "0, 0, 0, 0, NULL, ?)",
                    (
                        run_id,
                        watch.id,
                        source_name,
                        source_version,
                        integration_profile,
                        watch.username,
                        _platforms_json(watch.platforms),
                        definition,
                        previous.id if previous else None,
                        recorded_at,
                        len(watch.platforms),
                        error,
                    ),
                )
                run = BrandUsernameWatchRun(
                    cursor.lastrowid,
                    run_id,
                    watch.id,
                    "failed",
                    source_name,
                    source_version,
                    integration_profile,
                    watch.username,
                    watch.platforms,
                    definition,
                    previous.id if previous else None,
                    None,
                    recorded_at,
                    len(watch.platforms),
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    None,
                    error,
                )
                connection.commit()
                return BrandUsernameWatchRunReport(
                    watch, run, (), 0, 0, False, None,
                )
            except BaseException:
                connection.rollback()
                raise

    def run_details(self, run_id, *, item_limit):
        if type(item_limit) is not int or not 1 <= item_limit <= 500:
            raise ValidationError("Sonuç sınırı 1–500 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            watches, _, runs, items = self._audit(connection)
        run = runs.get(run_id)
        if run is None:
            raise ValidationError("Sosyal kullanıcı adı izleme çalışması bulunamadı.")
        order = {name: index for index, name in enumerate(_ITEM_ACTION_ORDER)}
        selected = sorted(
            (item for item in items if item.run_id == run.id),
            key=lambda item: (order[item.action], item.platform),
        )
        attention = (
            0 if run.status == "failed" or run.previous_complete_run_id is None
            else run.newly_found_count
            + run.changed_count
            + run.no_longer_reported_count
        )
        return BrandUsernameWatchRunReport(
            watches[run.watch_id],
            run,
            tuple(selected[:item_limit]),
            len(selected),
            attention,
            run.status == "complete" and run.previous_complete_run_id is None,
            None,
        )
