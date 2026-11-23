"""Reconstruct schema94 without discarding any P06/P07 evidence."""

from xti.adapters.actionability_schema import TABLES


def case_evidence_layout_v94(connection):
    """Remove only empty schema95/96 state, preserving all older rows."""
    from tests.case_evidence_v95_fixture import case_evidence_layout_v95

    case_evidence_layout_v95(connection)
    for table in reversed(tuple(TABLES)):
        if connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE name=?", (table,)
        ).fetchone():
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise ValueError("Fixture contains schema95 actionability evidence")
            connection.execute(f"DROP TABLE {table}")
