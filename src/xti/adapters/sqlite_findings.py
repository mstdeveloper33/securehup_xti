"""Atomic offline imports, evidence links and append-only review history."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.domain.assets import ValidationError
from xti.domain.findings import (
    Finding,
    FindingDetails,
    ImportDocument,
    ImportSummary,
    MatchCandidate,
    Observation,
    Review,
)


_DATETIME_TYPE = datetime
_FINDING_COLUMNS = (
    "id, asset_id, asset_value, domain, rule_version, reasons, status, "
    "created_at, last_seen_at"
)


class SQLiteFindingRepository:
    """Persist already validated import documents without performing network I/O."""

    def __init__(self, path: Path, clock: Callable[[], datetime] | None = None) -> None:
        self._storage = SQLiteAssetRepository(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self._clock()
        if (
            not isinstance(value, _DATETIME_TYPE)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise StorageError("Kayıt zamanı geçersiz; işlem durduruldu.")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _not_expired(value, now: datetime) -> bool:
        if value is None:
            return True
        try:
            if not isinstance(value, str) or not value or len(value) > 64:
                raise ValueError("Invalid expiration")
            parsed = _DATETIME_TYPE.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("Invalid expiration")
            return parsed.astimezone(timezone.utc) > now
        except (ValueError, TypeError, OverflowError) as exc:
            raise StorageError("İstisna kaydının bitiş zamanı bozuk; işlem durduruldu.") from exc

    @staticmethod
    def _finding(row: tuple) -> Finding:
        try:
            reasons = json.loads(row[5])
        except (ValueError, TypeError) as error:
            raise StorageError("Bulgunun açıklama kaydı okunamadı.") from error
        if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
            raise StorageError("Bulgunun açıklama kaydı beklenen biçimde değil.")
        return Finding(
            id=row[0], asset_id=row[1], asset_value=row[2], domain=row[3],
            rule_version=row[4], reasons=tuple(reasons), status=row[6],
            created_at=row[7], last_seen_at=row[8],
        )

    @staticmethod
    def _get(connection: sqlite3.Connection, finding_id: str) -> Finding:
        row = connection.execute(
            "SELECT " + _FINDING_COLUMNS + " FROM findings WHERE id = ?", (finding_id,)
        ).fetchone()
        if row is None:
            raise ValidationError("Bulgu bulunamadı. Kimliği bulgu listesinden kontrol edin.")
        return SQLiteFindingRepository._finding(row)

    @staticmethod
    def _notify_new_finding(connection: sqlite3.Connection, finding_id: str, created_at: str) -> None:
        """The event shares the finding transaction; read state is never reset."""
        connection.execute(
            "INSERT INTO notifications "
            "(sequence, id, finding_id, event_type, origin, created_at, read_at) "
            "VALUES (?, ?, ?, 'finding_created', 'new', ?, NULL) "
            "ON CONFLICT(finding_id, event_type) DO NOTHING",
            (next_notification_sequence(connection), str(uuid4()), finding_id, created_at),
        )

    def save_import(
        self, document: ImportDocument, candidates: Sequence[MatchCandidate]
    ) -> ImportSummary:
        """Commit all observations and candidate matches together, or none.

        Observation identity is content hash + original source line. A renamed
        file therefore cannot duplicate evidence. Candidate identity is separate,
        allowing an old document to be matched against a newly registered asset.
        """
        observations_created = 0
        findings_created = 0
        findings_existing = 0
        findings_suppressed = 0
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                now_instant = self._now()
                now = now_instant.isoformat()
                observations_by_domain: dict[str, set[str]] = {}
                for record in document.records:
                    cursor = connection.execute(
                        "INSERT INTO observations (id, domain, raw_domain, source_name, "
                        "source_sha256, source_line, observed_at, ingested_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(source_sha256, source_line) DO NOTHING",
                        (
                            str(uuid4()), record.domain, record.raw_domain, document.source_name,
                            document.sha256, record.source_line, record.observed_at, now,
                        ),
                    )
                    observations_created += cursor.rowcount
                    observation = connection.execute(
                        "SELECT id, domain, raw_domain, observed_at FROM observations "
                        "WHERE source_sha256 = ? AND source_line = ?",
                        (document.sha256, record.source_line),
                    ).fetchone()
                    if observation[1:] != (record.domain, record.raw_domain, record.observed_at):
                        raise StorageError(
                            "Aynı dosya ve satır için çelişen gözlem bulundu. "
                            "İçe aktarma geri alındı."
                        )
                    observations_by_domain.setdefault(record.domain, set()).add(observation[0])

                processed: set[tuple[str, str, str]] = set()
                active_pairs: set[tuple[str, str]] = set()
                asset_ids = tuple(dict.fromkeys(item.asset_id for item in candidates))
                for start in range(0, len(asset_ids), 400):
                    chunk = asset_ids[start:start + 400]
                    placeholders = ",".join("?" for _ in chunk)
                    for asset_id, domain, expires_at in connection.execute(
                        "SELECT asset_id, domain, expires_at FROM allowlist_entries "
                        "WHERE active = 1 "
                        f"AND asset_id IN ({placeholders})", chunk,
                    ):
                        if self._not_expired(expires_at, now_instant):
                            active_pairs.add((asset_id, domain))
                for candidate in candidates:
                    key = (candidate.asset_id, candidate.domain, candidate.rule_version)
                    if key in processed:
                        continue
                    processed.add(key)
                    observation_ids = observations_by_domain.get(candidate.domain)
                    if not observation_ids:
                        raise StorageError(
                            "Bulguya ait kaynak gözlem bulunamadı. İçe aktarma geri alındı."
                        )
                    asset = connection.execute(
                        "SELECT value FROM assets WHERE id = ?", (candidate.asset_id,)
                    ).fetchone()
                    if asset != (candidate.asset_value,):
                        raise StorageError(
                            "Bulguya ait kayıtlı adres değişti veya bulunamadı. "
                            "İçe aktarmayı yeniden çalıştırın."
                        )
                    if (candidate.asset_id, candidate.domain) in active_pairs:
                        findings_suppressed += 1
                        continue
                    cursor = connection.execute(
                        "INSERT INTO findings (" + _FINDING_COLUMNS + ") "
                        "VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?) "
                        "ON CONFLICT(asset_id, domain, rule_version) DO NOTHING",
                        (
                            str(uuid4()), candidate.asset_id, candidate.asset_value,
                            candidate.domain, candidate.rule_version,
                            json.dumps(candidate.reasons, ensure_ascii=True), now, now,
                        ),
                    )
                    created = bool(cursor.rowcount)
                    if created:
                        findings_created += 1
                    else:
                        findings_existing += 1
                    finding_id = connection.execute(
                        "SELECT id FROM findings WHERE asset_id = ? AND domain = ? "
                        "AND rule_version = ?", key,
                    ).fetchone()[0]
                    if created:
                        self._notify_new_finding(connection, finding_id, now)
                    links_created = 0
                    for observation_id in sorted(observation_ids):
                        cursor = connection.execute(
                            "INSERT INTO finding_observations (finding_id, observation_id) "
                            "VALUES (?, ?) ON CONFLICT(finding_id, observation_id) DO NOTHING",
                            (finding_id, observation_id),
                        )
                        links_created += cursor.rowcount
                    if links_created:
                        connection.execute(
                            "UPDATE findings SET last_seen_at = MAX(last_seen_at, ?) WHERE id = ?",
                            (now, finding_id),
                        )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return ImportSummary(
            total_records=len(document.records),
            observations_created=observations_created,
            observations_existing=len(document.records) - observations_created,
            findings_created=findings_created,
            findings_existing=findings_existing,
            findings_suppressed=findings_suppressed,
        )

    def list_findings(self, status: str | None = None) -> list[Finding]:
        with self._storage._connection(readonly=True) as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT " + _FINDING_COLUMNS + " FROM findings ORDER BY created_at, id"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT " + _FINDING_COLUMNS +
                    " FROM findings WHERE status = ? ORDER BY created_at, id", (status,)
                ).fetchall()
        return [self._finding(row) for row in rows]

    def get_finding(self, finding_id: str) -> FindingDetails:
        with self._storage._connection(readonly=True) as connection:
            # One snapshot keeps the status, observations and review history consistent.
            connection.execute("BEGIN")
            details = self._details(connection, finding_id)
            connection.rollback()
        return details

    @staticmethod
    def _details(connection: sqlite3.Connection, finding_id: str) -> FindingDetails:
        """Read evidence on the caller's connection and snapshot."""
        finding = SQLiteFindingRepository._get(connection, finding_id)
        observations = tuple(
            Observation(*row) for row in connection.execute(
                "SELECT o.id, o.domain, o.raw_domain, o.source_name, o.source_sha256, "
                "o.source_line, o.observed_at, o.ingested_at FROM observations o "
                "JOIN finding_observations link ON link.observation_id = o.id "
                "WHERE link.finding_id = ? "
                "ORDER BY o.ingested_at, o.source_sha256, o.source_line, o.id",
                (finding_id,),
            )
        )
        reviews = tuple(
            Review(*row) for row in connection.execute(
                "SELECT id, finding_id, decision, reason, created_at FROM reviews "
                # Insertion order is stable when the device clock moves backwards.
                "WHERE finding_id = ? ORDER BY rowid", (finding_id,),
            )
        )
        return FindingDetails(finding=finding, observations=observations, reviews=reviews)

    def review_finding(self, finding_id: str, decision: str, reason: str) -> Finding:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._get(connection, finding_id)
                connection.execute(
                    "INSERT INTO reviews (id, finding_id, decision, reason, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (str(uuid4()), finding_id, decision, reason, self._now().isoformat()),
                )
                connection.execute(
                    "UPDATE findings SET status = ? WHERE id = ?", (decision, finding_id)
                )
                finding = self._get(connection, finding_id)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return finding
