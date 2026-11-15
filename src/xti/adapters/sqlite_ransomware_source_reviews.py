"""Append-only human decisions for cross-source ransomware comparisons."""

from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.ransomlook_ransomware import RansomLookClaim
from xti.domain.ransomware_claims import RansomwareClaim
from xti.domain.ransomware_source_comparison import (
    RANSOMWARE_SOURCE_COMPARISON_BASES,
    RansomwareSourceComparison,
    RansomwareSourceComparisonEvidence,
    RansomwareSourceReviewDetails,
    RansomwareSourceReviewEvent,
    RansomwareSourceReviewMutation,
    RansomwareSourceReviewState,
    compare_ransomware_source_claims,
    normalize_ransomware_source_comparison_id,
    normalize_ransomware_source_review_decision,
    normalize_ransomware_source_review_reason,
    ransomware_source_comparison_evidence_json,
    ransomware_source_comparison_evidence_sha256,
)


_SELECT = (
    "sequence, id, comparison_id, threatcluster_run_id, ransomlook_run_id, "
    "threatcluster_claim_id, ransomlook_claim_id, evidence_json, evidence_sha256, "
    "decision, reason, recorded_at, previous_event_id"
)
_MAX_EVENTS = 100_000
_EVIDENCE_FIELDS = {
    "comparison", "threatcluster_run_id", "ransomlook_run_id",
}
_COMPARISON_FIELDS = {
    "id", "basis", "common_evidence", "different_evidence",
    "threatcluster_claim", "ransomlook_claim",
}
_THREATCLUSTER_FIELDS = {
    "id", "group", "victim", "country", "sector", "discovered_at", "status",
    "website", "last_seen_at", "delisted_at", "first_party",
    "source_post_available",
}
_RANSOMLOOK_FIELDS = {"id", "group", "victim", "discovered_at"}


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
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    normalized = normalize_cti_timestamp(value, field="kaynak karşılaştırma karar zamanı")
    if normalized != value:
        raise ValueError("Non-canonical timestamp")
    return normalized


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON number")


class SQLiteRansomwareSourceReviewRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _snapshots(runs, items, selection=None):
        """Audit every replay state; optionally retain only requested evidence.

        A selected run with value None needs its complete snapshot. A set of
        claim identities retains only those records for frozen review checks.
        The default preserves the full historical snapshot behavior.
        """
        current = {}
        by_run = {}
        for item in items:
            by_run.setdefault(item.run_id, []).append(item)
        snapshots = {}
        for run in runs:
            if run.status != "complete":
                continue
            for item in by_run.get(run.id, ()):
                if item.action in {"added", "updated"}:
                    current[item.claim.id] = item.claim
                elif item.action == "removed":
                    current.pop(item.claim.id, None)
            if len(current) != run.claim_count:
                raise StorageError("Kaynak karşılaştırma snapshot'ı yeniden kurulamadı.")
            if selection is None or run.id in selection:
                wanted = selection.get(run.id) if selection is not None else None
                snapshots[run.id] = (
                    dict(current) if wanted is None
                    else {identifier: current[identifier] for identifier in wanted if identifier in current}
                )
        return snapshots

    @staticmethod
    def _threatcluster_claim(value: object) -> RansomwareClaim:
        if not isinstance(value, dict) or set(value) != _THREATCLUSTER_FIELDS:
            raise ValueError("Invalid ThreatCluster claim")
        return SQLiteRansomwareClaimRepository._claim(RansomwareClaim(**value))

    @staticmethod
    def _ransomlook_claim(value: object) -> RansomLookClaim:
        if not isinstance(value, dict) or set(value) != _RANSOMLOOK_FIELDS:
            raise ValueError("Invalid RansomLook claim")
        return SQLiteRansomLookClaimRepository._claim(RansomLookClaim(**value))

    @classmethod
    def _evidence_json(cls, value: object) -> RansomwareSourceComparisonEvidence:
        if not isinstance(value, str) or len(value.encode("utf-8")) > 30_000:
            raise ValueError("Invalid evidence JSON")
        payload = json.loads(
            value, object_pairs_hook=_object, parse_constant=_constant,
        )
        if not isinstance(payload, dict) or set(payload) != _EVIDENCE_FIELDS:
            raise ValueError("Invalid evidence fields")
        comparison_value = payload["comparison"]
        if (
            not isinstance(comparison_value, dict)
            or set(comparison_value) != _COMPARISON_FIELDS
        ):
            raise ValueError("Invalid comparison fields")
        common = comparison_value["common_evidence"]
        different = comparison_value["different_evidence"]
        if not isinstance(common, list) or not isinstance(different, list):
            raise ValueError("Invalid comparison evidence")
        comparison = RansomwareSourceComparison(
            id=normalize_ransomware_source_comparison_id(comparison_value["id"]),
            basis=comparison_value["basis"],
            common_evidence=tuple(common),
            different_evidence=tuple(different),
            threatcluster_claim=cls._threatcluster_claim(
                comparison_value["threatcluster_claim"]
            ),
            ransomlook_claim=cls._ransomlook_claim(
                comparison_value["ransomlook_claim"]
            ),
        )
        evidence = RansomwareSourceComparisonEvidence(
            comparison=comparison,
            threatcluster_run_id=_uuid(payload["threatcluster_run_id"]),
            ransomlook_run_id=_uuid(payload["ransomlook_run_id"]),
        )
        recalculated = compare_ransomware_source_claims(
            comparison.threatcluster_claim, comparison.ransomlook_claim,
        )
        if (
            comparison.basis not in RANSOMWARE_SOURCE_COMPARISON_BASES
            or recalculated is None
            or recalculated != comparison
            or ransomware_source_comparison_evidence_json(evidence) != value
        ):
            raise ValueError("Invalid canonical comparison evidence")
        return evidence

    @classmethod
    def _validate_evidence(
        cls, evidence, *, threatcluster_runs, ransomlook_runs,
        threatcluster_snapshots, ransomlook_snapshots,
    ) -> RansomwareSourceComparisonEvidence:
        if not isinstance(evidence, RansomwareSourceComparisonEvidence):
            raise ValueError("Invalid comparison evidence")
        comparison = replace(evidence.comparison, current_review=None)
        evidence = replace(evidence, comparison=comparison)
        threatcluster_run = threatcluster_runs.get(evidence.threatcluster_run_id)
        ransomlook_run = ransomlook_runs.get(evidence.ransomlook_run_id)
        if (
            threatcluster_run is None
            or threatcluster_run.status != "complete"
            or ransomlook_run is None
            or ransomlook_run.status != "complete"
        ):
            raise ValueError("Missing complete source run")
        threatcluster_claim = threatcluster_snapshots.get(
            evidence.threatcluster_run_id, {}
        ).get(comparison.threatcluster_claim.id)
        ransomlook_claim = ransomlook_snapshots.get(
            evidence.ransomlook_run_id, {}
        ).get(comparison.ransomlook_claim.id)
        if (
            threatcluster_claim != comparison.threatcluster_claim
            or ransomlook_claim != comparison.ransomlook_claim
        ):
            raise ValueError("Comparison claim missing from source snapshot")
        recalculated = compare_ransomware_source_claims(
            comparison.threatcluster_claim, comparison.ransomlook_claim,
        )
        if recalculated is None or recalculated != comparison:
            raise ValueError("Invalid comparison")
        return evidence

    @classmethod
    def _audit(cls, connection, *, compact=False):
        threatcluster_runs_tuple, threatcluster_items = (
            SQLiteRansomwareClaimRepository._audit(connection)
        )
        ransomlook_runs_tuple, ransomlook_items = (
            SQLiteRansomLookClaimRepository._audit(connection)
        )
        threatcluster_runs = {run.id: run for run in threatcluster_runs_tuple}
        ransomlook_runs = {run.id: run for run in ransomlook_runs_tuple}
        rows = connection.execute(
            f"SELECT {_SELECT} FROM ransomware_source_review_events "
            "ORDER BY sequence LIMIT ?", (_MAX_EVENTS + 1,),
        ).fetchall()
        if len(rows) > _MAX_EVENTS:
            raise StorageError(
                "Kaynak karşılaştırma karar geçmişi güvenli sınırı aşıyor."
            )
        threatcluster_selection = ransomlook_selection = None
        if compact:
            threatcluster_selection, ransomlook_selection = {}, {}
            try:
                for row in rows:
                    threatcluster_selection.setdefault(_uuid(row[3]), set()).add(_sha256(row[5]))
                    ransomlook_selection.setdefault(_uuid(row[4]), set()).add(_sha256(row[6]))
            except (TypeError, ValueError, OverflowError) as error:
                raise StorageError(
                    "Kaynak karşılaştırma karar geçmişi bozuk; işlem durduruldu."
                ) from error
            for runs, selection in (
                (threatcluster_runs_tuple, threatcluster_selection),
                (ransomlook_runs_tuple, ransomlook_selection),
            ):
                latest = next((run for run in reversed(runs) if run.status == "complete"), None)
                if latest is not None:
                    selection[latest.id] = None
        threatcluster_snapshots = cls._snapshots(
            threatcluster_runs_tuple, threatcluster_items, threatcluster_selection,
        )
        ransomlook_snapshots = cls._snapshots(
            ransomlook_runs_tuple, ransomlook_items, ransomlook_selection,
        )
        records = []
        evidences = {}
        try:
            for row in rows:
                if type(row[0]) is not int or row[0] < 1:
                    raise ValueError("Invalid sequence")
                event_id = _uuid(row[1])
                comparison_id = normalize_ransomware_source_comparison_id(row[2])
                threatcluster_run_id = _uuid(row[3])
                ransomlook_run_id = _uuid(row[4])
                threatcluster_claim_id = _sha256(row[5])
                ransomlook_claim_id = _sha256(row[6])
                evidence = cls._evidence_json(row[7])
                evidence = cls._validate_evidence(
                    evidence,
                    threatcluster_runs=threatcluster_runs,
                    ransomlook_runs=ransomlook_runs,
                    threatcluster_snapshots=threatcluster_snapshots,
                    ransomlook_snapshots=ransomlook_snapshots,
                )
                evidence_sha = _sha256(row[8])
                if (
                    evidence.comparison.id != comparison_id
                    or evidence.threatcluster_run_id != threatcluster_run_id
                    or evidence.ransomlook_run_id != ransomlook_run_id
                    or evidence.comparison.threatcluster_claim.id
                    != threatcluster_claim_id
                    or evidence.comparison.ransomlook_claim.id != ransomlook_claim_id
                    or ransomware_source_comparison_evidence_sha256(evidence)
                    != evidence_sha
                ):
                    raise ValueError("Evidence relation mismatch")
                event = RansomwareSourceReviewEvent(
                    sequence=row[0], id=event_id,
                    comparison_id=comparison_id,
                    decision=normalize_ransomware_source_review_decision(row[9]),
                    reason=normalize_ransomware_source_review_reason(row[10]),
                    recorded_at=_timestamp(row[11]),
                    previous_event_id=_uuid(row[12]) if row[12] is not None else None,
                    evidence_sha256=evidence_sha,
                )
                source_finished = max(
                    datetime.fromisoformat(threatcluster_runs[threatcluster_run_id].finished_at),
                    datetime.fromisoformat(ransomlook_runs[ransomlook_run_id].finished_at),
                )
                if datetime.fromisoformat(event.recorded_at) < source_finished:
                    raise ValueError("Decision predates source evidence")
                existing = evidences.get(comparison_id)
                if (
                    existing is not None
                    and ransomware_source_comparison_evidence_json(existing)
                    != ransomware_source_comparison_evidence_json(evidence)
                ):
                    raise ValueError("Comparison evidence changed")
                evidences[comparison_id] = evidence
                records.append(event)
        except (
            TypeError, ValueError, ValidationError, OverflowError,
            json.JSONDecodeError,
        ) as error:
            raise StorageError(
                "Kaynak karşılaştırma karar geçmişi bozuk; işlem durduruldu."
            ) from error
        if len({event.sequence for event in records}) != len(records):
            raise StorageError(
                "Kaynak karşılaştırma karar sırası bozuk; işlem durduruldu."
            )
        by_comparison = {comparison_id: [] for comparison_id in evidences}
        for event in records:
            by_comparison[event.comparison_id].append(event)
        for history in by_comparison.values():
            for index, event in enumerate(history):
                expected_previous = history[index - 1].id if index else None
                if event.previous_event_id != expected_previous:
                    raise StorageError(
                        "Kaynak karşılaştırma karar zinciri bozuk; işlem durduruldu."
                    )
                if index and datetime.fromisoformat(
                    history[index - 1].recorded_at
                ) > datetime.fromisoformat(event.recorded_at):
                    raise StorageError(
                        "Kaynak karşılaştırma karar zamanı bozuk; işlem durduruldu."
                    )
                if event.evidence_sha256 != history[0].evidence_sha256:
                    raise StorageError(
                        "Kaynak karşılaştırma karar kanıtı değişmiş; işlem durduruldu."
                    )
        return (
            threatcluster_runs_tuple, ransomlook_runs_tuple,
            threatcluster_snapshots, ransomlook_snapshots,
            evidences, tuple(records), by_comparison,
        )

    @staticmethod
    def _state(comparison_id, history):
        latest = history[-1]
        return RansomwareSourceReviewState(
            comparison_id=comparison_id, decision=latest.decision,
            reason=latest.reason, reviewed_at=latest.recorded_at,
            event_count=len(history),
        )

    @classmethod
    def _details(
        cls, comparison_id, threatcluster_runs, ransomlook_runs,
        evidences, by_comparison, *, event_limit,
    ):
        evidence = evidences.get(comparison_id)
        history = by_comparison.get(comparison_id)
        if evidence is None or not history:
            raise ValidationError("Kayıtlı kaynak karşılaştırma kararı bulunamadı.")
        current = cls._state(comparison_id, history)
        evidence = replace(
            evidence,
            comparison=replace(evidence.comparison, current_review=current),
        )
        return RansomwareSourceReviewDetails(
            evidence=evidence,
            threatcluster_run=threatcluster_runs[evidence.threatcluster_run_id],
            ransomlook_run=ransomlook_runs[evidence.ransomlook_run_id],
            current=current,
            events=tuple(history[-event_limit:]),
            total_event_count=len(history),
        )

    def record(self, evidence, *, decision, reason, recorded_at):
        decision = normalize_ransomware_source_review_decision(decision)
        reason = normalize_ransomware_source_review_reason(reason)
        try:
            recorded_at = _timestamp(recorded_at)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("Kaynak karşılaştırma karar zamanı geçersiz.") from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                (
                    threatcluster_runs_tuple, ransomlook_runs_tuple,
                    threatcluster_snapshots, ransomlook_snapshots,
                    evidences, _, by_comparison,
                ) = self._audit(connection)
                threatcluster_runs = {
                    run.id: run for run in threatcluster_runs_tuple
                }
                ransomlook_runs = {run.id: run for run in ransomlook_runs_tuple}
                try:
                    evidence = self._validate_evidence(
                        evidence,
                        threatcluster_runs=threatcluster_runs,
                        ransomlook_runs=ransomlook_runs,
                        threatcluster_snapshots=threatcluster_snapshots,
                        ransomlook_snapshots=ransomlook_snapshots,
                    )
                except (TypeError, ValueError, StorageError) as error:
                    raise ValidationError(
                        "Güncel kaynak karşılaştırma kanıtı geçersiz."
                    ) from error
                latest_threatcluster = next(
                    (run for run in reversed(threatcluster_runs_tuple)
                     if run.status == "complete"), None,
                )
                latest_ransomlook = next(
                    (run for run in reversed(ransomlook_runs_tuple)
                     if run.status == "complete"), None,
                )
                if (
                    latest_threatcluster is None
                    or latest_ransomlook is None
                    or evidence.threatcluster_run_id != latest_threatcluster.id
                    or evidence.ransomlook_run_id != latest_ransomlook.id
                ):
                    raise ValidationError(
                        "Kaynak snapshot'ı karar öncesinde değişti; karşılaştırmayı "
                        "yeniden çalıştırın."
                    )
                comparison_id = evidence.comparison.id
                history = by_comparison.get(comparison_id, [])
                if history:
                    stored = evidences[comparison_id]
                    if (
                        stored.comparison.id != evidence.comparison.id
                        or stored.comparison.basis != evidence.comparison.basis
                        or stored.comparison.common_evidence
                        != evidence.comparison.common_evidence
                        or stored.comparison.different_evidence
                        != evidence.comparison.different_evidence
                    ):
                        raise StorageError(
                            "Kaynak karşılaştırmanın kayıtlı kanıtı güncel adayla "
                            "uyuşmuyor."
                        )
                    evidence = stored
                    latest = history[-1]
                    if datetime.fromisoformat(recorded_at) < datetime.fromisoformat(
                        latest.recorded_at
                    ):
                        raise ValidationError(
                            "Kaynak karşılaştırma karar zamanı önceki karardan eski."
                        )
                    if latest.decision == decision and latest.reason == reason:
                        connection.commit()
                        return RansomwareSourceReviewMutation(
                            "unchanged",
                            self._details(
                                comparison_id, threatcluster_runs, ransomlook_runs,
                                evidences, by_comparison, event_limit=500,
                            ),
                        )
                source_finished = max(
                    datetime.fromisoformat(
                        threatcluster_runs[evidence.threatcluster_run_id].finished_at
                    ),
                    datetime.fromisoformat(
                        ransomlook_runs[evidence.ransomlook_run_id].finished_at
                    ),
                )
                if datetime.fromisoformat(recorded_at) < source_finished:
                    raise ValidationError(
                        "Kaynak karşılaştırma karar zamanı kaynak kanıtından eski."
                    )
                evidence_json = ransomware_source_comparison_evidence_json(evidence)
                evidence_sha = ransomware_source_comparison_evidence_sha256(evidence)
                comparison = evidence.comparison
                connection.execute(
                    "INSERT INTO ransomware_source_review_events "
                    "(id, comparison_id, threatcluster_run_id, ransomlook_run_id, "
                    "threatcluster_claim_id, ransomlook_claim_id, evidence_json, "
                    "evidence_sha256, decision, reason, recorded_at, previous_event_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid4()), comparison.id,
                        evidence.threatcluster_run_id, evidence.ransomlook_run_id,
                        comparison.threatcluster_claim.id,
                        comparison.ransomlook_claim.id,
                        evidence_json, evidence_sha, decision, reason, recorded_at,
                        history[-1].id if history else None,
                    ),
                )
                (
                    threatcluster_runs_tuple, ransomlook_runs_tuple, _, _,
                    evidences, _, by_comparison,
                ) = self._audit(connection)
                threatcluster_runs = {
                    run.id: run for run in threatcluster_runs_tuple
                }
                ransomlook_runs = {run.id: run for run in ransomlook_runs_tuple}
                details = self._details(
                    comparison.id, threatcluster_runs, ransomlook_runs,
                    evidences, by_comparison, event_limit=500,
                )
                connection.commit()
                return RansomwareSourceReviewMutation(
                    "recorded" if details.total_event_count == 1 else "updated",
                    details,
                )
            except BaseException:
                connection.rollback()
                raise

    def details(self, comparison_id, *, event_limit):
        comparison_id = normalize_ransomware_source_comparison_id(comparison_id)
        if type(event_limit) is not int or not 1 <= event_limit <= 500:
            raise ValidationError(
                "Kaynak karşılaştırma karar olayı sınırı 1–500 arasında olmalı."
            )
        with self._storage._connection(readonly=True) as connection:
            (
                threatcluster_runs_tuple, ransomlook_runs_tuple, _, _,
                evidences, _, by_comparison,
            ) = self._audit(connection)
        return self._details(
            comparison_id,
            {run.id: run for run in threatcluster_runs_tuple},
            {run.id: run for run in ransomlook_runs_tuple},
            evidences, by_comparison, event_limit=event_limit,
        )

    def states(self):
        with self._storage._connection(readonly=True) as connection:
            _, _, _, _, _, _, by_comparison = self._audit(connection)
        return tuple(
            self._state(comparison_id, by_comparison[comparison_id])
            for comparison_id in sorted(
                by_comparison,
                key=lambda value: by_comparison[value][-1].sequence,
            )
        )
