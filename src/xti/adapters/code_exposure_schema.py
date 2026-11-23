"""Schema89: indexed current state, immutable masked evidence and bounded run receipts."""
from xti.adapters.group_schema import CASE_EVIDENCE_DDL as PREVIOUS_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL

CASE_EVIDENCE_DDL = PREVIOUS_CASE_DDL.replace("'research_group'))", "'research_group', 'code_exposure'))")

# One declaration drives schema metadata, avoiding divergent migration/validation lists.
DEFINITIONS = {
    'code_watches': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('domain', 'TEXT NOT NULL'), ('name', 'TEXT NOT NULL'),
        ('revision', 'INTEGER NOT NULL'), ('enabled', 'INTEGER NOT NULL CHECK(enabled IN (0,1))'),
        ('scope_json', 'TEXT NOT NULL'), ('scope_sha256', 'TEXT NOT NULL'),
        ('checkpoints_json', 'TEXT NOT NULL'), ('created_at', 'TEXT NOT NULL'),
        ('updated_at', 'TEXT NOT NULL'), ('last_started_at', 'TEXT'), ('last_run_id', 'TEXT')],
    'code_runs': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('watch_id', 'TEXT NOT NULL REFERENCES code_watches(id) ON DELETE RESTRICT'),
        ('watch_revision', 'INTEGER NOT NULL'), ('request_key', 'TEXT NOT NULL UNIQUE'),
        ('request_sha256', 'TEXT NOT NULL'), ('scope_json', 'TEXT NOT NULL'), ('scope_sha256', 'TEXT NOT NULL'),
        ('status', "TEXT NOT NULL CHECK(status IN ('running','complete','partial','failed','interrupted'))"),
        ('report_json', 'TEXT'), ('report_sha256', 'TEXT'), ('started_at', 'TEXT NOT NULL'), ('finished_at', 'TEXT')],
    'code_evidence': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('watch_id', 'TEXT NOT NULL REFERENCES code_watches(id) ON DELETE RESTRICT'),
        ('identity', 'TEXT NOT NULL'), ('body_json', 'TEXT NOT NULL'), ('body_sha256', 'TEXT NOT NULL'),
        ('observed_at', 'TEXT NOT NULL')],
    'code_findings': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('watch_id', 'TEXT NOT NULL REFERENCES code_watches(id) ON DELETE RESTRICT'),
        ('domain', 'TEXT NOT NULL'), ('source', 'TEXT NOT NULL'), ('locator_sha256', 'TEXT NOT NULL'),
        ('kind', 'TEXT NOT NULL'), ('identity', 'TEXT NOT NULL'),
        ('evidence_id', 'TEXT NOT NULL REFERENCES code_evidence(id) ON DELETE RESTRICT'),
        ('state', "TEXT NOT NULL CHECK(state IN ('observed','not_observed_in_file'))"),
        ('first_seen', 'TEXT NOT NULL'), ('last_seen', 'TEXT NOT NULL'),
        ('observation_revision', 'INTEGER NOT NULL'), ('review_revision', 'INTEGER NOT NULL')],
    'code_reviews': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('finding_id', 'TEXT NOT NULL REFERENCES code_findings(id) ON DELETE RESTRICT'),
        ('evidence_id', 'TEXT NOT NULL REFERENCES code_evidence(id) ON DELETE RESTRICT'),
        ('decision', 'TEXT NOT NULL'), ('reason', 'TEXT NOT NULL'), ('revision', 'INTEGER NOT NULL'),
        ('observation_revision', 'INTEGER NOT NULL'),
        ('created_at', 'TEXT NOT NULL')],
    'code_mutations': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('request_key', 'TEXT NOT NULL UNIQUE'), ('operation', 'TEXT NOT NULL'),
        ('request_sha256', 'TEXT NOT NULL'), ('result_json', 'TEXT NOT NULL'), ('result_sha256', 'TEXT NOT NULL'),
        ('created_at', 'TEXT NOT NULL')],
    'code_changes': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('watch_id', 'TEXT NOT NULL REFERENCES code_watches(id) ON DELETE RESTRICT'),
        ('run_id', 'TEXT NOT NULL REFERENCES code_runs(id) ON DELETE RESTRICT'),
        ('finding_id', 'TEXT NOT NULL REFERENCES code_findings(id) ON DELETE RESTRICT'), ('kind', 'TEXT NOT NULL'),
        ('before_evidence_id', 'TEXT REFERENCES code_evidence(id) ON DELETE RESTRICT'),
        ('after_evidence_id', 'TEXT NOT NULL REFERENCES code_evidence(id) ON DELETE RESTRICT'), ('created_at', 'TEXT NOT NULL')],
    'code_notifications': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('change_id', 'TEXT NOT NULL UNIQUE REFERENCES code_changes(id) ON DELETE RESTRICT'),
        ('created_at', 'TEXT NOT NULL'), ('read_at', 'TEXT')],
}
COMPOSITE = {
    'code_evidence': ('watch_id', 'identity', 'body_sha256'),
    'code_findings': ('watch_id', 'identity'),
    'code_reviews': ('finding_id', 'revision'),
}
INDEXES = {
    'code_watch_domain': ('code_watches', ('domain', 'sequence')),
    'code_run_watch': ('code_runs', ('watch_id', 'sequence')),
    'code_run_watch_status': ('code_runs', ('watch_id', 'status', 'sequence')),
    'code_run_status': ('code_runs', ('status', 'sequence')),
    'code_finding_domain': ('code_findings', ('domain', 'sequence')),
    'code_finding_watch': ('code_findings', ('watch_id', 'sequence')),
    'code_finding_document': ('code_findings', ('watch_id', 'source', 'locator_sha256')),
    'code_change_watch': ('code_changes', ('watch_id', 'sequence')),
    'code_change_run': ('code_changes', ('run_id', 'sequence')),
    'code_review_finding_sequence': ('code_reviews', ('finding_id', 'sequence')),
}
DDL = tuple(
    'CREATE TABLE ' + table + ' (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, ' +
    ', '.join(name + ' ' + declaration for name, declaration in columns) +
    (', UNIQUE(' + ','.join(COMPOSITE[table]) + ')' if table in COMPOSITE else '') + ')'
    for table, columns in DEFINITIONS.items()) + tuple(
    f'CREATE INDEX {name} ON {table} ({",".join(columns)})' for name, (table, columns) in INDEXES.items())
TABLES = {table: [('sequence', 'INTEGER', 1, 1)] +
          [(name, declaration.split()[0], int('NOT NULL' in declaration), 0) for name, declaration in columns]
          for table, columns in DEFINITIONS.items()}
UNIQUE_KEYS = {table: {(name,) for name, declaration in columns if 'UNIQUE' in declaration} |
               ({COMPOSITE[table]} if table in COMPOSITE else set()) for table, columns in DEFINITIONS.items()}
FOREIGN_KEYS = {table: {(declaration.split('REFERENCES ')[1].split('(')[0], name, 'id', 'NO ACTION', 'RESTRICT')
                       for name, declaration in columns if 'REFERENCES' in declaration}
                for table, columns in DEFINITIONS.items()}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        row = connection.execute('SELECT sql FROM sqlite_schema WHERE name=?', (statement.split()[2],)).fetchone()
        if row is None or ' '.join(row[0].split()) != ' '.join(statement.split()):
            raise SchemaError('Kod maruziyeti kayıt düzeni beklenen biçimde değil.')
    if empty:
        for table in TABLES:
            if connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                raise SchemaError('Eski şemada kod maruziyeti tabloları boş olmalı.')


def create(connection):
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction: raise SchemaError('Kod maruziyeti geçişi transaction gerektirir.')
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='code_watches'").fetchone():
        validate(connection, empty=True)
    else:
        for statement in DDL: connection.execute(statement)
    current = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()[0]
    if ' '.join(current.split()) == ' '.join(CASE_EVIDENCE_DDL.split()): return
    if ' '.join(current.split()) != ' '.join(PREVIOUS_CASE_DDL.split()):
        raise SchemaError('Kod maruziyeti geçişinde vaka düzeni uyuşmuyor.')
    columns = ','.join(CASE_EVIDENCE_COLUMNS)
    connection.execute(f'CREATE TEMP TABLE xti_code_case_v88 AS SELECT rowid AS legacy_rowid,{columns} FROM case_evidence ORDER BY rowid')
    connection.execute('DROP TABLE case_evidence')
    connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(f'INSERT INTO case_evidence (rowid,{columns}) SELECT legacy_rowid,{columns} FROM xti_code_case_v88 ORDER BY legacy_rowid')
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute('DROP TABLE temp.xti_code_case_v88')
