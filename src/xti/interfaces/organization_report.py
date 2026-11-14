"""Safe, source-preserving terminal navigation for an organization report."""

from argparse import _SubParsersAction
from dataclasses import asdict
import shlex

from xti.application.organization_report import OrganizationReportService
from xti.domain.organization_report import OrganizationReport, OrganizationReportAttempt, ReportNavigation
from xti.interfaces.cname import check_lines as cname_lines
from xti.interfaces.mail import check_lines as mail_lines
from xti.interfaces.services import check_lines as service_lines
from xti.interfaces.surface import check_lines as web_lines
from xti.interfaces.text import safe_text


_SECTIONS = {"findings": "Domain/marka bulguları", "surface_candidates": "Pasif alt alan adı adayları",
             "profiles": "Sosyal profil sonuçları", "claims": "Kaynak iddiaları",
             "public_notices": "Kamu olay kataloğu tam domain eşleşmeleri",
             "notifications": "Yerel bildirimler", "case_links": "Açık vaka bağlantıları"}
_FRESHNESS = {"never": "başarılı kayıt yok", "current": "güncel", "stale": "eski", "clock_error": "gelecek zamanlı kayıt"}


def register_organization_report_parser(actions: _SubParsersAction) -> None:
    parser = actions.add_parser("report", help="Kuruluşun açıkça bağlı kayıtlı kanıtlarını birleştir; ağa çıkmaz.")
    parser.add_argument("organization_id")
    parser.add_argument("--target-offset", type=int, default=0)
    parser.add_argument("--target-limit", type=int, default=50)
    parser.add_argument("--item-offset", type=int, default=0)
    parser.add_argument("--item-limit", type=int, default=50)
    parser.add_argument("--stale-after-hours", type=int, default=24)


def _command(navigation: ReportNavigation, indent: str = "    ") -> str:
    # This is printable navigation only. No shell command is executed.
    return f"{indent}{safe_text(navigation.label)}: {safe_text(shlex.join(('./xti', *navigation.arguments)))}"


def _attempt(label: str, attempt: OrganizationReportAttempt | None) -> str:
    if attempt is None:
        return f"      {label}: kayıt yok"
    value = f"      {label}: {safe_text(attempt.status)} | {safe_text(attempt.recorded_at)} | {safe_text(attempt.id)}"
    if attempt.definition_matches_current is not None:
        value += f" | güncel tanım: {'evet' if attempt.definition_matches_current else 'hayır'}"
    if attempt.is_baseline is not None:
        value += f" | {'ilk karşılaştırma tabanı' if attempt.is_baseline else 'devam çalışması'}"
    if attempt.source_run_id:
        value += f" | kaynak çalışma: {safe_text(attempt.source_run_id)}"
    if attempt.error:
        value += f" | hata: {safe_text(attempt.error)}"
    return value


def organization_report_lines(report: OrganizationReport) -> list[str]:
    organization = report.scope.organization
    lines = [
        f"Kuruluş birleşik raporu: {safe_text(organization.display_name)} | {safe_text(organization.id)}",
        f"Rapor zamanı: {safe_text(report.observed_at)} | yalnız kayıtlı veri",
        f"Kuruluş: {'etkin' if organization.active else 'geri çekilmiş'} | "
        f"etkin hedef: {report.total_target_count} | etkin olmayan bağlantı: {report.scope.excluded_link_count}",
        f"Gösterilen hedef: {len(report.targets)} | başlangıç: {report.target_offset} | sınır: {report.target_limit}",
    ]
    if report.scope.excluded_link_count:
        lines.append(_command(ReportNavigation("Etkin olmayan bağlantılar ve hedef durumları",
                                               ("organizations", "show", organization.id)), ""))
    for target in report.targets:
        view = target.membership
        lines.extend(("", f"{safe_text(view.target.display_name)} | {safe_text(view.link.target.kind)} | {safe_text(view.link.target.value)}",
                      f"  Açık bağlantı kimliği: {safe_text(view.link.id)} | kaynak: {safe_text(view.target.source)}"))
        for label, value in target.current_definition:
            lines.append(f"  {safe_text(label)}: {safe_text(value)}")
        lines.append("  Kaynak ve kanıt güncelliği:")
        for item in target.coverage:
            lines.extend((f"    {safe_text(item.family)}/{safe_text(item.source)} | {_FRESHNESS[item.freshness]}",
                          _attempt("Son deneme", item.latest_attempt), _attempt("Son başarı", item.latest_success)))
            lines.extend(f"      {safe_text(note)}" for note in item.notes)
        if target.surface is not None:
            scope = target.surface.scope
            lines.append(f"  Aktif kontrol izni: {'etkin' if scope and scope.active else 'geri çekilmiş' if scope else 'kayıt yok'}")
            for label, check, render in (
                ("Web/DNS/TLS", target.surface.latest_check, web_lines),
                ("E-posta DNS", target.surface.latest_mail_check, mail_lines),
                ("Servis", target.surface.latest_service_check, service_lines),
                ("CNAME", target.surface.latest_cname_check, cname_lines),
            ):
                lines.append(f"  {label} kanıtı: {safe_text(check.id) if check else 'kontrol kaydı yok'}")
                if check is not None:
                    lines.extend(render(check, indent="    "))
        for section in target.sections:
            lines.append(f"  {_SECTIONS[section.kind]}: toplam {section.total_count} | bu sayfa {len(section.items)} | başlangıç {section.offset}")
            for record in section.items:
                lines.append(f"    {safe_text(record.value)} | {safe_text(record.status)} | {safe_text(record.source)}")
                lines.append(f"      Kimlik: {safe_text(record.id)} | zaman: {safe_text(record.recorded_at)}")
                lines.extend(f"      {safe_text(detail)}" for detail in record.details)
                for label, value in (("Çalışma", record.run_id), ("Kaynak çalışma", record.source_run_id), ("Tanım özeti", record.definition_sha256)):
                    if value is not None:
                        lines.append(f"      {label}: {safe_text(value)}")
                lines.extend(_command(link, "      ") for link in record.navigation)
            if section.has_more:
                lines.append(f"    Bu bölümün devamı: --item-offset {section.offset + len(section.items)} --item-limit {section.limit}")
        lines.extend(_command(link) for link in target.navigation)
        lines.extend(f"  Not: {safe_text(note)}" for note in target.notes)
    if report.has_more_targets:
        lines.append(f"Sonraki hedef sayfası: --target-offset {report.target_offset + len(report.targets)} --target-limit {report.target_limit}")
    lines.extend(f"Not: {safe_text(note)}" for note in report.notes)
    return lines


def execute_organization_report_command(service: OrganizationReportService, args) -> tuple[dict, list[str]]:
    result = service.show(args.organization_id, target_offset=args.target_offset, target_limit=args.target_limit,
                          item_offset=args.item_offset, item_limit=args.item_limit,
                          stale_after_hours=args.stale_after_hours)
    return asdict(result), organization_report_lines(result)
