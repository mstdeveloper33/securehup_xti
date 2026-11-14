"""Remove only empty schema62 tables when constructing genuine old fixtures."""


def remove_public_notice_watch_schema(connection):
    """Preserve legacy data and refuse to hide populated new-feature fixtures."""
    tables = (
        "public_notice_watch_notifications",
        "public_notice_watch_runs",
        "public_notice_watch_events",
        "public_notice_watches",
    )
    existing = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'"
    )}
    for table in tables:
        if table in existing and connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
            raise ValueError("Fixture has schema62-only public notice watch data")
    for table in tables:
        if table in existing:
            connection.execute(f"DROP TABLE {table}")
