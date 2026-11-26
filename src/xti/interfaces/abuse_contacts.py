"""Terminal boundary for reviewed abuse-contact discovery."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
import time
from uuid import uuid4

from xti.adapters.abuse_contact_sources import AbuseContactSourceAdapter
from xti.adapters.sqlite_abuse_contacts import SQLiteAbuseContactRepository
from xti.application.abuse_contacts import AbuseContactService
from xti.application.foreground_monitor import MonotonicBudget
from xti.domain.abuse_contact_contract import PREFIX, WRITES
from xti.domain.assets import ValidationError
from xti.interfaces.text import safe_text


def make_abuse_contact_service(database):
    return AbuseContactService(
        SQLiteAbuseContactRepository(database), AbuseContactSourceAdapter(),
    )


def register_abuse_contact_parsers(actions) -> None:
    capabilities = actions.add_parser(
        "contact-capabilities", help="Abuse iletişim kaynaklarını ve güvenlik sınırlarını göster.",
    )
    capabilities.set_defaults(contact_operation=PREFIX + "capabilities")
    plan = actions.add_parser(
        "contact-plan", help="Vaka kanıtına bağlı domain/IP iletişim keşfini ağsız planla.",
    )
    plan.add_argument("case_id"); plan.add_argument("evidence_link_id")
    _subject(plan); _watch_options(plan)
    plan.set_defaults(contact_operation=PREFIX + "plan")
    add = actions.add_parser(
        "contact-watch-add", help="İnsan incelemeli abuse iletişim izlemesi kaydet.",
    )
    add.add_argument("case_id"); add.add_argument("evidence_link_id")
    _subject(add); _watch_options(add); _actor(add)
    add.set_defaults(contact_operation=PREFIX + "watch.add")
    listing = actions.add_parser("contact-watches", help="İletişim izlemelerini sayfalı listele.")
    listing.add_argument("--case-id"); listing.add_argument("--enabled", choices=("true", "false"))
    _page(listing); listing.set_defaults(contact_operation=PREFIX + "watches")
    show = actions.add_parser("contact-watch-show", help="İletişim izlemesi ve güncelliğini göster.")
    show.add_argument("watch_id"); show.set_defaults(contact_operation=PREFIX + "watch.show")
    events = actions.add_parser("contact-watch-events", help="İzleme değişiklik geçmişini sayfalı göster.")
    events.add_argument("watch_id"); _page(events); events.set_defaults(contact_operation=PREFIX + "watch.events")
    update = actions.add_parser("contact-watch-update", help="İzleme aralığı veya WHOIS fallback seçimini güncelle.")
    update.add_argument("watch_id"); update.add_argument("--expected-revision", type=int)
    update.add_argument("--interval-seconds", type=int)
    whois = update.add_mutually_exclusive_group()
    whois.add_argument("--include-whois", dest="include_whois", action="store_const", const=True)
    whois.add_argument("--exclude-whois", dest="include_whois", action="store_const", const=False)
    enabled = update.add_mutually_exclusive_group()
    enabled.add_argument("--enable", dest="enabled", action="store_const", const=True)
    enabled.add_argument("--disable", dest="enabled", action="store_const", const=False)
    _actor(update); update.set_defaults(contact_operation=PREFIX + "watch.update")
    disable = actions.add_parser("contact-watch-disable", help="İletişim izlemesini geçmişi silmeden kapat.")
    disable.add_argument("watch_id"); disable.add_argument("--expected-revision", type=int)
    _actor(disable); disable.set_defaults(contact_operation=PREFIX + "watch.disable")
    due = actions.add_parser("contact-due", help="Yenileme zamanı gelen iletişim izlemelerini göster.")
    due.add_argument("--at"); due.add_argument("--limit", type=int, default=100)
    due.set_defaults(contact_operation=PREFIX + "due")
    refresh = actions.add_parser("contact-refresh", help="RDAP, security.txt ve gerekirse WHOIS kaynaklarını yenile.")
    refresh.add_argument("watch_id"); refresh.add_argument("--expected-revision", type=int)
    refresh.add_argument("--force", action="store_true")
    refresh.add_argument("--timeout-seconds", type=int, default=60)
    refresh.add_argument("--idempotency-key")
    refresh.set_defaults(contact_operation=PREFIX + "refresh")
    runs = actions.add_parser("contact-runs", help="İletişim kaynak çalışmalarını sayfalı listele.")
    runs.add_argument("--watch-id"); runs.add_argument("--status", choices=("running", "complete", "partial", "failed", "interrupted"))
    _page(runs); runs.set_defaults(contact_operation=PREFIX + "runs")
    run_show = actions.add_parser("contact-run-show", help="Kaynak makbuzlarıyla iletişim çalışmasını göster.")
    run_show.add_argument("run_id"); run_show.set_defaults(contact_operation=PREFIX + "run.show")
    candidates = actions.add_parser("contact-candidates", help="Bulunan iletişim adaylarını sayfalı listele.")
    candidates.add_argument("watch_id")
    active = candidates.add_mutually_exclusive_group()
    active.add_argument("--active", dest="active", action="store_const", const=True)
    active.add_argument("--inactive", dest="active", action="store_const", const=False)
    candidates.add_argument("--decision", choices=("approved", "rejected", "uncertain"))
    _page(candidates); candidates.set_defaults(contact_operation=PREFIX + "candidates")
    candidate = actions.add_parser("contact-candidate-show", help="İletişim adayını kanıtı ve kararıyla göster.")
    candidate.add_argument("candidate_id"); candidate.set_defaults(contact_operation=PREFIX + "candidate.show")
    candidate_events = actions.add_parser("contact-candidate-events", help="Aday değişiklik geçmişini sayfalı göster.")
    candidate_events.add_argument("candidate_id"); _page(candidate_events)
    candidate_events.set_defaults(contact_operation=PREFIX + "candidate.events")
    review = actions.add_parser("contact-review", help="İletişim adayını güncel kanıt üzerinde insan kararıyla incele.")
    review.add_argument("candidate_id"); review.add_argument("--expected-observation-revision", type=int)
    review.add_argument("--expected-review-revision", type=int)
    review.add_argument("--decision", required=True, choices=("approved", "rejected", "uncertain"))
    _actor(review); review.set_defaults(contact_operation=PREFIX + "review")
    reviews = actions.add_parser("contact-reviews", help="İletişim adayı karar geçmişini sayfalı göster.")
    reviews.add_argument("candidate_id"); _page(reviews); reviews.set_defaults(contact_operation=PREFIX + "reviews")
    recover = actions.add_parser("contact-recover", help="Yarım kalmış iletişim çalışmasını kanıt kaybetmeden kapat.")
    recover.add_argument("run_id"); _actor(recover); recover.set_defaults(contact_operation=PREFIX + "recover")
    monitor = actions.add_parser("contact-monitor", help="Terminal açıkken zamanı gelen yenilemeleri sınırlı turla çalıştır.")
    monitor.add_argument("watch_id"); monitor.add_argument("--max-cycles", type=int, default=3)
    monitor.add_argument("--max-duration-seconds", type=int, default=86400)
    monitor.add_argument("--timeout-seconds", type=int, default=60)
    monitor.set_defaults(contact_operation="terminal.contact.monitor")


def _subject(parser) -> None:
    parser.add_argument("--subject-kind", required=True, choices=("domain", "ip"))
    parser.add_argument("--subject", dest="subject_value", required=True)


def _watch_options(parser) -> None:
    parser.add_argument("--interval-seconds", type=int, default=86400)
    parser.add_argument("--exclude-whois", dest="include_whois", action="store_false", default=True)


def _actor(parser) -> None:
    parser.add_argument("--actor", required=True); parser.add_argument("--reason", required=True)
    parser.add_argument("--idempotency-key")


def _page(parser) -> None:
    parser.add_argument("--offset", type=int, default=0); parser.add_argument("--limit", type=int, default=50)


def contact_lines(data: dict) -> list[str]:
    if "sources" in data and "automatic_submission" in data:
        whois = "kurulu" if data["sources"]["whois"]["available"] else "kurulu değil; zorunlu değil"
        return [
            "Abuse iletişim keşfi hazır.",
            "Ana kaynaklar: domain/IP RDAP; security.txt yalnız yardımcı; "
            f"WHOIS düşük güvenli fallback ({whois}).",
            "Bulunan adres insan onayı olmadan takedown taslağına bağlanmaz; otomatik gönderim yok.",
        ]
    if "plan_sha256" in data:
        return [
            f"İletişim planı: {safe_text(data['subject_kind'])} · {safe_text(data['subject_value'])}",
            "Kaynaklar: " + ", ".join(data["sources"]),
            f"Aralık: {data['interval_seconds']} sn | plan: {data['plan_sha256']}",
        ] + [safe_text(item) for item in data["notes"]]
    if "schedule" in data and "subject_value" in data:
        return [
            f"İletişim izlemesi: {safe_text(data['id'])} | sürüm {data['revision']} | " + ("etkin" if data["enabled"] else "kapalı"),
            f"Hedef: {safe_text(data['subject_kind'])} · {safe_text(data['subject_value'])}",
            f"Aktif aday: {data['active_candidate_count']} | çalışma: {data['total_run_count']} | sıradaki: {data['schedule']['due_at']}",
        ]
    if "status" in data and "watch_id" in data and "source_count" in data:
        return [
            f"İletişim çalışması: {safe_text(data['id'])} | {safe_text(data['status'])}",
            f"Kaynak: {data['succeeded_source_count']} tamamlanan / {data['failed_source_count']} eksik",
            f"Aktif aday: {data['candidate_count']} | yeni {data['added_count']} | güncel {data['updated_count']} | değişmeyen {data['unchanged_count']} | kaldırılan {data['removed_count']}",
            "Önceki başarılı kanıt kaynak hatasında korunur; otomatik başvuru yapılmaz.",
        ]
    if "contact_value" in data and "source_key" in data:
        decision = data["review"]["decision"] if data.get("review") and data.get("review_state") == "current" else data.get("review_state", "unreviewed")
        return [
            f"İletişim adayı: {safe_text(data['id'])} | {safe_text(data['contact_kind'])} | {safe_text(data['confidence'])}",
            f"Kanal: {safe_text(data['channel'])} · {safe_text(data['contact_value'])}",
            f"Kaynak sınıfı: {safe_text(data['source_key'])} | karar: {safe_text(decision)} | takedown için hazır: {data['usable_for_takedown']}",
        ]
    if "items" in data:
        lines = []
        for item in data["items"]:
            lines.extend(contact_lines(item))
        if not lines:
            lines.append("Bu kapsamda abuse iletişim kaydı yok.")
        if data.get("has_more"):
            lines.append("Sonraki sayfa için offset değerini artırın.")
        return lines
    return [safe_text(str(data))]


def _values(args) -> dict:
    keys = {
        "case_id", "evidence_link_id", "subject_kind", "subject_value",
        "interval_seconds", "include_whois", "watch_id", "run_id", "candidate_id",
        "expected_revision", "expected_observation_revision", "expected_review_revision",
        "enabled", "force", "timeout_seconds", "idempotency_key", "actor", "reason",
        "offset", "limit", "status", "active", "decision", "at",
    }
    result = {key: getattr(args, key) for key in keys if getattr(args, key, None) is not None}
    if getattr(args, "enabled", None) in {"true", "false"}:
        result["enabled"] = args.enabled == "true"
    return result


def _monitor(service, watch_id: str, *, max_cycles: int, max_duration_seconds: int,
             timeout_seconds: int, monotonic=time.monotonic, sleeper=time.sleep, clock=None,
             refresh_lock=lambda: nullcontext()) -> dict:
    if type(max_cycles) is not int or not 1 <= max_cycles <= 1000:
        raise ValidationError("İletişim izleme tur sınırı 1–1000 olmalı.")
    if type(max_duration_seconds) is not int or not 1 <= max_duration_seconds <= 604800:
        raise ValidationError("İletişim izleme süre sınırı 1–604800 saniye olmalı.")
    clock = clock or (lambda: datetime.now(timezone.utc))
    budget = MonotonicBudget(
        monotonic, invalid_message="İletişim izleme saati geçersiz.",
        rollback_message="İletişim izleme saati geriye gitti.",
    )
    budget.start(); runs = []; stop = "cycles"
    while len(runs) < max_cycles:
        remaining = max_duration_seconds - budget.elapsed()
        if remaining <= 0:
            stop = "duration"; break
        watch = service.execute(PREFIX + "watch.show", watch_id=watch_id)
        if not watch["enabled"]:
            stop = "disabled"; break
        due_at = datetime.fromisoformat(watch["schedule"]["due_at"])
        wait = max(0.0, (due_at - clock()).total_seconds())
        if wait:
            sleeper(min(1.0, remaining, wait)); continue
        try:
            with refresh_lock():
                run = service.execute(
                    PREFIX + "refresh", watch_id=watch_id,
                    expected_revision=watch["revision"], force=False,
                    timeout_seconds=timeout_seconds, idempotency_key="monitor:" + str(uuid4()),
                )
        except Exception as error:
            if getattr(error, "code", None) == "not_due":
                continue
            raise
        runs.append({key: run[key] for key in ("id", "status", "candidate_count", "failed_source_count")})
    return {"watch_id": watch_id, "runs": runs, "completed_cycles": len(runs),
            "stop_reason": stop, "elapsed_seconds": round(budget.elapsed(), 3),
            "notes": ["Her tamamlanan tur kalıcıdır; Ctrl+C önceki turları silmez.",
                      "Bu bir daemon değildir; düzenli çağrıyı güvenilen platform scheduler'ı yapar."]}


def execute_abuse_contacts(database, args) -> tuple[dict, list[str]]:
    service = make_abuse_contact_service(database)
    operation = args.contact_operation
    if operation == "terminal.contact.monitor":
        from xti.adapters.worker_lock import LocalExecutionLock
        data = _monitor(
            service, args.watch_id, max_cycles=args.max_cycles,
            max_duration_seconds=args.max_duration_seconds,
            timeout_seconds=args.timeout_seconds,
            refresh_lock=lambda: LocalExecutionLock(database).acquire(),
        )
        return data, [f"İletişim monitoru {data['completed_cycles']} tur tamamladı; durma nedeni: {data['stop_reason']}."]
    values = _values(args)
    if operation in WRITES:
        values.setdefault("idempotency_key", "cli:" + str(uuid4()))
        from xti.adapters.worker_lock import LocalExecutionLock
        lock = LocalExecutionLock(database).acquire()
    else:
        lock = nullcontext()
    with lock:
        if operation in {PREFIX + "watch.update", PREFIX + "watch.disable", PREFIX + "refresh"} and "expected_revision" not in values:
            values["expected_revision"] = service.execute(PREFIX + "watch.show", watch_id=values["watch_id"])["revision"]
        if operation == PREFIX + "review":
            candidate = service.execute(PREFIX + "candidate.show", candidate_id=values["candidate_id"])
            values.setdefault("expected_observation_revision", candidate["observation_revision"])
            values.setdefault("expected_review_revision", candidate["review_revision"])
        data = service.execute(operation, **values)
    return data, contact_lines(data)
