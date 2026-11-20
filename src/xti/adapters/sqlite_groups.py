"""Company-scoped group proof, decision and polling in one SQLite snapshot."""
import json
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.compressed_evidence import resolve_payload
from xti.domain.assets import ValidationError
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.group_ledger import project, MAX_ENTRIES, MAX_BYTES
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
    from xti.adapters.sqlite_group_reads import read as indexed_read
    return indexed_read(connection, path, operation, options, at)


def mutate(connection, path, operation, request, at):
    from xti.adapters.sqlite_group_projection import guard, current, event_row, state_at, full_record, store, seal, JOURNAL_COLUMNS
    from xti.domain.group_state import transition
    mode = request.get('response_mode', 'full')
    request = {key: value for key, value in request.items() if key != 'response_mode'}
    state = guard(connection)
    existing = connection.execute(f'SELECT {JOURNAL_COLUMNS} FROM research_group_journal WHERE request_key=?', (request['idempotency_key'],)).fetchone()
    if existing is not None:
        entry = event_row(connection, existing)
        original_request = {key: value for key, value in entry['request'].items() if key != 'response_mode'}
        if (entry['operation'], original_request) != (operation, request):
            raise ReportError('idempotency_conflict', 'Tekrar anahtarı başka grup işlemine bağlı.')
        record = state_at(connection, entry['id'])
        if mode == 'full':
            record = full_record(connection, entry['subject_id'], revision=record['revision'])
        return {'replayed': True, 'record': record}
    previous = current(connection, request['identifier'], required=operation != 'groups.capture')
    if request['expected_revision'] != (previous['revision'] if previous else 0):
        raise ReportError('revision_changed', 'Grup sürümü değişmiş; güncel kaydı alın.')
    if mode == 'full' and previous and previous['revision'] >= 1000:
        raise ReportError('history_requires_pagination', 'Güncel sonuç için --response-mode current kullanın; geçmiş groups history ile sayfalanır.')
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
    if previous and snapshot == previous['group']:
        snapshot = {'same_as_previous': digest(canonical_json(snapshot))}
    entry = {'version': 2, 'id': str(uuid4()), 'subject_id': request['identifier'], 'operation': operation,
        'request': request, 'recorded_at': at, 'snapshot': snapshot, 'limitations': limitations}
    record, proof = transition(previous, entry)
    payload = canonical_json(entry)
    checksum = digest(payload)
    connection.execute('INSERT INTO research_group_journal (id,subject_id,request_key,operation,payload_json,payload_sha256,chain_sha256) VALUES (?,?,?,?,?,?,?)',
        (entry['id'], entry['subject_id'], request['idempotency_key'], operation, payload, checksum, identity(state[3], checksum)))
    store(connection, record, entry, proof)
    if proof:
        from xti.adapters.sqlite_group_notifications import emit
        emit(connection, proof, proofs={entry['id']: proof})
    seal(connection, event_added=True, notice_added=proof is not None)
    if mode == 'full':
        record = full_record(connection, record['id'])
    return {'replayed': False, 'record': record}


def case_snapshot(connection, identifier):
    from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
    from xti.domain.group_ledger import case_payload
    from xti.adapters.sqlite_group_projection import guard, current
    guard(connection)
    record = current(connection, identifier)
    payload, checksum = canonical_snapshot(case_payload(record))
    return CaseEvidenceSnapshot('research_group', identifier, f"{record['group']['root'][1]} — {record['group']['rule']}"[:1000],
        ('groups current ' if record['state_version'] == 2 else 'groups show ') + identifier, payload, checksum)
