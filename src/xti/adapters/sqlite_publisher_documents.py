"""Atomic publisher receipts, original object hashes and immutable report capture."""
import hashlib
import json
from uuid import uuid4
import zlib

from xti.adapters.sqlite import StorageError
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.compressed_evidence import unpack
from xti.domain.assets import ValidationError
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.research import identity
from xti.domain.reports import ReportError, project, report_view, sha
from xti.domain.publisher_documents import full_document, MAX_STORED_BODY_BYTES
from xti.domain.report_contract import parameters
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.cti_indicators import normalize_cti_timestamp

MAX_OBJECT_BYTES = 64 * 1024 * 1024
MAX_RUNS = 10000
MAX_RUN_BYTES = 16 * 1024 * 1024


def check_objects(connection, documents):
    if connection.execute('SELECT 1 FROM publisher_objects WHERE typeof(raw_size) != ? OR raw_size < 1 OR raw_size > ? '
            'OR typeof(body) != ? OR LENGTH(body) > ? LIMIT 1', ('integer', MAX_STORED_BODY_BYTES, 'blob', MAX_STORED_BODY_BYTES + 4096)).fetchone():
        raise StorageError('Yayıncı özgün nesne boyutu veya biçimi geçersiz.')
    count, size, packed = connection.execute('SELECT COUNT(*),COALESCE(SUM(raw_size),0),COALESCE(SUM(LENGTH(body)),0) FROM publisher_objects').fetchone()
    if count > MAX_RUNS or size > MAX_OBJECT_BYTES or packed > MAX_OBJECT_BYTES + 4096 * count:
        raise StorageError('Yayıncı özgün nesne kapasitesi aşılıyor.')
    checked = set()
    for doc in documents:
        if doc['model_version'] != 2 or doc['source_sha256'] in checked:
            continue
        row = connection.execute('SELECT raw_size,body FROM publisher_objects WHERE sha256=?', (doc['source_sha256'],)).fetchone()
        if row is None or row[0] != doc['acquisition']['body_bytes']:
            raise StorageError('Yayıncı raporunun özgün kaynak nesnesi eksik veya farklı.')
        unpack(row[1], row[0], doc['source_sha256'], maximum=MAX_STORED_BODY_BYTES)
        checked.add(doc['source_sha256'])


def read_fetches(connection, *, report_entries=None):
    from xti.adapters.sqlite_reports import read_reports
    if not ResearchReadBudget(connection, set(), rows=MAX_RUNS, size=MAX_RUN_BYTES).admit(('publisher_fetch_runs',), 'publisher_budget'):
        raise StorageError('Yayıncı çalışma günlüğü sınırı aşılıyor.')
    rows, chain, previous = [], None, None
    entries = read_reports(connection, audit_fetches=False)[1] if report_entries is None else report_entries
    by_key = {entry['request_key']: entry for entry in entries}
    current_documents, entry_documents, checked_objects = {}, {}, set()
    for entry in entries:
        if entry['operation'] in ('reports.capture', 'reports.fetch') and entry['payload'] is not None:
            current_documents[entry['report_id']] = entry['payload']
        if entry['operation'] == 'reports.fetch':
            entry_documents[entry['id']] = current_documents[entry['report_id']]
    try:
        for seq, rid, key, payload, checksum, next_chain in connection.execute('SELECT sequence,id,request_key,payload_json,payload_sha256,chain_sha256 FROM publisher_fetch_runs ORDER BY sequence'):
            if seq != len(rows) + 1 or digest(payload) != checksum or identity(chain, checksum) != next_chain:
                raise ValueError('Receipt chain')
            row = json.loads(payload)
            if canonical_json(row) != payload or set(row) != {'id', 'request', 'recorded_at', 'status', 'error', 'entry_id', 'body_sha256', 'body_bytes'}:
                raise ValueError('Receipt shape')
            normalize_knowledge_id(rid)
            if row['id'] != rid or row['request'] != parameters('reports.fetch', row['request'], scoped=False, stored=True) or key != row['request']['idempotency_key']:
                raise ValueError('Receipt request')
            at = normalize_cti_timestamp(row['recorded_at'])
            if at != row['recorded_at'] or previous is not None and at < previous:
                raise ValueError('Receipt time')
            entry = by_key.get(key)
            if row['status'] == 'complete':
                sha(row['body_sha256'])
                if (row['error'] is not None or entry is None or entry['id'] != row['entry_id'] or entry['operation'] != 'reports.fetch' or
                        entry['request'] != row['request'] or entry['recorded_at'] != at or type(row['body_bytes']) is not int or
                        not 1 <= row['body_bytes'] <= MAX_STORED_BODY_BYTES):
                    raise ValueError('Receipt document link')
                obj = connection.execute('SELECT raw_size,body FROM publisher_objects WHERE sha256=?', (row['body_sha256'],)).fetchone()
                if obj is None or obj[0] != row['body_bytes']:
                    raise ValueError('Receipt object')
                if row['body_sha256'] not in checked_objects:
                    unpack(obj[1], obj[0], row['body_sha256'], maximum=MAX_STORED_BODY_BYTES)
                    checked_objects.add(row['body_sha256'])
                if entry_documents[entry['id']]['source_sha256'] != row['body_sha256']:
                    raise ValueError('Unchanged receipt source')
                if entry['payload'] is not None and (entry['payload']['source_run_id'] != rid or entry['payload']['source_sha256'] != row['body_sha256']):
                    raise ValueError('Receipt source')
            elif row['status'] != 'failed' or entry is not None or any(row[k] is not None for k in ('entry_id', 'body_sha256', 'body_bytes')) or not isinstance(row['error'], str) or not 1 <= len(row['error']) <= 1000 or not row['error'].isprintable():
                raise ValueError('Failure receipt')
            rows.append(row); chain = next_chain; previous = at
        allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='publisher_fetch_runs'").fetchone()
        if allocated is not None and allocated[0] != len(rows) or allocated is None and rows:
            raise ValueError('Deleted receipt tail')
        successful = {row['entry_id'] for row in rows if row['status'] == 'complete'}
        if any(entry['operation'] == 'reports.fetch' and entry['id'] not in successful for entry in entries):
            raise ValueError('Missing publisher receipt')
        return rows, entries, chain
    except (KeyError, ValueError, TypeError, ValidationError, RecursionError) as error:
        raise StorageError('Yayıncı çalışma kanıtı tutarsız; eksik sonuç üretilmedi.') from error


def _response(row, entries, replayed):
    if row['status'] == 'failed':
        return {'run': row, 'replayed': replayed}
    index = next(i for i, entry in enumerate(entries) if entry['id'] == row['entry_id'])
    entry = entries[index]
    record = project(entries[:index + 1])[entry['report_id']]
    return {'run': row, 'replayed': replayed, 'record': report_view(record), 'action': 'changed' if entry['payload'] is not None else 'unchanged'}


def fetch_replay(connection, request):
    rows, entries, _ = read_fetches(connection)
    for row in rows:
        if row['request']['idempotency_key'] == request['idempotency_key']:
            if row['request'] != request:
                raise ReportError('idempotency_conflict', 'Tekrar anahtarı farklı yayıncı isteğine bağlı.')
            return _response(row, entries, True)
    if any(entry['request_key'] == request['idempotency_key'] for entry in entries):
        raise ReportError('idempotency_conflict', 'Tekrar anahtarı farklı rapor isteğine bağlı.')
    if len(rows) >= MAX_RUNS:
        raise ValidationError('Yayıncı çalışma kapasitesi doldu.')
    return None


def record_fetch(repository, connection, request, fetched, error, at):
    replay = fetch_replay(connection, request)
    if replay is not None:
        return replay
    rows, entries, chain = read_fetches(connection)
    rid = str(uuid4())
    receipt = {'id': rid, 'request': request, 'recorded_at': at, 'status': 'failed' if error is not None else 'complete',
        'error': error, 'entry_id': None, 'body_sha256': None, 'body_bytes': None}
    if error is not None:
        receipt['error'] = ' '.join(str(error).split())[:1000]
        if not receipt['error'] or not receipt['error'].isprintable():
            receipt['error'] = 'Yayıncı alınamadı; önceki belge korundu.'
    else:
        doc = full_document(fetched, rid)
        if doc['provider'] != request['provider'] or doc['source_reference'] != request['url']:
            raise ValidationError('Yayıncı yanıtı farklı isteğe ait.')
        total = connection.execute('SELECT COALESCE(SUM(raw_size),0) FROM publisher_objects').fetchone()[0]
        if not connection.execute('SELECT 1 FROM publisher_objects WHERE sha256=?', (doc['source_sha256'],)).fetchone():
            if total + len(fetched.body) > MAX_OBJECT_BYTES:
                raise ValidationError('Yayıncı özgün nesne kapasitesi 64 MiB sınırında.')
            connection.execute('INSERT INTO publisher_objects VALUES (?,?,?)', (doc['source_sha256'], len(fetched.body), zlib.compress(fetched.body, 6)))
        repository._mutate_in(connection, 'reports.fetch', request, at, doc)
        entry_id = connection.execute('SELECT id FROM report_journal WHERE request_key=?', (request['idempotency_key'],)).fetchone()[0]
        receipt.update(entry_id=entry_id, body_sha256=doc['source_sha256'], body_bytes=len(fetched.body))
    text = canonical_json(receipt)
    current_size = connection.execute('SELECT COALESCE(SUM(LENGTH(payload_json)+512),0) FROM publisher_fetch_runs').fetchone()[0]
    if current_size + len(text) + 512 > MAX_RUN_BYTES:
        raise ValidationError('Yayıncı çalışma byte kapasitesi doldu.')
    connection.execute('INSERT INTO publisher_fetch_runs (id,request_key,payload_json,payload_sha256,chain_sha256) VALUES (?,?,?,?,?)',
        (rid, request['idempotency_key'], text, digest(text), identity(chain, digest(text))))
    checked, entries, _ = read_fetches(connection)
    return _response(checked[-1], entries, False)
