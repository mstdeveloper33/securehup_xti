"""Build schema65 fixtures without discarding any publisher news evidence."""


def remove_news_schema(connection):
    from tests.mentions_legacy_fixture import remove_mentions_schema
    tables = ("news_articles", "news_runs", "news_snapshots")
    existing = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'"
    )}
    for table in tables:
        if table in existing and connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
            raise ValueError("Fixture has schema66-only publisher news data")
    remove_mentions_schema(connection)
    for table in tables:
        if table in existing:
            connection.execute(f"DROP TABLE {table}")
