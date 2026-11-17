"""Schema 74: immutable external context and per-query acquisition receipts."""
DDL = (
    "CREATE TABLE enrichment_snapshots (sha256 TEXT PRIMARY KEY NOT NULL, content BLOB NOT NULL)",
    "CREATE TABLE enrichment_runs (id TEXT PRIMARY KEY NOT NULL, provider TEXT NOT NULL, indicator_type TEXT NOT NULL, "
    "value TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT NOT NULL, status TEXT NOT NULL "
    "CHECK (status IN ('matched','no_match','failed')), http_status INTEGER, "
    "snapshot_sha256 TEXT REFERENCES enrichment_snapshots(sha256) ON DELETE RESTRICT, error TEXT, "
    "CHECK ((status IN ('matched','no_match') AND http_status IS NOT NULL AND snapshot_sha256 IS NOT NULL AND error IS NULL) "
    "OR (status='failed' AND snapshot_sha256 IS NULL AND error IS NOT NULL)))",
    "CREATE INDEX enrichment_runs_query ON enrichment_runs(provider,indicator_type,value,status)",
)
TABLES = {
    "enrichment_snapshots": [("sha256", "TEXT", 1, 1), ("content", "BLOB", 1, 0)],
    "enrichment_runs": [("id", "TEXT", 1, 1), ("provider", "TEXT", 1, 0), ("indicator_type", "TEXT", 1, 0),
        ("value", "TEXT", 1, 0), ("started_at", "TEXT", 1, 0), ("finished_at", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0), ("http_status", "INTEGER", 0, 0), ("snapshot_sha256", "TEXT", 0, 0), ("error", "TEXT", 0, 0)],
}
UNIQUE_KEYS = {"enrichment_snapshots": {("sha256",)}, "enrichment_runs": {("id",)}}
FOREIGN_KEYS = {"enrichment_snapshots": set(), "enrichment_runs": {
    ("enrichment_snapshots", "snapshot_sha256", "sha256", "NO ACTION", "RESTRICT")}}
INDEXES = {"enrichment_runs_query": ("enrichment_runs", ("provider", "indicator_type", "value", "status"))}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        row = connection.execute("SELECT sql FROM sqlite_schema WHERE name=?", (statement.split()[2],)).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("Kaynak araştırması kayıt düzeni beklenen biçimde değil.")
    if empty and any(connection.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone() for name in TABLES):
        raise SchemaError("Eski şemada kaynak araştırması verisi bulunamaz.")


def create(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name IN (?,?)", tuple(TABLES)).fetchone():
        validate(connection, empty=True)
        return
    for statement in DDL:
        connection.execute(statement)
