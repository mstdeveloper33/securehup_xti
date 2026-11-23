"""Safe, source-preserving terminal navigation for an organization report."""

from argparse import _SubParsersAction
from dataclasses import asdict

from xti.application.organization_report import OrganizationReportService
from xti.application.organization_export import OrganizationExportService
from xti.domain.organization_report import OrganizationReport, OrganizationReportAttempt, ReportNavigation
from xti.interfaces.cname import check_lines as cname_lines
from xti.interfaces.mail import check_lines as mail_lines
from xti.interfaces.services import check_lines as service_lines
from xti.interfaces.surface import check_lines as web_lines
from xti.interfaces.text import safe_text
from xti.interfaces.text import xti_command
from xti.interfaces.evidence_status import coverage_status_text
from xti.interfaces.public_notice_watches import watch_detail_lines


_SECTIONS = {
    "brand_protection": "Marka/sayfa/sosyal/uygulama taklidi adayları",
    "monitored_content": "Firma/tedarikçi yayın ve kanal içerikleri",
    "code_exposures": "Kod deposu/paste adayları","findings": "Domain/marka bulguları", "surface_candidates": "Pasif alt alan adı adayları",
             "research_groups": "Kayıtlı inceleme grupları",
             "profiles": "Sosyal profil sonuçları", "claims": "Kaynak iddiaları",
             "public_notices": "Kamu olay kataloğu tam domain eşleşmeleri",
             "notifications": "Yerel bildirimler", "case_links": "Açık vaka bağlantıları",
             "content": "Güncel kapsamın içerik adayları", "historical_content": "Tarihî kapsamın içerik adayları"}
CONTENT_SCOPE_LABELS = {"current": "Güncel kapsam", "old_definition": "Eski isim/domain kapsamı",
    "old_request": "Eski arama konusu/sonuç sınırı",
    "inactive_organization": "Kuruluş geri çekilmiş", "inactive_target": "Tedarikçi etkin değil",
    "inactive_relationship": "Etkin açık tedarikçi ilişkisi kalmamış"}
_CONTENT_STATUSES = {"source_candidate": "arama adayı", "retained_candidate": "önceki aramadan korunan aday",
                     "historical_candidate": "tarihî kapsamın adayı"}


def register_organization_report_parser(actions: _SubParsersAction) -> None:
    from xti.interfaces.company_content import register_company_content_parser
    register_company_content_parser(actions)
    parser = actions.add_parser("report", help="Kuruluşun açıkça bağlı kayıtlı kanıtlarını birleştir; ağa çıkmaz.")
    parser.add_argument("organization_id")
    parser.add_argument("--target-offset", type=int, default=0)
    parser.add_argument("--target-limit", type=int, default=50)
    parser.add_argument("--item-offset", type=int, default=0)
    parser.add_argument("--item-limit", type=int, default=50)
    parser.add_argument("--stale-after-hours", type=int, default=24)
    parser.add_argument("--summary", action="store_true", help="Kapsam/hatalar ve bölüm başına ilk üç kaydı göster. JSON ve HTML dışa aktarma kapsamı değişmez.")
    export = actions.add_parser("export", help="Kuruluş raporunun tamamını ağsız, yeni bir HTML dosyasına yaz.")
    export.add_argument("organization_id")
    export.add_argument("--output", required=True, help="Yeni .html dosyası; mevcut dosyanın üzerine yazılmaz.")
    export.add_argument("--stale-after-hours", type=int, default=24)


def _command(navigation: ReportNavigation, indent: str = "    ", *, data_dir=None) -> str:
    # This is printable navigation only. No shell command is executed.
    return f"{indent}{safe_text(navigation.label)}: {xti_command(*navigation.arguments, data_dir=data_dir)}"


def _attempt(label: str, attempt: OrganizationReportAttempt | None) -> str:
    if attempt is None:
        return f"      {label}: kayıt yok"
    status = "başarılı, boş sonuç" if attempt.status == "empty" else attempt.status
    value = f"      {label}: {safe_text(status)} | {safe_text(attempt.recorded_at)} | {safe_text(attempt.id)}"
    if attempt.definition_matches_current is not None:
        value += f" | güncel tanım: {'evet' if attempt.definition_matches_current else 'hayır'}"
    if attempt.is_baseline is not None:
        value += f" | {'ilk karşılaştırma tabanı' if attempt.is_baseline else 'devam çalışması'}"
    if attempt.source_run_id:
        value += f" | kaynak çalışma: {safe_text(attempt.source_run_id)}"
    if attempt.error:
        value += f" | hata: {safe_text(attempt.error)}"
    return value


def organization_report_lines(report: OrganizationReport, *, summary=False, data_dir=None) -> list[str]:
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
                                               ("organizations", "show", organization.id)), "", data_dir=data_dir))
    if summary:
        lines.append("Kısa görünüm: bölüm başına bu sayfanın ilk üç kaydı; sayılar birbirine eklenmez.")
    for target in report.targets:
        view = target.membership
        lines.extend(("", f"{safe_text(view.target.display_name)} | {safe_text(view.link.target.kind)} | {safe_text(view.link.target.value)}",
                      f"  Açık bağlantı kimliği: {safe_text(view.link.id)} | kaynak: {safe_text(view.target.source)}"))
        for label, value in target.current_definition:
            lines.append(f"  {safe_text(label)}: {safe_text(value)}")
        lines.append("  Kaynak ve kanıt güncelliği:")
        for item in target.coverage:
            lines.append(f"    {safe_text(item.family)}/{safe_text(item.source)} | {coverage_status_text(item)}")
            if not summary:
                lines.extend((_attempt("Son deneme", item.latest_attempt), _attempt("Son başarı", item.latest_success)))
            elif item.latest_attempt and item.latest_attempt.error:
                lines.append("      Hata: " + safe_text(item.latest_attempt.error))
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
                    if summary:
                        lines.extend("    Hata: " + safe_text(error) for error in check.result.errors)
                    else:
                        lines.extend(render(check, indent="    "))
        for section in target.sections:
            lines.append(f"  {_SECTIONS[section.kind]}: toplam {section.total_count} | bu sayfa {len(section.items)} | başlangıç {section.offset}")
            shown = section.items[:3] if summary else section.items
            for record in shown:
                lines.append(f"    {safe_text(record.value)} | {safe_text(record.status)} | {safe_text(record.source)}")
                if summary:
                    lines.append("      Kimlik: " + safe_text(record.id))
                    continue
                lines.append(f"      Kimlik: {safe_text(record.id)} | zaman: {safe_text(record.recorded_at)}")
                lines.extend(f"      {safe_text(detail)}" for detail in record.details)
                for label, value in (("Çalışma", record.run_id), ("Kaynak çalışma", record.source_run_id), ("Tanım özeti", record.definition_sha256)):
                    if value is not None:
                        lines.append(f"      {label}: {safe_text(value)}")
                lines.extend(_command(link, "      ", data_dir=data_dir) for link in record.navigation)
            if summary and section.total_count > len(shown):
                lines.append(f"    Bu özette yer almayan: {section.total_count - len(shown)} kayıt; aşağıdaki tam ayrıntı komutunu kullan.")
            if section.has_more:
                lines.append(f"    Bu bölümün devamı: --item-offset {section.offset + len(section.items)} --item-limit {section.limit}")
        lines.extend(_command(link, data_dir=data_dir) for link in target.navigation)
        lines.extend(f"  Not: {safe_text(note)}" for note in target.notes)
    if report.has_more_targets:
        lines.append(f"Sonraki hedef sayfası: --target-offset {report.target_offset + len(report.targets)} --target-limit {report.target_limit}")
    lines.append("")
    if report.public_notice_watch is not None:
        lines.append("Kuruluşa ait kamu olay izleme geçmişi (çalışma anındaki kapsam):")
        if summary:
            watch = report.public_notice_watch
            lines.append(f"  İzleme çalışması: {watch.total_run_count}; geçmiş aşağıdaki tam ayrıntı komutunda bulunur.")
            if watch.latest_source_run is not None:
                lines.append("  Son kaynak denemesi: " + safe_text(watch.latest_source_run.status))
                if watch.latest_source_run.error:
                    lines.append("  Hata: " + safe_text(watch.latest_source_run.error))
            lines.extend("  " + safe_text(note) for note in watch.notes)
            lines.extend(("  " + safe_text(watch.attribution), "  " + safe_text(watch.license)))
        else:
            lines.extend(watch_detail_lines(report.public_notice_watch))
        lines.append("Bu tarihî bölümün kapsamı, yukarıdaki güncel domain bölümlerinden ayrıdır.")
    else:
        lines.append("Bu kuruluş için kamu olay izlemesi açılmamış.")
        lines.append("Açmak için: " + xti_command("notices", "watch", "enable", organization.id, data_dir=data_dir))
    if report.public_notice_case_links is not None:
        page = report.public_notice_case_links
        lines.append(f"Kamu olay vaka bağlantıları: toplam {page.total_count} | bu sayfa {len(page.items)}")
        shown = page.items[:3] if summary else page.items
        for record in shown:
            lines.append(f"  {safe_text(record.value)} | {safe_text(record.status)} | {safe_text(record.id)}")
            if not summary:
                lines.extend(f"    {safe_text(detail)}" for detail in record.details)
                lines.extend(_command(link, data_dir=data_dir) for link in record.navigation)
        if summary and page.total_count > len(shown):
            lines.append(f"  Bu özette yer almayan vaka bağlantısı: {page.total_count - len(shown)}")
        if page.has_more:
            lines.append(f"Kamu olay vaka bağlantılarının devamı: --item-offset {page.offset + len(page.items)} --item-limit {page.limit}")
    if report.content is not None:
        lines.extend(content_lines(report.content, summary=summary, data_dir=data_dir))
    if summary:
        lines.append("Bu sayfanın tam ayrıntısı: " + xti_command(
            "organizations", "report", organization.id,
            "--target-offset", str(report.target_offset), "--target-limit", str(report.target_limit),
            "--item-offset", str(report.item_offset), "--item-limit", str(report.item_limit),
            "--stale-after-hours", str(report.stale_after_hours), data_dir=data_dir,
        ))
    lines.extend(f"Not: {safe_text(note)}" for note in report.notes)
    return lines


def content_lines(content, *, summary=False, data_dir=None) -> list[str]:
    lines = ["", "Firma ve tedarikçi içerikleri (Tavily, kayıtlı veri):",
             f"İstek kapsamı: toplam {content.total_scope_count} | bu sayfa {len(content.scopes)} | başlangıç {content.scope_offset}"]
    for item in content.scopes:
        target, coverage = item.target, item.coverage
        lines.extend((f"  {safe_text(target.name)} | {safe_text(target.kind)} | {safe_text(target.id)}",
                      "    " + CONTENT_SCOPE_LABELS[item.scope_status],
                      f"    Aramadaki domainler: {safe_text(', '.join(target.domains) or 'yok')}",
                      f"    Güncel açık grup kimlikleri: {safe_text(', '.join(item.current_group_ids) or 'yok')}",
                      f"    Kaynak durumu: {coverage_status_text(coverage)}",
                      _attempt("Son deneme", coverage.latest_attempt), _attempt("Son başarı", coverage.latest_success)))
        if item.request is not None:
            lines.append(f"    Konu: {safe_text(item.request.topic)} | sonuç sınırı: {item.request.max_results} | istek özeti: {safe_text(item.request_key)}")
        lines.append(f"    Son başarılı arama sonucu: {item.latest_success_result_count if item.latest_success_result_count is not None else 'başarılı kayıt yok'} | korunan aday: {item.retained_record_count}")
        lines.extend(f"    Not: {safe_text(note)}" for note in (*coverage.notes, *item.notes))
        lines.extend(_command(link, data_dir=data_dir) for link in item.navigation)
    if content.has_more_scopes:
        lines.append(f"İçerik kapsamlarının devamı: --target-offset {content.scope_offset + len(content.scopes)} --target-limit {content.scope_limit}")
    for page in content.sections:
        lines.append(f"  {_SECTIONS[page.kind]}: toplam {page.total_count} | bu sayfa {len(page.items)} | başlangıç {page.offset}")
        shown = page.items[:3] if summary else page.items
        for record in shown:
            if summary:
                lines.append(f"    {safe_text(record.value)} | {safe_text(_CONTENT_STATUSES.get(record.status, record.status))} | {safe_text(record.id)}")
                lines.extend(_command(link, data_dir=data_dir) for link in record.navigation[:1])
                continue
            lines.extend((f"    {safe_text(record.value)} | {safe_text(_CONTENT_STATUSES.get(record.status, record.status))} | {safe_text(record.source)}",
                          f"      Kimlik: {safe_text(record.id)} | zaman: {safe_text(record.recorded_at)}",
                          f"      İstek özeti: {safe_text(record.definition_sha256)}"))
            lines.extend(f"      {safe_text(detail)}" for detail in record.details)
            lines.extend(_command(link, "      ", data_dir=data_dir) for link in record.navigation)
        if summary and page.total_count > len(shown):
            lines.append(f"    Bu özette yer almayan içerik: {page.total_count - len(shown)}")
        if page.has_more:
            lines.append(f"    Bu içerik bölümünün devamı: --item-offset {page.offset + len(page.items)} --item-limit {page.limit}")
    lines.extend(f"  Not: {safe_text(note)}" for note in content.notes)
    return lines


def execute_organization_report_command(service: OrganizationReportService, args) -> tuple[dict, list[str]]:
    result = service.show(args.organization_id, target_offset=args.target_offset, target_limit=args.target_limit,
                          item_offset=args.item_offset, item_limit=args.item_limit,
                          stale_after_hours=args.stale_after_hours)
    return asdict(result), organization_report_lines(result, summary=getattr(args, 'summary', False),
                                                   data_dir=getattr(args, 'data_dir', None))


def execute_organization_export_command(service: OrganizationExportService, args) -> tuple[dict, list[str]]:
    result = service.export(args.organization_id, destination=args.output,
                            stale_after_hours=args.stale_after_hours)
    return asdict(result), [
        "Kuruluşun tam HTML raporu oluşturuldu: " + safe_text(result.file.path),
        f"Etkin hedef: {result.target_count} | kapsam/kanıt/geçmiş kaydı: {result.record_count}",
        f"Kamu olay izleme çalışması: {result.public_notice_watch_run_count}",
        f"Dosya: {result.file.byte_count} bayt | SHA-256: {result.file.sha256}",
        "Dosyayı tarayıcıda çevrimdışı açabilir veya yazdırabilirsin. Veritabanı değiştirilmedi.",
        "Yüzey bölümleri son kontrol kanıtlarını içerir; eski kontrollerin tüm geçmişi rapora dahil değildir.",
    ]
