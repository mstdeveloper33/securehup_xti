"""Schema90: indexed content windows, immutable evidence and explicit review receipts."""
from xti.adapters.code_exposure_schema import CASE_EVIDENCE_DDL as PREVIOUS_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL

CASE_EVIDENCE_DDL = PREVIOUS_CASE_DDL.replace("'code_exposure'))", "'code_exposure', 'content_match'))")
DEFINITIONS = {
    'content_sources': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('revision', 'INTEGER NOT NULL'),
        ('enabled', 'INTEGER NOT NULL CHECK(enabled IN (0,1))'),
        ('definition_json', 'TEXT NOT NULL'), ('definition_sha256', 'TEXT NOT NULL'),
        ('created_at', 'TEXT NOT NULL'), ('updated_at', 'TEXT NOT NULL')],
    'content_watches': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('revision', 'INTEGER NOT NULL'),
        ('enabled', 'INTEGER NOT NULL CHECK(enabled IN (0,1))'),
        ('scope_json', 'TEXT NOT NULL'), ('scope_sha256', 'TEXT NOT NULL'),
        ('bindings_json', 'TEXT NOT NULL'), ('bindings_sha256', 'TEXT NOT NULL'),
        ('checkpoints_json', 'TEXT NOT NULL'), ('checkpoints_sha256', 'TEXT NOT NULL'),
        ('created_at', 'TEXT NOT NULL'), ('updated_at', 'TEXT NOT NULL'),
        ('last_started_at', 'TEXT'), ('last_run_id', 'TEXT')],
    'content_runs': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('watch_id', 'TEXT NOT NULL REFERENCES content_watches(id) ON DELETE RESTRICT'),
        ('watch_revision', 'INTEGER NOT NULL'), ('request_key', 'TEXT NOT NULL UNIQUE'),
        ('request_sha256', 'TEXT NOT NULL'), ('snapshot_json', 'TEXT NOT NULL'), ('snapshot_sha256', 'TEXT NOT NULL'),
        ('status', "TEXT NOT NULL CHECK(status IN ('running','complete','partial','failed','interrupted'))"),
        ('report_json', 'TEXT'), ('report_sha256', 'TEXT'), ('started_at', 'TEXT NOT NULL'), ('finished_at', 'TEXT')],
    'content_watch_targets': [
        ('watch_id', 'TEXT NOT NULL REFERENCES content_watches(id) ON DELETE RESTRICT'),
        ('target_kind', 'TEXT NOT NULL'), ('target_id', 'TEXT NOT NULL')],
    'content_watch_domains': [
        ('watch_id', 'TEXT NOT NULL REFERENCES content_watches(id) ON DELETE RESTRICT'), ('domain', 'TEXT NOT NULL')],
    'content_evidence': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('source_id', 'TEXT NOT NULL REFERENCES content_sources(id) ON DELETE RESTRICT'),
        ('identity', 'TEXT NOT NULL'), ('body_json', 'TEXT NOT NULL'), ('body_sha256', 'TEXT NOT NULL'),
        ('observed_at', 'TEXT NOT NULL')],
    'content_matches': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('watch_id', 'TEXT NOT NULL REFERENCES content_watches(id) ON DELETE RESTRICT'),
        ('target_kind', 'TEXT NOT NULL'), ('target_id', 'TEXT NOT NULL'), ('target_json', 'TEXT NOT NULL'),
        ('target_sha256', 'TEXT NOT NULL'), ('source_id', 'TEXT NOT NULL REFERENCES content_sources(id) ON DELETE RESTRICT'),
        ('identity', 'TEXT NOT NULL'), ('evidence_id', 'TEXT NOT NULL REFERENCES content_evidence(id) ON DELETE RESTRICT'),
        ('match_json', 'TEXT NOT NULL'), ('match_sha256', 'TEXT NOT NULL'),
        ('scope_revision', 'INTEGER NOT NULL'), ('first_seen', 'TEXT NOT NULL'), ('last_seen', 'TEXT NOT NULL'),
        ('observation_revision', 'INTEGER NOT NULL'), ('review_revision', 'INTEGER NOT NULL')],
    'content_match_domains': [
        ('match_id', 'TEXT NOT NULL REFERENCES content_matches(id) ON DELETE RESTRICT'), ('domain', 'TEXT NOT NULL')],
    'content_reviews': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('match_id', 'TEXT NOT NULL REFERENCES content_matches(id) ON DELETE RESTRICT'),
        ('evidence_id', 'TEXT NOT NULL REFERENCES content_evidence(id) ON DELETE RESTRICT'),
        ('decision', 'TEXT NOT NULL'), ('reason', 'TEXT NOT NULL'), ('revision', 'INTEGER NOT NULL'),
        ('observation_revision', 'INTEGER NOT NULL'), ('created_at', 'TEXT NOT NULL')],
    'content_changes': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('watch_id', 'TEXT NOT NULL REFERENCES content_watches(id) ON DELETE RESTRICT'),
        ('run_id', 'TEXT NOT NULL REFERENCES content_runs(id) ON DELETE RESTRICT'),
        ('match_id', 'TEXT NOT NULL REFERENCES content_matches(id) ON DELETE RESTRICT'), ('kind', 'TEXT NOT NULL'),
        ('before_evidence_id', 'TEXT REFERENCES content_evidence(id) ON DELETE RESTRICT'),
        ('after_evidence_id', 'TEXT NOT NULL REFERENCES content_evidence(id) ON DELETE RESTRICT'), ('created_at', 'TEXT NOT NULL')],
    'content_notifications': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('change_id', 'TEXT NOT NULL UNIQUE REFERENCES content_changes(id) ON DELETE RESTRICT'),
        ('created_at', 'TEXT NOT NULL'), ('read_at', 'TEXT')],
    'content_mutations': [
        ('id', 'TEXT NOT NULL UNIQUE'), ('request_key', 'TEXT NOT NULL UNIQUE'), ('operation', 'TEXT NOT NULL'),
        ('request_sha256', 'TEXT NOT NULL'), ('result_json', 'TEXT NOT NULL'), ('result_sha256', 'TEXT NOT NULL'),
        ('created_at', 'TEXT NOT NULL')],
}
COMPOSITE = {'content_evidence': ('source_id', 'identity', 'body_sha256'),
             'content_watch_targets': ('target_kind', 'target_id', 'watch_id'),
             'content_watch_domains': ('domain', 'watch_id'),
             'content_matches': ('watch_id', 'target_kind', 'target_id', 'identity'),
             'content_match_domains': ('domain', 'match_id'), 'content_reviews': ('match_id', 'revision')}
INDEXES = {
    'content_run_watch': ('content_runs', ('watch_id', 'sequence')),
    'content_run_status': ('content_runs', ('watch_id', 'status', 'sequence')),
    'content_match_watch': ('content_matches', ('watch_id', 'sequence')),
    'content_match_target': ('content_matches', ('target_kind', 'target_id', 'sequence')),
    'content_domain_match': ('content_match_domains', ('match_id',)),
    'content_change_watch': ('content_changes', ('watch_id', 'sequence')),
    'content_change_run': ('content_changes', ('run_id', 'sequence')),
    'content_review_match': ('content_reviews', ('match_id', 'sequence')),
    'content_watch_target_watch': ('content_watch_targets', ('watch_id',)),
    'content_watch_domain_watch': ('content_watch_domains', ('watch_id',)),
    'content_match_document': ('content_matches', ('watch_id', 'identity')),
}
DDL = tuple('CREATE TABLE ' + table + ' (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, ' +
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
            raise SchemaError('İçerik izleme kayıt düzeni beklenen biçimde değil.')
    if empty:
        for table in TABLES:
            if connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                raise SchemaError('Eski şemada içerik izleme tabloları boş olmalı.')


def create(connection):
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction: raise SchemaError('İçerik izleme geçişi transaction gerektirir.')
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='content_sources'").fetchone():
        validate(connection, empty=True)
    else:
        for statement in DDL: connection.execute(statement)
    current = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()[0]
    if ' '.join(current.split()) == ' '.join(CASE_EVIDENCE_DDL.split()): return
    if ' '.join(current.split()) != ' '.join(PREVIOUS_CASE_DDL.split()):
        raise SchemaError('İçerik izleme geçişinde vaka düzeni uyuşmuyor.')
    columns = ','.join(CASE_EVIDENCE_COLUMNS)
    connection.execute(f'CREATE TEMP TABLE xti_content_case_v89 AS SELECT rowid AS legacy_rowid,{columns} FROM case_evidence ORDER BY rowid')
    connection.execute('DROP TABLE case_evidence')
    connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(f'INSERT INTO case_evidence (rowid,{columns}) SELECT legacy_rowid,{columns} FROM xti_content_case_v89 ORDER BY legacy_rowid')
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute('DROP TABLE temp.xti_content_case_v89')
