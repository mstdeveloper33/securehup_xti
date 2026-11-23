"""Schema92: explainable CTI analysis candidates and immutable review history."""

from xti.adapters.brand_protection_schema import CASE_EVIDENCE_DDL as PREVIOUS_CASE_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL


CASE_EVIDENCE_DDL = PREVIOUS_CASE_DDL.replace(
    "'brand_protection'))", "'brand_protection', 'cti_analysis'))"
)
P = "cti_analysis_"
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
        ("input_sha256", "TEXT NOT NULL"),
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
    "candidates": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("profile_id", f"TEXT NOT NULL REFERENCES {P}profiles(id) ON DELETE RESTRICT"),
        ("candidate_key", "TEXT NOT NULL"),
        ("kind", "TEXT NOT NULL CHECK(kind IN ('identity','technique','attribution','tag','priority'))"),
        ("subject_kind", "TEXT NOT NULL"),
        ("subject_id", "TEXT NOT NULL"),
        ("object_kind", "TEXT NOT NULL"),
        ("object_id", "TEXT NOT NULL"),
        ("evidence_id", f"TEXT NOT NULL REFERENCES {P}evidence(id) ON DELETE RESTRICT"),
        ("last_run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("profile_revision", "INTEGER NOT NULL"),
        ("observation_revision", "INTEGER NOT NULL"),
        ("review_revision", "INTEGER NOT NULL"),
        ("score", "INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100)"),
        ("priority", "TEXT NOT NULL CHECK(priority IN ('low','medium','high','critical'))"),
        ("first_seen", "TEXT NOT NULL"),
        ("last_seen", "TEXT NOT NULL"),
    ],
    "reviews": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("candidate_id", f"TEXT NOT NULL REFERENCES {P}candidates(id) ON DELETE RESTRICT"),
        ("evidence_id", f"TEXT NOT NULL REFERENCES {P}evidence(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL"),
        ("observation_revision", "INTEGER NOT NULL"),
        ("decision", "TEXT NOT NULL CHECK(decision IN ('accepted','rejected','uncertain','same_entity','different_entity'))"),
        ("reason", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
    ],
    "changes": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("profile_id", f"TEXT NOT NULL REFERENCES {P}profiles(id) ON DELETE RESTRICT"),
        ("run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("candidate_id", f"TEXT NOT NULL REFERENCES {P}candidates(id) ON DELETE RESTRICT"),
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
}
DEFINITIONS = {P + key: value for key, value in DEFINITIONS.items()}
COMPOSITE = {
    P + "profiles": ("organization_id", "name_key"),
    P + "candidates": ("profile_id", "candidate_key"),
    P + "reviews": ("candidate_id", "revision"),
}
INDEXES = {
    P + "profile_organization": (P + "profiles", ("organization_id", "sequence")),
    P + "run_profile": (P + "runs", ("profile_id", "sequence")),
    P + "run_status": (P + "runs", ("profile_id", "status", "sequence")),
    P + "candidate_profile": (P + "candidates", ("profile_id", "sequence")),
    P + "candidate_last_run": (P + "candidates", ("profile_id", "last_run_id", "sequence")),
    P + "candidate_kind_score": (P + "candidates", ("profile_id", "kind", "score", "sequence")),
    P + "review_candidate": (P + "reviews", ("candidate_id", "sequence")),
    P + "change_profile": (P + "changes", ("profile_id", "sequence")),
    P + "change_run": (P + "changes", ("run_id", "sequence")),
    P + "notification_read": (P + "notifications", ("read_at", "sequence")),
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
    + [(name, declaration.split()[0], int("NOT NULL" in declaration), 0) for name, declaration in columns]
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
        row = connection.execute("SELECT sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("CTI analiz kayıt düzeni beklenen biçimde değil.")
    if empty:
        for table in TABLES:
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise SchemaError("Eski şemada CTI analiz kayıtları boş olmalı.")


def create(connection) -> None:
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError("CTI analiz geçişi transaction gerektirir.")
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (P + "profiles",)).fetchone():
        validate(connection, empty=True)
    else:
        for statement in DDL:
            connection.execute(statement)
    current = connection.execute("SELECT sql FROM sqlite_schema WHERE name='case_evidence'").fetchone()[0]
    if " ".join(current.split()) == " ".join(CASE_EVIDENCE_DDL.split()):
        return
    if " ".join(current.split()) != " ".join(PREVIOUS_CASE_DDL.split()):
        raise SchemaError("CTI analiz geçişinde vaka düzeni uyuşmuyor.")
    columns = ",".join(CASE_EVIDENCE_COLUMNS)
    connection.execute(
        f"CREATE TEMP TABLE xti_cti_analysis_case_v91 AS "
        f"SELECT rowid AS legacy_rowid,{columns} FROM case_evidence ORDER BY rowid"
    )
    connection.execute("DROP TABLE case_evidence")
    connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(
        f"INSERT INTO case_evidence (rowid,{columns}) "
        f"SELECT legacy_rowid,{columns} FROM xti_cti_analysis_case_v91 ORDER BY legacy_rowid"
    )
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute("DROP TABLE temp.xti_cti_analysis_case_v91")
