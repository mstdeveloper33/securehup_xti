"""Reconstruct schema97 without losing P07/P08 or existing case evidence."""

from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL
from xti.adapters.telemetry_schema import (
    CASE_EVIDENCE_DDL as CURRENT_CASE_DDL,
    PREVIOUS_CASE_DDL,
    TABLES,
)


def telemetry_layout_v97(connection):
    existing = {
        table for table in TABLES if connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,),
        ).fetchone()
    }
    if not existing:
        return
    if existing != set(TABLES):
        raise ValueError("Fixture contains a partial schema98 telemetry layout")
    for table in reversed(tuple(TABLES)):
        if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
            raise ValueError("Fixture contains schema98 telemetry evidence")
        connection.execute(f"DROP TABLE {table}")
    case_row = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE type='table' AND name='case_evidence'"
    ).fetchone()
    # Schemas before case management legitimately have no case_evidence table.
    # Their downgrade fixtures still need the empty schema98 telemetry tables
    # removed, but there is no later evidence CHECK to reconstruct.
    if case_row is None:
        return
    current = case_row[0]
    if " ".join(current.split()) != " ".join(CURRENT_CASE_DDL.split()):
        raise ValueError("Fixture current case layout differs")
    columns = ",".join(CASE_EVIDENCE_COLUMNS)
    connection.execute(
        f"CREATE TEMP TABLE telemetry_case_v97 AS "
        f"SELECT rowid AS legacy_rowid,{columns} FROM case_evidence ORDER BY rowid"
    )
    connection.execute("DROP TABLE case_evidence")
    connection.execute(PREVIOUS_CASE_DDL)
    connection.execute(
        f"INSERT INTO case_evidence (rowid,{columns}) "
        f"SELECT legacy_rowid,{columns} FROM telemetry_case_v97 ORDER BY legacy_rowid"
    )
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
    connection.execute("DROP TABLE telemetry_case_v97")
