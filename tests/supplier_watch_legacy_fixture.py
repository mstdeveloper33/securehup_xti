"""Remove only empty schema64 tables when constructing genuine old fixtures."""


def remove_supplier_watch_schema(connection):
    tables = (
        "supplier_watch_notifications", "supplier_watch_runs",
        "supplier_watch_events", "supplier_watches",
    )
    existing = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'"
    )}
    for table in tables:
        if table in existing and connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
            raise ValueError("Fixture has schema64-only supplier watch data")
    for table in tables:
        if table in existing:
            connection.execute(f"DROP TABLE {table}")
