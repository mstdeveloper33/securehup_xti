"""Durable provider waits that can only be extended, never silently shortened."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.operations import SourceCooldown


_PROVIDERS = frozenset({"crt.sh", "urlscan", "circl", "ripestat"})
_REASONS = frozenset({"request_spacing", "retry_after", "rate_limit", "provider_wait"})
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)


def _provider(value) -> str:
    if not isinstance(value, str) or value not in _PROVIDERS:
        raise ValueError("Unknown provider")
    return value


def _timestamp(value) -> datetime:
    if not isinstance(value, str) or len(value) > 64 or _TIMESTAMP.fullmatch(value) is None:
        raise ValueError("Invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def _record(provider, not_before, recorded_at, reason) -> SourceCooldown:
    provider = _provider(provider)
    deadline = _timestamp(not_before)
    observed = _timestamp(recorded_at)
    if deadline < observed:
        raise ValueError("Wait deadline precedes receipt")
    if not isinstance(reason, str) or reason not in _REASONS:
        raise ValueError("Unknown wait reason")
    return SourceCooldown(provider, deadline.isoformat(), observed.isoformat(), reason)


class SQLiteCooldownRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _row(row) -> SourceCooldown:
        try:
            return _record(*row)
        except (ValueError, TypeError, OverflowError) as error:
            raise StorageError("Kaynağın bekleme kaydı bozuk; yeni istek gönderilmedi.") from error

    def get(self, provider: str) -> SourceCooldown | None:
        try:
            _provider(provider)
        except ValueError as error:
            raise ValidationError("Bu internet kaynağı desteklenmiyor.") from error
        with self._storage._connection(readonly=True) as connection:
            row = connection.execute(
                "SELECT provider, not_before, recorded_at, reason "
                "FROM provider_cooldowns WHERE provider = ?", (provider,),
            ).fetchone()
        return self._row(row) if row is not None else None

    def list(self) -> tuple[SourceCooldown, ...]:
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT provider, not_before, recorded_at, reason "
                "FROM provider_cooldowns ORDER BY provider"
            ).fetchall()
        return tuple(self._row(row) for row in rows)

    def extend(
        self, provider: str, not_before: str, recorded_at: str, reason: str,
    ) -> SourceCooldown:
        try:
            candidate = _record(provider, not_before, recorded_at, reason)
        except (ValueError, TypeError, OverflowError) as error:
            raise ValidationError("Kaynağın bekleme bilgisi geçersiz; kaydedilmedi.") from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT provider, not_before, recorded_at, reason "
                    "FROM provider_cooldowns WHERE provider = ?", (provider,),
                ).fetchone()
                previous = self._row(row) if row is not None else None
                if previous is not None and _timestamp(previous.not_before) >= _timestamp(candidate.not_before):
                    # Preserve the explanation and receipt time of the longer hold.
                    connection.rollback()
                    return previous
                connection.execute(
                    "INSERT INTO provider_cooldowns (provider, not_before, recorded_at, reason) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(provider) DO UPDATE SET "
                    "not_before = excluded.not_before, recorded_at = excluded.recorded_at, "
                    "reason = excluded.reason",
                    (candidate.provider, candidate.not_before, candidate.recorded_at, candidate.reason),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return candidate
