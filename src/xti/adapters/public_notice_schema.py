"""Additive schema60 catalog tables; no source data or implicit backfill."""


PUBLIC_NOTICE_DDL = (
    "CREATE TABLE public_notice_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "status TEXT NOT NULL CHECK (status IN ('complete', 'failed')), "
    "started_at TEXT NOT NULL, finished_at TEXT NOT NULL, fetched_at TEXT, "
    "content_sha256 TEXT, snapshot_sha256 TEXT, notice_count INTEGER NOT NULL CHECK (notice_count BETWEEN 0 AND 10000), "
    "added_count INTEGER NOT NULL CHECK (added_count BETWEEN 0 AND 10000), "
    "updated_count INTEGER NOT NULL CHECK (updated_count BETWEEN 0 AND 10000), "
    "unchanged_count INTEGER NOT NULL CHECK (unchanged_count BETWEEN 0 AND 10000), "
    "removed_count INTEGER NOT NULL CHECK (removed_count BETWEEN 0 AND 10000), "
    "error TEXT, chain_sha256 TEXT NOT NULL, CHECK ("
    "(status='failed' AND fetched_at IS NULL AND content_sha256 IS NULL AND snapshot_sha256 IS NULL "
    "AND error IS NOT NULL AND notice_count=0 AND added_count=0 AND updated_count=0 AND unchanged_count=0 AND removed_count=0) OR "
    "(status='complete' AND fetched_at IS NOT NULL AND content_sha256 IS NOT NULL AND snapshot_sha256 IS NOT NULL "
    "AND error IS NULL AND notice_count>0 AND notice_count=added_count+updated_count+unchanged_count)))",
    "CREATE TABLE public_notice_changes ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "
    "run_id TEXT NOT NULL REFERENCES public_notice_runs(id) ON DELETE RESTRICT, "
    "notice_id TEXT NOT NULL, action TEXT NOT NULL CHECK (action IN ('added', 'updated', 'removed')), "
    "record_json TEXT NOT NULL, state_sha256 TEXT NOT NULL, UNIQUE(run_id,notice_id))",
    "CREATE INDEX public_notice_changes_run_sequence ON public_notice_changes(run_id,sequence)",
    "CREATE INDEX public_notice_changes_notice_sequence ON public_notice_changes(notice_id,sequence)",
)
