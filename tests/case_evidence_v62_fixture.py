"""Faithful schema54–62 evidence CHECK for migration fixtures only."""

from xti.adapters.case_public_notice_schema import (
    CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL, CASE_EVIDENCE_V62_DDL,
)


def case_evidence_layout_v62(connection):
    """Refuse new types; preserve all old rows and identities in fixture setup."""
    if not connection.in_transaction:
        connection.execute("BEGIN")
    if connection.execute(
        "SELECT 1 FROM case_evidence WHERE evidence_type IN ('public_notice', 'public_notice_watch') LIMIT 1"
    ).fetchone():
        raise ValueError("Fixture has schema63-only case evidence")
    columns = ", ".join(CASE_EVIDENCE_COLUMNS)
    rows = connection.execute(f"SELECT rowid, {columns} FROM case_evidence ORDER BY rowid").fetchall()
    connection.execute("DROP TABLE case_evidence")
    connection.execute(CASE_EVIDENCE_V62_DDL)
    for row in rows:
        connection.execute(
            f"INSERT INTO case_evidence (rowid, {columns}) VALUES ({','.join('?' for _ in row)})", row,
        )
    connection.execute(CASE_EVIDENCE_INDEX_DDL)
