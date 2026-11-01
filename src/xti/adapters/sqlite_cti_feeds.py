"""Atomic complete-snapshot ingestion into the canonical sourced IOC catalog."""

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.domain.assets import ValidationError
from xti.domain.cti_feeds import (
    CtiFeedIndicator,
    CtiFeedPolicy,
    CtiFeedRun,
    CtiFeedSnapshot,
    CtiFeedStatus,
    FEED_ITEM_ACTIONS,
    FEED_RUN_STATUSES,
    FEODO_POLICY,
    feed_indicator_state_sha256,
    validate_sha256,
)
from xti.domain.cti_indicators import (
    normalize_confidence,
    normalize_cti_timestamp,
    normalize_indicator_description,
    normalize_indicator_type,
    normalize_indicator_value,
    normalize_source_name,
    normalize_source_reference,
)


_INDICATOR_SELECT = "id, indicator_type, value, created_at, updated_at"
_ASSERTION_SELECT = (
    "id, indicator_id, source_name, source_reference, confidence, valid_from, "
    "valid_until, active, description, first_seen_at, last_seen_at, created_at, updated_at"
)
_RUN_SELECT = (
    "id, sequence, source_name, status, source_url, content_sha256, started_at, "
    "finished_at, source_record_count, indicator_count, added_count, observed_count, "
    "updated_count, unchanged_count, reactivated_count, revoked_count, error"
)
_MAX_RUNS = 10_000
_MAX_ITEMS = 500_000
_MAX_SOURCE_EVENTS = 500_000


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("Non-canonical UUID")
    return normalized


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    normalized = normalize_cti_timestamp(value, field=field)
    if normalized != value:
        raise ValueError("Non-canonical timestamp")
    return normalized


def _error_text(value: object) -> str:
    if not isinstance(value, str) or any(not character.isprintable() for character in value):
        raise ValueError("Invalid error")
    normalized = " ".join(value.strip().split())
    if not 5 <= len(normalized) <= 2000:
        raise ValueError("Invalid error")
    return normalized


class SQLiteCtiFeedRepository:
    def __init__(
        self, path: Path, policy: CtiFeedPolicy = FEODO_POLICY,
    ) -> None:
        if not isinstance(policy, CtiFeedPolicy):
            raise ValidationError("IOC beslemesi kaynak politikası geçersiz.")
        self._storage = SQLiteAssetRepository(path)
        self.policy = policy

    def _run(self, row) -> CtiFeedRun:
        try:
            sequence = row[1]
            if type(sequence) is not int or sequence < 1:
                raise ValueError("Invalid sequence")
            source_name = normalize_source_name(row[2])
            if source_name != row[2] or source_name != self.policy.source_name:
                raise ValueError("Invalid source")
            if row[3] not in FEED_RUN_STATUSES or row[4] != self.policy.source_url:
                raise ValueError("Invalid run identity")
            content_sha256 = row[5]
            if content_sha256 is not None:
                content_sha256 = validate_sha256(content_sha256, field="IOC içerik özeti")
            started_at = _timestamp(row[6], field="IOC beslemesi başlangıcı")
            finished_at = _timestamp(row[7], field="IOC beslemesi bitişi")
            if datetime.fromisoformat(finished_at) < datetime.fromisoformat(started_at):
                raise ValueError("Reversed run time")
            counts = row[8:16]
            if any(type(value) is not int or value < 0 for value in counts):
                raise ValueError("Invalid counts")
            source_count, indicator_count = counts[:2]
            if indicator_count > source_count:
                raise ValueError("Impossible source count")
            error = row[16]
            if row[3] == "failed":
                if content_sha256 is not None or any(counts) or error is None:
                    raise ValueError("Invalid failed run")
                error = _error_text(error)
            else:
                if content_sha256 is None or error is not None:
                    raise ValueError("Invalid complete run")
                if sum(counts[2:7]) != indicator_count:
                    raise ValueError("Invalid indicator action counts")
            return CtiFeedRun(
                id=_uuid(row[0]), sequence=sequence, source_name=source_name,
                status=row[3], source_url=row[4], content_sha256=content_sha256,
                started_at=started_at, finished_at=finished_at,
                source_record_count=source_count, indicator_count=indicator_count,
                added_count=counts[2], observed_count=counts[3],
                updated_count=counts[4], unchanged_count=counts[5],
                reactivated_count=counts[6], revoked_count=counts[7], error=error,
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("IOC beslemesi çalışma kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _validate_times(started_at: str, finished_at: str) -> tuple[str, str]:
        try:
            started_at = normalize_cti_timestamp(
                started_at, field="IOC beslemesi başlangıcı",
            )
            finished_at = normalize_cti_timestamp(
                finished_at, field="IOC beslemesi bitişi",
            )
            if datetime.fromisoformat(finished_at) < datetime.fromisoformat(started_at):
                raise ValueError("Reversed time")
            return started_at, finished_at
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("IOC beslemesi çalışma zamanları geçersiz.") from error

    def _validate_item(
        self, item: CtiFeedIndicator, *, finished_at: str,
    ) -> CtiFeedIndicator:
        try:
            if not isinstance(item, CtiFeedIndicator):
                raise ValueError("Invalid item")
            indicator_type = normalize_indicator_type(item.indicator_type)
            value = normalize_indicator_value(indicator_type, item.value)
            reference = normalize_source_reference(item.source_reference)
            confidence = normalize_confidence(item.confidence)
            description = normalize_indicator_description(item.description)
            valid_from = normalize_cti_timestamp(
                item.valid_from, field="IOC geçerlilik başlangıcı",
            )
            last_seen = normalize_cti_timestamp(
                item.last_seen_at, field="IOC son gözlem zamanı",
            )
            if (
                indicator_type != item.indicator_type or value != item.value
                or reference != item.source_reference
                or confidence != self.policy.confidence
                or description != item.description or valid_from != item.valid_from
                or last_seen != item.last_seen_at
            ):
                raise ValueError("Non-canonical item")
            if datetime.fromisoformat(valid_from) > datetime.fromisoformat(last_seen):
                raise ValueError("Reversed observation")
            if datetime.fromisoformat(last_seen) > datetime.fromisoformat(finished_at):
                raise ValueError("Future observation")
            expected_reference = self.policy.source_reference(indicator_type, value)
            if reference != expected_reference:
                raise ValueError("Invalid stable reference")
            expected_hash = feed_indicator_state_sha256(
                indicator_type=indicator_type, value=value,
                source_reference=reference, confidence=confidence,
                description=description, valid_from=valid_from,
                last_seen_at=last_seen,
            )
            if validate_sha256(item.state_sha256, field="IOC durum özeti") != expected_hash:
                raise ValueError("Invalid state hash")
            return item
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("IOC beslemesi normalize edilmiş kayıtları geçersiz.") from error

    def _validate_snapshot(
        self, snapshot: CtiFeedSnapshot, *, finished_at: str,
    ) -> tuple[CtiFeedIndicator, ...]:
        try:
            if not isinstance(snapshot, CtiFeedSnapshot):
                raise ValueError("Invalid snapshot")
            if (
                snapshot.source_name != self.policy.source_name
                or snapshot.source_url != self.policy.source_url
                or type(snapshot.source_record_count) is not int
                or not 0 <= snapshot.source_record_count <= self.policy.maximum_records
                or not isinstance(snapshot.indicators, tuple)
                or len(snapshot.indicators) > snapshot.source_record_count
            ):
                raise ValueError("Invalid snapshot identity")
            validate_sha256(snapshot.content_sha256, field="IOC içerik özeti")
            validated = tuple(
                self._validate_item(item, finished_at=finished_at)
                for item in snapshot.indicators
            )
            keys = [(item.indicator_type, item.value) for item in validated]
            if len(set(keys)) != len(keys):
                raise ValueError("Duplicate snapshot indicator")
            return validated
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError("IOC beslemesi tam snapshot verisi geçersiz.") from error

    def _validate_existing_source(self, connection) -> dict[tuple[str, str], object]:
        rows = connection.execute(
            "SELECT a.id, a.indicator_id, a.source_name, a.source_reference, "
            "a.confidence, a.valid_from, a.valid_until, a.active, a.description, "
            "a.first_seen_at, a.last_seen_at, a.created_at, a.updated_at, "
            "i.id, i.indicator_type, i.value, i.created_at, "
            "i.updated_at FROM cti_indicator_assertions a JOIN cti_indicators i "
            "ON i.id = a.indicator_id WHERE a.source_name = ? "
            "ORDER BY a.source_reference, a.id LIMIT ?",
            (self.policy.source_name, self.policy.maximum_records + 1),
        ).fetchall()
        if len(rows) > self.policy.maximum_records:
            raise StorageError(
                f"{self.policy.label} IOC iddiası güvenli sınırı aştı."
            )
        result: dict[tuple[str, str], object] = {}
        event_counts: dict[str, int] = {}
        for row in rows:
            assertion = SQLiteCtiIndicatorRepository._assertion(row[:13])
            indicator = SQLiteCtiIndicatorRepository._indicator(row[13:])
            if assertion.indicator_id != indicator.id:
                raise StorageError(
                    f"{self.policy.label} IOC bağlantısı bozuk; işlem durduruldu."
                )
            expected = self.policy.source_reference(
                indicator.indicator_type, indicator.value,
            )
            key = (indicator.indicator_type, indicator.value)
            if (
                assertion.source_reference != expected
                or assertion.valid_from is None
                or key in result
            ):
                raise StorageError(
                    f"{self.policy.label} kaynak kimliği çakışıyor; senkronizasyon durduruldu."
                )
            result[key] = (assertion, indicator)
            event_counts[assertion.id] = 0
        event_rows = connection.execute(
            "SELECT e.id, e.assertion_id, e.action, e.confidence, e.valid_from, "
            "e.valid_until, e.description, e.reason, e.observed_at, e.recorded_at "
            "FROM cti_indicator_assertion_events e JOIN cti_indicator_assertions a "
            "ON a.id = e.assertion_id WHERE a.source_name = ? "
            "ORDER BY e.rowid LIMIT ?",
            (self.policy.source_name, _MAX_SOURCE_EVENTS + 1),
        ).fetchall()
        if len(event_rows) > _MAX_SOURCE_EVENTS:
            raise StorageError(
                f"{self.policy.label} IOC olay geçmişi güvenli sınırı aştı."
            )
        for row in event_rows:
            event = SQLiteCtiIndicatorRepository._event(row)
            if event.assertion_id not in event_counts:
                raise StorageError(
                    f"{self.policy.label} IOC geçmişi yanlış kayda bağlı."
                )
            event_counts[event.assertion_id] += 1
        if any(count < 1 for count in event_counts.values()):
            raise StorageError(
                f"{self.policy.label} IOC geçmişi eksik; işlem durduruldu."
            )
        return result

    @staticmethod
    def _insert_item(
        connection, *, run_id: str, assertion_id: str, action: str,
        state_sha256: str, recorded_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO cti_feed_run_items "
            "(id, run_id, assertion_id, action, state_sha256, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), run_id, assertion_id, action, state_sha256, recorded_at),
        )

    def apply(
        self, snapshot: CtiFeedSnapshot, *, started_at: str, finished_at: str,
    ) -> CtiFeedRun:
        started_at, finished_at = self._validate_times(started_at, finished_at)
        indicators = self._validate_snapshot(snapshot, finished_at=finished_at)
        run_id = str(uuid4())
        counts = {action: 0 for action in FEED_ITEM_ACTIONS}
        incoming_keys = {
            (item.indicator_type, item.value) for item in indicators
        }
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = self._validate_existing_source(connection)
                connection.execute(
                    "INSERT INTO cti_feed_runs "
                    "(id, source_name, status, source_url, content_sha256, started_at, "
                    "finished_at, source_record_count, indicator_count, added_count, "
                    "observed_count, updated_count, unchanged_count, reactivated_count, "
                    "revoked_count, error) VALUES (?, ?, 'complete', ?, ?, ?, ?, ?, ?, "
                    "0, 0, 0, 0, 0, 0, NULL)",
                    (run_id, self.policy.source_name, self.policy.source_url,
                     snapshot.content_sha256,
                     started_at, finished_at, snapshot.source_record_count, len(indicators)),
                )
                for item in indicators:
                    linked = existing.get((item.indicator_type, item.value))
                    if linked is None:
                        indicator_row = connection.execute(
                            f"SELECT {_INDICATOR_SELECT} FROM cti_indicators "
                            "WHERE indicator_type = ? AND value = ?",
                            (item.indicator_type, item.value),
                        ).fetchone()
                        if indicator_row is None:
                            indicator_id = str(uuid4())
                            connection.execute(
                                "INSERT INTO cti_indicators "
                                "(id, indicator_type, value, created_at, updated_at) "
                                "VALUES (?, ?, ?, ?, ?)",
                                (indicator_id, item.indicator_type, item.value,
                                 finished_at, finished_at),
                            )
                        else:
                            indicator = SQLiteCtiIndicatorRepository._indicator(indicator_row)
                            indicator_id = indicator.id
                        assertion_row = connection.execute(
                            f"SELECT {_ASSERTION_SELECT} FROM cti_indicator_assertions "
                            "WHERE indicator_id = ? AND source_name = ? AND source_reference = ?",
                            (indicator_id, self.policy.source_name, item.source_reference),
                        ).fetchone()
                        if assertion_row is not None:
                            raise StorageError(
                                f"{self.policy.label} IOC kaynak kimliği beklenmedik biçimde çakıştı."
                            )
                        assertion_id = str(uuid4())
                        action = "added"
                        connection.execute(
                            "INSERT INTO cti_indicator_assertions "
                            "(id, indicator_id, source_name, source_reference, confidence, "
                            "valid_from, valid_until, active, description, first_seen_at, "
                            "last_seen_at, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, NULL, 1, ?, ?, ?, ?, ?)",
                            (assertion_id, indicator_id, self.policy.source_name,
                             item.source_reference, item.confidence, item.valid_from,
                             item.description, item.valid_from, item.last_seen_at,
                             finished_at, finished_at),
                        )
                        effective_valid_from = item.valid_from
                        first_seen = item.valid_from
                        last_seen = item.last_seen_at
                    else:
                        current, indicator = linked
                        if (
                            indicator.indicator_type != item.indicator_type
                            or indicator.value != item.value
                        ):
                            raise StorageError(
                                f"{self.policy.label} kaynak başvurusu farklı IOC'ye bağlanıyor."
                            )
                        assertion_id = current.id
                        indicator_id = indicator.id
                        if self.policy.preserve_active_observation_time and current.active:
                            effective_valid_from = current.valid_from
                            last_seen = current.last_seen_at
                        else:
                            effective_valid_from = min(
                                current.valid_from, item.valid_from,
                            )
                            last_seen = max(current.last_seen_at, item.last_seen_at)
                        first_seen = min(current.first_seen_at, effective_valid_from)
                        metadata_same = (
                            current.confidence == item.confidence
                            and current.valid_from == effective_valid_from
                            and current.valid_until is None
                            and current.description == item.description
                        )
                        observation_changed = (
                            first_seen != current.first_seen_at
                            or last_seen != current.last_seen_at
                        )
                        if not current.active:
                            action = "reactivated"
                        elif not metadata_same:
                            action = "updated"
                        elif observation_changed:
                            action = "observed"
                        else:
                            action = "unchanged"
                        if action != "unchanged":
                            updated_at = max(current.updated_at, finished_at)
                            connection.execute(
                                "UPDATE cti_indicator_assertions SET confidence = ?, "
                                "valid_from = ?, valid_until = NULL, active = 1, "
                                "description = ?, first_seen_at = ?, last_seen_at = ?, "
                                "updated_at = ? WHERE id = ?",
                                (item.confidence, effective_valid_from, item.description,
                                 first_seen, last_seen, updated_at, assertion_id),
                            )
                    final_state_sha256 = feed_indicator_state_sha256(
                        indicator_type=item.indicator_type, value=item.value,
                        source_reference=item.source_reference,
                        confidence=item.confidence, description=item.description,
                        valid_from=effective_valid_from, last_seen_at=last_seen,
                    )
                    if action != "unchanged":
                        connection.execute(
                            "INSERT INTO cti_indicator_assertion_events "
                            "(id, assertion_id, action, confidence, valid_from, valid_until, "
                            "description, reason, observed_at, recorded_at) "
                            "VALUES (?, ?, ?, ?, ?, NULL, ?, '', ?, ?)",
                            (str(uuid4()), assertion_id, action, item.confidence,
                             effective_valid_from, item.description, last_seen, finished_at),
                        )
                        connection.execute(
                            "UPDATE cti_indicators SET updated_at = MAX(updated_at, ?) "
                            "WHERE id = ?", (finished_at, indicator_id),
                        )
                    if action != "unchanged" or self.policy.record_unchanged_items:
                        self._insert_item(
                            connection, run_id=run_id, assertion_id=assertion_id,
                            action=action, state_sha256=final_state_sha256,
                            recorded_at=finished_at,
                        )
                    counts[action] += 1

                for item_key, linked in existing.items():
                    current, indicator = linked
                    if item_key in incoming_keys or not current.active:
                        continue
                    if datetime.fromisoformat(current.last_seen_at) > datetime.fromisoformat(
                        finished_at
                    ):
                        raise StorageError(
                            f"{self.policy.label} IOC zamanı sistem saatinden ileride; işlem durduruldu."
                        )
                    connection.execute(
                        "UPDATE cti_indicator_assertions SET active = 0, updated_at = MAX(updated_at, ?) "
                        "WHERE id = ?", (finished_at, current.id),
                    )
                    connection.execute(
                        "INSERT INTO cti_indicator_assertion_events "
                        "(id, assertion_id, action, confidence, valid_from, valid_until, "
                        "description, reason, observed_at, recorded_at) "
                        "VALUES (?, ?, 'revoked', ?, ?, NULL, ?, ?, ?, ?)",
                        (str(uuid4()), current.id, current.confidence, current.valid_from,
                         current.description, self.policy.retraction_reason,
                         current.last_seen_at,
                         finished_at),
                    )
                    connection.execute(
                        "UPDATE cti_indicators SET updated_at = MAX(updated_at, ?) WHERE id = ?",
                        (finished_at, indicator.id),
                    )
                    if current.valid_from is None:
                        raise StorageError(
                            f"{self.policy.label} IOC başlangıç zamanı eksik."
                        )
                    state_hash = feed_indicator_state_sha256(
                        indicator_type=indicator.indicator_type, value=indicator.value,
                        source_reference=current.source_reference,
                        confidence=current.confidence, description=current.description,
                        valid_from=current.valid_from, last_seen_at=current.last_seen_at,
                    )
                    self._insert_item(
                        connection, run_id=run_id, assertion_id=current.id,
                        action="revoked", state_sha256=state_hash,
                        recorded_at=finished_at,
                    )
                    counts["revoked"] += 1

                connection.execute(
                    "UPDATE cti_feed_runs SET added_count = ?, observed_count = ?, "
                    "updated_count = ?, unchanged_count = ?, reactivated_count = ?, "
                    "revoked_count = ? WHERE id = ?",
                    (counts["added"], counts["observed"], counts["updated"],
                     counts["unchanged"], counts["reactivated"], counts["revoked"], run_id),
                )
                row = connection.execute(
                    f"SELECT {_RUN_SELECT} FROM cti_feed_runs WHERE id = ?", (run_id,),
                ).fetchone()
                result = self._run(row)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def record_failure(
        self, *, started_at: str, finished_at: str, error: str,
    ) -> CtiFeedRun:
        started_at, finished_at = self._validate_times(started_at, finished_at)
        try:
            error = _error_text(error)
        except ValueError as exception:
            raise ValidationError("IOC beslemesi hata açıklaması geçersiz.") from exception
        run_id = str(uuid4())
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_existing_source(connection)
                connection.execute(
                    "INSERT INTO cti_feed_runs "
                    "(id, source_name, status, source_url, content_sha256, started_at, "
                    "finished_at, source_record_count, indicator_count, added_count, "
                    "observed_count, updated_count, unchanged_count, reactivated_count, "
                    "revoked_count, error) VALUES (?, ?, 'failed', ?, NULL, ?, ?, "
                    "0, 0, 0, 0, 0, 0, 0, 0, ?)",
                    (run_id, self.policy.source_name, self.policy.source_url,
                     started_at, finished_at, error),
                )
                row = connection.execute(
                    f"SELECT {_RUN_SELECT} FROM cti_feed_runs WHERE id = ?", (run_id,),
                ).fetchone()
                result = self._run(row)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def status(self, *, run_limit: int) -> CtiFeedStatus:
        if type(run_limit) is not int or not 1 <= run_limit <= 100:
            raise ValidationError("IOC beslemesi geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            source_records = self._validate_existing_source(connection)
            source_assertion_ids = {
                assertion.id for assertion, _ in source_records.values()
            }
            run_count = connection.execute(
                "SELECT COUNT(*) FROM cti_feed_runs WHERE source_name = ?",
                (self.policy.source_name,),
            ).fetchone()[0]
            item_count = connection.execute(
                "SELECT COUNT(*) FROM cti_feed_run_items i JOIN cti_feed_runs r "
                "ON r.id = i.run_id WHERE r.source_name = ?",
                (self.policy.source_name,),
            ).fetchone()[0]
            if (
                type(run_count) is not int or type(item_count) is not int
                or run_count > _MAX_RUNS or item_count > _MAX_ITEMS
            ):
                raise StorageError("IOC beslemesi geçmişi güvenli okuma sınırını aştı.")
            all_rows = connection.execute(
                f"SELECT {_RUN_SELECT} FROM cti_feed_runs WHERE source_name = ? "
                "ORDER BY sequence", (self.policy.source_name,),
            ).fetchall()
            runs = tuple(self._run(row) for row in all_rows)
            for run in runs:
                grouped = dict(connection.execute(
                    "SELECT action, COUNT(*) FROM cti_feed_run_items WHERE run_id = ? "
                    "GROUP BY action", (run.id,),
                ).fetchall())
                if any(action not in FEED_ITEM_ACTIONS for action in grouped):
                    raise StorageError("IOC beslemesi öğe geçmişi bozuk; işlem durduruldu.")
                expected = {
                    "added": run.added_count, "observed": run.observed_count,
                    "updated": run.updated_count,
                    "unchanged": (
                        run.unchanged_count if self.policy.record_unchanged_items else 0
                    ),
                    "reactivated": run.reactivated_count, "revoked": run.revoked_count,
                }
                if any(grouped.get(action, 0) != count for action, count in expected.items()):
                    raise StorageError("IOC beslemesi sayaçları geçmişle uyuşmuyor.")
                item_rows = connection.execute(
                    "SELECT id, assertion_id, action, state_sha256, recorded_at "
                    "FROM cti_feed_run_items WHERE run_id = ?", (run.id,),
                ).fetchall()
                for item in item_rows:
                    try:
                        _uuid(item[0]); _uuid(item[1])
                        if item[1] not in source_assertion_ids:
                            raise ValueError("Run item linked to another source")
                        if item[2] not in FEED_ITEM_ACTIONS:
                            raise ValueError("Invalid action")
                        validate_sha256(item[3], field="IOC durum özeti")
                        recorded_at = _timestamp(item[4], field="IOC beslemesi kayıt zamanı")
                        if recorded_at != run.finished_at:
                            raise ValueError("Invalid item time")
                    except (TypeError, ValueError, ValidationError, OverflowError) as error:
                        raise StorageError(
                            "IOC beslemesi öğe geçmişi bozuk; işlem durduruldu."
                        ) from error
            active_count = sum(1 for assertion, _ in source_records.values() if assertion.active)
            total_indicator_count = len({indicator.id for _, indicator in source_records.values()})
        recent = tuple(reversed(runs[-run_limit:]))
        return CtiFeedStatus(
            source_name=self.policy.source_name,
            source_label=self.policy.label,
            active_assertion_count=active_count,
            total_indicator_count=total_indicator_count,
            latest_run=recent[0] if recent else None,
            recent_runs=recent,
            notes=self.policy.notes,
        )
