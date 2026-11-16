"""Terminal commands for authorized Nmap targets and immutable dry-run plans."""

from dataclasses import asdict

from xti.application.nmap_management import NmapManagementService
from xti.domain.nmap_scan import NMAP_PROFILES
from xti.domain.nmap_options import NmapExecutionOptions, SCAN_TYPES, SCRIPT_CATALOG
from xti.interfaces.text import safe_text


def register_nmap_management_parsers(nmap_actions) -> None:
    targets = nmap_actions.add_parser(
        "targets", help="Yetkili kesin IP/CIDR kapsamlarını sürümlü olarak yönet.",
    )
    target_actions = targets.add_subparsers(dest="nmap_target_action", required=True)
    save = target_actions.add_parser(
        "save", help="Kesin genel IP veya sınırlandırılmış genel CIDR kaydet/güncelle.",
    )
    save.add_argument("domain", help="Etkin dış yüzey kapsamındaki domain.")
    save.add_argument("name", help="Bu hedef kümesi için kalıcı, anlaşılır ad.")
    save.add_argument(
        "--network", required=True,
        help="Kanonik kesin genel IP veya CIDR; tek kapsam en fazla 4096 adres.",
    )
    save.add_argument(
        "--exclude", action="append", default=[],
        help="Ana kapsam içindeki kesin IP/CIDR; birden çok kez verilebilir.",
    )
    save.add_argument(
        "--reason", required=True,
        help="Bu IP/CIDR kapsamını kontrol etmeye neden yetkili olduğun.",
    )
    listing = target_actions.add_parser("list", help="Kayıtlı hedef kapsamlarını göster.")
    listing.add_argument("domain", help="Kayıtlı domain.")
    listing.add_argument("--all", action="store_true", help="Geri çekilen kapsamları da göster.")
    listing.add_argument("--limit", type=int, default=100, help="Sonuç sınırı (1–500).")
    show = target_actions.add_parser("show", help="Hedef kapsamı ve sürüm geçmişini göster.")
    show.add_argument("domain", help="Kayıtlı domain.")
    show.add_argument("name", help="Hedef kapsamı adı.")
    show.add_argument("--history-limit", type=int, default=50, help="Geçmiş sınırı (1–500).")
    revoke = target_actions.add_parser(
        "revoke", help="Hedef kapsamını geri çek; geçmişi ve planları koru.",
    )
    revoke.add_argument("domain", help="Kayıtlı domain.")
    revoke.add_argument("name", help="Hedef kapsamı adı.")
    revoke.add_argument("--reason", required=True, help="Geri çekme gerekçesi.")

    plans = nmap_actions.add_parser(
        "plans", help="Nmap çalıştırmadan değiştirilemez tarama planı oluştur/göster.",
    )
    plan_actions = plans.add_subparsers(dest="nmap_plan_action", required=True)
    create = plan_actions.add_parser(
        "create", help="Hedef, port, hız ve bütçe sınırlarını donduran dry-run planı oluştur.",
    )
    create.add_argument("domain", help="Etkin dış yüzey kapsamındaki domain.")
    create.add_argument("--target", required=True, help="Etkin hedef kapsamı adı.")
    create.add_argument("--profile", choices=NMAP_PROFILES, default="safe")
    create.add_argument("--ports", help="Yalnız custom: 443,8443 veya 1-1024 biçimi.")
    create.add_argument("--timeout-seconds", type=int, default=300, help="Hedef başına 10–3600 sn.")
    create.add_argument("--max-rate", type=int, default=50, help="Port taraması hızı (1–1000 paket/sn); NSE için toplam kota değildir.")
    create.add_argument("--max-retries", type=int, default=1, help="Port başına 0–3 tekrar.")
    create.add_argument("--scan-delay-ms", type=int, default=0, help="Probelar arası 0–60000 ms.")
    create.add_argument("--max-parallelism", type=int, default=32, help="Azami eşzamanlı probe (1–256).")
    create.add_argument("--max-hostgroup", type=int, default=16, help="Kayıtlı host grubu sınırı; mevcut worker etkin 1 kullanır.")
    create.add_argument("--max-targets", type=int, default=16, help="Plan hedef sınırı (1–4096).")
    create.add_argument("--max-probes", type=int, default=100000, help="Yaklaşık port taraması bütçesi; ek servis/OS/NSE trafiği dahil değildir.")
    create.add_argument("--scan-type", choices=SCAN_TYPES, default="tcp_connect")
    create.add_argument("--service-detection", action="store_true", help="Servis ve sürüm sorguları gönder.")
    create.add_argument("--version-intensity", type=int, default=2, help="Sürüm sorgu yoğunluğu (0–9).")
    create.add_argument("--os-detection", action="store_true", help="Yetkili çalıştırıcıyla OS tahmini iste.")
    create.add_argument("--script", action="append", default=[], choices=tuple(SCRIPT_CATALOG), help="Açıkça seçilen NSE kontrolü; tekrarlanabilir.")
    create.add_argument("--script-timeout-seconds", type=int, default=30)
    create.add_argument("--max-duration-seconds", type=int, default=3600, help="Worker turunun toplam süresi (10–86400 sn).")
    create.add_argument(
        "--confirm-wide-scan", action="store_true",
        help="1024'ten fazla portu açıkça onayla.",
    )
    create.add_argument(
        "--confirm-range-scan", action="store_true",
        help="16'dan fazla hedef adresini açıkça onayla.",
    )
    plan_list = plan_actions.add_parser("list", help="Kaydedilmiş dry-run planlarını göster.")
    plan_list.add_argument("domain", help="Kayıtlı domain.")
    plan_list.add_argument("--limit", type=int, default=100, help="Sonuç sınırı (1–500).")
    plan_show = plan_actions.add_parser("show", help="Tek bir planın tüm dondurulmuş sınırlarını göster.")
    plan_show.add_argument("domain", help="Kayıtlı domain.")
    plan_show.add_argument("plan_id", help="Plan UUID kimliği.")


def _target_line(target) -> str:
    exclusions = ", ".join(safe_text(item) for item in target.definition.exclusions) or "yok"
    return (
        f"{safe_text(target.display_name)} | {'etkin' if target.active else 'geri çekildi'} | "
        f"{safe_text(target.definition.network)} | {target.definition.target_count} hedef | "
        f"hariç: {exclusions} | sürüm {target.revision}"
    )


def _plan_lines(plan) -> list[str]:
    value = plan.definition
    exclusions = ", ".join(
        safe_text(item) for item in value.target_definition.exclusions
    ) or "yok"
    return [
        "Yönetilen Nmap planı (plan oluşturmak ağ taraması yapmaz).",
        f"Plan: {safe_text(plan.id)}",
        f"SHA-256: {safe_text(plan.plan_sha256)}",
        f"Domain: {safe_text(plan.asset_value)} | hedef: {safe_text(plan.target_scope_name)} ",
        f"Hedef sürümü: {value.target_scope_revision} | "
        f"{safe_text(value.target_definition.network)} | hariç: {exclusions}",
        f"Gerçek hedef sayısı: {value.target_count} / izin verilen {value.max_targets}",
        f"Tarama türü: {safe_text(value.scan_type)} | host discovery: atlanır | profil: {safe_text(value.profile)}",
        f"Portlar: {safe_text(value.port_spec)} ({value.port_count} port)",
        f"Sınırlar: hedef başına {value.timeout_seconds} sn, "
        f"en fazla {value.max_rate_pps} paket/sn, {value.max_retries} tekrar, "
        f"{value.scan_delay_ms} ms gecikme",
        f"Paralellik: {value.max_parallelism} probe | kayıtlı host grubu: {value.max_hostgroup} | etkin: 1",
        f"Port taraması yaklaşık probe bütçesi: {value.probe_budget} / izin verilen {value.max_probe_budget}",
        f"Açık onaylar: geniş port={'evet' if value.wide_scan_confirmed else 'gerekmedi'}, "
        f"geniş hedef={'evet' if value.range_scan_confirmed else 'gerekmedi'}",
        f"Servis/sürüm: {(value.options or NmapExecutionOptions()).service_detection} | "
        f"OS tahmini: {(value.options or NmapExecutionOptions()).os_detection}",
        "NSE: " + (", ".join((value.options or NmapExecutionOptions()).scripts) or "seçilmedi"),
        "Hız/probe bütçesi servis, OS ve NSE trafiği için kesin paket kotası değildir.",
        "Çalıştırma: jobs submit ile kuyruğa ekle, jobs worker ile başlat.",
    ]


def execute_nmap_management_command(service: NmapManagementService, args):
    if args.nmap_action == "targets":
        if args.nmap_target_action == "save":
            mutation = service.save_target(
                args.domain, args.name, args.network, tuple(args.exclude), args.reason,
            )
            return asdict(mutation), [
                f"Nmap hedef kapsamı: {mutation.action}", _target_line(mutation.scope),
                f"Yetki gerekçesi: {safe_text(mutation.scope.authorization_reason)}",
                "Bu işlem ağ taraması yapmadı.",
            ]
        if args.nmap_target_action == "list":
            targets = service.list_targets(
                args.domain, active_only=not args.all, limit=args.limit,
            )
            return {"targets": [asdict(item) for item in targets]}, [
                f"Nmap hedef kapsamları ({len(targets)}):",
                *(_target_line(item) for item in targets),
            ]
        if args.nmap_target_action == "show":
            details = service.show_target(
                args.domain, args.name, event_limit=args.history_limit,
            )
            lines = [
                _target_line(details.scope),
                f"Yetki gerekçesi: {safe_text(details.scope.authorization_reason)}",
                f"Bağlı değiştirilemez plan: {details.plan_count}",
                f"Yaşam döngüsü olayı: {details.event_count}",
            ]
            lines.extend(
                f"  {safe_text(event.recorded_at)} | {safe_text(event.action)} | "
                f"sürüm {event.revision} | {safe_text(event.reason)}"
                for event in details.events
            )
            return asdict(details), lines
        mutation = service.revoke_target(args.domain, args.name, args.reason)
        return asdict(mutation), [
            f"Nmap hedef kapsamı: {mutation.action}", _target_line(mutation.scope),
            "Geçmiş ve daha önce oluşturulan planlar korundu.",
        ]
    if args.nmap_plan_action == "create":
        mutation = service.create_plan(
            args.domain, args.target,
            profile=args.profile, ports=args.ports,
            timeout_seconds=args.timeout_seconds, max_rate_pps=args.max_rate,
            max_retries=args.max_retries, scan_delay_ms=args.scan_delay_ms,
            max_parallelism=args.max_parallelism, max_hostgroup=args.max_hostgroup,
            max_targets=args.max_targets, max_probe_budget=args.max_probes,
            confirm_wide_scan=args.confirm_wide_scan,
            confirm_range_scan=args.confirm_range_scan,
            scan_type=args.scan_type,
            options=NmapExecutionOptions(args.service_detection, args.version_intensity,
                args.os_detection, tuple(args.script), args.script_timeout_seconds, args.max_duration_seconds),
        )
        return asdict(mutation), [f"Plan kaydı: {mutation.action}", *_plan_lines(mutation.plan)]
    if args.nmap_plan_action == "list":
        plans = service.list_plans(args.domain, limit=args.limit)
        return {"plans": [asdict(item) for item in plans]}, [
            f"Yönetilen Nmap planları ({len(plans)}):",
            *(
                f"{safe_text(plan.id)} | {safe_text(plan.target_scope_name)} | "
                f"{plan.definition.target_count} hedef × {plan.definition.port_count} port | "
                f"{plan.definition.probe_budget} probe"
                for plan in plans
            ),
        ]
    plan = service.show_plan(args.domain, args.plan_id)
    return asdict(plan), _plan_lines(plan)
