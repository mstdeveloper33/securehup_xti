"""Small terminal adapter for the first local XTI release."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import shlex
import sqlite3
import sys
import time
from typing import Any, Sequence
from uuid import uuid4

from xti import __version__
from xti.interfaces.arguments import Parser, UsageError, root_parser
from xti.interfaces.engine import register_engine_parser, run_engine
from xti.interfaces.platform_engine import DataDirectoryAction, register_platform_parser, run_platform
from xti.interfaces.components import register_components_parser, make_component_service, component_lines
from xti.interfaces.event_candidates import (
    register_event_candidates_parser, make_event_candidate_service, execute_event_candidates_command,
)
from xti.interfaces.news import register_news_parser, make_news_service, execute_news_command
from xti.interfaces.mentions import register_mentions_parser, make_mentions_service, execute_mentions_command
from xti.interfaces.mention_groups import make_mention_group_service, execute_mention_group_command
from xti.adapters.sqlite import SCHEMA_VERSION, SQLiteAssetRepository, StorageError
from xti.adapters.domain_file import read_domain_file
from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.crtsh import CrtShSource
from xti.adapters.theharvester_archive import TheHarvesterArchiveSource
from xti.adapters.urlscan import UrlscanSource
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.adapters.https_probe import (
    GoogleCnameDnsProbe,
    GoogleMailDnsProbe,
    HttpsTargetProbe,
)
from xti.adapters.sqlite_assessments import SQLiteAssessmentRepository
from xti.adapters.json_report import write_report
from xti.adapters.stix_json import write_stix_bundle
from xti.adapters.sqlite_webhooks import SQLiteWebhookRepository
from xti.adapters.webhook_https import SafeHttpsWebhookSender
from xti.adapters.webhook_secret_file import generate_webhook_secret, read_webhook_secret
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.sqlite_maintenance import SQLiteMaintenanceRepository
from xti.adapters.filesystem_storage_readiness import FileSystemStorageReadinessRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_status import SQLiteStatusRepository
from xti.adapters.sqlite_feedback import SQLiteFeedbackRepository
from xti.adapters.sqlite_monitoring import SQLiteMonitorRepository
from xti.adapters.unicode_security import unicode_security_profile
from xti.adapters.sqlite_allowlist import SQLiteAllowlistRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_surface_overview import SQLiteSurfaceOverviewRepository
from xti.adapters.sqlite_surface_freshness import SQLiteSurfaceFreshnessRepository
from xti.adapters.sqlite_surface_inventory import SQLiteSurfaceInventoryRepository
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_vulnerability import SQLiteKevRepository
from xti.adapters.sqlite_epss import SQLiteEpssRepository
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.adapters.sqlite_nvd_window import SQLiteNvdWindowRepository
from xti.adapters.sqlite_vulnerability_context import SQLiteVulnerabilityContextRepository
from xti.adapters.sqlite_nvd_enrichment_plan import SQLiteNvdEnrichmentPlanRepository
from xti.adapters.sqlite_nvd_applicability import SQLiteNvdApplicabilityRepository
from xti.adapters.sqlite_products import SQLiteAssetProductRepository
from xti.adapters.sqlite_packages import SQLiteAssetPackageRepository
from xti.adapters.sqlite_ubuntu_packages import SQLiteUbuntuAssetPackageRepository
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_cti_saved_searches import SQLiteCtiSavedSearchRepository
from xti.adapters.sqlite_cti_hunting_journal import SQLiteCtiHuntingJournalRepository
from xti.adapters.feodo_tracker import FeodoTrackerSource
from xti.adapters.certpl_warning import CertPlWarningSource
from xti.adapters.threatcluster_ransomware import ThreatClusterRansomwareSource
from xti.adapters.ransomlook_ransomware import RansomLookRansomwareSource
from xti.adapters.maigret_username import MaigretUsernameSource
from xti.adapters.sherlock_username import SherlockUsernameSource
from xti.adapters.sqlite_brand_username_watches import (
    SQLiteBrandUsernameWatchRepository,
)
from xti.adapters.sqlite_brand_username_reviews import (
    SQLiteBrandUsernameReviewRepository,
)
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.sqlite_ransomware_monitor_sessions import (
    SQLiteRansomwareMonitorSessionRepository,
)
from xti.adapters.sqlite_ransomware_identity_reviews import (
    SQLiteRansomwareIdentityReviewRepository,
)
from xti.adapters.sqlite_ransomware_source_reviews import (
    SQLiteRansomwareSourceReviewRepository,
)
from xti.adapters.mitre_attack import MitreAttackSource
from xti.adapters.sqlite_product_vulnerability import SQLiteProductVulnerabilityRepository
from xti.adapters.sqlite_product_vulnerability_overview import (
    SQLiteProductVulnerabilityOverviewRepository,
)
from xti.adapters.sqlite_product_vulnerability_inventory import (
    SQLiteProductVulnerabilityInventoryRepository,
)
from xti.adapters.sqlite_vulnerability_exposures import (
    SQLiteVulnerabilityExposureRepository,
)
from xti.adapters.sqlite_vulnerability_exposure_queue import (
    SQLiteVulnerabilityExposureQueueRepository,
)
from xti.adapters.sqlite_vulnerability_exposure_evidence import (
    SQLiteVulnerabilityExposureEvidenceRepository,
)
from xti.adapters.sqlite_vendor_package_evidence import (
    SQLiteVendorPackageEvidenceRepository,
)
from xti.adapters.sqlite_vulnerability_remediation import (
    SQLiteVulnerabilityRemediationRepository,
)
from xti.adapters.sqlite_vulnerability_exposure_suppressions import (
    SQLiteVulnerabilityExposureSuppressionRepository,
)
from xti.adapters.sqlite_asset_context import SQLiteAssetCriticalityRepository
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.adapters.sqlite_supplier_candidates import (
    SQLiteSupplierCandidateRepository,
    SQLiteSupplierDependencySource,
)
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_vulnerability_reassessment import (
    SQLiteVulnerabilityReassessmentRepository,
)
from xti.adapters.sqlite_vulnerability_notifications import (
    SQLiteVulnerabilityNotificationRepository,
)
from xti.adapters.sqlite_tracked_nvd_refresh import SQLiteTrackedNvdRefreshPlanRepository
from xti.adapters.cisa_kev import CisaKevSource
from xti.adapters.first_epss import FirstEpssSource
from xti.adapters.nvd_cve import NvdCveSource
from xti.adapters.nvd_window import NvdWindowSource
from xti.adapters.osv_dev import OsvDevAdvisorySource
from xti.adapters.ubuntu_osv import UbuntuOsvAdvisorySource
from xti.adapters.redhat_csaf_vex import RedHatCsafVexSource
from xti.adapters.suse_csaf_vex import SuseCsafVexSource
from xti.adapters.service_probe import BoundedServicePortProbe
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.adapters.nmap_scan import NmapTcpConnectProbe
from xti.adapters.sqlite_nmap_scans import SQLiteNmapScanRepository
from xti.adapters.sqlite_nmap_management import SQLiteNmapManagementRepository
from xti.interfaces.nmap_execution import (
    register_nmap_execution_parsers, execute_nmap_work_command, make_nmap_service,
)
from xti.domain.nmap_options import nmap_capabilities
from xti.adapters.evaluation_dataset import EvaluationDataError, load_evaluation_dataset
from xti.application.assets import AssetService
from xti.application.analysis import UnifiedAnalysisRefreshService, UnifiedAnalysisService
from xti.application.collection import CollectionService
from xti.application.scheduling import SchedulingService
from xti.adapters.systemd_schedule import SystemdScheduleWriter
from xti.adapters.scheduled_backups import ScheduledBackupMaintenance
from xti.interfaces.scheduling import (
    register_schedule_commands, generated_lines as schedule_generated_lines,
    preparation_lines as schedule_preparation_lines,
)
from xti.application.attack_catalog import AttackCatalogService
from xti.application.cti_context import CtiContextService
from xti.adapters.sqlite_cti_context import SQLiteCtiContextRepository
from xti.interfaces.cti_context import register_cti_context_parser, cti_context_lines
from xti.adapters.sqlite_attack_catalog import SQLiteAttackCatalogRepository
from xti.interfaces.attack_catalog import register_attack_catalog_parsers, run_attack_catalog_command
from xti.application.source_contribution import SourceContributionService
from xti.adapters.sqlite_source_contribution import SQLiteSourceContributionRepository
from xti.interfaces.source_contribution import source_contribution_lines
from xti.application.organization_contribution import OrganizationContributionService
from xti.adapters.sqlite_organization_contribution import SQLiteOrganizationContributionRepository
from xti.interfaces.organization_contribution import organization_contribution_lines
from xti.application.periodic_changes import PeriodicChangesService
from xti.adapters.sqlite_periodic_changes import SQLitePeriodicChangesRepository
from xti.interfaces.periodic_changes import periodic_changes_lines
from xti.application.organizations import OrganizationService
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.interfaces.organizations import register_organizations_parser, execute_organization_command
from xti.application.global_search import GlobalSearchService
from xti.adapters.sqlite_global_search import SQLiteGlobalSearchRepository
from xti.interfaces.global_search import register_global_search_parser, execute_global_search_command
from xti.interfaces.research import register_research_parser, execute_research
from xti.interfaces.investigation import register_investigation_parser, execute_investigation
from xti.interfaces.reports import register_report_parser, execute_report
from xti.domain.reports import ReportError
from xti.interfaces.company_review import register_company_review_parser, execute_company_review
from xti.interfaces.warninglists import register_warninglist_parser, execute_warninglists
from xti.domain.warninglists import WarninglistRunNotFound
from xti.interfaces.indicator_enrichment import register_enrichment_parser, execute_enrichment
from xti.domain.indicator_enrichment import EnrichmentRunNotFound
from xti.interfaces.research_history import register_history_parser as register_research_history_parser, execute_history
from xti.interfaces.source_jobs import register_source_jobs_parser, execute_source_jobs
from xti.domain.engine_jobs import EngineJobError
from xti.domain.research_history import ResearchHistoryError
from xti.interfaces.global_saved_searches import (
    register_global_saved_search_parser, make_global_saved_search_service,
    execute_global_saved_search_command,
)
from xti.application.asset_relations import AssetRelationsService
from xti.adapters.sqlite_asset_relations import SQLiteAssetRelationsRepository
from xti.interfaces.asset_relations import register_asset_relations_parser, execute_asset_relations_command
from xti.application.supplier_watches import SupplierWatchService
from xti.adapters.sqlite_supplier_watches import SQLiteSupplierWatchRepository
from xti.interfaces.supplier_watches import register_supplier_watch_parser, execute_supplier_watch
from xti.application.organization_report import OrganizationReportService
from xti.adapters.sqlite_organization_report import SQLiteOrganizationReportRepository
from xti.interfaces.organization_report import execute_organization_report_command, execute_organization_export_command
from xti.application.organization_export import OrganizationExportService
from xti.domain.organization_export import OrganizationExportPublicationError
from xti.adapters.html_report_writer import AtomicHtmlReportWriter
from xti.interfaces.html_organization_report import HtmlOrganizationReportRenderer
from xti.application.public_notices import PublicNoticeService
from xti.application.public_notice_watches import PublicNoticeWatchService
from xti.adapters.sqlite_public_notice_watches import SQLitePublicNoticeWatchRepository
from xti.interfaces.public_notice_watches import execute_public_notice_watch_command
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.hibp_public_notices import HibpPublicNoticeSource
from xti.interfaces.public_notices import (
    register_public_notice_parser, public_notice_status_lines,
    public_notice_refresh_lines, public_notice_search_lines, public_notice_detail_lines,
)
from xti.application.collection_history import CollectionHistoryService
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.interfaces.collection_history import (
    register_history_parser, page_lines as collection_history_page_lines,
    detail_lines as collection_history_detail_lines,
    resume_plan_lines, resume_result_lines,
)
from xti.application.collection_profiles import CollectionProfileService, collection_options
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.interfaces.collection_profiles import (
    add_collection_arguments, register_profiles_parser, definition_from_arguments,
    validate_profile_selection, detail_lines as profile_detail_lines,
    list_lines as profile_list_lines, mutation_lines as profile_mutation_lines,
)
from xti.application.collection_watches import CollectionWatchService
from xti.domain.collection import COLLECTION_TASK_IDS, DEFAULT_COLLECTION_TASKS
from xti.interfaces.collection import (
    plan_lines as collection_plan_lines,
    result_lines as collection_result_lines,
)
from xti.application.asset_context import AssetCriticalityService
from xti.application.suppliers import SupplierService
from xti.application.supplier_candidates import SupplierCandidateService
from xti.application.supplier_threat_events import SupplierThreatEventService
from xti.application.supplier_risk import SupplierRiskService
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.application.discovery import DiscoveryService, build_query_plan, build_prefix_query_plan
from xti.application.jobs import JobService
from xti.application.enrichment import FindingEnrichmentService, ReviewQueueService
from xti.application.reporting import FindingReportService
from xti.application.maintenance import MaintenanceService
from xti.application.storage_readiness import StorageReadinessService
from xti.application.inbox import InboxService
from xti.application.status import StatusService
from xti.application.feedback import FeedbackService
from xti.application.monitoring import MonitorService
from xti.application.allowlist import AllowlistService
from xti.application.surface import (
    SurfaceDiscoveryService,
    SurfaceOverviewService,
    SurfaceService,
    SurfaceWatchService,
)
from xti.application.mail import SurfaceMailService
from xti.application.cname import SurfaceCnameService
from xti.application.services import SurfaceServiceScanService
from xti.application.nmap_scan import NmapSurfaceScanService
from xti.application.nmap_management import NmapManagementService
from xti.application.surface_monitor import (
    MailSurfaceMonitorRunner,
    ServiceSurfaceMonitorRunner,
    SurfaceMonitorService,
    WebSurfaceMonitorRunner,
)
from xti.application.surface_freshness import SurfaceFreshnessService
from xti.application.surface_exposure import SurfaceExposureService
from xti.application.technology import TechnologyService
from xti.application.vulnerability import (
    EpssCatalogService,
    KevCatalogService,
    NvdCatalogService,
    NvdEnrichmentPlanService,
    NvdEnrichmentBatchService,
    NvdWindowService,
    NvdApplicabilityService,
    VulnerabilityContextService,
)
from xti.application.vendor_source_evaluation import VendorSourceEvaluationService
from xti.application.brand_source_evaluation import BrandSourceEvaluationService
from xti.application.brand_source_coverage import BrandSourceCoverageService
from xti.application.brand_username import (
    DEFAULT_PLATFORMS,
    EXTENDED_PLATFORMS,
    SHERLOCK_DEFAULT_PLATFORMS,
    SHERLOCK_EXTENDED_PLATFORMS,
    SHERLOCK_SUPPORTED_PLATFORMS,
    SUPPORTED_PLATFORMS,
    BrandUsernamePreviewService,
    SherlockUsernamePreviewService,
)
from xti.application.ubuntu_osv import UbuntuOsvPreviewService
from xti.application.ubuntu_package_match import UbuntuPackageMatchService
from xti.application.ubuntu_packages import (
    UbuntuAssetPackageService,
    UbuntuInventoryMatchService,
    UbuntuInventoryScanService,
)
from xti.application.ubuntu_evidence import UbuntuExposureEvidenceService
from xti.application.ubuntu_evidence_check import UbuntuEvidenceCheckService
from xti.application.ubuntu_evidence_scan import (
    UbuntuEvidencePlanService,
    UbuntuEvidenceScanService,
)
from xti.application.cti_indicators import CtiIndicatorService
from xti.application.cti_feeds import CtiFeedService
from xti.application.cti_attack import AttackSyncService
from xti.application.ransomware_claims import (
    RansomwareClaimHistoryService,
    RansomwareClaimService,
)
from xti.application.ransomlook_ransomware import (
    RansomLookClaimHistoryService,
    RansomLookClaimService,
)
from xti.application.ransomlook_watches import RansomLookWatchService
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.application.brand_username_watch_batch import (
    BrandUsernameWatchBatchService,
)
from xti.application.brand_username_watch_monitor import (
    BrandUsernameWatchMonitorService,
)
from xti.application.brand_username_reviews import BrandUsernameReviewService
from xti.application.ransomware_source_evaluation import (
    RansomwareSourceEvaluationService,
)
from xti.application.ransomware_source_comparison import (
    RansomwareSourceComparisonService,
)
from xti.application.ransomware_source_reviews import RansomwareSourceReviewService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.application.ransomware_watch_refresh import RansomwareWatchRefreshService
from xti.application.ransomware_watch_monitor import RansomwareWatchMonitorService
from xti.application.ransomware_monitor_sessions import RansomwareMonitorSessionService
from xti.application.ransomware_watch_timeline import RansomwareWatchTimelineService
from xti.application.ransomware_watch_identity_candidates import (
    RansomwareWatchIdentityCandidateService,
)
from xti.application.ransomware_identity_reviews import (
    RansomwareIdentityReviewService,
)
from xti.domain.cti_feeds import CTI_FEED_POLICIES
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.application.cti_saved_searches import CtiSavedSearchService
from xti.application.cti_saved_search_batch import CtiSavedSearchBatchService
from xti.application.cti_saved_search_monitor import CtiSavedSearchMonitorService
from xti.application.cti_hunting_journal import CtiHuntingJournalService
from xti.application.stix_export import StixExportService
from xti.application.webhooks import WebhookService
from xti.application.surface_inventory import SurfaceInventoryService
from xti.application.products import AssetProductService
from xti.application.packages import AssetPackageService
from xti.application.product_vulnerability import ProductVulnerabilityService
from xti.application.product_vulnerability_overview import ProductVulnerabilityOverviewService
from xti.application.product_vulnerability_inventory import ProductVulnerabilityInventoryService
from xti.application.vulnerability_exposures import VulnerabilityExposureService
from xti.application.vulnerability_exposure_queue import VulnerabilityExposureQueueService
from xti.application.vulnerability_exposure_evidence import (
    VulnerabilityExposureEvidenceService,
)
from xti.application.osv_advisory import OsvAdvisoryPreviewService
from xti.application.osv_advisory_evidence import OsvAdvisoryEvidenceService
from xti.application.vendor_advisory import VendorAdvisoryPreviewService
from xti.application.vendor_package_match import VendorPackageMatchService
from xti.application.vendor_package_evidence import VendorPackageEvidenceService
from xti.application.vendor_package_evidence_check import (
    VendorPackageEvidenceCheckService,
)
from xti.application.vulnerability_remediation import VulnerabilityRemediationService
from xti.application.vulnerability_exposure_suppressions import (
    VulnerabilityExposureSuppressionService,
)
from xti.application.vulnerability_reassessment import VulnerabilityReassessmentService
from xti.application.vulnerability_notifications import VulnerabilityNotificationService
from xti.application.tracked_nvd_refresh import TrackedNvdRefreshService
from xti.application.surface_discovery_status import SurfaceDiscoveryStatusService
from xti.application.surface_source_evaluation import SurfaceSourceEvaluationService
from xti.application.evaluation import EvaluationService
from xti.application.sources import SourceCatalogService
from xti.application.source_readiness import SourceReadinessService
from xti.adapters.source_readiness import SQLiteSourceReadinessRepository
from xti.interfaces.source_readiness import report_lines as source_readiness_lines
from xti.application.findings import (
    DomainImportService, FindingService, FINDING_STATUSES, REVIEW_DECISIONS,
)
from xti.config import Settings
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.discovery import ScanResult
from xti.domain.enrichment import BatchCheckResult
from xti.domain.feedback import FeedbackError
from xti.domain.jobs import JOB_STATUSES, ScanAttempt
from xti.domain.vulnerability import normalize_cve_id
from xti.domain.monitoring import MonitorSpec
from xti.domain.matching import (
    DomainMatcher, EXPANDED_ASCII_RULE_VERSION, IDN_RULE_VERSION,
    LEGACY_RULE_VERSION, RULE_VERSION,
)
from xti.domain.priority import parse_timestamp
from xti.domain.surface import SURFACE_DISCOVERY_PROVIDERS
from xti.ports.jobs import WorkerBusyError
from xti.ports.discovery import SourceError
from xti.interfaces.text import safe_text
from xti.interfaces.cti_attack import attack_sync_lines
from xti.interfaces.analysis import (
    refresh_result_lines as unified_analysis_refresh_lines,
    report_lines as unified_analysis_lines,
)
from xti.interfaces.inbox import page_lines as inbox_page_lines, detail_lines as inbox_detail_lines
from xti.interfaces.status import status_lines
from xti.interfaces.feedback import feedback_lines
from xti.interfaces.osv_advisory import (
    evidence_selection_lines as osv_advisory_evidence_lines,
    preview_lines as osv_advisory_preview_lines,
)
from xti.interfaces.vendor_advisory import preview_lines as vendor_advisory_preview_lines
from xti.interfaces.vendor_package_match import report_lines as vendor_package_match_lines
from xti.interfaces.vendor_package_evidence import (
    selection_lines as vendor_package_evidence_selection_lines,
    mutation_lines as vendor_package_evidence_mutation_lines,
    list_lines as vendor_package_evidence_list_lines,
    detail_lines as vendor_package_evidence_detail_lines,
)
from xti.interfaces.vendor_package_evidence_check import (
    report_lines as vendor_package_evidence_check_lines,
)
from xti.interfaces.monitoring import run_lines as monitor_run_lines, report_lines as monitor_report_lines, entry_lines as monitor_entry_lines
from xti.interfaces.evaluation import evaluation_lines
from xti.interfaces.surface import (
    candidate_detail_lines as surface_candidate_detail_lines,
    candidate_list_lines as surface_candidate_list_lines,
    check_lines as surface_check_lines,
    detail_lines as surface_detail_lines,
    discovery_lines as surface_discovery_lines,
    discovery_run_detail_lines as surface_discovery_run_detail_lines,
    discovery_run_list_lines as surface_discovery_run_list_lines,
    list_lines as surface_list_lines,
    overview_lines as surface_overview_lines,
    watch_lines as surface_watch_lines,
)
from xti.interfaces.mail import (
    check_lines as mail_check_lines,
    detail_lines as mail_detail_lines,
)
from xti.interfaces.cname import (
    check_lines as cname_check_lines,
    detail_lines as cname_detail_lines,
    result_status as cname_result_status,
)
from xti.interfaces.services import (
    check_lines as service_check_lines,
    detail_lines as service_detail_lines,
    result_status as service_result_status,
)
from xti.interfaces.nmap_scan import (
    check_lines as nmap_check_lines,
    detail_lines as nmap_detail_lines,
    readiness_lines as nmap_readiness_lines,
)
from xti.interfaces.nmap_management import (
    execute_nmap_management_command, register_nmap_management_parsers,
)
from xti.domain.nmap_scan import NMAP_PROFILES, build_nmap_scan_plan
from xti.interfaces.surface_monitor import report_lines as surface_monitor_report_lines
from xti.interfaces.surface_freshness import report_lines as surface_freshness_report_lines
from xti.interfaces.surface_exposure import report_lines as surface_exposure_report_lines
from xti.interfaces.technology import report_lines as technology_report_lines
from xti.interfaces.vulnerability import (
    detail_lines as kev_detail_lines,
    list_lines as kev_list_lines,
    status_lines as kev_status_lines,
    sync_lines as kev_sync_lines,
    epss_detail_lines,
    epss_list_lines,
    epss_status_lines,
    epss_sync_lines,
    nvd_detail_lines,
    nvd_list_lines,
    nvd_status_lines,
    nvd_sync_lines,
    context_lines as vulnerability_context_lines,
    enrichment_plan_lines as nvd_enrichment_plan_lines,
    enrichment_batch_lines as nvd_enrichment_batch_lines,
    applicability_lines as nvd_applicability_lines,
)
from xti.interfaces.surface_inventory import report_lines as surface_inventory_report_lines
from xti.interfaces.surface_discovery_status import (
    health_lines as surface_discovery_health_lines,
    report_lines as surface_discovery_status_report_lines,
)
from xti.interfaces.storage_readiness import report_lines as storage_readiness_report_lines
from xti.interfaces.products import (
    detail_lines as product_detail_lines,
    list_lines as product_list_lines,
    mutation_lines as product_mutation_lines,
)
from xti.interfaces.packages import (
    detail_lines as package_detail_lines,
    list_lines as package_list_lines,
    mutation_lines as package_mutation_lines,
)
from xti.interfaces.cti_indicators import (
    detail_lines as cti_indicator_detail_lines,
    list_lines as cti_indicator_list_lines,
    mutation_lines as cti_indicator_mutation_lines,
)
from xti.interfaces.cti_feeds import (
    status_lines as cti_feed_status_lines,
    sync_lines as cti_feed_sync_lines,
)
from xti.interfaces.ransomware_claims import (
    history_status_lines as ransomware_history_status_lines,
    refresh_lines as ransomware_refresh_lines,
    report_lines as ransomware_claim_report_lines,
)
from xti.interfaces.ransomlook_ransomware import (
    history_status_lines as ransomlook_history_status_lines,
    report_lines as ransomlook_claim_report_lines,
    refresh_lines as ransomlook_refresh_lines,
)
from xti.interfaces.ransomlook_watches import (
    detail_lines as ransomlook_watch_detail_lines,
    list_lines as ransomlook_watch_list_lines,
    mutation_lines as ransomlook_watch_mutation_lines,
    run_lines as ransomlook_watch_run_lines,
)
from xti.interfaces.brand_username_watches import (
    batch_lines as brand_username_watch_batch_lines,
    detail_lines as brand_username_watch_detail_lines,
    list_lines as brand_username_watch_list_lines,
    mutation_lines as brand_username_watch_mutation_lines,
    monitor_lines as brand_username_watch_monitor_lines,
    run_lines as brand_username_watch_run_lines,
    review_detail_lines as brand_username_review_detail_lines,
    review_mutation_lines as brand_username_review_mutation_lines,
)
from xti.interfaces.ransomware_source_evaluation import (
    report_lines as ransomware_source_evaluation_lines,
)
from xti.interfaces.ransomware_source_comparison import (
    report_lines as ransomware_source_comparison_lines,
    review_detail_lines as ransomware_source_review_detail_lines,
    review_mutation_lines as ransomware_source_review_mutation_lines,
)
from xti.interfaces.ransomware_watches import (
    detail_lines as ransomware_watch_detail_lines,
    identity_candidate_lines as ransomware_watch_identity_candidate_lines,
    identity_review_detail_lines as ransomware_identity_review_detail_lines,
    identity_review_mutation_lines as ransomware_identity_review_mutation_lines,
    list_lines as ransomware_watch_list_lines,
    monitor_lines as ransomware_watch_monitor_lines,
    monitor_session_detail_lines as ransomware_monitor_session_detail_lines,
    monitor_session_list_lines as ransomware_monitor_session_list_lines,
    mutation_lines as ransomware_watch_mutation_lines,
    refresh_all_lines as ransomware_watch_refresh_all_lines,
    run_lines as ransomware_watch_run_lines,
    timeline_lines as ransomware_watch_timeline_lines,
)
from xti.interfaces.cti_knowledge import (
    entity_detail_lines as cti_entity_detail_lines,
    entity_list_lines as cti_entity_list_lines,
    entity_mutation_lines as cti_entity_mutation_lines,
    relationship_detail_lines as cti_relationship_detail_lines,
    relationship_list_lines as cti_relationship_list_lines,
    relationship_mutation_lines as cti_relationship_mutation_lines,
    search_lines as cti_search_lines,
)
from xti.interfaces.cti_saved_searches import (
    batch_lines as cti_saved_search_batch_lines,
    detail_lines as cti_saved_search_detail_lines,
    list_lines as cti_saved_search_list_lines,
    mutation_lines as cti_saved_search_mutation_lines,
    monitor_lines as cti_saved_search_monitor_lines,
    run_lines as cti_saved_search_run_lines,
)
from xti.interfaces.cti_hunting_journal import (
    journal_lines as cti_hunting_journal_lines,
    note_lines as cti_hunting_note_lines,
    tag_mutation_lines as cti_hunting_tag_mutation_lines,
)
from xti.interfaces.stix_export import export_lines as stix_export_lines
from xti.interfaces.webhooks import (
    delivery_detail_lines as webhook_delivery_detail_lines,
    delivery_lines as webhook_delivery_lines,
    delivery_page_lines as webhook_delivery_page_lines,
    delivery_result_lines as webhook_delivery_result_lines,
    destination_lines as webhook_destination_lines,
    destination_list_lines as webhook_destination_list_lines,
    destination_mutation_lines as webhook_destination_mutation_lines,
    secret_lines as webhook_secret_lines,
)
from xti.interfaces.product_vulnerability import assessment_lines as product_vulnerability_lines
from xti.interfaces.product_vulnerability_overview import (
    overview_lines as product_vulnerability_overview_lines,
)
from xti.interfaces.product_vulnerability_inventory import (
    inventory_lines as product_vulnerability_inventory_lines,
)
from xti.interfaces.vulnerability_exposures import (
    detail_lines as vulnerability_exposure_detail_lines,
    list_lines as vulnerability_exposure_list_lines,
    mutation_lines as vulnerability_exposure_mutation_lines,
)
from xti.interfaces.vulnerability_exposure_queue import (
    queue_lines as vulnerability_exposure_queue_lines,
)
from xti.interfaces.asset_context import (
    detail_lines as asset_criticality_detail_lines,
    mutation_lines as asset_criticality_mutation_lines,
)
from xti.interfaces.suppliers import (
    detail_lines as supplier_detail_lines,
    list_lines as supplier_list_lines,
    mutation_lines as supplier_mutation_lines,
)
from xti.interfaces.supplier_candidates import (
    detail_lines as supplier_candidate_detail_lines,
    list_lines as supplier_candidate_list_lines,
    mutation_lines as supplier_candidate_mutation_lines,
    refresh_lines as supplier_candidate_refresh_lines,
)
from xti.interfaces.supplier_threat_events import (
    detail_lines as supplier_threat_event_detail_lines,
    report_lines as supplier_threat_event_report_lines,
)
from xti.interfaces.supplier_risk import (
    detail_lines as supplier_risk_detail_lines,
    report_lines as supplier_risk_report_lines,
)
from xti.interfaces.cases import (
    detail_lines as case_detail_lines,
    evidence_mutation_lines as case_evidence_mutation_lines,
    evidence_detail_lines as case_evidence_detail_lines,
    list_lines as case_list_lines,
    mutation_lines as case_mutation_lines,
    note_lines as case_note_lines,
    report_lines as case_report_lines,
    task_mutation_lines as case_task_mutation_lines,
)
from xti.interfaces.vulnerability_exposure_evidence import (
    detail_lines as vulnerability_exposure_evidence_detail_lines,
    list_lines as vulnerability_exposure_evidence_list_lines,
    mutation_lines as vulnerability_exposure_evidence_mutation_lines,
)
from xti.interfaces.vulnerability_remediation import (
    detail_lines as vulnerability_remediation_detail_lines,
    list_lines as vulnerability_remediation_list_lines,
    mutation_lines as vulnerability_remediation_mutation_lines,
)
from xti.interfaces.vulnerability_exposure_suppressions import (
    detail_lines as vulnerability_exposure_suppression_detail_lines,
    mutation_lines as vulnerability_exposure_suppression_mutation_lines,
)
from xti.interfaces.vulnerability_reassessment import (
    plan_lines as vulnerability_reassessment_plan_lines,
    run_lines as vulnerability_reassessment_run_lines,
    run_list_lines as vulnerability_reassessment_run_list_lines,
)
from xti.interfaces.vulnerability_notifications import (
    notification_lines as vulnerability_notification_lines,
)
from xti.interfaces.tracked_nvd_refresh import (
    plan_lines as tracked_nvd_refresh_plan_lines,
    result_lines as tracked_nvd_refresh_result_lines,
)
from xti.interfaces.nvd_window import (
    coverage_lines as nvd_window_coverage_lines,
    detail_lines as nvd_window_detail_lines,
    gap_fetch_lines as nvd_window_gap_fetch_lines,
    gap_plan_lines as nvd_window_gap_plan_lines,
    list_lines as nvd_window_list_lines,
    operations_lines as nvd_window_operations_lines,
    plan_lines as nvd_window_plan_lines,
    restart_lines as nvd_window_restart_lines,
    result_lines as nvd_window_result_lines,
)
from xti.interfaces.vendor_source_evaluation import (
    report_lines as vendor_source_evaluation_lines,
)
from xti.interfaces.brand_source_evaluation import (
    report_lines as brand_source_evaluation_lines,
)
from xti.interfaces.surface_source_evaluation import (
    report_lines as surface_source_evaluation_lines,
)
from xti.interfaces.brand_source_coverage import (
    report_lines as brand_source_coverage_lines,
)
from xti.interfaces.brand_username import (
    preview_lines as brand_username_preview_lines,
    profile_lines as brand_username_profile_lines,
)
from xti.interfaces.ubuntu_osv import ubuntu_preview_lines
from xti.interfaces.ubuntu_package_match import report_lines as ubuntu_package_match_lines
from xti.interfaces.ubuntu_packages import (
    detail_lines as ubuntu_package_detail_lines,
    list_lines as ubuntu_package_list_lines,
    match_lines as ubuntu_inventory_match_lines,
    scan_lines as ubuntu_inventory_scan_lines,
    mutation_lines as ubuntu_package_mutation_lines,
)
from xti.interfaces.ubuntu_evidence import (
    selection_lines as ubuntu_evidence_selection_lines,
)
from xti.interfaces.ubuntu_evidence_check import (
    report_lines as ubuntu_evidence_check_lines,
)
from xti.interfaces.ubuntu_evidence_scan import (
    plan_lines as ubuntu_evidence_plan_lines,
    scan_lines as ubuntu_evidence_scan_lines,
)
from xti.interfaces.enrichment import (
    batch_lines, check_lines, checks_incomplete, queue_lines, PRIORITY_LABELS,
)


STATUS_LABELS = {
    "new": "Yeni",
    "suspicious": "Şüpheli",
    "dismissed": "Normal / kapatıldı",
    "uncertain": "Emin değilim",
}

JOB_LABELS = {
    "queued": "Sırada", "running": "Çalışıyor", "complete": "Tamamlandı",
    "partial": "Kısmi", "failed": "Başarısız", "interrupted": "Yarım kaldı",
}

SOURCE_LABELS = {
    "crt.sh": "crt.sh sertifika kayıtları",
    "urlscan": "urlscan web inceleme kayıtları",
}


def build_parser() -> Parser:
    parser = root_parser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Yerel kayıt alanını oluştur.")
    commands.add_parser("doctor", help="Kayıt alanının durumunu kontrol et.")
    commands.add_parser(
        "evaluate",
        help="Eşleştirme kurallarını sürümlü sentetik örneklerle ağsız ve kayıtsız ölç.",
    )
    commands.add_parser(
        "feedback",
        help="Kayıtlı kullanıcı kararlarını kural sürümüne göre ağsız ve salt okunur özetle.",
    )
    analyze = commands.add_parser(
        "analyze",
        help="Bir domainin kayıtlı dış risk kanıtlarını tek ağsız görünümde birleştir.",
    )
    analyze.add_argument("domain", help="Önceden kaydedilmiş kök alan adı.")
    analyze.add_argument(
        "--stale-after-hours", type=int, default=24,
        help="Bu saatten eski kanıtı eski göster (1–8760; varsayılan 24).",
    )
    analyze.add_argument(
        "--finding-limit", type=int, default=10,
        help="Gösterilecek marka/domain adayı sınırı (1–50).",
    )
    analyze.add_argument(
        "--refresh-ioc", choices=("feodo", "certpl"),
        help=(
            "Açık seçimle ücretsiz IOC listesini internetten yenile, kaydet ve analizi "
            "tekrar üret. Verilmezse komut ağsız ve salt-okunurdur."
        ),
    )
    collect = commands.add_parser(
        "collect",
        help="Kayıtlı domain için seçilen pasif kaynakları topla ve birleşik analiz üret.",
    )
    collect.add_argument("domain", nargs="?", help="Önceden kaydedilmiş domain.")
    collect.add_argument("--profile", metavar="AD", help="Kayıtlı toplama profilini kullan.")
    collect.add_argument(
        "--plan", action="store_true",
        help="Seçilen işleri ağ ve veri yazımı olmadan göster; toplama başlatmaz.",
    )
    add_collection_arguments(collect)
    collect.add_argument("--summary", action="store_true", help="Kaynak durumunu ve hedef özetini kısa göster; toplama kapsamı ve JSON değişmez.")
    register_profiles_parser(commands)
    register_schedule_commands(commands)
    changes = commands.add_parser("changes", help="Son gün veya haftadaki kayıtlı değişiklikleri ve kaynak boşluklarını göster.")
    changes.add_argument("--days", type=int, choices=(1, 7), default=1)
    change_scope = changes.add_mutually_exclusive_group()
    change_scope.add_argument("--domain", help="Yalnız bu domainin marka, dış yüzey ve kamu olay kayıtları.")
    change_scope.add_argument("--organization", help="Kuruluşun güncel etkin bağlantılarındaki kayıtları göster.")
    changes.add_argument("--limit", type=int, default=100, help="Bölüm başına görünüm sınırı (1–500).")
    changes.add_argument("--offset", type=int, default=0, help="Her bölümdeki ilk gösterilecek kayıt.")
    register_public_notice_parser(commands)
    register_history_parser(commands)
    register_organizations_parser(commands)
    register_global_search_parser(commands)
    register_research_parser(commands)
    register_investigation_parser(commands)
    register_report_parser(commands)
    from xti.interfaces.journal_storage import register_journal_parser
    register_journal_parser(commands)
    from xti.interfaces.evidence import register_evidence_parser
    register_evidence_parser(commands)
    register_company_review_parser(commands)
    register_research_history_parser(commands)
    register_source_jobs_parser(commands)
    register_warninglist_parser(commands)
    register_enrichment_parser(commands)
    register_global_saved_search_parser(commands)
    register_news_parser(commands)
    register_mentions_parser(commands)
    register_engine_parser(commands)
    register_platform_parser(commands)
    register_components_parser(commands)
    register_event_candidates_parser(commands)
    brand = commands.add_parser(
        "brand",
        help="Sosyal kullanıcı adı ve geniş marka OSINT kaynaklarını değerlendir.",
    )
    brand_actions = brand.add_subparsers(dest="brand_action", required=True)
    brand_actions.add_parser(
        "source-evaluation",
        help="Ücretsiz dış araçların kabul kararını ağsız ve kayıtsız göster.",
    )
    brand_actions.add_parser(
        "source-coverage",
        help=(
            "Maigret ve ikinci ücretsiz sosyal kaynak kapsamını sürümlü, ağsız "
            "kanıtla karşılaştır."
        ),
    )
    brand_profile_list = brand_actions.add_parser(
        "profile-list",
        help="Maigret ve Sherlock safe/extended platform listelerini ağsız göster.",
    )
    brand_profile_list.add_argument(
        "--source",
        choices=("maigret", "sherlock", "all"),
        default="all",
    )
    brand_username_preview = brand_actions.add_parser(
        "username-preview",
        help=(
            "Maigret veya Sherlock ile seçili herkese açık platformlarda "
            "yazmasız önizleme yap."
        ),
    )
    brand_username_preview.add_argument(
        "username", help="Açıkça araştırılacak marka kullanıcı adı.",
    )
    brand_username_preview.add_argument(
        "--source",
        choices=("maigret", "sherlock"),
        default="maigret",
        help="Kullanılacak ücretsiz kaynak (varsayılan maigret).",
    )
    brand_username_scope = brand_username_preview.add_mutually_exclusive_group()
    brand_username_scope.add_argument(
        "--profile",
        choices=("safe", "extended"),
        help=(
            "Platform kapsamı: safe dar varsayılan, extended incelenmiş geniş "
            "liste. Verilmezse safe kullanılır."
        ),
    )
    brand_username_scope.add_argument(
        "--site",
        action="append",
        dest="platforms",
        metavar="PLATFORM",
        help="Seçilen kaynağın kontrol edeceği platform.",
    )
    brand_username_preview.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Her platform isteği için 5–30 saniye (varsayılan 10).",
    )
    brand_watch_add = brand_actions.add_parser(
        "watch-add",
        help="Marka kullanıcı adını seçili platformlarda kalıcı izlemeye ekle.",
    )
    brand_watch_add.add_argument("name", help="İzlemeyi ayırt eden yerel ad.")
    brand_watch_add.add_argument("username", help="İzlenecek açık marka kullanıcı adı.")
    brand_watch_add.add_argument(
        "--source",
        choices=("maigret", "sherlock"),
        default="maigret",
        help="Kalıcı izleme kaynağı (varsayılan maigret; sonradan değiştirilemez).",
    )
    brand_watch_scope = brand_watch_add.add_mutually_exclusive_group()
    brand_watch_scope.add_argument(
        "--profile",
        choices=("safe", "extended"),
        help=(
            "İzlenecek platform kapsamı. Verilmezse safe; --site kullanılırsa "
            "özel liste oluşturulur."
        ),
    )
    brand_watch_scope.add_argument(
        "--site", action="append",
        dest="platforms",
        metavar="PLATFORM",
        help="Seçilen kaynağın izleyeceği platform.",
    )
    brand_watch_list = brand_actions.add_parser(
        "watch-list", help="Kayıtlı sosyal kullanıcı adı izlemelerini ağsız listele.",
    )
    brand_watch_list.add_argument("--all", action="store_true")
    brand_watch_list.add_argument("--limit", type=int, default=50)
    brand_watch_show = brand_actions.add_parser(
        "watch-show", help="Bir izlemenin tanımını ve çalışma geçmişini ağsız göster.",
    )
    brand_watch_show.add_argument("watch_id")
    brand_watch_show.add_argument("--event-limit", type=int, default=50)
    brand_watch_show.add_argument("--run-limit", type=int, default=20)
    brand_watch_revoke = brand_actions.add_parser(
        "watch-revoke", help="İzlemeyi gerekçesiyle geri çek; geçmişi silme.",
    )
    brand_watch_revoke.add_argument("watch_id")
    brand_watch_revoke.add_argument("--reason", required=True)
    brand_watch_run = brand_actions.add_parser(
        "watch-run", help="İzlemeyi kayıtlı kaynağıyla bir kez çalıştır ve farkı kaydet.",
    )
    brand_watch_run.add_argument("watch_id")
    brand_watch_run.add_argument("--timeout", type=int, default=10)
    brand_watch_run.add_argument("--limit", type=int, default=100)
    brand_watch_run_all = brand_actions.add_parser(
        "watch-run-all",
        help="Bütün etkin sosyal kullanıcı adı izlemelerini bir kez çalıştır.",
    )
    brand_watch_run_all.add_argument(
        "--watch-limit",
        type=int,
        default=10,
        help="Çalıştırılabilecek etkin izleme üst sınırı (1–100; varsayılan 10).",
    )
    brand_watch_run_all.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Her platform isteği için 5–30 saniye (varsayılan 10).",
    )
    brand_watch_monitor = brand_actions.add_parser(
        "watch-monitor",
        help="Tek izlemeyi terminal açıkken sınırlı aralıklarla tekrarla.",
    )
    brand_watch_monitor.add_argument("watch_id")
    brand_watch_monitor.add_argument(
        "--cycles",
        type=int,
        default=3,
        help="En fazla tur sayısı (1–1000; varsayılan 3).",
    )
    brand_watch_monitor.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Turlar arası saniye (300–86400; varsayılan 3600).",
    )
    brand_watch_monitor.add_argument(
        "--duration",
        type=int,
        default=86400,
        help="Yeni tur başlatma bütçesi (1–604800 saniye; varsayılan 86400).",
    )
    brand_watch_monitor.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Her platform isteği için 5–30 saniye (varsayılan 10).",
    )
    brand_watch_run_show = brand_actions.add_parser(
        "watch-run-show", help="Kayıtlı bir sosyal kullanıcı adı çalışmasını ağsız göster.",
    )
    brand_watch_run_show.add_argument("run_id")
    brand_watch_run_show.add_argument("--limit", type=int, default=100)
    brand_watch_review = brand_actions.add_parser(
        "watch-review",
        help="Son başarılı çalışmadaki tam profil kanıtına gerekçeli kullanıcı kararı ver.",
    )
    brand_watch_review.add_argument("watch_id")
    brand_watch_review.add_argument(
        "platform", choices=SUPPORTED_PLATFORMS + SHERLOCK_SUPPORTED_PLATFORMS,
    )
    brand_watch_review.add_argument(
        "--decision",
        required=True,
        choices=("known_official", "possible_impersonation", "uncertain"),
    )
    brand_watch_review.add_argument("--reason", required=True)
    brand_watch_review_show = brand_actions.add_parser(
        "watch-review-show", help="Kayıtlı tam profil karar geçmişini ağsız göster.",
    )
    brand_watch_review_show.add_argument("candidate_id")
    brand_watch_review_show.add_argument("--event-limit", type=int, default=100)
    ransomware = commands.add_parser(
        "ransomware",
        help="Açık bir akıştaki ransomware leak-site iddialarını güvenli biçimde araştır.",
    )
    ransomware_actions = ransomware.add_subparsers(
        dest="ransomware_action", required=True,
    )
    ransomware_recent = ransomware_actions.add_parser(
        "recent",
        help="Seçilen açık iddia akışını bir kez al ve yerelde ara.",
    )
    ransomware_recent.add_argument(
        "query", nargs="?",
        help="İsteğe bağlı kuruluş, domain, grup, ülke veya sektör ifadesi.",
    )
    ransomware_recent.add_argument(
        "--status", choices=("all", "listed", "delisted"), default="all",
        help="ThreatCluster ilan durumu; RansomLook yalnız all destekler.",
    )
    ransomware_recent.add_argument(
        "--source", choices=("threatcluster", "ransomlook"),
        default="threatcluster", help="Açık kaynak (varsayılan: threatcluster).",
    )
    ransomware_recent.add_argument(
        "--limit", type=int, default=20, help="Gösterilecek kayıt sınırı (1–100).",
    )
    ransomware_actions.add_parser(
        "source-evaluation",
        help="İkinci ücretsiz ransomware kaynağı kabul kararını ağsız göster.",
    )
    ransomware_source_compare = ransomware_actions.add_parser(
        "source-compare",
        help=(
            "ThreatCluster ve RansomLook son yerel snapshot'larını birleştirmeden "
            "ağsız karşılaştır."
        ),
    )
    ransomware_source_compare.add_argument(
        "--limit", type=int, default=100,
        help="Gösterilecek açıklanabilir eşleşme sınırı (1–500).",
    )
    ransomware_source_review = ransomware_actions.add_parser(
        "source-review",
        help="Bir kaynak karşılaştırmasına gerekçeli insan kararı kaydet.",
    )
    ransomware_source_review.add_argument("comparison_id")
    ransomware_source_review.add_argument(
        "--decision", required=True,
        choices=("possible_same", "different", "uncertain"),
    )
    ransomware_source_review.add_argument("--reason", required=True)
    ransomware_source_review_show = ransomware_actions.add_parser(
        "source-review-show",
        help="Kaynak karşılaştırmasının silinmeyen karar geçmişini göster.",
    )
    ransomware_source_review_show.add_argument("comparison_id")
    ransomware_source_review_show.add_argument(
        "--event-limit", type=int, default=100,
    )
    ransomware_refresh = ransomware_actions.add_parser(
        "refresh",
        help="Açık iddia snapshot'ını al, yerel geçmişe kaydet ve öncekiyle karşılaştır.",
    )
    ransomware_refresh.add_argument(
        "--limit", type=int, default=100,
        help="Gösterilecek geçmiş öğesi sınırı (1–500).",
    )
    ransomware_refresh.add_argument(
        "--source", choices=("threatcluster", "ransomlook"),
        default="threatcluster", help="Kaydedilecek açık kaynak (varsayılan: threatcluster).",
    )
    ransomware_status = ransomware_actions.add_parser(
        "status", help="Yerel snapshot çalışma geçmişini ağ kullanmadan göster.",
    )
    ransomware_status.add_argument(
        "--limit", type=int, default=10,
        help="Gösterilecek çalışma sınırı (1–100).",
    )
    ransomware_status.add_argument(
        "--source", choices=("threatcluster", "ransomlook"),
        default="threatcluster", help="Gösterilecek ayrı kaynak geçmişi.",
    )
    ransomware_watch_add = ransomware_actions.add_parser(
        "watch-add",
        help="Kuruluş veya domain için yerel, kalıcı iddia izlemesi kaydet.",
    )
    ransomware_watch_add.add_argument("name", help="İzlemenin benzersiz görünen adı.")
    ransomware_watch_add.add_argument("query", help="Kuruluş adı veya kök domain.")
    ransomware_watch_add.add_argument(
        "--kind", choices=("organization", "domain"), required=True,
        help="Kuruluş adı mı, web domaini mi izlenecek.",
    )
    ransomware_watch_add.add_argument(
        "--match", choices=("exact", "contains"), default="exact",
        help="Kuruluş için exact veya contains; domain yalnız exact olabilir.",
    )
    ransomware_watch_add.add_argument(
        "--source", choices=("threatcluster", "ransomlook"),
        default="threatcluster", help="İzleme kaynağı (varsayılan: threatcluster).",
    )
    ransomware_watch_list = ransomware_actions.add_parser(
        "watch-list", help="Kayıtlı ransomware izlemelerini ağsız listele.",
    )
    ransomware_watch_list.add_argument(
        "--all", action="store_true", help="Geri çekilmiş izlemeleri de göster.",
    )
    ransomware_watch_list.add_argument("--limit", type=int, default=50)
    ransomware_watch_list.add_argument(
        "--source", choices=("threatcluster", "ransomlook"),
        default="threatcluster", help="Listelenecek ayrı kaynak izlemeleri.",
    )
    ransomware_watch_show = ransomware_actions.add_parser(
        "watch-show", help="Bir izlemenin tanımını ve çalışma geçmişini göster.",
    )
    ransomware_watch_show.add_argument("watch_id")
    ransomware_watch_show.add_argument("--event-limit", type=int, default=50)
    ransomware_watch_show.add_argument("--run-limit", type=int, default=20)
    ransomware_watch_show.add_argument(
        "--source", choices=("threatcluster", "ransomlook"),
        default="threatcluster", help="İzlemenin ayrı kaynağı.",
    )
    ransomware_watch_revoke = ransomware_actions.add_parser(
        "watch-revoke", help="İzlemeyi gerekçesiyle geri çek; geçmişi silme.",
    )
    ransomware_watch_revoke.add_argument("watch_id")
    ransomware_watch_revoke.add_argument("--reason", required=True)
    ransomware_watch_revoke.add_argument(
        "--source", choices=("threatcluster", "ransomlook"),
        default="threatcluster", help="İzlemenin ayrı kaynağı.",
    )
    ransomware_watch_run = ransomware_actions.add_parser(
        "watch-run",
        help="İzlemeyi son başarılı yerel snapshot üzerinde ağsız çalıştır.",
    )
    ransomware_watch_run.add_argument("watch_id")
    ransomware_watch_run.add_argument("--limit", type=int, default=100)
    ransomware_watch_run.add_argument(
        "--source", choices=("threatcluster", "ransomlook"),
        default="threatcluster", help="Çalıştırılacak ayrı kaynak izlemesi.",
    )
    ransomware_watch_refresh_all = ransomware_actions.add_parser(
        "watch-refresh-all",
        help="Açık kaynağı yenile, ardından bütün etkin izlemeleri bir kez çalıştır.",
    )
    ransomware_watch_refresh_all.add_argument(
        "--watch-limit", type=int, default=50,
        help="Çalıştırılabilecek etkin izleme sınırı (1–500).",
    )
    ransomware_watch_refresh_all.add_argument(
        "--source-item-limit", type=int, default=100,
        help="Kaynak fark raporu öğe sınırı (1–500).",
    )
    ransomware_watch_refresh_all.add_argument(
        "--watch-item-limit", type=int, default=100,
        help="Her izleme için sonuç görünüm sınırı (1–500).",
    )
    ransomware_watch_monitor = ransomware_actions.add_parser(
        "watch-monitor",
        help="Kaynak yenileme ve bütün etkin izlemeleri terminal açıkken tekrarla.",
    )
    ransomware_watch_monitor.add_argument(
        "--cycles", type=int, default=3,
        help="En fazla tur (1–1000; varsayılan 3).",
    )
    ransomware_watch_monitor.add_argument(
        "--interval", type=int, default=3600,
        help="Tamamlanan turlar arasındaki saniye (300–86400).",
    )
    ransomware_watch_monitor.add_argument(
        "--duration", type=int, default=86400,
        help="Yeni tur başlatma süresi, saniye (1–604800).",
    )
    ransomware_watch_monitor.add_argument(
        "--watch-limit", type=int, default=50,
        help="Her turdaki etkin izleme sınırı (1–500).",
    )
    ransomware_watch_monitor.add_argument(
        "--source-item-limit", type=int, default=100,
        help="Her turdaki kaynak fark raporu öğe sınırı (1–500).",
    )
    ransomware_watch_monitor.add_argument(
        "--watch-item-limit", type=int, default=100,
        help="Her izleme için sonuç görünüm sınırı (1–500).",
    )
    ransomware_watch_monitor_list = ransomware_actions.add_parser(
        "watch-monitor-list",
        help="Kalıcı ransomware monitor oturum geçmişini ağsız listele.",
    )
    ransomware_watch_monitor_list.add_argument("--limit", type=int, default=20)
    ransomware_watch_monitor_show = ransomware_actions.add_parser(
        "watch-monitor-show",
        help="Bir monitor oturumunu ve kalıcı tur kanıtlarını ağsız göster.",
    )
    ransomware_watch_monitor_show.add_argument("session_id")
    ransomware_watch_monitor_show.add_argument("--cycle-limit", type=int, default=100)
    ransomware_watch_timeline = ransomware_actions.add_parser(
        "watch-timeline",
        help="Bir izlemenin kayıtlı kaynak iddiası zaman çizelgesini ağsız göster.",
    )
    ransomware_watch_timeline.add_argument("watch_id")
    ransomware_watch_timeline.add_argument("--event-limit", type=int, default=100)
    ransomware_watch_identity_candidates = ransomware_actions.add_parser(
        "watch-identity-candidates",
        help="Olası kaynak kimliği değişimlerini birleştirmeden ağsız göster.",
    )
    ransomware_watch_identity_candidates.add_argument("watch_id")
    ransomware_watch_identity_candidates.add_argument(
        "--candidate-limit", type=int, default=100,
    )
    ransomware_identity_review = ransomware_actions.add_parser(
        "watch-identity-review",
        help="Bir kimlik adayına gerekçeli insan kararı kaydet.",
    )
    ransomware_identity_review.add_argument("watch_id")
    ransomware_identity_review.add_argument("candidate_id")
    ransomware_identity_review.add_argument(
        "--decision", required=True,
        choices=("possible_same", "different", "uncertain"),
    )
    ransomware_identity_review.add_argument("--reason", required=True)
    ransomware_identity_review_show = ransomware_actions.add_parser(
        "watch-identity-review-show",
        help="Bir kimlik adayının silinmeyen karar geçmişini göster.",
    )
    ransomware_identity_review_show.add_argument("candidate_id")
    ransomware_identity_review_show.add_argument("--event-limit", type=int, default=100)
    ransomware_watch_run_show = ransomware_actions.add_parser(
        "watch-run-show", help="Kayıtlı bir izleme çalışmasının sonuçlarını göster.",
    )
    ransomware_watch_run_show.add_argument("run_id")
    ransomware_watch_run_show.add_argument("--limit", type=int, default=100)
    ransomware_watch_run_show.add_argument(
        "--source", choices=("threatcluster", "ransomlook"),
        default="threatcluster", help="Çalışmanın ayrı kaynağı.",
    )
    vuln = commands.add_parser(
        "vuln",
        help="Uyumluluk için korunan eski zafiyet kayıtlarını yönet; aktif plan dışıdır.",
    )
    vuln_actions = vuln.add_subparsers(dest="vuln_action", required=True)
    vuln_actions.add_parser(
        "source-evaluation",
        help="Sonraki resmî üretici kaynağı için sürümlü ve ağsız değerlendirme kapısını göster.",
    )
    vuln_sync = vuln_actions.add_parser(
        "sync", help="Seçilen resmî zafiyet kaynağını internetten güncelle.",
    )
    vuln_sync.add_argument(
        "--source", choices=("kev", "epss", "nvd"), default="kev",
        help="CISA KEV, FIRST günlük EPSS veya tek CVE için NVD.",
    )
    vuln_sync.add_argument(
        "--cve", help="NVD kaynağında alınacak tek CVE; örnek: CVE-2021-44228.",
    )
    vuln_status = vuln_actions.add_parser(
        "status", help="Son kaynak çalışmasını ve yerel katalog sayılarını göster.",
    )
    vuln_status.add_argument("--limit", type=int, default=10, help="Çalışma sınırı (1–100).")
    vuln_status.add_argument("--source", choices=("kev", "epss", "nvd"), default="kev")
    vuln_list = vuln_actions.add_parser(
        "list", help="Seçilen yerel zafiyet kayıtlarını internete çıkmadan listele.",
    )
    vuln_list.add_argument(
        "--all", action="store_true", dest="all_entries",
        help="CISA'nın güncel kataloğundan çıkmış geçmiş kayıtları da göster.",
    )
    vuln_list.add_argument("--limit", type=int, default=20, help="Kayıt sınırı (1–500).")
    vuln_list.add_argument("--source", choices=("kev", "epss", "nvd"), default="kev")
    vuln_show = vuln_actions.add_parser(
        "show", help="Bir CVE'nin seçilen yerel kaynak kaydını göster.",
    )
    vuln_show.add_argument("cve_id", help="Örnek: CVE-2021-44228")
    vuln_show.add_argument(
        "--event-limit", type=int, default=20, help="Değişiklik geçmişi sınırı (1–100).",
    )
    vuln_show.add_argument("--source", choices=("kev", "epss", "nvd"), default="kev")
    vuln_overview = vuln_actions.add_parser(
        "overview", help="Bir CVE'nin yerel KEV, EPSS ve NVD bağlamını tek ekranda göster.",
    )
    vuln_overview.add_argument("cve_id", help="Örnek: CVE-2021-44228")
    vuln_plan = vuln_actions.add_parser(
        "plan", help="NVD bağlamı eksik öncelikli CVE'leri internete çıkmadan sırala.",
    )
    vuln_plan.add_argument("--limit", type=int, default=20, help="Plan sınırı (1–100).")
    vuln_plan.add_argument(
        "--min-epss", default="0.9", help="EPSS seçim eşiği, 0–1 (varsayılan 0.9).",
    )
    vuln_enrich = vuln_actions.add_parser(
        "enrich-nvd", help="Çevrimdışı planın en fazla beş CVE'sini aralıklı olarak NVD'den al.",
    )
    vuln_enrich.add_argument("--limit", type=int, default=3, help="İstek sınırı (1–5).")
    vuln_enrich.add_argument(
        "--min-epss", default="0.9", help="EPSS seçim eşiği, 0–1 (varsayılan 0.9).",
    )
    for action, help_text in (
        (
            "nvd-window-plan",
            "En fazla yedi günlük resmî NVD değişiklik penceresinin sonraki sayfasını ağsız planla.",
        ),
        (
            "nvd-window-fetch",
            "Planlanan resmî NVD değişiklik penceresinden yalnız bir sayfa al.",
        ),
    ):
        window_parser = vuln_actions.add_parser(action, help=help_text)
        window_parser.add_argument(
            "--start", required=True, dest="window_start",
            help="Saat dilimli ISO-8601 başlangıcı; örnek: 2026-10-01T00:00:00Z.",
        )
        window_parser.add_argument(
            "--end", required=True, dest="window_end",
            help="Saat dilimli ISO-8601 bitişi; başlangıçtan en fazla yedi gün sonra.",
        )
        window_parser.add_argument(
            "--page-size", type=int, default=20,
            help="Bu çağrıda alınacak en yüksek kayıt sayısı (1–100; varsayılan 20).",
        )
    nvd_window_list = vuln_actions.add_parser(
        "nvd-window-list", help="Kayıtlı NVD tarih pencerelerini internete çıkmadan listele.",
    )
    nvd_window_list.add_argument(
        "--status", choices=("all", "ready", "failed", "complete"), default="all",
    )
    nvd_window_list.add_argument("--limit", type=int, default=20)
    nvd_window_coverage = vuln_actions.add_parser(
        "nvd-window-coverage",
        help="Tamamlanan pencerelerin kapsadığı ve açık bıraktığı dönemleri göster.",
    )
    nvd_window_coverage.add_argument("--start", required=True, dest="window_start")
    nvd_window_coverage.add_argument("--end", required=True, dest="window_end")
    nvd_window_gap_plan = vuln_actions.add_parser(
        "nvd-window-gap-plan",
        help="Kapsama boşluklarını ağsız olarak en fazla yedi günlük pencerelere böl.",
    )
    nvd_window_gap_plan.add_argument("--start", required=True, dest="window_start")
    nvd_window_gap_plan.add_argument("--end", required=True, dest="window_end")
    nvd_window_gap_plan.add_argument("--page-size", type=int, default=20)
    nvd_window_gap_plan.add_argument("--limit", type=int, default=20)
    nvd_window_gap_fetch = vuln_actions.add_parser(
        "nvd-window-gap-fetch",
        help="İlk en fazla üç NVD boşluğunun her birinden yalnız bir sayfa al.",
    )
    nvd_window_gap_fetch.add_argument("--start", required=True, dest="window_start")
    nvd_window_gap_fetch.add_argument("--end", required=True, dest="window_end")
    nvd_window_gap_fetch.add_argument("--page-size", type=int, default=20)
    nvd_window_gap_fetch.add_argument("--limit", type=int, default=1)
    nvd_window_operations = vuln_actions.add_parser(
        "nvd-window-operations",
        help="Seçilen dönemin pencere, hata, ilerleme ve kapsama özetini ağsız göster.",
    )
    nvd_window_operations.add_argument("--start", required=True, dest="window_start")
    nvd_window_operations.add_argument("--end", required=True, dest="window_end")
    nvd_window_operations.add_argument("--recent-limit", type=int, default=10)
    for action, help_text in (
        ("nvd-window-show", "Bir NVD penceresini ve yeniden başlatma geçmişini göster."),
        (
            "nvd-window-restart",
            "Mevcut NVD penceresini gerekçeli ve denetlenebilir biçimde baştan başlat.",
        ),
    ):
        window_parser = vuln_actions.add_parser(action, help=help_text)
        window_parser.add_argument("--start", required=True, dest="window_start")
        window_parser.add_argument("--end", required=True, dest="window_end")
        window_parser.add_argument("--page-size", type=int, default=20)
        if action == "nvd-window-show":
            window_parser.add_argument("--event-limit", type=int, default=20)
        else:
            window_parser.add_argument("--reason", required=True)
    tracked_nvd_plan = vuln_actions.add_parser(
        "tracked-nvd-plan",
        help="Maruziyetlerle ilgili eski NVD kayıtlarını ağsız yenileme planına al.",
    )
    tracked_nvd_plan.add_argument(
        "--stale-after-hours", type=int, default=168,
        help="Son başarılı kontrolden sonra yenileme eşiği (1–8760; varsayılan 168).",
    )
    tracked_nvd_plan.add_argument("--include-closed", action="store_true")
    tracked_nvd_plan.add_argument("--include-suppressed", action="store_true")
    tracked_nvd_plan.add_argument(
        "--limit", type=int, default=20, help="Dikkat kaydı sınırı (1–100).",
    )
    tracked_nvd_refresh = vuln_actions.add_parser(
        "tracked-nvd-refresh",
        help="İlgili eski NVD kayıtlarından en fazla beşini resmî API'den yenile.",
    )
    tracked_nvd_refresh.add_argument(
        "--stale-after-hours", type=int, default=168,
        help="Son başarılı kontrolden sonra yenileme eşiği (1–8760; varsayılan 168).",
    )
    tracked_nvd_refresh.add_argument("--include-closed", action="store_true")
    tracked_nvd_refresh.add_argument("--include-suppressed", action="store_true")
    tracked_nvd_refresh.add_argument(
        "--limit", type=int, default=3, help="İstek sınırı (1–5).",
    )
    vuln_applicability = vuln_actions.add_parser(
        "applicability",
        help="Yerel NVD kaydındaki CPE ürün/sürüm koşullarını salt okunur göster.",
    )
    vuln_applicability.add_argument("cve_id", help="Örnek: CVE-2021-44228")
    vuln_applicability.add_argument(
        "--limit", type=int, default=50, help="Gösterim sınırı (1–500).",
    )
    vuln_assess_product = vuln_actions.add_parser(
        "assess-product",
        help="Doğrulanmış ürün kaydını yerel NVD CPE koşullarıyla salt okunur karşılaştır.",
    )
    vuln_assess_product.add_argument("product_id", help="./xti products list çıktısındaki kimlik.")
    vuln_assess_product.add_argument("cve_id", help="Örnek: CVE-2021-44228")
    vuln_assess_product.add_argument(
        "--limit", type=int, default=50, help="İlgili koşul gösterim sınırı (1–500).",
    )
    vuln_asset_overview = vuln_actions.add_parser(
        "asset-overview",
        help="Doğrulanmış ürün koşulu, KEV, EPSS ve CVSS bağlamını birlikte göster.",
    )
    vuln_asset_overview.add_argument("product_id", help="./xti products list çıktısındaki kimlik.")
    vuln_asset_overview.add_argument("cve_id", help="Örnek: CVE-2021-44228")
    vuln_asset_overview.add_argument(
        "--limit", type=int, default=20, help="İlgili koşul sınırı (1–100).",
    )
    vuln_match_products = vuln_actions.add_parser(
        "match-products",
        help="Bir yerel NVD CVE kaydını etkin doğrulanmış ürün envanteriyle karşılaştır.",
    )
    vuln_match_products.add_argument("cve_id", help="Örnek: CVE-2021-44228")
    vuln_match_products.add_argument(
        "--all", action="store_true", dest="include_unmatched",
        help="Eşleşmeyen ürünleri de göster.",
    )
    vuln_match_products.add_argument(
        "--limit", type=int, default=100, help="Ürün gösterim sınırı (1–500).",
    )
    vuln_match_products.add_argument(
        "--condition-limit", type=int, default=5,
        help="JSON'da ürün başına koşul sınırı (1–20).",
    )
    vuln_advisory_preview = vuln_actions.add_parser(
        "advisory-preview",
        help="Açıkça seçilen CVE için ücretsiz OSV duyuru/paket bağlamını önizle.",
    )
    vuln_advisory_preview.add_argument("cve_id")
    vuln_advisory_preview.add_argument(
        "--affected-limit", type=int, default=50,
        help="Gösterilecek paket/sürüm kaydı sınırı (1–200).",
    )
    vuln_advisory_preview.add_argument(
        "--reference-limit", type=int, default=50,
        help="Gösterilecek ADVISORY başvurusu sınırı (1–200).",
    )
    ubuntu_preview = vuln_actions.add_parser(
        "ubuntu-preview",
        help="Tek CVE için Canonical'ın resmî Ubuntu OSV paket/yayın bağlamını önizle.",
    )
    ubuntu_preview.add_argument("cve_id")
    ubuntu_preview.add_argument("--affected-limit", type=int, default=50)
    ubuntu_preview.add_argument("--reference-limit", type=int, default=50)
    ubuntu_match = vuln_actions.add_parser(
        "ubuntu-match",
        help="Açık Ubuntu yayın, kaynak paket ve sürümünü Canonical OSV sınırıyla karşılaştır.",
    )
    ubuntu_match.add_argument("cve_id", help="Örnek: CVE-2025-6491")
    ubuntu_match.add_argument(
        "--ecosystem", required=True,
        help="OSV kaydındaki tam Ubuntu yayını; örnek: Ubuntu:24.04:LTS.",
    )
    ubuntu_match.add_argument(
        "--source-package", required=True,
        help="Doğrulanmış Debian kaynak paket adı; örnek: php8.3.",
    )
    ubuntu_match.add_argument(
        "--version", required=True, dest="installed_version",
        help="Doğrulanmış kurulu Debian paket sürümü.",
    )
    ubuntu_match.add_argument(
        "--reference-limit", type=int, default=50,
        help="Gösterilecek Canonical duyurusu sınırı (1–200).",
    )
    ubuntu_inventory_match = vuln_actions.add_parser(
        "ubuntu-inventory-match",
        help="Doğrulanmış Ubuntu envanter kaydını Canonical OSV ile karşılaştır.",
    )
    ubuntu_inventory_match.add_argument(
        "package_id", help="./xti ubuntu-packages list çıktısındaki kimlik.",
    )
    ubuntu_inventory_match.add_argument("cve_id", help="Örnek: CVE-2025-6491")
    ubuntu_inventory_match.add_argument(
        "--reference-limit", type=int, default=50,
        help="Gösterilecek Canonical duyurusu sınırı (1–200).",
    )
    ubuntu_inventory_scan = vuln_actions.add_parser(
        "ubuntu-inventory-scan",
        help="Tek CVE'yi bütün etkin Ubuntu paket envanteriyle bir kaynak çağrısında karşılaştır.",
    )
    ubuntu_inventory_scan.add_argument("cve_id", help="Örnek: CVE-2025-6491")
    ubuntu_inventory_scan.add_argument(
        "--domain", help="Yalnız bu kayıtlı varlığın etkin Ubuntu paketleri.",
    )
    ubuntu_inventory_scan.add_argument(
        "--limit", type=int, default=50, help="Gösterilecek paket sınırı (1–500).",
    )
    ubuntu_inventory_scan.add_argument(
        "--reference-limit", type=int, default=50,
        help="Gösterilecek Canonical duyurusu sınırı (1–200).",
    )
    ubuntu_evidence_add = vuln_actions.add_parser(
        "ubuntu-evidence-add",
        help="Güncel Ubuntu paket/Canonical sonucunu maruziyete insan seçimiyle bağla.",
    )
    ubuntu_evidence_add.add_argument(
        "exposure_id", help="Mevcut insan maruziyet incelemesi kimliği.",
    )
    ubuntu_evidence_add.add_argument(
        "package_id", help="./xti ubuntu-packages list çıktısındaki kimlik.",
    )
    ubuntu_evidence_add.add_argument(
        "--summary", required=True, help="İnsan tarafından yazılan kanıt açıklaması.",
    )
    ubuntu_evidence_check = vuln_actions.add_parser(
        "ubuntu-evidence-check",
        help="Kayıtlı Ubuntu kanıtını güncel paket ve Canonical kaydıyla salt okunur karşılaştır.",
    )
    ubuntu_evidence_check.add_argument(
        "evidence_id", help="exposure-evidence-list çıktısındaki kanıt kimliği.",
    )
    ubuntu_evidence_plan = vuln_actions.add_parser(
        "ubuntu-evidence-plan",
        help="Etkin Ubuntu kanıtlarının yerel paket değişikliklerini ağsız planla.",
    )
    ubuntu_evidence_plan.add_argument(
        "--domain", help="Yalnız bu kayıtlı varlığın etkin Ubuntu kanıtları.",
    )
    ubuntu_evidence_plan.add_argument(
        "--limit", type=int, default=50, help="Gösterilecek kanıt sınırı (1–500).",
    )
    ubuntu_evidence_scan = vuln_actions.add_parser(
        "ubuntu-evidence-scan",
        help="Etkin Ubuntu kanıtlarından sınırlı bir grubu güncel Canonical kaydıyla kontrol et.",
    )
    ubuntu_evidence_scan.add_argument(
        "--domain", help="Yalnız bu kayıtlı varlığın etkin Ubuntu kanıtları.",
    )
    ubuntu_evidence_scan.add_argument(
        "--limit", type=int, default=10, help="Kontrol edilecek kanıt sınırı (1–20).",
    )
    vuln_advisory_evidence = vuln_actions.add_parser(
        "advisory-evidence-add",
        help="Seçilen güncel OSV HTTPS duyurusunu insan onayıyla kanıta bağla.",
    )
    vuln_advisory_evidence.add_argument(
        "exposure_id", help="Maruziyet inceleme kimliği.",
    )
    vuln_advisory_evidence.add_argument(
        "--type", required=True, dest="evidence_type",
        choices=("vendor_advisory", "distribution_advisory"),
        help="Duyurunun kullanıcı tarafından seçilen türü.",
    )
    vuln_advisory_evidence.add_argument(
        "--reference", required=True,
        help="Önizlemede görülen tam HTTPS ADVISORY başvurusu.",
    )
    vuln_advisory_evidence.add_argument(
        "--summary", required=True, help="İnsan tarafından yazılan kanıt açıklaması.",
    )
    vuln_vendor_preview = vuln_actions.add_parser(
        "vendor-preview",
        help="Seçilen CVE için doğrudan üreticinin VEX durumlarını önizle.",
    )
    vuln_vendor_preview.add_argument("cve_id", help="Örnek: CVE-2014-0160")
    vuln_vendor_preview.add_argument(
        "--provider", choices=("redhat", "suse"), default="redhat",
        help="Doğrudan kaynak sağlayıcısı: redhat veya suse.",
    )
    vuln_vendor_preview.add_argument(
        "--product-limit", type=int, default=5,
        help="Her durum için ürün/bileşen örneği sınırı (1–50).",
    )
    vuln_vendor_preview.add_argument(
        "--remediation-limit", type=int, default=10,
        help="Düzeltme başvurusu sınırı (1–100).",
    )
    vuln_vendor_match = vuln_actions.add_parser(
        "vendor-match",
        help="Kesin yerel Red Hat RPM kaydını doğrudan VEX ürün bağıyla karşılaştır.",
    )
    vuln_vendor_match.add_argument(
        "package_id", help="./xti packages list çıktısındaki kimlik.",
    )
    vuln_vendor_match.add_argument("cve_id", help="Örnek: CVE-2014-0160")
    vuln_vendor_match.add_argument(
        "--provider", choices=("redhat",), default="redhat",
        help="Doğrudan kaynak sağlayıcısı (şimdilik redhat).",
    )
    vuln_vendor_match.add_argument(
        "--match-limit", type=int, default=50,
        help="Gösterilecek kesin ürün bağı sınırı (1–100).",
    )
    vendor_evidence_add = vuln_actions.add_parser(
        "vendor-evidence-add",
        help="Seçilen güncel kesin RPM/VEX bağını insan onayıyla kalıcı kanıta ekle.",
    )
    vendor_evidence_add.add_argument("exposure_id", help="Maruziyet inceleme kimliği.")
    vendor_evidence_add.add_argument("package_id", help="Kesin RPM kanıtı kimliği.")
    vendor_evidence_add.add_argument(
        "--vex-product-id", required=True,
        help="vendor-match çıktısından seçilen tam VEX ürün bağı kimliği.",
    )
    vendor_evidence_add.add_argument(
        "--summary", required=True, help="İnsan tarafından yazılan kanıt açıklaması.",
    )
    vendor_evidence_list = vuln_actions.add_parser(
        "vendor-evidence-list", help="Bir maruziyetin kesin Red Hat paket kanıtlarını listele.",
    )
    vendor_evidence_list.add_argument("exposure_id")
    vendor_evidence_list.add_argument(
        "--all", action="store_true", dest="all_entries",
        help="Etkisizleştirilmiş kanıtları da göster.",
    )
    vendor_evidence_list.add_argument("--limit", type=int, default=50)
    vendor_evidence_show = vuln_actions.add_parser(
        "vendor-evidence-show", help="Kesin Red Hat paket kanıtını ve geçmişini göster.",
    )
    vendor_evidence_show.add_argument("evidence_id")
    vendor_evidence_show.add_argument("--event-limit", type=int, default=50)
    vendor_evidence_revoke = vuln_actions.add_parser(
        "vendor-evidence-revoke", help="Kesin üretici kanıtını geçmişi silmeden etkisizleştir.",
    )
    vendor_evidence_revoke.add_argument("evidence_id")
    vendor_evidence_revoke.add_argument("--reason", required=True)
    vendor_evidence_check = vuln_actions.add_parser(
        "vendor-evidence-check",
        help="Kayıtlı kesin Red Hat kanıtını güncel VEX ve RPM anlık görüntüsüyle karşılaştır.",
    )
    vendor_evidence_check.add_argument("evidence_id")
    remediation_plan = vuln_actions.add_parser(
        "remediation-plan",
        help="Maruziyet için kaynaklı, insan onaylı bir düzeltme planı oluştur.",
    )
    remediation_plan.add_argument("exposure_id")
    remediation_plan.add_argument("--recommendation", required=True, help="Uygulanacak düzeltme.")
    remediation_plan.add_argument(
        "--source-type", required=True,
        choices=("vendor_package_evidence", "exposure_evidence", "analyst_note"),
        help="Önerinin dayandığı yerel kaynak türü.",
    )
    remediation_plan.add_argument(
        "--source-reference", required=True,
        help="Seçilmiş kanıt kimliği veya yerel analist notu başvurusu.",
    )
    remediation_plan.add_argument("--reason", required=True, help="Planlama gerekçesi.")
    remediation_plan.add_argument("--recheck-days", type=int)
    remediation_implement = vuln_actions.add_parser(
        "remediation-implement", help="Planlanan düzeltmenin uygulandığını kanıtla kaydet.",
    )
    remediation_implement.add_argument("remediation_id")
    remediation_implement.add_argument("--reason", required=True)
    remediation_implement.add_argument("--evidence-reference", required=True)
    remediation_implement.add_argument(
        "--recheck-days", required=True, type=int,
        help="Uygulama sonrası kontrolün kaç gün sonra yapılacağı.",
    )
    remediation_recheck = vuln_actions.add_parser(
        "remediation-recheck", help="Uygulanmış düzeltmenin kontrol sonucunu kaydet.",
    )
    remediation_recheck.add_argument("remediation_id")
    remediation_recheck.add_argument(
        "--outcome", required=True,
        choices=("not_observed", "still_present", "inconclusive"),
    )
    remediation_recheck.add_argument("--reason", required=True)
    remediation_recheck.add_argument("--evidence-reference", required=True)
    remediation_recheck.add_argument(
        "--recheck-days", type=int,
        help="Risk sürüyor veya sonuçsuzsa zorunlu sonraki kontrol süresi.",
    )
    remediation_cancel = vuln_actions.add_parser(
        "remediation-cancel", help="Düzeltme planını geçmişi silmeden iptal et.",
    )
    remediation_cancel.add_argument("remediation_id")
    remediation_cancel.add_argument("--reason", required=True)
    remediation_list = vuln_actions.add_parser(
        "remediation-list", help="Düzeltme planlarını ve kontrolü gelenleri listele.",
    )
    remediation_list.add_argument("--exposure-id")
    remediation_list.add_argument("--state", choices=("planned", "implemented", "cancelled"))
    remediation_list.add_argument("--due-only", action="store_true")
    remediation_list.add_argument("--limit", type=int, default=50)
    remediation_show = vuln_actions.add_parser(
        "remediation-show", help="Düzeltme planını ve eklemeli kontrol geçmişini göster.",
    )
    remediation_show.add_argument("remediation_id")
    remediation_show.add_argument("--event-limit", type=int, default=50)
    vuln_exposure_open = vuln_actions.add_parser(
        "exposure-open",
        help="Bir ürün-CVE adayını insan incelemesine al ve kanıt özetlerini sabitle.",
    )
    vuln_exposure_open.add_argument("product_id", help="Doğrulanmış ürün kimliği.")
    vuln_exposure_open.add_argument("cve_id", help="Örnek: CVE-2021-44228")
    vuln_exposure_open.add_argument("--reason", required=True, help="İnceleme açma gerekçesi.")
    vuln_exposure_open.add_argument(
        "--recheck-days", type=int, help="Bu kadar gün sonra yeniden kontrol uyarısı ver (1–3650).",
    )
    vuln_exposure_review = vuln_actions.add_parser(
        "exposure-review", help="Maruziyet incelemesine insan kararı ve gerekçe kaydet.",
    )
    vuln_exposure_review.add_argument("exposure_id", help="Maruziyet inceleme kimliği.")
    vuln_exposure_review.add_argument(
        "--status", required=True,
        choices=("investigating", "affected", "not_affected", "fixed"),
        help="İnsan kararı.",
    )
    vuln_exposure_review.add_argument("--reason", required=True, help="Karar gerekçesi.")
    suppression = vuln_exposure_review.add_mutually_exclusive_group()
    suppression.add_argument(
        "--suppress", dest="suppressed", action="store_const", const=True, default=None,
        help="Kaydı varsayılan listeden gizle; ayrıntı ve geçmiş korunur.",
    )
    suppression.add_argument(
        "--unsuppress", dest="suppressed", action="store_const", const=False,
        help="Bastırılmış kaydı yeniden varsayılan listede göster.",
    )
    recheck = vuln_exposure_review.add_mutually_exclusive_group()
    recheck.add_argument(
        "--recheck-days", type=int, help="Bu kadar gün sonra yeniden kontrol uyarısı ver.",
    )
    recheck.add_argument(
        "--clear-recheck", action="store_true", help="Planlanmış yeniden kontrol tarihini kaldır.",
    )
    vuln_exposure_list = vuln_actions.add_parser(
        "exposure-list", help="Kalıcı ürün-CVE maruziyet incelemelerini listele.",
    )
    vuln_exposure_list.add_argument(
        "--status", choices=("investigating", "affected", "not_affected", "fixed"),
    )
    vuln_exposure_list.add_argument(
        "--include-suppressed", action="store_true", help="Bastırılmış kayıtları da göster.",
    )
    vuln_exposure_list.add_argument("--limit", type=int, default=50, help="Kayıt sınırı (1–500).")
    vuln_exposure_show = vuln_actions.add_parser(
        "exposure-show", help="Maruziyet kararını, güncelliğini ve geçmişini göster.",
    )
    vuln_exposure_show.add_argument("exposure_id")
    vuln_exposure_show.add_argument(
        "--event-limit", type=int, default=50, help="Geçmiş sınırı (1–100).",
    )
    vuln_exposure_suppress = vuln_actions.add_parser(
        "exposure-suppress",
        help="Açık maruziyeti belirli süreyle çalışma listesinden gizle.",
    )
    vuln_exposure_suppress.add_argument("exposure_id")
    vuln_exposure_suppress.add_argument(
        "--days", required=True, type=int, help="Bastırma süresi (1–3650 gün).",
    )
    vuln_exposure_suppress.add_argument(
        "--reason", required=True, help="Süreli bastırma gerekçesi.",
    )
    vuln_exposure_unsuppress = vuln_actions.add_parser(
        "exposure-unsuppress", help="Süreli bastırmayı vadesinden önce kaldır.",
    )
    vuln_exposure_unsuppress.add_argument("exposure_id")
    vuln_exposure_unsuppress.add_argument(
        "--reason", required=True, help="Bastırmayı kaldırma gerekçesi.",
    )
    vuln_exposure_suppression_show = vuln_actions.add_parser(
        "exposure-suppression-show",
        help="Süreli bastırma durumunu ve eklemeli geçmişini göster.",
    )
    vuln_exposure_suppression_show.add_argument("exposure_id")
    vuln_exposure_suppression_show.add_argument("--event-limit", type=int, default=50)
    vuln_exposure_queue = vuln_actions.add_parser(
        "exposure-queue",
        help="Açık maruziyet incelemelerini KEV, EPSS ve CVSS nedenleriyle sırala.",
    )
    vuln_exposure_queue.add_argument(
        "--min-epss", default="0.9", help="Yüksek EPSS öncelik eşiği, 0–1.",
    )
    vuln_exposure_queue.add_argument(
        "--include-closed", action="store_true",
        help="Etkilenmiyor ve düzeltildi kararlarını da göster.",
    )
    vuln_exposure_queue.add_argument(
        "--include-suppressed", action="store_true",
        help="Bastırılmış kayıtları da göster.",
    )
    vuln_exposure_queue.add_argument(
        "--evidence", choices=("all", "present", "missing"), default="all",
        help="Tümünü, etkin destek kanıtı olanı veya olmayanı göster.",
    )
    vuln_exposure_queue.add_argument(
        "--limit", type=int, default=50, help="Kayıt sınırı (1–500).",
    )
    vuln_exposure_queue.add_argument(
        "--surface-stale-hours", type=int, default=24,
        help="Web/servis kanıtını bu saatten sonra eski say (1–8760).",
    )
    reassessment_plan = vuln_actions.add_parser(
        "reassessment-plan",
        help="Değişen yerel ürün/NVD kanıtları nedeniyle yeniden incelenecek kayıtları planla.",
    )
    reassessment_plan.add_argument(
        "--include-closed", action="store_true",
        help="Etkilenmiyor ve düzeltildi kararlarını da plana dahil et.",
    )
    reassessment_plan.add_argument(
        "--include-suppressed", action="store_true",
        help="Süreli veya kalıcı gizlenmiş kayıtları da plana dahil et.",
    )
    reassessment_plan.add_argument(
        "--limit", type=int, default=50, help="Gösterilecek aday sınırı (1–500).",
    )
    reassessment_run = vuln_actions.add_parser(
        "reassessment-run",
        help="Planı güncel yerel koşullarla değerlendir ve değişmez denetim kaydı oluştur.",
    )
    reassessment_run.add_argument("--include-closed", action="store_true")
    reassessment_run.add_argument("--include-suppressed", action="store_true")
    reassessment_run.add_argument(
        "--limit", type=int, default=50, help="Değerlendirilecek aday sınırı (1–500).",
    )
    reassessment_runs = vuln_actions.add_parser(
        "reassessment-runs", help="Kayıtlı toplu yeniden değerlendirme çalışmalarını listele.",
    )
    reassessment_runs.add_argument(
        "--limit", type=int, default=20, help="Çalışma sınırı (1–100).",
    )
    reassessment_show = vuln_actions.add_parser(
        "reassessment-show", help="Bir toplu yeniden değerlendirme kaydını göster.",
    )
    reassessment_show.add_argument("run_id", help="Yeniden değerlendirme çalışma kimliği.")
    change_notify = vuln_actions.add_parser(
        "change-notify",
        help="Değişmiş ürün/NVD kanıtlarını yerel kutuya tekrarsız bildirim olarak ekle.",
    )
    change_notify.add_argument(
        "--include-closed", action="store_true",
        help="Etkilenmiyor ve düzeltildi kararlarını da bildir.",
    )
    change_notify.add_argument(
        "--include-suppressed", action="store_true",
        help="Süreli veya kalıcı gizlenmiş kayıtları da bildir.",
    )
    change_notify.add_argument(
        "--limit", type=int, default=50, help="Bir çalışmada eklenecek yeni bildirim sınırı (1–100).",
    )
    evidence_add = vuln_actions.add_parser(
        "exposure-evidence-add", help="Maruziyet incelemesine kaynaklı destek kanıtı bağla.",
    )
    evidence_add.add_argument("exposure_id")
    evidence_add.add_argument(
        "--type", required=True, dest="evidence_type",
        choices=("vendor_advisory", "distribution_advisory", "package_inventory", "analyst_note"),
    )
    evidence_add.add_argument(
        "--reference", required=True,
        help="Duyuru için HTTPS adresi; paket/not için yerel başvuru kimliği.",
    )
    evidence_add.add_argument("--summary", required=True, help="Kanıtın ne söylediği.")
    evidence_list = vuln_actions.add_parser(
        "exposure-evidence-list", help="Bir maruziyet incelemesinin destek kanıtlarını listele.",
    )
    evidence_list.add_argument("exposure_id")
    evidence_list.add_argument(
        "--all", action="store_true", dest="all_entries",
        help="Etkisizleştirilmiş kanıtları da göster.",
    )
    evidence_list.add_argument("--limit", type=int, default=50, help="Kayıt sınırı (1–500).")
    evidence_show = vuln_actions.add_parser(
        "exposure-evidence-show", help="Destek kanıtını ve geçmişini göster.",
    )
    evidence_show.add_argument("evidence_id")
    evidence_show.add_argument("--event-limit", type=int, default=50)
    evidence_revoke = vuln_actions.add_parser(
        "exposure-evidence-revoke", help="Destek kanıtını geçmişini silmeden etkisizleştir.",
    )
    evidence_revoke.add_argument("evidence_id")
    evidence_revoke.add_argument("--reason", required=True)
    status = commands.add_parser("status", help="Arama güncelliği, bekleyen işler ve bildirimleri birlikte göster.")
    status.add_argument("domain", nargs="?", help="Yalnız bu kayıtlı adresin arama geçmişini göster.")
    status.add_argument("--stale-after-hours", type=int, default=24,
                        help="Tam aramayı eski sayma eşiği (1–8760 saat); arama zamanlaması değildir.")
    status.add_argument("--limit", type=int, default=20, help="Gösterilecek adres sayısı (1–100).")
    monitor = commands.add_parser("monitor", help="Sınırlı izleme denemesi başlat ve kayıtlı sonuçlarını gör.")
    monitor_actions = monitor.add_subparsers(dest="monitor_action", required=True)
    monitor_start = monitor_actions.add_parser("start", help="İnternet kaynaklarında süre ve tur sınırıyla izle.")
    monitor_start.add_argument("domain", nargs="?", help="İzlenecek adres; verilmezse kayıtlı en fazla beş adres.")
    monitor_start.add_argument("--source", choices=["all", *SOURCE_LABELS], default="all")
    monitor_start.add_argument("--cycles", type=int, default=3, help="En fazla tur (1–1000; varsayılan 3).")
    monitor_start.add_argument("--interval", type=int, default=3600, help="Turlar arasında saniye (300–86400).")
    monitor_start.add_argument("--duration", type=int, default=86400,
                               help="Yeni çalışma başlatma süresi, saniye (1–604800); başlamış kaynak araması tamamlanabilir.")
    monitor_start.add_argument(
        "--typos", action="store_true",
        help="Sınırlı yazım ve Punycode benzer-harf varyantlarını da ara.",
    )
    monitor_list = monitor_actions.add_parser("list", help="Son izleme denemelerini göster; ağ isteği yapmaz.")
    monitor_list.add_argument("--limit", type=int, default=20, help="En fazla deneme (1–100).")
    monitor_show = monitor_actions.add_parser("show", help="Bir denemenin kaynak sonuçlarını tekrar aç.")
    monitor_show.add_argument("run_id")
    monitor_show.add_argument("--limit", type=int, default=20, help="Gösterilecek son kaynak çalışması (1–2000).")
    monitor_actions.add_parser("recover", help="Kapanmış süreçten kalan denemeyi güvenle kapat; aramayı sürdürmez.")
    commands.add_parser("migrate", help="Eski kayıt düzenini yedek alarak güncelle.")
    assets = commands.add_parser("assets", help="İzlenecek internet adreslerini yönet.")
    actions = assets.add_subparsers(dest="asset_action", required=True)
    add = actions.add_parser("add", help="Bir internet adresi ekle.")
    add.add_argument("domain", help="Örnek: example.com")
    actions.add_parser("list", help="Kayıtlı adresleri listele.")
    criticality_set = actions.add_parser(
        "criticality-set", help="Kayıtlı varlığın insan onaylı iş önemini tanımla.",
    )
    criticality_set.add_argument("domain")
    criticality_set.add_argument(
        "--level", choices=("low", "medium", "high", "critical"), required=True,
    )
    criticality_set.add_argument("--reason", required=True)
    criticality_clear = actions.add_parser(
        "criticality-clear", help="İş önemi kaydını geçmişini silmeden kaldır.",
    )
    criticality_clear.add_argument("domain")
    criticality_clear.add_argument("--reason", required=True)
    criticality_show = actions.add_parser(
        "criticality-show", help="İş önemini ve karar geçmişini göster.",
    )
    criticality_show.add_argument("domain")
    criticality_show.add_argument("--event-limit", type=int, default=50)
    cases = commands.add_parser(
        "cases", help="Kanıtları insan yönetimli yerel vakalarda birleştir.",
    )
    case_actions = cases.add_subparsers(dest="case_action", required=True)
    case_create = case_actions.add_parser(
        "create", help="Açık bir vaka oluştur; otomatik tehdit hükmü üretme.",
    )
    case_create.add_argument("title", help="Vakanın kısa başlığı.")
    case_create.add_argument("--summary", required=True, help="Vakanın kapsam ve amacı.")
    case_create.add_argument(
        "--priority", choices=("low", "medium", "high", "critical"),
        default="medium",
    )
    case_create.add_argument("--reason", required=True, help="Vaka açma gerekçesi.")
    case_list = case_actions.add_parser("list", help="Vakaları ağsız listele.")
    case_list.add_argument(
        "--status",
        choices=("all", "open", "investigating", "monitoring", "resolved", "closed"),
        default="all",
    )
    case_list.add_argument(
        "--priority", choices=("all", "low", "medium", "high", "critical"),
        default="all",
    )
    case_list.add_argument("--limit", type=int, default=100)
    case_show = case_actions.add_parser(
        "show", help="Vakayı kanıt, görev ve tek zaman çizelgesiyle göster.",
    )
    case_show.add_argument("case_id")
    case_show.add_argument("--evidence-limit", type=int, default=100)
    case_show.add_argument("--task-limit", type=int, default=100)
    case_show.add_argument("--activity-limit", type=int, default=200)
    case_update = case_actions.add_parser(
        "update", help="Vaka başlığı, özeti veya önceliğini gerekçeyle güncelle.",
    )
    case_update.add_argument("case_id")
    case_update.add_argument("--title")
    case_update.add_argument("--summary")
    case_update.add_argument(
        "--priority", choices=("low", "medium", "high", "critical"),
    )
    case_update.add_argument("--reason", required=True)
    case_status = case_actions.add_parser(
        "status", help="Vaka durumunu gerekçeyle değiştir, kapatma ve açmayı kaydet.",
    )
    case_status.add_argument("case_id")
    case_status.add_argument(
        "status", choices=("open", "investigating", "monitoring", "resolved", "closed"),
    )
    case_status.add_argument("--reason", required=True)
    case_status.add_argument(
        "--resolution", help="resolved veya closed için zorunlu sonuç açıklaması.",
    )
    case_note = case_actions.add_parser(
        "note-add", help="Vakaya değişmez ve zaman çizelgeli analist notu ekle.",
    )
    case_note.add_argument("case_id")
    case_note.add_argument("body")
    case_note.add_argument(
        "--kind", choices=("observation", "action", "decision", "closure"),
        default="observation",
    )
    case_evidence_add = case_actions.add_parser(
        "evidence-add", help="Mevcut yerel kanıtın doğrulanmış anlık görüntüsünü vakaya bağla.",
    )
    case_evidence_add.add_argument("case_id")
    case_evidence_add.add_argument(
        "--type", required=True,
        choices=(
            "finding", "social_profile", "ransomware_threatcluster",
            "ransomware_ransomlook", "supplier", "public_notice", "public_notice_watch",
        ),
    )
    case_evidence_add.add_argument("--evidence-id", required=True)
    case_evidence_add.add_argument("--reason", required=True)
    case_evidence_show = case_actions.add_parser(
        "evidence-show", help="Vakadaki tek kanıtın donmuş tarihî kaydını göster; ağa çıkmaz.",
    )
    case_evidence_show.add_argument("case_id")
    case_evidence_show.add_argument("evidence_link_id")
    case_evidence_remove = case_actions.add_parser(
        "evidence-remove", help="Kanıtı silmeden etkin vaka bağından çıkar.",
    )
    case_evidence_remove.add_argument("case_id")
    case_evidence_remove.add_argument("evidence_link_id")
    case_evidence_remove.add_argument("--reason", required=True)
    case_task_add = case_actions.add_parser(
        "task-add", help="Vakaya takip görevi ekle.",
    )
    case_task_add.add_argument("case_id")
    case_task_add.add_argument("title")
    case_task_add.add_argument(
        "--due-at", help="Saat dilimli ISO-8601 bitiş zamanı; ör. 2026-11-02T12:00:00+03:00.",
    )
    case_task_add.add_argument("--reason", required=True)
    case_task_update = case_actions.add_parser(
        "task-update", help="Vaka görevini tamamla, iptal et veya yeniden aç.",
    )
    case_task_update.add_argument("case_id")
    case_task_update.add_argument("task_id")
    case_task_update.add_argument("--status", choices=("open", "done", "cancelled"), required=True)
    case_task_update.add_argument("--reason", required=True)
    case_report = case_actions.add_parser(
        "report", help="Vakanın kaynak sınırlı yönetim özetini ağsız üret.",
    )
    case_report.add_argument("case_id")
    case_report.add_argument("--evidence-limit", type=int, default=500)
    case_report.add_argument("--task-limit", type=int, default=500)
    case_report.add_argument("--activity-limit", type=int, default=1000)
    suppliers = commands.add_parser(
        "suppliers", help="İnsan onaylı yerel tedarikçi envanterini yönet.",
    )
    supplier_actions = suppliers.add_subparsers(dest="supplier_action", required=True)
    register_supplier_watch_parser(supplier_actions)
    supplier_add = supplier_actions.add_parser(
        "add", help="Bir kuruluşu açıkça tedarikçi olarak kaydet.",
    )
    supplier_add.add_argument("name", help="Tedarikçinin görünen kuruluş adı.")
    supplier_add.add_argument("--domain", required=True, help="Kuruluşun ana domaini.")
    supplier_add.add_argument(
        "--relationship", required=True,
        choices=(
            "software", "cloud", "payment", "communications",
            "professional_service", "other",
        ),
        help="Tedarikçiden aldığın hizmetin türü.",
    )
    supplier_add.add_argument(
        "--criticality", required=True,
        choices=("low", "medium", "high", "critical"),
        help="Bu hizmetin senin işin için önemi.",
    )
    supplier_add.add_argument("--reason", required=True, help="İlişkinin gerekçesi.")
    supplier_list = supplier_actions.add_parser(
        "list", help="Tedarikçileri ağsız listele.",
    )
    supplier_list.add_argument(
        "--all", action="store_true", dest="all_entries",
        help="Pasife alınmış kayıtları da göster.",
    )
    supplier_list.add_argument("--limit", type=int, default=100)
    supplier_show = supplier_actions.add_parser(
        "show", help="Tedarikçi kaydını ve değişiklik geçmişini göster.",
    )
    supplier_show.add_argument("supplier_id")
    supplier_show.add_argument("--event-limit", type=int, default=50)
    supplier_update = supplier_actions.add_parser(
        "update", help="Tedarikçi adı, ilişki türü veya iş önemini güncelle.",
    )
    supplier_update.add_argument("supplier_id")
    supplier_update.add_argument("--name")
    supplier_update.add_argument(
        "--relationship",
        choices=(
            "software", "cloud", "payment", "communications",
            "professional_service", "other",
        ),
    )
    supplier_update.add_argument(
        "--criticality", choices=("low", "medium", "high", "critical"),
    )
    supplier_update.add_argument("--reason", required=True)
    supplier_revoke = supplier_actions.add_parser(
        "revoke", help="Tedarikçiyi geçmişini silmeden pasife al.",
    )
    supplier_revoke.add_argument("supplier_id")
    supplier_revoke.add_argument("--reason", required=True)
    supplier_candidate_refresh = supplier_actions.add_parser(
        "candidate-refresh",
        help="Kayıtlı CNAME kanıtlarından dış hizmet adaylarını yerelde yenile.",
    )
    supplier_candidate_refresh.add_argument(
        "--limit", type=int, default=1000,
        help="İncelenecek en fazla son CNAME kanıtı (1–1000).",
    )
    supplier_candidate_list = supplier_actions.add_parser(
        "candidate-list", help="Tedarikçi adaylarını ağsız listele.",
    )
    supplier_candidate_list.add_argument(
        "--status", choices=("pending", "accepted", "uncertain", "rejected", "all"),
        default="pending",
    )
    supplier_candidate_list.add_argument(
        "--include-historical", action="store_true",
        help="Artık son CNAME kanıtında görünmeyen adayları da göster.",
    )
    supplier_candidate_list.add_argument("--limit", type=int, default=100)
    supplier_candidate_show = supplier_actions.add_parser(
        "candidate-show", help="Adayı, CNAME kanıtını ve karar geçmişini göster.",
    )
    supplier_candidate_show.add_argument("candidate_id")
    supplier_candidate_show.add_argument("--evidence-limit", type=int, default=20)
    supplier_candidate_show.add_argument("--resolution-limit", type=int, default=20)
    supplier_candidate_review = supplier_actions.add_parser(
        "candidate-review", help="Aday için geri alınabilir insan kararı kaydet.",
    )
    supplier_candidate_review.add_argument("candidate_id")
    supplier_candidate_review.add_argument(
        "--decision", choices=("pending", "accepted", "uncertain", "rejected"),
        required=True,
    )
    supplier_candidate_review.add_argument(
        "--supplier", help="Yalnız accepted kararında etkin tedarikçi kimliği.",
    )
    supplier_candidate_review.add_argument("--reason", required=True)
    supplier_event_list = supplier_actions.add_parser(
        "event-list",
        help="Tedarikçilerle eşleşen kayıtlı kaynak iddialarını ağsız göster.",
    )
    supplier_event_list.add_argument(
        "--supplier", help="Yalnız bu etkin tedarikçinin kimliği.",
    )
    supplier_event_list.add_argument(
        "--source", choices=("all", "threatcluster", "ransomlook"), default="all",
        help="Yerel iddia kaynağı filtresi.",
    )
    supplier_event_list.add_argument("--limit", type=int, default=100)
    supplier_event_show = supplier_actions.add_parser(
        "event-show", help="Kaynak iddiasını ve eşleşme dayanaklarını göster.",
    )
    supplier_event_show.add_argument("event_id")
    supplier_risk_list = supplier_actions.add_parser(
        "risk-list",
        help="Açıklanabilir tedarikçi inceleme kartlarını ağsız göster.",
    )
    supplier_risk_list.add_argument("--limit", type=int, default=100)
    supplier_risk_show = supplier_actions.add_parser(
        "risk-show",
        help="Bir tedarikçinin kanıt, eksik veri ve sonraki adım kartını göster.",
    )
    supplier_risk_show.add_argument("supplier_id")
    products = commands.add_parser(
        "products", help="Uyumluluk için korunan eski ürün kayıtlarını yönet; aktif plan dışıdır.",
    )
    product_actions = products.add_subparsers(dest="product_action", required=True)
    product_add = product_actions.add_parser(
        "add", help="Bir varlığa açık üretici, ürün ve sürüm kanıtı ekle.",
    )
    product_add.add_argument("domain", help="Önce assets add ile kaydedilmiş alan adı.")
    product_add.add_argument(
        "--part", choices=("a", "o", "h"), required=True,
        help="CPE türü: a uygulama, o işletim sistemi, h donanım.",
    )
    product_add.add_argument("--vendor", required=True, help="Üretici CPE adı; örnek: apache.")
    product_add.add_argument("--product", required=True, help="Ürün CPE adı; örnek: http_server.")
    product_add.add_argument("--version", required=True, help="Doğrulanmış açık sürüm; örnek: 2.4.58.")
    product_add.add_argument(
        "--evidence", required=True, help="Sürümün nasıl doğrulandığını açıklayan kanıt.",
    )
    product_list = product_actions.add_parser("list", help="Doğrulanmış ürün kayıtlarını listele.")
    product_list.add_argument("domain", nargs="?", help="Yalnız bu kayıtlı varlığın ürünleri.")
    product_list.add_argument(
        "--all", action="store_true", dest="all_entries",
        help="Kaldırılmış ürün kayıtlarını da göster.",
    )
    product_list.add_argument("--limit", type=int, default=50, help="Kayıt sınırı (1–500).")
    product_show = product_actions.add_parser("show", help="Ürün kanıtını ve geçmişini göster.")
    product_show.add_argument("product_id")
    product_show.add_argument(
        "--event-limit", type=int, default=50, help="Geçmiş sınırı (1–100).",
    )
    product_revoke = product_actions.add_parser(
        "revoke", help="Ürün kanıtını geçmişini silmeden etkisizleştir.",
    )
    product_revoke.add_argument("product_id")
    product_revoke.add_argument("--reason", required=True, help="Kaldırma gerekçesi.")
    ioc = commands.add_parser(
        "ioc", help="Domain, IP, URL ve hash göstergelerini kaynaklarıyla yönet.",
    )
    ioc_actions = ioc.add_subparsers(dest="ioc_action", required=True)
    from xti.interfaces.ioc_lifecycle import register_ioc_lifecycle_parser
    register_ioc_lifecycle_parser(ioc_actions)
    from xti.interfaces.evidence import register_comparison_parser
    register_comparison_parser(ioc_actions)
    ioc_add = ioc_actions.add_parser(
        "add", help="Kanonik bir IOC'ye bağımsız kaynak iddiası ekle veya gözlemi yenile.",
    )
    ioc_add.add_argument(
        "indicator_type", choices=("domain", "ipv4", "ipv6", "url", "md5", "sha1", "sha256"),
        help="Gösterge türü.",
    )
    ioc_add.add_argument("value", help="Domain, IP, tam HTTP(S) URL veya hash değeri.")
    ioc_add.add_argument(
        "--source", required=True, dest="source_name",
        help="Kısa kaynak adı; örnek: manual, abusech veya analyst-note.",
    )
    ioc_add.add_argument(
        "--reference", required=True, dest="source_reference",
        help="Kaynak URL'si, bülten kimliği veya yerel kanıt başvurusu.",
    )
    ioc_add.add_argument(
        "--confidence", required=True, type=int, help="Kaynak güveni (0–100).",
    )
    ioc_add.add_argument(
        "--description", required=True, help="Kaynağın gösterge hakkında ne söylediği.",
    )
    ioc_add.add_argument(
        "--valid-from", help="İsteğe bağlı, saat dilimli geçerlilik başlangıcı.",
    )
    ioc_add.add_argument(
        "--valid-until", help="İsteğe bağlı, saat dilimli kesin geçerlilik sonu.",
    )
    ioc_add.add_argument(
        "--observed-at", help="İsteğe bağlı, saat dilimli kaynak gözlem zamanı.",
    )
    ioc_list = ioc_actions.add_parser(
        "list", help="Yerel IOC kataloğunu internete çıkmadan listele.",
    )
    ioc_list.add_argument(
        "--type", dest="indicator_type",
        choices=("domain", "ipv4", "ipv6", "url", "md5", "sha1", "sha256"),
        help="Yalnız seçilen gösterge türü.",
    )
    ioc_list.add_argument(
        "--all", action="store_true", dest="all_entries",
        help="Geçerliliği bitmiş veya bütün kaynakları geri çekilmiş kayıtları da göster.",
    )
    ioc_list.add_argument("--limit", type=int, default=50, help="Kayıt sınırı (1–500).")
    ioc_show = ioc_actions.add_parser(
        "show", help="IOC'yi, kaynak iddialarını ve değişiklik geçmişini göster.",
    )
    ioc_show.add_argument("indicator_id", help="IOC liste çıktısındaki ana kayıt kimliği.")
    ioc_show.add_argument("--assertion-limit", type=int, default=50)
    ioc_show.add_argument("--event-limit", type=int, default=100)
    ioc_lookup = ioc_actions.add_parser(
        "lookup", help="Tür ve değeri kanonikleştirerek yerel IOC kaydını ara.",
    )
    ioc_lookup.add_argument(
        "indicator_type", choices=("domain", "ipv4", "ipv6", "url", "md5", "sha1", "sha256"),
    )
    ioc_lookup.add_argument("value")
    ioc_lookup.add_argument("--assertion-limit", type=int, default=50)
    ioc_lookup.add_argument("--event-limit", type=int, default=100)
    ioc_revoke = ioc_actions.add_parser(
        "revoke", help="Tek bir kaynak iddiasını geçmişi silmeden geri çek.",
    )
    ioc_revoke.add_argument(
        "assertion_id", help="IOC ayrıntısındaki kaynak iddiası kimliği.",
    )
    ioc_revoke.add_argument("--reason", required=True, help="Geri çekme gerekçesi.")
    ioc_sync = ioc_actions.add_parser(
        "sync", help="Ücretsiz bir IOC beslemesinin tam listesini güvenle güncelle.",
    )
    ioc_sync.add_argument(
        "--source", choices=("feodo", "certpl"), required=True,
        help="Anahtarsız Feodo C2 veya CERT Polska son-ay domain listesi.",
    )
    ioc_status = ioc_actions.add_parser(
        "status", help="IOC beslemesi sağlığını ve son çalışma geçmişini göster.",
    )
    ioc_status.add_argument(
        "--source", choices=("feodo", "certpl"), required=True,
    )
    ioc_status.add_argument("--limit", type=int, default=10, help="Çalışma sınırı (1–100).")
    cti = commands.add_parser(
        "cti", help="Aktör, kampanya, malware, rapor ve kaynaklı ilişkileri yönet.",
    )
    cti_actions = cti.add_subparsers(dest="cti_action", required=True)
    register_attack_catalog_parsers(cti_actions)
    register_cti_context_parser(cti_actions)
    cti_search = cti_actions.add_parser(
        "search", help="Yerel CTI varlık ve IOC kayıtlarında ağsız arama yap.",
    )
    cti_search.add_argument("query", help="Ad, alternatif ad veya IOC değeri parçası.")
    cti_search.add_argument(
        "--kind", choices=("all", "entity", "indicator"), default="all",
        help="Aranacak kayıt ailesi.",
    )
    cti_search.add_argument(
        "--entity-type", choices=("threat-actor", "campaign", "malware", "report"),
    )
    cti_search.add_argument(
        "--indicator-type", choices=("domain", "ipv4", "ipv6", "url", "md5", "sha1", "sha256"),
    )
    cti_search.add_argument(
        "--all", action="store_true", dest="all_entries",
        help="Geri çekilmiş veya süresi dolmuş kaynak geçmişini de ara.",
    )
    cti_search.add_argument("--limit", type=int, default=50, help="Sonuç sınırı (1–500).")
    cti_stix_export = cti_actions.add_parser(
        "stix-export",
        help="Güncel yerel IOC kaynak iddialarını STIX 2.1 JSON paketine çıkar.",
    )
    cti_stix_export.add_argument(
        "destination", help="Var olmayan hedef JSON dosyası.",
    )
    cti_stix_export.add_argument(
        "--indicator-type",
        choices=("domain", "ipv4", "ipv6", "url", "md5", "sha1", "sha256"),
        help="Yalnız seçilen IOC türünü dışa aktar.",
    )
    cti_actions.add_parser(
        "attack-sync",
        help=(
            "Sabit MITRE ATT&CK Enterprise sürümündeki etkin grup, kampanya, "
            "malware, teknik/taktik kataloğu ve kaynaklı ilişkileri atomik yenile."
        ),
    )
    cti_watch_add = cti_actions.add_parser(
        "watch-add", help="Yerel bir CTI aramasını daha sonra karşılaştırmak için kaydet.",
    )
    cti_watch_add.add_argument("name", help="Kayıtlı aramanın benzersiz görünen adı.")
    cti_watch_add.add_argument("query", help="Ad, alternatif ad veya IOC değeri parçası.")
    cti_watch_add.add_argument(
        "--kind", choices=("all", "entity", "indicator"), default="all",
    )
    cti_watch_add.add_argument(
        "--entity-type", choices=("threat-actor", "campaign", "malware", "report"),
    )
    cti_watch_add.add_argument(
        "--indicator-type",
        choices=("domain", "ipv4", "ipv6", "url", "md5", "sha1", "sha256"),
    )
    cti_watch_add.add_argument(
        "--all", action="store_true", dest="all_entries",
        help="Geri çekilmiş veya süresi dolmuş kaynak geçmişini de ara.",
    )
    cti_watch_list = cti_actions.add_parser(
        "watch-list", help="Kayıtlı CTI aramalarını ve son çalışma özetini göster.",
    )
    cti_watch_list.add_argument("--all", action="store_true", dest="all_entries")
    cti_watch_list.add_argument("--limit", type=int, default=50)
    cti_watch_show = cti_actions.add_parser(
        "watch-show", help="Kayıtlı CTI aramasını, tanım ve çalışma geçmişiyle göster.",
    )
    cti_watch_show.add_argument("saved_search_id")
    cti_watch_show.add_argument("--event-limit", type=int, default=50)
    cti_watch_show.add_argument("--run-limit", type=int, default=20)
    cti_watch_run = cti_actions.add_parser(
        "watch-run", help="Kayıtlı aramayı çalıştır ve önceki tam sonuçla farkını kaydet.",
    )
    cti_watch_run.add_argument("saved_search_id")
    cti_watch_run.add_argument("--item-limit", type=int, default=100)
    cti_watch_run_all = cti_actions.add_parser(
        "watch-run-all", help="Etkin kayıtlı CTI aramalarının tamamını bir kez çalıştır.",
    )
    cti_watch_run_all.add_argument("--search-limit", type=int, default=50)
    cti_watch_run_all.add_argument("--item-limit", type=int, default=100)
    cti_watch_run_show = cti_actions.add_parser(
        "watch-run-show", help="Kaydedilmiş tek bir CTI arama çalışmasını göster.",
    )
    cti_watch_run_show.add_argument("run_id")
    cti_watch_run_show.add_argument("--item-limit", type=int, default=100)
    cti_watch_monitor = cti_actions.add_parser(
        "watch-monitor",
        help="Kayıtlı CTI aramasını terminal açıkken sınırlı aralıklarla tekrarla.",
    )
    cti_watch_monitor.add_argument("saved_search_id")
    cti_watch_monitor.add_argument("--cycles", type=int, default=3)
    cti_watch_monitor.add_argument("--interval", type=int, default=3600)
    cti_watch_monitor.add_argument("--duration", type=int, default=86400)
    cti_watch_monitor.add_argument("--item-limit", type=int, default=100)
    cti_watch_tag_add = cti_actions.add_parser(
        "watch-tag-add", help="Kayıtlı CTI aramasına geçmişi korunan etiket ekle.",
    )
    cti_watch_tag_add.add_argument("saved_search_id")
    cti_watch_tag_add.add_argument("tag")
    cti_watch_tag_remove = cti_actions.add_parser(
        "watch-tag-remove", help="Kayıtlı CTI aramasından etiketi geçmişi silmeden kaldır.",
    )
    cti_watch_tag_remove.add_argument("saved_search_id")
    cti_watch_tag_remove.add_argument("tag")
    cti_watch_note_add = cti_actions.add_parser(
        "watch-note-add", help="Kayıtlı CTI aramasına eklemeli analist notu yaz.",
    )
    cti_watch_note_add.add_argument("saved_search_id")
    cti_watch_note_add.add_argument("--text", required=True)
    cti_watch_note_add.add_argument(
        "--kind", choices=("observation", "hypothesis", "conclusion", "follow-up"),
        default="observation",
    )
    cti_watch_note_add.add_argument("--run-id")
    cti_watch_journal = cti_actions.add_parser(
        "watch-journal", help="Kayıtlı CTI aramasının etiket ve analist notlarını göster.",
    )
    cti_watch_journal.add_argument("saved_search_id")
    cti_watch_journal.add_argument("--note-limit", type=int, default=50)
    cti_watch_journal.add_argument("--event-limit", type=int, default=100)
    cti_watch_revoke = cti_actions.add_parser(
        "watch-revoke", help="Kayıtlı CTI aramasını gerekçesiyle geri çek.",
    )
    cti_watch_revoke.add_argument("saved_search_id")
    cti_watch_revoke.add_argument("--reason", required=True)
    cti_entity_add = cti_actions.add_parser(
        "entity-add", help="Kaynaklı bir CTI varlık iddiası ekle veya güncelle.",
    )
    cti_entity_add.add_argument(
        "entity_type", choices=("threat-actor", "campaign", "malware", "report"),
    )
    cti_entity_add.add_argument("name")
    cti_entity_add.add_argument("--alias", action="append", default=[])
    cti_entity_add.add_argument("--source", required=True, dest="source_name")
    cti_entity_add.add_argument("--reference", required=True, dest="source_reference")
    cti_entity_add.add_argument("--confidence", required=True, type=int)
    cti_entity_add.add_argument("--description", required=True)
    cti_entity_add.add_argument("--observed-at")
    cti_entity_list = cti_actions.add_parser(
        "entity-list", help="Yerel CTI varlıklarını internete çıkmadan listele.",
    )
    cti_entity_list.add_argument(
        "--type", dest="entity_type",
        choices=("threat-actor", "campaign", "malware", "report"),
    )
    cti_entity_list.add_argument("--all", action="store_true", dest="all_entries")
    cti_entity_list.add_argument("--limit", type=int, default=50)
    cti_entity_show = cti_actions.add_parser("entity-show", help="CTI varlığını ve geçmişini göster.")
    cti_entity_show.add_argument("entity_id")
    cti_entity_show.add_argument("--assertion-limit", type=int, default=50)
    cti_entity_show.add_argument("--event-limit", type=int, default=100)
    cti_entity_lookup = cti_actions.add_parser("entity-lookup", help="Tür ve adla CTI varlığı ara.")
    cti_entity_lookup.add_argument(
        "entity_type", choices=("threat-actor", "campaign", "malware", "report"),
    )
    cti_entity_lookup.add_argument("name")
    cti_entity_lookup.add_argument("--assertion-limit", type=int, default=50)
    cti_entity_lookup.add_argument("--event-limit", type=int, default=100)
    cti_entity_revoke = cti_actions.add_parser(
        "entity-revoke", help="Tek bir varlık kaynak iddiasını geri çek.",
    )
    cti_entity_revoke.add_argument("assertion_id")
    cti_entity_revoke.add_argument("--reason", required=True)
    cti_relation_add = cti_actions.add_parser(
        "relation-add", help="Bir CTI varlığından varlık veya IOC'ye kaynaklı ilişki ekle.",
    )
    cti_relation_add.add_argument("source_entity_id")
    cti_relation_add.add_argument(
        "relationship_type", choices=(
            "attributed-to", "uses", "targets", "delivers", "communicates-with",
            "indicates", "related-to", "reports-on",
        ),
    )
    target = cti_relation_add.add_mutually_exclusive_group(required=True)
    target.add_argument("--to-entity", dest="target_entity_id")
    target.add_argument("--to-ioc", dest="target_indicator_id")
    cti_relation_add.add_argument("--source", required=True, dest="source_name")
    cti_relation_add.add_argument("--reference", required=True, dest="source_reference")
    cti_relation_add.add_argument("--confidence", required=True, type=int)
    cti_relation_add.add_argument("--description", required=True)
    cti_relation_add.add_argument("--observed-at")
    cti_relation_list = cti_actions.add_parser(
        "relation-list", help="Kaynaklı CTI ilişkilerini internete çıkmadan listele.",
    )
    cti_relation_list.add_argument("--entity", dest="entity_id")
    cti_relation_list.add_argument("--all", action="store_true", dest="all_entries")
    cti_relation_list.add_argument("--limit", type=int, default=50)
    cti_relation_show = cti_actions.add_parser(
        "relation-show", help="CTI ilişkisini ve kaynak geçmişini göster.",
    )
    cti_relation_show.add_argument("relationship_id")
    cti_relation_show.add_argument("--assertion-limit", type=int, default=50)
    cti_relation_show.add_argument("--event-limit", type=int, default=100)
    cti_relation_revoke = cti_actions.add_parser(
        "relation-revoke", help="Tek bir ilişki kaynak iddiasını geri çek.",
    )
    cti_relation_revoke.add_argument("assertion_id")
    cti_relation_revoke.add_argument("--reason", required=True)
    packages = commands.add_parser(
        "packages", help="Uyumluluk için korunan eski RPM kayıtlarını yönet; aktif plan dışıdır.",
    )
    package_actions = packages.add_subparsers(dest="package_action", required=True)
    package_add = package_actions.add_parser(
        "add", help="Bir varlığa dağıtım bağlamıyla doğrulanmış RPM paketi ekle.",
    )
    package_add.add_argument("domain", help="Önce assets add ile kaydedilmiş alan adı.")
    package_add.add_argument(
        "--provider", choices=("redhat",), default="redhat",
        help="Paket sağlayıcısı (şimdilik redhat).",
    )
    package_add.add_argument("--name", required=True, help="RPM paket adı; örnek: openssl.")
    package_add.add_argument(
        "--epoch", required=True, type=int,
        help="RPM epoch değeri; paket yöneticisi '(none)' gösteriyorsa 0.",
    )
    package_add.add_argument("--version", required=True, help="RPM sürümü; örnek: 1.0.1e.")
    package_add.add_argument(
        "--release", required=True, help="RPM release değeri; örnek: 16.el6_5.7.",
    )
    package_add.add_argument(
        "--arch", required=True, dest="architecture", help="RPM mimarisi; örnek: x86_64.",
    )
    package_add.add_argument(
        "--distribution-cpe", required=True,
        help="Kesin Red Hat dağıtım CPE'si; örnek: cpe:/o:redhat:enterprise_linux:6::client.",
    )
    package_add.add_argument(
        "--source-rpm",
        help="Biliniyorsa tam kaynak RPM dosya adı; örnek: openssl-1.0.1e-16.el6_5.7.src.rpm.",
    )
    package_add.add_argument(
        "--evidence", required=True, help="Paket ve dağıtım bilgisinin nasıl doğrulandığı.",
    )
    package_list = package_actions.add_parser("list", help="Doğrulanmış RPM kayıtlarını listele.")
    package_list.add_argument("domain", nargs="?", help="Yalnız bu kayıtlı varlığın paketleri.")
    package_list.add_argument(
        "--all", action="store_true", dest="all_entries",
        help="Kaldırılmış paket kayıtlarını da göster.",
    )
    package_list.add_argument("--limit", type=int, default=50, help="Kayıt sınırı (1–500).")
    package_show = package_actions.add_parser("show", help="RPM kanıtını ve geçmişini göster.")
    package_show.add_argument("package_id")
    package_show.add_argument(
        "--event-limit", type=int, default=50, help="Geçmiş sınırı (1–100).",
    )
    package_revoke = package_actions.add_parser(
        "revoke", help="RPM kanıtını geçmişini silmeden etkisizleştir.",
    )
    package_revoke.add_argument("package_id")
    package_revoke.add_argument("--reason", required=True, help="Kaldırma gerekçesi.")
    ubuntu_packages = commands.add_parser(
        "ubuntu-packages",
        help="Uyumluluk için korunan eski Ubuntu paket kayıtlarını yönet; aktif plan dışıdır.",
    )
    ubuntu_package_actions = ubuntu_packages.add_subparsers(
        dest="ubuntu_package_action", required=True,
    )
    ubuntu_package_add = ubuntu_package_actions.add_parser(
        "add", help="Bir varlığa doğrulanmış Ubuntu binary/source paket bağı ekle.",
    )
    ubuntu_package_add.add_argument(
        "domain", help="Önce assets add ile kaydedilmiş alan adı.",
    )
    ubuntu_package_add.add_argument(
        "--ecosystem", required=True,
        help="Tam Ubuntu OSV yayını; örnek: Ubuntu:24.04:LTS.",
    )
    ubuntu_package_add.add_argument(
        "--binary-package", required=True, dest="binary_name",
        help="Kurulu binary paket adı; örnek: php8.3-cli.",
    )
    ubuntu_package_add.add_argument(
        "--binary-version", required=True,
        help="Kurulu binary Debian paket sürümü.",
    )
    ubuntu_package_add.add_argument(
        "--arch", required=True, dest="architecture",
        help="Kurulu paket mimarisi; örnek: amd64.",
    )
    ubuntu_package_add.add_argument(
        "--source-package", required=True, dest="source_name",
        help="Doğrulanmış kaynak paket adı; örnek: php8.3.",
    )
    ubuntu_package_add.add_argument(
        "--source-version", required=True,
        help="Doğrulanmış kaynak Debian paket sürümü; OSV karşılaştırması bunu kullanır.",
    )
    ubuntu_package_add.add_argument(
        "--evidence", required=True,
        help="Binary→source bağı ve sürümlerin nasıl doğrulandığı.",
    )
    ubuntu_package_list = ubuntu_package_actions.add_parser(
        "list", help="Doğrulanmış Ubuntu paket kayıtlarını listele.",
    )
    ubuntu_package_list.add_argument(
        "domain", nargs="?", help="Yalnız bu kayıtlı varlığın paketleri.",
    )
    ubuntu_package_list.add_argument(
        "--all", action="store_true", dest="all_entries",
        help="Kaldırılmış paket kayıtlarını da göster.",
    )
    ubuntu_package_list.add_argument("--limit", type=int, default=50)
    ubuntu_package_show = ubuntu_package_actions.add_parser(
        "show", help="Ubuntu paket kanıtını ve geçmişini göster.",
    )
    ubuntu_package_show.add_argument("package_id")
    ubuntu_package_show.add_argument("--event-limit", type=int, default=50)
    ubuntu_package_revoke = ubuntu_package_actions.add_parser(
        "revoke", help="Ubuntu paket kanıtını geçmişini silmeden etkisizleştir.",
    )
    ubuntu_package_revoke.add_argument("package_id")
    ubuntu_package_revoke.add_argument("--reason", required=True)
    allowlist = commands.add_parser(
        "allowlist", help="Meşru tam alan adı istisnalarını ve geçmişini yönet.",
    )
    allowlist_actions = allowlist.add_subparsers(dest="allowlist_action", required=True)
    allow_add = allowlist_actions.add_parser(
        "add", help="İzlenen adres için tam bir aday alan adını istisna yap.",
    )
    allow_add.add_argument("asset", help="Kayıtlı izlenen adres; örnek: markam.com")
    allow_add.add_argument("domain", help="Tam aday adres; joker karakter kabul edilmez.")
    allow_add.add_argument("--reason", required=True, help="Neden meşru kabul edildiği.")
    allow_add.add_argument(
        "--expires-in-days", type=int,
        help="İstisnayı 1–3650 gün sonra otomatik etkisiz yap; verilmezse kalıcıdır.",
    )
    allow_finding = allowlist_actions.add_parser(
        "add-finding", help="Kayıtlı bir bulgunun tam alan adını istisna yap.",
    )
    allow_finding.add_argument("finding_id")
    allow_finding.add_argument("--reason", required=True)
    allow_finding.add_argument(
        "--expires-in-days", type=int,
        help="İstisnayı 1–3650 gün sonra otomatik etkisiz yap; verilmezse kalıcıdır.",
    )
    allow_list = allowlist_actions.add_parser("list", help="Etkin istisnaları listele.")
    allow_list.add_argument("--all", action="store_true", dest="all_entries",
                            help="Kaldırılmış kayıtları da göster.")
    allow_list.add_argument("--asset", help="Yalnız bu kayıtlı izlenen adres.")
    allow_list.add_argument("--limit", type=int, default=100, help="Kayıt sınırı (1–500).")
    allow_show = allowlist_actions.add_parser("show", help="İstisnayı ve işlem geçmişini göster.")
    allow_show.add_argument("entry_id")
    allow_revoke = allowlist_actions.add_parser(
        "revoke", help="İstisnayı kaldır; geçmiş ve eski bulgular korunur.",
    )
    allow_revoke.add_argument("entry_id")
    allow_revoke.add_argument("--reason", required=True, help="Neden yeniden izlemeye alındığı.")
    surface = commands.add_parser(
        "surface", help="Kayıtlı adreslerin pasif ve yetkili aktif dış yüzey kanıtlarını yönet.",
    )
    surface_actions = surface.add_subparsers(dest="surface_action", required=True)
    register_asset_relations_parser(surface_actions)
    surface_actions.add_parser(
        "source-evaluation",
        help="Pasif kaynak adaptörlerinin sürümlü kabul kararını ağsız göster.",
    )
    surface_approve = surface_actions.add_parser(
        "approve", help="Kayıtlı adresi açık gerekçeyle yetkili kontrol kapsamına al.",
    )
    surface_approve.add_argument("domain", help="Önceden assets add ile kaydedilmiş adres.")
    surface_approve.add_argument(
        "--reason", required=True, help="Bu adresi kontrol etmeye neden yetkili olduğun.",
    )
    surface_check = surface_actions.add_parser(
        "check", help="Etkin kapsamdaki adresin sınırlı DNS/TLS temel kaydını al.",
    )
    surface_check.add_argument("domain")
    surface_list = surface_actions.add_parser(
        "list", help="Kapsamları ve son kaydedilen durumu göster; internete çıkmaz.",
    )
    surface_list.add_argument("--all", action="store_true", dest="all_entries")
    surface_list.add_argument("--limit", type=int, default=100, help="Kayıt sınırı (1–100).")
    surface_show = surface_actions.add_parser(
        "show", help="Bir adresin kapsam ve kontrol geçmişini göster; internete çıkmaz.",
    )
    surface_show.add_argument("domain")
    surface_show.add_argument(
        "--history-limit", type=int, default=20, help="Gösterilecek son kontrol (1–100).",
    )
    surface_overview = surface_actions.add_parser(
        "overview",
        help="Kök, alt alan adı, IP, sertifika ve posta ilişkilerini tek görünümde göster.",
    )
    surface_overview.add_argument("domain", help="Önceden kaydedilmiş kök adres.")
    surface_overview.add_argument(
        "--candidate-limit", type=int, default=20,
        help="İlişkide gösterilecek alt alan adı sınırı (1–100).",
    )
    surface_freshness = surface_actions.add_parser(
        "freshness",
        help="Web, posta ve servis kanıtlarının güncel, eski veya eksik olduğunu göster.",
    )
    surface_freshness.add_argument("domain", help="Önceden kaydedilmiş kök adres.")
    surface_freshness.add_argument(
        "--stale-after-hours", type=int, default=24,
        help="Bu saatten eski kanıtı eski göster (1–8760; varsayılan 24).",
    )
    surface_exposure = surface_actions.add_parser(
        "exposures",
        help="Kayıtlı kanıttan açıklanabilir maruziyet adayları ve kapsam boşlukları çıkar.",
    )
    surface_exposure.add_argument("domain", help="Önceden kaydedilmiş kök adres.")
    surface_exposure.add_argument(
        "--stale-after-hours", type=int, default=24,
        help="Bu saatten eski kanıtı eski göster (1–8760; varsayılan 24).",
    )
    surface_technologies = surface_actions.add_parser(
        "technologies",
        help="Açık portlardan yalnız ürün/sürüm iddiası taşımayan teknoloji ipuçları çıkar.",
    )
    surface_technologies.add_argument("domain", help="Önceden kaydedilmiş kök adres.")
    surface_technologies.add_argument(
        "--stale-after-hours", type=int, default=24,
        help="Bu saatten eski servis kanıtını eski göster (1–8760; varsayılan 24).",
    )
    surface_inventory = surface_actions.add_parser(
        "inventory",
        help="Pasif aday, varlık kaydı ve aktif kontrol kapsamını ayrı katmanlarda göster.",
    )
    surface_inventory.add_argument("domain", help="Önceden kaydedilmiş kök adres.")
    surface_inventory.add_argument(
        "--status", choices=("pending", "owned", "rejected", "all"), default="all",
        help="Aday durumu (varsayılan: all).",
    )
    surface_inventory.add_argument(
        "--limit", type=int, default=100, help="Gösterilecek aday sınırı (1–500).",
    )
    surface_revoke = surface_actions.add_parser(
        "revoke", help="Adresi aktif kontrol kapsamından çıkar; geçmişi koru.",
    )
    surface_revoke.add_argument("domain")
    surface_revoke.add_argument("--reason", required=True, help="Kapsamdan çıkarma gerekçesi.")
    surface_discover = surface_actions.add_parser(
        "discover", help="Kayıtlı kökün alt alan adlarını seçilen pasif kaynakta ara.",
    )
    surface_discover.add_argument("domain", help="Önceden kaydedilmiş kök adres.")
    surface_discover.add_argument(
        "--source", choices=SURFACE_DISCOVERY_PROVIDERS, default="crt.sh",
        help="Pasif kaynak (varsayılan: crt.sh).",
    )
    surface_watch = surface_actions.add_parser(
        "watch", help="Pasif alt alan adı keşfini terminal açıkken sınırlı olarak tekrarla.",
    )
    surface_watch.add_argument("domain", help="Önceden kaydedilmiş kök adres.")
    surface_watch.add_argument(
        "--source", choices=SURFACE_DISCOVERY_PROVIDERS, default="crt.sh",
        help="Her turda kullanılacak pasif kaynak (varsayılan: crt.sh).",
    )
    surface_watch.add_argument(
        "--cycles", type=int, default=3, help="En fazla tur (1–1000; varsayılan 3).",
    )
    surface_watch.add_argument(
        "--interval", type=int, default=3600,
        help="Tamamlanan turlar arasındaki saniye (300–86400).",
    )
    surface_watch.add_argument(
        "--duration", type=int, default=86400,
        help="Yeni tur başlatma süresi, saniye (1–604800).",
    )
    surface_monitor = surface_actions.add_parser(
        "monitor",
        help="Seçili dış yüzey kontrollerini terminal açıkken sınırlı olarak tekrarla.",
    )
    surface_monitor.add_argument("domain", help="Etkin dış yüzey kapsamındaki kök adres.")
    surface_monitor.add_argument(
        "--checks", nargs="+", choices=("web", "mail", "services"),
        default=("web", "mail"),
        help="Kontroller: web, mail ve isteğe bağlı services (varsayılan: web mail).",
    )
    surface_monitor.add_argument(
        "--service-address",
        help="services seçildiyse yönetmeye yetkili olduğun kesin genel IP.",
    )
    surface_monitor.add_argument(
        "--service-reason",
        help="services seçildiyse bu kesin IP'yi kontrol etme yetki gerekçen.",
    )
    surface_monitor.add_argument(
        "--cycles", type=int, default=3, help="En fazla tur (1–1000; varsayılan 3).",
    )
    surface_monitor.add_argument(
        "--interval", type=int, default=3600,
        help="Tamamlanan turlar arasındaki saniye (300–86400).",
    )
    surface_monitor.add_argument(
        "--duration", type=int, default=86400,
        help="Yeni kontrol başlatma süresi, saniye (1–604800).",
    )
    surface_runs = surface_actions.add_parser(
        "runs", help="Pasif keşif çalışmalarının sonuç geçmişini göster; internete çıkmaz.",
    )
    surface_runs.add_argument("domain", help="Kayıtlı kök adres.")
    surface_runs.add_argument("--limit", type=int, default=20, help="Geçmiş sınırı (1–100).")
    surface_discovery_status = surface_actions.add_parser(
        "discovery-status",
        help="Geçerli boş sonucu kaynak kesintisi veya eksik yanıttan ayır.",
    )
    surface_discovery_status.add_argument("domain", help="Kayıtlı kök adres.")
    surface_discovery_status.add_argument(
        "--source", choices=SURFACE_DISCOVERY_PROVIDERS,
        help="Yalnız seçilen sağlayıcının son kaydını göster; verilmezse en son çalışma.",
    )
    surface_discovery_status.add_argument(
        "--stale-after-hours", type=int, default=24,
        help="Bu saatten eski çalışmayı eski göster (1–8760; varsayılan 24).",
    )
    surface_discovery_health = surface_actions.add_parser(
        "discovery-health",
        help="Her pasif sağlayıcının son kayıtlı sonucunu ayrı ve ağsız göster.",
    )
    surface_discovery_health.add_argument("domain", help="Kayıtlı kök adres.")
    surface_discovery_health.add_argument(
        "--stale-after-hours", type=int, default=24,
        help="Bu saatten eski kaydı eski göster (1–8760; varsayılan 24).",
    )
    surface_run = surface_actions.add_parser(
        "run", help="Tek bir pasif keşif çalışmasının ayrıntısını göster; internete çıkmaz.",
    )
    surface_run.add_argument("run_id", help="Keşif sonucunda veya geçmişte gösterilen kimlik.")
    surface_candidates = surface_actions.add_parser(
        "candidates", help="Pasif alt alan adı adaylarını listele; internete çıkmaz.",
    )
    surface_candidates.add_argument("domain", help="Kayıtlı kök adres.")
    surface_candidates.add_argument(
        "--status", choices=("pending", "owned", "rejected", "all"), default="pending",
        help="Aday durumu (varsayılan: pending).",
    )
    surface_candidates.add_argument("--limit", type=int, default=100, help="Kayıt sınırı (1–500).")
    surface_candidate = surface_actions.add_parser(
        "candidate", help="Tek bir pasif alt alan adı adayını göster veya sınıflandır.",
    )
    candidate_actions = surface_candidate.add_subparsers(
        dest="candidate_action", required=True,
    )
    candidate_show = candidate_actions.add_parser(
        "show", help="Adayı, kaynaklarını ve karar geçmişini göster.",
    )
    candidate_show.add_argument("candidate_id")
    candidate_show.add_argument(
        "--source-limit", type=int, default=100, help="Kaynak kanıtı sınırı (1–500).",
    )
    candidate_decide = candidate_actions.add_parser(
        "decide", help="Adayı onay bekliyor, bana ait veya reddedildi olarak işaretle.",
    )
    candidate_decide.add_argument("candidate_id")
    candidate_decide.add_argument(
        "--status", choices=("pending", "owned", "rejected"), required=True,
    )
    candidate_decide.add_argument("--reason", required=True, help="Kararın gerekçesi.")
    surface_cname = surface_actions.add_parser(
        "cname",
        help="Etkin tam adresin CNAME zincirini hedef siteye bağlanmadan izle.",
    )
    cname_actions = surface_cname.add_subparsers(dest="cname_action", required=True)
    cname_check = cname_actions.add_parser(
        "check", help="Google Public DNS üzerinden sınırlı CNAME hedef kanıtı al.",
    )
    cname_check.add_argument("domain", help="Etkin dış yüzey kapsamındaki tam adres.")
    cname_show = cname_actions.add_parser(
        "show", help="Kaydedilmiş CNAME geçmişini göster; internete çıkmaz.",
    )
    cname_show.add_argument("domain", help="Kayıtlı tam adres.")
    cname_show.add_argument(
        "--history-limit", type=int, default=20,
        help="Gösterilecek son kontrol (1–100).",
    )
    surface_mail = surface_actions.add_parser(
        "mail", help="Etkin kökün MX, SPF ve DMARC kayıtlarını izle.",
    )
    mail_actions = surface_mail.add_subparsers(dest="mail_action", required=True)
    mail_check = mail_actions.add_parser(
        "check", help="İnternetten MX/SPF/DMARC temel kaydı al ve değişikliği kaydet.",
    )
    mail_check.add_argument("domain", help="Etkin dış yüzey kapsamındaki kök adres.")
    mail_show = mail_actions.add_parser(
        "show", help="Kaydedilmiş MX/SPF/DMARC geçmişini göster; internete çıkmaz.",
    )
    mail_show.add_argument("domain", help="Kayıtlı kök adres.")
    mail_show.add_argument(
        "--history-limit", type=int, default=20,
        help="Gösterilecek son kontrol (1–100).",
    )
    surface_services = surface_actions.add_parser(
        "services", help="Onaylı domain ve kesin genel IP için sınırlı TCP servislerini izle.",
    )
    service_actions = surface_services.add_subparsers(dest="service_action", required=True)
    service_check = service_actions.add_parser(
        "check", help="Sabit 10 TCP portunu banner/veri almadan kontrol et.",
    )
    service_check.add_argument("domain", help="Etkin dış yüzey kapsamındaki domain.")
    service_check.add_argument(
        "--address", required=True,
        help="Yönetmeye yetkili olduğunu açıkça beyan ettiğin güncel genel IP.",
    )
    service_check.add_argument(
        "--reason", required=True, help="Bu kesin IP'yi kontrol etmeye neden yetkili olduğun.",
    )
    service_show = service_actions.add_parser(
        "show", help="Kaydedilmiş servis geçmişini göster; internete çıkmaz.",
    )
    service_show.add_argument("domain", help="Kayıtlı domain.")
    service_show.add_argument(
        "--history-limit", type=int, default=20,
        help="Gösterilecek son kontrol (1–100).",
    )
    surface_nmap = surface_actions.add_parser(
        "nmap",
        help="Onaylı kesin IP'lerde sınırlandırılmış Nmap TCP servis kanıtı al.",
    )
    nmap_actions = surface_nmap.add_subparsers(dest="nmap_action", required=True)
    nmap_actions.add_parser(
        "readiness", help="Nmap kurulumunu ve desteklenen sürümü ağ kullanmadan doğrula.",
    )
    nmap_check = nmap_actions.add_parser(
        "check", help="Ayarlanabilir ama sınırlı Nmap -sT kontrolü çalıştır.",
    )
    nmap_check.add_argument("domain", help="Etkin dış yüzey kapsamındaki domain.")
    nmap_check.add_argument(
        "--address", action="append", required=True,
        help="Yönetmeye yetkili olduğun kesin genel IP; her hedef için tekrarlanabilir.",
    )
    nmap_check.add_argument(
        "--reason", required=True, help="Bu kesin IP'leri kontrol etmeye neden yetkili olduğun.",
    )
    nmap_check.add_argument(
        "--profile", choices=NMAP_PROFILES, default="safe",
        help="safe, extended (1-1024), full (1-65535) veya custom; varsayılan safe.",
    )
    nmap_check.add_argument(
        "--ports", help="Yalnız custom profilinde: 443,8443 veya 1-1024 biçimi.",
    )
    nmap_check.add_argument(
        "--timeout-seconds", type=int,
        help="Hedef başına kesin süre sınırı (10–3600); profil varsayılanı kullanılır.",
    )
    nmap_check.add_argument(
        "--max-rate", type=int,
        help="Nmap azami paket/saniye hızı (1–1000); kesin bayt kotası değildir.",
    )
    nmap_check.add_argument(
        "--max-retries", type=int,
        help="Port başına Nmap yeniden deneme sınırı (0–3).",
    )
    nmap_check.add_argument(
        "--target-limit", type=int,
        help="Bu komutta izin verilen kesin IP sayısı (1–16).",
    )
    nmap_check.add_argument(
        "--max-probes", type=int,
        help="Port × hedef × deneme için yaklaşık üst bütçe (1–1000000).",
    )
    nmap_check.add_argument(
        "--confirm-wide-scan", action="store_true",
        help="1024'ten fazla TCP portu seçtiğini açıkça onayla.",
    )
    nmap_check.add_argument(
        "--confirm-multi-target", action="store_true",
        help="Birden fazla kesin IP hedefini açıkça onayla.",
    )
    nmap_show = nmap_actions.add_parser(
        "show", help="Kaydedilmiş Nmap geçmişini göster; Nmap veya internet çalıştırmaz.",
    )
    nmap_show.add_argument("domain", help="Kayıtlı domain.")
    nmap_show.add_argument(
        "--history-limit", type=int, default=20,
        help="Gösterilecek son hedef kaydı (1–100).",
    )
    register_nmap_management_parsers(nmap_actions)
    register_nmap_execution_parsers(nmap_actions)
    backup = commands.add_parser("backup", help="Tutarlı bir veritabanı yedeği al.")
    backup.add_argument("--output", type=Path, help="Yeni yedek dosyasının konumu.")
    restore = commands.add_parser("restore", help="Yedeği boş bir kayıt alanına geri yükle.")
    restore.add_argument("source", type=Path, help="XTI ile oluşturulmuş yedek dosyası.")
    imports = commands.add_parser("import", help="Yerel dosyadan gözlem al ve karşılaştır.")
    import_types = imports.add_subparsers(dest="import_type", required=True)
    domains = import_types.add_parser("domains", help=".txt veya .jsonl adres listesini işle.")
    domains.add_argument("source", type=Path, help="Örnek: examples/domains.txt")
    for command, description in (
        ("scan", "İnternetteki sertifika ve web inceleme kayıtlarında benzer adları ara."),
        ("watch", "Terminal açıkken internet aramasını düzenli tekrarla."),
    ):
        scan = commands.add_parser(command, help=description)
        scan.add_argument("domain", nargs="?", help="İzlenecek adres; verilmezse kayıtlı adresler aranır.")
        scan.add_argument("--source", choices=["all", *SOURCE_LABELS], default="all",
                          help="Arama kaynağı; varsayılan all iki kaynağı da kullanır.")
        scan.add_argument(
            "--typos", action="store_true",
            help="En fazla 6 yazım ve 4 Punycode benzer-harf varyantını ek ara (daha uzun sürer).",
        )
        scan.add_argument("--check", action="store_true",
                          help="Aramadan sonra adaylara sınırlı DNS/HTTPS kontrolü yap.")
        scan.add_argument("--check-limit", type=int, default=10,
                          help="Bir turda kontrol edilecek en fazla bulgu (1–20, varsayılan 10).")
        if command == "scan":
            scan.add_argument("--queue", action="store_true", help="İşi kaydet, internet aramasını daha sonra çalıştır.")
        if command == "watch":
            scan.add_argument("--interval", type=int, default=3600,
                              help="Aramalar arasındaki saniye; en az 300, varsayılan 3600.")
            scan.add_argument("--cycles", type=int,
                              help="Belirli sayıda turdan sonra dur; varsayılan Ctrl+C ile durdurulur.")
    jobs = commands.add_parser("jobs", help="Arama geçmişini ve bekleyen işleri yönet.")
    job_actions = jobs.add_subparsers(dest="job_action", required=True)
    job_list = job_actions.add_parser("list", help="Son aramaları ve durumlarını göster.")
    job_list.add_argument("--status", choices=sorted(JOB_STATUSES))
    job_list.add_argument("--limit", type=int, default=20, help="Son kaç iş gösterilsin (1–100).")
    job_show = job_actions.add_parser("show", help="İşin denemelerini ve sorgu geçmişini göster.")
    job_show.add_argument("job_id")
    job_retry = job_actions.add_parser("retry", help="Bekleyen veya yarım/hatalı işi yeni denemeyle çalıştır.")
    job_retry.add_argument("job_id")
    job_actions.add_parser("recover", help="Kapanmış çalıştırıcıdan kalan işleri yarım olarak işaretle.")
    worker = commands.add_parser("worker", help="Sıradaki kayıtlı işi çalıştır.")
    worker.add_argument("--once", action="store_true", required=True, help="Bir işi çalıştırıp çık.")
    sources = commands.add_parser(
        "sources",
        help="Kullanılan kaynakları, sınırlarını ve son kaydedilen sonucu göster; ağ isteği yapmaz.",
    )
    source_actions = sources.add_subparsers(dest="source_action")
    contribution = source_actions.add_parser("contribution", help="Kayıtlı kaynakların tekil/ortak domain katkısını ve çalışma sonuçlarını karşılaştır.")
    contribution.add_argument("domain", nargs="?")
    contribution.add_argument("--organization", help="Açık kuruluş bağlantılarındaki domainleri ayrı karşılaştır.")
    contribution.add_argument("--offset", type=int, help="Kuruluş domain sayfası başlangıcı.")
    contribution.add_argument("--limit", type=int, help="Kuruluşta gösterilecek domain sayısı (1–50).")
    contribution.add_argument("--family", choices=("all", "surface", "brand"), default="all")
    contribution.add_argument("--detail-offset", type=int, default=0)
    contribution.add_argument("--detail-limit", type=int, default=100)
    source_status = source_actions.add_parser(
        "status", help="Kurulum, son çalışma, veri güncelliği ve sonraki komutu tek ekranda göster.",
    )
    source_status.add_argument("--domain", help="Tarama ve alt alan adı kayıtlarını bu domaine daralt.")
    source_status.add_argument("--details", action="store_true", help="Kaynak kapsamını, zamanları ve kanıt sınırlarını aç.")
    source_status.add_argument(
        "--stale-after-hours", type=int, default=24,
        help="Son başarılı yerel kayıt için güncellik eşiği (1–8760 saat; varsayılan 24).",
    )
    findings = commands.add_parser("findings", help="Aday bulguları incele ve kararını kaydet.")
    finding_actions = findings.add_subparsers(dest="finding_action", required=True)
    listing = finding_actions.add_parser("list", help="Aday bulguları listele.")
    listing.add_argument("--status", choices=sorted(FINDING_STATUSES), help="Duruma göre filtrele.")
    show = finding_actions.add_parser("show", help="Bulguyu kaynakları ve karar geçmişiyle göster.")
    show.add_argument("finding_id", help="Listede gösterilen bulgu kimliği.")
    check = finding_actions.add_parser("check", help="Kayıtlı adayın DNS/HTTPS durumunu kontrol et.")
    check.add_argument("finding_id", nargs="?",
                       help="Verilmezse kontrol bekleyen açık bulguları sırayla işler.")
    check.add_argument("--limit", type=int, default=10, help="Toplu kontrolde en fazla bulgu (1–20).")
    review = finding_actions.add_parser("review", help="İnceleme kararını kaydet.")
    review.add_argument("finding_id", help="Listede gösterilen bulgu kimliği.")
    review.add_argument("--decision", required=True, choices=sorted(REVIEW_DECISIONS),
                        help="suspicious: şüpheli; dismissed: normal; uncertain: emin değilim.")
    review.add_argument("--reason", required=True, help="Kararının kısa gerekçesi.")
    triage = commands.add_parser("triage", help="Bulguları açıklamalı inceleme sırasıyla göster; ağ isteği yapmaz.")
    triage.add_argument("--all", action="store_true", help="Kullanıcının kapattığı bulguları da göster.")
    triage.add_argument("--limit", type=int, default=100, help="En fazla gösterilecek kayıt (1–500).")
    report = commands.add_parser("report", help="Bir bulgunun kanıtları ve geçmişiyle raporunu oluştur.")
    report.add_argument("finding_id", help="Listede gösterilen bulgu kimliği.")
    report.add_argument("--output", type=Path, help="Yeni JSON raporunun konumu; mevcut dosya ezilmez.")
    storage = commands.add_parser("storage", help="Kayıt boyutunu gör ve bağlantısız eski gözlemleri yönet.")
    storage_actions = storage.add_subparsers(dest="storage_action", required=True)
    storage_actions.add_parser("status", help="Kayıt boyutunu ve yeniden kullanılabilir alanı göster.")
    storage_readiness = storage_actions.add_parser(
        "readiness", help="Disk, yedek, saklama ve yerel kurtarma hazırlığını birlikte göster.",
    )
    storage_readiness.add_argument(
        "--backup-stale-after-days", type=int, default=7,
        help="Bu günden eski yönetilen yedeği eski göster (1–3650; varsayılan 7).",
    )
    storage_readiness.add_argument(
        "--retention-days", type=int, default=90,
        help="Bağlantısız gözlem saklama önizlemesi (7–3650; varsayılan 90).",
    )
    cleanup = storage_actions.add_parser("cleanup", help="Eski bağlantısız gözlemler için temizlik önizlemesi oluştur.")
    cleanup.add_argument("--older-than-days", type=int, default=90,
                         help="İlk yerel kayıttan itibaren yaş sınırı (7–3650 gün; varsayılan 90).")
    cleanup.add_argument("--limit", type=int, default=10000,
                         help="Bir işlemde en fazla silinecek gözlem (1–10000).")
    cleanup.add_argument("--apply", dest="apply_token", metavar="TOKEN",
                         help="Önizlemede gösterilen kimlikle yedek alıp temizliği uygula.")
    cleanup_history = storage_actions.add_parser("history", help="Tamamlanmış temizlikleri ve yedek konumlarını göster.")
    cleanup_history.add_argument("--limit", type=int, default=20, help="En fazla geçmiş kaydı (1–100).")
    inbox = commands.add_parser("inbox", help="Yerel bildirim kutusunu ve okundu bilgisini yönet.")
    inbox.set_defaults(inbox_action="list", status="unread", limit=20, before=None)
    inbox_actions = inbox.add_subparsers(dest="inbox_action")
    inbox_list = inbox_actions.add_parser("list", help="Bildirimleri göster; kendiliğinden okundu işaretlemez.")
    inbox_list.add_argument("--status", choices=["unread", "read", "all"], default="unread")
    inbox_list.add_argument("--limit", type=int, default=20, help="Bir sayfada en fazla bildirim (1–100).")
    inbox_list.add_argument("--before", type=int, help="Önceki sayfanın verdiği sayıyla daha eski kayıtlara geç.")
    inbox_show = inbox_actions.add_parser(
        "show", help="Bildirimin ilgili bulgu, aday veya değişim kanıtını göster."
    )
    inbox_show.add_argument("notification_id", help="Kutuda gösterilen bildirim kimliği.")
    for action, description in (("read", "Seçtiğin bildirimleri okundu işaretle."),
                                ("unread", "Seçtiğin bildirimleri yeniden okunmamış işaretle.")):
        mark = inbox_actions.add_parser(action, help=description)
        mark.add_argument("notification_ids", nargs="+", help="Bir veya birden çok bildirim kimliği (en fazla 100).")
    webhook = commands.add_parser(
        "webhook", help="Seçilen yerel bildirimleri imzalı HTTPS teslim kuyruğuyla gönder.",
    )
    webhook_actions = webhook.add_subparsers(dest="webhook_action", required=True)
    webhook_secret = webhook_actions.add_parser(
        "secret-generate", help="Üzerine yazmadan özel izinli ortak gizli anahtar dosyası oluştur.",
    )
    webhook_secret.add_argument("destination", help="Var olmayan hedef anahtar dosyası.")
    webhook_target_add = webhook_actions.add_parser(
        "target-add", help="HTTPS/443 webhook hedefini gizli anahtar dosyasıyla kaydet.",
    )
    webhook_target_add.add_argument("name", help="Benzersiz görünen hedef adı.")
    webhook_target_add.add_argument("url", help="HTTPS/443 webhook adresi.")
    webhook_target_add.add_argument("--secret-file", required=True)
    webhook_target_list = webhook_actions.add_parser(
        "target-list", help="Webhook hedeflerini tam adres ve sır olmadan listele.",
    )
    webhook_target_list.add_argument("--all", action="store_true", dest="all_entries")
    webhook_target_list.add_argument("--limit", type=int, default=50)
    webhook_target_show = webhook_actions.add_parser(
        "target-show", help="Bir webhook hedefinin güvenli özetini göster.",
    )
    webhook_target_show.add_argument("destination_id")
    webhook_target_revoke = webhook_actions.add_parser(
        "target-revoke", help="Webhook hedefini geçmişi silmeden devre dışı bırak.",
    )
    webhook_target_revoke.add_argument("destination_id")
    webhook_target_secret = webhook_actions.add_parser(
        "target-secret-set", help="Etkin hedefin gizli anahtarını özel dosyadan değiştir.",
    )
    webhook_target_secret.add_argument("destination_id")
    webhook_target_secret.add_argument("--secret-file", required=True)
    webhook_queue = webhook_actions.add_parser(
        "queue", help="Bir yerel bildirimin değişmez anlık görüntüsünü hedefe kuyruğa al.",
    )
    webhook_queue.add_argument("destination_id")
    webhook_queue.add_argument("notification_id")
    webhook_delivery_list = webhook_actions.add_parser(
        "delivery-list", help="Webhook teslim kuyruğunu ve sonuçlarını göster.",
    )
    webhook_delivery_list.add_argument(
        "--status", choices=("all", "queued", "retryable", "failed", "delivered"),
        default="all",
    )
    webhook_delivery_list.add_argument("--limit", type=int, default=50)
    webhook_delivery_show = webhook_actions.add_parser(
        "delivery-show", help="Değişmez gövde özetini ve teslim denemelerini göster.",
    )
    webhook_delivery_show.add_argument("delivery_id")
    webhook_delivery_show.add_argument("--attempt-limit", type=int, default=50)
    webhook_deliver = webhook_actions.add_parser(
        "deliver", help="Kuyruktaki tek teslimi açıkça HTTPS ile gönder veya yeniden dene.",
    )
    webhook_deliver.add_argument("delivery_id")
    return parser


def emit(data: dict[str, Any], lines: list[str], *, as_json: bool, ok: bool = True) -> None:
    if as_json:
        print(json.dumps({"ok": ok, "data": data}, ensure_ascii=True))
    else:
        for line in lines:
            print(line)


def report_error(code: str, message: str, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"ok": False, "error": {"code": code, "message": message}},
                         ensure_ascii=True), file=sys.stderr)
    else:
        print(f"Hata: {safe_text(message)}", file=sys.stderr)


def scan_data(result: ScanResult, attempt: ScanAttempt | None, provider: str) -> dict:
    data = {**asdict(result), "provider": provider}
    if attempt:
        data.update(job_id=attempt.job_id, attempt_id=attempt.id, attempt_number=attempt.number)
    return data


def emit_scan(
    result: ScanResult, *, as_json: bool, attempt: ScanAttempt | None = None,
    provider: str = "crt.sh", checks: BatchCheckResult | None = None,
) -> None:
    data = scan_data(result, attempt, provider)
    if checks is not None:
        data["checks"] = check_data(checks)
    if as_json:
        print(json.dumps({"ok": result.status == "complete" and (
            checks is None or not checks_incomplete(checks.assessments)
        ), "data": data},
                         ensure_ascii=True), flush=True)
        return
    if attempt:
        print(f"İş kimliği: {safe_text(attempt.job_id)} | Deneme: {attempt.number}")
    labels = {
        "complete": "İstenen kaynak sorguları tamamlandı.",
        "partial": "Arama kısmen tamamlandı; aşağıdaki eksiklere dikkat et.",
        "failed": "Kaynağa erişilemedi; bu arama sonuç üretmedi.",
    }
    print(labels[result.status])
    print(f"Kaynak: {safe_text(SOURCE_LABELS.get(provider, provider))}. Bu arama bütün interneti kapsamaz.")
    coverage = dict.fromkeys(note for query in result.queries for note in query.coverage_notes)
    for note in coverage:
        print(f"  Kapsam: {safe_text(note)}")
    for query in result.queries:
        if query.error:
            print(f"  {safe_text(query.pattern)}: {safe_text(query.error)}")
        for warning in query.warnings:
            print(f"  {safe_text(warning)}")
        if query.skipped_names:
            print(f"  {query.skipped_names} desteklenmeyen ad karşılaştırılamadı.")
    if result.status != "failed":
        print(f"Yeni kaynak kaydı: {result.summary.observations_created}.")
        print(f"Yeni aday bulgu: {result.summary.findings_created}; "
              f"mevcut aday bulgu: {result.summary.findings_existing}.")
        if result.summary.findings_suppressed:
            print(
                "Tam adres istisnasıyla bastırılan aday: "
                f"{result.summary.findings_suppressed}."
            )
        for domain in result.candidate_domains[:50]:
            print(f"  {safe_text(domain)}")
        if len(result.candidate_domains) > 50:
            print(f"  İlk 50 aday gösterildi; toplam {len(result.candidate_domains)} aday adres var.")
        print("Kaynakta görülmesi sitenin şu an aktif veya zararlı olduğunu kanıtlamaz.")
    print("Kayıtlı bulgular: ./xti findings list", flush=True)
    print("Yeni bildirimler: ./xti inbox", flush=True)
    if checks is not None:
        for line in batch_lines(checks):
            print(line)


def make_domain_matcher() -> DomainMatcher:
    security = unicode_security_profile()
    resolver = PublicSuffixResolver(unicode_security=security)
    suffix = f"/psl:{resolver.sha256}"
    return DomainMatcher(
        resolver,
        rule_version=f"{RULE_VERSION}{suffix}/unicode:{security.version}",
        unicode_security=security,
        ascii_rule_version=f"{LEGACY_RULE_VERSION}{suffix}",
        expanded_ascii_rule_version=f"{EXPANDED_ASCII_RULE_VERSION}{suffix}",
        idn_rule_version=f"{IDN_RULE_VERSION}{suffix}/unicode:{security.version}",
    )


def make_jobs(settings: Settings, repository: SQLiteAssetRepository) -> JobService:
    findings = SQLiteFindingRepository(settings.database)
    matcher = make_domain_matcher()
    cooldowns = SQLiteCooldownRepository(settings.database)
    allowlist = SQLiteAllowlistRepository(settings.database)
    discoveries = {
        "crt.sh": DiscoveryService(
            repository, findings, matcher, CrtShSource(cooldowns=cooldowns),
            allowlist=allowlist,
        ),
        "urlscan": DiscoveryService(
            repository, findings, matcher, UrlscanSource(cooldowns=cooldowns),
            query_planner=build_prefix_query_plan, allowlist=allowlist,
        ),
    }
    return JobService(
        SQLiteJobRepository(settings.database), discoveries["crt.sh"],
        LocalExecutionLock(settings.database), discoveries=discoveries,
    )


def terminal_progress(as_json: bool):
    return None if as_json else lambda message: print(
        safe_text(message), file=sys.stderr, flush=True,
    )


def make_enrichment(settings: Settings) -> FindingEnrichmentService:
    return FindingEnrichmentService(
        SQLiteFindingRepository(settings.database), SQLiteAssessmentRepository(settings.database),
        HttpsTargetProbe(),
    )


def make_case_service(settings: Settings) -> CaseService:
    event_service = SupplierThreatEventService(
        SQLiteSupplierRepository(settings.database),
        SQLiteRansomwareClaimRepository(settings.database),
        SQLiteRansomLookClaimRepository(settings.database),
    )
    supplier_risk = SupplierRiskService(
        SQLiteSupplierRepository(settings.database),
        SQLiteSupplierCandidateRepository(settings.database),
        event_service,
    )
    resolver = CaseEvidenceResolverService(
        SQLiteCaseEvidenceSourceRepository(settings.database), supplier_risk,
    )
    return CaseService(SQLiteCaseRepository(settings.database), resolver)


def make_cti_feed(settings: Settings, source_name: str):
    policy = CTI_FEED_POLICIES[source_name]
    source = (
        FeodoTrackerSource() if source_name == "feodo" else CertPlWarningSource()
    )
    return SQLiteCtiFeedRepository(settings.database, policy), source


def make_analysis_service(settings: Settings, repository: SQLiteAssetRepository) -> UnifiedAnalysisService:
    return UnifiedAnalysisService(
        SurfaceOverviewService(repository, SQLiteSurfaceOverviewRepository(settings.database)),
        SurfaceFreshnessService(repository, SQLiteSurfaceFreshnessRepository(settings.database)),
        SurfaceDiscoveryStatusService(repository, SQLiteSurfaceCandidateRepository(settings.database)),
        SurfaceExposureService(repository, SQLiteSurfaceFreshnessRepository(settings.database)),
        SQLiteFindingRepository(settings.database),
        SQLiteCtiIndicatorRepository(settings.database),
    )


def make_collection_service(
    settings: Settings, repository: SQLiteAssetRepository, tasks: Sequence[str] | None,
    *, username_watch_ids: Sequence[str] = (),
    ransomware_watch_ids: Sequence[str] = (), ransomlook_watch_ids: Sequence[str] = (),
    watch_item_limit: int = 100,
    news_sources: Sequence[str] = (), search_watch_ids: Sequence[str] = (),
) -> CollectionService:
    username_watch_ids, ransomware_watch_ids, ransomlook_watch_ids = (
        CollectionWatchService.validate_selection(
            username_watch_ids=username_watch_ids,
            ransomware_watch_ids=ransomware_watch_ids,
            ransomlook_watch_ids=ransomlook_watch_ids, item_limit=watch_item_limit,
        )
    )
    selected = DEFAULT_COLLECTION_TASKS if tasks is None else tasks
    discoveries = {}
    if "discover-crtsh" in selected:
        discoveries["crt.sh"] = SurfaceDiscoveryService(
            repository, SQLiteSurfaceCandidateRepository(settings.database),
            CrtShSource(cooldowns=SQLiteCooldownRepository(settings.database)),
        )
    if "discover-theharvester" in selected:
        discoveries["theharvester"] = SurfaceDiscoveryService(
            repository, SQLiteSurfaceCandidateRepository(settings.database),
            TheHarvesterArchiveSource(),
        )
    feeds = {}
    for name in ("feodo", "certpl"):
        if f"ioc-{name}" in selected:
            feed_repository, feed_source = make_cti_feed(settings, name)
            feeds[name] = CtiFeedService(feed_repository, feed_source)
    watch_collection = None
    if username_watch_ids or ransomware_watch_ids or ransomlook_watch_ids:
        username = None
        if username_watch_ids:
            username_repository = SQLiteBrandUsernameWatchRepository(settings.database)
            definitions = BrandUsernameWatchService(username_repository, {})
            source_keys = {
                definitions.show(watch_id, event_limit=1, run_limit=1).watch.source_key
                for watch_id in username_watch_ids
            }
            sources = {}
            if "maigret" in source_keys:
                sources["maigret"] = MaigretUsernameSource()
            if "sherlock" in source_keys:
                sources["sherlock"] = SherlockUsernameSource()
            username = BrandUsernameWatchService(username_repository, sources)
        histories = {}
        watches = {}
        if ransomware_watch_ids:
            claim_repository = SQLiteRansomwareClaimRepository(settings.database)
            histories["threatcluster"] = RansomwareClaimHistoryService(
                claim_repository, ThreatClusterRansomwareSource(),
            )
            watches["threatcluster"] = RansomwareWatchService(
                SQLiteRansomwareWatchRepository(settings.database), claim_repository,
            )
        if ransomlook_watch_ids:
            claim_repository = SQLiteRansomLookClaimRepository(settings.database)
            histories["ransomlook"] = RansomLookClaimHistoryService(
                claim_repository, RansomLookRansomwareSource(),
            )
            watches["ransomlook"] = RansomLookWatchService(
                SQLiteRansomLookWatchRepository(settings.database), claim_repository,
            )
        watch_collection = CollectionWatchService(
            username=username, ransomware_histories=histories, ransomware_watches=watches,
        )
    news_searches = None
    if search_watch_ids:
        from xti.adapters.sqlite_collection_news import SQLiteCollectionNewsSearches
        news_searches = SQLiteCollectionNewsSearches(settings.database)
    return CollectionService(
        make_jobs(settings, repository), discoveries, feeds,
        make_analysis_service(settings, repository),
        watch_collection=watch_collection,
        public_notices=(PublicNoticeService(
            SQLitePublicNoticeRepository(settings.database), HibpPublicNoticeSource(),
        ) if "notices-hibp" in selected else None),
        news=make_news_service(settings.database, refresh=True) if news_sources else None,
        news_searches=news_searches,
    )


def make_collection_history_service(settings: Settings, repository: SQLiteAssetRepository) -> CollectionHistoryService:
    def collection_factory(definition: CollectionProfileDefinition) -> CollectionService:
        return make_collection_service(
            settings, repository, definition.task_ids,
            username_watch_ids=definition.username_watch_ids,
            ransomware_watch_ids=definition.ransomware_watch_ids,
            ransomlook_watch_ids=definition.ransomlook_watch_ids,
            watch_item_limit=definition.watch_item_limit,
            news_sources=definition.news_sources,
            search_watch_ids=definition.search_watch_ids,
        )
    return CollectionHistoryService(
        SQLiteCollectionHistoryRepository(settings.database), collection_factory,
        LocalExecutionLock(settings.database),
    )


def make_profile_service(settings: Settings, repository: SQLiteAssetRepository) -> CollectionProfileService:
    return CollectionProfileService(
        SQLiteCollectionProfileRepository(settings.database),
        lambda definition: make_collection_history_service(settings, repository),
        LocalExecutionLock(settings.database),
    )


def make_scheduling_service(settings: Settings, repository: SQLiteAssetRepository) -> SchedulingService:
    return SchedulingService(
        SQLiteCollectionProfileRepository(settings.database),
        lambda definition: make_collection_history_service(settings, repository),
        SQLiteCollectionHistoryRepository(settings.database),
        LocalExecutionLock(settings.database),
        SystemdScheduleWriter(
            launcher=Path(__file__).resolve().parents[3] / "xti",
            database=settings.database,
        ),
        ScheduledBackupMaintenance(settings.database),
    )


def surface_check_incomplete(check) -> bool:
    return bool(check.result.errors) or check.result.dns_status in {"failed", "blocked"}


def check_data(result: BatchCheckResult) -> dict:
    return {"status": "partial" if checks_incomplete(result.assessments) else "complete", **asdict(result)}


def emit_attempt(
    attempt: ScanAttempt | None, *, as_json: bool, provider: str = "crt.sh",
    checks: BatchCheckResult | None = None,
) -> int:
    if attempt is None:
        emit({"processed": 0}, ["Sırada bekleyen iş yok. Geçmiş: ./xti jobs list"], as_json=as_json)
        return 0
    assert attempt.result is not None
    emit_scan(attempt.result, as_json=as_json, attempt=attempt, provider=provider, checks=checks)
    return 0 if attempt.status == "complete" and (
        checks is None or not checks_incomplete(checks.assessments)
    ) else 3


def emit_cycle(
    attempts: list[tuple[str, ScanAttempt]], *, as_json: bool,
    checks: BatchCheckResult | None = None,
) -> int:
    statuses = [attempt.status for _, attempt in attempts]
    status = "complete" if all(value == "complete" for value in statuses) else (
        "failed" if all(value == "failed" for value in statuses) else "partial"
    )
    if checks is not None and checks_incomplete(checks.assessments) and status == "complete":
        status = "partial"
    if as_json:
        results = []
        for provider, attempt in attempts:
            assert attempt.result is not None
            results.append(scan_data(attempt.result, attempt, provider))
        data = {"status": status, "results": results}
        if checks is not None:
            data["checks"] = check_data(checks)
        print(json.dumps({"ok": status == "complete", "data": data}, ensure_ascii=True), flush=True)
    else:
        for provider, attempt in attempts:
            emit_attempt(attempt, as_json=False, provider=provider)
        if checks is not None:
            for line in batch_lines(checks):
                print(line)
    return 0 if status == "complete" else 3


def run(args: argparse.Namespace) -> int | None:
    if args.command == "platform":
        return run_platform(args)
    settings = Settings.from_path(args.data_dir)
    if args.command == "engine":
        return run_engine(settings.database, describe=args.describe)
    if args.command == "components":
        report = make_component_service().list()
        emit(report, component_lines(report), as_json=args.json)
        return None
    repository = SQLiteAssetRepository(settings.database)
    service = AssetService(repository)

    if args.command == "init":
        repository.initialize()
        emit(
            {"data_dir": str(settings.data_dir), "database": str(settings.database),
             "schema_version": SCHEMA_VERSION},
            ["XTI kayıt alanı hazır.", f"Konum: {safe_text(settings.database)}",
             "Bir adres eklemek için: ./xti assets add example.com"], as_json=args.json,
        )
    elif args.command == "webhook":
        if args.webhook_action == "secret-generate":
            artifact = generate_webhook_secret(Path(args.destination))
            emit(asdict(artifact), webhook_secret_lines(artifact), as_json=args.json)
            return None
        webhooks = WebhookService(
            SQLiteWebhookRepository(settings.database),
            SQLiteInboxRepository(settings.database),
            SafeHttpsWebhookSender(),
        )
        if args.webhook_action == "target-add":
            result = webhooks.add_destination(
                args.name, args.url, read_webhook_secret(Path(args.secret_file)),
            )
            emit(
                asdict(result), webhook_destination_mutation_lines(result),
                as_json=args.json,
            )
        elif args.webhook_action == "target-list":
            destinations = webhooks.list_destinations(
                active_only=not args.all_entries, limit=args.limit,
            )
            emit(
                {"destinations": [asdict(item) for item in destinations],
                 "active_only": not args.all_entries},
                webhook_destination_list_lines(destinations), as_json=args.json,
            )
        elif args.webhook_action == "target-show":
            destination = webhooks.show_destination(args.destination_id)
            emit(
                asdict(destination), webhook_destination_lines(destination),
                as_json=args.json,
            )
        elif args.webhook_action == "target-revoke":
            result = webhooks.revoke_destination(args.destination_id)
            emit(
                asdict(result), webhook_destination_mutation_lines(result),
                as_json=args.json,
            )
        elif args.webhook_action == "target-secret-set":
            result = webhooks.rotate_secret(
                args.destination_id, read_webhook_secret(Path(args.secret_file)),
            )
            emit(
                asdict(result), webhook_destination_mutation_lines(result),
                as_json=args.json,
            )
        elif args.webhook_action == "queue":
            delivery, created = webhooks.queue(
                args.destination_id, args.notification_id,
            )
            emit(
                {"delivery": asdict(delivery), "created": created},
                webhook_delivery_lines(delivery, created=created), as_json=args.json,
            )
        elif args.webhook_action == "delivery-list":
            page = webhooks.list_deliveries(status=args.status, limit=args.limit)
            emit(
                asdict(page), webhook_delivery_page_lines(page), as_json=args.json,
            )
        elif args.webhook_action == "delivery-show":
            details = webhooks.show_delivery(
                args.delivery_id, attempt_limit=args.attempt_limit,
            )
            emit(
                asdict(details), webhook_delivery_detail_lines(details),
                as_json=args.json,
            )
        elif args.webhook_action == "deliver":
            with LocalExecutionLock(settings.database).acquire():
                result = webhooks.deliver(args.delivery_id)
            emit(
                asdict(result), webhook_delivery_result_lines(result),
                as_json=args.json,
            )
            return 0 if result.delivery.status == "delivered" else 3
    elif args.command == "evaluate":
        report = EvaluationService(make_domain_matcher()).run(load_evaluation_dataset())
        emit(asdict(report), evaluation_lines(report), as_json=args.json)
    elif args.command == "changes":
        report = PeriodicChangesService(SQLitePeriodicChangesRepository(settings.database)).show(
            days=args.days, domain=args.domain, organization_id=args.organization,
            limit=args.limit, offset=args.offset,
        )
        emit(asdict(report), periodic_changes_lines(report), as_json=args.json)
    elif args.command == "mentions":
        if args.mentions_action == "groups":
            data, lines, status = execute_mention_group_command(make_mention_group_service(
                settings.database, api_key_file=getattr(args, "api_key_file", None)), args,
                progress=terminal_progress(args.json))
            emit(data, lines, as_json=args.json, ok=status == 0)
            return status
        data, lines, status = execute_mentions_command(
            None if args.mentions_action == "configure" else make_mentions_service(
                settings.database, search=args.mentions_action == "search",
                api_key_file=getattr(args, "api_key_file", None)), args,
        )
        emit(data, lines, as_json=args.json, ok=status == 0)
        return status
    elif args.command == "news":
        data, lines, status = execute_news_command(
            None if args.news_action == "sources" else make_news_service(
                settings.database, refresh=args.news_action == "refresh"), args,
        )
        emit(data, lines, as_json=args.json, ok=status == 0)
        return status
    elif args.command == "notices":
        if args.notice_action in {"watch", "watch-run-show"}:
            data, lines = execute_public_notice_watch_command(
                PublicNoticeWatchService(SQLitePublicNoticeWatchRepository(settings.database),
                                         LocalExecutionLock(settings.database)), args,
            )
            emit(data, lines, as_json=args.json)
            return 0
        notices = PublicNoticeService(
            SQLitePublicNoticeRepository(settings.database),
            HibpPublicNoticeSource() if args.notice_action == "refresh" else None,
        )
        if args.notice_action == "refresh":
            with LocalExecutionLock(settings.database).acquire():
                result = notices.refresh(item_limit=args.limit)
            emit(asdict(result), public_notice_refresh_lines(result), as_json=args.json,
                 ok=result.run.status == "complete")
            return 0 if result.run.status == "complete" else 3
        if args.notice_action == "status":
            result = notices.status(run_limit=args.limit, offset=args.offset)
            lines = public_notice_status_lines(result)
        elif args.notice_action == "search":
            result = notices.search(args.query, domain=args.domain, limit=args.limit, offset=args.offset)
            lines = public_notice_search_lines(result)
        elif args.notice_action == "run-show":
            result = notices.run_show(args.run_id, item_limit=args.limit, offset=args.offset)
            lines = public_notice_refresh_lines(result)
        else:
            result = notices.show(args.notice_id)
            lines = public_notice_detail_lines(result)
        emit(asdict(result), lines, as_json=args.json)
    elif args.command == "schedule":
        scheduling = make_scheduling_service(settings, repository)
        if args.schedule_command == "generate":
            result = scheduling.generate(
                args.profile, output=args.output, at=args.at, timezone=args.timezone,
                weekday=args.weekday, keep=args.keep,
            )
            lines = schedule_generated_lines(result)
        else:
            result = scheduling.prepare(args.profile, keep=args.keep)
            lines = schedule_preparation_lines(result)
        emit(asdict(result), lines, as_json=args.json)
    elif args.command == "enrich":
        data, lines = execute_enrichment(settings.database, args)
        ok = data.get("status") != "failed"
        emit(data, lines, as_json=args.json, ok=ok)
        return 0 if ok else 3
    elif args.command == "warninglists":
        data, lines = execute_warninglists(settings.database, args)
        ok = data.get("status") not in {"failed", "partial"}
        emit(data, lines, as_json=args.json, ok=ok)
        return 0 if ok else 3
    elif args.command == "source-jobs":
        data, lines = execute_source_jobs(settings.database, args)
        ok = not (args.source_job_action == 'worker' and data and data['status'] in {'partial', 'failed', 'interrupted'})
        emit(data, lines, as_json=args.json, ok=ok)
        return 0 if ok else 3
    elif args.command == "research-history":
        data, lines = execute_history(settings.database, args)
        emit(data, lines, as_json=args.json)
    elif args.command == "review-queue":
        data, lines = execute_company_review(settings.database, args)
        emit(data, lines, as_json=args.json)
    elif hasattr(args, "evidence_operation"):
        from xti.interfaces.evidence import execute_evidence
        data, lines = execute_evidence(settings.database, args)
        emit(data, lines, as_json=args.json)
    elif args.command == 'journals':
        from xti.interfaces.journal_storage import execute_journal
        data, lines = execute_journal(settings.database, args)
        emit(data, lines, as_json=args.json)
    elif args.command in {"reports", "observations"}:
        data, lines = execute_report(settings.database, args)
        emit(data, lines, as_json=args.json)
    elif args.command == "investigate":
        data, lines = execute_investigation(settings.database, args)
        emit(data, lines, as_json=args.json)
    elif args.command == "research":
        data, lines = execute_research(settings.database, args)
        emit(data, lines, as_json=args.json)
    elif args.command == "search":
        data, lines = execute_global_search_command(
            GlobalSearchService(SQLiteGlobalSearchRepository(settings.database)), args,
        )
        emit(data, lines, as_json=args.json)
    elif args.command == "events":
        data, lines = execute_event_candidates_command(make_event_candidate_service(settings.database), args)
        emit(data, lines, as_json=args.json)
    elif args.command == "search-watch":
        data, lines = execute_global_saved_search_command(
            make_global_saved_search_service(settings.database), args,
            progress=terminal_progress(args.json),
        )
        emit(data, lines, as_json=args.json)
    elif args.command == "organizations":
        if args.organization_action == "content":
            from xti.adapters.sqlite_company_content import SQLiteCompanyContentRepository
            from xti.application.company_content import CompanyContentService
            from xti.interfaces.company_content import content_lines
            data = CompanyContentService(SQLiteCompanyContentRepository(settings.database)).show(
                args.organization_id, scope_offset=args.scope_offset, scope_limit=args.scope_limit,
                offset=args.offset, limit=args.limit, stale_after_hours=args.stale_after_hours,
            )
            lines = content_lines(data, data_dir=settings.data_dir, history=args.history)
        elif args.organization_action == "report":
            data, lines = execute_organization_report_command(
                OrganizationReportService(SQLiteOrganizationReportRepository(settings.database)), args,
            )
        elif args.organization_action == "export":
            data, lines = execute_organization_export_command(
                OrganizationExportService(
                    SQLiteOrganizationReportRepository(settings.database),
                    HtmlOrganizationReportRenderer(), AtomicHtmlReportWriter(),
                ), args,
            )
        else:
            organization_service = OrganizationService(
                SQLiteOrganizationRepository(settings.database), LocalExecutionLock(settings.database),
            )
            data, lines = execute_organization_command(organization_service, args)
        emit(data, lines, as_json=args.json)
    elif args.command == "collections":
        histories = make_collection_history_service(settings, repository)
        if args.collection_action == "list":
            page = histories.list(limit=args.limit, before=args.before)
            emit(asdict(page), collection_history_page_lines(page), as_json=args.json)
        elif args.collection_action == "show":
            details = histories.show(args.session_id)
            emit(asdict(details), collection_history_detail_lines(details, data_dir=args.data_dir), as_json=args.json)
        elif args.collection_action == "recover":
            recovered = histories.recover()
            emit({"recovered_session_ids": recovered}, [f"Kapatılan kesilmiş çalışma: {len(recovered)}", *recovered], as_json=args.json)
        elif args.plan:
            plan = histories.resume_plan(args.session_id)
            emit(asdict(plan), resume_plan_lines(plan, data_dir=args.data_dir), as_json=args.json)
        else:
            result = histories.resume(args.session_id, progress=terminal_progress(args.json))
            if args.json:
                print(json.dumps({"ok": result.history.session.status == "complete", "data": asdict(result)}, ensure_ascii=True))
            else:
                for line in resume_result_lines(result, data_dir=args.data_dir):
                    print(line)
            return 0 if result.history.session.status == "complete" else 3
    elif args.command == "profiles":
        profiles = make_profile_service(settings, repository)
        if args.profile_action == "save":
            mutation = profiles.save(args.name, definition_from_arguments(args))
            emit(asdict(mutation), profile_mutation_lines(mutation), as_json=args.json)
        elif args.profile_action == "list":
            records, has_more = profiles.list_window(active_only=not args.all_entries, limit=args.limit)
            emit(
                {"profiles": [asdict(item) for item in records], "has_more": has_more},
                profile_list_lines(records, has_more), as_json=args.json,
            )
        elif args.profile_action == "show":
            details = profiles.show(args.name, event_limit=args.event_limit)
            emit(asdict(details), profile_detail_lines(details), as_json=args.json)
        else:
            mutation = profiles.revoke(args.name, reason=args.reason)
            emit(asdict(mutation), profile_mutation_lines(mutation), as_json=args.json)
    elif args.command == "collect":
        validate_profile_selection(args)
        if args.profile is not None:
            profiles = make_profile_service(settings, repository)
            if args.plan:
                plan = profiles.plan(args.profile)
                emit(asdict(plan), collection_plan_lines(plan), as_json=args.json)
                return 0
            result = profiles.run(args.profile, progress=terminal_progress(args.json))
        else:
            definition = definition_from_arguments(args)
            collection = make_collection_history_service(settings, repository)
            options = collection_options(definition)
            if args.plan:
                plan = collection.plan(definition.asset_value, **options)
                emit(asdict(plan), collection_plan_lines(plan), as_json=args.json)
                return 0
            result = collection.run(
                definition.asset_value, progress=terminal_progress(args.json), **options,
            )
        if args.json:
            print(json.dumps({"ok": result.status == "complete", "data": asdict(result)}, ensure_ascii=True))
        else:
            for line in collection_result_lines(result, data_dir=args.data_dir, summary=args.summary):
                print(line)
        return 0 if result.status == "complete" else 3
    elif args.command == "analyze":
        analysis_service = make_analysis_service(settings, repository)
        if args.refresh_ioc is not None:
            feed_repository, feed_source = make_cti_feed(
                settings, args.refresh_ioc,
            )
            # Validate feed storage before the execution lock and external request.
            feed_repository.status(run_limit=1)
            refresh_service = UnifiedAnalysisRefreshService(
                analysis_service,
                CtiFeedService(feed_repository, feed_source),
                source=args.refresh_ioc,
            )
            with LocalExecutionLock(settings.database).acquire():
                result = refresh_service.run(
                    args.domain,
                    stale_after_hours=args.stale_after_hours,
                    finding_limit=args.finding_limit,
                )
            if args.json:
                print(json.dumps({
                    "ok": result.refresh.status == "complete",
                    "data": asdict(result),
                }, ensure_ascii=True))
            else:
                for line in unified_analysis_refresh_lines(result):
                    print(line)
            return 0 if result.refresh.status == "complete" else 3
        report = analysis_service.show(
            args.domain, stale_after_hours=args.stale_after_hours,
            finding_limit=args.finding_limit,
        )
        emit(asdict(report), unified_analysis_lines(report), as_json=args.json)
    elif args.command == "brand":
        if args.brand_action == "source-evaluation":
            report = BrandSourceEvaluationService().report()
            emit(
                asdict(report), brand_source_evaluation_lines(report),
                as_json=args.json,
            )
        elif args.brand_action == "source-coverage":
            report = BrandSourceCoverageService().report()
            emit(
                asdict(report), brand_source_coverage_lines(report),
                as_json=args.json,
            )
        elif args.brand_action == "profile-list":
            profiles = (
                {
                    "source": "maigret",
                    "display_name": "Maigret",
                    "safe": DEFAULT_PLATFORMS,
                    "extended": EXTENDED_PLATFORMS,
                },
                {
                    "source": "sherlock",
                    "display_name": "Sherlock",
                    "safe": SHERLOCK_DEFAULT_PLATFORMS,
                    "extended": SHERLOCK_EXTENDED_PLATFORMS,
                },
            )
            if args.source != "all":
                profiles = tuple(
                    profile for profile in profiles
                    if profile["source"] == args.source
                )
            emit(
                {"profiles": profiles},
                brand_username_profile_lines(profiles),
                as_json=args.json,
            )
        elif args.brand_action == "username-preview":
            preview_service = (
                BrandUsernamePreviewService(MaigretUsernameSource())
                if args.source == "maigret"
                else SherlockUsernamePreviewService(SherlockUsernameSource())
            )
            report = preview_service.preview(
                args.username,
                platforms=None if args.platforms is None else tuple(args.platforms),
                profile=args.profile,
                request_timeout=args.timeout,
            )
            emit(
                asdict(report), brand_username_preview_lines(report),
                as_json=args.json,
            )
        else:
            brand_watch_service = BrandUsernameWatchService(
                SQLiteBrandUsernameWatchRepository(settings.database),
                {
                    "maigret": MaigretUsernameSource(),
                    "sherlock": SherlockUsernameSource(),
                },
            )
            brand_review_service = BrandUsernameReviewService(
                SQLiteBrandUsernameReviewRepository(settings.database),
            )
            if args.brand_action == "watch-add":
                with LocalExecutionLock(settings.database).acquire():
                    result = brand_watch_service.add(
                        args.name,
                        args.username,
                        platforms=(
                            None if args.platforms is None else tuple(args.platforms)
                        ),
                        profile=args.profile,
                        source_key=args.source,
                    )
                emit(
                    asdict(result), brand_username_watch_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.brand_action == "watch-list":
                records = brand_watch_service.list(
                    active_only=not args.all, limit=args.limit,
                )
                emit(
                    {"records": [asdict(value) for value in records]},
                    brand_username_watch_list_lines(
                        records, active_only=not args.all,
                    ),
                    as_json=args.json,
                )
            elif args.brand_action == "watch-show":
                details = brand_watch_service.show(
                    args.watch_id,
                    event_limit=args.event_limit,
                    run_limit=args.run_limit,
                )
                emit(
                    asdict(details), brand_username_watch_detail_lines(details),
                    as_json=args.json,
                )
            elif args.brand_action == "watch-revoke":
                with LocalExecutionLock(settings.database).acquire():
                    result = brand_watch_service.revoke(
                        args.watch_id, reason=args.reason,
                    )
                emit(
                    asdict(result), brand_username_watch_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.brand_action == "watch-run":
                with LocalExecutionLock(settings.database).acquire():
                    report = brand_watch_service.run(
                        args.watch_id,
                        request_timeout=args.timeout,
                        item_limit=args.limit,
                    )
                    report = brand_review_service.decorate(report)
                if args.json:
                    print(json.dumps({
                        "ok": report.run.status == "complete",
                        "data": asdict(report),
                    }, ensure_ascii=True))
                else:
                    for line in brand_username_watch_run_lines(report):
                        print(line)
                return 0 if report.run.status == "complete" else 3
            elif args.brand_action == "watch-run-all":
                BrandUsernameWatchBatchService.validate_limits(
                    args.watch_limit,
                    args.timeout,
                )
                with LocalExecutionLock(settings.database).acquire():
                    report = BrandUsernameWatchBatchService(
                        brand_watch_service,
                    ).run(
                        max_watches=args.watch_limit,
                        request_timeout=args.timeout,
                        progress=terminal_progress(args.json),
                    )
                if args.json:
                    print(json.dumps({
                        "ok": report.failed_watch_count == 0,
                        "data": asdict(report),
                    }, ensure_ascii=True))
                else:
                    for line in brand_username_watch_batch_lines(report):
                        print(line)
                return 0 if report.failed_watch_count == 0 else 3
            elif args.brand_action == "watch-monitor":
                BrandUsernameWatchMonitorService.validate_limits(
                    args.cycles,
                    args.interval,
                    args.duration,
                    args.timeout,
                )
                with LocalExecutionLock(settings.database).acquire():
                    report = BrandUsernameWatchMonitorService(
                        brand_watch_service,
                    ).run(
                        args.watch_id,
                        max_cycles=args.cycles,
                        interval_seconds=args.interval,
                        max_duration_seconds=args.duration,
                        request_timeout=args.timeout,
                        progress=terminal_progress(args.json),
                    )
                if args.json:
                    print(json.dumps({
                        "ok": report.failed_cycles == 0,
                        "data": asdict(report),
                    }, ensure_ascii=True))
                else:
                    for line in brand_username_watch_monitor_lines(report):
                        print(line)
                return 0 if report.failed_cycles == 0 else 3
            elif args.brand_action == "watch-run-show":
                report = brand_review_service.decorate(brand_watch_service.show_run(
                    args.run_id, item_limit=args.limit,
                ))
                if args.json:
                    print(json.dumps({
                        "ok": report.run.status == "complete",
                        "data": asdict(report),
                    }, ensure_ascii=True))
                else:
                    for line in brand_username_watch_run_lines(report):
                        print(line)
                return 0 if report.run.status == "complete" else 3
            elif args.brand_action == "watch-review":
                with LocalExecutionLock(settings.database).acquire():
                    result = brand_review_service.decide(
                        args.watch_id,
                        args.platform,
                        decision=args.decision,
                        reason=args.reason,
                    )
                emit(
                    asdict(result), brand_username_review_mutation_lines(result),
                    as_json=args.json,
                )
            else:
                details = brand_review_service.show(
                    args.candidate_id, event_limit=args.event_limit,
                )
                emit(
                    asdict(details), brand_username_review_detail_lines(details),
                    as_json=args.json,
                )
    elif args.command == "ransomware":
        if args.ransomware_action == "source-evaluation":
            report = RansomwareSourceEvaluationService().report()
            emit(
                asdict(report), ransomware_source_evaluation_lines(report),
                as_json=args.json,
            )
        elif args.ransomware_action == "source-compare":
            comparison_service = RansomwareSourceComparisonService(
                SQLiteRansomwareClaimRepository(settings.database),
                SQLiteRansomLookClaimRepository(settings.database),
            )
            review_service = RansomwareSourceReviewService(
                SQLiteRansomwareSourceReviewRepository(settings.database),
                comparison_service,
            )
            report = review_service.decorate(
                comparison_service.compare(limit=args.limit)
            )
            emit(
                asdict(report), ransomware_source_comparison_lines(report),
                as_json=args.json,
            )
        elif args.ransomware_action == "source-review":
            comparison_service = RansomwareSourceComparisonService(
                SQLiteRansomwareClaimRepository(settings.database),
                SQLiteRansomLookClaimRepository(settings.database),
            )
            review_service = RansomwareSourceReviewService(
                SQLiteRansomwareSourceReviewRepository(settings.database),
                comparison_service,
            )
            with LocalExecutionLock(settings.database).acquire():
                result = review_service.decide(
                    args.comparison_id, decision=args.decision, reason=args.reason,
                )
            emit(
                asdict(result), ransomware_source_review_mutation_lines(result),
                as_json=args.json,
            )
        elif args.ransomware_action == "source-review-show":
            details = RansomwareSourceReviewService(
                SQLiteRansomwareSourceReviewRepository(settings.database),
                RansomwareSourceComparisonService(
                    SQLiteRansomwareClaimRepository(settings.database),
                    SQLiteRansomLookClaimRepository(settings.database),
                ),
            ).show(args.comparison_id, event_limit=args.event_limit)
            emit(
                asdict(details), ransomware_source_review_detail_lines(details),
                as_json=args.json,
            )
        elif args.ransomware_action == "recent":
            if args.source == "ransomlook":
                if args.status != "all":
                    raise ValidationError(
                        "RansomLook güncel/kaldırılmış ilan durumu sağlamaz; "
                        "--status all kullanın."
                    )
                report = RansomLookClaimService(RansomLookRansomwareSource()).recent(
                    args.query, limit=args.limit,
                )
                emit(
                    asdict(report), ransomlook_claim_report_lines(report),
                    as_json=args.json,
                )
            else:
                report = RansomwareClaimService(ThreatClusterRansomwareSource()).recent(
                    args.query, status=args.status, limit=args.limit,
                )
                emit(
                    asdict(report), ransomware_claim_report_lines(report),
                    as_json=args.json,
                )
        elif args.ransomware_action in {"refresh", "status"}:
            if args.source == "ransomlook":
                ransomlook_repository = SQLiteRansomLookClaimRepository(settings.database)
                ransomlook_history = RansomLookClaimHistoryService(
                    ransomlook_repository,
                    RansomLookRansomwareSource()
                    if args.ransomware_action == "refresh" else None,
                )
                if args.ransomware_action == "status":
                    status = ransomlook_history.status(run_limit=args.limit)
                    emit(
                        asdict(status), ransomlook_history_status_lines(status),
                        as_json=args.json,
                    )
                    return None
                # Audit the separate store before making the external request.
                ransomlook_history.status(run_limit=1)
                with LocalExecutionLock(settings.database).acquire():
                    report = ransomlook_history.refresh(item_limit=args.limit)
                if args.json:
                    print(json.dumps({
                        "ok": report.run.status == "complete", "data": asdict(report),
                    }, ensure_ascii=True))
                else:
                    for line in ransomlook_refresh_lines(report):
                        print(line)
                return 0 if report.run.status == "complete" else 3
            ransomware_repository = SQLiteRansomwareClaimRepository(settings.database)
            history = RansomwareClaimHistoryService(
                ransomware_repository,
                ThreatClusterRansomwareSource() if args.ransomware_action == "refresh" else None,
            )
            if args.ransomware_action == "status":
                status = history.status(run_limit=args.limit)
                emit(
                    asdict(status), ransomware_history_status_lines(status),
                    as_json=args.json,
                )
                return None
            # Validate the current schema and history before the internet request.
            history.status(run_limit=1)
            with LocalExecutionLock(settings.database).acquire():
                report = history.refresh(item_limit=args.limit)
            if args.json:
                print(json.dumps({
                    "ok": report.run.status == "complete", "data": asdict(report),
                }, ensure_ascii=True))
            else:
                for line in ransomware_refresh_lines(report):
                    print(line)
            return 0 if report.run.status == "complete" else 3
        elif args.ransomware_action == "watch-refresh-all":
            claim_repository = SQLiteRansomwareClaimRepository(settings.database)
            watch_service = RansomwareWatchService(
                SQLiteRansomwareWatchRepository(settings.database), claim_repository,
            )
            history = RansomwareClaimHistoryService(
                claim_repository, ThreatClusterRansomwareSource(),
            )
            combined = RansomwareWatchRefreshService(history, watch_service)
            combined.validate_limits(
                args.watch_limit, args.source_item_limit, args.watch_item_limit,
            )
            # Audit both stores and the complete active window before any internet request.
            history.status(run_limit=1)
            combined.preflight(max_watches=args.watch_limit)
            with LocalExecutionLock(settings.database).acquire():
                report = combined.run(
                    max_watches=args.watch_limit,
                    source_item_limit=args.source_item_limit,
                    watch_item_limit=args.watch_item_limit,
                    progress=terminal_progress(args.json),
                )
            if args.json:
                print(json.dumps({
                    "ok": report.refresh.run.status == "complete",
                    "data": asdict(report),
                }, ensure_ascii=True))
            else:
                for line in ransomware_watch_refresh_all_lines(report):
                    print(line)
            return 0 if report.refresh.run.status == "complete" else 3
        elif args.ransomware_action == "watch-monitor":
            RansomwareWatchMonitorService.validate_limits(
                args.cycles, args.interval, args.duration,
            )
            RansomwareWatchRefreshService.validate_limits(
                args.watch_limit, args.source_item_limit, args.watch_item_limit,
            )
            claim_repository = SQLiteRansomwareClaimRepository(settings.database)
            watch_service = RansomwareWatchService(
                SQLiteRansomwareWatchRepository(settings.database), claim_repository,
            )
            history = RansomwareClaimHistoryService(
                claim_repository, ThreatClusterRansomwareSource(),
            )
            combined = RansomwareWatchRefreshService(history, watch_service)
            # Audit source history and the complete active watch window before network.
            history.status(run_limit=1)
            combined.preflight(max_watches=args.watch_limit)
            with LocalExecutionLock(settings.database).acquire():
                report = RansomwareMonitorSessionService(
                    SQLiteRansomwareMonitorSessionRepository(settings.database),
                    RansomwareWatchMonitorService(combined),
                ).run(
                    max_cycles=args.cycles,
                    interval_seconds=args.interval,
                    max_duration_seconds=args.duration,
                    max_watches=args.watch_limit,
                    source_item_limit=args.source_item_limit,
                    watch_item_limit=args.watch_item_limit,
                    progress=terminal_progress(args.json),
                )
            successful = report.completed_cycles > 0 and report.failed_cycles == 0
            if args.json:
                print(json.dumps({
                    "ok": successful, "data": asdict(report),
                }, ensure_ascii=True))
            else:
                for line in ransomware_watch_monitor_lines(report):
                    print(line)
            return 0 if successful else 3
        elif args.ransomware_action in {"watch-monitor-list", "watch-monitor-show"}:
            claim_repository = SQLiteRansomwareClaimRepository(settings.database)
            watch_service = RansomwareWatchService(
                SQLiteRansomwareWatchRepository(settings.database), claim_repository,
            )
            history = RansomwareClaimHistoryService(
                claim_repository, ThreatClusterRansomwareSource(),
            )
            sessions = RansomwareMonitorSessionService(
                SQLiteRansomwareMonitorSessionRepository(settings.database),
                RansomwareWatchMonitorService(
                    RansomwareWatchRefreshService(history, watch_service),
                ),
            )
            if args.ransomware_action == "watch-monitor-list":
                records = sessions.list(limit=args.limit)
                emit(
                    {"sessions": [asdict(value) for value in records]},
                    ransomware_monitor_session_list_lines(records),
                    as_json=args.json,
                )
            else:
                details = sessions.show(
                    args.session_id, cycle_limit=args.cycle_limit,
                )
                emit(
                    asdict(details), ransomware_monitor_session_detail_lines(details),
                    as_json=args.json,
                )
        elif (
            args.ransomware_action in {
                "watch-add", "watch-list", "watch-show", "watch-revoke",
                "watch-run", "watch-run-show",
            }
            and args.source == "ransomlook"
        ):
            ransomlook_watch_service = RansomLookWatchService(
                SQLiteRansomLookWatchRepository(settings.database),
                SQLiteRansomLookClaimRepository(settings.database),
            )
            if args.ransomware_action == "watch-add":
                with LocalExecutionLock(settings.database).acquire():
                    result = ransomlook_watch_service.add(
                        args.name, args.query, kind=args.kind, match_mode=args.match,
                    )
                emit(
                    asdict(result), ransomlook_watch_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-list":
                records = ransomlook_watch_service.list(
                    active_only=not args.all, limit=args.limit,
                )
                emit(
                    {"records": [asdict(value) for value in records]},
                    ransomlook_watch_list_lines(records, active_only=not args.all),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-show":
                details = ransomlook_watch_service.show(
                    args.watch_id, event_limit=args.event_limit,
                    run_limit=args.run_limit,
                )
                emit(
                    asdict(details), ransomlook_watch_detail_lines(details),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-revoke":
                with LocalExecutionLock(settings.database).acquire():
                    result = ransomlook_watch_service.revoke(
                        args.watch_id, reason=args.reason,
                    )
                emit(
                    asdict(result), ransomlook_watch_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-run":
                with LocalExecutionLock(settings.database).acquire():
                    report = ransomlook_watch_service.run(
                        args.watch_id, item_limit=args.limit,
                    )
                emit(
                    asdict(report), ransomlook_watch_run_lines(report),
                    as_json=args.json,
                )
            else:
                report = ransomlook_watch_service.show_run(
                    args.run_id, item_limit=args.limit,
                )
                emit(
                    asdict(report), ransomlook_watch_run_lines(report),
                    as_json=args.json,
                )
        else:
            claim_repository = SQLiteRansomwareClaimRepository(settings.database)
            watch_service = RansomwareWatchService(
                SQLiteRansomwareWatchRepository(settings.database), claim_repository,
            )
            if args.ransomware_action == "watch-add":
                with LocalExecutionLock(settings.database).acquire():
                    result = watch_service.add(
                        args.name, args.query, kind=args.kind, match_mode=args.match,
                    )
                emit(
                    asdict(result), ransomware_watch_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-list":
                records = watch_service.list(
                    active_only=not args.all, limit=args.limit,
                )
                emit(
                    {"records": [asdict(value) for value in records]},
                    ransomware_watch_list_lines(records, active_only=not args.all),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-show":
                details = watch_service.show(
                    args.watch_id, event_limit=args.event_limit, run_limit=args.run_limit,
                )
                emit(
                    asdict(details), ransomware_watch_detail_lines(details),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-revoke":
                with LocalExecutionLock(settings.database).acquire():
                    result = watch_service.revoke(args.watch_id, reason=args.reason)
                emit(
                    asdict(result), ransomware_watch_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-run":
                with LocalExecutionLock(settings.database).acquire():
                    report = watch_service.run(args.watch_id, item_limit=args.limit)
                emit(
                    asdict(report), ransomware_watch_run_lines(report),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-timeline":
                report = RansomwareWatchTimelineService(
                    SQLiteRansomwareWatchRepository(settings.database),
                    claim_repository,
                ).show(args.watch_id, event_limit=args.event_limit)
                emit(
                    asdict(report), ransomware_watch_timeline_lines(report),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-identity-candidates":
                candidate_service = RansomwareWatchIdentityCandidateService(
                    SQLiteRansomwareWatchRepository(settings.database),
                    claim_repository,
                )
                review_service = RansomwareIdentityReviewService(
                    SQLiteRansomwareIdentityReviewRepository(settings.database),
                    candidate_service,
                )
                report = review_service.decorate(candidate_service.show(
                    args.watch_id, candidate_limit=args.candidate_limit,
                ))
                emit(
                    asdict(report), ransomware_watch_identity_candidate_lines(report),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-identity-review":
                review_service = RansomwareIdentityReviewService(
                    SQLiteRansomwareIdentityReviewRepository(settings.database),
                    RansomwareWatchIdentityCandidateService(
                        SQLiteRansomwareWatchRepository(settings.database),
                        claim_repository,
                    ),
                )
                with LocalExecutionLock(settings.database).acquire():
                    result = review_service.decide(
                        args.watch_id, args.candidate_id,
                        decision=args.decision, reason=args.reason,
                    )
                emit(
                    asdict(result), ransomware_identity_review_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.ransomware_action == "watch-identity-review-show":
                details = RansomwareIdentityReviewService(
                    SQLiteRansomwareIdentityReviewRepository(settings.database),
                    RansomwareWatchIdentityCandidateService(
                        SQLiteRansomwareWatchRepository(settings.database),
                        claim_repository,
                    ),
                ).show(args.candidate_id, event_limit=args.event_limit)
                emit(
                    asdict(details), ransomware_identity_review_detail_lines(details),
                    as_json=args.json,
                )
            else:
                report = watch_service.show_run(args.run_id, item_limit=args.limit)
                emit(
                    asdict(report), ransomware_watch_run_lines(report),
                    as_json=args.json,
                )
    elif args.command == "vuln":
        if args.vuln_action == "source-evaluation":
            report = VendorSourceEvaluationService().report()
            emit(
                asdict(report), vendor_source_evaluation_lines(report), as_json=args.json,
            )
            return None
        if args.vuln_action == "ubuntu-preview":
            report = UbuntuOsvPreviewService(UbuntuOsvAdvisorySource()).preview(
                args.cve_id,
                affected_limit=args.affected_limit,
                reference_limit=args.reference_limit,
            )
            emit(asdict(report), ubuntu_preview_lines(report), as_json=args.json)
            return None
        if args.vuln_action == "ubuntu-match":
            report = UbuntuPackageMatchService(UbuntuOsvAdvisorySource()).match(
                args.cve_id, ecosystem=args.ecosystem,
                source_package=args.source_package,
                installed_version=args.installed_version,
                reference_limit=args.reference_limit,
            )
            emit(asdict(report), ubuntu_package_match_lines(report), as_json=args.json)
            return None
        if args.vuln_action == "ubuntu-inventory-match":
            report = UbuntuInventoryMatchService(
                SQLiteUbuntuAssetPackageRepository(settings.database),
                UbuntuOsvAdvisorySource(),
            ).match(
                args.package_id, args.cve_id,
                reference_limit=args.reference_limit,
            )
            emit(asdict(report), ubuntu_inventory_match_lines(report), as_json=args.json)
            return None
        if args.vuln_action == "ubuntu-inventory-scan":
            report = UbuntuInventoryScanService(
                SQLiteUbuntuAssetPackageRepository(settings.database),
                UbuntuOsvAdvisorySource(),
            ).scan(
                args.cve_id, asset_value=args.domain, limit=args.limit,
                reference_limit=args.reference_limit,
            )
            emit(asdict(report), ubuntu_inventory_scan_lines(report), as_json=args.json)
            return None
        if args.vuln_action == "ubuntu-evidence-add":
            result = UbuntuExposureEvidenceService(
                SQLiteVulnerabilityExposureRepository(settings.database),
                SQLiteUbuntuAssetPackageRepository(settings.database),
                SQLiteVulnerabilityExposureEvidenceRepository(settings.database),
                UbuntuOsvAdvisorySource(),
            ).add(args.exposure_id, args.package_id, summary=args.summary)
            emit(
                asdict(result), ubuntu_evidence_selection_lines(result),
                as_json=args.json,
            )
            return None
        if args.vuln_action == "ubuntu-evidence-check":
            report = UbuntuEvidenceCheckService(
                SQLiteVulnerabilityExposureEvidenceRepository(settings.database),
                SQLiteVulnerabilityExposureRepository(settings.database),
                SQLiteUbuntuAssetPackageRepository(settings.database),
                UbuntuOsvAdvisorySource(),
            ).check(args.evidence_id)
            emit(
                asdict(report), ubuntu_evidence_check_lines(report),
                as_json=args.json,
            )
            return None
        if args.vuln_action == "ubuntu-evidence-plan":
            report = UbuntuEvidencePlanService(
                SQLiteVulnerabilityExposureEvidenceRepository(settings.database),
                SQLiteVulnerabilityExposureRepository(settings.database),
                SQLiteUbuntuAssetPackageRepository(settings.database),
            ).plan(asset_value=args.domain, limit=args.limit)
            emit(asdict(report), ubuntu_evidence_plan_lines(report), as_json=args.json)
            return None
        if args.vuln_action == "ubuntu-evidence-scan":
            report = UbuntuEvidenceScanService(
                SQLiteVulnerabilityExposureEvidenceRepository(settings.database),
                SQLiteVulnerabilityExposureRepository(settings.database),
                SQLiteUbuntuAssetPackageRepository(settings.database),
                UbuntuOsvAdvisorySource(),
            ).scan(asset_value=args.domain, limit=args.limit)
            emit(asdict(report), ubuntu_evidence_scan_lines(report), as_json=args.json)
            return None
        if args.vuln_action == "advisory-preview":
            report = OsvAdvisoryPreviewService(OsvDevAdvisorySource()).preview(
                args.cve_id, affected_limit=args.affected_limit,
                reference_limit=args.reference_limit,
            )
            emit(asdict(report), osv_advisory_preview_lines(report), as_json=args.json)
            return None
        if args.vuln_action == "advisory-evidence-add":
            result = OsvAdvisoryEvidenceService(
                SQLiteVulnerabilityExposureRepository(settings.database),
                SQLiteVulnerabilityExposureEvidenceRepository(settings.database),
                OsvDevAdvisorySource(),
            ).add(
                args.exposure_id, evidence_type=args.evidence_type,
                selected_reference=args.reference, summary=args.summary,
            )
            emit(asdict(result), osv_advisory_evidence_lines(result), as_json=args.json)
            return None
        if args.vuln_action == "vendor-preview":
            source = {
                "redhat": RedHatCsafVexSource(),
                "suse": SuseCsafVexSource(),
            }[args.provider]
            report = VendorAdvisoryPreviewService(source).preview(
                args.cve_id, product_limit=args.product_limit,
                remediation_limit=args.remediation_limit,
            )
            emit(
                asdict(report), vendor_advisory_preview_lines(report),
                as_json=args.json,
            )
            return None
        if args.vuln_action == "vendor-match":
            source = {"redhat": RedHatCsafVexSource()}[args.provider]
            report = VendorPackageMatchService(
                SQLiteAssetPackageRepository(settings.database), source,
            ).match(args.package_id, args.cve_id, match_limit=args.match_limit)
            emit(asdict(report), vendor_package_match_lines(report), as_json=args.json)
            return None
        if args.vuln_action in {
            "vendor-evidence-add", "vendor-evidence-list",
            "vendor-evidence-show", "vendor-evidence-revoke",
        }:
            vendor_evidence_service = VendorPackageEvidenceService(
                SQLiteVulnerabilityExposureRepository(settings.database),
                SQLiteAssetPackageRepository(settings.database),
                SQLiteVendorPackageEvidenceRepository(settings.database),
                RedHatCsafVexSource(),
            )
            if args.vuln_action == "vendor-evidence-add":
                result = vendor_evidence_service.add(
                    args.exposure_id, args.package_id,
                    selected_vex_product_id=args.vex_product_id,
                    summary=args.summary,
                )
                emit(
                    asdict(result), vendor_package_evidence_selection_lines(result),
                    as_json=args.json,
                )
            elif args.vuln_action == "vendor-evidence-list":
                records = vendor_evidence_service.list(
                    args.exposure_id, active_only=not args.all_entries, limit=args.limit,
                )
                emit(
                    {"records": [asdict(record) for record in records],
                     "active_only": not args.all_entries},
                    vendor_package_evidence_list_lines(
                        records, active_only=not args.all_entries,
                    ),
                    as_json=args.json,
                )
            elif args.vuln_action == "vendor-evidence-show":
                details = vendor_evidence_service.show(
                    args.evidence_id, event_limit=args.event_limit,
                )
                emit(
                    asdict(details), vendor_package_evidence_detail_lines(details),
                    as_json=args.json,
                )
            else:
                result = vendor_evidence_service.revoke(
                    args.evidence_id, reason=args.reason,
                )
                emit(
                    asdict(result), vendor_package_evidence_mutation_lines(result),
                    as_json=args.json,
                )
            return None
        if args.vuln_action == "change-notify":
            result = VulnerabilityNotificationService(
                SQLiteVulnerabilityReassessmentRepository(settings.database),
                SQLiteVulnerabilityNotificationRepository(settings.database),
            ).notify(
                include_closed=args.include_closed,
                include_suppressed=args.include_suppressed,
                limit=args.limit,
            )
            emit(
                asdict(result), vulnerability_notification_lines(result),
                as_json=args.json,
            )
            return None
        if args.vuln_action == "vendor-evidence-check":
            report = VendorPackageEvidenceCheckService(
                SQLiteVendorPackageEvidenceRepository(settings.database),
                SQLiteAssetPackageRepository(settings.database),
                RedHatCsafVexSource(),
            ).check(args.evidence_id)
            emit(
                asdict(report), vendor_package_evidence_check_lines(report),
                as_json=args.json,
            )
            return None
        if args.vuln_action == "overview":
            context = VulnerabilityContextService(
                SQLiteVulnerabilityContextRepository(settings.database),
            ).show(args.cve_id)
            emit(asdict(context), vulnerability_context_lines(context), as_json=args.json)
            return None
        if args.vuln_action == "plan":
            plan = NvdEnrichmentPlanService(
                SQLiteNvdEnrichmentPlanRepository(settings.database),
            ).build(min_epss=args.min_epss, limit=args.limit)
            emit(asdict(plan), nvd_enrichment_plan_lines(plan), as_json=args.json)
            return None
        if args.vuln_action == "nvd-window-plan":
            plan = NvdWindowService(
                SQLiteNvdWindowRepository(settings.database),
                SQLiteNvdRepository(settings.database),
            ).plan(
                window_start=args.window_start,
                window_end=args.window_end,
                page_size=args.page_size,
            )
            emit(asdict(plan), nvd_window_plan_lines(plan), as_json=args.json)
            return None
        if args.vuln_action == "nvd-window-list":
            result = NvdWindowService(
                SQLiteNvdWindowRepository(settings.database),
                SQLiteNvdRepository(settings.database),
            ).list(status=args.status, limit=args.limit)
            emit(asdict(result), nvd_window_list_lines(result), as_json=args.json)
            return None
        if args.vuln_action == "nvd-window-coverage":
            result = NvdWindowService(
                SQLiteNvdWindowRepository(settings.database),
                SQLiteNvdRepository(settings.database),
            ).coverage(
                requested_start=args.window_start, requested_end=args.window_end,
            )
            emit(
                asdict(result), nvd_window_coverage_lines(result), as_json=args.json,
            )
            return None
        if args.vuln_action == "nvd-window-gap-plan":
            result = NvdWindowService(
                SQLiteNvdWindowRepository(settings.database),
                SQLiteNvdRepository(settings.database),
            ).gap_plan(
                requested_start=args.window_start,
                requested_end=args.window_end,
                page_size=args.page_size,
                limit=args.limit,
            )
            emit(asdict(result), nvd_window_gap_plan_lines(result), as_json=args.json)
            return None
        if args.vuln_action == "nvd-window-gap-fetch":
            window_repository = SQLiteNvdWindowRepository(settings.database)
            nvd_repository = SQLiteNvdRepository(settings.database)
            if not 1 <= args.limit <= 3:
                raise ValidationError("NVD boşluk yürütme sınırı 1–3 arasında olmalı.")
            preflight = NvdWindowService(window_repository, nvd_repository)
            preflight.gap_plan(
                requested_start=args.window_start,
                requested_end=args.window_end,
                page_size=args.page_size,
                limit=args.limit,
            )
            nvd_repository.status(run_limit=1)
            with LocalExecutionLock(settings.database).acquire():
                result = NvdWindowService(
                    window_repository, nvd_repository, NvdWindowSource(),
                ).gap_fetch(
                    requested_start=args.window_start,
                    requested_end=args.window_end,
                    page_size=args.page_size,
                    limit=args.limit,
                )
            emit(asdict(result), nvd_window_gap_fetch_lines(result), as_json=args.json)
            return 3 if result.status == "stopped" else 0
        if args.vuln_action == "nvd-window-operations":
            result = NvdWindowService(
                SQLiteNvdWindowRepository(settings.database),
                SQLiteNvdRepository(settings.database),
            ).operations(
                requested_start=args.window_start,
                requested_end=args.window_end,
                recent_limit=args.recent_limit,
            )
            emit(asdict(result), nvd_window_operations_lines(result), as_json=args.json)
            return None
        if args.vuln_action == "nvd-window-show":
            result = NvdWindowService(
                SQLiteNvdWindowRepository(settings.database),
                SQLiteNvdRepository(settings.database),
            ).show(
                window_start=args.window_start, window_end=args.window_end,
                page_size=args.page_size, event_limit=args.event_limit,
            )
            emit(asdict(result), nvd_window_detail_lines(result), as_json=args.json)
            return None
        if args.vuln_action == "nvd-window-restart":
            window_repository = SQLiteNvdWindowRepository(settings.database)
            service = NvdWindowService(
                window_repository, SQLiteNvdRepository(settings.database),
            )
            service.show(
                window_start=args.window_start, window_end=args.window_end,
                page_size=args.page_size,
            )
            with LocalExecutionLock(settings.database).acquire():
                result = service.restart(
                    window_start=args.window_start, window_end=args.window_end,
                    page_size=args.page_size, reason=args.reason,
                )
            emit(asdict(result), nvd_window_restart_lines(result), as_json=args.json)
            return None
        if args.vuln_action == "nvd-window-fetch":
            window_repository = SQLiteNvdWindowRepository(settings.database)
            nvd_repository = SQLiteNvdRepository(settings.database)
            preflight = NvdWindowService(window_repository, nvd_repository)
            preflight.plan(
                window_start=args.window_start,
                window_end=args.window_end,
                page_size=args.page_size,
            )
            nvd_repository.status(run_limit=1)
            with LocalExecutionLock(settings.database).acquire():
                result = NvdWindowService(
                    window_repository, nvd_repository, NvdWindowSource(),
                ).fetch(
                    window_start=args.window_start,
                    window_end=args.window_end,
                    page_size=args.page_size,
                )
            emit(
                asdict(result), nvd_window_result_lines(result), as_json=args.json,
            )
            return 3 if result.status == "failed" else 0
        if args.vuln_action == "enrich-nvd":
            nvd_repository = SQLiteNvdRepository(settings.database)
            # A missing, legacy or corrupt database must stop before lock or network use.
            nvd_repository.status(run_limit=1)
            with LocalExecutionLock(settings.database).acquire():
                result = NvdEnrichmentBatchService(
                    SQLiteNvdEnrichmentPlanRepository(settings.database),
                    nvd_repository,
                    NvdCveSource(),
                ).run(min_epss=args.min_epss, limit=args.limit)
            emit(asdict(result), nvd_enrichment_batch_lines(result), as_json=args.json)
            return 0 if result.status == "complete" else 3
        if args.vuln_action == "tracked-nvd-plan":
            plan = TrackedNvdRefreshService(
                SQLiteTrackedNvdRefreshPlanRepository(settings.database),
                SQLiteNvdRepository(settings.database),
            ).plan(
                stale_after_hours=args.stale_after_hours,
                include_closed=args.include_closed,
                include_suppressed=args.include_suppressed,
                limit=args.limit,
            )
            emit(
                asdict(plan), tracked_nvd_refresh_plan_lines(plan), as_json=args.json,
            )
            return None
        if args.vuln_action == "tracked-nvd-refresh":
            plan_repository = SQLiteTrackedNvdRefreshPlanRepository(settings.database)
            nvd_repository = SQLiteNvdRepository(settings.database)
            preflight = TrackedNvdRefreshService(plan_repository, nvd_repository)
            # Missing, legacy or corrupt storage must stop before lock or network use.
            preflight.plan(
                stale_after_hours=args.stale_after_hours,
                include_closed=args.include_closed,
                include_suppressed=args.include_suppressed,
                limit=args.limit,
            )
            nvd_repository.status(run_limit=1)
            with LocalExecutionLock(settings.database).acquire():
                result = TrackedNvdRefreshService(
                    plan_repository, nvd_repository, NvdCveSource(),
                ).refresh(
                    stale_after_hours=args.stale_after_hours,
                    include_closed=args.include_closed,
                    include_suppressed=args.include_suppressed,
                    limit=args.limit,
                )
            emit(
                asdict(result), tracked_nvd_refresh_result_lines(result),
                as_json=args.json,
            )
            return 0 if result.status == "complete" else 3
        if args.vuln_action == "applicability":
            report = NvdApplicabilityService(
                SQLiteNvdApplicabilityRepository(settings.database),
            ).show(args.cve_id, limit=args.limit)
            emit(asdict(report), nvd_applicability_lines(report), as_json=args.json)
            return None
        if args.vuln_action == "assess-product":
            report = ProductVulnerabilityService(
                SQLiteProductVulnerabilityRepository(settings.database),
            ).assess(args.product_id, args.cve_id, limit=args.limit)
            emit(asdict(report), product_vulnerability_lines(report), as_json=args.json)
            return None
        if args.vuln_action == "asset-overview":
            report = ProductVulnerabilityOverviewService(
                SQLiteProductVulnerabilityOverviewRepository(settings.database),
            ).show(args.product_id, args.cve_id, limit=args.limit)
            emit(
                asdict(report), product_vulnerability_overview_lines(report),
                as_json=args.json,
            )
            return None
        if args.vuln_action == "match-products":
            report = ProductVulnerabilityInventoryService(
                SQLiteProductVulnerabilityInventoryRepository(settings.database),
            ).match(
                args.cve_id, include_unmatched=args.include_unmatched,
                limit=args.limit, condition_limit=args.condition_limit,
            )
            emit(
                asdict(report), product_vulnerability_inventory_lines(report),
                as_json=args.json,
            )
            return None
        if args.vuln_action in {
            "exposure-open", "exposure-review", "exposure-list", "exposure-show",
        }:
            exposure_service = VulnerabilityExposureService(
                SQLiteVulnerabilityExposureRepository(settings.database),
                SQLiteProductVulnerabilityRepository(settings.database),
            )
            if args.vuln_action == "exposure-open":
                result = exposure_service.open(
                    args.product_id, args.cve_id, reason=args.reason,
                    recheck_days=args.recheck_days,
                )
                emit(
                    asdict(result), vulnerability_exposure_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.vuln_action == "exposure-review":
                result = exposure_service.review(
                    args.exposure_id, status=args.status, reason=args.reason,
                    suppressed=args.suppressed, recheck_days=args.recheck_days,
                    clear_recheck=args.clear_recheck,
                )
                emit(
                    asdict(result), vulnerability_exposure_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.vuln_action == "exposure-list":
                report = exposure_service.list(
                    status=args.status, include_suppressed=args.include_suppressed,
                    limit=args.limit,
                )
                emit(asdict(report), vulnerability_exposure_list_lines(report), as_json=args.json)
            else:
                details = exposure_service.show(args.exposure_id, event_limit=args.event_limit)
                emit(
                    asdict(details), vulnerability_exposure_detail_lines(details),
                    as_json=args.json,
                )
            return None
        if args.vuln_action in {
            "exposure-suppress", "exposure-unsuppress", "exposure-suppression-show",
        }:
            suppression_service = VulnerabilityExposureSuppressionService(
                SQLiteVulnerabilityExposureSuppressionRepository(settings.database),
            )
            if args.vuln_action == "exposure-suppress":
                result = suppression_service.activate(
                    args.exposure_id, reason=args.reason, days=args.days,
                )
                emit(
                    asdict(result), vulnerability_exposure_suppression_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.vuln_action == "exposure-unsuppress":
                result = suppression_service.revoke(
                    args.exposure_id, reason=args.reason,
                )
                emit(
                    asdict(result), vulnerability_exposure_suppression_mutation_lines(result),
                    as_json=args.json,
                )
            else:
                details = suppression_service.show(
                    args.exposure_id, event_limit=args.event_limit,
                )
                emit(
                    asdict(details), vulnerability_exposure_suppression_detail_lines(details),
                    as_json=args.json,
                )
            return None
        if args.vuln_action in {
            "remediation-plan", "remediation-implement", "remediation-recheck",
            "remediation-cancel", "remediation-list", "remediation-show",
        }:
            remediation_service = VulnerabilityRemediationService(
                SQLiteVulnerabilityRemediationRepository(settings.database),
            )
            if args.vuln_action == "remediation-plan":
                result = remediation_service.plan(
                    args.exposure_id, recommendation=args.recommendation,
                    source_type=args.source_type, source_reference=args.source_reference,
                    reason=args.reason, recheck_days=args.recheck_days,
                )
                emit(
                    asdict(result), vulnerability_remediation_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.vuln_action == "remediation-implement":
                result = remediation_service.implement(
                    args.remediation_id, reason=args.reason,
                    evidence_reference=args.evidence_reference,
                    recheck_days=args.recheck_days,
                )
                emit(
                    asdict(result), vulnerability_remediation_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.vuln_action == "remediation-recheck":
                result = remediation_service.recheck(
                    args.remediation_id, outcome=args.outcome, reason=args.reason,
                    evidence_reference=args.evidence_reference,
                    recheck_days=args.recheck_days,
                )
                emit(
                    asdict(result), vulnerability_remediation_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.vuln_action == "remediation-cancel":
                result = remediation_service.cancel(args.remediation_id, reason=args.reason)
                emit(
                    asdict(result), vulnerability_remediation_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.vuln_action == "remediation-list":
                report = remediation_service.list(
                    exposure_id=args.exposure_id, state=args.state,
                    due_only=args.due_only, limit=args.limit,
                )
                emit(
                    asdict(report), vulnerability_remediation_list_lines(report),
                    as_json=args.json,
                )
            else:
                details = remediation_service.show(
                    args.remediation_id, event_limit=args.event_limit,
                )
                emit(
                    asdict(details), vulnerability_remediation_detail_lines(details),
                    as_json=args.json,
                )
            return None
        if args.vuln_action == "exposure-queue":
            report = VulnerabilityExposureQueueService(
                SQLiteVulnerabilityExposureQueueRepository(settings.database),
            ).show(
                min_epss=args.min_epss, include_closed=args.include_closed,
                include_suppressed=args.include_suppressed,
                evidence_filter=args.evidence, limit=args.limit,
                surface_stale_hours=args.surface_stale_hours,
            )
            emit(asdict(report), vulnerability_exposure_queue_lines(report), as_json=args.json)
            return None
        if args.vuln_action in {
            "reassessment-plan", "reassessment-run", "reassessment-runs",
            "reassessment-show",
        }:
            reassessment_service = VulnerabilityReassessmentService(
                SQLiteVulnerabilityReassessmentRepository(settings.database),
                SQLiteProductVulnerabilityRepository(settings.database),
            )
            if args.vuln_action == "reassessment-plan":
                report = reassessment_service.plan(
                    include_closed=args.include_closed,
                    include_suppressed=args.include_suppressed,
                    limit=args.limit,
                )
                emit(
                    asdict(report), vulnerability_reassessment_plan_lines(report),
                    as_json=args.json,
                )
            elif args.vuln_action == "reassessment-run":
                run = reassessment_service.run(
                    include_closed=args.include_closed,
                    include_suppressed=args.include_suppressed,
                    limit=args.limit,
                )
                emit(
                    asdict(run), vulnerability_reassessment_run_lines(run),
                    as_json=args.json,
                )
            elif args.vuln_action == "reassessment-runs":
                records = reassessment_service.list_runs(limit=args.limit)
                emit(
                    {"records": [asdict(record) for record in records]},
                    vulnerability_reassessment_run_list_lines(records),
                    as_json=args.json,
                )
            else:
                run = reassessment_service.show(args.run_id)
                emit(
                    asdict(run), vulnerability_reassessment_run_lines(run),
                    as_json=args.json,
                )
            return None
        if args.vuln_action in {
            "exposure-evidence-add", "exposure-evidence-list",
            "exposure-evidence-show", "exposure-evidence-revoke",
        }:
            evidence_service = VulnerabilityExposureEvidenceService(
                SQLiteVulnerabilityExposureEvidenceRepository(settings.database),
            )
            if args.vuln_action == "exposure-evidence-add":
                result = evidence_service.add(
                    args.exposure_id, evidence_type=args.evidence_type,
                    source_reference=args.reference, summary=args.summary,
                )
                emit(
                    asdict(result), vulnerability_exposure_evidence_mutation_lines(result),
                    as_json=args.json,
                )
            elif args.vuln_action == "exposure-evidence-list":
                records = evidence_service.list(
                    args.exposure_id, active_only=not args.all_entries, limit=args.limit,
                )
                emit(
                    {"records": [asdict(record) for record in records],
                     "active_only": not args.all_entries},
                    vulnerability_exposure_evidence_list_lines(
                        records, active_only=not args.all_entries,
                    ),
                    as_json=args.json,
                )
            elif args.vuln_action == "exposure-evidence-show":
                details = evidence_service.show(args.evidence_id, event_limit=args.event_limit)
                emit(
                    asdict(details), vulnerability_exposure_evidence_detail_lines(details),
                    as_json=args.json,
                )
            else:
                result = evidence_service.revoke(args.evidence_id, reason=args.reason)
                emit(
                    asdict(result), vulnerability_exposure_evidence_mutation_lines(result),
                    as_json=args.json,
                )
            return None
        selected_source = args.source
        kev_repository = SQLiteKevRepository(settings.database)
        epss_repository = SQLiteEpssRepository(settings.database)
        nvd_repository = SQLiteNvdRepository(settings.database)
        if args.vuln_action == "sync":
            if selected_source == "nvd":
                if args.cve is None:
                    raise ValidationError("NVD güncellemesi için --cve CVE-YIL-SAYI gerekli.")
                cve_id = normalize_cve_id(args.cve)
            else:
                if args.cve is not None:
                    raise ValidationError("--cve yalnız --source nvd ile kullanılabilir.")
                cve_id = None
            # A missing/legacy/corrupt database must stop before an internet request.
            selected_repository = {
                "kev": kev_repository, "epss": epss_repository, "nvd": nvd_repository,
            }[selected_source]
            selected_repository.status(run_limit=1)
            with LocalExecutionLock(settings.database).acquire():
                if selected_source == "kev":
                    run = KevCatalogService(kev_repository, CisaKevSource()).sync()
                elif selected_source == "epss":
                    run = EpssCatalogService(epss_repository, FirstEpssSource()).sync()
                else:
                    run = NvdCatalogService(nvd_repository, NvdCveSource()).sync(cve_id)
            if args.json:
                print(json.dumps({
                    "ok": run.status == "complete", "data": asdict(run),
                }, ensure_ascii=True))
            else:
                lines = {
                    "kev": kev_sync_lines,
                    "epss": epss_sync_lines,
                    "nvd": nvd_sync_lines,
                }[selected_source](run)
                for line in lines:
                    print(line)
            return 0 if run.status == "complete" else 3
        if selected_source == "epss":
            epss = EpssCatalogService(epss_repository)
            if args.vuln_action == "status":
                status = epss.status(run_limit=args.limit)
                emit(asdict(status), epss_status_lines(status), as_json=args.json)
            elif args.vuln_action == "list":
                active_only = not args.all_entries
                items = epss.list(active_only=active_only, limit=args.limit)
                emit(
                    {"active_only": active_only, "items": [asdict(item) for item in items]},
                    epss_list_lines(items, active_only=active_only), as_json=args.json,
                )
            elif args.vuln_action == "show":
                details = epss.show(args.cve_id)
                emit(asdict(details), epss_detail_lines(details), as_json=args.json)
            return None
        if selected_source == "nvd":
            nvd = NvdCatalogService(nvd_repository)
            if args.vuln_action == "status":
                status = nvd.status(run_limit=args.limit)
                emit(asdict(status), nvd_status_lines(status), as_json=args.json)
            elif args.vuln_action == "list":
                if args.all_entries:
                    raise ValidationError("--all NVD tek-CVE kayıtlarında kullanılmaz.")
                items = nvd.list(limit=args.limit)
                emit(
                    {"items": [asdict(item) for item in items]},
                    nvd_list_lines(items), as_json=args.json,
                )
            elif args.vuln_action == "show":
                details = nvd.show(args.cve_id, event_limit=args.event_limit)
                emit(asdict(details), nvd_detail_lines(details), as_json=args.json)
            return None
        kev = KevCatalogService(kev_repository)
        if args.vuln_action == "status":
            status = kev.status(run_limit=args.limit)
            emit(asdict(status), kev_status_lines(status), as_json=args.json)
        elif args.vuln_action == "list":
            active_only = not args.all_entries
            items = kev.list(active_only=active_only, limit=args.limit)
            emit(
                {"active_only": active_only, "items": [asdict(item) for item in items]},
                kev_list_lines(items, active_only=active_only), as_json=args.json,
            )
        elif args.vuln_action == "show":
            details = kev.show(args.cve_id, event_limit=args.event_limit)
            emit(asdict(details), kev_detail_lines(details), as_json=args.json)
    elif args.command == "monitor":
        monitor_repository = SQLiteMonitorRepository(settings.database)
        if args.monitor_action == "start":
            providers = tuple(SOURCE_LABELS) if args.source == "all" else (args.source,)
            # Reject bad limits/domains before creating a local record area.
            MonitorService.validate_spec(MonitorSpec(
                (args.domain,) if args.domain is not None else ("example.com",), providers,
                args.typos, "pending-validation", args.cycles, args.interval, args.duration,
            ))
            matcher = make_domain_matcher()
            resolver = matcher.resolver
            domains = [args.domain] if args.domain is not None else None
            if domains is not None:
                build_query_plan(
                    domains, resolver, typos=args.typos,
                    unicode_security=matcher.unicode_security,
                )
                repository.initialize()
                asset, _ = service.add(args.domain)
                domains = [asset.value]
            jobs = make_jobs(settings, repository)
            targets = jobs.discovery.validate_targets(domains, typos=args.typos)
            spec = MonitorSpec(targets, providers, args.typos, jobs.discovery.matcher.rule_version,
                               args.cycles, args.interval, args.duration)
            monitoring = MonitorService(monitor_repository, jobs)
            report = monitoring.start(spec, progress=terminal_progress(args.json))
            command = shlex.join(["./xti", "--data-dir", str(settings.data_dir), "monitor", "show", report.run.id])
            data = {"report": asdict(report), "show_command": command}
            if args.json:
                print(json.dumps({"ok": report.outcome == "complete", "data": data}, ensure_ascii=True))
            else:
                emit(data, monitor_report_lines(report, command), as_json=False)
            return 0 if report.outcome == "complete" else 3
        monitoring = MonitorService(monitor_repository)
        if args.monitor_action == "list":
            runs = monitoring.list(args.limit)
            emit({"runs": [asdict(item) for item in runs]}, monitor_run_lines(runs), as_json=args.json)
        elif args.monitor_action == "show":
            if not 1 <= args.limit <= 2000:
                raise ValidationError("Gösterilecek kaynak çalışması sınırı 1–2000 arasında olmalı.")
            details = monitoring.details(args.run_id)
            report = monitoring.summarize(details)
            command = shlex.join(["./xti", "--data-dir", str(settings.data_dir), "monitor", "show", report.run.id])
            entries = details.entries[-args.limit:]
            emit({"report": asdict(report), "entries": [asdict(entry) for entry in entries],
                  "total_entries": len(details.entries), "show_command": command},
                 monitor_report_lines(report, command) + monitor_entry_lines(details, args.limit), as_json=args.json)
        elif args.monitor_action == "recover":
            count = MonitorService(monitor_repository, make_jobs(settings, repository)).recover()
            emit({"recovered_runs": count}, [f"Kapatılan yarım izleme denemesi: {count}.",
                 "Tamamlanan kayıtlar korundu. Yeni izleme için monitor start kullan."], as_json=args.json)
    elif args.command == "allowlist":
        allow_repository = SQLiteAllowlistRepository(settings.database)
        allow_service = AllowlistService(repository, allow_repository, make_domain_matcher())
        if args.allowlist_action == "add":
            entry, changed = allow_service.add(
                args.asset, args.domain, args.reason, args.expires_in_days,
            )
            emit(asdict(entry), [
                ("Tam alan adı istisnası etkinleştirildi." if changed
                 else "Bu tam alan adı istisnası zaten etkindi; kayıt değiştirilmedi."),
                f"Kimlik: {safe_text(entry.id)}",
                f"İzlenen: {safe_text(entry.asset_value)} | İstisna: {safe_text(entry.domain)}",
                (f"Bitiş: {safe_text(entry.expires_at)}" if entry.expires_at
                 else "Bitiş: yok; açıkça kaldırılana kadar kalıcı."),
                "Ham gözlemler saklanır; bu adres için yeni bulgu ve bildirim üretilmez.",
            ], as_json=args.json)
        elif args.allowlist_action == "add-finding":
            details = FindingService(SQLiteFindingRepository(settings.database)).show(args.finding_id)
            entry, changed = allow_service.add(
                details.finding.asset_value, details.finding.domain, args.reason,
                args.expires_in_days,
            )
            emit(asdict(entry), [
                ("Bulgunun tam alan adı istisna olarak etkinleştirildi." if changed
                 else "Bu bulgunun tam alan adı istisnası zaten etkindi."),
                f"Kimlik: {safe_text(entry.id)}",
                "Mevcut bulgu, kanıt, karar ve bildirim silinmedi veya değiştirilmedi.",
            ], as_json=args.json)
        elif args.allowlist_action == "list":
            entries = allow_service.list(
                active_only=not args.all_entries, asset_value=args.asset, limit=args.limit,
            )
            lines = [
                (f"İstisnalar ({len(entries)}):" if entries else "Bu kapsamda istisna yok."),
            ]
            for entry in entries:
                state = (
                    "Etkin" if entry.active else
                    "Kaldırıldı" if entry.revoked else "Süresi doldu"
                )
                lines.append(
                    f"{safe_text(entry.id)} | {state} | {safe_text(entry.asset_value)} → "
                    f"{safe_text(entry.domain)} | {safe_text(entry.reason)} | "
                    + (f"Bitiş: {safe_text(entry.expires_at)}" if entry.expires_at else "Kalıcı")
                )
            emit({"entries": [asdict(entry) for entry in entries]}, lines, as_json=args.json)
        elif args.allowlist_action == "show":
            details = allow_service.show(args.entry_id)
            entry = details.entry
            lines = [
                f"İstisna: {safe_text(entry.id)}",
                "Durum: " + (
                    "Etkin" if entry.active else
                    "Kaldırıldı" if entry.revoked else "Süresi doldu"
                ),
                f"İzlenen: {safe_text(entry.asset_value)} | Tam adres: {safe_text(entry.domain)}",
                (f"Bitiş: {safe_text(entry.expires_at)}" if entry.expires_at
                 else "Bitiş: yok; kalıcı."),
                f"Güncel gerekçe: {safe_text(entry.reason)}",
                "İşlem geçmişi:",
            ]
            labels = {
                "added": "Eklendi", "reactivated": "Yeniden etkin",
                "updated": "Süresi güncellendi", "revoked": "Kaldırıldı",
            }
            for event in details.events:
                lines.append(
                    f"  {safe_text(event.created_at)} | {labels[event.action]} | "
                    f"{safe_text(event.reason)} | "
                    + (f"Bitiş: {safe_text(event.expires_at)}" if event.expires_at else "Kalıcı")
                )
            emit(asdict(details), lines, as_json=args.json)
        elif args.allowlist_action == "revoke":
            entry = allow_service.revoke(args.entry_id, args.reason)
            emit(asdict(entry), [
                "İstisna kaldırıldı; işlem geçmişi korundu.",
                f"İzlenen: {safe_text(entry.asset_value)} | Yeniden değerlendirilecek: "
                f"{safe_text(entry.domain)}",
                "Önceki bulgu ve kararlar değişmedi. Sonraki kaynak kaydı yeniden aday olabilir.",
            ], as_json=args.json)
    elif args.command == "surface":
        if args.surface_action == "relations":
            data, lines = execute_asset_relations_command(
                AssetRelationsService(SQLiteAssetRelationsRepository(settings.database)), args,
            )
            emit(data, lines, as_json=args.json)
            return None
        if args.surface_action == "source-evaluation":
            report = SurfaceSourceEvaluationService().report()
            emit(
                asdict(report), surface_source_evaluation_lines(report),
                as_json=args.json,
            )
            return None
        if args.surface_action == "nmap" and args.nmap_action == "capabilities":
            data = nmap_capabilities()
            emit(data, ["Nmap türleri: " + ", ".join(data["scan_types"]),
                        "NSE kontrolleri: " + ", ".join(s["id"] for s in data["scripts"])], as_json=args.json)
            return None
        if args.surface_action == "nmap" and args.nmap_action == "jobs":
            data, lines = execute_nmap_work_command(make_nmap_service(settings.database), args)
            emit(data, lines, as_json=args.json)
            return None
        if args.surface_action == "nmap" and args.nmap_action == "readiness":
            version, executable = NmapTcpConnectProbe().readiness()
            emit(
                {"state": "ready", "version": version, "executable": executable},
                nmap_readiness_lines(version, executable), as_json=args.json,
            )
            return None
        surface_repository = SQLiteSurfaceRepository(settings.database)
        surface_service = SurfaceService(repository, surface_repository)
        candidate_repository = SQLiteSurfaceCandidateRepository(settings.database)
        candidate_service = SurfaceDiscoveryService(repository, candidate_repository)
        if args.surface_action == "nmap" and args.nmap_action in {"targets", "plans"}:
            data, lines = execute_nmap_management_command(
                NmapManagementService(
                    repository, surface_repository,
                    SQLiteNmapManagementRepository(settings.database),
                    LocalExecutionLock(settings.database),
                ),
                args,
            )
            emit(data, lines, as_json=args.json)
            return None
        if args.surface_action == "cname":
            cname_repository = SQLiteSurfaceCnameRepository(settings.database)
            cname_service = SurfaceCnameService(
                repository, surface_repository, cname_repository,
            )
            if args.cname_action == "show":
                details = cname_service.show(
                    args.domain, history_limit=args.history_limit,
                )
                emit(asdict(details), cname_detail_lines(details), as_json=args.json)
            elif args.cname_action == "check":
                scope = cname_service.prepare(args.domain)
                progress = terminal_progress(args.json)
                if progress:
                    progress(f"Yetkili sınırlı CNAME kontrolü: {scope.asset_value}")
                with LocalExecutionLock(settings.database).acquire():
                    check = SurfaceCnameService(
                        repository, surface_repository, cname_repository,
                        GoogleCnameDnsProbe(),
                    ).check(scope.asset_value)
                status = cname_result_status(check)
                data = {"status": status, "check": asdict(check)}
                if args.json:
                    print(json.dumps({
                        "ok": status == "complete", "data": data,
                    }, ensure_ascii=True))
                else:
                    for line in cname_check_lines(check):
                        print(line)
                return 0 if status == "complete" else 3
        elif args.surface_action == "services":
            service_repository = SQLiteSurfaceServiceScanRepository(settings.database)
            service = SurfaceServiceScanService(
                repository, surface_repository, service_repository,
            )
            if args.service_action == "show":
                details = service.show(args.domain, history_limit=args.history_limit)
                emit(asdict(details), service_detail_lines(details), as_json=args.json)
            elif args.service_action == "check":
                scope, address, reason = service.prepare(
                    args.domain, args.address, args.reason,
                )
                progress = terminal_progress(args.json)
                if progress:
                    progress(
                        f"Yetkili sınırlı TCP servis kontrolü: "
                        f"{scope.asset_value} → {address}"
                    )
                with LocalExecutionLock(settings.database).acquire():
                    check = SurfaceServiceScanService(
                        repository, surface_repository, service_repository,
                        BoundedServicePortProbe(),
                    ).check(scope.asset_value, address, reason)
                status = service_result_status(check)
                notified = check.change.kind == "changed"
                data = {
                    "status": status, "check": asdict(check),
                    "notification_created": notified,
                }
                if args.json:
                    print(json.dumps({"ok": status == "complete", "data": data}, ensure_ascii=True))
                else:
                    for line in service_check_lines(check):
                        print(line)
                    if notified:
                        print("Değişiklik için yerel bildirim oluşturuldu: ./xti inbox")
                return 0 if status == "complete" else 3
        elif args.surface_action == "nmap":
            nmap_repository = SQLiteNmapScanRepository(settings.database)
            nmap_service = NmapSurfaceScanService(
                repository, surface_repository, nmap_repository,
            )
            if args.nmap_action == "show":
                details = nmap_service.show(
                    args.domain, history_limit=args.history_limit,
                )
                emit(asdict(details), nmap_detail_lines(details), as_json=args.json)
            elif args.nmap_action == "check":
                addresses = tuple(args.address)
                plan = build_nmap_scan_plan(
                    args.profile, target_count=len(addresses), ports=args.ports,
                    timeout_seconds=args.timeout_seconds, max_rate_pps=args.max_rate,
                    max_retries=args.max_retries, target_limit=args.target_limit,
                    max_probe_budget=args.max_probes,
                    confirm_wide_scan=args.confirm_wide_scan,
                    confirm_multi_target=args.confirm_multi_target,
                )
                scope, addresses, reason, plan = nmap_service.prepare(
                    args.domain, addresses, args.reason, plan,
                )
                probe = NmapTcpConnectProbe()
                probe.readiness()
                progress = terminal_progress(args.json)
                if progress:
                    progress(
                        f"Yetkili Nmap TCP kontrolü: {scope.asset_value} → "
                        f"{len(addresses)} kesin IP, {plan.port_count} port"
                    )
                with LocalExecutionLock(settings.database).acquire():
                    checks = NmapSurfaceScanService(
                        repository, surface_repository, nmap_repository, probe,
                    ).check(scope.asset_value, addresses, reason, plan)
                statuses = tuple(check.result.status for check in checks)
                status = (
                    "complete" if statuses and all(item == "complete" for item in statuses)
                    else "failed" if statuses and all(item == "failed" for item in statuses)
                    else "timeout" if statuses and all(item == "timeout" for item in statuses)
                    else "partial"
                )
                data = {
                    "status": status, "plan": asdict(plan),
                    "checks": [asdict(check) for check in checks],
                }
                if args.json:
                    print(json.dumps({
                        "ok": status == "complete", "data": data,
                    }, ensure_ascii=True))
                else:
                    print(
                        f"Nmap çalışma sonucu: {status} | "
                        f"{len(checks)} kesin IP kaydı"
                    )
                    for check in checks:
                        for line in nmap_check_lines(check, indent="  "):
                            print(line)
                return 0 if status == "complete" else 3
        elif args.surface_action == "mail":
            mail_repository = SQLiteSurfaceMailRepository(settings.database)
            mail_service = SurfaceMailService(
                repository, surface_repository, mail_repository,
            )
            if args.mail_action == "show":
                details = mail_service.show(
                    args.domain, history_limit=args.history_limit,
                )
                emit(asdict(details), mail_detail_lines(details), as_json=args.json)
            elif args.mail_action == "check":
                # Reject unknown or inactive roots before taking the shared
                # worker lock or opening the public DNS connection.
                scope = surface_service.scope_for_check(args.domain)
                progress = terminal_progress(args.json)
                if progress:
                    progress(
                        f"Yetkili MX/SPF/DMARC kontrolü: {scope.asset_value}"
                    )
                with LocalExecutionLock(settings.database).acquire():
                    check = SurfaceMailService(
                        repository, surface_repository, mail_repository,
                        GoogleMailDnsProbe(),
                    ).check(scope.asset_value)
                incomplete = bool(check.result.errors)
                statuses = (
                    check.result.mx_status,
                    check.result.spf_status,
                    check.result.dmarc_status,
                )
                status = (
                    "failed" if all(item == "failed" for item in statuses)
                    else "partial" if incomplete else "complete"
                )
                notified = check.change.kind == "changed"
                data = {
                    "status": status, "check": asdict(check),
                    "notification_created": notified,
                }
                if args.json:
                    print(json.dumps({"ok": not incomplete, "data": data}, ensure_ascii=True))
                else:
                    for line in mail_check_lines(check):
                        print(line)
                    if notified:
                        print("Değişiklik için yerel bildirim oluşturuldu: ./xti inbox")
                return 3 if incomplete else 0
        elif args.surface_action == "discover":
            # Validate the registered root and current schema before taking the
            # execution lock or opening the passive internet source.
            candidate_service.list(args.domain, status=None, limit=1)
            progress = terminal_progress(args.json)
            if progress:
                progress(
                    f"Pasif kaynakta alt alan adı aranıyor: {args.domain} | {args.source}"
                )
            source = (
                CrtShSource(cooldowns=SQLiteCooldownRepository(settings.database))
                if args.source == "crt.sh" else TheHarvesterArchiveSource()
            )
            with LocalExecutionLock(settings.database).acquire():
                result = SurfaceDiscoveryService(
                    repository, candidate_repository, source,
                ).discover(args.domain)
            data = asdict(result)
            if args.json:
                print(json.dumps({"ok": result.status == "complete", "data": data,
                                  }, ensure_ascii=True))
            else:
                for line in surface_discovery_lines(result):
                    print(line)
            return 0 if result.status == "complete" else 3
        elif args.surface_action == "watch":
            # Limits and root are rejected before ownership or passive network access.
            SurfaceWatchService.validate_limits(args.cycles, args.interval, args.duration)
            candidate_service.list(args.domain, status=None, limit=1)
            source = (
                CrtShSource(cooldowns=SQLiteCooldownRepository(settings.database))
                if args.source == "crt.sh" else TheHarvesterArchiveSource()
            )
            discovery = SurfaceDiscoveryService(
                repository, candidate_repository, source,
            )
            with LocalExecutionLock(settings.database).acquire():
                report = SurfaceWatchService(discovery).run(
                    args.domain, max_cycles=args.cycles,
                    interval_seconds=args.interval,
                    max_duration_seconds=args.duration,
                    progress=terminal_progress(args.json),
                )
            successful = (
                report.completed_cycles > 0 and report.partial == 0 and report.failed == 0
            )
            data = asdict(report)
            if args.json:
                print(json.dumps({"ok": successful, "data": data}, ensure_ascii=True))
            else:
                for line in surface_watch_lines(report):
                    print(line)
            return 0 if successful else 3
        elif args.surface_action == "monitor":
            checks = tuple(args.checks)
            SurfaceMonitorService.validate_limits(
                args.cycles, args.interval, args.duration,
            )
            if "services" in checks:
                if args.service_address is None or args.service_reason is None:
                    raise ValidationError(
                        "services kontrolü için --service-address ve --service-reason gerekli."
                    )
            elif args.service_address is not None or args.service_reason is not None:
                raise ValidationError(
                    "Servis IP bilgileri yalnız --checks içinde services seçilirse kullanılabilir."
                )

            runners = []
            for check_type in checks:
                if check_type == "web":
                    runners.append(WebSurfaceMonitorRunner(SurfaceService(
                        repository, surface_repository, HttpsTargetProbe(),
                    )))
                elif check_type == "mail":
                    runners.append(MailSurfaceMonitorRunner(SurfaceMailService(
                        repository, surface_repository,
                        SQLiteSurfaceMailRepository(settings.database),
                        GoogleMailDnsProbe(),
                    )))
                elif check_type == "services":
                    runners.append(ServiceSurfaceMonitorRunner(
                        SurfaceServiceScanService(
                            repository, surface_repository,
                            SQLiteSurfaceServiceScanRepository(settings.database),
                            BoundedServicePortProbe(),
                        ),
                        args.service_address, args.service_reason,
                    ))

            monitor = SurfaceMonitorService(runners)
            # Reject duplicates, missing scope and invalid exact IP before taking
            # the shared worker lock or opening any network connection.
            normalized = monitor.prepare(args.domain)
            with LocalExecutionLock(settings.database).acquire():
                report = monitor.run(
                    normalized, max_cycles=args.cycles,
                    interval_seconds=args.interval,
                    max_duration_seconds=args.duration,
                    progress=terminal_progress(args.json),
                )
            successful = (
                report.completed_cycles > 0
                and report.completed_checks == report.completed_cycles * len(report.checks)
                and report.partial_checks == 0
                and report.failed_checks == 0
            )
            if args.json:
                print(json.dumps({
                    "ok": successful, "data": asdict(report),
                }, ensure_ascii=True))
            else:
                for line in surface_monitor_report_lines(report):
                    print(line)
            return 0 if successful else 3
        elif args.surface_action == "candidates":
            status = None if args.status == "all" else args.status
            items = candidate_service.list(args.domain, status=status, limit=args.limit)
            asset_value = normalize_domain(args.domain)
            emit(
                {"asset_value": asset_value, "status": status,
                 "items": [asdict(item) for item in items]},
                surface_candidate_list_lines(items, asset_value=asset_value, status=status),
                as_json=args.json,
            )
        elif args.surface_action == "runs":
            runs = candidate_service.runs(args.domain, limit=args.limit)
            asset_value = normalize_domain(args.domain)
            emit(
                {"asset_value": asset_value, "runs": [asdict(run) for run in runs]},
                surface_discovery_run_list_lines(runs, asset_value=asset_value),
                as_json=args.json,
            )
        elif args.surface_action == "discovery-status":
            report = SurfaceDiscoveryStatusService(
                repository, candidate_repository,
            ).show(
                args.domain, provider=args.source,
                freshness_hours=args.stale_after_hours,
            )
            emit(
                asdict(report), surface_discovery_status_report_lines(report),
                as_json=args.json,
            )
        elif args.surface_action == "discovery-health":
            report = SurfaceDiscoveryStatusService(
                repository, candidate_repository,
            ).health(args.domain, freshness_hours=args.stale_after_hours)
            emit(
                asdict(report), surface_discovery_health_lines(report),
                as_json=args.json,
            )
        elif args.surface_action == "run":
            run = candidate_service.run(args.run_id)
            emit(asdict(run), surface_discovery_run_detail_lines(run), as_json=args.json)
        elif args.surface_action == "candidate":
            if args.candidate_action == "show":
                details = candidate_service.show(
                    args.candidate_id, source_limit=args.source_limit,
                )
                emit(
                    asdict(details), surface_candidate_detail_lines(details), as_json=args.json,
                )
            elif args.candidate_action == "decide":
                candidate, changed = candidate_service.decide(
                    args.candidate_id, args.status, args.reason,
                )
                labels = {
                    "pending": "Onay bekliyor", "owned": "Bana ait",
                    "rejected": "Reddedildi",
                }
                lines = [
                    ("Aday kararı kaydedildi." if changed
                     else "Aday zaten aynı durum ve gerekçedeydi; kayıt değiştirilmedi."),
                    f"Adres: {safe_text(candidate.domain)} | Durum: {labels[candidate.status]}",
                    "Bu sınıflandırma aktif DNS/TLS kontrolü başlatmadı.",
                ]
                if candidate.status == "owned":
                    lines.extend([
                        "Aktif kontrol istersen iki ayrı açık adım gerekir:",
                        f"  ./xti assets add {safe_text(candidate.domain)}",
                        f"  ./xti surface approve {safe_text(candidate.domain)} --reason \"Yetkili adresim\"",
                    ])
                emit(
                    {"candidate": asdict(candidate), "changed": changed}, lines,
                    as_json=args.json,
                )
        elif args.surface_action == "approve":
            scope, changed = surface_service.approve(args.domain, args.reason)
            emit({"scope": asdict(scope), "changed": changed}, [
                ("Adres dış yüzey kontrol kapsamına alındı." if changed
                 else "Adres zaten aynı gerekçeyle etkin kapsamdaydı; kayıt değiştirilmedi."),
                f"Adres: {safe_text(scope.asset_value)}",
                f"Gerekçe: {safe_text(scope.reason)}",
                "Bu kullanıcı yetki beyanıdır; teknik alan adı sahipliği doğrulaması değildir.",
                f"İlk temel kayıt: ./xti surface check {safe_text(scope.asset_value)}",
            ], as_json=args.json)
        elif args.surface_action == "revoke":
            scope = surface_service.revoke(args.domain, args.reason)
            emit({"scope": asdict(scope)}, [
                "Adres aktif dış yüzey kapsamından çıkarıldı; geçmiş korunuyor.",
                f"Adres: {safe_text(scope.asset_value)}",
            ], as_json=args.json)
        elif args.surface_action == "list":
            items = surface_service.list(
                active_only=not args.all_entries, limit=args.limit,
            )
            emit({"items": [asdict(item) for item in items]}, surface_list_lines(items),
                 as_json=args.json)
        elif args.surface_action == "show":
            details = surface_service.show(args.domain, history_limit=args.history_limit)
            emit(asdict(details), surface_detail_lines(details), as_json=args.json)
        elif args.surface_action == "overview":
            overview = SurfaceOverviewService(
                repository, SQLiteSurfaceOverviewRepository(settings.database),
            ).show(args.domain, candidate_limit=args.candidate_limit)
            emit(asdict(overview), surface_overview_lines(overview), as_json=args.json)
        elif args.surface_action == "freshness":
            report = SurfaceFreshnessService(
                repository, SQLiteSurfaceFreshnessRepository(settings.database),
            ).show(args.domain, freshness_hours=args.stale_after_hours)
            emit(
                asdict(report), surface_freshness_report_lines(report),
                as_json=args.json,
            )
        elif args.surface_action == "exposures":
            report = SurfaceExposureService(
                repository, SQLiteSurfaceFreshnessRepository(settings.database),
            ).show(args.domain, stale_after_hours=args.stale_after_hours)
            emit(
                asdict(report), surface_exposure_report_lines(report),
                as_json=args.json,
            )
        elif args.surface_action == "technologies":
            report = TechnologyService(
                repository, SQLiteSurfaceFreshnessRepository(settings.database),
            ).show(args.domain, stale_after_hours=args.stale_after_hours)
            emit(
                asdict(report), technology_report_lines(report),
                as_json=args.json,
            )
        elif args.surface_action == "inventory":
            report = SurfaceInventoryService(
                repository, SQLiteSurfaceInventoryRepository(settings.database),
            ).show(args.domain, status=args.status, limit=args.limit)
            emit(
                asdict(report), surface_inventory_report_lines(report),
                as_json=args.json,
            )
        elif args.surface_action == "check":
            # Reject missing, unknown or inactive scope before taking a lock or connecting.
            scope = surface_service.scope_for_check(args.domain)
            progress = terminal_progress(args.json)
            if progress:
                progress(f"Yetkili DNS/TLS dış yüzey kontrolü: {scope.asset_value}")
            with LocalExecutionLock(settings.database).acquire():
                check = SurfaceService(
                    repository, surface_repository, HttpsTargetProbe(),
                ).check(scope.asset_value)
            incomplete = surface_check_incomplete(check)
            notified = check.change.kind == "changed"
            data = {
                "status": "partial" if incomplete else "complete",
                "check": asdict(check), "notification_created": notified,
            }
            if args.json:
                print(json.dumps({"ok": not incomplete, "data": data}, ensure_ascii=True))
            else:
                for line in surface_check_lines(check):
                    print(line)
                if notified:
                    print("Değişiklik için yerel bildirim oluşturuldu: ./xti inbox")
            return 3 if incomplete else 0
    elif args.command == "status":
        report = StatusService(SQLiteStatusRepository(settings.database)).show(
            args.domain, freshness_hours=args.stale_after_hours, limit=args.limit,
        )
        prefix = ["./xti", "--data-dir", str(settings.data_dir)]
        commands = {
            name: shlex.join([*prefix, *suffix]) for name, suffix in {
                "inbox": ["inbox"], "jobs": ["jobs", "list"], "sources": ["sources"],
                "scan_example": ["scan", "example.com"],
                "status_domain": ["status", "ALAN_ADI", "--stale-after-hours", str(report.freshness_hours)],
                "status_more": ["status", "--limit", "100", "--stale-after-hours", str(report.freshness_hours)],
            }.items()
        }
        emit({**asdict(report), "commands": commands},
             status_lines(report, commands), as_json=args.json)
    elif args.command == "feedback":
        report = FeedbackService(SQLiteFeedbackRepository(settings.database)).show()
        emit(asdict(report), feedback_lines(report), as_json=args.json)
    elif args.command == "doctor":
        data = repository.inspect()
        data.update({"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                     "database": str(settings.database), "status": "ready"})
        emit(data, ["Kayıt alanı sağlıklı.", f"Kayıtlı adres: {data['asset_count']}",
                    f"Alınan gözlem: {data['observation_count']}",
                    f"Aday bulgu: {data['finding_count']}",
                    f"Kaydedilen hedef kontrolü: {data['assessment_count']}",
                    f"Bildirim kutusu: {data['unread_notification_count']} okunmamış / {data['notification_count']} toplam.",
                    f"Tam adres istisnası: {data['active_allowlist_count']} etkin / "
                    f"{data['expired_allowlist_count']} süresi dolmuş / "
                    f"{data['allowlist_count']} toplam.",
                    f"Dış yüzey kapsamı: {data['active_surface_scope_count']} etkin / "
                    f"{data['surface_scope_count']} toplam; kontrol: {data['surface_check_count']}.",
                    f"Varlık iş önemi: {data['active_asset_criticality_count']} etkin / "
                    f"{data['asset_criticality_count']} toplam.",
                    f"Tedarikçi envanteri: {data['active_supplier_count']} etkin / "
                    f"{data['supplier_count']} toplam; "
                    f"{data['supplier_event_count']} değişiklik olayı.",
                    f"Tedarikçi adayı: {data['current_supplier_candidate_count']} güncel / "
                    f"{data['pending_supplier_candidate_count']} inceleme bekliyor / "
                    f"{data['supplier_candidate_count']} toplam; "
                    f"{data['supplier_candidate_evidence_count']} kanıt / "
                    f"{data['supplier_candidate_resolution_count']} karar.",
                    f"Vaka yönetimi: {data['open_case_count']} açık / "
                    f"{data['case_count']} toplam; "
                    f"{data['active_case_evidence_count']} etkin kanıt / "
                    f"{data['open_case_task_count']} açık görev / "
                    f"{data['case_activity_count']} zaman çizelgesi olayı.",
                    f"Pasif alt alan adı adayı: {data['surface_candidate_count']} toplam / "
                    f"{data['pending_surface_candidate_count']} onay bekliyor; "
                    f"keşif çalışması: {data['surface_discovery_run_count']}.",
                    f"E-posta DNS temel kaydı: {data['surface_mail_check_count']} kontrol.",
                    f"Sınırlı servis envanteri: {data['surface_service_check_count']} kontrol.",
                    f"Yetkili Nmap TCP kanıtı: {data['surface_nmap_check_count']} hedef kaydı.",
                    f"CNAME hedef kanıtı: {data['surface_cname_check_count']} kontrol.",
                    f"CISA KEV kataloğu: {data['active_kev_entry_count']} etkin kayıt; "
                    f"kaynak çalışması: {data['vulnerability_source_run_count']}.",
                    f"FIRST EPSS kataloğu: {data['active_epss_score_count']} etkin puan.",
                    f"NVD CVE kayıtları: {data['nvd_cve_count']} yerel kayıt; "
                    f"tarih penceresi: {data['nvd_window_sync_count']} çalışma; "
                    f"yeniden başlatma: {data['nvd_window_restart_count']}.",
                    f"Doğrulanmış varlık ürünü: {data['active_asset_product_count']} etkin kayıt.",
                    f"Kesin Red Hat RPM paketi: {data['active_asset_package_count']} etkin kayıt.",
                    f"Doğrulanmış Ubuntu binary→source paketi: "
                    f"{data['active_ubuntu_asset_package_count']} etkin kayıt.",
                    f"Yerel IOC kataloğu: {data['cti_indicator_count']} gösterge / "
                    f"{data['active_cti_assertion_count']} etkin kaynak iddiası.",
                    f"Sosyal kullanıcı adı izlemesi: "
                    f"{data['active_brand_username_watch_count']} etkin / "
                    f"{data['brand_username_watch_count']} toplam; "
                    f"{data['brand_username_watch_run_count']} çalışma / "
                    f"{data['failed_brand_username_watch_run_count']} kaynak hatası.",
                    f"Sosyal profil kullanıcı kararı: "
                    f"{data['brand_username_review_candidate_count']} profil / "
                    f"{data['brand_username_review_event_count']} karar olayı.",
                    f"Sosyal profil olası taklit bildirimi: "
                    f"{data['unread_brand_username_review_notification_count']} "
                    f"okunmamış / "
                    f"{data['brand_username_review_notification_count']} toplam.",
                    f"Ransomware iddiası geçmişi: {data['ransomware_claim_run_count']} "
                    f"çalışma / {data['ransomware_claim_item_count']} fark öğesi.",
                    f"RansomLook ayrı geçmişi: {data['ransomlook_claim_run_count']} "
                    f"çalışma / {data['ransomlook_claim_item_count']} fark öğesi.",
                    f"RansomLook kuruluş izlemesi: "
                    f"{data['active_ransomlook_watch_count']} etkin / "
                    f"{data['ransomlook_watch_count']} toplam; "
                    f"{data['ransomlook_watch_run_count']} çalışma.",
                    f"Ransomware izlemesi: {data['active_ransomware_watch_count']} etkin / "
                    f"{data['ransomware_watch_count']} toplam; "
                    f"{data['ransomware_watch_run_count']} çalışma / "
                    f"{data['unread_ransomware_watch_notification_count']} okunmamış bildirim.",
                    f"Ransomware kimlik adayı incelemesi: "
                    f"{data['ransomware_identity_review_candidate_count']} aday / "
                    f"{data['ransomware_identity_review_event_count']} karar olayı.",
                    f"Ransomware kaynak karşılaştırma incelemesi: "
                    f"{data['ransomware_source_review_candidate_count']} aday / "
                    f"{data['ransomware_source_review_event_count']} karar olayı.",
                    f"Webhook: {data['active_webhook_destination_count']} etkin hedef / "
                    f"{data['webhook_destination_count']} toplam; "
                    f"{data['queued_webhook_delivery_count']} bekleyen, "
                    f"{data['failed_webhook_delivery_count']} başarısız, "
                    f"{data['delivered_webhook_delivery_count']} teslim edilmiş.",
                    f"Zafiyet maruziyet incelemesi: "
                    f"{data['open_vulnerability_exposure_count']} açık/görünür / "
                    f"{data['vulnerability_exposure_count']} toplam.",
                    f"Süreli maruziyet bastırma: "
                    f"{data['active_vulnerability_exposure_suppression_count']} etkin / "
                    f"{data['vulnerability_exposure_suppression_count']} toplam.",
                    f"Etkin maruziyet destek kanıtı: "
                    f"{data['active_vulnerability_exposure_evidence_count']} kayıt.",
                    f"Toplu zafiyet yeniden değerlendirme: "
                    f"{data['vulnerability_reassessment_run_count']} kayıtlı çalışma.",
                    f"Zafiyet değişiklik bildirimi: "
                    f"{data['vulnerability_change_notification_count']} kayıt.",
                    f"Etkin kesin Red Hat paket/VEX kanıtı: "
                    f"{data['active_vendor_package_evidence_count']} kayıt.",
                    f"Zafiyet düzeltme planı: "
                    f"{data['open_vulnerability_remediation_count']} açık / "
                    f"{data['vulnerability_remediation_count']} toplam.",
                    f"Arama işi: {data['job_count']}; sırada: {data['queued_job_count']}; "
                    f"yarım: {data['interrupted_job_count']}.",
                    f"Konum: {safe_text(settings.database)}",
                    "İnternet araması: ./xti scan | Düzenli kontrol: ./xti watch"], as_json=args.json)
    elif args.command == "migrate":
        data = repository.migrate()
        lines = ["Kayıt düzeni güncellendi." if data["changed"] else "Kayıt düzeni zaten güncel."]
        if data["backup"]:
            lines.append(f"Geçiş öncesi yedek: {safe_text(data['backup'])}")
        emit(data, lines, as_json=args.json)
    elif args.command == "assets" and args.asset_action == "add":
        asset, created = service.add(args.domain)
        message = "Adres eklendi" if created else "Adres zaten kayıtlı"
        emit({"asset": asdict(asset), "created": created},
             [f"{message}: {safe_text(asset.value)}"], as_json=args.json)
    elif args.command == "assets" and args.asset_action == "list":
        assets = service.list()
        lines = ["Kayıtlı adres yok. Örnek: ./xti assets add example.com"]
        if assets:
            lines = [f"Kayıtlı adresler ({len(assets)}):"]
            lines.extend(f"  {safe_text(asset.value)}" for asset in assets)
        emit({"assets": [asdict(asset) for asset in assets]}, lines, as_json=args.json)
    elif args.command == "assets" and args.asset_action in {
        "criticality-set", "criticality-clear", "criticality-show",
    }:
        criticality_service = AssetCriticalityService(
            SQLiteAssetCriticalityRepository(settings.database),
        )
        if args.asset_action == "criticality-set":
            result = criticality_service.set(
                args.domain, level=args.level, reason=args.reason,
            )
            emit(
                asdict(result), asset_criticality_mutation_lines(result),
                as_json=args.json,
            )
        elif args.asset_action == "criticality-clear":
            result = criticality_service.clear(args.domain, reason=args.reason)
            emit(
                asdict(result), asset_criticality_mutation_lines(result),
                as_json=args.json,
            )
        else:
            details = criticality_service.show(
                args.domain, event_limit=args.event_limit,
            )
            emit(
                asdict(details), asset_criticality_detail_lines(details),
                as_json=args.json,
            )
    elif args.command == "cases":
        case_service = make_case_service(settings)
        if args.case_action == "create":
            result = case_service.create(
                args.title, summary=args.summary, priority=args.priority,
                reason=args.reason,
            )
            emit(asdict(result), case_mutation_lines(result), as_json=args.json)
        elif args.case_action == "list":
            records = case_service.list(
                status=None if args.status == "all" else args.status,
                priority=None if args.priority == "all" else args.priority,
                limit=args.limit,
            )
            emit(
                {"cases": [asdict(record) for record in records]},
                case_list_lines(records), as_json=args.json,
            )
        elif args.case_action in {"show", "report"}:
            details = case_service.show(
                args.case_id, evidence_limit=args.evidence_limit,
                task_limit=args.task_limit, activity_limit=args.activity_limit,
            )
            lines = case_report_lines(details) if args.case_action == "report" else case_detail_lines(details)
            emit(asdict(details), lines, as_json=args.json)
        elif args.case_action == "update":
            result = case_service.update(
                args.case_id, title=args.title, summary=args.summary,
                priority=args.priority, reason=args.reason,
            )
            emit(asdict(result), case_mutation_lines(result), as_json=args.json)
        elif args.case_action == "status":
            result = case_service.set_status(
                args.case_id, args.status, reason=args.reason,
                resolution=args.resolution,
            )
            emit(asdict(result), case_mutation_lines(result), as_json=args.json)
        elif args.case_action == "note-add":
            activity = case_service.add_note(
                args.case_id, args.body, kind=args.kind,
            )
            emit(asdict(activity), case_note_lines(activity), as_json=args.json)
        elif args.case_action == "evidence-add":
            result = case_service.add_evidence(
                args.case_id, args.type, args.evidence_id, reason=args.reason,
            )
            emit(
                asdict(result), case_evidence_mutation_lines(result),
                as_json=args.json,
            )
        elif args.case_action == "evidence-show":
            evidence = case_service.evidence_show(args.case_id, args.evidence_link_id)
            emit(asdict(evidence), case_evidence_detail_lines(evidence), as_json=args.json)
        elif args.case_action == "evidence-remove":
            result = case_service.remove_evidence(
                args.case_id, args.evidence_link_id, reason=args.reason,
            )
            emit(
                asdict(result), case_evidence_mutation_lines(result),
                as_json=args.json,
            )
        elif args.case_action == "task-add":
            result = case_service.add_task(
                args.case_id, args.title, due_at=args.due_at, reason=args.reason,
            )
            emit(asdict(result), case_task_mutation_lines(result), as_json=args.json)
        else:
            result = case_service.update_task(
                args.case_id, args.task_id, status=args.status, reason=args.reason,
            )
            emit(asdict(result), case_task_mutation_lines(result), as_json=args.json)
    elif args.command == "suppliers":
        if args.supplier_action in {"watch", "watch-run-show"}:
            data, lines = execute_supplier_watch(args, SupplierWatchService(
                SQLiteSupplierWatchRepository(settings.database), LocalExecutionLock(settings.database),
            ))
            emit(data, lines, as_json=args.json)
            return None
        supplier_service = SupplierService(SQLiteSupplierRepository(settings.database))
        if args.supplier_action == "add":
            result = supplier_service.add(
                args.name,
                domain=args.domain,
                relationship_type=args.relationship,
                criticality=args.criticality,
                reason=args.reason,
            )
            emit(asdict(result), supplier_mutation_lines(result), as_json=args.json)
        elif args.supplier_action == "list":
            records = supplier_service.list(
                active_only=not args.all_entries, limit=args.limit,
            )
            emit(
                {
                    "suppliers": [asdict(record) for record in records],
                    "active_only": not args.all_entries,
                },
                supplier_list_lines(records, active_only=not args.all_entries),
                as_json=args.json,
            )
        elif args.supplier_action == "show":
            details = supplier_service.show(
                args.supplier_id, event_limit=args.event_limit,
            )
            emit(asdict(details), supplier_detail_lines(details), as_json=args.json)
        elif args.supplier_action == "update":
            result = supplier_service.update(
                args.supplier_id,
                name=args.name,
                relationship_type=args.relationship,
                criticality=args.criticality,
                reason=args.reason,
            )
            emit(asdict(result), supplier_mutation_lines(result), as_json=args.json)
        elif args.supplier_action == "revoke":
            result = supplier_service.revoke(
                args.supplier_id, reason=args.reason,
            )
            emit(asdict(result), supplier_mutation_lines(result), as_json=args.json)
        elif args.supplier_action in {
            "event-list", "event-show", "risk-list", "risk-show",
        }:
            event_service = SupplierThreatEventService(
                SQLiteSupplierRepository(settings.database),
                SQLiteRansomwareClaimRepository(settings.database),
                SQLiteRansomLookClaimRepository(settings.database),
            )
            if args.supplier_action == "event-list":
                report = event_service.list(
                    supplier_id=args.supplier, source=args.source, limit=args.limit,
                )
                emit(
                    asdict(report), supplier_threat_event_report_lines(report),
                    as_json=args.json,
                )
            elif args.supplier_action == "event-show":
                details = event_service.show(args.event_id)
                emit(
                    asdict(details), supplier_threat_event_detail_lines(details),
                    as_json=args.json,
                )
            else:
                risk_service = SupplierRiskService(
                    SQLiteSupplierRepository(settings.database),
                    SQLiteSupplierCandidateRepository(settings.database),
                    event_service,
                )
                if args.supplier_action == "risk-list":
                    report = risk_service.list(limit=args.limit)
                    emit(
                        asdict(report), supplier_risk_report_lines(report),
                        as_json=args.json,
                    )
                else:
                    details = risk_service.show(args.supplier_id)
                    emit(
                        asdict(details), supplier_risk_detail_lines(details),
                        as_json=args.json,
                    )
        else:
            candidate_service = SupplierCandidateService(
                SQLiteSupplierDependencySource(settings.database),
                SQLiteSupplierCandidateRepository(settings.database),
                PublicSuffixResolver(unicode_security=unicode_security_profile()),
            )
            if args.supplier_action == "candidate-refresh":
                result = candidate_service.refresh(limit=args.limit)
                emit(
                    asdict(result), supplier_candidate_refresh_lines(result),
                    as_json=args.json,
                )
            elif args.supplier_action == "candidate-list":
                status = None if args.status == "all" else args.status
                records = candidate_service.list(
                    status=status, current_only=not args.include_historical,
                    limit=args.limit,
                )
                emit(
                    {
                        "candidates": [asdict(record) for record in records],
                        "status": status,
                        "current_only": not args.include_historical,
                    },
                    supplier_candidate_list_lines(
                        records, status=status,
                        current_only=not args.include_historical,
                    ),
                    as_json=args.json,
                )
            elif args.supplier_action == "candidate-show":
                details = candidate_service.show(
                    args.candidate_id, evidence_limit=args.evidence_limit,
                    resolution_limit=args.resolution_limit,
                )
                emit(
                    asdict(details), supplier_candidate_detail_lines(details),
                    as_json=args.json,
                )
            else:
                result = candidate_service.review(
                    args.candidate_id, decision=args.decision,
                    supplier_id=args.supplier, reason=args.reason,
                )
                emit(
                    asdict(result), supplier_candidate_mutation_lines(result),
                    as_json=args.json,
                )
    elif args.command == "products":
        product_service = AssetProductService(SQLiteAssetProductRepository(settings.database))
        if args.product_action == "add":
            result = product_service.add(
                args.domain, part=args.part, vendor=args.vendor, product=args.product,
                version=args.version, evidence=args.evidence,
            )
            emit(asdict(result), product_mutation_lines(result), as_json=args.json)
        elif args.product_action == "list":
            records = product_service.list(
                asset_value=args.domain, active_only=not args.all_entries, limit=args.limit,
            )
            emit(
                {"records": [asdict(record) for record in records],
                 "active_only": not args.all_entries},
                product_list_lines(records, active_only=not args.all_entries),
                as_json=args.json,
            )
        elif args.product_action == "show":
            details = product_service.show(args.product_id, event_limit=args.event_limit)
            emit(asdict(details), product_detail_lines(details), as_json=args.json)
        elif args.product_action == "revoke":
            result = product_service.revoke(args.product_id, reason=args.reason)
            emit(asdict(result), product_mutation_lines(result), as_json=args.json)
    elif args.command == "ioc":
        if args.ioc_action == "lifecycle":
            from xti.interfaces.ioc_lifecycle import execute_ioc_lifecycle
            data, lines = execute_ioc_lifecycle(settings.database, args)
            emit(data, lines, as_json=args.json)
            return None
        if args.ioc_action in {"sync", "status"}:
            feed_repository, feed_source = make_cti_feed(settings, args.source)
            if args.ioc_action == "status":
                status = CtiFeedService(feed_repository).status(run_limit=args.limit)
                emit(asdict(status), cti_feed_status_lines(status), as_json=args.json)
                return None
            # Fail closed before making any internet request.
            feed_repository.status(run_limit=1)
            with LocalExecutionLock(settings.database).acquire():
                run = CtiFeedService(
                    feed_repository, feed_source,
                ).sync()
            if args.json:
                print(json.dumps({
                    "ok": run.status == "complete", "data": asdict(run),
                }, ensure_ascii=True))
            else:
                for line in cti_feed_sync_lines(run):
                    print(line)
            return 0 if run.status == "complete" else 3
        ioc_service = CtiIndicatorService(
            SQLiteCtiIndicatorRepository(settings.database),
        )
        if args.ioc_action == "add":
            result = ioc_service.add(
                args.indicator_type, args.value, source_name=args.source_name,
                source_reference=args.source_reference, confidence=args.confidence,
                description=args.description, valid_from=args.valid_from,
                valid_until=args.valid_until, observed_at=args.observed_at,
            )
            emit(
                asdict(result), cti_indicator_mutation_lines(result),
                as_json=args.json,
            )
        elif args.ioc_action == "list":
            summaries = ioc_service.list(
                indicator_type=args.indicator_type,
                active_only=not args.all_entries, limit=args.limit,
            )
            emit(
                {
                    "summaries": [asdict(summary) for summary in summaries],
                    "active_only": not args.all_entries,
                },
                cti_indicator_list_lines(
                    summaries, active_only=not args.all_entries,
                ),
                as_json=args.json,
            )
        elif args.ioc_action == "show":
            details = ioc_service.show(
                args.indicator_id, assertion_limit=args.assertion_limit,
                event_limit=args.event_limit,
            )
            emit(
                asdict(details), cti_indicator_detail_lines(details),
                as_json=args.json,
            )
        elif args.ioc_action == "lookup":
            details = ioc_service.lookup(
                args.indicator_type, args.value,
                assertion_limit=args.assertion_limit,
                event_limit=args.event_limit,
            )
            emit(
                asdict(details), cti_indicator_detail_lines(details),
                as_json=args.json,
            )
        elif args.ioc_action == "revoke":
            result = ioc_service.revoke(args.assertion_id, reason=args.reason)
            emit(
                asdict(result), cti_indicator_mutation_lines(result),
                as_json=args.json,
            )
    elif args.command == "cti":
        knowledge_repository = SQLiteCtiKnowledgeRepository(settings.database)
        service = CtiKnowledgeService(knowledge_repository)
        if args.cti_action == "context":
            result = CtiContextService(SQLiteCtiContextRepository(settings.database)).show(
                indicator_type=args.indicator_type, value=args.value, entity_id=args.entity,
                include_inactive=args.include_inactive, offset=args.offset, limit=args.limit,
                source_offset=args.source_offset, source_limit=args.source_limit,
            )
            emit(asdict(result), cti_context_lines(result), as_json=args.json)
        elif args.cti_action in {"attack-status", "attack-search", "attack-show"}:
            result, lines = run_attack_catalog_command(
                args, AttackCatalogService(SQLiteAttackCatalogRepository(settings.database)),
            )
            emit(asdict(result), lines, as_json=args.json)
        elif args.cti_action == "attack-sync":
            with LocalExecutionLock(settings.database).acquire():
                result = AttackSyncService(
                    knowledge_repository, MitreAttackSource(),
                ).sync()
            emit(asdict(result), attack_sync_lines(result), as_json=args.json)
        elif args.cti_action == "stix-export":
            build = StixExportService(
                SQLiteCtiIndicatorRepository(settings.database),
            ).build(indicator_type=args.indicator_type)
            artifact = write_stix_bundle(build.bundle, Path(args.destination))
            emit(
                {
                    "generated_at": build.generated_at,
                    "indicator_type": build.indicator_type,
                    "indicator_count": build.indicator_count,
                    "object_count": build.object_count,
                    "artifact": asdict(artifact),
                },
                stix_export_lines(build, artifact),
                as_json=args.json,
            )
        elif args.cti_action == "search":
            report = service.search(
                args.query, kind=args.kind, entity_type=args.entity_type,
                indicator_type=args.indicator_type,
                active_only=not args.all_entries, limit=args.limit,
            )
            emit(asdict(report), cti_search_lines(report), as_json=args.json)
        elif args.cti_action == "watch-add":
            saved = CtiSavedSearchService(SQLiteCtiSavedSearchRepository(settings.database))
            result = saved.add(
                args.name, args.query, kind=args.kind, entity_type=args.entity_type,
                indicator_type=args.indicator_type, active_only=not args.all_entries,
            )
            emit(
                asdict(result), cti_saved_search_mutation_lines(result), as_json=args.json,
            )
        elif args.cti_action == "watch-list":
            saved = CtiSavedSearchService(SQLiteCtiSavedSearchRepository(settings.database))
            records = saved.list(active_only=not args.all_entries, limit=args.limit)
            emit(
                {"records": [asdict(value) for value in records],
                 "active_only": not args.all_entries},
                cti_saved_search_list_lines(records, active_only=not args.all_entries),
                as_json=args.json,
            )
        elif args.cti_action == "watch-show":
            saved = CtiSavedSearchService(SQLiteCtiSavedSearchRepository(settings.database))
            details = saved.show(
                args.saved_search_id, event_limit=args.event_limit, run_limit=args.run_limit,
            )
            emit(
                asdict(details), cti_saved_search_detail_lines(details), as_json=args.json,
            )
        elif args.cti_action == "watch-run":
            saved = CtiSavedSearchService(SQLiteCtiSavedSearchRepository(settings.database))
            report = saved.run(args.saved_search_id, item_limit=args.item_limit)
            emit(asdict(report), cti_saved_search_run_lines(report), as_json=args.json)
        elif args.cti_action == "watch-run-all":
            CtiSavedSearchBatchService.validate_limits(
                args.search_limit, args.item_limit,
            )
            saved = CtiSavedSearchService(SQLiteCtiSavedSearchRepository(settings.database))
            with LocalExecutionLock(settings.database).acquire():
                report = CtiSavedSearchBatchService(saved).run(
                    max_searches=args.search_limit, item_limit=args.item_limit,
                    progress=terminal_progress(args.json),
                )
            emit(
                asdict(report), cti_saved_search_batch_lines(report), as_json=args.json,
            )
        elif args.cti_action == "watch-run-show":
            saved = CtiSavedSearchService(SQLiteCtiSavedSearchRepository(settings.database))
            report = saved.show_run(args.run_id, item_limit=args.item_limit)
            emit(asdict(report), cti_saved_search_run_lines(report), as_json=args.json)
        elif args.cti_action == "watch-monitor":
            CtiSavedSearchMonitorService.validate_limits(
                args.cycles, args.interval, args.duration,
            )
            if type(args.item_limit) is not int or not 1 <= args.item_limit <= 500:
                raise ValidationError("CTI izleme sonuç sınırı 1–500 arasında olmalı.")
            saved = CtiSavedSearchService(SQLiteCtiSavedSearchRepository(settings.database))
            with LocalExecutionLock(settings.database).acquire():
                report = CtiSavedSearchMonitorService(saved).run(
                    args.saved_search_id, max_cycles=args.cycles,
                    interval_seconds=args.interval,
                    max_duration_seconds=args.duration,
                    item_limit=args.item_limit,
                    progress=terminal_progress(args.json),
                )
            emit(
                asdict(report), cti_saved_search_monitor_lines(report), as_json=args.json,
            )
        elif args.cti_action in {"watch-tag-add", "watch-tag-remove"}:
            journal = CtiHuntingJournalService(
                SQLiteCtiHuntingJournalRepository(settings.database),
            )
            if args.cti_action == "watch-tag-add":
                result = journal.add_tag(args.saved_search_id, args.tag)
            else:
                result = journal.remove_tag(args.saved_search_id, args.tag)
            emit(
                asdict(result), cti_hunting_tag_mutation_lines(result), as_json=args.json,
            )
        elif args.cti_action == "watch-note-add":
            journal = CtiHuntingJournalService(
                SQLiteCtiHuntingJournalRepository(settings.database),
            )
            note = journal.add_note(
                args.saved_search_id, args.text, note_kind=args.kind, run_id=args.run_id,
            )
            emit(asdict(note), cti_hunting_note_lines(note), as_json=args.json)
        elif args.cti_action == "watch-journal":
            journal = CtiHuntingJournalService(
                SQLiteCtiHuntingJournalRepository(settings.database),
            )
            report = journal.journal(
                args.saved_search_id, note_limit=args.note_limit,
                event_limit=args.event_limit,
            )
            emit(asdict(report), cti_hunting_journal_lines(report), as_json=args.json)
        elif args.cti_action == "watch-revoke":
            saved = CtiSavedSearchService(SQLiteCtiSavedSearchRepository(settings.database))
            result = saved.revoke(args.saved_search_id, reason=args.reason)
            emit(
                asdict(result), cti_saved_search_mutation_lines(result), as_json=args.json,
            )
        elif args.cti_action == "entity-add":
            result = service.add_entity(
                args.entity_type, args.name, aliases=args.alias,
                source_name=args.source_name,
                source_reference=args.source_reference,
                confidence=args.confidence, description=args.description,
                observed_at=args.observed_at,
            )
            emit(asdict(result), cti_entity_mutation_lines(result), as_json=args.json)
        elif args.cti_action == "entity-list":
            records = service.list_entities(
                entity_type=args.entity_type, active_only=not args.all_entries,
                limit=args.limit,
            )
            emit(
                {"records": [asdict(value) for value in records],
                 "active_only": not args.all_entries},
                cti_entity_list_lines(records, active_only=not args.all_entries),
                as_json=args.json,
            )
        elif args.cti_action == "entity-show":
            details = service.show_entity(
                args.entity_id, assertion_limit=args.assertion_limit,
                event_limit=args.event_limit,
            )
            emit(asdict(details), cti_entity_detail_lines(details), as_json=args.json)
        elif args.cti_action == "entity-lookup":
            details = service.lookup_entity(
                args.entity_type, args.name, assertion_limit=args.assertion_limit,
                event_limit=args.event_limit,
            )
            emit(asdict(details), cti_entity_detail_lines(details), as_json=args.json)
        elif args.cti_action == "entity-revoke":
            result = service.revoke_entity(args.assertion_id, reason=args.reason)
            emit(asdict(result), cti_entity_mutation_lines(result), as_json=args.json)
        elif args.cti_action == "relation-add":
            result = service.add_relationship(
                args.source_entity_id, args.relationship_type,
                target_entity_id=args.target_entity_id,
                target_indicator_id=args.target_indicator_id,
                source_name=args.source_name,
                source_reference=args.source_reference,
                confidence=args.confidence, description=args.description,
                observed_at=args.observed_at,
            )
            emit(
                asdict(result), cti_relationship_mutation_lines(result),
                as_json=args.json,
            )
        elif args.cti_action == "relation-list":
            records = service.list_relationships(
                entity_id=args.entity_id, active_only=not args.all_entries,
                limit=args.limit,
            )
            emit(
                {"records": [asdict(value) for value in records],
                 "active_only": not args.all_entries},
                cti_relationship_list_lines(records, active_only=not args.all_entries),
                as_json=args.json,
            )
        elif args.cti_action == "relation-show":
            details = service.show_relationship(
                args.relationship_id, assertion_limit=args.assertion_limit,
                event_limit=args.event_limit,
            )
            emit(
                asdict(details), cti_relationship_detail_lines(details),
                as_json=args.json,
            )
        elif args.cti_action == "relation-revoke":
            result = service.revoke_relationship(args.assertion_id, reason=args.reason)
            emit(
                asdict(result), cti_relationship_mutation_lines(result),
                as_json=args.json,
            )
    elif args.command == "packages":
        package_service = AssetPackageService(SQLiteAssetPackageRepository(settings.database))
        if args.package_action == "add":
            result = package_service.add(
                args.domain, provider=args.provider, name=args.name, epoch=args.epoch,
                version=args.version, release=args.release,
                architecture=args.architecture, distribution_cpe=args.distribution_cpe,
                source_rpm=args.source_rpm, evidence=args.evidence,
            )
            emit(asdict(result), package_mutation_lines(result), as_json=args.json)
        elif args.package_action == "list":
            records = package_service.list(
                asset_value=args.domain, active_only=not args.all_entries, limit=args.limit,
            )
            emit(
                {"records": [asdict(record) for record in records],
                 "active_only": not args.all_entries},
                package_list_lines(records, active_only=not args.all_entries),
                as_json=args.json,
            )
        elif args.package_action == "show":
            details = package_service.show(args.package_id, event_limit=args.event_limit)
            emit(asdict(details), package_detail_lines(details), as_json=args.json)
        elif args.package_action == "revoke":
            result = package_service.revoke(args.package_id, reason=args.reason)
            emit(asdict(result), package_mutation_lines(result), as_json=args.json)
    elif args.command == "ubuntu-packages":
        ubuntu_package_service = UbuntuAssetPackageService(
            SQLiteUbuntuAssetPackageRepository(settings.database),
        )
        if args.ubuntu_package_action == "add":
            result = ubuntu_package_service.add(
                args.domain, ecosystem=args.ecosystem,
                binary_name=args.binary_name, binary_version=args.binary_version,
                architecture=args.architecture, source_name=args.source_name,
                source_version=args.source_version, evidence=args.evidence,
            )
            emit(
                asdict(result), ubuntu_package_mutation_lines(result),
                as_json=args.json,
            )
        elif args.ubuntu_package_action == "list":
            records = ubuntu_package_service.list(
                asset_value=args.domain, active_only=not args.all_entries,
                limit=args.limit,
            )
            emit(
                {"records": [asdict(record) for record in records],
                 "active_only": not args.all_entries},
                ubuntu_package_list_lines(
                    records, active_only=not args.all_entries,
                ),
                as_json=args.json,
            )
        elif args.ubuntu_package_action == "show":
            details = ubuntu_package_service.show(
                args.package_id, event_limit=args.event_limit,
            )
            emit(
                asdict(details), ubuntu_package_detail_lines(details),
                as_json=args.json,
            )
        elif args.ubuntu_package_action == "revoke":
            result = ubuntu_package_service.revoke(
                args.package_id, reason=args.reason,
            )
            emit(
                asdict(result), ubuntu_package_mutation_lines(result),
                as_json=args.json,
            )
    elif args.command == "backup":
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = args.output or (
            settings.data_dir / "backups" / f"xti-{timestamp}-{uuid4().hex[:8]}.db"
        )
        backup = repository.backup(destination)
        emit({"backup": str(backup)},
             [f"Yedek oluşturuldu: {safe_text(backup)}",
              "Disk arızasına karşı bu dosyanın bir kopyasını ayrı ortamda tut."],
             as_json=args.json)
    elif args.command == "restore":
        SQLiteAssetRepository.restore(args.source, settings.database)
        emit({"database": str(settings.database)},
             [f"Yedek geri yüklendi: {safe_text(settings.database)}"], as_json=args.json)
    elif args.command == "storage":
        maintenance = MaintenanceService(SQLiteMaintenanceRepository(settings.database))
        if args.storage_action == "status":
            usage = maintenance.usage()
            emit(asdict(usage), [
                f"Veritabanı dosyası: {usage.database_bytes} bayt.",
                f"SQLite içindeki toplam alan: {usage.logical_bytes} bayt.",
                f"SQLite'ın tekrar kullanabileceği boş alan: {usage.reusable_bytes} bayt.",
                f"Ek işlem dosyaları: WAL {usage.wal_bytes}; journal {usage.journal_bytes} bayt.",
                f"Gözlem: {usage.observation_count}; bulguya bağlı ve korunan: {usage.linked_observation_count}.",
                "Bu sayılar yedek/rapor klasörlerini kapsamaz. Boş alan diskten silinmiş alan değildir.",
                "Temizlik önizlemesi: ./xti storage cleanup",
            ], as_json=args.json)
        elif args.storage_action == "readiness":
            report = StorageReadinessService(
                SQLiteMaintenanceRepository(settings.database),
                FileSystemStorageReadinessRepository(settings.database),
            ).show(
                backup_stale_after_days=args.backup_stale_after_days,
                retention_days=args.retention_days,
            )
            emit(
                asdict(report), storage_readiness_report_lines(report),
                as_json=args.json,
            )
        elif args.storage_action == "history":
            runs = maintenance.history(args.limit)
            lines = [f"Son temizlik işlemleri ({len(runs)}):"]
            for item in runs:
                lines.extend([
                    f"{safe_text(item.created_at)} | Silinen bağlantısız gözlem: {item.deleted_count}",
                    f"  İşlem: {safe_text(item.id)} | Yedek: {safe_text(item.backup)}",
                ])
            emit({"runs": [asdict(item) for item in runs]}, lines, as_json=args.json)
        elif args.storage_action == "cleanup":
            if args.apply_token is not None and (
                len(args.apply_token) != 64 or any(char not in "0123456789abcdef" for char in args.apply_token)
            ):
                raise ValidationError("Geçerli önizleme kimliği gerekli; önce storage cleanup çalıştır.")
            plan = maintenance.preview(older_than_days=args.older_than_days, limit=args.limit)
            if args.apply_token is None:
                command = shlex.join([
                    "./xti", "--data-dir", str(settings.data_dir), "storage", "cleanup",
                    "--older-than-days", str(args.older_than_days), "--limit", str(args.limit),
                    "--apply", plan.token,
                ])
                lines = [
                    "Temizlik önizlemesi; hiçbir kayıt silinmedi.",
                    f"Kesim zamanı: {safe_text(plan.cutoff)} (UTC); yaş ilk yerel kayda göre hesaplanır.",
                    f"Uygun bağlantısız gözlem: {plan.eligible_count}; bu işlemde seçilen: {plan.selected_count}.",
                    f"Sonraki işleme kalan: {plan.remaining_count}.",
                    f"Bağlantısı nedeniyle korunan: {plan.protected_count}; geçersiz/gelecek zamanı nedeniyle korunan: {plan.invalid_time_count}.",
                    "Bulgular, bağlı kanıtlar, kararlar, hedef kontrolleri ve arama geçmişi korunur.",
                ]
                if plan.selected_count:
                    lines.extend(["Bu seçimi yedek alarak uygulayan komut:", safe_text(command)])
                emit({"plan": asdict(plan), "apply_command": command if plan.selected_count else None},
                     lines, as_json=args.json)
            else:
                with LocalExecutionLock(settings.database).acquire():
                    result = maintenance.apply(args.apply_token, older_than_days=args.older_than_days, limit=args.limit)
                lines = [f"Silinen bağlantısız eski gözlem: {result.deleted_count}."]
                if result.backup:
                    lines.append(f"Temizlik öncesi yedek: {safe_text(result.backup)}")
                lines.append("Bulgular ve inceleme geçmişi korundu. Dosya küçültme yapılmadı.")
                emit(asdict(result), lines, as_json=args.json)
    elif args.command in {"scan", "watch"}:
        if not 1 <= args.check_limit <= 20:
            raise ValidationError("Hedef kontrol sınırı 1–20 arasında olmalı.")
        if args.command == "scan" and args.queue and args.check:
            raise ValidationError("--queue ile --check birlikte kullanılamaz; iş bitince findings check çalıştır.")
        if args.command == "watch":
            if not 300 <= args.interval <= 86400:
                raise ValidationError("Arama aralığı 300–86400 saniye arasında olmalı.")
            if args.cycles is not None and not 1 <= args.cycles <= 10000:
                raise ValidationError("Tur sayısı 1–10000 arasında olmalı.")
        matcher = make_domain_matcher()
        resolver = matcher.resolver
        domains = [args.domain] if args.domain is not None else None
        if domains is not None:
            # Bad input must not create storage or register an asset.
            build_query_plan(
                domains, resolver, typos=args.typos,
                unicode_security=matcher.unicode_security,
            )
            repository.initialize()
            asset, _ = service.add(args.domain)
            domains = [asset.value]
        jobs = make_jobs(settings, repository)
        progress = terminal_progress(args.json)
        providers = tuple(SOURCE_LABELS) if args.source == "all" else (args.source,)
        if args.command == "scan" and args.queue:
            queued = [jobs.enqueue(domains, typos=args.typos, provider=provider) for provider in providers]
            data = {"jobs": [asdict(job) for job in queued]} if args.source == "all" else {"job": asdict(queued[0])}
            lines = [f"İş sıraya kaydedildi ({safe_text(job.provider)}): {safe_text(job.id)}" for job in queued]
            lines.append("Sıradaki tek işi başlatmak için: ./xti worker --once")
            emit(data, lines, as_json=args.json)
            return 0
        if args.typos and progress:
            progress(
                "Ek arama: ad başına en fazla 6 yazım ve 4 Punycode benzer-harf "
                "varyantı; bütün olasılıkları kapsamaz."
            )
        cycles = 0
        exit_code = 0
        while True:
            queued = [jobs.enqueue(domains, typos=args.typos, provider=provider) for provider in providers]
            attempts = []
            for job in queued:
                if progress:
                    progress(f"Kaynak: {SOURCE_LABELS[job.provider]}")
                try:
                    attempt = jobs.run(job.id, progress=progress)
                except WorkerBusyError as exc:
                    raise WorkerBusyError(
                        f"{exc} Bekleyen işler sırada korundu. 'xti jobs list' ile görebilirsin."
                    ) from exc
                assert attempt is not None
                attempts.append((job.provider, attempt))
            checks = None
            if args.check:
                with LocalExecutionLock(settings.database).acquire():
                    checks = make_enrichment(settings).check_pending(
                        limit=args.check_limit, domains=domains, progress=progress,
                    )
            cycle_code = emit_cycle(attempts, as_json=args.json, checks=checks) if args.source == "all" else (
                emit_attempt(attempts[0][1], as_json=args.json, provider=attempts[0][0], checks=checks)
            )
            exit_code = max(exit_code, cycle_code)
            cycles += 1
            if args.command == "scan" or (args.cycles is not None and cycles >= args.cycles):
                return exit_code
            if progress:
                progress(f"Sonraki kontrol {args.interval} saniye sonra. Durdurmak için Ctrl+C.")
            time.sleep(args.interval)
    elif args.command == "jobs":
        jobs = make_jobs(settings, repository)
        if args.job_action == "list":
            saved = jobs.list(args.status, args.limit)
            lines = ["Kayıtlı arama işi yok."] if not saved else [f"Son arama işleri ({len(saved)}):"]
            for job in saved:
                lines.append(
                    f"  {safe_text(job.id)} | {JOB_LABELS[job.status]} | "
                    f"{safe_text(job.provider)} | {safe_text(', '.join(job.targets))} | Deneme: {job.attempt_count}"
                )
            emit({"jobs": [asdict(job) for job in saved]}, lines, as_json=args.json)
        elif args.job_action == "show":
            details = jobs.show(args.job_id)
            lines = [
                f"İş: {safe_text(details.job.id)} | {JOB_LABELS[details.job.status]}",
                f"İzlenen: {safe_text(', '.join(details.job.targets))}",
                f"Kaynak: {safe_text(details.job.provider)}",
            ]
            if not details.attempts:
                lines.append("Henüz çalıştırılmadı.")
            for attempt in details.attempts:
                lines.extend([
                    f"Deneme {attempt.number}: {JOB_LABELS[attempt.status]}",
                    f"  Başlangıç: {safe_text(attempt.started_at)}",
                    f"  Bitiş: {safe_text(attempt.finished_at or 'henüz kaydedilmedi')}",
                ])
                if attempt.progress:
                    lines.append(f"  Son adım: {safe_text(attempt.progress)}")
                if attempt.error:
                    lines.append(f"  Hata: {safe_text(attempt.error)}")
                for query in attempt.queries:
                    lines.append(
                        f"  Sorgu: {safe_text(query.pattern)} | {JOB_LABELS[query.status]} | "
                        f"Kaynak kaydı: {query.record_count}"
                    )
                    lines.append(f"  Kaynak bağlantısı: {safe_text(query.source_url)}")
                    if query.error:
                        lines.append(f"  Hata: {safe_text(query.error)}")
                    for warning in query.warnings:
                        lines.append(f"  Uyarı: {safe_text(warning)}")
                    for note in query.coverage_notes:
                        lines.append(f"  Kapsam: {safe_text(note)}")
                    if query.skipped_names:
                        lines.append(f"  Karşılaştırılamayan ad: {query.skipped_names}")
                if attempt.result:
                    lines.append(f"  Bu denemede yeni aday: {attempt.result.summary.findings_created}")
                    if attempt.result.summary.findings_suppressed:
                        lines.append(
                            "  Tam adres istisnasıyla bastırılan aday: "
                            f"{attempt.result.summary.findings_suppressed}"
                        )
            emit(asdict(details), lines, as_json=args.json)
        elif args.job_action == "recover":
            recovered = jobs.recover()
            emit({"recovered": recovered}, [
                f"Yarım kaldığı kaydedilen iş: {recovered}.",
                "Bu işlem arama başlatmaz. Görmek için: ./xti jobs list --status interrupted",
            ], as_json=args.json)
        elif args.job_action == "retry":
            attempt = jobs.retry(args.job_id, progress=terminal_progress(args.json))
            return emit_attempt(attempt, as_json=args.json, provider=jobs.show(attempt.job_id).job.provider)
    elif args.command == "worker":
        jobs = make_jobs(settings, repository)
        attempt = jobs.run(progress=terminal_progress(args.json))
        provider = jobs.show(attempt.job_id).job.provider if attempt is not None else "crt.sh"
        return emit_attempt(attempt, as_json=args.json, provider=provider)
    elif args.command == "sources" and args.source_action == "contribution":
        if (args.domain is None) == (args.organization is None):
            raise ValidationError("Kaynak katkısı için yalnız domain veya --organization seçin.")
        if args.organization is not None:
            report = OrganizationContributionService(SQLiteOrganizationContributionRepository(settings.database)).show(
                args.organization, family=args.family,
                offset=args.offset if args.offset is not None else 0,
                limit=args.limit if args.limit is not None else 20,
                detail_offset=args.detail_offset, detail_limit=args.detail_limit,
            )
            lines = organization_contribution_lines(report)
        else:
            if args.offset is not None or args.limit is not None:
                raise ValidationError("Domain ayrıntısı için --detail-offset/--detail-limit kullanın; --offset/--limit kuruluş içindir.")
            report = SourceContributionService(SQLiteSourceContributionRepository(settings.database)).show(
                args.domain, family=args.family, detail_offset=args.detail_offset, detail_limit=args.detail_limit,
            )
            lines = source_contribution_lines(report)
        emit(asdict(report), lines, as_json=args.json)
    elif args.command == "sources" and args.source_action == "status":
        report = SourceReadinessService(
            SQLiteSourceReadinessRepository(settings.database),
        ).show(domain=args.domain, stale_after_hours=args.stale_after_hours)
        emit(asdict(report), source_readiness_lines(report, details=args.details), as_json=args.json)
    elif args.command == "sources":
        catalog = SourceCatalogService().list()
        statuses = make_jobs(settings, repository).source_status()
        recorded_waits = SQLiteCooldownRepository(settings.database).list()
        now = datetime.now(timezone.utc)
        cooldowns = []
        for item in recorded_waits:
            deadline = parse_timestamp(item.not_before)
            assert deadline is not None  # The repository validates every persisted timestamp.
            seconds = max(0, math.ceil((deadline - now).total_seconds()))
            cooldowns.append({**asdict(item), "active": seconds > 0, "remaining_seconds": seconds})
        lines = [
            "Kullanılan kaynaklar ve bağlantılar:",
            "Bu katalog yapılandırmayı açıklar; şu anki erişilebilirliği ölçmez.",
        ]
        for item in catalog:
            lines.extend([
                f"{safe_text(item.label)} ({safe_text(item.identifier)}):",
                f"  Amaç: {safe_text(item.purpose)}",
                f"  Erişim: {safe_text(item.access)}",
                "  İzlenen hedefe doğrudan bağlantı: "
                + ("Evet; yalnız açık kullanıcı komutuyla." if item.contacts_monitored_target
                   else "Hayır."),
                f"  Komutlar: {safe_text(', '.join(item.commands))}",
            ])
            for limit in item.limits:
                lines.append(f"  Sınır: {safe_text(limit)}")
            lines.append(f"  Resmî başvuru: {safe_text(item.reference_url)}")
        lines.append("Son kaydedilen pasif arama sonuçları:")
        if not statuses:
            lines.append("Henüz kaynak kontrolü kaydı yok.")
        labels = {"unknown": "Yanıt kaydı yok", "responded": "Yanıt alındı", "partial": "Kısmi yanıt", "failed": "Sorgular başarısız"}
        for item in statuses:
            lines.extend([
                f"{safe_text(item['provider'])}: {labels[item['source_status']]}",
                f"  Kontrol: {JOB_LABELS[item['attempt_status']]} | Başlangıç: {safe_text(item['started_at'])}",
                f"  İş: {safe_text(item['job_id'])}",
            ])
            for query in item["queries"]:
                if query.error:
                    lines.append(f"  {safe_text(query.error)}")
                for note in query.coverage_notes:
                    lines.append(f"  Kapsam: {safe_text(note)}")
            if item["error"]:
                lines.append(f"  İşlem hatası: {safe_text(item['error'])}")
        if cooldowns:
            lines.append("Kayıtlı kaynak beklemeleri (cihazın UTC saatine göre):")
        for wait in cooldowns:
            lines.append(
                f"  {safe_text(wait['provider'])}: " + (
                    f"{wait['remaining_seconds']} saniye kaldı; en erken {safe_text(wait['not_before'])}."
                    if wait["active"] else "Kaydedilmiş bekleme süresi doldu."
                )
            )
        data = [{**item, "queries": [asdict(query) for query in item["queries"]]} for item in statuses]
        emit({
            "catalog": [asdict(item) for item in catalog],
            "sources": data,
            "cooldowns": cooldowns,
            "observed_at": now.isoformat(),
        }, lines, as_json=args.json)
    elif args.command == "import":
        document = read_domain_file(args.source)
        matcher = make_domain_matcher()
        analysis = DomainImportService(
            repository, SQLiteFindingRepository(settings.database),
            matcher, SQLiteAllowlistRepository(settings.database),
        )
        summary = analysis.import_document(document)
        emit(asdict(summary), [
            f"{summary.total_records} adres satırı işlendi.",
            f"Yeni gözlem: {summary.observations_created}; önceden kayıtlı: {summary.observations_existing}.",
            f"Yeni aday bulgu: {summary.findings_created}; mevcut bulgu: {summary.findings_existing}.",
            f"Tam adres istisnasıyla bastırılan aday: {summary.findings_suppressed}.",
            "Bunlar inceleme adaylarıdır; kesin phishing kararı değildir.",
            "Sonuçları görmek için: ./xti findings list",
        ], as_json=args.json)
    elif args.command == "inbox":
        inbox = InboxService(SQLiteInboxRepository(settings.database))
        if args.inbox_action in {None, "list"}:
            page = inbox.list(status=args.status, limit=args.limit, before=args.before)
            next_command = None
            if page.next_before is not None:
                next_command = shlex.join([
                    "./xti", "--data-dir", str(settings.data_dir), "inbox", "list",
                    "--status", args.status, "--limit", str(args.limit), "--before", str(page.next_before),
                ])
            emit({**asdict(page), "next_command": next_command},
                 inbox_page_lines(page, status=args.status, next_command=next_command), as_json=args.json)
        elif args.inbox_action == "show":
            item = inbox.show(args.notification_id)
            emit(asdict(item), inbox_detail_lines(item, data_dir=settings.data_dir), as_json=args.json)
        elif args.inbox_action in {"read", "unread"}:
            result = inbox.mark(args.notification_ids, read=args.inbox_action == "read")
            label = "okundu" if args.inbox_action == "read" else "okunmamış"
            emit(asdict(result), [
                f"Seçilen {len(result.notifications)} bildirim {label} durumunda; değişen: {result.changed_count}.",
                "Bulgu ve aday inceleme kararları korundu. Kutuyu görmek için: ./xti inbox",
            ], as_json=args.json)
    elif args.command == "triage":
        items = ReviewQueueService(
            SQLiteFindingRepository(settings.database), SQLiteAssessmentRepository(settings.database),
        ).list(include_dismissed=args.all, limit=args.limit)
        emit({"items": [asdict(item) for item in items], "limit": args.limit},
             queue_lines(items, args.limit), as_json=args.json)
    elif args.command == "report":
        report = FindingReportService(SQLiteAssessmentRepository(settings.database)).build(args.finding_id)
        if args.output:
            destination = write_report(report, args.output)
            emit({"output": str(destination), "finding_id": args.finding_id, "format_version": 1},
                 [f"Bulgu raporu kaydedildi: {safe_text(destination)}"], as_json=args.json)
        else:
            lines = [
                f"Bulgu raporu: {safe_text(report['finding']['domain'])}",
                f"Öncelik: {PRIORITY_LABELS[report['priority']['level']]}",
                f"Kaynak kaydı: {len(report['observations'])}; hedef kontrolü: {len(report['assessments'])}; "
                f"karar: {len(report['reviews'])}.",
                f"Tam JSON raporu: ./xti --json report {safe_text(args.finding_id)}",
            ]
            lines.extend(f"Neden: {safe_text(reason)}" for reason in report['priority']['reasons'])
            emit(report, lines, as_json=args.json)
    elif args.command == "findings":
        findings_service = FindingService(SQLiteFindingRepository(settings.database))
        if args.finding_action == "list":
            findings = findings_service.list(args.status)
            lines = ["Bu filtrede aday bulgu yok."]
            if findings:
                lines = [f"İncelenecek adaylar ({len(findings)}):"]
                for finding in findings:
                    lines.extend([
                        "",
                        f"Kimlik: {safe_text(finding.id)}",
                        f"Adres: {safe_text(finding.domain)}",
                        f"İzlenen: {safe_text(finding.asset_value)}",
                        f"Durum: {STATUS_LABELS.get(finding.status, safe_text(finding.status))}",
                    ])
                    lines.extend(f"  Neden: {safe_text(reason)}" for reason in finding.reasons)
            emit({"findings": [asdict(item) for item in findings]}, lines, as_json=args.json)
        elif args.finding_action == "show":
            FindingService._validate_id(args.finding_id)
            enriched = SQLiteAssessmentRepository(settings.database).details(args.finding_id)
            details = enriched.details
            finding = details.finding
            lines = [
                f"Aday adres: {safe_text(finding.domain)}",
                f"İzlenen adres: {safe_text(finding.asset_value)}",
                f"Durum: {STATUS_LABELS.get(finding.status, safe_text(finding.status))}",
                "Bu bulgu tek başına phishing veya dolandırıcılık kanıtı değildir.",
            ]
            lines.extend(f"Neden: {safe_text(reason)}" for reason in finding.reasons)
            lines.append("Kaynak kayıtları:")
            for observation in details.observations:
                lines.append(
                    f"  {safe_text(observation.source_name)} / satır {observation.source_line}"
                    f" / {safe_text(observation.raw_domain)}"
                )
                lines.append(f"  Kaynak özeti: {safe_text(observation.source_sha256)}")
                lines.append(f"  Kaynak zamanı: {safe_text(observation.observed_at or 'belirtilmemiş')}")
            lines.append("Karar geçmişi:")
            if not details.reviews:
                lines.append("  Henüz karar verilmedi.")
            for review in details.reviews:
                lines.append(
                    f"  {safe_text(review.created_at)}: "
                    f"{STATUS_LABELS.get(review.decision, safe_text(review.decision))}"
                    f" — {safe_text(review.reason)}"
                )
            lines.append("Hedef kontrol geçmişi:")
            if not enriched.assessments:
                lines.append("  Henüz yapılmadı. Kontrol: ./xti findings check " + safe_text(finding.id))
            for assessment in enriched.assessments:
                lines.extend(check_lines(assessment))
            emit({**asdict(details), "assessments": [asdict(item) for item in enriched.assessments]},
                 lines, as_json=args.json)
        elif args.finding_action == "check":
            if not 1 <= args.limit <= 20:
                raise ValidationError("Hedef kontrol sınırı 1–20 arasında olmalı.")
            enrichment = make_enrichment(settings)
            progress = terminal_progress(args.json)
            # Validate existence before creating the execution lock or connecting.
            if args.finding_id is not None:
                details = findings_service.show(args.finding_id)
                if progress:
                    progress(f"DNS/HTTPS hedef kontrolü: {details.finding.domain}")
            else:
                findings_service.list()
            with LocalExecutionLock(settings.database).acquire():
                if args.finding_id is not None:
                    assessment = enrichment.check(args.finding_id)
                    result = BatchCheckResult((assessment,), skipped_fresh=0, remaining=0)
                else:
                    result = enrichment.check_pending(limit=args.limit, progress=progress)
            incomplete = checks_incomplete(result.assessments)
            if args.json:
                print(json.dumps({"ok": not incomplete, "data": check_data(result)}, ensure_ascii=True))
            else:
                for line in batch_lines(result):
                    print(line)
            return 3 if incomplete else 0
        elif args.finding_action == "review":
            finding = findings_service.review(args.finding_id, args.decision, args.reason)
            emit({"finding": asdict(finding)}, [
                f"Karar kaydedildi: {STATUS_LABELS[finding.status]}",
                f"Adres: {safe_text(finding.domain)}",
            ], as_json=args.json)


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not values:
        parser.print_help()
        return 0
    as_json = "--json" in values
    try:
        args = parser.parse_args(values)
        return run(args) or 0
    except EngineJobError as exc:
        report_error(exc.code, str(exc), as_json=args.json)
        return 3 if exc.code == 'not_found' else 1
    except (ResearchHistoryError, ReportError) as exc:
        report_error(exc.code, str(exc), as_json=as_json)
        return 3 if exc.code == "not_found" else 1
    except (WarninglistRunNotFound, EnrichmentRunNotFound) as exc:
        report_error("not_found", str(exc), as_json=as_json)
        return 3
    except (ValidationError, UsageError) as exc:
        if isinstance(exc, UsageError):
            from xti.interfaces.platform_engine import platform_command_requested, report_platform_usage_error
            if platform_command_requested(values):
                report_platform_usage_error()
                return 2
        report_error("validation_error", str(exc), as_json=as_json)
        return 2
    except (StorageError, FeedbackError) as exc:
        report_error("storage_error", str(exc), as_json=as_json)
        return 1
    except WorkerBusyError as exc:
        report_error("worker_busy", str(exc), as_json=as_json)
        return 4
    except EvaluationDataError as exc:
        report_error("evaluation_data_error", str(exc), as_json=as_json)
        return 1
    except SourceError as exc:
        report_error("source_error", str(exc), as_json=as_json)
        return 3
    except OrganizationExportPublicationError as exc:
        report_error("filesystem_error", str(exc), as_json=as_json)
        return 1
    except OSError:
        report_error("filesystem_error", "Dosyaya erişilemedi. Konumu ve izinleri kontrol et.",
                     as_json=as_json)
        return 1
    except KeyboardInterrupt:
        report_error("interrupted", "İşlem durduruldu.", as_json=as_json)
        return 130
    return 0

