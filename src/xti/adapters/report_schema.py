"""Schema 77: append-only report revisions, decisions and idempotency receipts."""

DDL = (
    'CREATE TABLE report_journal (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    'id TEXT NOT NULL UNIQUE, report_id TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE, '
    'operation TEXT NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, chain_sha256 TEXT NOT NULL)',
    'CREATE INDEX report_journal_subject ON report_journal(report_id,sequence)',
)
TABLES = {'report_journal': [('sequence', 'INTEGER', 1, 1)] + [
    (name, 'TEXT', 1, 0) for name in ('id', 'report_id', 'request_key', 'operation', 'payload_json', 'payload_sha256', 'chain_sha256')]}
UNIQUE_KEYS = {'report_journal': {('id',), ('request_key',)}}
FOREIGN_KEYS = {'report_journal': set()}
INDEXES = {'report_journal_subject': ('report_journal', ('report_id', 'sequence'))}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for sql in DDL:
        row = connection.execute('SELECT sql FROM sqlite_schema WHERE name=?', (sql.split()[2],)).fetchone()
        if row is None or ' '.join(row[0].split()) != ' '.join(sql.split()):
            raise SchemaError('Rapor günlüğünün kayıt düzeni beklenen biçimde değil.')
    if empty and connection.execute('SELECT 1 FROM report_journal LIMIT 1').fetchone():
        raise SchemaError('Eski şemada rapor günlüğü boş olmalı.')


def create(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='report_journal'").fetchone():
        validate(connection, empty=True)
        return
    for sql in DDL:
        connection.execute(sql)
