"""Schema95: versioned runbooks, human-approved takedown and IOC import receipts."""

P = "action_"
DEFINITIONS = {
    "runbooks": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("case_id", "TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT"),
        ("template_id", "TEXT NOT NULL"), ("template_version", "INTEGER NOT NULL"),
        ("case_snapshot_sha256", "TEXT NOT NULL"), ("plan_json", "TEXT NOT NULL"),
        ("plan_sha256", "TEXT NOT NULL"), ("idempotency_key", "TEXT NOT NULL UNIQUE"),
        ("reason", "TEXT NOT NULL"), ("created_at", "TEXT NOT NULL"),
    ],
    "runbook_items": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("runbook_id", f"TEXT NOT NULL REFERENCES {P}runbooks(id) ON DELETE RESTRICT"),
        ("ordinal", "INTEGER NOT NULL"), ("code", "TEXT NOT NULL"),
        ("title", "TEXT NOT NULL"), ("rationale", "TEXT NOT NULL"),
        ("case_task_id", "TEXT NOT NULL REFERENCES case_tasks(id) ON DELETE RESTRICT"),
    ],
    "takedowns": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("case_id", "TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT"),
        ("evidence_link_id", "TEXT NOT NULL REFERENCES case_evidence(id) ON DELETE RESTRICT"),
        ("target_kind", "TEXT NOT NULL CHECK(target_kind IN ('domain_hosting','registrar','social_platform','app_store','code_host','search_engine'))"),
        ("target_value", "TEXT NOT NULL"), ("recipient", "TEXT NOT NULL"),
        ("requested_action", "TEXT NOT NULL"), ("grounds", "TEXT NOT NULL"),
        ("state", "TEXT NOT NULL CHECK(state IN ('draft','approved','submitted','acknowledged','resolved','rejected','cancelled'))"),
        ("revision", "INTEGER NOT NULL"), ("evidence_sha256", "TEXT NOT NULL"),
        ("draft_json", "TEXT NOT NULL"), ("draft_sha256", "TEXT NOT NULL"),
        ("idempotency_key", "TEXT NOT NULL UNIQUE"), ("approved_by", "TEXT"),
        ("approved_at", "TEXT"), ("external_reference", "TEXT"),
        ("created_at", "TEXT NOT NULL"), ("updated_at", "TEXT NOT NULL"),
    ],
    "takedown_events": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("request_id", f"TEXT NOT NULL REFERENCES {P}takedowns(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL"),
        ("action", "TEXT NOT NULL CHECK(action IN ('draft','approve','submit','acknowledge','resolve','reject','cancel'))"),
        ("state", "TEXT NOT NULL CHECK(state IN ('draft','approved','submitted','acknowledged','resolved','rejected','cancelled'))"),
        ("actor", "TEXT NOT NULL"), ("reason", "TEXT NOT NULL"),
        ("external_reference", "TEXT"), ("snapshot_sha256", "TEXT NOT NULL"),
        ("snapshot_json", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "ioc_import_runs": [
        ("id", "TEXT NOT NULL UNIQUE"), ("idempotency_key", "TEXT NOT NULL UNIQUE"),
        ("format", "TEXT NOT NULL CHECK(format IN ('csv','json','stix'))"),
        ("source_name", "TEXT NOT NULL"), ("source_reference", "TEXT NOT NULL"),
        ("content_sha256", "TEXT NOT NULL"), ("preview_sha256", "TEXT NOT NULL"),
        ("record_count", "INTEGER NOT NULL"), ("added_count", "INTEGER NOT NULL"),
        ("observed_count", "INTEGER NOT NULL"), ("updated_count", "INTEGER NOT NULL"),
        ("reactivated_count", "INTEGER NOT NULL"), ("unchanged_count", "INTEGER NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
    ],
    "ioc_import_items": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("run_id", f"TEXT NOT NULL REFERENCES {P}ioc_import_runs(id) ON DELETE RESTRICT"),
        ("ordinal", "INTEGER NOT NULL"),
        ("indicator_id", "TEXT NOT NULL REFERENCES cti_indicators(id) ON DELETE RESTRICT"),
        ("assertion_id", "TEXT NOT NULL REFERENCES cti_indicator_assertions(id) ON DELETE RESTRICT"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','observed','updated','reactivated','unchanged'))"),
        ("row_sha256", "TEXT NOT NULL"),
    ],
}
DEFINITIONS = {P + key: value for key, value in DEFINITIONS.items()}
COMPOSITE = {
    P + "runbook_items": ("runbook_id", "ordinal"),
    P + "takedown_events": ("request_id", "revision"),
    P + "ioc_import_items": ("run_id", "ordinal"),
}
INDEXES = {
    P + "runbook_case": (P + "runbooks", ("case_id", "sequence")),
    P + "runbook_item_run": (P + "runbook_items", ("runbook_id", "ordinal")),
    P + "takedown_case_state": (P + "takedowns", ("case_id", "state", "sequence")),
    P + "takedown_event_request": (P + "takedown_events", ("request_id", "revision")),
    P + "ioc_import_run_time": (P + "ioc_import_runs", ("created_at", "sequence")),
    P + "ioc_import_item_run": (P + "ioc_import_items", ("run_id", "ordinal")),
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


def validate(connection, *, empty: bool = False) -> None:
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        name = statement.split()[2]
        object_type = "index" if statement.startswith("CREATE INDEX") else "table"
        row = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
        ).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("P06 aksiyon kayıt düzeni beklenen biçimde değil.")
    if empty:
        for table in TABLES:
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise SchemaError("Eski şemada P06 aksiyon kaydı bulunamaz.")


def create(connection) -> None:
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError("P06 şema geçişi transaction gerektirir.")
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (P + "runbooks",)).fetchone():
        validate(connection, empty=True)
        return
    for statement in DDL:
        connection.execute(statement)
