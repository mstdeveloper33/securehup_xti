"""Bounded SQL windows for current state, history and frozen change proofs."""
from xti.adapters.sqlite_group_projection import (
    guard, current, full_record, event_row, change_proof, page_result, JOURNAL_COLUMNS, audit,
)
from xti.domain.group_ledger import summary
from xti.domain.engine_jobs import canonical_json
from xti.domain.research import identity
from xti.domain.research_groups import NOTES


def read(connection, path, operation, options, at):
    from xti.adapters.sqlite_groups import preview_in
    from xti.adapters.sqlite_evidence import page
    if operation == 'groups.audit':
        return audit(connection)
    state = guard(connection)
    snapshot = identity('groups-indexed-page-v1', state[1], state[3], state[5], operation, options.get('identifier'))
    if operation in ('groups.current', 'groups.show'):
        value = current(connection, options['identifier']) if operation == 'groups.current' else full_record(connection, options['identifier'])
        return {'model_version': 2 if operation == 'groups.current' else 1, 'record': value, 'notes': NOTES}
    if operation in ('groups.history', 'groups.changes'):
        value = current(connection, options['identifier'])
        if operation == 'groups.history':
            rows = [event_row(connection, row) for row in connection.execute(
                f'SELECT {JOURNAL_COLUMNS} FROM research_group_journal WHERE subject_id=? ORDER BY sequence LIMIT ? OFFSET ?',
                (value['id'], options['limit'], options['offset']))]
            total = value['revision']
        else:
            rows = [change_proof(connection, row[0]) for row in connection.execute(
                'SELECT event_id FROM research_group_changes WHERE subject_id=? ORDER BY revision LIMIT ? OFFSET ?',
                (value['id'], options['limit'], options['offset']))]
            total = value['change_count']
        return page_result(rows, options, total, snapshot, extra={'notes': NOTES})
    if operation in ('groups.notifications', 'groups.notification-show'):
        from xti.adapters.sqlite_group_notifications import get_notification, notification_row, COLUMNS
        if operation == 'groups.notification-show':
            return {'notification': get_notification(connection, options['identifier']), 'notes': NOTES}
        rows = []
        for row in connection.execute(f'SELECT {COLUMNS} FROM research_group_notifications ORDER BY ordinal DESC LIMIT ? OFFSET ?', (options['limit'], options['offset'])):
            value = notification_row(connection, row)
            rows.append({'id': value['id'], 'group_id': value['snapshot']['group_id'], 'created_at': value['created_at'],
                'read_at': value['read_at'], 'snapshot_sha256': value['snapshot_sha256'], 'change': value['snapshot']['change']})
        return page_result(rows, options, state[4], snapshot, extra={'notes': NOTES})
    if operation == 'groups.preview':
        rows, extra = preview_in(connection, path, options, at)
        for row in rows:
            saved = current(connection, row['id'], required=False)
            row['saved'] = summary(saved) if saved else None
        return page(rows, options, {k: options[k] for k in ('indicator_type', 'value', 'max_hops', 'time_window_hours')}, extra=extra)
    total = connection.execute('SELECT COUNT(*) FROM research_group_heads').fetchone()[0]
    records = [current(connection, row[0]) for row in connection.execute(
        'SELECT id FROM research_group_heads ORDER BY id LIMIT ? OFFSET ?', (options['limit'], options['offset']))]
    selected = page_result([summary(r) for r in records], options, total, snapshot, extra={'notes': NOTES})
    if operation == 'groups.list':
        return selected
    cache, result = {}, []
    for record in records:
        group = record['group']
        key = canonical_json([group['root'], group['scope']])
        if key not in cache:
            cache[key] = preview_in(connection, path,
                dict(indicator_type=group['root'][0], value=group['root'][1], **group['scope']), at)
        candidates, extra = cache[key]
        candidate = next((row for row in candidates if row['id'] == record['id']), None)
        status = ('indeterminate' if not extra['coverage_complete'] else 'not_in_view' if candidate is None else
            'changed' if candidate['evidence_sha256'] != group['evidence_sha256'] else
            'needs_review' if not record['review_current'] else 'current')
        if status != 'current':
            result.append({**summary(record), 'queue_state': status, 'current_evidence_sha256': candidate['evidence_sha256'] if candidate else None,
                'coverage_complete': extra['coverage_complete'], 'limitations': extra['limitations']})
    return {**selected, 'records': result, 'examined_count': len(records), 'pagination_basis': 'saved_groups_examined',
        'pending_in_window': len(result), 'notes': NOTES + ['Sayfalama saklı grup listesini sabitler; kanıt her pencerede yeniden okunur. Boş pencere sonraki sayfa yok demek değildir.']}
