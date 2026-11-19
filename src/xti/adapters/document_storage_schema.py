"""Schema 79: publisher receipts/raw objects and lossless cold journal bodies."""

DDL = (
    'CREATE TABLE publisher_objects (sha256 TEXT PRIMARY KEY NOT NULL, raw_size INTEGER NOT NULL, body BLOB NOT NULL)',
    'CREATE TABLE publisher_fetch_runs (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, '
    'request_key TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, chain_sha256 TEXT NOT NULL)',
    'CREATE TABLE journal_payload_archives (journal TEXT NOT NULL, sequence INTEGER NOT NULL, archive_id TEXT NOT NULL, '
    'payload_sha256 TEXT NOT NULL, raw_size INTEGER NOT NULL, body BLOB NOT NULL, PRIMARY KEY(journal,sequence))',
    'CREATE TABLE journal_storage_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, '
    'payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, chain_sha256 TEXT NOT NULL)',
)
TABLES = {
    'publisher_objects': [('sha256', 'TEXT', 1, 1), ('raw_size', 'INTEGER', 1, 0), ('body', 'BLOB', 1, 0)],
    'publisher_fetch_runs': [('sequence', 'INTEGER', 1, 1)] + [(k, 'TEXT', 1, 0) for k in
        ('id', 'request_key', 'payload_json', 'payload_sha256', 'chain_sha256')],
    'journal_payload_archives': [('journal', 'TEXT', 1, 1), ('sequence', 'INTEGER', 1, 2),
        ('archive_id', 'TEXT', 1, 0), ('payload_sha256', 'TEXT', 1, 0), ('raw_size', 'INTEGER', 1, 0), ('body', 'BLOB', 1, 0)],
    'journal_storage_events': [('sequence', 'INTEGER', 1, 1)] + [(k, 'TEXT', 1, 0) for k in
        ('id', 'payload_json', 'payload_sha256', 'chain_sha256')],
}
UNIQUE_KEYS = {'publisher_objects': {('sha256',)}, 'publisher_fetch_runs': {('id',), ('request_key',)},
    'journal_payload_archives': {('journal', 'sequence')}, 'journal_storage_events': {('id',)}}
FOREIGN_KEYS = {name: set() for name in TABLES}
INDEXES = {}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for sql in DDL:
        name = sql.split()[2]
        row = connection.execute('SELECT sql FROM sqlite_schema WHERE name=?', (name,)).fetchone()
        if row is None or ' '.join(row[0].split()) != ' '.join(sql.split()):
            raise SchemaError('Yayıncı/arşiv kayıt düzeni beklenen biçimde değil.')
        if empty and connection.execute(f'SELECT 1 FROM {name} LIMIT 1').fetchone():
            raise SchemaError('Eski şemada yayıncı/arşiv tabloları boş olmalı.')


def create(connection):
    if any(connection.execute('SELECT 1 FROM sqlite_schema WHERE name=?', (name,)).fetchone() for name in TABLES):
        validate(connection, empty=True)
        return
    for sql in DDL:
        connection.execute(sql)
