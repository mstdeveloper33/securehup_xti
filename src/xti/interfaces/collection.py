"""Terminal views of passive collection; JSON uses the same domain models."""

from xti.domain.brand_username_watches import BrandUsernameWatchRunReport
from xti.domain.collection import CollectionPlan, CollectionResult, CollectionStep
from xti.interfaces.analysis import report_lines as analysis_lines
from xti.interfaces.public_notices import public_notice_collection_lines
from xti.interfaces.news import refresh_lines as news_refresh_lines
from xti.interfaces.global_saved_searches import run_lines as search_run_lines
from xti.interfaces.ransomlook_watches import run_lines as ransomlook_watch_lines
from xti.interfaces.ransomware_watches import run_lines as ransomware_watch_lines
from xti.interfaces.text import safe_text


_STATUS = {"complete": "Tamamlandı", "partial": "Kısmi", "failed": "Başarısız", "skipped": "Atlandı"}
_SOCIAL_ACTIONS = {
    "baseline_found": "başlangıçta bulundu, doğrulanmadı",
    "baseline_unreported": "başlangıçta raporlanmadı",
    "newly_found": "yeni bulundu, doğrulanmadı",
    "changed": "profil adresi değişti",
    "unchanged_found": "bulundu, değişmedi",
    "no_longer_reported": "artık raporlanmadı",
    "unchanged_unreported": "raporlanmadı, değişmedi",
}


def plan_lines(plan: CollectionPlan) -> list[str]:
    lines = [
        f"Pasif toplama planı: {safe_text(plan.asset_value)}",
        "Bu önizleme ağ isteği veya veri yazımı yapmadı.",
        f"Ek yazım varyantları: {'açık' if plan.typos else 'kapalı'}",
        "",
    ]
    for number, task in enumerate(plan.tasks, start=1):
        lines.append(f"  {number}. {safe_text(task.label)} ({safe_text(task.id)})")
        for watch in task.watches:
            lines.extend([
                f"    İzleme: {safe_text(watch.display_name)} | {safe_text(watch.watch_id)}",
                f"    Kaynak: {safe_text(task.source)} | tür: {safe_text(watch.kind)} | "
                f"aranan: {safe_text(watch.query)} | eşleşme: {safe_text(watch.match_mode)}",
            ])
            if watch.platforms:
                lines.append(f"    Platformlar: {safe_text(', '.join(watch.platforms))}")
    if any(task.watches for task in plan.tasks):
        lines.extend([
            "",
            f"Her izleme için gösterilecek kayıt sınırı: {plan.watch_item_limit}",
            "İzlemeler açık seçimle eklenir; domainle otomatik sahiplik bağı kurulmaz.",
        ])
    lines.extend(["", *(safe_text(note) for note in plan.notes)])
    return lines


def _username_lines(report: BrandUsernameWatchRunReport) -> list[str]:
    run, watch = report.run, report.watch
    lines = [
        f"  İzleme: {safe_text(watch.display_name)} | {safe_text(watch.id)}",
        f"  Kullanıcı adı: @{safe_text(watch.username)} | kaynak: {safe_text(watch.source_key)}",
        f"  Çalışma: {safe_text(run.id)}",
    ]
    if run.status == "failed":
        return [
            *lines, f"  Hata: {safe_text(run.error or 'Bilinmeyen kaynak hatası')}",
            "  Önceki başarılı ölçüm korunur; kaynak hatası hesabın bulunmadığı anlamına gelmez.",
        ]
    if report.is_baseline:
        lines.append("  İlk başarılı ölçüm başlangıçtır; bulunan profiller yeni alarm sayılmaz.")
    lines.extend([
        f"  Platform: {run.platform_count} | bulunan: {run.found_count} | "
        f"raporlanmayan: {run.unreported_count}",
        f"  Yeni bulunan: {run.newly_found_count} | değişen: {run.changed_count} | "
        f"artık raporlanmayan: {run.no_longer_reported_count} | "
        f"bulunup değişmeyen: {run.unchanged_found_count}",
        f"  Sonuç öğesi: {report.total_item_count}; {len(report.items)} gösteriliyor.",
    ])
    for item in report.items:
        suffix = f" | {safe_text(item.profile_url)}" if item.profile_url else ""
        lines.append(f"    {safe_text(item.platform)} | {_SOCIAL_ACTIONS[item.action]}{suffix}")
    if report.total_item_count > len(report.items):
        lines.append(f"  {report.total_item_count - len(report.items)} öğe görünüm sınırı dışında.")
    lines.extend([
        "  Raporlanmamak hesabın yokluğu/silinmesi; bulunmak sahiplik veya taklit kanıtı değildir.",
        f"  Kayıt ve insan kararları: ./xti brand watch-run-show {safe_text(run.id)} --limit 500",
    ])
    return lines


def _ransomware_lines(step: CollectionStep) -> list[str]:
    result = step.ransomware
    assert result is not None
    source = result.refresh.run
    lines = [
        f"  Kaynak: {safe_text(step.task.source)} | yenileme kaydı: {safe_text(source.id)}",
    ]
    if source.status == "failed":
        lines.extend([
            f"  Hata: {safe_text(source.error or 'Bilinmeyen kaynak hatası')}",
            "  Kaynak yenilenemedi; eski snapshot üzerinde izleme çalıştırılmadı.",
        ])
        labels = {watch.watch_id: watch.display_name for watch in step.task.watches}
        for watch_id in result.skipped_watch_ids:
            lines.append(
                f"  Çalıştırılmadı: {safe_text(labels.get(watch_id, watch_id))} | {safe_text(watch_id)}"
            )
        return lines
    lines.extend([
        f"  Kaynak listesindeki iddia: {source.claim_count}",
        "  Bu sayı kaynak listesine aittir; domainin bulgu sayısı değildir.",
    ])
    render = ransomlook_watch_lines if step.task.source == "ransomlook" else ransomware_watch_lines
    for report in result.watches:
        lines.extend([
            f"  İzleme: {safe_text(report.watch.id)} | kaynak çalışması: {safe_text(report.run.source_run_id)}",
        ])
        if report.is_baseline:
            lines.append("  Başlangıç ölçümü: aşağıdaki kayıtlar yeni olay veya alarm sayılmaz.")
        lines.extend(f"  {line}" for line in render(report))
        lines.append(
            f"  Ayrıntı: ./xti ransomware watch-run-show {safe_text(report.run.id)} "
            f"--source {safe_text(step.task.source)} --limit 500"
        )
    lines.append("  Aynı iddia birden fazla izlemede eşleşebilir; sayılar benzersiz toplam diye toplanmaz.")
    return lines


def result_lines(result: CollectionResult, *, data_dir=None, summary=False) -> list[str]:
    if summary:
        from xti.interfaces.collection_summary import summary_lines
        return summary_lines(result, data_dir=data_dir)
    lines = [
        f"Pasif toplama: {safe_text(result.plan.asset_value)}",
        f"Genel sonuç: {_STATUS[result.status]}",
        f"Başlangıç: {safe_text(result.started_at)} | Bitiş: {safe_text(result.finished_at)}",
        "",
    ]
    if result.session_id is not None:
        lines.append(f"Toplama oturumu: {safe_text(result.session_id)}")
        lines.append(f"Geçmiş: ./xti collections show {safe_text(result.session_id)}")
    for step in result.steps:
        lines.append(f"{safe_text(step.task.label)}: {_STATUS[step.status]}")
        if step.attempt is not None:
            attempt = step.attempt
            lines.append(f"  İş: {safe_text(attempt.job_id)} | Deneme: {safe_text(attempt.id)}")
            if attempt.result is not None:
                scan = attempt.result
                summary = scan.summary
                lines.append(
                    f"  Yeni bulgu: {summary.findings_created} | "
                    f"Yeni gözlem: {summary.observations_created} | "
                    f"Önceden kayıtlı gözlem: {summary.observations_existing}"
                )
                for domain in scan.candidate_domains:
                    lines.append(f"  Marka adayı: {safe_text(domain)}")
                for query in scan.queries:
                    lines.append(
                        f"  Sorgu: {safe_text(query.pattern)} | {_STATUS[query.status]} | "
                        f"Kaynak kaydı: {query.record_count}"
                    )
                    if query.error:
                        lines.append(f"    Hata: {safe_text(query.error)}")
                    lines.extend(f"    Uyarı: {safe_text(note)}" for note in query.warnings)
                    lines.extend(f"    Kapsam: {safe_text(note)}" for note in query.coverage_notes)
            if attempt.error:
                lines.append(f"  Hata: {safe_text(attempt.error)}")
        elif step.discovery is not None:
            discovery = step.discovery
            lines.extend([
                f"  Keşif kaydı: {safe_text(discovery.run_id)}",
                f"  Yeni aday: {discovery.candidates_created} | "
                f"Mevcut aday: {discovery.candidates_existing} | "
                f"Yeni kaynak kanıtı: {discovery.evidence_created}",
            ])
            lines.extend(f"  Alt alan adı: {safe_text(domain)}" for domain in discovery.candidate_domains)
            if discovery.error:
                lines.append(f"  Hata: {safe_text(discovery.error)}")
            lines.extend(f"  Uyarı: {safe_text(note)}" for note in discovery.warnings)
        elif step.feed is not None:
            feed = step.feed
            lines.append(f"  Liste yenileme kaydı: {safe_text(feed.id)}")
            if feed.status == "complete":
                lines.extend([
                    f"  Kaynak listesindeki gösterge: {feed.indicator_count} | "
                    f"Yeni: {feed.added_count} | Değişen: {feed.updated_count} | "
                    f"Çıkan: {feed.revoked_count}",
                    "  Bu sayılar kaynak listesine aittir; domainin bulgu sayısı değildir.",
                ])
            else:
                lines.append(f"  Hata: {safe_text(feed.error)}")
                lines.append("  Liste alınamadı; sıfır gösterge bulunduğu anlamına gelmez.")
                lines.append("  Varsa önceki geçerli yerel IOC kaydı analizde korunur.")
        elif step.public_notices is not None:
            lines.extend("  " + line for line in public_notice_collection_lines(step.public_notices))
        elif step.news is not None:
            lines.extend("  " + line for line in news_refresh_lines(
                step.news, limit=result.plan.watch_item_limit, data_dir=data_dir, comparison_pending=True,
            ))
            lines.append("  Haber sayısı yayıncıya aittir; seçilen domainin bulgu sayısı değildir.")
        elif step.search is not None:
            lines.extend("  " + line for line in search_run_lines(step.search, data_dir=data_dir))
        elif step.task.kind == "search_watch" and step.status == "skipped":
            lines.append("  Haber yenilemesi tamamlanamadı; eski katalogdan yeni bildirim üretilmedi.")
        elif step.username is not None:
            lines.extend(_username_lines(step.username))
        elif step.ransomware is not None:
            lines.extend(_ransomware_lines(step))
        lines.append("")
    if result.status != "complete":
        lines.extend([
            "Toplama eksik kaldı; aşağıdaki kayıtlı analiz kaynak hatasını ortadan kaldırmaz.",
            "",
        ])
    if any(step.task.watches for step in result.steps):
        lines.append("Domain için kayıtlı analiz; seçilen izlemelerin sonuçları yukarıda ayrı gösterildi:")
    lines.extend(analysis_lines(result.analysis, after_collection=True))
    lines.extend(["", *(safe_text(note) for note in result.plan.notes)])
    return lines
