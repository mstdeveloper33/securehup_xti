"""Read existing evidence and source histories in one consistent SQLite snapshot."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_findings import SQLiteFindingRepository, _FINDING_COLUMNS
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository, _ATTEMPT_COLUMNS
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository, _RUN_SELECT as FEED_RUN_SELECT
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cti_feeds import CTI_FEED_POLICIES
from xti.domain.periodic_changes import (
    FAMILIES,
    PeriodicChangesSnapshot,
    PeriodicChangeEvidence,
    PeriodicSection,
    PeriodicScope,
    PeriodicSourceCoverage,
    PeriodicWindow,
    in_period,
    periodic_time,
)
_MAX_ROWS = 50000
_MAX_RUNS = 10000


@dataclass(frozen=True, slots=True)
class _Run:
    family: str
    source: str
    scope_kind: str
    scope_id: str
    id: str
    status: str
    at: str
    order: int


class SQLitePeriodicChangesRepository:

    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _rows(connection, sql, values=(), *, maximum=_MAX_ROWS):
        rows = connection.execute(sql + ' LIMIT ?', (*values, maximum + 1)).fetchall()
        if len(rows) > maximum:
            raise StorageError('Dönem raporu doğrulama sınırı aşıldı; daha dar bir domain kapsamı seçin.')
        return rows

    @staticmethod
    def _inside(value, window):
        try:
            return in_period(value, window)
        except ValidationError as error:
            raise StorageError('Dönem raporu kayıt zamanı bozuk; işlem durduruldu.') from error

    @staticmethod
    def _put(events, event, window):
        if SQLitePeriodicChangesRepository._inside(event.recorded_at, window):
            events.append(event)
            if len(events) > _MAX_ROWS:
                raise StorageError('Dönem raporunda 50.000 satır doğrulama sınırı aşıldı.')

    def _domains(self, connection, scope, window, events, runs, expected):
        assets = self._rows(
            connection,
            'SELECT value FROM assets WHERE (? IS NULL OR value=?) ORDER BY value',
            (scope.domain, scope.domain),
            maximum=_MAX_RUNS,
        )
        for asset, in assets:
            if normalize_domain(asset) != asset:
                raise StorageError('Dönem raporu domain kaydı bozuk.')
            for family, source in (
                ('brand', 'crt.sh'),
                ('brand', 'urlscan'),
                ('surface', 'crt.sh'),
                ('surface', 'theharvester'),
            ):
                expected.add((family, source, 'domain', asset))
        if scope.domain is not None and (not assets):
            raise ValidationError('Bu domain kayıtlı değil.')
        rows = self._rows(
            connection,
            f'SELECT {_FINDING_COLUMNS} FROM findings WHERE (? IS NULL OR asset_value=?) ORDER BY created_at,id',
            (scope.domain, scope.domain),
        )
        for row in rows:
            finding = SQLiteFindingRepository._finding(row)
            if (
                normalize_domain(finding.asset_value) != finding.asset_value or normalize_domain(finding.domain) != finding.domain
            ):
                raise StorageError('Dönem raporu bulgu hedefi bozuk.')
            if not connection.execute(
                'SELECT 1 FROM assets WHERE id=? AND value=?',
                (finding.asset_id, finding.asset_value),
            ).fetchone():
                raise StorageError('Dönem raporu bulgu varlık bağı bozuk.')
            self._put(
                events,
                PeriodicChangeEvidence(
                    'brand',
                    'local-match',
                    finding.id,
                    'new_finding',
                    finding.created_at,
                    finding.domain,
                    asset_value=finding.asset_value,
                    definition_sha256=None,
                    rule_version=finding.rule_version,
                ),
                window,
            )
        rows = self._rows(
            connection,
            'SELECT e.id,e.candidate_id,e.action,e.status,e.reason,e.created_at FROM surface_candidate_events e LEFT JOIN surface_candidates c ON c.id=e.candidate_id WHERE (? IS NULL OR c.asset_value=?) ORDER BY e.rowid',
            (scope.domain, scope.domain),
        )
        candidates = {}
        for row in rows:
            event = SQLiteSurfaceCandidateRepository._event(row)
            if (
                not self._inside(event.created_at, window) or event.action not in {'discovered', 'owned', 'rejected', 'reopened'}
            ):
                continue
            candidate = candidates.get(event.candidate_id)
            if candidate is None:
                candidate = SQLiteSurfaceCandidateRepository._candidate(SQLiteSurfaceCandidateRepository._candidate_row(connection, event.candidate_id))
                candidates[event.candidate_id] = candidate
            self._put(
                events,
                PeriodicChangeEvidence(
                    'surface',
                    'local-surface',
                    event.id,
                    event.action,
                    event.created_at,
                    candidate.domain,
                    asset_value=candidate.asset_value,
                    target_record_id=candidate.id,
                ),
                window,
            )
        rows = self._rows(
            connection,
            'SELECT a.rowid,a.id FROM scan_attempts a LEFT JOIN scan_jobs j ON j.id=a.job_id WHERE (? IS NULL OR instr(j.targets,?)>0) ORDER BY a.rowid',
            (scope.domain, '"' + scope.domain + '"' if scope.domain else None),
            maximum=_MAX_RUNS,
        )
        for order, attempt_id in rows:
            attempt = SQLiteJobRepository._get_attempt(connection, attempt_id)
            job = SQLiteJobRepository._get_job(connection, attempt.job_id)
            targets = tuple((target for target in job.targets if scope.domain is None or target == scope.domain))
            if not targets:
                continue
            at = attempt.finished_at or attempt.started_at
            periodic_time(at)
            for target in targets:
                runs.append(_Run(
                    'brand',
                    job.provider,
                    'domain',
                    target,
                    attempt.id,
                    attempt.status,
                    at,
                    order,
                ))
                if attempt.status in {'partial', 'failed', 'interrupted', 'running'}:
                    self._put(
                        events,
                        PeriodicChangeEvidence(
                            'brand',
                            job.provider,
                            attempt.id,
                            attempt.status,
                            at,
                            attempt.error or 'Kontrol tam olarak tamamlanmadı.',
                            attempt.status,
                            asset_value=target,
                            run_id=attempt.id,
                        ),
                        window,
                    )
        rows = self._rows(
            connection,
            'SELECT id FROM surface_discovery_runs WHERE (? IS NULL OR asset_value=?) ORDER BY sequence',
            (scope.domain, scope.domain),
            maximum=_MAX_RUNS,
        )
        for identifier, in rows:
            run = SQLiteSurfaceCandidateRepository._run(SQLiteSurfaceCandidateRepository._run_row(connection, identifier))
            runs.append(_Run(
                'surface',
                run.provider,
                'domain',
                run.asset_value,
                run.id,
                run.status,
                run.finished_at,
                run.sequence,
            ))
            if run.status in {'partial', 'failed'}:
                self._put(
                    events,
                    PeriodicChangeEvidence(
                        'surface',
                        run.provider,
                        run.id,
                        run.status,
                        run.finished_at,
                        run.error or 'Kaynak sonucu kısmi.',
                        run.status,
                        asset_value=run.asset_value,
                        run_id=run.id,
                        reference=run.source_url,
                    ),
                    window,
                )

    def _social(self, connection, window, events, runs, expected):
        watches, _, history, items = SQLiteBrandUsernameWatchRepository._audit(connection)
        for watch in watches.values():
            expected.add(('username', watch.source_key, 'watch', watch.id))
        for run in history.values():
            source = run.source_name.casefold()
            runs.append(_Run(
                'username',
                source,
                'watch',
                run.watch_id,
                run.id,
                run.status,
                run.recorded_at,
                run.sequence,
            ))
            if run.status == 'failed':
                self._put(
                    events,
                    PeriodicChangeEvidence(
                        'username',
                        source,
                        run.id,
                        'failed',
                        run.recorded_at,
                        run.error or 'Sosyal kaynak çalışması başarısız.',
                        'failed',
                        watch_id=run.watch_id,
                        run_id=run.id,
                        definition_sha256=run.definition_sha256,
                    ),
                    window,
                )
        for item in items:
            run = history[item.run_id]
            if not self._inside(run.recorded_at, window):
                continue
            baseline = run.previous_complete_run_id is None
            if not baseline and item.action not in {'newly_found', 'changed', 'no_longer_reported'}:
                continue
            self._put(
                events,
                PeriodicChangeEvidence(
                    'username',
                    run.source_name.casefold(),
                    item.id,
                    item.action,
                    run.recorded_at,
                    f'{run.username} / {item.platform}',
                    watch_id=run.watch_id,
                    run_id=run.id,
                    reference=item.profile_url,
                    previous_run_id=run.previous_complete_run_id,
                    definition_sha256=run.definition_sha256,
                    source_observed_at=run.checked_at,
                    is_baseline=baseline,
                ),
                window,
            )

    def _ransomware(self, connection, window, events, runs, expected):
        for family, claim_repository, watch_repository in (
            ('threatcluster', SQLiteRansomwareClaimRepository, SQLiteRansomwareWatchRepository),
            ('ransomlook', SQLiteRansomLookClaimRepository, SQLiteRansomLookWatchRepository),
        ):
            source_runs, _ = claim_repository._audit(connection)
            expected.add((family, family, 'global-source', family))
            for run in source_runs:
                runs.append(_Run(
                    family,
                    family,
                    'global-source',
                    family,
                    run.id,
                    run.status,
                    run.finished_at,
                    run.sequence,
                ))
                if run.status == 'failed':
                    self._put(
                        events,
                        PeriodicChangeEvidence(
                            family,
                            family,
                            run.id,
                            'failed',
                            run.finished_at,
                            run.error or 'Kaynak yenilemesi başarısız.',
                            'failed',
                            run_id=run.id,
                            reference=run.source_url,
                        ),
                        window,
                    )
            watches, _, history, items, *_ = watch_repository._audit(connection)
            for watch in watches.values():
                expected.add((family, family, 'watch', watch.id))
            item_runs = set()
            for run in history.values():
                runs.append(_Run(
                    family,
                    family,
                    'watch',
                    run.watch_id,
                    run.id,
                    'complete',
                    run.executed_at,
                    run.sequence,
                ))
            for item in items:
                run = history[item.run_id]
                if not self._inside(run.executed_at, window):
                    continue
                baseline = run.previous_run_id is None
                if not baseline and item.action == 'unchanged':
                    continue
                item_runs.add(run.id)
                claim = item.match.claim
                self._put(
                    events,
                    PeriodicChangeEvidence(
                        family,
                        family,
                        item.id,
                        item.action,
                        run.executed_at,
                        f'{claim.group} / {claim.victim}',
                        watch_id=run.watch_id,
                        run_id=run.id,
                        source_run_id=run.source_run_id,
                        previous_run_id=run.previous_run_id,
                        definition_sha256=run.definition_sha256,
                        source_observed_at=claim.discovered_at,
                        is_baseline=baseline,
                        target_record_id=claim.id,
                    ),
                    window,
                )
            for run in history.values():
                if (
                    run.previous_run_id is None and run.id not in item_runs and (run.total_count == 0)
                ):
                    self._put(
                        events,
                        PeriodicChangeEvidence(
                            family,
                            family,
                            run.id,
                            'baseline_empty',
                            run.executed_at,
                            'İlk ölçümde eşleşen iddia yok.',
                            watch_id=run.watch_id,
                            run_id=run.id,
                            source_run_id=run.source_run_id,
                            definition_sha256=run.definition_sha256,
                            is_baseline=True,
                        ),
                        window,
                    )

    def _other_sources(self, connection, window, events, runs, expected):
        for key, policy in CTI_FEED_POLICIES.items():
            expected.add(('collection', key, 'global-source', key))
            repo = SQLiteCtiFeedRepository(self._storage.path, policy)
            rows = self._rows(
                connection,
                f'SELECT {FEED_RUN_SELECT} FROM cti_feed_runs WHERE source_name=? ORDER BY sequence',
                (policy.source_name,),
                maximum=_MAX_RUNS,
            )
            for row in rows:
                run = repo._run(row)
                runs.append(_Run(
                    'collection',
                    key,
                    'global-source',
                    key,
                    run.id,
                    run.status,
                    run.finished_at,
                    run.sequence,
                ))
                if run.status == 'failed':
                    self._put(
                        events,
                        PeriodicChangeEvidence(
                            'collection',
                            key,
                            run.id,
                            'failed',
                            run.finished_at,
                            run.error or 'IOC kaynağı yenilenemedi.',
                            'failed',
                            run_id=run.id,
                            reference=run.source_url,
                        ),
                        window,
                    )
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        if 'collection_sessions' not in tables:
            return
        from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
        rows = self._rows(
            connection,
            'SELECT id FROM collection_sessions ORDER BY sequence',
            maximum=_MAX_RUNS,
        )
        for identifier, in rows:
            details = SQLiteCollectionHistoryRepository._details(connection, identifier)
            receipted = {receipt.step_id for receipt in details.receipts}
            for step in details.steps:
                if step.id in receipted or step.status not in {'interrupted', 'skipped', 'running'}:
                    continue
                at = step.finished_at or step.started_at
                if at is None:
                    continue
                self._put(
                    events,
                    PeriodicChangeEvidence(
                        'collection',
                        step.source,
                        step.id,
                        step.status,
                        at,
                        step.error_code or 'Toplama adımı hâlâ açık.',
                        step.status,
                        asset_value=details.session.plan.definition.asset_value,
                        watch_id=step.watch_id,
                        run_id=details.session.id,
                    ),
                    window,
                )

    @staticmethod
    def _coverage(window, runs, expected):
        grouped = defaultdict(list)
        for run in runs:
            periodic_time(run.at)
            grouped[run.family, run.source, run.scope_kind, run.scope_id].append(run)
        result = []
        for key in sorted(expected | set(grouped)):
            values = sorted(grouped.get(key, ()), key=lambda run: (run.order, run.id))
            values = [run for run in values if periodic_time(run.at) < periodic_time(window.end_at)]
            current = [run for run in values if in_period(run.at, window)]
            complete = [run for run in values if run.status == 'complete']
            last = values[-1] if values else None
            last_complete = complete[-1] if complete else None
            counts = {status: sum((run.status == status for run in current)) for status in (
                'complete',
                'partial',
                'failed',
                'interrupted',
                'running',
            )}
            state = 'no_history' if not values else 'not_checked' if not current else 'incomplete' if any((counts[status] for status in ('partial', 'failed', 'interrupted', 'running'))) else 'observed'
            result.append(PeriodicSourceCoverage(
                *key,
                last.id if last else None,
                last.status if last else None,
                last.at if last else None,
                last_complete.id if last_complete else None,
                last_complete.at if last_complete else None,
                len(current),
                counts['complete'],
                counts['partial'],
                counts['failed'],
                counts['interrupted'],
                state,
            ))
        return tuple(result)

    def read(self, window: PeriodicWindow, scope: PeriodicScope, *, limit_per_section: int):
        if (
            not isinstance(window, PeriodicWindow) or type(window.days) is not int or window.days not in {1, 7}
        ):
            raise ValidationError('Geçerli 1/7 günlük dönem gerekli.')
        if (
            periodic_time(window.end_at) - periodic_time(window.start_at) != timedelta(days=window.days)
        ):
            raise ValidationError('Dönem başlangıç ve bitişi gün seçimiyle uyuşmuyor.')
        if (
            not isinstance(scope, PeriodicScope) or (scope.domain is not None and normalize_domain(scope.domain) != scope.domain)
        ):
            raise ValidationError('Dönem kapsamı geçersiz.')
        if type(limit_per_section) is not int or not 1 <= limit_per_section <= 500:
            raise ValidationError('Dönem bölüm sınırı 1–500 arasında olmalı.')
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            events = []
            runs = []
            expected = set()
            self._domains(connection, scope, window, events, runs, expected)
            if scope.domain is None:
                self._social(connection, window, events, runs, expected)
                self._ransomware(connection, window, events, runs, expected)
                self._other_sources(connection, window, events, runs, expected)
            if len(runs) > _MAX_ROWS:
                raise StorageError('Dönem raporu çalışma doğrulama sınırı aşıldı.')
            sections = []
            for family in FAMILIES if scope.domain is None else FAMILIES[:2]:
                selected = sorted(
                    (event for event in events if event.family == family),
                    key=lambda event: (
                        periodic_time(event.recorded_at),
                        event.record_id,
                        event.run_id or '',
                    ),
                    reverse=True,
                )
                failures = tuple((event for event in selected if event.status in {
                    'partial',
                    'failed',
                    'interrupted',
                    'skipped',
                    'running',
                }))
                baselines = tuple((event for event in selected if event.is_baseline))
                changes = tuple((event for event in selected if event.status not in {
                    'partial',
                    'failed',
                    'interrupted',
                    'skipped',
                    'running',
                } and (not event.is_baseline)))
                shown_changes = changes[:limit_per_section]
                shown_baselines = baselines[:limit_per_section]
                shown_failures = failures[:limit_per_section]
                omitted = len(changes) + len(baselines) + len(failures) - len(shown_changes) - len(shown_baselines) - len(shown_failures)
                sections.append(PeriodicSection(
                    family,
                    shown_changes,
                    shown_baselines,
                    shown_failures,
                    len(changes),
                    len(baselines),
                    len(failures),
                    omitted,
                ))
            coverage = self._coverage(window, runs, expected)
            notes = []
            future = sum((periodic_time(run.at) >= periodic_time(window.end_at) for run in runs))
            if future:
                notes.append(f'{future} çalışma dönem bitişinde/sonrasında kaldığı için dönem ve son durum hesabına katılmadı; saatleri inceleyin.')
            if len(coverage) > limit_per_section:
                notes.append(f'Kontrol kapsamı görünümünde {len(coverage) - limit_per_section} satır daha var; --limit değerini artırın.')
            notes.append('Görünüm sınırı her ailenin değişim, başlangıç ve hata alt bölümüne ayrı uygulanır; gösterilmeyen satır sayısı ayrıca verilir.')
            notes.append('Kaynak doğrulayıcıları ilgili yerel tarihçeyi denetler; geçerli kontrol yokluğu temiz sonuç değildir.')
            return PeriodicChangesSnapshot(
                tuple(sections),
                coverage[:limit_per_section],
                SCHEMA_VERSION,
                tuple(notes),
                len(coverage),
                max(0, len(coverage) - limit_per_section),
            )
