"""Atomic, source-isolated history for bounded RansomLook snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
import hashlib
import json

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_receipts import record_collection_step_receipt
from xti.domain.collection_history import CollectionOperationToken
from xti.domain.assets import ValidationError
from xti.domain.ransomlook_ransomware import (
    RANSOMLOOK_ITEM_ACTIONS,
    RANSOMLOOK_RUN_STATUSES,
    RANSOMLOOK_SOURCE_LICENSE,
    RANSOMLOOK_SOURCE_NAME,
    RANSOMLOOK_SOURCE_URL,
    RansomLookClaim,
    RansomLookClaimFeed,
    RansomLookClaimHistoryEvidence,
    RansomLookClaimHistoryStatus,
    RansomLookClaimRun,
    RansomLookClaimRunItem,
    RansomLookClaimRunReport,
    RansomLookClaimSnapshot,
    ransomlook_claim_state_sha256,
)


_RUN_SELECT = (
    "sequence, id, source_name, status, source_url, content_sha256, started_at, "
    "finished_at, fetched_at, window_days, source_record_count, claim_count, "
    "added_count, updated_count, unchanged_count, removed_count, error"
)
_ITEM_SELECT = (
    "id, run_id, claim_id, group_name, victim, discovered_at, action, state_sha256"
)
_MAX_RUNS = 10_000
_MAX_ITEMS = 1_000_000


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("Non-canonical UUID")
    return normalized


def _sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("Invalid SHA-256")
    return value


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Naive timestamp")
    if parsed.astimezone(timezone.utc).isoformat() != value:
        raise ValueError("Non-canonical timestamp")
    return value


def _text(value: object, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or value != " ".join(value.strip().split())
        or not 1 <= len(value) <= maximum
        or any(not character.isprintable() for character in value)
    ):
        raise ValueError("Invalid text")
    return value


def _error_text(value: object) -> str:
    normalized = _text(value, maximum=2000)
    if len(normalized) < 5:
        raise ValueError("Invalid error")
    return normalized


def _claim_id(group: str, victim: str, discovered_at: str) -> str:
    canonical = json.dumps(
        [group, victim, discovered_at], ensure_ascii=True, separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


class SQLiteRansomLookClaimRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _times(started_at: str, finished_at: str) -> tuple[str, str]:
        try:
            started_at = _timestamp(started_at)
            finished_at = _timestamp(finished_at)
            if datetime.fromisoformat(finished_at) < datetime.fromisoformat(started_at):
                raise ValueError("Reversed time")
            return started_at, finished_at
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("RansomLook çalışma zamanları geçersiz.") from error

    @staticmethod
    def _claim(value: RansomLookClaim) -> RansomLookClaim:
        try:
            if not isinstance(value, RansomLookClaim):
                raise ValueError("Invalid claim")
            group = _text(value.group, maximum=100)
            victim = _text(value.victim, maximum=300)
            discovered_at = _timestamp(value.discovered_at)
            if _sha256(value.id) != _claim_id(group, victim, discovered_at):
                raise ValueError("Invalid claim identity")
            return value
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("RansomLook snapshot kaydı geçersiz.") from error

    @classmethod
    def _feed(
        cls, feed: RansomLookClaimFeed, *, finished_at: str,
    ) -> tuple[RansomLookClaim, ...]:
        try:
            if not isinstance(feed, RansomLookClaimFeed):
                raise ValueError("Invalid feed")
            if (
                feed.source_name != RANSOMLOOK_SOURCE_NAME
                or feed.source_url != RANSOMLOOK_SOURCE_URL
                or feed.license != RANSOMLOOK_SOURCE_LICENSE
                or feed.window_days != 7
                or type(feed.source_record_count) is not int
                or not 0 <= feed.source_record_count <= 10_000
                or not isinstance(feed.claims, tuple)
                or len(feed.claims) != feed.source_record_count
            ):
                raise ValueError("Invalid feed identity")
            _sha256(feed.content_sha256)
            fetched_at = _timestamp(feed.fetched_at)
            _text(feed.source_note, maximum=2000)
            if datetime.fromisoformat(fetched_at) > datetime.fromisoformat(finished_at):
                raise ValueError("Invalid feed time")
            claims = tuple(cls._claim(claim) for claim in feed.claims)
            if len({claim.id for claim in claims}) != len(claims):
                raise ValueError("Duplicate claim")
            fetched = datetime.fromisoformat(fetched_at)
            earliest = fetched - timedelta(days=8)
            latest = fetched + timedelta(minutes=15)
            if any(
                not earliest <= datetime.fromisoformat(claim.discovered_at) <= latest
                for claim in claims
            ):
                raise ValueError("Claim outside feed window")
            return claims
        except ValidationError:
            raise
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("RansomLook tam snapshot verisi geçersiz.") from error

    @staticmethod
    def _run(row) -> RansomLookClaimRun:
        try:
            sequence = row[0]
            if type(sequence) is not int or sequence < 1:
                raise ValueError("Invalid sequence")
            run_id = _uuid(row[1])
            if (
                row[2] != RANSOMLOOK_SOURCE_NAME
                or row[3] not in RANSOMLOOK_RUN_STATUSES
                or row[4] != RANSOMLOOK_SOURCE_URL
            ):
                raise ValueError("Invalid source")
            content_sha256 = _sha256(row[5]) if row[5] is not None else None
            started_at, finished_at = SQLiteRansomLookClaimRepository._times(
                row[6], row[7]
            )
            fetched_at = _timestamp(row[8]) if row[8] is not None else None
            window_days = row[9]
            counts = row[10:16]
            if any(type(value) is not int or value < 0 for value in counts):
                raise ValueError("Invalid counts")
            source_count, claim_count, added, updated, unchanged, removed = counts
            if source_count > 10_000 or claim_count > 10_000 or removed > 10_000:
                raise ValueError("Counts exceed bounds")
            error = row[16]
            if row[3] == "failed":
                if (
                    content_sha256 is not None
                    or fetched_at is not None
                    or window_days is not None
                    or any(counts)
                    or error is None
                ):
                    raise ValueError("Invalid failed run")
                error = _error_text(error)
            else:
                if (
                    content_sha256 is None
                    or fetched_at is None
                    or window_days != 7
                    or error is not None
                    or source_count != claim_count
                    or added + updated + unchanged != claim_count
                    or datetime.fromisoformat(fetched_at) > datetime.fromisoformat(finished_at)
                ):
                    raise ValueError("Invalid complete run")
            return RansomLookClaimRun(
                sequence=sequence, id=run_id, source_name=row[2], status=row[3],
                source_url=row[4], content_sha256=content_sha256,
                started_at=started_at, finished_at=finished_at,
                fetched_at=fetched_at, window_days=window_days,
                source_record_count=source_count, claim_count=claim_count,
                added_count=added, updated_count=updated,
                unchanged_count=unchanged, removed_count=removed, error=error,
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError(
                "RansomLook çalışma geçmişi bozuk; işlem durduruldu."
            ) from error

    @classmethod
    def _item(cls, row) -> RansomLookClaimRunItem:
        try:
            item_id, run_id = _uuid(row[0]), _uuid(row[1])
            claim = cls._claim(RansomLookClaim(
                id=_sha256(row[2]), group=_text(row[3], maximum=100),
                victim=_text(row[4], maximum=300), discovered_at=_timestamp(row[5]),
            ))
            if row[6] not in RANSOMLOOK_ITEM_ACTIONS:
                raise ValueError("Invalid action")
            state = _sha256(row[7])
            if state != ransomlook_claim_state_sha256(claim):
                raise ValueError("Invalid state")
            return RansomLookClaimRunItem(item_id, run_id, claim, row[6], state)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError(
                "RansomLook öğe geçmişi bozuk; işlem durduruldu."
            ) from error

    @classmethod
    def _audit(
        cls, connection,
    ) -> tuple[tuple[RansomLookClaimRun, ...], tuple[RansomLookClaimRunItem, ...]]:
        run_count = connection.execute(
            "SELECT COUNT(*) FROM ransomlook_claim_runs"
        ).fetchone()[0]
        item_count = connection.execute(
            "SELECT COUNT(*) FROM ransomlook_claim_run_items"
        ).fetchone()[0]
        if (
            type(run_count) is not int
            or type(item_count) is not int
            or run_count > _MAX_RUNS
            or item_count > _MAX_ITEMS
        ):
            raise StorageError("RansomLook geçmişi güvenli okuma sınırını aştı.")
        runs = tuple(cls._run(row) for row in connection.execute(
            f"SELECT {_RUN_SELECT} FROM ransomlook_claim_runs ORDER BY sequence"
        ).fetchall())
        run_ids = {run.id: run for run in runs}
        items = tuple(cls._item(row) for row in connection.execute(
            f"SELECT {_ITEM_SELECT} FROM ransomlook_claim_run_items ORDER BY rowid"
        ).fetchall())
        grouped: dict[str, dict[str, int]] = {run.id: {} for run in runs}
        by_run: dict[str, list[RansomLookClaimRunItem]] = {run.id: [] for run in runs}
        identities: set[tuple[str, str]] = set()
        for item in items:
            if item.run_id not in run_ids or (item.run_id, item.claim.id) in identities:
                raise StorageError("RansomLook öğe bağlantıları bozuk.")
            identities.add((item.run_id, item.claim.id))
            grouped[item.run_id][item.action] = (
                grouped[item.run_id].get(item.action, 0) + 1
            )
            by_run[item.run_id].append(item)
        current: dict[str, RansomLookClaimRunItem] = {}
        for run in runs:
            expected = {
                "added": run.added_count,
                "updated": run.updated_count,
                "unchanged": 0,
                "removed": run.removed_count,
            }
            if any(
                grouped[run.id].get(action, 0) != count
                for action, count in expected.items()
            ):
                raise StorageError("RansomLook geçmiş sayaçları uyuşmuyor.")
            for item in by_run[run.id]:
                exists = item.claim.id in current
                if item.action == "added":
                    if exists:
                        raise StorageError("RansomLook fark geçmişi çakışıyor.")
                    current[item.claim.id] = item
                elif item.action == "updated":
                    if not exists:
                        raise StorageError("RansomLook fark geçmişi eksik.")
                    current[item.claim.id] = item
                elif item.action == "removed":
                    if not exists or current[item.claim.id].state_sha256 != item.state_sha256:
                        raise StorageError("RansomLook çıkarma kanıtı bozuk.")
                    current.pop(item.claim.id)
                else:
                    raise StorageError("RansomLook geçmişinde yinelenen aynı öğe var.")
            if run.status == "complete" and len(current) != run.claim_count:
                raise StorageError("RansomLook snapshot sayacı geçmişle uyuşmuyor.")
        return runs, items

    @staticmethod
    def _insert_item(connection, item: RansomLookClaimRunItem) -> None:
        claim = item.claim
        connection.execute(
            "INSERT INTO ransomlook_claim_run_items "
            "(id, run_id, claim_id, group_name, victim, discovered_at, action, state_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id, item.run_id, claim.id, claim.group, claim.victim,
                claim.discovered_at, item.action, item.state_sha256,
            ),
        )

    def apply(
        self, feed: RansomLookClaimFeed, *, started_at: str, finished_at: str,
        item_limit: int, operation: CollectionOperationToken | None = None,
    ) -> RansomLookClaimRunReport:
        if type(item_limit) is not int or not 1 <= item_limit <= 500:
            raise ValidationError("Değişiklik görünüm sınırı 1–500 arasında olmalı.")
        started_at, finished_at = self._times(started_at, finished_at)
        claims = self._feed(feed, finished_at=finished_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                from xti.adapters.sqlite_supplier_watches import preflight_supplier_watches
                preflight_supplier_watches(connection)
                runs, all_items = self._audit(connection)
                previous = next(
                    (run for run in reversed(runs) if run.status == "complete"), None
                )
                prior_items: dict[str, RansomLookClaimRunItem] = {}
                if previous is not None:
                    for item in all_items:
                        if item.action in {"added", "updated"}:
                            prior_items[item.claim.id] = item
                        elif item.action == "removed":
                            prior_items.pop(item.claim.id, None)
                run_id = str(uuid4())
                items: list[RansomLookClaimRunItem] = []
                for claim in claims:
                    state = ransomlook_claim_state_sha256(claim)
                    prior = prior_items.pop(claim.id, None)
                    action = "added" if prior is None else (
                        "unchanged" if prior.state_sha256 == state else "updated"
                    )
                    items.append(RansomLookClaimRunItem(
                        str(uuid4()), run_id, claim, action, state,
                    ))
                for prior in prior_items.values():
                    items.append(RansomLookClaimRunItem(
                        str(uuid4()), run_id, prior.claim, "removed", prior.state_sha256,
                    ))
                action_order = {"added": 0, "updated": 1, "removed": 2, "unchanged": 3}
                items.sort(key=lambda item: (
                    action_order[item.action], item.claim.victim.casefold(), item.claim.id,
                ))
                counts = {action: 0 for action in RANSOMLOOK_ITEM_ACTIONS}
                for item in items:
                    counts[item.action] += 1
                cursor = connection.execute(
                    "INSERT INTO ransomlook_claim_runs "
                    "(id, source_name, status, source_url, content_sha256, started_at, "
                    "finished_at, fetched_at, window_days, source_record_count, claim_count, "
                    "added_count, updated_count, unchanged_count, removed_count, error) "
                    "VALUES (?, ?, 'complete', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                    (
                        run_id, feed.source_name, feed.source_url, feed.content_sha256,
                        started_at, finished_at, feed.fetched_at, feed.window_days,
                        feed.source_record_count, len(claims), counts["added"],
                        counts["updated"], counts["unchanged"], counts["removed"],
                    ),
                )
                stored_items = [item for item in items if item.action != "unchanged"]
                for item in stored_items:
                    self._insert_item(connection, item)
                run = RansomLookClaimRun(
                    sequence=cursor.lastrowid, id=run_id, source_name=feed.source_name,
                    status="complete", source_url=feed.source_url,
                    content_sha256=feed.content_sha256, started_at=started_at,
                    finished_at=finished_at, fetched_at=feed.fetched_at,
                    window_days=feed.window_days,
                    source_record_count=feed.source_record_count,
                    claim_count=len(claims), added_count=counts["added"],
                    updated_count=counts["updated"], unchanged_count=counts["unchanged"],
                    removed_count=counts["removed"], error=None,
                )
                from xti.adapters.sqlite_supplier_watches import process_supplier_watches
                process_supplier_watches(connection, "ransomlook", run.id)
                record_collection_step_receipt(
                    connection, operation, result_kind="ransomlook_source_run",
                    result_id=run.id, result_status=run.status,
                )
                connection.commit()
                return RansomLookClaimRunReport(
                    run=run, items=tuple(stored_items[:item_limit]),
                    total_item_count=len(stored_items), is_baseline=previous is None,
                )
            except BaseException:
                connection.rollback()
                raise

    def record_failure(
        self, *, started_at: str, finished_at: str, error: str,
        operation: CollectionOperationToken | None = None,
    ) -> RansomLookClaimRun:
        started_at, finished_at = self._times(started_at, finished_at)
        try:
            error = _error_text(error)
        except ValueError as exception:
            raise ValidationError("RansomLook hata açıklaması geçersiz.") from exception
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                from xti.adapters.sqlite_supplier_watches import preflight_supplier_watches
                preflight_supplier_watches(connection)
                self._audit(connection)
                run_id = str(uuid4())
                cursor = connection.execute(
                    "INSERT INTO ransomlook_claim_runs "
                    "(id, source_name, status, source_url, content_sha256, started_at, "
                    "finished_at, fetched_at, window_days, source_record_count, claim_count, "
                    "added_count, updated_count, unchanged_count, removed_count, error) "
                    "VALUES (?, ?, 'failed', ?, NULL, ?, ?, NULL, NULL, 0, 0, 0, 0, 0, 0, ?)",
                    (
                        run_id, RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL,
                        started_at, finished_at, error,
                    ),
                )
                run = RansomLookClaimRun(
                    sequence=cursor.lastrowid, id=run_id,
                    source_name=RANSOMLOOK_SOURCE_NAME, status="failed",
                    source_url=RANSOMLOOK_SOURCE_URL, content_sha256=None,
                    started_at=started_at, finished_at=finished_at, fetched_at=None,
                    window_days=None, source_record_count=0, claim_count=0,
                    added_count=0, updated_count=0, unchanged_count=0,
                    removed_count=0, error=error,
                )
                record_collection_step_receipt(
                    connection, operation, result_kind="ransomlook_source_run",
                    result_id=run.id, result_status=run.status,
                )
                connection.commit()
                return run
            except BaseException:
                connection.rollback()
                raise

    def status(self, *, run_limit: int) -> RansomLookClaimHistoryStatus:
        if type(run_limit) is not int or not 1 <= run_limit <= 100:
            raise ValidationError("RansomLook geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            from xti.adapters.sqlite_supplier_watches import preflight_supplier_watches
            preflight_supplier_watches(connection)
            runs, _ = self._audit(connection)
        latest = runs[-1] if runs else None
        complete = next((run for run in reversed(runs) if run.status == "complete"), None)
        return RansomLookClaimHistoryStatus(
            latest_run=latest, latest_complete_run=complete,
            recent_runs=tuple(reversed(runs[-run_limit:])),
            notes=(
                "Kayıtlar doğrulanmış ihlal değil, kamuya açık grup iddialarıdır.",
                "İlk başarılı snapshot yalnız başlangıç çizgisidir; alarm değildir.",
                "Pencereden çıkış silinme, çözüm veya yanlış iddia kanıtı değildir.",
                "RansomLook ve ThreatCluster geçmişleri ayrı tutulur.",
            ),
        )

    def latest_snapshot(self) -> RansomLookClaimSnapshot:
        with self._storage._connection(readonly=True) as connection:
            runs, items = self._audit(connection)
        complete = next((run for run in reversed(runs) if run.status == "complete"), None)
        if complete is None:
            raise ValidationError(
                "Henüz başarılı RansomLook snapshot'ı yok. Önce "
                "'./xti ransomware refresh --source ransomlook' çalıştırın."
            )
        current: dict[str, RansomLookClaim] = {}
        by_run: dict[str, list[RansomLookClaimRunItem]] = {}
        for item in items:
            by_run.setdefault(item.run_id, []).append(item)
        for run in runs:
            if run.sequence > complete.sequence:
                break
            for item in by_run.get(run.id, ()):
                if item.action in {"added", "updated"}:
                    current[item.claim.id] = item.claim
                elif item.action == "removed":
                    current.pop(item.claim.id, None)
        if len(current) != complete.claim_count:
            raise StorageError("RansomLook son snapshot durumu yeniden kurulamadı.")
        claims = tuple(sorted(
            current.values(), key=lambda claim: (claim.victim.casefold(), claim.id),
        ))
        return RansomLookClaimSnapshot(complete, claims)

    def history(self) -> RansomLookClaimHistoryEvidence:
        with self._storage._connection(readonly=True) as connection:
            runs, items = self._audit(connection)
        return RansomLookClaimHistoryEvidence(runs=runs, items=items)
