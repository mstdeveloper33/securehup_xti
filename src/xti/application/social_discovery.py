"""Merge bounded independent discoveries, then verify each unique profile once."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import time
from urllib.parse import urlsplit

from xti.domain.assets import ValidationError
from xti.domain.brand_username import ALL_PLATFORM_HOSTS
from xti.domain.social_discovery import (
    POLICY, MAX_CANDIDATES, STATES, SocialDiscoveryError, assess, parameters, profile_url, seeds, usernames,
)
from xti.ports.social_discovery import PublicProfilePages, SocialDiscoverySources, SocialDiscoveryRepository


NOTES = [
    'Bulundu: profil kimliği açık sayfa kanıtıyla doğrulandı; firmanın resmî hesabı olduğu doğrulanmadı.',
    'Aday: kaynak bildirdi, sayfa doğrulaması tamamlanamadı. Kontrol edilemedi: var/yok kararı verilmedi.',
    'Bulunamadı yalnız listelenen profil adresinin bu denemedeki sonucudur; firmanın başka hesabı olabilir.',
    'Kapsam seçili platformlar, türetilen kullanıcı adları ve bulunan bağlantılarla sınırlıdır; tüm internet değildir.',
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hosts(candidate):
    hosts = set()
    for host in ALL_PLATFORM_HOSTS[candidate['platform']]:
        hosts.update((host, 'www.' + host))
    if candidate['platform'] == 'HackerNews': hosts.add('news.ycombinator.com')
    hosts.add(urlsplit(candidate['url']).hostname)
    return tuple(sorted(hosts))


class SocialDiscoveryService:
    def __init__(self, repository: SocialDiscoveryRepository, *, pages: PublicProfilePages | None = None,
                 sources: SocialDiscoverySources | None = None, clock=None, monotonic=None):
        self.repository, self.pages, self.sources = repository, pages, sources
        self.clock, self.monotonic = clock or _now, monotonic or time.monotonic

    def execute(self, operation, **options):
        options = parameters(operation, options)
        if operation == 'brand.discovery.plan':
            return {'scope': options, 'usernames': list(usernames(options)), 'policy': POLICY,
                    'network_access': False, 'page_concurrency': 4,
                    'web_search_max_requests': 3 if options['web_search'] else 0,
                    'web_search_max_credits': 6 if options['web_search'] else 0,
                    'notes': NOTES}
        if operation == 'brand.discovery.list': return self.repository.list(**options)
        if operation == 'brand.discovery.show': return self.repository.show(options['identifier'])
        key = options.pop('idempotency_key')
        return self._run(options, key)

    def run_tracking(self, scope, context, key):
        """Internal workflow only: public discovery parameters cannot inject targets."""
        from xti.domain.social_retained import validate_scope
        return self._run(validate_scope({**scope, 'tracking': context}), key)

    def reserve_tracking(self, scope, context, key):
        """Close a cancelled recovery without collecting or inventing provider data."""
        from xti.domain.social_retained import validate_scope
        return self.repository.reserve(validate_scope({**scope, 'tracking': context}), key, self.clock())

    def _run(self, options, key):
        if self.pages is None or self.sources is None:
            raise SocialDiscoveryError('invalid_parameters', 'Sosyal keşif için toplama adaptörleri gerekli.')
        receipt = self.repository.reserve(options, key, self.clock())
        if receipt['replayed']: return receipt
        report = self._collect(options)
        return self.repository.finish(receipt['record']['id'], report, self.clock())

    def _collect(self, scope):
        start = self.monotonic(); deadline = start + scope['budget_seconds']
        candidates, source_runs, ignored, truncated = {}, [], 0, False
        def add(url, source, *, claimed=False, platform=None, username=None):
            nonlocal ignored, truncated
            try:
                item = profile_url(url, platform)
                if item['platform'] not in scope['platforms']: return
                comparable = item['username'].removesuffix('.bsky.social') if item['platform'] == 'Bluesky' else item['username']
                if username and comparable.casefold() != username.casefold():
                    raise ValidationError('Farklı kullanıcı adı.')
            except ValidationError:
                ignored += 1
                return
            if item['url'] not in candidates:
                if len(candidates) >= MAX_CANDIDATES:
                    truncated = True
                    return
                candidates[item['url']] = {**item, 'discovered_by': [], 'claimed_by': [], 'aliases': []}
            row = candidates[item['url']]
            if source not in row['discovered_by']: row['discovered_by'].append(source)
            if claimed and source not in row['claimed_by']: row['claimed_by'].append(source)

        # Persisted historical targets get a reserved, rotating half-page window.
        # They are not current ownership/source claims and never raise confidence.
        retained = scope.get('tracking', {}).get('urls', [])
        for url in retained: add(url, 'retained_profile')
        for seed in seeds(scope): add(seed['url'], 'username_hypothesis')
        for url in self.repository.known_links(scope['domain']): add(url, 'stored_company_search', claimed=True)

        # Reserve half the collection budget for the independent page checks.
        collection_deadline = start + scope['budget_seconds'] * 0.5
        home = 'https://' + scope['domain'] + '/'
        home_domain = scope['domain'].removeprefix('www.')
        # A corporate landing-page alias is followed only after an HTTP redirect;
        # this is an exact host list, not permission to crawl arbitrary subdomains.
        home_hosts = tuple(dict.fromkeys((scope['domain'], home_domain,
                                         'www.' + home_domain, 'about.' + home_domain)))
        with ThreadPoolExecutor(max_workers=4) as pool:
            home_task = pool.submit(self.pages.fetch, home, allowed_hosts=home_hosts,
                                    timeout=min(scope['timeout'], max(0.001, collection_deadline-self.monotonic())))
            tasks = []
            for username in usernames(scope):
                for source in ('maigret', 'sherlock'):
                    # Compute remaining in the worker, not before waiting in its queue.
                    def collect(source=source, username=username):
                        remaining = collection_deadline-self.monotonic()
                        if remaining <= 0:
                            return {'source': source, 'username': username, 'status': 'budget_exhausted',
                                    'matches': [], 'requested_platforms': [], 'unreported_platforms': []}
                        return self.sources.collect(source, username, tuple(scope['platforms']),
                                                    timeout=scope['timeout'], remaining=remaining)
                    tasks.append(pool.submit(collect))
            web = pool.submit(lambda: self.sources.search(scope, remaining=max(0, collection_deadline-self.monotonic()))) if scope['web_search'] else None
            homepage = home_task.result()
            if homepage.status == 200 and not homepage.error:
                for url in homepage.links: add(url, 'company_homepage', claimed=True)
            for task in tasks:
                run = task.result()
                source_runs.append({key: value for key, value in run.items() if key != 'matches'})
                for item in run['matches']:
                    add(item['url'], run['source'], claimed=True, platform=item['platform'], username=run['username'])
            if web is not None:
                for run in web.result():
                    source_runs.append({key: value for key, value in run.items() if key != 'matches'})
                    for item in run['matches']: add(item['url'], 'tavily', claimed=True)

        # Official links first; then hypotheses missed by tools, then other source claims.
        ordered = sorted(candidates.values(), key=lambda r: (
            'retained_profile' not in r['discovered_by'],
            retained.index(r['url']) if r['url'] in retained else len(retained),
            'company_homepage' not in r['discovered_by'], 'username_hypothesis' not in r['discovered_by'],
            r['platform'], r['url']))
        pages = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            def verify(candidate):
                remaining = deadline-self.monotonic()
                if remaining <= 0: return None
                return self.pages.fetch(candidate['url'], allowed_hosts=_hosts(candidate), timeout=min(scope['timeout'],remaining))
            tasks = [(item, pool.submit(verify, item)) for item in ordered[:scope['max_pages']]]
            for item, task in tasks: pages[item['url']] = task.result()
        for row in ordered:
            page = pages.get(row['url'])
            if page is None:
                decision = {'state': 'inconclusive', 'reason': 'page_budget_exhausted', 'brand_relation': 'unverified'}
                evidence = None
            else:
                decision = assess(row, page, scope)
                evidence = {'checked_at': page.checked_at, 'status': page.status, 'final_url': page.final_url,
                            'title': page.title, 'description': page.description, 'body_sha256': page.body_sha256,
                            'error': page.error, 'requests': page.requests, 'received_bytes': page.received_bytes,
                            'elapsed_seconds': page.elapsed_seconds, 'canonical_urls': list(page.canonical_urls),
                            'profile_type': page.profile_type, 'profile_username': page.profile_username,
                            'identity_text': page.visible_text[:4096] if row['platform']=='HackerNews' or page.visible_text.strip().casefold() in ('no such user.','no such user') else '',
                            'company_links': [url for url in page.links
                                if (urlsplit(url).hostname or '').removeprefix('www.') == scope['domain'].removeprefix('www.')][:8]}
            if decision['state'] == 'inconclusive' and row['claimed_by']:
                decision['state'] = 'candidate'
            row.update(decision, evidence=evidence)
        # LinkedIn company -> showcase is an observed route alias, not a second account.
        # Merge only when the redirected page itself proves the target profile.
        by_url={row['url']:row for row in ordered}
        removed=set()
        for row in ordered:
            page=pages.get(row['url'])
            if row['platform']!='LinkedIn' or page is None:continue
            try: target=profile_url(page.final_url,'LinkedIn')
            except ValidationError:continue
            routes={urlsplit(row['url']).path.split('/')[1],urlsplit(target['url']).path.split('/')[1]}
            if routes!={'company','showcase'} or target['username']!=row['username']:continue
            decision=assess(target,page,scope)
            if decision['state']!='found':continue
            other=by_url.get(target['url'])
            if other is not None and other['state']!='found':continue
            if other is None:
                old_url=row['url'];row.update(target,**decision);row['aliases'].append(old_url)
                by_url[target['url']]=row
            else:
                other['aliases'].append(row['url'])
                for field in ('discovered_by','claimed_by'):
                    other[field]=list(dict.fromkeys([*other[field],*row[field]]))
                removed.add(row['url'])
        ordered=[row for row in ordered if row['url'] not in removed]
        elapsed = round(self.monotonic()-start,3)
        coverage = []
        for platform in scope['platforms']:
            related = [row for row in ordered if row['platform'] == platform]
            coverage.append({'platform': platform,
                'source_checks': [r['source'] + ':' + r['username'] for r in source_runs
                                  if r.get('username') and platform in r.get('requested_platforms',[]) and r['status'] == 'complete'],
                'profiles': len(related), 'pages_checked': sum(r['evidence'] is not None for r in related),
                'found': sum(r['state'] == 'found' for r in related),
                'state': 'profile_found' if any(r['state'] == 'found' for r in related) else 'unresolved'})
        partial = (truncated or any(r['state'] in ('candidate','inconclusive') for r in ordered)
                   or any(r['status'] not in ('complete','unsupported') for r in source_runs)
                   or homepage.error is not None or homepage.status != 200)
        all_pages = [homepage, *[page for page in pages.values() if page is not None]]
        return {'policy': POLICY, 'scope': scope, 'usernames': list(usernames(scope)),
            'status': 'partial' if partial else 'complete', 'profiles': ordered,
            'counts': {state: sum(r['state'] == state for r in ordered) for state in STATES},
            'coverage': coverage, 'sources': source_runs,
            'homepage': {'url': home, 'status': homepage.status, 'error': homepage.error,
                         'checked_at': homepage.checked_at, 'body_sha256': homepage.body_sha256},
            'metrics': {'elapsed_seconds': elapsed, 'unique_profiles': len(ordered),
                'profile_pages_checked': sum(p is not None for p in pages.values()),
                'page_http_requests': sum(p.requests for p in all_pages),
                'page_received_bytes': sum(p.received_bytes for p in all_pages),
                'ignored_links': ignored, 'candidate_limit_reached': truncated,
                'merged_aliases': sum(len(row['aliases']) for row in ordered),
                'deadline_reached': self.monotonic() >= deadline,
                'tool_request_count': None,
                'web_search_credits_reported': sum(r.get('credits') or 0 for r in source_runs),
                'web_search_usage_unknown': any(r['source'] == 'tavily' and r.get('attempted') and r.get('credits') is None for r in source_runs)},
            'notes': NOTES + ['HTTP sayaçları ek sayfa kontrollerine aittir; Maigret/Sherlock iç trafiği ölçülmüyor.']}
