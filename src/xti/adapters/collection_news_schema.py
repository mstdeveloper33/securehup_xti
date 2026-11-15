"""Schema69 collection extension; existing evidence bytes and rowids survive."""

import sqlite3

from xti.adapters.collection_public_notice_schema import (
    COLLECTION_HISTORY_DDL as COLLECTION_HISTORY_V68_DDL,
    COLLECTION_STEP_COLUMNS, COLLECTION_RECEIPT_V60_COLUMNS,
)

COLLECTION_RECEIPT_V68_COLUMNS = (*COLLECTION_RECEIPT_V60_COLUMNS, "public_notice_run_id")
COLLECTION_HISTORY_DDL = (
    COLLECTION_HISTORY_V68_DDL[0],
    COLLECTION_HISTORY_V68_DDL[1]
        .replace("BETWEEN 1 AND 59", "BETWEEN 1 AND 62")
        .replace("'public_notice'))", "'public_notice', 'news_refresh', 'search_watch'))")
        .replace("'hibp'))", "'hibp', 'cisa', 'ncsc', 'cert-fr', 'local'))"),
    COLLECTION_HISTORY_V68_DDL[2]
        .replace("REFERENCES public_notice_runs(id) ON DELETE RESTRICT, CHECK",
                 "REFERENCES public_notice_runs(id) ON DELETE RESTRICT, "
                 "news_run_id TEXT UNIQUE REFERENCES news_runs(id) ON DELETE RESTRICT, "
                 "saved_search_run_id TEXT UNIQUE REFERENCES global_saved_search_runs(id) ON DELETE RESTRICT, CHECK")
        .replace("(public_notice_run_id IS NOT NULL)=1", "(public_notice_run_id IS NOT NULL) + "
                 "(news_run_id IS NOT NULL) + (saved_search_run_id IS NOT NULL)=1"),
    *COLLECTION_HISTORY_V68_DDL[3:],
)


def migrate_collection_news_schema(connection):
    """Rebuild the two bounded tables in the backed-up caller transaction."""
    if not connection.in_transaction:
        raise sqlite3.OperationalError("Collection migration requires a transaction")
    connection.execute("CREATE TEMP TABLE xti_collection_steps_v68 AS "
                       "SELECT rowid AS legacy_rowid,* FROM collection_session_steps")
    connection.execute("CREATE TEMP TABLE xti_collection_receipts_v68 AS "
                       "SELECT rowid AS legacy_rowid,* FROM collection_step_receipts")
    connection.execute("DROP TABLE collection_step_receipts")
    connection.execute("UPDATE collection_session_steps SET depends_on_step_id=NULL")
    connection.execute("DROP TABLE collection_session_steps")
    connection.execute(COLLECTION_HISTORY_DDL[1])
    connection.execute(COLLECTION_HISTORY_DDL[2])
    steps = ",".join(COLLECTION_STEP_COLUMNS)
    receipts = ",".join(COLLECTION_RECEIPT_V68_COLUMNS)
    connection.execute(f"INSERT INTO collection_session_steps (rowid,{steps}) "
                       f"SELECT legacy_rowid,{steps} FROM xti_collection_steps_v68 ORDER BY legacy_rowid")
    connection.execute(f"INSERT INTO collection_step_receipts (rowid,{receipts}) "
                       f"SELECT legacy_rowid,{receipts} FROM xti_collection_receipts_v68 ORDER BY legacy_rowid")
    for statement in COLLECTION_HISTORY_DDL[5:]:
        connection.execute(statement)
    connection.execute("DROP TABLE temp.xti_collection_receipts_v68")
    connection.execute("DROP TABLE temp.xti_collection_steps_v68")
