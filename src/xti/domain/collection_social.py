"""Frozen social tracking selection in the existing collection recipe."""
import re
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cases import normalize_case_title
from xti.domain.collection import CollectionTask, CollectionWatchTarget
from xti.domain.social_discovery import fingerprint, PLATFORMS

POLICY = 'collection-social-v1'


def task_for(watch, domain):
    if not watch['enabled'] or watch['scope']['domain'] != domain:
        raise ValidationError('Sosyal izleme etkin ve toplama profiliyle aynı domaine ait olmalı.')
    target = CollectionWatchTarget(watch['id'], watch['name'], domain, 'company-social', 'exact',
        tuple(watch['scope']['platforms']), revision=watch['revision'])
    return CollectionTask('social-tracking:' + watch['id'], 'social_tracking', 'social-tracking',
        'Birleşik sosyal hesap takibi: ' + watch['name'], (target,))


def contract(watch):
    return POLICY + ':' + fingerprint(watch['scope'])


def validate_unit(unit):
    watch = unit.watch
    if (unit.source != 'social-tracking' or unit.step_key != 'social-tracking:' + watch.watch_id
            or watch.kind != 'company-social' or watch.match_mode != 'exact' or watch.search_event_id is not None
            or watch.query != unit.asset_value or normalize_domain(watch.query) != watch.query
            or normalize_case_title(watch.display_name) != watch.display_name
            or type(watch.revision) is not int or watch.revision < 1
            or not isinstance(watch.platforms, tuple) or not watch.platforms
            or any(p not in PLATFORMS for p in watch.platforms) or len(set(watch.platforms)) != len(watch.platforms)
            or re.fullmatch(POLICY + r':[0-9a-f]{64}', unit.contract_version) is None):
        raise ValidationError('Dondurulmuş birleşik sosyal toplama kapsamı geçersiz.')


def operation_key(step_id):
    return 'collection-social-' + step_id
