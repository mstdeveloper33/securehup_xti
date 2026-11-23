"""Schema94: XposedOrNot provenance plus legacy-readable credential history."""

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
        ("kind", "TEXT NOT NULL CHECK(kind IN ('ransomware_claim','breach_notice','credential_exposure'))"),
        ("target_kind", "TEXT NOT NULL CHECK(target_kind IN ('organization','supplier'))"),
        ("target_id", "TEXT NOT NULL"),
        ("source_key", "TEXT NOT NULL CHECK(source_key IN ('ransomlook','threatcluster','hibp_public','hibp_domain','xposedornot_domain'))"),
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
}
DEFINITIONS = {P + key: value for key, value in DEFINITIONS.items()}
COMPOSITE = {
    P + "profiles": ("organization_id", "name_key"),
    P + "findings": ("profile_id", "candidate_key"),
    P + "reviews": ("finding_id", "revision"),
    P + "credential_accounts": ("organization_id", "domain", "identity_hmac"),
    P + "credential_changes": ("run_id", "account_id"),
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
V93_DDL = tuple(
    statement.replace(
        "CHECK(source_key IN ('ransomlook','threatcluster','hibp_public','hibp_domain','xposedornot_domain'))",
        "CHECK(source_key IN ('ransomlook','threatcluster','hibp_public','hibp_domain'))",
    ).replace(
        "CHECK(provider IN ('hibp_domain','xposedornot_domain'))",
        "CHECK(provider='hibp_domain')",
    )
    for statement in DDL
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
        validate_v93(connection)

    table_statements = [statement for statement in DDL if statement.startswith("CREATE TABLE ")]
    old_sequences = dict(connection.execute(
        "SELECT name,seq FROM sqlite_sequence WHERE name IN ("
        + ",".join("?" for _ in DEFINITIONS) + ")",
        tuple(DEFINITIONS),
    ))
    for table in DEFINITIONS:
        columns = ["sequence", *(name for name, _declaration in DEFINITIONS[table])]
        names = ",".join(columns)
        connection.execute(
            f"CREATE TEMP TABLE xti_xon_{table} AS SELECT {names} FROM {table} ORDER BY sequence"
        )
    for table in reversed(tuple(DEFINITIONS)):
        connection.execute("DROP TABLE " + table)
    for statement in DDL:
        connection.execute(statement)
    for table in DEFINITIONS:
        columns = ["sequence", *(name for name, _declaration in DEFINITIONS[table])]
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
    if len(table_statements) != len(DEFINITIONS):
        raise SchemaError("XposedOrNot geçiş tablosu sayısı beklenen biçimde değil.")
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
