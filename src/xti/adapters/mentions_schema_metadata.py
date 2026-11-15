"""Independent schema67 structural expectations."""


TABLES = {
    "mentions_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("request_key", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("payload_json", "TEXT", 1, 0), ("payload_sha256", "TEXT", 1, 0),
        ("chain_sha256", "TEXT", 1, 0),
    ],
}
UNIQUE_KEYS = {"mentions_runs": {("id",)}}
INDEXES = {"mentions_runs_request_sequence": ("mentions_runs", ("request_key", "sequence"))}
FOREIGN_KEYS = {"mentions_runs": set()}
