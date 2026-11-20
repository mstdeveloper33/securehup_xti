"""Explicit, versioned SQLite layout; no automatic migrations on reads."""

import sqlite3
from uuid import uuid4

from xti.adapters.case_public_notice_schema import (
    CASE_EVIDENCE_DDL, CASE_EVIDENCE_V62_DDL, migrate_case_public_notice_schema,
)
from xti.adapters.public_notice_schema import PUBLIC_NOTICE_DDL
from xti.adapters.public_notice_watch_schema import PUBLIC_NOTICE_WATCH_DDL
from xti.adapters.supplier_watch_schema import SUPPLIER_WATCH_DDL
from xti.adapters import supplier_watch_schema_metadata
from xti.adapters.global_saved_search_schema import (
    GLOBAL_SAVED_SEARCH_DDL, GLOBAL_SAVED_SEARCH_CURRENT_DDL, upgrade_global_saved_search_scopes,
)
from xti.adapters import global_saved_search_schema_metadata
from xti.adapters.news_schema import NEWS_DDL
from xti.adapters import news_schema_metadata
from xti.adapters.mentions_schema import MENTIONS_DDL
from xti.adapters import mentions_schema_metadata
from xti.adapters.mention_group_schema import MENTION_GROUP_DDL
from xti.adapters import mention_group_schema_metadata
from xti.adapters import nmap_management_schema as nmap_management_schema_metadata
from xti.adapters import nmap_jobs_schema
from xti.adapters import warninglist_schema
from xti.adapters import enrichment_schema
from xti.adapters import research_history_schema
from xti.adapters import investigation_schema
from xti.adapters import report_schema, evidence_schema, document_storage_schema, relationship_notification_schema, social_discovery_schema
from xti.adapters import social_enrichment_schema, social_tracking_schema, group_schema, group_operations_schema
from xti.adapters.collection_public_notice_schema import (
    COLLECTION_HISTORY_V60_DDL,
    COLLECTION_RECEIPT_V60_COLUMNS, migrate_collection_public_notice_schema,
)

from xti.adapters.collection_news_schema import (
    COLLECTION_HISTORY_V68_DDL, COLLECTION_RECEIPT_V68_COLUMNS,
    migrate_collection_news_schema,
)
from xti.adapters.collection_social_schema import (
    COLLECTION_HISTORY_DDL, COLLECTION_HISTORY_V84_DDL, COLLECTION_RECEIPT_V84_COLUMNS,
)


# 85 gates social profile recipes and lossless discovery-body archives.
# 86 adds immutable research groups and frozen group case evidence.
# 87 adds atomic group notifications and lossless archived group bodies.
SCHEMA_VERSION = 87
NMAP_MANAGEMENT_DDL = nmap_management_schema_metadata.NMAP_MANAGEMENT_DDL

ATTACK_CATALOG_DDL = ('CREATE TABLE attack_catalog_runs (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, version TEXT NOT NULL, source_url TEXT NOT NULL, content_sha256 TEXT NOT NULL, source_object_count INTEGER NOT NULL CHECK (source_object_count BETWEEN 1 AND 30000), fetched_at TEXT NOT NULL, recorded_at TEXT NOT NULL, entity_count INTEGER NOT NULL CHECK (entity_count >= 0), relationship_count INTEGER NOT NULL CHECK (relationship_count >= 0), phase_count INTEGER NOT NULL CHECK (phase_count >= 0), added_count INTEGER NOT NULL CHECK (added_count >= 0), updated_count INTEGER NOT NULL CHECK (updated_count >= 0), reactivated_count INTEGER NOT NULL CHECK (reactivated_count >= 0), revoked_count INTEGER NOT NULL CHECK (revoked_count >= 0), unchanged_count INTEGER NOT NULL CHECK (unchanged_count >= 0), chain_sha256 TEXT NOT NULL)', 'CREATE TABLE attack_catalog_entities (stix_id TEXT PRIMARY KEY NOT NULL, external_id TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL, state_sha256 TEXT NOT NULL, active INTEGER NOT NULL CHECK (active IN (0,1)), first_run_id TEXT NOT NULL REFERENCES attack_catalog_runs(id) ON DELETE RESTRICT, last_run_id TEXT NOT NULL REFERENCES attack_catalog_runs(id) ON DELETE RESTRICT)', 'CREATE TABLE attack_catalog_relationships (stix_id TEXT PRIMARY KEY NOT NULL, source_stix_id TEXT NOT NULL REFERENCES attack_catalog_entities(stix_id) ON DELETE RESTRICT, target_stix_id TEXT NOT NULL REFERENCES attack_catalog_entities(stix_id) ON DELETE RESTRICT, relationship_type TEXT NOT NULL, record_json TEXT NOT NULL, state_sha256 TEXT NOT NULL, active INTEGER NOT NULL CHECK (active IN (0,1)), first_run_id TEXT NOT NULL REFERENCES attack_catalog_runs(id) ON DELETE RESTRICT, last_run_id TEXT NOT NULL REFERENCES attack_catalog_runs(id) ON DELETE RESTRICT)', 'CREATE TABLE attack_catalog_phases (id TEXT PRIMARY KEY NOT NULL, technique_stix_id TEXT NOT NULL REFERENCES attack_catalog_entities(stix_id) ON DELETE RESTRICT, tactic_stix_id TEXT NOT NULL REFERENCES attack_catalog_entities(stix_id) ON DELETE RESTRICT, record_json TEXT NOT NULL, state_sha256 TEXT NOT NULL, active INTEGER NOT NULL CHECK (active IN (0,1)), first_run_id TEXT NOT NULL REFERENCES attack_catalog_runs(id) ON DELETE RESTRICT, last_run_id TEXT NOT NULL REFERENCES attack_catalog_runs(id) ON DELETE RESTRICT, UNIQUE(technique_stix_id,tactic_stix_id))', "CREATE TABLE attack_catalog_changes (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, run_id TEXT NOT NULL REFERENCES attack_catalog_runs(id) ON DELETE RESTRICT, record_kind TEXT NOT NULL CHECK (record_kind IN ('entity','relationship','phase')), record_key TEXT NOT NULL, action TEXT NOT NULL CHECK (action IN ('added','updated','reactivated','revoked')), record_json TEXT NOT NULL, state_sha256 TEXT NOT NULL, UNIQUE(run_id,record_kind,record_key))", 'CREATE INDEX attack_catalog_entities_active_external ON attack_catalog_entities(active,external_id)', 'CREATE INDEX attack_catalog_relationships_source ON attack_catalog_relationships(source_stix_id,active)', 'CREATE INDEX attack_catalog_relationships_target ON attack_catalog_relationships(target_stix_id,active)', 'CREATE INDEX attack_catalog_changes_record_sequence ON attack_catalog_changes(record_kind,record_key,sequence)', 'CREATE INDEX attack_catalog_changes_run_sequence ON attack_catalog_changes(run_id,sequence)')
APPLICATION_ID = 0x58544901


ORGANIZATION_DDL = (
    "CREATE TABLE organizations (id TEXT PRIMARY KEY NOT NULL, name_key TEXT NOT NULL UNIQUE, "
    "display_name TEXT NOT NULL, revision INTEGER NOT NULL CHECK (revision > 0), "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE organization_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "
    "id TEXT NOT NULL UNIQUE, organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'renamed', 'reactivated', 'revoked')), "
    "revision INTEGER NOT NULL CHECK (revision > 0), name_key TEXT NOT NULL, display_name TEXT NOT NULL, "
    "reason TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE (organization_id, revision))",
    "CREATE TABLE organization_links (id TEXT PRIMARY KEY NOT NULL, "
    "organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT, "
    "target_kind TEXT NOT NULL CHECK (target_kind IN ('domain', 'username-watch', 'ransomware-watch', 'ransomlook-watch')), "
    "target_value TEXT NOT NULL, asset_id TEXT REFERENCES assets(id) ON DELETE RESTRICT, "
    "username_watch_id TEXT REFERENCES brand_username_watches(id) ON DELETE RESTRICT, "
    "ransomware_watch_id TEXT REFERENCES ransomware_watches(id) ON DELETE RESTRICT, "
    "ransomlook_watch_id TEXT REFERENCES ransomlook_watches(id) ON DELETE RESTRICT, "
    "revision INTEGER NOT NULL CHECK (revision > 0), active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "reason TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE (organization_id, target_kind, target_value), CHECK ("
    "(target_kind='domain' AND asset_id IS NOT NULL AND username_watch_id IS NULL AND ransomware_watch_id IS NULL AND ransomlook_watch_id IS NULL) OR "
    "(target_kind='username-watch' AND asset_id IS NULL AND username_watch_id=target_value AND username_watch_id IS NOT NULL AND ransomware_watch_id IS NULL AND ransomlook_watch_id IS NULL) OR "
    "(target_kind='ransomware-watch' AND asset_id IS NULL AND username_watch_id IS NULL AND ransomware_watch_id=target_value AND ransomware_watch_id IS NOT NULL AND ransomlook_watch_id IS NULL) OR "
    "(target_kind='ransomlook-watch' AND asset_id IS NULL AND username_watch_id IS NULL AND ransomware_watch_id IS NULL AND ransomlook_watch_id=target_value AND ransomlook_watch_id IS NOT NULL)))",
    "CREATE TABLE organization_link_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "
    "id TEXT NOT NULL UNIQUE, link_id TEXT NOT NULL REFERENCES organization_links(id) ON DELETE RESTRICT, "
    "organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('linked', 'updated', 'reactivated', 'revoked')), "
    "revision INTEGER NOT NULL CHECK (revision > 0), target_kind TEXT NOT NULL CHECK "
    "(target_kind IN ('domain', 'username-watch', 'ransomware-watch', 'ransomlook-watch')), "
    "target_value TEXT NOT NULL, reason TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE (link_id, revision))",
    "CREATE INDEX organizations_active_name ON organizations(active, name_key)",
    "CREATE INDEX organization_events_organization_sequence ON organization_events(organization_id, sequence)",
    "CREATE INDEX organization_links_organization_active_target ON organization_links(organization_id, active, target_kind, target_value)",
    "CREATE INDEX organization_link_events_link_sequence ON organization_link_events(link_id, sequence)",
)


RANSOMLOOK_NOTIFICATION_DDL = (
    "CREATE TABLE ransomlook_watch_notifications ("
    "sequence INTEGER PRIMARY KEY NOT NULL CHECK (sequence > 0), id TEXT NOT NULL UNIQUE, "
    "run_id TEXT NOT NULL UNIQUE REFERENCES ransomlook_watch_runs(id) ON DELETE RESTRICT, "
    "watch_id TEXT NOT NULL REFERENCES ransomlook_watches(id) ON DELETE RESTRICT, "
    "event_type TEXT NOT NULL CHECK (event_type = 'ransomlook_watch_changed'), "
    "origin TEXT NOT NULL CHECK (origin = 'new'), created_at TEXT NOT NULL, read_at TEXT)",
    "CREATE INDEX ransomlook_watch_notifications_read_sequence ON "
    "ransomlook_watch_notifications(read_at, sequence)",
)


class SchemaError(ValueError):
    """A database is not a supported XTI layout."""


ASSETS_DDL = (
    "CREATE TABLE assets (id TEXT PRIMARY KEY NOT NULL, "
    "value TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)"
)

COLLECTION_PROFILE_DDL = (
    "CREATE TABLE collection_profiles ("
    "id TEXT PRIMARY KEY NOT NULL, name_key TEXT NOT NULL UNIQUE, "
    "display_name TEXT NOT NULL, revision INTEGER NOT NULL CHECK (revision > 0), "
    "definition_json TEXT NOT NULL, definition_sha256 TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL)",
    "CREATE TABLE collection_profile_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "profile_id TEXT NOT NULL REFERENCES collection_profiles(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'updated', 'reactivated', 'revoked')), "
    "revision INTEGER NOT NULL CHECK (revision > 0), display_name TEXT NOT NULL, "
    "definition_json TEXT NOT NULL, definition_sha256 TEXT NOT NULL, "
    "reason TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE (profile_id, revision))",
    "CREATE INDEX collection_profiles_active_name ON collection_profiles(active, name_key)",
    "CREATE INDEX collection_profile_events_profile_sequence ON "
    "collection_profile_events(profile_id, sequence)",
)

ASSET_CRITICALITY_DDL = (
    "CREATE TABLE asset_criticalities ("
    "asset_id TEXT PRIMARY KEY NOT NULL REFERENCES assets(id) ON DELETE RESTRICT, "
    "asset_value TEXT NOT NULL UNIQUE, level TEXT NOT NULL CHECK (level IN "
    "('low', 'medium', 'high', 'critical')), active INTEGER NOT NULL "
    "CHECK (active IN (0, 1)), reason TEXT NOT NULL, created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL)",
    "CREATE TABLE asset_criticality_events ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL REFERENCES "
    "asset_criticalities(asset_id) ON DELETE RESTRICT, action TEXT NOT NULL CHECK "
    "(action IN ('set', 'updated', 'reactivated', 'cleared')), level TEXT NOT NULL "
    "CHECK (level IN ('low', 'medium', 'high', 'critical')), reason TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL)",
    "CREATE INDEX asset_criticality_events_asset_id ON "
    "asset_criticality_events(asset_id, recorded_at)",
)

SUPPLIER_INVENTORY_DDL = (
    "CREATE TABLE suppliers ("
    "id TEXT PRIMARY KEY NOT NULL, name_key TEXT NOT NULL, display_name TEXT NOT NULL, "
    "primary_domain TEXT NOT NULL UNIQUE, relationship_type TEXT NOT NULL CHECK "
    "(relationship_type IN ('software', 'cloud', 'payment', 'communications', "
    "'professional_service', 'other')), criticality TEXT NOT NULL CHECK "
    "(criticality IN ('low', 'medium', 'high', 'critical')), active INTEGER NOT NULL "
    "CHECK (active IN (0, 1)), reason TEXT NOT NULL, created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL)",
    "CREATE TABLE supplier_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "supplier_id TEXT NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN "
    "('added', 'updated', 'reactivated', 'revoked')), display_name TEXT NOT NULL, "
    "primary_domain TEXT NOT NULL, relationship_type TEXT NOT NULL CHECK "
    "(relationship_type IN ('software', 'cloud', 'payment', 'communications', "
    "'professional_service', 'other')), criticality TEXT NOT NULL CHECK "
    "(criticality IN ('low', 'medium', 'high', 'critical')), reason TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL)",
    "CREATE INDEX suppliers_active_name ON suppliers(active, name_key, primary_domain)",
    "CREATE INDEX supplier_events_supplier_sequence ON "
    "supplier_events(supplier_id, sequence)",
)

SUPPLIER_CANDIDATE_DDL = (
    "CREATE TABLE supplier_candidates ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES assets(id) ON DELETE RESTRICT, asset_value TEXT NOT NULL, "
    "candidate_domain TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN "
    "('pending', 'accepted', 'uncertain', 'rejected')), current INTEGER NOT NULL "
    "CHECK (current IN (0, 1)), supplier_id TEXT REFERENCES suppliers(id) "
    "ON DELETE RESTRICT, resolution_reason TEXT, first_seen_at TEXT NOT NULL, "
    "last_seen_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(asset_id, candidate_domain), CHECK ((status = 'accepted' AND "
    "supplier_id IS NOT NULL AND resolution_reason IS NOT NULL) OR "
    "(status = 'pending' AND supplier_id IS NULL AND resolution_reason IS NULL) OR "
    "(status IN ('uncertain', 'rejected') AND supplier_id IS NULL AND "
    "resolution_reason IS NOT NULL)))",
    "CREATE TABLE supplier_candidate_evidence ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "candidate_id TEXT NOT NULL REFERENCES supplier_candidates(id) ON DELETE RESTRICT, "
    "source_evidence_id TEXT NOT NULL REFERENCES surface_cname_checks(id) "
    "ON DELETE RESTRICT, derivation_key TEXT NOT NULL UNIQUE, source_domain TEXT NOT NULL, "
    "target_domain TEXT NOT NULL, state_sha256 TEXT NOT NULL, "
    "public_suffix_version TEXT NOT NULL, public_suffix_sha256 TEXT NOT NULL, "
    "observed_at TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE TABLE supplier_candidate_resolution_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "candidate_id TEXT NOT NULL REFERENCES supplier_candidates(id) ON DELETE RESTRICT, "
    "decision TEXT NOT NULL CHECK (decision IN "
    "('pending', 'accepted', 'uncertain', 'rejected')), supplier_id TEXT "
    "REFERENCES suppliers(id) ON DELETE RESTRICT, reason TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL, CHECK ((decision = 'accepted' AND supplier_id IS NOT NULL) "
    "OR (decision != 'accepted' AND supplier_id IS NULL)))",
    "CREATE INDEX supplier_candidates_status_current ON "
    "supplier_candidates(status, current, asset_value, candidate_domain)",
    "CREATE INDEX supplier_candidate_evidence_candidate_sequence ON "
    "supplier_candidate_evidence(candidate_id, sequence)",
    "CREATE INDEX supplier_candidate_resolutions_candidate_sequence ON "
    "supplier_candidate_resolution_events(candidate_id, sequence)",
)

CASE_V62_DDL = (
    "CREATE TABLE cases ("
    "id TEXT PRIMARY KEY NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL, "
    "status TEXT NOT NULL CHECK (status IN "
    "('open', 'investigating', 'monitoring', 'resolved', 'closed')), "
    "priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')), "
    "resolution TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, closed_at TEXT, "
    "CHECK ((status IN ('resolved', 'closed') AND resolution IS NOT NULL) OR "
    "(status NOT IN ('resolved', 'closed') AND resolution IS NULL)), "
    "CHECK ((status = 'closed' AND closed_at IS NOT NULL) OR "
    "(status != 'closed' AND closed_at IS NULL)))",
    CASE_EVIDENCE_V62_DDL,
    "CREATE TABLE case_tasks ("
    "id TEXT PRIMARY KEY NOT NULL, case_id TEXT NOT NULL REFERENCES cases(id) "
    "ON DELETE RESTRICT, title TEXT NOT NULL, status TEXT NOT NULL CHECK "
    "(status IN ('open', 'done', 'cancelled')), due_at TEXT, reason TEXT NOT NULL, "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE case_activities ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT, "
    "activity_type TEXT NOT NULL CHECK (activity_type IN "
    "('case_created', 'case_updated', 'status_changed', 'note_added', "
    "'evidence_added', 'evidence_refreshed', 'evidence_reactivated', "
    "'evidence_removed', 'task_added', 'task_updated')), reference_id TEXT, "
    "summary TEXT NOT NULL, reason TEXT NOT NULL, snapshot_json TEXT NOT NULL, "
    "snapshot_sha256 TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX cases_status_priority_updated ON "
    "cases(status, priority, updated_at)",
    "CREATE INDEX case_evidence_case_active_updated ON "
    "case_evidence(case_id, active, updated_at)",
    "CREATE INDEX case_tasks_case_status_due ON "
    "case_tasks(case_id, status, due_at)",
    "CREATE INDEX case_activities_case_sequence ON "
    "case_activities(case_id, sequence)",
)

CASE_DDL = tuple(
    CASE_EVIDENCE_DDL if statement == CASE_EVIDENCE_V62_DDL else statement
    for statement in CASE_V62_DDL
)

FINDINGS_DDL = (
    "CREATE TABLE observations ("
    "id TEXT PRIMARY KEY NOT NULL, domain TEXT NOT NULL, raw_domain TEXT NOT NULL, "
    "source_name TEXT NOT NULL, source_sha256 TEXT NOT NULL, "
    "source_line INTEGER NOT NULL CHECK (source_line > 0), observed_at TEXT, "
    "ingested_at TEXT NOT NULL, UNIQUE(source_sha256, source_line))",
    "CREATE TABLE findings ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES assets(id) ON DELETE RESTRICT, asset_value TEXT NOT NULL, "
    "domain TEXT NOT NULL, rule_version TEXT NOT NULL, reasons TEXT NOT NULL, "
    "status TEXT NOT NULL CHECK (status IN ('new', 'suspicious', 'dismissed', 'uncertain')), "
    "created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, "
    "UNIQUE(asset_id, domain, rule_version))",
    "CREATE TABLE finding_observations ("
    "finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE RESTRICT, "
    "observation_id TEXT NOT NULL REFERENCES observations(id) ON DELETE RESTRICT, "
    "PRIMARY KEY(finding_id, observation_id))",
    "CREATE TABLE reviews ("
    "id TEXT PRIMARY KEY NOT NULL, finding_id TEXT NOT NULL "
    "REFERENCES findings(id) ON DELETE RESTRICT, "
    "decision TEXT NOT NULL CHECK (decision IN ('suspicious', 'dismissed', 'uncertain')), "
    "reason TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE INDEX findings_status ON findings(status)",
    "CREATE INDEX reviews_finding_id ON reviews(finding_id)",
    "CREATE INDEX finding_observations_observation_id "
    "ON finding_observations(observation_id)",
)

JOBS_DDL = (
    "CREATE TABLE scan_jobs ("
    "id TEXT PRIMARY KEY NOT NULL, targets TEXT NOT NULL, "
    "typos INTEGER NOT NULL CHECK (typos IN (0, 1)), provider TEXT NOT NULL, "
    "rule_version TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN "
    "('queued', 'running', 'complete', 'partial', 'failed', 'interrupted')), "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "attempt_count INTEGER NOT NULL CHECK (attempt_count >= 0))",
    "CREATE TABLE scan_attempts ("
    "id TEXT PRIMARY KEY NOT NULL, job_id TEXT NOT NULL REFERENCES scan_jobs(id) "
    "ON DELETE RESTRICT, number INTEGER NOT NULL CHECK (number > 0), "
    "status TEXT NOT NULL CHECK (status IN "
    "('running', 'complete', 'partial', 'failed', 'interrupted')), "
    "started_at TEXT NOT NULL, finished_at TEXT, progress TEXT, error TEXT, "
    "queries TEXT NOT NULL, result TEXT, UNIQUE(job_id, number))",
    "CREATE INDEX scan_jobs_status_created ON scan_jobs(status, created_at)",
)

ASSESSMENTS_DDL = (
    "CREATE TABLE finding_assessments ("
    "id TEXT PRIMARY KEY NOT NULL, finding_id TEXT NOT NULL "
    "REFERENCES findings(id) ON DELETE RESTRICT, result TEXT NOT NULL)",
    "CREATE INDEX finding_assessments_finding_id ON finding_assessments(finding_id)",
)

OPERATIONS_DDL = (
    "CREATE TABLE provider_cooldowns ("
    "provider TEXT PRIMARY KEY NOT NULL, not_before TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL, reason TEXT NOT NULL)",
    "CREATE TABLE cleanup_runs ("
    "id TEXT PRIMARY KEY NOT NULL, created_at TEXT NOT NULL, cutoff TEXT NOT NULL, "
    "deleted_count INTEGER NOT NULL CHECK (deleted_count > 0), "
    "token TEXT NOT NULL, backup TEXT NOT NULL)",
)

INBOX_DDL = (
    "CREATE TABLE notifications ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "
    "id TEXT NOT NULL UNIQUE, finding_id TEXT NOT NULL "
    "REFERENCES findings(id) ON DELETE RESTRICT, "
    "event_type TEXT NOT NULL CHECK (event_type = 'finding_created'), "
    "origin TEXT NOT NULL CHECK (origin IN ('new', 'existing')), "
    "created_at TEXT NOT NULL, read_at TEXT, UNIQUE(finding_id, event_type))",
    "CREATE INDEX notifications_read_sequence ON notifications(read_at, sequence)",
)

MONITOR_DDL = (
    "CREATE TABLE monitor_runs ("
    "id TEXT PRIMARY KEY NOT NULL, targets TEXT NOT NULL, providers TEXT NOT NULL, "
    "typos INTEGER NOT NULL CHECK (typos IN (0, 1)), rule_version TEXT NOT NULL, "
    "max_cycles INTEGER NOT NULL CHECK (max_cycles BETWEEN 1 AND 1000), "
    "interval_seconds INTEGER NOT NULL CHECK (interval_seconds BETWEEN 300 AND 86400), "
    "max_duration_seconds INTEGER NOT NULL CHECK (max_duration_seconds BETWEEN 1 AND 604800), "
    "status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'interrupted', 'failed')), "
    "started_at TEXT NOT NULL, finished_at TEXT, "
    "elapsed_seconds REAL CHECK (elapsed_seconds >= 0), "
    "stop_reason TEXT CHECK (stop_reason IN ('cycles', 'duration', 'cancelled', 'recovered', 'error')))",
    "CREATE TABLE monitor_jobs ("
    "run_id TEXT NOT NULL REFERENCES monitor_runs(id) ON DELETE RESTRICT, "
    "cycle INTEGER NOT NULL CHECK (cycle BETWEEN 1 AND 1000), provider TEXT NOT NULL, "
    "job_id TEXT NOT NULL UNIQUE REFERENCES scan_jobs(id) ON DELETE RESTRICT, "
    "PRIMARY KEY(run_id, cycle, provider))",
    "CREATE INDEX monitor_runs_status ON monitor_runs(status)",
)

ALLOWLIST_V8_DDL = (
    "CREATE TABLE allowlist_entries ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES assets(id) ON DELETE RESTRICT, asset_value TEXT NOT NULL, "
    "domain TEXT NOT NULL, active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "reason TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(asset_id, domain))",
    "CREATE TABLE allowlist_events ("
    "id TEXT PRIMARY KEY NOT NULL, entry_id TEXT NOT NULL "
    "REFERENCES allowlist_entries(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'reactivated', 'revoked')), "
    "reason TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE INDEX allowlist_active_asset_domain "
    "ON allowlist_entries(active, asset_id, domain)",
    "CREATE INDEX allowlist_events_entry_id ON allowlist_events(entry_id)",
)

ALLOWLIST_DDL = (
    "CREATE TABLE allowlist_entries ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES assets(id) ON DELETE RESTRICT, asset_value TEXT NOT NULL, "
    "domain TEXT NOT NULL, active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "expires_at TEXT, reason TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(asset_id, domain))",
    "CREATE TABLE allowlist_events ("
    "id TEXT PRIMARY KEY NOT NULL, entry_id TEXT NOT NULL "
    "REFERENCES allowlist_entries(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'reactivated', 'updated', 'revoked')), "
    "expires_at TEXT, reason TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE INDEX allowlist_active_asset_domain "
    "ON allowlist_entries(active, asset_id, domain)",
    "CREATE INDEX allowlist_events_entry_id ON allowlist_events(entry_id)",
)

SURFACE_DDL = (
    "CREATE TABLE surface_scopes ("
    "asset_id TEXT PRIMARY KEY NOT NULL REFERENCES assets(id) ON DELETE RESTRICT, "
    "asset_value TEXT NOT NULL UNIQUE, active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "reason TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE surface_scope_events ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES surface_scopes(asset_id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('approved', 'updated', 'reactivated', 'revoked')), "
    "reason TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE surface_checks ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES surface_scopes(asset_id) ON DELETE RESTRICT, result TEXT NOT NULL, "
    "state_sha256 TEXT NOT NULL, change TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX surface_scope_events_asset_id ON surface_scope_events(asset_id)",
    "CREATE INDEX surface_checks_asset_id ON surface_checks(asset_id)",
)

SURFACE_DISCOVERY_V50_DDL = (
    "CREATE TABLE surface_candidates ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES assets(id) ON DELETE RESTRICT, asset_value TEXT NOT NULL, "
    "domain TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN "
    "('pending', 'owned', 'rejected')), reason TEXT NOT NULL, "
    "first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(asset_id, domain))",
    "CREATE TABLE surface_candidate_sources ("
    "id TEXT PRIMARY KEY NOT NULL, candidate_id TEXT NOT NULL "
    "REFERENCES surface_candidates(id) ON DELETE RESTRICT, "
    "provider TEXT NOT NULL CHECK (provider = 'crt.sh'), source_name TEXT NOT NULL, "
    "source_sha256 TEXT NOT NULL, raw_domain TEXT NOT NULL, observed_at TEXT, "
    "recorded_at TEXT NOT NULL, UNIQUE(candidate_id, source_sha256))",
    "CREATE TABLE surface_candidate_events ("
    "id TEXT PRIMARY KEY NOT NULL, candidate_id TEXT NOT NULL "
    "REFERENCES surface_candidates(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN "
    "('discovered', 'owned', 'rejected', 'reopened', 'updated')), "
    "status TEXT NOT NULL CHECK (status IN ('pending', 'owned', 'rejected')), "
    "reason TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE INDEX surface_candidates_asset_status "
    "ON surface_candidates(asset_id, status, domain)",
    "CREATE INDEX surface_candidate_sources_candidate_id "
    "ON surface_candidate_sources(candidate_id)",
    "CREATE INDEX surface_candidate_events_candidate_id "
    "ON surface_candidate_events(candidate_id)",
)

SURFACE_DISCOVERY_DDL = (
    SURFACE_DISCOVERY_V50_DDL[0],
    SURFACE_DISCOVERY_V50_DDL[1].replace(
        "CHECK (provider = 'crt.sh')",
        "CHECK (provider IN ('crt.sh', 'theharvester'))",
    ),
    *SURFACE_DISCOVERY_V50_DDL[2:],
)

SURFACE_DISCOVERY_HISTORY_V50_DDL = (
    "CREATE TABLE surface_discovery_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE RESTRICT, "
    "asset_value TEXT NOT NULL, provider TEXT NOT NULL CHECK (provider = 'crt.sh'), "
    "status TEXT NOT NULL CHECK (status IN ('complete', 'partial', 'failed')), "
    "source_url TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT NOT NULL, "
    "record_count INTEGER NOT NULL CHECK (record_count >= 0), "
    "skipped_names INTEGER NOT NULL CHECK (skipped_names >= 0), "
    "ignored_names INTEGER NOT NULL CHECK (ignored_names >= 0), warnings TEXT NOT NULL, "
    "candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0), "
    "candidates_created INTEGER NOT NULL CHECK (candidates_created >= 0), "
    "candidates_existing INTEGER NOT NULL CHECK (candidates_existing >= 0), "
    "evidence_created INTEGER NOT NULL CHECK (evidence_created >= 0), "
    "evidence_existing INTEGER NOT NULL CHECK (evidence_existing >= 0), error TEXT, "
    "CHECK ((status = 'failed' AND error IS NOT NULL) OR "
    "(status != 'failed' AND error IS NULL)))",
    "CREATE TABLE surface_candidate_notifications ("
    "sequence INTEGER PRIMARY KEY NOT NULL CHECK (sequence > 0), "
    "id TEXT NOT NULL UNIQUE, candidate_id TEXT NOT NULL UNIQUE "
    "REFERENCES surface_candidates(id) ON DELETE RESTRICT, "
    "event_type TEXT NOT NULL CHECK (event_type = 'surface_candidate_discovered'), "
    "origin TEXT NOT NULL CHECK (origin = 'new'), created_at TEXT NOT NULL, read_at TEXT)",
    "CREATE INDEX surface_discovery_runs_asset_sequence "
    "ON surface_discovery_runs(asset_id, sequence)",
    "CREATE INDEX surface_candidate_notifications_read_sequence "
    "ON surface_candidate_notifications(read_at, sequence)",
)

SURFACE_DISCOVERY_HISTORY_DDL = (
    SURFACE_DISCOVERY_HISTORY_V50_DDL[0].replace(
        "CHECK (provider = 'crt.sh')",
        "CHECK (provider IN ('crt.sh', 'theharvester'))",
    ),
    *SURFACE_DISCOVERY_HISTORY_V50_DDL[1:],
)

SURFACE_MAIL_DDL = (
    "CREATE TABLE surface_mail_checks ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES surface_scopes(asset_id) ON DELETE RESTRICT, result TEXT NOT NULL, "
    "state_sha256 TEXT NOT NULL, change TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX surface_mail_checks_asset_id ON surface_mail_checks(asset_id)",
)

SURFACE_SERVICE_DDL = (
    "CREATE TABLE surface_service_checks ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES surface_scopes(asset_id) ON DELETE RESTRICT, "
    "authorization_reason TEXT NOT NULL, result TEXT NOT NULL, "
    "state_sha256 TEXT NOT NULL, change TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX surface_service_checks_asset_id ON surface_service_checks(asset_id)",
)

SURFACE_NMAP_DDL = (
    "CREATE TABLE surface_nmap_checks ("
    "id TEXT PRIMARY KEY NOT NULL, execution_id TEXT NOT NULL, "
    "asset_id TEXT NOT NULL REFERENCES surface_scopes(asset_id) ON DELETE RESTRICT, "
    "authorization_reason TEXT NOT NULL, result TEXT NOT NULL, "
    "state_sha256 TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX surface_nmap_checks_asset_id ON surface_nmap_checks(asset_id)",
    "CREATE INDEX surface_nmap_checks_execution_id ON surface_nmap_checks(execution_id)",
)

SURFACE_CNAME_DDL = (
    "CREATE TABLE surface_cname_checks ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES surface_scopes(asset_id) ON DELETE RESTRICT, result TEXT NOT NULL, "
    "state_sha256 TEXT NOT NULL, change TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX surface_cname_checks_asset_id ON surface_cname_checks(asset_id)",
)

SURFACE_CHANGE_NOTIFICATION_DDL = (
    "CREATE TABLE surface_change_notifications ("
    "sequence INTEGER PRIMARY KEY NOT NULL CHECK (sequence > 0), "
    "id TEXT NOT NULL UNIQUE, "
    "surface_check_id TEXT UNIQUE REFERENCES surface_checks(id) ON DELETE RESTRICT, "
    "mail_check_id TEXT UNIQUE REFERENCES surface_mail_checks(id) ON DELETE RESTRICT, "
    "service_check_id TEXT UNIQUE REFERENCES surface_service_checks(id) ON DELETE RESTRICT, "
    "event_type TEXT NOT NULL CHECK (event_type = 'surface_evidence_changed'), "
    "origin TEXT NOT NULL CHECK (origin = 'new'), created_at TEXT NOT NULL, read_at TEXT, "
    "CHECK ((surface_check_id IS NOT NULL) + (mail_check_id IS NOT NULL) + "
    "(service_check_id IS NOT NULL) = 1))",
    "CREATE INDEX surface_change_notifications_read_sequence "
    "ON surface_change_notifications(read_at, sequence)",
)

VULNERABILITY_DDL = (
    "CREATE TABLE vulnerability_source_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "source TEXT NOT NULL CHECK (source IN ('cisa_kev', 'first_epss', 'nvd_cve')), "
    "status TEXT NOT NULL CHECK (status IN ('complete', 'failed')), "
    "source_url TEXT NOT NULL, source_version TEXT, source_timestamp TEXT, "
    "content_sha256 TEXT, started_at TEXT NOT NULL, finished_at TEXT NOT NULL, "
    "record_count INTEGER NOT NULL CHECK (record_count >= 0), "
    "created_count INTEGER NOT NULL CHECK (created_count >= 0), "
    "updated_count INTEGER NOT NULL CHECK (updated_count >= 0), "
    "unchanged_count INTEGER NOT NULL CHECK (unchanged_count >= 0), "
    "deactivated_count INTEGER NOT NULL CHECK (deactivated_count >= 0), "
    "reactivated_count INTEGER NOT NULL CHECK (reactivated_count >= 0), error TEXT, "
    "CHECK ((status = 'complete' AND source_version IS NOT NULL AND "
    "source_timestamp IS NOT NULL AND content_sha256 IS NOT NULL AND error IS NULL) OR "
    "(status = 'failed' AND source_version IS NULL AND source_timestamp IS NULL AND "
    "content_sha256 IS NULL AND error IS NOT NULL)))",
    "CREATE TABLE kev_entries ("
    "cve_id TEXT PRIMARY KEY NOT NULL, state TEXT NOT NULL, state_sha256 TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), first_seen_at TEXT NOT NULL, "
    "last_seen_at TEXT NOT NULL, updated_at TEXT NOT NULL, latest_run_id TEXT NOT NULL "
    "REFERENCES vulnerability_source_runs(id) ON DELETE RESTRICT)",
    "CREATE TABLE kev_entry_events ("
    "id TEXT PRIMARY KEY NOT NULL, cve_id TEXT NOT NULL "
    "REFERENCES kev_entries(cve_id) ON DELETE RESTRICT, run_id TEXT NOT NULL "
    "REFERENCES vulnerability_source_runs(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN "
    "('added', 'updated', 'deactivated', 'reactivated')), state TEXT NOT NULL, "
    "state_sha256 TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE(cve_id, run_id))",
    "CREATE INDEX vulnerability_source_runs_source_sequence "
    "ON vulnerability_source_runs(source, sequence)",
    "CREATE INDEX kev_entries_active_cve ON kev_entries(active, cve_id)",
    "CREATE INDEX kev_entry_events_cve_id ON kev_entry_events(cve_id)",
)

EPSS_DDL = (
    "CREATE TABLE epss_scores ("
    "cve_id TEXT PRIMARY KEY NOT NULL, epss TEXT NOT NULL, percentile TEXT NOT NULL, "
    "state_sha256 TEXT NOT NULL, active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "model_version TEXT NOT NULL, score_date TEXT NOT NULL, first_seen_at TEXT NOT NULL, "
    "last_seen_at TEXT NOT NULL, updated_at TEXT NOT NULL, latest_run_id TEXT NOT NULL "
    "REFERENCES vulnerability_source_runs(id) ON DELETE RESTRICT)",
    "CREATE INDEX epss_scores_active_cve ON epss_scores(active, cve_id)",
)

NVD_DDL = (
    "CREATE TABLE nvd_cve_records ("
    "cve_id TEXT PRIMARY KEY NOT NULL, state TEXT NOT NULL, record_json TEXT NOT NULL, "
    "state_sha256 TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL, latest_run_id TEXT NOT NULL "
    "REFERENCES vulnerability_source_runs(id) ON DELETE RESTRICT)",
    "CREATE TABLE nvd_cve_events ("
    "id TEXT PRIMARY KEY NOT NULL, cve_id TEXT NOT NULL "
    "REFERENCES nvd_cve_records(cve_id) ON DELETE RESTRICT, run_id TEXT NOT NULL "
    "REFERENCES vulnerability_source_runs(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'updated')), state TEXT NOT NULL, "
    "record_json TEXT NOT NULL, state_sha256 TEXT NOT NULL, recorded_at TEXT NOT NULL, "
    "UNIQUE(cve_id, run_id))",
    "CREATE INDEX nvd_cve_events_cve_id ON nvd_cve_events(cve_id)",
)

NVD_WINDOW_DDL = (
    "CREATE TABLE nvd_window_syncs ("
    "id TEXT PRIMARY KEY NOT NULL, window_start TEXT NOT NULL, window_end TEXT NOT NULL, "
    "page_size INTEGER NOT NULL CHECK (page_size BETWEEN 1 AND 100), "
    "next_start_index INTEGER NOT NULL CHECK (next_start_index >= 0), "
    "total_results INTEGER CHECK (total_results >= 0), "
    "status TEXT NOT NULL CHECK (status IN ('ready', 'complete')), "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_success_at TEXT, "
    "last_error TEXT, latest_run_id TEXT REFERENCES vulnerability_source_runs(id) "
    "ON DELETE RESTRICT, UNIQUE(window_start, window_end, page_size), "
    "CHECK ((status = 'complete' AND total_results IS NOT NULL AND "
    "next_start_index >= total_results) OR (status = 'ready' AND "
    "(total_results IS NULL OR next_start_index < total_results))))",
    "CREATE INDEX nvd_window_syncs_status_updated ON "
    "nvd_window_syncs(status, updated_at)",
)

NVD_WINDOW_RESTART_DDL = (
    "CREATE TABLE nvd_window_restart_events ("
    "id TEXT PRIMARY KEY NOT NULL, sync_id TEXT NOT NULL REFERENCES "
    "nvd_window_syncs(id) ON DELETE RESTRICT, "
    "previous_next_start_index INTEGER NOT NULL CHECK (previous_next_start_index >= 0), "
    "previous_total_results INTEGER CHECK (previous_total_results >= 0), "
    "previous_status TEXT NOT NULL CHECK (previous_status IN ('ready', 'complete')), "
    "previous_last_success_at TEXT, previous_last_error TEXT, "
    "previous_latest_run_id TEXT REFERENCES vulnerability_source_runs(id) ON DELETE RESTRICT, "
    "reason TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX nvd_window_restart_events_sync_recorded ON "
    "nvd_window_restart_events(sync_id, recorded_at)",
)

PRODUCT_EVIDENCE_DDL = (
    "CREATE TABLE asset_products ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES assets(id) ON DELETE RESTRICT, asset_value TEXT NOT NULL, "
    "part TEXT NOT NULL CHECK (part IN ('a', 'o', 'h')), vendor TEXT NOT NULL, "
    "product TEXT NOT NULL, version TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), evidence_type TEXT NOT NULL, "
    "evidence TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(asset_id, part, vendor, product, version))",
    "CREATE TABLE asset_product_events ("
    "id TEXT PRIMARY KEY NOT NULL, asset_product_id TEXT NOT NULL "
    "REFERENCES asset_products(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'updated', 'reactivated', 'revoked')), "
    "evidence_type TEXT NOT NULL, evidence TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX asset_products_active_asset ON "
    "asset_products(active, asset_id, part, vendor, product, version)",
    "CREATE INDEX asset_product_events_product_id ON "
    "asset_product_events(asset_product_id, recorded_at)",
)

PACKAGE_EVIDENCE_DDL = (
    "CREATE TABLE asset_packages ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES assets(id) ON DELETE RESTRICT, asset_value TEXT NOT NULL, "
    "provider TEXT NOT NULL CHECK (provider = 'redhat'), "
    "ecosystem TEXT NOT NULL CHECK (ecosystem = 'rpm'), name TEXT NOT NULL, "
    "epoch INTEGER NOT NULL CHECK (epoch BETWEEN 0 AND 2147483647), "
    "version TEXT NOT NULL, release TEXT NOT NULL, architecture TEXT NOT NULL, "
    "source_rpm TEXT, distribution_cpe TEXT NOT NULL, purl TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), evidence_type TEXT NOT NULL "
    "CHECK (evidence_type = 'user_verified'), evidence TEXT NOT NULL, "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(asset_id, provider, ecosystem, name, epoch, version, release, architecture, "
    "distribution_cpe))",
    "CREATE TABLE asset_package_events ("
    "id TEXT PRIMARY KEY NOT NULL, asset_package_id TEXT NOT NULL "
    "REFERENCES asset_packages(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'updated', 'reactivated', 'revoked')), "
    "source_rpm TEXT, evidence_type TEXT NOT NULL CHECK (evidence_type = 'user_verified'), "
    "evidence TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX asset_packages_active_asset ON "
    "asset_packages(active, asset_id, provider, name, architecture)",
    "CREATE INDEX asset_package_events_package_id ON "
    "asset_package_events(asset_package_id, recorded_at)",
)

UBUNTU_PACKAGE_EVIDENCE_DDL = (
    "CREATE TABLE ubuntu_asset_packages ("
    "id TEXT PRIMARY KEY NOT NULL, asset_id TEXT NOT NULL "
    "REFERENCES assets(id) ON DELETE RESTRICT, asset_value TEXT NOT NULL, "
    "ecosystem TEXT NOT NULL, binary_name TEXT NOT NULL, binary_version TEXT NOT NULL, "
    "architecture TEXT NOT NULL, source_name TEXT NOT NULL, source_version TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), evidence_type TEXT NOT NULL "
    "CHECK (evidence_type = 'user_verified'), evidence TEXT NOT NULL, "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(asset_id, ecosystem, binary_name, binary_version, architecture, "
    "source_name, source_version))",
    "CREATE TABLE ubuntu_asset_package_events ("
    "id TEXT PRIMARY KEY NOT NULL, ubuntu_package_id TEXT NOT NULL "
    "REFERENCES ubuntu_asset_packages(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'updated', 'reactivated', 'revoked')), "
    "evidence_type TEXT NOT NULL CHECK (evidence_type = 'user_verified'), "
    "evidence TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX ubuntu_asset_packages_active_asset ON "
    "ubuntu_asset_packages(active, asset_id, ecosystem, binary_name, architecture)",
    "CREATE INDEX ubuntu_asset_package_events_package_id ON "
    "ubuntu_asset_package_events(ubuntu_package_id, recorded_at)",
)

CTI_INDICATOR_DDL = (
    "CREATE TABLE cti_indicators ("
    "id TEXT PRIMARY KEY NOT NULL, indicator_type TEXT NOT NULL CHECK (indicator_type IN "
    "('domain', 'ipv4', 'ipv6', 'url', 'md5', 'sha1', 'sha256')), "
    "value TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(indicator_type, value))",
    "CREATE TABLE cti_indicator_assertions ("
    "id TEXT PRIMARY KEY NOT NULL, indicator_id TEXT NOT NULL "
    "REFERENCES cti_indicators(id) ON DELETE RESTRICT, source_name TEXT NOT NULL, "
    "source_reference TEXT NOT NULL, confidence INTEGER NOT NULL "
    "CHECK (confidence BETWEEN 0 AND 100), valid_from TEXT, valid_until TEXT, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), description TEXT NOT NULL, "
    "first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL, UNIQUE(indicator_id, source_name, source_reference))",
    "CREATE TABLE cti_indicator_assertion_events ("
    "id TEXT PRIMARY KEY NOT NULL, assertion_id TEXT NOT NULL "
    "REFERENCES cti_indicator_assertions(id) ON DELETE RESTRICT, action TEXT NOT NULL "
    "CHECK (action IN ('added', 'observed', 'updated', 'reactivated', 'revoked')), "
    "confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100), "
    "valid_from TEXT, valid_until TEXT, description TEXT NOT NULL, reason TEXT NOT NULL, "
    "observed_at TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX cti_indicator_assertions_active_indicator ON "
    "cti_indicator_assertions(active, indicator_id, confidence)",
    "CREATE INDEX cti_indicator_assertion_events_assertion_id ON "
    "cti_indicator_assertion_events(assertion_id, recorded_at)",
)

CTI_FEED_DDL = (
    "CREATE TABLE cti_feed_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "source_name TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('complete', 'failed')), "
    "source_url TEXT NOT NULL, content_sha256 TEXT, started_at TEXT NOT NULL, "
    "finished_at TEXT NOT NULL, source_record_count INTEGER NOT NULL CHECK "
    "(source_record_count >= 0), indicator_count INTEGER NOT NULL CHECK "
    "(indicator_count >= 0 AND indicator_count <= source_record_count), "
    "added_count INTEGER NOT NULL CHECK (added_count >= 0), observed_count INTEGER NOT NULL "
    "CHECK (observed_count >= 0), updated_count INTEGER NOT NULL CHECK (updated_count >= 0), "
    "unchanged_count INTEGER NOT NULL CHECK (unchanged_count >= 0), "
    "reactivated_count INTEGER NOT NULL CHECK (reactivated_count >= 0), "
    "revoked_count INTEGER NOT NULL CHECK (revoked_count >= 0), error TEXT)",
    "CREATE TABLE cti_feed_run_items ("
    "id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES cti_feed_runs(id) "
    "ON DELETE RESTRICT, assertion_id TEXT NOT NULL REFERENCES cti_indicator_assertions(id) "
    "ON DELETE RESTRICT, action TEXT NOT NULL CHECK (action IN "
    "('added', 'observed', 'updated', 'unchanged', 'reactivated', 'revoked')), "
    "state_sha256 TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE(run_id, assertion_id))",
    "CREATE INDEX cti_feed_runs_source_sequence ON cti_feed_runs(source_name, sequence)",
    "CREATE INDEX cti_feed_run_items_run_id ON cti_feed_run_items(run_id, assertion_id)",
)

RANSOMWARE_CLAIM_DDL = (
    "CREATE TABLE ransomware_claim_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "source_name TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('complete', 'failed')), "
    "source_url TEXT NOT NULL, content_sha256 TEXT, started_at TEXT NOT NULL, "
    "finished_at TEXT NOT NULL, fetched_at TEXT, generated_at TEXT, window_days INTEGER "
    "CHECK (window_days BETWEEN 1 AND 365), source_record_count INTEGER NOT NULL CHECK "
    "(source_record_count >= 0), claim_count INTEGER NOT NULL CHECK (claim_count >= 0), "
    "added_count INTEGER NOT NULL CHECK (added_count >= 0), updated_count INTEGER NOT NULL "
    "CHECK (updated_count >= 0), unchanged_count INTEGER NOT NULL CHECK "
    "(unchanged_count >= 0), removed_count INTEGER NOT NULL CHECK (removed_count >= 0), "
    "error TEXT)",
    "CREATE TABLE ransomware_claim_run_items ("
    "id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES ransomware_claim_runs(id) "
    "ON DELETE RESTRICT, claim_id TEXT NOT NULL, group_name TEXT NOT NULL, victim TEXT NOT NULL, "
    "country TEXT, sector TEXT, discovered_at TEXT NOT NULL, claim_status TEXT NOT NULL CHECK "
    "(claim_status IN ('listed', 'delisted')), website TEXT, last_seen_at TEXT, "
    "delisted_at TEXT, first_party INTEGER CHECK (first_party IN (0, 1)), "
    "source_post_available INTEGER NOT NULL CHECK (source_post_available IN (0, 1)), "
    "action TEXT NOT NULL CHECK (action IN ('added', 'updated', 'unchanged', 'removed')), "
    "state_sha256 TEXT NOT NULL, UNIQUE(run_id, claim_id))",
    "CREATE INDEX ransomware_claim_runs_source_sequence ON "
    "ransomware_claim_runs(source_name, sequence)",
    "CREATE INDEX ransomware_claim_run_items_run_action ON "
    "ransomware_claim_run_items(run_id, action, claim_id)",
)

RANSOMLOOK_CLAIM_DDL = (
    "CREATE TABLE ransomlook_claim_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "source_name TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('complete', 'failed')), "
    "source_url TEXT NOT NULL, content_sha256 TEXT, started_at TEXT NOT NULL, "
    "finished_at TEXT NOT NULL, fetched_at TEXT, window_days INTEGER "
    "CHECK (window_days = 7), source_record_count INTEGER NOT NULL CHECK "
    "(source_record_count >= 0), claim_count INTEGER NOT NULL CHECK (claim_count >= 0), "
    "added_count INTEGER NOT NULL CHECK (added_count >= 0), updated_count INTEGER NOT NULL "
    "CHECK (updated_count >= 0), unchanged_count INTEGER NOT NULL CHECK "
    "(unchanged_count >= 0), removed_count INTEGER NOT NULL CHECK (removed_count >= 0), "
    "error TEXT)",
    "CREATE TABLE ransomlook_claim_run_items ("
    "id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES ransomlook_claim_runs(id) "
    "ON DELETE RESTRICT, claim_id TEXT NOT NULL, group_name TEXT NOT NULL, victim TEXT NOT NULL, "
    "discovered_at TEXT NOT NULL, action TEXT NOT NULL CHECK (action IN "
    "('added', 'updated', 'unchanged', 'removed')), state_sha256 TEXT NOT NULL, "
    "UNIQUE(run_id, claim_id))",
    "CREATE INDEX ransomlook_claim_runs_source_sequence ON "
    "ransomlook_claim_runs(source_name, sequence)",
    "CREATE INDEX ransomlook_claim_run_items_run_action ON "
    "ransomlook_claim_run_items(run_id, action, claim_id)",
)

RANSOMLOOK_WATCH_DDL = (
    "CREATE TABLE ransomlook_watches ("
    "id TEXT PRIMARY KEY NOT NULL, name_key TEXT NOT NULL UNIQUE, "
    "display_name TEXT NOT NULL, query TEXT NOT NULL, query_key TEXT NOT NULL, "
    "match_mode TEXT NOT NULL CHECK (match_mode IN ('exact', 'contains')), "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL)",
    "CREATE TABLE ransomlook_watch_events ("
    "id TEXT PRIMARY KEY NOT NULL, watch_id TEXT NOT NULL REFERENCES "
    "ransomlook_watches(id) ON DELETE RESTRICT, action TEXT NOT NULL CHECK "
    "(action IN ('added', 'updated', 'reactivated', 'revoked')), "
    "definition_sha256 TEXT NOT NULL, reason TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE TABLE ransomlook_watch_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "watch_id TEXT NOT NULL REFERENCES ransomlook_watches(id) ON DELETE RESTRICT, "
    "source_run_id TEXT NOT NULL REFERENCES ransomlook_claim_runs(id) ON DELETE RESTRICT, "
    "definition_sha256 TEXT NOT NULL, previous_run_id TEXT REFERENCES "
    "ransomlook_watch_runs(id) ON DELETE RESTRICT, executed_at TEXT NOT NULL, "
    "total_count INTEGER NOT NULL CHECK (total_count >= 0), added_count INTEGER NOT NULL "
    "CHECK (added_count >= 0), updated_count INTEGER NOT NULL CHECK (updated_count >= 0), "
    "unchanged_count INTEGER NOT NULL CHECK (unchanged_count >= 0), removed_count INTEGER "
    "NOT NULL CHECK (removed_count >= 0), result_sha256 TEXT NOT NULL)",
    "CREATE TABLE ransomlook_watch_run_items ("
    "id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES "
    "ransomlook_watch_runs(id) ON DELETE RESTRICT, claim_id TEXT NOT NULL, "
    "group_name TEXT NOT NULL, victim TEXT NOT NULL, discovered_at TEXT NOT NULL, "
    "matched_value TEXT NOT NULL, match_type TEXT NOT NULL CHECK "
    "(match_type IN ('exact', 'contains')), action TEXT NOT NULL CHECK "
    "(action IN ('added', 'updated', 'unchanged', 'removed')), state_sha256 TEXT NOT NULL, "
    "UNIQUE(run_id, claim_id))",
    "CREATE INDEX ransomlook_watch_events_watch_recorded ON "
    "ransomlook_watch_events(watch_id, recorded_at)",
    "CREATE INDEX ransomlook_watch_runs_watch_sequence ON "
    "ransomlook_watch_runs(watch_id, sequence)",
    "CREATE INDEX ransomlook_watch_run_items_run_action ON "
    "ransomlook_watch_run_items(run_id, action, claim_id)",
)

BRAND_USERNAME_WATCH_V49_DDL = (
    "CREATE TABLE brand_username_watches ("
    "id TEXT PRIMARY KEY NOT NULL, name_key TEXT NOT NULL UNIQUE, "
    "display_name TEXT NOT NULL, username TEXT NOT NULL, platforms_json TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL)",
    "CREATE TABLE brand_username_watch_events ("
    "id TEXT PRIMARY KEY NOT NULL, watch_id TEXT NOT NULL REFERENCES "
    "brand_username_watches(id) ON DELETE RESTRICT, action TEXT NOT NULL CHECK "
    "(action IN ('added', 'updated', 'reactivated', 'revoked')), "
    "definition_sha256 TEXT NOT NULL, reason TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE TABLE brand_username_watch_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "watch_id TEXT NOT NULL REFERENCES brand_username_watches(id) ON DELETE RESTRICT, "
    "status TEXT NOT NULL CHECK (status IN ('complete', 'failed')), "
    "source_name TEXT NOT NULL, source_version TEXT NOT NULL, "
    "integration_profile TEXT NOT NULL, username TEXT NOT NULL, "
    "platforms_json TEXT NOT NULL, definition_sha256 TEXT NOT NULL, "
    "previous_complete_run_id TEXT REFERENCES brand_username_watch_runs(id) "
    "ON DELETE RESTRICT, checked_at TEXT, recorded_at TEXT NOT NULL, "
    "platform_count INTEGER NOT NULL CHECK (platform_count BETWEEN 1 AND 10), "
    "found_count INTEGER NOT NULL CHECK (found_count >= 0), "
    "newly_found_count INTEGER NOT NULL CHECK (newly_found_count >= 0), "
    "changed_count INTEGER NOT NULL CHECK (changed_count >= 0), "
    "unchanged_found_count INTEGER NOT NULL CHECK (unchanged_found_count >= 0), "
    "no_longer_reported_count INTEGER NOT NULL CHECK (no_longer_reported_count >= 0), "
    "unreported_count INTEGER NOT NULL CHECK (unreported_count >= 0), "
    "result_sha256 TEXT, error TEXT, CHECK ((status='complete' AND checked_at IS NOT NULL "
    "AND result_sha256 IS NOT NULL AND error IS NULL) OR (status='failed' AND "
    "checked_at IS NULL AND result_sha256 IS NULL AND error IS NOT NULL)))",
    "CREATE TABLE brand_username_watch_run_items ("
    "id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES "
    "brand_username_watch_runs(id) ON DELETE RESTRICT, platform TEXT NOT NULL, "
    "profile_url TEXT, result_status TEXT NOT NULL CHECK "
    "(result_status IN ('found_unverified', 'unreported')), action TEXT NOT NULL CHECK "
    "(action IN ('baseline_found', 'baseline_unreported', 'newly_found', 'changed', "
    "'unchanged_found', 'no_longer_reported', 'unchanged_unreported')), "
    "state_sha256 TEXT NOT NULL, UNIQUE(run_id, platform))",
    "CREATE INDEX brand_username_watch_events_watch_recorded ON "
    "brand_username_watch_events(watch_id, recorded_at)",
    "CREATE INDEX brand_username_watch_runs_watch_sequence ON "
    "brand_username_watch_runs(watch_id, sequence)",
    "CREATE INDEX brand_username_watch_run_items_run_action ON "
    "brand_username_watch_run_items(run_id, action, platform)",
)

BRAND_USERNAME_WATCH_DDL = (
    BRAND_USERNAME_WATCH_V49_DDL[0].replace(
        "updated_at TEXT NOT NULL)",
        "updated_at TEXT NOT NULL, source_key TEXT NOT NULL DEFAULT 'maigret' "
        "CHECK (source_key IN ('maigret', 'sherlock')))",
    ),
    *BRAND_USERNAME_WATCH_V49_DDL[1:],
)

BRAND_USERNAME_REVIEW_DDL = (
    "CREATE TABLE brand_username_review_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "candidate_id TEXT NOT NULL, watch_id TEXT NOT NULL REFERENCES "
    "brand_username_watches(id) ON DELETE RESTRICT, run_id TEXT NOT NULL REFERENCES "
    "brand_username_watch_runs(id) ON DELETE RESTRICT, platform TEXT NOT NULL, "
    "candidate_json TEXT NOT NULL, candidate_sha256 TEXT NOT NULL, decision TEXT NOT NULL "
    "CHECK (decision IN ('known_official', 'possible_impersonation', 'uncertain')), "
    "reason TEXT NOT NULL, recorded_at TEXT NOT NULL, previous_event_id TEXT REFERENCES "
    "brand_username_review_events(id) ON DELETE RESTRICT)",
    "CREATE INDEX brand_username_review_events_candidate_sequence ON "
    "brand_username_review_events(candidate_id, sequence)",
    "CREATE INDEX brand_username_review_events_watch_platform_sequence ON "
    "brand_username_review_events(watch_id, platform, sequence)",
)

BRAND_USERNAME_REVIEW_NOTIFICATION_DDL = (
    "CREATE TABLE brand_username_review_notifications ("
    "sequence INTEGER PRIMARY KEY NOT NULL CHECK (sequence > 0), "
    "id TEXT NOT NULL UNIQUE, candidate_id TEXT NOT NULL UNIQUE, "
    "review_event_id TEXT NOT NULL UNIQUE REFERENCES "
    "brand_username_review_events(id) ON DELETE RESTRICT, event_type TEXT NOT NULL "
    "CHECK (event_type = 'social_profile_possible_impersonation'), origin TEXT NOT NULL "
    "CHECK (origin = 'new'), created_at TEXT NOT NULL, read_at TEXT)",
    "CREATE INDEX brand_username_review_notifications_read_sequence ON "
    "brand_username_review_notifications(read_at, sequence)",
)

RANSOMWARE_WATCH_DDL = (
    "CREATE TABLE ransomware_watches ("
    "id TEXT PRIMARY KEY NOT NULL, name_key TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, "
    "kind TEXT NOT NULL CHECK (kind IN ('organization', 'domain')), query TEXT NOT NULL, "
    "query_key TEXT NOT NULL, match_mode TEXT NOT NULL CHECK (match_mode IN "
    "('exact', 'contains')), active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "CHECK (kind != 'domain' OR match_mode = 'exact'))",
    "CREATE TABLE ransomware_watch_events ("
    "id TEXT PRIMARY KEY NOT NULL, watch_id TEXT NOT NULL REFERENCES ransomware_watches(id) "
    "ON DELETE RESTRICT, action TEXT NOT NULL CHECK (action IN "
    "('added', 'updated', 'reactivated', 'revoked')), definition_sha256 TEXT NOT NULL, "
    "reason TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE TABLE ransomware_watch_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "watch_id TEXT NOT NULL REFERENCES ransomware_watches(id) ON DELETE RESTRICT, "
    "source_run_id TEXT NOT NULL REFERENCES ransomware_claim_runs(id) ON DELETE RESTRICT, "
    "definition_sha256 TEXT NOT NULL, previous_run_id TEXT REFERENCES "
    "ransomware_watch_runs(id) ON DELETE RESTRICT, executed_at TEXT NOT NULL, "
    "total_count INTEGER NOT NULL CHECK (total_count >= 0), added_count INTEGER NOT NULL "
    "CHECK (added_count >= 0), updated_count INTEGER NOT NULL CHECK (updated_count >= 0), "
    "unchanged_count INTEGER NOT NULL CHECK (unchanged_count >= 0), removed_count INTEGER "
    "NOT NULL CHECK (removed_count >= 0), result_sha256 TEXT NOT NULL)",
    "CREATE TABLE ransomware_watch_run_items ("
    "id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES ransomware_watch_runs(id) "
    "ON DELETE RESTRICT, claim_id TEXT NOT NULL, group_name TEXT NOT NULL, victim TEXT NOT NULL, "
    "country TEXT, sector TEXT, discovered_at TEXT NOT NULL, claim_status TEXT NOT NULL CHECK "
    "(claim_status IN ('listed', 'delisted')), website TEXT, last_seen_at TEXT, delisted_at TEXT, "
    "first_party INTEGER CHECK (first_party IN (0, 1)), source_post_available INTEGER NOT NULL "
    "CHECK (source_post_available IN (0, 1)), matched_field TEXT NOT NULL CHECK "
    "(matched_field IN ('victim', 'website')), matched_value TEXT NOT NULL, match_type TEXT NOT "
    "NULL CHECK (match_type IN ('exact', 'contains', 'subdomain')), action TEXT NOT NULL CHECK "
    "(action IN ('added', 'updated', 'unchanged', 'removed')), state_sha256 TEXT NOT NULL, "
    "UNIQUE(run_id, claim_id))",
    "CREATE TABLE ransomware_watch_notifications ("
    "sequence INTEGER PRIMARY KEY NOT NULL CHECK (sequence > 0), id TEXT NOT NULL UNIQUE, "
    "run_id TEXT NOT NULL UNIQUE REFERENCES ransomware_watch_runs(id) ON DELETE RESTRICT, "
    "watch_id TEXT NOT NULL REFERENCES ransomware_watches(id) ON DELETE RESTRICT, "
    "event_type TEXT NOT NULL CHECK (event_type = 'ransomware_watch_changed'), "
    "origin TEXT NOT NULL CHECK (origin = 'new'), created_at TEXT NOT NULL, read_at TEXT)",
    "CREATE INDEX ransomware_watch_events_watch_recorded ON "
    "ransomware_watch_events(watch_id, recorded_at)",
    "CREATE INDEX ransomware_watch_runs_watch_sequence ON "
    "ransomware_watch_runs(watch_id, sequence)",
    "CREATE INDEX ransomware_watch_run_items_run_action ON "
    "ransomware_watch_run_items(run_id, action, claim_id)",
    "CREATE INDEX ransomware_watch_notifications_read_sequence ON "
    "ransomware_watch_notifications(read_at, sequence)",
)

RANSOMWARE_MONITOR_SESSION_DDL = (
    "CREATE TABLE ransomware_monitor_sessions ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "status TEXT NOT NULL CHECK (status IN "
    "('running', 'complete', 'partial', 'interrupted', 'failed')), "
    "started_at TEXT NOT NULL, finished_at TEXT, stop_reason TEXT NOT NULL CHECK "
    "(stop_reason IN ('', 'cycles', 'duration', 'interrupted', 'error')), "
    "planned_cycles INTEGER NOT NULL CHECK (planned_cycles BETWEEN 1 AND 1000), "
    "interval_seconds INTEGER NOT NULL CHECK (interval_seconds BETWEEN 300 AND 86400), "
    "max_duration_seconds INTEGER NOT NULL CHECK "
    "(max_duration_seconds BETWEEN 1 AND 604800), "
    "max_watches INTEGER NOT NULL CHECK (max_watches BETWEEN 1 AND 500), "
    "source_item_limit INTEGER NOT NULL CHECK (source_item_limit BETWEEN 1 AND 500), "
    "watch_item_limit INTEGER NOT NULL CHECK (watch_item_limit BETWEEN 1 AND 500), "
    "error TEXT NOT NULL, CHECK ("
    "(status='running' AND finished_at IS NULL AND stop_reason='' AND error='') OR "
    "(status IN ('complete', 'partial') AND finished_at IS NOT NULL AND "
    "stop_reason IN ('cycles', 'duration') AND error='') OR "
    "(status='interrupted' AND finished_at IS NOT NULL AND "
    "stop_reason='interrupted' AND error='') OR "
    "(status='failed' AND finished_at IS NOT NULL AND stop_reason='error' "
    "AND length(error)>0)))",
    "CREATE TABLE ransomware_monitor_cycles ("
    "id TEXT PRIMARY KEY NOT NULL, session_id TEXT NOT NULL REFERENCES "
    "ransomware_monitor_sessions(id) ON DELETE RESTRICT, "
    "cycle INTEGER NOT NULL CHECK (cycle BETWEEN 1 AND 1000), "
    "source_run_id TEXT NOT NULL UNIQUE REFERENCES ransomware_claim_runs(id) "
    "ON DELETE RESTRICT, planned_watch_count INTEGER NOT NULL CHECK "
    "(planned_watch_count BETWEEN 0 AND 500), completed_watch_count INTEGER NOT NULL "
    "CHECK (completed_watch_count BETWEEN 0 AND planned_watch_count), "
    "baseline_watch_count INTEGER NOT NULL CHECK "
    "(baseline_watch_count BETWEEN 0 AND completed_watch_count), "
    "total_count INTEGER NOT NULL CHECK (total_count>=0), "
    "added_count INTEGER NOT NULL CHECK (added_count>=0), "
    "updated_count INTEGER NOT NULL CHECK (updated_count>=0), "
    "unchanged_count INTEGER NOT NULL CHECK (unchanged_count>=0), "
    "removed_count INTEGER NOT NULL CHECK (removed_count>=0), "
    "notification_count INTEGER NOT NULL CHECK "
    "(notification_count BETWEEN 0 AND completed_watch_count), "
    "CHECK (total_count=added_count+updated_count+unchanged_count), "
    "UNIQUE(session_id, cycle))",
    "CREATE TABLE ransomware_monitor_cycle_watch_runs ("
    "id TEXT PRIMARY KEY NOT NULL, cycle_id TEXT NOT NULL REFERENCES "
    "ransomware_monitor_cycles(id) ON DELETE RESTRICT, "
    "position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 500), "
    "watch_run_id TEXT NOT NULL UNIQUE REFERENCES ransomware_watch_runs(id) "
    "ON DELETE RESTRICT, UNIQUE(cycle_id, position), UNIQUE(cycle_id, watch_run_id))",
    "CREATE INDEX ransomware_monitor_sessions_status_sequence ON "
    "ransomware_monitor_sessions(status, sequence)",
)

RANSOMWARE_IDENTITY_REVIEW_DDL = (
    "CREATE TABLE ransomware_identity_review_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "candidate_id TEXT NOT NULL, watch_id TEXT NOT NULL REFERENCES ransomware_watches(id) "
    "ON DELETE RESTRICT, transition_source_run_id TEXT NOT NULL REFERENCES "
    "ransomware_claim_runs(id) ON DELETE RESTRICT, older_claim_id TEXT NOT NULL, "
    "newer_claim_id TEXT NOT NULL, candidate_json TEXT NOT NULL, "
    "candidate_sha256 TEXT NOT NULL, decision TEXT NOT NULL CHECK (decision IN "
    "('possible_same', 'different', 'uncertain')), reason TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL, previous_event_id TEXT REFERENCES "
    "ransomware_identity_review_events(id) ON DELETE RESTRICT, "
    "CHECK (older_claim_id != newer_claim_id))",
    "CREATE INDEX ransomware_identity_review_events_candidate_sequence ON "
    "ransomware_identity_review_events(candidate_id, sequence)",
    "CREATE INDEX ransomware_identity_review_events_watch_sequence ON "
    "ransomware_identity_review_events(watch_id, sequence)",
)

RANSOMWARE_SOURCE_REVIEW_DDL = (
    "CREATE TABLE ransomware_source_review_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "
    "id TEXT NOT NULL UNIQUE, comparison_id TEXT NOT NULL, "
    "threatcluster_run_id TEXT NOT NULL REFERENCES ransomware_claim_runs(id) "
    "ON DELETE RESTRICT, ransomlook_run_id TEXT NOT NULL REFERENCES "
    "ransomlook_claim_runs(id) ON DELETE RESTRICT, "
    "threatcluster_claim_id TEXT NOT NULL, ransomlook_claim_id TEXT NOT NULL, "
    "evidence_json TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, "
    "decision TEXT NOT NULL CHECK (decision IN "
    "('possible_same', 'different', 'uncertain')), reason TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL, previous_event_id TEXT REFERENCES "
    "ransomware_source_review_events(id) ON DELETE RESTRICT)",
    "CREATE INDEX ransomware_source_review_events_comparison_sequence ON "
    "ransomware_source_review_events(comparison_id, sequence)",
    "CREATE INDEX ransomware_source_review_events_decision_sequence ON "
    "ransomware_source_review_events(decision, sequence)",
)

CTI_KNOWLEDGE_DDL = (
    "CREATE TABLE cti_entities ("
    "id TEXT PRIMARY KEY NOT NULL, entity_type TEXT NOT NULL CHECK (entity_type IN "
    "('threat-actor', 'campaign', 'malware', 'report')), name_key TEXT NOT NULL, "
    "display_name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(entity_type, name_key))",
    "CREATE TABLE cti_entity_assertions ("
    "id TEXT PRIMARY KEY NOT NULL, entity_id TEXT NOT NULL REFERENCES cti_entities(id) "
    "ON DELETE RESTRICT, source_name TEXT NOT NULL, source_reference TEXT NOT NULL, "
    "confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100), "
    "aliases_json TEXT NOT NULL, description TEXT NOT NULL, active INTEGER NOT NULL "
    "CHECK (active IN (0, 1)), first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(entity_id, source_name, source_reference))",
    "CREATE TABLE cti_entity_assertion_events ("
    "id TEXT PRIMARY KEY NOT NULL, assertion_id TEXT NOT NULL REFERENCES "
    "cti_entity_assertions(id) ON DELETE RESTRICT, action TEXT NOT NULL CHECK (action IN "
    "('added', 'observed', 'updated', 'reactivated', 'revoked')), confidence INTEGER "
    "NOT NULL CHECK (confidence BETWEEN 0 AND 100), aliases_json TEXT NOT NULL, "
    "description TEXT NOT NULL, reason TEXT NOT NULL, observed_at TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL)",
    "CREATE TABLE cti_relationships ("
    "id TEXT PRIMARY KEY NOT NULL, source_entity_id TEXT NOT NULL REFERENCES "
    "cti_entities(id) ON DELETE RESTRICT, relationship_type TEXT NOT NULL CHECK "
    "(relationship_type IN ('attributed-to', 'uses', 'targets', 'delivers', "
    "'communicates-with', 'indicates', 'related-to', 'reports-on')), "
    "target_kind TEXT NOT NULL CHECK (target_kind IN ('entity', 'indicator')), "
    "target_entity_id TEXT REFERENCES cti_entities(id) ON DELETE RESTRICT, "
    "target_indicator_id TEXT REFERENCES cti_indicators(id) ON DELETE RESTRICT, "
    "target_key TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "CHECK ((target_kind = 'entity' AND target_entity_id IS NOT NULL AND "
    "target_indicator_id IS NULL AND target_key = 'entity:' || target_entity_id) OR "
    "(target_kind = 'indicator' AND target_indicator_id IS NOT NULL AND "
    "target_entity_id IS NULL AND target_key = 'indicator:' || target_indicator_id)), "
    "UNIQUE(source_entity_id, relationship_type, target_key))",
    "CREATE TABLE cti_relationship_assertions ("
    "id TEXT PRIMARY KEY NOT NULL, relationship_id TEXT NOT NULL REFERENCES "
    "cti_relationships(id) ON DELETE RESTRICT, source_name TEXT NOT NULL, "
    "source_reference TEXT NOT NULL, confidence INTEGER NOT NULL CHECK "
    "(confidence BETWEEN 0 AND 100), description TEXT NOT NULL, active INTEGER NOT NULL "
    "CHECK (active IN (0, 1)), first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(relationship_id, source_name, source_reference))",
    "CREATE TABLE cti_relationship_assertion_events ("
    "id TEXT PRIMARY KEY NOT NULL, assertion_id TEXT NOT NULL REFERENCES "
    "cti_relationship_assertions(id) ON DELETE RESTRICT, action TEXT NOT NULL CHECK "
    "(action IN ('added', 'observed', 'updated', 'reactivated', 'revoked')), "
    "confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100), "
    "description TEXT NOT NULL, reason TEXT NOT NULL, observed_at TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL)",
    "CREATE INDEX cti_entity_assertions_active_entity ON "
    "cti_entity_assertions(active, entity_id, confidence)",
    "CREATE INDEX cti_entity_assertion_events_assertion ON "
    "cti_entity_assertion_events(assertion_id, recorded_at)",
    "CREATE INDEX cti_relationships_source_target ON "
    "cti_relationships(source_entity_id, target_key, relationship_type)",
    "CREATE INDEX cti_relationship_assertions_active_relation ON "
    "cti_relationship_assertions(active, relationship_id, confidence)",
    "CREATE INDEX cti_relationship_assertion_events_assertion ON "
    "cti_relationship_assertion_events(assertion_id, recorded_at)",
)

CTI_SAVED_SEARCH_DDL = (
    "CREATE TABLE cti_saved_searches ("
    "id TEXT PRIMARY KEY NOT NULL, name_key TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, "
    "query TEXT NOT NULL, query_key TEXT NOT NULL, kind TEXT NOT NULL CHECK "
    "(kind IN ('all', 'entity', 'indicator')), entity_type TEXT CHECK "
    "(entity_type IN ('threat-actor', 'campaign', 'malware', 'report')), "
    "indicator_type TEXT CHECK (indicator_type IN "
    "('domain', 'ipv4', 'ipv6', 'url', 'md5', 'sha1', 'sha256')), "
    "active_only INTEGER NOT NULL CHECK (active_only IN (0, 1)), "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL, CHECK (NOT (kind = 'entity' AND indicator_type IS NOT NULL) "
    "AND NOT (kind = 'indicator' AND entity_type IS NOT NULL)))",
    "CREATE TABLE cti_saved_search_events ("
    "id TEXT PRIMARY KEY NOT NULL, saved_search_id TEXT NOT NULL REFERENCES "
    "cti_saved_searches(id) ON DELETE RESTRICT, action TEXT NOT NULL CHECK "
    "(action IN ('added', 'updated', 'reactivated', 'revoked')), "
    "definition_sha256 TEXT NOT NULL, reason TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE TABLE cti_saved_search_runs ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "saved_search_id TEXT NOT NULL REFERENCES cti_saved_searches(id) ON DELETE RESTRICT, "
    "definition_sha256 TEXT NOT NULL, previous_run_id TEXT REFERENCES "
    "cti_saved_search_runs(id) ON DELETE RESTRICT, executed_at TEXT NOT NULL, "
    "total_count INTEGER NOT NULL CHECK (total_count >= 0), added_count INTEGER NOT NULL "
    "CHECK (added_count >= 0), updated_count INTEGER NOT NULL CHECK (updated_count >= 0), "
    "unchanged_count INTEGER NOT NULL CHECK (unchanged_count >= 0), removed_count INTEGER "
    "NOT NULL CHECK (removed_count >= 0), result_sha256 TEXT NOT NULL)",
    "CREATE TABLE cti_saved_search_run_items ("
    "id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES cti_saved_search_runs(id) "
    "ON DELETE RESTRICT, kind TEXT NOT NULL CHECK (kind IN ('entity', 'indicator')), "
    "record_id TEXT NOT NULL, record_type TEXT NOT NULL, display_value TEXT NOT NULL, "
    "matched_field TEXT NOT NULL CHECK (matched_field IN ('name', 'alias', 'value')), "
    "matched_value TEXT NOT NULL, match_type TEXT NOT NULL CHECK "
    "(match_type IN ('exact', 'prefix', 'contains')), action TEXT NOT NULL CHECK "
    "(action IN ('added', 'updated', 'unchanged', 'removed')), state_sha256 TEXT NOT NULL, "
    "UNIQUE(run_id, kind, record_id))",
    "CREATE INDEX cti_saved_search_events_search_recorded ON "
    "cti_saved_search_events(saved_search_id, recorded_at)",
    "CREATE INDEX cti_saved_search_runs_search_sequence ON "
    "cti_saved_search_runs(saved_search_id, sequence)",
    "CREATE INDEX cti_saved_search_run_items_run ON "
    "cti_saved_search_run_items(run_id, action, kind, record_id)",
)

CTI_SAVED_SEARCH_NOTIFICATION_DDL = (
    "CREATE TABLE cti_saved_search_notifications ("
    "sequence INTEGER PRIMARY KEY NOT NULL CHECK (sequence > 0), "
    "id TEXT NOT NULL UNIQUE, run_id TEXT NOT NULL UNIQUE REFERENCES "
    "cti_saved_search_runs(id) ON DELETE RESTRICT, saved_search_id TEXT NOT NULL REFERENCES "
    "cti_saved_searches(id) ON DELETE RESTRICT, event_type TEXT NOT NULL CHECK "
    "(event_type = 'cti_saved_search_changed'), origin TEXT NOT NULL CHECK "
    "(origin = 'new'), created_at TEXT NOT NULL, read_at TEXT)",
    "CREATE INDEX cti_saved_search_notifications_read_sequence ON "
    "cti_saved_search_notifications(read_at, sequence)",
)

CTI_HUNTING_JOURNAL_DDL = (
    "CREATE TABLE cti_saved_search_tags ("
    "saved_search_id TEXT NOT NULL REFERENCES cti_saved_searches(id) ON DELETE RESTRICT, "
    "tag_key TEXT NOT NULL, display_tag TEXT NOT NULL, active INTEGER NOT NULL CHECK "
    "(active IN (0, 1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "PRIMARY KEY(saved_search_id, tag_key))",
    "CREATE TABLE cti_saved_search_tag_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "saved_search_id TEXT NOT NULL REFERENCES cti_saved_searches(id) ON DELETE RESTRICT, "
    "tag_key TEXT NOT NULL, display_tag TEXT NOT NULL, action TEXT NOT NULL CHECK "
    "(action IN ('added', 'updated', 'reactivated', 'removed')), recorded_at TEXT NOT NULL, "
    "FOREIGN KEY(saved_search_id, tag_key) REFERENCES "
    "cti_saved_search_tags(saved_search_id, tag_key) ON DELETE RESTRICT)",
    "CREATE TABLE cti_saved_search_notes ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "saved_search_id TEXT NOT NULL REFERENCES cti_saved_searches(id) ON DELETE RESTRICT, "
    "run_id TEXT REFERENCES cti_saved_search_runs(id) ON DELETE RESTRICT, "
    "note_kind TEXT NOT NULL CHECK (note_kind IN "
    "('observation', 'hypothesis', 'conclusion', 'follow-up')), "
    "body TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX cti_saved_search_tags_active_search ON "
    "cti_saved_search_tags(saved_search_id, active, tag_key)",
    "CREATE INDEX cti_saved_search_tag_events_search_sequence ON "
    "cti_saved_search_tag_events(saved_search_id, sequence)",
    "CREATE INDEX cti_saved_search_notes_search_sequence ON "
    "cti_saved_search_notes(saved_search_id, sequence)",
)

WEBHOOK_DDL = (
    "CREATE TABLE webhook_destinations ("
    "id TEXT PRIMARY KEY NOT NULL, name_key TEXT NOT NULL UNIQUE, "
    "display_name TEXT NOT NULL, url TEXT NOT NULL, endpoint TEXT NOT NULL, "
    "secret_b64 TEXT NOT NULL, active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE webhook_destination_events ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "destination_id TEXT NOT NULL REFERENCES webhook_destinations(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'secret_rotated', 'revoked')), "
    "endpoint TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE TABLE webhook_deliveries ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "destination_id TEXT NOT NULL REFERENCES webhook_destinations(id) ON DELETE RESTRICT, "
    "notification_id TEXT NOT NULL, event_type TEXT NOT NULL, status TEXT NOT NULL CHECK "
    "(status IN ('queued', 'retryable', 'failed', 'delivered')), "
    "payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, "
    "attempt_count INTEGER NOT NULL CHECK (attempt_count BETWEEN 0 AND 100), "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, delivered_at TEXT, "
    "last_http_status INTEGER, last_error TEXT, "
    "UNIQUE(destination_id, notification_id))",
    "CREATE TABLE webhook_delivery_attempts ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id TEXT NOT NULL UNIQUE, "
    "delivery_id TEXT NOT NULL REFERENCES webhook_deliveries(id) ON DELETE RESTRICT, "
    "number INTEGER NOT NULL CHECK (number BETWEEN 1 AND 100), "
    "outcome TEXT NOT NULL CHECK (outcome IN ('retryable', 'failed', 'delivered')), "
    "http_status INTEGER, error TEXT, attempted_at TEXT NOT NULL, "
    "UNIQUE(delivery_id, number))",
    "CREATE INDEX webhook_destinations_active_name ON "
    "webhook_destinations(active, name_key)",
    "CREATE INDEX webhook_destination_events_destination_sequence ON "
    "webhook_destination_events(destination_id, sequence)",
    "CREATE INDEX webhook_deliveries_status_sequence ON "
    "webhook_deliveries(status, sequence)",
    "CREATE INDEX webhook_delivery_attempts_delivery_number ON "
    "webhook_delivery_attempts(delivery_id, number)",
)

VULNERABILITY_EXPOSURE_DDL = (
    "CREATE TABLE vulnerability_exposures ("
    "id TEXT PRIMARY KEY NOT NULL, asset_product_id TEXT NOT NULL "
    "REFERENCES asset_products(id) ON DELETE RESTRICT, cve_id TEXT NOT NULL "
    "REFERENCES nvd_cve_records(cve_id) ON DELETE RESTRICT, "
    "status TEXT NOT NULL CHECK (status IN "
    "('investigating', 'affected', 'not_affected', 'fixed')), "
    "reason TEXT NOT NULL, suppressed INTEGER NOT NULL CHECK (suppressed IN (0, 1)), "
    "recheck_at TEXT, assessment_status TEXT NOT NULL, "
    "nvd_source_record_sha256 TEXT NOT NULL, product_evidence_updated_at TEXT NOT NULL, "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(asset_product_id, cve_id))",
    "CREATE TABLE vulnerability_exposure_events ("
    "id TEXT PRIMARY KEY NOT NULL, exposure_id TEXT NOT NULL "
    "REFERENCES vulnerability_exposures(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('opened', 'reviewed')), "
    "status TEXT NOT NULL CHECK (status IN "
    "('investigating', 'affected', 'not_affected', 'fixed')), "
    "reason TEXT NOT NULL, suppressed INTEGER NOT NULL CHECK (suppressed IN (0, 1)), "
    "recheck_at TEXT, assessment_status TEXT NOT NULL, "
    "nvd_source_record_sha256 TEXT NOT NULL, product_evidence_updated_at TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL)",
    "CREATE INDEX vulnerability_exposures_status_suppressed ON "
    "vulnerability_exposures(suppressed, status, cve_id, asset_product_id)",
    "CREATE INDEX vulnerability_exposure_events_exposure_id ON "
    "vulnerability_exposure_events(exposure_id, recorded_at)",
)

VULNERABILITY_EXPOSURE_SUPPRESSION_DDL = (
    "CREATE TABLE vulnerability_exposure_suppressions ("
    "id TEXT PRIMARY KEY NOT NULL, exposure_id TEXT NOT NULL UNIQUE "
    "REFERENCES vulnerability_exposures(id) ON DELETE RESTRICT, "
    "reason TEXT NOT NULL, expires_at TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE vulnerability_exposure_suppression_events ("
    "id TEXT PRIMARY KEY NOT NULL, suppression_id TEXT NOT NULL "
    "REFERENCES vulnerability_exposure_suppressions(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN "
    "('activated', 'extended', 'reactivated', 'revoked')), "
    "reason TEXT NOT NULL, expires_at TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX vulnerability_exposure_suppressions_active_exposure ON "
    "vulnerability_exposure_suppressions(active, exposure_id, expires_at)",
    "CREATE INDEX vulnerability_exposure_suppression_events_suppression_id ON "
    "vulnerability_exposure_suppression_events(suppression_id, recorded_at)",
)

VULNERABILITY_REASSESSMENT_DDL = (
    "CREATE TABLE vulnerability_reassessment_runs ("
    "id TEXT PRIMARY KEY NOT NULL, include_closed INTEGER NOT NULL "
    "CHECK (include_closed IN (0, 1)), include_suppressed INTEGER NOT NULL "
    "CHECK (include_suppressed IN (0, 1)), examined_count INTEGER NOT NULL "
    "CHECK (examined_count >= 0), candidate_count INTEGER NOT NULL "
    "CHECK (candidate_count >= 0 AND candidate_count <= examined_count), "
    "selected_count INTEGER NOT NULL "
    "CHECK (selected_count >= 0 AND selected_count <= candidate_count), "
    "truncated INTEGER NOT NULL CHECK (truncated IN (0, 1) AND truncated = "
    "CASE WHEN selected_count < candidate_count THEN 1 ELSE 0 END), "
    "recorded_at TEXT NOT NULL)",
    "CREATE TABLE vulnerability_reassessment_items ("
    "id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES "
    "vulnerability_reassessment_runs(id) ON DELETE RESTRICT, exposure_id TEXT NOT NULL "
    "REFERENCES vulnerability_exposures(id) ON DELETE RESTRICT, asset_value TEXT NOT NULL, "
    "cve_id TEXT NOT NULL, decision_status TEXT NOT NULL CHECK (decision_status IN "
    "('investigating', 'affected', 'not_affected', 'fixed')), "
    "previous_assessment_status TEXT NOT NULL CHECK (previous_assessment_status IN "
    "('inactive_product', 'nvd_conditions_missing', 'no_product_condition', "
    "'no_version_condition', 'manual_review_required', 'exact_condition_candidate')), "
    "current_assessment_status TEXT NOT NULL CHECK (current_assessment_status IN "
    "('inactive_product', 'nvd_conditions_missing', 'no_product_condition', "
    "'no_version_condition', 'manual_review_required', 'exact_condition_candidate')), "
    "triggers TEXT NOT NULL, nvd_source_record_sha256 TEXT NOT NULL, "
    "product_evidence_updated_at TEXT NOT NULL, recorded_at TEXT NOT NULL, "
    "UNIQUE(run_id, exposure_id))",
    "CREATE INDEX vulnerability_reassessment_items_run_id ON "
    "vulnerability_reassessment_items(run_id, exposure_id)",
)

VULNERABILITY_CHANGE_NOTIFICATION_DDL = (
    "CREATE TABLE vulnerability_change_notifications ("
    "sequence INTEGER PRIMARY KEY NOT NULL CHECK (sequence > 0), "
    "id TEXT NOT NULL UNIQUE, exposure_id TEXT NOT NULL REFERENCES "
    "vulnerability_exposures(id) ON DELETE RESTRICT, state_sha256 TEXT NOT NULL, "
    "triggers TEXT NOT NULL, asset_value TEXT NOT NULL, cve_id TEXT NOT NULL, "
    "decision_status TEXT NOT NULL CHECK (decision_status IN "
    "('investigating', 'affected', 'not_affected', 'fixed')), "
    "product_active INTEGER NOT NULL CHECK (product_active IN (0, 1)), "
    "recheck_at TEXT, "
    "nvd_source_record_sha256 TEXT NOT NULL, "
    "product_evidence_updated_at TEXT NOT NULL, event_type TEXT NOT NULL "
    "CHECK (event_type = 'vulnerability_review_required'), origin TEXT NOT NULL "
    "CHECK (origin = 'new'), created_at TEXT NOT NULL, read_at TEXT, "
    "UNIQUE(exposure_id, state_sha256))",
    "CREATE INDEX vulnerability_change_notifications_read_sequence ON "
    "vulnerability_change_notifications(read_at, sequence)",
)

VULNERABILITY_EXPOSURE_EVIDENCE_DDL = (
    "CREATE TABLE vulnerability_exposure_evidence ("
    "id TEXT PRIMARY KEY NOT NULL, exposure_id TEXT NOT NULL "
    "REFERENCES vulnerability_exposures(id) ON DELETE RESTRICT, "
    "evidence_type TEXT NOT NULL CHECK (evidence_type IN "
    "('vendor_advisory', 'distribution_advisory', 'package_inventory', 'analyst_note')), "
    "source_reference TEXT NOT NULL, summary TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(exposure_id, evidence_type, source_reference))",
    "CREATE TABLE vulnerability_exposure_evidence_events ("
    "id TEXT PRIMARY KEY NOT NULL, evidence_id TEXT NOT NULL "
    "REFERENCES vulnerability_exposure_evidence(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'updated', 'reactivated', 'revoked')), "
    "summary TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX vulnerability_exposure_evidence_active_exposure ON "
    "vulnerability_exposure_evidence(active, exposure_id, evidence_type)",
    "CREATE INDEX vulnerability_exposure_evidence_events_evidence_id ON "
    "vulnerability_exposure_evidence_events(evidence_id, recorded_at)",
)

VENDOR_PACKAGE_EVIDENCE_DDL = (
    "CREATE TABLE vulnerability_vendor_package_evidence ("
    "id TEXT PRIMARY KEY NOT NULL, exposure_id TEXT NOT NULL "
    "REFERENCES vulnerability_exposures(id) ON DELETE RESTRICT, "
    "asset_package_id TEXT NOT NULL REFERENCES asset_packages(id) ON DELETE RESTRICT, "
    "provider TEXT NOT NULL CHECK (provider = 'redhat'), cve_id TEXT NOT NULL, "
    "source_url TEXT NOT NULL, source_sha256 TEXT NOT NULL, document_version TEXT NOT NULL, "
    "current_release_at TEXT NOT NULL, vendor_status TEXT NOT NULL CHECK (vendor_status IN "
    "('fixed', 'known_affected', 'known_not_affected', 'under_investigation', "
    "'first_affected', 'first_fixed', 'last_affected', 'recommended')), "
    "match_kind TEXT NOT NULL CHECK (match_kind IN "
    "('exact_binary_package', 'source_package_context')), vex_product_id TEXT NOT NULL, "
    "component_product_id TEXT NOT NULL, component_purl TEXT NOT NULL, "
    "context_product_id TEXT NOT NULL, context_cpe TEXT NOT NULL, "
    "package_updated_at TEXT NOT NULL, summary TEXT NOT NULL, "
    "active INTEGER NOT NULL CHECK (active IN (0, 1)), "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "UNIQUE(exposure_id, asset_package_id, source_sha256, vex_product_id, vendor_status, "
    "package_updated_at))",
    "CREATE TABLE vulnerability_vendor_package_evidence_events ("
    "id TEXT PRIMARY KEY NOT NULL, evidence_id TEXT NOT NULL "
    "REFERENCES vulnerability_vendor_package_evidence(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN ('added', 'updated', 'reactivated', 'revoked')), "
    "summary TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE INDEX vulnerability_vendor_package_evidence_active_exposure ON "
    "vulnerability_vendor_package_evidence(active, exposure_id, asset_package_id)",
    "CREATE INDEX vulnerability_vendor_package_evidence_events_evidence_id ON "
    "vulnerability_vendor_package_evidence_events(evidence_id, recorded_at)",
)

VULNERABILITY_REMEDIATION_DDL = (
    "CREATE TABLE vulnerability_remediations ("
    "id TEXT PRIMARY KEY NOT NULL, exposure_id TEXT NOT NULL "
    "REFERENCES vulnerability_exposures(id) ON DELETE RESTRICT, "
    "recommendation TEXT NOT NULL, source_type TEXT NOT NULL CHECK (source_type IN "
    "('vendor_package_evidence', 'exposure_evidence', 'analyst_note')), "
    "source_reference TEXT NOT NULL, state TEXT NOT NULL CHECK (state IN "
    "('planned', 'implemented', 'cancelled')), latest_outcome TEXT NOT NULL CHECK "
    "(latest_outcome IN ('not_run', 'not_observed', 'still_present', 'inconclusive')), "
    "recheck_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE vulnerability_remediation_events ("
    "id TEXT PRIMARY KEY NOT NULL, remediation_id TEXT NOT NULL "
    "REFERENCES vulnerability_remediations(id) ON DELETE RESTRICT, "
    "action TEXT NOT NULL CHECK (action IN "
    "('planned', 'implemented', 'cancelled', 'rechecked')), "
    "state TEXT NOT NULL CHECK (state IN ('planned', 'implemented', 'cancelled')), "
    "outcome TEXT NOT NULL CHECK (outcome IN "
    "('not_run', 'not_observed', 'still_present', 'inconclusive')), "
    "reason TEXT NOT NULL, evidence_reference TEXT NOT NULL, recheck_at TEXT, "
    "exposure_status TEXT NOT NULL CHECK (exposure_status IN "
    "('investigating', 'affected', 'not_affected', 'fixed')), "
    "nvd_source_record_sha256 TEXT NOT NULL, product_evidence_updated_at TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL)",
    "CREATE INDEX vulnerability_remediations_exposure_state ON "
    "vulnerability_remediations(exposure_id, state, recheck_at)",
    "CREATE INDEX vulnerability_remediation_events_remediation_id ON "
    "vulnerability_remediation_events(remediation_id, recorded_at)",
)

# (column name, declared type, NOT NULL, primary-key position)
TABLES = {
    **supplier_watch_schema_metadata.TABLES,
    **global_saved_search_schema_metadata.TABLES,
    **news_schema_metadata.TABLES,
    **mentions_schema_metadata.TABLES,
    **mention_group_schema_metadata.TABLES,
    **nmap_management_schema_metadata.TABLES,
    **nmap_jobs_schema.TABLES,
    **warninglist_schema.TABLES,
    **enrichment_schema.TABLES,
    **research_history_schema.TABLES,
    **investigation_schema.TABLES,
    **report_schema.TABLES,
    **evidence_schema.TABLES,
    **document_storage_schema.TABLES,
    **relationship_notification_schema.TABLES,
    **social_discovery_schema.TABLES,
    **social_enrichment_schema.TABLES,
    **social_tracking_schema.TABLES,
    **group_schema.TABLES,
    **group_operations_schema.TABLES,
    'public_notice_watches': [('id', 'TEXT', 1, 1), ('organization_id', 'TEXT', 1, 0), ('active', 'INTEGER', 1, 0), ('revision', 'INTEGER', 1, 0), ('created_at', 'TEXT', 1, 0), ('updated_at', 'TEXT', 1, 0)],
    'public_notice_watch_events': [('sequence', 'INTEGER', 1, 1), ('id', 'TEXT', 1, 0), ('watch_id', 'TEXT', 1, 0), ('organization_id', 'TEXT', 1, 0), ('action', 'TEXT', 1, 0), ('revision', 'INTEGER', 1, 0), ('reason', 'TEXT', 1, 0), ('recorded_at', 'TEXT', 1, 0)],
    'public_notice_watch_runs': [('sequence', 'INTEGER', 1, 1), ('id', 'TEXT', 1, 0), ('watch_id', 'TEXT', 1, 0), ('organization_id', 'TEXT', 1, 0), ('source_run_id', 'TEXT', 1, 0), ('watch_event_id', 'TEXT', 1, 0), ('previous_run_id', 'TEXT', 0, 0), ('recorded_at', 'TEXT', 1, 0), ('scope_json', 'TEXT', 1, 0), ('scope_sha256', 'TEXT', 1, 0), ('result_sha256', 'TEXT', 1, 0), ('matched_count', 'INTEGER', 1, 0), ('baseline_count', 'INTEGER', 1, 0), ('added_count', 'INTEGER', 1, 0), ('updated_count', 'INTEGER', 1, 0), ('removed_count', 'INTEGER', 1, 0), ('unchanged_count', 'INTEGER', 1, 0)],
    'public_notice_watch_notifications': [('sequence', 'INTEGER', 1, 1), ('id', 'TEXT', 1, 0), ('run_id', 'TEXT', 1, 0), ('watch_id', 'TEXT', 1, 0), ('organization_id', 'TEXT', 1, 0), ('event_type', 'TEXT', 1, 0), ('origin', 'TEXT', 1, 0), ('created_at', 'TEXT', 1, 0), ('read_at', 'TEXT', 0, 0)],
    'public_notice_runs': [('sequence', 'INTEGER', 1, 1), ('id', 'TEXT', 1, 0), ('status', 'TEXT', 1, 0), ('started_at', 'TEXT', 1, 0), ('finished_at', 'TEXT', 1, 0), ('fetched_at', 'TEXT', 0, 0), ('content_sha256', 'TEXT', 0, 0), ('snapshot_sha256', 'TEXT', 0, 0), ('notice_count', 'INTEGER', 1, 0), ('added_count', 'INTEGER', 1, 0), ('updated_count', 'INTEGER', 1, 0), ('unchanged_count', 'INTEGER', 1, 0), ('removed_count', 'INTEGER', 1, 0), ('error', 'TEXT', 0, 0), ('chain_sha256', 'TEXT', 1, 0)],
    'public_notice_changes': [('sequence', 'INTEGER', 1, 1), ('run_id', 'TEXT', 1, 0), ('notice_id', 'TEXT', 1, 0), ('action', 'TEXT', 1, 0), ('record_json', 'TEXT', 1, 0), ('state_sha256', 'TEXT', 1, 0)],

    'ransomlook_watch_notifications': [('sequence', 'INTEGER', 1, 1), ('id', 'TEXT', 1, 0), ('run_id', 'TEXT', 1, 0), ('watch_id', 'TEXT', 1, 0), ('event_type', 'TEXT', 1, 0), ('origin', 'TEXT', 1, 0), ('created_at', 'TEXT', 1, 0), ('read_at', 'TEXT', 0, 0)],
    'attack_catalog_runs': [('sequence', 'INTEGER', 1, 1), ('id', 'TEXT', 1, 0), ('version', 'TEXT', 1, 0), ('source_url', 'TEXT', 1, 0), ('content_sha256', 'TEXT', 1, 0), ('source_object_count', 'INTEGER', 1, 0), ('fetched_at', 'TEXT', 1, 0), ('recorded_at', 'TEXT', 1, 0), ('entity_count', 'INTEGER', 1, 0), ('relationship_count', 'INTEGER', 1, 0), ('phase_count', 'INTEGER', 1, 0), ('added_count', 'INTEGER', 1, 0), ('updated_count', 'INTEGER', 1, 0), ('reactivated_count', 'INTEGER', 1, 0), ('revoked_count', 'INTEGER', 1, 0), ('unchanged_count', 'INTEGER', 1, 0), ('chain_sha256', 'TEXT', 1, 0)],
    'attack_catalog_entities': [('stix_id', 'TEXT', 1, 1), ('external_id', 'TEXT', 1, 0), ('record_json', 'TEXT', 1, 0), ('state_sha256', 'TEXT', 1, 0), ('active', 'INTEGER', 1, 0), ('first_run_id', 'TEXT', 1, 0), ('last_run_id', 'TEXT', 1, 0)],
    'attack_catalog_relationships': [('stix_id', 'TEXT', 1, 1), ('source_stix_id', 'TEXT', 1, 0), ('target_stix_id', 'TEXT', 1, 0), ('relationship_type', 'TEXT', 1, 0), ('record_json', 'TEXT', 1, 0), ('state_sha256', 'TEXT', 1, 0), ('active', 'INTEGER', 1, 0), ('first_run_id', 'TEXT', 1, 0), ('last_run_id', 'TEXT', 1, 0)],
    'attack_catalog_phases': [('id', 'TEXT', 1, 1), ('technique_stix_id', 'TEXT', 1, 0), ('tactic_stix_id', 'TEXT', 1, 0), ('record_json', 'TEXT', 1, 0), ('state_sha256', 'TEXT', 1, 0), ('active', 'INTEGER', 1, 0), ('first_run_id', 'TEXT', 1, 0), ('last_run_id', 'TEXT', 1, 0)],
    'attack_catalog_changes': [('sequence', 'INTEGER', 1, 1), ('run_id', 'TEXT', 1, 0), ('record_kind', 'TEXT', 1, 0), ('record_key', 'TEXT', 1, 0), ('action', 'TEXT', 1, 0), ('record_json', 'TEXT', 1, 0), ('state_sha256', 'TEXT', 1, 0)],

    'organizations': [('id', 'TEXT', 1, 1), ('name_key', 'TEXT', 1, 0), ('display_name', 'TEXT', 1, 0), ('revision', 'INTEGER', 1, 0), ('active', 'INTEGER', 1, 0), ('created_at', 'TEXT', 1, 0), ('updated_at', 'TEXT', 1, 0)],
    'organization_events': [('sequence', 'INTEGER', 1, 1), ('id', 'TEXT', 1, 0), ('organization_id', 'TEXT', 1, 0), ('action', 'TEXT', 1, 0), ('revision', 'INTEGER', 1, 0), ('name_key', 'TEXT', 1, 0), ('display_name', 'TEXT', 1, 0), ('reason', 'TEXT', 1, 0), ('recorded_at', 'TEXT', 1, 0)],
    'organization_links': [('id', 'TEXT', 1, 1), ('organization_id', 'TEXT', 1, 0), ('target_kind', 'TEXT', 1, 0), ('target_value', 'TEXT', 1, 0), ('asset_id', 'TEXT', 0, 0), ('username_watch_id', 'TEXT', 0, 0), ('ransomware_watch_id', 'TEXT', 0, 0), ('ransomlook_watch_id', 'TEXT', 0, 0), ('revision', 'INTEGER', 1, 0), ('active', 'INTEGER', 1, 0), ('reason', 'TEXT', 1, 0), ('created_at', 'TEXT', 1, 0), ('updated_at', 'TEXT', 1, 0)],
    'organization_link_events': [('sequence', 'INTEGER', 1, 1), ('id', 'TEXT', 1, 0), ('link_id', 'TEXT', 1, 0), ('organization_id', 'TEXT', 1, 0), ('action', 'TEXT', 1, 0), ('revision', 'INTEGER', 1, 0), ('target_kind', 'TEXT', 1, 0), ('target_value', 'TEXT', 1, 0), ('reason', 'TEXT', 1, 0), ('recorded_at', 'TEXT', 1, 0)],
    'collection_sessions': [('sequence', 'INTEGER', 1, 1), ('id', 'TEXT', 1, 0), ('root_id', 'TEXT', 1, 0), ('parent_id', 'TEXT', 0, 0), ('generation', 'INTEGER', 1, 0), ('profile_event_id', 'TEXT', 0, 0), ('definition_json', 'TEXT', 1, 0), ('definition_sha256', 'TEXT', 1, 0), ('plan_json', 'TEXT', 1, 0), ('plan_sha256', 'TEXT', 1, 0), ('executor_contract_version', 'INTEGER', 1, 0), ('status', 'TEXT', 1, 0), ('started_at', 'TEXT', 1, 0), ('finished_at', 'TEXT', 0, 0), ('stop_reason', 'TEXT', 0, 0), ('analysis_status', 'TEXT', 1, 0), ('analysis_recorded_at', 'TEXT', 0, 0)],
    'collection_session_steps': [('id', 'TEXT', 1, 1), ('session_id', 'TEXT', 1, 0), ('ordinal', 'INTEGER', 1, 0), ('step_key', 'TEXT', 1, 0), ('kind', 'TEXT', 1, 0), ('source', 'TEXT', 1, 0), ('watch_id', 'TEXT', 0, 0), ('target_sha256', 'TEXT', 1, 0), ('depends_on_step_id', 'TEXT', 0, 0), ('scan_job_id', 'TEXT', 0, 0), ('status', 'TEXT', 1, 0), ('started_at', 'TEXT', 0, 0), ('finished_at', 'TEXT', 0, 0), ('error_code', 'TEXT', 0, 0)],
    'collection_step_receipts': [('step_id', 'TEXT', 1, 1), ('recorded_at', 'TEXT', 1, 0), ('result_status', 'TEXT', 1, 0), ('summary_json', 'TEXT', 1, 0), ('summary_sha256', 'TEXT', 1, 0), ('scan_attempt_id', 'TEXT', 0, 0), ('discovery_run_id', 'TEXT', 0, 0), ('feed_run_id', 'TEXT', 0, 0), ('username_run_id', 'TEXT', 0, 0), ('threatcluster_source_run_id', 'TEXT', 0, 0), ('ransomlook_source_run_id', 'TEXT', 0, 0), ('threatcluster_watch_run_id', 'TEXT', 0, 0), ('ransomlook_watch_run_id', 'TEXT', 0, 0), ('public_notice_run_id', 'TEXT', 0, 0), ('news_run_id', 'TEXT', 0, 0), ('saved_search_run_id', 'TEXT', 0, 0)],

    "collection_profiles": [
        ("id", "TEXT", 1, 1), ("name_key", "TEXT", 1, 0),
        ("display_name", "TEXT", 1, 0), ("revision", "INTEGER", 1, 0),
        ("definition_json", "TEXT", 1, 0), ("definition_sha256", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "collection_profile_events": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("profile_id", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("revision", "INTEGER", 1, 0), ("display_name", "TEXT", 1, 0),
        ("definition_json", "TEXT", 1, 0), ("definition_sha256", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "assets": [("id", "TEXT", 1, 1), ("value", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0)],
    "asset_criticalities": [
        ("asset_id", "TEXT", 1, 1), ("asset_value", "TEXT", 1, 0),
        ("level", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("reason", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "asset_criticality_events": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("level", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "suppliers": [
        ("id", "TEXT", 1, 1), ("name_key", "TEXT", 1, 0),
        ("display_name", "TEXT", 1, 0), ("primary_domain", "TEXT", 1, 0),
        ("relationship_type", "TEXT", 1, 0), ("criticality", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("reason", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "supplier_events": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("supplier_id", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("display_name", "TEXT", 1, 0), ("primary_domain", "TEXT", 1, 0),
        ("relationship_type", "TEXT", 1, 0), ("criticality", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "supplier_candidates": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("asset_value", "TEXT", 1, 0), ("candidate_domain", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0), ("current", "INTEGER", 1, 0),
        ("supplier_id", "TEXT", 0, 0), ("resolution_reason", "TEXT", 0, 0),
        ("first_seen_at", "TEXT", 1, 0), ("last_seen_at", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "supplier_candidate_evidence": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("candidate_id", "TEXT", 1, 0), ("source_evidence_id", "TEXT", 1, 0),
        ("derivation_key", "TEXT", 1, 0), ("source_domain", "TEXT", 1, 0),
        ("target_domain", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
        ("public_suffix_version", "TEXT", 1, 0),
        ("public_suffix_sha256", "TEXT", 1, 0),
        ("observed_at", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "supplier_candidate_resolution_events": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("candidate_id", "TEXT", 1, 0), ("decision", "TEXT", 1, 0),
        ("supplier_id", "TEXT", 0, 0), ("reason", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "cases": [
        ("id", "TEXT", 1, 1), ("title", "TEXT", 1, 0),
        ("summary", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("priority", "TEXT", 1, 0), ("resolution", "TEXT", 0, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
        ("closed_at", "TEXT", 0, 0),
    ],
    "case_evidence": [
        ("id", "TEXT", 1, 1), ("case_id", "TEXT", 1, 0),
        ("evidence_type", "TEXT", 1, 0), ("evidence_id", "TEXT", 1, 0),
        ("display_value", "TEXT", 1, 0), ("source_reference", "TEXT", 1, 0),
        ("snapshot_json", "TEXT", 1, 0), ("snapshot_sha256", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("added_reason", "TEXT", 1, 0),
        ("added_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
        ("removed_reason", "TEXT", 0, 0), ("removed_at", "TEXT", 0, 0),
    ],
    "case_tasks": [
        ("id", "TEXT", 1, 1), ("case_id", "TEXT", 1, 0),
        ("title", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("due_at", "TEXT", 0, 0), ("reason", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "case_activities": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("case_id", "TEXT", 1, 0), ("activity_type", "TEXT", 1, 0),
        ("reference_id", "TEXT", 0, 0), ("summary", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("snapshot_json", "TEXT", 1, 0),
        ("snapshot_sha256", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "observations": [
        ("id", "TEXT", 1, 1), ("domain", "TEXT", 1, 0),
        ("raw_domain", "TEXT", 1, 0), ("source_name", "TEXT", 1, 0),
        ("source_sha256", "TEXT", 1, 0), ("source_line", "INTEGER", 1, 0),
        ("observed_at", "TEXT", 0, 0), ("ingested_at", "TEXT", 1, 0),
    ],
    "findings": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("asset_value", "TEXT", 1, 0), ("domain", "TEXT", 1, 0),
        ("rule_version", "TEXT", 1, 0), ("reasons", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("last_seen_at", "TEXT", 1, 0),
    ],
    "finding_observations": [
        ("finding_id", "TEXT", 1, 1), ("observation_id", "TEXT", 1, 2),
    ],
    "reviews": [
        ("id", "TEXT", 1, 1), ("finding_id", "TEXT", 1, 0),
        ("decision", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0),
    ],
    "scan_jobs": [
        ("id", "TEXT", 1, 1), ("targets", "TEXT", 1, 0), ("typos", "INTEGER", 1, 0),
        ("provider", "TEXT", 1, 0), ("rule_version", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0), ("attempt_count", "INTEGER", 1, 0),
    ],
    "scan_attempts": [
        ("id", "TEXT", 1, 1), ("job_id", "TEXT", 1, 0), ("number", "INTEGER", 1, 0),
        ("status", "TEXT", 1, 0), ("started_at", "TEXT", 1, 0),
        ("finished_at", "TEXT", 0, 0), ("progress", "TEXT", 0, 0),
        ("error", "TEXT", 0, 0), ("queries", "TEXT", 1, 0), ("result", "TEXT", 0, 0),
    ],
    "finding_assessments": [
        ("id", "TEXT", 1, 1), ("finding_id", "TEXT", 1, 0), ("result", "TEXT", 1, 0),
    ],
    "provider_cooldowns": [
        ("provider", "TEXT", 1, 1), ("not_before", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
    ],
    "cleanup_runs": [
        ("id", "TEXT", 1, 1), ("created_at", "TEXT", 1, 0), ("cutoff", "TEXT", 1, 0),
        ("deleted_count", "INTEGER", 1, 0), ("token", "TEXT", 1, 0), ("backup", "TEXT", 1, 0),
    ],
    "notifications": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("finding_id", "TEXT", 1, 0), ("event_type", "TEXT", 1, 0),
        ("origin", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("read_at", "TEXT", 0, 0),
    ],
    "monitor_runs": [
        ("id", "TEXT", 1, 1), ("targets", "TEXT", 1, 0),
        ("providers", "TEXT", 1, 0), ("typos", "INTEGER", 1, 0),
        ("rule_version", "TEXT", 1, 0), ("max_cycles", "INTEGER", 1, 0),
        ("interval_seconds", "INTEGER", 1, 0), ("max_duration_seconds", "INTEGER", 1, 0),
        ("status", "TEXT", 1, 0), ("started_at", "TEXT", 1, 0),
        ("finished_at", "TEXT", 0, 0), ("elapsed_seconds", "REAL", 0, 0),
        ("stop_reason", "TEXT", 0, 0),
    ],
    "monitor_jobs": [
        ("run_id", "TEXT", 1, 1), ("cycle", "INTEGER", 1, 2),
        ("provider", "TEXT", 1, 3), ("job_id", "TEXT", 1, 0),
    ],
    "allowlist_entries": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("asset_value", "TEXT", 1, 0), ("domain", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("expires_at", "TEXT", 0, 0),
        ("reason", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "allowlist_events": [
        ("id", "TEXT", 1, 1), ("entry_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("expires_at", "TEXT", 0, 0),
        ("reason", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0),
    ],
    "surface_scopes": [
        ("asset_id", "TEXT", 1, 1), ("asset_value", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("reason", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "surface_scope_events": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0),
    ],
    "surface_checks": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("result", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
        ("change", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "surface_candidates": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("asset_value", "TEXT", 1, 0), ("domain", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("first_seen_at", "TEXT", 1, 0), ("last_seen_at", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "surface_candidate_sources": [
        ("id", "TEXT", 1, 1), ("candidate_id", "TEXT", 1, 0),
        ("provider", "TEXT", 1, 0), ("source_name", "TEXT", 1, 0),
        ("source_sha256", "TEXT", 1, 0), ("raw_domain", "TEXT", 1, 0),
        ("observed_at", "TEXT", 0, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "surface_candidate_events": [
        ("id", "TEXT", 1, 1), ("candidate_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
    ],
    "surface_discovery_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("asset_id", "TEXT", 1, 0), ("asset_value", "TEXT", 1, 0),
        ("provider", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("source_url", "TEXT", 1, 0), ("started_at", "TEXT", 1, 0),
        ("finished_at", "TEXT", 1, 0), ("record_count", "INTEGER", 1, 0),
        ("skipped_names", "INTEGER", 1, 0), ("ignored_names", "INTEGER", 1, 0),
        ("warnings", "TEXT", 1, 0), ("candidate_count", "INTEGER", 1, 0),
        ("candidates_created", "INTEGER", 1, 0),
        ("candidates_existing", "INTEGER", 1, 0),
        ("evidence_created", "INTEGER", 1, 0),
        ("evidence_existing", "INTEGER", 1, 0), ("error", "TEXT", 0, 0),
    ],
    "surface_candidate_notifications": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("candidate_id", "TEXT", 1, 0), ("event_type", "TEXT", 1, 0),
        ("origin", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("read_at", "TEXT", 0, 0),
    ],
    "surface_mail_checks": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("result", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
        ("change", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "surface_service_checks": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("authorization_reason", "TEXT", 1, 0), ("result", "TEXT", 1, 0),
        ("state_sha256", "TEXT", 1, 0), ("change", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "surface_nmap_checks": [
        ("id", "TEXT", 1, 1), ("execution_id", "TEXT", 1, 0),
        ("asset_id", "TEXT", 1, 0),
        ("authorization_reason", "TEXT", 1, 0), ("result", "TEXT", 1, 0),
        ("state_sha256", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "surface_cname_checks": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("result", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
        ("change", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "surface_change_notifications": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("surface_check_id", "TEXT", 0, 0), ("mail_check_id", "TEXT", 0, 0),
        ("service_check_id", "TEXT", 0, 0), ("event_type", "TEXT", 1, 0),
        ("origin", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("read_at", "TEXT", 0, 0),
    ],
    "vulnerability_source_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("source", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("source_url", "TEXT", 1, 0), ("source_version", "TEXT", 0, 0),
        ("source_timestamp", "TEXT", 0, 0), ("content_sha256", "TEXT", 0, 0),
        ("started_at", "TEXT", 1, 0), ("finished_at", "TEXT", 1, 0),
        ("record_count", "INTEGER", 1, 0), ("created_count", "INTEGER", 1, 0),
        ("updated_count", "INTEGER", 1, 0), ("unchanged_count", "INTEGER", 1, 0),
        ("deactivated_count", "INTEGER", 1, 0),
        ("reactivated_count", "INTEGER", 1, 0), ("error", "TEXT", 0, 0),
    ],
    "kev_entries": [
        ("cve_id", "TEXT", 1, 1), ("state", "TEXT", 1, 0),
        ("state_sha256", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("first_seen_at", "TEXT", 1, 0), ("last_seen_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0), ("latest_run_id", "TEXT", 1, 0),
    ],
    "kev_entry_events": [
        ("id", "TEXT", 1, 1), ("cve_id", "TEXT", 1, 0),
        ("run_id", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("state", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "epss_scores": [
        ("cve_id", "TEXT", 1, 1), ("epss", "TEXT", 1, 0),
        ("percentile", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("model_version", "TEXT", 1, 0),
        ("score_date", "TEXT", 1, 0), ("first_seen_at", "TEXT", 1, 0),
        ("last_seen_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
        ("latest_run_id", "TEXT", 1, 0),
    ],
    "nvd_cve_records": [
        ("cve_id", "TEXT", 1, 1), ("state", "TEXT", 1, 0),
        ("record_json", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
        ("first_seen_at", "TEXT", 1, 0), ("last_seen_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0), ("latest_run_id", "TEXT", 1, 0),
    ],
    "nvd_cve_events": [
        ("id", "TEXT", 1, 1), ("cve_id", "TEXT", 1, 0),
        ("run_id", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("state", "TEXT", 1, 0), ("record_json", "TEXT", 1, 0),
        ("state_sha256", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "nvd_window_syncs": [
        ("id", "TEXT", 1, 1), ("window_start", "TEXT", 1, 0),
        ("window_end", "TEXT", 1, 0), ("page_size", "INTEGER", 1, 0),
        ("next_start_index", "INTEGER", 1, 0),
        ("total_results", "INTEGER", 0, 0), ("status", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
        ("last_success_at", "TEXT", 0, 0), ("last_error", "TEXT", 0, 0),
        ("latest_run_id", "TEXT", 0, 0),
    ],
    "nvd_window_restart_events": [
        ("id", "TEXT", 1, 1), ("sync_id", "TEXT", 1, 0),
        ("previous_next_start_index", "INTEGER", 1, 0),
        ("previous_total_results", "INTEGER", 0, 0),
        ("previous_status", "TEXT", 1, 0),
        ("previous_last_success_at", "TEXT", 0, 0),
        ("previous_last_error", "TEXT", 0, 0),
        ("previous_latest_run_id", "TEXT", 0, 0),
        ("reason", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "asset_products": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("asset_value", "TEXT", 1, 0), ("part", "TEXT", 1, 0),
        ("vendor", "TEXT", 1, 0), ("product", "TEXT", 1, 0),
        ("version", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("evidence_type", "TEXT", 1, 0), ("evidence", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "asset_product_events": [
        ("id", "TEXT", 1, 1), ("asset_product_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("evidence_type", "TEXT", 1, 0),
        ("evidence", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "asset_packages": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("asset_value", "TEXT", 1, 0), ("provider", "TEXT", 1, 0),
        ("ecosystem", "TEXT", 1, 0), ("name", "TEXT", 1, 0),
        ("epoch", "INTEGER", 1, 0), ("version", "TEXT", 1, 0),
        ("release", "TEXT", 1, 0), ("architecture", "TEXT", 1, 0),
        ("source_rpm", "TEXT", 0, 0), ("distribution_cpe", "TEXT", 1, 0),
        ("purl", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("evidence_type", "TEXT", 1, 0), ("evidence", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "asset_package_events": [
        ("id", "TEXT", 1, 1), ("asset_package_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("source_rpm", "TEXT", 0, 0),
        ("evidence_type", "TEXT", 1, 0), ("evidence", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "ubuntu_asset_packages": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("asset_value", "TEXT", 1, 0), ("ecosystem", "TEXT", 1, 0),
        ("binary_name", "TEXT", 1, 0), ("binary_version", "TEXT", 1, 0),
        ("architecture", "TEXT", 1, 0), ("source_name", "TEXT", 1, 0),
        ("source_version", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("evidence_type", "TEXT", 1, 0), ("evidence", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "ubuntu_asset_package_events": [
        ("id", "TEXT", 1, 1), ("ubuntu_package_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("evidence_type", "TEXT", 1, 0),
        ("evidence", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "vulnerability_exposures": [
        ("id", "TEXT", 1, 1), ("asset_product_id", "TEXT", 1, 0),
        ("cve_id", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("suppressed", "INTEGER", 1, 0),
        ("recheck_at", "TEXT", 0, 0), ("assessment_status", "TEXT", 1, 0),
        ("nvd_source_record_sha256", "TEXT", 1, 0),
        ("product_evidence_updated_at", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "vulnerability_exposure_events": [
        ("id", "TEXT", 1, 1), ("exposure_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("suppressed", "INTEGER", 1, 0),
        ("recheck_at", "TEXT", 0, 0), ("assessment_status", "TEXT", 1, 0),
        ("nvd_source_record_sha256", "TEXT", 1, 0),
        ("product_evidence_updated_at", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "vulnerability_exposure_suppressions": [
        ("id", "TEXT", 1, 1), ("exposure_id", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("expires_at", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "vulnerability_exposure_suppression_events": [
        ("id", "TEXT", 1, 1), ("suppression_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("expires_at", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "vulnerability_reassessment_runs": [
        ("id", "TEXT", 1, 1), ("include_closed", "INTEGER", 1, 0),
        ("include_suppressed", "INTEGER", 1, 0),
        ("examined_count", "INTEGER", 1, 0),
        ("candidate_count", "INTEGER", 1, 0),
        ("selected_count", "INTEGER", 1, 0),
        ("truncated", "INTEGER", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "vulnerability_reassessment_items": [
        ("id", "TEXT", 1, 1), ("run_id", "TEXT", 1, 0),
        ("exposure_id", "TEXT", 1, 0), ("asset_value", "TEXT", 1, 0),
        ("cve_id", "TEXT", 1, 0), ("decision_status", "TEXT", 1, 0),
        ("previous_assessment_status", "TEXT", 1, 0),
        ("current_assessment_status", "TEXT", 1, 0),
        ("triggers", "TEXT", 1, 0),
        ("nvd_source_record_sha256", "TEXT", 1, 0),
        ("product_evidence_updated_at", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "vulnerability_change_notifications": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("exposure_id", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
        ("triggers", "TEXT", 1, 0), ("asset_value", "TEXT", 1, 0),
        ("cve_id", "TEXT", 1, 0), ("decision_status", "TEXT", 1, 0),
        ("product_active", "INTEGER", 1, 0), ("recheck_at", "TEXT", 0, 0),
        ("nvd_source_record_sha256", "TEXT", 1, 0),
        ("product_evidence_updated_at", "TEXT", 1, 0),
        ("event_type", "TEXT", 1, 0), ("origin", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("read_at", "TEXT", 0, 0),
    ],
    "vulnerability_exposure_evidence": [
        ("id", "TEXT", 1, 1), ("exposure_id", "TEXT", 1, 0),
        ("evidence_type", "TEXT", 1, 0), ("source_reference", "TEXT", 1, 0),
        ("summary", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "vulnerability_exposure_evidence_events": [
        ("id", "TEXT", 1, 1), ("evidence_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("summary", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "vulnerability_vendor_package_evidence": [
        ("id", "TEXT", 1, 1), ("exposure_id", "TEXT", 1, 0),
        ("asset_package_id", "TEXT", 1, 0), ("provider", "TEXT", 1, 0),
        ("cve_id", "TEXT", 1, 0), ("source_url", "TEXT", 1, 0),
        ("source_sha256", "TEXT", 1, 0), ("document_version", "TEXT", 1, 0),
        ("current_release_at", "TEXT", 1, 0), ("vendor_status", "TEXT", 1, 0),
        ("match_kind", "TEXT", 1, 0), ("vex_product_id", "TEXT", 1, 0),
        ("component_product_id", "TEXT", 1, 0), ("component_purl", "TEXT", 1, 0),
        ("context_product_id", "TEXT", 1, 0), ("context_cpe", "TEXT", 1, 0),
        ("package_updated_at", "TEXT", 1, 0), ("summary", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "vulnerability_vendor_package_evidence_events": [
        ("id", "TEXT", 1, 1), ("evidence_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("summary", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "vulnerability_remediations": [
        ("id", "TEXT", 1, 1), ("exposure_id", "TEXT", 1, 0),
        ("recommendation", "TEXT", 1, 0), ("source_type", "TEXT", 1, 0),
        ("source_reference", "TEXT", 1, 0), ("state", "TEXT", 1, 0),
        ("latest_outcome", "TEXT", 1, 0), ("recheck_at", "TEXT", 0, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "vulnerability_remediation_events": [
        ("id", "TEXT", 1, 1), ("remediation_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("state", "TEXT", 1, 0),
        ("outcome", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("evidence_reference", "TEXT", 1, 0), ("recheck_at", "TEXT", 0, 0),
        ("exposure_status", "TEXT", 1, 0),
        ("nvd_source_record_sha256", "TEXT", 1, 0),
        ("product_evidence_updated_at", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "cti_indicators": [
        ("id", "TEXT", 1, 1), ("indicator_type", "TEXT", 1, 0),
        ("value", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "cti_indicator_assertions": [
        ("id", "TEXT", 1, 1), ("indicator_id", "TEXT", 1, 0),
        ("source_name", "TEXT", 1, 0), ("source_reference", "TEXT", 1, 0),
        ("confidence", "INTEGER", 1, 0), ("valid_from", "TEXT", 0, 0),
        ("valid_until", "TEXT", 0, 0), ("active", "INTEGER", 1, 0),
        ("description", "TEXT", 1, 0), ("first_seen_at", "TEXT", 1, 0),
        ("last_seen_at", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "cti_indicator_assertion_events": [
        ("id", "TEXT", 1, 1), ("assertion_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("confidence", "INTEGER", 1, 0),
        ("valid_from", "TEXT", 0, 0), ("valid_until", "TEXT", 0, 0),
        ("description", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("observed_at", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "cti_feed_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("source_name", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("source_url", "TEXT", 1, 0), ("content_sha256", "TEXT", 0, 0),
        ("started_at", "TEXT", 1, 0), ("finished_at", "TEXT", 1, 0),
        ("source_record_count", "INTEGER", 1, 0),
        ("indicator_count", "INTEGER", 1, 0), ("added_count", "INTEGER", 1, 0),
        ("observed_count", "INTEGER", 1, 0), ("updated_count", "INTEGER", 1, 0),
        ("unchanged_count", "INTEGER", 1, 0),
        ("reactivated_count", "INTEGER", 1, 0),
        ("revoked_count", "INTEGER", 1, 0), ("error", "TEXT", 0, 0),
    ],
    "cti_feed_run_items": [
        ("id", "TEXT", 1, 1), ("run_id", "TEXT", 1, 0),
        ("assertion_id", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("state_sha256", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "ransomware_claim_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("source_name", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("source_url", "TEXT", 1, 0), ("content_sha256", "TEXT", 0, 0),
        ("started_at", "TEXT", 1, 0), ("finished_at", "TEXT", 1, 0),
        ("fetched_at", "TEXT", 0, 0), ("generated_at", "TEXT", 0, 0),
        ("window_days", "INTEGER", 0, 0),
        ("source_record_count", "INTEGER", 1, 0),
        ("claim_count", "INTEGER", 1, 0), ("added_count", "INTEGER", 1, 0),
        ("updated_count", "INTEGER", 1, 0),
        ("unchanged_count", "INTEGER", 1, 0),
        ("removed_count", "INTEGER", 1, 0), ("error", "TEXT", 0, 0),
    ],
    "ransomware_claim_run_items": [
        ("id", "TEXT", 1, 1), ("run_id", "TEXT", 1, 0),
        ("claim_id", "TEXT", 1, 0), ("group_name", "TEXT", 1, 0),
        ("victim", "TEXT", 1, 0), ("country", "TEXT", 0, 0),
        ("sector", "TEXT", 0, 0), ("discovered_at", "TEXT", 1, 0),
        ("claim_status", "TEXT", 1, 0), ("website", "TEXT", 0, 0),
        ("last_seen_at", "TEXT", 0, 0), ("delisted_at", "TEXT", 0, 0),
        ("first_party", "INTEGER", 0, 0),
        ("source_post_available", "INTEGER", 1, 0),
        ("action", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
    ],
    "ransomlook_claim_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("source_name", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("source_url", "TEXT", 1, 0), ("content_sha256", "TEXT", 0, 0),
        ("started_at", "TEXT", 1, 0), ("finished_at", "TEXT", 1, 0),
        ("fetched_at", "TEXT", 0, 0), ("window_days", "INTEGER", 0, 0),
        ("source_record_count", "INTEGER", 1, 0),
        ("claim_count", "INTEGER", 1, 0), ("added_count", "INTEGER", 1, 0),
        ("updated_count", "INTEGER", 1, 0),
        ("unchanged_count", "INTEGER", 1, 0),
        ("removed_count", "INTEGER", 1, 0), ("error", "TEXT", 0, 0),
    ],
    "ransomlook_claim_run_items": [
        ("id", "TEXT", 1, 1), ("run_id", "TEXT", 1, 0),
        ("claim_id", "TEXT", 1, 0), ("group_name", "TEXT", 1, 0),
        ("victim", "TEXT", 1, 0), ("discovered_at", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
    ],
    "ransomlook_watches": [
        ("id", "TEXT", 1, 1), ("name_key", "TEXT", 1, 0),
        ("display_name", "TEXT", 1, 0), ("query", "TEXT", 1, 0),
        ("query_key", "TEXT", 1, 0), ("match_mode", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "ransomlook_watch_events": [
        ("id", "TEXT", 1, 1), ("watch_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("definition_sha256", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "ransomlook_watch_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("watch_id", "TEXT", 1, 0), ("source_run_id", "TEXT", 1, 0),
        ("definition_sha256", "TEXT", 1, 0),
        ("previous_run_id", "TEXT", 0, 0), ("executed_at", "TEXT", 1, 0),
        ("total_count", "INTEGER", 1, 0), ("added_count", "INTEGER", 1, 0),
        ("updated_count", "INTEGER", 1, 0),
        ("unchanged_count", "INTEGER", 1, 0),
        ("removed_count", "INTEGER", 1, 0), ("result_sha256", "TEXT", 1, 0),
    ],
    "ransomlook_watch_run_items": [
        ("id", "TEXT", 1, 1), ("run_id", "TEXT", 1, 0),
        ("claim_id", "TEXT", 1, 0), ("group_name", "TEXT", 1, 0),
        ("victim", "TEXT", 1, 0), ("discovered_at", "TEXT", 1, 0),
        ("matched_value", "TEXT", 1, 0), ("match_type", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("state_sha256", "TEXT", 1, 0),
    ],
    "brand_username_watches": [
        ("id", "TEXT", 1, 1), ("name_key", "TEXT", 1, 0),
        ("display_name", "TEXT", 1, 0), ("username", "TEXT", 1, 0),
        ("platforms_json", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
        ("source_key", "TEXT", 1, 0),
    ],
    "brand_username_watch_events": [
        ("id", "TEXT", 1, 1), ("watch_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("definition_sha256", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "brand_username_watch_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("watch_id", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("source_name", "TEXT", 1, 0), ("source_version", "TEXT", 1, 0),
        ("integration_profile", "TEXT", 1, 0), ("username", "TEXT", 1, 0),
        ("platforms_json", "TEXT", 1, 0),
        ("definition_sha256", "TEXT", 1, 0),
        ("previous_complete_run_id", "TEXT", 0, 0),
        ("checked_at", "TEXT", 0, 0), ("recorded_at", "TEXT", 1, 0),
        ("platform_count", "INTEGER", 1, 0),
        ("found_count", "INTEGER", 1, 0),
        ("newly_found_count", "INTEGER", 1, 0),
        ("changed_count", "INTEGER", 1, 0),
        ("unchanged_found_count", "INTEGER", 1, 0),
        ("no_longer_reported_count", "INTEGER", 1, 0),
        ("unreported_count", "INTEGER", 1, 0),
        ("result_sha256", "TEXT", 0, 0), ("error", "TEXT", 0, 0),
    ],
    "brand_username_watch_run_items": [
        ("id", "TEXT", 1, 1), ("run_id", "TEXT", 1, 0),
        ("platform", "TEXT", 1, 0), ("profile_url", "TEXT", 0, 0),
        ("result_status", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("state_sha256", "TEXT", 1, 0),
    ],
    "brand_username_review_events": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("candidate_id", "TEXT", 1, 0), ("watch_id", "TEXT", 1, 0),
        ("run_id", "TEXT", 1, 0), ("platform", "TEXT", 1, 0),
        ("candidate_json", "TEXT", 1, 0),
        ("candidate_sha256", "TEXT", 1, 0),
        ("decision", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0), ("previous_event_id", "TEXT", 0, 0),
    ],
    "brand_username_review_notifications": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("candidate_id", "TEXT", 1, 0), ("review_event_id", "TEXT", 1, 0),
        ("event_type", "TEXT", 1, 0), ("origin", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("read_at", "TEXT", 0, 0),
    ],
    "ransomware_watches": [
        ("id", "TEXT", 1, 1), ("name_key", "TEXT", 1, 0),
        ("display_name", "TEXT", 1, 0), ("kind", "TEXT", 1, 0),
        ("query", "TEXT", 1, 0), ("query_key", "TEXT", 1, 0),
        ("match_mode", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "ransomware_watch_events": [
        ("id", "TEXT", 1, 1), ("watch_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("definition_sha256", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "ransomware_watch_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("watch_id", "TEXT", 1, 0), ("source_run_id", "TEXT", 1, 0),
        ("definition_sha256", "TEXT", 1, 0), ("previous_run_id", "TEXT", 0, 0),
        ("executed_at", "TEXT", 1, 0), ("total_count", "INTEGER", 1, 0),
        ("added_count", "INTEGER", 1, 0), ("updated_count", "INTEGER", 1, 0),
        ("unchanged_count", "INTEGER", 1, 0), ("removed_count", "INTEGER", 1, 0),
        ("result_sha256", "TEXT", 1, 0),
    ],
    "ransomware_watch_run_items": [
        ("id", "TEXT", 1, 1), ("run_id", "TEXT", 1, 0),
        ("claim_id", "TEXT", 1, 0), ("group_name", "TEXT", 1, 0),
        ("victim", "TEXT", 1, 0), ("country", "TEXT", 0, 0),
        ("sector", "TEXT", 0, 0), ("discovered_at", "TEXT", 1, 0),
        ("claim_status", "TEXT", 1, 0), ("website", "TEXT", 0, 0),
        ("last_seen_at", "TEXT", 0, 0), ("delisted_at", "TEXT", 0, 0),
        ("first_party", "INTEGER", 0, 0),
        ("source_post_available", "INTEGER", 1, 0),
        ("matched_field", "TEXT", 1, 0), ("matched_value", "TEXT", 1, 0),
        ("match_type", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("state_sha256", "TEXT", 1, 0),
    ],
    "ransomware_watch_notifications": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("run_id", "TEXT", 1, 0), ("watch_id", "TEXT", 1, 0),
        ("event_type", "TEXT", 1, 0), ("origin", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("read_at", "TEXT", 0, 0),
    ],
    "ransomware_monitor_sessions": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0), ("started_at", "TEXT", 1, 0),
        ("finished_at", "TEXT", 0, 0), ("stop_reason", "TEXT", 1, 0),
        ("planned_cycles", "INTEGER", 1, 0),
        ("interval_seconds", "INTEGER", 1, 0),
        ("max_duration_seconds", "INTEGER", 1, 0),
        ("max_watches", "INTEGER", 1, 0),
        ("source_item_limit", "INTEGER", 1, 0),
        ("watch_item_limit", "INTEGER", 1, 0),
        ("error", "TEXT", 1, 0),
    ],
    "ransomware_monitor_cycles": [
        ("id", "TEXT", 1, 1), ("session_id", "TEXT", 1, 0),
        ("cycle", "INTEGER", 1, 0), ("source_run_id", "TEXT", 1, 0),
        ("planned_watch_count", "INTEGER", 1, 0),
        ("completed_watch_count", "INTEGER", 1, 0),
        ("baseline_watch_count", "INTEGER", 1, 0),
        ("total_count", "INTEGER", 1, 0),
        ("added_count", "INTEGER", 1, 0),
        ("updated_count", "INTEGER", 1, 0),
        ("unchanged_count", "INTEGER", 1, 0),
        ("removed_count", "INTEGER", 1, 0),
        ("notification_count", "INTEGER", 1, 0),
    ],
    "ransomware_monitor_cycle_watch_runs": [
        ("id", "TEXT", 1, 1), ("cycle_id", "TEXT", 1, 0),
        ("position", "INTEGER", 1, 0), ("watch_run_id", "TEXT", 1, 0),
    ],
    "ransomware_identity_review_events": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("candidate_id", "TEXT", 1, 0), ("watch_id", "TEXT", 1, 0),
        ("transition_source_run_id", "TEXT", 1, 0),
        ("older_claim_id", "TEXT", 1, 0),
        ("newer_claim_id", "TEXT", 1, 0),
        ("candidate_json", "TEXT", 1, 0),
        ("candidate_sha256", "TEXT", 1, 0),
        ("decision", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
        ("previous_event_id", "TEXT", 0, 0),
    ],
    "ransomware_source_review_events": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("comparison_id", "TEXT", 1, 0),
        ("threatcluster_run_id", "TEXT", 1, 0),
        ("ransomlook_run_id", "TEXT", 1, 0),
        ("threatcluster_claim_id", "TEXT", 1, 0),
        ("ransomlook_claim_id", "TEXT", 1, 0),
        ("evidence_json", "TEXT", 1, 0),
        ("evidence_sha256", "TEXT", 1, 0),
        ("decision", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
        ("previous_event_id", "TEXT", 0, 0),
    ],
    "cti_entities": [
        ("id", "TEXT", 1, 1), ("entity_type", "TEXT", 1, 0),
        ("name_key", "TEXT", 1, 0), ("display_name", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "cti_entity_assertions": [
        ("id", "TEXT", 1, 1), ("entity_id", "TEXT", 1, 0),
        ("source_name", "TEXT", 1, 0), ("source_reference", "TEXT", 1, 0),
        ("confidence", "INTEGER", 1, 0), ("aliases_json", "TEXT", 1, 0),
        ("description", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("first_seen_at", "TEXT", 1, 0), ("last_seen_at", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "cti_entity_assertion_events": [
        ("id", "TEXT", 1, 1), ("assertion_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("confidence", "INTEGER", 1, 0),
        ("aliases_json", "TEXT", 1, 0), ("description", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("observed_at", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "cti_relationships": [
        ("id", "TEXT", 1, 1), ("source_entity_id", "TEXT", 1, 0),
        ("relationship_type", "TEXT", 1, 0), ("target_kind", "TEXT", 1, 0),
        ("target_entity_id", "TEXT", 0, 0),
        ("target_indicator_id", "TEXT", 0, 0), ("target_key", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "cti_relationship_assertions": [
        ("id", "TEXT", 1, 1), ("relationship_id", "TEXT", 1, 0),
        ("source_name", "TEXT", 1, 0), ("source_reference", "TEXT", 1, 0),
        ("confidence", "INTEGER", 1, 0), ("description", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("first_seen_at", "TEXT", 1, 0),
        ("last_seen_at", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "cti_relationship_assertion_events": [
        ("id", "TEXT", 1, 1), ("assertion_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("confidence", "INTEGER", 1, 0),
        ("description", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("observed_at", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "cti_saved_searches": [
        ("id", "TEXT", 1, 1), ("name_key", "TEXT", 1, 0),
        ("display_name", "TEXT", 1, 0), ("query", "TEXT", 1, 0),
        ("query_key", "TEXT", 1, 0), ("kind", "TEXT", 1, 0),
        ("entity_type", "TEXT", 0, 0), ("indicator_type", "TEXT", 0, 0),
        ("active_only", "INTEGER", 1, 0), ("active", "INTEGER", 1, 0),
        ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "cti_saved_search_events": [
        ("id", "TEXT", 1, 1), ("saved_search_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("definition_sha256", "TEXT", 1, 0),
        ("reason", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "cti_saved_search_runs": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("saved_search_id", "TEXT", 1, 0),
        ("definition_sha256", "TEXT", 1, 0),
        ("previous_run_id", "TEXT", 0, 0), ("executed_at", "TEXT", 1, 0),
        ("total_count", "INTEGER", 1, 0), ("added_count", "INTEGER", 1, 0),
        ("updated_count", "INTEGER", 1, 0),
        ("unchanged_count", "INTEGER", 1, 0),
        ("removed_count", "INTEGER", 1, 0), ("result_sha256", "TEXT", 1, 0),
    ],
    "cti_saved_search_run_items": [
        ("id", "TEXT", 1, 1), ("run_id", "TEXT", 1, 0),
        ("kind", "TEXT", 1, 0), ("record_id", "TEXT", 1, 0),
        ("record_type", "TEXT", 1, 0), ("display_value", "TEXT", 1, 0),
        ("matched_field", "TEXT", 1, 0), ("matched_value", "TEXT", 1, 0),
        ("match_type", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("state_sha256", "TEXT", 1, 0),
    ],
    "cti_saved_search_notifications": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("run_id", "TEXT", 1, 0), ("saved_search_id", "TEXT", 1, 0),
        ("event_type", "TEXT", 1, 0), ("origin", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("read_at", "TEXT", 0, 0),
    ],
    "cti_saved_search_tags": [
        ("saved_search_id", "TEXT", 1, 1), ("tag_key", "TEXT", 1, 2),
        ("display_tag", "TEXT", 1, 0), ("active", "INTEGER", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "cti_saved_search_tag_events": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("saved_search_id", "TEXT", 1, 0), ("tag_key", "TEXT", 1, 0),
        ("display_tag", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "cti_saved_search_notes": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("saved_search_id", "TEXT", 1, 0), ("run_id", "TEXT", 0, 0),
        ("note_kind", "TEXT", 1, 0), ("body", "TEXT", 1, 0),
        ("recorded_at", "TEXT", 1, 0),
    ],
    "webhook_destinations": [
        ("id", "TEXT", 1, 1), ("name_key", "TEXT", 1, 0),
        ("display_name", "TEXT", 1, 0), ("url", "TEXT", 1, 0),
        ("endpoint", "TEXT", 1, 0), ("secret_b64", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ],
    "webhook_destination_events": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("destination_id", "TEXT", 1, 0), ("action", "TEXT", 1, 0),
        ("endpoint", "TEXT", 1, 0), ("recorded_at", "TEXT", 1, 0),
    ],
    "webhook_deliveries": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("destination_id", "TEXT", 1, 0), ("notification_id", "TEXT", 1, 0),
        ("event_type", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
        ("payload_json", "TEXT", 1, 0), ("payload_sha256", "TEXT", 1, 0),
        ("attempt_count", "INTEGER", 1, 0), ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0), ("delivered_at", "TEXT", 0, 0),
        ("last_http_status", "INTEGER", 0, 0), ("last_error", "TEXT", 0, 0),
    ],
    "webhook_delivery_attempts": [
        ("sequence", "INTEGER", 1, 1), ("id", "TEXT", 1, 0),
        ("delivery_id", "TEXT", 1, 0), ("number", "INTEGER", 1, 0),
        ("outcome", "TEXT", 1, 0), ("http_status", "INTEGER", 0, 0),
        ("error", "TEXT", 0, 0), ("attempted_at", "TEXT", 1, 0),
    ],
}

ALLOWLIST_V8_TABLES = {
    "allowlist_entries": [
        ("id", "TEXT", 1, 1), ("asset_id", "TEXT", 1, 0),
        ("asset_value", "TEXT", 1, 0), ("domain", "TEXT", 1, 0),
        ("active", "INTEGER", 1, 0), ("reason", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "allowlist_events": [
        ("id", "TEXT", 1, 1), ("entry_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0), ("reason", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0),
    ],
}

UNIQUE_KEYS = {
    **supplier_watch_schema_metadata.UNIQUE_KEYS,
    **global_saved_search_schema_metadata.UNIQUE_KEYS,
    **news_schema_metadata.UNIQUE_KEYS,
    **mentions_schema_metadata.UNIQUE_KEYS,
    **mention_group_schema_metadata.UNIQUE_KEYS,
    **nmap_management_schema_metadata.UNIQUE_KEYS,
    **nmap_jobs_schema.UNIQUE_KEYS,
    **warninglist_schema.UNIQUE_KEYS,
    **enrichment_schema.UNIQUE_KEYS,
    **research_history_schema.UNIQUE_KEYS,
    **investigation_schema.UNIQUE_KEYS,
    **report_schema.UNIQUE_KEYS,
    **evidence_schema.UNIQUE_KEYS,
    **document_storage_schema.UNIQUE_KEYS,
    **relationship_notification_schema.UNIQUE_KEYS,
    **social_discovery_schema.UNIQUE_KEYS,
    **social_enrichment_schema.UNIQUE_KEYS,
    **social_tracking_schema.UNIQUE_KEYS,
    **group_schema.UNIQUE_KEYS,
    **group_operations_schema.UNIQUE_KEYS,
    'public_notice_watches': {('organization_id',), ('id',)},
    'public_notice_watch_events': {('id',), ('watch_id', 'revision')},
    'public_notice_watch_runs': {('id',), ('watch_id', 'source_run_id')},
    'public_notice_watch_notifications': {('id',), ('run_id',)},
    'public_notice_runs': {('id',)},
    'public_notice_changes': {('run_id', 'notice_id')},
    'ransomlook_watch_notifications': {('run_id',), ('id',)},
    'attack_catalog_runs': {('id',)},
    'attack_catalog_entities': {('stix_id',), ('external_id',)},
    'attack_catalog_relationships': {('stix_id',)},
    'attack_catalog_phases': {('id',), ('technique_stix_id', 'tactic_stix_id')},
    'attack_catalog_changes': {('run_id', 'record_kind', 'record_key')},

    'organizations': {('name_key',), ('id',)},
    'organization_events': {('id',), ('organization_id', 'revision')},
    'organization_links': {('id',), ('organization_id', 'target_kind', 'target_value')},
    'organization_link_events': {('id',), ('link_id', 'revision')},
    'collection_sessions': {('id',), ('parent_id',), ('root_id', 'generation')},
    'collection_session_steps': {('session_id', 'ordinal'), ('session_id', 'step_key'), ('id',), ('scan_job_id',)},
    'collection_step_receipts': {('news_run_id',), ('saved_search_run_id',), ('public_notice_run_id',), ('threatcluster_watch_run_id',), ('username_run_id',), ('scan_attempt_id',), ('discovery_run_id',), ('ransomlook_source_run_id',), ('ransomlook_watch_run_id',), ('threatcluster_source_run_id',), ('step_id',), ('feed_run_id',)},

    "collection_profiles": {("id",), ("name_key",)},
    "collection_profile_events": {("id",), ("profile_id", "revision")},
    "assets": {("id",), ("value",)},
    "asset_criticalities": {("asset_id",), ("asset_value",)},
    "asset_criticality_events": {("id",)},
    "suppliers": {("id",), ("primary_domain",)},
    "supplier_events": {("id",)},
    "supplier_candidates": {("id",), ("asset_id", "candidate_domain")},
    "supplier_candidate_evidence": {("id",), ("derivation_key",)},
    "supplier_candidate_resolution_events": {("id",)},
    "cases": {("id",)},
    "case_evidence": {("id",), ("case_id", "evidence_type", "evidence_id")},
    "case_tasks": {("id",)},
    "case_activities": {("id",)},
    "observations": {("id",), ("source_sha256", "source_line")},
    "findings": {("id",), ("asset_id", "domain", "rule_version")},
    "finding_observations": {("finding_id", "observation_id")},
    "reviews": {("id",)},
    "scan_jobs": {("id",)},
    "scan_attempts": {("id",), ("job_id", "number")},
    "finding_assessments": {("id",)},
    "provider_cooldowns": {("provider",)},
    "cleanup_runs": {("id",)},
    # An INTEGER PRIMARY KEY aliases rowid and does not create a unique index.
    "notifications": {("id",), ("finding_id", "event_type")},
    "monitor_runs": {("id",)},
    "monitor_jobs": {("run_id", "cycle", "provider"), ("job_id",)},
    "allowlist_entries": {("id",), ("asset_id", "domain")},
    "allowlist_events": {("id",)},
    "surface_scopes": {("asset_id",), ("asset_value",)},
    "surface_scope_events": {("id",)},
    "surface_checks": {("id",)},
    "surface_candidates": {("id",), ("asset_id", "domain")},
    "surface_candidate_sources": {("id",), ("candidate_id", "source_sha256")},
    "surface_candidate_events": {("id",)},
    # INTEGER PRIMARY KEY fields alias rowid and do not create unique indexes.
    "surface_discovery_runs": {("id",)},
    "surface_candidate_notifications": {("id",), ("candidate_id",)},
    "surface_mail_checks": {("id",)},
    "surface_service_checks": {("id",)},
    "surface_nmap_checks": {("id",)},
    "surface_cname_checks": {("id",)},
    "surface_change_notifications": {
        ("id",), ("surface_check_id",), ("mail_check_id",), ("service_check_id",),
    },
    "vulnerability_source_runs": {("id",)},
    "kev_entries": {("cve_id",)},
    "kev_entry_events": {("id",), ("cve_id", "run_id")},
    "epss_scores": {("cve_id",)},
    "nvd_cve_records": {("cve_id",)},
    "nvd_cve_events": {("id",), ("cve_id", "run_id")},
    "nvd_window_syncs": {
        ("id",), ("window_start", "window_end", "page_size"),
    },
    "nvd_window_restart_events": {("id",)},
    "asset_products": {("id",), ("asset_id", "part", "vendor", "product", "version")},
    "asset_product_events": {("id",)},
    "asset_packages": {
        ("id",),
        ("asset_id", "provider", "ecosystem", "name", "epoch", "version", "release",
         "architecture", "distribution_cpe"),
    },
    "asset_package_events": {("id",)},
    "ubuntu_asset_packages": {
        ("id",),
        ("asset_id", "ecosystem", "binary_name", "binary_version", "architecture",
         "source_name", "source_version"),
    },
    "ubuntu_asset_package_events": {("id",)},
    "vulnerability_exposures": {("id",), ("asset_product_id", "cve_id")},
    "vulnerability_exposure_events": {("id",)},
    "vulnerability_exposure_suppressions": {("id",), ("exposure_id",)},
    "vulnerability_exposure_suppression_events": {("id",)},
    "vulnerability_reassessment_runs": {("id",)},
    "vulnerability_reassessment_items": {("id",), ("run_id", "exposure_id")},
    "vulnerability_change_notifications": {
        ("id",), ("exposure_id", "state_sha256"),
    },
    "vulnerability_exposure_evidence": {
        ("id",), ("exposure_id", "evidence_type", "source_reference"),
    },
    "vulnerability_exposure_evidence_events": {("id",)},
    "vulnerability_vendor_package_evidence": {
        ("id",),
        ("exposure_id", "asset_package_id", "source_sha256", "vex_product_id", "vendor_status", "package_updated_at"),
    },
    "vulnerability_vendor_package_evidence_events": {("id",)},
    "vulnerability_remediations": {("id",)},
    "vulnerability_remediation_events": {("id",)},
    "cti_indicators": {("id",), ("indicator_type", "value")},
    "cti_indicator_assertions": {
        ("id",), ("indicator_id", "source_name", "source_reference"),
    },
    "cti_indicator_assertion_events": {("id",)},
    "cti_feed_runs": {("id",)},
    "cti_feed_run_items": {("id",), ("run_id", "assertion_id")},
    "ransomware_claim_runs": {("id",)},
    "ransomware_claim_run_items": {("id",), ("run_id", "claim_id")},
    "ransomlook_claim_runs": {("id",)},
    "ransomlook_claim_run_items": {("id",), ("run_id", "claim_id")},
    "ransomlook_watches": {("id",), ("name_key",)},
    "ransomlook_watch_events": {("id",)},
    "ransomlook_watch_runs": {("id",)},
    "ransomlook_watch_run_items": {("id",), ("run_id", "claim_id")},
    "brand_username_watches": {("id",), ("name_key",)},
    "brand_username_watch_events": {("id",)},
    "brand_username_watch_runs": {("id",)},
    "brand_username_watch_run_items": {("id",), ("run_id", "platform")},
    "brand_username_review_events": {("id",)},
    "brand_username_review_notifications": {
        ("id",), ("candidate_id",), ("review_event_id",),
    },
    "ransomware_watches": {("id",), ("name_key",)},
    "ransomware_watch_events": {("id",)},
    "ransomware_watch_runs": {("id",)},
    "ransomware_watch_run_items": {("id",), ("run_id", "claim_id")},
    "ransomware_watch_notifications": {("id",), ("run_id",)},
    "ransomware_monitor_sessions": {("id",)},
    "ransomware_monitor_cycles": {
        ("id",), ("source_run_id",), ("session_id", "cycle"),
    },
    "ransomware_monitor_cycle_watch_runs": {
        ("id",), ("watch_run_id",), ("cycle_id", "position"),
        ("cycle_id", "watch_run_id"),
    },
    "ransomware_identity_review_events": {("id",)},
    "ransomware_source_review_events": {("id",)},
    "cti_entities": {("id",), ("entity_type", "name_key")},
    "cti_entity_assertions": {
        ("id",), ("entity_id", "source_name", "source_reference"),
    },
    "cti_entity_assertion_events": {("id",)},
    "cti_relationships": {
        ("id",), ("source_entity_id", "relationship_type", "target_key"),
    },
    "cti_relationship_assertions": {
        ("id",), ("relationship_id", "source_name", "source_reference"),
    },
    "cti_relationship_assertion_events": {("id",)},
    "cti_saved_searches": {("id",), ("name_key",)},
    "cti_saved_search_events": {("id",)},
    "cti_saved_search_runs": {("id",)},
    "cti_saved_search_run_items": {("id",), ("run_id", "kind", "record_id")},
    "cti_saved_search_notifications": {("id",), ("run_id",)},
    "cti_saved_search_tags": {("saved_search_id", "tag_key")},
    "cti_saved_search_tag_events": {("id",)},
    "cti_saved_search_notes": {("id",)},
    "webhook_destinations": {("id",), ("name_key",)},
    "webhook_destination_events": {("id",)},
    "webhook_deliveries": {("id",), ("destination_id", "notification_id")},
    "webhook_delivery_attempts": {("id",), ("delivery_id", "number")},
}

INDEXES = {
    **supplier_watch_schema_metadata.INDEXES,
    **global_saved_search_schema_metadata.INDEXES,
    **news_schema_metadata.INDEXES,
    **mentions_schema_metadata.INDEXES,
    **mention_group_schema_metadata.INDEXES,
    **nmap_management_schema_metadata.INDEXES,
    **warninglist_schema.INDEXES,
    **enrichment_schema.INDEXES,
    **research_history_schema.INDEXES,
    **investigation_schema.INDEXES,
    **report_schema.INDEXES,
    **evidence_schema.INDEXES,
    **document_storage_schema.INDEXES,
    **relationship_notification_schema.INDEXES,
    **social_discovery_schema.INDEXES,
    **social_enrichment_schema.INDEXES,
    **social_tracking_schema.INDEXES,
    **group_schema.INDEXES,
    **group_operations_schema.INDEXES,
    'public_notice_watches_active_organization': ('public_notice_watches', ('active', 'organization_id')),
    'public_notice_watch_events_watch_sequence': ('public_notice_watch_events', ('watch_id', 'sequence')),
    'public_notice_watch_runs_watch_sequence': ('public_notice_watch_runs', ('watch_id', 'sequence')),
    'public_notice_watch_notifications_read_sequence': ('public_notice_watch_notifications', ('read_at', 'sequence')),
    'public_notice_changes_run_sequence': ('public_notice_changes', ('run_id', 'sequence')),
    'public_notice_changes_notice_sequence': ('public_notice_changes', ('notice_id', 'sequence')),
    'ransomlook_watch_notifications_read_sequence': ('ransomlook_watch_notifications', ('read_at', 'sequence')),
    'attack_catalog_entities_active_external': ('attack_catalog_entities', ('active', 'external_id')),
    'attack_catalog_relationships_target': ('attack_catalog_relationships', ('target_stix_id', 'active')),
    'attack_catalog_relationships_source': ('attack_catalog_relationships', ('source_stix_id', 'active')),
    'attack_catalog_changes_run_sequence': ('attack_catalog_changes', ('run_id', 'sequence')),
    'attack_catalog_changes_record_sequence': ('attack_catalog_changes', ('record_kind', 'record_key', 'sequence')),

    'organizations_active_name': ('organizations', ('active', 'name_key')),
    'organization_events_organization_sequence': ('organization_events', ('organization_id', 'sequence')),
    'organization_links_organization_active_target': ('organization_links', ('organization_id', 'active', 'target_kind', 'target_value')),
    'organization_link_events_link_sequence': ('organization_link_events', ('link_id', 'sequence')),
    'collection_sessions_status_sequence': ('collection_sessions', ('status', 'sequence')),
    'collection_sessions_root_generation': ('collection_sessions', ('root_id', 'generation')),
    'collection_session_steps_session_ordinal': ('collection_session_steps', ('session_id', 'ordinal')),
    'collection_session_steps_scan_job': ('collection_session_steps', ('scan_job_id',)),

    "collection_profiles_active_name": ("collection_profiles", ("active", "name_key")),
    "collection_profile_events_profile_sequence": (
        "collection_profile_events", ("profile_id", "sequence"),
    ),
    "asset_criticality_events_asset_id": (
        "asset_criticality_events", ("asset_id", "recorded_at"),
    ),
    "suppliers_active_name": (
        "suppliers", ("active", "name_key", "primary_domain"),
    ),
    "supplier_events_supplier_sequence": (
        "supplier_events", ("supplier_id", "sequence"),
    ),
    "supplier_candidates_status_current": (
        "supplier_candidates", ("status", "current", "asset_value", "candidate_domain"),
    ),
    "supplier_candidate_evidence_candidate_sequence": (
        "supplier_candidate_evidence", ("candidate_id", "sequence"),
    ),
    "supplier_candidate_resolutions_candidate_sequence": (
        "supplier_candidate_resolution_events", ("candidate_id", "sequence"),
    ),
    "cases_status_priority_updated": (
        "cases", ("status", "priority", "updated_at"),
    ),
    "case_evidence_case_active_updated": (
        "case_evidence", ("case_id", "active", "updated_at"),
    ),
    "case_tasks_case_status_due": (
        "case_tasks", ("case_id", "status", "due_at"),
    ),
    "case_activities_case_sequence": (
        "case_activities", ("case_id", "sequence"),
    ),
    "findings_status": ("findings", ("status",)),
    "reviews_finding_id": ("reviews", ("finding_id",)),
    "finding_observations_observation_id": ("finding_observations", ("observation_id",)),
    "scan_jobs_status_created": ("scan_jobs", ("status", "created_at")),
    "finding_assessments_finding_id": ("finding_assessments", ("finding_id",)),
    "notifications_read_sequence": ("notifications", ("read_at", "sequence")),
    "monitor_runs_status": ("monitor_runs", ("status",)),
    "allowlist_active_asset_domain": (
        "allowlist_entries", ("active", "asset_id", "domain"),
    ),
    "allowlist_events_entry_id": ("allowlist_events", ("entry_id",)),
    "surface_scope_events_asset_id": ("surface_scope_events", ("asset_id",)),
    "surface_checks_asset_id": ("surface_checks", ("asset_id",)),
    "surface_candidates_asset_status": (
        "surface_candidates", ("asset_id", "status", "domain"),
    ),
    "surface_candidate_sources_candidate_id": (
        "surface_candidate_sources", ("candidate_id",),
    ),
    "surface_candidate_events_candidate_id": (
        "surface_candidate_events", ("candidate_id",),
    ),
    "surface_discovery_runs_asset_sequence": (
        "surface_discovery_runs", ("asset_id", "sequence"),
    ),
    "surface_candidate_notifications_read_sequence": (
        "surface_candidate_notifications", ("read_at", "sequence"),
    ),
    "surface_mail_checks_asset_id": ("surface_mail_checks", ("asset_id",)),
    "surface_service_checks_asset_id": ("surface_service_checks", ("asset_id",)),
    "surface_nmap_checks_asset_id": ("surface_nmap_checks", ("asset_id",)),
    "surface_nmap_checks_execution_id": ("surface_nmap_checks", ("execution_id",)),
    "surface_cname_checks_asset_id": ("surface_cname_checks", ("asset_id",)),
    "surface_change_notifications_read_sequence": (
        "surface_change_notifications", ("read_at", "sequence"),
    ),
    "vulnerability_source_runs_source_sequence": (
        "vulnerability_source_runs", ("source", "sequence"),
    ),
    "kev_entries_active_cve": ("kev_entries", ("active", "cve_id")),
    "kev_entry_events_cve_id": ("kev_entry_events", ("cve_id",)),
    "epss_scores_active_cve": ("epss_scores", ("active", "cve_id")),
    "nvd_cve_events_cve_id": ("nvd_cve_events", ("cve_id",)),
    "nvd_window_syncs_status_updated": (
        "nvd_window_syncs", ("status", "updated_at"),
    ),
    "nvd_window_restart_events_sync_recorded": (
        "nvd_window_restart_events", ("sync_id", "recorded_at"),
    ),
    "asset_products_active_asset": (
        "asset_products", ("active", "asset_id", "part", "vendor", "product", "version"),
    ),
    "asset_product_events_product_id": (
        "asset_product_events", ("asset_product_id", "recorded_at"),
    ),
    "asset_packages_active_asset": (
        "asset_packages", ("active", "asset_id", "provider", "name", "architecture"),
    ),
    "asset_package_events_package_id": (
        "asset_package_events", ("asset_package_id", "recorded_at"),
    ),
    "ubuntu_asset_packages_active_asset": (
        "ubuntu_asset_packages",
        ("active", "asset_id", "ecosystem", "binary_name", "architecture"),
    ),
    "ubuntu_asset_package_events_package_id": (
        "ubuntu_asset_package_events", ("ubuntu_package_id", "recorded_at"),
    ),
    "vulnerability_exposures_status_suppressed": (
        "vulnerability_exposures", ("suppressed", "status", "cve_id", "asset_product_id"),
    ),
    "vulnerability_exposure_events_exposure_id": (
        "vulnerability_exposure_events", ("exposure_id", "recorded_at"),
    ),
    "vulnerability_exposure_suppressions_active_exposure": (
        "vulnerability_exposure_suppressions", ("active", "exposure_id", "expires_at"),
    ),
    "vulnerability_exposure_suppression_events_suppression_id": (
        "vulnerability_exposure_suppression_events", ("suppression_id", "recorded_at"),
    ),
    "vulnerability_reassessment_items_run_id": (
        "vulnerability_reassessment_items", ("run_id", "exposure_id"),
    ),
    "vulnerability_change_notifications_read_sequence": (
        "vulnerability_change_notifications", ("read_at", "sequence"),
    ),
    "vulnerability_exposure_evidence_active_exposure": (
        "vulnerability_exposure_evidence", ("active", "exposure_id", "evidence_type"),
    ),
    "vulnerability_exposure_evidence_events_evidence_id": (
        "vulnerability_exposure_evidence_events", ("evidence_id", "recorded_at"),
    ),
    "vulnerability_vendor_package_evidence_active_exposure": (
        "vulnerability_vendor_package_evidence",
        ("active", "exposure_id", "asset_package_id"),
    ),
    "vulnerability_vendor_package_evidence_events_evidence_id": (
        "vulnerability_vendor_package_evidence_events", ("evidence_id", "recorded_at"),
    ),
    "vulnerability_remediations_exposure_state": (
        "vulnerability_remediations", ("exposure_id", "state", "recheck_at"),
    ),
    "vulnerability_remediation_events_remediation_id": (
        "vulnerability_remediation_events", ("remediation_id", "recorded_at"),
    ),
    "cti_indicator_assertions_active_indicator": (
        "cti_indicator_assertions", ("active", "indicator_id", "confidence"),
    ),
    "cti_indicator_assertion_events_assertion_id": (
        "cti_indicator_assertion_events", ("assertion_id", "recorded_at"),
    ),
    "cti_feed_runs_source_sequence": (
        "cti_feed_runs", ("source_name", "sequence"),
    ),
    "cti_feed_run_items_run_id": (
        "cti_feed_run_items", ("run_id", "assertion_id"),
    ),
    "ransomware_claim_runs_source_sequence": (
        "ransomware_claim_runs", ("source_name", "sequence"),
    ),
    "ransomware_claim_run_items_run_action": (
        "ransomware_claim_run_items", ("run_id", "action", "claim_id"),
    ),
    "ransomlook_claim_runs_source_sequence": (
        "ransomlook_claim_runs", ("source_name", "sequence"),
    ),
    "ransomlook_claim_run_items_run_action": (
        "ransomlook_claim_run_items", ("run_id", "action", "claim_id"),
    ),
    "ransomlook_watch_events_watch_recorded": (
        "ransomlook_watch_events", ("watch_id", "recorded_at"),
    ),
    "ransomlook_watch_runs_watch_sequence": (
        "ransomlook_watch_runs", ("watch_id", "sequence"),
    ),
    "ransomlook_watch_run_items_run_action": (
        "ransomlook_watch_run_items", ("run_id", "action", "claim_id"),
    ),
    "brand_username_watch_events_watch_recorded": (
        "brand_username_watch_events", ("watch_id", "recorded_at"),
    ),
    "brand_username_watch_runs_watch_sequence": (
        "brand_username_watch_runs", ("watch_id", "sequence"),
    ),
    "brand_username_watch_run_items_run_action": (
        "brand_username_watch_run_items", ("run_id", "action", "platform"),
    ),
    "brand_username_review_events_candidate_sequence": (
        "brand_username_review_events", ("candidate_id", "sequence"),
    ),
    "brand_username_review_events_watch_platform_sequence": (
        "brand_username_review_events", ("watch_id", "platform", "sequence"),
    ),
    "brand_username_review_notifications_read_sequence": (
        "brand_username_review_notifications", ("read_at", "sequence"),
    ),
    "ransomware_watch_events_watch_recorded": (
        "ransomware_watch_events", ("watch_id", "recorded_at"),
    ),
    "ransomware_watch_runs_watch_sequence": (
        "ransomware_watch_runs", ("watch_id", "sequence"),
    ),
    "ransomware_watch_run_items_run_action": (
        "ransomware_watch_run_items", ("run_id", "action", "claim_id"),
    ),
    "ransomware_watch_notifications_read_sequence": (
        "ransomware_watch_notifications", ("read_at", "sequence"),
    ),
    "ransomware_monitor_sessions_status_sequence": (
        "ransomware_monitor_sessions", ("status", "sequence"),
    ),
    "ransomware_identity_review_events_candidate_sequence": (
        "ransomware_identity_review_events", ("candidate_id", "sequence"),
    ),
    "ransomware_identity_review_events_watch_sequence": (
        "ransomware_identity_review_events", ("watch_id", "sequence"),
    ),
    "ransomware_source_review_events_comparison_sequence": (
        "ransomware_source_review_events", ("comparison_id", "sequence"),
    ),
    "ransomware_source_review_events_decision_sequence": (
        "ransomware_source_review_events", ("decision", "sequence"),
    ),
    "cti_entity_assertions_active_entity": (
        "cti_entity_assertions", ("active", "entity_id", "confidence"),
    ),
    "cti_entity_assertion_events_assertion": (
        "cti_entity_assertion_events", ("assertion_id", "recorded_at"),
    ),
    "cti_relationships_source_target": (
        "cti_relationships", ("source_entity_id", "target_key", "relationship_type"),
    ),
    "cti_relationship_assertions_active_relation": (
        "cti_relationship_assertions", ("active", "relationship_id", "confidence"),
    ),
    "cti_relationship_assertion_events_assertion": (
        "cti_relationship_assertion_events", ("assertion_id", "recorded_at"),
    ),
    "cti_saved_search_events_search_recorded": (
        "cti_saved_search_events", ("saved_search_id", "recorded_at"),
    ),
    "cti_saved_search_runs_search_sequence": (
        "cti_saved_search_runs", ("saved_search_id", "sequence"),
    ),
    "cti_saved_search_run_items_run": (
        "cti_saved_search_run_items", ("run_id", "action", "kind", "record_id"),
    ),
    "cti_saved_search_notifications_read_sequence": (
        "cti_saved_search_notifications", ("read_at", "sequence"),
    ),
    "cti_saved_search_tags_active_search": (
        "cti_saved_search_tags", ("saved_search_id", "active", "tag_key"),
    ),
    "cti_saved_search_tag_events_search_sequence": (
        "cti_saved_search_tag_events", ("saved_search_id", "sequence"),
    ),
    "cti_saved_search_notes_search_sequence": (
        "cti_saved_search_notes", ("saved_search_id", "sequence"),
    ),
    "webhook_destinations_active_name": (
        "webhook_destinations", ("active", "name_key"),
    ),
    "webhook_destination_events_destination_sequence": (
        "webhook_destination_events", ("destination_id", "sequence"),
    ),
    "webhook_deliveries_status_sequence": (
        "webhook_deliveries", ("status", "sequence"),
    ),
    "webhook_delivery_attempts_delivery_number": (
        "webhook_delivery_attempts", ("delivery_id", "number"),
    ),
}

FOREIGN_KEYS = {
    **supplier_watch_schema_metadata.FOREIGN_KEYS,
    **global_saved_search_schema_metadata.FOREIGN_KEYS,
    **news_schema_metadata.FOREIGN_KEYS,
    **mentions_schema_metadata.FOREIGN_KEYS,
    **mention_group_schema_metadata.FOREIGN_KEYS,
    **nmap_management_schema_metadata.FOREIGN_KEYS,
    **nmap_jobs_schema.FOREIGN_KEYS,
    **warninglist_schema.FOREIGN_KEYS,
    **enrichment_schema.FOREIGN_KEYS,
    **research_history_schema.FOREIGN_KEYS,
    **investigation_schema.FOREIGN_KEYS,
    **report_schema.FOREIGN_KEYS,
    **evidence_schema.FOREIGN_KEYS,
    **document_storage_schema.FOREIGN_KEYS,
    **relationship_notification_schema.FOREIGN_KEYS,
    **social_discovery_schema.FOREIGN_KEYS,
    **social_enrichment_schema.FOREIGN_KEYS,
    **social_tracking_schema.FOREIGN_KEYS,
    **group_schema.FOREIGN_KEYS,
    **group_operations_schema.FOREIGN_KEYS,
    'public_notice_watches': {('organizations', 'organization_id', 'id', 'NO ACTION', 'RESTRICT')},
    'public_notice_watch_events': {('organizations', 'organization_id', 'id', 'NO ACTION', 'RESTRICT'), ('public_notice_watches', 'watch_id', 'id', 'NO ACTION', 'RESTRICT')},
    'public_notice_watch_runs': {('organizations', 'organization_id', 'id', 'NO ACTION', 'RESTRICT'), ('public_notice_watches', 'watch_id', 'id', 'NO ACTION', 'RESTRICT'), ('public_notice_watch_events', 'watch_event_id', 'id', 'NO ACTION', 'RESTRICT'), ('public_notice_watch_runs', 'previous_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('public_notice_runs', 'source_run_id', 'id', 'NO ACTION', 'RESTRICT')},
    'public_notice_watch_notifications': {('public_notice_watch_runs', 'run_id', 'id', 'NO ACTION', 'RESTRICT'), ('organizations', 'organization_id', 'id', 'NO ACTION', 'RESTRICT'), ('public_notice_watches', 'watch_id', 'id', 'NO ACTION', 'RESTRICT')},
    'public_notice_runs': set(),
    'public_notice_changes': {('public_notice_runs', 'run_id', 'id', 'NO ACTION', 'RESTRICT')},
    'ransomlook_watch_notifications': {('ransomlook_watch_runs', 'run_id', 'id', 'NO ACTION', 'RESTRICT'), ('ransomlook_watches', 'watch_id', 'id', 'NO ACTION', 'RESTRICT')},
    'attack_catalog_runs': set(),
    'attack_catalog_entities': {('attack_catalog_runs', 'last_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('attack_catalog_runs', 'first_run_id', 'id', 'NO ACTION', 'RESTRICT')},
    'attack_catalog_relationships': {('attack_catalog_entities', 'source_stix_id', 'stix_id', 'NO ACTION', 'RESTRICT'), ('attack_catalog_entities', 'target_stix_id', 'stix_id', 'NO ACTION', 'RESTRICT'), ('attack_catalog_runs', 'last_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('attack_catalog_runs', 'first_run_id', 'id', 'NO ACTION', 'RESTRICT')},
    'attack_catalog_phases': {('attack_catalog_entities', 'technique_stix_id', 'stix_id', 'NO ACTION', 'RESTRICT'), ('attack_catalog_entities', 'tactic_stix_id', 'stix_id', 'NO ACTION', 'RESTRICT'), ('attack_catalog_runs', 'last_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('attack_catalog_runs', 'first_run_id', 'id', 'NO ACTION', 'RESTRICT')},
    'attack_catalog_changes': {('attack_catalog_runs', 'run_id', 'id', 'NO ACTION', 'RESTRICT')},

    'organizations': set(),
    'organization_events': {('organizations', 'organization_id', 'id', 'NO ACTION', 'RESTRICT')},
    'organization_links': {('ransomlook_watches', 'ransomlook_watch_id', 'id', 'NO ACTION', 'RESTRICT'), ('brand_username_watches', 'username_watch_id', 'id', 'NO ACTION', 'RESTRICT'), ('ransomware_watches', 'ransomware_watch_id', 'id', 'NO ACTION', 'RESTRICT'), ('assets', 'asset_id', 'id', 'NO ACTION', 'RESTRICT'), ('organizations', 'organization_id', 'id', 'NO ACTION', 'RESTRICT')},
    'organization_link_events': {('organization_links', 'link_id', 'id', 'NO ACTION', 'RESTRICT'), ('organizations', 'organization_id', 'id', 'NO ACTION', 'RESTRICT')},
    'collection_sessions': {('collection_sessions', 'root_id', 'id', 'NO ACTION', 'RESTRICT'), ('collection_profile_events', 'profile_event_id', 'id', 'NO ACTION', 'RESTRICT'), ('collection_sessions', 'parent_id', 'id', 'NO ACTION', 'RESTRICT')},
    'collection_session_steps': {('collection_session_steps', 'depends_on_step_id', 'id', 'NO ACTION', 'RESTRICT'), ('scan_jobs', 'scan_job_id', 'id', 'NO ACTION', 'RESTRICT'), ('collection_sessions', 'session_id', 'id', 'NO ACTION', 'RESTRICT')},
    'collection_step_receipts': {('news_runs', 'news_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('global_saved_search_runs', 'saved_search_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('public_notice_runs', 'public_notice_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('ransomware_watch_runs', 'threatcluster_watch_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('ransomlook_watch_runs', 'ransomlook_watch_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('ransomlook_claim_runs', 'ransomlook_source_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('brand_username_watch_runs', 'username_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('collection_session_steps', 'step_id', 'id', 'NO ACTION', 'RESTRICT'), ('cti_feed_runs', 'feed_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('scan_attempts', 'scan_attempt_id', 'id', 'NO ACTION', 'RESTRICT'), ('surface_discovery_runs', 'discovery_run_id', 'id', 'NO ACTION', 'RESTRICT'), ('ransomware_claim_runs', 'threatcluster_source_run_id', 'id', 'NO ACTION', 'RESTRICT')},

    "collection_profiles": set(),
    "collection_profile_events": {
        ("collection_profiles", "profile_id", "id", "NO ACTION", "RESTRICT"),
    },
    "assets": set(),
    "asset_criticalities": {("assets", "asset_id", "id", "NO ACTION", "RESTRICT")},
    "asset_criticality_events": {
        ("asset_criticalities", "asset_id", "asset_id", "NO ACTION", "RESTRICT"),
    },
    "suppliers": set(),
    "supplier_events": {
        ("suppliers", "supplier_id", "id", "NO ACTION", "RESTRICT"),
    },
    "supplier_candidates": {
        ("assets", "asset_id", "id", "NO ACTION", "RESTRICT"),
        ("suppliers", "supplier_id", "id", "NO ACTION", "RESTRICT"),
    },
    "supplier_candidate_evidence": {
        ("supplier_candidates", "candidate_id", "id", "NO ACTION", "RESTRICT"),
        ("surface_cname_checks", "source_evidence_id", "id", "NO ACTION", "RESTRICT"),
    },
    "supplier_candidate_resolution_events": {
        ("supplier_candidates", "candidate_id", "id", "NO ACTION", "RESTRICT"),
        ("suppliers", "supplier_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cases": set(),
    "case_evidence": {
        ("cases", "case_id", "id", "NO ACTION", "RESTRICT"),
    },
    "case_tasks": {
        ("cases", "case_id", "id", "NO ACTION", "RESTRICT"),
    },
    "case_activities": {
        ("cases", "case_id", "id", "NO ACTION", "RESTRICT"),
    },
    "observations": set(),
    "findings": {("assets", "asset_id", "id", "NO ACTION", "RESTRICT")},
    "finding_observations": {
        ("findings", "finding_id", "id", "NO ACTION", "RESTRICT"),
        ("observations", "observation_id", "id", "NO ACTION", "RESTRICT"),
    },
    "reviews": {("findings", "finding_id", "id", "NO ACTION", "RESTRICT")},
    "scan_jobs": set(),
    "scan_attempts": {("scan_jobs", "job_id", "id", "NO ACTION", "RESTRICT")},
    "finding_assessments": {("findings", "finding_id", "id", "NO ACTION", "RESTRICT")},
    "provider_cooldowns": set(),
    "cleanup_runs": set(),
    "notifications": {("findings", "finding_id", "id", "NO ACTION", "RESTRICT")},
    "monitor_runs": set(),
    "monitor_jobs": {
        ("monitor_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
        ("scan_jobs", "job_id", "id", "NO ACTION", "RESTRICT"),
    },
    "allowlist_entries": {("assets", "asset_id", "id", "NO ACTION", "RESTRICT")},
    "allowlist_events": {
        ("allowlist_entries", "entry_id", "id", "NO ACTION", "RESTRICT"),
    },
    "surface_scopes": {("assets", "asset_id", "id", "NO ACTION", "RESTRICT")},
    "surface_scope_events": {
        ("surface_scopes", "asset_id", "asset_id", "NO ACTION", "RESTRICT"),
    },
    "surface_checks": {
        ("surface_scopes", "asset_id", "asset_id", "NO ACTION", "RESTRICT"),
    },
    "surface_candidates": {("assets", "asset_id", "id", "NO ACTION", "RESTRICT")},
    "surface_candidate_sources": {
        ("surface_candidates", "candidate_id", "id", "NO ACTION", "RESTRICT"),
    },
    "surface_candidate_events": {
        ("surface_candidates", "candidate_id", "id", "NO ACTION", "RESTRICT"),
    },
    "surface_discovery_runs": {
        ("assets", "asset_id", "id", "NO ACTION", "RESTRICT"),
    },
    "surface_candidate_notifications": {
        ("surface_candidates", "candidate_id", "id", "NO ACTION", "RESTRICT"),
    },
    "surface_mail_checks": {
        ("surface_scopes", "asset_id", "asset_id", "NO ACTION", "RESTRICT"),
    },
    "surface_service_checks": {
        ("surface_scopes", "asset_id", "asset_id", "NO ACTION", "RESTRICT"),
    },
    "surface_nmap_checks": {
        ("surface_scopes", "asset_id", "asset_id", "NO ACTION", "RESTRICT"),
    },
    "surface_cname_checks": {
        ("surface_scopes", "asset_id", "asset_id", "NO ACTION", "RESTRICT"),
    },
    "surface_change_notifications": {
        ("surface_checks", "surface_check_id", "id", "NO ACTION", "RESTRICT"),
        ("surface_mail_checks", "mail_check_id", "id", "NO ACTION", "RESTRICT"),
        ("surface_service_checks", "service_check_id", "id", "NO ACTION", "RESTRICT"),
    },
    "vulnerability_source_runs": set(),
    "kev_entries": {
        ("vulnerability_source_runs", "latest_run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "kev_entry_events": {
        ("kev_entries", "cve_id", "cve_id", "NO ACTION", "RESTRICT"),
        ("vulnerability_source_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "epss_scores": {
        ("vulnerability_source_runs", "latest_run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "nvd_cve_records": {
        ("vulnerability_source_runs", "latest_run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "nvd_cve_events": {
        ("nvd_cve_records", "cve_id", "cve_id", "NO ACTION", "RESTRICT"),
        ("vulnerability_source_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "nvd_window_syncs": {
        ("vulnerability_source_runs", "latest_run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "nvd_window_restart_events": {
        ("nvd_window_syncs", "sync_id", "id", "NO ACTION", "RESTRICT"),
        (
            "vulnerability_source_runs", "previous_latest_run_id", "id",
            "NO ACTION", "RESTRICT",
        ),
    },
    "asset_products": {("assets", "asset_id", "id", "NO ACTION", "RESTRICT")},
    "asset_product_events": {
        ("asset_products", "asset_product_id", "id", "NO ACTION", "RESTRICT"),
    },
    "asset_packages": {("assets", "asset_id", "id", "NO ACTION", "RESTRICT")},
    "asset_package_events": {
        ("asset_packages", "asset_package_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ubuntu_asset_packages": {
        ("assets", "asset_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ubuntu_asset_package_events": {
        ("ubuntu_asset_packages", "ubuntu_package_id", "id", "NO ACTION", "RESTRICT"),
    },
    "vulnerability_exposures": {
        ("asset_products", "asset_product_id", "id", "NO ACTION", "RESTRICT"),
        ("nvd_cve_records", "cve_id", "cve_id", "NO ACTION", "RESTRICT"),
    },
    "vulnerability_exposure_events": {
        ("vulnerability_exposures", "exposure_id", "id", "NO ACTION", "RESTRICT"),
    },
    "vulnerability_exposure_suppressions": {
        ("vulnerability_exposures", "exposure_id", "id", "NO ACTION", "RESTRICT"),
    },
    "vulnerability_exposure_suppression_events": {
        (
            "vulnerability_exposure_suppressions", "suppression_id", "id",
            "NO ACTION", "RESTRICT",
        ),
    },
    "vulnerability_reassessment_runs": set(),
    "vulnerability_reassessment_items": {
        (
            "vulnerability_reassessment_runs", "run_id", "id",
            "NO ACTION", "RESTRICT",
        ),
        (
            "vulnerability_exposures", "exposure_id", "id",
            "NO ACTION", "RESTRICT",
        ),
    },
    "vulnerability_change_notifications": {
        (
            "vulnerability_exposures", "exposure_id", "id",
            "NO ACTION", "RESTRICT",
        ),
    },
    "vulnerability_exposure_evidence": {
        ("vulnerability_exposures", "exposure_id", "id", "NO ACTION", "RESTRICT"),
    },
    "vulnerability_exposure_evidence_events": {
        ("vulnerability_exposure_evidence", "evidence_id", "id", "NO ACTION", "RESTRICT"),
    },
    "vulnerability_vendor_package_evidence": {
        ("vulnerability_exposures", "exposure_id", "id", "NO ACTION", "RESTRICT"),
        ("asset_packages", "asset_package_id", "id", "NO ACTION", "RESTRICT"),
    },
    "vulnerability_vendor_package_evidence_events": {
        ("vulnerability_vendor_package_evidence", "evidence_id", "id", "NO ACTION", "RESTRICT"),
    },
    "vulnerability_remediations": {
        ("vulnerability_exposures", "exposure_id", "id", "NO ACTION", "RESTRICT"),
    },
    "vulnerability_remediation_events": {
        ("vulnerability_remediations", "remediation_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_indicators": set(),
    "cti_indicator_assertions": {
        ("cti_indicators", "indicator_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_indicator_assertion_events": {
        (
            "cti_indicator_assertions", "assertion_id", "id",
            "NO ACTION", "RESTRICT",
        ),
    },
    "cti_feed_runs": set(),
    "cti_feed_run_items": {
        ("cti_feed_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
        ("cti_indicator_assertions", "assertion_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomware_claim_runs": set(),
    "ransomware_claim_run_items": {
        ("ransomware_claim_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomlook_claim_runs": set(),
    "ransomlook_claim_run_items": {
        ("ransomlook_claim_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomlook_watches": set(),
    "ransomlook_watch_events": {
        ("ransomlook_watches", "watch_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomlook_watch_runs": {
        ("ransomlook_watches", "watch_id", "id", "NO ACTION", "RESTRICT"),
        ("ransomlook_claim_runs", "source_run_id", "id", "NO ACTION", "RESTRICT"),
        ("ransomlook_watch_runs", "previous_run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomlook_watch_run_items": {
        ("ransomlook_watch_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "brand_username_watches": set(),
    "brand_username_watch_events": {
        ("brand_username_watches", "watch_id", "id", "NO ACTION", "RESTRICT"),
    },
    "brand_username_watch_runs": {
        ("brand_username_watches", "watch_id", "id", "NO ACTION", "RESTRICT"),
        (
            "brand_username_watch_runs", "previous_complete_run_id", "id",
            "NO ACTION", "RESTRICT",
        ),
    },
    "brand_username_watch_run_items": {
        ("brand_username_watch_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "brand_username_review_events": {
        ("brand_username_watches", "watch_id", "id", "NO ACTION", "RESTRICT"),
        ("brand_username_watch_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
        (
            "brand_username_review_events", "previous_event_id", "id",
            "NO ACTION", "RESTRICT",
        ),
    },
    "brand_username_review_notifications": {
        (
            "brand_username_review_events", "review_event_id", "id",
            "NO ACTION", "RESTRICT",
        ),
    },
    "ransomware_watches": set(),
    "ransomware_watch_events": {
        ("ransomware_watches", "watch_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomware_watch_runs": {
        ("ransomware_watches", "watch_id", "id", "NO ACTION", "RESTRICT"),
        ("ransomware_claim_runs", "source_run_id", "id", "NO ACTION", "RESTRICT"),
        ("ransomware_watch_runs", "previous_run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomware_watch_run_items": {
        ("ransomware_watch_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomware_watch_notifications": {
        ("ransomware_watch_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
        ("ransomware_watches", "watch_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomware_monitor_sessions": set(),
    "ransomware_monitor_cycles": {
        ("ransomware_monitor_sessions", "session_id", "id", "NO ACTION", "RESTRICT"),
        ("ransomware_claim_runs", "source_run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomware_monitor_cycle_watch_runs": {
        ("ransomware_monitor_cycles", "cycle_id", "id", "NO ACTION", "RESTRICT"),
        ("ransomware_watch_runs", "watch_run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "ransomware_identity_review_events": {
        ("ransomware_watches", "watch_id", "id", "NO ACTION", "RESTRICT"),
        (
            "ransomware_claim_runs", "transition_source_run_id", "id",
            "NO ACTION", "RESTRICT",
        ),
        (
            "ransomware_identity_review_events", "previous_event_id", "id",
            "NO ACTION", "RESTRICT",
        ),
    },
    "ransomware_source_review_events": {
        (
            "ransomware_claim_runs", "threatcluster_run_id", "id",
            "NO ACTION", "RESTRICT",
        ),
        (
            "ransomlook_claim_runs", "ransomlook_run_id", "id",
            "NO ACTION", "RESTRICT",
        ),
        (
            "ransomware_source_review_events", "previous_event_id", "id",
            "NO ACTION", "RESTRICT",
        ),
    },
    "cti_entities": set(),
    "cti_entity_assertions": {
        ("cti_entities", "entity_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_entity_assertion_events": {
        ("cti_entity_assertions", "assertion_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_relationships": {
        ("cti_entities", "source_entity_id", "id", "NO ACTION", "RESTRICT"),
        ("cti_entities", "target_entity_id", "id", "NO ACTION", "RESTRICT"),
        ("cti_indicators", "target_indicator_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_relationship_assertions": {
        ("cti_relationships", "relationship_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_relationship_assertion_events": {
        ("cti_relationship_assertions", "assertion_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_saved_searches": set(),
    "cti_saved_search_events": {
        ("cti_saved_searches", "saved_search_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_saved_search_runs": {
        ("cti_saved_searches", "saved_search_id", "id", "NO ACTION", "RESTRICT"),
        ("cti_saved_search_runs", "previous_run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_saved_search_run_items": {
        ("cti_saved_search_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_saved_search_notifications": {
        ("cti_saved_search_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
        ("cti_saved_searches", "saved_search_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_saved_search_tags": {
        ("cti_saved_searches", "saved_search_id", "id", "NO ACTION", "RESTRICT"),
    },
    "cti_saved_search_tag_events": {
        ("cti_saved_searches", "saved_search_id", "id", "NO ACTION", "RESTRICT"),
        ("cti_saved_search_tags", "saved_search_id", "saved_search_id", "NO ACTION", "RESTRICT"),
        ("cti_saved_search_tags", "tag_key", "tag_key", "NO ACTION", "RESTRICT"),
    },
    "cti_saved_search_notes": {
        ("cti_saved_searches", "saved_search_id", "id", "NO ACTION", "RESTRICT"),
        ("cti_saved_search_runs", "run_id", "id", "NO ACTION", "RESTRICT"),
    },
    "webhook_destinations": set(),
    "webhook_destination_events": {
        ("webhook_destinations", "destination_id", "id", "NO ACTION", "RESTRICT"),
    },
    "webhook_deliveries": {
        ("webhook_destinations", "destination_id", "id", "NO ACTION", "RESTRICT"),
    },
    "webhook_delivery_attempts": {
        ("webhook_deliveries", "delivery_id", "id", "NO ACTION", "RESTRICT"),
    },
}

BRAND_USERNAME_WATCH_V49_COLUMNS = TABLES["brand_username_watches"][:-1]

# Explicit layouts keep future tables out of the legacy validation path.
TABLES['collection_step_receipts'].append(('social_tracking_run_id', 'TEXT', 0, 0))
UNIQUE_KEYS['collection_step_receipts'].add(('social_tracking_run_id',))
FOREIGN_KEYS['collection_step_receipts'].add(('social_tracking_journal', 'social_tracking_run_id', 'id', 'NO ACTION', 'RESTRICT'))

VERSION_TABLES = {
    1: frozenset({"assets"}),
    2: frozenset({"assets", "observations", "findings", "finding_observations", "reviews"}),
    3: frozenset({"assets", "observations", "findings", "finding_observations", "reviews",
                  "scan_jobs", "scan_attempts"}),
    4: frozenset({"assets", "observations", "findings", "finding_observations", "reviews",
                  "scan_jobs", "scan_attempts", "finding_assessments"}),
    5: frozenset({"assets", "observations", "findings", "finding_observations", "reviews",
                  "scan_jobs", "scan_attempts", "finding_assessments", "provider_cooldowns",
                  "cleanup_runs"}),
    6: frozenset({"assets", "observations", "findings", "finding_observations", "reviews",
                  "scan_jobs", "scan_attempts", "finding_assessments", "provider_cooldowns",
                  "cleanup_runs", "notifications"}),
    7: frozenset({
        "assets", "observations", "findings", "finding_observations", "reviews",
        "scan_jobs", "scan_attempts", "finding_assessments", "provider_cooldowns",
        "cleanup_runs", "notifications", "monitor_runs", "monitor_jobs",
    }),
    8: frozenset(TABLES) - {
        "surface_scopes", "surface_scope_events", "surface_checks",
        "surface_candidates", "surface_candidate_sources", "surface_candidate_events",
        "surface_discovery_runs", "surface_candidate_notifications", "surface_mail_checks",
        "surface_service_checks", "surface_change_notifications", "surface_cname_checks",
        "vulnerability_source_runs", "kev_entries", "kev_entry_events", "epss_scores",
        "nvd_cve_records", "nvd_cve_events",
    },
    9: frozenset(TABLES) - {
        "surface_scopes", "surface_scope_events", "surface_checks",
        "surface_candidates", "surface_candidate_sources", "surface_candidate_events",
        "surface_discovery_runs", "surface_candidate_notifications", "surface_mail_checks",
        "surface_service_checks", "surface_change_notifications", "surface_cname_checks",
        "vulnerability_source_runs", "kev_entries", "kev_entry_events", "epss_scores",
        "nvd_cve_records", "nvd_cve_events",
    },
    10: frozenset(TABLES) - {
        "surface_candidates", "surface_candidate_sources", "surface_candidate_events",
        "surface_discovery_runs", "surface_candidate_notifications", "surface_mail_checks",
        "surface_service_checks", "surface_change_notifications", "surface_cname_checks",
        "vulnerability_source_runs", "kev_entries", "kev_entry_events", "epss_scores",
        "nvd_cve_records", "nvd_cve_events",
    },
    11: frozenset(TABLES) - {
        "surface_discovery_runs", "surface_candidate_notifications", "surface_mail_checks",
        "surface_service_checks", "surface_change_notifications", "surface_cname_checks",
        "vulnerability_source_runs", "kev_entries", "kev_entry_events", "epss_scores",
        "nvd_cve_records", "nvd_cve_events",
    },
    12: frozenset(TABLES) - {
        "surface_mail_checks", "surface_service_checks", "surface_change_notifications",
        "surface_cname_checks",
        "vulnerability_source_runs", "kev_entries", "kev_entry_events", "epss_scores",
        "nvd_cve_records", "nvd_cve_events",
    },
    13: frozenset(TABLES) - {
        "surface_service_checks", "surface_change_notifications", "surface_cname_checks",
        "vulnerability_source_runs", "kev_entries", "kev_entry_events", "epss_scores",
        "nvd_cve_records", "nvd_cve_events",
    },
    14: frozenset(TABLES) - {
        "surface_change_notifications", "surface_cname_checks",
        "vulnerability_source_runs", "kev_entries", "kev_entry_events", "epss_scores",
        "nvd_cve_records", "nvd_cve_events",
    },
    15: frozenset(TABLES) - {
        "surface_cname_checks", "vulnerability_source_runs", "kev_entries",
        "kev_entry_events", "epss_scores", "nvd_cve_records", "nvd_cve_events",
    },
    16: frozenset(TABLES) - {
        "vulnerability_source_runs", "kev_entries", "kev_entry_events", "epss_scores",
        "nvd_cve_records", "nvd_cve_events",
    },
    17: frozenset(TABLES) - {"epss_scores", "nvd_cve_records", "nvd_cve_events"},
    18: frozenset(TABLES) - {"nvd_cve_records", "nvd_cve_events"},
    19: frozenset(TABLES) - {
        "asset_products", "asset_product_events", "vulnerability_exposures",
        "vulnerability_exposure_events",
    },
    20: frozenset(TABLES) - {
        "vulnerability_exposures", "vulnerability_exposure_events",
        "vulnerability_exposure_evidence", "vulnerability_exposure_evidence_events",
    },
    21: frozenset(TABLES) - {
        "vulnerability_exposure_evidence", "vulnerability_exposure_evidence_events",
    },
    22: frozenset(TABLES) - {"asset_packages", "asset_package_events"},
    23: frozenset(TABLES) - {
        "vulnerability_vendor_package_evidence",
        "vulnerability_vendor_package_evidence_events",
    },
    24: frozenset(TABLES) - {
        "vulnerability_remediations", "vulnerability_remediation_events",
    },
    25: frozenset(TABLES) - {
        "vulnerability_exposure_suppressions",
        "vulnerability_exposure_suppression_events",
    },
    26: frozenset(TABLES) - {"asset_criticalities", "asset_criticality_events"},
    27: frozenset(TABLES) - {
        "vulnerability_reassessment_runs", "vulnerability_reassessment_items",
    },
    28: frozenset(TABLES) - {"vulnerability_change_notifications"},
    29: frozenset(TABLES) - {"nvd_window_syncs"},
    30: frozenset(TABLES) - {"nvd_window_restart_events"},
    31: frozenset(TABLES) - {
        "ubuntu_asset_packages", "ubuntu_asset_package_events",
    },
    32: frozenset(TABLES) - {
        "cti_indicators", "cti_indicator_assertions",
        "cti_indicator_assertion_events",
    },
    33: frozenset(TABLES) - {"cti_feed_runs", "cti_feed_run_items"},
    34: frozenset(TABLES) - {
        "cti_entities", "cti_entity_assertions", "cti_entity_assertion_events",
        "cti_relationships", "cti_relationship_assertions",
        "cti_relationship_assertion_events",
    },
    35: frozenset(TABLES) - {
        "cti_saved_searches", "cti_saved_search_events",
        "cti_saved_search_runs", "cti_saved_search_run_items",
    },
    36: frozenset(TABLES) - {"cti_saved_search_notifications"},
    37: frozenset(TABLES) - {
        "cti_saved_search_tags", "cti_saved_search_tag_events",
        "cti_saved_search_notes",
    },
    38: frozenset(TABLES) - {
        "webhook_destinations", "webhook_destination_events",
        "webhook_deliveries", "webhook_delivery_attempts",
    },
    39: frozenset(TABLES),
    40: frozenset(TABLES),
    41: frozenset(TABLES),
    42: frozenset(TABLES),
    43: frozenset(TABLES),
    44: frozenset(TABLES),
    45: frozenset(TABLES),
    46: frozenset(TABLES),
    47: frozenset(TABLES),
    48: frozenset(TABLES),
    49: frozenset(TABLES),
    50: frozenset(TABLES),
    51: frozenset(TABLES),
    52: frozenset(TABLES),
    53: frozenset(TABLES),
    54: frozenset(TABLES),
    55: frozenset(TABLES),
    56: frozenset(TABLES),
    57: frozenset(TABLES),
    58: frozenset(TABLES),
    59: frozenset(TABLES),
    60: frozenset(TABLES),
    61: frozenset(TABLES),
    62: frozenset(TABLES),
    63: frozenset(TABLES),
    64: frozenset(TABLES),
    65: frozenset(TABLES),
    66: frozenset(TABLES),
    67: frozenset(TABLES),
    68: frozenset(TABLES),
    69: frozenset(TABLES),
    70: frozenset(TABLES),
    71: frozenset(TABLES),
    72: frozenset(TABLES),
    73: frozenset(TABLES),
    74: frozenset(TABLES),
    75: frozenset(TABLES),
    76: frozenset(TABLES),
    77: frozenset(TABLES),
    78: frozenset(TABLES),
    79: frozenset(TABLES),
    80: frozenset(TABLES),
    81: frozenset(TABLES),
    82: frozenset(TABLES),
    83: frozenset(TABLES),
    84: frozenset(TABLES),
    85: frozenset(TABLES),
    86: frozenset(TABLES),
    87: frozenset(TABLES),
}

for _legacy_version in range(1, 87):
    VERSION_TABLES[_legacy_version] -= group_operations_schema.TABLES.keys()

for _legacy_version in range(1, 86):
    VERSION_TABLES[_legacy_version] -= group_schema.TABLES.keys()

for _legacy_version in range(1, 83):
    VERSION_TABLES[_legacy_version] -= social_tracking_schema.TABLES.keys()

for _legacy_version in range(1, 82):
    VERSION_TABLES[_legacy_version] -= social_enrichment_schema.TABLES.keys()

for _legacy_version in range(1, 81):
    VERSION_TABLES[_legacy_version] -= social_discovery_schema.TABLES.keys()

for _legacy_version in range(1, 80):
    VERSION_TABLES[_legacy_version] -= relationship_notification_schema.TABLES.keys()

for _legacy_version in range(1, 79):
    VERSION_TABLES[_legacy_version] -= document_storage_schema.TABLES.keys()

for _legacy_version in range(1, 78):
    VERSION_TABLES[_legacy_version] -= evidence_schema.TABLES.keys()

for _legacy_version in range(1, 77):
    VERSION_TABLES[_legacy_version] -= report_schema.TABLES.keys()

for _legacy_version in range(1, 76):
    VERSION_TABLES[_legacy_version] -= investigation_schema.TABLES.keys()

for _legacy_version in range(1, 75):
    VERSION_TABLES[_legacy_version] -= research_history_schema.TABLES.keys()

for _legacy_version in range(1, 74):
    VERSION_TABLES[_legacy_version] -= enrichment_schema.TABLES.keys()

for _legacy_version in range(1, 73):
    VERSION_TABLES[_legacy_version] -= warninglist_schema.TABLES.keys()

for _legacy_version in range(1, 72):
    VERSION_TABLES[_legacy_version] -= nmap_jobs_schema.TABLES.keys()

for _legacy_version in range(1, 71):
    VERSION_TABLES[_legacy_version] -= nmap_management_schema_metadata.TABLES.keys()

for _legacy_version in range(1, 70):
    VERSION_TABLES[_legacy_version] -= {"surface_nmap_checks"}

for _legacy_version in range(1, 68):
    VERSION_TABLES[_legacy_version] -= {*mention_group_schema_metadata.TABLES, "mention_notification_operations"}

for _legacy_version in range(1, 67):
    VERSION_TABLES[_legacy_version] -= mentions_schema_metadata.TABLES.keys()

for _legacy_version in range(1, 66):
    VERSION_TABLES[_legacy_version] -= news_schema_metadata.TABLES.keys()

for _legacy_version in range(1, 65):
    VERSION_TABLES[_legacy_version] -= global_saved_search_schema_metadata.TABLES.keys()

for _legacy_version in range(1, 64):
    VERSION_TABLES[_legacy_version] -= supplier_watch_schema_metadata.TABLES.keys()

for _legacy_version in range(1, 62):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {'public_notice_watch_events', 'public_notice_watches', 'public_notice_watch_runs', 'public_notice_watch_notifications'}

for _legacy_version in range(1, 60):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {"public_notice_runs", "public_notice_changes"}

for _legacy_version in range(1, 59):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {"ransomlook_watch_notifications"}

for _legacy_version in range(1, 58):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {'attack_catalog_runs', 'attack_catalog_relationships', 'attack_catalog_changes', 'attack_catalog_phases', 'attack_catalog_entities'}

for _legacy_version in range(1, 57):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "organizations", "organization_events", "organization_links", "organization_link_events",
    }

for _legacy_version in range(1, 56):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "collection_sessions", "collection_session_steps", "collection_step_receipts",
    }

for _legacy_version in range(1, 55):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "collection_profiles", "collection_profile_events",
    }

for _legacy_version in range(1, 54):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "cases", "case_evidence", "case_tasks", "case_activities",
    }

for _legacy_version in range(1, 53):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "supplier_candidates", "supplier_candidate_evidence",
        "supplier_candidate_resolution_events",
    }

for _legacy_version in range(1, 52):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "suppliers", "supplier_events",
    }

for _legacy_version in range(1, 49):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "brand_username_review_notifications",
    }

for _legacy_version in range(1, 48):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "brand_username_review_events",
    }

for _legacy_version in range(1, 47):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "brand_username_watches", "brand_username_watch_events",
        "brand_username_watch_runs", "brand_username_watch_run_items",
    }

for _legacy_version in range(1, 46):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "ransomware_source_review_events",
    }

for _legacy_version in range(1, 45):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "ransomlook_watches", "ransomlook_watch_events",
        "ransomlook_watch_runs", "ransomlook_watch_run_items",
    }

for _legacy_version in range(1, 44):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "ransomlook_claim_runs", "ransomlook_claim_run_items",
    }

for _legacy_version in range(1, 43):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "ransomware_identity_review_events",
    }

for _legacy_version in range(1, 42):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "ransomware_monitor_sessions", "ransomware_monitor_cycles",
        "ransomware_monitor_cycle_watch_runs",
    }

for _legacy_version in range(1, 41):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "ransomware_watches", "ransomware_watch_events", "ransomware_watch_runs",
        "ransomware_watch_run_items", "ransomware_watch_notifications",
    }

for _legacy_version in range(1, 40):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "ransomware_claim_runs", "ransomware_claim_run_items",
    }

# TABLES contains the newest layout, so every legacy layout must explicitly omit
# later product-evidence and exposure-review tables.
for _legacy_version in range(1, 20):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "asset_products", "asset_product_events",
    }
for _legacy_version in range(1, 21):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "vulnerability_exposures", "vulnerability_exposure_events",
    }
for _legacy_version in range(1, 22):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "vulnerability_exposure_evidence", "vulnerability_exposure_evidence_events",
    }
for _legacy_version in range(1, 23):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "asset_packages", "asset_package_events",
    }
for _legacy_version in range(1, 24):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "vulnerability_vendor_package_evidence",
        "vulnerability_vendor_package_evidence_events",
    }
for _legacy_version in range(1, 25):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "vulnerability_remediations", "vulnerability_remediation_events",
    }
for _legacy_version in range(1, 26):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "vulnerability_exposure_suppressions",
        "vulnerability_exposure_suppression_events",
    }
for _legacy_version in range(1, 27):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "asset_criticalities", "asset_criticality_events",
    }
for _legacy_version in range(1, 28):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "vulnerability_reassessment_runs", "vulnerability_reassessment_items",
    }
for _legacy_version in range(1, 29):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "vulnerability_change_notifications",
    }
for _legacy_version in range(1, 30):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "nvd_window_syncs",
    }
for _legacy_version in range(1, 31):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "nvd_window_restart_events",
    }
for _legacy_version in range(1, 32):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "ubuntu_asset_packages", "ubuntu_asset_package_events",
    }
for _legacy_version in range(1, 33):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "cti_indicators", "cti_indicator_assertions",
        "cti_indicator_assertion_events",
    }
for _legacy_version in range(1, 34):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "cti_feed_runs", "cti_feed_run_items",
    }
for _legacy_version in range(1, 35):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "cti_entities", "cti_entity_assertions", "cti_entity_assertion_events",
        "cti_relationships", "cti_relationship_assertions",
        "cti_relationship_assertion_events",
    }
for _legacy_version in range(1, 36):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "cti_saved_searches", "cti_saved_search_events",
        "cti_saved_search_runs", "cti_saved_search_run_items",
    }
for _legacy_version in range(1, 37):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "cti_saved_search_notifications",
    }
for _legacy_version in range(1, 38):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "cti_saved_search_tags", "cti_saved_search_tag_events",
        "cti_saved_search_notes",
    }
for _legacy_version in range(1, 39):
    VERSION_TABLES[_legacy_version] = VERSION_TABLES[_legacy_version] - {
        "webhook_destinations", "webhook_destination_events",
        "webhook_deliveries", "webhook_delivery_attempts",
    }


def create_mention_group_schema(connection: sqlite3.Connection) -> None:
    for statement in MENTION_GROUP_DDL:
        connection.execute(statement)


def create_mentions_schema(connection: sqlite3.Connection) -> None:
    for statement in MENTIONS_DDL:
        connection.execute(statement)


def create_news_schema(connection: sqlite3.Connection) -> None:
    for statement in NEWS_DDL:
        connection.execute(statement)


def create_global_saved_search_schema(connection: sqlite3.Connection) -> None:
    for statement in GLOBAL_SAVED_SEARCH_DDL:
        connection.execute(statement)


def create_supplier_watch_schema(connection: sqlite3.Connection) -> None:
    for statement in SUPPLIER_WATCH_DDL:
        connection.execute(statement)


def create_public_notice_watch_schema(connection: sqlite3.Connection) -> None:
    for statement in PUBLIC_NOTICE_WATCH_DDL:
        connection.execute(statement)


def create_public_notice_schema(connection: sqlite3.Connection) -> None:
    for statement in PUBLIC_NOTICE_DDL:
        connection.execute(statement)


def create_attack_catalog_schema(connection: sqlite3.Connection) -> None:
    for statement in ATTACK_CATALOG_DDL:
        connection.execute(statement)


def create_ransomlook_notification_schema(connection: sqlite3.Connection) -> None:
    for statement in RANSOMLOOK_NOTIFICATION_DDL:
        connection.execute(statement)


def create_organization_schema(connection: sqlite3.Connection) -> None:
    for statement in ORGANIZATION_DDL:
        connection.execute(statement)


def create_collection_history_schema(connection: sqlite3.Connection) -> None:
    for statement in COLLECTION_HISTORY_DDL:
        connection.execute(statement)


def create_collection_profile_schema(connection: sqlite3.Connection) -> None:
    """Create saved collection recipes and their immutable lifecycle snapshots."""
    for statement in COLLECTION_PROFILE_DDL:
        connection.execute(statement)


def create_asset_criticality_schema(connection: sqlite3.Connection) -> None:
    """Create explicit business criticality state and append-only history."""
    for statement in ASSET_CRITICALITY_DDL:
        connection.execute(statement)


def create_supplier_inventory_schema(connection: sqlite3.Connection) -> None:
    """Create explicit supplier relationships and append-only snapshots."""
    for statement in SUPPLIER_INVENTORY_DDL:
        connection.execute(statement)


def create_supplier_candidate_schema(connection: sqlite3.Connection) -> None:
    """Create evidence-bound supplier suggestions and reversible resolutions."""
    for statement in SUPPLIER_CANDIDATE_DDL:
        connection.execute(statement)


def create_case_schema(connection: sqlite3.Connection) -> None:
    """Create human-managed cases, tasks, evidence links and one activity stream."""
    for statement in CASE_DDL:
        connection.execute(statement)


def create_vulnerability_reassessment_schema(connection: sqlite3.Connection) -> None:
    """Create durable, decision-preserving reassessment audit history."""
    for statement in VULNERABILITY_REASSESSMENT_DDL:
        connection.execute(statement)


def create_vulnerability_change_notification_schema(connection: sqlite3.Connection) -> None:
    """Create deduplicated local notices for changed exposure evidence."""
    for statement in VULNERABILITY_CHANGE_NOTIFICATION_DDL:
        connection.execute(statement)


def create_findings_schema(connection: sqlite3.Connection) -> None:
    """Execute each DDL statement inside the caller's transaction."""
    for statement in FINDINGS_DDL:
        connection.execute(statement)


def create_jobs_schema(connection: sqlite3.Connection) -> None:
    """Create durable work tables inside the caller's transaction."""
    for statement in JOBS_DDL:
        connection.execute(statement)


def create_assessments_schema(connection: sqlite3.Connection) -> None:
    """Create append-only target evidence inside the caller's transaction."""
    for statement in ASSESSMENTS_DDL:
        connection.execute(statement)


def create_operations_schema(connection: sqlite3.Connection) -> None:
    """Create provider state and cleanup audit tables in the caller's transaction."""
    for statement in OPERATIONS_DDL:
        connection.execute(statement)


def create_inbox_schema(connection: sqlite3.Connection) -> None:
    """Create durable local notifications inside the caller's transaction."""
    for statement in INBOX_DDL:
        connection.execute(statement)


def create_monitor_schema(connection: sqlite3.Connection) -> None:
    """Create bounded session history and atomic job links in the caller's transaction."""
    for statement in MONITOR_DDL:
        connection.execute(statement)


def create_allowlist_schema(connection: sqlite3.Connection) -> None:
    """Create exact-domain policy and its append-only action history."""
    for statement in ALLOWLIST_DDL:
        connection.execute(statement)


def create_surface_schema(connection: sqlite3.Connection) -> None:
    """Create explicitly approved surface scope and append-only check evidence."""
    for statement in SURFACE_DDL:
        connection.execute(statement)


def create_surface_discovery_schema(connection: sqlite3.Connection) -> None:
    """Create passive domain candidate, evidence and decision tables."""
    for statement in SURFACE_DISCOVERY_DDL:
        connection.execute(statement)


def create_surface_discovery_history_schema(connection: sqlite3.Connection) -> None:
    """Create durable passive-run history and local candidate notices."""
    for statement in SURFACE_DISCOVERY_HISTORY_DDL:
        connection.execute(statement)


def migrate_surface_discovery_provider_schema(connection: sqlite3.Connection) -> None:
    """Widen only provider checks while preserving every passive row and sequence."""
    connection.execute("DROP INDEX surface_candidate_sources_candidate_id")
    connection.execute("DROP INDEX surface_discovery_runs_asset_sequence")
    connection.execute(
        "ALTER TABLE surface_candidate_sources RENAME TO surface_candidate_sources_v50"
    )
    connection.execute(
        "ALTER TABLE surface_discovery_runs RENAME TO surface_discovery_runs_v50"
    )
    connection.execute(SURFACE_DISCOVERY_DDL[1])
    connection.execute(SURFACE_DISCOVERY_HISTORY_DDL[0])
    connection.execute(
        "INSERT INTO surface_candidate_sources "
        "(id, candidate_id, provider, source_name, source_sha256, raw_domain, "
        "observed_at, recorded_at) SELECT id, candidate_id, provider, source_name, "
        "source_sha256, raw_domain, observed_at, recorded_at "
        "FROM surface_candidate_sources_v50 ORDER BY rowid"
    )
    connection.execute(
        "INSERT INTO surface_discovery_runs "
        "(sequence, id, asset_id, asset_value, provider, status, source_url, "
        "started_at, finished_at, record_count, skipped_names, ignored_names, warnings, "
        "candidate_count, candidates_created, candidates_existing, evidence_created, "
        "evidence_existing, error) SELECT sequence, id, asset_id, asset_value, provider, "
        "status, source_url, started_at, finished_at, record_count, skipped_names, "
        "ignored_names, warnings, candidate_count, candidates_created, "
        "candidates_existing, evidence_created, evidence_existing, error "
        "FROM surface_discovery_runs_v50 ORDER BY sequence"
    )
    connection.execute(SURFACE_DISCOVERY_DDL[4])
    connection.execute(SURFACE_DISCOVERY_HISTORY_DDL[2])
    connection.execute("DROP TABLE surface_candidate_sources_v50")
    connection.execute("DROP TABLE surface_discovery_runs_v50")


def create_surface_mail_schema(connection: sqlite3.Connection) -> None:
    """Create approved-scope append-only mail DNS evidence."""
    for statement in SURFACE_MAIL_DDL:
        connection.execute(statement)


def create_surface_service_schema(connection: sqlite3.Connection) -> None:
    """Create approved-domain and exact-IP TCP service evidence."""
    for statement in SURFACE_SERVICE_DDL:
        connection.execute(statement)


def _validate_staged_surface_nmap_schema(connection: sqlite3.Connection) -> None:
    """Accept only a complete, exact and empty staged v70 Nmap layout."""
    names = (
        "surface_nmap_checks", "surface_nmap_checks_asset_id",
        "surface_nmap_checks_execution_id",
    )
    existing = set(connection.execute(
        "SELECT name FROM sqlite_schema WHERE name IN (?, ?, ?)", names,
    ).fetchall())
    if existing != {(name,) for name in names}:
        raise SchemaError("Nmap kontrol kayıt düzeni eksik veya beklenmeyen biçimde.")
    for name, statement in zip(names, SURFACE_NMAP_DDL):
        object_type = "index" if statement.startswith("CREATE INDEX") else "table"
        declaration = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
        ).fetchone()
        if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
            raise SchemaError("Nmap kontrol kayıt düzeni beklenen biçimde değil.")
    if connection.execute("SELECT COUNT(*) FROM surface_nmap_checks").fetchone()[0] != 0:
        raise SchemaError("Eski şema sürümünde Nmap kanıtı bulunamaz.")


def create_surface_nmap_schema(connection: sqlite3.Connection) -> None:
    """Create separately stored, bounded Nmap TCP evidence."""
    existing = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE name LIKE 'surface_nmap_checks%' LIMIT 1"
    ).fetchone()
    if existing is not None:
        _validate_staged_surface_nmap_schema(connection)
        return
    for statement in SURFACE_NMAP_DDL:
        connection.execute(statement)


def _validate_staged_nmap_management_schema(connection: sqlite3.Connection) -> None:
    """Accept only the complete, exact and empty staged v71 management layout."""
    expected = {
        (
            statement.split()[2],
            "index" if statement.startswith("CREATE INDEX") else "table",
        )
        for statement in NMAP_MANAGEMENT_DDL
    }
    names = tuple(name for name, _object_type in expected)
    placeholders = ",".join("?" for _name in names)
    actual = set(connection.execute(
        f"SELECT name, type FROM sqlite_schema WHERE name IN ({placeholders})", names,
    ).fetchall())
    if actual != expected:
        raise SchemaError("Yönetilen Nmap kayıt düzeni eksik veya beklenmeyen biçimde.")
    for statement in NMAP_MANAGEMENT_DDL:
        name = statement.split()[2]
        object_type = "index" if statement.startswith("CREATE INDEX") else "table"
        declaration = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
        ).fetchone()
        if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
            raise SchemaError("Yönetilen Nmap kayıt düzeni beklenen biçimde değil.")
    for table_name in nmap_management_schema_metadata.TABLES:
        if connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0] != 0:
            raise SchemaError("Eski şema sürümünde yönetilen Nmap kaydı bulunamaz.")


def create_nmap_management_schema(connection: sqlite3.Connection) -> None:
    """Create versioned target scopes and immutable managed Nmap plans."""
    names = tuple(nmap_management_schema_metadata.TABLES)
    placeholders = ",".join("?" for _name in names)
    existing = connection.execute(
        f"SELECT 1 FROM sqlite_schema WHERE name IN ({placeholders}) LIMIT 1", names,
    ).fetchone()
    if existing is not None:
        _validate_staged_nmap_management_schema(connection)
        return
    for statement in NMAP_MANAGEMENT_DDL:
        connection.execute(statement)


def create_surface_cname_schema(connection: sqlite3.Connection) -> None:
    """Create approved exact-domain append-only CNAME evidence."""
    for statement in SURFACE_CNAME_DDL:
        connection.execute(statement)


def create_surface_change_notification_schema(connection: sqlite3.Connection) -> None:
    """Create local notices linked to changed surface evidence."""
    for statement in SURFACE_CHANGE_NOTIFICATION_DDL:
        connection.execute(statement)


def create_vulnerability_schema(connection: sqlite3.Connection) -> None:
    """Create versioned official vulnerability-source catalog tables."""
    for statement in VULNERABILITY_DDL:
        connection.execute(statement)


def create_epss_schema(connection: sqlite3.Connection) -> None:
    """Create the current daily EPSS score table."""
    for statement in EPSS_DDL:
        connection.execute(statement)


def create_nvd_schema(connection: sqlite3.Connection) -> None:
    """Create requested NVD CVE records and append-only change evidence."""
    for statement in NVD_DDL:
        connection.execute(statement)


def create_nvd_window_schema(connection: sqlite3.Connection) -> None:
    """Create durable, resumable NVD date-window progress."""
    for statement in NVD_WINDOW_DDL:
        connection.execute(statement)


def create_nvd_window_restart_schema(connection: sqlite3.Connection) -> None:
    """Create append-only audit events for explicit NVD-window restarts."""
    for statement in NVD_WINDOW_RESTART_DDL:
        connection.execute(statement)


def create_product_evidence_schema(connection: sqlite3.Connection) -> None:
    """Create user-verified asset product evidence and append-only history."""
    for statement in PRODUCT_EVIDENCE_DDL:
        connection.execute(statement)


def create_package_evidence_schema(connection: sqlite3.Connection) -> None:
    """Create exact Red Hat RPM evidence and append-only history."""
    for statement in PACKAGE_EVIDENCE_DDL:
        connection.execute(statement)


def create_ubuntu_package_evidence_schema(connection: sqlite3.Connection) -> None:
    """Create verified Ubuntu binary/source package evidence and history."""
    for statement in UBUNTU_PACKAGE_EVIDENCE_DDL:
        connection.execute(statement)


def create_cti_indicator_schema(connection: sqlite3.Connection) -> None:
    """Create canonical IOC identities, sourced claims and append-only history."""
    for statement in CTI_INDICATOR_DDL:
        connection.execute(statement)


def create_cti_feed_schema(connection: sqlite3.Connection) -> None:
    """Create complete-snapshot feed runs and per-assertion provenance."""
    for statement in CTI_FEED_DDL:
        connection.execute(statement)


def create_ransomware_claim_schema(connection: sqlite3.Connection) -> None:
    """Create bounded public-claim snapshot runs and safe local item history."""
    for statement in RANSOMWARE_CLAIM_DDL:
        connection.execute(statement)


def create_ransomlook_claim_schema(connection: sqlite3.Connection) -> None:
    """Create source-isolated RansomLook snapshot runs and safe item history."""
    for statement in RANSOMLOOK_CLAIM_DDL:
        connection.execute(statement)


def create_ransomlook_watch_schema(connection: sqlite3.Connection) -> None:
    """Create source-isolated RansomLook organization-watch history."""
    for statement in RANSOMLOOK_WATCH_DDL:
        connection.execute(statement)


def create_brand_username_watch_schema(connection: sqlite3.Connection) -> None:
    """Create durable, source-minimized social username watch history."""
    for statement in BRAND_USERNAME_WATCH_DDL:
        connection.execute(statement)


def migrate_brand_username_watch_source_schema(
    connection: sqlite3.Connection,
) -> None:
    """Bind every legacy watch to Maigret without rewriting its evidence."""
    connection.execute(
        "ALTER TABLE brand_username_watches ADD COLUMN source_key TEXT NOT NULL "
        "DEFAULT 'maigret' CHECK (source_key IN ('maigret', 'sherlock'))"
    )


def create_brand_username_review_schema(connection: sqlite3.Connection) -> None:
    """Create append-only, exact-state social profile decisions."""
    for statement in BRAND_USERNAME_REVIEW_DDL:
        connection.execute(statement)


def create_brand_username_review_notification_schema(
    connection: sqlite3.Connection,
) -> None:
    """Create deduplicated local notices for possible social impersonation."""
    for statement in BRAND_USERNAME_REVIEW_NOTIFICATION_DDL:
        connection.execute(statement)


def create_ransomware_watch_schema(connection: sqlite3.Connection) -> None:
    """Create durable local organization/domain watches and inbox notices."""
    for statement in RANSOMWARE_WATCH_DDL:
        connection.execute(statement)


def create_ransomware_monitor_session_schema(connection: sqlite3.Connection) -> None:
    """Create durable foreground ransomware monitor sessions and cycle links."""
    for statement in RANSOMWARE_MONITOR_SESSION_DDL:
        connection.execute(statement)


def create_ransomware_identity_review_schema(connection: sqlite3.Connection) -> None:
    """Create append-only analyst decisions for identity-change candidates."""
    for statement in RANSOMWARE_IDENTITY_REVIEW_DDL:
        connection.execute(statement)


def create_ransomware_source_review_schema(connection: sqlite3.Connection) -> None:
    """Create append-only cross-source comparison decision history."""
    for statement in RANSOMWARE_SOURCE_REVIEW_DDL:
        connection.execute(statement)


def create_cti_knowledge_schema(connection: sqlite3.Connection) -> None:
    """Create sourced CTI entities, relationships and append-only claim history."""
    for statement in CTI_KNOWLEDGE_DDL:
        connection.execute(statement)


def create_cti_saved_search_schema(connection: sqlite3.Connection) -> None:
    """Create durable local CTI searches, runs and complete result snapshots."""
    for statement in CTI_SAVED_SEARCH_DDL:
        connection.execute(statement)


def create_cti_saved_search_notification_schema(connection: sqlite3.Connection) -> None:
    """Create local inbox notices for meaningful saved CTI search changes."""
    for statement in CTI_SAVED_SEARCH_NOTIFICATION_DDL:
        connection.execute(statement)


def create_cti_hunting_journal_schema(connection: sqlite3.Connection) -> None:
    """Create append-only tags and analyst notes for durable CTI searches."""
    for statement in CTI_HUNTING_JOURNAL_DDL:
        connection.execute(statement)


def create_webhook_schema(connection: sqlite3.Connection) -> None:
    """Create private destinations, immutable payloads and attempt history."""
    for statement in WEBHOOK_DDL:
        connection.execute(statement)


def create_vulnerability_exposure_schema(connection: sqlite3.Connection) -> None:
    """Create human-reviewed product/CVE exposure state and append-only history."""
    for statement in VULNERABILITY_EXPOSURE_DDL:
        connection.execute(statement)


def create_vulnerability_exposure_suppression_schema(connection: sqlite3.Connection) -> None:
    """Create expiring exposure suppression state and append-only history."""
    for statement in VULNERABILITY_EXPOSURE_SUPPRESSION_DDL:
        connection.execute(statement)


def create_vulnerability_exposure_evidence_schema(connection: sqlite3.Connection) -> None:
    """Create sourced supporting evidence and append-only lifecycle history."""
    for statement in VULNERABILITY_EXPOSURE_EVIDENCE_DDL:
        connection.execute(statement)


def create_vendor_package_evidence_schema(connection: sqlite3.Connection) -> None:
    """Create selected exact RPM/VEX evidence and append-only lifecycle history."""
    for statement in VENDOR_PACKAGE_EVIDENCE_DDL:
        connection.execute(statement)


def create_vulnerability_remediation_schema(connection: sqlite3.Connection) -> None:
    """Create human-approved remediation plans and append-only rechecks."""
    for statement in VULNERABILITY_REMEDIATION_DDL:
        connection.execute(statement)


def migrate_allowlist_expiry_schema(connection: sqlite3.Connection) -> None:
    """Rebuild v8 policy tables while preserving identity and insertion order."""
    connection.execute("DROP INDEX allowlist_active_asset_domain")
    connection.execute("DROP INDEX allowlist_events_entry_id")
    connection.execute("ALTER TABLE allowlist_events RENAME TO allowlist_events_v8")
    connection.execute("ALTER TABLE allowlist_entries RENAME TO allowlist_entries_v8")
    create_allowlist_schema(connection)
    connection.execute(
        "INSERT INTO allowlist_entries "
        "(id, asset_id, asset_value, domain, active, expires_at, reason, created_at, updated_at) "
        "SELECT id, asset_id, asset_value, domain, active, NULL, reason, created_at, updated_at "
        "FROM allowlist_entries_v8 ORDER BY rowid"
    )
    connection.execute(
        "INSERT INTO allowlist_events "
        "(id, entry_id, action, expires_at, reason, created_at) "
        "SELECT id, entry_id, action, NULL, reason, created_at "
        "FROM allowlist_events_v8 ORDER BY rowid"
    )
    connection.execute("DROP TABLE allowlist_events_v8")
    connection.execute("DROP TABLE allowlist_entries_v8")


def backfill_inbox(connection: sqlite3.Connection, created_at: str) -> None:
    """Expose every historical finding without inventing new discoveries or reads.

    Migration time describes arrival in the inbox, not finding discovery time.
    Finding insertion order is retained even if the device clock moved backward.
    """
    for (finding_id,) in connection.execute("SELECT id FROM findings ORDER BY rowid"):
        connection.execute(
            "INSERT INTO notifications (id, finding_id, event_type, origin, created_at, read_at) "
            "VALUES (?, ?, 'finding_created', 'existing', ?, NULL)",
            (str(uuid4()), finding_id, created_at),
        )


def _index_columns(connection: sqlite3.Connection, name: str) -> tuple[str, ...]:
    return tuple(
        row[0] for row in connection.execute(
            "SELECT name FROM pragma_index_info(?) ORDER BY seqno", (name,)
        )
    )


def validate_schema(connection: sqlite3.Connection, *, allow_legacy: bool = False) -> int:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    application_id = connection.execute("PRAGMA application_id").fetchone()[0]
    if application_id != APPLICATION_ID:
        raise SchemaError("Dosya desteklenen bir XTI veritabanı değil.")
    if version in VERSION_TABLES and version < SCHEMA_VERSION and not allow_legacy:
        raise SchemaError(
            "Veritabanı eski sürümde. Dosya değiştirilmedi; "
            "yedekli geçiş için './xti migrate' çalıştırın."
        )
    if version not in VERSION_TABLES:
        raise SchemaError(
            "Veritabanı sürümü bu uygulamayla uyumlu değil. "
            "Dosya değiştirilmedi; uygun uygulama sürümünü kullanın."
        )
    tables = {name: TABLES[name] for name in VERSION_TABLES[version]}
    if 65 <= version < 68:
        tables.update(global_saved_search_schema_metadata.LEGACY_TABLES)
    if 61 <= version < 69:
        tables["collection_step_receipts"] = [
            column for column in TABLES["collection_step_receipts"]
            if column[0] in COLLECTION_RECEIPT_V68_COLUMNS
        ]
    if 69 <= version < 85:
        tables['collection_step_receipts'] = [column for column in TABLES['collection_step_receipts']
                                              if column[0] in COLLECTION_RECEIPT_V84_COLUMNS]
    if 56 <= version < 61:
        tables["collection_step_receipts"] = [
            column for column in TABLES["collection_step_receipts"]
            if column[0] in COLLECTION_RECEIPT_V60_COLUMNS
        ]
    if 47 <= version < 50:
        tables["brand_username_watches"] = BRAND_USERNAME_WATCH_V49_COLUMNS
    if version == 8:
        tables.update(ALLOWLIST_V8_TABLES)
    indexes = {name: details for name, details in INDEXES.items() if details[0] in tables}
    objects = set(connection.execute(
        "SELECT name, type FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
    ).fetchall())
    if version < 70 and any(
        name.startswith("surface_nmap_checks") for name, _object_type in objects
    ):
        _validate_staged_surface_nmap_schema(connection)
        objects -= {
            ("surface_nmap_checks", "table"),
            ("surface_nmap_checks_asset_id", "index"),
            ("surface_nmap_checks_execution_id", "index"),
        }
    managed_nmap_objects = {
        (
            statement.split()[2],
            "index" if statement.startswith("CREATE INDEX") else "table",
        )
        for statement in NMAP_MANAGEMENT_DDL
    }
    if version < 71 and objects.intersection(managed_nmap_objects):
        _validate_staged_nmap_management_schema(connection)
        objects -= managed_nmap_objects
    job_objects = {(name, "table") for name in nmap_jobs_schema.TABLES}
    if version < 72 and objects.intersection(job_objects):
        nmap_jobs_schema.validate(connection, empty=True)
        objects -= job_objects
    if version >= 72:
        nmap_jobs_schema.validate(connection)
    warninglist_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in warninglist_schema.DDL}
    if version < 73 and objects.intersection(warninglist_objects):
        warninglist_schema.validate(connection, empty=True)
        objects -= warninglist_objects
    if version >= 73:
        warninglist_schema.validate(connection)
    enrichment_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in enrichment_schema.DDL}
    if version < 74 and objects.intersection(enrichment_objects):
        enrichment_schema.validate(connection, empty=True)
        objects -= enrichment_objects
    if version >= 74:
        enrichment_schema.validate(connection)
    history_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in research_history_schema.DDL}
    if version < 75 and objects.intersection(history_objects):
        research_history_schema.validate(connection, empty=True)
        objects -= history_objects
    if version >= 75:
        research_history_schema.validate(connection)
    investigation_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in investigation_schema.DDL}
    if version < 76 and objects.intersection(investigation_objects):
        investigation_schema.validate(connection, empty=True)
        objects -= investigation_objects
    if version >= 76:
        investigation_schema.validate(connection)
    report_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in report_schema.DDL}
    if version < 77 and objects.intersection(report_objects):
        report_schema.validate(connection, empty=True)
        objects -= report_objects
    if version >= 77:
        report_schema.validate(connection)
    evidence_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in evidence_schema.DDL}
    if version < 78 and objects.intersection(evidence_objects):
        evidence_schema.validate(connection, empty=True)
        objects -= evidence_objects
    if version >= 78:
        evidence_schema.validate(connection)
    document_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in document_storage_schema.DDL}
    if version < 79 and objects.intersection(document_objects):
        document_storage_schema.validate(connection, empty=True)
        objects -= document_objects
    if version >= 79:
        document_storage_schema.validate(connection)
    relationship_objects = {(statement.split()[2], 'table') for statement in relationship_notification_schema.DDL}
    if version < 80 and objects.intersection(relationship_objects):
        relationship_notification_schema.validate(connection, empty=True)
        objects -= relationship_objects
    if version >= 80:
        relationship_notification_schema.validate(connection)
    social_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in social_discovery_schema.DDL}
    if version < 81 and objects.intersection(social_objects):
        social_discovery_schema.validate(connection, empty=True)
        objects -= social_objects
    if version >= 81:
        social_discovery_schema.validate(connection)
    enrichment_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in social_enrichment_schema.DDL}
    if version < 82 and objects.intersection(enrichment_objects):
        social_enrichment_schema.validate(connection, empty=True)
        objects -= enrichment_objects
    if version >= 82:
        social_enrichment_schema.validate(connection)
    tracking_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in social_tracking_schema.DDL}
    if version < 83 and objects.intersection(tracking_objects):
        social_tracking_schema.validate(connection, empty=True)
        objects -= tracking_objects
    if version >= 83:
        social_tracking_schema.validate(connection)
    group_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in group_schema.DDL}
    if version < 86 and objects.intersection(group_objects):
        group_schema.validate(connection, empty=True)
        objects -= group_objects
    if version >= 86:
        group_schema.validate(connection)
    group_operation_objects = {(statement.split()[2], statement.split()[1].lower()) for statement in group_operations_schema.DDL}
    if version < 87 and objects.intersection(group_operation_objects):
        group_operations_schema.validate(connection, empty=True)
        objects -= group_operation_objects
    if version >= 87:
        group_operations_schema.validate(connection)
    expected = {(name, "table") for name in tables} | {(name, "index") for name in indexes}
    if objects != expected:
        raise SchemaError("Veritabanının kayıt düzeni beklenen biçimde değil.")
    if "mention_group_events" in tables:
        for statement in MENTION_GROUP_DDL:
            object_type, name = statement.split()[1].lower(), statement.split()[2]
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()
            if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
                raise SchemaError("Firma izleme grubu kayıt düzeni beklenen biçimde değil.")
    if "mentions_runs" in tables:
        for statement in MENTIONS_DDL:
            object_type, name = statement.split()[1].lower(), statement.split()[2]
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()
            if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
                raise SchemaError("İçerik araması kayıt düzeni beklenen biçimde değil.")
    if "news_runs" in tables:
        for statement in NEWS_DDL:
            object_type, name = statement.split()[1].lower(), statement.split()[2]
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()
            if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
                raise SchemaError("Haber kayıt düzeni beklenen biçimde değil.")
    if "global_saved_searches" in tables:
        for statement in (GLOBAL_SAVED_SEARCH_CURRENT_DDL if version >= 68 else GLOBAL_SAVED_SEARCH_DDL):
            object_type, name = statement.split()[1].lower(), statement.split()[2]
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()
            if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
                raise SchemaError("Genel kayıtlı arama düzeni beklenen biçimde değil.")
    if "supplier_watches" in tables:
        for statement in SUPPLIER_WATCH_DDL:
            object_type, name = statement.split()[1].lower(), statement.split()[2]
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()
            if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
                raise SchemaError("Tedarikçi izleme kayıt düzeni beklenen biçimde değil.")
    if "public_notice_watches" in tables:
        for statement in PUBLIC_NOTICE_WATCH_DDL:
            object_type, name = statement.split()[1].lower(), statement.split()[2]
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()
            if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
                raise SchemaError("Kamu olay izleme kayıt düzeni beklenen biçimde değil.")
    if "public_notice_runs" in tables:
        for statement in PUBLIC_NOTICE_DDL:
            object_type, name = statement.split()[1].lower(), statement.split()[2]
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()
            if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
                raise SchemaError("Kamu olay kataloğu kayıt düzeni beklenen biçimde değil.")
    if "attack_catalog_runs" in tables:
        for name, statement in zip(('attack_catalog_runs', 'attack_catalog_entities', 'attack_catalog_relationships', 'attack_catalog_phases', 'attack_catalog_changes', 'attack_catalog_entities_active_external', 'attack_catalog_relationships_source', 'attack_catalog_relationships_target', 'attack_catalog_changes_record_sequence', 'attack_catalog_changes_run_sequence'), ATTACK_CATALOG_DDL):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute("SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type)).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("ATT&CK katalog kayıt düzeni beklenen biçimde değil.")
    if "ransomlook_watch_notifications" in tables:
        for statement in RANSOMLOOK_NOTIFICATION_DDL:
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            name = statement.split()[2]
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()
            if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
                raise SchemaError("RansomLook bildirim düzeni beklenen biçimde değil.")
    if "organizations" in tables:
        for statement in ORGANIZATION_DDL:
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            name = statement.split()[2]
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()
            if declaration is None or " ".join(declaration[0].split()) != " ".join(statement.split()):
                raise SchemaError("Kuruluş kayıt düzeni beklenen biçimde değil.")
    if "collection_sessions" in tables:
        collection_ddl = (COLLECTION_HISTORY_V60_DDL if version < 61 else
                          COLLECTION_HISTORY_V68_DDL if version < 69 else
                          COLLECTION_HISTORY_V84_DDL if version < 85 else COLLECTION_HISTORY_DDL)
        for statement in collection_ddl:
            words = statement.split()
            object_type, name = words[1].lower(), words[2]
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Toplama oturum kayıt düzeni beklenen biçimde değil.")
    if "collection_profiles" in tables:
        for name, statement in zip(
            (
                "collection_profiles", "collection_profile_events",
                "collection_profiles_active_name", "collection_profile_events_profile_sequence",
            ),
            COLLECTION_PROFILE_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=? AND type=?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Toplama profil kayıt düzeni beklenen biçimde değil.")
    if "notifications" in tables:
        # table_info cannot distinguish INTEGER PRIMARY KEY from AUTOINCREMENT.
        # Require our canonical declaration, retained by SQLite backup/VACUUM,
        # so a retired sequence can never be reused by a later notification.
        declaration = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name = 'notifications' AND type = 'table'"
        ).fetchone()[0]
        if " ".join(declaration.split()) != " ".join(INBOX_DDL[0].split()):
            raise SchemaError("Veritabanının bildirim sıra düzeni beklenen biçimde değil.")
    if "monitor_runs" in tables:
        for name, statement in zip(("monitor_runs", "monitor_jobs"), MONITOR_DDL):
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = 'table'", (name,)
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Veritabanının izleme denemesi düzeni beklenen biçimde değil.")
    if "ransomware_identity_review_events" in tables:
        declaration = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name = "
            "'ransomware_identity_review_events' AND type = 'table'"
        ).fetchone()[0]
        if " ".join(declaration.split()) != " ".join(
            RANSOMWARE_IDENTITY_REVIEW_DDL[0].split()
        ):
            raise SchemaError("Kimlik adayı karar sıra düzeni beklenen biçimde değil.")
    if "ransomware_source_review_events" in tables:
        for name, statement in zip(
            (
                "ransomware_source_review_events",
                "ransomware_source_review_events_comparison_sequence",
                "ransomware_source_review_events_decision_sequence",
            ),
            RANSOMWARE_SOURCE_REVIEW_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError(
                    "Kaynak karşılaştırma karar düzeni beklenen biçimde değil."
                )
    if "ransomlook_claim_runs" in tables:
        for name, statement in zip(
            (
                "ransomlook_claim_runs", "ransomlook_claim_run_items",
                "ransomlook_claim_runs_source_sequence",
                "ransomlook_claim_run_items_run_action",
            ),
            RANSOMLOOK_CLAIM_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("RansomLook geçmiş kayıt düzeni beklenen biçimde değil.")
    if "ransomlook_watches" in tables:
        for name, statement in zip(
            (
                "ransomlook_watches", "ransomlook_watch_events",
                "ransomlook_watch_runs", "ransomlook_watch_run_items",
                "ransomlook_watch_events_watch_recorded",
                "ransomlook_watch_runs_watch_sequence",
                "ransomlook_watch_run_items_run_action",
            ),
            RANSOMLOOK_WATCH_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("RansomLook izleme kayıt düzeni beklenen biçimde değil.")
    if "brand_username_watches" in tables:
        watch_ddl = (
            BRAND_USERNAME_WATCH_V49_DDL
            if version < 50
            else BRAND_USERNAME_WATCH_DDL
        )
        for name, statement in zip(
            (
                "brand_username_watches", "brand_username_watch_events",
                "brand_username_watch_runs", "brand_username_watch_run_items",
                "brand_username_watch_events_watch_recorded",
                "brand_username_watch_runs_watch_sequence",
                "brand_username_watch_run_items_run_action",
            ),
            watch_ddl,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError(
                    "Sosyal kullanıcı adı izleme kayıt düzeni beklenen biçimde değil."
                )
    if "brand_username_review_events" in tables:
        for name, statement in zip(
            (
                "brand_username_review_events",
                "brand_username_review_events_candidate_sequence",
                "brand_username_review_events_watch_platform_sequence",
            ),
            BRAND_USERNAME_REVIEW_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Profil kararı kayıt düzeni beklenen biçimde değil.")
    if "brand_username_review_notifications" in tables:
        for name, statement in zip(
            (
                "brand_username_review_notifications",
                "brand_username_review_notifications_read_sequence",
            ),
            BRAND_USERNAME_REVIEW_NOTIFICATION_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Sosyal profil bildirim düzeni beklenen biçimde değil.")
    if "allowlist_entries" in tables:
        allowlist_ddl = ALLOWLIST_V8_DDL if version == 8 else ALLOWLIST_DDL
        for name, statement in zip(("allowlist_entries", "allowlist_events"), allowlist_ddl):
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = 'table'", (name,)
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Veritabanının istisna kayıt düzeni beklenen biçimde değil.")
    if "asset_criticalities" in tables:
        for name, statement in zip(
            (
                "asset_criticalities", "asset_criticality_events",
                "asset_criticality_events_asset_id",
            ),
            ASSET_CRITICALITY_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Varlık önemi kayıt düzeni beklenen biçimde değil.")
    if "suppliers" in tables:
        for name, statement in zip(
            (
                "suppliers", "supplier_events", "suppliers_active_name",
                "supplier_events_supplier_sequence",
            ),
            SUPPLIER_INVENTORY_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Tedarikçi envanteri kayıt düzeni beklenen biçimde değil.")
    if "supplier_candidates" in tables:
        for name, statement in zip(
            (
                "supplier_candidates", "supplier_candidate_evidence",
                "supplier_candidate_resolution_events",
                "supplier_candidates_status_current",
                "supplier_candidate_evidence_candidate_sequence",
                "supplier_candidate_resolutions_candidate_sequence",
            ),
            SUPPLIER_CANDIDATE_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Tedarikçi adayı kayıt düzeni beklenen biçimde değil.")
    if "cases" in tables:
        for name, statement in zip(
            (
                "cases", "case_evidence", "case_tasks", "case_activities",
                "cases_status_priority_updated", "case_evidence_case_active_updated",
                "case_tasks_case_status_due", "case_activities_case_sequence",
            ),
            CASE_V62_DDL if version < 63 else tuple((group_schema.CASE_EVIDENCE_DDL if version >= 86 else social_tracking_schema.CASE_EVIDENCE_DDL if version >= 83 else relationship_notification_schema.CASE_EVIDENCE_DDL) if statement == CASE_EVIDENCE_DDL else statement for statement in CASE_DDL) if version >= 80 else CASE_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Vaka yönetimi kayıt düzeni beklenen biçimde değil.")
    if "surface_scopes" in tables:
        for name, statement in zip(
            ("surface_scopes", "surface_scope_events", "surface_checks"), SURFACE_DDL
        ):
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = 'table'", (name,)
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Veritabanının dış yüzey kayıt düzeni beklenen biçimde değil.")
    if "surface_candidates" in tables:
        discovery_ddl = (
            SURFACE_DISCOVERY_V50_DDL if version < 51 else SURFACE_DISCOVERY_DDL
        )
        for name, statement in zip(
            ("surface_candidates", "surface_candidate_sources", "surface_candidate_events"),
            discovery_ddl,
        ):
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = 'table'", (name,)
            ).fetchone()[0]
            accepted = {" ".join(statement.split())}
            if version < 51 and name == "surface_candidate_sources":
                accepted.add(" ".join(SURFACE_DISCOVERY_DDL[1].split()))
            if " ".join(declaration.split()) not in accepted:
                raise SchemaError("Veritabanının pasif dış yüzey keşif düzeni beklenen biçimde değil.")
    if "surface_discovery_runs" in tables:
        discovery_history_ddl = (
            SURFACE_DISCOVERY_HISTORY_V50_DDL
            if version < 51 else SURFACE_DISCOVERY_HISTORY_DDL
        )
        for name, statement in zip(
            (
                "surface_discovery_runs", "surface_candidate_notifications",
                "surface_discovery_runs_asset_sequence",
                "surface_candidate_notifications_read_sequence",
            ),
            discovery_history_ddl,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            accepted = {" ".join(statement.split())}
            if version < 51 and name == "surface_discovery_runs":
                accepted.add(" ".join(SURFACE_DISCOVERY_HISTORY_DDL[0].split()))
            if " ".join(declaration.split()) not in accepted:
                raise SchemaError("Pasif keşif geçmişi veya bildirim düzeni beklenen biçimde değil.")
    if "surface_mail_checks" in tables:
        for name, statement in zip(
            ("surface_mail_checks", "surface_mail_checks_asset_id"), SURFACE_MAIL_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("E-posta DNS kayıt düzeni beklenen biçimde değil.")
    if "surface_service_checks" in tables:
        for name, statement in zip(
            ("surface_service_checks", "surface_service_checks_asset_id"),
            SURFACE_SERVICE_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Servis kontrol kayıt düzeni beklenen biçimde değil.")
    if "surface_nmap_checks" in tables:
        for name, statement in zip(
            (
                "surface_nmap_checks", "surface_nmap_checks_asset_id",
                "surface_nmap_checks_execution_id",
            ),
            SURFACE_NMAP_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Nmap kontrol kayıt düzeni beklenen biçimde değil.")
    if "surface_nmap_target_scopes" in tables:
        for statement in NMAP_MANAGEMENT_DDL:
            name = statement.split()[2]
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()
            if (
                declaration is None
                or " ".join(declaration[0].split()) != " ".join(statement.split())
            ):
                raise SchemaError("Yönetilen Nmap kayıt düzeni beklenen biçimde değil.")
    if "surface_cname_checks" in tables:
        for name, statement in zip(
            ("surface_cname_checks", "surface_cname_checks_asset_id"),
            SURFACE_CNAME_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("CNAME kontrol kayıt düzeni beklenen biçimde değil.")
    if "surface_change_notifications" in tables:
        for name, statement in zip(
            (
                "surface_change_notifications",
                "surface_change_notifications_read_sequence",
            ),
            SURFACE_CHANGE_NOTIFICATION_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Dış yüzey değişiklik bildirim düzeni beklenen biçimde değil.")
    if "vulnerability_source_runs" in tables:
        for name, statement in zip(
            (
                "vulnerability_source_runs", "kev_entries", "kev_entry_events",
                "vulnerability_source_runs_source_sequence", "kev_entries_active_cve",
                "kev_entry_events_cve_id",
            ),
            VULNERABILITY_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Zafiyet kataloğu kayıt düzeni beklenen biçimde değil.")
    if "epss_scores" in tables:
        for name, statement in zip(
            ("epss_scores", "epss_scores_active_cve"), EPSS_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("EPSS kayıt düzeni beklenen biçimde değil.")
    if "nvd_cve_records" in tables:
        for name, statement in zip(
            ("nvd_cve_records", "nvd_cve_events", "nvd_cve_events_cve_id"), NVD_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("NVD CVE kayıt düzeni beklenen biçimde değil.")
    if "nvd_window_syncs" in tables:
        for name, statement in zip(
            ("nvd_window_syncs", "nvd_window_syncs_status_updated"),
            NVD_WINDOW_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("NVD pencere ilerleme düzeni beklenen biçimde değil.")
    if "nvd_window_restart_events" in tables:
        for name, statement in zip(
            (
                "nvd_window_restart_events",
                "nvd_window_restart_events_sync_recorded",
            ),
            NVD_WINDOW_RESTART_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("NVD pencere yeniden başlatma düzeni beklenen biçimde değil.")
    if "asset_products" in tables:
        for name, statement in zip(
            (
                "asset_products", "asset_product_events",
                "asset_products_active_asset", "asset_product_events_product_id",
            ),
            PRODUCT_EVIDENCE_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Varlık ürün kanıtı kayıt düzeni beklenen biçimde değil.")
    if "asset_packages" in tables:
        for name, statement in zip(
            (
                "asset_packages", "asset_package_events",
                "asset_packages_active_asset", "asset_package_events_package_id",
            ),
            PACKAGE_EVIDENCE_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("RPM paket kanıtı kayıt düzeni beklenen biçimde değil.")
    if "ubuntu_asset_packages" in tables:
        for name, statement in zip(
            (
                "ubuntu_asset_packages", "ubuntu_asset_package_events",
                "ubuntu_asset_packages_active_asset",
                "ubuntu_asset_package_events_package_id",
            ),
            UBUNTU_PACKAGE_EVIDENCE_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Ubuntu paket kanıtı kayıt düzeni beklenen biçimde değil.")
    if "vulnerability_exposures" in tables:
        for name, statement in zip(
            (
                "vulnerability_exposures", "vulnerability_exposure_events",
                "vulnerability_exposures_status_suppressed",
                "vulnerability_exposure_events_exposure_id",
            ),
            VULNERABILITY_EXPOSURE_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Zafiyet maruziyet inceleme düzeni beklenen biçimde değil.")
    if "vulnerability_exposure_suppressions" in tables:
        for name, statement in zip(
            (
                "vulnerability_exposure_suppressions",
                "vulnerability_exposure_suppression_events",
                "vulnerability_exposure_suppressions_active_exposure",
                "vulnerability_exposure_suppression_events_suppression_id",
            ),
            VULNERABILITY_EXPOSURE_SUPPRESSION_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Süreli maruziyet bastırma düzeni beklenen biçimde değil.")
    if "vulnerability_reassessment_runs" in tables:
        for name, statement in zip(
            (
                "vulnerability_reassessment_runs",
                "vulnerability_reassessment_items",
                "vulnerability_reassessment_items_run_id",
            ),
            VULNERABILITY_REASSESSMENT_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Yeniden değerlendirme kayıt düzeni beklenen biçimde değil.")
    if "vulnerability_change_notifications" in tables:
        for name, statement in zip(
            (
                "vulnerability_change_notifications",
                "vulnerability_change_notifications_read_sequence",
            ),
            VULNERABILITY_CHANGE_NOTIFICATION_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Zafiyet değişiklik bildirim düzeni beklenen biçimde değil.")
    if "vulnerability_exposure_evidence" in tables:
        for name, statement in zip(
            (
                "vulnerability_exposure_evidence",
                "vulnerability_exposure_evidence_events",
                "vulnerability_exposure_evidence_active_exposure",
                "vulnerability_exposure_evidence_events_evidence_id",
            ),
            VULNERABILITY_EXPOSURE_EVIDENCE_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Maruziyet destek kanıtı kayıt düzeni beklenen biçimde değil.")
    if "vulnerability_vendor_package_evidence" in tables:
        for name, statement in zip(
            (
                "vulnerability_vendor_package_evidence",
                "vulnerability_vendor_package_evidence_events",
                "vulnerability_vendor_package_evidence_active_exposure",
                "vulnerability_vendor_package_evidence_events_evidence_id",
            ),
            VENDOR_PACKAGE_EVIDENCE_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Kesin üretici paket kanıtı kayıt düzeni beklenen biçimde değil.")
    if "vulnerability_remediations" in tables:
        for name, statement in zip(
            (
                "vulnerability_remediations", "vulnerability_remediation_events",
                "vulnerability_remediations_exposure_state",
                "vulnerability_remediation_events_remediation_id",
            ),
            VULNERABILITY_REMEDIATION_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?", (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Zafiyet düzeltme kayıt düzeni beklenen biçimde değil.")
    if "webhook_destinations" in tables:
        for name, statement in zip(
            (
                "webhook_destinations", "webhook_destination_events",
                "webhook_deliveries", "webhook_delivery_attempts",
                "webhook_destinations_active_name",
                "webhook_destination_events_destination_sequence",
                "webhook_deliveries_status_sequence",
                "webhook_delivery_attempts_delivery_number",
            ),
            WEBHOOK_DDL,
        ):
            object_type = "index" if statement.startswith("CREATE INDEX") else "table"
            declaration = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = ? AND type = ?",
                (name, object_type),
            ).fetchone()[0]
            if " ".join(declaration.split()) != " ".join(statement.split()):
                raise SchemaError("Webhook teslim kayıt düzeni beklenen biçimde değil.")
    for name, columns in tables.items():
        actual = [tuple(row) for row in connection.execute(
            'SELECT name, type, "notnull", pk FROM pragma_table_info(?) ORDER BY cid', (name,)
        )]
        if actual != columns:
            raise SchemaError("Veritabanının alanları beklenen biçimde değil.")
        unique_columns = {
            _index_columns(connection, row[1])
            for row in connection.execute("SELECT * FROM pragma_index_list(?)", (name,))
            if row[2] and not row[4]
        }
        expected_unique = UNIQUE_KEYS[name]
        if name == 'collection_step_receipts' and version < 85:
            expected_unique = expected_unique - {('social_tracking_run_id',)}
        if name == "collection_step_receipts" and version < 69:
            expected_unique = expected_unique - {("news_run_id",), ("saved_search_run_id",)}
        if name == "collection_step_receipts" and version < 61:
            expected_unique = expected_unique - {("public_notice_run_id",)}
        if not expected_unique.issubset(unique_columns):
            raise SchemaError("Veritabanında gerekli tekillik kontrolü eksik.")
        keys = {tuple(row) for row in connection.execute(
            'SELECT "table", "from", "to", on_update, on_delete '
            "FROM pragma_foreign_key_list(?)", (name,)
        )}
        expected_keys = FOREIGN_KEYS[name]
        if name == 'collection_step_receipts' and version < 85:
            expected_keys = expected_keys - {('social_tracking_journal', 'social_tracking_run_id', 'id', 'NO ACTION', 'RESTRICT')}
        if name == "collection_step_receipts" and version < 69:
            expected_keys = expected_keys - {
                ("news_runs", "news_run_id", "id", "NO ACTION", "RESTRICT"),
                ("global_saved_search_runs", "saved_search_run_id", "id", "NO ACTION", "RESTRICT"),
            }
        if name == "collection_step_receipts" and version < 61:
            expected_keys = expected_keys - {
                ("public_notice_runs", "public_notice_run_id", "id", "NO ACTION", "RESTRICT"),
            }
        if keys != expected_keys:
            raise SchemaError("Veritabanının kayıt bağlantıları beklenen biçimde değil.")
    for name, (table, columns) in indexes.items():
        row = connection.execute(
            "SELECT tbl_name FROM sqlite_schema WHERE name = ? AND type = 'index'", (name,)
        ).fetchone()
        if row != (table,) or _index_columns(connection, name) != columns:
            raise SchemaError("Veritabanının arama dizinleri beklenen biçimde değil.")
    return version
