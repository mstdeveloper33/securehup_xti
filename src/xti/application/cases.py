"""Validated local case lifecycle and evidence orchestration."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.cases import (
    Case,
    CaseActivity,
    CaseDetails,
    CaseEvidenceMutation,
    CaseEvidenceSnapshot,
    CaseMutation,
    CaseTaskMutation,
    canonical_snapshot,
    normalize_case_evidence_id,
    normalize_case_evidence_link_id,
    normalize_case_evidence_type,
    normalize_case_id,
    normalize_case_note,
    normalize_case_note_kind,
    normalize_case_priority,
    normalize_case_reason,
    normalize_case_resolution,
    normalize_case_status,
    normalize_case_summary,
    normalize_case_task_id,
    normalize_case_task_status,
    normalize_case_task_title,
    normalize_case_title,
)
from xti.ports.cases import CaseEvidenceSourceRepository, CaseRepository


class CaseEvidenceResolverService:
    """Resolve source records and compose the supplier card without merging records."""

    def __init__(self, repository: CaseEvidenceSourceRepository, supplier_risk=None) -> None:
        self.repository = repository
        self.supplier_risk = supplier_risk

    def resolve(self, evidence_type: str, evidence_id: str) -> CaseEvidenceSnapshot:
        evidence_type = normalize_case_evidence_type(evidence_type)
        evidence_id = normalize_case_evidence_id(evidence_id)
        if evidence_type != "supplier":
            return self.repository.resolve(evidence_type, evidence_id)
        if self.supplier_risk is None:
            raise ValidationError("Tedarikçi inceleme kartı çözücüsü yapılandırılmadı.")
        details = self.supplier_risk.show(evidence_id)
        payload = {
            "kind": "supplier_review_card",
            "details": asdict(details),
            "limitations": [
                "Kaynak iddiası doğrulanmış ihlal değildir.",
                "Kart sayısal risk skoru veya kullanıcı etkisi üretmez.",
            ],
        }
        snapshot_json, digest = canonical_snapshot(payload)
        return CaseEvidenceSnapshot(
            evidence_type="supplier",
            evidence_id=details.card.supplier.id,
            display_value=(
                f"{details.card.supplier.display_name} — "
                f"{details.card.attention}"
            ),
            source_reference="suppliers risk-show",
            snapshot_json=snapshot_json,
            snapshot_sha256=digest,
        )


class CaseService:
    def __init__(
        self, repository: CaseRepository, resolver: CaseEvidenceResolverService, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.resolver = resolver
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Vaka işlem zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int, label: str, maximum: int = 500) -> int:
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValidationError(f"{label} 1–{maximum} arasında olmalı.")
        return value

    @staticmethod
    def _optional_time(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not 1 <= len(value) <= 64:
            raise ValidationError("Görev bitiş zamanı geçerli bir ISO-8601 zamanı olmalı.")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValidationError("Görev bitiş zamanı geçerli bir ISO-8601 zamanı olmalı.") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValidationError("Görev bitiş zamanı saat dilimi içermeli.")
        return parsed.astimezone(timezone.utc).isoformat()

    def create(
        self, title: str, *, summary: str, priority: str = "medium", reason: str,
    ) -> CaseMutation:
        return self.repository.create(
            title=normalize_case_title(title),
            summary=normalize_case_summary(summary),
            priority=normalize_case_priority(priority),
            reason=normalize_case_reason(reason),
            recorded_at=self._now(),
        )

    def update(
        self, case_id: str, *, title: str | None = None,
        summary: str | None = None, priority: str | None = None, reason: str,
    ) -> CaseMutation:
        if title is None and summary is None and priority is None:
            raise ValidationError("Güncelleme için başlık, özet veya öncelik gerekli.")
        return self.repository.update(
            normalize_case_id(case_id),
            title=normalize_case_title(title) if title is not None else None,
            summary=normalize_case_summary(summary) if summary is not None else None,
            priority=normalize_case_priority(priority) if priority is not None else None,
            reason=normalize_case_reason(reason), recorded_at=self._now(),
        )

    def set_status(
        self, case_id: str, status: str, *, reason: str,
        resolution: str | None = None,
    ) -> CaseMutation:
        status = normalize_case_status(status)
        if status in {"resolved", "closed"}:
            if resolution is None:
                raise ValidationError("Çözülen veya kapanan vaka için --resolution gerekli.")
            resolution = normalize_case_resolution(resolution)
        elif resolution is not None:
            raise ValidationError("--resolution yalnız resolved veya closed durumunda kullanılır.")
        return self.repository.set_status(
            normalize_case_id(case_id), status=status, resolution=resolution,
            reason=normalize_case_reason(reason), recorded_at=self._now(),
        )

    def add_note(self, case_id: str, body: str, *, kind: str) -> CaseActivity:
        return self.repository.add_note(
            normalize_case_id(case_id), kind=normalize_case_note_kind(kind),
            body=normalize_case_note(body), recorded_at=self._now(),
        )

    def add_evidence(
        self, case_id: str, evidence_type: str, evidence_id: str, *, reason: str,
    ) -> CaseEvidenceMutation:
        case_id = normalize_case_id(case_id)
        snapshot = self.resolver.resolve(evidence_type, evidence_id)
        return self.repository.add_evidence(
            case_id, snapshot=snapshot, reason=normalize_case_reason(reason),
            recorded_at=self._now(),
        )

    def remove_evidence(
        self, case_id: str, evidence_link_id: str, *, reason: str,
    ) -> CaseEvidenceMutation:
        return self.repository.remove_evidence(
            normalize_case_id(case_id), normalize_case_evidence_link_id(evidence_link_id),
            reason=normalize_case_reason(reason), recorded_at=self._now(),
        )

    def add_task(
        self, case_id: str, title: str, *, due_at: str | None, reason: str,
    ) -> CaseTaskMutation:
        return self.repository.add_task(
            normalize_case_id(case_id), title=normalize_case_task_title(title),
            due_at=self._optional_time(due_at), reason=normalize_case_reason(reason),
            recorded_at=self._now(),
        )

    def update_task(
        self, case_id: str, task_id: str, *, status: str, reason: str,
    ) -> CaseTaskMutation:
        return self.repository.update_task(
            normalize_case_id(case_id), normalize_case_task_id(task_id),
            status=normalize_case_task_status(status),
            reason=normalize_case_reason(reason), recorded_at=self._now(),
        )

    def list(
        self, *, status: str | None = None, priority: str | None = None,
        limit: int = 100,
    ) -> tuple[Case, ...]:
        return self.repository.list(
            status=normalize_case_status(status) if status is not None else None,
            priority=normalize_case_priority(priority) if priority is not None else None,
            limit=self._limit(limit, "Vaka liste sınırı"),
        )

    def show(
        self, case_id: str, *, evidence_limit: int = 100,
        task_limit: int = 100, activity_limit: int = 200,
    ) -> CaseDetails:
        return self.repository.show(
            normalize_case_id(case_id),
            evidence_limit=self._limit(evidence_limit, "Kanıt sınırı"),
            task_limit=self._limit(task_limit, "Görev sınırı"),
            activity_limit=self._limit(activity_limit, "Zaman çizelgesi sınırı", 1000),
        )

