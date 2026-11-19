"""Schema 82: durable provider submissions, independent of discovery receipts."""
DDL = (
    'CREATE TABLE social_enrichment_runs (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    'id TEXT NOT NULL UNIQUE, request_key TEXT NOT NULL UNIQUE, discovery_id TEXT NOT NULL '
    'REFERENCES social_discovery_runs(id) ON DELETE RESTRICT, '
    'scope_json TEXT NOT NULL, state_json TEXT NOT NULL, receipt_sha256 TEXT NOT NULL, '
    'started_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
    'CREATE INDEX social_enrichment_discovery_idx ON social_enrichment_runs (discovery_id, sequence)',
)
TABLES = {'social_enrichment_runs': [('sequence', 'INTEGER', 1, 1)] +
    [(key, 'TEXT', 1, 0) for key in ('id', 'request_key', 'discovery_id', 'scope_json', 'state_json',
                                   'receipt_sha256', 'started_at', 'updated_at')]}
UNIQUE_KEYS = {'social_enrichment_runs': {('id',), ('request_key',)}}
FOREIGN_KEYS = {'social_enrichment_runs': {('social_discovery_runs', 'discovery_id', 'id', 'NO ACTION', 'RESTRICT')}}
INDEXES = {'social_enrichment_discovery_idx': ('social_enrichment_runs', ('discovery_id', 'sequence'))}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for declaration in DDL:
        row = connection.execute('SELECT sql FROM sqlite_schema WHERE name=?', (declaration.split()[2],)).fetchone()
        if row is None or ' '.join(row[0].split()) != ' '.join(declaration.split()):
            raise SchemaError('Sosyal ek kanıt kayıt düzeni beklenen biçimde değil.')
    if empty and connection.execute('SELECT 1 FROM social_enrichment_runs LIMIT 1').fetchone():
        raise SchemaError('Eski şemada sosyal ek kanıt tablosu boş olmalı.')


def create(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='social_enrichment_runs'").fetchone():
        validate(connection, empty=True)
    else:
        for statement in DDL: connection.execute(statement)
