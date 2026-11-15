"""Company and supplier content search, credential setup, and offline history."""

from dataclasses import asdict, is_dataclass
from pathlib import Path
import shlex

from xti.domain.assets import ValidationError
from xti.domain.mentions import MENTION_NOTES, build_query
from xti.interfaces.text import safe_text


def register_mentions_parser(commands):
    parser = commands.add_parser("mentions", help="Firma ve tedarikçi hakkında internette içerik ara; kaynaklı geçmişi incele.")
    actions = parser.add_subparsers(dest="mentions_action", required=True)
    from xti.interfaces.mention_groups import register_mention_groups
    register_mention_groups(actions)
    configure = actions.add_parser("configure", help="Tavily anahtarını gizli girişle özel dosyaya kaydet; internete bağlanma.")
    configure.add_argument("--api-key-file", type=Path)
    for action in ("plan", "search"):
        item = actions.add_parser(action, help=("Gönderilecek sorguyu ağsız göster." if action == "plan"
                                               else "Tek temel Tavily araması yap ve sonuçları kaydet."))
        selection = item.add_mutually_exclusive_group(required=True)
        selection.add_argument("--name", help="Doğrudan aranacak firma adı.")
        selection.add_argument("--organization", help="Kayıtlı kuruluş kimliği.")
        selection.add_argument("--supplier", help="Kayıtlı tedarikçi kimliği.")
        item.add_argument("--domain", action="append", default=[], help="--name için firma domaini; birden fazla verilebilir.")
        item.add_argument("--topic", choices=("general", "news"), default="general")
        item.add_argument("--max-results", type=int, default=10, help="Toplanacak sonuç sayısı: 1–20. Tek istek gönderilir.")
        if action == "search":
            item.add_argument("--api-key-file", type=Path, help="Varsayılan anahtar dosyası veya ortam yerine kullanılacak özel dosya.")
    for action in ("list", "status"):
        item = actions.add_parser(action, help="Saklanan içerikleri göster." if action == "list" else "Arama geçmişini ve bildirilen kredi kullanımını göster.")
        selection = item.add_mutually_exclusive_group()
        selection.add_argument("--organization")
        selection.add_argument("--supplier")
        item.add_argument("--topic", choices=("general", "news"))
        item.add_argument("--offset", type=int, default=0)
        item.add_argument("--limit", type=int, default=20)
    item = actions.add_parser("show", help="Kaydedilen tek içeriğin ayrıntılarını ağsız göster.")
    item.add_argument("record_id")
    item = actions.add_parser("run-show", help="Bir aramanın özgün sonuçlarını ve önce/sonra farklarını ağsız göster.")
    item.add_argument("run_id")


def _wire(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_wire(item) for item in value]
    return value


def mentions_command(*arguments, data_dir=None):
    prefix = ("./xti", "--data-dir", str(data_dir)) if data_dir is not None else ("./xti",)
    return safe_text(shlex.join((*prefix, "mentions", *(str(value) for value in arguments))))


def _request_lines(request):
    target = request.target
    return [f"Hedef: {safe_text(target.name)} | {safe_text(target.kind)} | {safe_text(target.id)}",
            f"Sorgu: {safe_text(build_query(target))}",
            f"Kapsam: {request.topic} | en çok {request.max_results} sonuç | kaynak: Tavily"]


def _hit_lines(hit, *, prefix=""):
    lines = [prefix + safe_text(hit.title), "  Bağlantı: " + safe_text(hit.url),
             "  Açıklama: " + safe_text(hit.summary or "Kaynak açıklama sunmadı."),
             "  Kaynak tarih tahmini (yayın/güncelleme): " + safe_text(hit.published_at or "Yok")]
    if hit.summary_truncated:
        lines.append("  Açıklama saklama sınırına kısaltıldı; tam makale değildir.")
    return lines


def _match_lines(terms, fields):
    if terms:
        return ["  Görünür eşleşme: " + safe_text(", ".join(terms)),
                "  Eşleşen alanlar: " + safe_text(", ".join(fields))]
    return ["  Yalnız arama kaynağının önerisi; görünür başlık/açıklama/bağlantıda ad veya domain eşleşmedi."]


def record_lines(record, *, data_dir=None):
    return [*_request_lines(record.request), *_hit_lines(record.hit),
            *_match_lines(record.matched_terms, record.match_fields),
            "  Kayıt kimliği: " + safe_text(record.id),
            f"  İlk görülme: {record.first_seen_at} | son görülme: {record.last_seen_at}",
            "  Son içerik değişimi: " + safe_text(record.last_changed_at),
            "  Son kanıt: " + mentions_command("run-show", record.last_seen_run_id, data_dir=data_dir)]


def run_lines(report, *, data_dir=None):
    run = report["run"]
    lines = [f"İçerik araması: {safe_text(run.status)} | {safe_text(run.id)}", *_request_lines(run.request),
             f"Başlangıç: {run.started_at} | bitiş: {run.finished_at}",
             f"Yeni {run.added_count} | değişen {run.updated_count} | aynı {run.unchanged_count}"]
    credits = run.response.credits if run.response else None
    lines.append("Bu istekte kaynakça bildirilen kredi: " + (str(credits) if credits is not None else "bilinmiyor"))
    if run.error:
        lines.extend(("Kaynak hatası: " + safe_text(run.error),
                      "Önceki kanıt korunur. İstek başarısız görünse de kredi tüketimi sıfır varsayılmaz."))
    elif not report["results"]:
        lines.append("Bu sınırlı sorguda sonuç dönmedi; internette içerik olmadığı anlamına gelmez.")
    for item in report["results"]:
        lines.extend(("", "İşlem: " + item["action"]))
        if item["action"] == "updated":
            lines.extend(_hit_lines(item["before"], prefix="Önce: "))
        lines.extend(_hit_lines(item["after"], prefix="Sonuç: "))
        lines.extend(_match_lines(item["matched_terms"], item["match_fields"]))
    lines.append("Çalışma kanıtı: " + mentions_command("run-show", run.id, data_dir=data_dir))
    return lines + list(MENTION_NOTES)


def _next_page(args, page):
    values = [args.mentions_action, "--offset", args.offset + len(page["records"] if "records" in page else page["runs"]),
              "--limit", args.limit]
    for option, value in (("--organization", args.organization), ("--supplier", args.supplier), ("--topic", args.topic)):
        if value is not None:
            values.extend((option, value))
    return mentions_command(*values, data_dir=args.data_dir)


class _ConfiguredTavilySource:
    """Credentials are loaded only after scope/storage/lock validation."""
    def __init__(self, key_file):
        self.key_file = key_file

    def fetch(self, request):
        from xti.adapters.tavily_search import TavilySearchSource, load_tavily_api_key
        return TavilySearchSource(load_tavily_api_key(self.key_file)).fetch(request)


def make_mentions_service(database, *, search=False, api_key_file=None):
    from xti.adapters.sqlite_mentions import SQLiteMentionRepository
    from xti.adapters.sqlite_mention_targets import SQLiteMentionTargetRepository
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.application.mentions import MentionService
    return MentionService(SQLiteMentionRepository(database), SQLiteMentionTargetRepository(database),
        _ConfiguredTavilySource(api_key_file) if search else None,
        LocalExecutionLock(database) if search else None)


def configure_mentions(args):
    import getpass
    import sys
    import warnings
    from xti.adapters.tavily_search import save_tavily_api_key
    if not sys.stdin.isatty():
        raise ValidationError("Anahtar kurulumu gizli giriş için etkileşimli terminal gerektirir; TAVILY_API_KEY veya özel anahtar dosyasını kullanın.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("Tavily API anahtarı (giriş görünmez): ")
    except getpass.GetPassWarning:
        raise ValidationError("Terminal gizli girişi desteklemiyor; anahtar okunmadı. Özel anahtar dosyası kullanın.") from None
    except EOFError:
        raise ValidationError("Anahtar girişi tamamlanmadı; kayıt yapılmadı.") from None
    path = save_tavily_api_key(key, args.api_key_file)
    return {"configured": True, "key_file": str(path)}, [
        "Tavily anahtarı yalnız sahibinin okuyabildiği dosyaya kaydedildi.",
        "Dosya: " + safe_text(str(path)), "Kurulum arama yapmaz veya kredi tüketmez.",
        "Anahtar önceliği: açık --api-key-file, TAVILY_API_KEY, varsayılan özel dosya."], 0


def execute_mentions_command(service, args):
    action = args.mentions_action
    if action == "configure":
        return configure_mentions(args)
    if action in {"plan", "search"}:
        values = dict(name=args.name, domains=args.domain, organization_id=args.organization,
                      supplier_id=args.supplier, topic=args.topic, max_results=args.max_results)
        if action == "plan":
            request = service.plan(**values)
            data = {"request": request, "query": build_query(request.target), "source": "tavily",
                    "requests": 1, "search_depth": "basic", "expected_credits": 1}
            return _wire(data), [*_request_lines(request),
                "Plan: tek temel arama isteği, belgelenen tüketim 1 kredi. Otomatik tekrar yok.",
                "Bu plan internete çıkmaz, kredi tüketmez ve kayıt yazmaz.",
                "Ücretsiz bakiye bu komutla sorgulanmaz; hesabın ücretli bakiyesi varsa kullanım ona da yansıyabilir."], 0
        run = service.search(**values)
        report = service.run_show(run.id)
        return _wire(report), run_lines(report, data_dir=args.data_dir), 0 if run.status == "complete" else 3
    if action == "run-show":
        report = service.run_show(args.run_id)
        return _wire(report), run_lines(report, data_dir=args.data_dir), 0
    if action == "show":
        record = service.show(args.record_id)
        return _wire(record), record_lines(record, data_dir=args.data_dir) + list(MENTION_NOTES), 0
    filters = dict(organization_id=args.organization, supplier_id=args.supplier,
                   topic=args.topic, offset=args.offset, limit=args.limit)
    page = service.list(**filters) if action == "list" else service.status(**filters)
    shown = page["records"] if action == "list" else page["runs"]
    lines = [f"Saklanan içerik {'kayıtları' if action == 'list' else 'aramaları'}: toplam {page['total_count']} | gösterilen {len(shown)} | başlangıç {page['offset']}"]
    if action == "list":
        if page["latest_run"] is None:
            lines.append("Bu kapsamda henüz arama yapılmadı.")
        elif page["latest_run"].status == "failed":
            lines.append("Bu kapsamdaki son arama başarısız; önceki başarılı sonuçlar korunur.")
        for record in shown:
            lines.extend(("", *record_lines(record, data_dir=args.data_dir)))
            lines.append("  Ayrıntı: " + mentions_command("show", record.id, data_dir=args.data_dir))
    else:
        lines.extend((f"Kaynakça bildirilen toplam kredi: {page['reported_credits']}",
                      f"Kullanımı bilinmeyen çalışma: {page['unknown_usage_runs']}",
                      "Bu sayaç hesap bakiyesi veya fatura değildir; yalnız bu veri alanındaki çalışmaları kapsar."))
        for run in shown:
            lines.extend((f"  {safe_text(run.request.target.name)} | {run.request.topic} | {run.status} | {run.finished_at}",
                          "    Kanıt: " + mentions_command("run-show", run.id, data_dir=args.data_dir)))
    if page["has_more"]:
        lines.append("Sonraki sayfa: " + _next_page(args, page))
    return _wire(page), lines + list(MENTION_NOTES), 0
