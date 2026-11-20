"""Construct the real pre85 collection layout, preserving all existing rows."""
from xti.adapters.collection_social_schema import (
    COLLECTION_HISTORY_DDL, COLLECTION_HISTORY_V84_DDL,
    COLLECTION_RECEIPT_V84_COLUMNS, COLLECTION_STEP_COLUMNS,
)


def collection_layout_v84(connection):
    found = connection.execute("SELECT sql FROM sqlite_schema WHERE name='collection_step_receipts'").fetchone()
    if found is None or found[0] != COLLECTION_HISTORY_DDL[2]: return
    if connection.execute('SELECT 1 FROM collection_step_receipts WHERE social_tracking_run_id IS NOT NULL LIMIT 1').fetchone():
        raise ValueError('Fixture contains schema85 social collection receipts')
    if connection.execute("SELECT 1 FROM collection_session_steps WHERE kind='social_tracking' LIMIT 1").fetchone():
        raise ValueError('Fixture contains schema85 social collection steps')
    data = []
    for table, columns in (('collection_session_steps', COLLECTION_STEP_COLUMNS),
                           ('collection_step_receipts', COLLECTION_RECEIPT_V84_COLUMNS)):
        names = ','.join(columns)
        data.append((table, names, connection.execute(f'SELECT rowid,{names} FROM {table} ORDER BY rowid').fetchall()))
    connection.execute('DROP TABLE collection_step_receipts')
    connection.execute('UPDATE collection_session_steps SET depends_on_step_id=NULL')
    connection.execute('DROP TABLE collection_session_steps')
    connection.execute(COLLECTION_HISTORY_V84_DDL[1])
    connection.execute(COLLECTION_HISTORY_V84_DDL[2])
    for table, names, rows in data:
        for row in rows:
            connection.execute(f'INSERT INTO {table} (rowid,{names}) VALUES ({",".join("?" for _ in row)})', row)
    for statement in COLLECTION_HISTORY_V84_DDL[5:]: connection.execute(statement)
