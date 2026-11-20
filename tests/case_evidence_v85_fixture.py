"""Restore exact schema85 case DDL; refuse to discard new evidence."""
from xti.adapters.group_schema import CASE_EVIDENCE_DDL as CURRENT_DDL, PREVIOUS_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL


def case_evidence_layout_v85(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='research_group_journal'").fetchone():
        if connection.execute('SELECT 1 FROM research_group_journal LIMIT 1').fetchone():
            raise ValueError('Fixture contains schema86 group evidence')
        connection.execute('DROP TABLE research_group_journal')
    row = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()
    if row is None or row[0] != CURRENT_DDL:
        return
    if connection.execute("SELECT 1 FROM case_evidence WHERE evidence_type='research_group' LIMIT 1").fetchone():
        raise ValueError('Fixture contains schema86 case evidence')
    names = ','.join(CASE_EVIDENCE_COLUMNS)
    rows = connection.execute(f'SELECT rowid,{names} FROM case_evidence ORDER BY rowid').fetchall()
    connection.execute('DROP TABLE case_evidence')
    connection.execute(PREVIOUS_CASE_DDL)
    for row in rows:
        connection.execute(f'INSERT INTO case_evidence (rowid,{names}) VALUES ({",".join("?" for _ in row)})', row)
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
