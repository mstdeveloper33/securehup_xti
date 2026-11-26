"""Schema101: reviewed abuse-contact discovery and takedown bindings."""

P = "action_contact_"

DEFINITIONS = {
    "watches": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("case_id", "TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT"),
        ("evidence_link_id", "TEXT NOT NULL REFERENCES case_evidence(id) ON DELETE RESTRICT"),
        ("subject_kind", "TEXT NOT NULL CHECK(subject_kind IN ('domain','ip'))"),
        ("subject_value", "TEXT NOT NULL"),
        ("evidence_sha256", "TEXT NOT NULL"),
        ("interval_seconds", "INTEGER NOT NULL CHECK(interval_seconds BETWEEN 300 AND 2592000)"),
        ("include_whois", "INTEGER NOT NULL CHECK(include_whois IN (0,1))"),
        ("enabled", "INTEGER NOT NULL CHECK(enabled IN (0,1))"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("idempotency_key", "TEXT NOT NULL UNIQUE"),
        ("created_by", "TEXT NOT NULL"),
        ("reason", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"),
        ("updated_at", "TEXT NOT NULL"),
        ("last_started_at", "TEXT"),
        ("last_run_id", "TEXT"),
    ],
    "watch_events": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("watch_id", f"TEXT NOT NULL REFERENCES {P}watches(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','updated','disabled','enabled'))"),
        ("snapshot_json", "TEXT NOT NULL"),
        ("snapshot_sha256", "TEXT NOT NULL"),
        ("idempotency_key", "TEXT NOT NULL UNIQUE"),
        ("actor", "TEXT NOT NULL"),
        ("reason", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "runs": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("watch_id", f"TEXT NOT NULL REFERENCES {P}watches(id) ON DELETE RESTRICT"),
        ("watch_revision", "INTEGER NOT NULL CHECK(watch_revision>0)"),
        ("idempotency_key", "TEXT NOT NULL UNIQUE"),
        ("request_sha256", "TEXT NOT NULL"),
        ("status", "TEXT NOT NULL CHECK(status IN ('running','complete','partial','failed','interrupted'))"),
        ("source_count", "INTEGER NOT NULL CHECK(source_count>=0)"),
        ("succeeded_source_count", "INTEGER NOT NULL CHECK(succeeded_source_count>=0)"),
        ("failed_source_count", "INTEGER NOT NULL CHECK(failed_source_count>=0)"),
        ("candidate_count", "INTEGER NOT NULL CHECK(candidate_count>=0)"),
        ("added_count", "INTEGER NOT NULL CHECK(added_count>=0)"),
        ("updated_count", "INTEGER NOT NULL CHECK(updated_count>=0)"),
        ("reactivated_count", "INTEGER NOT NULL CHECK(reactivated_count>=0)"),
        ("unchanged_count", "INTEGER NOT NULL CHECK(unchanged_count>=0)"),
        ("removed_count", "INTEGER NOT NULL CHECK(removed_count>=0)"),
        ("report_json", "TEXT"),
        ("report_sha256", "TEXT"),
        ("error_code", "TEXT"),
        ("error", "TEXT"),
        ("started_at", "TEXT NOT NULL"),
        ("finished_at", "TEXT"),
        ("previous_chain_sha256", "TEXT"),
        ("chain_sha256", "TEXT"),
        ("recovery_key", "TEXT UNIQUE"),
        ("recovered_by", "TEXT"),
        ("recovery_reason", "TEXT"),
    ],
    "source_results": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("source_key", "TEXT NOT NULL CHECK(source_key IN ('domain_rdap','ip_rdap','security_txt','whois'))"),
        ("status", "TEXT NOT NULL CHECK(status IN ('complete','empty','failed','skipped','requirement_missing'))"),
        ("source_reference", "TEXT NOT NULL"),
        ("observed_at", "TEXT NOT NULL"),
        ("content_sha256", "TEXT"),
        ("result_json", "TEXT NOT NULL"),
        ("result_sha256", "TEXT NOT NULL"),
        ("candidate_count", "INTEGER NOT NULL CHECK(candidate_count>=0)"),
        ("request_count", "INTEGER NOT NULL CHECK(request_count>=0)"),
        ("received_bytes", "INTEGER NOT NULL CHECK(received_bytes>=0)"),
        ("elapsed_ms", "INTEGER NOT NULL CHECK(elapsed_ms>=0)"),
        ("error_code", "TEXT"),
        ("error", "TEXT"),
    ],
    "candidates": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("watch_id", f"TEXT NOT NULL REFERENCES {P}watches(id) ON DELETE RESTRICT"),
        ("candidate_key", "TEXT NOT NULL"),
        ("contact_kind", "TEXT NOT NULL CHECK(contact_kind IN ('registrar_abuse','network_abuse','security_contact','whois_abuse'))"),
        ("channel", "TEXT NOT NULL CHECK(channel IN ('email','url','phone'))"),
        ("contact_value", "TEXT NOT NULL"),
        ("routing_kind", "TEXT NOT NULL CHECK(routing_kind IN ('registrar','domain_hosting'))"),
        ("source_key", "TEXT NOT NULL CHECK(source_key IN ('domain_rdap','ip_rdap','security_txt','whois'))"),
        ("source_reference", "TEXT NOT NULL"),
        ("confidence", "TEXT NOT NULL CHECK(confidence IN ('high','medium','low'))"),
        ("active", "INTEGER NOT NULL CHECK(active IN (0,1))"),
        ("observation_revision", "INTEGER NOT NULL CHECK(observation_revision>0)"),
        ("review_revision", "INTEGER NOT NULL CHECK(review_revision>=0)"),
        ("evidence_json", "TEXT NOT NULL"),
        ("evidence_sha256", "TEXT NOT NULL"),
        ("first_run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("last_run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("first_seen", "TEXT NOT NULL"),
        ("last_seen", "TEXT NOT NULL"),
    ],
    "candidate_events": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("candidate_id", f"TEXT NOT NULL REFERENCES {P}candidates(id) ON DELETE RESTRICT"),
        ("run_id", f"TEXT NOT NULL REFERENCES {P}runs(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("action", "TEXT NOT NULL CHECK(action IN ('added','updated','reactivated','removed'))"),
        ("state_json", "TEXT NOT NULL"),
        ("state_sha256", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "reviews": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("candidate_id", f"TEXT NOT NULL REFERENCES {P}candidates(id) ON DELETE RESTRICT"),
        ("revision", "INTEGER NOT NULL CHECK(revision>0)"),
        ("observation_revision", "INTEGER NOT NULL CHECK(observation_revision>0)"),
        ("decision", "TEXT NOT NULL CHECK(decision IN ('approved','rejected','uncertain'))"),
        ("idempotency_key", "TEXT NOT NULL UNIQUE"),
        ("actor", "TEXT NOT NULL"),
        ("reason", "TEXT NOT NULL"),
        ("evidence_sha256", "TEXT NOT NULL"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
    "takedown_links": [
        ("id", "TEXT NOT NULL UNIQUE"),
        ("takedown_id", "TEXT NOT NULL UNIQUE REFERENCES action_takedowns(id) ON DELETE RESTRICT"),
        ("candidate_id", f"TEXT NOT NULL REFERENCES {P}candidates(id) ON DELETE RESTRICT"),
        ("candidate_evidence_sha256", "TEXT NOT NULL"),
        ("review_revision", "INTEGER NOT NULL CHECK(review_revision>0)"),
        ("recorded_at", "TEXT NOT NULL"),
    ],
}

DEFINITIONS = {P + name: columns for name, columns in DEFINITIONS.items()}
COMPOSITE = {
    P + "watches": ("case_id", "evidence_link_id", "subject_kind", "subject_value"),
    P + "watch_events": ("watch_id", "revision"),
    P + "source_results": ("run_id", "source_key"),
    P + "candidates": ("watch_id", "candidate_key"),
    P + "candidate_events": ("candidate_id", "revision"),
    P + "reviews": ("candidate_id", "revision"),
}
INDEXES = {
    P + "watches_due": (P + "watches", ("enabled", "last_started_at", "sequence")),
    P + "watch_events_watch": (P + "watch_events", ("watch_id", "revision")),
    P + "runs_watch": (P + "runs", ("watch_id", "sequence")),
    P + "runs_status": (P + "runs", ("status", "sequence")),
    P + "source_results_run": (P + "source_results", ("run_id", "source_key")),
    P + "candidates_watch": (P + "candidates", ("watch_id", "active", "sequence")),
    P + "candidate_events_candidate": (P + "candidate_events", ("candidate_id", "revision")),
    P + "reviews_candidate": (P + "reviews", ("candidate_id", "revision")),
    P + "takedown_links_candidate": (P + "takedown_links", ("candidate_id", "sequence")),
}

DDL = tuple(
    "CREATE TABLE " + table + " (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "
    + ", ".join(name + " " + declaration for name, declaration in columns)
    + (", UNIQUE(" + ",".join(COMPOSITE[table]) + ")" if table in COMPOSITE else "")
    + ")"
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
        kind = "index" if statement.startswith("CREATE INDEX") else "table"
        row = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, kind),
        ).fetchone()
        if row is None or " ".join(row[0].split()) != " ".join(statement.split()):
            raise SchemaError("Abuse iletişim kayıt düzeni beklenen biçimde değil.")
    if empty:
        for table in TABLES:
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise SchemaError("Eski şemada abuse iletişim kaydı bulunamaz.")


def create(connection) -> None:
    from xti.adapters.schema import SchemaError
    if not connection.in_transaction:
        raise SchemaError("Abuse iletişim şema geçişi transaction gerektirir.")
    if connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE name=?", (P + "watches",),
    ).fetchone():
        validate(connection, empty=True)
        return
    for statement in DDL:
        connection.execute(statement)
