"""Schema85: social tracking receipts in existing collection sessions."""
import sqlite3
from xti.adapters.collection_news_schema import COLLECTION_HISTORY_DDL as COLLECTION_HISTORY_V84_DDL
from xti.adapters.collection_news_schema import COLLECTION_RECEIPT_V68_COLUMNS
from xti.adapters.collection_public_notice_schema import COLLECTION_STEP_COLUMNS

COLLECTION_RECEIPT_V84_COLUMNS = (*COLLECTION_RECEIPT_V68_COLUMNS, 'news_run_id', 'saved_search_run_id')
COLLECTION_HISTORY_DDL = (
    COLLECTION_HISTORY_V84_DDL[0],
    COLLECTION_HISTORY_V84_DDL[1]
        .replace("'search_watch'))", "'search_watch', 'social_tracking'))")
        .replace("'local'))", "'local', 'social-tracking'))"),
    COLLECTION_HISTORY_V84_DDL[2]
        .replace('REFERENCES global_saved_search_runs(id) ON DELETE RESTRICT, CHECK',
                 'REFERENCES global_saved_search_runs(id) ON DELETE RESTRICT, '
                 'social_tracking_run_id TEXT UNIQUE REFERENCES social_tracking_journal(id) ON DELETE RESTRICT, CHECK')
        .replace('(saved_search_run_id IS NOT NULL)=1', '(saved_search_run_id IS NOT NULL) + (social_tracking_run_id IS NOT NULL)=1'),
    *COLLECTION_HISTORY_V84_DDL[3:],
)


def migrate_collection_social_schema(connection):
    if not connection.in_transaction:
        raise sqlite3.OperationalError('Collection migration requires a transaction')
    connection.execute('CREATE TEMP TABLE xti_collection_steps_v84 AS SELECT rowid AS legacy_rowid,* FROM collection_session_steps')
    connection.execute('CREATE TEMP TABLE xti_collection_receipts_v84 AS SELECT rowid AS legacy_rowid,* FROM collection_step_receipts')
    connection.execute('DROP TABLE collection_step_receipts')
    connection.execute('UPDATE collection_session_steps SET depends_on_step_id=NULL')
    connection.execute('DROP TABLE collection_session_steps')
    connection.execute(COLLECTION_HISTORY_DDL[1])
    connection.execute(COLLECTION_HISTORY_DDL[2])
    for table, columns, temporary in (
        ('collection_session_steps', COLLECTION_STEP_COLUMNS, 'xti_collection_steps_v84'),
        ('collection_step_receipts', COLLECTION_RECEIPT_V84_COLUMNS, 'xti_collection_receipts_v84'),
    ):
        names = ','.join(columns)
        connection.execute(f'INSERT INTO {table} (rowid,{names}) SELECT legacy_rowid,{names} FROM {temporary} ORDER BY legacy_rowid')
    for statement in COLLECTION_HISTORY_DDL[5:]:
        connection.execute(statement)
    connection.execute('DROP TABLE temp.xti_collection_receipts_v84')
    connection.execute('DROP TABLE temp.xti_collection_steps_v84')
