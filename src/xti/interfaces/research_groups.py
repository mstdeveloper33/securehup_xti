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


def monitor_group(database, identifier, *, rounds=1, interval_seconds=60, sleep=None, queued=False):
    import time
    from uuid import uuid4
    from xti.domain.assets import ValidationError
    from xti.domain.group_contract import parameters
    from xti.interfaces.evidence import make_evidence_service
    from xti.adapters.worker_lock import LocalExecutionLock
    parameters('groups.show', {'identifier': identifier})
    if type(rounds) is not int or not 1 <= rounds <= 100 or type(interval_seconds) is not int or not 1 <= interval_seconds <= 3600:
        raise ValidationError('Grup takibi 1–100 tur; aralık 1–3600 saniye olmalı.')
    if type(queued) is not bool:
        raise ValidationError('Grup kuyruk seçimi boolean olmalı.')
    service, result, run_id = make_evidence_service(database), [], str(uuid4())
    if queued:
        from types import SimpleNamespace
        from xti.interfaces.source_jobs import make_source_job_service
        from xti.interfaces.platform_jobs import make_job_service
        context = SimpleNamespace(data_dir=database.parent, database=database)
        jobs, worker = make_source_job_service(context), make_job_service(context)
    for index in range(rounds):
        if index:
            (sleep or time.sleep)(interval_seconds)
        if queued:
            previous = service.execute('groups.current', identifier=identifier)['record']
            plan = jobs.plan(indicator_type=previous['group']['root'][0], value=previous['group']['root'][1],
                sources=['group-refresh'], group_id=identifier)
            job = jobs.submit(**plan['plan'], plan_sha256=plan['plan_sha256'],
                idempotency_key=f'group-monitor:{run_id}:{index}')
            worker.work_one(job.id)
            job = jobs.status(job.id)
            receipt = job.steps[0]['receipt']
            result.append({'round': index + 1, 'job_id': job.id, 'job_status': job.status,
                'revision': receipt['revision'] if receipt else None,
                'status': receipt['group_status'] if receipt else job.status,
                'new_changes': int(receipt is not None and receipt['notification_id'] is not None)})
            if job.status not in ('complete', 'partial'):
                break
            continue
        with LocalExecutionLock(database).acquire():
            previous = service.execute('groups.current', identifier=identifier)['record']
            current = service.execute('groups.refresh', identifier=identifier, expected_revision=previous['revision'],
                idempotency_key=f'group-monitor:{run_id}:{index}', response_mode='current')['record']
        result.append({'round': index + 1, 'revision': current['revision'], 'status': current['status'],
            'new_changes': current['change_count'] - previous['change_count']})
    return {'run_id': run_id, 'group_id': identifier, 'rounds': result, 'stored_data_only': True,
        'execution': 'managed_queue' if queued else 'foreground'}


def group_lines(data):
    if 'integrity' in data:
        lines = [f"Grup geçmişi doğrulandı: {data['group_count']} grup, {data['event_count']} kontrol/karar, {data['change_count']} değişiklik."]
        if data.get('backup'):
            lines.append('Önceki veritabanı yedeği: ' + data['backup'])
        return lines
    if 'notification' in data:
        notice = data['notification']
        proof = notice['snapshot']
        lines = [f"Bildirim: {notice['id']} | {notice['created_at']} | okundu: {notice['read_at'] or 'hayır'}"]
        for label, record in (('Önceki kanıt', proof['before']), ('Kontrol sonucu', proof['after'])):
            lines.append(label + ' | ' + record['status'])
            lines.extend(group_lines({'record': {**record, 'id': proof['group_id']}, 'notes': []}))
        lines.append('Bildirim anındaki kanıtlar korunur; insan kararı değiştirilmez.')
        return lines
    result = []
    records = [data['record']] if 'record' in data else data.get('records', [])
    for record in records:
        if 'operation' in record and 'subject_id' in record:
            snapshot = record['snapshot']
            kind = 'önceki kanıt aynı' if isinstance(snapshot, dict) and 'same_as_previous' in snapshot else 'görünümde yok' if snapshot is None else 'kanıt gövdesi kayıtlı'
            result.append(f"{record['recorded_at']} | {record['operation']} | sürüm {record['request']['expected_revision'] + 1} | {kind}")
            result.append('  Olay: ' + record['id'])
            continue
        if record.get('kind') == 'research_group_change':
            change = record['change']
            result.append(f"{change['recorded_at']} | eklenen {len(change['added'])}, görünümden çıkan {len(change['removed_from_view'])} | olay: {change['id']}")
            continue
        if 'snapshot_sha256' in record and 'change' in record:
            result.append(f"Bildirim: {record['id']} | {record['created_at']} | grup: {record['group_id']}")
            result.append(f"  Eklenen: {len(record['change']['added'])} | görünümden çıkan: {len(record['change']['removed_from_view'])}")
            continue
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
            result.append('  Kayıtlı üye: ' + str(group['member_count']) + ' | Ayrıntı: groups current ' + record['id'])
        if 'temporal' in group:
            result.append('  Zaman: ' + TIME_LABELS[group['temporal']['state']])
        if group.get('noise_reasons'):
            result.extend('  ' + NOISE_LABELS.get(reason, safe_text(reason)) for reason in group['noise_reasons'])
        if 'revision' in record:
            result.append(f"  Sürüm: {record['revision']} | durum: {record['status']} | karar güncel: {record['review_current']}")
            decision = record['decision']
            result.append('  İnsan kararı: ' + (decision['value'] + ' — ' + safe_text(decision['reason']) if decision else 'henüz yok'))
        if 'change_count' in record and 'changes' not in record:
            result.append(f"  Kayıtlı değişiklik: {record['change_count']} | Geçmiş: groups changes {record['id']}")
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
