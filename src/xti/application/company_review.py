"""One explainable review list for the selected workspace."""

from datetime import datetime, timezone
from xti.domain.assets import ValidationError
from xti.domain.research import identity, ResearchSnapshotChanged
from xti.domain.research_priority import PRIORITIES, POLICY_VERSION
from xti.ports.company_review import CompanyReviewRepository
from xti.application.research import priority_data


from xti.domain.company_review import review_parameters


class CompanyReviewService:
    def __init__(self, repository: CompanyReviewRepository, *, clock=None):
        self.repository, self.clock = repository, clock or (lambda: datetime.now(timezone.utc))

    def show(self, **parameters):
        options = review_parameters(**parameters)
        data = self.repository.read(checked_at=self.clock().isoformat(), **{key: options[key]
            for key in ('stale_after_hours', 'root_offset', 'root_limit')})
        items, roots_by_item = {}, {}
        for review in data.pop('reviews'):
            result = priority_data(review)
            for item in result['items']:
                items[item['id']] = item
                roots_by_item.setdefault(item['id'], []).append({'kind': review.research.query.indicator_type,
                                                                'value': review.research.query.value})
        for identifier, item in items.items():
            item['roots'] = roots_by_item[identifier]
            item['source_states'] = [{'source': row['source'], 'status': row['status'], 'current': row['current'],
                'freshness': row['freshness'], 'evidence_id': row['id']} for row in item['evidence'] if row['kind'] == 'source_claim']
        rows = sorted(items.values(), key=lambda item: (PRIORITIES.index(item['priority']), item['id']))
        def stable(value):
            if isinstance(value, dict):
                return {key: stable(item) for key, item in value.items() if key != 'checked_at'}
            if isinstance(value, list):
                return [stable(item) for item in value]
            return value
        snapshot = identity(POLICY_VERSION, options['root_offset'], options['root_limit'],
            options['stale_after_hours'], stable(rows), data['limitations'], data['root_total_count'])
        if options['expected_snapshot'] is not None and snapshot != options['expected_snapshot']:
            raise ResearchSnapshotChanged('Firma inceleme listesi değişti; ilk sayfadan yeniden alın.')
        selected = rows[options['offset']:options['offset'] + options['limit']]
        return {**data, 'model_version': 1, 'policy_version': POLICY_VERSION, 'snapshot_id': snapshot,
            'items': selected, 'total_count': len(rows), 'offset': options['offset'], 'limit': options['limit'],
            'has_more': options['offset'] + len(selected) < len(rows),
            'priority_counts': {priority: sum(item['priority'] == priority for item in rows) for priority in PRIORITIES},
            'consistency': 'single_read_snapshot', 'stored_data_only': True,
            'notes': ['Liste seçili firma çalışma alanıyla sınırlıdır.',
                'Kaynak durumu farkı mantıksal çelişki veya güvenli/zararlı kararı değildir; kaynaklar ayrı gösterilir.',
                'Kök penceresi eksikse öncelik sırası yalnız incelenen kapsamı karşılaştırır; sonraki kök penceresini de alın.']}
