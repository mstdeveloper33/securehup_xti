"""Independent schema68 group ledger structural expectations."""

TABLES = {"mention_group_events": [
    ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
    ("group_id", "TEXT", 1, 0), ("run_id", "TEXT", 0, 0),
    ("action", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ("payload_json", "TEXT", 1, 0), ("payload_sha256", "TEXT", 1, 0),
    ("chain_sha256", "TEXT", 1, 0),
]}
UNIQUE_KEYS = {"mention_group_events": {("id",)}}
INDEXES = {
    "mention_group_events_group_sequence": ("mention_group_events", ("group_id", "sequence")),
    "mention_group_events_run_sequence": ("mention_group_events", ("run_id", "sequence")),
}
FOREIGN_KEYS = {"mention_group_events": set()}
