"""Persistence and source-resolution boundaries for local cases."""

from typing import Protocol

from xti.domain.cases import (
    Case,
    CaseActivity,
    CaseDetails,
    CaseEvidence,
    CaseEvidenceMutation,
    CaseEvidenceSnapshot,
    CaseMutation,
    CaseTaskMutation,
)


class CaseEvidenceSourceRepository(Protocol):
    def resolve(self, evidence_type: str, evidence_id: str) -> CaseEvidenceSnapshot:
        ...


class CaseRepository(Protocol):
    def evidence_show(self, case_id: str, evidence_link_id: str) -> CaseEvidence:
        ...

    def create(
        self, *, title: str, summary: str, priority: str, reason: str, recorded_at: str,
    ) -> CaseMutation:
        ...

    def update(
        self, case_id: str, *, title: str | None, summary: str | None,
        priority: str | None, reason: str, recorded_at: str,
    ) -> CaseMutation:
        ...

    def set_status(
        self, case_id: str, *, status: str, resolution: str | None,
        reason: str, recorded_at: str,
    ) -> CaseMutation:
        ...

    def add_note(
        self, case_id: str, *, kind: str, body: str, recorded_at: str,
    ) -> CaseActivity:
        ...

    def add_evidence(
        self, case_id: str, *, snapshot: CaseEvidenceSnapshot,
        reason: str, recorded_at: str,
    ) -> CaseEvidenceMutation:
        ...

    def remove_evidence(
        self, case_id: str, evidence_link_id: str, *, reason: str, recorded_at: str,
    ) -> CaseEvidenceMutation:
        ...

    def add_task(
        self, case_id: str, *, title: str, due_at: str | None,
        reason: str, recorded_at: str,
    ) -> CaseTaskMutation:
        ...

    def update_task(
        self, case_id: str, task_id: str, *, status: str,
        reason: str, recorded_at: str,
    ) -> CaseTaskMutation:
        ...

    def list(
        self, *, status: str | None, priority: str | None, limit: int,
    ) -> tuple[Case, ...]:
        ...

    def show(
        self, case_id: str, *, evidence_limit: int, task_limit: int,
        activity_limit: int,
    ) -> CaseDetails:
        ...

