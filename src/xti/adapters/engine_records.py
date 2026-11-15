"""Structured engine record reads over the existing audited SQLite evidence.

Every call owns one read transaction. It neither runs collectors nor follows
the human-oriented CLI navigation stored in search results.
"""

from dataclasses import is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_reviews import SQLiteBrandUsernameReviewRepository
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository, read_case_evidence_links
from xti.adapters.sqlite_cti_context import _audit_assertion_history
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_public_notices import read_public_notice_history
from xti.adapters.sqlite_news import read_news_catalog
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_supplier_history import read_supplier_history
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.brand_username_reviews import brand_username_review_candidate_id
from xti.domain.cases import canonical_snapshot
from xti.domain.cti_attack import ATTACK_SOURCE_NAME
from xti.domain.cti_indicators import INDICATOR_TYPES
from xti.domain.cti_knowledge import ENTITY_TYPES
from xti.domain.engine import EngineContractError, EngineRecordReference
from xti.domain.public_notices import HIBP_ATTRIBUTION, HIBP_LICENSE, HIBP_SOURCE_NAME, HIBP_SOURCE_URL
from xti.domain.ransomlook_ransomware import RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL, RANSOMLOOK_SOURCE_LICENSE
from xti.domain.ransomware_claims import RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL, RANSOMWARE_SOURCE_LICENSE


MAX_DETAIL_ROWS = 50_000
_LOCAL_TYPES = {
    ('domain', 'registered_domain'): 'local-assets',
    ('domain', 'surface_candidate'): 'passive-discovery',
    ('finding', 'brand_finding'): 'local-match',
    ('social', 'username_watch'): 'local-social',
    ('social', 'social_profile'): 'local-social',
    ('public-notice', 'public_breach_notice'): 'hibp',
    ('case', 'case'): 'local-case-management',
    ('supplier', 'supplier'): 'local-suppliers',
    ('organization', 'organization'): 'local-organizations',
}

# Contract v1 projections are deliberately frozen. A new internal dataclass
# field must not silently become externally visible, even when nested.
_WIRE_FIELDS = {
    'BrandUsernameReviewState': ('candidate_id', 'decision', 'reason', 'reviewed_at', 'event_count', 'state_sha256'),
    'BrandUsernameReviewEvent': ('sequence', 'id', 'candidate_id', 'watch_id', 'run_id', 'decision', 'reason', 'recorded_at', 'previous_event_id', 'candidate_sha256'),
    'BrandUsernameWatch': ('id', 'name_key', 'display_name', 'username', 'platforms', 'source_key', 'active', 'created_at', 'updated_at'),
    'BrandUsernameWatchEvent': ('id', 'watch_id', 'action', 'definition_sha256', 'reason', 'recorded_at'),
    'BrandUsernameWatchRun': ('sequence', 'id', 'watch_id', 'status', 'source_name', 'source_version', 'integration_profile', 'username', 'platforms', 'definition_sha256', 'previous_complete_run_id', 'checked_at', 'recorded_at', 'platform_count', 'found_count', 'newly_found_count', 'changed_count', 'unchanged_found_count', 'no_longer_reported_count', 'unreported_count', 'result_sha256', 'error'),
    # A run item is historical source evidence. The derived current human
    # review has one authority: provenance.current_review in record.get.
    'BrandUsernameWatchRunItem': ('id', 'run_id', 'platform', 'profile_url', 'status', 'action', 'state_sha256'),
    'Case': ('id', 'title', 'summary', 'status', 'priority', 'resolution', 'created_at', 'updated_at', 'closed_at'),
    'CaseEvidence': ('id', 'case_id', 'evidence_type', 'evidence_id', 'display_value', 'source_reference', 'snapshot_json', 'snapshot_sha256', 'active', 'added_reason', 'added_at', 'updated_at', 'removed_reason', 'removed_at'),
    'CaseTask': ('id', 'case_id', 'title', 'status', 'due_at', 'reason', 'created_at', 'updated_at'),
    'CaseActivity': ('sequence', 'id', 'case_id', 'activity_type', 'reference_id', 'summary', 'reason', 'snapshot_sha256', 'recorded_at'),
    'CtiIndicator': ('id', 'indicator_type', 'value', 'created_at', 'updated_at'),
    'CtiIndicatorAssertion': ('id', 'indicator_id', 'source_name', 'source_reference', 'confidence', 'valid_from', 'valid_until', 'active', 'description', 'first_seen_at', 'last_seen_at', 'created_at', 'updated_at'),
    'CtiIndicatorAssertionEvent': ('id', 'assertion_id', 'action', 'confidence', 'valid_from', 'valid_until', 'description', 'reason', 'observed_at', 'recorded_at'),
    'CtiEntity': ('id', 'entity_type', 'name_key', 'display_name', 'created_at', 'updated_at'),
    'CtiEntityAssertion': ('id', 'entity_id', 'source_name', 'source_reference', 'confidence', 'aliases', 'description', 'active', 'first_seen_at', 'last_seen_at', 'created_at', 'updated_at'),
    'CtiEntityAssertionEvent': ('id', 'assertion_id', 'action', 'confidence', 'aliases', 'description', 'reason', 'observed_at', 'recorded_at'),
    'Observation': ('id', 'domain', 'raw_domain', 'source_name', 'source_sha256', 'source_line', 'observed_at', 'ingested_at'),
    'Finding': ('id', 'asset_id', 'asset_value', 'domain', 'rule_version', 'reasons', 'status', 'created_at', 'last_seen_at'),
    'Review': ('id', 'finding_id', 'decision', 'reason', 'created_at'),
    'OrganizationTargetReference': ('kind', 'value'),
    'Organization': ('id', 'name_key', 'display_name', 'revision', 'active', 'created_at', 'updated_at'),
    'OrganizationEvent': ('sequence', 'id', 'organization_id', 'action', 'revision', 'name_key', 'display_name', 'reason', 'recorded_at'),
    'OrganizationLink': ('id', 'organization_id', 'target', 'revision', 'active', 'reason', 'created_at', 'updated_at'),
    'OrganizationLinkEvent': ('sequence', 'id', 'link_id', 'organization_id', 'action', 'revision', 'target', 'reason', 'recorded_at'),
    'OrganizationTargetSummary': ('reference', 'display_name', 'source', 'active'),
    'PublicNotice': ('id', 'title', 'domain', 'breach_date', 'added_at', 'modified_at', 'pwn_count', 'data_classes', 'is_verified', 'is_fabricated', 'is_sensitive', 'is_retired', 'is_spam_list', 'is_malware', 'is_stealer_log', 'source_attribution', 'source_url'),
    'PublicNoticeRun': ('sequence', 'id', 'status', 'started_at', 'finished_at', 'fetched_at', 'content_sha256', 'snapshot_sha256', 'notice_count', 'added_count', 'updated_count', 'unchanged_count', 'removed_count', 'error'),
    'PublicNoticeChange': ('run_id', 'action', 'notice', 'state_sha256'),
    'NewsArticle': ('id', 'source_key', 'source_entry_id', 'url', 'title', 'summary', 'summary_truncated', 'published_at', 'updated_at', 'published_raw', 'updated_raw'),
    'NewsSourceDefinition': ('key', 'name', 'url', 'homepage', 'attribution'),
    'NewsRun': ('sequence', 'id', 'source_key', 'status', 'started_at', 'finished_at', 'fetched_at', 'content_sha256', 'snapshot_sha256', 'article_count', 'added_count', 'updated_count', 'unchanged_count', 'error'),
    'RansomLookClaim': ('id', 'group', 'victim', 'discovered_at'),
    'RansomLookClaimRunItem': ('id', 'run_id', 'claim', 'action', 'state_sha256'),
    'RansomLookClaimRun': ('sequence', 'id', 'source_name', 'status', 'source_url', 'content_sha256', 'started_at', 'finished_at', 'fetched_at', 'window_days', 'source_record_count', 'claim_count', 'added_count', 'updated_count', 'unchanged_count', 'removed_count', 'error'),
    'RansomwareClaim': ('id', 'group', 'victim', 'country', 'sector', 'discovered_at', 'status', 'website', 'last_seen_at', 'delisted_at', 'first_party', 'source_post_available'),
    'RansomwareClaimRunItem': ('id', 'run_id', 'claim', 'action', 'state_sha256'),
    'RansomwareClaimRun': ('sequence', 'id', 'source_name', 'status', 'source_url', 'content_sha256', 'started_at', 'finished_at', 'fetched_at', 'generated_at', 'window_days', 'source_record_count', 'claim_count', 'added_count', 'updated_count', 'unchanged_count', 'removed_count', 'error'),
    'Supplier': ('id', 'name_key', 'display_name', 'primary_domain', 'relationship_type', 'criticality', 'active', 'reason', 'created_at', 'updated_at'),
    'SupplierEvent': ('sequence', 'id', 'supplier_id', 'action', 'display_name', 'primary_domain', 'relationship_type', 'criticality', 'reason', 'recorded_at'),
    'SurfaceCandidate': ('id', 'asset_id', 'asset_value', 'domain', 'status', 'reason', 'first_seen_at', 'last_seen_at', 'created_at', 'updated_at', 'source_count'),
    'SurfaceCandidateSource': ('id', 'candidate_id', 'provider', 'source_name', 'source_sha256', 'raw_domain', 'observed_at', 'recorded_at'),
    'SurfaceCandidateEvent': ('id', 'candidate_id', 'action', 'status', 'reason', 'created_at'),
}


def _value(value):
    if is_dataclass(value):
        fields = _WIRE_FIELDS.get(type(value).__name__)
        if fields is None or not type(value).__module__.startswith('xti.domain.'):
            raise StorageError('Kayıt veri türü engine v1 sözleşmesinde tanımlı değil.')
        return {field: _value(getattr(value, field)) for field in fields}
    if isinstance(value, dict):
        return {key: _value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_value(item) for item in value]
    return value


def _not_found():
    raise EngineContractError('not_found', 'Belirtilen tür ve kaynak alanında kayıt bulunamadı.')


def _time(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError('Invalid record timestamp')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Record timestamp needs timezone')
    return parsed.astimezone(timezone.utc).isoformat()


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('Noncanonical record identity')
    return value


def _rows(connection, query, parameters=()):
    values = connection.execute(query, parameters).fetchmany(MAX_DETAIL_ROWS + 1)
    if len(values) > MAX_DETAIL_ROWS:
        raise StorageError('Engine kayıt ayrıntısı güvenli okuma sınırını aşıyor; eksik sonuç üretilmedi.')
    return values


def _page(items, offset, limit):
    return {'items': _value(items[offset:offset + limit]), 'total_count': len(items),
            'offset': offset, 'limit': limit, 'has_more': offset + limit < len(items)}


class SQLiteEngineRecordRepository:
    def __init__(self, path: Path):
        self.storage = SQLiteAssetRepository(path)

    def get(self, reference: EngineRecordReference, *, offset: int = 0, limit: int = 50) -> dict:
        if (not isinstance(reference, EngineRecordReference)
                or type(offset) is not int or not 0 <= offset <= 1_000_000
                or type(limit) is not int or not 1 <= limit <= 500):
            raise EngineContractError('invalid_request', 'Kayıt başvurusu veya sayfalama geçersiz.')
        key = (reference.kind, reference.record_type)
        if reference.kind == 'cti':
            valid = reference.record_type in ENTITY_TYPES and reference.namespace == 'local-cti'
        elif reference.kind == 'indicator':
            valid = reference.record_type in INDICATOR_TYPES and reference.namespace == 'local-ioc'
        elif reference.kind == 'ransomware':
            valid = reference.record_type == 'ransomware_claim' and reference.namespace in {'threatcluster', 'ransomlook'}
        elif reference.kind == 'news':
            valid = reference.record_type == 'news_article' and reference.namespace in {'cisa', 'ncsc', 'cert-fr'}
        else:
            valid = _LOCAL_TYPES.get(key) == reference.namespace and key in _LOCAL_TYPES
        if not valid:
            _not_found()
        try:
            with self.storage._connection(readonly=True) as connection:
                connection.execute('BEGIN')
                if reference.kind in {'cti', 'indicator'}:
                    record, sections, provenance, notes = self._intelligence(connection, reference)
                elif reference.kind in {'public-notice', 'ransomware'}:
                    record, sections, provenance, notes = self._catalog(connection, reference)
                elif reference.kind == 'news':
                    record, sections, provenance, notes = self._news(connection, reference)
                else:
                    handlers = {'registered_domain': self._asset, 'surface_candidate': self._candidate,
                                'brand_finding': self._finding, 'username_watch': self._watch,
                                'social_profile': self._profile, 'case': self._case,
                                'supplier': self._supplier, 'organization': self._organization}
                    record, sections, provenance, notes = handlers[reference.record_type](connection, reference.record_id)
                return {'reference': reference.to_dict(), 'record': _value(record),
                        'sections': {name: _page(items, offset, limit) for name, items in sections.items()},
                        'provenance': _value(provenance), 'notes': list(notes)}
        except EngineContractError:
            raise
        except (TypeError, ValueError, KeyError, IndexError, AttributeError, OverflowError) as error:
            raise StorageError('Engine kayıt ayrıntısı veya kaynak bağlantıları bozuk; kısmi sonuç üretilmedi.') from error

    @staticmethod
    def _news(connection, reference):
        catalog = read_news_catalog(connection)
        stored = next((value for value in catalog.articles
                       if value.article.id == reference.record_id
                       and value.article.source_key == reference.namespace), None)
        if stored is None:
            _not_found()
        status = next(item for item in catalog.sources if item.source.key == reference.namespace)
        return stored.article, {}, {
            'source': status.source, 'state_sha256': stored.state_sha256,
            'first_run_id': stored.first_run_id, 'last_change_run_id': stored.last_change_run_id,
            'last_seen_run_id': stored.last_seen_run_id, 'first_seen_at': stored.first_seen_at,
            'last_changed_at': stored.last_changed_at, 'last_seen_at': stored.last_seen_at,
            'latest_attempt': status.latest_run, 'latest_success': status.latest_complete_run,
            'retention': 'rolling_feed_articles_retained',
        }, catalog.notes

    @staticmethod
    def _asset(connection, identifier):
        row = connection.execute('SELECT id,value,created_at FROM assets WHERE id=?', (identifier,)).fetchone()
        if row is None:
            _not_found()
        _uuid(row[0])
        if normalize_domain(row[1]) != row[1]:
            raise ValueError('Noncanonical asset domain')
        _time(row[2])
        return {'id': row[0], 'value': row[1], 'created_at': row[2]}, {}, {'source': 'local-assets'}, (
            'Kayıtlı domain sahiplik veya aktif kontrol yetkisi kanıtı değildir.',)

    @staticmethod
    def _candidate(connection, identifier):
        if connection.execute('SELECT 1 FROM surface_candidates WHERE id=?', (identifier,)).fetchone() is None:
            _not_found()
        details = SQLiteSurfaceCandidateRepository._details(connection, identifier, source_limit=MAX_DETAIL_ROWS + 1)
        value = details.candidate
        if len(details.sources) != details.total_source_count or len(details.sources) > MAX_DETAIL_ROWS:
            raise StorageError('Alt alan adı kaynakları güvenli kayıt ayrıntısı sınırını aşıyor.')
        asset = connection.execute('SELECT value FROM assets WHERE id=?', (value.asset_id,)).fetchone()
        if (asset != (value.asset_value,) or not details.events
                or details.events[0].action != 'discovered'
                or (details.events[-1].status, details.events[-1].reason) != (value.status, value.reason)
                or any(item.candidate_id != value.id for item in (*details.sources, *details.events))):
            raise ValueError('Candidate evidence differs')
        return value, {'sources': details.sources, 'events': details.events}, {
            'source': 'passive-discovery', 'first_seen_at': value.first_seen_at, 'last_seen_at': value.last_seen_at,
        }, ('Alt alan adı adayıdır; sahiplik veya güncel erişilebilirlik kararı değildir.',)

    @staticmethod
    def _finding(connection, identifier):
        if connection.execute('SELECT 1 FROM findings WHERE id=?', (identifier,)).fetchone() is None:
            _not_found()
        counts = {}
        for table, field in (('finding_observations', 'finding_id'), ('reviews', 'finding_id')):
            counts[table] = connection.execute(f'SELECT COUNT(*) FROM {table} WHERE {field}=?', (identifier,)).fetchone()[0]
            if counts[table] > MAX_DETAIL_ROWS:
                raise StorageError('Bulgu kanıt geçmişi güvenli okuma sınırını aşıyor.')
        details = SQLiteFindingRepository._details(connection, identifier)
        value = details.finding
        _uuid(value.id)
        asset = connection.execute('SELECT value FROM assets WHERE id=?', (value.asset_id,)).fetchone()
        if (asset != (value.asset_value,) or normalize_domain(value.domain) != value.domain
                or value.status not in {'new', 'suspicious', 'uncertain', 'dismissed'}
                or datetime.fromisoformat(_time(value.last_seen_at)) < datetime.fromisoformat(_time(value.created_at))
                or not details.observations or len(details.observations) != counts['finding_observations']
                or len(details.reviews) != counts['reviews']):
            raise ValueError('Finding evidence differs')
        for observation in details.observations:
            _uuid(observation.id)
            _time(observation.ingested_at)
            if observation.observed_at is not None:
                _time(observation.observed_at)
            if (observation.domain != value.domain or type(observation.source_line) is not int
                    or observation.source_line < 1 or not isinstance(observation.source_sha256, str)
                    or len(observation.source_sha256) != 64
                    or any(char not in '0123456789abcdef' for char in observation.source_sha256)):
                raise ValueError('Finding source domain differs')
        for review in details.reviews:
            _uuid(review.id)
            _time(review.created_at)
            if review.finding_id != value.id or review.decision not in {'suspicious', 'uncertain', 'dismissed'}:
                raise ValueError('Finding review differs')
        if value.status != (details.reviews[-1].decision if details.reviews else 'new'):
            raise ValueError('Finding review state differs')
        return value, {'observations': details.observations, 'reviews': details.reviews}, {
            'source': 'local-match', 'rule_version': value.rule_version,
        }, ('Eşleşme ve kaynak kanıtıdır; tek başına taklit veya zararlılık hükmü değildir.',)

    @staticmethod
    def _watch(connection, identifier):
        watches, events, runs, _ = SQLiteBrandUsernameWatchRepository._audit(connection)
        value = watches.get(identifier)
        if value is None:
            _not_found()
        return value, {
            'events': tuple(event for event in events if event.watch_id == identifier),
            'runs': tuple(sorted((run for run in runs.values() if run.watch_id == identifier), key=lambda run: run.sequence)),
        }, {'source': value.source_key, 'definition_sha256': SQLiteBrandUsernameWatchRepository._definition(value)}, (
            'İzleme tanımıdır; hesap bulunduğu veya kimliğin doğrulandığı anlamına gelmez.',)

    @staticmethod
    def _profile(connection, identifier):
        watches, runs, items, candidates, _, _, reviews, _ = SQLiteBrandUsernameReviewRepository._audit(connection)
        item = next((item for item in items if item.id == identifier), None)
        if item is None:
            _not_found()
        run = runs[item.run_id]
        watch = watches[run.watch_id]
        definition = SQLiteBrandUsernameWatchRepository._definition(watch)
        latest = max((value for value in runs.values() if value.watch_id == watch.id
                      and value.definition_sha256 == definition and value.status == 'complete'),
                     key=lambda value: value.sequence, default=None)
        candidate_id = brand_username_review_candidate_id(watch_id=watch.id,
            definition_sha256=run.definition_sha256, platform=item.platform, state_sha256=item.state_sha256)
        history = reviews.get(candidate_id, ())
        review = SQLiteBrandUsernameReviewRepository._state(candidate_id, history, candidates) if history else None
        return item, {'review_events': history}, {
            'source': run.source_name, 'run': run, 'watch_id': watch.id,
            'current': watch.active and latest is not None and latest.id == run.id,
            'current_review': review,
        }, ('Öğe kendi tarihî çalışmasına aittir; güncel izleme tanımıyla yeniden yazılmaz.',
            'Bulunan profil kimliği veya taklidi doğrulamaz; unreported hesap yokluğu değildir.')

    @staticmethod
    def _catalog(connection, reference):
        if reference.kind == 'public-notice':
            history = read_public_notice_history(connection)
            runs, changes, field = history.runs, history.changes, 'notice'
            name, url, license_note = HIBP_SOURCE_NAME, HIBP_SOURCE_URL, HIBP_LICENSE
        elif reference.namespace == 'threatcluster':
            runs, changes = SQLiteRansomwareClaimRepository._audit(connection)
            field, name, url, license_note = 'claim', RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL, RANSOMWARE_SOURCE_LICENSE
        else:
            runs, changes = SQLiteRansomLookClaimRepository._audit(connection)
            field, name, url, license_note = 'claim', RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL, RANSOMLOOK_SOURCE_LICENSE
        by_id = {run.id: run for run in runs}
        selected = sorted((change for change in changes if getattr(change, field).id == reference.record_id),
                          key=lambda change: by_id[change.run_id].sequence)
        if not selected:
            _not_found()
        last = selected[-1]
        current = last.action != 'removed'
        success = next((run for run in reversed(runs) if run.status == 'complete'), None)
        record_run = success if current else by_id[last.run_id]
        provenance = {'source': name, 'source_url': url, 'license': license_note,
                      'current': current, 'latest_run': runs[-1] if runs else None,
                      'latest_complete_run': success, 'record_run_id': record_run.id,
                      'last_change_run_id': last.run_id, 'state_sha256': last.state_sha256}
        if reference.kind == 'public-notice':
            provenance['attribution'] = HIBP_ATTRIBUTION
        return getattr(last, field), {'changes': tuple({'change': change, 'run': by_id[change.run_id]} for change in selected)}, provenance, (
            'Son bilinen kaynak kaydıdır; katalogdan çıkarılma çözüm veya yanlış iddia kararı değildir.',
            'Değişim geçmişi yalnız ekleme, değişme ve çıkarılmadır; değişmeyen her toplama ayrı öğe değildir.',
            'Kaynak iddiasıdır; bağımsız doğrulanmış ihlal hükmü değildir.')

    @staticmethod
    def _supplier(connection, identifier):
        history = read_supplier_history(connection)
        value = history.suppliers.get(identifier)
        if value is None:
            _not_found()
        return value, {'events': tuple(event for event in history.events if event.supplier_id == identifier)}, {
            'source': 'local-suppliers',
        }, ('Kullanıcının tedarikçi tanımıdır; bu kayıt tek başına risk veya ihlal kararı değildir.',)

    @staticmethod
    def _organization(connection, identifier):
        state = SQLiteOrganizationRepository._audit(connection)
        value = state.organizations.get(identifier)
        if value is None:
            _not_found()
        links = sorted((stored.link for stored in state.links.values() if stored.link.organization_id == identifier),
                       key=lambda item: (item.target.kind, item.target.value, item.id))
        identifiers = {link.id for link in links}
        return value, {
            'events': tuple(event for event in state.events if event.organization_id == identifier),
            'links': tuple({'link': link, 'target': state.targets[link.target][1]} for link in links),
            'link_events': tuple(event for event in state.link_events if event.link_id in identifiers),
        }, {'source': 'local-organizations'}, ('Kuruluş gruplaması sahiplik veya müşteri erişim yalıtımı değildir.',)

    @staticmethod
    def _case(connection, identifier):
        row = connection.execute('SELECT id,title,summary,status,priority,resolution,created_at,updated_at,closed_at FROM cases WHERE id=?', (identifier,)).fetchone()
        if row is None:
            _not_found()
        value = SQLiteCaseRepository._case(row)
        links = tuple(link for link in read_case_evidence_links(connection) if link.case_id == identifier)
        tasks = tuple(SQLiteCaseRepository._task(row) for row in _rows(connection,
            'SELECT id,case_id,title,status,due_at,reason,created_at,updated_at FROM case_tasks WHERE case_id=? ORDER BY created_at,id', (identifier,)))
        raw = _rows(connection, 'SELECT sequence,id,case_id,activity_type,reference_id,summary,reason,snapshot_json,snapshot_sha256,recorded_at FROM case_activities WHERE case_id=? ORDER BY sequence', (identifier,))
        activities = tuple(SQLiteCaseRepository._activity(row) for row in raw)
        lifecycle = [row for row in raw if row[3] in {'case_created', 'case_updated', 'status_changed'}]
        if (not activities or activities[0].activity_type != 'case_created' or not lifecycle
                or lifecycle[-1][7] != canonical_snapshot(SQLiteCaseRepository._case_payload(value))[0]
                or any(item.case_id != identifier for item in (*links, *tasks, *activities))):
            raise ValueError('Case evidence differs from current state')
        return value, {'evidence': links, 'tasks': tasks, 'activities': activities}, {
            'source': 'local-case-management',
        }, ('Kişisel vaka geçmişidir; kaynak kanıtları ile insan kararları ayrı korunur.',)

    def _intelligence(self, connection, reference):
        knowledge = SQLiteCtiKnowledgeRepository(self.storage.path)
        if reference.kind == 'cti':
            if connection.execute('SELECT 1 FROM cti_entities WHERE id=? AND entity_type=?', (reference.record_id, reference.record_type)).fetchone() is None:
                _not_found()
            details = knowledge._entity_details(connection, reference.record_id, 10_000, 100_000)
            record, kind = details.entity, 'entity'
        else:
            repository = SQLiteCtiIndicatorRepository(self.storage.path)
            row = repository._select_indicator(connection, reference.record_id)
            if row is None or row[1] != reference.record_type:
                _not_found()
            details = repository._details(connection, row, assertion_limit=10_000, event_limit=100_000)
            record, kind = details.indicator, 'indicator'
        if not details.assertions:
            raise ValueError('Missing intelligence source assertion')
        _audit_assertion_history(connection, details, kind)
        if any(assertion.source_name == ATTACK_SOURCE_NAME for assertion in details.assertions):
            knowledge._audit_attack_source(connection)
        return record, {'assertions': details.assertions, 'events': details.events}, {
            'source': reference.namespace,
        }, ('Her kaynak iddiası kendi güveni, açıklaması ve geçmişiyle korunur; otomatik doğrulama değildir.',)
