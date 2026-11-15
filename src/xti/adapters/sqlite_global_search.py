"""One read-only SQLite snapshot for the personal workspace search.

Existing source readers own history validation. This adapter composes their
records; it never collects a source, initializes storage or persists a view.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_reviews import SQLiteBrandUsernameReviewRepository
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository, read_case_evidence_links
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository, _FINDING_COLUMNS
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_public_notices import read_public_notice_history
from xti.adapters.sqlite_news import read_news_catalog
from xti.adapters.sqlite_mentions import read_mentions_catalog
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_supplier_history import read_supplier_history
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.brand_username_reviews import brand_username_review_candidate_id
from xti.domain.cases import canonical_snapshot
from xti.domain.cti_knowledge import search_query_key
from xti.domain.engine import reference_for_result
from xti.domain.global_search import (
    GLOBAL_SEARCH_KINDS, MAX_SEARCH_ROWS, GlobalSearchCoverage, GlobalSearchReport,
    GlobalSearchResult, global_match, normalize_global_kinds, normalize_global_query,
)
from xti.domain.organization_report import ReportNavigation
from xti.domain.organizations import normalize_organization_id
from xti.domain.mentions import build_query, request_key
from xti.domain.global_saved_searches import mention_semantic
from xti.domain.ransomlook_ransomware import RANSOMLOOK_SOURCE_LICENSE
from xti.domain.ransomware_claims import RANSOMWARE_SOURCE_LICENSE


def _rows(connection, query, parameters=()):
    rows = connection.execute(query + ' LIMIT ?', (*parameters, MAX_SEARCH_ROWS + 1)).fetchall()
    if len(rows) > MAX_SEARCH_ROWS:
        raise StorageError('Yerel aramanın bir kayıt kapsamı 50.000 sınırını aşıyor; kısmi sonuç üretilmedi.')
    return rows


def _time(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError('Invalid search record time')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Search record time needs timezone')
    return parsed.astimezone(timezone.utc).isoformat()


def _nav(label, *arguments):
    return ReportNavigation(label, arguments)


class _SearchReader:
    def __init__(self, connection, path, query, include_inactive, checked_at, *, tracking=False,
                 mention_request_key=None, mention_run_id=None, news_run_ids=None):
        self.connection, self.path, self.query = connection, path, query
        self.include_inactive, self.checked_at = include_inactive, checked_at
        self.results, self.coverage = [], []
        self.observations = [] if tracking else None
        self.mention_request_key, self.mention_run_id = mention_request_key, mention_run_id
        self.news_run_ids = news_run_ids

    def track(self, result, *, identity=None, semantic=None):
        if self.observations is None:
            return
        if len(self.observations) >= MAX_SEARCH_ROWS:
            raise StorageError('Kayıtlı genel arama tam sonuç sınırını aşıyor; kısmi çalışma kaydedilmedi.')
        identity = identity or reference_for_result(result).to_dict()
        self.observations.append((result, identity, semantic or {}))

    def add(self, kind, record_type, record_id, display_value, status, current,
            recorded_at, source, fields, *, source_run_id=None, details=(), navigation=(),
            tracking_identity=None, semantic=None):
        recorded_at = _time(recorded_at)
        match = global_match(self.query, fields)
        if match is None:
            return
        match_type, matched_field, matched_value = match
        result = GlobalSearchResult(
            kind, record_type, record_id, display_value, matched_field, matched_value,
            match_type, status, current, recorded_at, source, source_run_id,
            tuple(details), tuple(navigation),
        )
        self.results.append(result)
        self.track(result, identity=tracking_identity, semantic=semantic)

    def cover(self, kind, source, count, start, *, latest=None, success=None, notes=()):
        notes = list(notes)
        if latest is not None and latest.status == 'failed':
            notes.append('Son kaynak denemesi başarısız; önceki başarılı kanıtlar yeni kontrol sayılmaz.')
            if latest.error:
                notes.append('Kaynak hatası: ' + latest.error)
        if success is None and latest is not None:
            notes.append('Bu kapsam için başarılı kaynak çalışması yok; sıfır sonuç yokluk kanıtı değildir.')
        at = None
        if success is not None:
            at = _time(getattr(success, 'finished_at', None) or success.recorded_at)
        self.coverage.append(GlobalSearchCoverage(
            kind, source, count, len(self.results) - start,
            latest.id if latest else None, latest.status if latest else None,
            success.id if success else None, at, tuple(notes),
            _time(getattr(latest, 'finished_at', None) or latest.recorded_at) if latest else None,
        ))

    def assets(self):
        rows = _rows(self.connection, 'SELECT id,value,created_at FROM assets ORDER BY id')
        result = {}
        for identifier, domain, created_at in rows:
            normalize_organization_id(identifier)
            if normalize_domain(domain) != domain:
                raise ValueError('Noncanonical asset')
            _time(created_at)
            result[identifier] = (domain, created_at)
        return result

    def domains(self):
        start, assets = len(self.results), self.assets()
        for identifier, (domain, created_at) in assets.items():
            self.add('domain', 'registered_domain', identifier, domain, 'registered', True,
                     created_at, 'local-assets', (('domain', domain),),
                     navigation=(_nav('Domain analizi', 'analyze', domain),))
        self.cover('domain', 'local-assets', len(assets), start,
                   notes=('Kayıtlı domain sahiplik veya aktif test yetkisi doğrulaması değildir.',))
        start = len(self.results)
        rows = _rows(self.connection, 'SELECT id FROM surface_candidates ORDER BY id')
        for (identifier,) in rows:
            data = SQLiteSurfaceCandidateRepository._details(
                self.connection, identifier, source_limit=MAX_SEARCH_ROWS + 1,
            )
            value = data.candidate
            if len(data.sources) != data.total_source_count or len(data.sources) > MAX_SEARCH_ROWS:
                raise StorageError('Alt alan adı kaynak kapsamı sınırı aşılıyor; kısmi arama üretilmedi.')
            if value.asset_id not in assets or value.asset_value != assets[value.asset_id][0]:
                raise ValueError('Candidate parent differs')
            if (any(item.candidate_id != value.id for item in (*data.sources, *data.events))
                    or not data.events or data.events[0].action != 'discovered'
                    or (data.events[-1].status, data.events[-1].reason) != (value.status, value.reason)):
                raise ValueError('Candidate decision or source binding differs')
            current = value.status != 'rejected'
            if not current and not self.include_inactive:
                continue
            self.add('domain', 'surface_candidate', value.id, value.domain, value.status,
                     current, value.last_seen_at, 'passive-discovery',
                     (('domain', value.domain), ('root_domain', value.asset_value)),
                     details=(f'Kök domain: {value.asset_value}', f'İnsan gerekçesi: {value.reason}',
                              'Kaynaklar: ' + ', '.join(sorted({source.provider for source in data.sources}))),
                     semantic={'root_domain': value.asset_value, 'reason': value.reason,
                               'providers': sorted({source.provider for source in data.sources})},
                     navigation=(_nav('Aday ve kaynakları', 'surface', 'candidate', 'show', value.id),))
        self.cover('domain', 'passive-discovery', len(rows), start,
                   notes=('Pasif alt alan adaylarıdır; aday kaydı güncel kontrol veya sahiplik kanıtı değildir.',
                          'Reddedilmiş adaylar yalnız --all seçildiğinde eşleşmelere eklenir.'))

    def findings(self):
        start, assets = len(self.results), self.assets()
        rows = _rows(self.connection, f'SELECT {_FINDING_COLUMNS} FROM findings ORDER BY id')
        for row in rows:
            value = SQLiteFindingRepository._finding(row)
            normalize_organization_id(value.id)
            if (value.asset_id not in assets or value.asset_value != assets[value.asset_id][0]
                    or normalize_domain(value.domain) != value.domain
                    or value.status not in {'new', 'suspicious', 'uncertain', 'dismissed'}):
                raise ValueError('Finding identity or state differs')
            if datetime.fromisoformat(_time(value.last_seen_at)) < datetime.fromisoformat(_time(value.created_at)):
                raise ValueError('Finding time regression')
            self.add('finding', 'brand_finding', value.id, value.domain, value.status, True,
                     value.last_seen_at, 'local-match',
                     (('domain', value.domain), ('asset_domain', value.asset_value)),
                     details=(f'İzlenen domain: {value.asset_value}',) + value.reasons,
                     semantic={'asset_domain': value.asset_value, 'reasons': value.reasons},
                     navigation=(_nav('Bulgu ve insan kararı', 'findings', 'show', value.id),))
        self.cover('finding', 'local-match', len(rows), start,
                   notes=('Tüm insan kararları, dismissed dahil, korunur; eşleşme taklit hükmü değildir.',))

    def social(self):
        watches, runs, items, candidates, _, _, reviews, _ = SQLiteBrandUsernameReviewRepository._audit(self.connection)
        if not watches:
            self.cover('social', 'username-watches', 0, len(self.results), notes=('Kayıtlı kullanıcı adı izlemesi yok.',))
        for watch in sorted(watches.values(), key=lambda value: value.id):
            selected = sorted((run for run in runs.values() if run.watch_id == watch.id), key=lambda run: run.sequence)
            definition = SQLiteBrandUsernameWatchRepository._definition(watch)
            latest = selected[-1] if selected else None
            success = next((run for run in reversed(selected)
                            if run.status == 'complete' and run.definition_sha256 == definition), None)
            latest_items = {}
            eligible = {run.id: run for run in selected if run.status == 'complete'}
            for item in sorted(items, key=lambda item: runs[item.run_id].sequence):
                run = eligible.get(item.run_id)
                if run is not None:
                    latest_items[(run.definition_sha256, item.platform)] = item
            start = len(self.results)
            if watch.active or self.include_inactive:
                self.add('social', 'username_watch', watch.id, watch.display_name,
                         'active' if watch.active else 'inactive', watch.active, watch.updated_at,
                         watch.source_key, (('watch_name', watch.display_name), ('username', watch.username)),
                         details=(f'Kullanıcı adı: {watch.username}', f'Güncel tanım: {definition}',
                                  'İzleme tanımıdır; hesap bulunduğu anlamına gelmez.'),
                         semantic={'username': watch.username, 'definition_sha256': definition},
                         navigation=(_nav('İzleme', 'brand', 'watch-show', watch.id),))
            for (item_definition, _), item in sorted(latest_items.items()):
                run = runs[item.run_id]
                current = watch.active and success is not None and item.run_id == success.id
                if not current and not self.include_inactive:
                    continue
                details = [f'İzlemenin güncel etiketi: {watch.display_name} ({watch.id})', f'Kullanıcı adı: {run.username}',
                           f'Platform: {item.platform}', f'Çalışma tanımı: {item_definition}',
                           f'Değişim: {item.action}']
                navigation = [_nav('Kaynak çalışması', 'brand', 'watch-run-show', run.id)]
                review_state = None
                if item.status == 'found_unverified':
                    candidate_id = brand_username_review_candidate_id(
                        watch_id=watch.id, definition_sha256=item_definition,
                        platform=item.platform, state_sha256=item.state_sha256,
                    )
                    if candidate_id in reviews:
                        review = SQLiteBrandUsernameReviewRepository._state(candidate_id, reviews[candidate_id], candidates)
                        details.extend((f'İnsan kararı: {review.decision}', f'Gerekçe: {review.reason}'))
                        navigation.append(_nav('İnsan incelemesi', 'brand', 'watch-review-show', candidate_id))
                        review_state = {'decision': review.decision, 'reason': review.reason}
                self.add('social', 'social_profile', item.id, item.profile_url or f'{run.username} / {item.platform}',
                         item.status, current, run.recorded_at, run.source_name,
                         (('username', run.username), ('profile_url', item.profile_url), ('platform', item.platform)),
                         source_run_id=run.id, details=details, navigation=navigation,
                         tracking_identity={'kind': 'social', 'record_type': 'social_profile',
                                            'namespace': watch.source_key, 'watch_id': watch.id,
                                            'definition_sha256': item_definition, 'platform': item.platform},
                         semantic={'username': run.username, 'platform': item.platform,
                                   'profile_url': item.profile_url, 'review': review_state,
                                   'watch_id': watch.id, 'definition_sha256': item_definition,
                                   'source_key': watch.source_key})
            notes = [f'İzleme: {watch.display_name} ({watch.id}); etkin={watch.active}.',
                     'Varsayılan: güncel tanımın son başarılı çalışması; --all: her tanım/platformun son bilinen kaydı.',
                     'unreported hesap yokluğu/silinmesi değildir; bulunan profil kimliği veya taklidi doğrulamaz.']
            if latest is None:
                notes.append('Bu izleme henüz çalıştırılmamış.')
            elif latest.definition_sha256 != definition:
                notes.append('Son deneme eski tanıma aittir; güncel tanımın kontrolü sayılmaz.')
            self.cover('social', watch.source_key, 1 + len(latest_items), start,
                       latest=latest, success=success, notes=notes)

    def catalog(self, *, kind, source, runs, changes, value_of, license_note):
        start, current, known, change_run = len(self.results), {}, {}, {}
        run_by_id = {run.id: run for run in runs}
        for item in sorted(changes, key=lambda item: run_by_id[item.run_id].sequence):
            value = value_of(item)
            known[value.id], change_run[value.id] = value, run_by_id[item.run_id]
            if item.action == 'removed':
                current.pop(value.id, None)
            else:
                current[value.id] = value
        latest = runs[-1] if runs else None
        success = next((run for run in reversed(runs) if run.status == 'complete'), None)
        selected = known if self.include_inactive else current
        for identifier, value in sorted(selected.items()):
            is_current = identifier in current
            run = success if is_current else change_run[identifier]
            if kind == 'ransomware':
                details = (f'Grup: {value.group}', f'Kaynak olay zamanı: {value.discovered_at}',
                           'Kaynağın iddiası; doğrulanmış ihlal hükmü değildir.', license_note)
                if source == 'threatcluster':
                    details += (f'Kaynak ilan durumu: {value.status}', f'Kaynak domaini: {value.website or "belirtilmemiş"}',
                                f'Ülke: {value.country or "belirtilmemiş"}; sektör: {value.sector or "belirtilmemiş"}',
                                f'Kaynakta son görülme: {value.last_seen_at or "belirtilmemiş"}',
                                f'Kaynakta ilandan çıkarılma: {value.delisted_at or "belirtilmemiş"}')
                fields = (('victim', value.victim), ('group', value.group), ('website', getattr(value, 'website', None)))
                display, record_type = value.victim, 'ransomware_claim'
                navigation = (_nav('Kaynak çalışma geçmişi', 'ransomware', 'status', '--source', source),)
            else:
                flags = ', '.join(f'{name}={getattr(value, name)}' for name in (
                    'is_verified', 'is_fabricated', 'is_sensitive', 'is_retired',
                    'is_spam_list', 'is_malware', 'is_stealer_log'))
                details = (f'Domain: {value.domain or "belirtilmemiş"}', f'Kaynak olay tarihi: {value.breach_date}',
                           f'Kaynağa eklenme: {value.added_at}', f'Kaynakta değişme: {value.modified_at}',
                           f'Kaynağın kayıt sayısı: {value.pwn_count}',
                           'Veri kategorileri: ' + ', '.join(value.data_classes),
                           'Kaynak sınıfları (XTI kararı değil): ' + flags,
                           value.source_url, license_note)
                if value.source_attribution:
                    details += ('Kaynak katkısı: ' + value.source_attribution,)
                fields = (('title', value.title), ('domain', value.domain), ('notice_id', value.id))
                display, record_type = value.title, 'public_breach_notice'
                navigation = ((_nav('Kamu olay kanıtı', 'notices', 'show', identifier),) if is_current else
                              (_nav('Katalogdan çıkarılma kanıtı', 'notices', 'run-show', run.id),))
            semantic = asdict(value)
            if kind == 'ransomware':
                semantic.pop('last_seen_at', None)
            else:
                # Category order is publisher presentation, not a change in
                # exposed data. The exact original order remains in details.
                semantic['data_classes'] = sorted(value.data_classes)
            self.add(kind, record_type, identifier, display,
                     'source_claim' if is_current else 'withdrawn_from_catalog', is_current,
                     run.finished_at, source, fields, source_run_id=run.id,
                     details=details, navigation=navigation, semantic=semantic)
        notes = [license_note, 'Varsayılan son başarılı katalog; --all çıkarılmış kimliklerin son bilinen kaydını da içerir.',
                 'Aynı kimliğin eski sürümleri ve her çalışma ayrı arama satırı değildir.',
                 'Sıfır eşleşme ihlal olmadığını kanıtlamaz; kaynakta kaldırılma çözüm anlamına gelmez.']
        if latest is None:
            notes.append('Henüz bu kaynak için kayıtlı toplama yok; internet sorgulanmadı.')
        self.cover(kind, source, len(known), start, latest=latest, success=success, notes=notes)

    def ransomware(self):
        for source, repository, license_note in (
            ('threatcluster', SQLiteRansomwareClaimRepository, RANSOMWARE_SOURCE_LICENSE),
            ('ransomlook', SQLiteRansomLookClaimRepository, RANSOMLOOK_SOURCE_LICENSE),
        ):
            runs, items = repository._audit(self.connection)
            self.catalog(kind='ransomware', source=source, runs=runs, changes=items,
                         value_of=lambda item: item.claim, license_note=license_note)

    def public_notices(self):
        history = read_public_notice_history(self.connection)
        self.catalog(kind='public-notice', source=history.source_name,
                     runs=history.runs, changes=history.changes, value_of=lambda item: item.notice,
                     license_note=history.attribution + ' | ' + history.license)

    def news(self):
        catalog = read_news_catalog(self.connection, through_run_ids=self.news_run_ids)
        for status in catalog.sources:
            start = len(self.results)
            source = status.source
            records = tuple(record for record in catalog.articles if record.article.source_key == source.key)
            for record in records:
                article = record.article
                self.add('news', 'news_article', article.id, article.title,
                         'publisher_metadata', True, record.last_changed_at, source.key,
                         (('title', article.title), ('summary', article.summary), ('url', article.url)),
                         source_run_id=record.last_change_run_id,
                         details=(f'Özet: {article.summary}', f'Özet sınırlandı: {article.summary_truncated}',
                                  f'Özgün haber: {article.url}', f'Yayıncı: {source.name}', source.attribution,
                                  f'Kaynak yayın tarihi: {article.published_at or article.published_raw or "belirtilmedi"}',
                                  f'Kaynak güncelleme tarihi: {article.updated_at or article.updated_raw or "belirtilmedi"}',
                                  f'İlk toplama: {record.first_seen_at}', f'Son görülme: {record.last_seen_at}',
                                  'Son bilinen haber; akış penceresinden düşmesi silinme veya geri çekilme sayılmaz.'),
                         semantic=asdict(article),
                         navigation=(_nav('Haber ayrıntısı', 'news', 'show', article.id),
                                     _nav('Kaynak çalışma kanıtı', 'news', 'run-show', record.last_change_run_id)))
            self.cover('news', source.key, len(records), start,
                       latest=status.latest_run, success=status.latest_complete_run,
                       notes=(source.attribution, source.url, *catalog.notes,
                              'Kayıt sayısı saklanan son bilinen haberlerdir; yalnız son akış yanıtının boyutu değildir.'))

    def mentions(self):
        catalog = (read_mentions_catalog(self.connection, through_run_id=self.mention_run_id)
                   if self.mention_run_id is not None else read_mentions_catalog(self.connection))
        records = tuple(record for record in catalog.records
                        if self.mention_request_key is None or record.request_key == self.mention_request_key)
        runs = tuple(run for run in catalog.runs
                     if self.mention_request_key is None or request_key(run.request) == self.mention_request_key)
        start = len(self.results)
        for record in records:
            request, hit = record.request, record.hit
            fields = ((('mention_request_key', self.mention_request_key),)
                      if self.mention_request_key is not None else
                      (('title', hit.title), ('summary', hit.summary), ('url', hit.url),
                       ('target_name', request.target.name),
                       ('target_domains', ', '.join(request.target.domains))))
            self.add('mention', 'company_mention', record.id, hit.title,
                     'search_candidate', True, record.last_changed_at, 'tavily',
                     fields,
                     source_run_id=record.last_change_run_id,
                     details=(f'Hedef: {request.target.name} ({request.target.kind})',
                              f'Hedef kimliği: {request.target.id}',
                              f'Arama: {build_query(request.target)} | kapsam: {request.topic} | sonuç sınırı: {request.max_results}',
                              f'Özgün bağlantı: {hit.url}', f'Özet: {hit.summary}',
                              f'Sağlayıcının tarih bilgisi: {hit.published_at or "belirtilmedi"}',
                              'Eşleşen terimler: ' + (', '.join(record.matched_terms) or 'Görünür metinde eşleşme yok'),
                              'Eşleşen alanlar: ' + (', '.join(record.match_fields) or 'Sağlayıcı arama adayı'),
                              f'İlk toplama: {record.first_seen_at}', f'Son görülme: {record.last_seen_at}',
                              'Arama sonucu adayı; doğrulanmış tehdit veya kesin kuruluş kimliği değildir.'),
                     semantic=mention_semantic(record),
                     navigation=(_nav('İçerik ayrıntısı', 'mentions', 'show', record.id),
                                 _nav('Arama çalışma kanıtı', 'mentions', 'run-show', record.last_change_run_id)))
        latest = runs[-1] if runs else None
        success = next((run for run in reversed(runs) if run.status == 'complete'), None)
        scope_note = ('Kaynak zamanı yalnız bu kesin hedef/sorgu kapsamına aittir.'
                      if self.mention_request_key is not None else
                      'Kaynak son deneme/başarı zamanı başka bir hedef veya arama kapsamına ait olabilir.')
        self.cover('mention', 'tavily', len(records), start, latest=latest, success=success,
                   notes=('Yalnız açıkça aranmış hedeflerin saklanan son bilinen sonuçlarıdır.',
                          scope_note,
                          'Her istek en çok 20 sıralanmış sonuç alır; sonuç yokluğu internette içerik yokluğu değildir.',
                          'Aramadan düşen eski sonuç silinmez; bu arama interneti yeniden sorgulamaz.'))

    def cases(self):
        start = len(self.results)
        links = read_case_evidence_links(self.connection)
        rows = _rows(self.connection, 'SELECT id,title,summary,status,priority,resolution,created_at,updated_at,closed_at FROM cases ORDER BY id')
        activities = _rows(self.connection, 'SELECT sequence,id,case_id,activity_type,reference_id,summary,reason,snapshot_json,snapshot_sha256,recorded_at FROM case_activities ORDER BY sequence')
        by_case = {}
        for row in activities:
            value = SQLiteCaseRepository._activity(row)
            by_case.setdefault(value.case_id, []).append((value, row))
        case_ids = {row[0] for row in rows}
        if set(by_case) - case_ids or any(link.case_id not in case_ids for link in links):
            raise ValueError('Case history references missing case')
        for row in rows:
            value = SQLiteCaseRepository._case(row)
            timeline = by_case.get(value.id, [])
            lifecycle = [item for item in timeline if item[0].activity_type in {'case_created', 'case_updated', 'status_changed'}]
            if (not timeline or timeline[0][0].activity_type != 'case_created' or not lifecycle
                    or lifecycle[-1][1][7] != canonical_snapshot(SQLiteCaseRepository._case_payload(value))[0]):
                raise ValueError('Case state differs from lifecycle evidence')
            selected_links = [link for link in links if link.case_id == value.id and (link.active or self.include_inactive)]
            fields = (('title', value.title), ('summary', value.summary)) + tuple(
                ('linked_evidence' if link.active else 'removed_evidence', link.display_value) for link in selected_links)
            evidence_details = tuple(f'Kanıt: {link.evidence_type} / {link.evidence_id}; bağlantı={link.id}; etkin={link.active}'
                                     for link in selected_links if global_match(self.query, (('evidence', link.display_value),)))
            self.add('case', 'case', value.id, value.title, value.status, True,
                     value.updated_at, 'local-case-management', fields,
                     details=(f'Öncelik: {value.priority}', f'Özet: {value.summary}',
                              f'Vaka durumu zamanı: {lifecycle[-1][0].recorded_at}',
                              f'Son vaka etkinliği: {timeline[-1][0].recorded_at}') + evidence_details,
                     semantic={'priority': value.priority, 'summary': value.summary, 'resolution': value.resolution,
                               'links': [{'id': link.id, 'evidence_type': link.evidence_type,
                                          'evidence_id': link.evidence_id, 'display_value': link.display_value,
                                          'active': link.active} for link in sorted(selected_links, key=lambda item: item.id)]},
                     navigation=(_nav('Vaka', 'cases', 'show', value.id),))
        self.cover('case', 'local-case-management', len(rows), start,
                   notes=('Kişisel çalışma alanının tüm vaka durumları aranır; başlık, özet ve açık kanıt bağlantıları eşleşir.',
                          'Vaka alanları son güncel sürümdür; eski notlar ve tüm kanıt JSON içerikleri aranmaz.',
                          'Kaldırılan kanıt bağlantıları yalnız --all ile eşleşebilir; etkinlikleri ayrıca gösterilir.'))

    def suppliers(self):
        start = len(self.results)
        values = read_supplier_history(self.connection).suppliers.values()
        for value in values:
            if not value.active and not self.include_inactive:
                continue
            self.add('supplier', 'supplier', value.id, value.display_name,
                     'active' if value.active else 'inactive', value.active, value.updated_at,
                     'local-suppliers', (('name', value.display_name), ('domain', value.primary_domain)),
                     details=(f'Birincil domain: {value.primary_domain}', f'İlişki: {value.relationship_type}',
                              f'Önem: {value.criticality}'),
                     semantic={'domain': value.primary_domain, 'relationship_type': value.relationship_type,
                               'criticality': value.criticality},
                     navigation=(_nav('Tedarikçi', 'suppliers', 'show', value.id),))
        self.cover('supplier', 'local-suppliers', len(values), start,
                   notes=('Yerel tedarikçi tanımıdır; risk veya ihlal kararı değildir.',))

    def organizations(self):
        start = len(self.results)
        values = SQLiteOrganizationRepository._audit(self.connection).organizations.values()
        for value in values:
            if not value.active and not self.include_inactive:
                continue
            self.add('organization', 'organization', value.id, value.display_name,
                     'active' if value.active else 'inactive', value.active, value.updated_at,
                     'local-organizations', (('name', value.display_name),),
                     details=(f'Tanım sürümü: {value.revision}',),
                     semantic={'revision': value.revision},
                     navigation=(_nav('Kuruluş', 'organizations', 'show', value.id),))
        self.cover('organization', 'local-organizations', len(values), start,
                   notes=('Kişisel kuruluş gruplarıdır; müşteri ayrımı veya sahiplik doğrulaması değildir.',))

    def intelligence(self, kinds):
        repo = SQLiteCtiKnowledgeRepository(self.path)
        selected_kind = 'all' if {'cti', 'indicator'} <= set(kinds) else 'entity' if 'cti' in kinds else 'indicator'
        report = repo.search_snapshot(self.connection, query=self.query, query_key=search_query_key(self.query),
                                      kind=selected_kind, entity_type=None, indicator_type=None,
                                      active_only=not self.include_inactive, checked_at=self.checked_at,
                                      limit=MAX_SEARCH_ROWS * 2)
        if len(report.results) != report.total_match_count:
            raise StorageError('CTI arama kapsamı eksik; kısmi birleşik sonuç üretilmedi.')
        for kind, table in (('cti', 'cti_entities'), ('indicator', 'cti_indicators')):
            if kind not in kinds:
                continue
            start = len(self.results)
            count = self.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for result in report.results:
                if (result.kind == 'entity') != (kind == 'cti'):
                    continue
                if kind == 'cti':
                    data = repo._entity_details(self.connection, result.record_id, 10_000, 100_000)
                    at = data.entity.updated_at
                    assertions = tuple(value for value in data.assertions if self.include_inactive or value.active)
                    navigation = (_nav('CTI varlığı', 'cti', 'entity-show', result.record_id),)
                else:
                    row = self.connection.execute('SELECT id,indicator_type,value,created_at,updated_at FROM cti_indicators WHERE id=?', (result.record_id,)).fetchone()
                    data = SQLiteCtiIndicatorRepository(self.path)._details(self.connection, row, assertion_limit=10_000, event_limit=100_000)
                    at = data.indicator.updated_at
                    assertions = tuple(value for value in data.assertions if self.include_inactive or SQLiteCtiIndicatorRepository._is_current(value, self.checked_at))
                    navigation = (_nav('IOC kanıtı', 'ioc', 'show', result.record_id),)
                current = result.current_assertion_count > 0
                sources = ', '.join(sorted({value.source_name for value in assertions}))
                details = (f'Etkin kaynak iddiası: {result.current_assertion_count}/{result.total_assertion_count}',
                           f'En yüksek etkin kaynak güveni: {result.max_current_confidence}',) + tuple(
                    f'Kaynak: {value.source_name} | {value.source_reference} | etkin={value.active}' for value in assertions)
                value = GlobalSearchResult(kind, result.record_type, result.record_id, result.display_value,
                    result.matched_field, result.matched_value, result.match_type,
                    'active_source_assertions' if current else 'inactive_source_assertions', current,
                    _time(at), sources, details=details, navigation=navigation)
                self.results.append(value)
                self.track(value, semantic={
                    'current_assertion_count': result.current_assertion_count,
                    'total_assertion_count': result.total_assertion_count,
                    'max_current_confidence': result.max_current_confidence,
                    'sources': [{'source_name': item.source_name, 'source_reference': item.source_reference,
                                 'active': item.active} for item in sorted(assertions, key=lambda item: item.id)],
                })
            self.cover(kind, 'local-cti', count, start,
                       notes=('Mevcut cti search araması ve kaynak geçmişi denetimi kullanılır; açıklama gövdeleri aranmaz.',
                              'Varsayılan etkin/geçerli kaynak iddiaları; --all etkin olmayan kimlik ve kaynak alanlarını da içerir.'))


def read_global_search_snapshot(connection, path, query, *, kinds, include_inactive, checked_at,
                                tracking=False, mention_request_key=None, mention_run_id=None, news_run_ids=None):
    """Compose all selected families inside the caller's existing transaction."""
    if mention_request_key is not None and (kinds != ('mention',) or query != mention_request_key
                                           or include_inactive):
        raise ValueError('Typed mention search requires its exact request scope')
    if mention_run_id is not None and mention_request_key is None:
        raise ValueError('Historical mention source run requires an exact request scope')
    if news_run_ids is not None and (kinds != ("news",) or include_inactive):
        raise ValueError("Historical news collection requires news-only scope")
    reader = _SearchReader(connection, path, query, include_inactive, checked_at, tracking=tracking,
                           mention_request_key=mention_request_key, mention_run_id=mention_run_id, news_run_ids=news_run_ids)
    handlers = {'domain': reader.domains, 'finding': reader.findings, 'social': reader.social,
                'ransomware': reader.ransomware, 'public-notice': reader.public_notices, 'news': reader.news,
                'mention': reader.mentions,
                'case': reader.cases, 'supplier': reader.suppliers, 'organization': reader.organizations}
    for kind in kinds:
        if kind in handlers:
            handlers[kind]()
    if 'cti' in kinds or 'indicator' in kinds:
        reader.intelligence(kinds)
    reader.results.sort(key=lambda value: (
        ('exact', 'prefix', 'contains').index(value.match_type), GLOBAL_SEARCH_KINDS.index(value.kind),
        value.record_type, value.display_value.casefold(), value.source, value.record_id,
    ))
    return reader


class SQLiteGlobalSearchRepository:
    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    def search(self, query, *, kinds, include_inactive, checked_at, offset, limit):
        query, kinds = normalize_global_query(query), normalize_global_kinds(kinds)
        if (type(include_inactive) is not bool or type(offset) is not int or not 0 <= offset <= 1_000_000
                or type(limit) is not int or not 1 <= limit <= 500):
            raise ValidationError('Yerel arama seçenekleri geçersiz.')
        try:
            checked_at = _time(checked_at)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError('Yerel arama zamanı geçersiz.') from error
        try:
            with self._storage._connection(readonly=True) as connection:
                connection.execute('BEGIN')
                reader = read_global_search_snapshot(connection, self._storage.path, query,
                    kinds=kinds, include_inactive=include_inactive, checked_at=checked_at)
                ordered = reader.results
                selected = tuple(ordered[offset:offset + limit])
                return GlobalSearchReport(query, kinds, include_inactive, checked_at, len(ordered), offset, limit,
                    offset + len(selected) < len(ordered), selected, tuple(reader.coverage), (
                        'Yalnız bu kişisel çalışma alanının kayıtları tek okuma anında aranır; internet sorgusu veya kayıt değişikliği yapılmaz.',
                        'Taranan kayıt sayısı etkin olmayan denetlenmiş kimlikleri de kapsar; sonuç filtresi varsayılan güncel kayıtlardır.',
                        '--all tüm sürüm arşivi değildir: kaynak kimliğinin son bilinen kaydı ve sosyal tanım/platform başına son kayıt seçilir.',
                        'Arama eşleşmesi yeni güvenlik bulgusu, sahiplik veya doğrulanmış ihlal değildir; sonuç yokluğu güvenli demek değildir.',
                        'Kaynak ham yanıtları, komut metinleri, tüm notlar, bildirimler ve her teknik kontrol geçmişi bu isim/değer aramasının dışında kalır.',
                    ))
        except (TypeError, ValueError, KeyError, IndexError, AttributeError, OverflowError) as error:
            raise StorageError('Yerel arama kayıtları veya kaynak bağları bozuk; kısmi sonuç üretilmedi.') from error
