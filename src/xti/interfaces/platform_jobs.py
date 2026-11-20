"""Explicit per-company queue setup and collector composition."""

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.config import Settings


def jobs_database(context):
    return context.data_dir / 'engine-jobs.sqlite3'


def initialize_jobs(context):
    from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
    SQLiteEngineJobRepository(jobs_database(context)).initialize()


def validate_jobs(context):
    from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
    with SQLiteAssetRepository(context.database)._connection(readonly=True):
        pass
    SQLiteEngineJobRepository(jobs_database(context)).validate()


def recover_storage(context):
    """Explicit administrative recovery, before read-only admission validation.

    SQLite must open a hot rollback journal with write permission. Hold the
    established queue -> core locks; ordinary reads never repair either DB.
    This neither creates a missing database nor claims/restarts a job.
    """
    from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
    queue = jobs_database(context)
    with LocalExecutionLock(queue).acquire(), LocalExecutionLock(context.database).acquire():
        with SQLiteEngineJobRepository(queue)._connection():
            pass
        storage = SQLiteAssetRepository(context.database)
        with storage._connection() as connection:
            storage._check_integrity(connection)
        validate_jobs(context)


def make_job_service(context):
    from xti.adapters.engine_job_collection import CollectionProfileJobRunner
    from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
    from xti.application.engine_jobs import EngineJobService

    def history():
        from xti.interfaces.cli import make_collection_history_service
        return make_collection_history_service(Settings(context.data_dir), SQLiteAssetRepository(context.database))

    queue = jobs_database(context)
    return EngineJobService(SQLiteEngineJobRepository(queue),
        CollectionProfileJobRunner(SQLiteCollectionProfileRepository(context.database), history),
        LocalExecutionLock(queue), source_runner=make_source_runner(context.database))


def make_source_runner(database):
    from xti.adapters.source_job_steps import ExistingSourceJobOperations
    from xti.application.source_jobs import CooperativeSourceJobRunner
    def enrichment(**kwargs):
        from xti.interfaces.indicator_enrichment import make_enrichment_service
        return make_enrichment_service(database, **kwargs)

    def warninglists(**kwargs):
        from xti.interfaces.warninglists import make_warninglist_service
        return make_warninglist_service(database, **kwargs)

    def history():
        from xti.interfaces.research_history import make_history_service
        return make_history_service(database)

    def news(request_usage=None):
        from xti.application.news import NewsService
        from xti.adapters.sqlite_news import SQLiteNewsRepository
        from xti.adapters.source_job_news import HeldSourceJobLock, source
        return NewsService(SQLiteNewsRepository(database), source(request_usage), HeldSourceJobLock())

    def investigations():
        from xti.interfaces.investigation import make_investigation_service
        return make_investigation_service(database)

    def publishers(request_usage=None):
        from xti.adapters.source_job_publishers import PublisherDocumentStep
        from xti.adapters.publisher_documents import PublisherDocumentSource
        from xti.adapters.sqlite_reports import SQLiteReportRepository
        from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
        return PublisherDocumentStep(SQLiteReportRepository(database),
            SQLiteEngineJobRepository(database.parent / "engine-jobs.sqlite3"),
            PublisherDocumentSource(request_usage=request_usage))

    def relationship_notifications():
        from xti.adapters.source_job_relationships import RelationshipNotificationStep
        from xti.interfaces.evidence import make_evidence_service
        return RelationshipNotificationStep(database, make_evidence_service(database))

    def social_tracking(*, network=False):
        from xti.adapters.source_job_social import SocialTrackingStep
        from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
        from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
        from xti.interfaces.social_tracking import make_social_tracking_service
        return SocialTrackingStep(make_social_tracking_service(database, network=network),
            SQLiteSocialDiscoveryRepository(database), SQLiteEngineJobRepository(database.parent / 'engine-jobs.sqlite3'))

    def groups():
        from xti.adapters.source_job_groups import GroupRefreshStep
        from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
        return GroupRefreshStep(database, SQLiteEngineJobRepository(database.parent / 'engine-jobs.sqlite3'))

    from xti.adapters.source_job_reports import VersionedReportStep
    operations = ExistingSourceJobOperations(enrichment, warninglists, history,
        news=news, investigations=investigations, reports=lambda: VersionedReportStep(database),
        publishers=publishers, relationship_notifications=relationship_notifications, social_tracking=social_tracking, groups=groups)
    return CooperativeSourceJobRunner(operations, LocalExecutionLock(database))


def migrate_jobs(context):
    from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
    queue = jobs_database(context)
    with LocalExecutionLock(queue).acquire():
        return SQLiteEngineJobRepository(queue).migrate()
