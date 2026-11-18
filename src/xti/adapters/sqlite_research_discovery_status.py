"""Latest attempt and last complete passive response, in the research snapshot."""

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_research_discovery import _stored_bytes
from xti.domain.surface import SURFACE_DISCOVERY_PROVIDERS
from xti.domain.surface_discovery_status import StoredDiscoveryStatus


MAX_STATUS_BYTES = 4 * 1024 * 1024
_RUN_BYTES = _stored_bytes('id', 'asset_id', 'asset_value', 'provider', 'status', 'source_url',
                          'started_at', 'finished_at', 'warnings', 'error', 'record_count',
                          'skipped_names', 'ignored_names', 'candidate_count', 'candidates_created',
                          'candidates_existing', 'evidence_created', 'evidence_existing')


class StoredDiscoveryStatuses:
    def __init__(self, connection, *, limitations, coverage):
        self.connection, self.limitations, self.coverage = connection, limitations, coverage
        self.cache, self.bytes = {}, 0

    def read(self, asset_id, domain):
        if asset_id in self.cache:
            return self.cache[asset_id]
        states, count, complete = [], 0, True
        for provider in SURFACE_DISCOVERY_PROVIDERS:
            chosen = []
            # Sequence is insertion order, including a wall-clock rollback.
            for suffix in ('', " AND status='complete'"):
                row = self.connection.execute(
                    f"SELECT id,{_RUN_BYTES} FROM surface_discovery_runs "
                    f"WHERE asset_id=? AND provider=?{suffix} ORDER BY sequence DESC LIMIT 1",
                    (asset_id, provider),
                ).fetchone()
                chosen.append(row)
            sizes = {row[0]: row[1] for row in chosen if row is not None}
            size = sum(sizes.values())
            if size + self.bytes > MAX_STATUS_BYTES:
                self.limitations.add('discovery_status_read_budget')
                states.append(StoredDiscoveryStatus(provider, read_complete=False))
                complete = False
                continue
            self.bytes += size
            decoded = {}
            for identifier in sizes:
                raw = SQLiteSurfaceCandidateRepository._run_row(self.connection, identifier)
                run = SQLiteSurfaceCandidateRepository._run(raw)
                if (run.asset_id != asset_id or run.asset_value != domain or raw[3] != domain or
                    run.provider != provider or run.id != identifier):
                    raise StorageError('Pasif keşif çalışmasının kayıtlı kök/kaynak bağlantısı tutarsız.')
                decoded[identifier] = run
            latest, good = (decoded[row[0]] if row else None for row in chosen)
            if good and (not latest or good.sequence > latest.sequence):
                raise StorageError('Pasif keşfin son çalışma sırası tutarsız.')
            count += len(decoded)
            states.append(StoredDiscoveryStatus(provider, latest, good))
        self.coverage.append({'kind': 'surface_discovery_status', 'scope': ['domain', domain],
            'examined_count': count, 'window_limit': 4, 'complete': complete,
            'order': 'provider_latest_and_last_complete_sequence'})
        self.cache[asset_id] = tuple(states)
        return self.cache[asset_id]
