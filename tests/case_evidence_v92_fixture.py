"""Reconstruct the exact schema92 case layout without discarding P05 evidence."""

from xti.adapters.case_public_notice_schema import (
    CASE_EVIDENCE_COLUMNS,
    CASE_EVIDENCE_INDEX_DDL,
)
from xti.adapters.darkweb_monitoring_schema import (
    CASE_EVIDENCE_DDL,
    PREVIOUS_CASE_DDL,
    TABLES,
)


def case_evidence_layout_v92(connection):
    """Remove only empty schema93 state and restore the preceding case CHECK."""
    from tests.case_evidence_v94_fixture import case_evidence_layout_v94

    case_evidence_layout_v94(connection)
    for table in reversed(tuple(TABLES)):
        if connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE name=?", (table,)
        ).fetchone():
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise ValueError("Fixture contains schema93 dark-web evidence")
            connection.execute(f"DROP TABLE {table}")

    row = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE name='case_evidence'"
    ).fetchone()
    if row is None or row[0] != CASE_EVIDENCE_DDL:
        return
    if connection.execute(
        "SELECT 1 FROM case_evidence "
        "WHERE evidence_type='darkweb_monitoring' LIMIT 1"
    ).fetchone():
        raise ValueError("Fixture contains schema93 case evidence")

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
