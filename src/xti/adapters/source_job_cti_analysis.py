"""Queue bridge for deterministic P04 analysis; it performs no network request."""

from xti.adapters.sqlite import StorageError
from xti.domain.cti_analysis import CtiAnalysisError, digest
from xti.domain.cti_analysis_jobs import (
    SOURCE, guard, snapshot_scope_sha256,
)
from xti.domain.engine_jobs import EngineJobError


class CtiAnalysisStep:
    def __init__(self, service, jobs):
        self.service, self.jobs = service, jobs

    @staticmethod
    def key(identifier: str) -> str:
        return "cti-analysis-job:" + identifier

    @staticmethod
    def reference(run: dict, *, reused: bool = False) -> dict:
        report = run.get("report") or {}
        return {"kind": "cti_analysis_run", "run_id": run["id"],
            "profile_id": run["profile_id"],
            "profile_revision": run["snapshot"]["profile_revision"],
            "report_sha256": digest(report), "source_status": run["status"],
            "reused_receipt": reused,
            "usage": {"version": 1, "unit": "http_open_attempt", "attempts": 0,
                      "responses": 0, "transport_errors": 0, "rate_limited": 0,
                      "budget_rejections": 0}}

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
                    "SELECT id FROM cti_analysis_runs WHERE request_key=?", (request_key,),
                ).fetchone()
            if row is None:
                continue
            run = self.service.execute("cti.analysis.run.show", identifier=row[0])
            if (run["profile_id"] != plan["analysis_profile_id"]
                    or run["snapshot"]["profile_revision"] != plan["analysis_profile_revision"]
                    or snapshot_scope_sha256(run["snapshot"]) != plan["value"]):
                raise StorageError("CTI analiz iş makbuzu başka profile bağlı.")
            if run["status"] == "running":
                raise EngineJobError("execution_uncertain",
                    "CTI analiz turu kesilmiş; analiz recover sonrası açık tekrar gerekli.")
            if run["status"] == "interrupted" and reused:
                continue
            return self.reference(run, reused=reused)
        profile = self.service.execute("cti.analysis.profile.show",
                                       identifier=plan["analysis_profile_id"])
        if not guard(profile, plan):
            raise EngineJobError("plan_changed", "CTI analiz profili, sürümü veya kapsam özeti değişti.")
        try:
            run = self.service.execute("cti.analysis.run", identifier=profile["id"],
                expected_revision=profile["revision"],
                force=plan["analysis_force"] or self.jobs.get(job_id).payload.retry_of is not None,
                idempotency_key=self.key(job_id))
        except CtiAnalysisError as error:
            raise EngineJobError(error.code, error.message) from error
        return self.reference(run)

    def verify(self, receipt: dict, plan: dict) -> None:
        run = self.service.execute("cti.analysis.run.show", identifier=receipt["run_id"])
        if (receipt != self.reference(run, reused=receipt["reused_receipt"])
                or snapshot_scope_sha256(run["snapshot"]) != plan["value"]):
            raise StorageError("CTI analiz iş sonucu özgün profil makbuzuyla uyuşmuyor.")
