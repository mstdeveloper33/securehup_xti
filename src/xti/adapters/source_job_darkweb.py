"""Queue bridge for deterministic P05 analysis; it performs no network request."""

from xti.adapters.sqlite import StorageError
from xti.domain.content_monitoring import digest
from xti.domain.darkweb_jobs import SOURCE, guard, snapshot_scope_sha256
from xti.domain.darkweb_monitoring import DarkwebError
from xti.domain.engine_jobs import EngineJobError


class DarkwebMonitoringStep:
    def __init__(self, service, jobs):
        self.service, self.jobs = service, jobs

    @staticmethod
    def key(identifier: str) -> str:
        return "darkweb-monitor-job:" + identifier

    @staticmethod
    def reference(run: dict, *, reused: bool = False) -> dict:
        return {
            "kind": "darkweb_monitor_run",
            "run_id": run["id"],
            "profile_id": run["profile_id"],
            "profile_revision": run["snapshot"]["profile_revision"],
            "report_sha256": digest(run.get("report") or {}),
            "source_status": run["status"],
            "reused_receipt": reused,
            "usage": {
                "version": 1,
                "unit": "http_open_attempt",
                "attempts": 0,
                "responses": 0,
                "transport_errors": 0,
                "rate_limited": 0,
                "budget_rejections": 0,
            },
        }

    def execute(self, plan: dict, job_id: str) -> dict:
        keys = [(self.key(job_id), False)]
        ancestor = self.jobs.get(job_id)
        while ancestor.payload.retry_of is not None:
            ancestor = self.jobs.get(ancestor.payload.retry_of)
            step = next(step for step in ancestor.steps if step["key"] == SOURCE)
            if step["receipt"] is not None:
                break
            keys.append((self.key(ancestor.id), True))
        for request_key, reused in keys:
            with self.service.repository.storage._connection(readonly=True) as connection:
                row = connection.execute(
                    "SELECT id FROM darkweb_runs WHERE request_key=?", (request_key,),
                ).fetchone()
            if row is None:
                continue
            run = self.service.execute("darkweb.run.show", identifier=row[0])
            if (
                run["profile_id"] != plan["darkweb_profile_id"]
                or run["snapshot"]["profile_revision"] != plan["darkweb_profile_revision"]
                or snapshot_scope_sha256(run["snapshot"]) != plan["value"]
            ):
                raise StorageError("Dark web iş makbuzu başka profile bağlı.")
            if run["status"] == "running":
                raise EngineJobError(
                    "execution_uncertain",
                    "Dark web turu kesilmiş; recover sonrası açık tekrar gerekli.",
                )
            if run["status"] == "interrupted" and reused:
                continue
            return self.reference(run, reused=reused)
        profile = self.service.execute(
            "darkweb.profile.show", identifier=plan["darkweb_profile_id"],
        )
        if not guard(profile, plan):
            raise EngineJobError(
                "plan_changed", "Dark web profili, sürümü veya kapsam özeti değişti."
            )
        try:
            run = self.service.execute(
                "darkweb.run",
                identifier=profile["id"],
                expected_revision=profile["revision"],
                force=plan["darkweb_force"] or self.jobs.get(job_id).payload.retry_of is not None,
                idempotency_key=self.key(job_id),
            )
        except DarkwebError as error:
            raise EngineJobError(error.code, error.message) from error
        return self.reference(run)

    def verify(self, receipt: dict, plan: dict) -> None:
        run = self.service.execute("darkweb.run.show", identifier=receipt["run_id"])
        if (
            receipt != self.reference(run, reused=receipt["reused_receipt"])
            or snapshot_scope_sha256(run["snapshot"]) != plan["value"]
        ):
            raise StorageError("Dark web iş sonucu özgün profil makbuzuyla uyuşmuyor.")
