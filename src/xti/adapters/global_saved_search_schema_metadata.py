"""Static schema65 expectations, independent of the database being validated."""


TABLES = {
    "global_saved_searches": [
        ("id", "TEXT", 1, 1), ("name_key", "TEXT", 1, 0),
        ("display_name", "TEXT", 1, 0), ("query", "TEXT", 1, 0),
        ("kinds_json", "TEXT", 1, 0), ("include_inactive", "INTEGER", 1, 0),
        ("active", "INTEGER", 1, 0), ("revision", "INTEGER", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "global_saved_search_events": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("search_id", "TEXT", 1, 0), ("revision", "INTEGER", 1, 0),
        ("action", "TEXT", 1, 0), ("definition_json", "TEXT", 1, 0),
        ("definition_sha256", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "global_search_snapshots": [
        ("sha256", "TEXT", 1, 1), ("payload_json", "TEXT", 1, 0),
    ],
    "global_saved_search_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("search_id", "TEXT", 1, 0), ("event_id", "TEXT", 1, 0),
        ("snapshot_sha256", "TEXT", 1, 0), ("previous_run_id", "TEXT", 0, 0),
        ("executed_at", "TEXT", 1, 0), ("total_count", "INTEGER", 1, 0),
        ("added_count", "INTEGER", 1, 0), ("updated_count", "INTEGER", 1, 0),
        ("unchanged_count", "INTEGER", 1, 0), ("removed_count", "INTEGER", 1, 0),
        ("diff_sha256", "TEXT", 1, 0),
    ],
    "global_saved_search_notifications": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("run_id", "TEXT", 1, 0), ("search_id", "TEXT", 1, 0),
        ("event_type", "TEXT", 1, 0), ("origin", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("read_at", "TEXT", 0, 0),
    ],
}

UNIQUE_KEYS = {
    "global_saved_searches": {("id",), ("name_key",)},
    "global_saved_search_events": {("id",), ("search_id", "revision")},
    "global_search_snapshots": {("sha256",)},
    "global_saved_search_runs": {("id",)},
    "global_saved_search_notifications": {("id",), ("run_id",)},
}

INDEXES = {
    "global_saved_searches_active_name": ("global_saved_searches", ("active", "name_key")),
    "global_saved_search_events_search_sequence": ("global_saved_search_events", ("search_id", "sequence")),
    "global_saved_search_runs_search_sequence": ("global_saved_search_runs", ("search_id", "sequence")),
    "global_saved_search_notifications_read_sequence": ("global_saved_search_notifications", ("read_at", "sequence")),
}

FOREIGN_KEYS = {
    "global_saved_searches": set(),
    "global_saved_search_events": {
        ("global_saved_searches", "search_id", "id", "NO ACTION", "RESTRICT"),
    },
    "global_search_snapshots": set(),
    "global_saved_search_runs": {
        ("global_saved_searches", "search_id", "id", "NO ACTION", "RESTRICT"),
        ("global_saved_search_events", "event_id", "id", "NO ACTION", "RESTRICT"),
        ("global_search_snapshots", "snapshot_sha256", "sha256", "NO ACTION", "RESTRICT"),
        ("global_saved_search_runs", "previous_run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "global_saved_search_notifications": {
        ("global_saved_search_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
        ("global_saved_searches", "search_id", "id", "NO ACTION", "RESTRICT"),
    },
}
