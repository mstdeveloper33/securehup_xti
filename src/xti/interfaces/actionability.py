"""Terminal adapter for P06 reports, runbooks and human-approved takedown."""

from dataclasses import asdict
from pathlib import Path

from xti.adapters.case_package_files import AtomicCasePackagePublisher
from xti.adapters.sqlite_actionability import SQLiteActionabilityRepository
from xti.adapters.sqlite_case_packages import SQLiteCasePackageReader
from xti.application.actionability import ActionabilityService
from xti.application.case_packages import CasePackageService
from xti.interfaces.text import safe_text


def register_actionability_parser(commands) -> None:
    parser = commands.add_parser(
        "action", help="Vaka raporu, runbook ve insan onaylı takedown iş akışlarını yönet.",
    )
    actions = parser.add_subparsers(dest="action_action", required=True)
    actions.add_parser("capabilities", help="P06 güvenlik sınırlarını ve kullanılabilir işlemleri göster.")
    plan = actions.add_parser("runbook-plan", help="Vaka kanıtından yazmasız, sürümlü savunma planı üret.")
    plan.add_argument("case_id")
    apply = actions.add_parser("runbook-apply", help="Görülen planı atomik ve tekrar güvenli vaka görevlerine dönüştür.")
    apply.add_argument("case_id")
    apply.add_argument("--expected-plan-sha256", required=True)
    apply.add_argument("--idempotency-key", required=True)
    apply.add_argument("--reason", required=True)
    show = actions.add_parser("runbook-show", help="Uygulanmış runbook makbuzunu ağsız göster.")
    show.add_argument("runbook_id")
    package = actions.add_parser("package-create", help="Yeni, doğrulanabilir vaka kanıt paketi dizini oluştur.")
    package.add_argument("case_id")
    package.add_argument("destination", type=Path)
    package.add_argument("--pdf", action="store_true", help="Sabit çevrimdışı Chromium ile yönetici PDF'i de üret.")
    verify = actions.add_parser("package-verify", help="Paket manifestini ve her dosyanın SHA-256 bütünlüğünü doğrula.")
    verify.add_argument("destination", type=Path)
    create = actions.add_parser("takedown-create", help="Etkin vaka kanıtından gönderilmeyen takedown taslağı oluştur.")
    create.add_argument("case_id"); create.add_argument("evidence_link_id")
    create.add_argument("--target-kind", choices=(
        "domain_hosting", "registrar", "social_platform", "app_store",
        "code_host", "search_engine",
    ))
    create.add_argument("--target")
    routing = create.add_mutually_exclusive_group(required=True)
    routing.add_argument("--recipient")
    routing.add_argument("--contact-candidate-id")
    create.add_argument("--requested-action", required=True)
    create.add_argument("--grounds", required=True)
    create.add_argument("--actor", required=True)
    create.add_argument("--idempotency-key", required=True)
    listing = actions.add_parser("takedown-list", help="Takedown kayıtlarını sayfalı ve ağsız listele.")
    listing.add_argument("--case-id")
    listing.add_argument("--state", choices=(
        "draft", "approved", "submitted", "acknowledged", "resolved", "rejected", "cancelled",
    ))
    listing.add_argument("--offset", type=int, default=0); listing.add_argument("--limit", type=int, default=50)
    details = actions.add_parser("takedown-show", help="Taslak, onay ve durum olay zincirini göster.")
    details.add_argument("request_id")
    for command, action, help_text, reference in (
        ("takedown-approve", "approve", "Taslağı yetkili insan kararıyla onayla.", False),
        ("takedown-submit", "submit", "Dışarıda yapılan başvuruyu referansıyla kaydet; motor göndermez.", True),
        ("takedown-acknowledge", "acknowledge", "Sağlayıcı alındı bilgisini kaydet.", False),
        ("takedown-resolve", "resolve", "Kapatma sonucunu insan kanıtıyla çözüldü işaretle.", False),
        ("takedown-reject", "reject", "Başvurunun reddedildiğini kaydet.", False),
        ("takedown-cancel", "cancel", "Taslak veya onaylı işlemi iptal et.", False),
    ):
        item = actions.add_parser(command, help=help_text)
        item.set_defaults(transition_action=action)
        item.add_argument("request_id"); item.add_argument("--expected-revision", type=int, required=True)
        item.add_argument("--actor", required=True); item.add_argument("--reason", required=True)
        item.add_argument("--external-reference", required=reference)
    from xti.interfaces.abuse_contacts import register_abuse_contact_parsers
    register_abuse_contact_parsers(actions)


class _ActionabilityBoundary:
    def __init__(self, database: Path) -> None:
        self.legacy = ActionabilityService(SQLiteActionabilityRepository(database))
        from xti.interfaces.abuse_contacts import make_abuse_contact_service
        self.contacts = make_abuse_contact_service(database)

    def execute(self, operation: str, **options):
        if operation.startswith("action.contact."):
            return self.contacts.execute(operation, **options)
        return self.legacy.execute(operation, **options)

    def __getattr__(self, name):
        return getattr(self.legacy, name)


def _service(database: Path) -> _ActionabilityBoundary:
    return _ActionabilityBoundary(database)


def _runbook_lines(data: dict, *, plan: bool) -> list[str]:
    lines = ["Savunma runbook planı" if plan else "Runbook uygulama makbuzu"]
    lines.append(f"Vaka: {safe_text(data['case_id'])}")
    lines.append(f"Plan SHA-256: {safe_text(data['plan_sha256'])}")
    if plan:
        lines.append(f"Şablon: {safe_text(data['template_id'])} v{data['template_version']}")
        for index, step in enumerate(data["steps"], 1):
            lines.append(f"  {index}. {safe_text(step['title'])}")
        lines.extend(data["limitations"])
        lines.append("Uygulamak için bu plan SHA-256 değerini --expected-plan-sha256 ile verin.")
    else:
        lines.append(f"Runbook: {safe_text(data['id'])} | görev: {len(data['created_task_ids'])}")
        lines.append("Tekrar oynatıldı; yeni görev oluşmadı." if data["replayed"] else "Vaka görevleri atomik oluşturuldu.")
    return lines


def _takedown_lines(data: dict) -> list[str]:
    record = data["request"] if "request" in data else data
    lines = [
        "İnsan onaylı takedown kaydı",
        f"Kimlik: {safe_text(record['id'])} | durum: {safe_text(record['state'])} | sürüm: {record['revision']}",
        f"Vaka: {safe_text(record['case_id'])} | kanıt: {safe_text(record['evidence_link_id'])}",
        f"Hedef: {safe_text(record['target_kind'])} · {safe_text(record['target_value'])}",
        f"Alıcı: {safe_text(record['recipient'])}",
        "Motor bu taslağı veya başvuruyu otomatik göndermez.",
    ]
    if "events" in data:
        lines.append(f"Olay zinciri: {len(data['events'])}")
    return lines


def execute_actionability(database: Path, args) -> tuple[dict, list[str]]:
    if getattr(args, "contact_operation", None) is not None:
        from xti.interfaces.abuse_contacts import execute_abuse_contacts
        return execute_abuse_contacts(database, args)
    if args.action_action == "capabilities":
        data = {
            "contract_version": 1,
            "case_package": {"html": True, "technical_json": True, "csv": True, "offline_pdf": True},
            "runbook": {"versioned": True, "idempotent_apply": True},
            "takedown": {"human_approval_required": True, "automatic_submission": False,
                         "reviewed_abuse_contact_binding": True},
            "abuse_contact_discovery": {"domain_rdap": True, "ip_rdap": True,
                                         "security_txt_auxiliary": True,
                                         "whois_fallback_optional": True},
            "bulk_ioc": {"preview": True, "atomic_import": True, "formats": ["csv", "json", "stix"]},
            "external_connectors": False,
        }
        return data, [
            "P06 aksiyon paketi hazır.",
            "Kanıt paketi: HTML + teknik JSON + CSV; doğrulanmış yerel araçla isteğe bağlı PDF.",
            "Runbook: sürümlü plan ve tekrar güvenli görev uygulaması.",
            "Takedown: insan onaylı kayıt; otomatik dış gönderim yok.",
            "Abuse iletişimi: RDAP ana kaynak, security.txt yardımcı, WHOIS isteğe bağlı fallback; aday ayrıca onaylanır.",
            "Toplu IOC: kesin CSV/JSON/STIX önizleme, atomik import ve yeni dosyaya export.",
            "Harici SIEM/SOAR/ticket bağlantıları kullanıcı kararıyla bu pakete dahil edilmedi.",
        ]
    if args.action_action in {"package-create", "package-verify"}:
        service = CasePackageService(
            SQLiteCasePackageReader(database), AtomicCasePackagePublisher(),
        )
        artifact = (
            service.create(args.case_id, args.destination, include_pdf=args.pdf)
            if args.action_action == "package-create" else service.verify(args.destination)
        )
        data = asdict(artifact)
        return data, [
            "Vaka kanıt paketi oluşturuldu." if args.action_action == "package-create" else "Vaka kanıt paketi doğrulandı.",
            f"Konum: {safe_text(artifact.destination)}",
            f"Vaka görünümü: {safe_text(artifact.case_snapshot_sha256)}",
            f"Manifest: {safe_text(artifact.manifest_sha256)}",
        ]
    service = _service(database)
    if args.action_action == "runbook-plan":
        data = asdict(service.runbook_plan(args.case_id))
        return data, _runbook_lines(data, plan=True)
    if args.action_action == "runbook-apply":
        data = asdict(service.runbook_apply(
            args.case_id, expected_plan_sha256=args.expected_plan_sha256,
            idempotency_key=args.idempotency_key, reason=args.reason,
        ))
        return data, _runbook_lines(data, plan=False)
    if args.action_action == "runbook-show":
        data = asdict(service.runbook_show(args.runbook_id))
        return data, _runbook_lines(data, plan=False)
    if args.action_action == "takedown-create":
        details = service.takedown_create(
            args.case_id, args.evidence_link_id, target_kind=args.target_kind,
            target_value=args.target, recipient=args.recipient,
            contact_candidate_id=args.contact_candidate_id,
            requested_action=args.requested_action, grounds=args.grounds,
            idempotency_key=args.idempotency_key, actor=args.actor,
        )
        data = asdict(details); return data, _takedown_lines(data)
    if args.action_action == "takedown-list":
        records = service.takedown_list(
            case_id=args.case_id, state=args.state, offset=args.offset, limit=args.limit,
        )
        data = {"records": [asdict(item) for item in records], "offset": args.offset, "limit": args.limit}
        lines = [f"Takedown kayıtları ({len(records)}):"] + [
            f"  {safe_text(item.id)} | {safe_text(item.state)} | {safe_text(item.target_kind)} | {safe_text(item.target_value)}"
            for item in records
        ]
        return data, lines
    if args.action_action == "takedown-show":
        data = asdict(service.takedown_show(args.request_id)); return data, _takedown_lines(data)
    details = service.takedown_transition(
        args.request_id, action=args.transition_action,
        expected_revision=args.expected_revision, actor=args.actor,
        reason=args.reason, external_reference=args.external_reference,
    )
    data = asdict(details); return data, _takedown_lines(data)
