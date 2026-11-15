"""Schema68 immutable group definitions, work reservations and receipts."""

MENTION_GROUP_DDL = (
    "CREATE TABLE mention_group_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "group_id TEXT NOT NULL, run_id TEXT, action TEXT NOT NULL CHECK (action IN "
    "('saved','disabled','begun','reserved','result','unknown','skipped','notified','finished')), "
    "recorded_at TEXT NOT NULL, payload_json TEXT NOT NULL, "
    "payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256)=64), "
    "chain_sha256 TEXT NOT NULL CHECK (length(chain_sha256)=64))",
    "CREATE INDEX mention_group_events_group_sequence ON mention_group_events(group_id,sequence)",
    "CREATE INDEX mention_group_events_run_sequence ON mention_group_events(run_id,sequence)",
)
