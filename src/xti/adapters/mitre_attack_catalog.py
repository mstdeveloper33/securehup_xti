"""Validate the additional ATT&CK catalog from the already decoded official bundle."""
from xti.domain.assets import ValidationError
from xti.domain.attack_catalog import ENTITY_TYPES, AttackCatalogEntity, AttackCatalogRelationship, AttackCatalogPhaseLink, AttackCatalogSnapshot, validate_catalog_snapshot
from xti.domain.cti_attack import ATTACK_VERSION, ATTACK_SOURCE_URL
from xti.domain.cti_knowledge import normalize_aliases, normalize_entity_name
from xti.ports.discovery import SourceError

def catalog_from_objects(objects, content_times, *, content_sha256, fetched_at):
    # Reuses the single decoded official response; no second fetch or JSON decode.
    from xti.adapters.mitre_attack import _active, _stix_id, _timestamp
    entities = {}
    phases = {}
    tactics = {}
    try:
        indexed = set(content_times)
        expected = {identifier for (identifier, raw) in objects.items() if raw['type'] not in {'x-mitre-collection', 'marking-definition'}}
        if indexed != expected:
            raise ValueError('incomplete collection object index')
        for identifier in indexed:
            if _timestamp(objects[identifier].get('modified'), 'koleksiyon nesne zamanı', fetched_at=fetched_at) != content_times[identifier]:
                raise ValueError('collection object version mismatch')
        for raw in objects.values():
            kind = raw['type']
            if kind not in ENTITY_TYPES or not _active(raw):
                continue
            if raw.get('spec_version') != '2.1' or not isinstance(raw.get('x_mitre_domains'), list) or 'enterprise-attack' not in raw['x_mitre_domains']:
                raise ValueError('STIX scope')
            identifier = _stix_id(raw['id'], kind)
            references = raw.get('external_references')
            if not isinstance(references, list) or len(references) > 500 or any((not isinstance(r, dict) for r in references)):
                raise ValueError('references')
            selected = [r for r in references if r.get('source_name') == 'mitre-attack']
            if len(selected) != 1:
                raise ValueError('official reference')
            name = normalize_entity_name(raw.get('name'))
            aliases = raw.get('x_mitre_aliases' if kind == 'malware' else 'aliases', [])
            if not isinstance(aliases, list) or any((not isinstance(a, str) for a in aliases)):
                raise ValueError('aliases')
            aliases = normalize_aliases(tuple((a for a in aliases if a.casefold() != name.casefold())))
            created = _timestamp(raw.get('created'), 'katalog oluşturma zamanı', fetched_at=fetched_at)
            modified = _timestamp(raw.get('modified'), 'katalog değişiklik zamanı', fetched_at=fetched_at)
            if content_times.get(identifier) != modified:
                raise ValueError('collection index')
            platforms = raw.get('x_mitre_platforms', []) if kind == 'attack-pattern' else []
            if not isinstance(platforms, list) or len(platforms) > 64 or any((not isinstance(p, str) for p in platforms)) or (len(set(platforms)) != len(platforms)):
                raise ValueError('platforms')
            is_subtechnique = raw.get('x_mitre_is_subtechnique') if kind == 'attack-pattern' else False
            shortname = raw.get('x_mitre_shortname') if kind == 'x-mitre-tactic' else None
            item = AttackCatalogEntity(identifier, selected[0].get('external_id'), kind, name, raw.get('description', ''), selected[0].get('url'), created, modified, aliases, tuple(sorted(platforms)), is_subtechnique, shortname)
            entities[identifier] = item
            if kind == 'x-mitre-tactic':
                if shortname in tactics:
                    raise ValueError('duplicate tactic')
                tactics[shortname] = identifier
            if kind == 'attack-pattern':
                raw_phases = raw.get('kill_chain_phases')
                if not isinstance(raw_phases, list) or not 1 <= len(raw_phases) <= 64:
                    raise ValueError('phases')
                names = []
                for phase in raw_phases:
                    if not isinstance(phase, dict) or set(phase) != {'kill_chain_name', 'phase_name'} or phase['kill_chain_name'] != 'mitre-attack' or (not isinstance(phase['phase_name'], str)):
                        raise ValueError('phase fields')
                    names.append(phase['phase_name'])
                if len(set(names)) != len(names):
                    raise ValueError('duplicate phase')
                phases[identifier] = names
        relationships = []
        for raw in objects.values():
            if raw['type'] != 'relationship' or not _active(raw):
                continue
            (source, target) = (_stix_id(raw.get('source_ref')), _stix_id(raw.get('target_ref')))
            if source not in objects or target not in objects:
                raise ValueError('relationship endpoint missing from complete bundle')
            if source not in entities or target not in entities:
                continue
            if raw.get('spec_version') != '2.1':
                raise ValueError('relationship version')
            identifier = _stix_id(raw['id'], 'relationship')
            created = _timestamp(raw.get('created'), 'ilişki oluşturma zamanı', fetched_at=fetched_at)
            modified = _timestamp(raw.get('modified'), 'ilişki değişiklik zamanı', fetched_at=fetched_at)
            if content_times.get(identifier) != modified:
                raise ValueError('relationship collection index')
            relationships.append(AttackCatalogRelationship(identifier, source, raw.get('relationship_type'), target, raw.get('description', ''), ATTACK_SOURCE_URL + '#' + identifier, created, modified))
        links = []
        for (technique, names) in phases.items():
            for name in names:
                if name not in tactics:
                    raise ValueError('unknown active tactic')
                links.append(AttackCatalogPhaseLink(technique, tactics[name], name))
        return validate_catalog_snapshot(AttackCatalogSnapshot(ATTACK_VERSION, ATTACK_SOURCE_URL, content_sha256, len(objects), fetched_at.isoformat(), tuple(sorted(entities.values(), key=lambda x: x.stix_id)), tuple(sorted(relationships, key=lambda x: x.stix_id)), tuple(sorted(links, key=lambda x: x.key))))
    except (ValueError, TypeError, KeyError, ValidationError, RecursionError) as error:
        raise SourceError('MITRE ATT&CK teknik/taktik kataloğu tutarlı tam kapsamda değil; önceki kayıtlar korunmalı.') from error
