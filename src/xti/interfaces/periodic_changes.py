"""Plain Turkish lines for a bounded local changes report."""
from xti.interfaces.text import safe_text
from xti.domain.periodic_changes import PeriodicChangesReport
_LABELS = {
    'brand': 'Marka/domain',
    'surface': 'Dış yüzey',
    'username': 'Sosyal izleme',
    'threatcluster': 'ThreatCluster',
    'ransomlook': 'RansomLook',
    'collection': 'Kaynak ve toplama durumu',
}
_ACTIONS = {
    'new_finding': 'Yeni aday bulgu',
    'discovered': 'Yeni alt alan adayı',
    'owned': 'Sahiplik kapsam kararı',
    'rejected': 'Kapsamdan reddedildi',
    'reopened': 'Kapsam yeniden açıldı',
    'newly_found': 'Yeni görüldü',
    'changed': 'Değişti',
    'no_longer_reported': 'Artık raporlanmıyor',
    'baseline_found': 'Başlangıçta görüldü',
    'baseline_unreported': 'Başlangıçta raporlanmadı',
    'added': 'Listeye eklendi',
    'updated': 'Güncellendi',
    'removed': 'Kaynak listesinden çıktı',
    'failed': 'Kaynak hatası',
    'partial': 'Kısmi sonuç',
    'interrupted': 'Kesilmiş',
    'skipped': 'Kontrol atlandı',
    'running': 'Çalışma hâlâ açık',
    'baseline_empty': 'Başlangıçta eşleşme yok',
}
_COVERAGE = {
    'complete_no_changes': 'Başarılı kontrol var; değişim olmayabilir',
    'observed': 'Dönemde kayıtlı kontrol var',
    'incomplete': 'Hata/kısmi/kesilmiş kontrol var',
    'not_checked': 'Bu dönemde kontrol yok',
    'no_history': 'Geçerli kontrol geçmişi yok',
}


def periodic_changes_lines(report: PeriodicChangesReport) -> list[str]:
    lines = [
        f'Son {report.window.days * 24} saat — yerel değişim raporu',
        f'UTC aralığı: {safe_text(report.window.start_at)} dahil → {safe_text(report.window.end_at)} hariç',
        f"Kapsam: {safe_text(report.scope.domain or 'Bütün yerel kayıtlar')}",
    ]
    for section in report.sections:
        lines.append(f'\n{_LABELS[section.family]}: {section.total_change_count} değişim, {section.total_baseline_count} başlangıç, {section.total_failure_count} hata/eksik kontrol')
        for label, items in (
            ('Değişimler', section.changes),
            ('İlk ölçümler', section.baselines),
            ('Hata / eksik kontrol', section.failures),
        ):
            if not items:
                continue
            lines.append(label + ':')
            for item in items:
                lines.append(f'  {safe_text(item.recorded_at)} | {safe_text(item.source)} | {safe_text(_ACTIONS.get(item.action, item.action))} | {safe_text(item.value)}')
                ids = [f'kayıt={item.record_id}']
                for key, value in (
                    ('çalışma', item.run_id),
                    ('izleme', item.watch_id),
                    ('kaynak çalışma', item.source_run_id),
                    ('önceki çalışma', item.previous_run_id),
                ):
                    if value is not None:
                        ids.append(f'{key}={value}')
                lines.append('    ' + safe_text(' | '.join(ids)))
                if item.rule_version:
                    lines.append('    Kural sürümü: ' + safe_text(item.rule_version))
                if item.target_record_id:
                    lines.append('    Hedef kayıt: ' + safe_text(item.target_record_id))
                if item.reference:
                    lines.append('    Kanıt: ' + safe_text(item.reference))
                if item.definition_sha256:
                    lines.append('    Tarihsel tanım özeti: ' + safe_text(item.definition_sha256))
        if section.omitted_count:
            lines.append(f'  Görünüm sınırı nedeniyle gösterilmeyen {section.omitted_count} satır var.')
    lines.append(f'\nKontrol kapsamı: {report.coverage_total_count} satır, {report.coverage_omitted_count} gösterilmeyen')
    for item in report.coverage:
        lines.append(f'  {safe_text(item.source)} | {safe_text(item.scope_id)} | {_COVERAGE[item.coverage_state]} | dönemde {item.window_run_count} çalışma')
        if item.last_run_id:
            lines.append(f"    Son kayıt: {safe_text(item.last_run_id)} | {safe_text(item.last_recorded_at or '')} | {safe_text(item.last_status or '')}")
    lines.extend(('Not: ' + safe_text(note) for note in report.notes))
    return lines
