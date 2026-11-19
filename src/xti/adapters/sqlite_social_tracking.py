"""One workspace transaction for review history, tracking receipts and inbox delivery."""
import json
from uuid import uuid4, uuid5, NAMESPACE_URL

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository, COLUMNS, _receipt
from xti.adapters.sqlite_social_enrichment import SQLiteSocialEnrichmentRepository, COLUMNS as ENRICHMENT_COLUMNS
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.domain.assets import ValidationError
from xti.domain.mentions import mention_time, mention_uuid
from xti.domain.research_history import history_key
from xti.domain.social_discovery import SocialDiscoveryError, canonical, fingerprint
from xti.domain.social_tracking import (
    MAX_EVENTS, MAX_BYTES, POLICY, apply_event, case_id, empty_state, parameters, profile_key,
    public_watch, selected_profile, validate_case_snapshot,
)


def _bounded(connection, table, columns):
    count, size, largest = connection.execute(f'SELECT COUNT(*),COALESCE(SUM({columns}),0),COALESCE(MAX({columns}),0) FROM {table}').fetchone()
    allocated = connection.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (table,)).fetchone()
    if (count > MAX_EVENTS or size > MAX_BYTES or largest > 32768 or
            (allocated is None and count) or (allocated is not None and allocated[0] != count)):
        raise StorageError('Sosyal izleme kayıt sınırı veya günlük sıra bütünlüğü geçersiz.')
    return count, size


def discovery_in(connection, identifier):
    row = connection.execute(f'SELECT {COLUMNS} FROM social_discovery_runs WHERE id=?', (identifier,)).fetchone()
    if row is None: raise SocialDiscoveryError('not_found', 'Sosyal keşif bu çalışma alanında bulunamadı.')
    return _receipt(row)


def audit(connection):
    count, size = connection.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(scope_json)+COALESCE(LENGTH(report_json),0)),0) FROM social_discovery_runs').fetchone()
    allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='social_discovery_runs'").fetchone()
    if count > 10000 or size > 64 * 1024 * 1024 or (allocated is None and count) or (allocated is not None and allocated[0] != count):
        raise StorageError('Sosyal kaynak geçmişi okuma kapasitesi veya sıra bütünlüğü geçersiz.')
    _bounded(connection, 'social_tracking_journal', 'LENGTH(request_json)+LENGTH(request_key)+LENGTH(operation)+256')
    state, chain, previous_at, cache = empty_state(), None, None, {}
    try:
        for sequence, rid, key, op, text, did, dsha, checksum, at in connection.execute(
                'SELECT sequence,id,request_key,operation,request_json,discovery_id,discovery_sha256,chain_sha256,recorded_at '
                'FROM social_tracking_journal ORDER BY sequence'):
            mention_uuid(rid); history_key(key); mention_time(at)
            if sequence != len(state['events']) + 1 or previous_at is not None and at < previous_at:
                raise ValueError('Order')
            req = json.loads(text)
            if canonical(req) != text or fingerprint([POLICY, chain, sequence, rid, key, op, req, did, dsha, at]) != checksum:
                raise ValueError('Chain')
            if did != req.get('discovery_id'): raise ValueError('Discovery reference')
            discovery = None
            if did is not None:
                if did not in cache: cache[did] = discovery_in(connection, did)
                discovery = cache[did]
                if discovery['report_sha256'] != dsha: raise ValueError('Receipt changed')
            elif dsha is not None: raise ValueError('Unexpected receipt hash')
            event = {'id': rid, 'key': key, 'operation': op, 'request': req, 'recorded_at': at}
            apply_event(state, event, discovery)
            chain, previous_at = checksum, at
        return state, chain, previous_at
    except (ValidationError, SocialDiscoveryError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise StorageError('Sosyal inceleme/izleme günlüğü veya kaynak kanıtı doğrulanamadı.') from error


def notification_id(run_id, change_id):
    return str(uuid5(NAMESPACE_URL, 'xti-social:' + run_id + ':' + change_id))


def notifications_in(connection, state=None):
    state = audit(connection)[0] if state is None else state
    _bounded(connection, 'social_tracking_notifications', '256')
    expected = {notification_id(run['id'], change['id']): (run, change)
                for run in state['runs'].values() for change in run['changes']}
    result, previous_sequence = {}, 0
    try:
        for ordinal, sequence, rid, run_id, change_id, at, read_at in connection.execute(
                'SELECT ordinal,sequence,id,run_id,change_id,created_at,read_at FROM social_tracking_notifications ORDER BY ordinal'):
            if rid not in expected or ordinal != len(result) + 1 or sequence <= previous_sequence:
                raise ValueError('Notification order')
            run, change = expected[rid]
            if run['id'] != run_id or change['id'] != change_id or run['finished_at'] != at:
                raise ValueError('Notification reference')
            if read_at is not None: mention_time(read_at)
            result[rid] = {'id': rid, 'sequence': sequence, 'watch_id': run['watch_id'], 'run_id': run_id,
                           'domain': run['scope']['domain'], 'change': change, 'created_at': at, 'read_at': read_at,
                           'meaning': 'observed_profile_change_not_impersonation_or_ownership_verdict'}
            previous_sequence = sequence
        if set(expected) != set(result): raise ValueError('Missing notification')
        return result
    except (ValidationError, ValueError, TypeError, KeyError) as error:
        raise StorageError('Sosyal değişiklik bildirimi ve çalışma kanıtı uyuşmuyor.') from error


def provider_window(connection, discovery, repository):
    repository._capacity(connection)
    rows = connection.execute(f'SELECT {ENRICHMENT_COLUMNS} FROM social_enrichment_runs WHERE discovery_id=? ORDER BY sequence DESC LIMIT 21', (discovery['id'],)).fetchall()
    return ([repository._record(connection, row, discovery=discovery) for row in rows[:20]], len(rows) > 20)


def review_in(connection, discovery, url, state, enrichment_repository, *, provider_records=None):
    profile = selected_profile(discovery, url)
    history = state['reviews'].get(profile_key(discovery['scope']['domain'], url), [])
    providers = []
    # Return only bounded minimal provider evidence relevant to this exact profile.
    records, truncated = provider_window(connection, discovery, enrichment_repository) if provider_records is None else provider_records
    for record in records:
        if url not in record['scope']['targets']: continue
        result = next((r for r in record['state']['profiles'] if r['url'] == url), None)
        providers.append({'id': record['id'], 'receipt_sha256': record['receipt_sha256'],
                          'status': record['state']['status'], 'checked_at': record['state']['checked_at'],
                          'result': result})
    return {'domain': discovery['scope']['domain'], 'discovery_id': discovery['id'],
            'report_sha256': discovery['report_sha256'], 'checked_at': discovery['finished_at'],
            'profile': profile, 'provider_evidence': providers, 'provider_evidence_truncated': truncated,
            'review': history[-1] if history else None, 'revision': len(history), 'review_history': history,
            'review_matches_discovery': bool(history and history[-1]['discovery_id'] == discovery['id']),
            'case_evidence_type': 'social_discovery', 'case_evidence_id': case_id(discovery['id'], url)}


def review_list_in(connection, path, *, domain=None, offset=0, limit=20, state=None):
    state = audit(connection)[0] if state is None else state
    discovery_repo = SQLiteSocialDiscoveryRepository(path)
    discovery_repo._capacity(connection)
    where, args = (' AND d.domain=?', (domain,)) if domain else ('', ())
    ids = [r[0] for r in connection.execute('SELECT d.id FROM social_discovery_runs d WHERE d.report_json IS NOT NULL '
        'AND d.sequence=(SELECT MAX(x.sequence) FROM social_discovery_runs x WHERE x.domain=d.domain AND x.report_json IS NOT NULL)'
        + where + ' ORDER BY d.domain', args)]
    total, rows, digest_rows = 0, [], []
    enrichment_repo = SQLiteSocialEnrichmentRepository(path)
    for identifier in ids:
        discovery = discovery_in(connection, identifier)
        providers = None
        for profile in sorted(discovery['report']['profiles'], key=lambda r: (r['platform'], r['url'])):
            # Empty username hypotheses are retained in discovery-show, not the analyst queue.
            if profile['state'] not in ('found', 'candidate') and not profile['claimed_by']: continue
            history = state['reviews'].get(profile_key(discovery['scope']['domain'], profile['url']), [])
            digest_rows.append([identifier, discovery['report_sha256'], profile['url'], history[-1] if history else None])
            if offset <= total < offset + limit:
                if providers is None: providers = provider_window(connection, discovery, enrichment_repo)
                row = review_in(connection, discovery, profile['url'], state, enrichment_repo, provider_records=providers)
                row.pop('review_history')
                rows.append(row)
            total += 1
    return {'records': rows, 'total_count': total, 'offset': offset, 'limit': limit,
            'has_more': offset + len(rows) < total, 'stored_data_only': True,
            'snapshot_id': fingerprint([POLICY, digest_rows, rows]),
            'notes': ['En son tamamlanmış firma keşfi gösterilir; devam eden çalışma önceki kanıtı silmez.',
                      'Profil varlığı, sağlayıcı kanıtı ve insan kararı ayrı kayıtlardır.']}


class SQLiteSocialTrackingRepository:
    def __init__(self, path):
        self.path = path
        self.storage = SQLiteAssetRepository(path)

    def read(self, operation, request):
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = audit(connection)[0]
            if operation == 'brand.review.list': return review_list_in(connection, self.path, state=state, **request)
            if operation == 'brand.review.show':
                return {'record': review_in(connection, discovery_in(connection, request['discovery_id']),
                    request['url'], state, SQLiteSocialEnrichmentRepository(self.path))}
            if operation == 'brand.tracking.list':
                rows = sorted(state['watches'].values(), key=lambda r: (r['name'], r['id']))
                offset, limit = request['offset'], request['limit']
                return {'records': [public_watch(row) for row in rows[offset:offset + limit]], 'total_count': len(rows),
                        'offset': offset, 'limit': limit, 'has_more': offset + limit < len(rows)}
            identifier = request['identifier']
            rows = notifications_in(connection, state) if operation == 'brand.change.show' else state[
                'runs' if operation == 'brand.tracking.run.show' else 'watches']
            if identifier not in rows: raise SocialDiscoveryError('not_found', 'Sosyal kayıt bu çalışma alanında bulunamadı.')
            record = public_watch(rows[identifier]) if operation == 'brand.tracking.show' else rows[identifier]
            return {'record': record}

    def write(self, operation, request, at):
        request = dict(request); key = history_key(request.pop('idempotency_key')); mention_time(at)
        with self.storage._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                state, chain, previous_at = audit(connection)
                notifications_in(connection, state)
                for event in state['events'].values():
                    if event['key'] == key:
                        if event['operation'] != operation or event['request'] != request:
                            raise SocialDiscoveryError('idempotency_conflict', 'Tekrar anahtarı farklı sosyal işleme ait.')
                        record = state['runs'][event['id']] if operation == 'brand.tracking.run' else state['responses'][event['id']]
                        connection.rollback()
                        return {'record': record, 'replayed': True}
                if previous_at is not None and at < previous_at:
                    raise SocialDiscoveryError('clock_regressed', 'Saat kayıt geçmişinin gerisinde; işlem yapılmadı.')
                count, size = _bounded(connection, 'social_tracking_journal', 'LENGTH(request_json)+LENGTH(request_key)+LENGTH(operation)+256')
                text = canonical(request)
                if count >= MAX_EVENTS or size + len(text) + 512 > MAX_BYTES:
                    raise StorageError('Sosyal izleme günlük kapasitesi doldu.')
                did = request.get('discovery_id')
                discovery = discovery_in(connection, did) if did else None
                rid = str(uuid4()); dsha = discovery['report_sha256'] if discovery else None
                event = {'id': rid, 'key': key, 'operation': operation, 'request': request, 'recorded_at': at}
                result = apply_event(state, event, discovery)
                chain = fingerprint([POLICY, chain, count + 1, rid, key, operation, request, did, dsha, at])
                connection.execute('INSERT INTO social_tracking_journal '
                    '(id,request_key,operation,request_json,discovery_id,discovery_sha256,chain_sha256,recorded_at) VALUES (?,?,?,?,?,?,?,?)',
                    (rid, key, operation, text, did, dsha, chain, at))
                if operation == 'brand.tracking.finish':
                    count, _ = _bounded(connection, 'social_tracking_notifications', '256')
                    if count + len(result['changes']) > MAX_EVENTS: raise StorageError('Sosyal bildirim kapasitesi doldu.')
                    for change in result['changes']:
                        connection.execute('INSERT INTO social_tracking_notifications '
                            '(sequence,id,run_id,change_id,created_at) VALUES (?,?,?,?,?)',
                            (next_notification_sequence(connection), notification_id(result['id'], change['id']), result['id'], change['id'], at))
                notifications_in(connection, state)
                connection.commit()
                return {'record': result, 'replayed': False}
            except BaseException:
                connection.rollback(); raise


def case_snapshot(connection, path, evidence_id):
    from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
    try:
        identifier, url_hash = evidence_id.split(':')
        mention_uuid(identifier)
    except (ValueError, ValidationError) as error:
        raise ValidationError('Sosyal vaka kanıtı keşif-kimliği:profil-özeti biçiminde olmalı.') from error
    discovery = discovery_in(connection, identifier)
    profile = next((r for r in (discovery['report'] or {}).get('profiles', []) if fingerprint(r['url']) == url_hash), None)
    if profile is None: raise SocialDiscoveryError('not_found', 'Sosyal vaka profil kanıtı bulunamadı.')
    view = review_in(connection, discovery, profile['url'], audit(connection)[0], SQLiteSocialEnrichmentRepository(path))
    payload = {key: view[key] for key in ('domain', 'discovery_id', 'report_sha256', 'profile', 'provider_evidence', 'review_history')}
    payload.update(kind='social_discovery_evidence', version=1, scope=discovery['scope'], limitations=[
        'Seçilen keşif ve ek kanıtın vakaya ekleme anındaki kopyasıdır; sonraki tarama bunu değiştirmez.',
        'Profil varlığı veya sağlayıcı kaydı marka sahipliği/taklit hükmü değildir; karar insana aittir.',
        'Ek sağlayıcı kapsamı bu keşfin son 20 işlemidir; eski kayıtlar ayrıca açılabilir.' if view['provider_evidence_truncated'] else 'İlgili ek sağlayıcı geçmişi tamdır.'])
    validate_case_snapshot(payload)
    text, checksum = canonical_snapshot(payload)
    return CaseEvidenceSnapshot('social_discovery', evidence_id, f"{view['domain']} | {profile['platform']} | {profile['state']}",
                                'brand review-show ' + identifier + ' --url ' + profile['url'], text, checksum)
