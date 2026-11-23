"""Terminal and company JSON boundary for P12 telemetry."""

from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite_telemetry import SQLiteTelemetryRepository
from xti.adapters.telemetry_files import (
    preview_data, preview_file_payload, read_telemetry_file,
)
from xti.application.telemetry import TelemetryService
from xti.domain.assets import ValidationError
from xti.domain.telemetry import (
    DECISIONS, INPUT_FORMATS, PREFIX, READS, RECORD_KINDS, SOURCE_KINDS, WRITES,
)
from xti.interfaces.text import safe_text


def make_telemetry_service(database: Path) -> TelemetryService:
    return TelemetryService(SQLiteTelemetryRepository(database))


def register_telemetry_parser(commands) -> None:
    root = commands.add_parser(
        "telemetry",
        help="Honeypot/sinkhole gözlemlerini ve tamamlanmış sandbox raporlarını güvenli kanıt olarak yönet.",
    )
    actions = root.add_subparsers(dest="telemetry_action", required=True)
    actions.add_parser("capabilities", help="Desteklenen biçimleri, sınırları ve saklanmayan hassas alanları göster.")
    add = actions.add_parser("source-add", help="Kuruluş kapsamında telemetri kaynağı tanımla.")
    add.add_argument("--organization", dest="organization_id", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--kind", dest="source_kind", choices=SOURCE_KINDS, required=True)
    add.add_argument("--format", dest="input_format", choices=INPUT_FORMATS, required=True)
    add.add_argument("--description", required=True)
    add.add_argument("--idempotency-key")
    update = actions.add_parser("source-update", help="Kaynak adını/açıklamasını veya etkinliğini sürümlü güncelle.")
    update.add_argument("identifier")
    update.add_argument("--expected-revision", type=int)
    update.add_argument("--name")
    update.add_argument("--description")
    enabled = update.add_mutually_exclusive_group()
    enabled.add_argument("--enable", dest="enabled", action="store_const", const=True, default=None)
    enabled.add_argument("--disable", dest="enabled", action="store_const", const=False)
    update.add_argument("--reason", required=True)
    update.add_argument("--idempotency-key")
    sources = actions.add_parser("sources", help="Kayıtlı telemetri kaynaklarını sayfalı listele.")
    sources.add_argument("--organization", dest="organization_id")
    _page(sources)
    show = actions.add_parser("source-show", help="Tek kaynak ve değişiklik geçmişini göster.")
    show.add_argument("identifier")
    preview = actions.add_parser("preview", help="Telemetri dosyasını yazmadan ve çalıştırmadan doğrula.")
    preview.add_argument("source", type=Path)
    preview.add_argument("--format", dest="input_format", choices=INPUT_FORMATS, required=True)
    apply = actions.add_parser("import", help="Önizlenmiş telemetriyi tekrar güvenli ve atomik içe al.")
    apply.add_argument("source_id")
    apply.add_argument("source", type=Path)
    apply.add_argument("--format", dest="input_format", choices=INPUT_FORMATS, required=True)
    apply.add_argument("--expected-revision", type=int)
    apply.add_argument("--expected-content-sha256", required=True)
    apply.add_argument("--idempotency-key")
    runs = actions.add_parser("runs", help="İçe alma çalışmalarını sayfalı listele.")
    runs.add_argument("--organization", dest="organization_id")
    runs.add_argument("--source-id")
    _page(runs)
    run = actions.add_parser("run-show", help="İçe alma makbuzu ve kayıt eylemlerini göster.")
    run.add_argument("identifier")
    records = actions.add_parser("records", help="Normalize telemetri kanıtlarını sayfalı listele.")
    records.add_argument("--organization", dest="organization_id")
    records.add_argument("--source-id")
    records.add_argument("--kind", dest="record_kind", choices=RECORD_KINDS)
    _page(records)
    record = actions.add_parser("record-show", help="Tek telemetri kanıtı, sürümleri ve incelemelerini göster.")
    record.add_argument("identifier")
    review = actions.add_parser("review", help="Güncel telemetri kanıtına insan kararı bağla.")
    review.add_argument("identifier")
    review.add_argument("--expected-revision", type=int)
    review.add_argument("--decision", choices=DECISIONS, required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--actor", required=True)
    review.add_argument("--idempotency-key")
    reviews = actions.add_parser("reviews", help="Tek kaydın inceleme geçmişini göster.")
    reviews.add_argument("identifier")
    _page(reviews)
    report = actions.add_parser("report", help="Kuruluşun telemetri kaynak, çalışma, kayıt ve inceleme özetini göster.")
    report.add_argument("organization_id")
    recover = actions.add_parser("recover", help="Kesilmiş telemetri çalışmalarını açıkça interrupted durumuna al.")
    recover.add_argument("source_id")
    recover.add_argument("--reason", required=True)
    recover.add_argument("--idempotency-key")


def _page(parser):
    parser.add_argument("--after", type=int, default=0)
    parser.add_argument("--limit", type=int, default=50)


def _lines(data: dict) -> list[str]:
    if "never_stored" in data:
        return [
            "Telemetri alımı hazır: " + ", ".join(data["input_formats"]),
            "Saklanmayanlar: " + ", ".join(data["never_stored"]),
            "XTI zararlı örnek çalıştırmaz; yalnız tamamlanmış raporu normalize eder.",
        ]
    if "items" in data:
        lines = []
        for item in data["items"]:
            if "summary" in item:
                lines.append(f"{item['id']} | {item.get('kind','record')} | {safe_text(item['summary'])}")
            elif "status" in item:
                lines.append(f"{item['id']} | {item['status']} | kayıt {item.get('record_count',0)}")
            else:
                lines.append(f"{item['id']} | {safe_text(item.get('name', item.get('decision','telemetry')))}")
        if not lines:
            lines.append("Bu kapsamda telemetri kaydı yok.")
        if data.get("next_after"):
            lines.append("Sonraki sayfa: --after " + str(data["next_after"]))
        return lines
    if "source" in data and "action" in data:
        source = data["source"]
        return [f"Kaynak {data['action']}: {source['id']}",
                f"{safe_text(source['name'])} | {source['source_kind']} | {source['input_format']} | sürüm {source['revision']}"]
    if "source_kind" in data and "input_format" in data:
        return [f"{data['id']} | {safe_text(data['name'])} | {data['source_kind']} | {data['input_format']}",
                f"Sürüm {data['revision']} | etkin {data['enabled']}"]
    if "content_sha256" in data and "preview_sha256" in data:
        return [f"Çalışma: {data.get('id','önizleme')} | {data.get('status','doğrulandı')}",
                f"Girdi {data['input_count']} | kabul {data['record_count']} | atlanan {data['ignored_count']} | aynı tekrar {data['duplicate_count']}",
                f"İçerik SHA-256: {data['content_sha256']}"]
    if "body" in data:
        return [f"{data['id']} | {data['kind']} | {safe_text(data['summary'])}",
                f"Kaynak: {safe_text(data['source']['name'])} | olay: {data['event_at']}",
                f"İnceleme: {data['review']['decision'] if data['review'] else 'bekliyor'} | yeniden inceleme: {data['needs_review']}"]
    if "review" in data and "action" in data:
        review = data["review"]
        return [f"İnceleme kaydedildi: {review['decision']} | sürüm {review['revision']}", safe_text(review["reason"])]
    if "organization" in data and "records" in data:
        return [f"Telemetri özeti: {safe_text(data['organization']['name'])}",
                f"Kaynak {data['sources']['enabled']}/{data['sources']['total']} etkin | çalışma {data['runs']['total']}",
                f"Kayıt {data['records']['total']} | yeniden inceleme {data['reviews']['needs_review']}"]
    if data.get("action") == "recovered":
        return [f"Kesilmiş çalışma sayısı: {data['recovered_count']}"]
    return [safe_text(str(data))]


def execute_telemetry(database: Path, args) -> tuple[dict, list[str]]:
    action = args.telemetry_action
    if action == "preview":
        result = preview_file_payload(
            read_telemetry_file(args.source), input_format=args.input_format,
        )
        data = preview_data(result)
        return data, [
            "Telemetri dosyası doğrulandı; henüz veritabanına yazılmadı.",
            *_lines(data),
            "İçe almak için içerik SHA-256 değerini --expected-content-sha256 ile kullanın.",
        ]
    service = make_telemetry_service(database)
    operation = {
        "capabilities": "capabilities", "source-add": "source.add",
        "source-update": "source.update", "sources": "sources",
        "source-show": "source.get", "runs": "runs", "run-show": "run.get",
        "records": "records", "record-show": "record.get", "review": "review",
        "reviews": "reviews", "report": "report", "recover": "recover",
    }.get(action)
    if action == "import":
        preview = preview_file_payload(
            read_telemetry_file(args.source), input_format=args.input_format,
        )
        if preview.content_sha256 != args.expected_content_sha256:
            raise ValidationError("Telemetri dosyası önizlemeden sonra değişti; yeniden önizleyin.")
        source = service.execute(PREFIX + "source.get", identifier=args.source_id)
        revision = args.expected_revision or source["revision"]
        from xti.adapters.worker_lock import LocalExecutionLock
        with LocalExecutionLock(database).acquire():
            data = service.import_preview(
                source_id=args.source_id, expected_revision=revision, preview=preview,
                idempotency_key=args.idempotency_key or "cli:" + str(uuid4()),
            )
        return data, _lines(data)
    values = {}
    for key in (
        "identifier", "organization_id", "name", "source_kind", "input_format",
        "description", "expected_revision", "enabled", "reason", "source_id",
        "record_kind", "decision", "actor", "after", "limit", "idempotency_key",
    ):
        value = getattr(args, key, None)
        if value is not None:
            values[key] = value
    full = PREFIX + operation
    if full in WRITES:
        values.setdefault("idempotency_key", "cli:" + str(uuid4()))
    if full in {PREFIX + "source.update", PREFIX + "review"} and "expected_revision" not in values:
        current_operation = PREFIX + ("source.get" if full.endswith("source.update") else "record.get")
        current = service.execute(current_operation, identifier=values["identifier"])
        values["expected_revision"] = current["revision"]
    from xti.adapters.worker_lock import LocalExecutionLock
    with LocalExecutionLock(database).acquire() if full in WRITES else nullcontext():
        data = service.execute(full, **values)
    return data, _lines(data)


def execute_platform_telemetry(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    values = dict(request.parameters)
    if values.pop("expected_workspace_id") != context.workspace_id:
        raise EngineContractError("scope_mismatch", "Telemetri isteği güncel firma veri alanına ait değil.")
    with LocalExecutionLock(context.database).acquire():
        return make_telemetry_service(context.database).execute(request.operation, **values)
