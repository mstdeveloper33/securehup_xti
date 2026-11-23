"""P04 terminal and company-platform composition boundary."""

from contextlib import nullcontext
import json
import time
from uuid import uuid4

from xti.domain.assets import ValidationError
from xti.domain.cti_analysis import (
    PREFIX, PROFILE_FIELDS, WRITES, CRITICALITIES, DECISIONS, KINDS, integer,
)
from xti.interfaces.text import safe_text


CLI = {name.replace(".", "-"): PREFIX + name for name in (
    "capabilities", "profiles", "profile.add", "profile.update", "profile.show", "plan",
    "run", "runs", "run.show", "candidates", "candidate.show", "evidence.show", "review",
    "reviews", "changes", "graph", "timeline", "trends", "source.quality", "report", "recover",
)}


def make_cti_analysis_service(database):
    from xti.adapters.cti_analysis_inputs import SQLiteCtiAnalysisInputs
    from xti.adapters.sqlite_cti_analysis import SQLiteCtiAnalysisRepository
    from xti.application.cti_analysis import CtiAnalysisService
    return CtiAnalysisService(SQLiteCtiAnalysisRepository(database), SQLiteCtiAnalysisInputs(database))


def register_cti_analysis_parser(actions) -> None:
    for command, operation in CLI.items():
        parser = actions.add_parser("analysis-" + command, help="Kanıtlı CTI analiz işlemi: " + command)
        parser.set_defaults(cti_analysis_operation=operation)
        if command.endswith(("-show", "-update")) or command in ("plan", "run", "review", "reviews", "recover"):
            parser.add_argument("identifier")
        if command in ("profile-add", "profile-update"):
            parser.add_argument("--name", required=command == "profile-add")
            parser.add_argument("--organization", dest="organization_id", required=command == "profile-add")
            parser.add_argument("--criticality", choices=CRITICALITIES)
            parser.add_argument("--identity-threshold", type=int)
            parser.add_argument("--minimum-independent-sources", type=int)
            parser.add_argument("--alert-score-min", type=int)
            parser.add_argument("--trend-new-threshold", type=int)
            parser.add_argument("--fresh-days", type=int)
            parser.add_argument("--max-entities", type=int)
            parser.add_argument("--max-relationships", type=int)
            parser.add_argument("--max-candidates", type=int)
            parser.add_argument("--max-graph-nodes", type=int)
            parser.add_argument("--max-graph-edges", type=int)
            parser.add_argument("--interval-seconds", type=int)
            parser.add_argument("--source-policy-json", dest="source_policies", action="append")
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
        if command in ("profiles", "runs", "candidates", "reviews", "changes", "timeline", "trends"):
            parser.add_argument("--after", type=int, default=0)
            parser.add_argument("--limit", type=int, default=20)
            if command != "profiles":
                parser.add_argument("--profile-id")
        if command in ("candidates", "changes"):
            parser.add_argument("--kind", choices=KINDS)
            parser.add_argument("--decision", choices=DECISIONS)
            parser.add_argument("--minimum-score", type=int)
        if command in ("graph", "report", "source-quality"):
            parser.add_argument("--profile-id", required=True)
            parser.add_argument("--run-id")
        if command == "graph":
            parser.add_argument("--node-after", type=int, default=0)
            parser.add_argument("--edge-after", type=int, default=0)
            parser.add_argument("--node-limit", type=int, default=50)
            parser.add_argument("--edge-limit", type=int, default=100)
            parser.add_argument("--expected-snapshot")
        if operation in WRITES:
            parser.add_argument("--idempotency-key")
    monitor = actions.add_parser("analysis-monitor", help="Bir CTI analiz profilini sınırlı döngüde çalıştır.")
    monitor.add_argument("identifier")
    monitor.add_argument("--cycles", type=int, default=1)
    monitor.set_defaults(cti_analysis_monitor=True)


def analysis_lines(data: dict) -> list[str]:
    if "candidate_key" in data and "evidence" in data:
        body = data["evidence"]["body"]
        return [
            f"{data['id']} | {data['kind']} | skor {data['score']} | {data['priority']}",
            "  " + safe_text(body["subject"]["label"]) + " → " + safe_text(body["object"]["label"]),
            "  Kural: " + safe_text(body["rule"]),
            "  Sinyaller: " + ", ".join(safe_text(value) for value in body["signals"]),
            "  Kaynak: " + ", ".join(sorted({safe_text(value["source_name"]) for value in body["anchors"]})),
            "  Karar: " + (data["review"]["decision"] if data.get("review") else "inceleme bekliyor")
            + " | Yeniden inceleme: " + str(data["needs_review"]),
            "  Not: Skor inceleme önceliğidir; gerçeklik, risk olasılığı veya otomatik atıf değildir.",
        ]
    if "items" in data:
        lines = []
        for item in data["items"]:
            lines.extend(analysis_lines(item))
        if not lines:
            lines.append("Bu kapsamda kayıt yok; profil ve son kaynak kapsamını da kontrol edin.")
        if data.get("next_after") is not None:
            lines.append("Sonraki sayfa: --after " + str(data["next_after"]))
        return lines
    if "definition" in data and "organization" in data and "id" in data:
        return [f"{data['id']} | {safe_text(data['definition']['name'])} | sürüm {data['revision']} | {data['binding_state']}",
                "  Kuruluş: " + safe_text(data["organization"]["display_name"]),
                f"  Kimlik eşiği: {data['definition']['identity_threshold']} | Alarm eşiği: {data['definition']['alert_score_min']}"]
    if "definition" in data and "organization" in data and "profile" in data:
        return [f"Plan: {safe_text(data['definition']['name'])} | profil {data['profile']['id']} | sürüm {data['profile']['revision']}",
                "  Kuruluş: " + safe_text(data["organization"]["display_name"]),
                "  Ağ erişimi: yok | Ücretli API: yok",
                "  Kuyruk kapsamı: " + safe_text(data.get("queue_scope_sha256", "mevcut değil"))]
    if "snapshot" in data:
        report = data.get("report") or {}
        return [f"Çalışma: {data['id']} | {data['status']}",
                "  Adaylar: " + safe_text(json.dumps(report.get("counts", {}), ensure_ascii=False)),
                "  Trend: " + safe_text((report.get("trend") or {}).get("state", "henüz yok")),
                f"  Yeni: {report.get('new_candidates', 0)} | Değişen: {report.get('changed_candidates', 0)} | Bildirim: {report.get('notifications', 0)}"]
    if "nodes" in data and "edges" in data:
        return [f"Graf: {data['total_nodes']} düğüm / {data['total_edges']} kenar",
                f"Bu sayfa: {len(data['nodes'])} düğüm / {len(data['edges'])} kenar",
                "Snapshot: " + data["snapshot_sha256"],
                "Graf ilişkileri kaynak iddiası veya inceleme adayıdır; otomatik atıf değildir."]
    if "sources" in data:
        return [f"{row['source_name']} | güven {row['reliability']} | aday {row['candidate_count']} | kabul {row['accepted']} | ret {row['rejected']}"
                for row in data["sources"]] + ["İnsan kararları güven puanını sessizce değiştirmez."]
    if "candidate_counts" in data:
        return ["CTI analiz raporu: " + safe_text(data["profile"]["definition"]["name"]),
                "Adaylar: " + safe_text(json.dumps(data["candidate_counts"], ensure_ascii=False)),
                "İnceleme bekleyen: " + str(data["pending_review_count"]),
                "Trend: " + safe_text(data["latest_run"]["report"]["trend"]["state"])]
    if "decision" in data:
        return [f"İnceleme: {data['id']} | {data['decision']}", safe_text(data["reason"])]
    return [safe_text(json.dumps(data, ensure_ascii=False))]


def execute_cti_analysis(database, args):
    from xti.adapters.worker_lock import LocalExecutionLock
    service = make_cti_analysis_service(database)
    if getattr(args, "cti_analysis_monitor", False):
        integer(args.cycles, 1, 100)
        runs = []
        for index in range(args.cycles):
            with LocalExecutionLock(database).acquire():
                profile = service.execute(PREFIX + "profile.show", identifier=args.identifier)
                run = service.execute(PREFIX + "run", identifier=profile["id"], expected_revision=profile["revision"],
                    force=index > 0, idempotency_key="monitor:" + str(uuid4()))
            runs.append({"id": run["id"], "status": run["status"]})
            if not args.json:
                print("\n".join(analysis_lines(run)), flush=True)
            if index + 1 < args.cycles:
                time.sleep(profile["definition"]["interval_seconds"])
        return {"runs": runs}, ["CTI analiz izleme döngüsü tamamlandı."]
    operation = args.cti_analysis_operation
    keys = PROFILE_FIELDS | {"identifier", "after", "limit", "profile_id", "run_id", "kind", "decision",
        "minimum_score", "evidence_id", "expected_revision", "expected_observation_revision", "enabled", "force",
        "reason", "idempotency_key", "node_after", "edge_after", "node_limit", "edge_limit", "expected_snapshot"}
    values = {key: getattr(args, key) for key in keys if getattr(args, key, None) is not None}
    if "source_policies" in values:
        try:
            values["source_policies"] = [json.loads(value) for value in values["source_policies"]]
        except (ValueError, RecursionError):
            raise ValidationError("Kaynak güven kuralı geçerli JSON olmalı.") from None
    if operation in WRITES:
        values.setdefault("idempotency_key", "cli:" + str(uuid4()))
    lock = LocalExecutionLock(database).acquire() if operation in WRITES else nullcontext()
    with lock:
        if operation in (PREFIX + "profile.update", PREFIX + "run", PREFIX + "review") and "expected_revision" not in values:
            record = service.execute(PREFIX + ("candidate.show" if operation == PREFIX + "review" else "profile.show"), identifier=values["identifier"])
            values["expected_revision"] = record["review_revision"] if operation == PREFIX + "review" else record["revision"]
        if operation == PREFIX + "review" and "expected_observation_revision" not in values:
            values["expected_observation_revision"] = service.execute(PREFIX + "candidate.show", identifier=values["identifier"])["observation_revision"]
        result = service.execute(operation, **values)
    return result, analysis_lines(result)


def execute_platform_cti_analysis(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    values = dict(request.parameters)
    if values.pop("expected_workspace_id") != context.workspace_id:
        raise EngineContractError("scope_mismatch", "CTI analiz isteği güncel firma alanına ait değil.")
    with LocalExecutionLock(context.database).acquire():
        return make_cti_analysis_service(context.database).execute(request.operation, **values)
