"""Explicit organization grouping commands and safe terminal rendering."""

from dataclasses import asdict

from xti.application.organizations import OrganizationService
from xti.domain.organizations import ORGANIZATION_TARGET_KINDS, organization_link_effective
from xti.interfaces.text import safe_text
from xti.interfaces.organization_report import register_organization_report_parser

_ACTIONS = {"added": "Kaydedildi", "renamed": "Ad değişti", "reactivated": "Yeniden etkin",
            "revoked": "Geri çekildi", "unchanged": "Değişmedi", "linked": "Bağlandı", "updated": "Güncellendi"}
_KINDS = {"domain": "Domain", "username-watch": "Sosyal izleme",
          "ransomware-watch": "ThreatCluster izlemesi", "ransomlook-watch": "RansomLook izlemesi"}


def register_organizations_parser(commands) -> None:
    parser = commands.add_parser("organizations", help="Domain ve izlemeleri açık seçimle kuruluş altında grupla.")
    actions = parser.add_subparsers(dest="organization_action", required=True)
    register_organization_report_parser(actions)
    add = actions.add_parser("add", help="Yerel kuruluş grubu oluştur; veri toplamaz.")
    add.add_argument("name")
    add.add_argument("--reason", default="Terminalden kuruluş grubu oluşturuldu.", help="İsteğe bağlı açıklama.")
    listing = actions.add_parser("list", help="Kayıtlı kuruluş gruplarını listele.")
    listing.add_argument("--all", action="store_true", dest="all_entries")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=100)
    show = actions.add_parser("show", help="Kuruluş bağlantılarını ve değişiklik geçmişini göster.")
    show.add_argument("organization_id")
    show.add_argument("--active-links", action="store_true")
    show.add_argument("--offset", type=int, default=0)
    show.add_argument("--limit", type=int, default=100)
    show.add_argument("--event-limit", type=int, default=50)
    rename = actions.add_parser("rename", help="Kuruluşun kimliğini koruyarak adını değiştir.")
    rename.add_argument("organization_id")
    rename.add_argument("name")
    rename.add_argument("--reason", required=True)
    for operation, help_text in (("revoke", "Kuruluş grubunu kaydı silmeden kapat."), ("reactivate", "Kuruluş grubunu yeniden etkinleştir.")):
        command = actions.add_parser(operation, help=help_text)
        command.add_argument("organization_id")
        command.add_argument("--reason", required=True)
    link = actions.add_parser("link", help="Mevcut domain veya izlemeyi açık seçimle bağla.")
    link.add_argument("organization_id")
    link.add_argument("--kind", choices=ORGANIZATION_TARGET_KINDS, required=True)
    link.add_argument("--value", required=True, help="Domain veya kayıtlı izleme kimliği.")
    link.add_argument("--reason", default="Kullanıcının açık kuruluş gruplaması.", help="İsteğe bağlı açıklama.")
    unlink = actions.add_parser("unlink", help="Bağlantıyı geçmişini koruyarak geri çek.")
    unlink.add_argument("organization_id")
    unlink.add_argument("link_id")
    unlink.add_argument("--reason", required=True)
    detail = actions.add_parser("link-show", help="Tek bağlantının geçmişini göster.")
    detail.add_argument("organization_id")
    detail.add_argument("link_id")
    detail.add_argument("--event-limit", type=int, default=50)


def execute_organization_command(service: OrganizationService, args) -> tuple[dict, list[str]]:
    action = args.organization_action
    if action == "list":
        result = service.list(active_only=not args.all_entries, offset=args.offset, limit=args.limit)
        lines = [f"Kayıtlı kuruluş grubu: {result.total_count}"]
        for item in result.organizations:
            lines.append(f"  {safe_text(item.display_name)} | {safe_text(item.id)} | {'etkin' if item.active else 'geri çekilmiş'}")
        if result.offset + len(result.organizations) < result.total_count:
            lines.append(f"Sonraki sayfa: --offset {result.offset + len(result.organizations)}")
    elif action == "show":
        result = service.show(args.organization_id, active_links_only=args.active_links, link_offset=args.offset, link_limit=args.limit, event_limit=args.event_limit)
        org = result.organization
        lines = [f"Kuruluş: {safe_text(org.display_name)} | {safe_text(org.id)}", f"Durum: {'Etkin' if org.active else 'Geri çekilmiş'} | sürüm {org.revision}", f"Bağlantı sayısı: {result.total_link_count}"]
        for view in result.links:
            link, target = view.link, view.target
            lines.extend([
                f"  {_KINDS[link.target.kind]}: {safe_text(target.display_name)} | {safe_text(link.target.value)}",
                f"    Bağlantı: {safe_text(link.id)} | kaynak: {safe_text(target.source)}",
                f"    Grup içinde etkin: {'evet' if organization_link_effective(org, view) else 'hayır'} | bağlantı etkin: {'evet' if link.active else 'hayır'} | hedef etkin: {'evet' if target.active else 'hayır'}",
            ])
        if result.link_offset + len(result.links) < result.total_link_count:
            lines.append(f"Daha fazla bağlantı var; --offset {result.link_offset + len(result.links)}")
        lines.append(f"Kuruluş geçmişi: {result.total_event_count}")
        for event in result.events:
            lines.append(f"  {safe_text(event.recorded_at)} | {_ACTIONS[event.action]} | {safe_text(event.reason)}")
        if result.total_event_count > len(result.events):
            lines.append("Eski değişikliklerin bir bölümü görünüm sınırı dışında.")
    elif action == "link-show":
        result = service.show_link(args.organization_id, args.link_id, event_limit=args.event_limit)
        lines = [f"Bağlantı: {safe_text(result.view.link.id)}", f"Hedef: {safe_text(result.view.link.target.value)}", f"Kayıtlı değişiklik: {result.total_event_count}"]
        for event in result.events:
            lines.append(f"  {safe_text(event.recorded_at)} | {_ACTIONS[event.action]} | {safe_text(event.reason)}")
        if result.total_event_count > len(result.events):
            lines.append("Eski değişikliklerin bir bölümü görünüm sınırı dışında.")
    elif action in {"link", "unlink"}:
        if action == "link":
            result = service.link(args.organization_id, kind=args.kind, value=args.value, reason=args.reason)
        else:
            result = service.unlink(args.organization_id, args.link_id, reason=args.reason)
        lines = [f"Bağlantı: {_ACTIONS[result.action]}", f"Kimlik: {safe_text(result.link.id)}", f"Hedef: {safe_text(result.link.target.value)}"]
    else:
        if action == "add":
            result = service.add(args.name, reason=args.reason)
        elif action == "rename":
            result = service.rename(args.organization_id, args.name, reason=args.reason)
        else:
            result = getattr(service, action)(args.organization_id, reason=args.reason)
        lines = [f"Kuruluş: {_ACTIONS[result.action]}", f"{safe_text(result.organization.display_name)} | {safe_text(result.organization.id)}"]
    lines.append("Bu gruplama kullanıcı seçimidir; sahiplik/taklit/ihlal doğrulaması veya yeni izleme başlatma değildir.")
    return asdict(result), lines
