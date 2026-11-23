"""Terminal and company-platform composition for P08 data retention."""

from contextlib import nullcontext
import json
from uuid import uuid4

from xti.domain.data_retention import FAMILY, FAMILIES, HOLD_KINDS, PREFIX, WRITES
from xti.interfaces.text import safe_text


CLI = {name.replace(".", "-"): PREFIX + name for name in (
    "capabilities", "catalog", "policies", "policy.add", "policy.update",
    "policy.disable", "policy.show", "plan", "apply", "restore", "runs",
    "run.show", "hold.add", "hold.release", "holds", "hold.show", "audit",
    "recover",
)}


def make_retention_service(database):
    from xti.adapters.sqlite_data_retention import SQLiteDataRetentionRepository
    from xti.application.data_retention import DataRetentionService
    return DataRetentionService(SQLiteDataRetentionRepository(database))


def register_retention_parser(commands) -> None:
    root = commands.add_parser(
        "retention", help="Kuruluş verisinin saklama, koruma, arşiv ve denetim yaşam döngüsünü yönet.",
    )
    actions = root.add_subparsers(dest="retention_action", required=True)
    for command, operation in CLI.items():
        parser = actions.add_parser(command, help="Saklama işlemi: " + command)
        parser.set_defaults(retention_operation=operation)
        if command in (
            "policy-show", "policy-update", "policy-disable", "plan", "apply",
            "restore", "run-show", "hold-release", "hold-show", "recover",
        ):
            parser.add_argument("identifier")
        if command in ("policy-add", "policy-update"):
            parser.add_argument("--name", required=command == "policy-add")
            parser.add_argument("--organization", dest="organization_id",
                                required=command == "policy-add")
            parser.add_argument("--family", action="append", dest="families", choices=FAMILIES)
            parser.add_argument("--archive-after-days", type=int)
            parser.add_argument("--batch-limit", type=int)
            parser.add_argument("--purpose")
            parser.add_argument("--retention-basis")
        if command == "policy-update":
            state = parser.add_mutually_exclusive_group()
            state.add_argument("--enable", dest="enabled", action="store_const", const=True)
            state.add_argument("--disable", dest="enabled", action="store_const", const=False)
        if command == "hold-add":
            parser.add_argument("--organization", dest="organization_id", required=True)
            parser.add_argument("--family", choices=FAMILIES, default=FAMILY)
            parser.add_argument("--record-id")
            parser.add_argument("--case-id")
            parser.add_argument("--kind", choices=HOLD_KINDS, required=True)
        if command in ("policy-update", "policy-disable", "apply", "hold-release"):
            parser.add_argument("--expected-revision", type=int)
        if command == "apply":
            parser.add_argument("--token", required=True)
        if command in ("policies", "runs", "holds", "audit"):
            parser.add_argument("--after", type=int, default=0)
            parser.add_argument("--limit", type=int, default=20)
        if command in ("policies", "holds", "audit"):
            parser.add_argument("--organization", dest="organization_id")
        if command == "policies":
            state = parser.add_mutually_exclusive_group()
            state.add_argument("--enabled", dest="enabled", action="store_const", const=True)
            state.add_argument("--disabled", dest="enabled", action="store_const", const=False)
        if command == "runs":
            parser.add_argument("--policy-id")
            parser.add_argument("--status", choices=("running", "complete", "failed", "interrupted"))
        if command == "holds":
            parser.add_argument("--family", choices=FAMILIES)
            state = parser.add_mutually_exclusive_group()
            state.add_argument("--active", dest="active", action="store_const", const=True)
            state.add_argument("--released", dest="active", action="store_const", const=False)
        if command == "audit":
            parser.add_argument("--resource-kind")
        if operation in WRITES:
            parser.add_argument("--actor", required=True)
            parser.add_argument("--reason", required=True)
            parser.add_argument("--idempotency-key")


def retention_lines(data: dict) -> list[str]:
    if "managed_families" in data:
        families = data["managed_families"]
        labels = [item["id"] if isinstance(item, dict) else item for item in families]
        return ["Yönetilen veri aileleri: " + ", ".join(labels),
                "Otomatik mantıksal silme: hayır; vaka ve açık korumalar korunur."]
    if "definition" in data and "revision" in data:
        definition = data["definition"]
        return [f"{data['id']} | {safe_text(definition['name'])} | sürüm {data['revision']} | "
                + ("etkin" if data["enabled"] else "kapalı"),
                f"  Arşiv eşiği: {definition['archive_after_days']} gün | pencere: {definition['batch_limit']}",
                "  Aileler: " + ", ".join(definition["families"])]
    if "selected_count" in data and "cutoff" in data:
        return [f"Seçilen: {data['selected_count']} | uygun: {data['eligible_count']} | kalan: {data['remaining_count']}",
                f"Korunan: vaka={data['case_protected_count']} açık koruma={data['explicit_hold_count']}",
                "Kesim zamanı: " + data["cutoff"], "Önizleme kimliği: " + data["token"]]
    if "operation" in data and "status" in data:
        receipt = data.get("receipt") or {}
        return [f"Saklama çalışması: {data['id']} | {data['operation']} | {data['status']}",
                f"  Değişen gövde: {receipt.get('changed_count', 0)} | mantıksal silme: hayır"]
    if "scope_key" in data and "kind" in data:
        return [f"Koruma: {data['id']} | {data['kind']} | "
                + ("etkin" if data["active"] else "kaldırılmış"),
                f"  Aile: {data['family']} | kapsam: {data['scope_key']}"]
    if "items" in data:
        lines = []
        for item in data["items"]:
            lines.extend(retention_lines(item) if isinstance(item, dict) else [safe_text(str(item))])
        if not lines:
            lines.append("Bu kapsamda saklama kaydı yok.")
        if data.get("next_after") is not None:
            lines.append("Sonraki sayfa: --after " + str(data["next_after"]))
        return lines
    if "recovered_count" in data:
        return [f"Kesilmiş çalışma: {data['recovered_count']} kayıt kapatıldı."]
    return [safe_text(json.dumps(data, ensure_ascii=False))]


def execute_retention(database, args):
    from xti.adapters.worker_lock import LocalExecutionLock
    service = make_retention_service(database)
    operation = args.retention_operation
    keys = {
        "identifier", "name", "organization_id", "families", "archive_after_days",
        "batch_limit", "purpose", "retention_basis", "enabled", "expected_revision",
        "token", "record_id", "case_id", "family", "kind", "policy_id", "status",
        "active", "resource_kind", "after", "limit", "actor", "reason", "idempotency_key",
    }
    values = {key: getattr(args, key) for key in keys if getattr(args, key, None) is not None}
    if operation in WRITES:
        values.setdefault("idempotency_key", "cli:" + str(uuid4()))
    lock = LocalExecutionLock(database).acquire() if operation in WRITES else nullcontext()
    with lock:
        if operation in (PREFIX + "policy.update", PREFIX + "policy.disable", PREFIX + "apply") \
                and "expected_revision" not in values:
            values["expected_revision"] = service.execute(
                PREFIX + "policy.show", identifier=values["identifier"],
            )["revision"]
        if operation == PREFIX + "hold.release" and "expected_revision" not in values:
            values["expected_revision"] = service.execute(
                PREFIX + "hold.show", identifier=values["identifier"],
            )["revision"]
        result = service.execute(operation, **values)
    return result, retention_lines(result)


def execute_platform_retention(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    values = dict(request.parameters)
    if values.pop("expected_workspace_id") != context.workspace_id:
        raise EngineContractError("scope_mismatch", "Saklama isteği güncel firma veri alanına ait değil.")
    with LocalExecutionLock(context.database).acquire():
        return make_retention_service(context.database).execute(request.operation, **values)
