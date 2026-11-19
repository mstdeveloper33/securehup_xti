"""Schema 81: reserved operation keys and immutable completed social reports."""
DDL = (
    'CREATE TABLE social_discovery_runs (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    'id TEXT NOT NULL UNIQUE, request_key TEXT NOT NULL UNIQUE, domain TEXT NOT NULL, '
    'scope_json TEXT NOT NULL, scope_sha256 TEXT NOT NULL, '
    "status TEXT NOT NULL CHECK(status IN ('running','complete','partial')), "
    'report_json TEXT, report_sha256 TEXT, started_at TEXT NOT NULL, finished_at TEXT)',
    'CREATE INDEX social_discovery_domain_idx ON social_discovery_runs (domain, sequence)',
)
TABLES = {'social_discovery_runs': [('sequence','INTEGER',1,1)] +
    [(key,'TEXT',1,0) for key in ('id','request_key','domain','scope_json','scope_sha256','status')] +
    [(key,'TEXT',0,0) for key in ('report_json','report_sha256')] + [('started_at','TEXT',1,0),('finished_at','TEXT',0,0)]}
UNIQUE_KEYS = {'social_discovery_runs': {('id',), ('request_key',)}}
FOREIGN_KEYS = {'social_discovery_runs': set()}
INDEXES = {'social_discovery_domain_idx': ('social_discovery_runs', ('domain','sequence'))}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for declaration in DDL:
        row = connection.execute('SELECT sql FROM sqlite_schema WHERE name=?', (declaration.split()[2],)).fetchone()
        if row is None or ' '.join(row[0].split()) != ' '.join(declaration.split()):
            raise SchemaError('Sosyal keşif kayıt düzeni beklenen biçimde değil.')
    if empty and connection.execute('SELECT 1 FROM social_discovery_runs LIMIT 1').fetchone():
        raise SchemaError('Eski şemada sosyal keşif tablosu boş olmalı.')


def create(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='social_discovery_runs'").fetchone():
        validate(connection, empty=True)
    else:
        for statement in DDL: connection.execute(statement)
