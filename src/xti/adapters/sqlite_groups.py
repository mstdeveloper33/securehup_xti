"""Company-scoped group proof, decision and polling in one SQLite snapshot."""
import json
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.compressed_evidence import resolve_payload, journal_bytes
from xti.domain.assets import ValidationError
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.group_ledger import project, summary, MAX_ENTRIES, MAX_BYTES
from xti.domain.research import research_query, build_research, identity
from xti.domain.research_groups import groups, NOTES
from xti.domain.reports import ReportError


def read_groups(connection, *, change_proofs=None):
    if not ResearchReadBudget(connection, set(), rows=MAX_ENTRIES, size=MAX_BYTES).admit(('research_group_journal',), 'group_budget'):
        raise StorageError('Grup günlüğü okuma sınırını aşıyor; eksik başarı üretilmedi.')
    entries, chain = [], None
    try:
        for sequence, rid, subject, key, operation, text, checksum, next_chain in connection.execute(
                'SELECT sequence,id,subject_id,request_key,operation,payload_json,payload_sha256,chain_sha256 FROM research_group_journal ORDER BY sequence'):
            text = resolve_payload(connection, 'research_group_journal', sequence, text, checksum)
            if sequence != len(entries) + 1 or digest(text) != checksum or identity(chain, checksum) != next_chain:
                raise ValueError('Group chain')
            row = json.loads(text)
            if canonical_json(row) != text or (rid, subject, key, operation) != (row['id'], row['subject_id'], row['request']['idempotency_key'], row['operation']):
                raise ValueError('Group metadata')
            entries.append(row); chain = next_chain
        allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='research_group_journal'").fetchone()
        if (allocated is None and entries) or (allocated is not None and allocated[0] != len(entries)):
            raise ValueError('Deleted group tail')
        return project(entries, change_proofs=change_proofs), entries, chain
    except (ValidationError, ReportError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise StorageError('Grup günlüğü veya kanıtı bozuk; işlem durduruldu.') from error


def preview_in(connection, path, options, at):
    from xti.adapters.sqlite_research import _Reader
    query = research_query(indicator_type=options['indicator_type'], value=options['value'], max_hops=options['max_hops'])
    reader = _Reader(path, connection, at)
    graph = build_research(reader, query, at, paginate=False)
    if reader.audit_attack:
        reader.knowledge._audit_attack_source(connection)
    from xti.domain.research_reports import parse_document_id
    text_hashes = {}
    for node in graph.nodes:
        if node.key[0] == 'report_document':
            rid, revision = parse_document_id(node.key[1])
            # Reuse the already audited, bounded report read in this transaction.
            document = reader.report_context.records[rid]['documents'][revision - 1]['document']
            text_hashes[node.key[1]] = digest(document['text'])
    result, limitations, omitted = groups(graph, time_window_hours=options['time_window_hours'], report_text_hashes=text_hashes)
    return result, {'coverage_complete': not limitations, 'limitations': limitations, 'omitted_group_count': omitted,
        'evidence_snapshot_id': graph.snapshot_id, 'stored_data_only': True, 'notes': NOTES}


def read(connection, path, operation, options, at):
    from xti.adapters.sqlite_evidence import page
    if operation in ('groups.notifications', 'groups.notification-show'):
        from xti.adapters.sqlite_group_notifications import read_notifications
        notifications = read_notifications(connection)[0]
        if operation == 'groups.notification-show':
            row = notifications.get(options['identifier'])
            if row is None:
                raise ReportError('not_found', 'Grup bildirimi seçili çalışma alanında bulunamadı.')
            return {'notification': row, 'notes': NOTES}
        rows = [{'id': row['id'], 'group_id': row['snapshot']['group_id'], 'created_at': row['created_at'],
            'read_at': row['read_at'], 'snapshot_sha256': row['snapshot_sha256'],
            'change': row['snapshot']['change']} for row in sorted(notifications.values(), key=lambda r: r['sequence'], reverse=True)]
        return page(rows, options, 'group-notifications', extra={'notes': NOTES})
    records = read_groups(connection)[0]
    if operation == 'groups.show':
        record = records.get(options['identifier'])
        if record is None:
            raise ReportError('not_found', 'Grup seçili çalışma alanında bulunamadı.')
        return {'model_version': 1, 'record': record, 'notes': NOTES}
    if operation == 'groups.preview':
        rows, extra = preview_in(connection, path, options, at)
        for row in rows:
            row['saved'] = summary(records[row['id']]) if row['id'] in records else None
        return page(rows, options, {k: options[k] for k in ('indicator_type', 'value', 'max_hops', 'time_window_hours')}, extra=extra)
    saved = [summary(records[key]) for key in sorted(records)]
    if operation == 'groups.list':
        return page(saved, options, 'saved-groups', extra={'notes': NOTES})
    # Queue scans a bounded record window, sharing the same read snapshot.
    selected = page(saved, options, 'group-queue-records')
    cache, result = {}, []
    for row in selected['records']:
        record = records[row['id']]
        group = record['group']
        key = canonical_json([group['root'], group['scope']])
        if key not in cache:
            cache[key] = preview_in(connection, path,
                dict(indicator_type=group['root'][0], value=group['root'][1], **group['scope']), at)
        candidates, extra = cache[key]
        current = next((candidate for candidate in candidates if candidate['id'] == record['id']), None)
        state = ('indeterminate' if not extra['coverage_complete'] else 'not_in_view' if current is None else
                 'changed' if current['evidence_sha256'] != group['evidence_sha256'] else
                 'needs_review' if not record['review_current'] else 'current')
        if state != 'current':
            result.append({**row, 'queue_state': state, 'current_evidence_sha256': current['evidence_sha256'] if current else None,
                'coverage_complete': extra['coverage_complete'], 'limitations': extra['limitations']})
    return {**selected, 'records': result, 'examined_count': len(selected['records']),
        'pagination_basis': 'saved_groups_examined', 'pending_in_window': len(result),
        'notes': NOTES + ['Sayfalama saklı grup listesini sabitler; kanıt her pencerede yeniden okunur. Boş pencere sonraki sayfa yok demek değildir.']}


def mutate(connection, path, operation, request, at):
    records, entries, chain = read_groups(connection)
    for index, entry in enumerate(entries):
        if entry['request']['idempotency_key'] == request['idempotency_key']:
            if (entry['operation'], entry['request']) != (operation, request):
                raise ReportError('idempotency_conflict', 'Tekrar anahtarı başka grup işlemine bağlı.')
            return {'replayed': True, 'record': project(entries[:index + 1])[entry['subject_id']]}
    previous = records.get(request['identifier'])
    if operation != 'groups.capture' and previous is None:
        raise ReportError('not_found', 'Grup seçili çalışma alanında bulunamadı.')
    if request['expected_revision'] != (previous['revision'] if previous else 0):
        raise ReportError('revision_changed', 'Grup sürümü değişmiş; güncel kaydı alın.')
    limitations = []
    if operation == 'groups.review' and request['decision'] == 'withdrawn':
        snapshot = previous['group']
    else:
        options = request if operation == 'groups.capture' else dict(indicator_type=previous['group']['root'][0],
            value=previous['group']['root'][1], **previous['group']['scope'])
        candidates, extra = preview_in(connection, path, options, at)
        snapshot = next((row for row in candidates if row['id'] == request['identifier']), None)
        if operation == 'groups.refresh':
            limitations = extra['limitations']
        elif snapshot is None or snapshot['evidence_sha256'] != request['evidence_sha256']:
            raise ReportError('source_changed', 'Grup kanıtı değişmiş veya görünümde yok; güncel önizlemeyi alın.')
        if operation == 'groups.review' and snapshot != previous['group']:
            raise ReportError('source_changed', 'Önce grubun güncel kanıtını refresh ile kaydedin.')
    entry = {'version': 1, 'id': str(uuid4()), 'subject_id': request['identifier'], 'operation': operation,
        'request': request, 'recorded_at': at, 'snapshot': snapshot, 'limitations': limitations}
    proofs = {}
    record = project([*entries, entry], change_proofs=proofs)[request['identifier']]
    payload = canonical_json(entry)
    size = journal_bytes(connection, 'research_group_journal')
    if len(entries) >= MAX_ENTRIES or size + len(payload) + 512 > MAX_BYTES:
        raise ValidationError('Grup günlüğü 10000 olay / 64 MiB sınırını aşıyor; önceki kayıt korunur.')
    checksum = digest(payload)
    connection.execute('INSERT INTO research_group_journal (id,subject_id,request_key,operation,payload_json,payload_sha256,chain_sha256) VALUES (?,?,?,?,?,?,?)',
        (entry['id'], entry['subject_id'], request['idempotency_key'], operation, payload, checksum, identity(chain, checksum)))
    if entry['id'] in proofs:
        from xti.adapters.sqlite_group_notifications import emit
        emit(connection, proofs[entry['id']], proofs=proofs)
    return {'replayed': False, 'record': record}


def case_snapshot(connection, identifier):
    from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
    from xti.domain.group_ledger import case_payload
    record = read_groups(connection)[0].get(identifier)
    if record is None:
        raise ReportError('not_found', 'Grup seçili çalışma alanında bulunamadı.')
    payload, checksum = canonical_snapshot(case_payload(record))
    return CaseEvidenceSnapshot('research_group', identifier, f"{record['group']['root'][1]} — {record['group']['rule']}"[:1000],
        'groups show ' + identifier, payload, checksum)
