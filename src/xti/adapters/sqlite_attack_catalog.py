"""Additive STIX-identity catalog with replay-checked history and atomic CTI sync."""
from dataclasses import asdict
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.cti_attack import ATTACK_SOURCE_NAME, ATTACK_SOURCE_URL, ATTACK_VERSION
from xti.domain.attack_catalog import AttackCatalogRun, AttackCatalogSnapshot, AttackCatalogSyncSummary, AttackCatalogItem, AttackCatalogPage, AttackCatalogDetails, AttackCatalogStatus, AttackCatalogRelationView, AttackCatalogPhaseView, AttackCatalogChange, CATALOG_KINDS, canonical_json, record_json, digest, valid_hash, timestamp, parse_record, validate_catalog_snapshot
_TABLES = {'entity': 'attack_catalog_entities', 'relationship': 'attack_catalog_relationships', 'phase': 'attack_catalog_phases'}
_MAX_RECORDS = {'entity': 10000, 'relationship': 100000, 'phase': 20000}
_MAX_CHANGES = 250000
_MAX_RUNS = 10000
_COUNTS = ('entity_count', 'relationship_count', 'phase_count', 'added_count', 'updated_count', 'reactivated_count', 'revoked_count', 'unchanged_count')
_RUN_COLUMNS = 'sequence,id,version,source_url,content_sha256,source_object_count,fetched_at,recorded_at,' + ','.join(_COUNTS) + ',chain_sha256'

def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('canonical UUID required')
    return value

def _key(kind, record):
    return record.key if kind == 'phase' else record.stix_id

def _chain(run, previous, changes):
    return digest(canonical_json({'run': asdict(run), 'previous': previous, 'changes': changes}))

def _identity(kind, prior, new):
    if kind == 'entity':
        return (prior.stix_id, prior.external_id, prior.stix_type) == (new.stix_id, new.external_id, new.stix_type)
    if kind == 'relationship':
        return (prior.stix_id, prior.source_stix_id, prior.relationship_type, prior.target_stix_id) == (new.stix_id, new.source_stix_id, new.relationship_type, new.target_stix_id)
    return prior.key == new.key

class SQLiteAttackCatalogRepository:

    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    @classmethod
    def _audit(cls, connection):
        try:
            rows = connection.execute(f'SELECT {_RUN_COLUMNS} FROM attack_catalog_runs ORDER BY sequence LIMIT ?', (_MAX_RUNS + 1,)).fetchall()
            if len(rows) > _MAX_RUNS:
                raise ValueError('run limit')
            runs = []
            chains = {}
            for row in rows:
                run = AttackCatalogRun(*row[:-1])
                if type(run.sequence) is not int or run.sequence < 1 or run.version != ATTACK_VERSION or (run.source_url != ATTACK_SOURCE_URL) or (type(run.source_object_count) is not int) or (not 1 <= run.source_object_count <= 30000):
                    raise ValueError('run metadata')
                _uuid(run.id)
                valid_hash(run.content_sha256)
                timestamp(run.fetched_at)
                timestamp(run.recorded_at)
                valid_hash(row[-1])
                if any((type(getattr(run, name)) is not int or not 0 <= getattr(run, name) <= 250000 for name in _COUNTS)):
                    raise ValueError('run counters')
                runs.append(run)
                chains[run.id] = row[-1]
            events = connection.execute('SELECT sequence,run_id,record_kind,record_key,action,record_json,state_sha256 FROM attack_catalog_changes ORDER BY sequence LIMIT ?', (_MAX_CHANGES + 1,)).fetchall()
            if len(events) > _MAX_CHANGES:
                raise ValueError('change limit')
            by_run = {run.id: [] for run in runs}
            for row in events:
                if row[1] not in by_run:
                    raise ValueError('unlinked change')
                by_run[row[1]].append(row)
            states = {kind: {} for kind in _TABLES}
            changes = []
            active_counts = {kind: 0 for kind in _TABLES}
            # Reconstruct every transition before accepting the materialized current rows.
            previous_chain = None
            previous_event_sequence = 0
            for run in runs:
                actions = {name: 0 for name in ('added', 'updated', 'reactivated', 'revoked')}
                fingerprints = []
                seen = set()
                for (sequence, run_id, kind, key, action, encoded, state_sha) in by_run[run.id]:
                    if kind not in states or action not in actions or type(sequence) is not int or (sequence <= previous_event_sequence) or ((kind, key) in seen):
                        raise ValueError('change order')
                    previous_event_sequence = sequence
                    seen.add((kind, key))
                    item = parse_record(kind, encoded)
                    if _key(kind, item) != key or digest(encoded) != state_sha:
                        raise ValueError('record digest')
                    prior = states[kind].get(key)
                    if action == 'added':
                        if prior is not None:
                            raise ValueError('duplicate add')
                        first_run = run.id
                        active_counts[kind] += 1
                    else:
                        if prior is None or not _identity(kind, prior[0], item):
                            raise ValueError('changed stable identity')
                        first_run = prior[2]
                        if action == 'revoked':
                            if not prior[1] or prior[4] != state_sha:
                                raise ValueError('invalid revocation')
                            active_counts[kind] -= 1
                        elif action == 'reactivated':
                            if prior[1]:
                                raise ValueError('invalid reactivation')
                            active_counts[kind] += 1
                        elif not prior[1] or prior[4] == state_sha:
                            raise ValueError('invalid update')
                    states[kind][key] = (item, action != 'revoked', first_run, run.id, state_sha)
                    actions[action] += 1
                    fingerprints.append((kind, key, action, state_sha))
                    changes.append(AttackCatalogChange(sequence, run.id, kind, key, action, item))
                expected_counts = tuple((active_counts[k] for k in ('entity', 'relationship', 'phase')))
                if expected_counts != (run.entity_count, run.relationship_count, run.phase_count) or any((actions[action] != getattr(run, action + '_count') for action in actions)):
                    raise ValueError('counter mismatch')
                if run.unchanged_count != sum(expected_counts) - actions['added'] - actions['updated'] - actions['reactivated']:
                    raise ValueError('unchanged count')
                if chains[run.id] != _chain(run, previous_chain, fingerprints):
                    raise ValueError('run chain')
                previous_chain = chains[run.id]
            for (kind, table) in _TABLES.items():
                records = connection.execute(f'SELECT * FROM {table} LIMIT ?', (_MAX_RECORDS[kind] + 1,))
                names = [column[0] for column in records.description]
                stored = records.fetchall()
                if len(stored) > _MAX_RECORDS[kind] or len(stored) != len(states[kind]):
                    raise ValueError('record count')
                for values in stored:
                    row = dict(zip(names, values))
                    key = row['id' if kind == 'phase' else 'stix_id']
                    item = parse_record(kind, row['record_json'])
                    if type(row['active']) is not int or row['active'] not in (0, 1):
                        raise ValueError('active state')
                    actual = (item, bool(row['active']), row['first_run_id'], row['last_run_id'], row['state_sha256'])
                    if states[kind].get(key) != actual or _key(kind, item) != key or digest(row['record_json']) != row['state_sha256']:
                        raise ValueError('current record differs from history')
                    if kind == 'entity' and row['external_id'] != item.external_id:
                        raise ValueError('external identity')
                    if kind == 'relationship' and (row['source_stix_id'], row['target_stix_id'], row['relationship_type']) != (item.source_stix_id, item.target_stix_id, item.relationship_type):
                        raise ValueError('relationship index')
                    if kind == 'phase' and (row['technique_stix_id'], row['tactic_stix_id']) != (item.technique_stix_id, item.tactic_stix_id):
                        raise ValueError('phase index')
            if runs:
                latest = runs[-1]
                validate_catalog_snapshot(AttackCatalogSnapshot(latest.version, latest.source_url, latest.content_sha256, latest.source_object_count, latest.fetched_at, *(tuple((value[0] for (_, value) in sorted(states[kind].items()) if value[1])) for kind in ('entity', 'relationship', 'phase'))))
            return (tuple(runs), states, tuple(changes), previous_chain)
        except (ValueError, TypeError, KeyError, ValidationError, RecursionError, AttributeError) as error:
            raise StorageError('ATT&CK katalog geçmişi veya kaynak bağı bozuk; işlem durduruldu.') from error

    @classmethod
    def apply_in_transaction(cls, connection, snapshot, *, recorded_at):
        if not connection.in_transaction:
            raise StorageError('ATT&CK kataloğu CTI ile aynı transaction içinde yazılmalı.')
        snapshot = validate_catalog_snapshot(snapshot)
        timestamp(recorded_at)
        (runs, states, old_changes, previous_chain) = cls._audit(connection)
        if len(runs) >= _MAX_RUNS:
            raise StorageError('ATT&CK senkron geçmişi güvenli sınırına ulaştı.')
        incoming = {kind: {_key(kind, item): item for item in items} for (kind, items) in zip(('entity', 'relationship', 'phase'), (snapshot.entities, snapshot.relationships, snapshot.phases))}
        # Unchanged rows retain last_run_id as the last actual state change.
        pending = []
        counts = {action: 0 for action in ('added', 'updated', 'reactivated', 'revoked', 'unchanged')}
        for kind in _TABLES:
            if len(set(states[kind]) | set(incoming[kind])) > _MAX_RECORDS[kind]:
                raise StorageError('ATT&CK kayıt geçmişi güvenli sınırına ulaştı.')
            for (key, item) in sorted(incoming[kind].items()):
                encoded = record_json(item)
                state_sha = digest(encoded)
                prior = states[kind].get(key)
                if prior is not None and (not _identity(kind, prior[0], item)):
                    raise ValidationError('ATT&CK aynı STIX kimliğinin temel kaynak kimliği değişmiş.')
                action = 'added' if prior is None else 'reactivated' if not prior[1] else 'unchanged' if prior[4] == state_sha else 'updated'
                counts[action] += 1
                if action != 'unchanged':
                    pending.append((kind, key, action, item, encoded, state_sha))
            for (key, prior) in sorted(states[kind].items()):
                if prior[1] and key not in incoming[kind]:
                    counts['revoked'] += 1
                    pending.append((kind, key, 'revoked', prior[0], record_json(prior[0]), prior[4]))
        if len(old_changes) + len(pending) > _MAX_CHANGES:
            raise StorageError('ATT&CK değişim geçmişi güvenli sınırına ulaştı.')
        identifier = str(uuid4())
        values = (identifier, snapshot.version, snapshot.source_url, snapshot.content_sha256, snapshot.source_object_count, snapshot.fetched_at, recorded_at, len(snapshot.entities), len(snapshot.relationships), len(snapshot.phases), *(counts[key] for key in ('added', 'updated', 'reactivated', 'revoked', 'unchanged')))
        cursor = connection.execute('INSERT INTO attack_catalog_runs (id,version,source_url,content_sha256,source_object_count,fetched_at,recorded_at,' + ','.join(_COUNTS) + ',chain_sha256) VALUES (' + ','.join(('?' for _ in values)) + ", '')", values)
        run = AttackCatalogRun(cursor.lastrowid, *values)
        fingerprints = []
        for (kind, key, action, item, encoded, state_sha) in pending:
            prior = states[kind].get(key)
            first_run = prior[2] if prior else run.id
            common = (encoded, state_sha, int(action != 'revoked'), first_run, run.id)
            if kind == 'entity':
                connection.execute('INSERT INTO attack_catalog_entities (stix_id,external_id,record_json,state_sha256,active,first_run_id,last_run_id) VALUES (?,?,?,?,?,?,?) ON CONFLICT(stix_id) DO UPDATE SET record_json=excluded.record_json,state_sha256=excluded.state_sha256,active=excluded.active,last_run_id=excluded.last_run_id', (key, item.external_id, *common))
            elif kind == 'relationship':
                connection.execute('INSERT INTO attack_catalog_relationships (stix_id,source_stix_id,target_stix_id,relationship_type,record_json,state_sha256,active,first_run_id,last_run_id) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(stix_id) DO UPDATE SET record_json=excluded.record_json,state_sha256=excluded.state_sha256,active=excluded.active,last_run_id=excluded.last_run_id', (key, item.source_stix_id, item.target_stix_id, item.relationship_type, *common))
            else:
                connection.execute('INSERT INTO attack_catalog_phases (id,technique_stix_id,tactic_stix_id,record_json,state_sha256,active,first_run_id,last_run_id) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET record_json=excluded.record_json,state_sha256=excluded.state_sha256,active=excluded.active,last_run_id=excluded.last_run_id', (key, item.technique_stix_id, item.tactic_stix_id, *common))
            connection.execute('INSERT INTO attack_catalog_changes (run_id,record_kind,record_key,action,record_json,state_sha256) VALUES (?,?,?,?,?,?)', (run.id, kind, key, action, encoded, state_sha))
            fingerprints.append((kind, key, action, state_sha))
        # The provisional run digest is finalized before commit in the caller transaction.
        connection.execute('UPDATE attack_catalog_runs SET chain_sha256=? WHERE id=?', (_chain(run, previous_chain, fingerprints), run.id))
        cls._audit(connection)
        return AttackCatalogSyncSummary(run)

    def validate(self):
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            self._audit(connection)

    def status(self, *, run_limit=20):
        if type(run_limit) is not int or not 1 <= run_limit <= 100:
            raise ValidationError('ATT&CK geçmiş sınırı 1–100 arasında olmalı.')
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            (runs, states, _, _) = self._audit(connection)
            return AttackCatalogStatus(tuple(reversed(runs[-run_limit:])), len(runs), *(sum((value[1] for value in states[k].values())) for k in _TABLES))

    def search(self, query, *, kind=None, active_only=True, limit=50, offset=0):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200 or (not query.isprintable()) or (kind is not None and kind not in CATALOG_KINDS) or (type(active_only) is not bool) or (type(limit) is not int) or (not 1 <= limit <= 500) or (type(offset) is not int) or (not 0 <= offset <= 10000):
            raise ValidationError('ATT&CK arama seçimi veya görünüm sınırı geçersiz.')
        query = query.strip()
        key = query.casefold()
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            (_, states, _, _) = self._audit(connection)
            found = []
            for (item, active, first_run, last_run, _) in states['entity'].values():
                if active_only and (not active) or (kind is not None and item.kind != kind):
                    continue
                if any((key in field.casefold() for field in (item.external_id, item.stix_id, item.name, *item.aliases))):
                    found.append(AttackCatalogItem(item, active, first_run, last_run))
            found.sort(key=lambda value: (value.entity.external_id, value.entity.stix_id))
            return AttackCatalogPage(query, kind, active_only, tuple(found[offset:offset + limit]), len(found), offset, offset + limit if offset + limit < len(found) else None)

    def get(self, identifier, *, relationship_limit=100, relationship_offset=0, event_limit=20):
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 100 or (not identifier.isprintable()):
            raise ValidationError('ATT&CK dış veya STIX kimliği gerekli.')
        if type(relationship_offset) is not int or not 0 <= relationship_offset <= 100_000:
            raise ValidationError('ATT&CK ilişki başlangıcı 0–100000 arasında olmalı.')
        for value in (relationship_limit, event_limit):
            if type(value) is not int or not 1 <= value <= 500:
                raise ValidationError('ATT&CK ayrıntı sınırı 1–500 arasında olmalı.')
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            (_, states, changes, _) = self._audit(connection)
            matches = [value for value in states['entity'].values() if value[0].stix_id == identifier or value[0].external_id == identifier.upper()]
            if len(matches) != 1:
                raise ValidationError('ATT&CK kimliği bulunamadı; ada göre önce arama yapın.')
            (entity, active, first_run, last_run, _) = matches[0]
            relations = [AttackCatalogRelationView(r, states['entity'][r.source_stix_id][0], states['entity'][r.target_stix_id][0], enabled) for (r, enabled, *_) in states['relationship'].values() if entity.stix_id in (r.source_stix_id, r.target_stix_id)]
            relations.sort(key=lambda value: (not value.active, value.relationship.relationship_type, value.source.external_id, value.target.external_id, value.relationship.stix_id))
            phases = [AttackCatalogPhaseView(link, states['entity'][link.technique_stix_id][0], states['entity'][link.tactic_stix_id][0], enabled) for (link, enabled, *_) in states['phase'].values() if entity.stix_id in (link.technique_stix_id, link.tactic_stix_id)]
            phases.sort(key=lambda value: (not value.active, value.technique.external_id, value.tactic.external_id))
            selected_changes = [item for item in reversed(changes) if item.record_kind == 'entity' and item.record_key == entity.stix_id]
            links = connection.execute('SELECT entity_id FROM cti_entity_assertions WHERE source_name=? AND source_reference=? AND active=1', (ATTACK_SOURCE_NAME, entity.source_url)).fetchall()
            if len(links) > 1:
                raise StorageError('ATT&CK resmî kaynak başvurusu birden çok etkin CTI kaydına bağlı.')
            if links:
                # Validate the separate graph before exposing its exact-source link.
                from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
                SQLiteCtiKnowledgeRepository(self._storage.path)._audit_attack_source(connection)
            return AttackCatalogDetails(AttackCatalogItem(entity, active, first_run, last_run), tuple(relations[relationship_offset:relationship_offset + relationship_limit]), len(relations), tuple(phases), tuple(selected_changes[:event_limit]), len(selected_changes), links[0][0] if links else None, relationship_offset, relationship_offset + relationship_limit if relationship_offset + relationship_limit < len(relations) else None)
