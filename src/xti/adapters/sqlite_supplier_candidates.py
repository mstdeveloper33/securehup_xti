"""SQLite supplier candidates derived only from stored CNAME evidence."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.supplier_candidates import (
    SupplierCandidate,
    SupplierCandidateDetails,
    SupplierCandidateEvidence,
    SupplierCandidateMutation,
    SupplierCandidateProposal,
    SupplierCandidateRefresh,
    SupplierCandidateResolution,
    SupplierDependencyObservation,
    normalize_candidate_id,
    normalize_candidate_status,
    normalize_profile_text,
    normalize_resolution_reason,
    normalize_sha256,
    validate_candidate,
    validate_proposal,
)
from xti.domain.suppliers import Supplier, normalize_supplier_id


_MAX_CANDIDATES = 10_000
_MAX_EVIDENCE = 10_000
_MAX_RESOLUTIONS = 10_000
_CANDIDATE_SELECT = (
    "id, asset_id, asset_value, candidate_domain, status, current, supplier_id, "
    "resolution_reason, first_seen_at, last_seen_at, created_at, updated_at"
)
_EVIDENCE_SELECT = (
    "sequence, id, candidate_id, source_evidence_id, source_domain, target_domain, "
    "state_sha256, public_suffix_version, public_suffix_sha256, observed_at, recorded_at"
)
_RESOLUTION_SELECT = (
    "sequence, id, candidate_id, decision, supplier_id, reason, recorded_at"
)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid UUID")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("non-canonical UUID")
    return normalized


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc).isoformat()


def _latest(first: str, second: str) -> str:
    return max(datetime.fromisoformat(first), datetime.fromisoformat(second)).isoformat()


def _earliest(first: str, second: str) -> str:
    return min(datetime.fromisoformat(first), datetime.fromisoformat(second)).isoformat()


def _derivation_key(source_evidence_id: str, public_suffix_sha256: str) -> str:
    return hashlib.sha256(
        f"{source_evidence_id}\0{public_suffix_sha256}".encode("ascii")
    ).hexdigest()


class SQLiteSupplierDependencySource:
    """Read the latest CNAME state for each active, explicitly approved scope."""

    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    def latest(self, *, limit: int) -> tuple[SupplierDependencyObservation, ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValidationError("CNAME kanıt sınırı 1–1000 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT s.asset_id, s.asset_value, s.active, s.reason, s.created_at, "
                "s.updated_at, a.value, c.id, c.asset_id, c.result, c.state_sha256, "
                "c.change, c.recorded_at FROM surface_scopes s JOIN assets a ON "
                "a.id=s.asset_id JOIN surface_cname_checks c ON c.asset_id=s.asset_id "
                "WHERE s.active=1 AND c.rowid=(SELECT MAX(latest.rowid) FROM "
                "surface_cname_checks latest WHERE latest.asset_id=s.asset_id) "
                "ORDER BY s.asset_value, c.id LIMIT ?",
                (limit + 1,),
            ).fetchall()
        if len(rows) > limit:
            raise ValidationError(
                "Etkin kapsamın CNAME kanıtı sınırı aşıyor; hiçbir aday değiştirilmedi."
            )
        observations = []
        for row in rows:
            scope = SQLiteSurfaceCnameRepository._scope(row[:7])
            check = SQLiteSurfaceCnameRepository._check(
                (row[7], row[8], scope.asset_value, row[9], row[10], row[11], row[12]),
                scope.asset_value,
            )
            observations.append(SupplierDependencyObservation(
                source_evidence_id=check.id,
                asset_id=check.asset_id,
                source_domain=scope.asset_value,
                target_domain=check.result.target,
                state_sha256=check.state_sha256,
                observed_at=check.result.finished_at,
            ))
        return tuple(observations)


class SQLiteSupplierCandidateRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _candidate(row) -> SupplierCandidate:
        try:
            candidate = SupplierCandidate(
                id=_uuid(row[0]), asset_id=_uuid(row[1]),
                asset_value=normalize_domain(row[2]),
                candidate_domain=normalize_domain(row[3]),
                status=normalize_candidate_status(row[4]),
                current=bool(row[5]),
                supplier_id=(normalize_supplier_id(row[6]) if row[6] is not None else None),
                resolution_reason=(
                    normalize_resolution_reason(row[7]) if row[7] is not None else None
                ),
                first_seen_at=_timestamp(row[8]), last_seen_at=_timestamp(row[9]),
                created_at=_timestamp(row[10]), updated_at=_timestamp(row[11]),
            )
            validate_candidate(candidate)
            if (
                type(row[5]) is not int or row[5] not in {0, 1}
                or candidate.asset_value != row[2]
                or candidate.candidate_domain != row[3]
                or datetime.fromisoformat(candidate.last_seen_at)
                < datetime.fromisoformat(candidate.first_seen_at)
                or datetime.fromisoformat(candidate.updated_at)
                < datetime.fromisoformat(candidate.created_at)
            ):
                raise ValueError("invalid candidate state")
            return candidate
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Tedarikçi adayı kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _evidence(row) -> SupplierCandidateEvidence:
        try:
            if type(row[0]) is not int or row[0] <= 0:
                raise ValueError("invalid sequence")
            record = SupplierCandidateEvidence(
                sequence=row[0], id=_uuid(row[1]), candidate_id=_uuid(row[2]),
                source_evidence_id=_uuid(row[3]),
                source_domain=normalize_domain(row[4]),
                target_domain=normalize_domain(row[5]),
                state_sha256=normalize_sha256(row[6], label="Kaynak kanıt"),
                public_suffix_version=normalize_profile_text(
                    row[7], label="Public Suffix List sürümü",
                ),
                public_suffix_sha256=normalize_sha256(
                    row[8], label="Public Suffix List",
                ),
                observed_at=_timestamp(row[9]), recorded_at=_timestamp(row[10]),
            )
            if record.source_domain != row[4] or record.target_domain != row[5]:
                raise ValueError("non-canonical evidence")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Tedarikçi adayı kanıtı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _resolution(row) -> SupplierCandidateResolution:
        try:
            if type(row[0]) is not int or row[0] <= 0:
                raise ValueError("invalid sequence")
            decision = normalize_candidate_status(row[3])
            supplier_id = normalize_supplier_id(row[4]) if row[4] is not None else None
            if (decision == "accepted") != (supplier_id is not None):
                raise ValueError("invalid supplier link")
            return SupplierCandidateResolution(
                sequence=row[0], id=_uuid(row[1]), candidate_id=_uuid(row[2]),
                decision=decision, supplier_id=supplier_id,
                reason=normalize_resolution_reason(row[5]),
                recorded_at=_timestamp(row[6]),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Tedarikçi adayı karar geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _supplier(connection, supplier_id: str | None) -> Supplier | None:
        if supplier_id is None:
            return None
        row = SQLiteSupplierRepository._row_by_id(connection, supplier_id)
        if row is None:
            raise StorageError("Adaya bağlı tedarikçi kaydı bulunamadı.")
        return SQLiteSupplierRepository._supplier(row)

    def _validated_details(self, connection, candidate_id: str) -> SupplierCandidateDetails:
        row = connection.execute(
            f"SELECT {_CANDIDATE_SELECT} FROM supplier_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Tedarikçi adayı bulunamadı.")
        candidate = self._candidate(row)
        evidence_rows = connection.execute(
            f"SELECT {_EVIDENCE_SELECT} FROM supplier_candidate_evidence "
            "WHERE candidate_id=? ORDER BY sequence LIMIT ?",
            (candidate.id, _MAX_EVIDENCE + 1),
        ).fetchall()
        resolution_rows = connection.execute(
            f"SELECT {_RESOLUTION_SELECT} FROM supplier_candidate_resolution_events "
            "WHERE candidate_id=? ORDER BY sequence LIMIT ?",
            (candidate.id, _MAX_RESOLUTIONS + 1),
        ).fetchall()
        if len(evidence_rows) > _MAX_EVIDENCE or len(resolution_rows) > _MAX_RESOLUTIONS:
            raise StorageError("Tedarikçi adayı geçmişi güvenli sınırı aşıyor.")
        evidence = tuple(self._evidence(item) for item in evidence_rows)
        resolutions = tuple(self._resolution(item) for item in resolution_rows)
        if not evidence:
            raise StorageError("Tedarikçi adayı kaynak kanıtı eksik.")
        if any(item.candidate_id != candidate.id for item in (*evidence, *resolutions)):
            raise StorageError("Tedarikçi adayı geçmiş bağlantısı bozuk.")
        if any(a.sequence >= b.sequence for a, b in zip(evidence, evidence[1:])):
            raise StorageError("Tedarikçi adayı kanıt sırası bozuk.")
        if any(a.sequence >= b.sequence for a, b in zip(resolutions, resolutions[1:])):
            raise StorageError("Tedarikçi adayı karar sırası bozuk.")
        for item in evidence:
            source = connection.execute(
                "SELECT id, asset_id, ?, result, state_sha256, change, recorded_at "
                "FROM surface_cname_checks WHERE id=?",
                (candidate.asset_value, item.source_evidence_id),
            ).fetchone()
            if source is None:
                raise StorageError("Tedarikçi adayının CNAME kanıtı bulunamadı.")
            check = SQLiteSurfaceCnameRepository._check(source, candidate.asset_value)
            if (
                check.asset_id != candidate.asset_id
                or check.state_sha256 != item.state_sha256
                or check.result.target != item.target_domain
                or _timestamp(check.result.finished_at) != item.observed_at
                or item.source_domain != candidate.asset_value
            ):
                raise StorageError("Tedarikçi adayı CNAME kanıtıyla uyuşmuyor.")
        if resolutions:
            last = resolutions[-1]
            if (
                last.decision != candidate.status
                or last.supplier_id != candidate.supplier_id
                or (
                    candidate.status != "pending"
                    and last.reason != candidate.resolution_reason
                )
            ):
                raise StorageError("Tedarikçi adayı güncel kararla uyuşmuyor.")
        elif candidate.status != "pending" or candidate.supplier_id is not None:
            raise StorageError("Tedarikçi adayı karar geçmişi eksik.")
        supplier = self._supplier(connection, candidate.supplier_id)
        return SupplierCandidateDetails(
            candidate, supplier, evidence, resolutions, len(evidence), len(resolutions),
        )

    def _validate_all(self, connection) -> None:
        ids = connection.execute(
            "SELECT id FROM supplier_candidates ORDER BY id LIMIT ?",
            (_MAX_CANDIDATES + 1,),
        ).fetchall()
        if len(ids) > _MAX_CANDIDATES:
            raise StorageError("Tedarikçi adayı sayısı güvenli sınırı aşıyor.")
        for (candidate_id,) in ids:
            self._validated_details(connection, candidate_id)

    def refresh(
        self, proposals: tuple[SupplierCandidateProposal, ...], *,
        observation_count: int, recorded_at: str,
    ) -> SupplierCandidateRefresh:
        if (
            not isinstance(proposals, tuple) or len(proposals) > 1000
            or type(observation_count) is not int
            or not len(proposals) <= observation_count <= 1000
        ):
            raise ValidationError("Tedarikçi adayı yenileme kapsamı geçersiz.")
        recorded_at = _timestamp(recorded_at)
        normalized = []
        derivations: set[str] = set()
        for item in proposals:
            validate_proposal(item)
            proposal = SupplierCandidateProposal(
                item.source_evidence_id, item.asset_id, item.asset_value,
                item.target_domain, item.candidate_domain, item.state_sha256,
                item.public_suffix_version, item.public_suffix_sha256,
                _timestamp(item.observed_at),
            )
            derivation = _derivation_key(
                proposal.source_evidence_id, proposal.public_suffix_sha256,
            )
            if derivation in derivations:
                raise ValidationError("Tedarikçi adayı kanıtı yineleniyor.")
            derivations.add(derivation)
            normalized.append(proposal)
        normalized.sort(key=lambda item: (
            item.asset_value, item.candidate_domain, item.target_domain,
            item.source_evidence_id,
        ))
        desired = {(item.asset_id, item.candidate_domain) for item in normalized}
        created = existing_count = evidence_created = evidence_existing = 0
        became_current = became_historical = 0
        counted_existing: set[tuple[str, str]] = set()
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_all(connection)
                current_rows = connection.execute(
                    "SELECT id, asset_id, candidate_domain, current, updated_at "
                    "FROM supplier_candidates WHERE current=1"
                ).fetchall()
                for row in current_rows:
                    if (row[1], row[2]) not in desired:
                        connection.execute(
                            "UPDATE supplier_candidates SET current=0, updated_at=? WHERE id=?",
                            (_latest(_timestamp(row[4]), recorded_at), row[0]),
                        )
                        became_historical += 1
                for proposal in normalized:
                    key = (proposal.asset_id, proposal.candidate_domain)
                    row = connection.execute(
                        f"SELECT {_CANDIDATE_SELECT} FROM supplier_candidates "
                        "WHERE asset_id=? AND candidate_domain=?",
                        key,
                    ).fetchone()
                    if row is None:
                        candidate_id = str(uuid4())
                        connection.execute(
                            "INSERT INTO supplier_candidates (id, asset_id, asset_value, "
                            "candidate_domain, status, current, supplier_id, "
                            "resolution_reason, first_seen_at, last_seen_at, created_at, "
                            "updated_at) VALUES (?, ?, ?, ?, 'pending', 1, NULL, NULL, "
                            "?, ?, ?, ?)",
                            (
                                candidate_id, proposal.asset_id, proposal.asset_value,
                                proposal.candidate_domain, proposal.observed_at,
                                proposal.observed_at, recorded_at, recorded_at,
                            ),
                        )
                        created += 1
                        candidate = self._candidate(connection.execute(
                            f"SELECT {_CANDIDATE_SELECT} FROM supplier_candidates WHERE id=?",
                            (candidate_id,),
                        ).fetchone())
                    else:
                        candidate = self._candidate(row)
                        if candidate.asset_value != proposal.asset_value:
                            raise StorageError("Tedarikçi adayı varlık kaydıyla uyuşmuyor.")
                        if key not in counted_existing:
                            existing_count += 1
                            counted_existing.add(key)
                        if not candidate.current:
                            became_current += 1
                    derivation = _derivation_key(
                        proposal.source_evidence_id, proposal.public_suffix_sha256,
                    )
                    evidence_row = connection.execute(
                        f"SELECT {_EVIDENCE_SELECT} FROM supplier_candidate_evidence "
                        "WHERE derivation_key=?", (derivation,),
                    ).fetchone()
                    if evidence_row is None:
                        connection.execute(
                            "INSERT INTO supplier_candidate_evidence (id, candidate_id, "
                            "source_evidence_id, derivation_key, source_domain, target_domain, "
                            "state_sha256, public_suffix_version, public_suffix_sha256, "
                            "observed_at, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                str(uuid4()), candidate.id, proposal.source_evidence_id,
                                derivation, proposal.asset_value, proposal.target_domain,
                                proposal.state_sha256, proposal.public_suffix_version,
                                proposal.public_suffix_sha256, proposal.observed_at, recorded_at,
                            ),
                        )
                        evidence_created += 1
                    else:
                        evidence = self._evidence(evidence_row)
                        if (
                            evidence.candidate_id != candidate.id
                            or evidence.source_evidence_id != proposal.source_evidence_id
                            or evidence.source_domain != proposal.asset_value
                            or evidence.target_domain != proposal.target_domain
                            or evidence.state_sha256 != proposal.state_sha256
                            or evidence.public_suffix_version != proposal.public_suffix_version
                            or evidence.public_suffix_sha256 != proposal.public_suffix_sha256
                            or evidence.observed_at != proposal.observed_at
                        ):
                            raise StorageError("Tedarikçi adayı türetme kanıtı çelişiyor.")
                        evidence_existing += 1
                    new_first = _earliest(candidate.first_seen_at, proposal.observed_at)
                    new_last = _latest(candidate.last_seen_at, proposal.observed_at)
                    if (
                        not candidate.current or new_first != candidate.first_seen_at
                        or new_last != candidate.last_seen_at or evidence_row is None
                    ):
                        connection.execute(
                            "UPDATE supplier_candidates SET current=1, first_seen_at=?, "
                            "last_seen_at=?, updated_at=? WHERE id=?",
                            (
                                new_first, new_last,
                                _latest(candidate.updated_at, recorded_at), candidate.id,
                            ),
                        )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return SupplierCandidateRefresh(
            observation_count, len(normalized), created, existing_count,
            evidence_created, evidence_existing, became_current, became_historical,
        )

    def list(
        self, *, status: str | None, current_only: bool, limit: int,
    ) -> tuple[SupplierCandidate, ...]:
        if status is not None:
            status = normalize_candidate_status(status)
        if type(current_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Tedarikçi adayı liste isteği geçersiz.")
        where = []
        values: list[object] = []
        if status is not None:
            where.append("status=?")
            values.append(status)
        if current_only:
            where.append("current=1")
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                f"SELECT {_CANDIDATE_SELECT} FROM supplier_candidates{clause} "
                "ORDER BY current DESC, status, asset_value, candidate_domain, id LIMIT ?",
                (*values, limit),
            ).fetchall()
            candidates = []
            for row in rows:
                candidate = self._candidate(row)
                self._validated_details(connection, candidate.id)
                candidates.append(candidate)
        return tuple(candidates)

    def show(
        self, candidate_id: str, *, evidence_limit: int, resolution_limit: int,
    ) -> SupplierCandidateDetails:
        candidate_id = normalize_candidate_id(candidate_id)
        if (
            type(evidence_limit) is not int or not 1 <= evidence_limit <= 100
            or type(resolution_limit) is not int or not 1 <= resolution_limit <= 100
        ):
            raise ValidationError("Tedarikçi adayı görünüm sınırı geçersiz.")
        with self._storage._connection(readonly=True) as connection:
            details = self._validated_details(connection, candidate_id)
        return SupplierCandidateDetails(
            details.candidate, details.supplier,
            details.evidence[-evidence_limit:], details.resolutions[-resolution_limit:],
            details.total_evidence_count, details.total_resolution_count,
        )

    def review(
        self, candidate_id: str, *, decision: str, supplier_id: str | None,
        reason: str, recorded_at: str,
    ) -> SupplierCandidateMutation:
        candidate_id = normalize_candidate_id(candidate_id)
        decision = normalize_candidate_status(decision)
        reason = normalize_resolution_reason(reason)
        recorded_at = _timestamp(recorded_at)
        if decision == "accepted":
            if supplier_id is None:
                raise ValidationError("Kabul kararı için tedarikçi kimliği gerekli.")
            supplier_id = normalize_supplier_id(supplier_id)
        elif supplier_id is not None:
            raise ValidationError("Kabul dışındaki karar tedarikçiye bağlanamaz.")
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                details = self._validated_details(connection, candidate_id)
                supplier = self._supplier(connection, supplier_id)
                if supplier is not None and not supplier.active:
                    raise ValidationError("Pasif tedarikçi adaya bağlanamaz.")
                last = details.resolutions[-1] if details.resolutions else None
                same = (
                    details.candidate.status == decision
                    and details.candidate.supplier_id == supplier_id
                    and (
                        (decision == "pending" and last is not None and last.reason == reason)
                        or (
                            decision != "pending"
                            and details.candidate.resolution_reason == reason
                        )
                    )
                )
                if same:
                    result = SupplierCandidateMutation(
                        "unchanged", False, details.candidate, supplier,
                    )
                else:
                    resolution_reason = None if decision == "pending" else reason
                    connection.execute(
                        "UPDATE supplier_candidates SET status=?, supplier_id=?, "
                        "resolution_reason=?, updated_at=? WHERE id=?",
                        (
                            decision, supplier_id, resolution_reason,
                            _latest(details.candidate.updated_at, recorded_at), candidate_id,
                        ),
                    )
                    connection.execute(
                        "INSERT INTO supplier_candidate_resolution_events "
                        "(id, candidate_id, decision, supplier_id, reason, recorded_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid4()), candidate_id, decision, supplier_id, reason, recorded_at),
                    )
                    candidate = self._candidate(connection.execute(
                        f"SELECT {_CANDIDATE_SELECT} FROM supplier_candidates WHERE id=?",
                        (candidate_id,),
                    ).fetchone())
                    result = SupplierCandidateMutation(decision, True, candidate, supplier)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return result
