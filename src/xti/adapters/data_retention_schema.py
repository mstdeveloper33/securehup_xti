"""Schema99: retention policies, holds and lossless multi-family archives.

Schema97 introduced the original ``unified_monitoring_runs`` family.  Schema99
keeps every one of those rows and widens the two polymorphic record references
so normalized P12 telemetry can use the same policy, run, receipt and audit
lifecycle.  The record reference is deliberately validated by the repository:
SQLite cannot express a foreign key whose parent depends on ``family``.
"""


P = "retention_"
DEFINITIONS = {
    "policies": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("name_key", "TEXT NOT NULL"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("enabled", "INTEGER NOT NULL CHECK(enabled IN (0,1))"),
        ("definition_json", "TEXT NOT NULL"),
        ("definition_sha256", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
        ("updated_at", "TEXT NOT NULL"),
    ],
    "policy_events": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("policy_id", "TEXT NOT NULL REFERENCES retention_policies(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','updated','reactivated','disabled'))"),
        ("definition_json", "TEXT NOT NULL"),
        ("definition_sha256", "TEXT NOT NULL"),
        ("reason", "TEXT NOT NULL"),
        ("actor", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "holds": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("family", "TEXT NOT NULL CHECK(family='unified_monitoring_runs')"),
        ("scope_key", "TEXT NOT NULL"),
        ("record_id", "TEXT REFERENCES monitoring_runs(id) ON DELETE RESTRICT"),
        ("case_id", "TEXT REFERENCES cases(id) ON DELETE RESTRICT"),
        ("kind", "TEXT NOT NULL CHECK(kind IN ('legal','case','investigation','contractual'))"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("active", "INTEGER NOT NULL CHECK(active IN (0,1))"),
        ("reason", "TEXT NOT NULL"),
        ("actor", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
        ("updated_at", "TEXT NOT NULL"),
    ],
    "hold_events": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("hold_id", "TEXT NOT NULL REFERENCES retention_holds(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','reactivated','released'))"),
        ("reason", "TEXT NOT NULL"),
        ("actor", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "runs": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("operation", "TEXT NOT NULL CHECK(operation IN ('archive','restore'))"),
        ("policy_id", "TEXT NOT NULL REFERENCES retention_policies(id) ON DELETE RESTRICT"),
        ("policy_event_id", "TEXT NOT NULL REFERENCES retention_policy_events(id) ON DELETE RESTRICT"),
        ("target_run_id", "TEXT REFERENCES retention_runs(id) ON DELETE RESTRICT"),
        ("request_key", "TEXT NOT NULL UNIQUE"),
        ("request_sha256", "TEXT NOT NULL"),
        ("status", "TEXT NOT NULL CHECK(status IN ('running','complete','failed','interrupted'))"),
        ("plan_json", "TEXT NOT NULL"),
        ("plan_sha256", "TEXT NOT NULL"),
        ("receipt_json", "TEXT"),
        ("receipt_sha256", "TEXT"),
        ("actor", "TEXT NOT NULL"),
        ("reason", "TEXT NOT NULL"),
        ("error_code", "TEXT"),
        ("error_message", "TEXT"),
        ("started_at", "TEXT NOT NULL"),
        ("finished_at", "TEXT"),
    ],
    "archive_items": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("archive_run_id", "TEXT NOT NULL REFERENCES retention_runs(id) ON DELETE RESTRICT"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("family", "TEXT NOT NULL CHECK(family='unified_monitoring_runs')"),
        ("record_id", "TEXT NOT NULL REFERENCES monitoring_runs(id) ON DELETE RESTRICT"),
        ("active_key", "TEXT UNIQUE"),
        ("snapshot_sha256", "TEXT NOT NULL"),
        ("report_sha256", "TEXT NOT NULL"),
        ("snapshot_raw_size", "INTEGER NOT NULL CHECK(snapshot_raw_size>=0)"),
        ("report_raw_size", "INTEGER NOT NULL CHECK(report_raw_size>0)"),
        ("snapshot_body", "BLOB"),
        ("report_body", "BLOB"),
        ("active", "INTEGER NOT NULL CHECK(active IN (0,1))"),
        ("created_at", "TEXT NOT NULL"),
        ("restored_at", "TEXT"),
    ],
    "audit_events": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("action", "TEXT NOT NULL"),
        ("resource_kind", "TEXT NOT NULL"),
        ("resource_id", "TEXT NOT NULL"),
        ("actor", "TEXT NOT NULL"),
        ("reason", "TEXT NOT NULL"),
        ("details_json", "TEXT NOT NULL"),
        ("details_sha256", "TEXT NOT NULL"),
        ("previous_chain_sha256", "TEXT"),
        ("chain_sha256", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "mutations": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("request_key", "TEXT NOT NULL UNIQUE"),
        ("request_sha256", "TEXT NOT NULL"),
        ("operation", "TEXT NOT NULL"),
        ("result_json", "TEXT NOT NULL"),
        ("result_sha256", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
    ],
}
_V97_RAW_DEFINITIONS = DEFINITIONS
V97_DEFINITIONS = {P + key: list(value) for key, value in DEFINITIONS.items()}

# The family-specific parent is checked transactionally in the repository.
# Removing the old monitoring-only FK is what makes this a safe polymorphic
# reference; all other constraints and columns remain byte-for-byte compatible.
DEFINITIONS = {key: list(value) for key, value in _V97_RAW_DEFINITIONS.items()}
for _table in ("holds", "archive_items"):
    DEFINITIONS[_table] = [
        (
            name,
            (
                "TEXT"
                if _table == "holds" and name == "record_id"
                else "TEXT NOT NULL"
                if _table == "archive_items" and name == "record_id"
                else "TEXT NOT NULL CHECK(family IN "
                     "('unified_monitoring_runs','telemetry_records'))"
                if name == "family"
                else declaration
            ),
        )
        for name, declaration in DEFINITIONS[_table]
    ]
DEFINITIONS = {P + key: value for key, value in DEFINITIONS.items()}
COMPOSITE = {
    P + "policies": ("organization_id", "name_key"),
    P + "policy_events": ("policy_id", "revision"),
    P + "hold_events": ("hold_id", "revision"),
}

def _table_ddl(definitions, *, multi_family: bool = False):
    return tuple(
        "CREATE TABLE " + table + " (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "
        + ", ".join(name + " " + declaration for name, declaration in columns)
        + (", UNIQUE(" + ",".join(COMPOSITE[table]) + ")" if table in COMPOSITE else "")
        + (
            ", CHECK((record_id IS NULL AND scope_key='*') OR "
            "(record_id IS NOT NULL AND scope_key=record_id))"
            if table == P + "holds" else ""
        )
        + (
            (", CHECK((active=1 AND active_key IS NOT NULL AND "
             if multi_family else
             ", CHECK((active=1 AND active_key=family||':'||record_id AND ")
            +
            "report_body IS NOT NULL AND restored_at IS NULL) OR "
            "(active=0 AND active_key IS NULL AND snapshot_body IS NULL AND "
            "report_body IS NULL AND restored_at IS NOT NULL))"
            if table == P + "archive_items" else ""
        )
        + ")"
        for table, columns in definitions.items()
    )


INDEX_DDL = (
    "CREATE INDEX retention_policies_org_enabled ON retention_policies (organization_id,enabled,sequence)",
    "CREATE INDEX retention_policy_events_policy_revision ON retention_policy_events (policy_id,revision)",
    "CREATE INDEX retention_holds_scope_active ON retention_holds (organization_id,family,active,scope_key)",
    "CREATE INDEX retention_hold_events_hold_revision ON retention_hold_events (hold_id,revision)",
    "CREATE INDEX retention_runs_policy_sequence ON retention_runs (policy_id,sequence)",
    "CREATE INDEX retention_runs_status_sequence ON retention_runs (status,sequence)",
    "CREATE INDEX retention_archive_run_sequence ON retention_archive_items (archive_run_id,sequence)",
    "CREATE INDEX retention_audit_org_sequence ON retention_audit_events (organization_id,sequence)",
    "CREATE INDEX retention_audit_resource_sequence ON retention_audit_events (resource_kind,resource_id,sequence)",
)
DDL = _table_ddl(DEFINITIONS, multi_family=True) + INDEX_DDL
V97_DDL = _table_ddl(V97_DEFINITIONS) + INDEX_DDL

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
INDEXES = {
    "retention_policies_org_enabled": (P + "policies", ("organization_id", "enabled", "sequence")),
    "retention_policy_events_policy_revision": (P + "policy_events", ("policy_id", "revision")),
    "retention_holds_scope_active": (P + "holds", ("organization_id", "family", "active", "scope_key")),
    "retention_hold_events_hold_revision": (P + "hold_events", ("hold_id", "revision")),
    "retention_runs_policy_sequence": (P + "runs", ("policy_id", "sequence")),
    "retention_runs_status_sequence": (P + "runs", ("status", "sequence")),
    "retention_archive_run_sequence": (P + "archive_items", ("archive_run_id", "sequence")),
    "retention_audit_org_sequence": (P + "audit_events", ("organization_id", "sequence")),
    "retention_audit_resource_sequence": (P + "audit_events", ("resource_kind", "resource_id", "sequence")),
}
FOREIGN_KEYS = {
    table: {
        (declaration.split("REFERENCES ")[1].split("(")[0], name, "id", "NO ACTION", "RESTRICT")
        for name, declaration in columns if "REFERENCES" in declaration
    }
    for table, columns in DEFINITIONS.items()
}
V97_FOREIGN_KEYS = {
    table: {
        (declaration.split("REFERENCES ")[1].split("(")[0], name, "id", "NO ACTION", "RESTRICT")
        for name, declaration in columns if "REFERENCES" in declaration
    }
    for table, columns in V97_DEFINITIONS.items()
}


def validate(connection, *, empty: bool = False) -> None:
    from xti.adapters.schema import SchemaError
    for statement in DDL:
        name = statement.split()[2]
        kind = "index" if statement.startswith("CREATE ") and " INDEX " in statement else "table"
        row = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, kind),
        ).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("P08 saklama kayıt düzeni beklenen biçimde değil.")
    if empty:
        for table in TABLES:
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise SchemaError("Eski şemada P08 saklama kaydı bulunamaz.")


def validate_v98(connection, *, empty: bool = False) -> None:
    """Validate the monitoring-only schema used by core schemas 97 and 98."""
    from xti.adapters.schema import SchemaError
    for statement in V97_DDL:
        name = statement.split()[2]
        kind = "index" if statement.startswith("CREATE ") and " INDEX " in statement else "table"
        row = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, kind),
        ).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("P08 eski saklama kayıt düzeni beklenen biçimde değil.")
    if empty:
        for table in V97_DEFINITIONS:
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise SchemaError("Eski şemada P08 saklama kaydı bulunamaz.")


def migrate_v99(connection) -> None:
    """Widen the two family-bound tables while preserving ids and sequences."""
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError("P08/P12 saklama şema geçişi transaction gerektirir.")
    try:
        validate(connection)
        return
    except SchemaError:
        validate_v98(connection)

    names = ("retention_holds", "retention_hold_events", "retention_archive_items")
    for name in names:
        connection.execute(
            f"CREATE TEMP TABLE xti_v99_{name} AS SELECT * FROM {name} ORDER BY sequence"
        )
    connection.execute("DROP TABLE retention_hold_events")
    connection.execute("DROP TABLE retention_holds")
    connection.execute("DROP TABLE retention_archive_items")

    wanted = set(names) | {
        "retention_holds_scope_active", "retention_hold_events_hold_revision",
        "retention_archive_run_sequence",
    }
    for statement in DDL:
        if statement.split()[2] in wanted:
            connection.execute(statement)
    for name in names:
        columns = ["sequence"] + [column for column, _declaration in DEFINITIONS[name]]
        joined = ",".join(columns)
        connection.execute(
            f"INSERT INTO {name} ({joined}) SELECT {joined} FROM xti_v99_{name} ORDER BY sequence"
        )
        connection.execute(f"DROP TABLE temp.xti_v99_{name}")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise SchemaError("P08/P12 saklama geçişinde kayıt bağlantısı bozuldu.")
    validate(connection)


def create(connection) -> None:
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError("P08 şema geçişi transaction gerektirir.")
    if connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE name='retention_policies'"
    ).fetchone():
        try:
            validate(connection, empty=True)
        except SchemaError:
            validate_v98(connection, empty=True)
            migrate_v99(connection)
        return
    for statement in DDL:
        connection.execute(statement)
    validate(connection)
