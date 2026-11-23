"""Reconstruct schema96 without discarding any P08 retention evidence."""

from xti.adapters.data_retention_schema import TABLES


def case_evidence_layout_v96(connection):
    """Remove only empty schema97 retention state; P07 rows stay untouched."""
    from tests.case_evidence_v97_fixture import telemetry_layout_v97

    telemetry_layout_v97(connection)
    for table in reversed(tuple(TABLES)):
        if connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE name=?", (table,)
        ).fetchone():
            if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise ValueError("Fixture contains schema97 retention evidence")
            connection.execute(f"DROP TABLE {table}")
