"""Workspace-local social discovery receipts; replay never repeats collection."""
import json
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.mentions import mention_time, mention_uuid
from xti.domain.research_history import history_key
from xti.domain.social_discovery import (
    POLICY, MAX_REPORT_BYTES, SocialDiscoveryError, canonical, fingerprint, parameters, validate_report,
)
from xti.domain.social_retained import MAX_SCOPE_BYTES, validate_scope

MAX_RUNS = 10_000
MAX_TOTAL_BYTES = 64 * 1024 * 1024
COLUMNS = 'id,request_key,domain,scope_json,scope_sha256,status,report_json,report_sha256,started_at,finished_at'


def _receipt(row):
    try:
        identifier, key, domain, scope_json, scope_hash, status, payload, digest, started, finished = row
        mention_uuid(identifier); history_key(key); mention_time(started)
        if not isinstance(scope_json,str) or len(scope_json) > MAX_SCOPE_BYTES:
            raise ValueError('Scope size')
        scope = json.loads(scope_json)
        if (validate_scope(scope) != scope or canonical(scope) != scope_json
                or fingerprint([POLICY,scope]) != scope_hash or scope['domain'] != domain):
            raise ValueError('Scope changed')
        if 'tracking' in scope and key != 'social-tracking-' + scope['tracking']['run_id']:
            raise ValueError('Tracking operation key')
        report = None
        if status == 'running':
            if payload is not None or digest is not None or finished is not None: raise ValueError('Pending state')
        else:
            if not isinstance(payload,str) or len(payload) > MAX_REPORT_BYTES: raise ValueError('Report size')
            report = validate_report(json.loads(payload))
            if canonical(report) != payload or fingerprint(report) != digest or report['scope'] != scope or report['status'] != status:
                raise ValueError('Report integrity')
            mention_time(finished)
            if finished < started: raise ValueError('Report time')
        return {'id': identifier, 'idempotency_key': key, 'scope': scope, 'status': status,
                'started_at': started, 'finished_at': finished, 'report_sha256': digest, 'report': report}
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise StorageError('Sosyal keşif makbuzu doğrulanamadı; kayıt veya kanıt değiştirilmiş olabilir.') from error


class SQLiteSocialDiscoveryRepository:
    def __init__(self, path):
        self.storage = SQLiteAssetRepository(path)

    def _capacity(self, connection, *, extra=0, new=False):
        count, size, largest = connection.execute(
            'SELECT COUNT(*), COALESCE(SUM(LENGTH(scope_json)+COALESCE(LENGTH(report_json),0)),0), '
            'COALESCE(MAX(LENGTH(report_json)),0) FROM social_discovery_runs').fetchone()
        if count+int(new) > MAX_RUNS or size+extra > MAX_TOTAL_BYTES or largest > MAX_REPORT_BYTES:
            raise StorageError('Sosyal keşif saklama sınırına ulaştı; kayıtlar değiştirilmedi.')
        allocated=connection.execute("SELECT seq FROM sqlite_sequence WHERE name='social_discovery_runs'").fetchall()
        if (len(allocated)>1 or (not allocated and count) or (allocated and allocated[0][0]!=count)):
            raise StorageError('Sosyal keşif işlem geçmişinden kayıt eksilmiş; yeni ağ işi başlatılmadı.')
        if connection.execute('SELECT 1 FROM social_discovery_runs WHERE length(id)!=36 OR length(request_key)>128 '
                f'OR length(domain)>253 OR length(scope_json)>{MAX_SCOPE_BYTES} OR length(scope_sha256)!=64 '
                'OR length(status)>16 OR length(started_at)>64 OR length(finished_at)>64 LIMIT 1').fetchone():
            raise StorageError('Sosyal keşif makbuz alanları izin verilen sınırı aşıyor.')

    def reserve(self, scope, key, at):
        scope = validate_scope(scope); key = history_key(key); mention_time(at)
        if 'tracking' in scope and key != 'social-tracking-' + scope['tracking']['run_id']:
            raise ValidationError('Saklı profil isteği izleme turuna ait olmalı.')
        with self.storage._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                self._capacity(connection)
                existing = connection.execute(f'SELECT {COLUMNS} FROM social_discovery_runs WHERE request_key=?',(key,)).fetchone()
                if existing:
                    record = _receipt(existing)
                    if record['scope'] != scope:
                        raise SocialDiscoveryError('idempotency_conflict','Tekrar anahtarı farklı bir sosyal keşif kapsamına ait.')
                    connection.rollback()
                    return {'record': record, 'replayed': True}
                self._capacity(connection,extra=MAX_REPORT_BYTES+len(canonical(scope)),new=True)
                identifier = str(uuid4())
                connection.execute('INSERT INTO social_discovery_runs '
                    '(id,request_key,domain,scope_json,scope_sha256,status,started_at) VALUES (?,?,?,?,?,?,?)',
                    (identifier,key,scope['domain'],canonical(scope),fingerprint([POLICY,scope]),'running',at))
                record = _receipt(connection.execute(f'SELECT {COLUMNS} FROM social_discovery_runs WHERE id=?',(identifier,)).fetchone())
                connection.commit()
                return {'record':record,'replayed':False}
            except BaseException:
                connection.rollback(); raise

    def finish(self, identifier, report, at):
        mention_uuid(identifier); mention_time(at); validate_report(report)
        with self.storage._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                row = connection.execute(f'SELECT {COLUMNS} FROM social_discovery_runs WHERE id=?',(identifier,)).fetchone()
                if row is None: raise SocialDiscoveryError('not_found','Sosyal keşif çalışması bulunamadı.')
                record = _receipt(row)
                if record['status'] != 'running' or record['scope'] != report['scope'] or at < record['started_at']:
                    raise SocialDiscoveryError('invalid_state','Tamamlanan çalışma değiştirilemez; kapsam ve zaman eşleşmeli.')
                payload = canonical(report)
                self._capacity(connection,extra=len(payload))
                connection.execute('UPDATE social_discovery_runs SET status=?,report_json=?,report_sha256=?,finished_at=? WHERE id=?',
                    (report['status'],payload,fingerprint(report),at,identifier))
                result = _receipt(connection.execute(f'SELECT {COLUMNS} FROM social_discovery_runs WHERE id=?',(identifier,)).fetchone())
                connection.commit()
                return {'record': result, 'replayed':False}
            except BaseException:
                connection.rollback(); raise

    def show(self, identifier):
        mention_uuid(identifier)
        with self.storage._connection(readonly=True) as connection:
            self._capacity(connection)
            row = connection.execute(f'SELECT {COLUMNS} FROM social_discovery_runs WHERE id=?',(identifier,)).fetchone()
            if row is None: raise SocialDiscoveryError('not_found','Sosyal keşif çalışması bulunamadı.')
            return {'record':_receipt(row),'replayed':False}

    def find_key(self, key):
        history_key(key)
        with self.storage._connection(readonly=True) as connection:
            self._capacity(connection)
            row = connection.execute(f'SELECT {COLUMNS} FROM social_discovery_runs WHERE request_key=?', (key,)).fetchone()
            return _receipt(row) if row is not None else None

    def list(self, *, domain=None, offset=0, limit=20):
        options = parameters('brand.discovery.list',{'offset':offset,'limit':limit,**({'domain':domain} if domain else {})})
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            self._capacity(connection)
            where, values = (' WHERE domain=?',(options['domain'],)) if domain else ('',())
            total = connection.execute('SELECT COUNT(*) FROM social_discovery_runs'+where,values).fetchone()[0]
            records = []
            for row in connection.execute(f'SELECT {COLUMNS} FROM social_discovery_runs'+where+' ORDER BY sequence DESC LIMIT ? OFFSET ?',(*values,limit,offset)):
                record = _receipt(row)
                report = record.pop('report')
                record['counts'] = report['counts'] if report else None
                records.append(record)
            return {'records':records,'total_count':total,'offset':offset,'limit':limit,'has_more':offset+len(records)<total}

    def known_links(self, domain):
        from xti.adapters.sqlite_mentions import read_mentions_catalog
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            catalog = read_mentions_catalog(connection)
            # Only this workspace and this exact company-domain search scope.
            records = sorted((r for r in catalog.records if domain in r.request.target.domains),
                             key=lambda r:(r.last_seen_at,r.id), reverse=True)
            return tuple(dict.fromkeys(r.hit.url for r in records))[:120]
