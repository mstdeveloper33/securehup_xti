"""Workspace-local indexed evidence. No full-history replay on normal operations."""
from datetime import datetime, timedelta
import json
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.code_exposure import (CodeExposureError, SCOPE_FIELDS, POLICY, canonical, digest,
    scope, parameters, validate_observation, MAX_CANDIDATES)
from xti.domain.mentions import mention_time


def _one(connection, table, identifier):
    # Table names are internal constants supplied by this module, never request data.
    row = connection.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
    if row is None: raise CodeExposureError('not_found', 'Kod izleme kaydı bu çalışma alanında bulunamadı.')
    return dict(row)


def _json(payload, fingerprint=None, *, maximum=2 * 1024 * 1024):
    try:
        if not isinstance(payload, str) or len(payload) > maximum: raise ValueError()
        value = json.loads(payload)
        if canonical(value) != payload or fingerprint is not None and digest(value) != fingerprint:
            raise ValueError()
        return value
    except (ValueError, TypeError, RecursionError):
        raise StorageError('Kod izleme kaydı bütünlük kontrolünden geçmedi.') from None


def _watch(row):
    result = dict(row)
    result['scope'] = _json(result.pop('scope_json'), result.pop('scope_sha256'), maximum=65536)
    if scope(result['scope']) != result['scope'] or result['domain'] != result['scope']['domain']:
        raise StorageError('Kod izleme kapsamı değişmiş.')
    # Five bounded provider cursors can exceed one 64KiB scope, independently of retained history.
    result['checkpoints'] = _json(result.pop('checkpoints_json'), maximum=256 * 1024)
    result['enabled'] = bool(result['enabled'])
    return result


def _run(row):
    result = dict(row)
    result['scope'] = _json(result.pop('scope_json'), result.pop('scope_sha256'), maximum=65536)
    payload = result.pop('report_json')
    result['report'] = _json(payload, result['report_sha256']) if payload is not None else None
    if (result['status'] == 'running') != (payload is None) or (payload is None) != (result['finished_at'] is None):
        raise StorageError('Kod izleme çalışma makbuzu tutarsız.')
    return result


def evidence_in(connection, identifier):
    row = _one(connection, 'code_evidence', identifier)
    row['body'] = validate_observation(_json(row.pop('body_json'), row['body_sha256'], maximum=32768))
    if row['body']['identity'] != row['identity']: raise StorageError('Kod kanıtı kimliği değişmiş.')
    return row


def _finding(connection, row, *, history=False):
    result = dict(row)
    result['evidence'] = evidence_in(connection, result['evidence_id'])
    evidence = result['evidence']
    if (evidence['watch_id'] != result['watch_id'] or evidence['identity'] != result['identity']
            or evidence['body']['kind'] != result['kind'] or evidence['body']['source'] != result['source']):
        raise StorageError('Kod bulgusu ve özgün kanıt kapsamı uyuşmuyor.')
    review = connection.execute('SELECT * FROM code_reviews WHERE finding_id=? ORDER BY revision DESC LIMIT 1', (result['id'],)).fetchone()
    if (review['revision'] if review else 0) != result['review_revision']:
        raise StorageError('Kod bulgusu inceleme sürümü tutarsız.')
    if review:
        reviewed = evidence_in(connection, review['evidence_id'])
        if (reviewed['watch_id'] != result['watch_id'] or reviewed['identity'] != result['identity']
                or not 1 <= review['observation_revision'] <= result['observation_revision']):
            raise StorageError('İnceleme kararı farklı kod kanıtına ait.')
    result['review'] = dict(review) if review else None
    result['needs_review'] = (review is None or review['evidence_id'] != result['evidence_id']
                              or review['observation_revision'] != result['observation_revision'])
    if history:
        # The immutable review log is paged separately when large; detail never loads unlimited history.
        rows = connection.execute('SELECT * FROM code_reviews WHERE finding_id=? ORDER BY revision DESC LIMIT 21', (result['id'],)).fetchall()
        result['reviews'] = [dict(r) for r in rows[:20]]
        result['older_reviews_available'] = len(rows) > 20
    return result


def report_in(connection, domain):
    watch_count = connection.execute('SELECT COUNT(*) FROM code_watches WHERE domain=?', (domain,)).fetchone()[0]
    by_kind = dict(connection.execute('SELECT kind,COUNT(*) FROM code_findings WHERE domain=? GROUP BY kind', (domain,)))
    latest = connection.execute('SELECT r.* FROM code_runs r JOIN code_watches w ON w.id=r.watch_id '
                                'WHERE w.domain=? ORDER BY r.sequence DESC LIMIT 1', (domain,)).fetchone()
    rows = connection.execute('SELECT * FROM code_findings WHERE domain=? ORDER BY sequence DESC LIMIT 20', (domain,)).fetchall()
    return {'domain': domain, 'watch_count': watch_count, 'counts': by_kind,
            'latest_run': _run(latest) if latest else None,
            'items': [_finding(connection, row) for row in rows],
            'more_available': sum(by_kind.values()) > len(rows),
            'notes': ['Kamu kaynaklarının sınırlı keşif penceresidir; bütün depolar veya geçmiş paste arşivi taranmış sayılmaz.',
                      'Hassas bilgi adayı çalışır anahtar veya firma sahipliği kanıtı değildir.']}


class SQLiteCodeRepository:
    def __init__(self, path): self.storage = SQLiteAssetRepository(path)

    def read(self, operation, values):
        values = parameters(operation, values)
        with self.storage._connection(readonly=True) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN')
            if operation in ('code.watch.show', 'code.plan'):
                result = _watch(_one(connection, 'code_watches', values['identifier']))
                return result
            if operation == 'code.run.show': return _run(_one(connection, 'code_runs', values['identifier']))
            if operation == 'code.finding.show': return _finding(connection, _one(connection, 'code_findings', values['identifier']), history=True)
            if operation == 'code.evidence.show': return evidence_in(connection, values['identifier'])
            if operation == 'code.report': return report_in(connection, values['domain'])
            table = {'code.watch.list': 'code_watches', 'code.runs': 'code_runs',
                     'code.findings': 'code_findings', 'code.changes': 'code_changes', 'code.reviews': 'code_reviews'}[operation]
            clauses, arguments = ['sequence>?'], [values['after']]
            if operation == 'code.reviews':
                _one(connection, 'code_findings', values['identifier'])
                clauses.append('finding_id=?'); arguments.append(values['identifier'])
            for key in ('domain', 'watch_id', 'kind'):
                if key in values: clauses.append(key + '=?'); arguments.append(values[key])
            if 'decision' in values:
                clauses.append('EXISTS(SELECT 1 FROM code_reviews r WHERE r.finding_id=code_findings.id '
                               'AND r.revision=code_findings.review_revision AND r.decision=?)')
                arguments.append(values['decision'])
            rows = connection.execute(f'SELECT * FROM {table} WHERE ' + ' AND '.join(clauses) +
                                      ' ORDER BY sequence LIMIT ?', (*arguments, values['limit'] + 1)).fetchall()
            items = []
            for row in rows[:values['limit']]:
                items.append(_watch(row) if operation == 'code.watch.list' else _run(row) if operation == 'code.runs'
                             else _finding(connection, row) if operation == 'code.findings' else dict(row))
            return {'items': items, 'next_after': items[-1]['sequence'] if len(rows) > values['limit'] else None,
                    'pagination': 'stable_sequence_newer_records_may_appear'}

    @staticmethod
    def _replay(connection, operation, values):
        row = connection.execute('SELECT * FROM code_mutations WHERE request_key=?', (values['idempotency_key'],)).fetchone()
        if row:
            if row['operation'] != operation or row['request_sha256'] != digest(values):
                raise CodeExposureError('idempotency_conflict', 'Tekrar anahtarı başka bir kod izleme isteğine ait.')
            return _json(row['result_json'], row['result_sha256'])
        if connection.execute('SELECT 1 FROM code_runs WHERE request_key=?', (values['idempotency_key'],)).fetchone():
            raise CodeExposureError('idempotency_conflict', 'Tekrar anahtarı kayıtlı bir toplama işlemine ait.')
        return None

    def mutate(self, operation, values, at):
        values = parameters(operation, values); mention_time(at)
        with self.storage._connection() as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN IMMEDIATE')
            replay = self._replay(connection, operation, values)
            if replay is not None: return replay
            if operation == 'code.watch.add':
                selected = scope({k: v for k, v in values.items() if k in SCOPE_FIELDS})
                identifier = str(uuid4())
                connection.execute('INSERT INTO code_watches(id,domain,name,revision,enabled,scope_json,scope_sha256,checkpoints_json,created_at,updated_at) '
                    'VALUES(?,?,?,1,1,?,?,?,?,?)', (identifier, selected['domain'], selected['name'], canonical(selected), digest(selected), '{}', at, at))
                result = _watch(_one(connection, 'code_watches', identifier))
            elif operation == 'code.watch.update':
                watch = _watch(_one(connection, 'code_watches', values['identifier']))
                if values['expected_revision'] != watch['revision']:
                    raise CodeExposureError('revision_conflict', 'İzleme değişti; güncel sürümü yeniden alın.')
                if connection.execute("SELECT 1 FROM code_runs WHERE watch_id=? AND status='running'", (watch['id'],)).fetchone():
                    raise CodeExposureError('busy', 'Çalışan izleme önce tamamlanmalı veya kurtarılmalı.')
                selected = scope({**watch['scope'], **{k: v for k, v in values.items() if k in SCOPE_FIELDS}})
                if selected['domain'] != watch['domain']:
                    raise CodeExposureError('invalid_parameters', 'Domain değişikliği için yeni izleme oluşturun; eski kanıt kapsamı korunur.')
                checkpoints = watch['checkpoints'] if selected == watch['scope'] else {}
                connection.execute('UPDATE code_watches SET name=?,revision=revision+1,enabled=?,scope_json=?,scope_sha256=?,checkpoints_json=?,updated_at=? WHERE id=?',
                    (selected['name'], int(values.get('enabled', watch['enabled'])), canonical(selected), digest(selected), canonical(checkpoints), at, watch['id']))
                result = _watch(_one(connection, 'code_watches', watch['id']))
            elif operation == 'code.review':
                finding = _one(connection, 'code_findings', values['identifier'])
                if (finding['review_revision'] != values['expected_revision'] or finding['evidence_id'] != values['evidence_id']
                        or finding['observation_revision'] != values['expected_observation_revision']):
                    raise CodeExposureError('revision_conflict', 'Kanıt veya inceleme değişti; güncel bulguyu yeniden alın.')
                identifier = str(uuid4())
                connection.execute('INSERT INTO code_reviews(id,finding_id,evidence_id,decision,reason,revision,observation_revision,created_at) VALUES(?,?,?,?,?,?,?,?)',
                    (identifier, finding['id'], finding['evidence_id'], values['decision'], values['reason'], finding['review_revision'] + 1,
                     finding['observation_revision'], at))
                connection.execute('UPDATE code_findings SET review_revision=review_revision+1 WHERE id=?', (finding['id'],))
                result = dict(_one(connection, 'code_reviews', identifier))
            elif operation == 'code.recover':
                run = _run(_one(connection, 'code_runs', values['identifier']))
                if run['status'] == 'running':
                    report = {'status': 'interrupted', 'sources': [], 'changes': 0,
                              'note': 'Kesilen çalışmada gönderilmiş istekler olabilir; eski kanıt korundu. Yeni tekrar anahtarıyla yeniden çalıştırın.'}
                    connection.execute("UPDATE code_runs SET status='interrupted',report_json=?,report_sha256=?,finished_at=? WHERE id=?",
                                       (canonical(report), digest(report), at, run['id']))
                result = _run(_one(connection, 'code_runs', run['id']))
            else: raise CodeExposureError('invalid_parameters', 'Kod yazma işlemi bilinmiyor.')
            connection.execute('INSERT INTO code_mutations(id,request_key,operation,request_sha256,result_json,result_sha256,created_at) VALUES(?,?,?,?,?,?,?)',
                (str(uuid4()), values['idempotency_key'], operation, digest(values), canonical(result), digest(result), at))
            connection.commit()
            return result

    def reserve(self, values, at):
        values = parameters('code.run', values); mention_time(at)
        with self.storage._connection() as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute('SELECT * FROM code_runs WHERE request_key=?', (values['idempotency_key'],)).fetchone()
            if existing:
                if existing['request_sha256'] != digest(values):
                    raise CodeExposureError('idempotency_conflict', 'Tekrar anahtarı farklı toplama kapsamına ait.')
                return _run(existing), True
            self._replay(connection, 'code.run', values)
            watch = _watch(_one(connection, 'code_watches', values['identifier']))
            if values['expected_revision'] != watch['revision']:
                raise CodeExposureError('revision_conflict', 'Kod izleme kapsamı değişti; planı yeniden alın.')
            if not watch['enabled']: raise CodeExposureError('invalid_state', 'Kod izlemesi duraklatılmış.')
            if connection.execute("SELECT 1 FROM code_runs WHERE watch_id=? AND status='running'", (watch['id'],)).fetchone():
                raise CodeExposureError('busy', 'Önceki kod izlemesi tamamlanmadı; açık kurtarma işlemi gerekli.')
            if watch['last_started_at'] and not values['force']:
                due = datetime.fromisoformat(watch['last_started_at']) + timedelta(seconds=watch['scope']['interval_seconds'])
                if datetime.fromisoformat(at) < due: raise CodeExposureError('not_due', 'Kod izlemesinin zamanı henüz gelmedi.')
            identifier = str(uuid4())
            connection.execute('INSERT INTO code_runs(id,watch_id,watch_revision,request_key,request_sha256,scope_json,scope_sha256,status,started_at) '
                               "VALUES(?,?,?,?,?,?,?,'running',?)", (identifier, watch['id'], watch['revision'], values['idempotency_key'], digest(values),
                                                                    canonical(watch['scope']), digest(watch['scope']), at))
            connection.execute('UPDATE code_watches SET last_started_at=?,last_run_id=? WHERE id=?', (at, identifier, watch['id']))
            result = _run(_one(connection, 'code_runs', identifier))
            result['checkpoints'] = watch['checkpoints']
            connection.commit()
            return result, False

    @staticmethod
    def _change(connection, run, finding, kind, before, after, at, *, notify):
        identifier = str(uuid4())
        connection.execute('INSERT INTO code_changes(id,watch_id,run_id,finding_id,kind,before_evidence_id,after_evidence_id,created_at) VALUES(?,?,?,?,?,?,?,?)',
            (identifier, run['watch_id'], run['id'], finding, kind, before, after, at))
        if notify:
            from xti.adapters.sqlite_notification_sequence import next_notification_sequence
            connection.execute('INSERT INTO code_notifications(sequence,id,change_id,created_at) VALUES(?,?,?,?)',
                               (next_notification_sequence(connection), str(uuid4()), identifier, at))

    def finish(self, identifier, result, at):
        mention_time(at)
        candidates = result['candidates']
        if len(candidates) > MAX_CANDIDATES: raise StorageError('Tek tur kod kanıtı sınırı aşıldı.')
        for candidate in candidates: validate_observation(candidate)
        with self.storage._connection() as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN IMMEDIATE')
            run = _run(_one(connection, 'code_runs', identifier))
            if run['status'] != 'running': raise CodeExposureError('invalid_state', 'Toplama makbuzu zaten tamamlandı.')
            if at < run['started_at']: raise StorageError('Kod toplama zamanı geriye gitti.')
            watch = _watch(_one(connection, 'code_watches', run['watch_id']))
            if watch['revision'] != run['watch_revision']: raise CodeExposureError('revision_conflict', 'Toplama kapsamı değişmiş.')
            checkpoints = watch['checkpoints']
            baselines = {s: not checkpoints.get(s, {}).get('baseline', False) for s in run['scope']['sources']}
            changes, new_evidence, seen = 0, 0, set()
            for body in candidates:
                identity = body['identity']; seen.add(identity)
                encoded, fingerprint = canonical(body), digest(body)
                row = connection.execute('SELECT id FROM code_evidence WHERE watch_id=? AND identity=? AND body_sha256=?',
                                         (watch['id'], identity, fingerprint)).fetchone()
                evidence_id = row['id'] if row else str(uuid4())
                if row is None:
                    connection.execute('INSERT INTO code_evidence(id,watch_id,identity,body_json,body_sha256,observed_at) VALUES(?,?,?,?,?,?)',
                        (evidence_id, watch['id'], identity, encoded, fingerprint, at)); new_evidence += 1
                old = connection.execute('SELECT * FROM code_findings WHERE watch_id=? AND identity=?', (watch['id'], identity)).fetchone()
                if old is None:
                    fid = str(uuid4())
                    connection.execute('INSERT INTO code_findings(id,watch_id,domain,source,locator_sha256,kind,identity,evidence_id,state,first_seen,last_seen,observation_revision,review_revision) '
                                       "VALUES(?,?,?,?,?,?,?,?,'observed',?,?,1,0)",
                        (fid, watch['id'], watch['domain'], body['source'], digest(body['locator']), body['kind'], identity, evidence_id, at, at))
                    if not baselines[body['source']]:
                        self._change(connection, run, fid, 'new_candidate', None, evidence_id, at, notify=True); changes += 1
                else:
                    changed = old['evidence_id'] != evidence_id or old['state'] != 'observed'
                    connection.execute("UPDATE code_findings SET evidence_id=?,state='observed',last_seen=?,observation_revision=observation_revision+? WHERE id=?",
                                       (evidence_id, at, int(changed), old['id']))
                    if changed:
                        kind = 'reappeared' if old['state'] != 'observed' else 'evidence_changed'
                        self._change(connection, run, old['id'], kind, old['evidence_id'], evidence_id, at,
                                     notify=not baselines[body['source']]); changes += 1
            for document in result['checked_documents']:
                old_rows = connection.execute("SELECT * FROM code_findings WHERE watch_id=? AND source=? AND locator_sha256=? AND state='observed'",
                    (watch['id'], document['source'], digest(document['locator']))).fetchall()
                for old in old_rows:
                    if old['identity'] in seen or old['kind'] == 'secret_candidate' and not document['secret_checked']: continue
                    connection.execute("UPDATE code_findings SET state='not_observed_in_file',observation_revision=observation_revision+1 WHERE id=?", (old['id'],))
                    self._change(connection, run, old['id'], 'not_observed_in_file', old['evidence_id'], old['evidence_id'], at,
                                 notify=not baselines[document['source']]); changes += 1
            for source in result['sources']:
                old_checkpoint = checkpoints.get(source['source'], {})
                checkpoints[source['source']] = {'cursor': source['cursor'], 'retry_at': source['retry_at'],
                    'pages': source.get('pages', {}), 'file_offsets': source.get('file_offsets', {}),
                    'tree_pages': source.get('tree_pages', {}),
                    'baseline': bool(old_checkpoint.get('baseline') or source['observed'] and
                        (source['files'] > 0 or source['status'] == 'complete'))}
            report = {k: v for k, v in result.items() if k not in ('candidates', 'checked_documents')}
            report.update(changes=changes, new_evidence=new_evidence, candidates=len(candidates), baseline_sources=[s for s, v in baselines.items() if v])
            connection.execute('UPDATE code_runs SET status=?,report_json=?,report_sha256=?,finished_at=? WHERE id=?',
                (report['status'], canonical(report), digest(report), at, run['id']))
            connection.execute('UPDATE code_watches SET checkpoints_json=? WHERE id=?', (canonical(checkpoints), watch['id']))
            response = _run(_one(connection, 'code_runs', run['id']))
            connection.commit()
            return response


def case_snapshot(connection, identifier):
    from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
    previous = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        finding = _finding(connection, _one(connection, 'code_findings', identifier), history=False)
        value = {'version': 1, 'type': 'code_exposure', 'finding': finding}
        payload, checksum = canonical_snapshot(value)
        return CaseEvidenceSnapshot('code_exposure', identifier, finding['domain'] + ' — ' + finding['kind'],
                                    'code show ' + identifier, payload, checksum)
    finally: connection.row_factory = previous


def validate_case_snapshot(value):
    if not isinstance(value, dict) or set(value) != {'version', 'type', 'finding'} or value['version'] != 1 or value['type'] != 'code_exposure':
        raise StorageError('Kod maruziyeti vaka kopyası geçersiz.')
    validate_observation(value['finding']['evidence']['body'])
    return value


def notification_in(connection, identifier):
    previous = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        notice = _one(connection, 'code_notifications', identifier)
        change = _one(connection, 'code_changes', notice['change_id'])
        run = _run(_one(connection, 'code_runs', change['run_id']))
        finding = _one(connection, 'code_findings', change['finding_id'])
        before = evidence_in(connection, change['before_evidence_id']) if change['before_evidence_id'] else None
        after = evidence_in(connection, change['after_evidence_id'])
        if (change['watch_id'] != run['watch_id'] or finding['watch_id'] != run['watch_id']
                or any(e['watch_id'] != run['watch_id'] or e['identity'] != finding['identity']
                       for e in (before, after) if e is not None)):
            raise StorageError('Kod bildirimi kanıt kapsamıyla uyuşmuyor.')
        return {'id': identifier, 'domain': run['scope']['domain'], 'change': change,
                'before': before, 'after': after}
    finally: connection.row_factory = previous
