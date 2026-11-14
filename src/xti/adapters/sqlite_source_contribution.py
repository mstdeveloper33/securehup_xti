"""Read explicit domain/provider evidence in one transaction without invoking sources."""
from datetime import datetime, timezone
from pathlib import Path
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_jobs import SQLiteJobRepository, _JOB_COLUMNS, _ATTEMPT_COLUMNS
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.source_contribution import (
    FAMILIES,
    PROVIDERS,
    ContributionAttempt,
    ContributionQueuedJob,
    SourceContributionSnapshot,
    SurfaceContributionEvidence,
)
MAX_MEMBERSHIPS = 50000
MAX_JOBS = 10000
MAX_ATTEMPTS = 10000
MAX_CANDIDATE_VALUES = 250000


def _time(value):
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 64:
            raise ValueError('invalid time')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('timezone missing')
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError) as error:
        raise StorageError('Kaynak katkısı kayıt zamanı bozuk; işlem durduruldu.') from error


def _domain(value):
    try:
        normalized = normalize_domain(value)
        if normalized != value:
            raise ValueError('non-canonical domain')
        return normalized
    except (ValueError, TypeError) as error:
        raise StorageError('Kaynak katkısı domain kanıtı bozuk; işlem durduruldu.') from error


class SQLiteSourceContributionRepository:

    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _rows(connection, sql, values=(), *, limit):
        result = connection.execute(sql + ' LIMIT ?', (*values, limit + 1)).fetchall()
        if len(result) > limit:
            raise StorageError('Kaynak katkısı güvenli okuma sınırını aşıyor; eksik toplam üretilmedi.')
        return result

    def _surface(self, connection, asset_id, asset_value):
        evidence = []
        candidates = self._rows(
            connection,
            'SELECT id FROM surface_candidates WHERE asset_id=? OR asset_value=? ORDER BY id',
            (asset_id, asset_value),
            limit=MAX_MEMBERSHIPS,
        )
        for identifier, in candidates:
            candidate = SQLiteSurfaceCandidateRepository._candidate(SQLiteSurfaceCandidateRepository._candidate_row(connection, identifier))
            if candidate.asset_id != asset_id or candidate.asset_value != asset_value:
                raise StorageError('Alt alan adının kök varlık bağı uyuşmuyor.')
            rows = self._rows(
                connection,
                'SELECT id,candidate_id,provider,source_name,source_sha256,raw_domain,observed_at,recorded_at FROM surface_candidate_sources WHERE candidate_id=? ORDER BY id',
                (candidate.id,),
                limit=MAX_MEMBERSHIPS - len(evidence),
            )
            for row in rows:
                source = SQLiteSurfaceCandidateRepository._source(row)
                if (
                    source.candidate_id != candidate.id or source.provider not in PROVIDERS['surface']
                ):
                    raise StorageError('Alt alan adı sağlayıcı kanıtı geçersiz.')
                evidence.append(SurfaceContributionEvidence(
                    source.provider,
                    _domain(candidate.domain),
                    candidate.id,
                    candidate.status,
                    source.id,
                    source.source_name,
                    _time(source.recorded_at),
                    _time(source.observed_at) if source.observed_at is not None else None,
                ))
        attempts = []
        rows = self._rows(
            connection,
            'SELECT id FROM surface_discovery_runs WHERE asset_id=? OR asset_value=? ORDER BY sequence',
            (asset_id, asset_value),
            limit=MAX_ATTEMPTS,
        )
        for identifier, in rows:
            run = SQLiteSurfaceCandidateRepository._run(SQLiteSurfaceCandidateRepository._run_row(connection, identifier))
            if (
                run.asset_id != asset_id or run.asset_value != asset_value or run.provider not in PROVIDERS['surface']
            ):
                raise StorageError('Pasif keşif çalışması kök veya sağlayıcıyla uyuşmuyor.')
            attempts.append(ContributionAttempt(
                run.id,
                'surface',
                run.provider,
                run.status,
                _time(run.started_at),
                _time(run.finished_at),
                (asset_value,),
                result_available=True,
                warnings=run.warnings,
                reported_candidate_count=run.candidate_count,
            ))
        return (tuple(evidence), tuple(attempts))

    def _brand(self, connection, asset_value):
        attempts, queued = ([], [])
        jobs = self._rows(
            connection,
            f'SELECT {_JOB_COLUMNS} FROM scan_jobs WHERE instr(targets,?)>0 ORDER BY rowid',
            ('"' + asset_value + '"',),
            limit=MAX_JOBS,
        )
        candidate_values = 0
        for row in jobs:
            job = SQLiteJobRepository._job(row)
            if (
                job.provider not in PROVIDERS['brand'] or any((_domain(target) != target for target in job.targets))
            ):
                raise StorageError('Marka araması sağlayıcısı veya hedefleri geçersiz.')
            if asset_value not in job.targets:
                raise StorageError('Marka araması istenen hedefe ait değil.')
            _time(job.created_at)
            _time(job.updated_at)
            rows = self._rows(
                connection,
                f'SELECT {_ATTEMPT_COLUMNS} FROM scan_attempts WHERE job_id=? ORDER BY number',
                (job.id,),
                limit=MAX_ATTEMPTS - len(attempts),
            )
            if job.attempt_count != len(rows):
                raise StorageError('Marka araması deneme sayısı geçmişle uyuşmuyor.')
            if job.status == 'queued':
                if rows:
                    raise StorageError('Bekleyen arama işinin deneme geçmişi tutarsız.')
                queued.append(ContributionQueuedJob(
                    job.id,
                    job.provider,
                    job.targets,
                    job.rule_version,
                    job.typos,
                ))
            elif not rows and job.status != 'interrupted':
                raise StorageError('Arama işinin gerekli deneme geçmişi eksik.')
            last = None
            for index, row in enumerate(rows, 1):
                attempt = SQLiteJobRepository._attempt(row)
                if attempt.job_id != job.id or attempt.number != index:
                    raise StorageError('Marka araması deneme bağı/sırası bozuk.')
                result = attempt.result
                if (
                    result is not None and (result.targets != job.targets or result.status != attempt.status)
                ):
                    raise StorageError('Marka araması sonucu hedef/durum sözleşmesiyle uyuşmuyor.')
                if attempt.status in {'complete', 'partial'} and result is None:
                    raise StorageError('Tam/kısmi arama denemesinin kayıtlı sonucu eksik.')
                domains = tuple((_domain(value) for value in result.candidate_domains)) if result is not None else ()
                candidate_values += len(domains)
                if candidate_values > MAX_CANDIDATE_VALUES:
                    raise StorageError('Kaynak katkısı aday okuma sınırını aştı; kısmi örtüşme sonucu üretilmedi.')
                attempts.append(ContributionAttempt(
                    attempt.id,
                    'brand',
                    job.provider,
                    attempt.status,
                    _time(attempt.started_at),
                    _time(attempt.finished_at) if attempt.finished_at is not None else None,
                    job.targets,
                    job.rule_version,
                    job.typos,
                    job.id,
                    result is not None,
                    domains,
                    reported_candidate_count=len(domains) if result is not None else None,
                ))
                last = attempt
            if last is not None and last.status != job.status:
                raise StorageError('Arama işinin güncel durumu son denemeyle uyuşmuyor.')
        return (tuple(attempts), tuple(queued))

    def snapshot(self, asset_value: str, *, family: str):
        asset_value = normalize_domain(asset_value)
        if not isinstance(family, str) or family not in FAMILIES:
            raise ValidationError('Katkı ailesi all, surface veya brand olmalı.')
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            row = connection.execute(
                'SELECT id,value FROM assets WHERE value=?',
                (asset_value,),
            ).fetchone()
            if row is None:
                raise ValidationError('Kaynak katkısı için domain önceden kaydedilmeli.')
            asset_id, stored_value = row
            if stored_value != asset_value:
                raise StorageError('Kaynak katkısı varlık kaydı uyuşmuyor.')
            evidence, attempts, queued = ((), (), ())
            if family in {'all', 'surface'}:
                evidence, attempts = self._surface(connection, asset_id, asset_value)
            if family in {'all', 'brand'}:
                brand, queued = self._brand(connection, asset_value)
                attempts += brand
            return SourceContributionSnapshot(
                asset_id,
                asset_value,
                evidence,
                attempts,
                queued,
                SCHEMA_VERSION,
            )
