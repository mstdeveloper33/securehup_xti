"""Compact collection output with source failures and read-only drill-down."""

from xti.domain.collection import CollectionResult, CollectionStep
from xti.interfaces.text import safe_text, xti_command
from xti.interfaces.surface_discovery_status import summary_line as discovery_summary_line
from xti.interfaces.surface_freshness import item_summary_line as freshness_summary_line


_STATUS = {"complete": "Tamamlandı", "partial": "Kısmi", "failed": "Başarısız", "skipped": "Atlandı"}


def social_lines(run, *, data_dir=None):
    if run['status'] == 'not_due':
        return ['  Sosyal izlemenin zamanı gelmedi; ağ isteği yapılmadı.',
            '  İzleme: ' + xti_command('brand', 'tracking-show', run['watch_id'], data_dir=data_dir)]
    lines = ['  Sosyal çalışma: ' + safe_text(run['id']),
        '  Ayrıntı: ' + xti_command('brand', 'tracking-run-show', run['id'], data_dir=data_dir)]
    if run['baseline']:
        lines.append('  İlk ölçüm sessiz başlangıçtır; yeni alarm sayılmaz.')
    for change in run['changes'][:20]:
        lines.append('  ' + safe_text(change['url']) + ' | ' + safe_text(change['kind']))
    if len(run['changes']) > 20:
        lines.append('  Diğer değişiklikler çalışma ayrıntısında korunur.')
    return lines


def _step_lines(step: CollectionStep, *, data_dir=None) -> list[str]:
    def command(*args):
        return "  Ayrıntı: " + xti_command(*args, data_dir=data_dir)

    lines = [f"{safe_text(step.task.label)}: {_STATUS[step.status]}"]
    if step.attempt is not None:
        attempt = step.attempt
        lines.append(command("jobs", "show", attempt.job_id))
        if attempt.result is not None:
            scan = attempt.result
            lines.append(f"  Yeni marka adayı: {scan.summary.findings_created} | yeni gözlem: {scan.summary.observations_created}")
        # Failed attempts can have query evidence without a ScanResult.
        for query in attempt.queries:
            if query.status != "complete":
                lines.append(f"  Sorgu {safe_text(query.pattern)}: {_STATUS[query.status]} | alınan kayıt: {query.record_count}")
            if query.error:
                lines.append("  Hata: " + safe_text(query.error))
            lines.extend("  Kapsam: " + safe_text(note) for note in (*query.warnings, *query.coverage_notes))
        if attempt.error:
            lines.append("  Hata: " + safe_text(attempt.error))
    elif step.discovery is not None:
        result = step.discovery
        lines.append(f"  Yeni alt alan adayı: {result.candidates_created} | mevcut aday: {result.candidates_existing}")
        lines.append(command("surface", "run", result.run_id))
        if result.error:
            lines.append("  Hata: " + safe_text(result.error))
        lines.extend("  Kapsam: " + safe_text(note) for note in result.warnings)
    elif step.feed is not None:
        run = step.feed
        lines.append("  Ortak IOC kataloğu; katalog büyüklüğü domainin bulgu sayısı değildir.")
        lines.append("  Kaynak çalışma kimliği: " + safe_text(run.id))
        lines.append(command("ioc", "status", "--source", step.task.source, "--limit", "100"))
        if run.error:
            lines.append("  Hata: " + safe_text(run.error))
    elif step.news is not None:
        run = step.news.run
        lines.append("  Yayıncı akışı alındı; firma eşleşmesi seçilmiş aramada ayrıca değerlendirilir."
                     if run.status == "complete" else "  Yayıncı akışı yenilenemedi; eski haberler yeni sonuç sayılmaz.")
        lines.append(command("news", "run-show", run.id))
        if run.error:
            lines.append("  Hata: " + safe_text(run.error))
    elif step.public_notices is not None:
        report = step.public_notices
        lines.extend(("  Ortak kamu olay kataloğu; bu domain için ihlal doğrulaması değildir.",
                      "  " + safe_text(report.attribution), "  " + safe_text(report.license)))
        if report.is_baseline:
            lines.append("  İlk katalog başlangıçtır; kayıtlar yeni ihlal bildirimi sayılmaz.")
        if report.run.error:
            lines.append("  Hata: " + safe_text(report.run.error))
        lines.append(command("notices", "run-show", report.run.id))
    elif step.search is not None:
        report = step.search
        lines.append(f"  Seçilen arama: {safe_text(report.saved_search.display_name)} | eşleşme: {report.run.total_count}")
        if report.run.previous_run_id is None:
            lines.append("  İlk ölçüm başlangıçtır; yeni alarm sayılmaz.")
        lines.append(command("search-watch", "run-show", report.run.id))
    elif step.task.kind == "search_watch" and step.status == "skipped":
        lines.append("  Haber yenilemesi tamamlanamadı; eski katalogdan yeni bildirim üretilmedi.")
    elif step.social is not None:
        lines.extend(social_lines(step.social, data_dir=data_dir))
    elif step.username is not None:
        report = step.username
        lines.append(f"  İzleme: {safe_text(report.watch.display_name)} | kullanıcı adı: @{safe_text(report.watch.username)}")
        if report.run.error:
            lines.append("  Hata: " + safe_text(report.run.error))
        else:
            lines.append(f"  Bulunan profil: {report.run.found_count}; sahiplik veya taklit doğrulaması değildir.")
        if report.is_baseline:
            lines.append("  İlk ölçüm başlangıçtır; yeni alarm sayılmaz.")
        lines.append(command("brand", "watch-run-show", report.run.id))
    elif step.ransomware is not None:
        result = step.ransomware
        if result.refresh.run.error:
            lines.append("  Hata: " + safe_text(result.refresh.run.error))
        for report in result.watches:
            lines.append(f"  İzleme: {safe_text(report.watch.display_name)} | kaynak iddiası eşleşmesi: {report.run.total_count}")
            if report.is_baseline:
                lines.append("  İlk ölçüm başlangıçtır; yeni olay sayılmaz.")
            lines.append(command("ransomware", "watch-run-show", report.run.id, "--source", step.task.source))
        for identifier in result.skipped_watch_ids:
            lines.append("  Çalıştırılmayan izleme: " + safe_text(identifier))
    return lines


def summary_lines(result: CollectionResult, *, data_dir=None) -> list[str]:
    lines = [f"Pasif toplama: {safe_text(result.plan.asset_value)} — kısa görünüm",
             f"Genel sonuç: {_STATUS[result.status]}",
             f"Başlangıç: {safe_text(result.started_at)} | Bitiş: {safe_text(result.finished_at)}"]
    if result.session_id:
        lines.append("Kayıtlı çalışma: " + xti_command("collections", "show", result.session_id, data_dir=data_dir))
    for step in result.steps:
        lines.extend(_step_lines(step, data_dir=data_dir))
    if result.status != "complete":
        lines.append("Toplama eksik kaldı. Aşağıdaki yerel analiz önceki kanıtları da içerebilir; kaynak hatası boş sonuç değildir.")
    report = result.analysis
    lines.extend(("", "Domain için kayıtlı sonuçlar (kategoriler birbirine eklenmez):",
                  f"  Marka/domain adayı: {report.findings.total}",
                  f"  Pasif alt alan adayı: {report.overview.candidate_counts.total}",
                  f"  Dış yüzey inceleme adayı: {report.exposures.candidate_count}"))
    shown = report.findings.samples[:3]
    for item in shown:
        lines.append(f"    {safe_text(item.domain)} | {safe_text(item.status)} | {safe_text(item.id)}")
    if report.findings.total > len(shown):
        lines.append(f"  Özette yer almayan marka/domain adayı: {report.findings.total - len(shown)}")
    lines.append("  Pasif keşif: " + discovery_summary_line(report.discovery))
    if report.discovery.error:
        lines.append("  Son kayıtlı keşif hatası: " + safe_text(report.discovery.error))
    for item in report.freshness.items:
        lines.append("  " + freshness_summary_line(item))
    if report.ioc_catalog_status == "empty":
        lines.append("  IOC kataloğu boş; eşleşme değerlendirilmedi.")
    else:
        lines.append(f"  Kayıtlı IOC eşleşmesi: {len(report.ioc_matches)}; tek başına zararlılık hükmü değildir.")
        for item in report.ioc_matches[:3]:
            lines.append(f"    {safe_text(item.indicator_type)}: {safe_text(item.value)}")
        if len(report.ioc_matches) > 3:
            lines.append(f"  Özette yer almayan IOC eşleşmesi: {len(report.ioc_matches) - 3}")
    lines.extend(("Özet yalnız görünümü kısaltır; kaynak kayıtları ve JSON sonucu korunur.",
                  "Kaynak kayıtlarının ayrıntısını yukarıdaki okuma komutlarıyla açabilirsin; toplama yeniden çalışmaz.",
                  "Güncel yerel analiz: " + xti_command("analyze", result.plan.asset_value, data_dir=data_dir)))
    return lines
