"""Schema66: immutable publisher feed runs and retained article evidence."""


NEWS_DDL = (
    "CREATE TABLE news_snapshots ("
    "sha256 TEXT PRIMARY KEY NOT NULL CHECK (length(sha256)=64), "
    "source_key TEXT NOT NULL CHECK (source_key IN ('cisa','ncsc','cert-fr')), "
    "payload_json TEXT NOT NULL)",
    "CREATE TABLE news_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "source_key TEXT NOT NULL CHECK (source_key IN ('cisa','ncsc','cert-fr')), "
    "status TEXT NOT NULL CHECK (status IN ('complete','failed')), "
    "started_at TEXT NOT NULL, finished_at TEXT NOT NULL, fetched_at TEXT, "
    "content_sha256 TEXT CHECK (content_sha256 IS NULL OR length(content_sha256)=64), "
    "snapshot_sha256 TEXT REFERENCES news_snapshots(sha256) ON DELETE RESTRICT, "
    "article_count INTEGER NOT NULL CHECK (article_count>=0), "
    "added_count INTEGER NOT NULL CHECK (added_count>=0), "
    "updated_count INTEGER NOT NULL CHECK (updated_count>=0), "
    "unchanged_count INTEGER NOT NULL CHECK (unchanged_count>=0), "
    "error TEXT, chain_sha256 TEXT NOT NULL CHECK (length(chain_sha256)=64), "
    "CHECK (article_count=added_count+updated_count+unchanged_count), "
    "CHECK ((status='complete' AND fetched_at IS NOT NULL AND content_sha256 IS NOT NULL "
    "AND snapshot_sha256 IS NOT NULL AND error IS NULL) OR "
    "(status='failed' AND fetched_at IS NULL AND content_sha256 IS NULL "
    "AND snapshot_sha256 IS NULL AND article_count=0 AND error IS NOT NULL)))",
    "CREATE TABLE news_articles ("
    "id TEXT PRIMARY KEY NOT NULL CHECK (length(id)=64), "
    "source_key TEXT NOT NULL CHECK (source_key IN ('cisa','ncsc','cert-fr')), "
    "record_json TEXT NOT NULL, state_sha256 TEXT NOT NULL CHECK (length(state_sha256)=64), "
    "first_run_id TEXT NOT NULL REFERENCES news_runs(id) ON DELETE RESTRICT, "
    "last_change_run_id TEXT NOT NULL REFERENCES news_runs(id) ON DELETE RESTRICT, "
    "last_seen_run_id TEXT NOT NULL REFERENCES news_runs(id) ON DELETE RESTRICT, "
    "first_seen_at TEXT NOT NULL, last_changed_at TEXT NOT NULL, last_seen_at TEXT NOT NULL)",
    "CREATE INDEX news_runs_source_sequence ON news_runs(source_key,sequence)",
    "CREATE INDEX news_articles_source_id ON news_articles(source_key,id)",
)
