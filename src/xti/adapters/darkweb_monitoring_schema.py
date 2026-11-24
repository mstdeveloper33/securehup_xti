"""Schema100: P11 aggregate exposure and minimized AIL source history."""

from xti.adapters.cti_analysis_schema import CASE_EVIDENCE_DDL as PREVIOUS_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL


CASE_EVIDENCE_DDL = PREVIOUS_CASE_DDL.replace(
    "'cti_analysis'))", "'cti_analysis', 'darkweb_monitoring'))"
)
P = "darkweb_"
DEFINITIONS = {
    "profiles": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("name_key", "TEXT NOT NULL"),
        ("revision", "INTEGER NOT NULL"),
        ("enabled", "INTEGER NOT NULL CHECK(enabled IN (0,1))"),
        ("definition_json", "TEXT NOT NULL"),
        ("definition_sha256", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
        ("updated_at", "TEXT NOT NULL"),
        ("last_started_at", "TEXT"),
        ("last_run_id", "TEXT"),
    ],
    "runs": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("profile_id", f"TEXT NOT NULL REFERENCES {P}profiles(id) ON DELETE RESTRICT"),
        ("request_key", "TEXT NOT NULL UNIQUE"),
        ("request_sha256", "TEXT NOT NULL"),
        ("snapshot_json", "TEXT NOT NULL"),
        ("snapshot_sha256", "TEXT NOT NULL"),
        ("status", "TEXT NOT NULL CHECK(status IN ('running','complete','failed','interrupted'))"),
        ("baseline_run_id", f"TEXT REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("report_json", "TEXT"),
        ("report_sha256", "TEXT"),
        ("started_at", "TEXT NOT NULL"),
        ("finished_at", "TEXT"),
    ],
    "evidence": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("body_json", "TEXT NOT NULL"),
        ("body_sha256", "TEXT NOT NULL UNIQUE"),
        ("created_at", "TEXT NOT NULL"),
    ],
    "findings": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("profile_id", f"TEXT NOT NULL REFERENCES {P}profiles(id) ON DELETE RESTRICT"),
        ("candidate_key", "TEXT NOT NULL"),
        ("kind", "TEXT NOT NULL CHECK(kind IN ('ransomware_claim','breach_notice','credential_exposure','domain_exposure','underground_mention'))"),
        ("target_kind", "TEXT NOT NULL CHECK(target_kind IN ('organization','supplier'))"),
        ("target_id", "TEXT NOT NULL"),
        ("source_key", "TEXT NOT NULL CHECK(source_key IN ('ransomlook','threatcluster','hibp_public','hibp_domain','xposedornot_domain','lunar_domain','ail_tracker'))"),
        ("evidence_id", f"TEXT NOT NULL REFERENCES {P}evidence(id) ON DELETE RESTRICT"),
        ("last_run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("profile_revision", "INTEGER NOT NULL"),
        ("observation_revision", "INTEGER NOT NULL"),
        ("review_revision", "INTEGER NOT NULL"),
        ("priority", "TEXT NOT NULL CHECK(priority IN ('low','medium','high','critical'))"),
        ("first_seen", "TEXT NOT NULL"),
        ("last_seen", "TEXT NOT NULL"),
    ],
    "reviews": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("finding_id", f"TEXT NOT NULL REFERENCES {P}findings(id) ON DELETE RESTRICT"),
        ("evidence_id", f"TEXT NOT NULL REFERENCES {P}evidence(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL"),
        ("observation_revision", "INTEGER NOT NULL"),
        ("decision", "TEXT NOT NULL CHECK(decision IN ('relevant','unrelated','uncertain','confirmed_incident','resolved'))"),
        ("reason", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
    ],
    "changes": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("profile_id", f"TEXT NOT NULL REFERENCES {P}profiles(id) ON DELETE RESTRICT"),
        ("run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("finding_id", f"TEXT NOT NULL REFERENCES {P}findings(id) ON DELETE RESTRICT"),
        ("kind", "TEXT NOT NULL CHECK(kind IN ('new','changed'))"),
        ("before_evidence_id", f"TEXT REFERENCES {P}evidence(id) ON DELETE RESTRICT"),
        ("after_evidence_id", f"TEXT NOT NULL REFERENCES {P}evidence(id) ON DELETE RESTRICT"),
        ("created_at", "TEXT NOT NULL"),
    ],
    "notifications": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("change_id", f"TEXT NOT NULL UNIQUE REFERENCES {P}changes(id) ON DELETE RESTRICT"),
        ("created_at", "TEXT NOT NULL"),
        ("read_at", "TEXT"),
    ],
    "mutations": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("request_key", "TEXT NOT NULL UNIQUE"),
        ("request_sha256", "TEXT NOT NULL"),
        ("result_json", "TEXT NOT NULL"),
        ("result_sha256", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
    ],
    "credential_runs": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("profile_id", f"TEXT NOT NULL REFERENCES {P}profiles(id) ON DELETE RESTRICT"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("domain", "TEXT NOT NULL"),
        ("provider", "TEXT NOT NULL CHECK(provider IN ('hibp_domain','xposedornot_domain'))"),
        ("request_key", "TEXT NOT NULL UNIQUE"),
        ("request_sha256", "TEXT NOT NULL"),
        ("source_url", "TEXT NOT NULL"),
        ("status", "TEXT NOT NULL CHECK(status IN ('running','complete','failed','interrupted'))"),
        ("content_sha256", "TEXT"),
        ("snapshot_sha256", "TEXT"),
        ("account_count", "INTEGER NOT NULL"),
        ("added_count", "INTEGER NOT NULL"),
        ("updated_count", "INTEGER NOT NULL"),
        ("unchanged_count", "INTEGER NOT NULL"),
        ("removed_count", "INTEGER NOT NULL"),
        ("error_code", "TEXT"),
        ("error", "TEXT"),
        ("started_at", "TEXT NOT NULL"),
        ("finished_at", "TEXT"),
        ("fetched_at", "TEXT"),
        ("chain_sha256", "TEXT"),
    ],
    "credential_accounts": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("domain", "TEXT NOT NULL"),
        ("identity_hmac", "TEXT NOT NULL"),
        ("masked_account", "TEXT NOT NULL"),
        ("breaches_json", "TEXT NOT NULL"),
        ("breaches_sha256", "TEXT NOT NULL"),
        ("state_sha256", "TEXT NOT NULL"),
        ("active", "INTEGER NOT NULL CHECK(active IN (0,1))"),
        ("first_run_id", f"TEXT NOT NULL REFERENCES {P}credential_runs(id) ON DELETE RESTRICT"),
        ("last_run_id", f"TEXT NOT NULL REFERENCES {P}credential_runs(id) ON DELETE RESTRICT"),
        ("first_seen", "TEXT NOT NULL"),
        ("last_seen", "TEXT NOT NULL"),
    ],
    "credential_changes": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("run_id", f"TEXT NOT NULL REFERENCES {P}credential_runs(id) ON DELETE RESTRICT"),
        ("account_id", f"TEXT NOT NULL REFERENCES {P}credential_accounts(id) ON DELETE RESTRICT"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','updated','removed'))"),
        ("before_json", "TEXT"),
        ("before_sha256", "TEXT"),
        ("after_json", "TEXT"),
        ("after_sha256", "TEXT"),
        ("created_at", "TEXT NOT NULL"),
    ],
    "source_runs": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("profile_id", f"TEXT NOT NULL REFERENCES {P}profiles(id) ON DELETE RESTRICT"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("provider", "TEXT NOT NULL CHECK(provider IN ('lunar_domain','ail_tracker'))"),
        ("mode", "TEXT NOT NULL CHECK(mode IN ('snapshot','incremental'))"),
        ("target", "TEXT NOT NULL"),
        ("request_key", "TEXT NOT NULL UNIQUE"),
        ("request_sha256", "TEXT NOT NULL"),
        ("source_reference", "TEXT NOT NULL"),
        ("status", "TEXT NOT NULL CHECK(status IN ('running','pending','complete','failed','interrupted'))"),
        ("content_sha256", "TEXT"),
        ("snapshot_sha256", "TEXT"),
        ("record_count", "INTEGER NOT NULL"),
        ("added_count", "INTEGER NOT NULL"),
        ("updated_count", "INTEGER NOT NULL"),
        ("unchanged_count", "INTEGER NOT NULL"),
        ("removed_count", "INTEGER NOT NULL"),
        ("error_code", "TEXT"),
        ("error", "TEXT"),
        ("started_at", "TEXT NOT NULL"),
        ("finished_at", "TEXT"),
        ("fetched_at", "TEXT"),
        ("chain_sha256", "TEXT"),
    ],
    "source_records": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("organization_id", "TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT"),
        ("provider", "TEXT NOT NULL CHECK(provider IN ('lunar_domain','ail_tracker'))"),
        ("external_key", "TEXT NOT NULL"),
        ("record_kind", "TEXT NOT NULL CHECK(record_kind IN ('domain_exposure','underground_mention'))"),
        ("target_domain", "TEXT"),
        ("title", "TEXT NOT NULL"),
        ("body_json", "TEXT NOT NULL"),
        ("body_sha256", "TEXT NOT NULL"),
        ("state_sha256", "TEXT NOT NULL"),
        ("active", "INTEGER NOT NULL CHECK(active IN (0,1))"),
        ("first_run_id", f"TEXT NOT NULL REFERENCES {P}source_runs(id) ON DELETE RESTRICT"),
        ("last_run_id", f"TEXT NOT NULL REFERENCES {P}source_runs(id) ON DELETE RESTRICT"),
        ("first_seen", "TEXT NOT NULL"),
        ("last_seen", "TEXT NOT NULL"),
    ],
    "source_changes": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("run_id", f"TEXT NOT NULL REFERENCES {P}source_runs(id) ON DELETE RESTRICT"),
        ("record_id", f"TEXT NOT NULL REFERENCES {P}source_records(id) ON DELETE RESTRICT"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','updated','removed'))"),
        ("before_json", "TEXT"),
        ("before_sha256", "TEXT"),
        ("after_json", "TEXT"),
        ("after_sha256", "TEXT"),
        ("created_at", "TEXT NOT NULL"),
    ],
}
DEFINITIONS = {P + key: value for key, value in DEFINITIONS.items()}
COMPOSITE = {
    P + "profiles": ("organization_id", "name_key"),
    P + "findings": ("profile_id", "candidate_key"),
    P + "reviews": ("finding_id", "revision"),
    P + "credential_accounts": ("organization_id", "domain", "identity_hmac"),
    P + "credential_changes": ("run_id", "account_id"),
    P + "source_records": ("organization_id", "provider", "external_key"),
    P + "source_changes": ("run_id", "record_id"),
}
INDEXES = {
    P + "profile_organization": (P + "profiles", ("organization_id", "sequence")),
    P + "run_profile": (P + "runs", ("profile_id", "sequence")),
    P + "run_status": (P + "runs", ("profile_id", "status", "sequence")),
    P + "finding_profile": (P + "findings", ("profile_id", "sequence")),
    P + "finding_kind": (P + "findings", ("profile_id", "kind", "priority", "sequence")),
    P + "review_finding": (P + "reviews", ("finding_id", "sequence")),
    P + "change_profile": (P + "changes", ("profile_id", "sequence")),
    P + "change_run": (P + "changes", ("run_id", "sequence")),
    P + "notification_read": (P + "notifications", ("read_at", "sequence")),
    P + "credential_run_scope": (P + "credential_runs", ("organization_id", "domain", "sequence")),
    P + "credential_account_scope": (P + "credential_accounts", ("organization_id", "domain", "active", "sequence")),
    P + "credential_change_run": (P + "credential_changes", ("run_id", "sequence")),
    P + "source_run_scope": (P + "source_runs", ("organization_id", "provider", "sequence")),
    P + "source_record_scope": (P + "source_records", ("organization_id", "provider", "active", "sequence")),
    P + "source_change_run": (P + "source_changes", ("run_id", "sequence")),
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
P11_TABLES = frozenset({P + "source_runs", P + "source_records", P + "source_changes"})
V99_DEFINITIONS = {table: columns for table, columns in DEFINITIONS.items() if table not in P11_TABLES}
V99_DDL = tuple(
    statement.replace(
        "CHECK(kind IN ('ransomware_claim','breach_notice','credential_exposure','domain_exposure','underground_mention'))",
        "CHECK(kind IN ('ransomware_claim','breach_notice','credential_exposure'))",
    ).replace(
        "CHECK(source_key IN ('ransomlook','threatcluster','hibp_public','hibp_domain','xposedornot_domain','lunar_domain','ail_tracker'))",
        "CHECK(source_key IN ('ransomlook','threatcluster','hibp_public','hibp_domain','xposedornot_domain'))",
    )
    for statement in DDL
    if not any(name in statement for name in P11_TABLES)
    and not any(name in statement for name in (
        P + "source_run_scope", P + "source_record_scope", P + "source_change_run",
    ))
)
V93_DDL = tuple(
    statement.replace(
        "CHECK(source_key IN ('ransomlook','threatcluster','hibp_public','hibp_domain','xposedornot_domain'))",
        "CHECK(source_key IN ('ransomlook','threatcluster','hibp_public','hibp_domain'))",
    ).replace(
        "CHECK(provider IN ('hibp_domain','xposedornot_domain'))",
        "CHECK(provider='hibp_domain')",
    )
    for statement in V99_DDL
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
P11_OBJECTS = frozenset(
    {(table, "table") for table in P11_TABLES}
    | {(name, "index") for name, (table, _columns) in INDEXES.items() if table in P11_TABLES}
)


def _validate(connection, statements, *, empty: bool = False) -> None:
    from xti.adapters.schema import SchemaError
    for statement in statements:
        name = statement.split()[2]
        row = connection.execute("SELECT sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("Dark web kayıt düzeni beklenen biçimde değil.")
    if empty:
        for table in TABLES:
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise SchemaError("Eski şemada dark web kayıtları boş olmalı.")


def validate(connection, *, empty: bool = False) -> None:
    _validate(connection, DDL, empty=empty)


def validate_v99(connection) -> None:
    _validate(connection, V99_DDL)


def validate_staged_v100(connection) -> None:
    """Accept an exact future layout only while every P11 table is still empty."""
    from xti.adapters.schema import SchemaError
    _validate(connection, DDL)
    for table in P11_TABLES:
        if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
            raise SchemaError("Eski şemada P11 dark web kayıtları boş olmalı.")


def validate_v93(connection) -> None:
    _validate(connection, V93_DDL)


def migrate_xposedornot(connection) -> None:
    """Rebuild schema93 CHECK constraints without changing any row identity."""
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError("XposedOrNot geçişi transaction gerektirir.")
    try:
        validate(connection)
        return
    except SchemaError:
        try:
            validate_v99(connection)
            return
        except SchemaError:
            validate_v93(connection)

    table_statements = [statement for statement in V99_DDL if statement.startswith("CREATE TABLE ")]
    old_sequences = dict(connection.execute(
        "SELECT name,seq FROM sqlite_sequence WHERE name IN ("
        + ",".join("?" for _ in V99_DEFINITIONS) + ")",
        tuple(V99_DEFINITIONS),
    ))
    for table in V99_DEFINITIONS:
        columns = ["sequence", *(name for name, _declaration in V99_DEFINITIONS[table])]
        names = ",".join(columns)
        connection.execute(
            f"CREATE TEMP TABLE xti_xon_{table} AS SELECT {names} FROM {table} ORDER BY sequence"
        )
    for table in reversed(tuple(V99_DEFINITIONS)):
        connection.execute("DROP TABLE " + table)
    for statement in V99_DDL:
        connection.execute(statement)
    for table in V99_DEFINITIONS:
        columns = ["sequence", *(name for name, _declaration in V99_DEFINITIONS[table])]
        names = ",".join(columns)
        connection.execute(
            f"INSERT INTO {table} ({names}) SELECT {names} FROM xti_xon_{table} "
            "ORDER BY sequence"
        )
        if table in old_sequences:
            current = connection.execute(
                "SELECT seq FROM sqlite_sequence WHERE name=?", (table,),
            ).fetchone()
            preserved = max(old_sequences[table], current[0] if current else 0)
            if current:
                connection.execute(
                    "UPDATE sqlite_sequence SET seq=? WHERE name=?", (preserved, table),
                )
            else:
                connection.execute(
                    "INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)", (table, preserved),
                )
        connection.execute("DROP TABLE temp.xti_xon_" + table)
    if len(table_statements) != len(V99_DEFINITIONS):
        raise SchemaError("XposedOrNot geçiş tablosu sayısı beklenen biçimde değil.")
    validate_v99(connection)


def migrate_v100(connection) -> None:
    """Add P11 history and widen P05 finding constraints without losing row identity."""
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError("P11 dark web geçişi transaction gerektirir.")
    try:
        validate(connection)
        return
    except SchemaError:
        validate_v99(connection)

    old_sequences = dict(connection.execute(
        "SELECT name,seq FROM sqlite_sequence WHERE name IN ("
        + ",".join("?" for _ in V99_DEFINITIONS) + ")",
        tuple(V99_DEFINITIONS),
    ))
    for table in V99_DEFINITIONS:
        columns = ["sequence", *(name for name, _declaration in V99_DEFINITIONS[table])]
        names = ",".join(columns)
        connection.execute(
            f"CREATE TEMP TABLE xti_p11_{table} AS "
            f"SELECT {names} FROM {table} ORDER BY sequence"
        )
    for table in reversed(tuple(V99_DEFINITIONS)):
        connection.execute("DROP TABLE " + table)
    for statement in DDL:
        connection.execute(statement)
    for table in V99_DEFINITIONS:
        columns = ["sequence", *(name for name, _declaration in V99_DEFINITIONS[table])]
        names = ",".join(columns)
        connection.execute(
            f"INSERT INTO {table} ({names}) SELECT {names} FROM xti_p11_{table} "
            "ORDER BY sequence"
        )
        if table in old_sequences:
            current = connection.execute(
                "SELECT seq FROM sqlite_sequence WHERE name=?", (table,),
            ).fetchone()
            preserved = max(old_sequences[table], current[0] if current else 0)
            if current:
                connection.execute(
                    "UPDATE sqlite_sequence SET seq=? WHERE name=?", (preserved, table),
                )
            else:
                connection.execute(
                    "INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)", (table, preserved),
                )
        connection.execute("DROP TABLE temp.xti_p11_" + table)
    validate(connection)


def create(connection) -> None:
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError("Dark web geçişi transaction gerektirir.")
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (P + "profiles",)).fetchone():
        validate(connection, empty=True)
    else:
        for statement in DDL:
            connection.execute(statement)
    current = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()[0]
    if " ".join(current.split()) == " ".join(CASE_EVIDENCE_DDL.split()):
        return
    if " ".join(current.split()) != " ".join(PREVIOUS_CASE_DDL.split()):
        raise SchemaError("Dark web geçişinde vaka düzeni uyuşmuyor.")
    columns = ",".join(CASE_EVIDENCE_COLUMNS)
    connection.execute(
        f"CREATE TEMP TABLE xti_darkweb_case_v92 AS "
        f"SELECT rowid AS legacy_rowid,{columns} FROM case_evidence ORDER BY rowid"
    )
    connection.execute("DROP TABLE case_evidence")
    connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(
        f"INSERT INTO case_evidence (rowid,{columns}) "
        f"SELECT legacy_rowid,{columns} FROM xti_darkweb_case_v92 ORDER BY legacy_rowid"
    )
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute("DROP TABLE temp.xti_darkweb_case_v92")
