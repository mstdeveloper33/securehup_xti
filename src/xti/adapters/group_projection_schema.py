"""Schema88: rebuildable, guarded group read models; original journals stay intact."""

DDL = (
    'CREATE TABLE research_group_guard (id INTEGER PRIMARY KEY NOT NULL CHECK(id=1), dirty INTEGER NOT NULL, '
    'generation INTEGER NOT NULL, event_count INTEGER NOT NULL, event_chain TEXT, notice_count INTEGER NOT NULL, notice_chain TEXT)',
    'CREATE TABLE research_group_states (event_id TEXT PRIMARY KEY NOT NULL REFERENCES research_group_journal(id) ON DELETE RESTRICT, '
    'subject_id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot_event_id TEXT NOT NULL REFERENCES research_group_journal(id) ON DELETE RESTRICT, '
    'state_json TEXT NOT NULL, state_sha256 TEXT NOT NULL, UNIQUE(subject_id,revision))',
    'CREATE TABLE research_group_heads (id TEXT PRIMARY KEY NOT NULL, event_id TEXT NOT NULL UNIQUE REFERENCES research_group_states(event_id) ON DELETE RESTRICT, '
    'root_type TEXT NOT NULL, root_value TEXT NOT NULL)',
    'CREATE INDEX research_group_heads_root ON research_group_heads(root_type,root_value,id)',
    'CREATE TABLE research_group_changes (event_id TEXT PRIMARY KEY NOT NULL REFERENCES research_group_journal(id) ON DELETE RESTRICT, '
    'subject_id TEXT NOT NULL, revision INTEGER NOT NULL, proof_json TEXT NOT NULL, proof_sha256 TEXT NOT NULL, UNIQUE(subject_id,revision))',
)
TABLES = {
    'research_group_guard': [('id', 'INTEGER', 1, 1), ('dirty', 'INTEGER', 1, 0), ('generation', 'INTEGER', 1, 0),
        ('event_count', 'INTEGER', 1, 0), ('event_chain', 'TEXT', 0, 0), ('notice_count', 'INTEGER', 1, 0), ('notice_chain', 'TEXT', 0, 0)],
    'research_group_states': [('event_id', 'TEXT', 1, 1), ('subject_id', 'TEXT', 1, 0), ('revision', 'INTEGER', 1, 0),
        ('snapshot_event_id', 'TEXT', 1, 0), ('state_json', 'TEXT', 1, 0), ('state_sha256', 'TEXT', 1, 0)],
    'research_group_heads': [('id', 'TEXT', 1, 1), ('event_id', 'TEXT', 1, 0), ('root_type', 'TEXT', 1, 0), ('root_value', 'TEXT', 1, 0)],
    'research_group_changes': [('event_id', 'TEXT', 1, 1), ('subject_id', 'TEXT', 1, 0), ('revision', 'INTEGER', 1, 0),
        ('proof_json', 'TEXT', 1, 0), ('proof_sha256', 'TEXT', 1, 0)],
}
UNIQUE_KEYS = {name: {(columns[0][0],)} for name, columns in TABLES.items()}
UNIQUE_KEYS['research_group_states'].add(('subject_id', 'revision'))
UNIQUE_KEYS['research_group_changes'].add(('subject_id', 'revision'))
UNIQUE_KEYS['research_group_heads'].add(('event_id',))
UNIQUE_KEYS['research_group_guard'] = set()
FOREIGN_KEYS = {name: set() for name in TABLES}
FOREIGN_KEYS['research_group_states'] = {('research_group_journal', key, 'id', 'NO ACTION', 'RESTRICT') for key in ('event_id', 'snapshot_event_id')}
FOREIGN_KEYS['research_group_heads'] = {('research_group_states', 'event_id', 'event_id', 'NO ACTION', 'RESTRICT')}
FOREIGN_KEYS['research_group_changes'] = {('research_group_journal', 'event_id', 'id', 'NO ACTION', 'RESTRICT')}
INDEXES = {'research_group_heads_root': ('research_group_heads', ('root_type', 'root_value', 'id'))}

# An interrupted transaction rolls back both state and guard. SQL edits outside
# the reducer invalidate the projection; reads never silently repair evidence.
TRIGGERS = tuple(
    f'CREATE TRIGGER group_guard_{table}_{action.lower()} AFTER {action} ON {table} '
    + (("WHEN (OLD.journal='research_group_journal' OR NEW.journal='research_group_journal') " if action == 'UPDATE' else
        "WHEN " + ("NEW" if action == 'INSERT' else "OLD") + ".journal='research_group_journal' ") if table == 'journal_payload_archives' else '')
    + 'BEGIN UPDATE research_group_guard SET dirty=1 WHERE id=1; END'
    for table in ('research_group_journal', 'research_group_states', 'research_group_heads', 'research_group_changes',
                  'research_group_notifications', 'journal_payload_archives')
    for action in ('INSERT', 'UPDATE', 'DELETE'))


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for statement in DDL + TRIGGERS:
        row = connection.execute('SELECT sql FROM sqlite_schema WHERE name=?', (statement.split()[2],)).fetchone()
        if empty and row is None and statement in TRIGGERS and not connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (statement.split()[6],)).fetchone():
            continue  # Test/legacy staging may predate the trigger's source table.
        if row is None or ' '.join(row[0].split()) != ' '.join(statement.split()):
            raise SchemaError('Grup güncel durum kayıt düzeni beklenen biçimde değil.')
    if empty:
        for name in TABLES.keys() - {'research_group_guard'}:
            if connection.execute(f'SELECT 1 FROM {name} LIMIT 1').fetchone():
                raise SchemaError('Eski şemada grup güncel durum tabloları boş olmalı.')


def create(connection):
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError('Grup güncel durum geçişi transaction gerektirir.')
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='research_group_guard'").fetchone():
        for statement in TRIGGERS:
            if not connection.execute('SELECT 1 FROM sqlite_schema WHERE name=?', (statement.split()[2],)).fetchone():
                connection.execute(statement)
        validate(connection, empty=True)
        if (not connection.execute('SELECT 1 FROM research_group_journal LIMIT 1').fetchone()
                and not connection.execute('SELECT 1 FROM research_group_notifications LIMIT 1').fetchone()):
            from xti.adapters.sqlite_group_projection import guard
            guard(connection)
            return
    else:
        for statement in DDL + TRIGGERS:
            connection.execute(statement)
        connection.execute('INSERT INTO research_group_guard VALUES (1,1,0,0,NULL,0,NULL)')
    from xti.adapters.sqlite_group_projection import rebuild
    rebuild(connection)
