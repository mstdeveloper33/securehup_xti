"""Local SQLite storage, explicit migration and non-overwriting snapshots."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Iterator
from uuid import uuid4
from xti.adapters.private_directories import create_private_directory
from xti.adapters.nmap_jobs_schema import create as create_nmap_jobs_schema
from xti.adapters.warninglist_schema import create as create_warninglist_schema
from xti.adapters.enrichment_schema import create as create_enrichment_schema
from xti.adapters.research_history_schema import create as create_research_history_schema
from xti.adapters.investigation_schema import create as create_investigation_schema
from xti.adapters.report_schema import create as create_report_schema
from xti.adapters.evidence_schema import create as create_evidence_schema
from xti.adapters.document_storage_schema import create as create_document_storage_schema

from xti.domain.assets import Asset
from xti.adapters.schema import (
    APPLICATION_ID,
    ASSETS_DDL,
    SCHEMA_VERSION,
    SchemaError,
    backfill_inbox,
    create_asset_criticality_schema,
    create_supplier_inventory_schema,
    create_supplier_candidate_schema,
    create_case_schema,
    migrate_case_public_notice_schema,
    create_collection_profile_schema,
    create_collection_history_schema,
    migrate_collection_public_notice_schema,
    migrate_collection_news_schema,
    create_organization_schema,
    create_ransomlook_notification_schema,
    create_attack_catalog_schema,
    create_public_notice_schema,
    create_public_notice_watch_schema,
    create_supplier_watch_schema,
    create_global_saved_search_schema,
    create_news_schema,
    create_mentions_schema,
    create_mention_group_schema,
    upgrade_global_saved_search_scopes,
    create_epss_schema,
    create_nvd_schema,
    create_nvd_window_schema,
    create_nvd_window_restart_schema,
    create_package_evidence_schema,
    create_ubuntu_package_evidence_schema,
    create_cti_indicator_schema,
    create_cti_feed_schema,
    create_ransomware_claim_schema,
    create_ransomlook_claim_schema,
    create_ransomlook_watch_schema,
    create_brand_username_watch_schema,
    migrate_brand_username_watch_source_schema,
    create_brand_username_review_schema,
    create_brand_username_review_notification_schema,
    create_ransomware_monitor_session_schema,
    create_ransomware_identity_review_schema,
    create_ransomware_source_review_schema,
    create_ransomware_watch_schema,
    create_cti_knowledge_schema,
    create_cti_saved_search_schema,
    create_cti_saved_search_notification_schema,
    create_cti_hunting_journal_schema,
    create_webhook_schema,
    create_product_evidence_schema,
    create_vulnerability_exposure_schema,
    create_vulnerability_exposure_suppression_schema,
    create_vulnerability_reassessment_schema,
    create_vulnerability_change_notification_schema,
    create_vulnerability_exposure_evidence_schema,
    create_vendor_package_evidence_schema,
    create_vulnerability_remediation_schema,
    create_assessments_schema,
    create_allowlist_schema,
    migrate_allowlist_expiry_schema,
    create_findings_schema,
    create_inbox_schema,
    create_jobs_schema,
    create_monitor_schema,
    create_operations_schema,
    create_surface_discovery_schema,
    create_surface_discovery_history_schema,
    migrate_surface_discovery_provider_schema,
    create_surface_mail_schema,
    create_surface_service_schema,
    create_surface_nmap_schema,
    create_nmap_management_schema,
    create_surface_cname_schema,
    create_surface_change_notification_schema,
    create_surface_schema,
    create_vulnerability_schema,
    validate_schema,
)


class StorageError(RuntimeError):
    """A persistence operation failed; the message is safe for the CLI."""


class SQLiteAssetRepository:
    """SQLite implementation with explicit initialization and no read side effects."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser().absolute()

    @staticmethod
    def _validate_schema(
        connection: sqlite3.Connection, *, allow_legacy: bool = False
    ) -> int:
        try:
            return validate_schema(connection, allow_legacy=allow_legacy)
        except SchemaError as error:
            raise StorageError(str(error)) from error

    @staticmethod
    def _check_integrity(connection: sqlite3.Connection) -> None:
        result = connection.execute("PRAGMA quick_check").fetchall()
        if result != [("ok",)]:
            raise StorageError("Veritabanı bütünlük kontrolünden geçemedi.")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise StorageError("Veritabanında kopuk kayıt bağlantıları bulundu.")

    @contextmanager
    def _connection(
        self, *, readonly: bool = False, allow_legacy: bool = False
    ) -> Iterator[sqlite3.Connection]:
        if self.path.is_symlink() or not self.path.is_file():
            raise StorageError("Veritabanı bulunamadı. Önce 'xti init' çalıştırın.")
        mode = "ro" if readonly else "rw"
        connection = None
        try:
            connection = sqlite3.connect(
                self.path.as_uri() + f"?mode={mode}",
                uri=True,
                timeout=5,
                isolation_level=None,
            )
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA foreign_keys=ON")
            self._validate_schema(connection, allow_legacy=allow_legacy)
            yield connection
        except sqlite3.Error as error:
            raise StorageError(
                "Veritabanı işlemi tamamlanamadı. Dosya izinlerini, "
                "boş disk alanını ve veritabanının durumunu kontrol edin."
            ) from error
        finally:
            if connection is not None:
                connection.close()

    def initialize(self) -> None:
        """Create the current schema or validate an existing database unchanged."""
        if self.path.exists() or self.path.is_symlink():
            with self._connection(readonly=True) as connection:
                self._check_integrity(connection)
            return
        temporary = None
        try:
            create_private_directory(self.path.parent)
            temporary = self._temporary_path(self.path.parent)
            connection = sqlite3.connect(temporary)
            try:
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(ASSETS_DDL)
                create_asset_criticality_schema(connection)
                create_supplier_inventory_schema(connection)
                create_findings_schema(connection)
                create_jobs_schema(connection)
                create_assessments_schema(connection)
                create_operations_schema(connection)
                create_inbox_schema(connection)
                create_monitor_schema(connection)
                create_allowlist_schema(connection)
                create_surface_schema(connection)
                create_surface_discovery_schema(connection)
                create_surface_discovery_history_schema(connection)
                create_surface_mail_schema(connection)
                create_surface_service_schema(connection)
                create_surface_nmap_schema(connection)
                create_nmap_management_schema(connection)
                create_nmap_jobs_schema(connection)
                create_warninglist_schema(connection)
                create_enrichment_schema(connection)
                create_research_history_schema(connection)
                create_investigation_schema(connection)
                create_report_schema(connection)
                create_evidence_schema(connection)
                create_document_storage_schema(connection)
                create_surface_cname_schema(connection)
                create_supplier_candidate_schema(connection)
                create_case_schema(connection)
                create_collection_profile_schema(connection)
                create_public_notice_schema(connection)
                create_collection_history_schema(connection)
                create_organization_schema(connection)
                create_public_notice_watch_schema(connection)
                create_ransomlook_notification_schema(connection)
                create_attack_catalog_schema(connection)
                create_surface_change_notification_schema(connection)
                create_vulnerability_schema(connection)
                create_epss_schema(connection)
                create_nvd_schema(connection)
                create_nvd_window_schema(connection)
                create_nvd_window_restart_schema(connection)
                create_product_evidence_schema(connection)
                create_vulnerability_exposure_schema(connection)
                create_vulnerability_exposure_suppression_schema(connection)
                create_vulnerability_reassessment_schema(connection)
                create_vulnerability_change_notification_schema(connection)
                create_vulnerability_exposure_evidence_schema(connection)
                create_package_evidence_schema(connection)
                create_ubuntu_package_evidence_schema(connection)
                create_vendor_package_evidence_schema(connection)
                create_vulnerability_remediation_schema(connection)
                create_cti_indicator_schema(connection)
                create_cti_feed_schema(connection)
                create_ransomware_claim_schema(connection)
                create_ransomlook_claim_schema(connection)
                create_ransomlook_watch_schema(connection)
                create_brand_username_watch_schema(connection)
                create_brand_username_review_schema(connection)
                create_brand_username_review_notification_schema(connection)
                create_ransomware_watch_schema(connection)
                create_ransomware_monitor_session_schema(connection)
                create_ransomware_identity_review_schema(connection)
                create_ransomware_source_review_schema(connection)
                create_cti_knowledge_schema(connection)
                create_cti_saved_search_schema(connection)
                create_cti_saved_search_notification_schema(connection)
                create_cti_hunting_journal_schema(connection)
                create_webhook_schema(connection)
                create_supplier_watch_schema(connection)
                create_global_saved_search_schema(connection)
                create_news_schema(connection)
                create_mentions_schema(connection)
                upgrade_global_saved_search_scopes(connection)
                create_mention_group_schema(connection)
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                self._validate_schema(connection)
                self._check_integrity(connection)
                connection.commit()
            finally:
                connection.close()
            self._flush_file(temporary)
            try:
                os.link(temporary, self.path)
            except FileExistsError:
                # A concurrent init may have won; accept only our valid schema.
                with self._connection(readonly=True) as existing:
                    self._check_integrity(existing)
        except (OSError, sqlite3.Error) as error:
            raise StorageError(
                "Veritabanı oluşturulamadı. Hedef klasörün yazılabilir olduğunu kontrol edin."
            ) from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _asset(row: tuple[str, str, str]) -> Asset:
        return Asset(id=row[0], value=row[1], created_at=row[2])

    def add(self, domain: str) -> tuple[Asset, bool]:
        """Persist an already normalized domain, preserving an existing identity."""
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    "INSERT INTO assets (id, value, created_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(value) DO NOTHING",
                    (str(uuid4()), domain, datetime.now(timezone.utc).isoformat()),
                )
                created = cursor.rowcount == 1
                row = connection.execute(
                    "SELECT id, value, created_at FROM assets WHERE value = ?", (domain,)
                ).fetchone()
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return self._asset(row), created

    def list(self) -> list[Asset]:
        """Read assets in stable order; do not initialize a missing database."""
        with self._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT id, value, created_at FROM assets ORDER BY value, id"
            ).fetchall()
        return [self._asset(row) for row in rows]

    def inspect(self) -> dict[str, int | str]:
        """Inspect the known schema and SQLite integrity without writing records."""
        with self._connection(readonly=True) as connection:
            self._check_integrity(connection)
            count = connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            organization_count = connection.execute("SELECT COUNT(*) FROM organizations").fetchone()[0]
            organization_link_count = connection.execute("SELECT COUNT(*) FROM organization_links").fetchone()[0]
            active_organization_count = connection.execute("SELECT COUNT(*) FROM organizations WHERE active=1").fetchone()[0]
            collection_sessions = connection.execute("SELECT COUNT(*) FROM collection_sessions").fetchone()[0]
            collection_session_steps = connection.execute("SELECT COUNT(*) FROM collection_session_steps").fetchone()[0]
            collection_step_receipts = connection.execute("SELECT COUNT(*) FROM collection_step_receipts").fetchone()[0]
            collection_profiles = connection.execute(
                "SELECT COUNT(*) FROM collection_profiles"
            ).fetchone()[0]
            active_collection_profiles = connection.execute(
                "SELECT COUNT(*) FROM collection_profiles WHERE active=1"
            ).fetchone()[0]
            collection_profile_events = connection.execute(
                "SELECT COUNT(*) FROM collection_profile_events"
            ).fetchone()[0]
            observations = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            findings = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
            jobs = connection.execute("SELECT COUNT(*) FROM scan_jobs").fetchone()[0]
            assessments = connection.execute("SELECT COUNT(*) FROM finding_assessments").fetchone()[0]
            cooldowns = connection.execute("SELECT COUNT(*) FROM provider_cooldowns").fetchone()[0]
            cleanups = connection.execute("SELECT COUNT(*) FROM cleanup_runs").fetchone()[0]
            monitors = connection.execute("SELECT COUNT(*) FROM monitor_runs").fetchone()[0]
            running_monitors = connection.execute(
                "SELECT COUNT(*) FROM monitor_runs WHERE status = 'running'"
            ).fetchone()[0]
            notifications = connection.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
            candidate_notifications = connection.execute(
                "SELECT COUNT(*) FROM surface_candidate_notifications"
            ).fetchone()[0]
            surface_change_notifications = connection.execute(
                "SELECT COUNT(*) FROM surface_change_notifications"
            ).fetchone()[0]
            unread_notifications = connection.execute(
                "SELECT COUNT(*) FROM notifications WHERE read_at IS NULL"
            ).fetchone()[0]
            unread_candidate_notifications = connection.execute(
                "SELECT COUNT(*) FROM surface_candidate_notifications WHERE read_at IS NULL"
            ).fetchone()[0]
            unread_surface_change_notifications = connection.execute(
                "SELECT COUNT(*) FROM surface_change_notifications WHERE read_at IS NULL"
            ).fetchone()[0]
            allowlist_entries = connection.execute(
                "SELECT COUNT(*) FROM allowlist_entries"
            ).fetchone()[0]
            allowlist_now = datetime.now(timezone.utc).isoformat()
            active_allowlist_entries = connection.execute(
                "SELECT COUNT(*) FROM allowlist_entries WHERE active = 1 "
                "AND (expires_at IS NULL OR expires_at > ?)", (allowlist_now,),
            ).fetchone()[0]
            expired_allowlist_entries = connection.execute(
                "SELECT COUNT(*) FROM allowlist_entries WHERE active = 1 "
                "AND expires_at IS NOT NULL AND expires_at <= ?", (allowlist_now,),
            ).fetchone()[0]
            surface_scopes = connection.execute(
                "SELECT COUNT(*) FROM surface_scopes"
            ).fetchone()[0]
            active_surface_scopes = connection.execute(
                "SELECT COUNT(*) FROM surface_scopes WHERE active = 1"
            ).fetchone()[0]
            surface_checks = connection.execute(
                "SELECT COUNT(*) FROM surface_checks"
            ).fetchone()[0]
            surface_candidates = connection.execute(
                "SELECT COUNT(*) FROM surface_candidates"
            ).fetchone()[0]
            pending_surface_candidates = connection.execute(
                "SELECT COUNT(*) FROM surface_candidates WHERE status = 'pending'"
            ).fetchone()[0]
            surface_discovery_runs = connection.execute(
                "SELECT COUNT(*) FROM surface_discovery_runs"
            ).fetchone()[0]
            surface_mail_checks = connection.execute(
                "SELECT COUNT(*) FROM surface_mail_checks"
            ).fetchone()[0]
            surface_service_checks = connection.execute(
                "SELECT COUNT(*) FROM surface_service_checks"
            ).fetchone()[0]
            surface_nmap_checks = connection.execute(
                "SELECT COUNT(*) FROM surface_nmap_checks"
            ).fetchone()[0]
            surface_nmap_target_scopes = connection.execute(
                "SELECT COUNT(*) FROM surface_nmap_target_scopes"
            ).fetchone()[0]
            active_surface_nmap_target_scopes = connection.execute(
                "SELECT COUNT(*) FROM surface_nmap_target_scopes WHERE active = 1"
            ).fetchone()[0]
            surface_nmap_plans = connection.execute(
                "SELECT COUNT(*) FROM surface_nmap_plans"
            ).fetchone()[0]
            surface_cname_checks = connection.execute(
                "SELECT COUNT(*) FROM surface_cname_checks"
            ).fetchone()[0]
            kev_entries = connection.execute(
                "SELECT COUNT(*) FROM kev_entries WHERE active = 1"
            ).fetchone()[0]
            vulnerability_source_runs = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_source_runs"
            ).fetchone()[0]
            epss_scores = connection.execute(
                "SELECT COUNT(*) FROM epss_scores WHERE active = 1"
            ).fetchone()[0]
            nvd_cves = connection.execute(
                "SELECT COUNT(*) FROM nvd_cve_records"
            ).fetchone()[0]
            nvd_window_syncs = connection.execute(
                "SELECT COUNT(*) FROM nvd_window_syncs"
            ).fetchone()[0]
            nvd_window_restarts = connection.execute(
                "SELECT COUNT(*) FROM nvd_window_restart_events"
            ).fetchone()[0]
            active_asset_products = connection.execute(
                "SELECT COUNT(*) FROM asset_products WHERE active = 1"
            ).fetchone()[0]
            active_asset_packages = connection.execute(
                "SELECT COUNT(*) FROM asset_packages WHERE active = 1"
            ).fetchone()[0]
            active_ubuntu_asset_packages = connection.execute(
                "SELECT COUNT(*) FROM ubuntu_asset_packages WHERE active = 1"
            ).fetchone()[0]
            vulnerability_exposures = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_exposures"
            ).fetchone()[0]
            open_vulnerability_exposures = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_exposures "
                "WHERE suppressed = 0 AND status IN ('investigating', 'affected') "
                "AND NOT EXISTS (SELECT 1 FROM vulnerability_exposure_suppressions s "
                "WHERE s.exposure_id = vulnerability_exposures.id AND s.active = 1 "
                "AND s.expires_at > ?)", (allowlist_now,),
            ).fetchone()[0]
            vulnerability_exposure_suppressions = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_exposure_suppressions"
            ).fetchone()[0]
            active_vulnerability_exposure_suppressions = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_exposure_suppressions "
                "WHERE active = 1 AND expires_at > ?", (allowlist_now,),
            ).fetchone()[0]
            vulnerability_reassessment_runs = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_reassessment_runs"
            ).fetchone()[0]
            vulnerability_change_notifications = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_change_notifications"
            ).fetchone()[0]
            unread_vulnerability_change_notifications = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_change_notifications "
                "WHERE read_at IS NULL"
            ).fetchone()[0]
            vulnerability_exposure_evidence = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_exposure_evidence WHERE active = 1"
            ).fetchone()[0]
            vendor_package_evidence = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_vendor_package_evidence WHERE active = 1"
            ).fetchone()[0]
            vulnerability_remediations = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_remediations"
            ).fetchone()[0]
            open_vulnerability_remediations = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_remediations WHERE state != 'cancelled'"
            ).fetchone()[0]
            asset_criticalities = connection.execute(
                "SELECT COUNT(*) FROM asset_criticalities"
            ).fetchone()[0]
            active_asset_criticalities = connection.execute(
                "SELECT COUNT(*) FROM asset_criticalities WHERE active = 1"
            ).fetchone()[0]
            suppliers = connection.execute(
                "SELECT COUNT(*) FROM suppliers"
            ).fetchone()[0]
            active_suppliers = connection.execute(
                "SELECT COUNT(*) FROM suppliers WHERE active = 1"
            ).fetchone()[0]
            supplier_events = connection.execute(
                "SELECT COUNT(*) FROM supplier_events"
            ).fetchone()[0]
            supplier_candidates = connection.execute(
                "SELECT COUNT(*) FROM supplier_candidates"
            ).fetchone()[0]
            current_supplier_candidates = connection.execute(
                "SELECT COUNT(*) FROM supplier_candidates WHERE current=1"
            ).fetchone()[0]
            pending_supplier_candidates = connection.execute(
                "SELECT COUNT(*) FROM supplier_candidates WHERE status='pending'"
            ).fetchone()[0]
            supplier_candidate_evidence = connection.execute(
                "SELECT COUNT(*) FROM supplier_candidate_evidence"
            ).fetchone()[0]
            supplier_candidate_resolutions = connection.execute(
                "SELECT COUNT(*) FROM supplier_candidate_resolution_events"
            ).fetchone()[0]
            cases = connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
            open_cases = connection.execute(
                "SELECT COUNT(*) FROM cases WHERE status IN "
                "('open', 'investigating', 'monitoring')"
            ).fetchone()[0]
            case_evidence = connection.execute(
                "SELECT COUNT(*) FROM case_evidence WHERE active=1"
            ).fetchone()[0]
            open_case_tasks = connection.execute(
                "SELECT COUNT(*) FROM case_tasks WHERE status='open'"
            ).fetchone()[0]
            case_activities = connection.execute(
                "SELECT COUNT(*) FROM case_activities"
            ).fetchone()[0]
            cti_indicators = connection.execute(
                "SELECT COUNT(*) FROM cti_indicators"
            ).fetchone()[0]
            active_cti_assertions = connection.execute(
                "SELECT COUNT(*) FROM cti_indicator_assertions WHERE active = 1"
            ).fetchone()[0]
            cti_feed_runs = connection.execute(
                "SELECT COUNT(*) FROM cti_feed_runs"
            ).fetchone()[0]
            brand_username_watches = connection.execute(
                "SELECT COUNT(*) FROM brand_username_watches"
            ).fetchone()[0]
            active_brand_username_watches = connection.execute(
                "SELECT COUNT(*) FROM brand_username_watches WHERE active=1"
            ).fetchone()[0]
            brand_username_watch_runs = connection.execute(
                "SELECT COUNT(*) FROM brand_username_watch_runs"
            ).fetchone()[0]
            failed_brand_username_watch_runs = connection.execute(
                "SELECT COUNT(*) FROM brand_username_watch_runs WHERE status='failed'"
            ).fetchone()[0]
            brand_username_review_events = connection.execute(
                "SELECT COUNT(*) FROM brand_username_review_events"
            ).fetchone()[0]
            brand_username_review_candidates = connection.execute(
                "SELECT COUNT(DISTINCT candidate_id) FROM brand_username_review_events"
            ).fetchone()[0]
            brand_username_review_notifications = connection.execute(
                "SELECT COUNT(*) FROM brand_username_review_notifications"
            ).fetchone()[0]
            unread_brand_username_review_notifications = connection.execute(
                "SELECT COUNT(*) FROM brand_username_review_notifications "
                "WHERE read_at IS NULL"
            ).fetchone()[0]
            ransomware_claim_runs = connection.execute(
                "SELECT COUNT(*) FROM ransomware_claim_runs"
            ).fetchone()[0]
            ransomware_claim_items = connection.execute(
                "SELECT COUNT(*) FROM ransomware_claim_run_items"
            ).fetchone()[0]
            ransomlook_claim_runs = connection.execute(
                "SELECT COUNT(*) FROM ransomlook_claim_runs"
            ).fetchone()[0]
            ransomlook_claim_items = connection.execute(
                "SELECT COUNT(*) FROM ransomlook_claim_run_items"
            ).fetchone()[0]
            ransomlook_watches = connection.execute(
                "SELECT COUNT(*) FROM ransomlook_watches"
            ).fetchone()[0]
            active_ransomlook_watches = connection.execute(
                "SELECT COUNT(*) FROM ransomlook_watches WHERE active=1"
            ).fetchone()[0]
            ransomlook_watch_runs = connection.execute(
                "SELECT COUNT(*) FROM ransomlook_watch_runs"
            ).fetchone()[0]
            ransomware_watches = connection.execute(
                "SELECT COUNT(*) FROM ransomware_watches"
            ).fetchone()[0]
            active_ransomware_watches = connection.execute(
                "SELECT COUNT(*) FROM ransomware_watches WHERE active=1"
            ).fetchone()[0]
            ransomware_watch_runs = connection.execute(
                "SELECT COUNT(*) FROM ransomware_watch_runs"
            ).fetchone()[0]
            ransomlook_watch_notifications = connection.execute(
                "SELECT COUNT(*) FROM ransomlook_watch_notifications"
            ).fetchone()[0]
            unread_ransomlook_watch_notifications = connection.execute(
                "SELECT COUNT(*) FROM ransomlook_watch_notifications WHERE read_at IS NULL"
            ).fetchone()[0]
            public_notice_watches = connection.execute(
                "SELECT COUNT(*) FROM public_notice_watches"
            ).fetchone()[0]
            active_public_notice_watches = connection.execute(
                "SELECT COUNT(*) FROM public_notice_watches WHERE active=1"
            ).fetchone()[0]
            public_notice_watch_runs = connection.execute(
                "SELECT COUNT(*) FROM public_notice_watch_runs"
            ).fetchone()[0]
            public_notice_watch_notifications = connection.execute(
                "SELECT COUNT(*) FROM public_notice_watch_notifications"
            ).fetchone()[0]
            unread_public_notice_watch_notifications = connection.execute(
                "SELECT COUNT(*) FROM public_notice_watch_notifications WHERE read_at IS NULL"
            ).fetchone()[0]
            supplier_watches = connection.execute(
                "SELECT COUNT(*) FROM supplier_watches"
            ).fetchone()[0]
            active_supplier_watches = connection.execute(
                "SELECT COUNT(*) FROM supplier_watches WHERE active=1"
            ).fetchone()[0]
            supplier_watch_runs = connection.execute(
                "SELECT COUNT(*) FROM supplier_watch_runs"
            ).fetchone()[0]
            supplier_watch_notifications = connection.execute(
                "SELECT COUNT(*) FROM supplier_watch_notifications"
            ).fetchone()[0]
            unread_supplier_watch_notifications = connection.execute(
                "SELECT COUNT(*) FROM supplier_watch_notifications WHERE read_at IS NULL"
            ).fetchone()[0]
            news_articles = connection.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
            news_runs = connection.execute("SELECT COUNT(*) FROM news_runs").fetchone()[0]
            news_snapshots = connection.execute("SELECT COUNT(*) FROM news_snapshots").fetchone()[0]
            mentions_runs = connection.execute("SELECT COUNT(*) FROM mentions_runs").fetchone()[0]
            mention_group_events = connection.execute("SELECT COUNT(*) FROM mention_group_events").fetchone()[0]
            global_saved_searches = connection.execute(
                "SELECT COUNT(*) FROM global_saved_searches"
            ).fetchone()[0]
            active_global_saved_searches = connection.execute(
                "SELECT COUNT(*) FROM global_saved_searches WHERE active=1"
            ).fetchone()[0]
            global_saved_search_runs = connection.execute(
                "SELECT COUNT(*) FROM global_saved_search_runs"
            ).fetchone()[0]
            global_search_snapshots = connection.execute(
                "SELECT COUNT(*) FROM global_search_snapshots"
            ).fetchone()[0]
            global_saved_search_notifications = connection.execute(
                "SELECT COUNT(*) FROM global_saved_search_notifications"
            ).fetchone()[0]
            unread_global_saved_search_notifications = connection.execute(
                "SELECT COUNT(*) FROM global_saved_search_notifications WHERE read_at IS NULL"
            ).fetchone()[0]
            ransomware_watch_notifications = connection.execute(
                "SELECT COUNT(*) FROM ransomware_watch_notifications"
            ).fetchone()[0]
            unread_ransomware_watch_notifications = connection.execute(
                "SELECT COUNT(*) FROM ransomware_watch_notifications WHERE read_at IS NULL"
            ).fetchone()[0]
            ransomware_monitor_sessions = connection.execute(
                "SELECT COUNT(*) FROM ransomware_monitor_sessions"
            ).fetchone()[0]
            running_ransomware_monitor_sessions = connection.execute(
                "SELECT COUNT(*) FROM ransomware_monitor_sessions WHERE status='running'"
            ).fetchone()[0]
            ransomware_monitor_cycles = connection.execute(
                "SELECT COUNT(*) FROM ransomware_monitor_cycles"
            ).fetchone()[0]
            ransomware_monitor_cycle_watch_runs = connection.execute(
                "SELECT COUNT(*) FROM ransomware_monitor_cycle_watch_runs"
            ).fetchone()[0]
            ransomware_identity_review_events = connection.execute(
                "SELECT COUNT(*) FROM ransomware_identity_review_events"
            ).fetchone()[0]
            ransomware_identity_review_candidates = connection.execute(
                "SELECT COUNT(DISTINCT candidate_id) "
                "FROM ransomware_identity_review_events"
            ).fetchone()[0]
            ransomware_source_review_events = connection.execute(
                "SELECT COUNT(*) FROM ransomware_source_review_events"
            ).fetchone()[0]
            ransomware_source_review_candidates = connection.execute(
                "SELECT COUNT(DISTINCT comparison_id) "
                "FROM ransomware_source_review_events"
            ).fetchone()[0]
            cti_entities = connection.execute(
                "SELECT COUNT(*) FROM cti_entities"
            ).fetchone()[0]
            active_cti_entity_assertions = connection.execute(
                "SELECT COUNT(*) FROM cti_entity_assertions WHERE active = 1"
            ).fetchone()[0]
            cti_relationships = connection.execute(
                "SELECT COUNT(*) FROM cti_relationships"
            ).fetchone()[0]
            active_cti_relationship_assertions = connection.execute(
                "SELECT COUNT(*) FROM cti_relationship_assertions WHERE active = 1"
            ).fetchone()[0]
            cti_saved_searches = connection.execute(
                "SELECT COUNT(*) FROM cti_saved_searches"
            ).fetchone()[0]
            active_cti_saved_searches = connection.execute(
                "SELECT COUNT(*) FROM cti_saved_searches WHERE active = 1"
            ).fetchone()[0]
            cti_saved_search_runs = connection.execute(
                "SELECT COUNT(*) FROM cti_saved_search_runs"
            ).fetchone()[0]
            cti_saved_search_notifications = connection.execute(
                "SELECT COUNT(*) FROM cti_saved_search_notifications"
            ).fetchone()[0]
            unread_cti_saved_search_notifications = connection.execute(
                "SELECT COUNT(*) FROM cti_saved_search_notifications WHERE read_at IS NULL"
            ).fetchone()[0]
            cti_saved_search_tags = connection.execute(
                "SELECT COUNT(*) FROM cti_saved_search_tags"
            ).fetchone()[0]
            active_cti_saved_search_tags = connection.execute(
                "SELECT COUNT(*) FROM cti_saved_search_tags WHERE active = 1"
            ).fetchone()[0]
            cti_saved_search_notes = connection.execute(
                "SELECT COUNT(*) FROM cti_saved_search_notes"
            ).fetchone()[0]
            webhook_destinations = connection.execute(
                "SELECT COUNT(*) FROM webhook_destinations"
            ).fetchone()[0]
            active_webhook_destinations = connection.execute(
                "SELECT COUNT(*) FROM webhook_destinations WHERE active=1"
            ).fetchone()[0]
            webhook_deliveries = connection.execute(
                "SELECT COUNT(*) FROM webhook_deliveries"
            ).fetchone()[0]
            queued_webhook_deliveries = connection.execute(
                "SELECT COUNT(*) FROM webhook_deliveries WHERE status IN ('queued', 'retryable')"
            ).fetchone()[0]
            failed_webhook_deliveries = connection.execute(
                "SELECT COUNT(*) FROM webhook_deliveries WHERE status='failed'"
            ).fetchone()[0]
            delivered_webhook_deliveries = connection.execute(
                "SELECT COUNT(*) FROM webhook_deliveries WHERE status='delivered'"
            ).fetchone()[0]
            job_counts = dict(connection.execute(
                "SELECT status, COUNT(*) FROM scan_jobs GROUP BY status"
            ).fetchall())
        return {
            "schema_version": SCHEMA_VERSION,
            "organization_count": organization_count,
            "active_organization_count": active_organization_count,
            "organization_link_count": organization_link_count,
            "asset_count": count,
            "observation_count": observations,
            "finding_count": findings,
            "job_count": jobs,
            "assessment_count": assessments,
            "cooldown_count": cooldowns,
            "cleanup_count": cleanups,
            "monitor_count": monitors,
            "running_monitor_count": running_monitors,
            "notification_count": (
                notifications + candidate_notifications + surface_change_notifications
                + vulnerability_change_notifications + cti_saved_search_notifications
                + ransomware_watch_notifications + ransomlook_watch_notifications
                + public_notice_watch_notifications + supplier_watch_notifications
                + global_saved_search_notifications
                + brand_username_review_notifications
            ),
            "unread_notification_count": (
                unread_notifications + unread_candidate_notifications
                + unread_surface_change_notifications
                + unread_vulnerability_change_notifications
                + unread_cti_saved_search_notifications
                + unread_ransomware_watch_notifications + unread_ransomlook_watch_notifications
                + unread_public_notice_watch_notifications + unread_supplier_watch_notifications
                + unread_global_saved_search_notifications
                + unread_brand_username_review_notifications
            ),
            "surface_change_notification_count": surface_change_notifications,
            "vulnerability_change_notification_count": vulnerability_change_notifications,
            "allowlist_count": allowlist_entries,
            "active_allowlist_count": active_allowlist_entries,
            "expired_allowlist_count": expired_allowlist_entries,
            "surface_scope_count": surface_scopes,
            "active_surface_scope_count": active_surface_scopes,
            "surface_check_count": surface_checks,
            "surface_candidate_count": surface_candidates,
            "pending_surface_candidate_count": pending_surface_candidates,
            "surface_discovery_run_count": surface_discovery_runs,
            "surface_mail_check_count": surface_mail_checks,
            "surface_service_check_count": surface_service_checks,
            "surface_nmap_check_count": surface_nmap_checks,
            "surface_nmap_target_scope_count": surface_nmap_target_scopes,
            "active_surface_nmap_target_scope_count": active_surface_nmap_target_scopes,
            "surface_nmap_plan_count": surface_nmap_plans,
            "surface_cname_check_count": surface_cname_checks,
            "active_kev_entry_count": kev_entries,
            "vulnerability_source_run_count": vulnerability_source_runs,
            "active_epss_score_count": epss_scores,
            "nvd_cve_count": nvd_cves,
            "nvd_window_sync_count": nvd_window_syncs,
            "nvd_window_restart_count": nvd_window_restarts,
            "active_asset_product_count": active_asset_products,
            "active_asset_package_count": active_asset_packages,
            "active_ubuntu_asset_package_count": active_ubuntu_asset_packages,
            "vulnerability_exposure_count": vulnerability_exposures,
            "open_vulnerability_exposure_count": open_vulnerability_exposures,
            "vulnerability_exposure_suppression_count": (
                vulnerability_exposure_suppressions
            ),
            "active_vulnerability_exposure_suppression_count": (
                active_vulnerability_exposure_suppressions
            ),
            "vulnerability_reassessment_run_count": vulnerability_reassessment_runs,
            "active_vulnerability_exposure_evidence_count": vulnerability_exposure_evidence,
            "active_vendor_package_evidence_count": vendor_package_evidence,
            "vulnerability_remediation_count": vulnerability_remediations,
            "open_vulnerability_remediation_count": open_vulnerability_remediations,
            "asset_criticality_count": asset_criticalities,
            "active_asset_criticality_count": active_asset_criticalities,
            "supplier_count": suppliers,
            "active_supplier_count": active_suppliers,
            "supplier_event_count": supplier_events,
            "supplier_candidate_count": supplier_candidates,
            "current_supplier_candidate_count": current_supplier_candidates,
            "pending_supplier_candidate_count": pending_supplier_candidates,
            "supplier_candidate_evidence_count": supplier_candidate_evidence,
            "supplier_candidate_resolution_count": supplier_candidate_resolutions,
            "case_count": cases,
            "collection_session_count": collection_sessions,
            "collection_session_step_count": collection_session_steps,
            "collection_step_receipt_count": collection_step_receipts,
            "collection_profile_count": collection_profiles,
            "active_collection_profile_count": active_collection_profiles,
            "collection_profile_event_count": collection_profile_events,
            "open_case_count": open_cases,
            "active_case_evidence_count": case_evidence,
            "open_case_task_count": open_case_tasks,
            "case_activity_count": case_activities,
            "cti_indicator_count": cti_indicators,
            "active_cti_assertion_count": active_cti_assertions,
            "cti_feed_run_count": cti_feed_runs,
            "brand_username_watch_count": brand_username_watches,
            "active_brand_username_watch_count": active_brand_username_watches,
            "brand_username_watch_run_count": brand_username_watch_runs,
            "failed_brand_username_watch_run_count": (
                failed_brand_username_watch_runs
            ),
            "brand_username_review_event_count": brand_username_review_events,
            "brand_username_review_candidate_count": brand_username_review_candidates,
            "brand_username_review_notification_count": (
                brand_username_review_notifications
            ),
            "unread_brand_username_review_notification_count": (
                unread_brand_username_review_notifications
            ),
            "ransomware_claim_run_count": ransomware_claim_runs,
            "ransomware_claim_item_count": ransomware_claim_items,
            "ransomlook_claim_run_count": ransomlook_claim_runs,
            "ransomlook_claim_item_count": ransomlook_claim_items,
            "ransomlook_watch_count": ransomlook_watches,
            "active_ransomlook_watch_count": active_ransomlook_watches,
            "ransomlook_watch_run_count": ransomlook_watch_runs,
            "ransomware_watch_count": ransomware_watches,
            "active_ransomware_watch_count": active_ransomware_watches,
            "ransomware_watch_run_count": ransomware_watch_runs,
            "ransomlook_watch_notification_count": ransomlook_watch_notifications,
            "public_notice_watch_count": public_notice_watches,
            "active_public_notice_watch_count": active_public_notice_watches,
            "public_notice_watch_run_count": public_notice_watch_runs,
            "public_notice_watch_notification_count": public_notice_watch_notifications,
            "unread_public_notice_watch_notification_count": unread_public_notice_watch_notifications,
            "supplier_watch_count": supplier_watches,
            "active_supplier_watch_count": active_supplier_watches,
            "supplier_watch_run_count": supplier_watch_runs,
            "supplier_watch_notification_count": supplier_watch_notifications,
            "unread_supplier_watch_notification_count": unread_supplier_watch_notifications,
            "news_article_count": news_articles,
            "news_run_count": news_runs,
            "news_snapshot_count": news_snapshots,
            "mention_run_count": mentions_runs,
            "mention_group_event_count": mention_group_events,
            "global_saved_search_count": global_saved_searches,
            "active_global_saved_search_count": active_global_saved_searches,
            "global_saved_search_run_count": global_saved_search_runs,
            "global_search_snapshot_count": global_search_snapshots,
            "global_saved_search_notification_count": global_saved_search_notifications,
            "unread_global_saved_search_notification_count": unread_global_saved_search_notifications,
            "unread_ransomlook_watch_notification_count": unread_ransomlook_watch_notifications,
            "ransomware_watch_notification_count": ransomware_watch_notifications,
            "unread_ransomware_watch_notification_count": (
                unread_ransomware_watch_notifications
            ),
            "ransomware_monitor_session_count": ransomware_monitor_sessions,
            "running_ransomware_monitor_session_count": (
                running_ransomware_monitor_sessions
            ),
            "ransomware_monitor_cycle_count": ransomware_monitor_cycles,
            "ransomware_monitor_cycle_watch_run_count": (
                ransomware_monitor_cycle_watch_runs
            ),
            "ransomware_identity_review_event_count": (
                ransomware_identity_review_events
            ),
            "ransomware_identity_review_candidate_count": (
                ransomware_identity_review_candidates
            ),
            "ransomware_source_review_event_count": (
                ransomware_source_review_events
            ),
            "ransomware_source_review_candidate_count": (
                ransomware_source_review_candidates
            ),
            "cti_entity_count": cti_entities,
            "active_cti_entity_assertion_count": active_cti_entity_assertions,
            "cti_relationship_count": cti_relationships,
            "active_cti_relationship_assertion_count": (
                active_cti_relationship_assertions
            ),
            "cti_saved_search_count": cti_saved_searches,
            "active_cti_saved_search_count": active_cti_saved_searches,
            "cti_saved_search_run_count": cti_saved_search_runs,
            "cti_saved_search_notification_count": cti_saved_search_notifications,
            "unread_cti_saved_search_notification_count": (
                unread_cti_saved_search_notifications
            ),
            "cti_saved_search_tag_count": cti_saved_search_tags,
            "active_cti_saved_search_tag_count": active_cti_saved_search_tags,
            "cti_saved_search_note_count": cti_saved_search_notes,
            "webhook_destination_count": webhook_destinations,
            "active_webhook_destination_count": active_webhook_destinations,
            "webhook_delivery_count": webhook_deliveries,
            "queued_webhook_delivery_count": queued_webhook_deliveries,
            "failed_webhook_delivery_count": failed_webhook_deliveries,
            "delivered_webhook_delivery_count": delivered_webhook_deliveries,
            "queued_job_count": job_counts.get("queued", 0),
            "running_job_count": job_counts.get("running", 0),
            "interrupted_job_count": job_counts.get("interrupted", 0),
            "integrity": "ok",
        }

    def migrate(self) -> dict[str, int | str | bool | None]:
        """Upgrade a known legacy version after publishing a recovery snapshot.

        The writer lock spans backup and DDL, so no asset write can slip between
        them. A separate reader performs the backup: SQLite's backup API cannot
        copy from the connection that owns the active write transaction.
        """
        with self._connection(allow_legacy=True) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                version = self._validate_schema(connection, allow_legacy=True)
                self._check_integrity(connection)
                if version == SCHEMA_VERSION:
                    connection.rollback()
                    return {
                        "from_version": version, "to_version": version,
                        "backup": None, "changed": False,
                    }
                destination = (
                    self.path.parent / "backups" /
                    f"{self.path.stem}.pre-v{SCHEMA_VERSION}-{uuid4().hex}.db"
                )
                self.backup(destination)
                if version == 1:
                    create_findings_schema(connection)
                if version < 3:
                    create_jobs_schema(connection)
                if version < 4:
                    create_assessments_schema(connection)
                if version < 5:
                    create_operations_schema(connection)
                if version < 6:
                    create_inbox_schema(connection)
                    backfill_inbox(connection, datetime.now(timezone.utc).isoformat())
                if version < 7:
                    create_monitor_schema(connection)
                if version < 8:
                    create_allowlist_schema(connection)
                elif version == 8:
                    migrate_allowlist_expiry_schema(connection)
                if version < 10:
                    create_surface_schema(connection)
                if version < 11:
                    create_surface_discovery_schema(connection)
                if version < 12:
                    create_surface_discovery_history_schema(connection)
                if version < 13:
                    create_surface_mail_schema(connection)
                if version < 14:
                    create_surface_service_schema(connection)
                if version < 15:
                    create_surface_change_notification_schema(connection)
                if version < 16:
                    create_surface_cname_schema(connection)
                if version < 17:
                    create_vulnerability_schema(connection)
                if version < 18:
                    create_epss_schema(connection)
                if version < 19:
                    create_nvd_schema(connection)
                if version < 20:
                    create_product_evidence_schema(connection)
                if version < 21:
                    create_vulnerability_exposure_schema(connection)
                if version < 22:
                    create_vulnerability_exposure_evidence_schema(connection)
                if version < 23:
                    create_package_evidence_schema(connection)
                if version < 24:
                    create_vendor_package_evidence_schema(connection)
                if version < 25:
                    create_vulnerability_remediation_schema(connection)
                if version < 26:
                    create_vulnerability_exposure_suppression_schema(connection)
                if version < 27:
                    create_asset_criticality_schema(connection)
                if version < 28:
                    create_vulnerability_reassessment_schema(connection)
                if version < 29:
                    create_vulnerability_change_notification_schema(connection)
                if version < 30:
                    create_nvd_window_schema(connection)
                if version < 31:
                    create_nvd_window_restart_schema(connection)
                if version < 32:
                    create_ubuntu_package_evidence_schema(connection)
                if version < 33:
                    create_cti_indicator_schema(connection)
                if version < 34:
                    create_cti_feed_schema(connection)
                if version < 35:
                    create_cti_knowledge_schema(connection)
                if version < 36:
                    create_cti_saved_search_schema(connection)
                if version < 37:
                    create_cti_saved_search_notification_schema(connection)
                if version < 38:
                    create_cti_hunting_journal_schema(connection)
                if version < 39:
                    create_webhook_schema(connection)
                if version < 40:
                    create_ransomware_claim_schema(connection)
                if version < 41:
                    create_ransomware_watch_schema(connection)
                if version < 42:
                    create_ransomware_monitor_session_schema(connection)
                if version < 43:
                    create_ransomware_identity_review_schema(connection)
                if version < 44:
                    create_ransomlook_claim_schema(connection)
                if version < 45:
                    create_ransomlook_watch_schema(connection)
                if version < 46:
                    create_ransomware_source_review_schema(connection)
                if version < 47:
                    create_brand_username_watch_schema(connection)
                if version < 48:
                    create_brand_username_review_schema(connection)
                if version < 49:
                    create_brand_username_review_notification_schema(connection)
                if 47 <= version < 50:
                    migrate_brand_username_watch_source_schema(connection)
                if 11 <= version < 51:
                    migrate_surface_discovery_provider_schema(connection)
                if version < 52:
                    create_supplier_inventory_schema(connection)
                if version < 53:
                    create_supplier_candidate_schema(connection)
                if version < 54:
                    create_case_schema(connection)
                if version < 55:
                    create_collection_profile_schema(connection)
                if version < 56:
                    create_collection_history_schema(connection)
                if version < 57:
                    create_organization_schema(connection)
                if version < 58:
                    create_attack_catalog_schema(connection)
                if version < 59:
                    create_ransomlook_notification_schema(connection)
                if version < 60:
                    create_public_notice_schema(connection)
                if 56 <= version < 61:
                    migrate_collection_public_notice_schema(connection)
                if version < 62:
                    create_public_notice_watch_schema(connection)
                if 54 <= version < 63:
                    migrate_case_public_notice_schema(connection)
                if version < 64:
                    create_supplier_watch_schema(connection)
                if version < 65:
                    create_global_saved_search_schema(connection)
                if version < 66:
                    create_news_schema(connection)
                if version < 67:
                    create_mentions_schema(connection)
                if version < 68:
                    upgrade_global_saved_search_scopes(connection)
                    create_mention_group_schema(connection)
                if 56 <= version < 69:
                    migrate_collection_news_schema(connection)
                if version < 70:
                    create_surface_nmap_schema(connection)
                if version < 71:
                    create_nmap_management_schema(connection)
                if version < 72:
                    create_nmap_jobs_schema(connection)
                if version < 73:
                    create_warninglist_schema(connection)
                if version < 74:
                    create_enrichment_schema(connection)
                if version < 75:
                    create_research_history_schema(connection)
                if version < 76:
                    create_investigation_schema(connection)
                if version < 77:
                    create_report_schema(connection)
                if version < 78:
                    create_evidence_schema(connection)
                if version < 79:
                    create_document_storage_schema(connection)
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                self._validate_schema(connection)
                self._check_integrity(connection)
                connection.commit()
                return {
                    "from_version": version, "to_version": SCHEMA_VERSION,
                    "backup": str(destination), "changed": True,
                }
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _temporary_path(directory: Path) -> Path:
        descriptor, name = tempfile.mkstemp(prefix=".xti-", suffix=".tmp", dir=directory)
        os.close(descriptor)
        return Path(name)

    @staticmethod
    def _flush_file(path: Path) -> None:
        with path.open("rb") as stream:
            os.fsync(stream.fileno())

    def backup(self, destination: Path) -> Path:
        """Publish a validated SQLite snapshot only if the destination is absent."""
        destination = Path(destination).expanduser().absolute()
        if destination.exists() or destination.is_symlink():
            raise StorageError("Hedef dosya zaten var. Üzerine yazılmadı; yeni bir yol seçin.")
        temporary = None
        try:
            with self._connection(readonly=True, allow_legacy=True) as source:
                self._check_integrity(source)
                create_private_directory(destination.parent)
                temporary = self._temporary_path(destination.parent)
                target = sqlite3.connect(temporary)
                try:
                    target.execute("PRAGMA trusted_schema=OFF")
                    target.execute("PRAGMA foreign_keys=ON")
                    source.backup(target)
                    self._validate_schema(target, allow_legacy=True)
                    self._check_integrity(target)
                finally:
                    target.close()
            self._flush_file(temporary)
            # A same-directory hard link is atomic and cannot replace another file.
            os.link(temporary, destination)
            return destination
        except FileExistsError as error:
            raise StorageError("Hedef dosya zaten var. Üzerine yazılmadı.") from error
        except (OSError, sqlite3.Error) as error:
            raise StorageError(
                "Yedek oluşturulamadı. Hedef klasörün izinlerini ve boş alanı kontrol edin."
            ) from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @classmethod
    def restore(cls, source: Path, destination: Path) -> None:
        """Restore a known snapshot to a new path, leaving all existing files intact."""
        cls(source).backup(destination)
