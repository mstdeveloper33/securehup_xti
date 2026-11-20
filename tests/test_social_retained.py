"""Previously observed addresses survive source gaps without gaining confidence."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.domain.assets import ValidationError
from xti.domain.social_discovery import Page, parameters, validate_report
from xti.domain.social_retained import validate_scope
from xti.domain.social_tracking import apply_event, empty_state
from tests import test_social_tracking as tracking
from tests.test_social_discovery import IG, SCOPE, page, profile


class RetainedTests(unittest.TestCase):
    def setUp(self):
        self.f = tracking.TrackingTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def test_removed_homepage_link_is_rechecked_and_timeout_is_not_account_loss(self):
        f = self.f
        f.mode = 'new'; f.later()
        seed = f.discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='seed-support')['record']
        watch = f.add(discovery_id=seed['id'])
        f.run_watch(watch)
        f.later(); f.mode = 'normal'
        result = f.run_watch(watch, 'link-gone')['record']
        support = 'https://instagram.com/acme_support'
        self.assertIn(support, result['tracking']['urls'])
        record = f.discovery_repo.show(result['discovery_id'])['record']
        row = next(row for row in record['report']['profiles'] if row['url'] == support)
        self.assertEqual(row['state'], 'found')
        self.assertEqual(row['discovered_by'], ['retained_profile'])
        self.assertEqual(row['claimed_by'], [])
        self.assertEqual(result['changes'], [])
        original = f.pages.fetch
        def timeout(url, **kwargs):
            return Page(url, url, None, f.at, error='timeout') if url == support else original(url, **kwargs)
        f.later()
        with patch.object(f.pages, 'fetch', side_effect=timeout):
            result = f.run_watch(watch, 'temporarily-unavailable')['record']
        self.assertFalse(result['changes']); self.assertGreater(result['unchecked_count'], 0)
        rows = f.service.execute('brand.review.list')['records']
        self.assertEqual(next(row for row in rows if row['profile']['url'] == support)['profile']['state'], 'inconclusive')
        f.later()
        self.assertFalse(f.run_watch(watch, 'recovered')['record']['changes'])

    def test_small_page_budget_rotates_retained_addresses_and_never_uses_paid_search(self):
        f = self.f
        urls = [f'https://instagram.com/acme{i}' for i in range(6)]
        show_links = [True]
        def fetch(url, **kwargs):
            if url == 'https://acme.example/':
                return page(url, ''.join(f'<a href="{link}">Account</a>' for link in urls) if show_links[0] else 'Company')
            return profile(url, url.rsplit('/', 1)[-1])
        f.pages.fetch = fetch
        seed = f.discovery.execute('brand.discovery.run', **{**SCOPE, 'platforms': ['Instagram'], 'max_pages': 2},
                                   idempotency_key='small-budget')['record']
        watch = f.add(discovery_id=seed['id']); show_links[0] = False
        selected = []
        with patch.object(f.sources, 'search', side_effect=AssertionError('No paid search')):
            for i in range(7):
                f.later()
                run = f.run_watch(watch, f'rotating-{i}')['record']
                selected.extend(run['tracking']['urls'])
                report = f.discovery_repo.show(run['discovery_id'])['record']['report']
                self.assertLessEqual(report['metrics']['profile_pages_checked'], 2)
                self.assertEqual(len(run['tracking']['urls']), 1)
        self.assertTrue(set(urls) <= set(selected))
        self.assertEqual(len(selected), len(set(selected)))

    def test_retained_targets_are_internal_canonical_scope_bound_and_replay_is_offline(self):
        f = self.f; watch = f.add(); run = f.run_watch(watch)['record']
        scope = f.discovery_repo.show(run['discovery_id'])['record']['scope']
        self.assertEqual(validate_scope(scope), scope)
        with self.assertRaises(ValidationError): parameters('brand.discovery.plan', scope)
        for changed in ({'web_search': True}, {'tracking': {**scope['tracking'], 'urls': ['https://127.0.0.1/a']}}):
            with self.assertRaises((ValidationError, TypeError)):
                validate_scope({**scope, **changed})
        with patch.object(f.discovery, '_collect', side_effect=AssertionError('No repeat collection')):
            self.assertEqual(f.run_watch(watch)['record'], run)
        report = deepcopy(f.discovery_repo.show(run['discovery_id'])['record']['report'])
        report['scope'].pop('tracking')
        with self.assertRaises(ValidationError): validate_report(report)

    def test_legacy_run_replays_without_adding_new_fields_or_changing_its_scope(self):
        f = self.f; state = empty_state(); watch_id, run_id = str(uuid4()), str(uuid4())
        watch = apply_event(state, {'operation': 'brand.tracking.add', 'id': watch_id, 'key': 'legacy-watch',
            'recorded_at': f.at, 'request': {'discovery_id': f.seed['id'], 'name': 'Legacy', 'interval_seconds': 300}}, f.seed)
        run = apply_event(state, {'operation': 'brand.tracking.run', 'id': run_id, 'key': 'legacy-round',
            'recorded_at': f.at, 'request': {'identifier': watch_id, 'force': False}}, None)
        self.assertNotIn('version', run); self.assertNotIn('tracking', run)
        self.assertNotIn('retained_urls', watch)
        discovery = f.discovery.execute('brand.discovery.run', **run['scope'], idempotency_key=run['discovery_key'])['record']
        finished = apply_event(state, {'operation': 'brand.tracking.finish', 'id': str(uuid4()),
            'key': 'legacy-finish', 'recorded_at': f.at,
            'request': {'run_id': run_id, 'discovery_id': discovery['id']}}, discovery)
        self.assertEqual(finished['scope'], run['scope'])
        self.assertEqual(finished['changes'], [])
        self.assertNotIn('version', finished)


if __name__ == '__main__': unittest.main()
