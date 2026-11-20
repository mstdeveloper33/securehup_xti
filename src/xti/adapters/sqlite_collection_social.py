"""Bind social tracking to a frozen collection step, including crash recovery."""
from uuid import uuid4
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.collection_social import contract, operation_key, task_for, validate_unit
from xti.domain.collection_history import CollectionOperationToken
from xti.domain.social_discovery import canonical, fingerprint, POLICY as DISCOVERY_POLICY
from xti.domain.social_tracking import due_at


def validate_target(connection, unit):
    from xti.adapters.sqlite_social_tracking import audit
    validate_unit(unit)
    watch = audit(connection)[0]['watches'].get(unit.watch.watch_id)
    if watch is None:
        raise ValidationError('Sosyal izleme bu çalışma alanında bulunamadı.')
    task = task_for(watch, unit.asset_value)
    if task.watches[0] != unit.watch or contract(watch) != unit.contract_version:
        raise ValidationError('Sosyal izleme sürümü veya kapsamı değişmiş; yeni plan gerekli.')
    return watch


def validate_operation(connection, operation, action, request, key):
    from xti.adapters.sqlite_collection_receipts import operation_context
    from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
    session, step, unit, plan = operation_context(connection, operation)
    validate_unit(unit)
    if unit.watch.watch_id not in plan.definition.social_watch_ids:
        raise StorageError('Sosyal toplama seçimi özgün profilde yok.')
    if action == 'brand.tracking.run':
        validate_target(connection, unit)
        SQLiteCollectionHistoryRepository._current_origin(connection, plan)
        if request['identifier'] != unit.watch.watch_id or request['force'] or key != operation_key(step['id']):
            raise StorageError('Sosyal toplama işlem anahtarı veya hedefi uyuşmuyor.')
    elif action == 'brand.tracking.finish':
        from xti.adapters.sqlite_social_tracking import audit
        run = audit(connection)[0]['runs'].get(request['run_id'])
        if run is None or run['request_key'] != operation_key(step['id']) or run['watch_id'] != unit.watch.watch_id:
            raise StorageError('Sosyal toplama bitişi farklı çalışmaya ait.')
    else:
        raise StorageError('Toplama yalnız sosyal çalıştırma/bitiş işlemine bağlanabilir.')


def source_result(connection, unit, step, run_id, status):
    from xti.adapters.sqlite_social_tracking import audit
    validate_unit(unit)
    run = audit(connection)[0]['runs'].get(run_id)
    if (run is None or run['request_key'] != operation_key(step['id'])
            or run['watch_id'] != unit.watch.watch_id or run.get('watch_revision') != unit.watch.revision
            or run['scope']['domain'] != unit.asset_value or contract({'scope': run['scope']}) != unit.contract_version
            or run['status'] != status or status not in ('complete', 'partial', 'interrupted')
            or step['started_at'] is None or run['started_at'] < step['started_at']):
        raise StorageError('Sosyal sonuç dondurulmuş toplama adımıyla uyuşmuyor.')
    return run['finished_at'], tuple(sorted({'change_count': len(run['changes']), 'unchecked_count': run['unchecked_count']}.items()))


def attach_result(connection, operation, run):
    from xti.adapters.sqlite_collection_receipts import record_collection_step_receipt
    return record_collection_step_receipt(connection, operation, result_kind='social_tracking_run',
        result_id=run['id'], result_status=run['status'])


def recover_step(connection, step, at):
    """No network: preserve committed discovery or close an abandoned reservation."""
    from xti.adapters.sqlite_social_tracking import audit, write_in
    from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
    from xti.domain.social_retained import validate_scope
    state = audit(connection)[0]
    run = next((r for r in state['runs'].values() if r['request_key'] == operation_key(step.id)), None)
    if run is None:
        return False
    token = CollectionOperationToken(step.session_id, step.id, step.target_sha256)
    if run['status'] != 'running':
        attach_result(connection, token, run)
        return True
    row = connection.execute('SELECT id FROM social_discovery_runs WHERE request_key=?', (run['discovery_key'],)).fetchone()
    if row is None:
        scope = validate_scope({**run['scope'], 'tracking': run['tracking']})
        SQLiteSocialDiscoveryRepository._capacity(connection, extra=2*1024*1024+len(canonical(scope)), new=True)
        identifier = str(uuid4())
        connection.execute('INSERT INTO social_discovery_runs (id,request_key,domain,scope_json,scope_sha256,status,started_at) '
            "VALUES (?,?,?,?,?,'running',?)", (identifier, run['discovery_key'], scope['domain'], canonical(scope),
                fingerprint([DISCOVERY_POLICY, scope]), at))
    else:
        identifier = row[0]
    write_in(connection, 'brand.tracking.finish', {'run_id': run['id'], 'discovery_id': identifier,
        'idempotency_key': 'social-finish-' + run['id']}, at, collection_operation=token)
    return True


class SQLiteCollectionSocial:
    def __init__(self, path, service):
        self.storage, self.service = SQLiteAssetRepository(path), service

    def plan(self, identifiers, domain):
        return tuple(task_for(self.service.execute('brand.tracking.show', identifier=identifier)['record'], domain)
                     for identifier in identifiers)

    def contract(self, task):
        return contract(self.service.execute('brand.tracking.show', identifier=task.watches[0].watch_id)['record'])

    def due(self, task, at):
        watch = self.service.execute('brand.tracking.show', identifier=task.watches[0].watch_id)['record']
        return due_at(watch) is None or at >= due_at(watch)

    def run(self, task, operation):
        return self.service.execute_collection(task.watches[0].watch_id, operation)
