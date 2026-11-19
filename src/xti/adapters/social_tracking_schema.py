"""Schema 83: append-only social workflow and linked inbox notifications."""
from xti.adapters.relationship_notification_schema import CASE_EVIDENCE_DDL as PREVIOUS_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL

CASE_EVIDENCE_DDL = PREVIOUS_CASE_DDL.replace("'relationship_review'))", "'relationship_review', 'social_discovery'))")
DDL = (
    'CREATE TABLE social_tracking_journal (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    'id TEXT NOT NULL UNIQUE, request_key TEXT NOT NULL UNIQUE, operation TEXT NOT NULL, '
    'request_json TEXT NOT NULL, discovery_id TEXT REFERENCES social_discovery_runs(id) ON DELETE RESTRICT, '
    'discovery_sha256 TEXT, chain_sha256 TEXT NOT NULL, recorded_at TEXT NOT NULL)',
    'CREATE TABLE social_tracking_notifications (ordinal INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    'sequence INTEGER NOT NULL UNIQUE, id TEXT NOT NULL UNIQUE, run_id TEXT NOT NULL '
    'REFERENCES social_tracking_journal(id) ON DELETE RESTRICT, change_id TEXT NOT NULL UNIQUE, '
    'created_at TEXT NOT NULL, read_at TEXT)',
)
TABLES = {
    'social_tracking_journal': [('sequence', 'INTEGER', 1, 1)] +
        [(key, 'TEXT', 1, 0) for key in ('id', 'request_key', 'operation', 'request_json')] +
        [('discovery_id', 'TEXT', 0, 0), ('discovery_sha256', 'TEXT', 0, 0)] +
        [(key, 'TEXT', 1, 0) for key in ('chain_sha256', 'recorded_at')],
    'social_tracking_notifications': [('ordinal', 'INTEGER', 1, 1), ('sequence', 'INTEGER', 1, 0)] +
        [(key, 'TEXT', 1, 0) for key in ('id', 'run_id', 'change_id', 'created_at')] + [('read_at', 'TEXT', 0, 0)],
}
UNIQUE_KEYS = {'social_tracking_journal': {('id',), ('request_key',)},
               'social_tracking_notifications': {('sequence',), ('id',), ('change_id',)}}
FOREIGN_KEYS = {'social_tracking_journal': {('social_discovery_runs', 'discovery_id', 'id', 'NO ACTION', 'RESTRICT')},
                'social_tracking_notifications': {('social_tracking_journal', 'run_id', 'id', 'NO ACTION', 'RESTRICT')}}
INDEXES = {}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        name = statement.split()[2]
        row = connection.execute('SELECT sql FROM sqlite_schema WHERE name=?', (name,)).fetchone()
        if row is None or ' '.join(row[0].split()) != ' '.join(statement.split()):
            raise SchemaError('Sosyal inceleme/izleme kayıt düzeni beklenen biçimde değil.')
        if empty and connection.execute(f'SELECT 1 FROM {name} LIMIT 1').fetchone():
            raise SchemaError('Eski şemada sosyal izleme kayıtları boş olmalı.')


def create(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='social_tracking_journal'").fetchone():
        validate(connection, empty=True)
    else:
        for statement in DDL: connection.execute(statement)
    current = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()[0]
    if ' '.join(current.split()) == ' '.join(CASE_EVIDENCE_DDL.split()): return
    if ' '.join(current.split()) != ' '.join(PREVIOUS_CASE_DDL.split()):
        from xti.adapters.schema import SchemaError
        raise SchemaError('Sosyal vaka geçişi öncesi düzen uyuşmuyor.')
    columns = ', '.join(CASE_EVIDENCE_COLUMNS)
    connection.execute(f'CREATE TEMP TABLE xti_case_v82_copy AS SELECT rowid AS legacy_rowid, {columns} FROM case_evidence ORDER BY rowid')
    connection.execute('DROP TABLE case_evidence')
    connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(f'INSERT INTO case_evidence (rowid, {columns}) SELECT legacy_rowid, {columns} FROM xti_case_v82_copy ORDER BY legacy_rowid')
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute('DROP TABLE xti_case_v82_copy')
