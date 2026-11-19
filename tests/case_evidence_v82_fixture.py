"""Construct the genuine pre83 case layout without discarding any evidence."""
from xti.adapters.relationship_notification_schema import CASE_EVIDENCE_DDL
from xti.adapters.social_tracking_schema import CASE_EVIDENCE_DDL as CURRENT_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL


def case_evidence_layout_v82(connection):
    for table in ('social_tracking_notifications', 'social_tracking_journal'):
        if connection.execute('SELECT 1 FROM sqlite_schema WHERE name=?', (table,)).fetchone():
            if connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                raise ValueError('Fixture contains schema83 workflow evidence')
            connection.execute(f'DROP TABLE {table}')
    found = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()
    if found is None or found[0] != CURRENT_CASE_DDL: return
    if connection.execute("SELECT 1 FROM case_evidence WHERE evidence_type='social_discovery' LIMIT 1").fetchone():
        raise ValueError('Fixture contains schema83 case evidence')
    columns = ', '.join(CASE_EVIDENCE_COLUMNS)
    rows = connection.execute(f'SELECT rowid,{columns} FROM case_evidence ORDER BY rowid').fetchall()
    connection.execute('DROP TABLE case_evidence'); connection.execute(CASE_EVIDENCE_DDL)
    for row in rows:
        connection.execute(f'INSERT INTO case_evidence (rowid,{columns}) VALUES ({",".join("?" for _ in row)})', row)
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
