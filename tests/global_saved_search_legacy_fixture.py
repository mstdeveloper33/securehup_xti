"""Remove only empty schema65 tables when building genuine older fixtures."""


def remove_global_saved_search_schema(connection):
    from tests.news_legacy_fixture import remove_news_schema
    tables = (
        "global_saved_search_notifications", "global_saved_search_runs",
        "global_search_snapshots", "global_saved_search_events", "global_saved_searches",
    )
    existing = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'"
    )}
    for table in tables:
        if table in existing and connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
            raise ValueError("Fixture has schema65-only saved general search data")
    remove_news_schema(connection)
    for table in tables:
        if table in existing:
            connection.execute(f"DROP TABLE {table}")
