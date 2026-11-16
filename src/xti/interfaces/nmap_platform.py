"""Same application service; scope is supplied only by the trusted platform launcher."""

from dataclasses import asdict
from xti.domain.engine import EngineContractError
from xti.domain.nmap_options import nmap_capabilities
from xti.interfaces.nmap_execution import make_nmap_service, result_page


def execute_platform_nmap(context, request):
    parameters = dict(request.parameters)
    if ("expected_workspace_id" in parameters
            and parameters.pop("expected_workspace_id") != context.workspace_id):
        raise EngineContractError("scope_mismatch", "Nmap isteği güncel firma alanına ait değil.")
    operation = request.operation
    if operation == "nmap.capabilities":
        return nmap_capabilities()
    service = make_nmap_service(context.database)
    domain = parameters.pop("domain")
    if operation == "nmap.targets.list":
        return {"targets": [asdict(t) for t in service.management.list_targets(domain, **parameters)]}
    if operation == "nmap.plans.create":
        return asdict(service.management.create_plan(domain, **parameters))
    if operation == "nmap.plans.show":
        return asdict(service.management.show_plan(domain, **parameters))
    if operation == "nmap.jobs.list":
        return {"jobs": [work.summary() for work in service.list(domain, **parameters)]}
    if operation == "nmap.jobs.result":
        offset, limit = parameters.pop("offset", 0), parameters.pop("limit", 20)
        return result_page(service.show(domain, **parameters), offset, limit)
    method = {"nmap.jobs.submit": service.submit, "nmap.jobs.status": service.show,
              "nmap.jobs.cancel": service.cancel, "nmap.jobs.resume": service.resume}[operation]
    return {"job": method(domain, **parameters).summary()}
