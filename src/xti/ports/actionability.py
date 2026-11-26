"""Persistence boundaries for P06 defensive action workflows."""

from typing import Protocol

from xti.domain.actionability import (
    RunbookApplication, RunbookPlan, TakedownDetails, TakedownRequest,
)


class ActionabilityRepository(Protocol):
    def runbook_plan(self, case_id: str) -> RunbookPlan: ...

    def apply_runbook(self, case_id: str, *, expected_plan_sha256: str,
                      idempotency_key: str, reason: str,
                      recorded_at: str) -> RunbookApplication: ...

    def runbook_show(self, runbook_id: str) -> RunbookApplication: ...

    def create_takedown(self, case_id: str, evidence_link_id: str, *, target_kind: str | None,
                        target_value: str | None, recipient: str | None,
                        contact_candidate_id: str | None, requested_action: str,
                        grounds: str, idempotency_key: str, actor: str,
                        recorded_at: str) -> TakedownDetails: ...

    def transition_takedown(self, request_id: str, *, action: str, expected_revision: int,
                            actor: str, reason: str, external_reference: str | None,
                            recorded_at: str) -> TakedownDetails: ...

    def takedown_show(self, request_id: str) -> TakedownDetails: ...

    def takedown_list(self, *, case_id: str | None, state: str | None,
                      offset: int, limit: int) -> tuple[TakedownRequest, ...]: ...
