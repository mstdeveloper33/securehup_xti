"""Schema 76: append-only identity and extracted report candidate decisions."""

DDL = (
    'CREATE TABLE investigation_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    'id TEXT NOT NULL UNIQUE, subject_id TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE, '
    'kind TEXT NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, chain_sha256 TEXT NOT NULL)',
    'CREATE INDEX investigation_subject ON investigation_events(subject_id,sequence)',
)
TABLES = {'investigation_events': [('sequence', 'INTEGER', 1, 1)] + [
    (name, 'TEXT', 1, 0) for name in ('id', 'subject_id', 'request_key', 'kind', 'payload_json', 'payload_sha256', 'chain_sha256')]}
UNIQUE_KEYS = {'investigation_events': {('id',), ('request_key',)}}
FOREIGN_KEYS = {'investigation_events': set()}
INDEXES = {'investigation_subject': ('investigation_events', ('subject_id', 'sequence'))}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for sql in DDL:
        row = connection.execute('SELECT sql FROM sqlite_schema WHERE name=?', (sql.split()[2],)).fetchone()
        if row is None or ' '.join(row[0].split()) != ' '.join(sql.split()):
            raise SchemaError('Araştırma karar günlüğünün kayıt düzeni beklenen biçimde değil.')
    if empty and connection.execute('SELECT 1 FROM investigation_events LIMIT 1').fetchone():
        raise SchemaError('Eski şemada araştırma karar günlüğü boş olmalı.')


def create(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='investigation_events'").fetchone():
        validate(connection, empty=True)
        return
    for sql in DDL:
        connection.execute(sql)
