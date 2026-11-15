"""Schema67: append-only company search evidence, never provider credentials."""


MENTIONS_DDL = (
    "CREATE TABLE mentions_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "request_key TEXT NOT NULL CHECK (length(request_key)=64), "
    "status TEXT NOT NULL CHECK (status IN ('complete','failed')), "
    "payload_json TEXT NOT NULL, "
    "payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256)=64), "
    "chain_sha256 TEXT NOT NULL CHECK (length(chain_sha256)=64))",
    "CREATE INDEX mentions_runs_request_sequence ON mentions_runs(request_key,sequence)",
)
