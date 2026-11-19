"""Evidence views, not assertions that a customer was attacked."""

from xti.domain.cti_feeds import CERTPL_SOURCE, FEODO_SOURCE
from xti.domain.research import identity


def observations(records, snapshot, indicator_type, value):
    result = {}
    for record in records.values():
        for number, stored in enumerate(record['documents'], 1):
            doc = stored['document']
            for candidate in doc['candidates']:
                if (candidate['indicator_type'], candidate['value']) != (indicator_type, value):
                    continue
                identifier = identity('text_mention', record['id'], number, indicator_type, value)
                result[identifier] = {'id': identifier, 'kind': 'text_mention',
                    'indicator_type': indicator_type, 'value': value, 'source': doc['provider'],
                    'source_reference': doc['source_reference'], 'report_id': record['id'],
                    'document_revision': number, 'current_document': number == len(record['documents']),
                    'publication': doc['publication'], 'observed_at': None,
                    'collected_at': doc['collected_at'], 'recorded_at': stored['recorded_at'],
                    'source_run_id': doc['source_run_id'], 'source_sha256': doc['source_sha256'],
                    'span': {key: candidate[key] for key in ('start', 'end', 'original')},
                    'summary_truncated': doc['summary_truncated']}
    if snapshot.details is not None:
        claims = {claim.id: claim for claim in snapshot.details.assertions}
        for event in sorted(snapshot.details.events, key=lambda e: (e.recorded_at, e.id)):
            if event.action == 'revoked':
                continue
            claim = claims[event.assertion_id]
            kind = ('provider_observation' if claim.source_name == FEODO_SOURCE else
                    'feed_membership' if claim.source_name == CERTPL_SOURCE else 'source_assertion')
            # A confidence/description correction at the same source timestamp is
            # more provenance for the same claim, not another sighting.
            identifier = identity(kind, claim.id, event.observed_at)
            if identifier in result:
                result[identifier]['event_ids'].append(event.id)
                continue
            result[identifier] = {'id': identifier, 'kind': kind, 'indicator_type': indicator_type,
                'value': value, 'source': claim.source_name, 'source_reference': claim.source_reference,
                'assertion_id': claim.id, 'event_ids': [event.id], 'assertion_active': claim.active,
                'observed_at': event.observed_at if kind == 'provider_observation' else None,
                'source_time': event.observed_at,
                'time_semantics': {'provider_observation': 'provider_reported_ip_last_online',
                    'feed_membership': 'provider_list_version',
                    'source_assertion': 'unspecified_assertion_time'}[kind],
                'time_precision': 'provider_defined' if kind != 'source_assertion' else 'unknown',
                'collected_at': None, 'recorded_at': event.recorded_at,
                'collection_time_note': 'Historical source collection time is not inferred from a later refresh.'}
    return sorted(result.values(), key=lambda row: (row['recorded_at'], row['id']), reverse=True)
