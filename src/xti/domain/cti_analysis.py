"""Explainable CTI analysis candidates; no result is an automatic fact or merge."""

from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re
import unicodedata
from urllib.parse import urlsplit

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.content_monitoring import canonical, digest, integer, text
from xti.domain.mentions import mention_uuid


POLICY = "cti-analysis-v1"
PREFIX = "cti.analysis."
KINDS = ("identity", "technique", "attribution", "tag", "priority")
DECISIONS = ("accepted", "rejected", "uncertain", "same_entity", "different_entity")
CRITICALITIES = ("low", "medium", "high", "critical")
READS = tuple(PREFIX + name for name in (
    "capabilities", "profiles", "profile.show", "plan", "runs", "run.show",
    "candidates", "candidate.show", "evidence.show", "reviews", "changes",
    "graph", "timeline", "trends", "source.quality", "report",
))
WRITES = tuple(PREFIX + name for name in (
    "profile.add", "profile.update", "run", "review", "recover",
))
PROFILE_FIELDS = {
    "name", "organization_id", "criticality", "identity_threshold",
    "minimum_independent_sources", "alert_score_min", "trend_new_threshold",
    "fresh_days", "max_entities", "max_relationships", "max_candidates",
    "max_graph_nodes", "max_graph_edges", "interval_seconds", "source_policies",
}

_TECHNIQUE = re.compile(r"(?<![A-Z0-9])T[0-9]{4}(?:\.[0-9]{3})?(?![A-Z0-9])")
_WORDS = re.compile(r"[\w]+", re.UNICODE)
_GEO = {
    "TR": ("turkey", "türkiye", "turkish", "türkçe", "türk"),
    "RU": ("russia", "russian", "rusya", "rusça"),
    "CN": ("china", "chinese", "çin", "çince"),
    "IR": ("iran", "iranian", "iranlı"),
    "KP": ("north korea", "dprk", "kuzey kore"),
    "UA": ("ukraine", "ukrainian", "ukrayna"),
}
_SECTORS = {
    "finance": ("finance", "financial", "banking", "bankacılık", "finans"),
    "government": ("government", "public sector", "kamu", "devlet"),
    "healthcare": ("healthcare", "hospital", "sağlık", "hastane"),
    "energy": ("energy", "utility", "enerji"),
    "telecom": ("telecom", "telecommunication", "telekom"),
    "technology": ("technology", "software", "teknoloji", "yazılım"),
    "defense": ("defense", "defence", "savunma"),
    "education": ("education", "university", "eğitim", "üniversite"),
    "retail": ("retail", "e-commerce", "perakende", "e-ticaret"),
    "manufacturing": ("manufacturing", "industrial", "üretim", "sanayi"),
}
_NEGATIONS = ("not ", "no ", "without ", "değil", "hedeflemiyor", "ilişkili değil")


class CtiAnalysisError(ValidationError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def folded(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("i\u0307", "i")
    return " ".join(_WORDS.findall(value))[:400]


def _source_policy(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"source_name", "reliability", "independence_group"}:
        raise ValidationError("Kaynak güven kuralı ad, reliability ve bağımsızlık grubu içermeli.")
    source_name = text(value["source_name"], 200)
    group = text(value["independence_group"], 100)
    return {
        "source_name": source_name,
        "reliability": integer(value["reliability"], 0, 100),
        "independence_group": folded(group),
    }


def profile_definition(values: object) -> dict:
    if not isinstance(values, dict) or set(values) - PROFILE_FIELDS:
        raise ValidationError("CTI analiz profili alanları bilinmiyor.")
    policies = values.get("source_policies", [])
    if not isinstance(policies, list) or len(policies) > 100:
        raise ValidationError("CTI analiz profilinde en fazla 100 kaynak güven kuralı olabilir.")
    policies = [_source_policy(value) for value in policies]
    keys = [folded(value["source_name"]) for value in policies]
    if len(keys) != len(set(keys)):
        raise ValidationError("Kaynak güven kuralları aynı kaynağı tekrarlamamalı.")
    criticality = values.get("criticality", "medium")
    if criticality not in CRITICALITIES:
        raise ValidationError("Kuruluş önem seviyesi low, medium, high veya critical olmalı.")
    return {
        "name": text(values.get("name", "CTI analiz profili"), 200),
        "organization_id": mention_uuid(values.get("organization_id")),
        "criticality": criticality,
        "identity_threshold": integer(values.get("identity_threshold", 88), 70, 100),
        "minimum_independent_sources": integer(values.get("minimum_independent_sources", 2), 2, 5),
        "alert_score_min": integer(values.get("alert_score_min", 60), 0, 100),
        "trend_new_threshold": integer(values.get("trend_new_threshold", 5), 1, 1000),
        "fresh_days": integer(values.get("fresh_days", 30), 1, 3650),
        "max_entities": integer(values.get("max_entities", 5000), 1, 10000),
        "max_relationships": integer(values.get("max_relationships", 10000), 1, 50000),
        "max_candidates": integer(values.get("max_candidates", 1000), 1, 10000),
        "max_graph_nodes": integer(values.get("max_graph_nodes", 100), 1, 100),
        "max_graph_edges": integer(values.get("max_graph_edges", 200), 1, 200),
        "interval_seconds": integer(values.get("interval_seconds", 3600), 300, 604800),
        "source_policies": sorted(policies, key=lambda item: folded(item["source_name"])),
    }


def parameters(operation: str, value: object, *, scoped: bool = False) -> dict:
    name = operation.removeprefix(PREFIX)
    pages = {"profiles", "runs", "candidates", "reviews", "changes", "timeline", "trends"}
    allowed: set[str] = set()
    required: set[str] = set()
    if name in ("profile.add", "profile.update"):
        allowed = PROFILE_FIELDS | {"idempotency_key"}
        if name == "profile.add":
            required = {"name", "organization_id", "idempotency_key"}
        else:
            allowed |= {"identifier", "expected_revision", "enabled"}
            required = {"identifier", "expected_revision", "idempotency_key"}
    elif name == "run":
        allowed = {"identifier", "expected_revision", "idempotency_key", "force"}
        required = allowed - {"force"}
    elif name == "review":
        allowed = {"identifier", "evidence_id", "expected_revision", "expected_observation_revision", "decision", "reason", "idempotency_key"}
        required = allowed.copy()
    elif name == "recover":
        allowed = required = {"identifier", "idempotency_key"}
    elif name in ("profile.show", "plan", "run.show", "candidate.show", "evidence.show"):
        allowed = required = {"identifier"}
    elif name in pages:
        allowed = {"after", "limit", "profile_id"}
        if name in ("candidates", "changes"):
            allowed |= {"kind", "decision", "minimum_score"}
        if name == "reviews":
            allowed |= {"identifier"}
            required = {"identifier"}
    elif name in ("graph", "report", "source.quality"):
        allowed = {"profile_id", "run_id"}
        required = {"profile_id"}
        if name == "graph":
            allowed |= {"node_after", "edge_after", "node_limit", "edge_limit", "expected_snapshot"}
    elif name != "capabilities":
        raise ValidationError("CTI analiz işlemi bilinmiyor.")
    if scoped and operation in WRITES:
        allowed |= {"expected_workspace_id"}
        required |= {"expected_workspace_id"}
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValidationError("CTI analiz işlemi seçenekleri eksik veya bilinmiyor.")
    result = dict(value)
    for key in ("identifier", "profile_id", "run_id", "evidence_id", "expected_workspace_id"):
        if key in result:
            result[key] = mention_uuid(result[key])
    for key in ("expected_revision", "expected_observation_revision"):
        if key in result:
            result[key] = integer(result[key], 0 if name == "review" and key == "expected_revision" else 1, 2**31 - 1)
    for key in ("enabled", "force"):
        if key in result and type(result[key]) is not bool:
            raise ValidationError("CTI analiz bayrağı boolean olmalı.")
    if "idempotency_key" in result:
        from xti.domain.research_history import history_key
        result["idempotency_key"] = history_key(result["idempotency_key"])
    if name in pages:
        result["after"] = integer(result.get("after", 0), 0, 2**63 - 1)
        result["limit"] = integer(result.get("limit", 20), 1, 100)
    if name == "graph":
        for key, default, high in (("node_after", 0, 1_000_000), ("edge_after", 0, 1_000_000), ("node_limit", 50, 100), ("edge_limit", 100, 200)):
            result[key] = integer(result.get(key, default), 0 if key.endswith("after") else 1, high)
        if "expected_snapshot" in result and (not isinstance(result["expected_snapshot"], str) or not re.fullmatch("[0-9a-f]{64}", result["expected_snapshot"])):
            raise ValidationError("CTI graf snapshot kimliği geçersiz.")
    if "kind" in result and result["kind"] not in KINDS:
        raise ValidationError("CTI analiz aday türü bilinmiyor.")
    if "decision" in result and result["decision"] not in DECISIONS:
        raise ValidationError("CTI analiz inceleme kararı bilinmiyor.")
    if "minimum_score" in result:
        result["minimum_score"] = integer(result["minimum_score"], 0, 100)
    if "reason" in result:
        result["reason"] = text(result["reason"], 2000, 3)
    return result


def _excerpt(value: str, start: int, end: int, radius: int = 100) -> str:
    left, right = max(0, start - radius), min(len(value), end + radius)
    return " ".join(value[left:right].split())[:260]


def _policy_map(definition: dict) -> dict[str, dict]:
    return {folded(item["source_name"]): item for item in definition["source_policies"]}


def source_quality(assertions: list[dict], definition: dict, captured_at: str) -> dict:
    if not assertions:
        return {"score": 0, "stated_confidence": 0, "configured_reliability": 0,
                "freshness": 0, "independent_groups": 0, "source_count": 0,
                "meaning": "review_confidence_not_risk_probability"}
    policies = _policy_map(definition)
    now = datetime.fromisoformat(captured_at)
    reliability, confidence, freshness, groups = [], [], [], set()
    for item in assertions:
        policy = policies.get(folded(item["source_name"]), {
            "reliability": 50, "independence_group": folded(item["source_name"]),
        })
        reliability.append(policy["reliability"])
        confidence.append(item["confidence"])
        try:
            days = max(0.0, (now - datetime.fromisoformat(item["last_seen_at"])).total_seconds() / 86400)
        except (TypeError, ValueError):
            days = definition["fresh_days"] * 2
        # Freshness is a day-level evidence property.  Sub-day worker timing
        # must not manufacture a new immutable candidate body every few hours.
        age_days = int(days)
        freshness.append(max(0, round(100 * (1 - min(age_days / definition["fresh_days"], 1)))))
        groups.add(policy["independence_group"])
    stated = max(confidence)
    configured = round(sum(reliability) / len(reliability))
    fresh = max(freshness)
    corroboration = round(min(len(groups), 3) / 3 * 100)
    score = round(stated * .4 + configured * .3 + fresh * .2 + corroboration * .1)
    return {"score": score, "stated_confidence": stated,
            "configured_reliability": configured, "freshness": fresh,
            "independent_groups": len(groups), "source_count": len(assertions),
            "meaning": "review_confidence_not_risk_probability"}


def _entity_ref(entity: dict) -> dict:
    return {"kind": "cti_entity", "id": entity["id"], "type": entity["entity_type"], "label": entity["display_name"]}


def _attack_ref(entity: dict) -> dict:
    return {"kind": "attack_entity", "id": entity["stix_id"], "type": entity["stix_type"],
            "external_id": entity["external_id"], "label": entity["name"]}


def _anchor(assertion: dict, *, anchor_kind: str, record_id: str, excerpt: str | None = None) -> dict:
    return {"kind": anchor_kind, "record_id": record_id, "assertion_id": assertion.get("id"),
            "source_name": assertion["source_name"], "source_reference": assertion["source_reference"],
            "confidence": assertion["confidence"], "last_seen_at": assertion["last_seen_at"],
            "excerpt": excerpt if excerpt is not None else assertion.get("description", "")[:260]}


def _candidate(kind: str, subject: dict, object_: dict, rule: str, signals: list[str],
               anchors: list[dict], score: int, quality: dict, limitations: list[str],
               *, classification: str = "candidate") -> dict:
    # Labels, score components and organization criticality are mutable evidence,
    # not candidate identity.  Keep review continuity on stable record identities.
    key = digest({"kind": kind,
                  "subject": {"kind": subject["kind"], "id": subject["id"]},
                  "object": {"kind": object_["kind"], "id": object_["id"]},
                  "rule": rule})
    body = {"policy": POLICY, "candidate_key": key, "kind": kind,
            "subject": subject, "object": object_, "rule": rule,
            "classification": classification, "signals": sorted(set(signals)),
            "anchors": sorted(anchors, key=lambda item: (item["source_name"], item["source_reference"], item.get("assertion_id") or "")),
            "score": {"value": max(0, min(100, round(score))), "components": quality,
                      "meaning": "review_priority_not_fact_or_risk_probability"},
            "limitations": limitations, "automatic_verdict": False}
    validate_evidence(body)
    return {"candidate_key": key, "kind": kind, "score": body["score"]["value"], "body": body,
            "body_sha256": digest(body)}


def validate_evidence(body: object) -> dict:
    fields = {"policy", "candidate_key", "kind", "subject", "object", "rule", "classification",
              "signals", "anchors", "score", "limitations", "automatic_verdict"}
    if not isinstance(body, dict) or set(body) != fields or body.get("policy") != POLICY or body.get("kind") not in KINDS:
        raise CtiAnalysisError("corrupt_evidence", "CTI analiz kanıtı biçimi geçersiz.")
    if not re.fullmatch("[0-9a-f]{64}", str(body.get("candidate_key", ""))):
        raise CtiAnalysisError("corrupt_evidence", "CTI analiz aday anahtarı geçersiz.")
    if type(body.get("automatic_verdict")) is not bool or body["automatic_verdict"]:
        raise CtiAnalysisError("corrupt_evidence", "CTI analiz sonucu otomatik hüküm içeremez.")
    if not isinstance(body["anchors"], list) or not 1 <= len(body["anchors"]) <= 50:
        raise CtiAnalysisError("corrupt_evidence", "CTI analiz kaynak kanıtı eksik veya fazla.")
    if not isinstance(body["signals"], list) or len(body["signals"]) > 30 or not isinstance(body["limitations"], list) or not body["limitations"]:
        raise CtiAnalysisError("corrupt_evidence", "CTI analiz açıklaması geçersiz.")
    score = body.get("score")
    if not isinstance(score, dict) or set(score) != {"value", "components", "meaning"} or type(score["value"]) is not int or not 0 <= score["value"] <= 100:
        raise CtiAnalysisError("corrupt_evidence", "CTI analiz skoru geçersiz.")
    if len(canonical(body).encode()) > 200_000:
        raise CtiAnalysisError("evidence_too_large", "CTI analiz kanıtı boyut sınırını aşıyor.")
    return body


def _names(entity: dict) -> set[str]:
    result = {folded(entity["display_name"] if "display_name" in entity else entity["name"])}
    for assertion in entity.get("assertions", []):
        result.update(folded(value) for value in assertion.get("aliases", []))
    result.update(folded(value) for value in entity.get("aliases", []))
    return {value for value in result if len(value) >= 2}


def _similarity(left: set[str], right: set[str]) -> tuple[int, str]:
    overlap = left & right
    if overlap:
        return 100, sorted(overlap)[0]
    best, pair = 0, ""
    for a in left:
        for b in right:
            if abs(len(a) - len(b)) > max(4, round(max(len(a), len(b)) * .35)):
                continue
            value = round(SequenceMatcher(None, a[:200], b[:200], autojunk=True).ratio() * 100)
            if value > best:
                best, pair = value, a + " ≈ " + b
    return best, pair


def _pair_blocks(records: list[dict], name_getter) -> dict[tuple, list[int]]:
    blocks: dict[tuple, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        for name in name_getter(record):
            compact = name.replace(" ", "")
            if compact:
                bucket = len(compact) // 4
                # Adjacent length buckets keep boundary values comparable while
                # the first character and entity type still bound the search.
                for length_bucket in range(max(0, bucket - 1), bucket + 2):
                    blocks[(record.get("entity_type") or record.get("stix_type"), compact[0], length_bucket)].append(index)
    return blocks


def _negated(value: str, start: int) -> bool:
    window = folded(value[max(0, start - 45):start])
    return any(token.strip() in window.split()[-5:] or token in window[-35:] for token in _NEGATIONS)


def analyse(snapshot: dict) -> dict:
    """Return deterministic candidates from a bounded, already frozen snapshot."""
    definition = profile_definition(snapshot["definition"])
    captured_at = snapshot["captured_at"]
    datetime.fromisoformat(captured_at)
    entities = snapshot["entities"][:definition["max_entities"]]
    relationships = snapshot["relationships"][:definition["max_relationships"]]
    indicators = {item["id"]: item for item in snapshot["indicators"]}
    attack_entities = snapshot["attack"]["entities"]
    attack_by_stix = {item["stix_id"]: item for item in attack_entities}
    attack_techniques = {item["external_id"]: item for item in attack_entities if item["stix_type"] == "attack-pattern"}
    entity_by_id = {item["id"]: item for item in entities}
    candidates: dict[str, dict] = {}
    stats = defaultdict(int)

    def add(item: dict) -> None:
        prior = candidates.get(item["candidate_key"])
        if prior is None or item["score"] > prior["score"]:
            candidates[item["candidate_key"]] = item

    # CTI-to-CTI identity candidates: exact alias overlap plus bounded fuzzy blocks.
    pairs: set[tuple[int, int]] = set()
    by_exact: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, entity in enumerate(entities):
        for name in _names(entity):
            by_exact[(entity["entity_type"], name)].append(index)
    for indexes in by_exact.values():
        if len(indexes) <= 200:
            pairs.update((min(a, b), max(a, b)) for pos, a in enumerate(indexes) for b in indexes[pos + 1:])
        else:
            stats["oversized_identity_blocks"] += 1
    for indexes in _pair_blocks(entities, _names).values():
        indexes = sorted(set(indexes))
        if len(indexes) <= 80:
            pairs.update((a, b) for pos, a in enumerate(indexes) for b in indexes[pos + 1:])
        else:
            stats["oversized_identity_blocks"] += 1
    pair_budget = min(250_000, max(10_000, definition["max_entities"] * 40))
    if len(pairs) > pair_budget:
        stats["identity_comparison_budget_exhausted"] += len(pairs) - pair_budget
    for left_index, right_index in sorted(pairs)[:pair_budget]:
        left, right = entities[left_index], entities[right_index]
        if left["entity_type"] != right["entity_type"]:
            continue
        similarity, matched = _similarity(_names(left), _names(right))
        if similarity < definition["identity_threshold"]:
            continue
        assertions = left["assertions"] + right["assertions"]
        quality = source_quality(assertions, definition, captured_at)
        anchors = [_anchor(value, anchor_kind="entity_assertion", record_id=left["id"]) for value in left["assertions"][:10]]
        anchors += [_anchor(value, anchor_kind="entity_assertion", record_id=right["id"]) for value in right["assertions"][:10]]
        if not anchors:
            continue
        score = round(similarity * .7 + quality["score"] * .3)
        left_ref, right_ref = sorted((_entity_ref(left), _entity_ref(right)),
                                     key=lambda value: (value["kind"], value["id"]))
        add(_candidate("identity", left_ref, right_ref, "alias_or_name_similarity",
            ["same_entity_type", "exact_alias_overlap" if similarity == 100 else "bounded_name_similarity", matched],
            anchors, score, quality,
            ["Name or alias similarity is not identity proof.", "Records are not physically merged."]))

    # CTI-to-ATT&CK identity candidates.
    compatible = {"threat-actor": "intrusion-set", "campaign": "campaign", "malware": "malware"}
    attack_names = [_names(item) for item in attack_entities]
    attack_exact: dict[tuple[str, str], list[int]] = defaultdict(list)
    attack_blocks: dict[tuple[str, str, int], list[int]] = defaultdict(list)
    for attack_index, attack in enumerate(attack_entities):
        for name in attack_names[attack_index]:
            attack_exact[(attack["stix_type"], name)].append(attack_index)
            compact = name.replace(" ", "")
            if compact:
                bucket = len(compact) // 4
                for length_bucket in range(max(0, bucket - 1), bucket + 2):
                    attack_blocks[(attack["stix_type"], compact[0], length_bucket)].append(attack_index)
    attack_pairs: set[tuple[int, int]] = set()
    for entity_index, entity in enumerate(entities):
        attack_type = compatible.get(entity["entity_type"])
        if attack_type is None:
            continue
        for name in _names(entity):
            for attack_index in attack_exact.get((attack_type, name), ()):
                attack_pairs.add((entity_index, attack_index))
            compact = name.replace(" ", "")
            if not compact:
                continue
            bucket = len(compact) // 4
            block = set()
            for length_bucket in range(max(0, bucket - 1), bucket + 2):
                block.update(attack_blocks.get((attack_type, compact[0], length_bucket), ()))
            if len(block) <= 250:
                attack_pairs.update((entity_index, attack_index) for attack_index in block)
            else:
                stats["oversized_attack_identity_blocks"] += 1
    attack_pair_budget = min(250_000, max(10_000, definition["max_entities"] * 40))
    if len(attack_pairs) > attack_pair_budget:
        stats["attack_identity_comparison_budget_exhausted"] += len(attack_pairs) - attack_pair_budget
    for entity_index, attack_index in sorted(attack_pairs)[:attack_pair_budget]:
        entity, attack = entities[entity_index], attack_entities[attack_index]
        similarity, matched = _similarity(_names(entity), attack_names[attack_index])
        if similarity < definition["identity_threshold"]:
            continue
        quality = source_quality(entity["assertions"], definition, captured_at)
        anchors = [_anchor(value, anchor_kind="entity_assertion", record_id=entity["id"]) for value in entity["assertions"][:20]]
        anchors.append({"kind": "attack_catalog_entity", "record_id": attack["stix_id"], "assertion_id": None,
            "source_name": "MITRE ATT&CK", "source_reference": attack["source_url"], "confidence": 100,
            "last_seen_at": attack["modified_at"], "excerpt": matched})
        score = round(similarity * .75 + quality["score"] * .25)
        add(_candidate("identity", _entity_ref(entity), _attack_ref(attack), "cti_to_attack_alias_similarity",
            ["compatible_entity_type", "exact_attack_alias_overlap" if similarity == 100 else "bounded_attack_name_similarity", matched],
            anchors, score, quality,
            ["ATT&CK alias similarity is a review candidate, not a confirmed mapping.", "An analyst must accept same_entity before relationship inheritance."]))

    # Explicit technique mentions in source text.
    for entity in entities:
        for assertion in entity["assertions"]:
            for match in _TECHNIQUE.finditer(assertion["description"]):
                attack = attack_techniques.get(match.group(0))
                if attack is None:
                    stats["unknown_technique_mentions"] += 1
                    continue
                quality = source_quality([assertion], definition, captured_at)
                anchor = _anchor(assertion, anchor_kind="entity_assertion", record_id=entity["id"],
                                 excerpt=_excerpt(assertion["description"], *match.span()))
                add(_candidate("technique", _entity_ref(entity), _attack_ref(attack), "explicit_attack_id_in_source_text",
                    ["explicit_technique_identifier", "source_excerpt_preserved"], [anchor],
                    quality["score"], quality,
                    ["A technique identifier in text is a source claim, not proof that the entity used it."]))

    # Techniques inherited only from accepted CTI-to-ATT&CK identity decisions.
    accepted_links = {(item["cti_entity_id"], item["attack_stix_id"]): item for item in snapshot.get("accepted_identity_links", [])}
    attack_relations = snapshot["attack"]["relationships"]
    for (cti_id, attack_id), accepted in sorted(accepted_links.items()):
        entity = entity_by_id.get(cti_id)
        if entity is None:
            continue
        for relation in attack_relations:
            if relation["source_stix_id"] != attack_id or relation["relationship_type"] != "uses":
                continue
            technique = attack_by_stix.get(relation["target_stix_id"])
            if technique is None or technique["stix_type"] != "attack-pattern":
                continue
            identity_anchor = {"kind": "accepted_identity_review", "record_id": accepted["candidate_id"],
                "assertion_id": accepted["review_id"], "source_name": "local analyst review",
                "source_reference": "cti-analysis:" + accepted["evidence_id"], "confidence": 100,
                "last_seen_at": accepted["reviewed_at"], "excerpt": "same_entity"}
            attack_anchor = {"kind": "attack_catalog_relationship", "record_id": relation["stix_id"],
                "assertion_id": None, "source_name": "MITRE ATT&CK", "source_reference": relation["source_url"],
                "confidence": 100, "last_seen_at": relation["modified_at"], "excerpt": relation["description"][:260]}
            quality = {"score": 100, "stated_confidence": 100, "configured_reliability": 100,
                "freshness": 100, "independent_groups": 2, "source_count": 2,
                "meaning": "review_confidence_not_risk_probability"}
            add(_candidate("technique", _entity_ref(entity), _attack_ref(technique), "accepted_identity_plus_official_attack_uses",
                ["analyst_accepted_identity", "official_attack_uses_relationship"],
                [identity_anchor, attack_anchor], 100, quality,
                ["This inherits an ATT&CK catalog relationship; it does not prove current activity."]))

    # Explicit attribution and bounded multi-anchor correlation.
    indicator_edges: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for relation in relationships:
        assertions = relation["assertions"]
        source = entity_by_id.get(relation["source_entity_id"])
        if source is None or not assertions:
            continue
        if relation["relationship_type"] == "attributed-to" and relation["target_kind"] == "entity":
            target = entity_by_id.get(relation["target_id"])
            if target:
                quality = source_quality(assertions, definition, captured_at)
                anchors = [_anchor(value, anchor_kind="relationship_assertion", record_id=relation["id"]) for value in assertions[:20]]
                add(_candidate("attribution", _entity_ref(source), _entity_ref(target), "explicit_attributed_to_source_claim",
                    ["explicit_attributed_to_relationship"], anchors, quality["score"], quality,
                    ["Attribution remains a sourced claim and requires analyst review.", "Contradictory evidence may exist outside the stored scope."]))
        if relation["target_kind"] == "indicator" and relation["relationship_type"] in ("indicates", "communicates-with", "related-to"):
            indicator_edges[relation["target_id"]][source["id"]].extend(assertions)
    shared: dict[tuple[str, str], list[tuple[str, list[dict]]]] = defaultdict(list)
    for indicator_id, by_entity in indicator_edges.items():
        ids = sorted(by_entity)
        if len(ids) > 100:
            stats["oversized_indicator_clusters"] += 1
            continue
        for pos, left in enumerate(ids):
            for right in ids[pos + 1:]:
                shared[(left, right)].append((indicator_id, by_entity[left] + by_entity[right]))
    for (left_id, right_id), evidence in sorted(shared.items()):
        left, right = entity_by_id[left_id], entity_by_id[right_id]
        if "threat-actor" not in (left["entity_type"], right["entity_type"]) or len(evidence) < 2:
            continue
        assertions = [value for _, items in evidence for value in items]
        quality = source_quality(assertions, definition, captured_at)
        if quality["independent_groups"] < definition["minimum_independent_sources"]:
            continue
        actor, other = (left, right) if left["entity_type"] == "threat-actor" else (right, left)
        anchors = []
        for indicator_id, items in evidence[:10]:
            indicator = indicators.get(indicator_id)
            for value in items[:4]:
                anchors.append(_anchor(value, anchor_kind="shared_indicator_relationship", record_id=indicator_id,
                    excerpt=(indicator["indicator_type"] + ":" + indicator["value"]) if indicator else "shared indicator"))
        add(_candidate("attribution", _entity_ref(other), _entity_ref(actor), "multiple_shared_indicators_and_independent_sources",
            ["multiple_distinct_indicator_anchors", "multiple_independent_source_groups", "single_ip_not_sufficient"],
            anchors, min(90, quality["score"] + min(len(evidence), 5) * 3), quality,
            ["Correlation is not attribution proof.", "A single shared IP is explicitly insufficient.", "Infrastructure can be shared or compromised."]))

    # Controlled source-claim tags; obvious negation is not emitted as a positive tag.
    for entity in entities:
        for assertion in entity["assertions"]:
            lowered = folded(assertion["description"])
            for category, lexicon in (("geo", _GEO), ("sector", _SECTORS)):
                for tag, phrases in lexicon.items():
                    positions = [(lowered.find(folded(phrase)), phrase) for phrase in phrases if lowered.find(folded(phrase)) >= 0]
                    if not positions:
                        continue
                    start, phrase = min(positions)
                    if _negated(lowered, start):
                        stats["negated_tags_skipped"] += 1
                        continue
                    quality = source_quality([assertion], definition, captured_at)
                    object_ = {"kind": "tag", "id": category + ":" + tag, "type": category, "label": tag,
                               "truth_status": "source_claim"}
                    anchor = _anchor(assertion, anchor_kind="entity_assertion", record_id=entity["id"],
                                     excerpt=_excerpt(assertion["description"], start, start + len(phrase)))
                    add(_candidate("tag", _entity_ref(entity), object_, "controlled_phrase_source_claim",
                        ["controlled_dictionary_match", "source_claim_not_fact"], [anchor], quality["score"], quality,
                        ["A text mention is not verified origin, location, victim sector or targeting.", "Translation and semantic inference are outside this non-LLM rule."]))

    # Organization priority: only exact domain/subdomain or URL-host ownership evidence.
    organization = snapshot["organization"]
    domains = tuple(organization.get("domains", ()))
    matching_indicators: set[str] = set()
    for indicator in indicators.values():
        host = None
        if indicator["indicator_type"] == "domain":
            try: host = normalize_domain(indicator["value"])
            except ValidationError: pass
        elif indicator["indicator_type"] == "url":
            try: host = normalize_domain(urlsplit(indicator["value"]).hostname or "")
            except (ValidationError, ValueError): pass
        if host and any(host == domain or host.endswith("." + domain) for domain in domains):
            matching_indicators.add(indicator["id"])
    criticality_points = {"low": 5, "medium": 10, "high": 15, "critical": 20}[definition["criticality"]]
    for entity in entities:
        related = [relation for relation in relationships if relation["source_entity_id"] == entity["id"] and relation["target_kind"] == "indicator" and relation["target_id"] in matching_indicators]
        if not related:
            continue
        assertions = [value for relation in related for value in relation["assertions"]]
        quality = source_quality(assertions, definition, captured_at)
        anchors = []
        for relation in related[:10]:
            indicator = indicators[relation["target_id"]]
            for value in relation["assertions"][:4]:
                anchors.append(_anchor(value, anchor_kind="organization_indicator_relationship", record_id=relation["id"],
                    excerpt=indicator["indicator_type"] + ":" + indicator["value"]))
        score = min(100, 35 + criticality_points + round(quality["score"] * .35) + min(len(related), 5) * 3)
        object_ = {"kind": "organization", "id": organization["id"], "type": "organization",
                   "label": organization["display_name"], "criticality": definition["criticality"]}
        add(_candidate("priority", _entity_ref(entity), object_, "exact_owned_domain_indicator_relationship",
            ["exact_domain_or_subdomain_scope", "stored_cti_relationship", "business_criticality_applied"],
            anchors, score, quality,
            ["This is an investigation priority, not breach, attack or maliciousness probability.", "IP ownership is not inferred from DNS or hosting."]))

    ordered = sorted(candidates.values(), key=lambda item: (-item["score"], item["kind"], item["candidate_key"]))
    truncated = len(ordered) > definition["max_candidates"]
    ordered = ordered[:definition["max_candidates"]]
    counts = {kind: sum(item["kind"] == kind for item in ordered) for kind in KINDS}
    source_assertions = [
        assertion
        for record in (*entities, *relationships, *indicators.values())
        for assertion in record["assertions"]
    ]
    source_names = sorted({assertion["source_name"] for assertion in source_assertions}, key=folded)
    source_scope = {
        "observed_source_names": source_names,
        "configured_source_policies": definition["source_policies"],
    }
    analysis_profile_sha256 = digest(definition)
    coverage = {"cti_entities": len(entities), "cti_relationships": len(relationships),
        "cti_indicators": len(indicators), "attack_entities": len(attack_entities),
        "attack_relationships": len(attack_relations), "attack_run_id": snapshot["attack"].get("run_id"),
        "attack_content_sha256": snapshot["attack"].get("content_sha256"),
        "cti_assertions": len(source_assertions), "cti_source_count": len(source_names),
        "cti_source_names": source_names, "cti_source_scope_sha256": digest(source_scope),
        "analysis_profile_sha256": analysis_profile_sha256,
        "organization_domains": list(domains), "truncated": truncated,
        "warnings": dict(sorted(stats.items()))}
    coverage["comparison_sha256"] = digest({
        "attack_content_sha256": coverage["attack_content_sha256"],
        "cti_source_scope_sha256": coverage["cti_source_scope_sha256"],
        "analysis_profile_sha256": coverage["analysis_profile_sha256"],
        "organization_domains": coverage["organization_domains"],
        "truncated": coverage["truncated"],
        "analysis_limits": {key: definition[key] for key in (
            "max_entities", "max_relationships", "max_candidates",
            "identity_threshold", "minimum_independent_sources",
        )},
    })
    coverage["sha256"] = digest(coverage)

    nodes, edges = {}, []
    def graph_node(ref: dict) -> None:
        key = ref["kind"] + ":" + ref["id"]
        nodes.setdefault(key, {"id": key, "kind": ref["kind"], "record_id": ref["id"],
                               "type": ref["type"], "label": ref["label"]})
    # Preserve the source CTI graph as source claims.  Candidate edges are
    # layered on top and never replace the original provenance.
    for relation in relationships:
        source = entity_by_id.get(relation["source_entity_id"])
        if source is None or not relation["assertions"]:
            continue
        source_ref = _entity_ref(source)
        if relation["target_kind"] == "entity":
            target = entity_by_id.get(relation["target_id"])
            if target is None:
                continue
            target_ref = _entity_ref(target)
        else:
            indicator = indicators.get(relation["target_id"])
            if indicator is None:
                continue
            target_ref = {"kind": "cti_indicator", "id": indicator["id"],
                "type": indicator["indicator_type"], "label": indicator["value"]}
        graph_node(source_ref); graph_node(target_ref)
        source_key = source_ref["kind"] + ":" + source_ref["id"]
        target_key = target_ref["kind"] + ":" + target_ref["id"]
        proof = {"record_id": relation["id"], "relationship_type": relation["relationship_type"],
            "assertion_ids": sorted(item["id"] for item in relation["assertions"]),
            "source_references": sorted({item["source_reference"] for item in relation["assertions"]})}
        edges.append({"id": "source-claim:" + relation["id"], "kind": relation["relationship_type"],
            "source": source_key, "target": target_key, "state": "source_claim",
            "score": source_quality(relation["assertions"], definition, captured_at)["score"],
            "evidence_sha256": digest(proof), "evidence_reference": "cti.relationship:" + relation["id"],
            "source_assertion_ids": proof["assertion_ids"]})
    for item in ordered:
        graph_node(item["body"]["subject"]); graph_node(item["body"]["object"])
        edges.append({"id": "candidate:" + item["candidate_key"], "kind": item["kind"],
            "source": item["body"]["subject"]["kind"] + ":" + item["body"]["subject"]["id"],
            "target": item["body"]["object"]["kind"] + ":" + item["body"]["object"]["id"],
            "score": item["score"], "state": "candidate", "evidence_sha256": item["body_sha256"]})
    graph_nodes = sorted(nodes.values(), key=lambda value: value["id"])[:definition["max_graph_nodes"]]
    allowed_nodes = {value["id"] for value in graph_nodes}
    graph_edges = [value for value in sorted(edges, key=lambda value: value["id"])
                   if value["source"] in allowed_nodes and value["target"] in allowed_nodes][:definition["max_graph_edges"]]
    graph = {"nodes": graph_nodes, "edges": graph_edges,
             "truncated": len(nodes) > len(graph_nodes) or len(edges) > len(graph_edges)}
    graph["snapshot_sha256"] = digest(graph)

    timeline = []
    for entity in entities:
        for assertion in entity["assertions"]:
            timeline.append({"at": assertion["last_seen_at"], "kind": "entity_assertion",
                "record_id": assertion["id"], "entity_id": entity["id"], "source_name": assertion["source_name"]})
    for relation in relationships:
        for assertion in relation["assertions"]:
            timeline.append({"at": assertion["last_seen_at"], "kind": "relationship_assertion",
                "record_id": assertion["id"], "relationship_id": relation["id"], "source_name": assertion["source_name"]})
    timeline = sorted(timeline, key=lambda item: (item["at"], item["kind"], item["record_id"]), reverse=True)[:1000]
    return {"policy": POLICY, "captured_at": captured_at, "source_coverage": coverage,
            "counts": counts, "candidates": ordered, "graph": graph, "timeline": timeline,
            "trend_input": {"counts": counts, "high_score_count": sum(item["score"] >= definition["alert_score_min"] for item in ordered),
                            "coverage_sha256": coverage["sha256"]},
            "limitations": ["Candidates are not automatic facts, merges, attribution or maliciousness verdicts.",
                            "Only stored evidence and the local ATT&CK snapshot were analysed.",
                            "Missing records do not prove safety or global absence."]}


def validate_decision(kind: str, decision: str) -> str:
    if kind == "identity":
        allowed = ("same_entity", "different_entity", "uncertain")
    else:
        allowed = ("accepted", "rejected", "uncertain")
    if decision not in allowed:
        raise ValidationError("Bu CTI analiz aday türü için inceleme kararı geçersiz.")
    return decision
