"""Atomic submission reservation and workspace-local conservative usage budget."""
import json
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_social_discovery import COLUMNS as DISCOVERY_COLUMNS, _receipt as discovery_receipt
from xti.domain.mentions import mention_time, mention_uuid
from xti.domain.research_history import history_key
from xti.domain.social_discovery import SocialDiscoveryError, canonical, fingerprint
from xti.domain.social_enrichment import MAX_STATE_BYTES, TERMINAL, initial_state, parameters, plan, validate_state

MAX_RUNS = 10_000
MAX_TOTAL_BYTES = 64 * 1024 * 1024
COLUMNS = 'id,request_key,discovery_id,scope_json,state_json,receipt_sha256,started_at,updated_at'


class SQLiteSocialEnrichmentRepository:
    def __init__(self, path):
        self.storage = SQLiteAssetRepository(path)

    def _capacity(self, connection, *, extra=0, new=False):
        count, size, largest = connection.execute('SELECT COUNT(*), COALESCE(SUM(LENGTH(scope_json)+LENGTH(state_json)),0), '
            'COALESCE(MAX(LENGTH(state_json)),0) FROM social_enrichment_runs').fetchone()
        if count + int(new) > MAX_RUNS or size + extra > MAX_TOTAL_BYTES or largest > MAX_STATE_BYTES:
            raise StorageError('Ek kanıt saklama sınırına ulaştı; yeni sağlayıcı isteği yapılmadı.')
        seq = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='social_enrichment_runs'").fetchall()
        if len(seq) > 1 or (not seq and count) or (seq and seq[0][0] != count):
            raise StorageError('Ek kanıt geçmişinden kayıt eksilmiş; yeni sağlayıcı isteği yapılmadı.')
        if connection.execute('SELECT 1 FROM social_enrichment_runs WHERE LENGTH(scope_json)>32768 '
            'OR LENGTH(request_key)>128 OR LENGTH(id)!=36 OR LENGTH(discovery_id)!=36 OR LENGTH(receipt_sha256)!=64 '
            'OR LENGTH(started_at)>64 OR LENGTH(updated_at)>64 LIMIT 1').fetchone():
            raise StorageError('Ek kanıt kayıt sınırları geçersiz.')

    def _discovery(self, connection, identifier):
        row = connection.execute(f'SELECT {DISCOVERY_COLUMNS} FROM social_discovery_runs WHERE id=?', (identifier,)).fetchone()
        if row is None: raise SocialDiscoveryError('not_found', 'Bu çalışma alanında sosyal keşif bulunamadı.')
        return discovery_receipt(row)

    def discovery(self, identifier):
        mention_uuid(identifier)
        with self.storage._connection(readonly=True) as connection:
            return self._discovery(connection, identifier)

    def _record(self, connection, row):
        try:
            identifier, key, discovery_id, raw_scope, raw_state, digest, started, updated = row
            mention_uuid(identifier); mention_uuid(discovery_id); history_key(key)
            mention_time(started); mention_time(updated)
            if updated < started or len(raw_scope) > 32768 or len(raw_state) > MAX_STATE_BYTES:
                raise ValueError('Size/time')
            scope, state = json.loads(raw_scope), json.loads(raw_state)
            options = parameters('brand.enrichment.plan', {key: scope[key] for key in ('discovery_id', 'max_profiles', 'include_found')})
            discovery = self._discovery(connection, discovery_id)
            if (scope['discovery_id'] != discovery_id or scope != plan(discovery, options)
                    or not scope['targets'] or canonical(scope) != raw_scope or canonical(state) != raw_state):
                raise ValueError('Scope')
            validate_state(state, scope)
            if state['checked_at'] is not None and not started <= state['checked_at'] <= updated:
                raise ValueError('Evidence time')
            expected = fingerprint([identifier, key, scope, state, started, updated])
            if digest != expected: raise ValueError('Digest')
            return {'id': identifier, 'idempotency_key': key, 'scope': scope, 'state': state,
                    'started_at': started, 'updated_at': updated, 'receipt_sha256': digest,
                    'page_states': {r['url']: r['state'] for r in discovery['report']['profiles'] if r['url'] in scope['targets']}}
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            raise StorageError('Ek sağlayıcı makbuzu veya bağlı keşif kanıtı doğrulanamadı.') from error

    def _find(self, connection, scope, key):
        row = connection.execute(f'SELECT {COLUMNS} FROM social_enrichment_runs WHERE request_key=?', (key,)).fetchone()
        if row is None: return None
        record = self._record(connection, row)
        if record['scope'] != scope: raise SocialDiscoveryError('idempotency_conflict', 'Tekrar anahtarı farklı ek kanıt kapsamına ait.')
        return {'record': record, 'replayed': True}

    def find(self, scope, key):
        history_key(key)
        with self.storage._connection(readonly=True) as connection:
            self._capacity(connection)
            return self._find(connection, scope, key)

    def reserve(self, scope, key, at, daily_limit):
        history_key(key); mention_time(at)
        if type(daily_limit) is not int or not 1 <= daily_limit <= 50_000:
            raise SocialDiscoveryError('invalid_parameters', 'Günlük sağlayıcı sınırı geçersiz.')
        with self.storage._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                self._capacity(connection)
                found = self._find(connection, scope, key)
                if found: connection.rollback(); return found
                used, outstanding = 0, 0
                for row in connection.execute(f'SELECT {COLUMNS} FROM social_enrichment_runs'):
                    record = self._record(connection, row)
                    if at < record['started_at']: raise StorageError('Saat işlem geçmişinin gerisinde; yeni istek yapılmadı.')
                    if record['started_at'][:10] == at[:10]: used += len(record['scope']['targets'])
                    if record['state']['status'] in ('reserved', 'pending'): outstanding += MAX_STATE_BYTES
                if used + len(scope['targets']) > daily_limit:
                    raise SocialDiscoveryError('budget_exhausted', 'Bu çalışma alanında günlük Bright Data profil sınırı doldu.')
                self._capacity(connection, extra=outstanding + MAX_STATE_BYTES + len(canonical(scope)), new=True)
                identifier, state = str(uuid4()), initial_state()
                digest = fingerprint([identifier, key, scope, state, at, at])
                connection.execute('INSERT INTO social_enrichment_runs '
                    '(id,request_key,discovery_id,scope_json,state_json,receipt_sha256,started_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                    (identifier, key, scope['discovery_id'], canonical(scope), canonical(state), digest, at, at))
                record = self._record(connection, connection.execute(f'SELECT {COLUMNS} FROM social_enrichment_runs WHERE id=?', (identifier,)).fetchone())
                connection.commit()
                return {'record': record, 'replayed': False}
            except BaseException:
                connection.rollback(); raise

    def update(self, record, state, at):
        mention_time(at); validate_state(state, record['scope'])
        with self.storage._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                self._capacity(connection, extra=len(canonical(state)))
                row = connection.execute(f'SELECT {COLUMNS} FROM social_enrichment_runs WHERE id=?', (record['id'],)).fetchone()
                if row is None: raise SocialDiscoveryError('not_found', 'Ek kanıt çalışması bulunamadı.')
                current = self._record(connection, row)
                if current != record or current['state']['status'] in TERMINAL or at < record['updated_at']:
                    raise SocialDiscoveryError('invalid_state', 'Ek kanıt çalışması değişti veya tamamlandı.')
                if state['status'] == 'reserved' or (current['state']['status'] == 'pending' and
                        (state['snapshot_id'] != current['state']['snapshot_id'] or state['status'] == 'submission_unknown')):
                    raise SocialDiscoveryError('invalid_state', 'Sağlayıcı sonuç kimliği veya durum geçişi değiştirilemez.')
                if current['state']['status'] == 'reserved' and state['status'] not in ('pending', 'submission_unknown'):
                    raise SocialDiscoveryError('invalid_state', 'İlk gönderim doğrudan tamamlanmış sonuç olamaz.')
                digest = fingerprint([record['id'], record['idempotency_key'], record['scope'], state, record['started_at'], at])
                connection.execute('UPDATE social_enrichment_runs SET state_json=?,receipt_sha256=?,updated_at=? WHERE id=?',
                    (canonical(state), digest, at, record['id']))
                result = self._record(connection, connection.execute(f'SELECT {COLUMNS} FROM social_enrichment_runs WHERE id=?', (record['id'],)).fetchone())
                connection.commit()
                return {'record': result, 'replayed': False}
            except BaseException:
                connection.rollback(); raise

    def show(self, identifier):
        mention_uuid(identifier)
        with self.storage._connection(readonly=True) as connection:
            self._capacity(connection)
            row = connection.execute(f'SELECT {COLUMNS} FROM social_enrichment_runs WHERE id=?', (identifier,)).fetchone()
            if row is None: raise SocialDiscoveryError('not_found', 'Bu çalışma alanında ek kanıt çalışması bulunamadı.')
            return {'record': self._record(connection, row), 'replayed': False}

    def list(self, **options):
        options = parameters('brand.enrichment.list', options)
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            self._capacity(connection)
            where, values = (' WHERE discovery_id=?', (options['discovery_id'],)) if options.get('discovery_id') else ('', ())
            total = connection.execute('SELECT COUNT(*) FROM social_enrichment_runs' + where, values).fetchone()[0]
            records = [self._record(connection, row) for row in connection.execute(
                f'SELECT {COLUMNS} FROM social_enrichment_runs' + where + ' ORDER BY sequence DESC LIMIT ? OFFSET ?',
                (*values, options['limit'], options['offset']))]
            return {'records': records, 'total_count': total, 'offset': options['offset'], 'limit': options['limit'],
                    'has_more': options['offset'] + len(records) < total}
