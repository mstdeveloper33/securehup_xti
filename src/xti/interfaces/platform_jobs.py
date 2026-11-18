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

    operations = ExistingSourceJobOperations(enrichment, warninglists, history)
    return CooperativeSourceJobRunner(operations, LocalExecutionLock(database))


def migrate_jobs(context):
    from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
    queue = jobs_database(context)
    with LocalExecutionLock(queue).acquire():
        return SQLiteEngineJobRepository(queue).migrate()
