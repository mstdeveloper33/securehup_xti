"""Schema86: isolated group journal plus a lossless case-evidence extension."""
from xti.adapters.social_tracking_schema import CASE_EVIDENCE_DDL as PREVIOUS_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL

CASE_EVIDENCE_DDL = PREVIOUS_CASE_DDL.replace("'social_discovery'))", "'social_discovery', 'research_group'))")
DDL = (
    'CREATE TABLE research_group_journal (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    'id TEXT NOT NULL UNIQUE, subject_id TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE, '
    'operation TEXT NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, chain_sha256 TEXT NOT NULL)',
    'CREATE INDEX research_group_journal_subject ON research_group_journal(subject_id,sequence)',
)
TABLES = {'research_group_journal': [('sequence', 'INTEGER', 1, 1)] + [
    (name, 'TEXT', 1, 0) for name in ('id', 'subject_id', 'request_key', 'operation', 'payload_json', 'payload_sha256', 'chain_sha256')]}
UNIQUE_KEYS = {'research_group_journal': {('id',), ('request_key',)}}
FOREIGN_KEYS = {'research_group_journal': set()}
INDEXES = {'research_group_journal_subject': ('research_group_journal', ('subject_id', 'sequence'))}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        row = connection.execute('SELECT sql FROM sqlite_schema WHERE name=?', (statement.split()[2],)).fetchone()
        if row is None or ' '.join(row[0].split()) != ' '.join(statement.split()):
            raise SchemaError('İnceleme grubu kayıt düzeni beklenen biçimde değil.')
    if empty and connection.execute('SELECT 1 FROM research_group_journal LIMIT 1').fetchone():
        raise SchemaError('Eski şemada inceleme grubu günlüğü boş olmalı.')


def create(connection):
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError('Grup geçişi transaction gerektirir.')
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='research_group_journal'").fetchone():
        validate(connection, empty=True)
    else:
        for statement in DDL:
            connection.execute(statement)
    current = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()[0]
    if ' '.join(current.split()) == ' '.join(CASE_EVIDENCE_DDL.split()):
        return
    if ' '.join(current.split()) != ' '.join(PREVIOUS_CASE_DDL.split()):
        raise SchemaError('Grup geçişinde vaka kayıt düzeni uyuşmuyor.')
    columns = ','.join(CASE_EVIDENCE_COLUMNS)
    connection.execute(f'CREATE TEMP TABLE xti_group_case_v85 AS SELECT rowid AS legacy_rowid,{columns} FROM case_evidence ORDER BY rowid')
    connection.execute('DROP TABLE case_evidence')
    connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(f'INSERT INTO case_evidence (rowid,{columns}) SELECT legacy_rowid,{columns} FROM xti_group_case_v85 ORDER BY legacy_rowid')
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute('DROP TABLE temp.xti_group_case_v85')
