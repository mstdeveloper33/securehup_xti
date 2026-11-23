"""Reconstruct schema95 without discarding any P07 monitoring evidence."""

from xti.adapters.case_public_notice_schema import (
    CASE_EVIDENCE_COLUMNS,
    CASE_EVIDENCE_INDEX_DDL,
)
from xti.adapters.unified_monitoring_schema import (
    CASE_EVIDENCE_DDL,
    PREVIOUS_CASE_DDL,
    TABLES,
)


def case_evidence_layout_v95(connection):
    """Remove only empty schema96 state and restore the preceding case CHECK."""
    from tests.case_evidence_v96_fixture import case_evidence_layout_v96

    case_evidence_layout_v96(connection)
    for table in reversed(tuple(TABLES)):
        if connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE name=?", (table,)
        ).fetchone():
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise ValueError("Fixture contains schema96 unified-monitoring evidence")
            connection.execute(f"DROP TABLE {table}")

    row = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE name='case_evidence'"
    ).fetchone()
    if row is None or " ".join(row[0].split()) != " ".join(CASE_EVIDENCE_DDL.split()):
        return
    if connection.execute(
        "SELECT 1 FROM case_evidence "
        "WHERE evidence_type='unified_monitoring' LIMIT 1"
    ).fetchone():
        raise ValueError("Fixture contains schema96 case evidence")

    names = ",".join(CASE_EVIDENCE_COLUMNS)
    rows = connection.execute(
        f"SELECT rowid,{names} FROM case_evidence ORDER BY rowid"
    ).fetchall()
    connection.execute("DROP TABLE case_evidence")
    connection.execute(PREVIOUS_CASE_DDL)
    for evidence_row in rows:
        connection.execute(
            f"INSERT INTO case_evidence (rowid,{names}) "
            f"VALUES ({','.join('?' for _ in evidence_row)})",
            evidence_row,
        )
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
