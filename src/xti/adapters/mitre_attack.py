"""Strict, version-pinned MITRE ATT&CK Enterprise STIX 2.1 adapter."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
from http.client import HTTPException
import json
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from xti import __version__
from xti.domain.assets import ValidationError
from xti.domain.cti_attack import (
    ATTACK_SOURCE_URL,
    ATTACK_VERSION,
    AttackEntityRecord,
    AttackRelationshipRecord,
    AttackSnapshot,
    validate_attack_snapshot,
)
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.cti_knowledge import normalize_aliases, normalize_entity_name
from xti.ports.discovery import SourceError


MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_OBJECTS = 30_000
REQUEST_TIMEOUT = 60
_COLLECTION_ID = "x-mitre-collection--1f5f1533-f617-4ca8-9ab4-6a02367fa019"
_ID = re.compile(
    r"(bundle|intrusion-set|campaign|malware|relationship|[a-z0-9-]+)--"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
_TYPE_MAP = {
    "intrusion-set": ("threat-actor", "groups", "G"),
    "campaign": ("campaign", "campaigns", "C"),
    "malware": ("malware", "software", "S"),
}


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


def _stix_id(value: object, expected_type: str | None = None) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise SourceError("MITRE ATT&CK geçersiz STIX kimliği içeriyor.")
    kind, raw_uuid = value.split("--", 1)
    try:
        if str(UUID(raw_uuid)) != raw_uuid:
            raise ValueError("Non-canonical UUID")
    except (ValueError, AttributeError) as error:
        raise SourceError("MITRE ATT&CK geçersiz STIX kimliği içeriyor.") from error
    if expected_type is not None and kind != expected_type:
        raise SourceError("MITRE ATT&CK STIX türü ile kimliği uyuşmuyor.")
    return value


def _timestamp(value: object, field: str, *, fetched_at: datetime) -> str:
    try:
        normalized = normalize_cti_timestamp(value, field=field)
    except ValidationError as error:
        raise SourceError(f"MITRE ATT&CK geçersiz {field} içeriyor.") from error
    if datetime.fromisoformat(normalized) > fetched_at + timedelta(hours=1):
        raise SourceError("MITRE ATT&CK kayıt zamanı sistem saatinden ileride.")
    return normalized


def _active(raw: dict) -> bool:
    revoked = raw.get("revoked", False)
    deprecated = raw.get("x_mitre_deprecated", False)
    if type(revoked) is not bool or type(deprecated) is not bool:
        raise SourceError("MITRE ATT&CK etkinlik alanı geçersiz.")
    return not revoked and not deprecated


def _external_reference(raw: dict, stix_type: str) -> tuple[str, str]:
    references = raw.get("external_references")
    if not isinstance(references, list) or len(references) > 500:
        raise SourceError("MITRE ATT&CK dış başvuru alanı geçersiz.")
    if any(not isinstance(item, dict) for item in references):
        raise SourceError("MITRE ATT&CK dış başvuru alanı geçersiz.")
    selected = [
        item for item in references
        if isinstance(item, dict) and item.get("source_name") == "mitre-attack"
    ]
    if len(selected) != 1:
        raise SourceError("MITRE ATT&CK ana kaynak başvurusu eksik veya yinelenmiş.")
    item = selected[0]
    external_id, url = item.get("external_id"), item.get("url")
    _, path, prefix = _TYPE_MAP[stix_type]
    if (
        not isinstance(external_id, str)
        or not re.fullmatch(prefix + r"[0-9]{4}", external_id)
        or url != f"https://attack.mitre.org/{path}/{external_id}"
    ):
        raise SourceError("MITRE ATT&CK ana kaynak başvurusu geçersiz.")
    return external_id, url


def _entity(raw: dict, *, fetched_at: datetime) -> AttackEntityRecord:
    stix_type = raw.get("type")
    if stix_type not in _TYPE_MAP or raw.get("spec_version") != "2.1":
        raise SourceError("MITRE ATT&CK varlık STIX biçimi desteklenmiyor.")
    stix_id = _stix_id(raw.get("id"), stix_type)
    if not isinstance(raw.get("x_mitre_domains"), list) or (
        "enterprise-attack" not in raw["x_mitre_domains"]
    ):
        raise SourceError("MITRE ATT&CK varlığı Enterprise kapsamı taşımıyor.")
    try:
        name = normalize_entity_name(raw.get("name"))
        raw_aliases = (
            raw.get("x_mitre_aliases", []) if stix_type == "malware"
            else raw.get("aliases", [])
        )
        if not isinstance(raw_aliases, list):
            raise ValidationError("aliases")
        if any(not isinstance(value, str) for value in raw_aliases):
            raise ValidationError("aliases")
        aliases = normalize_aliases(tuple(
            value for value in raw_aliases
            if value.casefold() != name.casefold()
        ))
    except ValidationError as error:
        raise SourceError("MITRE ATT&CK varlık adı veya alternatif adı geçersiz.") from error
    external_id, source_reference = _external_reference(raw, stix_type)
    created = _timestamp(raw.get("created"), "oluşturma zamanı", fetched_at=fetched_at)
    modified = _timestamp(raw.get("modified"), "değişiklik zamanı", fetched_at=fetched_at)
    if datetime.fromisoformat(created) > datetime.fromisoformat(modified):
        raise SourceError("MITRE ATT&CK varlık zamanları ters sırada.")
    local_type = _TYPE_MAP[stix_type][0]
    description = (
        f"MITRE ATT&CK Enterprise {external_id} kaydı; STIX türü {stix_type}. "
        "Bu bilgi kaynak iddiasıdır; otomatik atıf veya tehdit hükmü değildir."
    )
    return AttackEntityRecord(
        stix_id, local_type, name, aliases, source_reference, description, modified,
    )


def parse_attack_response(content: bytes, *, fetched_at: datetime) -> AttackSnapshot:
    if (
        not isinstance(fetched_at, datetime)
        or fetched_at.tzinfo is None
        or fetched_at.utcoffset() is None
    ):
        raise SourceError("MITRE ATT&CK indirme zamanı geçersiz.")
    fetched_at = fetched_at.astimezone(timezone.utc)
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("MITRE ATT&CK yanıtı 64 MiB sınırını aştı.")
    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object,
            parse_constant=_constant,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise SourceError("MITRE ATT&CK geçerli STIX JSON göndermedi.") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"type", "id", "objects"}
        or payload["type"] != "bundle"
        or not isinstance(payload["objects"], list)
        or not 1 <= len(payload["objects"]) <= MAX_OBJECTS
    ):
        raise SourceError("MITRE ATT&CK yanıtı beklenen tam bundle biçiminde değil.")
    _stix_id(payload["id"], "bundle")

    objects: dict[str, dict] = {}
    for raw in payload["objects"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
            raise SourceError("MITRE ATT&CK bundle içinde geçersiz nesne var.")
        stix_id = _stix_id(raw.get("id"), raw["type"])
        if stix_id in objects:
            raise SourceError("MITRE ATT&CK bundle yinelenen STIX kimliği içeriyor.")
        objects[stix_id] = raw

    collections = [raw for raw in objects.values() if raw["type"] == "x-mitre-collection"]
    if len(collections) != 1:
        raise SourceError("MITRE ATT&CK Enterprise koleksiyon kaydı eksik veya yinelenmiş.")
    collection = collections[0]
    if (
        collection.get("id") != _COLLECTION_ID
        or collection.get("name") != "Enterprise ATT&CK"
        or collection.get("x_mitre_version") != ATTACK_VERSION
        or collection.get("spec_version") != "2.1"
    ):
        raise SourceError("MITRE ATT&CK Enterprise koleksiyon sürümü beklenenden farklı.")
    contents = collection.get("x_mitre_contents")
    if not isinstance(contents, list) or len(contents) > MAX_OBJECTS:
        raise SourceError("MITRE ATT&CK koleksiyon içerik dizini geçersiz.")
    content_times: dict[str, str] = {}
    for item in contents:
        if not isinstance(item, dict) or set(item) != {"object_ref", "object_modified"}:
            raise SourceError("MITRE ATT&CK koleksiyon içerik kaydı geçersiz.")
        object_ref = _stix_id(item["object_ref"])
        modified = _timestamp(
            item["object_modified"], "koleksiyon nesne zamanı", fetched_at=fetched_at,
        )
        if object_ref in content_times:
            raise SourceError("MITRE ATT&CK koleksiyon dizini yinelenen kayıt içeriyor.")
        content_times[object_ref] = modified

    selected: dict[str, AttackEntityRecord] = {}
    for raw in objects.values():
        if raw["type"] not in _TYPE_MAP or not _active(raw):
            continue
        record = _entity(raw, fetched_at=fetched_at)
        if content_times.get(record.stix_id) != record.observed_at:
            raise SourceError("MITRE ATT&CK koleksiyon dizini varlıkla uyuşmuyor.")
        selected[record.stix_id] = record

    relationships: list[AttackRelationshipRecord] = []
    for raw in objects.values():
        if raw["type"] != "relationship" or not _active(raw):
            continue
        source_ref, target_ref = raw.get("source_ref"), raw.get("target_ref")
        if source_ref not in selected or target_ref not in selected:
            continue
        if raw.get("spec_version") != "2.1":
            raise SourceError("MITRE ATT&CK ilişki STIX biçimi desteklenmiyor.")
        relationship_type = raw.get("relationship_type")
        if relationship_type not in {"uses", "attributed-to"}:
            raise SourceError("MITRE ATT&CK seçili varlıklar arasında bilinmeyen ilişki içeriyor.")
        stix_id = _stix_id(raw.get("id"), "relationship")
        created = _timestamp(
            raw.get("created"), "ilişki oluşturma zamanı", fetched_at=fetched_at,
        )
        modified = _timestamp(
            raw.get("modified"), "ilişki değişiklik zamanı", fetched_at=fetched_at,
        )
        if datetime.fromisoformat(created) > datetime.fromisoformat(modified):
            raise SourceError("MITRE ATT&CK ilişki zamanları ters sırada.")
        if content_times.get(stix_id) != modified:
            raise SourceError("MITRE ATT&CK koleksiyon dizini ilişkiyle uyuşmuyor.")
        relationships.append(AttackRelationshipRecord(
            stix_id=stix_id, source_stix_id=source_ref,
            relationship_type=relationship_type, target_stix_id=target_ref,
            source_reference=f"{ATTACK_SOURCE_URL}#{stix_id}",
            description=(
                f"MITRE ATT&CK Enterprise STIX ilişkisi {stix_id}. "
                "Bu bağlantı kaynak iddiasıdır; otomatik atıf veya nedensellik değildir."
            ),
            observed_at=modified,
        ))

    snapshot = AttackSnapshot(
        version=ATTACK_VERSION, source_url=ATTACK_SOURCE_URL,
        content_sha256=hashlib.sha256(content).hexdigest(),
        source_object_count=len(objects),
        entities=tuple(sorted(selected.values(), key=lambda value: value.stix_id)),
        relationships=tuple(sorted(relationships, key=lambda value: value.stix_id)),
    )
    try:
        return validate_attack_snapshot(snapshot)
    except ValidationError as error:
        raise SourceError("MITRE ATT&CK seçili CTI alt kümesi geçersiz.") from error


class MitreAttackSource:
    def __init__(
        self, *, opener: Callable | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._open = opener or build_opener(_NoRedirects()).open
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def fetch(self) -> AttackSnapshot:
        request = Request(ATTACK_SOURCE_URL, headers={
            "User-Agent": f"XTI/{__version__} (defensive CTI catalog)",
            "Accept": "text/plain", "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("MITRE ATT&CK başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("MITRE ATT&CK desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "text/plain":
                    raise SourceError("MITRE ATT&CK beklenen metin içerik türünü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                expected_length = None
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError("MITRE ATT&CK geçersiz yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise SourceError("MITRE ATT&CK yanıtı 64 MiB sınırını aşıyor.")
                    expected_length = length
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError("MITRE ATT&CK yanıtı 64 MiB sınırını aştı.")
                if expected_length is not None and len(content) != expected_length:
                    raise SourceError("MITRE ATT&CK yanıtı tamamlanmadan kesildi.")
                return parse_attack_response(content, fetched_at=self._clock())
        except SourceError:
            raise
        except HTTPError as error:
            raise SourceError(f"MITRE ATT&CK HTTP {error.code} verdi.") from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError("MITRE ATT&CK bağlantısı tamamlanamadı.") from error
