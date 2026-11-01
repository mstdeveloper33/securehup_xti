"""SQLite persistence for passive CT subdomain candidates and human decisions."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.surface import (
    SurfaceCandidate,
    SurfaceCandidateDetails,
    SurfaceCandidateEvent,
    SurfaceCandidateEvidence,
    SurfaceCandidateSaveSummary,
    SurfaceCandidateSource,
    SurfaceDiscoveryRun,
    SurfaceDiscoveryRunRequest,
)


_STATUSES = frozenset({"pending", "owned", "rejected"})
_ACTIONS = frozenset({"discovered", "owned", "rejected", "reopened", "updated"})
_INITIAL_REASON = "Pasif dış yüzey kaynağından bulundu."
_RUN_STATUSES = frozenset({"complete", "partial", "failed"})
_PROVIDERS = frozenset({"crt.sh", "theharvester"})
_MAX_SEQUENCE = 2**63 - 1


def _text(value, *, minimum: int = 0, maximum: int) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError("Invalid text")
    return value


def _identifier(value) -> str:
    value = _text(value, minimum=1, maximum=64)
    if not value.isprintable():
        raise ValueError("Invalid identifier")
    return value


def _timestamp(value) -> str:
    value = _text(value, minimum=1, maximum=64)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _optional_timestamp(value) -> str | None:
    return None if value is None else _timestamp(value)


def _reason(value) -> str:
    value = _text(value, minimum=1, maximum=1000)
    if value != value.strip() or not value.isprintable():
        raise ValueError("Invalid reason")
    return value


def _status(value) -> str:
    value = _text(value, minimum=1, maximum=16)
    if value not in _STATUSES:
        raise ValueError("Invalid status")
    return value


def _sha256(value) -> str:
    value = _text(value, minimum=64, maximum=64)
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError("Invalid SHA-256")
    return value


def _printable(value, *, maximum: int, minimum: int = 1) -> str:
    value = _text(value, minimum=minimum, maximum=maximum)
    if not value.isprintable():
        raise ValueError("Invalid external text")
    return value


def _strict_subdomain(domain: str, asset_value: str) -> str:
    domain = normalize_domain(domain)
    asset_value = normalize_domain(asset_value)
    if domain == asset_value or not domain.endswith("." + asset_value):
        raise ValueError("Candidate is outside the registered root")
    return domain


def _validated_evidence(
    item: SurfaceCandidateEvidence, asset_value: str,
) -> SurfaceCandidateEvidence:
    if not isinstance(item, SurfaceCandidateEvidence):
        raise ValueError("Invalid evidence")
    provider = _printable(item.provider, maximum=32)
    if provider not in _PROVIDERS:
        raise ValueError("Unsupported provider")
    return SurfaceCandidateEvidence(
        domain=_strict_subdomain(item.domain, asset_value),
        provider=provider,
        source_name=_printable(item.source_name, maximum=2048),
        source_sha256=_sha256(item.source_sha256),
        raw_domain=_printable(item.raw_domain, maximum=1024),
        observed_at=_optional_timestamp(item.observed_at),
    )


def _nonnegative(value) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Invalid count")
    return value


def _validated_request(
    request: SurfaceDiscoveryRunRequest, evidence: tuple[SurfaceCandidateEvidence, ...],
) -> SurfaceDiscoveryRunRequest:
    if not isinstance(request, SurfaceDiscoveryRunRequest):
        raise ValueError("Invalid discovery run")
    status = _printable(request.status, maximum=16)
    if status not in _RUN_STATUSES:
        raise ValueError("Invalid run status")
    source_url = _printable(request.source_url, maximum=4096)
    started_at = _timestamp(request.started_at)
    finished_at = _timestamp(request.finished_at)
    if datetime.fromisoformat(finished_at) < datetime.fromisoformat(started_at):
        raise ValueError("Invalid run interval")
    if (
        not isinstance(request.warnings, tuple) or len(request.warnings) > 100
        or any(
            not isinstance(item, str) or not 1 <= len(item) <= 1000 or not item.isprintable()
            for item in request.warnings
        )
    ):
        raise ValueError("Invalid warnings")
    error = None if request.error is None else _printable(request.error, maximum=2000)
    provider = _printable(request.provider, maximum=32)
    if provider not in _PROVIDERS:
        raise ValueError("Invalid provider")
    if any(item.provider != provider for item in evidence):
        raise ValueError("Evidence provider mismatch")
    candidate_count = _nonnegative(request.candidate_count)
    if candidate_count != len({item.domain for item in evidence}):
        raise ValueError("Candidate count mismatch")
    if (status == "failed") != (error is not None) or (status == "failed" and evidence):
        raise ValueError("Invalid failed run")
    return SurfaceDiscoveryRunRequest(
        status, source_url, started_at, finished_at,
        _nonnegative(request.record_count), _nonnegative(request.skipped_names),
        _nonnegative(request.ignored_names), request.warnings, candidate_count, error,
        provider,
    )


class SQLiteSurfaceCandidateRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _candidate(row) -> SurfaceCandidate:
        try:
            identifier = _identifier(row[0])
            asset_id = _identifier(row[1])
            asset_value = normalize_domain(_text(row[2], minimum=1, maximum=253))
            domain = _strict_subdomain(row[3], asset_value)
            status = _status(row[4])
            reason = _reason(row[5])
            first_seen = _timestamp(row[6])
            last_seen = _timestamp(row[7])
            created_at = _timestamp(row[8])
            updated_at = _timestamp(row[9])
            if datetime.fromisoformat(first_seen) > datetime.fromisoformat(last_seen):
                raise ValueError("Invalid seen range")
            if row[10] != asset_value:
                raise ValueError("Candidate disagrees with asset")
            source_count = row[11]
            if type(source_count) is not int or source_count < 1:
                raise ValueError("Invalid source count")
            return SurfaceCandidate(
                identifier, asset_id, asset_value, domain, status, reason,
                first_seen, last_seen, created_at, updated_at, source_count,
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise StorageError("Alt alan adı aday kaydı bozuk; işlem durduruldu.") from exc

    @staticmethod
    def _source(row) -> SurfaceCandidateSource:
        try:
            provider = _printable(row[2], maximum=32)
            if provider != "crt.sh":
                raise ValueError("Unsupported provider")
            return SurfaceCandidateSource(
                _identifier(row[0]), _identifier(row[1]), provider,
                _printable(row[3], maximum=2048), _sha256(row[4]),
                _printable(row[5], maximum=1024), _optional_timestamp(row[6]),
                _timestamp(row[7]),
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise StorageError("Alt alan adı kaynak kanıtı bozuk; işlem durduruldu.") from exc

    @staticmethod
    def _event(row) -> SurfaceCandidateEvent:
        try:
            action = _printable(row[2], maximum=16)
            if action not in _ACTIONS:
                raise ValueError("Invalid action")
            return SurfaceCandidateEvent(
                _identifier(row[0]), _identifier(row[1]), action,
                _status(row[3]), _reason(row[4]), _timestamp(row[5]),
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise StorageError("Alt alan adı karar geçmişi bozuk; işlem durduruldu.") from exc

    @staticmethod
    def _candidate_row(connection: sqlite3.Connection, candidate_id: str):
        return connection.execute(
            "SELECT c.id, c.asset_id, c.asset_value, c.domain, c.status, c.reason, "
            "c.first_seen_at, c.last_seen_at, c.created_at, c.updated_at, a.value, "
            "(SELECT COUNT(*) FROM surface_candidate_sources s WHERE s.candidate_id = c.id) "
            "FROM surface_candidates c JOIN assets a ON a.id = c.asset_id WHERE c.id = ?",
            (candidate_id,),
        ).fetchone()

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection, candidate_id: str, action: str,
        status: str, reason: str, recorded_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO surface_candidate_events "
            "(id, candidate_id, action, status, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), candidate_id, action, status, reason, recorded_at),
        )

    @staticmethod
    def _next_notification_sequence(connection: sqlite3.Connection) -> int:
        return next_notification_sequence(connection)

    @classmethod
    def _save_validated(
        cls, connection: sqlite3.Connection, asset_id: str, asset_value: str,
        validated: tuple[SurfaceCandidateEvidence, ...], recorded_at: str, *, notify: bool,
    ) -> SurfaceCandidateSaveSummary:
        created_candidates: set[str] = set()
        existing_candidates: set[str] = set()
        evidence_created = evidence_existing = 0
        asset = connection.execute(
            "SELECT value FROM assets WHERE id = ?", (asset_id,),
        ).fetchone()
        if asset != (asset_value,):
            raise ValidationError("Kayıtlı kök adres değişti veya bulunamadı.")
        for item in validated:
            seen_at = item.observed_at or recorded_at
            row = connection.execute(
                "SELECT id FROM surface_candidates WHERE asset_id = ? AND domain = ?",
                (asset_id, item.domain),
            ).fetchone()
            if row is None:
                candidate_id = str(uuid4())
                connection.execute(
                    "INSERT INTO surface_candidates "
                    "(id, asset_id, asset_value, domain, status, reason, first_seen_at, "
                    "last_seen_at, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
                    (candidate_id, asset_id, asset_value, item.domain, _INITIAL_REASON,
                     seen_at, seen_at, recorded_at, recorded_at),
                )
                cls._insert_event(
                    connection, candidate_id, "discovered", "pending",
                    _INITIAL_REASON, recorded_at,
                )
                if notify:
                    connection.execute(
                        "INSERT INTO surface_candidate_notifications "
                        "(sequence, id, candidate_id, event_type, origin, created_at, read_at) "
                        "VALUES (?, ?, ?, 'surface_candidate_discovered', 'new', ?, NULL)",
                        (cls._next_notification_sequence(connection), str(uuid4()),
                         candidate_id, recorded_at),
                    )
                created_candidates.add(candidate_id)
            else:
                candidate_id = _identifier(row[0])
                candidate = cls._candidate(cls._candidate_row(connection, candidate_id))
                if candidate.asset_id != asset_id or candidate.domain != item.domain:
                    raise StorageError("Alt alan adı adayı kayıtlı kökle uyuşmuyor.")
                if candidate_id not in created_candidates:
                    existing_candidates.add(candidate_id)

            source_row = connection.execute(
                "SELECT id, candidate_id, provider, source_name, source_sha256, "
                "raw_domain, observed_at, recorded_at FROM surface_candidate_sources "
                "WHERE candidate_id = ? AND source_sha256 = ?",
                (candidate_id, item.source_sha256),
            ).fetchone()
            if source_row is not None:
                existing = cls._source(source_row)
                if (
                    existing.provider != item.provider
                    or existing.source_name != item.source_name
                    or existing.raw_domain != item.raw_domain
                    or existing.observed_at != item.observed_at
                ):
                    raise ValidationError(
                        "Aynı sertifika özeti çelişen kaynak kanıtı taşıyor; kayıt yapılmadı."
                    )
                evidence_existing += 1
                continue

            connection.execute(
                "INSERT INTO surface_candidate_sources "
                "(id, candidate_id, provider, source_name, source_sha256, raw_domain, "
                "observed_at, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid4()), candidate_id, item.provider, item.source_name,
                 item.source_sha256, item.raw_domain, item.observed_at, recorded_at),
            )
            candidate = cls._candidate(cls._candidate_row(connection, candidate_id))
            first_seen = min(
                datetime.fromisoformat(candidate.first_seen_at), datetime.fromisoformat(seen_at),
            ).isoformat()
            last_seen = max(
                datetime.fromisoformat(candidate.last_seen_at), datetime.fromisoformat(seen_at),
            ).isoformat()
            connection.execute(
                "UPDATE surface_candidates SET first_seen_at = ?, last_seen_at = ?, "
                "updated_at = ? WHERE id = ?",
                (first_seen, last_seen, recorded_at, candidate_id),
            )
            evidence_created += 1
        return SurfaceCandidateSaveSummary(
            len(created_candidates), len(existing_candidates), evidence_created, evidence_existing,
        )

    @staticmethod
    def _validated_batch(
        asset_id: str, asset_value: str, evidence: tuple[SurfaceCandidateEvidence, ...],
        *, allow_empty: bool,
    ) -> tuple[str, str, tuple[SurfaceCandidateEvidence, ...]]:
        asset_id = _identifier(asset_id)
        asset_value = normalize_domain(asset_value)
        minimum = 0 if allow_empty else 1
        if not isinstance(evidence, tuple) or not minimum <= len(evidence) <= 10_000:
            raise ValueError("Invalid evidence batch")
        validated = tuple(_validated_evidence(item, asset_value) for item in evidence)
        if len({(item.domain, item.source_sha256) for item in validated}) != len(validated):
            raise ValueError("Duplicate evidence")
        return asset_id, asset_value, validated

    @staticmethod
    def _run(row) -> SurfaceDiscoveryRun:
        try:
            sequence = row[0]
            if type(sequence) is not int or not 1 <= sequence <= _MAX_SEQUENCE:
                raise ValueError("Invalid run sequence")
            warnings = json.loads(row[12])
            if (
                not isinstance(warnings, list) or len(warnings) > 100
                or any(
                    not isinstance(item, str) or not 1 <= len(item) <= 1000
                    or not item.isprintable() for item in warnings
                )
            ):
                raise ValueError("Invalid saved warnings")
            status = _printable(row[5], maximum=16)
            if status not in _RUN_STATUSES:
                raise ValueError("Invalid saved status")
            error = None if row[18] is None else _printable(row[18], maximum=2000)
            if (status == "failed") != (error is not None):
                raise ValueError("Invalid saved failure")
            started_at, finished_at = _timestamp(row[7]), _timestamp(row[8])
            if datetime.fromisoformat(finished_at) < datetime.fromisoformat(started_at):
                raise ValueError("Invalid saved interval")
            provider = _printable(row[4], maximum=32)
            if provider not in _PROVIDERS:
                raise ValueError("Invalid saved provider")
            return SurfaceDiscoveryRun(
                sequence, _identifier(row[1]), _identifier(row[2]),
                normalize_domain(_text(row[3], minimum=1, maximum=253)), provider, status,
                _printable(row[6], maximum=4096), started_at, finished_at,
                *(_nonnegative(row[index]) for index in range(9, 12)), tuple(warnings),
                *(_nonnegative(row[index]) for index in range(13, 18)), error,
            )
        except (ValueError, TypeError, OverflowError, json.JSONDecodeError) as exc:
            raise StorageError("Pasif keşif geçmişi bozuk; işlem durduruldu.") from exc

    @staticmethod
    def _run_row(connection: sqlite3.Connection, run_id: str):
        return connection.execute(
            "SELECT sequence, id, asset_id, asset_value, provider, status, source_url, "
            "started_at, finished_at, record_count, skipped_names, ignored_names, warnings, "
            "candidate_count, candidates_created, candidates_existing, evidence_created, "
            "evidence_existing, error FROM surface_discovery_runs WHERE id = ?",
            (run_id,),
        ).fetchone()

    def record_discovery(
        self, asset_id: str, asset_value: str,
        evidence: tuple[SurfaceCandidateEvidence, ...], request: SurfaceDiscoveryRunRequest,
    ) -> tuple[SurfaceCandidateSaveSummary, SurfaceDiscoveryRun]:
        try:
            asset_id, asset_value, validated = self._validated_batch(
                asset_id, asset_value, evidence, allow_empty=True,
            )
            request = _validated_request(request, validated)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValidationError("Pasif keşif çalışma kaydı geçersiz; kayıt yapılmadı.") from exc
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                summary = self._save_validated(
                    connection, asset_id, asset_value, validated,
                    request.finished_at, notify=request.status != "failed",
                )
                run_id = str(uuid4())
                connection.execute(
                    "INSERT INTO surface_discovery_runs "
                    "(id, asset_id, asset_value, provider, status, source_url, started_at, "
                    "finished_at, record_count, skipped_names, ignored_names, warnings, "
                    "candidate_count, candidates_created, candidates_existing, evidence_created, "
                    "evidence_existing, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?)",
                    (
                        run_id, asset_id, asset_value, request.provider, request.status,
                        request.source_url,
                        request.started_at, request.finished_at, request.record_count,
                        request.skipped_names, request.ignored_names,
                        json.dumps(request.warnings, ensure_ascii=True, separators=(",", ":")),
                        request.candidate_count, summary.candidates_created,
                        summary.candidates_existing, summary.evidence_created,
                        summary.evidence_existing, request.error,
                    ),
                )
                run = self._run(self._run_row(connection, run_id))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return summary, run

    def list_discovery_runs(
        self, asset_id: str, *, limit: int = 20,
    ) -> tuple[SurfaceDiscoveryRun, ...]:
        try:
            asset_id = _identifier(asset_id)
        except (ValueError, TypeError) as exc:
            raise ValidationError("Pasif keşif geçmişi için geçerli kök kimliği gerekli.") from exc
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Pasif keşif geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            if connection.execute("SELECT value FROM assets WHERE id = ?", (asset_id,)).fetchone() is None:
                raise ValidationError("Kayıtlı kök adres bulunamadı.")
            rows = connection.execute(
                "SELECT sequence, id, asset_id, asset_value, provider, status, source_url, "
                "started_at, finished_at, record_count, skipped_names, ignored_names, warnings, "
                "candidate_count, candidates_created, candidates_existing, evidence_created, "
                "evidence_existing, error FROM surface_discovery_runs WHERE asset_id = ? "
                "ORDER BY sequence DESC LIMIT ?", (asset_id, limit),
            ).fetchall()
            runs = tuple(self._run(row) for row in rows)
            connection.rollback()
        return runs

    def discovery_run(self, run_id: str) -> SurfaceDiscoveryRun:
        try:
            run_id = _identifier(run_id)
        except (ValueError, TypeError) as exc:
            raise ValidationError("Geçerli bir pasif keşif çalışma kimliği gerekli.") from exc
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._run_row(connection, run_id)
            if row is None:
                raise ValidationError("Pasif keşif çalışması bulunamadı.")
            run = self._run(row)
            connection.rollback()
        return run

    def list_candidates(
        self, asset_id: str, *, status: str | None = "pending", limit: int = 100,
    ) -> tuple[SurfaceCandidate, ...]:
        try:
            asset_id = _identifier(asset_id)
            if status is not None:
                status = _status(status)
        except (ValueError, TypeError) as exc:
            raise ValidationError("Alt alan adı aday filtresi geçersiz.") from exc
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Alt alan adı aday sınırı 1–500 arasında olmalı.")
        clause = "AND c.status = ?" if status is not None else ""
        parameters = (asset_id, status, limit) if status is not None else (asset_id, limit)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            if connection.execute("SELECT value FROM assets WHERE id = ?", (asset_id,)).fetchone() is None:
                raise ValidationError("Kayıtlı kök adres bulunamadı.")
            rows = connection.execute(
                "SELECT c.id, c.asset_id, c.asset_value, c.domain, c.status, c.reason, "
                "c.first_seen_at, c.last_seen_at, c.created_at, c.updated_at, a.value, "
                "(SELECT COUNT(*) FROM surface_candidate_sources s WHERE s.candidate_id = c.id) "
                "FROM surface_candidates c JOIN assets a ON a.id = c.asset_id "
                f"WHERE c.asset_id = ? {clause} "
                "ORDER BY c.domain, c.id LIMIT ?", parameters,
            ).fetchall()
            candidates = tuple(self._candidate(row) for row in rows)
            connection.rollback()
        return candidates

    def candidate_details(
        self, candidate_id: str, *, source_limit: int = 100,
    ) -> SurfaceCandidateDetails:
        try:
            candidate_id = _identifier(candidate_id)
        except (ValueError, TypeError) as exc:
            raise ValidationError("Geçerli bir alt alan adı aday kimliği gerekli.") from exc
        if type(source_limit) is not int or not 1 <= source_limit <= 500:
            raise ValidationError("Kaynak kanıtı sınırı 1–500 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            details = self._details(connection, candidate_id, source_limit=source_limit)
            connection.rollback()
        return details

    @classmethod
    def _details(
        cls, connection: sqlite3.Connection, candidate_id: str, *, source_limit: int = 100,
    ) -> SurfaceCandidateDetails:
        row = cls._candidate_row(connection, candidate_id)
        if row is None:
            raise ValidationError("Alt alan adı adayı bulunamadı.")
        candidate = cls._candidate(row)
        source_rows = connection.execute(
            "SELECT id, candidate_id, provider, source_name, source_sha256, raw_domain, "
            "observed_at, recorded_at FROM surface_candidate_sources "
            "WHERE candidate_id = ? ORDER BY rowid DESC LIMIT ?",
            (candidate_id, source_limit),
        ).fetchall()
        event_rows = connection.execute(
            "SELECT id, candidate_id, action, status, reason, created_at "
            "FROM surface_candidate_events WHERE candidate_id = ? ORDER BY rowid LIMIT 1001",
            (candidate_id,),
        ).fetchall()
        if len(event_rows) > 1000:
            raise StorageError("Alt alan adı karar geçmişi güvenli okuma sınırını aştı.")
        sources = tuple(cls._source(item) for item in reversed(source_rows))
        events = tuple(cls._event(item) for item in event_rows)
        return SurfaceCandidateDetails(candidate, sources, events, candidate.source_count)

    def decide_candidate(
        self, candidate_id: str, status: str, reason: str, recorded_at: str,
    ) -> tuple[SurfaceCandidate, bool]:
        try:
            candidate_id = _identifier(candidate_id)
            status = _status(status)
            reason = _reason(reason)
            recorded_at = _timestamp(recorded_at)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValidationError("Alt alan adı aday kararı geçersiz; kayıt yapılmadı.") from exc
        changed = False
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._candidate_row(connection, candidate_id)
                if row is None:
                    raise ValidationError("Alt alan adı adayı bulunamadı.")
                current = self._candidate(row)
                if current.status != status or current.reason != reason:
                    action = (
                        "updated" if current.status == status else
                        "reopened" if status == "pending" else status
                    )
                    connection.execute(
                        "UPDATE surface_candidates SET status = ?, reason = ?, updated_at = ? "
                        "WHERE id = ?", (status, reason, recorded_at, candidate_id),
                    )
                    self._insert_event(
                        connection, candidate_id, action, status, reason, recorded_at,
                    )
                    changed = True
                candidate = self._candidate(self._candidate_row(connection, candidate_id))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return candidate, changed
