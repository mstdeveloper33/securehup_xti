"""Independent structural schema66 expectations."""


TABLES = {
    "news_snapshots": [
        ("sha256", "TEXT", 1, 1), ("source_key", "TEXT", 1, 0), ("payload_json", "TEXT", 1, 0),
    ],
    "news_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("source_key", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("started_at", "TEXT", 1, 0), ("finished_at", "TEXT", 1, 0),
        ("fetched_at", "TEXT", 0, 0), ("content_sha256", "TEXT", 0, 0),
        ("snapshot_sha256", "TEXT", 0, 0), ("article_count", "INTEGER", 1, 0),
        ("added_count", "INTEGER", 1, 0), ("updated_count", "INTEGER", 1, 0),
        ("unchanged_count", "INTEGER", 1, 0), ("error", "TEXT", 0, 0),
        ("chain_sha256", "TEXT", 1, 0),
    ],
    "news_articles": [
        ("id", "TEXT", 1, 1), ("source_key", "TEXT", 1, 0),
        ("record_json", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
        ("first_run_id", "TEXT", 1, 0), ("last_change_run_id", "TEXT", 1, 0),
        ("last_seen_run_id", "TEXT", 1, 0), ("first_seen_at", "TEXT", 1, 0),
        ("last_changed_at", "TEXT", 1, 0), ("last_seen_at", "TEXT", 1, 0),
    ],
}

UNIQUE_KEYS = {
    "news_snapshots": {("sha256",)}, "news_runs": {("id",)}, "news_articles": {("id",)},
}

INDEXES = {
    "news_runs_source_sequence": ("news_runs", ("source_key", "sequence")),
    "news_articles_source_id": ("news_articles", ("source_key", "id")),
}

FOREIGN_KEYS = {
    "news_snapshots": set(),
    "news_runs": {("news_snapshots", "snapshot_sha256", "sha256", "NO ACTION", "RESTRICT")},
    "news_articles": {
        ("news_runs", "first_run_id", "id", "NO ACTION", "RESTRICT"),
        ("news_runs", "last_change_run_id", "id", "NO ACTION", "RESTRICT"),
        ("news_runs", "last_seen_run_id", "id", "NO ACTION", "RESTRICT"),
    },
}
