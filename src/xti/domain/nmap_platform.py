"""Strict typed parameters for company-scoped Nmap operations."""

from dataclasses import fields
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.engine_jobs import request_key
from xti.domain.nmap_management import normalize_target_name
from xti.domain.nmap_options import NmapExecutionOptions, normalize_options


NMAP_OPERATIONS = (
    "nmap.capabilities", "nmap.targets.list", "nmap.plans.create", "nmap.plans.show",
    "nmap.jobs.submit", "nmap.jobs.list", "nmap.jobs.status", "nmap.jobs.result",
    "nmap.jobs.cancel", "nmap.jobs.resume",
)
PLAN_FIELDS = {"profile", "ports", "timeout_seconds", "max_rate_pps", "max_retries",
    "scan_delay_ms", "max_parallelism", "max_hostgroup", "max_targets", "max_probe_budget",
    "confirm_wide_scan", "confirm_range_scan", "scan_type", "options"}


def parse_nmap_parameters(operation, value):
    if not isinstance(value, dict):
        raise ValidationError("Nmap parametreleri nesne olmalı.")
    allowed, required = {"domain"}, {"domain"}
    if operation == "nmap.capabilities":
        allowed, required = set(), set()
    elif operation == "nmap.plans.create":
        allowed |= {"target_name", "expected_workspace_id"} | PLAN_FIELDS
        required |= {"target_name", "expected_workspace_id"}
    elif operation == "nmap.plans.show":
        allowed |= {"plan_id"}
        required |= {"plan_id"}
    elif operation == "nmap.jobs.submit":
        allowed |= {"plan_id", "key", "expected_workspace_id"}
        required |= {"plan_id", "key", "expected_workspace_id"}
    elif operation in {"nmap.jobs.list", "nmap.targets.list"}:
        allowed |= {"limit", "offset"} if operation == "nmap.jobs.list" else {"limit"}
    else:
        allowed |= {"job_id"}
        required |= {"job_id"}
        if operation == "nmap.jobs.result":
            allowed |= {"limit", "offset"}
        if operation == "nmap.jobs.resume":
            allowed |= {"expected_workspace_id"}
            required |= {"expected_workspace_id"}
    if set(value) - allowed or required - set(value):
        raise ValidationError("Nmap istek alanları eksik veya desteklenmiyor.")
    result = dict(value)
    if "domain" in result:
        result["domain"] = normalize_domain(result["domain"])
    for key in ("plan_id", "job_id", "expected_workspace_id"):
        if key in result:
            result[key] = normalize_knowledge_id(result[key])
    if "key" in result:
        result["key"] = request_key(result["key"])
    if "target_name" in result:
        result["target_name"] = normalize_target_name(result["target_name"])
    for key, low, high in (("limit", 1, 100), ("offset", 0, 10000)):
        if key in result and (type(result[key]) is not int or not low <= result[key] <= high):
            raise ValidationError("Nmap sayfalaması geçersiz.")
    if operation == "nmap.plans.create":
        options = result.get("options", {})
        if not isinstance(options, dict) or set(options) - {f.name for f in fields(NmapExecutionOptions)}:
            raise ValidationError("Nmap çalışma seçenekleri geçersiz.")
        options = dict(options)
        if "scripts" in options:
            if not isinstance(options["scripts"], list):
                raise ValidationError("NSE seçimi liste olmalı.")
            options["scripts"] = tuple(options["scripts"])
        result["options"] = normalize_options(NmapExecutionOptions(**options))
    return result
