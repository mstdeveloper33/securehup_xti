"""Faithful pre80 layout; only explicitly empty new notification data may be removed."""
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_DDL, CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL
from xti.adapters.relationship_notification_schema import CASE_EVIDENCE_DDL as CURRENT_CASE_DDL


def case_evidence_layout_v79(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='relationship_review_notifications'").fetchone():
        if connection.execute('SELECT 1 FROM relationship_review_notifications LIMIT 1').fetchone():
            raise ValueError('Fixture contains schema80 notification evidence')
        connection.execute('DROP TABLE relationship_review_notifications')
    found = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()
    if found is None or found[0] != CURRENT_CASE_DDL:
        return
    if connection.execute("SELECT 1 FROM case_evidence WHERE evidence_type='relationship_review' LIMIT 1").fetchone():
        raise ValueError('Fixture contains schema80 case evidence')
    columns = ', '.join(CASE_EVIDENCE_COLUMNS)
    rows = connection.execute(f'SELECT rowid,{columns} FROM case_evidence ORDER BY rowid').fetchall()
    connection.execute('DROP TABLE case_evidence')
    connection.execute(CASE_EVIDENCE_DDL)
    for row in rows:
        connection.execute(f'INSERT INTO case_evidence (rowid,{columns}) VALUES ({",".join("?" for _ in row)})', row)
    connection.execute(CASE_EVIDENCE_INDEX_DDL)


def legacy_case_manifest_entry(entry):
    columns, rows, objects = entry
    normalized = []
    for kind, name, sql in objects:
        if name == 'case_evidence' and sql != CASE_EVIDENCE_DDL:
            if sql != CURRENT_CASE_DDL:
                raise AssertionError('Unexpected case layout')
            sql = CASE_EVIDENCE_DDL
        normalized.append((kind, name, sql))
    return columns, rows, normalized
