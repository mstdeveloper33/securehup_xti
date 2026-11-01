"""Atomic canonical IOC catalog with independent sourced assertions."""

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import (
    ASSERTION_ACTIONS,
    CtiIndicator,
    CtiIndicatorAssertion,
    CtiIndicatorAssertionEvent,
    CtiIndicatorDetails,
    CtiIndicatorExportItem,
    CtiIndicatorExportSnapshot,
    CtiIndicatorMutation,
    CtiIndicatorSummary,
    normalize_assertion_id,
    normalize_assertion_reason,
    normalize_confidence,
    normalize_cti_timestamp,
    normalize_indicator_description,
    normalize_indicator_id,
    normalize_indicator_type,
    normalize_indicator_value,
    normalize_source_name,
    normalize_source_reference,
    validate_validity_window,
)


_INDICATOR_SELECT = "id, indicator_type, value, created_at, updated_at"
_ASSERTION_SELECT = (
    "id, indicator_id, source_name, source_reference, confidence, valid_from, "
    "valid_until, active, description, first_seen_at, last_seen_at, created_at, updated_at"
)
_EVENT_SELECT = (
    "id, assertion_id, action, confidence, valid_from, valid_until, description, reason, "
    "observed_at, recorded_at"
)
_MAX_ASSERTIONS = 10_000
_MAX_EVENTS = 100_000
_MAX_EXPORT_INDICATORS = 50_000
_MAX_EXPORT_ASSERTIONS = 50_000


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    normalized = str(UUID(value))
    if value != normalized:
        raise ValueError("Non-canonical UUID")
    return normalized


def _timestamp(value: object, *, field: str = "IOC zamanı") -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    normalized = normalize_cti_timestamp(value, field=field)
    if value != normalized:
        raise ValueError("Non-canonical timestamp")
    return normalized


def _optional_timestamp(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid optional timestamp")
    return normalize_cti_timestamp(value, field=field)


class SQLiteCtiIndicatorRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _indicator(row) -> CtiIndicator:
        try:
            indicator_type = normalize_indicator_type(row[1])
            value = normalize_indicator_value(indicator_type, row[2])
            if row[1] != indicator_type or row[2] != value:
                raise ValueError("Non-canonical indicator")
            record = CtiIndicator(
                id=_uuid(row[0]), indicator_type=indicator_type, value=value,
                created_at=_timestamp(row[3]), updated_at=_timestamp(row[4]),
            )
            if datetime.fromisoformat(record.updated_at) < datetime.fromisoformat(
                record.created_at
            ):
                raise ValueError("Reversed indicator time")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("IOC ana kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _assertion(row) -> CtiIndicatorAssertion:
        try:
            valid_from, valid_until = validate_validity_window(row[5], row[6])
            if row[5] != valid_from or row[6] != valid_until:
                raise ValueError("Non-canonical validity time")
            if type(row[7]) is not int or row[7] not in {0, 1}:
                raise ValueError("Invalid assertion activity")
            record = CtiIndicatorAssertion(
                id=_uuid(row[0]), indicator_id=_uuid(row[1]),
                source_name=normalize_source_name(row[2]),
                source_reference=normalize_source_reference(row[3]),
                confidence=normalize_confidence(row[4]), valid_from=valid_from,
                valid_until=valid_until, active=bool(row[7]),
                description=normalize_indicator_description(row[8]),
                first_seen_at=_timestamp(row[9], field="IOC ilk gözlem zamanı"),
                last_seen_at=_timestamp(row[10], field="IOC son gözlem zamanı"),
                created_at=_timestamp(row[11]), updated_at=_timestamp(row[12]),
            )
            if row[2] != record.source_name or row[3] != record.source_reference:
                raise ValueError("Non-canonical source")
            first = datetime.fromisoformat(record.first_seen_at)
            last = datetime.fromisoformat(record.last_seen_at)
            created = datetime.fromisoformat(record.created_at)
            updated = datetime.fromisoformat(record.updated_at)
            if first > last or created > updated:
                raise ValueError("Reversed assertion time")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("IOC kaynak iddiası bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row) -> CtiIndicatorAssertionEvent:
        try:
            if row[2] not in ASSERTION_ACTIONS:
                raise ValueError("Invalid event action")
            valid_from, valid_until = validate_validity_window(row[4], row[5])
            if row[4] != valid_from or row[5] != valid_until:
                raise ValueError("Non-canonical event validity time")
            reason = row[7]
            if row[2] == "revoked":
                reason = normalize_assertion_reason(reason)
            elif reason != "":
                raise ValueError("Unexpected event reason")
            event = CtiIndicatorAssertionEvent(
                id=_uuid(row[0]), assertion_id=_uuid(row[1]), action=row[2],
                confidence=normalize_confidence(row[3]), valid_from=valid_from,
                valid_until=valid_until,
                description=normalize_indicator_description(row[6]), reason=reason,
                observed_at=_timestamp(row[8], field="IOC gözlem zamanı"),
                recorded_at=_timestamp(row[9]),
            )
            if datetime.fromisoformat(event.observed_at) > datetime.fromisoformat(
                event.recorded_at
            ):
                raise ValueError("Future observation")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("IOC kaynak iddiası geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _select_indicator(connection, indicator_id: str):
        return connection.execute(
            f"SELECT {_INDICATOR_SELECT} FROM cti_indicators WHERE id = ?",
            (indicator_id,),
        ).fetchone()

    @staticmethod
    def _select_assertion(connection, assertion_id: str):
        return connection.execute(
            f"SELECT {_ASSERTION_SELECT} FROM cti_indicator_assertions WHERE id = ?",
            (assertion_id,),
        ).fetchone()

    @staticmethod
    def _validated_add_input(
        *, indicator_type: str, value: str, source_name: str,
        source_reference: str, confidence: int, valid_from: str | None,
        valid_until: str | None, description: str, observed_at: str,
        recorded_at: str,
    ) -> tuple:
        try:
            indicator_type = normalize_indicator_type(indicator_type)
            value = normalize_indicator_value(indicator_type, value)
            valid_from, valid_until = validate_validity_window(valid_from, valid_until)
            observed_at = normalize_cti_timestamp(observed_at, field="IOC gözlem zamanı")
            recorded_at = normalize_cti_timestamp(recorded_at)
            if datetime.fromisoformat(observed_at) > datetime.fromisoformat(recorded_at):
                raise ValueError("Future observation")
            return (
                indicator_type, value, normalize_source_name(source_name),
                normalize_source_reference(source_reference),
                normalize_confidence(confidence), valid_from, valid_until,
                normalize_indicator_description(description), observed_at, recorded_at,
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("IOC kaynak iddiası kaydedilemedi; alanları kontrol edin.") from error

    def add_assertion(
        self, *, indicator_type: str, value: str, source_name: str,
        source_reference: str, confidence: int, valid_from: str | None,
        valid_until: str | None, description: str, observed_at: str,
        recorded_at: str,
    ) -> CtiIndicatorMutation:
        (
            indicator_type, value, source_name, source_reference, confidence,
            valid_from, valid_until, description, observed_at, recorded_at,
        ) = self._validated_add_input(
            indicator_type=indicator_type, value=value, source_name=source_name,
            source_reference=source_reference, confidence=confidence,
            valid_from=valid_from, valid_until=valid_until, description=description,
            observed_at=observed_at, recorded_at=recorded_at,
        )
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                indicator_row = connection.execute(
                    f"SELECT {_INDICATOR_SELECT} FROM cti_indicators "
                    "WHERE indicator_type = ? AND value = ?",
                    (indicator_type, value),
                ).fetchone()
                if indicator_row is None:
                    indicator_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO cti_indicators "
                        "(id, indicator_type, value, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (indicator_id, indicator_type, value, recorded_at, recorded_at),
                    )
                    indicator_updated_at = recorded_at
                else:
                    indicator = self._indicator(indicator_row)
                    indicator_id = indicator.id
                    indicator_updated_at = indicator.updated_at

                assertion_row = connection.execute(
                    f"SELECT {_ASSERTION_SELECT} FROM cti_indicator_assertions "
                    "WHERE indicator_id = ? AND source_name = ? AND source_reference = ?",
                    (indicator_id, source_name, source_reference),
                ).fetchone()
                if assertion_row is None:
                    assertion_id = str(uuid4())
                    action = "added"
                    first_seen_at = last_seen_at = observed_at
                    connection.execute(
                        "INSERT INTO cti_indicator_assertions "
                        "(id, indicator_id, source_name, source_reference, confidence, "
                        "valid_from, valid_until, active, description, first_seen_at, "
                        "last_seen_at, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)",
                        (assertion_id, indicator_id, source_name, source_reference,
                         confidence, valid_from, valid_until, description,
                         first_seen_at, last_seen_at, recorded_at, recorded_at),
                    )
                    assertion_updated_at = recorded_at
                else:
                    current = self._assertion(assertion_row)
                    if current.indicator_id != indicator_id:
                        raise StorageError(
                            "IOC kaynak iddiası yanlış ana kayda bağlı; işlem durduruldu."
                        )
                    assertion_id = current.id
                    first_seen_at = min(
                        datetime.fromisoformat(current.first_seen_at),
                        datetime.fromisoformat(observed_at),
                    ).isoformat()
                    last_seen_at = max(
                        datetime.fromisoformat(current.last_seen_at),
                        datetime.fromisoformat(observed_at),
                    ).isoformat()
                    metadata_same = (
                        current.confidence, current.valid_from, current.valid_until,
                        current.description,
                    ) == (confidence, valid_from, valid_until, description)
                    observation_changed = (
                        first_seen_at != current.first_seen_at
                        or last_seen_at != current.last_seen_at
                    )
                    if current.active and metadata_same and not observation_changed:
                        connection.rollback()
                        return CtiIndicatorMutation(
                            "unchanged", self._indicator(indicator_row), current,
                        )
                    if not current.active:
                        action = "reactivated"
                    elif metadata_same:
                        action = "observed"
                    else:
                        action = "updated"
                    assertion_updated_at = max(
                        datetime.fromisoformat(current.updated_at),
                        datetime.fromisoformat(recorded_at),
                    ).isoformat()
                    connection.execute(
                        "UPDATE cti_indicator_assertions SET confidence = ?, "
                        "valid_from = ?, valid_until = ?, active = 1, description = ?, "
                        "first_seen_at = ?, last_seen_at = ?, updated_at = ? WHERE id = ?",
                        (confidence, valid_from, valid_until, description, first_seen_at,
                         last_seen_at, assertion_updated_at, assertion_id),
                    )

                connection.execute(
                    "INSERT INTO cti_indicator_assertion_events "
                    "(id, assertion_id, action, confidence, valid_from, valid_until, "
                    "description, reason, observed_at, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?)",
                    (str(uuid4()), assertion_id, action, confidence, valid_from,
                     valid_until, description, observed_at, recorded_at),
                )
                effective_indicator_time = max(
                    datetime.fromisoformat(indicator_updated_at),
                    datetime.fromisoformat(assertion_updated_at),
                ).isoformat()
                connection.execute(
                    "UPDATE cti_indicators SET updated_at = ? WHERE id = ?",
                    (effective_indicator_time, indicator_id),
                )
                indicator = self._indicator(
                    self._select_indicator(connection, indicator_id)
                )
                assertion = self._assertion(
                    self._select_assertion(connection, assertion_id)
                )
                connection.commit()
                return CtiIndicatorMutation(action, indicator, assertion)
            except BaseException:
                connection.rollback()
                raise

    def revoke_assertion(
        self, assertion_id: str, *, reason: str, recorded_at: str,
    ) -> CtiIndicatorMutation:
        try:
            assertion_id = normalize_assertion_id(assertion_id)
            reason = normalize_assertion_reason(reason)
            recorded_at = normalize_cti_timestamp(recorded_at)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("IOC kaynak iddiası kaldırma isteği geçersiz.") from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._select_assertion(connection, assertion_id)
                if row is None:
                    raise ValidationError("IOC kaynak iddiası bulunamadı.")
                current = self._assertion(row)
                indicator_row = self._select_indicator(connection, current.indicator_id)
                if indicator_row is None:
                    raise StorageError("IOC ana kaydı eksik; işlem durduruldu.")
                indicator = self._indicator(indicator_row)
                if not current.active:
                    connection.rollback()
                    return CtiIndicatorMutation("unchanged", indicator, current)
                if datetime.fromisoformat(current.last_seen_at) > datetime.fromisoformat(
                    recorded_at
                ):
                    raise ValidationError(
                        "IOC son gözlem zamanı sistem saatinden ileride; geri çekme durduruldu."
                    )
                updated_at = max(
                    datetime.fromisoformat(current.updated_at),
                    datetime.fromisoformat(recorded_at),
                ).isoformat()
                connection.execute(
                    "UPDATE cti_indicator_assertions SET active = 0, updated_at = ? "
                    "WHERE id = ?",
                    (updated_at, assertion_id),
                )
                connection.execute(
                    "INSERT INTO cti_indicator_assertion_events "
                    "(id, assertion_id, action, confidence, valid_from, valid_until, "
                    "description, reason, observed_at, recorded_at) "
                    "VALUES (?, ?, 'revoked', ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), assertion_id, current.confidence, current.valid_from,
                     current.valid_until, current.description, reason,
                     current.last_seen_at, recorded_at),
                )
                indicator_updated_at = max(
                    datetime.fromisoformat(indicator.updated_at),
                    datetime.fromisoformat(updated_at),
                ).isoformat()
                connection.execute(
                    "UPDATE cti_indicators SET updated_at = ? WHERE id = ?",
                    (indicator_updated_at, indicator.id),
                )
                result = CtiIndicatorMutation(
                    "revoked",
                    self._indicator(self._select_indicator(connection, indicator.id)),
                    self._assertion(self._select_assertion(connection, assertion_id)),
                )
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _is_current(assertion: CtiIndicatorAssertion, checked_at: str) -> bool:
        if not assertion.active:
            return False
        checked = datetime.fromisoformat(checked_at)
        if assertion.valid_from is not None:
            if datetime.fromisoformat(assertion.valid_from) > checked:
                return False
        if assertion.valid_until is not None:
            if datetime.fromisoformat(assertion.valid_until) <= checked:
                return False
        return True

    def list(
        self, *, indicator_type: str | None, active_only: bool, checked_at: str,
        limit: int,
    ) -> tuple[CtiIndicatorSummary, ...]:
        try:
            if indicator_type is not None:
                indicator_type = normalize_indicator_type(indicator_type)
            if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
                raise ValueError("Invalid list request")
            checked_at = normalize_cti_timestamp(checked_at)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("IOC liste isteği geçersiz.") from error
        clauses, values = [], []
        if indicator_type is not None:
            clauses.append("i.indicator_type = ?")
            values.append(indicator_type)
        if active_only:
            clauses.append(
                "EXISTS (SELECT 1 FROM cti_indicator_assertions a "
                "WHERE a.indicator_id = i.id AND a.active = 1 "
                "AND (a.valid_from IS NULL OR a.valid_from <= ?) "
                "AND (a.valid_until IS NULL OR a.valid_until > ?))"
            )
            values.extend((checked_at, checked_at))
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            indicator_rows = connection.execute(
                f"SELECT {_INDICATOR_SELECT} FROM cti_indicators i {where} "
                "ORDER BY i.indicator_type, i.value, i.id LIMIT ?",
                (*values, limit),
            ).fetchall()
            if not indicator_rows:
                connection.rollback()
                return ()
            ids = [row[0] for row in indicator_rows]
            placeholders = ",".join("?" for _ in ids)
            assertion_rows = connection.execute(
                f"SELECT {_ASSERTION_SELECT} FROM cti_indicator_assertions "
                f"WHERE indicator_id IN ({placeholders}) "
                "ORDER BY indicator_id, source_name, source_reference, id "
                f"LIMIT {_MAX_ASSERTIONS + 1}",
                ids,
            ).fetchall()
            connection.rollback()
        if len(assertion_rows) > _MAX_ASSERTIONS:
            raise StorageError("IOC liste kapsamı güvenli kaynak iddiası sınırını aşıyor.")
        indicators = tuple(self._indicator(row) for row in indicator_rows)
        assertions = tuple(self._assertion(row) for row in assertion_rows)
        grouped: dict[str, list[CtiIndicatorAssertion]] = {item.id: [] for item in indicators}
        for assertion in assertions:
            if assertion.indicator_id not in grouped:
                raise StorageError("IOC kaynak iddiası yanlış ana kayda bağlı; işlem durduruldu.")
            grouped[assertion.indicator_id].append(assertion)
        summaries = []
        for indicator in indicators:
            records = grouped[indicator.id]
            if not records:
                raise StorageError("IOC ana kaydının kaynak iddiası eksik; işlem durduruldu.")
            current = [item for item in records if self._is_current(item, checked_at)]
            if active_only and not current:
                raise StorageError("IOC etkinlik özeti tutarsız; işlem durduruldu.")
            summaries.append(CtiIndicatorSummary(
                indicator=indicator,
                active_assertion_count=sum(item.active for item in records),
                current_assertion_count=len(current),
                total_assertion_count=len(records),
                max_current_confidence=(
                    max(item.confidence for item in current) if current else None
                ),
            ))
        return tuple(summaries)

    def current_summary(
        self, indicator_type: str, value: str, *, checked_at: str,
    ) -> CtiIndicatorSummary | None:
        """Return one exact IOC only when at least one source claim is current."""
        try:
            indicator_type = normalize_indicator_type(indicator_type)
            value = normalize_indicator_value(indicator_type, value)
            checked_at = normalize_cti_timestamp(checked_at)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("IOC güncel eşleşme isteği geçersiz.") from error
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            indicator_row = connection.execute(
                f"SELECT {_INDICATOR_SELECT} FROM cti_indicators "
                "WHERE indicator_type = ? AND value = ?",
                (indicator_type, value),
            ).fetchone()
            if indicator_row is None:
                connection.rollback()
                return None
            assertion_rows = connection.execute(
                f"SELECT {_ASSERTION_SELECT} FROM cti_indicator_assertions "
                "WHERE indicator_id = ? ORDER BY source_name, source_reference, id "
                f"LIMIT {_MAX_ASSERTIONS + 1}",
                (indicator_row[0],),
            ).fetchall()
            connection.rollback()
        if len(assertion_rows) > _MAX_ASSERTIONS:
            raise StorageError("IOC eşleşmesi güvenli kaynak iddiası sınırını aşıyor.")
        indicator = self._indicator(indicator_row)
        assertions = tuple(self._assertion(row) for row in assertion_rows)
        if not assertions:
            raise StorageError("IOC ana kaydının kaynak iddiası eksik; işlem durduruldu.")
        if any(item.indicator_id != indicator.id for item in assertions):
            raise StorageError("IOC kaynak iddiası yanlış ana kayda bağlı; işlem durduruldu.")
        current = tuple(item for item in assertions if self._is_current(item, checked_at))
        if not current:
            return None
        return CtiIndicatorSummary(
            indicator=indicator,
            active_assertion_count=sum(item.active for item in assertions),
            current_assertion_count=len(current),
            total_assertion_count=len(assertions),
            max_current_confidence=max(item.confidence for item in current),
        )

    def export_snapshot(
        self, *, indicator_type: str | None, checked_at: str,
    ) -> CtiIndicatorExportSnapshot:
        """Read every currently supported IOC in one bounded SQLite snapshot."""
        try:
            if indicator_type is not None:
                indicator_type = normalize_indicator_type(indicator_type)
            checked_at = normalize_cti_timestamp(checked_at)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("STIX IOC dışa aktarma isteği geçersiz.") from error

        clauses = [
            "EXISTS (SELECT 1 FROM cti_indicator_assertions current "
            "WHERE current.indicator_id = i.id AND current.active = 1 "
            "AND (current.valid_from IS NULL OR current.valid_from <= ?) "
            "AND (current.valid_until IS NULL OR current.valid_until > ?))"
        ]
        values: list[str] = [checked_at, checked_at]
        if indicator_type is not None:
            clauses.insert(0, "i.indicator_type = ?")
            values.insert(0, indicator_type)
        where = "WHERE " + " AND ".join(clauses)
        qualified_assertions = "a." + _ASSERTION_SELECT.replace(", ", ", a.")

        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            indicator_rows = connection.execute(
                f"SELECT {_INDICATOR_SELECT} FROM cti_indicators i {where} "
                "ORDER BY i.indicator_type, i.value, i.id "
                f"LIMIT {_MAX_EXPORT_INDICATORS + 1}",
                tuple(values),
            ).fetchall()
            if len(indicator_rows) > _MAX_EXPORT_INDICATORS:
                connection.rollback()
                raise StorageError(
                    "STIX dışa aktarma kapsamı 50.000 güncel IOC sınırını aşıyor."
                )
            assertion_rows = []
            if indicator_rows:
                assertion_rows = connection.execute(
                    f"SELECT {qualified_assertions} FROM cti_indicator_assertions a "
                    "JOIN cti_indicators i ON i.id = a.indicator_id "
                    f"{where} ORDER BY a.indicator_id, a.source_name, "
                    "a.source_reference, a.id "
                    f"LIMIT {_MAX_EXPORT_ASSERTIONS + 1}",
                    tuple(values),
                ).fetchall()
            connection.rollback()

        if len(assertion_rows) > _MAX_EXPORT_ASSERTIONS:
            raise StorageError(
                "STIX dışa aktarma kapsamı 50.000 kaynak iddiası sınırını aşıyor."
            )
        indicators = tuple(self._indicator(row) for row in indicator_rows)
        assertions = tuple(self._assertion(row) for row in assertion_rows)
        grouped: dict[str, list[CtiIndicatorAssertion]] = {
            indicator.id: [] for indicator in indicators
        }
        for assertion in assertions:
            if assertion.indicator_id not in grouped:
                raise StorageError(
                    "STIX IOC kaynak iddiası yanlış ana kayda bağlı; işlem durduruldu."
                )
            grouped[assertion.indicator_id].append(assertion)

        items = []
        for indicator in indicators:
            records = grouped[indicator.id]
            if not records:
                raise StorageError(
                    "STIX IOC ana kaydının kaynak iddiası eksik; işlem durduruldu."
                )
            if any(
                datetime.fromisoformat(assertion.updated_at)
                > datetime.fromisoformat(indicator.updated_at)
                for assertion in records
            ):
                raise StorageError(
                    "STIX IOC ana kayıt zamanı kaynak iddialarıyla tutarsız."
                )
            current = tuple(
                assertion for assertion in records
                if self._is_current(assertion, checked_at)
            )
            if not current:
                raise StorageError(
                    "STIX IOC etkinlik özeti tutarsız; işlem durduruldu."
                )
            items.append(CtiIndicatorExportItem(indicator, current))
        return CtiIndicatorExportSnapshot(
            checked_at=checked_at, indicator_type=indicator_type, items=tuple(items),
        )

    def _details(
        self, connection, indicator_row, *, assertion_limit: int, event_limit: int,
    ) -> CtiIndicatorDetails:
        indicator = self._indicator(indicator_row)
        assertion_rows = connection.execute(
            f"SELECT {_ASSERTION_SELECT} FROM cti_indicator_assertions "
            "WHERE indicator_id = ? ORDER BY source_name, source_reference, id "
            f"LIMIT {_MAX_ASSERTIONS + 1}",
            (indicator.id,),
        ).fetchall()
        if len(assertion_rows) > _MAX_ASSERTIONS:
            raise StorageError("IOC kaynak iddiası güvenli inceleme sınırını aşıyor.")
        event_rows = connection.execute(
            f"SELECT e.{_EVENT_SELECT.replace(', ', ', e.')} "
            "FROM cti_indicator_assertion_events e "
            "JOIN cti_indicator_assertions a ON a.id = e.assertion_id "
            "WHERE a.indicator_id = ? ORDER BY e.rowid DESC "
            f"LIMIT {_MAX_EVENTS + 1}",
            (indicator.id,),
        ).fetchall()
        if len(event_rows) > _MAX_EVENTS:
            raise StorageError("IOC geçmişi güvenli inceleme sınırını aşıyor.")
        assertions = tuple(self._assertion(row) for row in assertion_rows)
        events = tuple(self._event(row) for row in event_rows)
        if not assertions:
            raise StorageError("IOC ana kaydının kaynak iddiası eksik; işlem durduruldu.")
        assertion_ids = {item.id for item in assertions}
        event_assertion_ids = {item.assertion_id for item in events}
        if not event_assertion_ids.issubset(assertion_ids) or not assertion_ids.issubset(
            event_assertion_ids
        ):
            raise StorageError("IOC kaynak geçmişi eksik veya yanlış bağlı; işlem durduruldu.")
        if any(item.indicator_id != indicator.id for item in assertions):
            raise StorageError("IOC kaynak iddiası yanlış ana kayda bağlı; işlem durduruldu.")
        if any(
            datetime.fromisoformat(item.updated_at)
            > datetime.fromisoformat(indicator.updated_at)
            for item in assertions
        ):
            raise StorageError("IOC ana kayıt zamanı kaynak geçmişiyle tutarsız.")
        return CtiIndicatorDetails(
            indicator=indicator, assertions=assertions[:assertion_limit],
            events=events[:event_limit], total_assertion_count=len(assertions),
            total_event_count=len(events),
        )

    def details(
        self, indicator_id: str, *, assertion_limit: int, event_limit: int,
    ) -> CtiIndicatorDetails:
        indicator_id = normalize_indicator_id(indicator_id)
        if (
            type(assertion_limit) is not int or not 1 <= assertion_limit <= 500
            or type(event_limit) is not int or not 1 <= event_limit <= 500
        ):
            raise ValidationError("IOC ayrıntı sınırı geçersiz.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._select_indicator(connection, indicator_id)
            if row is None:
                raise ValidationError("IOC kaydı bulunamadı.")
            details = self._details(
                connection, row, assertion_limit=assertion_limit, event_limit=event_limit,
            )
            connection.rollback()
        return details

    def lookup(
        self, indicator_type: str, value: str, *, assertion_limit: int,
        event_limit: int,
    ) -> CtiIndicatorDetails:
        indicator_type = normalize_indicator_type(indicator_type)
        value = normalize_indicator_value(indicator_type, value)
        if (
            type(assertion_limit) is not int or not 1 <= assertion_limit <= 500
            or type(event_limit) is not int or not 1 <= event_limit <= 500
        ):
            raise ValidationError("IOC ayrıntı sınırı geçersiz.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                f"SELECT {_INDICATOR_SELECT} FROM cti_indicators "
                "WHERE indicator_type = ? AND value = ?",
                (indicator_type, value),
            ).fetchone()
            if row is None:
                raise ValidationError("IOC kaydı bulunamadı.")
            details = self._details(
                connection, row, assertion_limit=assertion_limit, event_limit=event_limit,
            )
            connection.rollback()
        return details
