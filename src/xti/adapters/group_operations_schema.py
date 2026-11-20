"""Schema87: frozen group-change references; existing group bodies may be archived."""

TABLE = 'research_group_notifications'
DDL = (
    'CREATE TABLE research_group_notifications (ordinal INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    'sequence INTEGER NOT NULL UNIQUE, id TEXT NOT NULL UNIQUE, group_id TEXT NOT NULL, '
    'event_id TEXT NOT NULL UNIQUE REFERENCES research_group_journal(id) ON DELETE RESTRICT, '
    'proof_sha256 TEXT NOT NULL, chain_sha256 TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT)',
)
TABLES = {TABLE: [('ordinal', 'INTEGER', 1, 1), ('sequence', 'INTEGER', 1, 0)] + [
    (name, 'TEXT', 0 if name == 'read_at' else 1, 0) for name in (
        'id', 'group_id', 'event_id', 'proof_sha256', 'chain_sha256', 'created_at', 'read_at')]}
UNIQUE_KEYS = {TABLE: {('sequence',), ('id',), ('event_id',)}}
FOREIGN_KEYS = {TABLE: {('research_group_journal', 'event_id', 'id', 'NO ACTION', 'RESTRICT')}}
INDEXES = {}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    row = connection.execute('SELECT sql FROM sqlite_schema WHERE name=?', (TABLE,)).fetchone()
    if row is None or ' '.join(row[0].split()) != ' '.join(DDL[0].split()):
        raise SchemaError('Grup bildirim kayıt düzeni beklenen biçimde değil.')
    if empty and connection.execute('SELECT 1 FROM research_group_notifications LIMIT 1').fetchone():
        raise SchemaError('Eski şemada grup bildirim günlüğü boş olmalı.')


def create(connection):
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError('Grup işletim geçişi transaction gerektirir.')
    if connection.execute('SELECT 1 FROM sqlite_schema WHERE name=?', (TABLE,)).fetchone():
        validate(connection, empty=True)
    else:
        connection.execute(DDL[0])
