"""Schema96: organization-scoped unified monitoring policies and alert reviews."""

from xti.adapters.darkweb_monitoring_schema import CASE_EVIDENCE_DDL as PREVIOUS_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL


CASE_EVIDENCE_DDL = PREVIOUS_CASE_DDL.replace(
    "'darkweb_monitoring'))", "'darkweb_monitoring', 'unified_monitoring'))"
)
P = "monitoring_"
DEFINITIONS = {
    "policies": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("name_key", "TEXT NOT NULL"), ("revision", "INTEGER NOT NULL"),
        ("enabled", "INTEGER NOT NULL CHECK(enabled IN (0,1))"),
        ("definition_json", "TEXT NOT NULL"), ("definition_sha256", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"), ("updated_at", "TEXT NOT NULL"),
    ],
    "policy_events": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("policy_id", f"TEXT NOT NULL REFERENCES {P}policies(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','updated','reactivated','disabled'))"),
        ("definition_json", "TEXT NOT NULL"), ("definition_sha256", "TEXT NOT NULL"),
        ("reason", "TEXT NOT NULL"), ("actor", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "runs": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("policy_id", f"TEXT NOT NULL REFERENCES {P}policies(id) ON DELETE RESTRICT"),
        ("policy_event_id", f"TEXT NOT NULL REFERENCES {P}policy_events(id) ON DELETE RESTRICT"),
        ("request_key", "TEXT NOT NULL UNIQUE"), ("request_sha256", "TEXT NOT NULL"),
        ("previous_run_id", f"TEXT REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("status", "TEXT NOT NULL CHECK(status IN ('running','complete','failed','interrupted'))"),
        ("snapshot_json", "TEXT"), ("snapshot_sha256", "TEXT"),
        ("report_json", "TEXT"), ("report_sha256", "TEXT"),
        ("error_code", "TEXT"), ("error_message", "TEXT"),
        ("started_at", "TEXT NOT NULL"), ("finished_at", "TEXT"),
    ],
    "alerts": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("run_id", f"TEXT NOT NULL UNIQUE REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("policy_id", f"TEXT NOT NULL REFERENCES {P}policies(id) ON DELETE RESTRICT"),
        ("priority", "TEXT NOT NULL CHECK(priority IN ('low','medium','high','critical'))"),
        ("event_type", "TEXT NOT NULL CHECK(event_type='unified_monitoring_changed')"),
        ("origin", "TEXT NOT NULL CHECK(origin='new')"),
        ("change_count", "INTEGER NOT NULL CHECK(change_count>0)"),
        ("created_at", "TEXT NOT NULL"), ("read_at", "TEXT"),
    ],
    "alert_reviews": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("alert_id", f"TEXT NOT NULL REFERENCES {P}alerts(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL"),
        ("decision", "TEXT NOT NULL CHECK(decision IN ('useful','not_useful','uncertain'))"),
        ("reason", "TEXT NOT NULL"), ("actor", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "mutations": [
        ("id", "TEXT NOT NULL UNIQUE"), ("request_key", "TEXT NOT NULL UNIQUE"),
        ("request_sha256", "TEXT NOT NULL"), ("operation", "TEXT NOT NULL"),
        ("result_json", "TEXT NOT NULL"), ("result_sha256", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
    ],
}
DEFINITIONS = {P + key: value for key, value in DEFINITIONS.items()}
COMPOSITE = {
    P + "policies": ("organization_id", "name_key"),
    P + "policy_events": ("policy_id", "revision"),
    P + "alert_reviews": ("alert_id", "revision"),
}
INDEXES = {
    P + "policies_org_enabled": (P + "policies", ("organization_id", "enabled", "sequence")),
    P + "events_policy_revision": (P + "policy_events", ("policy_id", "revision")),
    P + "runs_policy_sequence": (P + "runs", ("policy_id", "sequence")),
    P + "runs_status_sequence": (P + "runs", ("status", "sequence")),
    P + "alerts_read_sequence": (P + "alerts", ("read_at", "sequence")),
    P + "alerts_policy_sequence": (P + "alerts", ("policy_id", "sequence")),
    P + "reviews_alert_revision": (P + "alert_reviews", ("alert_id", "revision")),
}
DDL = tuple(
    "CREATE TABLE " + table + " (sequence INTEGER PRIMARY KEY "
    + ("NOT NULL, " if table == P + "alerts" else "AUTOINCREMENT NOT NULL, ")
    + ", ".join(name + " " + declaration for name, declaration in columns)
    + (", UNIQUE(" + ",".join(COMPOSITE[table]) + ")" if table in COMPOSITE else "") + ")"
    for table, columns in DEFINITIONS.items()
) + tuple(
    "CREATE INDEX " + name + " ON " + table + " (" + ",".join(columns) + ")"
    for name, (table, columns) in INDEXES.items()
)
TABLES = {
    table: [("sequence", "INTEGER", 1, 1)]
    + [(name, declaration.split()[0], int("NOT NULL" in declaration), 0)
       for name, declaration in columns]
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


def validate(connection, *, empty: bool = False, case_ddl: str | None = None) -> None:
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        name = statement.split()[2]
        kind = "index" if statement.startswith("CREATE INDEX") else "table"
        row = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, kind),
        ).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("P07 birleşik izleme kayıt düzeni beklenen biçimde değil.")
    current = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE name='case_evidence'"
    ).fetchone()[0]
    expected_case = CASE_EVIDENCE_DDL if case_ddl is None else case_ddl
    if " ".join(current.split()) != " ".join(expected_case.split()):
        raise SchemaError("P07 vaka kanıt düzeni beklenen biçimde değil.")
    if empty:
        for table in TABLES:
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise SchemaError("Eski şemada P07 birleşik izleme kaydı bulunamaz.")


def create(connection) -> None:
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError("P07 şema geçişi transaction gerektirir.")
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (P + "policies",)).fetchone():
        validate(connection, empty=True)
        return
    for statement in DDL:
        connection.execute(statement)
    current = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE name='case_evidence'"
    ).fetchone()[0]
    if " ".join(current.split()) != " ".join(PREVIOUS_CASE_DDL.split()):
        raise SchemaError("P07 geçişinde vaka düzeni uyuşmuyor.")
    columns = ",".join(CASE_EVIDENCE_COLUMNS)
    connection.execute(
        f"CREATE TEMP TABLE xti_monitoring_case_v95 AS "
        f"SELECT rowid AS legacy_rowid,{columns} FROM case_evidence ORDER BY rowid"
    )
    connection.execute("DROP TABLE case_evidence")
    connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(
        f"INSERT INTO case_evidence (rowid,{columns}) "
        f"SELECT legacy_rowid,{columns} FROM xti_monitoring_case_v95 ORDER BY legacy_rowid"
    )
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute("DROP TABLE temp.xti_monitoring_case_v95")
    validate(connection)
