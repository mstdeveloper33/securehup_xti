"""Schema63 widens case evidence types without rewriting historical payloads."""

import sqlite3


CASE_EVIDENCE_V62_DDL = (
    "CREATE TABLE case_evidence ("
    "id TEXT PRIMARY KEY NOT NULL, case_id TEXT NOT NULL REFERENCES cases(id) "
    "ON DELETE RESTRICT, evidence_type TEXT NOT NULL CHECK (evidence_type IN "
    "('finding', 'social_profile', 'ransomware_threatcluster', "
    "'ransomware_ransomlook', 'supplier')), evidence_id TEXT NOT NULL, "
    "display_value TEXT NOT NULL, source_reference TEXT NOT NULL, "
    "snapshot_json TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), added_reason TEXT NOT NULL, "
    "added_at TEXT NOT NULL, updated_at TEXT NOT NULL, removed_reason TEXT, removed_at TEXT, "
    "UNIQUE(case_id, evidence_type, evidence_id), "
    "CHECK ((active = 1 AND removed_reason IS NULL AND removed_at IS NULL) OR "
    "(active = 0 AND removed_reason IS NOT NULL AND removed_at IS NOT NULL)))"
)
CASE_EVIDENCE_DDL = CASE_EVIDENCE_V62_DDL.replace(
    "'ransomware_ransomlook', 'supplier'))",
    "'ransomware_ransomlook', 'supplier', 'public_notice', 'public_notice_watch'))",
)
CASE_EVIDENCE_INDEX_DDL = (
    "CREATE INDEX case_evidence_case_active_updated ON "
    "case_evidence(case_id, active, updated_at)"
)
CASE_EVIDENCE_COLUMNS = (
    "id", "case_id", "evidence_type", "evidence_id", "display_value",
    "source_reference", "snapshot_json", "snapshot_sha256", "active", "added_reason",
    "added_at", "updated_at", "removed_reason", "removed_at",
)


def migrate_case_public_notice_schema(connection: sqlite3.Connection) -> None:
    """Called under the migration writer lock after a verified recovery backup."""
    if not connection.in_transaction:
        raise sqlite3.OperationalError("Case evidence migration requires a transaction")
    columns = ", ".join(CASE_EVIDENCE_COLUMNS)
    connection.execute(
        "CREATE TEMP TABLE xti_case_evidence_v62_copy AS "
        f"SELECT rowid AS legacy_rowid, {columns} FROM case_evidence ORDER BY rowid"
    )
    # No table references case_evidence: activity references are frozen payloads.
    # All declared foreign keys remain enabled throughout this transaction.
    connection.execute("DROP TABLE case_evidence")
    connection.execute(CASE_EVIDENCE_DDL)
    connection.execute(
        f"INSERT INTO case_evidence (rowid, {columns}) "
        f"SELECT legacy_rowid, {columns} FROM xti_case_evidence_v62_copy ORDER BY legacy_rowid"
    )
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute("DROP TABLE xti_case_evidence_v62_copy")
