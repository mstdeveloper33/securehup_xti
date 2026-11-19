"""Atomic capture from audited local sources; never fetch a report URL."""

from dataclasses import asdict
import json
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.compressed_evidence import resolve_payload, journal_bytes
from xti.adapters.sqlite_ioc_lifecycle import SQLiteIocLifecycleRepository, _budget
from xti.domain.assets import ValidationError
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.research import identity
from xti.domain.reports import document, project, report_view, ReportError, MAX_ENTRIES, MAX_BYTES, validate_target


def read_reports(connection, *, audit_fetches=True):
    if not ResearchReadBudget(connection, set(), rows=MAX_ENTRIES, size=MAX_BYTES).admit(('report_journal',), 'report_budget'):
        raise StorageError('Rapor günlüğü okuma sınırını aşıyor; eksik sonuç üretilmedi.')
    entries, chain = [], None
    try:
        for sequence, identifier, report_id, key, operation, payload, sha, next_chain in connection.execute(
                'SELECT sequence,id,report_id,request_key,operation,payload_json,payload_sha256,chain_sha256 '
                'FROM report_journal ORDER BY sequence'):
            payload = resolve_payload(connection, 'report_journal', sequence, payload, sha)
            if sequence != len(entries) + 1 or digest(payload) != sha or identity(chain, sha) != next_chain:
                raise ValueError('Broken journal chain')
            entry = json.loads(payload)
            if canonical_json(entry) != payload or (identifier, report_id, key, operation) != (
                    entry['id'], entry['report_id'], entry['request_key'], entry['operation']):
                raise ValueError('Journal metadata mismatch')
            entries.append(entry)
            chain = next_chain
        allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='report_journal'").fetchone()
        if (allocated is None and entries) or (allocated is not None and allocated[0] != len(entries)):
            raise ValueError('Deleted journal tail')
        records = project(entries)
        from xti.adapters.sqlite_publisher_documents import check_objects
        check_objects(connection, (item['document'] for row in records.values() for item in row['documents']))
        if audit_fetches:
            from xti.adapters.sqlite_publisher_documents import read_fetches
            read_fetches(connection, report_entries=entries)
        return records, entries, chain
    except (ValidationError, KeyError, TypeError, ValueError, OverflowError, RecursionError) as error:
        raise StorageError('Rapor günlüğü bozuk; işlem durduruldu.') from error


def resolve_document(connection, source, identifier):
    # Preflight before the existing catalog audits decode source payloads.
    prefix = 'news_' if source == 'news' else 'mentions_'
    tables = tuple(row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")
                   if row[0].startswith(prefix))
    if not ResearchReadBudget(connection, set(), rows=20000, size=MAX_BYTES).admit(tables, 'report_source_budget'):
        raise StorageError('Rapor kaynak kanıtı okuma sınırını aşıyor.')
    if source == 'news':
        from xti.adapters.sqlite_news import read_news_catalog
        catalog = read_news_catalog(connection)
        stored = next((r for r in catalog.articles if r.article.id == identifier), None)
        if stored is None:
            raise ReportError('not_found', 'Haber kaydı seçili çalışma alanında bulunamadı.')
        item = stored.article
        fetched = connection.execute('SELECT fetched_at FROM news_runs WHERE id=?', (stored.last_change_run_id,)).fetchone()[0]
        extra = dict(provider=item.source_key, published_raw=item.published_raw,
                     published_normalized=item.published_at, source_updated_at=item.updated_at, collected_at=fetched, scope=[])
    else:
        from xti.adapters.sqlite_mentions import read_mentions_catalog
        catalog = read_mentions_catalog(connection)
        stored = next((r for r in catalog.records if r.id == identifier), None)
        if stored is None:
            raise ReportError('not_found', 'Firma içeriği seçili çalışma alanında bulunamadı.')
        item = stored.hit
        run = next(r for r in catalog.runs if r.id == stored.last_change_run_id)
        extra = dict(provider='tavily', published_raw=item.published_at, published_normalized=None,
                     source_updated_at=None, collected_at=run.finished_at, scope=list(stored.request.target.domains))
    return document(source=source, source_record_id=identifier, source_reference=item.url,
        title=item.title, summary=item.summary, summary_truncated=item.summary_truncated,
        source_run_id=stored.last_change_run_id, source_sha256=stored.state_sha256, **extra)


class SQLiteReportRepository:
    def __init__(self, path):
        self.storage = SQLiteAssetRepository(path)
        self.ioc = SQLiteIocLifecycleRepository(path)

    def read(self):
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            return read_reports(connection)[0]

    def evidence(self, indicator_type, value):
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            return read_reports(connection)[0], self.ioc.read_in(connection, indicator_type, value)

    def _target(self, connection, kind, identifier):
        from xti.adapters.sqlite_cti_context import _audit_assertion_history
        from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
        budget = MAX_BYTES
        # Scope budgets to the selected target, never to the complete IOC/ATT&CK catalog.
        table = 'cti_entities' if kind == 'entity' else 'cti_indicators'
        prefix = 'cti_entity' if kind == 'entity' else 'cti_indicator'
        foreign = 'entity_id' if kind == 'entity' else 'indicator_id'
        budget = _budget(connection, table, 'id=?', (identifier,), 1, budget)
        budget = _budget(connection, prefix + '_assertions', foreign + '=?', (identifier,), 500, budget)
        _budget(connection, prefix + '_assertion_events',
                f'assertion_id IN (SELECT id FROM {prefix}_assertions WHERE {foreign}=?)', (identifier,), 10000, budget)
        if kind == 'entity':
            if not connection.execute('SELECT 1 FROM cti_entities WHERE id=?', (identifier,)).fetchone():
                raise ReportError('not_found', 'CTI hedefi seçili çalışma alanında bulunamadı.')
            details = SQLiteCtiKnowledgeRepository(self.storage.path)._entity_details(connection, identifier, 500, 10000)
            _audit_assertion_history(connection, details, 'entity')
            target_type, label = details.entity.entity_type, details.entity.display_name
        else:
            row = connection.execute('SELECT indicator_type,value FROM cti_indicators WHERE id=?', (identifier,)).fetchone()
            if row is None:
                raise ReportError('not_found', 'IOC hedefi seçili çalışma alanında bulunamadı.')
            details = self.ioc.read_in(connection, *row).details
            target_type, label = details.indicator.indicator_type, details.indicator.value
        result = {'kind': kind, 'id': identifier, 'type': target_type, 'label': label,
                  'assertion_ids': sorted(c.id for c in details.assertions if c.active),
                  'state_sha256': identity(asdict(details))}
        validate_target(result)
        return result

    def fetch_replay(self, request):
        from xti.adapters.sqlite_publisher_documents import fetch_replay
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            return fetch_replay(connection, request)

    def fetches(self):
        from xti.adapters.sqlite_publisher_documents import read_fetches
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            return read_fetches(connection)[0]

    def record_fetch(self, request, fetched, error, at):
        from xti.adapters.sqlite_publisher_documents import record_fetch
        with self.storage._connection() as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            return record_fetch(self, connection, request, fetched, error, at)

    def mutate(self, operation, request, at):
        with self.storage._connection() as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            from xti.adapters.sqlite_publisher_documents import read_fetches
            if any(row['request']['idempotency_key'] == request['idempotency_key'] for row in read_fetches(connection)[0]):
                raise ReportError('idempotency_conflict', 'Tekrar anahtarı yayıncı işlemine bağlı.')
            return self._mutate_in(connection, operation, request, at)

    def _mutate_in(self, connection, operation, request, at, fetched_document=None):
        records, entries, chain = read_reports(connection)
        key = request['idempotency_key']
        for index, entry in enumerate(entries):
            if entry['request_key'] != key:
                continue
            if (entry['operation'], entry['request']) != (operation, request):
                raise ReportError('idempotency_conflict', 'Tekrar anahtarı başka bir rapor isteğine bağlı.')
            record = project(entries[:index + 1])[entry['report_id']]
            return {'action': 'changed' if entry['payload'] is not None else 'unchanged',
                    'replayed': True, 'record': report_view(record)}
        if len(entries) >= MAX_ENTRIES:
            raise ValidationError('Rapor günlüğü kapasitesi doldu.')
        if operation in ('reports.capture', 'reports.fetch'):
            payload = fetched_document if operation == 'reports.fetch' else resolve_document(connection, request['source'], request['identifier'])
            if request.get('expected_content_sha256', payload['content_sha256']) != payload['content_sha256']:
                raise ReportError('source_changed', 'Seçilen kaynak metni değişmiş; rapor seçimini yenileyin.')
            source_key = [payload['source'], payload['source_record_id']]
            record = next((r for r in records.values() if r['source_key'] == source_key), None)
            rid = record['id'] if record is not None else str(uuid4())
            if record is not None and record['documents'][-1]['document']['content_sha256'] == payload['content_sha256']:
                payload = None
        else:
            rid = request['identifier']
            record = records.get(rid)
            if record is None:
                raise ReportError('not_found', 'Rapor seçili çalışma alanında bulunamadı.')
            if request['expected_revision'] != record['revision']:
                raise ReportError('revision_changed', 'Rapor değişmiş; güncel sürümü yeniden alın.')
            selected = request.get('document_revision', len(record['documents']))
            if selected > len(record['documents']):
                raise ReportError('not_found', 'Bağlanacak rapor belge sürümü bulunamadı.')
            old = record['links'].get(identity(selected, request['target_kind'], request['target_id']))
            if old is not None and all(old[k] == request[k] for k in ('state', 'reason')):
                payload = None
            elif request['state'] == 'withdrawn':
                if old is None:
                    raise ValidationError('Geri çekilecek mevcut rapor bağlantısı gerekli.')
                payload = old['target']
            else:
                payload = self._target(connection, request['target_kind'], request['target_id'])
        entry = {'version': 1, 'id': str(uuid4()), 'report_id': rid, 'request_key': key,
                 'operation': operation, 'request': request, 'recorded_at': at, 'payload': payload}
        record = project([*entries, entry])[rid]
        text = canonical_json(entry)
        size = journal_bytes(connection, 'report_journal')
        if size + len(text.encode('utf-8')) + 512 > MAX_BYTES:
            raise ValidationError('Rapor günlüğü byte kapasitesi doldu.')
        connection.execute('INSERT INTO report_journal (id,report_id,request_key,operation,payload_json,payload_sha256,chain_sha256) '
            'VALUES (?,?,?,?,?,?,?)', (entry['id'], rid, key, operation, text, digest(text), identity(chain, digest(text))))
        return {'action': 'changed' if payload is not None else 'unchanged', 'replayed': False, 'record': report_view(record)}
