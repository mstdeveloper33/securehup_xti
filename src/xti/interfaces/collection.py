"""Terminal views of passive collection; JSON uses the same domain models."""

from xti.domain.collection import CollectionPlan, CollectionResult
from xti.interfaces.analysis import report_lines as analysis_lines
from xti.interfaces.text import safe_text


_STATUS = {"complete": "Tamamlandı", "partial": "Kısmi", "failed": "Başarısız"}


def plan_lines(plan: CollectionPlan) -> list[str]:
    lines = [
        f"Pasif toplama planı: {safe_text(plan.asset_value)}",
        "Bu önizleme ağ isteği veya veri yazımı yapmadı.",
        f"Ek yazım varyantları: {'açık' if plan.typos else 'kapalı'}",
        "",
    ]
    lines.extend(
        f"  {number}. {safe_text(task.label)} ({safe_text(task.id)})"
        for number, task in enumerate(plan.tasks, start=1)
    )
    lines.extend(["", *(safe_text(note) for note in plan.notes)])
    return lines


def result_lines(result: CollectionResult) -> list[str]:
    lines = [
        f"Pasif toplama: {safe_text(result.plan.asset_value)}",
        f"Genel sonuç: {_STATUS[result.status]}",
        f"Başlangıç: {safe_text(result.started_at)} | Bitiş: {safe_text(result.finished_at)}",
        "",
    ]
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
        lines.append("")
    if result.status != "complete":
        lines.extend([
            "Toplama eksik kaldı; aşağıdaki kayıtlı analiz kaynak hatasını ortadan kaldırmaz.",
            "",
        ])
    lines.extend(analysis_lines(result.analysis, after_collection=True))
    lines.extend(["", *(safe_text(note) for note in result.plan.notes)])
    return lines
