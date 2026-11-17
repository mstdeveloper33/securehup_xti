"""Schema 73: immutable acquired payloads and independent refresh receipts."""

DDL = (
    "CREATE TABLE warninglist_snapshots (sha256 TEXT PRIMARY KEY NOT NULL, content BLOB NOT NULL)",
    "CREATE TABLE warninglist_runs (id TEXT PRIMARY KEY NOT NULL, list_id TEXT NOT NULL, revision TEXT, "
    "started_at TEXT NOT NULL, finished_at TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('complete','failed')), "
    "snapshot_sha256 TEXT REFERENCES warninglist_snapshots(sha256) ON DELETE RESTRICT, error TEXT, "
    "CHECK ((status='complete' AND revision IS NOT NULL AND snapshot_sha256 IS NOT NULL AND error IS NULL) OR "
    "(status='failed' AND snapshot_sha256 IS NULL AND error IS NOT NULL)))",
    "CREATE INDEX warninglist_runs_list_status ON warninglist_runs(list_id,status)",
)
TABLES = {
    "warninglist_snapshots": [("sha256", "TEXT", 1, 1), ("content", "BLOB", 1, 0)],
    "warninglist_runs": [("id", "TEXT", 1, 1), ("list_id", "TEXT", 1, 0), ("revision", "TEXT", 0, 0),
        ("started_at", "TEXT", 1, 0), ("finished_at", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("snapshot_sha256", "TEXT", 0, 0), ("error", "TEXT", 0, 0)],
}
UNIQUE_KEYS = {"warninglist_snapshots": {("sha256",)}, "warninglist_runs": {("id",)}}
FOREIGN_KEYS = {"warninglist_snapshots": set(), "warninglist_runs": {
    ("warninglist_snapshots", "snapshot_sha256", "sha256", "NO ACTION", "RESTRICT")}}
# Metadata uses (table, column names); see schema.INDEXES.
INDEXES = {"warninglist_runs_list_status": ("warninglist_runs", ("list_id", "status"))}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        name = statement.split()[2]
        row = connection.execute("SELECT sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("Warninglist kayıt düzeni beklenen biçimde değil.")
    if empty and any(connection.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone() for name in TABLES):
        raise SchemaError("Eski şemada warninglist verisi bulunamaz.")


def create(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name IN (?,?)", tuple(TABLES)).fetchone():
        validate(connection, empty=True)
        return
    for statement in DDL:
        connection.execute(statement)
