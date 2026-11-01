"""Shared bounded parser and transport for official per-CVE CSAF VEX sources."""

from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
import json
import socket
from dataclasses import dataclass
from typing import Callable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError
from xti.domain.vendor_advisory import (
    VendorAdvisory,
    VendorAdvisorySnapshot,
    VendorProduct,
    VendorProductStatus,
    VendorRemediation,
)
from xti.domain.vulnerability import normalize_cve_id
from xti.ports.discovery import SourceError


MAX_RESPONSE_BYTES = 16 * 1024 * 1024
REQUEST_TIMEOUT = 30
_MAX_TREE_NODES = 100_000
_MAX_STATUS_PRODUCTS = 100_000
_STATUS_ORDER = (
    "fixed", "known_affected", "known_not_affected", "under_investigation",
    "first_affected", "first_fixed", "last_affected", "recommended",
)
_STATUS_VALUES = set(_STATUS_ORDER)
_REMEDIATION_CATEGORIES = {
    "mitigation", "no_fix_planned", "none_available", "vendor_fix", "workaround",
}
_DOCUMENT_STATUSES = {"draft", "interim", "final"}


@dataclass(frozen=True, slots=True)
class CsafVexProvider:
    """Authenticated source identity and deterministic endpoint policy."""

    key: str
    source: str
    provider_name: str
    publisher_name: str
    publisher_namespace: str
    url_builder: Callable[[str], str]


def _source_error(message: str) -> SourceError:
    return SourceError(f"CSAF VEX {message}")


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON number")


def _mapping(value: object, field: str) -> dict:
    if not isinstance(value, dict):
        raise _source_error(f"kaydında geçersiz {field} nesnesi var.")
    return value


def _text(
    value: object, field: str, maximum: int, *, optional: bool = False,
) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise _source_error(f"kaydında geçersiz {field} alanı var.")
    characters = []
    for character in value:
        if unicodedata.category(character) == "Zs" or character in "\r\n\t":
            characters.append(" ")
        elif character.isprintable():
            characters.append(character)
        else:
            raise _source_error(f"kaydında geçersiz {field} alanı var.")
    normalized = " ".join("".join(characters).split())
    if not normalized or len(normalized) > maximum:
        raise _source_error(f"kaydında geçersiz {field} alanı var.")
    return normalized


def _identifier(value: object, field: str, maximum: int = 2000) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) > 126 for character in value)
    ):
        raise _source_error(f"kaydında geçersiz {field} kimliği var.")
    return value


def _timestamp(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    value = _text(value, field, 64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as error:
        raise _source_error(f"kaydında geçersiz {field} zamanı var.") from error
    return parsed.isoformat()


def _url(value: object, field: str, *, optional: bool = False) -> str | None:
    value = _text(value, field, 4096, optional=optional)
    if value is None:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise _source_error(f"kaydında geçersiz {field} adresi var.") from error
    if (
        parsed.scheme not in {"http", "https"} or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or port is not None and not 1 <= port <= 65535
    ):
        raise _source_error(f"kaydında geçersiz {field} adresi var.")
    return value


def _product_helper(value: object) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    value = _mapping(value, "ürün tanımlama yardımcısı")
    purl = None
    cpe = None
    if "purl" in value:
        purl = _identifier(value["purl"], "ürün PURL", 4096)
        if not purl.startswith("pkg:") or "#" in purl:
            raise _source_error("kaydında geçersiz ürün PURL değeri var.")
    if "cpe" in value:
        cpe = _identifier(value["cpe"], "ürün CPE", 4096)
        if not cpe.startswith(("cpe:/", "cpe:2.3:")):
            raise _source_error("kaydında geçersiz ürün CPE değeri var.")
    return purl, cpe


def _product_catalog(product_tree: object) -> dict[str, VendorProduct]:
    _mapping(product_tree, "ürün ağacı")
    stack: list[tuple[object, int]] = [(product_tree, 0)]
    products: dict[str, VendorProduct] = {}
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > _MAX_TREE_NODES or depth > 100:
            raise _source_error("ürün ağacı güvenli sınırı aştı.")
        if isinstance(value, dict):
            if "product_id" in value or "name" in value:
                if "product_id" in value and "name" in value:
                    product_id = _identifier(value["product_id"], "ürün")
                    name = _text(value["name"], "ürün adı", 2000)
                    purl, cpe = _product_helper(value.get("product_identification_helper"))
                    product = VendorProduct(
                        product_id=product_id, name=name, purl=purl, cpe=cpe,
                    )
                    previous = products.get(product_id)
                    if previous is not None and previous != product:
                        raise _source_error("ürün kimliği çelişen tanımlar taşıyor.")
                    products[product_id] = product
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
    if not products:
        raise _source_error("kaydında doğrulanabilir ürün kimliği yok.")
    return products


def _relationships(
    product_tree: object, products: dict[str, VendorProduct],
) -> dict[str, tuple[str, str, str]]:
    tree = _mapping(product_tree, "ürün ağacı")
    value = tree.get("relationships", [])
    if not isinstance(value, list) or len(value) > _MAX_TREE_NODES:
        raise _source_error("kaydında geçersiz ürün ilişki listesi var.")
    result: dict[str, tuple[str, str, str]] = {}
    for item in value:
        item = _mapping(item, "ürün ilişkisi")
        category = _identifier(item.get("category"), "ürün ilişki türü", 100)
        component_id = _identifier(item.get("product_reference"), "ilişki bileşeni")
        context_id = _identifier(
            item.get("relates_to_product_reference"), "ilişki ürün bağlamı",
        )
        full = _mapping(item.get("full_product_name"), "ilişki tam ürün adı")
        full_id = _identifier(full.get("product_id"), "ilişki tam ürünü")
        if component_id not in products or context_id not in products or full_id not in products:
            raise _source_error("ürün ilişkisi ürün ağacında olmayan kimlik taşıyor.")
        relation = (category, component_id, context_id)
        previous = result.get(full_id)
        if previous is not None and previous != relation:
            raise _source_error("tam ürün kimliği çelişen ilişkiler taşıyor.")
        result[full_id] = relation
    return result


def _product_statuses(
    value: object, catalog: dict[str, VendorProduct],
    relationships: dict[str, tuple[str, str, str]],
) -> tuple[VendorProductStatus, ...]:
    value = _mapping(value, "ürün durumu")
    if not value or set(value).difference(_STATUS_VALUES):
        raise _source_error("kaydında geçersiz ürün durumu türü var.")
    statuses: dict[str, VendorProductStatus] = {}
    seen: set[str] = set()
    total = 0
    for status, raw_ids in value.items():
        if not isinstance(raw_ids, list):
            raise _source_error("kaydında geçersiz ürün durumu listesi var.")
        if not raw_ids:
            continue
        products = []
        local: set[str] = set()
        for raw_id in raw_ids:
            product_id = _identifier(raw_id, "durum ürün")
            if product_id in local or product_id in seen:
                raise _source_error("kaydında çelişen veya yinelenen ürün durumu var.")
            if product_id not in catalog:
                raise _source_error("ürün durumu ürün ağacında bulunmuyor.")
            local.add(product_id)
            seen.add(product_id)
            base = catalog[product_id]
            relation = relationships.get(product_id)
            if relation is None:
                products.append(base)
            else:
                category, component_id, context_id = relation
                component = catalog[component_id]
                context = catalog[context_id]
                products.append(VendorProduct(
                    product_id=base.product_id, name=base.name, purl=base.purl, cpe=base.cpe,
                    relationship_category=category,
                    component_product_id=component.product_id,
                    component_purl=component.purl,
                    context_product_id=context.product_id,
                    context_cpe=context.cpe,
                ))
        total += len(products)
        if total > _MAX_STATUS_PRODUCTS:
            raise _source_error("ürün durumu sınırı aşıldı.")
        statuses[status] = VendorProductStatus(
            status=status, products=tuple(sorted(products, key=lambda item: item.product_id)),
        )
    if not statuses:
        raise _source_error("kaydında doğrulanabilir ürün durumu yok.")
    return tuple(statuses[status] for status in _STATUS_ORDER if status in statuses)


def _remediations(value: object, products: dict[str, VendorProduct]) -> tuple[VendorRemediation, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > 10_000:
        raise _source_error("kaydında geçersiz düzeltme listesi var.")
    result = []
    total_targets = 0
    for item in value:
        item = _mapping(item, "düzeltme")
        category = _text(item.get("category"), "düzeltme türü", 50)
        if category not in _REMEDIATION_CATEGORIES:
            raise _source_error("kaydında desteklenmeyen düzeltme türü var.")
        product_ids = item.get("product_ids", [])
        group_ids = item.get("group_ids", [])
        if not isinstance(product_ids, list) or not isinstance(group_ids, list):
            raise _source_error("düzeltmesinde geçersiz hedef listesi var.")
        if len(product_ids) + len(group_ids) > _MAX_STATUS_PRODUCTS:
            raise _source_error("düzeltme hedef sınırı aşıldı.")
        normalized_products = {_identifier(value, "düzeltme ürünü") for value in product_ids}
        if len(normalized_products) != len(product_ids):
            raise _source_error("düzeltmesinde yinelenen ürün hedefi var.")
        if normalized_products.difference(products):
            raise _source_error("düzeltme ürünü ürün ağacında bulunmuyor.")
        normalized_groups = {_identifier(value, "düzeltme grubu") for value in group_ids}
        if len(normalized_groups) != len(group_ids):
            raise _source_error("düzeltmesinde yinelenen grup hedefi var.")
        target_count = len(product_ids) + len(group_ids)
        total_targets += target_count
        if total_targets > _MAX_STATUS_PRODUCTS:
            raise _source_error("toplam düzeltme hedef sınırı aşıldı.")
        result.append(VendorRemediation(
            category=category, details=_text(item.get("details"), "düzeltme açıklaması", 20_000),
            date=_timestamp(item.get("date"), "düzeltme", optional=True),
            url=_url(item.get("url"), "düzeltme", optional=True),
            target_count=target_count,
        ))
    return tuple(result)


def parse_csaf_vex_response(
    content: bytes, expected_cve_id: str, provider: CsafVexProvider,
) -> VendorAdvisorySnapshot:
    """Parse one authenticated provider's bounded single-CVE CSAF VEX document."""

    cve_id = normalize_cve_id(expected_cve_id)
    if len(content) > MAX_RESPONSE_BYTES:
        raise _source_error("yanıtı 16 MiB sınırını aştı.")
    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant,
        )
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise _source_error("kaynağı geçerli JSON verisi göndermedi.") from error
    payload = _mapping(payload, "kök")
    document = _mapping(payload.get("document"), "belge")
    if document.get("category") != "csaf_vex" or document.get("csaf_version") != "2.0":
        raise _source_error("yanıtı beklenen CSAF VEX 2.0 belgesi değil.")
    publisher = _mapping(document.get("publisher"), "yayımcı")
    if (
        publisher.get("category") != "vendor"
        or publisher.get("name") != provider.publisher_name
        or publisher.get("namespace") != provider.publisher_namespace
    ):
        raise _source_error(f"{provider.key} yayımcı kimliği doğrulanamadı.")
    tracking = _mapping(document.get("tracking"), "izleme")
    try:
        record_id = normalize_cve_id(tracking.get("id"))
    except ValidationError as error:
        raise _source_error("kayıt kimliği geçersiz.") from error
    if record_id != cve_id:
        raise _source_error("yanıtı istenenden farklı bir CVE içeriyor.")
    document_status = _text(tracking.get("status"), "belge durumu", 20)
    if document_status not in _DOCUMENT_STATUSES:
        raise _source_error("belge durumu geçersiz.")
    initial_release_at = _timestamp(tracking.get("initial_release_date"), "ilk yayın")
    current_release_at = _timestamp(tracking.get("current_release_date"), "güncel yayın")
    if datetime.fromisoformat(current_release_at) < datetime.fromisoformat(initial_release_at):
        raise _source_error("güncel yayın zamanı ilk yayından önce.")
    history = tracking.get("revision_history")
    if not isinstance(history, list) or not history or len(history) > 1000:
        raise _source_error("sürüm geçmişi geçersiz.")
    for item in history:
        item = _mapping(item, "sürüm geçmişi")
        _timestamp(item.get("date"), "sürüm geçmişi")
        _text(item.get("number"), "sürüm numarası", 100)
        _text(item.get("summary"), "sürüm özeti", 2000)

    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, list) or len(vulnerabilities) != 1:
        raise _source_error("tek-CVE kaydı tam bir zafiyet taşımalı.")
    vulnerability = _mapping(vulnerabilities[0], "zafiyet")
    try:
        vulnerability_cve = normalize_cve_id(vulnerability.get("cve"))
    except ValidationError as error:
        raise _source_error("zafiyet kimliği geçersiz.") from error
    if vulnerability_cve != cve_id:
        raise _source_error("zafiyet kimliği istenen CVE ile uyuşmuyor.")

    product_tree = payload.get("product_tree")
    products = _product_catalog(product_tree)
    relationships = _relationships(product_tree, products)
    statuses = _product_statuses(
        vulnerability.get("product_status"), products, relationships,
    )
    remediations = _remediations(vulnerability.get("remediations"), products)
    aggregate = document.get("aggregate_severity")
    severity = None
    if aggregate is not None:
        severity = _text(_mapping(aggregate, "toplu önem").get("text"), "önem", 100)
    advisory = VendorAdvisory(
        provider=provider.provider_name, cve_id=cve_id, record_id=record_id,
        title=_text(document.get("title"), "başlık", 5000),
        document_status=document_status,
        document_version=_text(tracking.get("version"), "belge sürümü", 100),
        initial_release_at=initial_release_at, current_release_at=current_release_at,
        severity=severity, product_statuses=statuses, remediations=remediations,
    )
    return VendorAdvisorySnapshot(
        source=provider.source, source_url=provider.url_builder(cve_id),
        format_version="CSAF VEX 2.0", content_sha256=hashlib.sha256(content).hexdigest(),
        advisory=advisory,
    )


class CsafVexSource:
    """Fetch one provider's deterministic HTTPS VEX object without redirects."""

    def __init__(
        self, provider: CsafVexProvider, *, opener: Callable | None = None,
    ) -> None:
        self.provider = provider
        self._open = opener or build_opener(_NoRedirects()).open

    def fetch(self, cve_id: str) -> VendorAdvisorySnapshot:
        cve_id = normalize_cve_id(cve_id)
        request = Request(self.provider.url_builder(cve_id), headers={
            "User-Agent": (
                f"XTI/{__version__} (personal defensive "
                f"{self.provider.key} CSAF VEX preview)"
            ),
            "Accept": "application/json", "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise _source_error("kaynağı başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise _source_error("kaynağı desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise _source_error("kaynağı JSON içerik türü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise _source_error("kaynağı geçersiz yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise _source_error("yanıtı 16 MiB sınırını aşıyor.")
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise _source_error("yanıtı 16 MiB sınırını aştı.")
                return parse_csaf_vex_response(content, cve_id, self.provider)
        except SourceError:
            raise
        except HTTPError as error:
            if error.code == 404:
                raise _source_error(
                    f"kaynağında CVE için {self.provider.key} kaydı bulunamadı."
                ) from error
            raise _source_error(f"kaynağı HTTP {error.code} verdi.") from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise _source_error("kaynağına güvenli bağlantı tamamlanamadı.") from error
        except ValidationError as error:
            raise SourceError(str(error)) from error
