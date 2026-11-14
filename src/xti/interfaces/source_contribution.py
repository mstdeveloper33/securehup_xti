"""Readable provider comparisons with real domain lists and evidence identifiers."""
from xti.interfaces.text import safe_text
from xti.domain.source_contribution import SourceContributionReport


def _page_lines(label, page):
    lines = [f'{label}: {page.total_count} farklı domain; bu sayfada {page.shown_count} (başlangıç {page.offset})']
    for item in page.items:
        lines.append(f"  {safe_text(item.domain)} | sağlayıcılar: {safe_text(', '.join(item.providers))}")
        lines.append('    Dayanak: ' + safe_text(', '.join(item.evidence_ids)))
        lines.append('    Kayıt/iş: ' + safe_text(', '.join(item.record_ids)))
        if item.review_statuses:
            lines.append('    Güncel kapsam kararı: ' + safe_text(', '.join(item.review_statuses)))
        if item.source_names:
            lines.append('    Kaynak başvuruları: ' + safe_text(', '.join(item.source_names)))
    if page.has_more:
        lines.append(f'  Devamı var; sonraki --detail-offset {page.offset + page.shown_count}.')
    return lines


def source_contribution_lines(report: SourceContributionReport) -> list[str]:
    lines = ['Yerel kaynak katkısı: ' + safe_text(report.asset_value)]
    for group in report.groups:
        label = 'Alt alan adı keşfi' if group.family == 'surface' else f"Marka araması | kural {safe_text(group.rule_version)} | yazım varyantları {('açık' if group.typos else 'kapalı')}"
        lines.append('\n' + label)
        lines.append('Karşılaştırma: ' + ('yerel kayıt kümeleri mevcut' if group.comparison_state == 'local_comparison' else 'geçmiş yetersiz; kaynak üstünlüğü çıkarılamaz'))
        lines.extend(_page_lines('Bütün kaynakların birleşimi', group.union_domains))
        for source in group.sources:
            outcomes = source.outcomes
            ratio = 'bilinmiyor (payda 0)' if outcomes.completion_rate is None else f'{outcomes.completion_numerator}/{outcomes.completion_denominator} (%{outcomes.completion_rate * 100:.1f})'
            lines.append(f'\nKaynak: {safe_text(source.provider)} | kayıtlı deneme tamamlanması {ratio}')
            lines.append(f'  Tam {outcomes.complete}; kısmi {outcomes.partial}; hatalı {outcomes.failed}; kesilmiş {outcomes.interrupted}; çalışan {outcomes.running}; bekleyen iş {source.queued_job_count}')
            lines.append(f'  Tamamlanmış boş sonuç {source.complete_empty_attempt_count}; sonucu olmayan deneme {source.resultless_attempt_count}; çok hedefli dışarıda tutulan deneme {source.excluded_multi_target_attempt_count}; çok hedefli bekleyen iş {source.excluded_multi_target_queued_job_count}')
            if source.first_attempt_at:
                lines.append(f'  Deneme aralığı: {safe_text(source.first_attempt_at)} → {safe_text(source.last_attempt_at)}')
            if source.first_evidence_recorded_at:
                lines.append(f'  Kanıtın yerel kayıt aralığı: {safe_text(source.first_evidence_recorded_at)} → {safe_text(source.last_evidence_recorded_at)}')
            lines.extend(_page_lines('Kaynağın adayları', source.all_domains))
            lines.extend(_page_lines('Başka kaynaklarda da bulunan', source.shared_domains))
            lines.extend(_page_lines(
                'Yalnız bu kaynağın yerel kayıtlarında bulunan',
                source.exclusive_domains,
            ))
            if source.attempt_ids:
                lines.append('  Hesaplanan denemeler: ' + safe_text(', '.join(source.attempt_ids)))
            if source.excluded_multi_target_attempt_ids:
                lines.append('  Çok hedefli denemeler: ' + safe_text(', '.join(source.excluded_multi_target_attempt_ids)))
            lines.extend(('  Kaynak notu: ' + safe_text(warning) for warning in source.warnings))
        for pair in group.overlaps:
            lines.extend(_page_lines(
                f'Ortak domainler — {safe_text(pair.first_provider)} / {safe_text(pair.second_provider)}',
                pair.domains,
            ))
        lines.extend(('Not: ' + safe_text(note) for note in group.notes))
    lines.extend(('Not: ' + safe_text(note) for note in report.notes))
    lines.append('Kaynak değerlendirmesi: ' + safe_text(report.provider_evaluation))
    return lines
