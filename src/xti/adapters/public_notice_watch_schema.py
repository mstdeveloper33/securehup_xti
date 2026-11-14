"""Schema62: explicit organization watches and their local inbox evidence."""


PUBLIC_NOTICE_WATCH_DDL = (
    "CREATE TABLE public_notice_watches ("
    "id TEXT PRIMARY KEY NOT NULL, organization_id TEXT NOT NULL UNIQUE "
    "REFERENCES organizations(id) ON DELETE RESTRICT, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "revision INTEGER NOT NULL CHECK (revision > 0), "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE public_notice_watch_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "watch_id TEXT NOT NULL REFERENCES public_notice_watches(id) ON DELETE RESTRICT, "
    "organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('enabled', 'disabled')), "
    "revision INTEGER NOT NULL CHECK (revision > 0), reason TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL, UNIQUE (watch_id, revision))",
    "CREATE TABLE public_notice_watch_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "watch_id TEXT NOT NULL REFERENCES public_notice_watches(id) ON DELETE RESTRICT, "
    "organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT, "
    "source_run_id TEXT NOT NULL REFERENCES public_notice_runs(id) ON DELETE RESTRICT, "
    "watch_event_id TEXT NOT NULL REFERENCES public_notice_watch_events(id) ON DELETE RESTRICT, "
    "previous_run_id TEXT REFERENCES public_notice_watch_runs(id) ON DELETE RESTRICT, "
    "recorded_at TEXT NOT NULL, scope_json TEXT NOT NULL, scope_sha256 TEXT NOT NULL, "
    "result_sha256 TEXT NOT NULL, matched_count INTEGER NOT NULL CHECK (matched_count BETWEEN 0 AND 10000), "
    "baseline_count INTEGER NOT NULL CHECK (baseline_count BETWEEN 0 AND 10000), "
    "added_count INTEGER NOT NULL CHECK (added_count BETWEEN 0 AND 10000), "
    "updated_count INTEGER NOT NULL CHECK (updated_count BETWEEN 0 AND 10000), "
    "removed_count INTEGER NOT NULL CHECK (removed_count BETWEEN 0 AND 10000), "
    "unchanged_count INTEGER NOT NULL CHECK (unchanged_count BETWEEN 0 AND 10000), "
    "UNIQUE (watch_id, source_run_id), "
    "CHECK (matched_count = baseline_count + added_count + updated_count + unchanged_count))",
    "CREATE TABLE public_notice_watch_notifications ("
    "sequence INTEGER PRIMARY KEY NOT NULL CHECK (sequence > 0), id TEXT NOT NULL UNIQUE, "
    "run_id TEXT NOT NULL UNIQUE REFERENCES public_notice_watch_runs(id) ON DELETE RESTRICT, "
    "watch_id TEXT NOT NULL REFERENCES public_notice_watches(id) ON DELETE RESTRICT, "
    "organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT, "
    "event_type TEXT NOT NULL CHECK (event_type = 'public_notice_watch_changed'), "
    "origin TEXT NOT NULL CHECK (origin = 'new'), created_at TEXT NOT NULL, read_at TEXT)",
    "CREATE INDEX public_notice_watches_active_organization ON "
    "public_notice_watches(active, organization_id)",
    "CREATE INDEX public_notice_watch_events_watch_sequence ON "
    "public_notice_watch_events(watch_id, sequence)",
    "CREATE INDEX public_notice_watch_runs_watch_sequence ON "
    "public_notice_watch_runs(watch_id, sequence)",
    "CREATE INDEX public_notice_watch_notifications_read_sequence ON "
    "public_notice_watch_notifications(read_at, sequence)",
)
