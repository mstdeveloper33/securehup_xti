"""Schema98: organization-scoped normalized sensor and sandbox telemetry."""

from xti.adapters.unified_monitoring_schema import CASE_EVIDENCE_DDL as PREVIOUS_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL


CASE_EVIDENCE_DDL = PREVIOUS_CASE_DDL.replace(
    "'unified_monitoring'))", "'unified_monitoring', 'telemetry'))"
)
P = "telemetry_"
DEFINITIONS = {
    "sources": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("name_key", "TEXT NOT NULL"),
        ("display_name", "TEXT NOT NULL"),
        ("source_kind", "TEXT NOT NULL CHECK(source_kind IN ('honeypot','sinkhole','sandbox'))"),
        ("input_format", "TEXT NOT NULL CHECK(input_format IN ('xti-sensor-v1','cowrie-jsonl','cape-report-v1'))"),
        ("description", "TEXT NOT NULL"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("enabled", "INTEGER NOT NULL CHECK(enabled IN (0,1))"),
        ("created_at", "TEXT NOT NULL"),
        ("updated_at", "TEXT NOT NULL"),
    ],
    "source_events": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("source_id", f"TEXT NOT NULL REFERENCES {P}sources(id) ON DELETE RESTRICT"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','updated','enabled','disabled'))"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("snapshot_json", "TEXT NOT NULL"),
        ("snapshot_sha256", "TEXT NOT NULL"),
        ("reason", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "runs": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("source_id", f"TEXT NOT NULL REFERENCES {P}sources(id) ON DELETE RESTRICT"),
        ("source_revision", "INTEGER NOT NULL CHECK(source_revision>0)"),
        ("request_key", "TEXT NOT NULL UNIQUE"),
        ("request_sha256", "TEXT NOT NULL"),
        ("input_format", "TEXT NOT NULL CHECK(input_format IN ('xti-sensor-v1','cowrie-jsonl','cape-report-v1'))"),
        ("content_sha256", "TEXT NOT NULL"),
        ("preview_sha256", "TEXT NOT NULL"),
        ("status", "TEXT NOT NULL CHECK(status IN ('running','complete','interrupted'))"),
        ("input_count", "INTEGER NOT NULL CHECK(input_count>=0)"),
        ("record_count", "INTEGER NOT NULL CHECK(record_count>=0)"),
        ("ignored_count", "INTEGER NOT NULL CHECK(ignored_count>=0)"),
        ("duplicate_count", "INTEGER NOT NULL CHECK(duplicate_count>=0)"),
        ("added_count", "INTEGER NOT NULL CHECK(added_count>=0)"),
        ("updated_count", "INTEGER NOT NULL CHECK(updated_count>=0)"),
        ("unchanged_count", "INTEGER NOT NULL CHECK(unchanged_count>=0)"),
        ("ignored_json", "TEXT NOT NULL"),
        ("error_code", "TEXT"),
        ("error", "TEXT"),
        ("started_at", "TEXT NOT NULL"),
        ("finished_at", "TEXT"),
    ],
    "records": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("source_id", f"TEXT NOT NULL REFERENCES {P}sources(id) ON DELETE RESTRICT"),
        ("native_key", "TEXT NOT NULL"),
        ("record_kind", "TEXT NOT NULL CHECK(record_kind IN ('connection','authentication','dns_query','file_download','sandbox_analysis'))"),
        ("event_at", "TEXT NOT NULL"),
        ("summary", "TEXT NOT NULL"),
        ("body_json", "TEXT NOT NULL"),
        ("body_sha256", "TEXT NOT NULL"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("review_revision", "INTEGER NOT NULL CHECK(review_revision>=0)"),
        ("first_run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("last_run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("first_seen_at", "TEXT NOT NULL"),
        ("last_seen_at", "TEXT NOT NULL"),
    ],
    "record_versions": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("record_id", f"TEXT NOT NULL REFERENCES {P}records(id) ON DELETE RESTRICT"),
        ("run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','updated'))"),
        ("body_json", "TEXT NOT NULL"),
        ("body_sha256", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "run_items": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("record_id", f"TEXT NOT NULL REFERENCES {P}records(id) ON DELETE RESTRICT"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','updated','unchanged'))"),
        ("record_revision", "INTEGER NOT NULL CHECK(record_revision>0)"),
        ("body_sha256", "TEXT NOT NULL"),
    ],
    "reviews": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("record_id", f"TEXT NOT NULL REFERENCES {P}records(id) ON DELETE RESTRICT"),
        ("record_revision", "INTEGER NOT NULL CHECK(record_revision>0)"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("decision", "TEXT NOT NULL CHECK(decision IN ('relevant','benign','suspicious','uncertain'))"),
        ("reason", "TEXT NOT NULL"),
        ("actor", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "mutations": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("request_key", "TEXT NOT NULL UNIQUE"),
        ("request_sha256", "TEXT NOT NULL"),
        ("result_json", "TEXT NOT NULL"),
        ("result_sha256", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
    ],
}
DEFINITIONS = {P + key: value for key, value in DEFINITIONS.items()}
COMPOSITE = {
    P + "sources": ("organization_id", "name_key"),
    P + "source_events": ("source_id", "revision"),
    P + "records": ("source_id", "native_key"),
    P + "record_versions": ("record_id", "revision"),
    P + "run_items": ("run_id", "record_id"),
    P + "reviews": ("record_id", "revision"),
}
INDEXES = {
    P + "source_org": (P + "sources", ("organization_id", "enabled", "sequence")),
    P + "source_event_source": (P + "source_events", ("source_id", "sequence")),
    P + "run_source": (P + "runs", ("source_id", "sequence")),
    P + "run_status": (P + "runs", ("status", "sequence")),
    P + "record_org_kind": (P + "records", ("organization_id", "record_kind", "sequence")),
    P + "record_source": (P + "records", ("source_id", "sequence")),
    P + "record_event": (P + "records", ("event_at", "sequence")),
    P + "version_record": (P + "record_versions", ("record_id", "sequence")),
    P + "item_run": (P + "run_items", ("run_id", "sequence")),
    P + "review_record": (P + "reviews", ("record_id", "sequence")),
}
DDL = tuple(
    "CREATE TABLE " + table + " (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "
    + ", ".join(name + " " + declaration for name, declaration in columns)
    + (", UNIQUE(" + ",".join(COMPOSITE[table]) + ")" if table in COMPOSITE else "") + ")"
    for table, columns in DEFINITIONS.items()
) + tuple(
    "CREATE INDEX " + name + " ON " + table + " (" + ",".join(columns) + ")"
    for name, (table, columns) in INDEXES.items()
)
TABLES = {
    table: [("sequence", "INTEGER", 1, 1)] + [
        (name, declaration.split()[0], int("NOT NULL" in declaration), 0)
        for name, declaration in columns
    ]
    for table, columns in DEFINITIONS.items()
}
UNIQUE_KEYS = {
    table: {(name,) for name, declaration in columns if "UNIQUE" in declaration}
    | ({COMPOSITE[table]} if table in COMPOSITE else set())
    for table, columns in DEFINITIONS.items()
}
FOREIGN_KEYS = {
    table: {
        (declaration.split("REFERENCES ")[1].split("(")[0], name, "id", "NO ACTION", "RESTRICT")
        for name, declaration in columns if "REFERENCES" in declaration
    }
    for table, columns in DEFINITIONS.items()
}


def validate(connection, *, empty: bool = False, case_ddl: str | None = CASE_EVIDENCE_DDL) -> None:
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        name = statement.split()[2]
        kind = "index" if statement.startswith("CREATE INDEX") else "table"
        row = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, kind),
        ).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("P12 telemetri kayıt düzeni beklenen biçimde değil.")
    if case_ddl is not None:
        current = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name='case_evidence'"
        ).fetchone()[0]
        if " ".join(current.split()) != " ".join(case_ddl.split()):
            raise SchemaError("P12 vaka kanıt düzeni beklenen biçimde değil.")
    if empty:
        for table in TABLES:
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise SchemaError("Eski şemada P12 telemetri kaydı bulunamaz.")


def create(connection) -> None:
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError("P12 şema geçişi transaction gerektirir.")
    existing = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE name=?", (P + "sources",),
    ).fetchone()
    if existing:
        validate(connection, empty=True, case_ddl=PREVIOUS_CASE_DDL)
    else:
        for statement in DDL:
            connection.execute(statement)
    current = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE name='case_evidence'"
    ).fetchone()[0]
    if " ".join(current.split()) != " ".join(PREVIOUS_CASE_DDL.split()):
        raise SchemaError("P12 geçişinde vaka düzeni uyuşmuyor.")
    columns = ",".join(CASE_EVIDENCE_COLUMNS)
    connection.execute(
        f"CREATE TEMP TABLE xti_telemetry_case_v97 AS "
        f"SELECT rowid AS legacy_rowid,{columns} FROM case_evidence ORDER BY rowid"
    )
    connection.execute("DROP TABLE case_evidence")
    connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(
        f"INSERT INTO case_evidence (rowid,{columns}) "
        f"SELECT legacy_rowid,{columns} FROM xti_telemetry_case_v97 ORDER BY legacy_rowid"
    )
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute("DROP TABLE temp.xti_telemetry_case_v97")
    validate(connection)
