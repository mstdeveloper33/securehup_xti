"""Read existing evidence and source histories in one consistent SQLite snapshot."""
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_organization_scope import read_organization_scope
from xti.adapters.sqlite_public_notices import read_public_notice_history
from xti.domain.organization_scope import OrganizationScope
from xti.domain.organizations import normalize_organization_id
from xti.adapters.sqlite_findings import SQLiteFindingRepository, _FINDING_COLUMNS
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository, _ATTEMPT_COLUMNS
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository, _RUN_SELECT as FEED_RUN_SELECT
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository, _calculate_change as calculate_web_change
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository, _calculate_change as calculate_mail_change
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository, _calculate_change as calculate_service_change
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository, _calculate_change as calculate_cname_change
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
    PeriodicValueChange,
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

    @staticmethod
    def _domain_clause(scope: PeriodicScope, organization: OrganizationScope | None, column: str):
        if organization is not None:
            if not organization.organization.active:
                return "0", ()
            return (
                f"{column} IN (SELECT target_value FROM organization_links "
                "WHERE organization_id=? AND target_kind='domain' AND active=1)",
                (organization.organization.id,),
            )
        if scope.domain is not None:
            return f"{column}=?", (scope.domain,)
        return "1", ()

    def _domains(self, connection, scope, organization, window, events, runs, expected):
        clause, parameters = self._domain_clause(scope, organization, "value")
        assets = self._rows(
            connection,
            f'SELECT value FROM assets WHERE {clause} ORDER BY value',
            parameters,
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
        selected_domains = {row[0] for row in assets}
        clause, parameters = self._domain_clause(scope, organization, 'asset_value')
        rows = self._rows(
            connection,
            f'SELECT {_FINDING_COLUMNS} FROM findings WHERE {clause} ORDER BY created_at,id',
            parameters,
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
                    commands=(('./xti', 'findings', 'show', finding.id),),
                ),
                window,
            )
        clause, parameters = self._domain_clause(scope, organization, 'c.asset_value')
        rows = self._rows(
            connection,
            f'SELECT e.id,e.candidate_id,e.action,e.status,e.reason,e.created_at FROM surface_candidate_events e LEFT JOIN surface_candidates c ON c.id=e.candidate_id WHERE {clause} ORDER BY e.rowid',
            parameters,
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
                    commands=(('./xti', 'surface', 'candidate', 'show', candidate.id),),
                ),
                window,
            )
        clause, parameters = self._domain_clause(scope, organization, 'asset.value')
        rows = self._rows(
            connection,
            'SELECT a.rowid,a.id FROM scan_attempts a LEFT JOIN scan_jobs j ON j.id=a.job_id '
            'WHERE EXISTS (SELECT 1 FROM assets asset '
            f'WHERE {clause} AND instr(j.targets, char(34)||asset.value||char(34))>0) '
            'ORDER BY a.rowid',
            parameters,
            maximum=_MAX_RUNS,
        )
        for order, attempt_id in rows:
            attempt = SQLiteJobRepository._get_attempt(connection, attempt_id)
            job = SQLiteJobRepository._get_job(connection, attempt.job_id)
            targets = tuple(target for target in job.targets if target in selected_domains)
            shared_scope = len(targets) != len(job.targets)
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
                            ('Paylaşılan çok hedefli kontrol tam tamamlanmadı; kapsam dışı hedef ayrıntıları çıkarıldı.' if shared_scope else attempt.error or 'Kontrol tam olarak tamamlanmadı.'),
                            attempt.status,
                            asset_value=target,
                            run_id=attempt.id,
                            commands=(('./xti', 'jobs', 'show', attempt.job_id),),
                            shared_scope=shared_scope,
                            evidence_note=('İş ayrıntısı kuruluş dışındaki hedefleri de içerebilir.' if shared_scope else None),
                        ),
                        window,
                    )
        clause, parameters = self._domain_clause(scope, organization, 'asset_value')
        rows = self._rows(
            connection,
            f'SELECT id FROM surface_discovery_runs WHERE {clause} ORDER BY sequence',
            parameters,
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
                        commands=(('./xti', 'surface', 'run', run.id),),
                    ),
                    window,
                )

    @staticmethod
    def _surface_status(kind: str, check) -> str:
        result = check.result
        if kind == 'web':
            if result.dns_status in {'failed', 'blocked'}:
                return 'failed'
            return 'partial' if result.errors else 'complete'
        if kind == 'mail':
            if all(getattr(result, field + '_status') == 'failed' for field in ('mx', 'spf', 'dmarc')):
                return 'failed'
            return 'partial' if result.errors else 'complete'
        if kind == 'service':
            if result.dns_status != 'resolved':
                return 'failed'
            return 'partial' if any(port.state == 'unknown' for port in result.ports) else 'complete'
        if result.alias_status == 'failed':
            return 'failed'
        return 'partial' if result.errors else 'complete'

    @staticmethod
    def _surface_values(kind: str, result) -> dict:
        if kind == 'web':
            values = {field: getattr(result, field) for field in (
                'dns_status', 'addresses', 'tls_status', 'http_status',
                'http_status_code', 'connected_address',
            )}
            values['addresses'] = tuple(sorted(result.addresses))
            if result.certificate is not None:
                values.update({'certificate.' + field: value
                               for field, value in asdict(result.certificate).items()})
                values['certificate.dns_names'] = tuple(sorted(result.certificate.dns_names))
            return values
        if kind == 'mail':
            return {field + suffix: (tuple(sorted(getattr(result, field + suffix))) if suffix == '_records' else getattr(result, field + suffix))
                    for field in ('mx', 'spf', 'dmarc') for suffix in ('_status', '_records')}
        if kind == 'service':
            values = {field: getattr(result, field) for field in (
                'dns_status', 'addresses', 'requested_address', 'checked_address',
            )}
            values['addresses'] = tuple(sorted(result.addresses))
            values.update({f'ports.{port.port}': port.state for port in result.ports})
            return values
        return {
            'alias_status': result.alias_status,
            'chain': tuple(f'{hop.owner} -> {hop.target}' for hop in result.chain),
            'target': result.target, 'target_status': result.target_status,
            'addresses': tuple(sorted(result.addresses)),
        }

    def _surface_checks(self, connection, scope, organization, window, events, runs, expected):
        clause, parameters = self._domain_clause(scope, organization, 's.asset_value')
        scope_rows = self._rows(connection,
            'SELECT s.asset_id,s.asset_value,s.active,s.reason,s.created_at,s.updated_at,a.value '
            f'FROM surface_scopes s LEFT JOIN assets a ON a.id=s.asset_id WHERE {clause} ORDER BY s.asset_id',
            parameters, maximum=_MAX_RUNS,
        )
        scoped = {record.asset_id: record for record in map(SQLiteSurfaceRepository._scope, scope_rows)}
        configurations = (
            ('web', 'surface_checks', SQLiteSurfaceRepository, calculate_web_change),
            ('mail', 'surface_mail_checks', SQLiteSurfaceMailRepository, calculate_mail_change),
            ('service', 'surface_service_checks', SQLiteSurfaceServiceScanRepository, calculate_service_change),
            ('cname', 'surface_cname_checks', SQLiteSurfaceCnameRepository, calculate_cname_change),
        )
        for kind, table, repository, calculate_change in configurations:
            source = 'stored-' + kind
            for target in scoped.values():
                expected.add(('surface', source, 'domain', target.asset_value))
            authorization = 'c.authorization_reason,' if kind == 'service' else ''
            rows = self._rows(connection,
                f'SELECT c.rowid,c.id,c.asset_id,s.asset_value,{authorization}'
                f'c.result,c.state_sha256,c.change,c.recorded_at FROM {table} c '
                f'LEFT JOIN surface_scopes s ON s.asset_id=c.asset_id WHERE {clause} ORDER BY c.rowid',
                parameters,
            )
            preceding = {}
            completed = {}
            for row in rows:
                check = repository._check(row[1:], row[3])
                if check.asset_id not in scoped or scoped[check.asset_id].asset_value != check.asset_value:
                    raise StorageError('Dönem kontrolü kayıtlı dış yüzey kapsamıyla uyuşmuyor.')
                previous = preceding.get(check.asset_id)
                if check.change != calculate_change(previous.result if previous else None, check.result):
                    raise StorageError('Dönem kontrol farkı önceki kanıtla uyuşmuyor.')
                preceding[check.asset_id] = check
                status = self._surface_status(kind, check)
                runs.append(_Run('surface', source, 'domain', check.asset_value,
                                 check.id, status, check.recorded_at, row[0]))
                # Keep the last complete comparable observation. A failed check
                # is never used as proof that an address, certificate or record vanished.
                previous_complete = completed.get(check.asset_id)
                if status == 'complete' and periodic_time(check.recorded_at) < periodic_time(window.end_at):
                    completed[check.asset_id] = check
                if not self._inside(check.recorded_at, window):
                    continue
                commands = (('./xti', 'surface', 'show', check.asset_value, '--history-limit', '100'),) if kind == 'web' else (
                    ('./xti', 'surface', 'services' if kind == 'service' else kind,
                     'show', check.asset_value, '--history-limit', '100'),
                )
                if status != 'complete':
                    self._put(events, PeriodicChangeEvidence(
                        'surface', source, check.id, status, check.recorded_at,
                        ' | '.join(check.result.errors) or 'Kontrolün tamamı doğrulanamadı.', status,
                        asset_value=check.asset_value, run_id=check.id,
                        previous_record_id=previous_complete.id if previous_complete else None,
                        evidence_type=kind, source_observed_at=check.result.finished_at,
                        commands=commands,
                        evidence_note='Hata/kısmi sonuç yeni durum veya kaybolma kanıtı sayılmadı. Komut son 100 kontrolün geçmişidir.',
                    ), window)
                    continue
                policy_changed = previous_complete is not None and previous_complete.result.policy_version != check.result.policy_version
                baseline = previous_complete is None or policy_changed
                before = None if baseline else self._surface_values(kind, previous_complete.result)
                after = self._surface_values(kind, check.result)
                changes = self._differences(before, after)
                if not baseline and not changes:
                    continue
                note = 'Alanlar kayıtlı gözlemlerdir; yapılandırma veya güvenlik hükmü değildir. Komut son 100 kontrolün geçmişidir.'
                if policy_changed:
                    note += ' Kontrol politikası değişti; yeni başlangıç ölçümü gösteriliyor.'
                elif previous is not None and previous_complete is not None and previous.id != previous_complete.id:
                    note += ' Aradaki eksik kontroller atlanarak son tamamlanan kanıtla karşılaştırıldı.'
                if kind == 'service' and previous_complete is not None and previous_complete.result.requested_address != check.result.requested_address:
                    note += ' Kontroller farklı IP seçmiş; port farkı aynı sunucunun değiştiği anlamına gelmez.'
                self._put(events, PeriodicChangeEvidence(
                    'surface', source, check.id, 'observed_baseline' if baseline else 'observed_changed',
                    check.recorded_at, check.asset_value, asset_value=check.asset_value,
                    run_id=check.id, previous_run_id=previous.id if previous else None,
                    previous_record_id=None if baseline else previous_complete.id,
                    evidence_type=kind, source_observed_at=check.result.finished_at,
                    is_baseline=baseline, value_changes=changes, commands=commands,
                    evidence_note=note,
                ), window)

    @staticmethod
    def _watch_ids(organization: OrganizationScope | None, kind: str):
        if organization is None:
            return None
        return frozenset(target.value for target in organization.effective_targets if target.kind == kind)

    @staticmethod
    def _differences(before: dict | None, after: dict | None):
        keys = sorted(set(before or {}) | set(after or {}))
        return tuple(
            PeriodicValueChange(key, (before or {}).get(key), (after or {}).get(key))
            for key in keys
            if before is None or after is None or before.get(key) != after.get(key)
        )

    def _social(self, connection, organization, window, events, runs, expected):
        selected = self._watch_ids(organization, 'username-watch')
        if selected == frozenset():
            return
        watches, _, history, items = SQLiteBrandUsernameWatchRepository._audit(connection)
        items_by_run = {(item.run_id, item.platform): item for item in items}
        for watch in watches.values():
            if selected is None or watch.id in selected:
                expected.add(('username', watch.source_key, 'watch', watch.id))
        for run in history.values():
            if selected is not None and run.watch_id not in selected:
                continue
            source = run.source_name.casefold()
            runs.append(_Run('username', source, 'watch', run.watch_id, run.id,
                             run.status, run.recorded_at, run.sequence))
            if run.status == 'failed':
                self._put(events, PeriodicChangeEvidence(
                    'username', source, run.id, 'failed', run.recorded_at,
                    run.error or 'Sosyal kaynak çalışması başarısız.', 'failed',
                    watch_id=run.watch_id, run_id=run.id,
                    definition_sha256=run.definition_sha256,
                    commands=(('./xti', 'brand', 'watch-run-show', run.id),),
                ), window)
        for item in items:
            run = history[item.run_id]
            if selected is not None and run.watch_id not in selected:
                continue
            if not self._inside(run.recorded_at, window):
                continue
            baseline = run.previous_complete_run_id is None
            if not baseline and item.action not in {'newly_found', 'changed', 'no_longer_reported'}:
                continue
            previous = items_by_run.get((run.previous_complete_run_id, item.platform))
            before = None if previous is None else {'status': previous.status, 'profile_url': previous.profile_url}
            after = {'status': item.status, 'profile_url': item.profile_url}
            self._put(events, PeriodicChangeEvidence(
                'username', run.source_name.casefold(), item.id, item.action,
                run.recorded_at, f'{run.username} / {item.platform}',
                watch_id=run.watch_id, run_id=run.id, reference=item.profile_url,
                previous_run_id=run.previous_complete_run_id,
                definition_sha256=run.definition_sha256,
                source_observed_at=run.checked_at, is_baseline=baseline,
                previous_record_id=previous.id if previous else None,
                evidence_type='username', value_changes=self._differences(before, after),
                commands=(('./xti', 'brand', 'watch-run-show', run.id),),
            ), window)

    def _ransomware(self, connection, organization, window, events, runs, expected):
        for family, kind, claim_repository, watch_repository in (
            ('threatcluster', 'ransomware-watch', SQLiteRansomwareClaimRepository, SQLiteRansomwareWatchRepository),
            ('ransomlook', 'ransomlook-watch', SQLiteRansomLookClaimRepository, SQLiteRansomLookWatchRepository),
        ):
            selected = self._watch_ids(organization, kind)
            if selected == frozenset():
                continue
            source_runs, _ = claim_repository._audit(connection)
            expected.add((family, family, 'global-source', family))
            for run in source_runs:
                runs.append(_Run(family, family, 'global-source', family,
                                 run.id, run.status, run.finished_at, run.sequence))
                if run.status == 'failed':
                    self._put(events, PeriodicChangeEvidence(
                        family, family, run.id, 'failed', run.finished_at,
                        run.error or 'Kaynak yenilemesi başarısız.', 'failed',
                        run_id=run.id, reference=run.source_url,
                        commands=(('./xti', 'ransomware', 'status', '--source', family),),
                        shared_scope=organization is not None,
                        evidence_note='Ortak kaynak yenileme durumudur; belirli bir izlemenin çalıştırıldığı anlamına gelmez.',
                    ), window)
            watches, _, history, items, *_ = watch_repository._audit(connection)
            items_by_run = {(item.run_id, item.match.claim.id): item for item in items}
            for watch in watches.values():
                if selected is None or watch.id in selected:
                    expected.add((family, family, 'watch', watch.id))
            for run in history.values():
                if selected is None or run.watch_id in selected:
                    runs.append(_Run(family, family, 'watch', run.watch_id, run.id,
                                     'complete', run.executed_at, run.sequence))
            for item in items:
                run = history[item.run_id]
                if selected is not None and run.watch_id not in selected:
                    continue
                if not self._inside(run.executed_at, window):
                    continue
                baseline = run.previous_run_id is None
                if not baseline and item.action == 'unchanged':
                    continue
                claim = item.match.claim
                previous = items_by_run.get((run.previous_run_id, claim.id))
                before = None if baseline else {'presence': 'not_reported' if item.action == 'added' else 'reported'}
                after = {'presence': 'not_reported' if item.action == 'removed' else 'reported'}
                if item.action == 'updated' and previous is not None:
                    before.update(asdict(previous.match.claim))
                    after.update(asdict(claim))
                self._put(events, PeriodicChangeEvidence(
                    family, family, item.id, item.action, run.executed_at,
                    f'{claim.group} / {claim.victim}', watch_id=run.watch_id, run_id=run.id,
                    source_run_id=run.source_run_id, previous_run_id=run.previous_run_id,
                    definition_sha256=run.definition_sha256, source_observed_at=claim.discovered_at,
                    is_baseline=baseline, target_record_id=claim.id,
                    previous_record_id=previous.id if previous else None,
                    evidence_type=family, value_changes=self._differences(before, after),
                    commands=(('./xti', 'ransomware', 'watch-run-show', run.id, '--source', family),),
                ), window)
            for run in history.values():
                if selected is not None and run.watch_id not in selected:
                    continue
                if run.previous_run_id is None and run.total_count == 0:
                    self._put(events, PeriodicChangeEvidence(
                        family, family, run.id, 'baseline_empty', run.executed_at,
                        'İlk ölçümde eşleşen iddia yok.', watch_id=run.watch_id, run_id=run.id,
                        source_run_id=run.source_run_id, definition_sha256=run.definition_sha256,
                        is_baseline=True,
                        commands=(('./xti', 'ransomware', 'watch-run-show', run.id, '--source', family),),
                    ), window)

    @staticmethod
    def _selected_collection_keys(details, organization: OrganizationScope | None):
        if organization is None:
            return {step.step_key for step in details.steps}
        targets = {(target.kind, target.value) for target in organization.effective_targets}
        plan = details.session.plan
        selected = set()
        for unit in plan.units:
            if unit.kind == 'username_watch':
                included = ('username-watch', unit.watch.watch_id) in targets
            elif unit.kind == 'ransomware_watch':
                kind = 'ransomware-watch' if unit.source == 'threatcluster' else 'ransomlook-watch'
                included = (kind, unit.watch.watch_id) in targets
            elif unit.kind == 'ransomware_refresh':
                included = any(
                    related.kind == 'ransomware_watch' and related.source == unit.source
                    and ('ransomware-watch' if unit.source == 'threatcluster' else 'ransomlook-watch', related.watch.watch_id) in targets
                    for related in plan.units
                )
            else:
                included = ('domain', unit.asset_value) in targets
            if included:
                selected.add(unit.step_key)
        return selected

    def _other_sources(self, connection, organization, window, events, runs, expected):
        if organization is None:
            for key, policy in CTI_FEED_POLICIES.items():
                expected.add(('collection', key, 'global-source', key))
                repo = SQLiteCtiFeedRepository(self._storage.path, policy)
                rows = self._rows(connection,
                    f'SELECT {FEED_RUN_SELECT} FROM cti_feed_runs WHERE source_name=? ORDER BY sequence',
                    (policy.source_name,), maximum=_MAX_RUNS,
                )
                for row in rows:
                    run = repo._run(row)
                    runs.append(_Run('collection', key, 'global-source', key,
                                     run.id, run.status, run.finished_at, run.sequence))
                    if run.status == 'failed':
                        self._put(events, PeriodicChangeEvidence(
                            'collection', key, run.id, 'failed', run.finished_at,
                            run.error or 'IOC kaynağı yenilenemedi.', 'failed',
                            run_id=run.id, reference=run.source_url,
                        ), window)
        elif not organization.effective_targets:
            return
        from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
        if organization is None:
            clause, values = '1', ()
        else:
            clause = (
                'EXISTS (SELECT 1 FROM organization_links l WHERE l.organization_id=? AND l.active=1 '
                'AND instr(s.plan_json,char(34)||l.target_value||char(34))>0)'
            )
            values = (organization.organization.id,)
        rows = self._rows(connection,
            f'SELECT s.id FROM collection_sessions s WHERE {clause} ORDER BY s.sequence',
            values, maximum=_MAX_RUNS,
        )
        for identifier, in rows:
            details = SQLiteCollectionHistoryRepository._details(connection, identifier)
            selected = self._selected_collection_keys(details, organization)
            if not selected:
                continue
            shared_scope = len(selected) != len(details.steps)
            receipts = {receipt.step_id: receipt for receipt in details.receipts}
            domain = details.session.plan.definition.asset_value
            domain_selected = organization is None or any(
                target.kind == 'domain' and target.value == domain for target in organization.effective_targets
            )
            for step in details.steps:
                if step.step_key not in selected:
                    continue
                receipt = receipts.get(step.id)
                # An explicitly selected IOC refresh supplies context even when
                # the organization report excludes unrelated global feed history.
                if organization is not None and receipt is not None and receipt.result_kind == 'feed_run':
                    repo = SQLiteCtiFeedRepository(self._storage.path, CTI_FEED_POLICIES[step.source])
                    row = connection.execute(
                        f'SELECT {FEED_RUN_SELECT} FROM cti_feed_runs WHERE id=?',
                        (receipt.result_id,),
                    ).fetchone()
                    if row is None:
                        raise StorageError('Dönem toplama kaynak bağı eksik.')
                    run = repo._run(row)
                    expected.add(('collection', step.source, 'collection-domain', domain))
                    runs.append(_Run('collection', step.source, 'collection-domain', domain,
                                     run.id, run.status, run.finished_at, run.sequence))
                    if run.status == 'failed':
                        self._put(events, PeriodicChangeEvidence(
                            'collection', step.source, step.id, 'failed', run.finished_at,
                            run.error or 'Seçili toplamada IOC kaynağı yenilenemedi.', 'failed',
                            asset_value=domain, run_id=details.session.id, source_run_id=run.id,
                            shared_scope=True,
                            commands=(('./xti', 'collections', 'show', details.session.id),),
                            evidence_note='Bu toplama için seçilen ortak IOC yenilemesidir; kuruluşun kendisinde ihlal kanıtı değildir.',
                        ), window)
                if receipt is not None or step.status not in {'failed', 'interrupted', 'skipped', 'running'}:
                    continue
                at = step.finished_at or step.started_at
                if at is None:
                    continue
                self._put(events, PeriodicChangeEvidence(
                    'collection', step.source, step.id, step.status, at,
                    step.error_code or 'Toplama adımı hâlâ açık.', step.status,
                    asset_value=domain if domain_selected else None,
                    watch_id=step.watch_id, run_id=details.session.id,
                    shared_scope=shared_scope,
                    commands=(('./xti', 'collections', 'show', details.session.id),),
                    evidence_note=('Bu satır yalnız seçili adıma aittir; tam oturum ayrıntısı kuruluş dışı hedefleri de içerebilir.' if shared_scope else None),
                ), window)

    def _public_notices(self, connection, scope, organization, window, events, runs, expected):
        selected = None
        if scope.domain is not None:
            selected = {scope.domain}
        elif organization is not None:
            selected = {target.value for target in organization.effective_targets if target.kind == 'domain'}
            if not selected:
                return
        history = read_public_notice_history(connection)
        # HIBP refreshes a shared public catalog. One refresh is not one check
        # for each linked domain and does not imply target-specific collection.
        expected.add(('notices', 'hibp', 'global-source', 'hibp'))
        grouped = defaultdict(list)
        for change in history.changes:
            grouped[change.run_id].append(change)
        previous_complete = None
        current = {}
        for run in history.runs:
            runs.append(_Run('notices', 'hibp', 'global-source', 'hibp', run.id,
                             run.status, run.finished_at, run.sequence))
            if run.status == 'failed':
                self._put(events, PeriodicChangeEvidence(
                    'notices', 'hibp', run.id, 'failed', run.finished_at,
                    run.error or 'Ortak kamu olay kataloğu yenilenemedi.', 'failed',
                    run_id=run.id, reference=history.source_url,
                    previous_run_id=previous_complete.id if previous_complete else None,
                    shared_scope=True, commands=(('./xti', 'notices', 'run-show', run.id),),
                    evidence_note='Ortak katalog yenileme hatasıdır; belirli bir domainin sorgulandığını veya güvenli olduğunu göstermez.',
                    source_attribution=history.attribution, source_license=history.license,
                ), window)
                continue
            baseline = previous_complete is None
            for change in grouped[run.id]:
                notice = change.notice
                previous = current.get(notice.id)
                old_notice = previous[0] if previous else None
                # Preserve exact historical Domain evidence when the publisher
                # changes that field; never infer a link from the title/name.
                bound_domains = {notice.domain, old_notice.domain if old_notice else None} - {None}
                visible_domains = bound_domains if selected is None else bound_domains & selected
                if selected is None or visible_domains:
                    before = asdict(old_notice) if old_notice is not None else None
                    after = None if change.action == 'removed' else asdict(notice)
                    if before is not None:
                        before['presence'] = 'reported'
                    elif not baseline:
                        before = {'presence': 'not_reported'}
                    if after is not None:
                        after['presence'] = 'reported'
                    else:
                        after = {'presence': 'not_reported'}
                    self._put(events, PeriodicChangeEvidence(
                        'notices', 'hibp', run.id + ':' + notice.id, change.action,
                        run.finished_at, notice.title,
                        asset_value=(notice.domain if selected is None or notice.domain in visible_domains
                                     else sorted(visible_domains)[0]),
                        run_id=run.id, source_run_id=run.id, reference=notice.source_url,
                        previous_run_id=previous_complete.id if previous_complete else None,
                        source_observed_at=notice.modified_at, is_baseline=baseline,
                        target_record_id=notice.id,
                        previous_record_id=previous[1] + ':' + notice.id if previous else None,
                        evidence_type='public-notice', value_changes=self._differences(before, after),
                        commands=(('./xti', 'notices', 'run-show', run.id),),
                        evidence_note='Kapsam kaynağın bu veya önceki kaydındaki tam Domain alanından gelir; başlık eşleşmesinden sahiplik çıkarılmaz. Sınıflar kaynağın beyanıdır. Listeden çıkış çözüm kanıtı değildir. Komut tam çalışmanın sayfalı fark geçmişidir.',
                        source_classification=tuple((key, value) for key, value in asdict(notice).items() if key.startswith('is_')),
                        source_attribution=history.attribution, source_license=history.license,
                    ), window)
                if change.action == 'removed':
                    current.pop(notice.id, None)
                else:
                    current[notice.id] = (notice, run.id)
            previous_complete = run

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

    def read(self, window: PeriodicWindow, scope: PeriodicScope, *, limit_per_section: int, offset: int = 0):
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
        if scope.organization_id is not None:
            normalize_organization_id(scope.organization_id)
            if scope.domain is not None:
                raise ValidationError('Domain ve kuruluş filtresi aynı anda kullanılamaz.')
        if type(limit_per_section) is not int or not 1 <= limit_per_section <= 500:
            raise ValidationError('Dönem bölüm sınırı 1–500 arasında olmalı.')
        if type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise ValidationError('Dönem görünüm başlangıcı 0–1.000.000 arasında olmalı.')
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            organization = read_organization_scope(connection, scope.organization_id) if scope.organization_id is not None else None
            events = []
            runs = []
            expected = set()
            self._domains(connection, scope, organization, window, events, runs, expected)
            self._surface_checks(connection, scope, organization, window, events, runs, expected)
            if scope.domain is None:
                self._social(connection, organization, window, events, runs, expected)
                self._ransomware(connection, organization, window, events, runs, expected)
                self._other_sources(connection, organization, window, events, runs, expected)
            self._public_notices(connection, scope, organization, window, events, runs, expected)
            if len(runs) > _MAX_ROWS:
                raise StorageError('Dönem raporu çalışma doğrulama sınırı aşıldı.')
            sections = []
            for family in FAMILIES if scope.domain is None else ('brand', 'surface', 'notices'):
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
                shown_changes = changes[offset:offset + limit_per_section]
                shown_baselines = baselines[offset:offset + limit_per_section]
                shown_failures = failures[offset:offset + limit_per_section]
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
                    offset,
                ))
            coverage = self._coverage(window, runs, expected)
            notes = []
            future = sum((periodic_time(run.at) >= periodic_time(window.end_at) for run in runs))
            if future:
                notes.append(f'{future} çalışma dönem bitişinde/sonrasında kaldığı için dönem ve son durum hesabına katılmadı; saatleri inceleyin.')
            shown_coverage = coverage[offset:offset + limit_per_section]
            if len(coverage) > len(shown_coverage):
                notes.append(f'Kontrol kapsamı görünümünde {len(coverage) - len(shown_coverage)} satır gösterilmedi; --offset ve --limit ile sayfaları seçin.')
            notes.append('Görünüm başlangıcı ve sınırı her ailenin değişim, başlangıç ve hata alt bölümüne ve kontrol kapsamına ayrı uygulanır; gerçek toplamlar değişmez.')
            if organization is not None and not organization.effective_targets:
                notes.append('Kuruluşun bu okuma anında etkin bağlantısı yok; bütün kayıtlar kapsamına dönülmedi.')
            notes.append('Dış yüzey farkları son tamamlanan aynı politikadaki gözlemlerden hesaplanır; başarısız kontrol boş/yok durumuna çevrilmez.')
            notes.append('Kamu olay kataloğu kontrol kapsamı ortak kaynağın yenileme durumudur; domain başına yapılmış sorgu değildir.')
            notes.append('Kaynak doğrulayıcıları ilgili yerel tarihçeyi denetler; geçerli kontrol yokluğu temiz sonuç değildir.')
            return PeriodicChangesSnapshot(
                tuple(sections),
                shown_coverage,
                SCHEMA_VERSION,
                tuple(notes),
                len(coverage),
                len(coverage) - len(shown_coverage),
                organization,
                offset,
            )
