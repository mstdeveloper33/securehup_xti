"""Terminal and company-platform boundary for P07 unified monitoring."""

from contextlib import nullcontext
import json
from uuid import uuid4

from xti.domain.unified_monitoring import (
    CHANGE_KINDS, GLOBAL_SEARCH_KINDS, MATCH_MODES, PREFIX, PRIORITIES,
    PROFILE_FIELDS, REVIEW_DECISIONS, SUBJECT_KINDS, WRITES,
)
from xti.interfaces.text import safe_text


CLI = {name.replace(".", "-"): PREFIX + name for name in (
    "capabilities", "policies", "policy.add", "policy.update", "policy.disable",
    "policy.show", "plan", "due", "run", "runs", "run.show", "alerts",
    "run.matches", "run.coverage", "run.changes", "alert.show", "alert.review", "reviews", "report", "recover",
)}


def make_unified_monitoring_service(database):
    from xti.adapters.sqlite_unified_monitoring import SQLiteUnifiedMonitoringRepository
    from xti.adapters.unified_monitoring_inputs import SQLiteUnifiedMonitoringInputs
    from xti.application.unified_monitoring import UnifiedMonitoringService
    return UnifiedMonitoringService(
        SQLiteUnifiedMonitoringRepository(database), SQLiteUnifiedMonitoringInputs(database),
    )


def register_unified_monitoring_parser(commands) -> None:
    root = commands.add_parser(
        "monitoring",
        help=(
            "Ağ çağrısı yapmadan kuruluşun saklı kanıtlarını ortak eşik, fark ve "
            "alarm politikasıyla değerlendir."
        ),
    )
    actions = root.add_subparsers(dest="monitoring_action", required=True)
    for command, operation in CLI.items():
        parser = actions.add_parser(command, help="Birleşik izleme işlemi: " + command)
        parser.set_defaults(monitoring_operation=operation)
        if command in ("policy-show", "plan", "run", "run-show", "run-matches", "run-coverage", "run-changes", "alert-show",
                       "alert-review", "reviews", "policy-disable", "policy-update", "recover"):
            parser.add_argument("identifier")
        if command in ("policy-add", "policy-update"):
            parser.add_argument("--name", required=command == "policy-add")
            parser.add_argument("--organization", dest="organization_id",
                                required=command == "policy-add")
            for kind in SUBJECT_KINDS:
                parser.add_argument("--" + kind, action="append", dest=kind + "_subjects")
            parser.add_argument("--record-kind", action="append", dest="record_kinds",
                                choices=GLOBAL_SEARCH_KINDS)
            parser.add_argument("--match-mode", action="append", dest="match_modes",
                                choices=MATCH_MODES)
            parser.add_argument("--notify-on", action="append", choices=CHANGE_KINDS)
            parser.add_argument("--minimum-changes", type=int, dest="minimum_change_count")
            parser.add_argument("--priority", choices=PRIORITIES)
            parser.add_argument("--interval-seconds", type=int)
            parser.add_argument("--max-matches", type=int)
            inactive = parser.add_mutually_exclusive_group()
            inactive.add_argument("--include-inactive", dest="include_inactive",
                                  action="store_const", const=True, default=None)
            inactive.add_argument("--current-only", dest="include_inactive",
                                  action="store_const", const=False)
        if command == "policy-update":
            enabled = parser.add_mutually_exclusive_group()
            enabled.add_argument("--enable", dest="enabled", action="store_const", const=True, default=None)
            enabled.add_argument("--disable", dest="enabled", action="store_const", const=False)
        if command in ("policy-update", "policy-disable", "run", "alert-review"):
            parser.add_argument("--expected-revision", type=int)
        if command == "run":
            parser.add_argument("--force", action="store_true")
        if command == "due":
            parser.add_argument("--at")
            parser.add_argument("--limit", type=int, default=100)
        if command in ("policies", "runs", "alerts", "reviews"):
            parser.add_argument("--after", type=int, default=0)
            parser.add_argument("--limit", type=int, default=20)
            if command in ("runs", "alerts"):
                parser.add_argument("--policy-id")
        if command in ("run-matches", "run-coverage", "run-changes"):
            parser.add_argument("--offset", type=int, default=0)
            parser.add_argument("--limit", type=int, default=100)
        if command == "alerts":
            parser.add_argument("--priority", choices=PRIORITIES)
            parser.add_argument("--decision", choices=REVIEW_DECISIONS)
            parser.add_argument("--read-state", choices=("all", "read", "unread"), default="all")
        if command == "alert-review":
            parser.add_argument("--decision", required=True, choices=REVIEW_DECISIONS)
        if command == "report":
            parser.add_argument("--policy-id", required=True)
            parser.add_argument("--run-id")
        if command in ("policy-add", "policy-update", "policy-disable", "alert-review", "recover"):
            parser.add_argument("--actor", required=True)
        if command in ("policy-add", "policy-update", "policy-disable", "alert-review", "recover"):
            parser.add_argument("--reason", required=True)
        if operation in WRITES:
            parser.add_argument("--idempotency-key")


def _subjects(args):
    result = []
    found = False
    for kind in SUBJECT_KINDS:
        values = getattr(args, kind + "_subjects", None)
        if values:
            found = True
            result.extend({"kind": kind, "value": value} for value in values)
    return result if found else None


def monitoring_lines(data: dict) -> list[str]:
    if "definition" in data and "schedule" in data:
        definition = data["definition"]
        return [
            f"{data['id']} | {safe_text(definition['name'])} | sürüm {data['revision']} | "
            + ("etkin" if data["enabled"] else "kapalı"),
            "  Hedefler: " + ", ".join(item["kind"] + "=" + safe_text(item["value"])
                                       for item in definition["subjects"]),
            f"  Eşik: {definition['minimum_change_count']} | öncelik: {definition['priority']} | "
            f"aralık: {definition['interval_seconds']} sn",
            f"  Sıradaki zaman: {data['schedule']['due_at']} | hazır: {data['schedule']['due']}",
        ]
    if "snapshot" in data and "status" in data:
        report = data.get("report") or {}
        return [f"Çalışma: {data['id']} | {data['status']}",
                "  Değişiklikler: " + safe_text(json.dumps(report.get("counts", {}), ensure_ascii=False)),
                f"  Alarm: {report.get('alert_required', False)} | sessiz başlangıç: {report.get('silent_baseline', False)}",
                "  Not: Yalnız kayıtlı yerel kanıt değerlendirildi; uzak kaynak yenilenmedi."]
    if "run" in data and "change_count" in data:
        decision = data["review"]["decision"] if data.get("review") else "inceleme bekliyor"
        return [f"Alarm: {data['id']} | {data['priority']} | {data['change_count']} değişiklik",
                f"  Karar: {decision} | çalışma: {data['run_id']}",
                "  Otomatik tehdit hükmü: hayır"]
    if "run_id" in data and "items" in data:
        return [f"Çalışma kanıtı: {data['run_id']} | {len(data['items'])}/{data['total_count']}",
                f"  Başlangıç: {data['offset']} | devam: {data['has_more']}"]
    if "items" in data:
        lines = []
        for item in data["items"]:
            lines.extend(monitoring_lines(item))
        if not lines: lines.append("Bu kapsamda birleşik izleme kaydı yok.")
        if data.get("next_after") is not None: lines.append("Sonraki sayfa: --after " + str(data["next_after"]))
        return lines
    if "decision" in data:
        return [f"Alarm incelemesi: {data['decision']} | sürüm {data['revision']}", safe_text(data["reason"])]
    return [safe_text(json.dumps(data, ensure_ascii=False))]


def execute_unified_monitoring(database, args):
    from xti.adapters.worker_lock import LocalExecutionLock
    service = make_unified_monitoring_service(database)
    operation = args.monitoring_operation
    keys = PROFILE_FIELDS | {"identifier", "expected_revision", "enabled", "force", "after",
        "limit", "policy_id", "run_id", "priority", "decision", "read_state", "reason",
        "actor", "idempotency_key", "at", "offset"}
    values = {key: getattr(args, key) for key in keys if getattr(args, key, None) is not None}
    subjects = _subjects(args)
    if subjects is not None: values["subjects"] = subjects
    if operation in WRITES:
        values.setdefault("idempotency_key", "cli:" + str(uuid4()))
    lock = LocalExecutionLock(database).acquire() if operation in WRITES else nullcontext()
    with lock:
        if operation in (PREFIX + "policy.update", PREFIX + "policy.disable", PREFIX + "run") \
                and "expected_revision" not in values:
            values["expected_revision"] = service.execute(
                PREFIX + "policy.show", identifier=values["identifier"],
            )["revision"]
        if operation == PREFIX + "alert.review" and "expected_revision" not in values:
            values["expected_revision"] = service.execute(
                PREFIX + "alert.show", identifier=values["identifier"],
            )["review_revision"]
        result = service.execute(operation, **values)
    return result, monitoring_lines(result)


def execute_platform_unified_monitoring(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    values = dict(request.parameters)
    if values.pop("expected_workspace_id") != context.workspace_id:
        raise EngineContractError("scope_mismatch", "İzleme isteği güncel firma veri alanına ait değil.")
    with LocalExecutionLock(context.database).acquire():
        return make_unified_monitoring_service(context.database).execute(request.operation, **values)
