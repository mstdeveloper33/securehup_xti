"""Faithful pre69 collection layout without discarding collection evidence."""

from xti.adapters.collection_news_schema import (
    COLLECTION_HISTORY_DDL, COLLECTION_HISTORY_V68_DDL, COLLECTION_RECEIPT_V68_COLUMNS,
)
from xti.adapters.collection_public_notice_schema import COLLECTION_STEP_COLUMNS


def collection_layout_v68(connection):
    columns = {row[1] for row in connection.execute('PRAGMA table_info(collection_step_receipts)')}
    if 'news_run_id' not in columns:
        return
    if connection.execute("SELECT 1 FROM collection_session_steps WHERE kind IN ('news_refresh','search_watch') OR ordinal>59").fetchone():
        raise ValueError('Fixture has schema69-only collection steps')
    if connection.execute('SELECT 1 FROM collection_step_receipts WHERE news_run_id IS NOT NULL OR saved_search_run_id IS NOT NULL').fetchone():
        raise ValueError('Fixture has schema69-only collection receipts')
    if not connection.in_transaction:
        connection.execute('BEGIN')
    step_columns = ','.join(COLLECTION_STEP_COLUMNS)
    receipt_columns = ','.join(COLLECTION_RECEIPT_V68_COLUMNS)
    steps = connection.execute(f'SELECT rowid,{step_columns} FROM collection_session_steps ORDER BY rowid').fetchall()
    receipts = connection.execute(f'SELECT rowid,{receipt_columns} FROM collection_step_receipts ORDER BY rowid').fetchall()
    connection.execute('DROP TABLE collection_step_receipts')
    connection.execute('UPDATE collection_session_steps SET depends_on_step_id=NULL')
    connection.execute('DROP TABLE collection_session_steps')
    for statement in COLLECTION_HISTORY_V68_DDL[1:3]:
        connection.execute(statement)
    for table, names, rows in (('collection_session_steps', step_columns, steps),
                               ('collection_step_receipts', receipt_columns, receipts)):
        for row in rows:
            connection.execute(f'INSERT INTO {table} (rowid,{names}) VALUES ({",".join("?" for _ in row)})', row)
    for statement in COLLECTION_HISTORY_V68_DDL[5:]:
        connection.execute(statement)


def legacy_collection_manifest_entry(table, entry):
    """Compare legacy rows while verifying the exact reviewed schema extension."""
    if table not in {'collection_session_steps', 'collection_step_receipts'}:
        return entry
    columns, rows, objects = entry
    if table == 'collection_step_receipts' and any(column[1] == 'news_run_id' for column in columns):
        if [column[1] for column in columns[-2:]] != ['news_run_id', 'saved_search_run_id']:
            raise AssertionError('Unexpected news receipt columns')
        if any(row[-2:] != (None, None) for row in rows):
            raise AssertionError('Legacy fixture acquired new collection receipts')
        columns, rows = columns[:-2], [row[:-2] for row in rows]
        # New nullable UNIQUE references also add two automatic index records.
        objects = [row for row in objects if not (row[0] == 'index' and row[1] in {
            'sqlite_autoindex_collection_step_receipts_11', 'sqlite_autoindex_collection_step_receipts_12'})]
    new, old = (COLLECTION_HISTORY_DDL[1], COLLECTION_HISTORY_V68_DDL[1]) if table == 'collection_session_steps' else (COLLECTION_HISTORY_DDL[2], COLLECTION_HISTORY_V68_DDL[2])
    normalized = []
    for kind, name, sql in objects:
        if kind == 'table' and sql != old:
            if sql != new:
                raise AssertionError('Unreviewed collection layout change')
            sql = old
        normalized.append((kind, name, sql))
    return columns, rows, normalized
