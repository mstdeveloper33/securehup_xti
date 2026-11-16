"""Schema metadata for authorized Nmap target scopes and immutable plans."""

NMAP_MANAGEMENT_DDL = (
    "CREATE TABLE surface_nmap_target_scopes ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES surface_scopes(asset_id) ON DELETE RESTRICT, "
    "name_key TEXT NOT NULL, display_name TEXT NOT NULL, "
    "revision INTEGER NOT NULL CHECK (revision > 0), "
    "definition_json TEXT NOT NULL, definition_sha256 TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "authorization_reason TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE (asset_id, name_key), UNIQUE (id, asset_id))",
    "CREATE TABLE surface_nmap_target_scope_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "target_scope_id TEXT NOT NULL REFERENCES surface_nmap_target_scopes(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'updated', 'reactivated', 'revoked')), "
    "revision INTEGER NOT NULL CHECK (revision > 0), display_name TEXT NOT NULL, "
    "definition_json TEXT NOT NULL, definition_sha256 TEXT NOT NULL, "
    "reason TEXT NOT NULL, recorded_at TEXT NOT NULL, "
    "UNIQUE (target_scope_id, revision))",
    "CREATE TABLE surface_nmap_plans ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "asset_id TEXT NOT NULL, target_scope_id TEXT NOT NULL, "
    "target_scope_revision INTEGER NOT NULL CHECK (target_scope_revision > 0), "
    "target_definition_sha256 TEXT NOT NULL, definition_json TEXT NOT NULL, "
    "plan_sha256 TEXT NOT NULL, created_at TEXT NOT NULL, "
    "UNIQUE (asset_id, plan_sha256), "
    "FOREIGN KEY (target_scope_id, asset_id) "
    "REFERENCES surface_nmap_target_scopes(id, asset_id) ON DELETE RESTRICT, "
    "FOREIGN KEY (target_scope_id, target_scope_revision) "
    "REFERENCES surface_nmap_target_scope_events(target_scope_id, revision) ON DELETE RESTRICT)",
    "CREATE INDEX surface_nmap_target_scopes_asset_active_name ON "
    "surface_nmap_target_scopes(asset_id, active, name_key)",
    "CREATE INDEX surface_nmap_target_scope_events_scope_sequence ON "
    "surface_nmap_target_scope_events(target_scope_id, sequence)",
    "CREATE INDEX surface_nmap_plans_asset_sequence ON surface_nmap_plans(asset_id, sequence)",
    "CREATE INDEX surface_nmap_plans_scope_sequence ON "
    "surface_nmap_plans(target_scope_id, sequence)",
)

TABLES = {
    "surface_nmap_target_scopes": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("name_key", "TEXT", 1, 0), ("display_name", "TEXT", 1, 0),
        ("revision", "INTEGER", 1, 0), ("definition_json", "TEXT", 1, 0),
        ("definition_sha256", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("authorization_reason", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "surface_nmap_target_scope_events": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("target_scope_id", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("revision", "INTEGER", 1, 0), ("display_name", "TEXT", 1, 0),
        ("definition_json", "TEXT", 1, 0), ("definition_sha256", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "surface_nmap_plans": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("asset_id", "TEXT", 1, 0), ("target_scope_id", "TEXT", 1, 0),
        ("target_scope_revision", "INTEGER", 1, 0),
        ("target_definition_sha256", "TEXT", 1, 0),
        ("definition_json", "TEXT", 1, 0), ("plan_sha256", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0),
    ],
}

UNIQUE_KEYS = {
    "surface_nmap_target_scopes": {
        ("id",), ("asset_id", "name_key"), ("id", "asset_id"),
    },
    "surface_nmap_target_scope_events": {
        ("id",), ("target_scope_id", "revision"),
    },
    "surface_nmap_plans": {("id",), ("asset_id", "plan_sha256")},
}

INDEXES = {
    "surface_nmap_target_scopes_asset_active_name": (
        "surface_nmap_target_scopes", ("asset_id", "active", "name_key"),
    ),
    "surface_nmap_target_scope_events_scope_sequence": (
        "surface_nmap_target_scope_events", ("target_scope_id", "sequence"),
    ),
    "surface_nmap_plans_asset_sequence": (
        "surface_nmap_plans", ("asset_id", "sequence"),
    ),
    "surface_nmap_plans_scope_sequence": (
        "surface_nmap_plans", ("target_scope_id", "sequence"),
    ),
}

FOREIGN_KEYS = {
    "surface_nmap_target_scopes": {
        ("surface_scopes", "asset_id", "asset_id", "NO ACTION", "RESTRICT"),
    },
    "surface_nmap_target_scope_events": {
        ("surface_nmap_target_scopes", "target_scope_id", "id", "NO ACTION", "RESTRICT"),
    },
    "surface_nmap_plans": {
        ("surface_nmap_target_scopes", "target_scope_id", "id", "NO ACTION", "RESTRICT"),
        ("surface_nmap_target_scopes", "asset_id", "asset_id", "NO ACTION", "RESTRICT"),
        (
            "surface_nmap_target_scope_events", "target_scope_id", "target_scope_id",
            "NO ACTION", "RESTRICT",
        ),
        (
            "surface_nmap_target_scope_events", "target_scope_revision", "revision",
            "NO ACTION", "RESTRICT",
        ),
    },
}
