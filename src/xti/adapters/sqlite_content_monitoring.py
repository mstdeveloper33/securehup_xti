"""Indexed content evidence; transactions join observations, review revisions and notifications."""
from datetime import datetime, timedelta
import json
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.content_monitoring import (ContentError, POLICY, SOURCE_FIELDS, SCOPE_FIELDS,
    canonical, digest, parameters, source_definition, scope, MAX_ITEMS, DECISIONS, validate_evidence_body)
from xti.domain.assets import ValidationError
from xti.domain.mentions import mention_time


def _one(connection, table, identifier):
    row = connection.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
    if row is None: raise ContentError('not_found', 'İçerik izleme kaydı bu çalışma alanında bulunamadı.')
    return dict(row)


def _json(payload, fingerprint, maximum=1024 * 1024):
    try:
        if not isinstance(payload, str) or len(payload) > maximum: raise ValueError()
        result = json.loads(payload)
        if canonical(result) != payload or digest(result) != fingerprint: raise ValueError()
        return result
    except (TypeError, ValueError, RecursionError):
        raise StorageError('İçerik kaydı bütünlük kontrolünden geçmedi.') from None


def _object(row, names):
    result = dict(row)
    for name in names:
        payload, sha = result.pop(name + '_json'), result.pop(name + '_sha256')
        result[name] = _json(payload, sha) if payload is not None else None
        if (payload is None) != (sha is None): raise StorageError('İçerik makbuzu özeti eksik.')
    if 'enabled' in result: result['enabled'] = bool(result['enabled'])
    return result


def source_in(connection, identifier):
    result = _object(_one(connection, 'content_sources', identifier), ('definition',))
    if source_definition(result['definition']) != result['definition']:
        raise StorageError('Kaynak tanımı değişmiş.')
    return result


def watch_in(connection, identifier):
    result = _object(_one(connection, 'content_watches', identifier), ('scope', 'bindings', 'checkpoints'))
    if scope(result['scope']) != result['scope']: raise StorageError('İçerik izleme kapsamı değişmiş.')
    return result


def run_in(connection, identifier):
    result = _object(_one(connection, 'content_runs', identifier), ('snapshot', 'report'))
    if (result['status'] == 'running') != (result['report'] is None) or (result['report'] is None) != (result['finished_at'] is None):
        raise StorageError('İçerik çalışma makbuzu tutarsız.')
    return result


def evidence_in(connection, identifier):
    result = _object(_one(connection, 'content_evidence', identifier), ('body',))
    body = result['body']
    try: validate_evidence_body(body)
    except (ValidationError, TypeError, KeyError): raise StorageError('İçerik kanıtının gövdesi geçersiz.') from None
    if (body.get('policy') != POLICY or body.get('source_id') != result['source_id']
            or digest([body.get('source_id'), body.get('native_id')]) != result['identity']):
        raise StorageError('İçerik kanıtının kaynak kimliği uyuşmuyor.')
    return result


def match_in(connection, identifier):
    result = _object(_one(connection, 'content_matches', identifier), ('target', 'match'))
    evidence = evidence_in(connection, result['evidence_id'])
    if (result['identity'] != evidence['identity'] or result['source_id'] != evidence['source_id']
            or result['target_kind'] != result['target']['kind'] or result['target_id'] != result['target']['id']):
        raise StorageError('İçerik eşleşmesi başka kapsamın kanıtına bağlı.')
    result['evidence'] = evidence
    review = connection.execute('SELECT * FROM content_reviews WHERE match_id=? ORDER BY revision DESC LIMIT 1', (identifier,)).fetchone()
    if (review['revision'] if review else 0) != result['review_revision']:
        raise StorageError('İçerik inceleme sürümü tutarsız.')
    if review:
        previous = evidence_in(connection, review['evidence_id'])
        if (previous['identity'] != result['identity'] or review['decision'] not in DECISIONS
                or not 1 <= review['observation_revision'] <= result['observation_revision']):
            raise StorageError('İçerik inceleme kararı başka kanıta ait.')
    result['review'] = dict(review) if review else None
    result['needs_review'] = not review or review['evidence_id'] != result['evidence_id'] or review['observation_revision'] != result['observation_revision']
    current = connection.execute('SELECT revision FROM content_watches WHERE id=?', (result['watch_id'],)).fetchone()
    result['scope_current'] = bool(current and current[0] == result['scope_revision'])
    return result


def _filters(values, *, prefix=''):
    clauses, args = [], []
    for key in ('watch_id', 'target_kind', 'target_id'):
        if key in values: clauses.append(prefix + key + '=?'); args.append(values[key])
    if 'domain' in values:
        clauses.append(prefix + 'id IN (SELECT match_id FROM content_match_domains WHERE domain=?)'); args.append(values['domain'])
    if 'decision' in values:
        clauses.append('EXISTS (SELECT 1 FROM content_reviews cr WHERE cr.match_id=' + prefix +
                       'id AND cr.revision=' + prefix + 'review_revision AND cr.decision=? AND cr.observation_revision=' + prefix + 'observation_revision)')
        args.append(values['decision'])
    return clauses, args


def report_in(connection, values):
    clauses, args = _filters(values, prefix='m.')
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    count = connection.execute('SELECT COUNT(*) FROM content_matches m' + where, args).fetchone()[0]
    rows = connection.execute('SELECT m.id FROM content_matches m' + where + ' ORDER BY m.sequence DESC LIMIT 20', args).fetchall()
    # Target/domain coverage includes watches with zero matches, not only positive results.
    watches, watch_where, watch_args = [], [], []
    if 'target_id' in values:
        watch_where.append('id IN (SELECT watch_id FROM content_watch_targets WHERE target_kind=? AND target_id=?)')
        watch_args.extend((values['target_kind'], values['target_id']))
    if 'domain' in values:
        watch_where.append('id IN (SELECT watch_id FROM content_watch_domains WHERE domain=?)'); watch_args.append(values['domain'])
    query = 'SELECT id FROM content_watches' + (' WHERE ' + ' AND '.join(watch_where) if watch_where else '') + ' ORDER BY sequence DESC LIMIT 21'
    for row in connection.execute(query, watch_args):
        watch = watch_in(connection, row[0])
        targets = watch['bindings']['targets']
        selected = any((('target_id' not in values or (t['kind'], t['id']) == (values['target_kind'], values['target_id']))
                        and ('domain' not in values or values['domain'] in t['domains'])) for t in targets)
        if selected:
            latest = run_in(connection, watch['last_run_id']) if watch['last_run_id'] else None
            watches.append({'id': watch['id'], 'name': watch['scope']['name'], 'enabled': watch['enabled'],
                            'revision': watch['revision'], 'state': latest['status'] if latest else 'not_checked',
                            'last_run_id': watch['last_run_id'], 'last_report': latest['report'] if latest else None,
                            'binding_state': binding_state(connection, watch)})
        if len(watches) == 21: break
    return {'stored_data_only': True, 'total_matches': count, 'items': [match_in(connection, r[0]) for r in rows],
            'more_available': count > len(rows), 'watches': watches[:20], 'more_watches_available': len(watches) > 20,
            'notes': ['Firma adı geçişi tek başına tehdit veya aynı firma kanıtı değildir.',
                      'Kaynak penceresinden çıkmak içeriğin silindiği veya riskin giderildiği anlamına gelmez.',
                      'Aynı içerik grubu farklı kaynaklardan bağımsız doğrulama sayılmaz.']}


def binding_state(connection, watch):
    if not watch['enabled']: return 'disabled'
    for frozen in watch['bindings']['sources']:
        source = source_in(connection, frozen['id'])
        if not source['enabled'] or source['revision'] != frozen['revision']: return 'scope_changed'
    organization_state = supplier_state = None
    for frozen in watch['bindings']['targets']:
        if frozen['kind'] == 'company': continue
        if frozen['kind'] == 'organization':
            from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
            organization_state = organization_state or SQLiteOrganizationRepository._audit(connection)
            try: record = SQLiteOrganizationRepository._organization_by_id(organization_state, frozen['id'])
            except ValidationError: return 'scope_unavailable'
            domains = sorted({stored.link.target.value for stored in organization_state.links.values()
                if stored.link.organization_id == frozen['id'] and stored.link.active and stored.link.target.kind == 'domain'
                and organization_state.targets[stored.link.target][1].active})
        else:
            from xti.adapters.sqlite_supplier_history import read_supplier_history
            supplier_state = supplier_state or read_supplier_history(connection)
            record = supplier_state.suppliers.get(frozen['id'])
            if record is None: return 'scope_unavailable'
            domains = [record.primary_domain]
        if not record.active or frozen['name'] != record.display_name or frozen['domains'] != domains: return 'scope_changed'
    return 'ready'


def company_in(connection, organization_scope, *, offset=0, limit=50):
    """Same read transaction as existing organization content, current explicit membership only."""
    previous = connection.row_factory; connection.row_factory = sqlite3.Row
    try:
        domains = sorted({t.value for t in organization_scope.effective_targets if t.kind == 'domain'})
        suppliers = sorted({t.value for t in organization_scope.effective_targets if t.kind == 'supplier'})
        clauses = ["(target_kind='organization' AND target_id=?)",
                   "(target_kind='supplier' AND watch_id IN (SELECT watch_id FROM content_watch_targets WHERE target_kind='organization' AND target_id=?))"]
        arguments = [organization_scope.organization.id, organization_scope.organization.id]
        watch_arguments = [organization_scope.organization.id]
        watch_clauses = ["id IN (SELECT watch_id FROM content_watch_targets WHERE target_kind='organization' AND target_id=?)"]
        if suppliers:
            placeholders = ','.join('?' for _ in suppliers)
            clauses.append("(target_kind='supplier' AND target_id IN (" + placeholders + '))')
            watch_clauses.append("id IN (SELECT watch_id FROM content_watch_targets WHERE target_kind='supplier' AND target_id IN (" + placeholders + '))')
            arguments.extend(suppliers)
            watch_arguments.extend(suppliers)
        if domains:
            placeholders = ','.join('?' for _ in domains)
            clauses.append('id IN (SELECT match_id FROM content_match_domains WHERE domain IN (' + placeholders + '))')
            watch_clauses.append('id IN (SELECT watch_id FROM content_watch_domains WHERE domain IN (' + placeholders + '))')
            arguments.extend(domains)
            watch_arguments.extend(domains)
        where = ' OR '.join(clauses)
        total = connection.execute('SELECT COUNT(*) FROM content_matches WHERE ' + where, arguments).fetchone()[0]
        effective_limit = min(limit, 100)
        rows = connection.execute('SELECT id FROM content_matches WHERE ' + where + ' ORDER BY sequence DESC LIMIT ? OFFSET ?',
            (*arguments, effective_limit, offset)).fetchall()
        watches = []
        for row in connection.execute('SELECT id FROM content_watches WHERE ' + ' OR '.join(watch_clauses) + ' ORDER BY sequence DESC LIMIT 21', watch_arguments):
            watch = watch_in(connection, row[0]); latest = run_in(connection, watch['last_run_id']) if watch['last_run_id'] else None
            watches.append({'id': watch['id'], 'name': watch['scope']['name'], 'enabled': watch['enabled'],
                            'revision': watch['revision'], 'latest_run': latest, 'binding_state': binding_state(connection, watch)})
        return {'items': [match_in(connection, r[0]) for r in rows], 'total_count': total,
                'offset': offset, 'limit': effective_limit, 'has_more': offset + len(rows) < total,
                'watches': watches[:20], 'more_watches_available': len(watches) > 20,
                'scope_basis': 'current_explicit_organization_membership'}
    finally: connection.row_factory = previous


class SQLiteContentRepository:
    def __init__(self, path): self.storage = SQLiteAssetRepository(path)

    def previous_targets(self, watch_id, source_id, native_id):
        with self.storage._connection(readonly=True) as connection:
            return set(connection.execute('SELECT target_kind,target_id FROM content_matches WHERE watch_id=? AND identity=?',
                (watch_id, digest([source_id, digest(native_id)]))))

    def read(self, operation, values):
        values = parameters(operation, values)
        with self.storage._connection(readonly=True) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN')
            readers = {'content.source.show': source_in, 'content.watch.show': watch_in, 'content.plan': watch_in,
                       'content.run.show': run_in, 'content.match.show': match_in, 'content.evidence.show': evidence_in}
            if operation in readers: return readers[operation](connection, values['identifier'])
            if operation == 'content.report': return report_in(connection, values)
            table, reader = {'content.sources': ('content_sources', source_in), 'content.watches': ('content_watches', watch_in),
                'content.runs': ('content_runs', run_in), 'content.matches': ('content_matches', match_in),
                'content.reviews': ('content_reviews', None), 'content.changes': ('content_changes', None)}[operation]
            clauses, arguments = _filters(values, prefix='m.') if operation == 'content.matches' else ([], [])
            if operation in ('content.runs', 'content.changes') and 'watch_id' in values:
                clauses.append('m.watch_id=?'); arguments.append(values['watch_id'])
            if operation == 'content.reviews':
                match_in(connection, values['identifier']); clauses.append('m.match_id=?'); arguments.append(values['identifier'])
            clauses.append('m.sequence>?'); arguments.append(values['after'])
            rows = connection.execute('SELECT m.* FROM ' + table + ' m WHERE ' + ' AND '.join(clauses) +
                ' ORDER BY m.sequence LIMIT ?', (*arguments, values['limit'] + 1)).fetchall()
            return {'items': [reader(connection, r['id']) if reader else dict(r) for r in rows[:values['limit']]],
                    'next_after': rows[values['limit'] - 1]['sequence'] if len(rows) > values['limit'] else None}

    def replay_run(self, values):
        values = parameters('content.run', values)
        with self.storage._connection(readonly=True) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute('SELECT id,request_sha256 FROM content_runs WHERE request_key=?', (values['idempotency_key'],)).fetchone()
            if row:
                if row['request_sha256'] != digest(values): raise ContentError('idempotency_conflict', 'Tekrar anahtarı başka içerik isteğine ait.')
                return run_in(connection, row['id'])
        return None

    def _replay(self, connection, operation, values):
        row = connection.execute('SELECT * FROM content_mutations WHERE request_key=?', (values['idempotency_key'],)).fetchone()
        if row:
            if row['operation'] != operation or row['request_sha256'] != digest(values):
                raise ContentError('idempotency_conflict', 'Tekrar anahtarı başka içerik isteğine ait.')
            return _json(row['result_json'], row['result_sha256'])
        if connection.execute('SELECT 1 FROM content_runs WHERE request_key=?', (values['idempotency_key'],)).fetchone():
            raise ContentError('idempotency_conflict', 'Tekrar anahtarı içerik toplama çalışmasına ait.')
        return None

    def replay_mutation(self, operation, values):
        values = parameters(operation, values)
        with self.storage._connection(readonly=True) as connection:
            connection.row_factory = sqlite3.Row
            return self._replay(connection, operation, values)

    @staticmethod
    def _bindings(connection, selected, bindings):
        if not isinstance(bindings, dict) or set(bindings) != {'targets', 'sources'}:
            raise ContentError('scope_changed', 'İçerik izleme hedefleri çözümlenmedi.')
        sources = [source_in(connection, identifier) for identifier in selected['sources']]
        if any(not s['enabled'] for s in sources): raise ContentError('source_disabled', 'Seçilen içerik kaynağı devre dışı.')
        actual = [{'id': s['id'], 'revision': s['revision'], 'definition': s['definition']} for s in sources]
        if bindings['sources'] != actual: raise ContentError('scope_changed', 'Kaynak kapsamı işlem sırasında değişti.')
        if len(bindings['targets']) != len(selected['targets']): raise ContentError('scope_changed', 'İçerik hedefleri eksik.')
        for defined, resolved in zip(selected['targets'], bindings['targets']):
            if any(defined[k] != resolved[k] for k in ('kind', 'id', 'aliases')):
                raise ContentError('scope_changed', 'İçerik hedef kimliği uyuşmuyor.')
        return bindings

    def mutate(self, operation, values, at, *, bindings=None):
        values = parameters(operation, values); mention_time(at)
        with self.storage._connection() as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN IMMEDIATE')
            replay = self._replay(connection, operation, values)
            if replay is not None: return {**replay, 'replayed': True}
            identifier = values.get('identifier', str(uuid4()))
            if operation.startswith('content.source.'):
                current = source_in(connection, identifier) if operation.endswith('.update') else None
                if current and current['revision'] != values['expected_revision']:
                    raise ContentError('revision_conflict', 'Kaynak sürümü değişti; güncel kaydı okuyun.')
                definition = source_definition({**(current['definition'] if current else {}), **{k: v for k, v in values.items() if k in SOURCE_FIELDS}})
                if current:
                    if any(current['definition'][k] != definition[k] for k in ('provider', 'locator')):
                        raise ContentError('source_identity_change', 'Farklı kaynak/kanal için yeni kaynak ekleyin; eski içerik kimlikleri korunur.')
                    connection.execute('UPDATE content_sources SET definition_json=?,definition_sha256=?,revision=revision+1,enabled=?,updated_at=? WHERE id=?',
                        (canonical(definition), digest(definition), int(values.get('enabled', current['enabled'])), at, identifier))
                else:
                    connection.execute('INSERT INTO content_sources (id,revision,enabled,definition_json,definition_sha256,created_at,updated_at) VALUES (?,1,1,?,?,?,?)',
                        (identifier, canonical(definition), digest(definition), at, at))
                result = source_in(connection, identifier)
            elif operation.startswith('content.watch.'):
                current = watch_in(connection, identifier) if operation.endswith('.update') else None
                if current:
                    if current['revision'] != values['expected_revision']: raise ContentError('revision_conflict', 'İzleme sürümü değişti.')
                    self._idle(connection, identifier)
                selected = scope({**(current['scope'] if current else {}), **{k: v for k, v in values.items() if k in SCOPE_FIELDS}})
                stopping = current is not None and values.get('enabled') is False and not SCOPE_FIELDS.intersection(values)
                bound = current['bindings'] if stopping else self._bindings(connection, selected, bindings)
                # Preserve source cursors only when the exact source definition stayed the same.
                checkpoints = {}
                if current:
                    previous = {s['id']: s for s in current['bindings']['sources']}
                    checkpoints = {s['id']: current['checkpoints'][s['id']] for s in bound['sources']
                                   if previous.get(s['id']) == s and s['id'] in current['checkpoints']}
                    connection.execute('UPDATE content_watches SET scope_json=?,scope_sha256=?,bindings_json=?,bindings_sha256=?,checkpoints_json=?,checkpoints_sha256=?,revision=revision+1,enabled=?,updated_at=? WHERE id=?',
                        (canonical(selected), digest(selected), canonical(bound), digest(bound), canonical(checkpoints), digest(checkpoints), int(values.get('enabled', current['enabled'])), at, identifier))
                else:
                    connection.execute('INSERT INTO content_watches (id,revision,enabled,scope_json,scope_sha256,bindings_json,bindings_sha256,checkpoints_json,checkpoints_sha256,created_at,updated_at) VALUES (?,1,1,?,?,?,?,?,?,?,?)',
                        (identifier, canonical(selected), digest(selected), canonical(bound), digest(bound), canonical(checkpoints), digest(checkpoints), at, at))
                connection.execute('DELETE FROM content_watch_targets WHERE watch_id=?', (identifier,))
                connection.execute('DELETE FROM content_watch_domains WHERE watch_id=?', (identifier,))
                connection.executemany('INSERT INTO content_watch_targets (watch_id,target_kind,target_id) VALUES (?,?,?)',
                    [(identifier, t['kind'], t['id']) for t in bound['targets']])
                connection.executemany('INSERT INTO content_watch_domains (watch_id,domain) VALUES (?,?)',
                    [(identifier, d) for d in sorted({d for t in bound['targets'] for d in t['domains']})])
                result = watch_in(connection, identifier)
            elif operation == 'content.review':
                current = match_in(connection, identifier)
                if (current['evidence_id'] != values['evidence_id'] or current['review_revision'] != values['expected_revision']
                        or current['observation_revision'] != values['expected_observation_revision']):
                    raise ContentError('revision_conflict', 'İçerik veya inceleme değişti; güncel kanıtı yeniden okuyun.')
                review_id, revision = str(uuid4()), current['review_revision'] + 1
                connection.execute('INSERT INTO content_reviews (id,match_id,evidence_id,decision,reason,revision,observation_revision,created_at) VALUES (?,?,?,?,?,?,?,?)',
                    (review_id, identifier, current['evidence_id'], values['decision'], values['reason'], revision, current['observation_revision'], at))
                connection.execute('UPDATE content_matches SET review_revision=? WHERE id=?', (revision, identifier))
                result = _one(connection, 'content_reviews', review_id)
            elif operation == 'content.recover':
                current = run_in(connection, identifier)
                if current['status'] == 'running':
                    report = {'status': 'interrupted', 'sources': [], 'reason': 'İşlem kesildi; otomatik kaynak tekrarı yapılmadı.',
                              'source_state_unknown': True, 'checkpoints_committed': False}
                    connection.execute("UPDATE content_runs SET status='interrupted',report_json=?,report_sha256=?,finished_at=? WHERE id=?",
                        (canonical(report), digest(report), at, identifier))
                result = run_in(connection, identifier)
            else: raise ContentError('invalid_parameters', 'İçerik yazma işlemi bilinmiyor.')
            connection.execute('INSERT INTO content_mutations (id,request_key,operation,request_sha256,result_json,result_sha256,created_at) VALUES (?,?,?,?,?,?,?)',
                (str(uuid4()), values['idempotency_key'], operation, digest(values), canonical(result), digest(result), at))
            connection.commit()
            return result

    @staticmethod
    def _idle(connection, identifier):
        if connection.execute("SELECT 1 FROM content_runs WHERE watch_id=? AND status='running' LIMIT 1", (identifier,)).fetchone():
            raise ContentError('watch_busy', 'İçerik izlemesi sürüyor veya kesildi; önce çalışma durumunu inceleyin.')

    def reserve(self, values, at, *, bindings):
        values = parameters('content.run', values); mention_time(at)
        with self.storage._connection() as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute('SELECT id,request_sha256 FROM content_runs WHERE request_key=?', (values['idempotency_key'],)).fetchone()
            if existing:
                if existing['request_sha256'] != digest(values): raise ContentError('idempotency_conflict', 'Tekrar anahtarı başka isteğe ait.')
                return run_in(connection, existing['id']), True
            self._replay(connection, 'content.run', values)
            watch = watch_in(connection, values['identifier'])
            if watch['revision'] != values['expected_revision']: raise ContentError('revision_conflict', 'İçerik izleme sürümü değişti.')
            if not watch['enabled']: raise ContentError('watch_disabled', 'İçerik izlemesi kapalı.')
            self._idle(connection, watch['id'])
            bound = self._bindings(connection, watch['scope'], bindings)
            if bound != watch['bindings']: raise ContentError('scope_changed', 'Firma veya kaynak değişti; izlemeyi açıkça güncelleyin.')
            if watch['last_started_at'] and not values['force']:
                due = datetime.fromisoformat(watch['last_started_at']) + timedelta(seconds=watch['scope']['interval_seconds'])
                if datetime.fromisoformat(at) < due: raise ContentError('not_due', 'İçerik izleme aralığı henüz dolmadı.')
            snapshot = {'scope': watch['scope'], 'bindings': bound, 'checkpoints': watch['checkpoints']}
            identifier = str(uuid4())
            connection.execute("INSERT INTO content_runs (id,watch_id,watch_revision,request_key,request_sha256,snapshot_json,snapshot_sha256,status,started_at) VALUES (?,?,?,?,?,?,?,'running',?)",
                (identifier, watch['id'], watch['revision'], values['idempotency_key'], digest(values), canonical(snapshot), digest(snapshot), at))
            connection.execute('UPDATE content_watches SET last_started_at=?,last_run_id=? WHERE id=?', (at, identifier, watch['id']))
            result = run_in(connection, identifier)
            connection.commit()
            return result, False

    def finish(self, identifier, result, at):
        mention_time(at)
        with self.storage._connection() as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN IMMEDIATE')
            run = run_in(connection, identifier)
            if run['status'] != 'running': return run
            watch = watch_in(connection, run['watch_id'])
            if watch['revision'] != run['watch_revision']: raise ContentError('revision_conflict', 'İçerik kapsamı toplama sırasında değişti.')
            documents = result.get('documents', [])
            if len(documents) > MAX_ITEMS: raise StorageError('İçerik turu öğe sınırını aşıyor.')
            changes = new_matches = new_evidence = 0
            targets = {(t['kind'], t['id']): t for t in run['snapshot']['bindings']['targets']}
            sources = {s['id']: s for s in run['snapshot']['bindings']['sources']}
            checkpoints = dict(watch['checkpoints'])
            seen = set()
            for document in documents:
                body = document['body']
                try: validate_evidence_body(body)
                except (ValidationError, TypeError, KeyError): raise StorageError('İçerik kanıtının gövdesi geçersiz.') from None
                if body['source_id'] not in sources or body['policy'] != POLICY or len(canonical(body)) > 256 * 1024:
                    raise StorageError('İçerik kanıtı seçilen kaynak kapsamına ait değil.')
                frozen_source = sources[body['source_id']]
                if (body['source_revision'] != frozen_source['revision'] or
                    any(body[k] != frozen_source['definition'][k] for k in ('provider', 'language', 'region')) or
                    body['source_locator'] != frozen_source['definition']['locator']):
                    raise StorageError('İçerik kanıtı kaynak tanımıyla uyuşmuyor.')
                identity, body_sha = digest([body['source_id'], body['native_id']]), digest(body)
                key = (body['source_id'], body['native_id'])
                if key in seen: raise StorageError('Kaynak aynı içerik kimliğini bir turda iki kez döndürdü.')
                seen.add(key)
                found = connection.execute('SELECT id FROM content_evidence WHERE source_id=? AND identity=? AND body_sha256=?', (body['source_id'], identity, body_sha)).fetchone()
                evidence_id = found[0] if found else str(uuid4())
                if not found:
                    connection.execute('INSERT INTO content_evidence (id,source_id,identity,body_json,body_sha256,observed_at) VALUES (?,?,?,?,?,?)',
                        (evidence_id, body['source_id'], identity, canonical(body), body_sha, at)); new_evidence += 1
                for entry in document['matches']:
                    target, match = entry['target'], entry['match']
                    if targets.get((target['kind'], target['id'])) != target: raise StorageError('İçerik eşleşmesinin hedef kapsamı uyuşmuyor.')
                    current = connection.execute('SELECT * FROM content_matches WHERE watch_id=? AND target_kind=? AND target_id=? AND identity=?',
                        (watch['id'], target['kind'], target['id'], identity)).fetchone()
                    match_id = current['id'] if current else str(uuid4())
                    changed = current is not None and (current['evidence_id'] != evidence_id or current['target_sha256'] != digest(target) or current['match_sha256'] != digest(match))
                    if current:
                        # Validate the previously committed evidence before advancing its projection.
                        match_in(connection, match_id)
                        connection.execute('UPDATE content_matches SET target_json=?,target_sha256=?,evidence_id=?,match_json=?,match_sha256=?,scope_revision=?,last_seen=?,observation_revision=observation_revision+? WHERE id=?',
                            (canonical(target), digest(target), evidence_id, canonical(match), digest(match), watch['revision'], at, int(changed), match_id))
                    else:
                        connection.execute('INSERT INTO content_matches (id,watch_id,target_kind,target_id,target_json,target_sha256,source_id,identity,evidence_id,match_json,match_sha256,scope_revision,first_seen,last_seen,observation_revision,review_revision) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0)',
                            (match_id, watch['id'], target['kind'], target['id'], canonical(target), digest(target), body['source_id'], identity, evidence_id, canonical(match), digest(match), watch['revision'], at, at)); new_matches += 1
                    connection.execute('DELETE FROM content_match_domains WHERE match_id=?', (match_id,))
                    connection.executemany('INSERT INTO content_match_domains (match_id,domain) VALUES (?,?)', [(match_id, d) for d in target['domains']])
                    baseline = not watch['checkpoints'].get(body['source_id'], {}).get('baseline_complete', False)
                    if changed or (not current and not baseline and not document.get('suppress_new_notification', False)):
                        change_id = str(uuid4())
                        connection.execute('INSERT INTO content_changes (id,watch_id,run_id,match_id,kind,before_evidence_id,after_evidence_id,created_at) VALUES (?,?,?,?,?,?,?,?)',
                            (change_id, watch['id'], identifier, match_id, 'changed' if current else 'new', current['evidence_id'] if current else None, evidence_id, at))
                        from xti.adapters.sqlite_notification_sequence import next_notification_sequence
                        connection.execute('INSERT INTO content_notifications (sequence,id,change_id,created_at) VALUES (?,?,?,?)',
                            (next_notification_sequence(connection), str(uuid4()), change_id, at)); changes += 1
            for source in result['sources']:
                if source['source_id'] not in sources: raise StorageError('Çalışma raporunun kaynağı kapsam dışında.')
                if source.get('checkpoint') is not None:
                    checkpoint = source['checkpoint']
                    if len(canonical(checkpoint)) > 65536: raise StorageError('Kaynak ilerleme kaydı sınırı aşıyor.')
                    checkpoints[source['source_id']] = checkpoint
            report = {k: v for k, v in result.items() if k != 'documents'}
            report.update(new_matches=new_matches, new_evidence=new_evidence, changes=changes,
                          retained_data_preserved=True, checkpoints_committed=True)
            if report['status'] not in ('complete', 'partial', 'failed'): raise StorageError('İçerik çalışma durumu geçersiz.')
            connection.execute('UPDATE content_runs SET status=?,report_json=?,report_sha256=?,finished_at=? WHERE id=?',
                (report['status'], canonical(report), digest(report), at, identifier))
            connection.execute('UPDATE content_watches SET checkpoints_json=?,checkpoints_sha256=? WHERE id=?', (canonical(checkpoints), digest(checkpoints), watch['id']))
            saved = run_in(connection, identifier)
            connection.commit()
            return saved


def case_snapshot(connection, identifier):
    from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
    previous = connection.row_factory; connection.row_factory = sqlite3.Row
    try:
        match = match_in(connection, identifier)
        payload, checksum = canonical_snapshot({'version': 1, 'type': 'content_match', 'match': match})
        return CaseEvidenceSnapshot('content_match', identifier, match['target']['name'] + ' — ' + match['evidence']['body']['title'][:200],
                                    'content show ' + identifier, payload, checksum)
    finally: connection.row_factory = previous


def validate_case_snapshot(value):
    from xti.domain.mentions import mention_uuid
    try:
        if not isinstance(value, dict) or set(value) != {'version', 'type', 'match'} or value['version'] != 1 or value['type'] != 'content_match':
            raise ValueError()
        match = value['match']; evidence = match['evidence']; body = evidence['body']
        for identifier in (match['id'], match['watch_id'], match['evidence_id'], evidence['id']): mention_uuid(identifier)
        if (match['evidence_id'] != evidence['id'] or body['policy'] != POLICY or body['source_id'] != match['source_id']
                or evidence['identity'] != match['identity'] or match['identity'] != digest([body['source_id'], body['native_id']])):
            raise ValueError()
        return value
    except (KeyError, TypeError, ValueError):
        raise StorageError('İçerik vaka kopyası geçersiz.') from None


def notification_in(connection, identifier):
    previous = connection.row_factory; connection.row_factory = sqlite3.Row
    try:
        notice = _one(connection, 'content_notifications', identifier)
        change = _one(connection, 'content_changes', notice['change_id'])
        run = run_in(connection, change['run_id'])
        match = _one(connection, 'content_matches', change['match_id'])
        before = evidence_in(connection, change['before_evidence_id']) if change['before_evidence_id'] else None
        after = evidence_in(connection, change['after_evidence_id'])
        target = next((t for t in run['snapshot']['bindings']['targets'] if (t['kind'], t['id']) == (match['target_kind'], match['target_id'])), None)
        if (target is None or change['watch_id'] != run['watch_id'] or match['watch_id'] != run['watch_id']
                or any(e['identity'] != match['identity'] or e['source_id'] != match['source_id'] for e in (before, after) if e is not None)):
            raise StorageError('İçerik bildirimi tarihî kanıt kapsamıyla uyuşmuyor.')
        return {'id': identifier, 'target': target, 'change': change, 'before': before, 'after': after}
    finally: connection.row_factory = previous
