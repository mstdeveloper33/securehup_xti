"""Compute set overlap and attempt completion from explicit stored provider evidence."""
from collections import defaultdict
from itertools import combinations
from datetime import datetime
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.source_contribution import (
    FAMILIES,
    PROVIDERS,
    ContributionDomain,
    ContributionDomainPage,
    ContributionGroup,
    ContributionPairOverlap,
    ProviderContribution,
    SourceContributionReport,
    outcome_counts,
)
from xti.ports.source_contribution import SourceContributionRepository


class SourceContributionService:

    def __init__(self, repository: SourceContributionRepository):
        self.repository = repository

    @staticmethod
    def _page(domains, records, offset, limit):
        selected = tuple((records[domain] for domain in sorted(domains)))
        shown = selected[offset:offset + limit]
        return ContributionDomainPage(
            shown,
            offset,
            limit,
            len(selected),
            len(shown),
            offset + len(shown) < len(selected),
        )

    @staticmethod
    def _range(values):
        if not values:
            return (None, None)
        ordered = sorted(
            values,
            key=lambda value: datetime.fromisoformat(value.replace('Z', '+00:00')),
        )
        return (ordered[0], ordered[-1])

    def _group(self, snapshot, family, rule_version, typos, offset, limit):
        providers = PROVIDERS[family]
        all_attempts = tuple((attempt for attempt in snapshot.attempts if attempt.family == family and (family == 'surface' or (attempt.rule_version, attempt.typos) == (rule_version, typos))))
        memberships = {provider: defaultdict(list) for provider in providers}
        for evidence in snapshot.surface_evidence if family == 'surface' else ():
            memberships[evidence.provider][evidence.domain].append(evidence)
        for attempt in all_attempts if family == 'brand' else ():
            if attempt.targets != (snapshot.asset_value,) or not attempt.result_available:
                continue
            for domain in set(attempt.candidate_domains):
                memberships[attempt.provider][domain].append(attempt)
        sets = {provider: set(values) for provider, values in memberships.items()}
        union = set().union(*sets.values())
        combined = {}
        by_provider = {provider: {} for provider in providers}
        for domain in sorted(union):
            source_providers = tuple((provider for provider in providers if domain in sets[provider]))
            all_evidence, all_records, all_names, all_reviews = (set(), set(), set(), set())
            for provider in source_providers:
                evidence_ids, record_ids, names, reviews = (set(), set(), set(), set())
                for evidence in memberships[provider][domain]:
                    if family == 'surface':
                        evidence_ids.add(evidence.evidence_id)
                        record_ids.add(evidence.candidate_id)
                        names.add(evidence.source_name)
                        reviews.add(evidence.review_status)
                    else:
                        evidence_ids.add(evidence.id)
                        record_ids.add(evidence.job_id)
                        names.add(provider)
                by_provider[provider][domain] = ContributionDomain(
                    domain,
                    source_providers,
                    tuple(sorted(evidence_ids)),
                    tuple(sorted(record_ids)),
                    tuple(sorted(names)),
                    tuple(sorted(reviews)),
                )
                all_evidence.update(evidence_ids)
                all_records.update(record_ids)
                all_names.update(names)
                all_reviews.update(reviews)
            combined[domain] = ContributionDomain(
                domain,
                source_providers,
                tuple(sorted(all_evidence)),
                tuple(sorted(all_records)),
                tuple(sorted(all_names)),
                tuple(sorted(all_reviews)),
            )
        sources = []
        for provider in providers:
            selected = tuple((attempt for attempt in all_attempts if attempt.provider == provider))
            eligible = tuple((attempt for attempt in selected if attempt.targets == (snapshot.asset_value,)))
            excluded = tuple((attempt for attempt in selected if attempt.targets != (snapshot.asset_value,)))
            other_domains = set().union(*(sets[other] for other in providers if other != provider))
            evidence_times = [evidence.recorded_at for values in memberships[provider].values() for evidence in values] if family == 'surface' else [attempt.finished_at for attempt in eligible if attempt.result_available and attempt.finished_at]
            evidence_first, evidence_last = self._range(evidence_times)
            attempt_first, attempt_last = self._range([attempt.started_at for attempt in eligible])
            reviews = tuple(((
                status,
                sum((status in record.review_statuses for record in by_provider[provider].values())),
            ) for status in ('pending', 'owned', 'rejected'))) if family == 'surface' else ()
            queued = sum((job.provider == provider and job.targets == (snapshot.asset_value,) and ((job.rule_version, job.typos) == (rule_version, typos)) for job in snapshot.queued_jobs)) if family == 'brand' else 0
            sources.append(ProviderContribution(
                provider,
                self._page(sets[provider], by_provider[provider], offset, limit),
                self._page(sets[provider] & other_domains, by_provider[provider], offset, limit),
                self._page(sets[provider] - other_domains, by_provider[provider], offset, limit),
                outcome_counts(eligible),
                outcome_counts(excluded),
                len(excluded),
                sum((not attempt.result_available for attempt in eligible)) if family == 'brand' else 0,
                sum((attempt.status == 'complete' and attempt.reported_candidate_count == 0 for attempt in eligible)),
                queued,
                sum((job.provider == provider and job.targets != (snapshot.asset_value,) and ((job.rule_version, job.typos) == (rule_version, typos)) for job in snapshot.queued_jobs)) if family == 'brand' else 0,
                evidence_first,
                evidence_last,
                attempt_first,
                attempt_last,
                reviews,
                tuple((attempt.id for attempt in eligible)),
                tuple((attempt.id for attempt in excluded)),
                tuple(sorted({warning for attempt in eligible for warning in attempt.warnings})),
            ))
        comparable = all((source.outcomes.complete > 0 for source in sources))
        notes = (
            'Sayılar yalnız saklanan yerel geçmişin küme katkısıdır; doğruluk, tehdit sayısı veya internet kapsama oranı değildir.',
            'Kaynakların zaman aralıkları ve çalışma sayıları farklı olabilir; yalnız-kaynak listesi üstünlük puanı değildir.',
        )
        if family == 'surface':
            notes += (
                'Kaynak kanıtları belirli discovery run üyelerine bağlı değildir; tekrar keşif veya çalışma başına aday katkısı hesaplanmaz.',
                'theHarvester üst sağlayıcıdır; Common Crawl/Wayback uyarı metninden ayrı başarı oranı çıkarılmaz.',
            )
        else:
            notes += (
                'Aday kümeleri yalnız tek hedefli, sonucu saklanan denemelerden gelir. Çok hedefli denemeler ayrı tutulur.',
                'Tamamlanma oranı tek hedefli terminal denemeler içindir; running ve queued paydaya girmez.',
            )
        return ContributionGroup(
            family,
            rule_version,
            typos,
            tuple(sources),
            self._page(union, combined, offset, limit),
            tuple((ContributionPairOverlap(a, b, self._page(sets[a] & sets[b], combined, offset, limit)) for a, b in combinations(providers, 2))),
            'local_comparison' if comparable else 'insufficient_history',
            notes,
        )

    def show(self, domain: str, *, family: str='all', detail_offset: int=0, detail_limit: int=100):
        domain = normalize_domain(domain)
        if not isinstance(family, str) or family not in FAMILIES:
            raise ValidationError('Katkı ailesi all, surface veya brand olmalı.')
        if type(detail_offset) is not int or not 0 <= detail_offset <= 1000000:
            raise ValidationError('Katkı ayrıntı başlangıcı 0–1000000 arasında olmalı.')
        if type(detail_limit) is not int or not 1 <= detail_limit <= 500:
            raise ValidationError('Katkı ayrıntı sınırı 1–500 arasında olmalı.')
        snapshot = self.repository.snapshot(domain, family=family)
        if snapshot.asset_value != domain:
            raise ValidationError('Kaynak katkısı seçilen domainle uyuşmuyor.')
        groups = []
        if family in {'all', 'surface'}:
            groups.append(self._group(snapshot, 'surface', None, None, detail_offset, detail_limit))
        if family in {'all', 'brand'}:
            selections = {(attempt.rule_version, attempt.typos) for attempt in snapshot.attempts if attempt.family == 'brand'}
            selections.update(((job.rule_version, job.typos) for job in snapshot.queued_jobs))
            for rule, typos in sorted(selections):
                groups.append(self._group(
                    snapshot,
                    'brand',
                    rule,
                    typos,
                    detail_offset,
                    detail_limit,
                ))
        notes = (
            'Ayrıntı sayfası toplamları değiştirmez; domainler ve dayanak kimlikleri kararlı sıralanır.',
            'Kayıtlı deneme tamamlanma oranı sağlayıcı hizmet seviyesi veya canlı erişilebilirlik ölçümü değildir.',
            'Common Crawl dış erişim hatası boş başarı sayılmaz; aynı arşivi başka araçtan çağırmak bağımsız katkı değildir.',
        )
        if family in {'all', 'brand'} and (not any((group.family == 'brand' for group in groups))):
            notes += ('Marka aramasında kayıtlı deneme veya bekleyen iş yok; karşılaştırma bilinmiyor.',)
        return SourceContributionReport(
            snapshot.asset_id,
            domain,
            family,
            tuple(groups),
            snapshot.schema_version,
            notes,
            'Yeni sağlayıcı seçilmedi. Mevcut yerel kapsam, bağımsız bir ücretsiz kaynağı eklemeyi tek başına gerekçelendirmez; ölçülen boşluk ve resmî erişim koşulları ayrıca doğrulanmalı.',
        )
