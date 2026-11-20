"""Common queue history independent of its storage and user interface."""
from xti.domain.job_history import parameters
from xti.ports.engine_jobs import JobHistoryRepository


class JobHistoryService:
    def __init__(self, repository: JobHistoryRepository):
        self.repository = repository

    def execute(self, operation, **values):
        options = parameters(operation, values)
        if operation == 'jobs.history':
            return self.repository.history(**options)
        if operation == 'jobs.audit':
            return self.repository.validate()
        return self.repository.capacity()
