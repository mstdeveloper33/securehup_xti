"""Readable projections of the same group payload used by the platform."""
from xti.interfaces.text import safe_text

TIME_LABELS = {'unknown': 'olay zamanı bilinmiyor', 'near_observations': 'gözlemler yakın dönemde',
               'separated_observations': 'gözlemler farklı dönemlerde'}
NOISE_LABELS = {
    'shared_hosting_possible': 'Ortak IP paylaşımlı barındırma/CDN olabilir.',
    'shared_certificate_not_ownership': 'Ortak sertifika aynı sahipliği kanıtlamaz.',
    'warninglist_context': 'Ortak dayanak bir bağlam listesinde bulunuyor.',
    'document_cooccurrence_only': 'Değerler aynı metinde geçiyor; saldırı bağı doğrulanmadı.',
    'duplicate_document_content': 'Aynı metnin kopyaları tek ortak dayanak altında tutuldu.',
    'historical_or_withdrawn_evidence': 'Tarihî veya geri çekilmiş kanıt bulunuyor.',
}


def monitor_group(database, identifier, *, rounds=1, interval_seconds=60, sleep=None):
    import time
    from uuid import uuid4
    from xti.domain.assets import ValidationError
    from xti.domain.group_contract import parameters
    from xti.interfaces.evidence import make_evidence_service
    from xti.adapters.worker_lock import LocalExecutionLock
    parameters('groups.show', {'identifier': identifier})
    if type(rounds) is not int or not 1 <= rounds <= 100 or type(interval_seconds) is not int or not 1 <= interval_seconds <= 3600:
        raise ValidationError('Grup takibi 1–100 tur; aralık 1–3600 saniye olmalı.')
    service, result, run_id = make_evidence_service(database), [], str(uuid4())
    for index in range(rounds):
        if index:
            (sleep or time.sleep)(interval_seconds)
        with LocalExecutionLock(database).acquire():
            previous = service.execute('groups.show', identifier=identifier)['record']
            current = service.execute('groups.refresh', identifier=identifier, expected_revision=previous['revision'],
                idempotency_key=f'group-monitor:{run_id}:{index}')['record']
        result.append({'round': index + 1, 'revision': current['revision'], 'status': current['status'],
            'new_changes': len(current['changes']) - len(previous['changes'])})
    return {'run_id': run_id, 'group_id': identifier, 'rounds': result, 'stored_data_only': True}


def group_lines(data):
    result = []
    records = [data['record']] if 'record' in data else data.get('records', [])
    for record in records:
        group = record.get('group', record)
        result.append(f"Grup: {record['id']} | {group.get('rule', '')}")
        if 'root' in group:
            result.append('  Araştırma kökü: ' + safe_text(group['root'][1]))
        if 'members' in group:
            result.append('  Üyeler: ' + ', '.join(safe_text(row['label']) for row in group['members']))
            result.append('  Ortak dayanak: ' + ', '.join(safe_text(row['label']) for row in group['anchors']))
            for member in group['members']:
                for edge in member['edges']:
                    for proof in edge['evidence']:
                        result.append(f"    {safe_text(member['label'])} | {safe_text(proof['source'])} | {proof['observed_at']} | {safe_text(proof['record_id'])}")
        elif 'member_count' in group:
            result.append('  Kayıtlı üye: ' + str(group['member_count']) + ' | Ayrıntı: groups show ' + record['id'])
        if 'temporal' in group:
            result.append('  Zaman: ' + TIME_LABELS[group['temporal']['state']])
        if group.get('noise_reasons'):
            result.extend('  ' + NOISE_LABELS.get(reason, safe_text(reason)) for reason in group['noise_reasons'])
        if 'revision' in record:
            result.append(f"  Sürüm: {record['revision']} | durum: {record['status']} | karar güncel: {record['review_current']}")
            decision = record['decision']
            result.append('  İnsan kararı: ' + (decision['value'] + ' — ' + safe_text(decision['reason']) if decision else 'henüz yok'))
        if 'evidence_sha256' in group:
            result.append('  Kanıt özeti: ' + group['evidence_sha256'])
        for change in record.get('changes', []):
            result.append(f"  Değişiklik: {change['recorded_at']} | eklenen {len(change['added'])}, görünümden çıkan {len(change['removed_from_view'])}")
        if 'queue_state' in record:
            result.append('  Yeniden inceleme: ' + record['queue_state'])
    if data.get('pagination_basis') == 'saved_groups_examined':
        result.append(f"Bu pencerede incelenen grup: {data['examined_count']} | yeniden inceleme gerektiren: {len(records)} | kayıtlı toplam: {data['total_count']}")
    elif 'total_count' in data:
        result.append(f"Gösterilen: {len(records)} / {data['total_count']}")
    if data.get('has_more'):
        result.append(f"Devam: --offset {data['next_offset']} --expected-snapshot {data['snapshot_id']}")
    if data.get('coverage_complete') is False:
        result.append('Kapsam eksik: ' + ', '.join(data['limitations']))
    if data.get('replayed'):
        result.append('İlk işlem sonucu tekrar gösteriliyor; yeni kontrol yapılmadı.')
    from xti.domain.research_groups import NOTES
    result.extend(data.get('notes', NOTES))
    return result
