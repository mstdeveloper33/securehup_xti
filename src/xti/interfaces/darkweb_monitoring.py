"""P05 terminal and company-platform composition boundary."""

from contextlib import nullcontext
import json
from pathlib import Path
import time
from uuid import uuid4

from xti.domain.darkweb_monitoring import (
    ACTIVE_SOURCES,
    DECISIONS,
    KINDS,
    PREFIX,
    PRIORITIES,
    PROFILE_FIELDS,
    WRITES,
    integer,
)
from xti.interfaces.text import safe_text


CLI = {name.replace(".", "-"): PREFIX + name for name in (
    "capabilities", "profiles", "profile.add", "profile.update", "profile.show", "plan",
    "run", "runs", "run.show", "findings", "finding.show", "evidence.show", "review",
    "reviews", "changes", "credential.runs", "credential.run.show",
    "source.runs", "source.run.show", "source.records", "source.record.show",
    "lunar.refresh", "ail.preview", "ail.import", "report", "recover",
)}


def make_darkweb_service(database):
    from xti.adapters.darkweb_monitoring_inputs import SQLiteDarkwebInputs
    from xti.adapters.lunar_domain_exposure import LunarDomainExposureSource
    from xti.adapters.sqlite_darkweb_monitoring import SQLiteDarkwebRepository
    from xti.application.darkweb_monitoring import DarkwebService
    return DarkwebService(
        SQLiteDarkwebRepository(database), SQLiteDarkwebInputs(database),
        LunarDomainExposureSource(),
    )


def register_darkweb_parser(commands) -> None:
    root = commands.add_parser(
        "darkweb", help="Kaynaklı ransomware, breach ve maskeli credential kanıtlarını izle.",
    )
    actions = root.add_subparsers(dest="darkweb_action", required=True)
    for command, operation in CLI.items():
        parser = actions.add_parser(command, help="Dark web izleme işlemi: " + command)
        parser.set_defaults(darkweb_operation=operation)
        if command.endswith(("-show", "-update")) or command in ("plan", "run", "review", "reviews", "recover"):
            parser.add_argument("identifier")
        if command in ("profile-add", "profile-update"):
            parser.add_argument("--name", required=command == "profile-add")
            parser.add_argument("--organization", dest="organization_id", required=command == "profile-add")
            parser.add_argument("--alias", dest="aliases", action="append")
            parser.add_argument("--source", dest="sources", action="append", choices=ACTIVE_SOURCES)
            supplier = parser.add_mutually_exclusive_group()
            supplier.add_argument("--include-suppliers", dest="include_suppliers", action="store_const", const=True, default=None)
            supplier.add_argument("--exclude-suppliers", dest="include_suppliers", action="store_const", const=False)
            parser.add_argument("--usage-mode", choices=("personal", "commercial"))
            parser.add_argument("--alert-priority", dest="alert_priorities", action="append", choices=PRIORITIES)
            parser.add_argument("--max-findings", type=int)
            parser.add_argument("--interval-seconds", type=int)
        if command == "profile-update":
            enabled = parser.add_mutually_exclusive_group()
            enabled.add_argument("--enable", dest="enabled", action="store_const", const=True, default=None)
            enabled.add_argument("--disable", dest="enabled", action="store_const", const=False)
        if command in ("profile-update", "run", "review"):
            parser.add_argument("--expected-revision", type=int)
        if command == "run":
            parser.add_argument("--force", action="store_true")
        if command == "review":
            parser.add_argument("--evidence-id", required=True)
            parser.add_argument("--observation-revision", dest="expected_observation_revision", type=int)
            parser.add_argument("--decision", required=True, choices=DECISIONS)
            parser.add_argument("--reason", required=True)
        if command == "lunar-refresh":
            parser.add_argument("identifier", help="Dark web profil kimliği.")
            parser.add_argument("domain", help="Kuruluşa açıkça bağlı kesin domain.")
            parser.add_argument("--expected-revision", type=int)
        if command in ("ail-preview", "ail-import"):
            parser.add_argument("identifier", help="AIL kaynağı seçilmiş dark web profil kimliği.")
            parser.add_argument("source", type=Path, help="xti-ail-v1 JSON zarfı dosyasının yolu.")
            if command == "ail-import":
                parser.add_argument("--expected-revision", type=int)
                parser.add_argument("--expected-content-sha256", required=True)
        if command in ("profiles", "runs", "findings", "reviews", "changes", "credential-runs",
                       "source-runs", "source-records"):
            parser.add_argument("--after", type=int, default=0)
            parser.add_argument("--limit", type=int, default=20)
            if command != "profiles":
                parser.add_argument("--profile-id")
            if command in ("source-runs", "source-records"):
                parser.add_argument("--provider", choices=("lunar_domain", "ail_tracker"))
            if command == "source-records":
                parser.add_argument("--kind", dest="record_kind",
                                    choices=("domain_exposure", "underground_mention"))
        if command == "findings":
            parser.add_argument("--kind", choices=KINDS)
            parser.add_argument("--decision", choices=DECISIONS)
            parser.add_argument("--priority", choices=PRIORITIES)
            parser.add_argument("--target-kind", choices=("organization", "supplier"))
        if command == "report":
            parser.add_argument("--profile-id", required=True)
            parser.add_argument("--run-id")
        if operation in WRITES:
            parser.add_argument("--idempotency-key")
    monitor = actions.add_parser("monitor", help="Bir dark web profilini sınırlı döngüde çalıştır.")
    monitor.add_argument("identifier")
    monitor.add_argument("--cycles", type=int, default=1)
    monitor.set_defaults(darkweb_monitor=True)


def darkweb_lines(data: dict) -> list[str]:
    if "candidate_key" in data and "evidence" in data:
        body = data["evidence"]["body"]
        return [
            f"{data['id']} | {data['kind']} | {data['priority']} | {data['observation_state']}",
            "  Hedef: " + safe_text(body["target"]["label"]) + " (" + body["target"]["kind"] + ")",
            "  Kaynak: " + safe_text(body["source"]["name"]) + " | kayıt " + safe_text(body["source"]["record_id"]),
            "  Eşleşme: " + "; ".join(safe_text(reason) for reason in body["match"]["reasons"]),
            "  Karar: " + (data["review"]["decision"] if data.get("review") else "inceleme bekliyor")
            + " | Yeniden inceleme: " + str(data["needs_review"]),
            "  Not: Kaynak iddiasıdır; otomatik ihlal veya incident kararı değildir.",
        ]
    if "items" in data:
        lines = []
        for item in data["items"]:
            lines.extend(darkweb_lines(item))
        if not lines:
            lines.append("Bu kapsamda kayıt yok; kaynak durumu ve son başarılı snapshot ayrıca kontrol edilmelidir.")
        if data.get("next_after") is not None:
            lines.append("Sonraki sayfa: --after " + str(data["next_after"]))
        return lines
    if "definition" in data and "organization" in data and "id" in data:
        return [f"{data['id']} | {safe_text(data['definition']['name'])} | sürüm {data['revision']} | {data['binding_state']}",
                "  Kuruluş: " + safe_text(data["organization"]["display_name"]),
                "  Kaynaklar: " + ", ".join(data["definition"]["sources"])]
    if "snapshot" in data:
        report = data.get("report") or {}
        return [f"Çalışma: {data['id']} | {data['status']}",
                "  Bulgular: " + safe_text(json.dumps(report.get("counts", {}), ensure_ascii=False)),
                f"  Yeni: {report.get('new_findings', 0)} | Değişen: {report.get('changed_findings', 0)} | Bildirim: {report.get('notifications', 0)}",
                "  Sessiz başlangıç: " + str(report.get("silent_baseline", False))]
    if data.get("provider") == "xposedornot_domain" and "account_count" in data:
        return [f"Credential kaynak turu: {data['id']} | {data['status']} | {data['domain']}",
                f"  Maskeli hesap: {data['account_count']} | yeni {data['added_count']} | değişen {data['updated_count']} | kaldırılan {data['removed_count']}",
                "  Ham alias, parola, token veya cookie saklanmaz ve çıktıya verilmez."]
    if data.get("ready_to_import") is True:
        return [
            f"AIL zarfı doğrulandı: {data['record_count']} kayıt",
            "İçerik SHA-256: " + data["content_sha256"],
            "Ham içerik veya kaynak adresi saklanmayacak.",
        ]
    if (data.get("provider") in ("lunar_domain", "ail_tracker")
            and "record_count" in data and "id" in data):
        return [
            f"Kaynak turu: {data['id']} | {data['provider']} | {data['status']}",
            f"Kayıt {data['record_count']} | yeni {data['added_count']} | değişen {data['updated_count']} | kaldırılan {data['removed_count']}",
            "  Ham credential, kaynak sayfa gövdesi ve Tor adresi saklanmaz.",
        ]
    if data.get("record_kind") in ("domain_exposure", "underground_mention"):
        return [
            f"{data['id']} | {data['record_kind']} | {safe_text(data['title'])}",
            f"Kaynak: {data['provider']} | etkin: {data['active']}",
        ]
    if "finding_counts" in data:
        return ["Dark web raporu: " + safe_text(data["profile"]["definition"]["name"]),
                "Bulgular: " + safe_text(json.dumps(data["finding_counts"], ensure_ascii=False)),
                "İnceleme bekleyen: " + str(data["pending_review_count"]),
                "Otomatik incident: hayır"]
    if "decision" in data:
        return [f"İnceleme: {data['id']} | {data['decision']}", safe_text(data["reason"])]
    return [safe_text(json.dumps(data, ensure_ascii=False))]


def execute_darkweb(database, args):
    from xti.adapters.worker_lock import LocalExecutionLock
    service = make_darkweb_service(database)
    if getattr(args, "darkweb_monitor", False):
        integer(args.cycles, 1, 100)
        runs = []
        for index in range(args.cycles):
            with LocalExecutionLock(database).acquire():
                profile = service.execute(PREFIX + "profile.show", identifier=args.identifier)
                run = service.execute(PREFIX + "run", identifier=profile["id"],
                    expected_revision=profile["revision"], force=index > 0,
                    idempotency_key="monitor:" + str(uuid4()))
            runs.append({"id": run["id"], "status": run["status"]})
            if not args.json:
                print("\n".join(darkweb_lines(run)), flush=True)
            if index + 1 < args.cycles:
                time.sleep(profile["definition"]["interval_seconds"])
        return {"runs": runs}, ["Dark web izleme döngüsü tamamlandı."]
    operation = args.darkweb_operation
    keys = PROFILE_FIELDS | {"identifier", "domain", "after", "limit", "profile_id", "run_id",
        "kind", "decision", "priority", "target_kind", "evidence_id", "expected_revision",
        "expected_observation_revision", "enabled", "force", "reason", "idempotency_key",
        "expected_content_sha256", "provider", "record_kind"}
    values = {key: getattr(args, key) for key in keys if getattr(args, key, None) is not None}
    if operation in (PREFIX + "ail.preview", PREFIX + "ail.import"):
        from xti.adapters.ail_intake_file import read_ail_envelope
        values["batch"] = read_ail_envelope(args.source)
    if operation in WRITES:
        values.setdefault("idempotency_key", "cli:" + str(uuid4()))
    lock = LocalExecutionLock(database).acquire() if operation in WRITES else nullcontext()
    with lock:
        if operation in (PREFIX + "profile.update", PREFIX + "run", PREFIX + "review",
                         PREFIX + "lunar.refresh", PREFIX + "ail.import") and "expected_revision" not in values:
            record = service.execute(PREFIX + ("finding.show" if operation == PREFIX + "review" else "profile.show"),
                                     identifier=values["identifier"])
            values["expected_revision"] = record["review_revision"] if operation == PREFIX + "review" else record["revision"]
        if operation == PREFIX + "review" and "expected_observation_revision" not in values:
            values["expected_observation_revision"] = service.execute(
                PREFIX + "finding.show", identifier=values["identifier"],
            )["observation_revision"]
        result = service.execute(operation, **values)
    return result, darkweb_lines(result)


def execute_platform_darkweb(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    values = dict(request.parameters)
    if values.pop("expected_workspace_id") != context.workspace_id:
        raise EngineContractError("scope_mismatch", "Dark web isteği güncel firma alanına ait değil.")
    with LocalExecutionLock(context.database).acquire():
        return make_darkweb_service(context.database).execute(request.operation, **values)
