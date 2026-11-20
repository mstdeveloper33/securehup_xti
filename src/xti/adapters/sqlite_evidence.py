"""One transaction for source selection, decisions, idempotency and strict replay."""
import json
from uuid import uuid4
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.compressed_evidence import resolve_payload, journal_bytes
from xti.domain.assets import ValidationError
from xti.domain.evidence_ledger import project, sighting_key, MAX_ENTRIES, MAX_BYTES
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.reports import ReportError
from xti.domain.research import identity


def read_evidence(connection):
    if not ResearchReadBudget(connection, set(), rows=MAX_ENTRIES, size=MAX_BYTES).admit(('evidence_journal',), 'evidence_budget'):
        raise StorageError('Görülme/ilişki günlüğü okuma sınırını aşıyor; eksik sonuç üretilmedi.')
    entries, chain = [], None
    try:
        for seq, identifier, subject, key, operation, payload, sha, next_chain in connection.execute(
                'SELECT sequence,id,subject_id,request_key,operation,payload_json,payload_sha256,chain_sha256 FROM evidence_journal ORDER BY sequence'):
            payload = resolve_payload(connection, 'evidence_journal', seq, payload, sha)
            if seq != len(entries) + 1 or digest(payload) != sha or identity(chain, sha) != next_chain:
                raise ValueError('Broken evidence chain')
            row = json.loads(payload)
            if canonical_json(row) != payload or (identifier, subject, key, operation) != (
                    row['id'], row['subject_id'], row['request']['idempotency_key'], row['operation']):
                raise ValueError('Evidence metadata mismatch')
            entries.append(row); chain = next_chain
        allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='evidence_journal'").fetchone()
        if (allocated is None and entries) or (allocated is not None and allocated[0] != len(entries)):
            raise ValueError('Deleted evidence tail')
        return project(entries), entries, chain
    except (ValidationError, ReportError, KeyError, ValueError, TypeError, OverflowError, RecursionError) as error:
        raise StorageError('Görülme/ilişki günlüğü bozuk; işlem durduruldu.') from error


def page(rows, options, scope, *, extra=None):
    def stable(value):
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items() if key not in ('age_seconds', 'checked_at')}
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value
    snapshot = identity('evidence-page-v1', scope, stable(rows), stable(extra))
    if options.get('expected_snapshot') is not None and options['expected_snapshot'] != snapshot:
        raise ReportError('snapshot_changed', 'Kanıt veya karar değişmiş; ilk sayfayı yeniden alın.')
    start, limit = options['offset'], options['limit']
    return {'model_version': 1, 'records': rows[start:start + limit], 'total_count': len(rows),
        'offset': start, 'limit': limit, 'has_more': start + limit < len(rows),
        'next_offset': start + limit if start + limit < len(rows) else None, 'snapshot_id': snapshot,
        'consistency': 'single_read_snapshot', **(extra or {})}


def relationship_rows(connection, path, options, at):
    from xti.adapters.sqlite_research import _Reader
    from xti.domain.research import research_query, build_research
    from xti.domain.relationship_candidates import candidates
    query = research_query(indicator_type=options['indicator_type'], value=options['value'], max_hops=2, node_limit=100, edge_limit=200)
    reader = _Reader(path, connection, at)
    graph = build_research(reader, query, at, paginate=False)
    if reader.audit_attack:
        reader.knowledge._audit_attack_source(connection)
    return candidates(graph), graph


def sightings_for(records, options):
    return sorted((row for row in records.values() if row['kind'] == 'sighting' and
        (row['observation']['indicator_type'], row['observation']['value']) == (options['indicator_type'], options['value'])),
        key=lambda row: (row['observation']['observed_at'], row['id']), reverse=True)


def review_queue(connection, path, records, options, at, *, proofs=None):
    from xti.domain.relationship_review_queue import review_item
    scope = [options['indicator_type'], options['value']] if 'indicator_type' in options else None
    reviewed = sorted((row for row in records.values() if row['kind'] == 'relationship' and row['decision'] != 'withdrawn'
        and (scope is None or row['candidate']['root'] == scope)), key=lambda row: row['id'])
    snapshot = identity('relationship-review-set-v1', scope, [(row['id'], row['state_sha256']) for row in reviewed])
    if options.get('expected_snapshot') is not None and options['expected_snapshot'] != snapshot:
        raise ReportError('snapshot_changed', 'Karar listesi değişmiş; ilk pencereden yeniden başlayın.')
    start, limit = options['offset'], options['limit']
    window = reviewed[start:start + limit]
    cache, items, evidence_states = {}, [], []
    for record in window:
        root = tuple(record['candidate']['root'])
        if root not in cache:
            rows, graph = relationship_rows(connection, path, dict(indicator_type=root[0], value=root[1]), at)
            cache[root] = ({row['id']: row for row in rows}, graph.limitations)
        candidates, limitations = cache[root]
        current = candidates.get(record['id'])
        item = review_item(record, current, limitations)
        evidence_states.append([record['id'], current['evidence_sha256'] if current else None, sorted(limitations)])
        if item is not None:
            items.append(item)
    if proofs is not None:
        proofs.update(cache)
    more = start + len(window) < len(reviewed)
    return {'model_version': 1, 'records': items, 'pending_in_window': len(items), 'examined_count': len(window),
        'total_review_count': len(reviewed), 'offset': start, 'limit': limit, 'has_more': more,
        'next_offset': start + len(window) if more else None, 'snapshot_id': snapshot,
        'evidence_snapshot_id': identity('relationship-review-window-v1', evidence_states),
        'consistency': 'single_read_snapshot', 'pagination_basis': 'review_records_examined',
        'notes': ['Liste yalnız bu çalışma alanının saklı insan kararlarını tarar; kararları değiştirmez.',
            'Sayfa sınırı incelenen karar sayısıdır; sıfır bekleyen kayıt olsa da sonraki pencere olabilir.',
            'expected_snapshot karar listesini sabitler; kanıt her pencerede yeniden okunur. Sayfalar arası kanıt kesiti ortak değildir.',
            'Güncel dayanak ve beklenen karar sürümüyle relationships review yapılınca ilgili kayıt listeden çıkar.']}


class SQLiteEvidenceRepository:
    def __init__(self, path):
        self.storage = SQLiteAssetRepository(path)

    def read(self, operation, options, at):
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            if operation.startswith('groups.'):
                from xti.adapters.sqlite_groups import read
                return read(connection, self.storage.path, operation, options, at)
            if operation == 'relationships.notification-show':
                from xti.adapters.sqlite_relationship_notifications import get_notification
                return {'notification': get_notification(connection, options['identifier'])}
            if operation == 'identity.view':
                from xti.adapters.sqlite_identity_view import identity_view
                return identity_view(connection, self.storage.path, options['kind'], options['identifier'])
            records = read_evidence(connection)[0]
            if operation == 'relationships.queue':
                return review_queue(connection, self.storage.path, records, options, at)
            if operation.endswith('.show'):
                row = records.get(options['identifier'])
                kind = 'sighting' if operation == 'sightings.show' else 'relationship'
                if row is None or row['kind'] != kind:
                    raise ReportError('not_found', 'Kanıt kaydı seçili çalışma alanında bulunamadı.')
                return {'model_version': 1, 'record': row}
            scope = [options['indicator_type'], options['value']]
            if operation == 'sightings.list':
                return page(sightings_for(records, options), options, scope, extra={'notes': [
                    'Sensörün bildirdiği görülmedir; motor sensörün doğruluğunu veya saldırı gerçekleştiğini bağımsız doğrulamaz.',
                    'Olay zamanı, kayıt zamanı ve geri çekme kararı ayrıdır. Ham log veya sır saklanmaz.']})
            if operation == 'ioc.compare':
                from xti.adapters.sqlite_source_comparison import source_comparison
                rows, extra = source_comparison(connection, self.storage.path, options, at, records)
                return page(rows, options, scope, extra=extra)
            rows, graph = relationship_rows(connection, self.storage.path, options, at)
            for row in rows:
                review = records.get(row['id'])
                row['review'] = None if review is None else {'revision': review['revision'], 'decision': review['decision'],
                    'reason': review['reason'], 'evidence_current': review['candidate']['evidence_sha256'] == row['evidence_sha256'],
                    'state_sha256': review['state_sha256'], 'recorded_at': review['history'][-1]['recorded_at']}
            present = {row['id'] for row in rows}
            previous = sorted(row['id'] for row in records.values() if row['kind'] == 'relationship' and row['candidate']['root'] == scope and row['id'] not in present)
            return page(rows, options, scope, extra={'coverage_complete': not graph.limitations,
                'limitations': list(graph.limitations), 'previous_reviews_outside_view': previous,
                'notes': ['Kurallar kayıtlı iki adımlı kanıttan aday üretir; otomatik CTI ilişkisi veya saldırgan atfı oluşturmaz.',
                          'Güncellik yalnız kayıtlı dayanak karşılaştırmasıdır. Görünmeyen önceki kararlar silinmez; show ile okunur.']})

    def mutate(self, operation, request, at):
        if operation == 'groups.rebuild':
            destination = self.storage.path.parent / 'backups' / f'{self.storage.path.stem}.pre-group-rebuild-{uuid4()}.db'
            backup = self.storage.backup(destination)
            from xti.adapters.sqlite_group_projection import rebuild
            with self.storage._connection() as connection, connection:
                connection.execute('BEGIN IMMEDIATE')
                return {**rebuild(connection), 'backup': str(backup)}
        with self.storage._connection() as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            if operation.startswith('groups.'):
                from xti.adapters.sqlite_groups import mutate
                return mutate(connection, self.storage.path, operation, request, at)
            if operation == 'relationships.notify':
                from xti.adapters.sqlite_relationship_notifications import notify
                return notify(connection, self.storage.path, request, at)
            records, entries, chain = read_evidence(connection)
            for index, entry in enumerate(entries):
                if entry['request']['idempotency_key'] == request['idempotency_key']:
                    if (entry['operation'], entry['request']) != (operation, request):
                        raise ReportError('idempotency_conflict', 'Tekrar anahtarı başka bir kanıt isteğine bağlı.')
                    return {'replayed': True, 'record': project(entries[:index + 1])[entry['subject_id']]}
            if len(entries) >= MAX_ENTRIES:
                raise ValidationError('Görülme/ilişki günlüğü kapasitesi doldu.')
            candidate = None
            identifier = request.get('identifier')
            if operation == 'sightings.record':
                match = next((row for row in records.values() if row['kind'] == 'sighting' and sighting_key(row['observation']) == sighting_key(request)), None)
                identifier = match['id'] if match else str(uuid4())
            elif operation == 'relationships.review':
                rows, graph = relationship_rows(connection, self.storage.path, request, at)
                candidate = next((row for row in rows if row['id'] == identifier), None)
                if request['decision'] == 'withdrawn' and identifier in records:
                    candidate = records[identifier]['candidate']
                if candidate is None or candidate['evidence_sha256'] != request['evidence_sha256']:
                    raise ReportError('source_changed', 'İlişki dayanağı görünümde yok veya değişmiş; adayları yeniden alın.')
            entry = {'version': 1, 'id': str(uuid4()), 'subject_id': identifier, 'operation': operation,
                     'request': request, 'recorded_at': at, 'candidate': candidate}
            projected = project([*entries, entry])[identifier]
            payload = canonical_json(entry)
            size = journal_bytes(connection, 'evidence_journal')
            if size + len(payload.encode('utf-8')) + 512 > MAX_BYTES:
                raise ValidationError('Görülme/ilişki günlüğü byte kapasitesi doldu.')
            connection.execute('INSERT INTO evidence_journal (id,subject_id,request_key,operation,payload_json,payload_sha256,chain_sha256) VALUES (?,?,?,?,?,?,?)',
                (entry['id'], identifier, request['idempotency_key'], operation, payload, digest(payload), identity(chain, digest(payload))))
            return {'replayed': False, 'record': projected}
