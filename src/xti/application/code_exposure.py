"""Collect, mask and commit a bounded observation through narrow ports."""
from datetime import datetime, timezone
import time

from xti.domain.code_exposure import (CodeExposureError, READS, WRITES, MAX_CANDIDATES,
                                     parameters, observations)
from xti.ports.code_exposure import CodeRepository, CodeSource, SecretScanner


class CodeExposureService:
    def __init__(self, repository: CodeRepository, sources: CodeSource, scanner: SecretScanner,
                 *, now=None, clock=time.monotonic):
        self.repository, self.sources, self.scanner = repository, sources, scanner
        self.now = now or (lambda: datetime.now(timezone.utc).isoformat())
        self.clock = clock

    def execute(self, operation, **values):
        values = parameters(operation, values)
        if operation == 'code.sources': return {'sources': self.sources.status(), 'scanner': self.scanner.status()}
        if operation == 'code.plan':
            watch = self.repository.read(operation, values)
            return {'watch': watch, 'sources': [s for s in self.sources.status() if s['source'] in watch['scope']['sources']],
                    'scanner': self.scanner.status(),
                    'network_access': False, 'credential_validation': False,
                    'notes': ['Depo keşfi bütün internetin veya bütün kodların aranması değildir.',
                              'Seçilen her kaynağın erişim, pencere ve eksik kapsamı çalışma sonucunda ayrı görünür.']}
        if operation in READS: return self.repository.read(operation, values)
        if operation not in WRITES: raise CodeExposureError('invalid_parameters', 'Kod izleme işlemi bilinmiyor.')
        if operation != 'code.run': return self.repository.mutate(operation, values, self.now())
        run, replayed = self.repository.reserve(values, self.now())
        if replayed: return {**run, 'replayed': True}
        started = self.clock()
        candidates, documents, scanner_errors = [], [], set()
        scanner_state = self.scanner.status()

        def consume(document):
            remaining = run['scope']['budget_seconds'] - (self.clock() - started)
            secrets, checked = [], False
            if scanner_state['state'] == 'ready' and remaining > 0:
                try:
                    secrets = self.scanner.scan(document.content, seconds=min(10, remaining)); checked = True
                except CodeExposureError as error: scanner_errors.add(error.code)
            else: scanner_errors.add('scanner_unavailable' if scanner_state['state'] != 'ready' else 'scanner_timeout')
            rows = observations(document, run['scope'], secrets)
            if len(candidates) + len(rows) > MAX_CANDIDATES:
                # Keep earlier evidence and explicitly mark this document as incompletely analysed.
                scanner_errors.add('candidate_limit'); return
            candidates.extend(rows)
            documents.append({'source': document.provider, 'locator': document.locator, 'secret_checked': checked})

        result = self.sources.collect(run['scope'], run['checkpoints'], consume)
        successful = [s for s in result['sources'] if s['status'] == 'complete']
        partial_coverage = any(s.get('skipped_files') or s.get('incomplete_results') for s in result['sources'])
        status = 'complete' if len(successful) == len(result['sources']) and not scanner_errors and not partial_coverage else 'partial'
        if not successful and not documents: status = 'failed'
        result.update(status=status, candidates=candidates, checked_documents=documents,
                      scanner=scanner_state, scanner_errors=sorted(scanner_errors),
                      policy='code-exposure-v1', all_internet_covered=False)
        return self.repository.finish(run['id'], result, self.now())
