"""Build schema66 fixtures without discarding company search evidence."""


def remove_mentions_schema(connection):
    exists = connection.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='mentions_runs'").fetchone()
    if exists:
        if connection.execute("SELECT 1 FROM mentions_runs LIMIT 1").fetchone():
            raise ValueError("Fixture has schema67-only content search data")
    from tests.mention_groups_legacy_fixture import remove_mention_group_schema
    remove_mention_group_schema(connection)
    if exists:
        connection.execute("DROP TABLE mentions_runs")
