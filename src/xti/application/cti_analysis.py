"""One CTI analysis service for terminal, engine and company platform."""

from datetime import datetime, timezone

from xti.domain.cti_analysis import PREFIX, READS, analyse, parameters
from xti.ports.cti_analysis import CtiAnalysisInputs, CtiAnalysisRepository


class CtiAnalysisService:
    def __init__(self, repository: CtiAnalysisRepository, inputs: CtiAnalysisInputs, *, now=None):
        self.repository, self.inputs = repository, inputs
        self.now = now or (lambda: datetime.now(timezone.utc).isoformat())

    def execute(self, operation: str, **values) -> dict:
        values = parameters(operation, values)
        if operation == PREFIX + "capabilities":
            return {
                "policy": "cti-analysis-v1", "network_access": False,
                "inputs": ["stored_cti", "stored_ioc", "organization_domains", "local_mitre_attack"],
                "candidate_kinds": ["identity", "technique", "attribution", "tag", "priority"],
                "automatic_merge": False, "automatic_attribution": False,
                "automatic_tag_fact": False, "llm": False,
            }
        if operation in READS:
            return self.repository.read(operation, values)
        if operation != PREFIX + "run":
            return self.repository.mutate(operation, values, self.now())
        replay = self.repository.replay(values)
        if replay is not None:
            return {**replay, "replayed": True}
        plan = self.repository.plan(values["identifier"])
        if plan["profile"]["revision"] != values["expected_revision"]:
            from xti.domain.cti_analysis import CtiAnalysisError
            raise CtiAnalysisError("revision_conflict", "CTI analiz profili değişti; planı yeniden okuyun.")
        accepted = self.repository.accepted_identity_links(plan["profile"]["id"])
        snapshot = self.inputs.capture(plan, accepted, self.now())
        run, replayed = self.repository.reserve(values, snapshot, self.now())
        if replayed:
            return {**run, "replayed": True}
        try:
            result = analyse(snapshot)
            return self.repository.finish(run["id"], result, self.now())
        except BaseException as error:
            self.repository.fail(run["id"], getattr(error, "code", "analysis_failed"), self.now())
            raise
