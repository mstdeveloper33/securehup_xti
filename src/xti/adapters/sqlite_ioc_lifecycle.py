"""Bounded, replay-checked IOC and collection evidence in one read transaction."""

from pathlib import Path
from uuid import UUID

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_context import _audit_assertion_history
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository, _RUN_SELECT
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.domain.cti_feeds import CTI_FEED_POLICIES, FEED_ITEM_ACTIONS, feed_indicator_state_sha256, validate_sha256
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.assets import ValidationError
from xti.domain.ioc_lifecycle import (
    FeedCollectionContext, IocLifecycleSnapshot, MAX_ASSERTIONS, MAX_EVENTS,
    MAX_READ_BYTES, MAX_RECEIPTS, lifecycle_parameters,
)


def _budget(connection, table, where, values, max_rows, remaining):
    # All SQL identifiers/clauses here are adapter constants, never user input.
    columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    sizes = '+'.join(f'COALESCE(LENGTH(CAST("{row[1]}" AS BLOB)),0)' for row in columns)
    count, size = connection.execute(
        f'SELECT COUNT(*),COALESCE(SUM({sizes}+128),0) FROM "{table}" WHERE {where}', values,
    ).fetchone()
    if count > max_rows or size > remaining:
        raise StorageError("IOC yaşam döngüsü kanıtı okuma sınırını aşıyor; eksik değerlendirme üretilmedi.")
    return remaining - size


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Invalid UUID")


class SQLiteIocLifecycleRepository:
    def __init__(self, path: Path):
        self.storage = SQLiteAssetRepository(path)
        self.indicators = SQLiteCtiIndicatorRepository(path)
        self.feeds = {policy.source_name: SQLiteCtiFeedRepository(path, policy)
                      for policy in CTI_FEED_POLICIES.values()}

    def read(self, indicator_type: str, value: str) -> IocLifecycleSnapshot:
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return self.read_in(connection, indicator_type, value)

    def read_in(self, connection, indicator_type: str, value: str) -> IocLifecycleSnapshot:
        """Reuse the caller's snapshot when composing multiple evidence families."""
        options = lifecycle_parameters(indicator_type=indicator_type, value=value)
        budget = _budget(connection, "cti_indicators", "indicator_type=? AND value=?",
            (options["indicator_type"], options["value"]), 1, MAX_READ_BYTES)
        row = connection.execute("SELECT id,indicator_type,value,created_at,updated_at "
            "FROM cti_indicators WHERE indicator_type=? AND value=?",
            (options["indicator_type"], options["value"])).fetchone()
        if row is None:
            return IocLifecycleSnapshot(None)
        identifier = row[0]
        assertion_scope = "SELECT id FROM cti_indicator_assertions WHERE indicator_id=?"
        budget = _budget(connection, "cti_indicator_assertions", "indicator_id=?",
            (identifier,), MAX_ASSERTIONS, budget)
        budget = _budget(connection, "cti_indicator_assertion_events", f"assertion_id IN ({assertion_scope})",
            (identifier,), MAX_EVENTS, budget)
        budget = _budget(connection, "cti_feed_run_items", f"assertion_id IN ({assertion_scope})",
            (identifier,), MAX_RECEIPTS, budget)
        details = self.indicators._details(connection, row, assertion_limit=MAX_ASSERTIONS, event_limit=MAX_EVENTS)
        _audit_assertion_history(connection, details, "indicator")
        contexts = []
        last_ids = {}
        for source_name in sorted({claim.source_name for claim in details.assertions} & self.feeds.keys()):
            latest = connection.execute("SELECT id FROM cti_feed_runs WHERE source_name=? ORDER BY sequence DESC LIMIT 1",
                (source_name,)).fetchone()
            success = connection.execute("SELECT id FROM cti_feed_runs WHERE source_name=? AND status='complete' ORDER BY sequence DESC LIMIT 1",
                (source_name,)).fetchone()
            last_ids[source_name] = (latest[0] if latest else None, success[0] if success else None)
        extra_ids = sorted({item for pair in last_ids.values() for item in pair if item is not None})
        run_scope = f"id IN (SELECT run_id FROM cti_feed_run_items WHERE assertion_id IN ({assertion_scope}))"
        run_values = (identifier,)
        if extra_ids:
            run_scope += " OR id IN (" + ",".join("?" for _ in extra_ids) + ")"
            run_values += tuple(extra_ids)
        _budget(connection, "cti_feed_runs", run_scope, run_values, MAX_RECEIPTS + 4, budget)
        runs = {}
        for run_row in connection.execute(f"SELECT {_RUN_SELECT} FROM cti_feed_runs WHERE {run_scope}", run_values):
            feed = self.feeds.get(run_row[2])
            if feed is None:
                raise StorageError("IOC makbuzu bilinmeyen kaynak çalışmasına bağlı.")
            run = feed._run(run_row)
            runs[run.id] = run
        for name, (latest, success) in last_ids.items():
            if latest is None or success is None:
                raise StorageError("Yönetilen IOC iddiasının kaynak toplama geçmişi eksik.")
            contexts.append(FeedCollectionContext(name, runs[latest], runs[success]))
        claims = {claim.id: claim for claim in details.assertions}
        receipts, ordered_receipts = {}, []
        for receipt in connection.execute("SELECT id,run_id,assertion_id,action,state_sha256,recorded_at "
                f"FROM cti_feed_run_items WHERE assertion_id IN ({assertion_scope})", (identifier,)):
            rid, run_id, assertion_id, action, digest, at = receipt
            try:
                for value_id in (rid, run_id, assertion_id):
                    _uuid(value_id)
                claim, run = claims[assertion_id], runs[run_id]
                validate_sha256(digest, field="IOC makbuz özeti")
                if (action not in FEED_ITEM_ACTIONS or run.source_name != claim.source_name
                        or run.status != "complete" or at != run.finished_at
                        or normalize_cti_timestamp(at) != at):
                    raise ValueError("Mismatched receipt")
            except (ValueError, TypeError, KeyError, ValidationError) as error:
                raise StorageError("IOC kaynak makbuzu eksik veya tutarsız.") from error
            key = (assertion_id, action, at, digest)
            receipts[key] = receipts.get(key, 0) + 1
            ordered_receipts.append((run.sequence, key))
        states = {}
        for _, key in sorted(ordered_receipts):
            assertion_id, action, _, digest = key
            previous = states.get(assertion_id)
            if ((receipts[key] != 1 and action != "unchanged") or (action == "added") != (previous is None)
                    or (action in {"unchanged", "revoked"} and previous != digest)):
                raise StorageError("IOC makbuz durum geçmişi tutarsız.")
            states[assertion_id] = digest
        feed_events, used_receipts = set(), set()
        for event in details.events:
            claim = claims[event.assertion_id]
            if claim.source_name not in self.feeds:
                continue
            digest = feed_indicator_state_sha256(indicator_type=details.indicator.indicator_type,
                value=details.indicator.value, source_reference=claim.source_reference,
                confidence=event.confidence, description=event.description,
                valid_from=event.valid_from, last_seen_at=event.observed_at)
            key = (claim.id, event.action, event.recorded_at, digest)
            matches = receipts.get(key, 0)
            # The existing operator revoke is allowed to have no source receipt.
            if matches > 1 or key in used_receipts or (matches != 1 and event.action != "revoked"):
                raise StorageError("IOC kaynak olayının doğrulanmış makbuzu eksik veya belirsiz.")
            if matches == 1:
                feed_events.add(event.id)
                used_receipts.add(key)
        if any(key[1] != "unchanged" and key not in used_receipts for key in receipts):
            raise StorageError("IOC kaynak makbuzunun karşılık gelen olayı eksik; yerel karar sayılmadı.")
        return IocLifecycleSnapshot(details, tuple(contexts), frozenset(feed_events))
