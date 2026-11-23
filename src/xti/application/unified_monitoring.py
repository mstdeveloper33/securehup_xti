"""Application orchestration for P07 stored-evidence monitoring."""

from __future__ import annotations

from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.unified_monitoring import MonitoringError, PREFIX, READS, parameters
from xti.ports.unified_monitoring import UnifiedMonitoringInputs, UnifiedMonitoringRepository


class UnifiedMonitoringService:
    def __init__(self, repository: UnifiedMonitoringRepository,
                 inputs: UnifiedMonitoringInputs, *, now=None) -> None:
        self.repository = repository
        self.inputs = inputs
        self.now = now or (lambda: datetime.now(timezone.utc).isoformat())

    def execute(self, operation: str, **values) -> dict:
        values = parameters(operation, values)
        at = self.now()
        if operation in READS:
            return self.repository.read(operation, values, at)
        if operation != PREFIX + "run":
            return self.repository.mutate(operation, values, at)
        replay = self.repository.replay_run(values)
        if replay is not None:
            return {**replay, "replayed": True}
        plan = self.repository.plan(values["identifier"], at)
        if plan["revision"] != values["expected_revision"]:
            raise MonitoringError("revision_conflict", "İzleme politikası değişti; planı yeniden okuyun.")
        run, replayed = self.repository.reserve(values, at)
        if replayed:
            return {**run, "replayed": True}
        try:
            snapshot = self.inputs.capture(plan, at)
            return self.repository.finish(run["id"], snapshot, self.now())
        except BaseException as error:
            code = str(getattr(error, "code", "monitoring_failed"))[:80]
            if isinstance(error, MonitoringError):
                message = error.message
            elif isinstance(error, ValidationError):
                message = str(error)
            else:
                message = "Birleşik izleme yerel kanıtları güvenle değerlendiremedi; önceki kanıt korundu."
            self.repository.fail(run["id"], code, message, self.now())
            if isinstance(error, Exception) and not isinstance(error, MonitoringError):
                raise MonitoringError(code, message) from error
            raise
