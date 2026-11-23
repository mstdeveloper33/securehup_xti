"""P08 retention orchestration with explicit reservation and recovery."""

from __future__ import annotations

from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.data_retention import PREFIX, READS, RetentionError, parameters
from xti.ports.data_retention import DataRetentionRepository


class DataRetentionService:
    def __init__(self, repository: DataRetentionRepository, *, now=None) -> None:
        self.repository = repository
        self.now = now or (lambda: datetime.now(timezone.utc).isoformat())

    def execute(self, operation: str, **values) -> dict:
        values = parameters(operation, values)
        at = self.now()
        if operation in READS:
            if operation == PREFIX + "plan":
                return self.repository.plan(values["identifier"], at)
            return self.repository.read(operation, values, at)
        if operation not in (PREFIX + "apply", PREFIX + "restore"):
            return self.repository.mutate(operation, values, at)
        replay = self.repository.replay_run(values)
        if replay is not None:
            return {**replay, "replayed": True}
        try:
            if operation == PREFIX + "apply":
                plan = self.repository.plan(values["identifier"], at)
                if plan["policy_revision"] != values["expected_revision"]:
                    raise RetentionError(
                        "revision_conflict", "Saklama politikası değişti; yeniden önizleyin."
                    )
                if plan["token"] != values["token"]:
                    raise RetentionError(
                        "snapshot_changed", "Saklama önizlemesi değişti veya başka çalışma alanına ait."
                    )
                run, replayed = self.repository.reserve_archive(values, plan, at)
                if replayed:
                    return {**run, "replayed": True}
                return self.repository.apply_archive(run["id"], values["token"], self.now())
            run, replayed = self.repository.reserve_restore(values, at)
            if replayed:
                return {**run, "replayed": True}
            return self.repository.apply_restore(run["id"], self.now())
        except BaseException as error:
            run_id = locals().get("run", {}).get("id")
            if run_id is not None:
                code = str(getattr(error, "code", "retention_failed"))[:80]
                if isinstance(error, (RetentionError, ValidationError)):
                    message = str(error)
                else:
                    message = "Saklama işlemi güvenle tamamlanamadı; önceki kanıt korundu."
                self.repository.fail(run_id, code, message, self.now())
            if isinstance(error, Exception) and not isinstance(error, RetentionError):
                if isinstance(error, ValidationError):
                    raise
                raise RetentionError("retention_failed", "Saklama işlemi güvenle tamamlanamadı.") from error
            raise
