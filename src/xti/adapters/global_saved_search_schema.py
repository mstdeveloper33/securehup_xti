"""Schema65: explicit general searches and immutable, shared result snapshots."""


GLOBAL_SAVED_SEARCH_DDL = (
    "CREATE TABLE global_saved_searches ("
    "id TEXT PRIMARY KEY NOT NULL, name_key TEXT NOT NULL UNIQUE, "
    "display_name TEXT NOT NULL, query TEXT NOT NULL, kinds_json TEXT NOT NULL, "
    "include_inactive INTEGER NOT NULL CHECK (include_inactive IN (0,1)), "
    "active INTEGER NOT NULL CHECK (active IN (0,1)), "
    "revision INTEGER NOT NULL CHECK (revision>0), "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE global_saved_search_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "search_id TEXT NOT NULL REFERENCES global_saved_searches(id) ON DELETE RESTRICT, "
    "revision INTEGER NOT NULL CHECK (revision>0), "
    "action TEXT NOT NULL CHECK (action IN ('added','updated','reactivated','disabled')), "
    "definition_json TEXT NOT NULL, definition_sha256 TEXT NOT NULL CHECK (length(definition_sha256)=64), "
    "reason TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE(search_id,revision))",
    "CREATE TABLE global_search_snapshots ("
    "sha256 TEXT PRIMARY KEY NOT NULL CHECK (length(sha256)=64), payload_json TEXT NOT NULL)",
    "CREATE TABLE global_saved_search_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "search_id TEXT NOT NULL REFERENCES global_saved_searches(id) ON DELETE RESTRICT, "
    "event_id TEXT NOT NULL REFERENCES global_saved_search_events(id) ON DELETE RESTRICT, "
    "snapshot_sha256 TEXT NOT NULL REFERENCES global_search_snapshots(sha256) ON DELETE RESTRICT, "
    "previous_run_id TEXT REFERENCES global_saved_search_runs(id) ON DELETE RESTRICT, "
    "executed_at TEXT NOT NULL, total_count INTEGER NOT NULL CHECK (total_count>=0), "
    "added_count INTEGER NOT NULL CHECK (added_count>=0), "
    "updated_count INTEGER NOT NULL CHECK (updated_count>=0), "
    "unchanged_count INTEGER NOT NULL CHECK (unchanged_count>=0), "
    "removed_count INTEGER NOT NULL CHECK (removed_count>=0), "
    "diff_sha256 TEXT NOT NULL CHECK (length(diff_sha256)=64), "
    "CHECK (total_count=added_count+updated_count+unchanged_count))",
    "CREATE TABLE global_saved_search_notifications ("
    "sequence INTEGER PRIMARY KEY NOT NULL CHECK (sequence>0), id TEXT NOT NULL UNIQUE, "
    "run_id TEXT NOT NULL UNIQUE REFERENCES global_saved_search_runs(id) ON DELETE RESTRICT, "
    "search_id TEXT NOT NULL REFERENCES global_saved_searches(id) ON DELETE RESTRICT, "
    "event_type TEXT NOT NULL CHECK (event_type='global_saved_search_changed'), "
    "origin TEXT NOT NULL CHECK (origin='new'), created_at TEXT NOT NULL, read_at TEXT)",
    "CREATE INDEX global_saved_searches_active_name ON global_saved_searches(active,name_key)",
    "CREATE INDEX global_saved_search_events_search_sequence ON global_saved_search_events(search_id,sequence)",
    "CREATE INDEX global_saved_search_runs_search_sequence ON global_saved_search_runs(search_id,sequence)",
    "CREATE INDEX global_saved_search_notifications_read_sequence ON global_saved_search_notifications(read_at,sequence)",
)


MENTION_SCOPE_COLUMN = (
    "mention_request_key TEXT CHECK (mention_request_key IS NULL OR length(mention_request_key)=64)"
)
MENTION_NOTIFICATION_OPERATION_DDL = (
    "CREATE TABLE mention_notification_operations ("
    "operation_id TEXT PRIMARY KEY NOT NULL, group_id TEXT NOT NULL, "
    "request_key TEXT NOT NULL CHECK (length(request_key)=64), "
    "mention_run_id TEXT NOT NULL REFERENCES mentions_runs(id) ON DELETE RESTRICT, "
    "search_run_id TEXT NOT NULL UNIQUE REFERENCES global_saved_search_runs(id) ON DELETE RESTRICT, "
    "created_at TEXT NOT NULL)",
)
GLOBAL_SAVED_SEARCH_CURRENT_DDL = (
    GLOBAL_SAVED_SEARCH_DDL[0][:-1] + ", " + MENTION_SCOPE_COLUMN + ")",
    *GLOBAL_SAVED_SEARCH_DDL[1:],
    *MENTION_NOTIFICATION_OPERATION_DDL,
)


def upgrade_global_saved_search_scopes(connection):
    """Schema68 adds exact source scopes while preserving historical rows and DDL."""
    connection.execute("ALTER TABLE global_saved_searches ADD COLUMN " + MENTION_SCOPE_COLUMN)
    for statement in MENTION_NOTIFICATION_OPERATION_DDL:
        connection.execute(statement)
