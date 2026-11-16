"""Additive schema 72: immutable work requests with checked event chains."""

DDL = (
    "CREATE TABLE surface_nmap_jobs ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL REFERENCES surface_scopes(asset_id) ON DELETE RESTRICT, "
    "plan_id TEXT NOT NULL REFERENCES surface_nmap_plans(id) ON DELETE RESTRICT, "
    "request_key TEXT NOT NULL, binding TEXT NOT NULL, created_at TEXT NOT NULL, "
    "event_count INTEGER NOT NULL CHECK (event_count >= 0), last_hash TEXT NOT NULL, "
    "cancel_requested INTEGER NOT NULL CHECK (cancel_requested IN (0,1)), UNIQUE (asset_id,request_key))",
    "CREATE TABLE surface_nmap_job_events ("
    "job_id TEXT NOT NULL REFERENCES surface_nmap_jobs(id) ON DELETE RESTRICT, "
    "ordinal INTEGER NOT NULL CHECK (ordinal > 0), event_json TEXT NOT NULL, "
    "event_sha256 TEXT NOT NULL, PRIMARY KEY (job_id,ordinal))",
)
TABLES = {
    "surface_nmap_jobs": [("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("plan_id", "TEXT", 1, 0), ("request_key", "TEXT", 1, 0), ("binding", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("event_count", "INTEGER", 1, 0),
        ("last_hash", "TEXT", 1, 0), ("cancel_requested", "INTEGER", 1, 0)],
    "surface_nmap_job_events": [("job_id", "TEXT", 1, 1), ("ordinal", "INTEGER", 1, 2),
        ("event_json", "TEXT", 1, 0), ("event_sha256", "TEXT", 1, 0)],
}
UNIQUE_KEYS = {"surface_nmap_jobs": {("id",), ("asset_id", "request_key")},
               "surface_nmap_job_events": {("job_id", "ordinal")}}
FOREIGN_KEYS = {
    "surface_nmap_jobs": {("surface_scopes", "asset_id", "asset_id", "NO ACTION", "RESTRICT"),
                          ("surface_nmap_plans", "plan_id", "id", "NO ACTION", "RESTRICT")},
    "surface_nmap_job_events": {("surface_nmap_jobs", "job_id", "id", "NO ACTION", "RESTRICT")},
}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        name = statement.split()[2]
        row = connection.execute("SELECT sql FROM sqlite_schema WHERE name=? AND type='table'", (name,)).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("Nmap iş şeması beklenen biçimde değil.")
        if empty and connection.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone():
            raise SchemaError("Eski şema sürümünde yeni Nmap işi bulunamaz.")


def create(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name IN (?,?)", tuple(TABLES)).fetchone():
        validate(connection, empty=True)
        return
    for statement in DDL:
        connection.execute(statement)
