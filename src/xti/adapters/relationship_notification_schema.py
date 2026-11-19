"""Schema 80: immutable notification proofs and a new case evidence type."""
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_DDL as PREVIOUS_CASE_DDL, CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL

CASE_EVIDENCE_DDL = PREVIOUS_CASE_DDL.replace("'public_notice_watch'))", "'public_notice_watch', 'relationship_review'))")
DDL = (
    'CREATE TABLE relationship_review_notifications (ordinal INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    'sequence INTEGER NOT NULL UNIQUE, id TEXT NOT NULL UNIQUE, change_id TEXT NOT NULL UNIQUE, '
    'review_event_id TEXT NOT NULL REFERENCES evidence_journal(id) ON DELETE RESTRICT, '
    'payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, chain_sha256 TEXT NOT NULL, '
    'created_at TEXT NOT NULL, read_at TEXT)',
)
TABLES = {'relationship_review_notifications': [('ordinal', 'INTEGER', 1, 1), ('sequence', 'INTEGER', 1, 0)] +
    [(key, 'TEXT', 1, 0) for key in ('id', 'change_id', 'review_event_id', 'payload_json', 'payload_sha256', 'chain_sha256', 'created_at')] + [('read_at', 'TEXT', 0, 0)]}
UNIQUE_KEYS = {'relationship_review_notifications': {('sequence',), ('id',), ('change_id',)}}
FOREIGN_KEYS = {'relationship_review_notifications': {('evidence_journal', 'review_event_id', 'id', 'NO ACTION', 'RESTRICT')}}
INDEXES = {}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    row = connection.execute("SELECT sql FROM sqlite_schema WHERE name='relationship_review_notifications'").fetchone()
    if row is None or ' '.join(row[0].split()) != ' '.join(DDL[0].split()):
        raise SchemaError('İlişki bildirimi kayıt düzeni beklenen biçimde değil.')
    if empty and connection.execute('SELECT 1 FROM relationship_review_notifications LIMIT 1').fetchone():
        raise SchemaError('Eski şemada ilişki bildirimleri boş olmalı.')


def create(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='relationship_review_notifications'").fetchone():
        validate(connection, empty=True)
    else:
        connection.execute(DDL[0])
    current = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()[0]
    if ' '.join(current.split()) == ' '.join(CASE_EVIDENCE_DDL.split()):
        return
    if ' '.join(current.split()) != ' '.join(PREVIOUS_CASE_DDL.split()):
        from xti.adapters.schema import SchemaError
        raise SchemaError('Vaka kanıtı geçiş öncesi düzenle uyuşmuyor.')
    columns = ', '.join(CASE_EVIDENCE_COLUMNS)
    connection.execute(f'CREATE TEMP TABLE xti_case_v79_copy AS SELECT rowid AS legacy_rowid, {columns} FROM case_evidence ORDER BY rowid')
    connection.execute('DROP TABLE case_evidence')
    connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(f'INSERT INTO case_evidence (rowid, {columns}) SELECT legacy_rowid, {columns} FROM xti_case_v79_copy ORDER BY legacy_rowid')
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute('DROP TABLE xti_case_v79_copy')
