"""Schema 75: immutable, scope-bound research review and comparison receipts."""
DDL = (
    "CREATE TABLE research_reviews (id TEXT PRIMARY KEY NOT NULL, scope_key TEXT NOT NULL, "
    "indicator_type TEXT NOT NULL, value TEXT NOT NULL, sequence INTEGER NOT NULL CHECK (sequence>0), "
    "request_key TEXT NOT NULL UNIQUE, previous_id TEXT UNIQUE REFERENCES research_reviews(id) ON DELETE RESTRICT, "
    "checked_at TEXT NOT NULL, policy_version TEXT NOT NULL, scope_json TEXT NOT NULL, "
    "snapshot_sha256 TEXT NOT NULL, comparison_sha256 TEXT NOT NULL, summary_json TEXT NOT NULL, "
    "header_sha256 TEXT NOT NULL, snapshot_json TEXT NOT NULL, comparison_json TEXT NOT NULL, "
    "UNIQUE(scope_key,sequence), CHECK ((sequence=1 AND previous_id IS NULL) OR (sequence>1 AND previous_id IS NOT NULL)))",
    "CREATE INDEX research_reviews_root ON research_reviews(indicator_type,value)",
)
TABLES = {"research_reviews": [(name, kind, required, primary) for name, kind, required, primary in (
    ("id", "TEXT", 1, 1), ("scope_key", "TEXT", 1, 0), ("indicator_type", "TEXT", 1, 0),
    ("value", "TEXT", 1, 0), ("sequence", "INTEGER", 1, 0), ("request_key", "TEXT", 1, 0),
    ("previous_id", "TEXT", 0, 0), ("checked_at", "TEXT", 1, 0), ("policy_version", "TEXT", 1, 0),
    ("scope_json", "TEXT", 1, 0), ("snapshot_sha256", "TEXT", 1, 0), ("comparison_sha256", "TEXT", 1, 0),
    ("summary_json", "TEXT", 1, 0), ("header_sha256", "TEXT", 1, 0),
    ("snapshot_json", "TEXT", 1, 0), ("comparison_json", "TEXT", 1, 0))]}
UNIQUE_KEYS = {"research_reviews": {("id",), ("request_key",), ("previous_id",), ("scope_key", "sequence")}}
FOREIGN_KEYS = {"research_reviews": {("research_reviews", "previous_id", "id", "NO ACTION", "RESTRICT")}}
INDEXES = {"research_reviews_root": ("research_reviews", ("indicator_type", "value"))}


def validate(connection, *, empty=False):
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        row = connection.execute("SELECT sql FROM sqlite_schema WHERE name=?", (statement.split()[2],)).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("İnceleme geçmişi kayıt düzeni beklenen biçimde değil.")
    if empty and connection.execute("SELECT 1 FROM research_reviews LIMIT 1").fetchone():
        raise SchemaError("Eski şemada inceleme geçmişi verisi bulunamaz.")


def create(connection):
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name='research_reviews'").fetchone():
        validate(connection, empty=True)
        return
    for statement in DDL:
        connection.execute(statement)
