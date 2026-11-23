"""Schema91: brand references, immutable comparison/artifact evidence and review history."""
from xti.adapters.content_monitoring_schema import CASE_EVIDENCE_DDL as PREVIOUS_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL

CASE_EVIDENCE_DDL = PREVIOUS_CASE_DDL.replace("'content_match'))", "'content_match', 'brand_protection'))")
P = 'brand_protection_'
DEFINITIONS = {
 'identities': [('id','TEXT NOT NULL UNIQUE'),('organization_id','TEXT REFERENCES organizations(id) ON DELETE RESTRICT'),('revision','INTEGER NOT NULL'),('enabled','INTEGER NOT NULL CHECK(enabled IN (0,1))'),('definition_json','TEXT NOT NULL'),('definition_sha256','TEXT NOT NULL'),('created_at','TEXT NOT NULL'),('updated_at','TEXT NOT NULL')],
 'domains': [('identity_id',f'TEXT NOT NULL REFERENCES {P}identities(id) ON DELETE RESTRICT'),('domain','TEXT NOT NULL')],
 'watches': [('id','TEXT NOT NULL UNIQUE'),('identity_id',f'TEXT NOT NULL REFERENCES {P}identities(id) ON DELETE RESTRICT'),('revision','INTEGER NOT NULL'),('enabled','INTEGER NOT NULL CHECK(enabled IN (0,1))'),('scope_json','TEXT NOT NULL'),('scope_sha256','TEXT NOT NULL'),('identity_revision','INTEGER NOT NULL'),('retained_after','INTEGER NOT NULL'),('created_at','TEXT NOT NULL'),('updated_at','TEXT NOT NULL'),('last_started_at','TEXT'),('last_run_id','TEXT')],
 'runs': [('id','TEXT NOT NULL UNIQUE'),('watch_id',f'TEXT NOT NULL REFERENCES {P}watches(id) ON DELETE RESTRICT'),('request_key','TEXT NOT NULL UNIQUE'),('request_sha256','TEXT NOT NULL'),('snapshot_json','TEXT NOT NULL'),('snapshot_sha256','TEXT NOT NULL'),('status',"TEXT NOT NULL CHECK(status IN ('running','complete','partial','failed','interrupted'))"),('report_json','TEXT'),('report_sha256','TEXT'),('started_at','TEXT NOT NULL'),('finished_at','TEXT')],
 'artifacts': [('id','TEXT NOT NULL UNIQUE'),('body','BLOB NOT NULL'),('bytes','INTEGER NOT NULL'),('created_at','TEXT NOT NULL')],
 'evidence': [('id','TEXT NOT NULL UNIQUE'),('body_json','TEXT NOT NULL'),('body_sha256','TEXT NOT NULL UNIQUE'),('created_at','TEXT NOT NULL')],
 'candidates': [('id','TEXT NOT NULL UNIQUE'),('watch_id',f'TEXT NOT NULL REFERENCES {P}watches(id) ON DELETE RESTRICT'),('identity_id',f'TEXT NOT NULL REFERENCES {P}identities(id) ON DELETE RESTRICT'),('candidate_key','TEXT NOT NULL'),('kind','TEXT NOT NULL'),('url','TEXT NOT NULL'),('evidence_id',f'TEXT NOT NULL REFERENCES {P}evidence(id) ON DELETE RESTRICT'),('scope_revision','INTEGER NOT NULL'),('identity_revision','INTEGER NOT NULL'),('observation_revision','INTEGER NOT NULL'),('review_revision','INTEGER NOT NULL'),('priority','TEXT NOT NULL'),('first_seen','TEXT NOT NULL'),('last_seen','TEXT NOT NULL')],
 'reviews': [('id','TEXT NOT NULL UNIQUE'),('candidate_id',f'TEXT NOT NULL REFERENCES {P}candidates(id) ON DELETE RESTRICT'),('evidence_id',f'TEXT NOT NULL REFERENCES {P}evidence(id) ON DELETE RESTRICT'),('revision','INTEGER NOT NULL'),('observation_revision','INTEGER NOT NULL'),('decision','TEXT NOT NULL'),('reason','TEXT NOT NULL'),('created_at','TEXT NOT NULL')],
 'changes': [('id','TEXT NOT NULL UNIQUE'),('watch_id',f'TEXT NOT NULL REFERENCES {P}watches(id) ON DELETE RESTRICT'),('run_id',f'TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT'),('candidate_id',f'TEXT NOT NULL REFERENCES {P}candidates(id) ON DELETE RESTRICT'),('kind','TEXT NOT NULL'),('before_evidence_id',f'TEXT REFERENCES {P}evidence(id) ON DELETE RESTRICT'),('after_evidence_id',f'TEXT NOT NULL REFERENCES {P}evidence(id) ON DELETE RESTRICT'),('created_at','TEXT NOT NULL')],
 'notifications': [('id','TEXT NOT NULL UNIQUE'),('change_id',f'TEXT NOT NULL UNIQUE REFERENCES {P}changes(id) ON DELETE RESTRICT'),('created_at','TEXT NOT NULL'),('read_at','TEXT')],
 'cooldowns': [('id','TEXT NOT NULL UNIQUE'),('not_before','REAL NOT NULL'),('reason','TEXT NOT NULL'),('updated_at','TEXT NOT NULL')],
 'mutations': [('id','TEXT NOT NULL UNIQUE'),('request_key','TEXT NOT NULL UNIQUE'),('request_sha256','TEXT NOT NULL'),('result_json','TEXT NOT NULL'),('result_sha256','TEXT NOT NULL'),('created_at','TEXT NOT NULL')],
}
DEFINITIONS = {P+k:v for k,v in DEFINITIONS.items()}
COMPOSITE = {P+'domains':('domain','identity_id'), P+'candidates':('watch_id','candidate_key'), P+'reviews':('candidate_id','revision')}
INDEXES = {P+'identity_organization':(P+'identities',('organization_id','sequence')), P+'watch_identity':(P+'watches',('identity_id','sequence')),
 P+'run_watch':(P+'runs',('watch_id','sequence')), P+'run_status':(P+'runs',('watch_id','status','sequence')),
 P+'candidate_identity':(P+'candidates',('identity_id','sequence')),P+'candidate_watch':(P+'candidates',('watch_id','sequence')),
 P+'review_candidate':(P+'reviews',('candidate_id','sequence')),P+'change_watch':(P+'changes',('watch_id','sequence')),
 P+'change_run':(P+'changes',('run_id','sequence')),P+'domain_identity':(P+'domains',('identity_id',))}
DDL = tuple('CREATE TABLE '+table+' (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '+', '.join(k+' '+v for k,v in columns)+(', UNIQUE('+','.join(COMPOSITE[table])+')' if table in COMPOSITE else '')+')' for table,columns in DEFINITIONS.items()) + tuple('CREATE INDEX '+name+' ON '+table+' ('+','.join(columns)+')' for name,(table,columns) in INDEXES.items())
TABLES = {table:[('sequence','INTEGER',1,1)]+[(k,v.split()[0],int('NOT NULL' in v),0) for k,v in columns] for table,columns in DEFINITIONS.items()}
UNIQUE_KEYS = {table:{(k,) for k,v in columns if 'UNIQUE' in v}|({COMPOSITE[table]} if table in COMPOSITE else set()) for table,columns in DEFINITIONS.items()}
FOREIGN_KEYS = {table:{(v.split('REFERENCES ')[1].split('(')[0],k,'id','NO ACTION','RESTRICT') for k,v in columns if 'REFERENCES' in v} for table,columns in DEFINITIONS.items()}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        row=connection.execute('SELECT sql FROM sqlite_schema WHERE name=?',(statement.split()[2],)).fetchone()
        if row is None or ' '.join(row[0].split()) != ' '.join(statement.split()): raise SchemaError('Marka koruma kayıt düzeni beklenen biçimde değil.')
    if empty:
        for table in TABLES:
            if connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone(): raise SchemaError('Eski şemada marka koruma kayıtları boş olmalı.')


def create(connection):
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction: raise SchemaError('Marka koruma geçişi transaction gerektirir.')
    if connection.execute('SELECT 1 FROM sqlite_schema WHERE name=?',(P+'identities',)).fetchone(): validate(connection,empty=True)
    else:
        for statement in DDL: connection.execute(statement)
    current=connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()[0]
    if ' '.join(current.split())==' '.join(CASE_EVIDENCE_DDL.split()): return
    if ' '.join(current.split())!=' '.join(PREVIOUS_CASE_DDL.split()): raise SchemaError('Marka geçişinde vaka düzeni uyuşmuyor.')
    columns=','.join(CASE_EVIDENCE_COLUMNS)
    connection.execute(f'CREATE TEMP TABLE xti_brand_case_v90 AS SELECT rowid AS legacy_rowid,{columns} FROM case_evidence ORDER BY rowid')
    connection.execute('DROP TABLE case_evidence'); connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(f'INSERT INTO case_evidence (rowid,{columns}) SELECT legacy_rowid,{columns} FROM xti_brand_case_v90 ORDER BY legacy_rowid')
    connection.execute(CASE_EVIDENCE_INDEX_DDL); connection.execute('DROP TABLE temp.xti_brand_case_v90')
