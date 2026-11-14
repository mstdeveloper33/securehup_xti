"""Versioned collection layout for an explicit public incident catalog task."""

import sqlite3


COLLECTION_HISTORY_V60_DDL = ('CREATE TABLE collection_sessions (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT '
 'NOT NULL UNIQUE, root_id TEXT NOT NULL REFERENCES collection_sessions(id) ON DELETE RESTRICT, '
 'parent_id TEXT UNIQUE REFERENCES collection_sessions(id) ON DELETE RESTRICT, generation INTEGER '
 'NOT NULL CHECK (generation BETWEEN 1 AND 100), profile_event_id TEXT REFERENCES '
 'collection_profile_events(id) ON DELETE RESTRICT, definition_json TEXT NOT NULL, '
 'definition_sha256 TEXT NOT NULL, plan_json TEXT NOT NULL, plan_sha256 TEXT NOT NULL, '
 'executor_contract_version INTEGER NOT NULL CHECK (executor_contract_version=1), status TEXT NOT '
 "NULL CHECK (status IN ('running', 'complete', 'partial', 'failed', 'interrupted')), started_at "
 'TEXT NOT NULL, finished_at TEXT, stop_reason TEXT, analysis_status TEXT NOT NULL CHECK '
 "(analysis_status IN ('pending', 'complete', 'failed')), analysis_recorded_at TEXT, UNIQUE "
 '(root_id, generation))',
 'CREATE TABLE collection_session_steps (id TEXT PRIMARY KEY NOT NULL, session_id TEXT NOT NULL '
 'REFERENCES collection_sessions(id) ON DELETE RESTRICT, ordinal INTEGER NOT NULL CHECK (ordinal '
 "BETWEEN 1 AND 58), step_key TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('scan', "
 "'discovery', 'ioc', 'username_watch', 'ransomware_refresh', 'ransomware_watch')), source TEXT "
 "NOT NULL CHECK (source IN ('crt.sh', 'urlscan', 'theharvester', 'feodo', 'certpl', 'maigret', "
 "'sherlock', 'threatcluster', 'ransomlook')), watch_id TEXT, target_sha256 TEXT NOT NULL, "
 'depends_on_step_id TEXT REFERENCES collection_session_steps(id) ON DELETE RESTRICT, scan_job_id '
 'TEXT UNIQUE REFERENCES scan_jobs(id) ON DELETE RESTRICT, status TEXT NOT NULL CHECK (status IN '
 "('pending', 'running', 'complete', 'partial', 'failed', 'interrupted', 'skipped')), started_at "
 'TEXT, finished_at TEXT, error_code TEXT, UNIQUE (session_id, ordinal), UNIQUE (session_id, '
 'step_key))',
 'CREATE TABLE collection_step_receipts (step_id TEXT PRIMARY KEY NOT NULL REFERENCES '
 'collection_session_steps(id) ON DELETE RESTRICT, recorded_at TEXT NOT NULL, result_status TEXT '
 "NOT NULL CHECK (result_status IN ('complete', 'partial', 'failed', 'interrupted')), summary_json "
 'TEXT NOT NULL, summary_sha256 TEXT NOT NULL, scan_attempt_id TEXT UNIQUE REFERENCES '
 'scan_attempts(id) ON DELETE RESTRICT, discovery_run_id TEXT UNIQUE REFERENCES '
 'surface_discovery_runs(id) ON DELETE RESTRICT, feed_run_id TEXT UNIQUE REFERENCES '
 'cti_feed_runs(id) ON DELETE RESTRICT, username_run_id TEXT UNIQUE REFERENCES '
 'brand_username_watch_runs(id) ON DELETE RESTRICT, threatcluster_source_run_id TEXT UNIQUE '
 'REFERENCES ransomware_claim_runs(id) ON DELETE RESTRICT, ransomlook_source_run_id TEXT UNIQUE '
 'REFERENCES ransomlook_claim_runs(id) ON DELETE RESTRICT, threatcluster_watch_run_id TEXT UNIQUE '
 'REFERENCES ransomware_watch_runs(id) ON DELETE RESTRICT, ransomlook_watch_run_id TEXT UNIQUE '
 'REFERENCES ransomlook_watch_runs(id) ON DELETE RESTRICT, CHECK ((scan_attempt_id IS NOT NULL) + '
 '(discovery_run_id IS NOT NULL) + (feed_run_id IS NOT NULL) + (username_run_id IS NOT NULL) + '
 '(threatcluster_source_run_id IS NOT NULL) + (ransomlook_source_run_id IS NOT NULL) + '
 '(threatcluster_watch_run_id IS NOT NULL) + (ransomlook_watch_run_id IS NOT NULL)=1))',
 'CREATE INDEX collection_sessions_status_sequence ON collection_sessions(status, sequence)',
 'CREATE INDEX collection_sessions_root_generation ON collection_sessions(root_id, generation)',
 'CREATE INDEX collection_session_steps_session_ordinal ON collection_session_steps(session_id, '
 'ordinal)',
 'CREATE INDEX collection_session_steps_scan_job ON collection_session_steps(scan_job_id)')

# Keep the exact v56–60 declarations available for legacy validation. The
# extension changes only the bounded task set and the new nullable receipt FK.
COLLECTION_HISTORY_DDL = (
    COLLECTION_HISTORY_V60_DDL[0],
    COLLECTION_HISTORY_V60_DDL[1]
        .replace("BETWEEN 1 AND 58", "BETWEEN 1 AND 59")
        .replace("'ransomware_watch'))", "'ransomware_watch', 'public_notice'))")
        .replace("'ransomlook'))", "'ransomlook', 'hibp'))"),
    COLLECTION_HISTORY_V60_DDL[2]
        .replace("REFERENCES ransomlook_watch_runs(id) ON DELETE RESTRICT, CHECK",
                 "REFERENCES ransomlook_watch_runs(id) ON DELETE RESTRICT, "
                 "public_notice_run_id TEXT UNIQUE REFERENCES public_notice_runs(id) ON DELETE RESTRICT, CHECK")
        .replace("(ransomlook_watch_run_id IS NOT NULL)=1", "(ransomlook_watch_run_id IS NOT NULL) + (public_notice_run_id IS NOT NULL)=1"),
    *COLLECTION_HISTORY_V60_DDL[3:],
)

COLLECTION_STEP_COLUMNS = (
    "id", "session_id", "ordinal", "step_key", "kind", "source", "watch_id",
    "target_sha256", "depends_on_step_id", "scan_job_id", "status", "started_at",
    "finished_at", "error_code",
)
COLLECTION_RECEIPT_V60_COLUMNS = (
    "step_id", "recorded_at", "result_status", "summary_json", "summary_sha256",
    "scan_attempt_id", "discovery_run_id", "feed_run_id", "username_run_id",
    "threatcluster_source_run_id", "ransomlook_source_run_id",
    "threatcluster_watch_run_id", "ransomlook_watch_run_id",
)


def migrate_collection_public_notice_schema(connection: sqlite3.Connection) -> None:
    """Rebuild only steps and receipts inside the caller's backed-up transaction.

    A temporary SQL copy retains rowids and every legacy value without loading
    histories into Python memory. No table is renamed, so SQLite cannot rewrite
    existing foreign keys to temporary names. Foreign-key enforcement stays on.
    The only incoming reference to steps is receipts. After its SQL copy is
    retained, the old table's optional self-links are cleared so RESTRICT does
    not prevent dropping it. The original self-links are restored verbatim
    with the copied rows; any failure rolls this entire transaction back.
    """
    if not connection.in_transaction:
        raise sqlite3.OperationalError("Collection migration requires a transaction")
    connection.execute(
        "CREATE TEMP TABLE xti_collection_steps_v60 AS "
        "SELECT rowid AS legacy_rowid, * FROM collection_session_steps"
    )
    connection.execute(
        "CREATE TEMP TABLE xti_collection_receipts_v60 AS "
        "SELECT rowid AS legacy_rowid, * FROM collection_step_receipts"
    )
    connection.execute("DROP TABLE collection_step_receipts")
    connection.execute("UPDATE collection_session_steps SET depends_on_step_id=NULL")
    connection.execute("DROP TABLE collection_session_steps")
    connection.execute(COLLECTION_HISTORY_DDL[1])
    connection.execute(COLLECTION_HISTORY_DDL[2])
    step_columns = ", ".join(COLLECTION_STEP_COLUMNS)
    receipt_columns = ", ".join(COLLECTION_RECEIPT_V60_COLUMNS)
    connection.execute(
        f"INSERT INTO collection_session_steps (rowid, {step_columns}) "
        f"SELECT legacy_rowid, {step_columns} FROM xti_collection_steps_v60 ORDER BY legacy_rowid"
    )
    connection.execute(
        f"INSERT INTO collection_step_receipts (rowid, {receipt_columns}, public_notice_run_id) "
        f"SELECT legacy_rowid, {receipt_columns}, NULL FROM xti_collection_receipts_v60 ORDER BY legacy_rowid"
    )
    for statement in COLLECTION_HISTORY_DDL[5:]:
        connection.execute(statement)
    connection.execute("DROP TABLE temp.xti_collection_receipts_v60")
    connection.execute("DROP TABLE temp.xti_collection_steps_v60")
