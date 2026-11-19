"""Bounded source context, separate from IOC assertions and risk decisions."""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import ipaddress
import json
from urllib.parse import urlencode
from uuid import UUID

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_indicator_value, normalize_cti_timestamp


MAX_BYTES = 2 * 1024 * 1024
URL_RESULT_LIMIT = 20
PROVIDERS = {
    'ripestat-whois': {'types': ('ipv4', 'ipv6'), 'label': 'RIPEstat / RIR kayıt bağlamı',
        'terms': 'https://www.ripe.net/about-us/legal/ripestat-service-terms-and-conditions/',
        'license': 'Provider and underlying registry terms; retain RIPE NCC attribution',
        'commercial_use': 'written_permission_required', 'api_key': 'not_required'},
    'ripestat': {'types': ('ipv4', 'ipv6'), 'label': 'RIPEstat / RIPE RIS ağ bağlamı',
        'terms': 'https://www.ripe.net/about-us/legal/ripestat-service-terms-and-conditions/',
        'license': 'Provider terms; retain RIPE NCC / RIPE RIS attribution',
        'commercial_use': 'written_permission_required', 'api_key': 'not_required'},
    "circl": {"types": ("md5", "sha1", "sha256"), "label": "CIRCL hashlookup",
        "terms": "https://www.circl.lu/services/hashlookup/", "license": "CC-BY (version unspecified)",
        "commercial_use": "attribution_required", "api_key": "not_required"},
    "urlscan": {"types": ("url",), "label": "urlscan existing public scans",
        "terms": "https://urlscan.io/terms/", "license": "Provider terms",
        "commercial_use": "provider_agreement_required_for_product_integration", "api_key": "optional_for_this_public_endpoint"},
}
NOTES = (
    "Kaynak kaydı bulunması veya bulunmaması güvenli/zararlı kararı değildir; IOC ve alarm durumu değiştirilmez.",
    "CIRCL bilinen dosya bağlamıdır; sağlayıcı güven puanı XTI risk skoru değildir.",
    "URL sonuçları geçmiş tarama kayıtlarıdır; yeni tarama gönderilmez, hedef veya dosya açılmaz.",
    "Son deneme ve son geçerli yanıt ayrıdır; kaynak hatası önceki yanıtı silmez.",
)


class EnrichmentRunNotFound(ValidationError):
    pass


@dataclass(frozen=True, slots=True)
class EnrichmentQuery:
    provider: str
    indicator_type: str
    value: str


def enrichment_query(*, indicator_type, value, provider=None):
    if indicator_type not in ("url", "md5", "sha1", "sha256", "ipv4", "ipv6"):
        raise ValidationError("Kaynak araştırması IP, URL, MD5, SHA-1 veya SHA-256 olmalı.")
    value = normalize_indicator_value(indicator_type, value)
    if provider is None:
        provider = "ripestat" if indicator_type in ('ipv4', 'ipv6') else "urlscan" if indicator_type == "url" else "circl"
    if not isinstance(provider, str) or provider not in PROVIDERS or indicator_type not in PROVIDERS[provider]["types"]:
        raise ValidationError("Kaynak bu gösterge türünü desteklemiyor.")
    return EnrichmentQuery(provider, indicator_type, value)


def request_url(query):
    if query.provider == 'ripestat-whois':
        return 'https://stat.ripe.net/data/whois/data.json?' + urlencode({'resource': query.value, 'preferred_version': '4.1'})
    if query.provider == 'ripestat':
        return 'https://stat.ripe.net/data/network-info/data.json?' + urlencode({'resource': query.value, 'preferred_version': '1.1'})
    if query.provider == "circl":
        return f"https://hashlookup.circl.lu/lookup/{query.indicator_type}/{query.value}"
    # The whole value is a quoted Elasticsearch keyword, not query syntax.
    escaped = query.value.replace("\\", "\\\\").replace('"', '\\"')
    search = f'(page.url.keyword:"{escaped}" OR task.url.keyword:"{escaped}")'
    return "https://urlscan.io/api/v1/search/?" + urlencode({"q": search, "size": URL_RESULT_LIMIT})


@dataclass(frozen=True, slots=True)
class EnrichmentSnapshot:
    sha256: str
    status: str
    records: tuple[dict, ...]
    has_more: bool = False
    excluded_count: int = 0
    search_date_limit_days: int | None = None


@dataclass(frozen=True, slots=True)
class EnrichmentRun:
    id: str
    provider: str
    indicator_type: str
    value: str
    started_at: str
    finished_at: str
    status: str
    http_status: int | None
    snapshot_sha256: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class EnrichmentState:
    query: EnrichmentQuery
    latest_run: EnrichmentRun | None
    successful_run: EnrichmentRun | None
    snapshot: EnrichmentSnapshot | None


def _text(value, *, limit=2048):
    if not isinstance(value, str) or not 1 <= len(value) <= limit or not value.isprintable():
        raise ValidationError("Kaynak metni geçersiz veya sınır dışında.")
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("Kaynak JSON alanı tekrarlanıyor.")
        result[key] = value
    return result


def parse_enrichment(query, http_status, content):
    """Validate only retained fields; unknown provider metadata stays in the receipt."""
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_BYTES:
        raise ValidationError("Kaynak yanıtı boş veya boyut sınırını aşıyor.")
    try:
        data = json.loads(content, object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON")))
        if not isinstance(data, dict):
            raise ValueError("Object required")
        digest = hashlib.sha256(content).hexdigest()
        if query.provider == 'ripestat-whois':
            from xti.domain.registry_context import registry_snapshot
            return registry_snapshot(query, http_status, data, digest)
        if query.provider == "circl":
            return _circl(query, http_status, data, digest)
        if query.provider == 'ripestat':
            return _ripestat(query, http_status, data, digest)
        return _urlscan(query, http_status, data, digest)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as error:
        raise ValidationError("Kaynak yanıtı sorguyla veya beklenen veri biçimiyle uyuşmuyor.") from error


def _ripestat(query, status, data, digest):
    if status != 200 or data.get('status') != 'ok' or data.get('data_call_name') != 'network-info':
        raise ValueError('Invalid RIPEstat response')
    payload = data['data']
    if not isinstance(payload, dict) or not isinstance(payload.get('asns'), list) or len(payload['asns']) > 100:
        raise ValueError('Invalid ASN list')
    parameters = data.get('query_params', {})
    if not isinstance(parameters, dict) or ('resource' in parameters and parameters['resource'] != query.value):
        raise ValueError('Wrong RIPEstat query scope')
    if payload.get('resource') is not None and payload['resource'] != query.value:
        raise ValueError('Wrong resource')
    prefix, asns = payload.get('prefix'), []
    for value in payload['asns']:
        if type(value) not in (str, int) or not str(value).isascii() or not str(value).isdigit() or not 1 <= int(value) <= 4294967295:
            raise ValueError('Invalid ASN')
        asns.append(int(value))
    if not prefix:
        if asns:
            raise ValueError('ASNs without prefix')
        return EnrichmentSnapshot(digest, 'no_match', ())
    network = ipaddress.ip_network(prefix, strict=True)
    if ipaddress.ip_address(query.value) not in network:
        raise ValueError('Prefix does not contain requested IP')
    links = [{'source_type': query.indicator_type, 'source_value': query.value,
              'target_type': 'network_prefix', 'target_value': str(network), 'relationship_type': 'reported_routing_prefix'}]
    links += [{'source_type': 'network_prefix', 'source_value': str(network),
               'target_type': 'asn', 'target_value': str(value), 'relationship_type': 'reported_origin_asn'}
              for value in sorted(set(asns))]
    return EnrichmentSnapshot(digest, 'matched', ({'id': query.value, 'reference': request_url(query),
        'observed_at': None, 'description': 'RIPE NCC / RIPE RIS yönlendirme bağlamı; prefix/ASN ilişkisi sahiplik, fiziksel konum veya zararlılık kanıtı değildir.',
        'attributes': {'prefix': str(network), 'asns': sorted(set(asns)), 'attribution': 'RIPE NCC / RIPE RIS'},
        'relationships': links},))


def _circl(query, status, data, digest):
    if status == 404:
        expected = {"md5": "Non existing MD5", "sha1": "Non existing SHA-1", "sha256": "Non existing SHA-256"}
        if data.get("message") != expected[query.indicator_type] or normalize_indicator_value(query.indicator_type, data["query"]) != query.value:
            raise ValueError("Not a documented absence response")
        return EnrichmentSnapshot(digest, "no_match", ())
    if status != 200:
        raise ValueError("Not successful")
    hashes = {}
    for kind, field in (("md5", "MD5"), ("sha1", "SHA-1"), ("sha256", "SHA-256")):
        if field in data:
            hashes[kind] = normalize_indicator_value(kind, data[field])
    if hashes.get(query.indicator_type) != query.value:
        raise ValueError("Wrong hash")
    attrs = {"hashes": hashes}
    for key, field in (("file_name", "FileName"), ("mime_type", "mimetype"), ("source", "source"), ("database", "db")):
        if field in data:
            attrs[key] = _text(data[field])
    if "FileSize" in data:
        value = data["FileSize"]
        if type(value) not in (int, str) or not str(value).isascii() or not str(value).isdigit() or len(str(value)) > 20:
            raise ValueError("Invalid size")
        attrs["file_size"] = int(value)
    if "hashlookup:trust" in data:
        trust = data["hashlookup:trust"]
        if type(trust) is not int or not 0 <= trust <= 100:
            raise ValueError("Invalid source trust")
        attrs["provider_trust"] = trust
    links = [{"source_type": query.indicator_type, "source_value": query.value,
              "target_type": kind, "target_value": value, "relationship_type": "provider_file_hash"}
             for kind, value in sorted(hashes.items()) if kind != query.indicator_type]
    record = {"id": query.value, "reference": request_url(query), "observed_at": None,
        "description": "CIRCL kaydında aynı dosya için bildirilen kimlikler; dosya zararlılığı veya çakışmasız kimlik kanıtı değildir.",
        "attributes": attrs, "relationships": links}
    return EnrichmentSnapshot(digest, "matched", (record,))


def _urlscan(query, status, data, digest):
    if status != 200 or not isinstance(data.get("results"), list) or type(data.get("has_more")) is not bool:
        raise ValueError("Invalid archive response")
    if len(data["results"]) > URL_RESULT_LIMIT:
        raise ValueError("Result limit exceeded")
    date_limit, total = data.get("search_date_limit_days"), data.get("total")
    if date_limit is not None and (type(date_limit) is not int or date_limit < 0):
        raise ValueError("Invalid time window")
    if total is not None and (type(total) is not int or total < len(data["results"])):
        raise ValueError("Invalid total")
    records, seen, excluded = [], set(), 0
    for row in data["results"]:
        task, page = row["task"], row["page"]
        identifier = str(UUID(row["_id"]))
        if identifier != row["_id"] or task.get("uuid") != identifier or identifier in seen or task.get("visibility") != "public":
            raise ValueError("Invalid public scan identity")
        seen.add(identifier)
        task_url = normalize_indicator_value("url", task["url"])
        page_url = normalize_indicator_value("url", page["url"])
        matched_fields = [field for field, value in (("task.url", task_url), ("page.url", page_url)) if value == query.value]
        if not matched_fields:
            excluded += 1
            continue
        observed_at = normalize_cti_timestamp(task["time"])
        attrs = {"task_url": task_url, "page_url": page_url, "matched_fields": matched_fields}
        if page.get("title"):
            attrs["title"] = _text(page["title"])
        links = []
        # The IP belongs to the observed final page, never to the submitted URL
        # merely because a redirect ended there.
        if page.get("ip"):
            ip = ipaddress.ip_address(page["ip"])
            attrs["page_ip"] = ip.compressed
            links.append({"source_type": "url", "source_value": page_url,
                "target_type": f"ipv{ip.version}", "target_value": ip.compressed,
                "relationship_type": "archived_page_ip"})
        if task_url != page_url:
            links.append({"source_type": "url", "source_value": task_url,
                "target_type": "url", "target_value": page_url, "relationship_type": "archived_navigation"})
        records.append({"id": identifier, "reference": f"https://urlscan.io/result/{identifier}/",
            "observed_at": observed_at, "description": "Geçmiş public urlscan kaydı; gezinme sonucu ve o tarihte bildirilen sayfa IP'si.",
            "attributes": attrs, "relationships": links})
    has_more = data["has_more"] or (total is not None and total > len(data["results"]))
    return EnrichmentSnapshot(digest, "matched" if records else "no_match", tuple(records), has_more, excluded, date_limit)
