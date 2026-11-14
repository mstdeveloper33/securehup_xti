"""Faithful pre61 collection layout for legacy migration fixtures only."""

from xti.adapters.collection_public_notice_schema import (
    COLLECTION_HISTORY_V60_DDL, COLLECTION_STEP_COLUMNS, COLLECTION_RECEIPT_V60_COLUMNS,
)


def collection_layout_v60(connection):
    """Preserve fixture rows while restoring the exact v56–60 constraints."""
    if not connection.in_transaction:
        connection.execute("BEGIN")
    if connection.execute(
        "SELECT 1 FROM collection_session_steps WHERE kind='public_notice' OR ordinal>58"
    ).fetchone() or connection.execute(
        "SELECT 1 FROM collection_step_receipts WHERE public_notice_run_id IS NOT NULL"
    ).fetchone():
        raise ValueError("Fixture has schema61-only collection data")
    step_columns = ", ".join(COLLECTION_STEP_COLUMNS)
    receipt_columns = ", ".join(COLLECTION_RECEIPT_V60_COLUMNS)
    steps = connection.execute(f"SELECT rowid, {step_columns} FROM collection_session_steps ORDER BY rowid").fetchall()
    receipts = connection.execute(f"SELECT rowid, {receipt_columns} FROM collection_step_receipts ORDER BY rowid").fetchall()
    connection.execute("DROP TABLE collection_step_receipts")
    connection.execute("UPDATE collection_session_steps SET depends_on_step_id=NULL")
    connection.execute("DROP TABLE collection_session_steps")
    connection.execute(COLLECTION_HISTORY_V60_DDL[1])
    connection.execute(COLLECTION_HISTORY_V60_DDL[2])
    for row in steps:
        connection.execute(f"INSERT INTO collection_session_steps (rowid, {step_columns}) VALUES ({','.join('?' for _ in row)})", row)
    for row in receipts:
        connection.execute(f"INSERT INTO collection_step_receipts (rowid, {receipt_columns}) VALUES ({','.join('?' for _ in row)})", row)
    for statement in COLLECTION_HISTORY_V60_DDL[5:]:
        connection.execute(statement)
