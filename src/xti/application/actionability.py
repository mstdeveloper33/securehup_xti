"""Application orchestration for bounded, human-approved defensive actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone

from xti.domain.actionability import (
    RunbookApplication, RunbookPlan, TakedownDetails, TakedownRequest,
    normalize_key, normalize_runbook_id, normalize_takedown_id,
)
from xti.domain.assets import ValidationError
from xti.domain.cases import normalize_case_id
from xti.ports.actionability import ActionabilityRepository


class ActionabilityService:
    def __init__(
        self, repository: ActionabilityRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Aksiyon işlem zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def runbook_plan(self, case_id: str) -> RunbookPlan:
        return self.repository.runbook_plan(normalize_case_id(case_id))

    def runbook_apply(
        self, case_id: str, *, expected_plan_sha256: str,
        idempotency_key: str, reason: str,
    ) -> RunbookApplication:
        return self.repository.apply_runbook(
            normalize_case_id(case_id), expected_plan_sha256=expected_plan_sha256,
            idempotency_key=normalize_key(idempotency_key),
            reason=reason, recorded_at=self._now(),
        )

    def runbook_show(self, runbook_id: str) -> RunbookApplication:
        return self.repository.runbook_show(normalize_runbook_id(runbook_id))

    def takedown_create(self, case_id: str, evidence_link_id: str, **options) -> TakedownDetails:
        return self.repository.create_takedown(
            normalize_case_id(case_id), evidence_link_id,
            recorded_at=self._now(), **options,
        )

    def takedown_transition(
        self, request_id: str, *, action: str, expected_revision: int,
        actor: str, reason: str, external_reference: str | None = None,
    ) -> TakedownDetails:
        return self.repository.transition_takedown(
            normalize_takedown_id(request_id), action=action,
            expected_revision=expected_revision, actor=actor, reason=reason,
            external_reference=external_reference, recorded_at=self._now(),
        )

    def takedown_show(self, request_id: str) -> TakedownDetails:
        return self.repository.takedown_show(normalize_takedown_id(request_id))

    def takedown_list(
        self, *, case_id: str | None = None, state: str | None = None,
        offset: int = 0, limit: int = 50,
    ) -> tuple[TakedownRequest, ...]:
        return self.repository.takedown_list(
            case_id=case_id, state=state, offset=offset, limit=limit,
        )

    def execute(self, operation: str, **options) -> dict:
        if operation == "action.capabilities":
            return {
                "contract_version": 1,
                "runbook": {"template": "xti-defensive-response", "version": 1, "idempotent_apply": True},
                "takedown": {"human_approval_required": True, "automatic_submission": False},
                "case_package": {"terminal_artifact": True, "platform_file_path_input": False},
                "bulk_ioc": {"terminal_file_artifact": True, "platform_file_path_input": False},
                "external_connectors": False,
            }
        if operation == "action.runbook.plan":
            return asdict(self.runbook_plan(**options))
        if operation == "action.runbook.show":
            return asdict(self.runbook_show(**options))
        if operation == "action.runbook.apply":
            case_id = options.pop("case_id")
            return asdict(self.runbook_apply(case_id, **options))
        if operation == "action.takedown.list":
            records = self.takedown_list(**options)
            return {"records": [asdict(item) for item in records], "offset": options.get("offset", 0), "limit": options.get("limit", 50)}
        if operation == "action.takedown.show":
            return asdict(self.takedown_show(**options))
        if operation == "action.takedown.create":
            case_id = options.pop("case_id"); evidence_link_id = options.pop("evidence_link_id")
            return asdict(self.takedown_create(case_id, evidence_link_id, **options))
        if operation == "action.takedown.transition":
            request_id = options.pop("request_id")
            return asdict(self.takedown_transition(request_id, **options))
        raise ValidationError("Aksiyon işlemi desteklenmiyor.")
