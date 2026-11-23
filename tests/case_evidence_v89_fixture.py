"""Reconstruct pre90 case layout; never discard populated new feature tables."""
from xti.adapters.content_monitoring_schema import CASE_EVIDENCE_DDL, PREVIOUS_CASE_DDL, TABLES
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL


def case_evidence_layout_v89(connection):
    from tests.case_evidence_v90_fixture import case_evidence_layout_v90
    case_evidence_layout_v90(connection)
    # Dependency order is the reverse of the creation order.
    for table in reversed(TABLES):
        if connection.execute('SELECT 1 FROM sqlite_schema WHERE name=?', (table,)).fetchone():
            if connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                raise ValueError('Fixture contains schema90 content evidence')
            connection.execute(f'DROP TABLE {table}')
    row = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()
    if row is None or row[0] != CASE_EVIDENCE_DDL: return
    if connection.execute("SELECT 1 FROM case_evidence WHERE evidence_type='content_match' LIMIT 1").fetchone():
        raise ValueError('Fixture contains schema90 case evidence')
    names = ','.join(CASE_EVIDENCE_COLUMNS)
    rows = connection.execute(f'SELECT rowid,{names} FROM case_evidence ORDER BY rowid').fetchall()
    connection.execute('DROP TABLE case_evidence')
    connection.execute(PREVIOUS_CASE_DDL)
    for row in rows:
        connection.execute(f'INSERT INTO case_evidence (rowid,{names}) VALUES ({",".join("?" for _ in row)})', row)
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
