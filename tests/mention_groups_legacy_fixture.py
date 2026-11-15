"""Build genuine pre68 fixtures without discarding group or typed-watch evidence."""

from xti.adapters.global_saved_search_schema import MENTION_SCOPE_COLUMN


def remove_mention_group_schema(connection):
    from tests.collection_v68_fixture import collection_layout_v68
    existing = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'"
    )}
    new_tables = ('mention_notification_operations', 'mention_group_events')
    for table in new_tables:
        if table in existing and connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
            raise ValueError('Fixture has schema68-only group or notification evidence')
    columns = {row[1] for row in connection.execute('PRAGMA table_info(global_saved_searches)')}
    if 'mention_request_key' in columns and connection.execute(
        'SELECT 1 FROM global_saved_searches WHERE mention_request_key IS NOT NULL LIMIT 1'
    ).fetchone():
        raise ValueError('Fixture has schema68-only typed search scope')
    collection_layout_v68(connection)
    for table in new_tables:
        if table in existing:
            connection.execute(f'DROP TABLE {table}')
    if 'mention_request_key' in columns:
        connection.execute('ALTER TABLE global_saved_searches DROP COLUMN mention_request_key')


def legacy_search_manifest_entry(entry):
    """Compare all old columns/rows/DDL while allowing only schema68's NULL column."""
    columns, rows, objects = entry
    scope_columns = [column for column in columns if column[1] == 'mention_request_key']
    if not scope_columns:
        return entry
    if len(scope_columns) != 1 or scope_columns[0][0] != len(columns) - 1:
        raise AssertionError('Unexpected scoped search column position')
    if any(row[-1] is not None for row in rows):
        raise AssertionError('Legacy fixture gained a nonempty typed search scope')
    old_columns = columns[:-1]
    old_rows = [row[:-1] for row in rows]
    old_objects = [(kind, name, sql.replace(', ' + MENTION_SCOPE_COLUMN, '') if sql else sql)
                   for kind, name, sql in objects]
    return old_columns, old_rows, old_objects
