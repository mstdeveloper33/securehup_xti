"""Strict offline reader for the pinned social-source coverage evidence."""

from collections.abc import Callable
import hashlib
from importlib.resources import files
import json
import re
from urllib.parse import urlsplit

from xti.domain.assets import ValidationError
from xti.domain.brand_source_coverage import (
    BrandSourceCoverageComparison,
    BrandSourceCoverageCriterion,
    BrandSourceCoverageReport,
    BrandSourceCoverageShortlistItem,
    BrandSourceCoverageSource,
)


PROFILE_SHA256 = "dbdba7826c6033bd22208c4b2584796af706c25282285368d4d25f92bfd4f5a1"
MAX_PROFILE_BYTES = 32 * 1024
_HEX_40 = re.compile(r"[0-9a-f]{40}")
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


def _packaged_profile() -> bytes:
    return files("xti").joinpath("data").joinpath(
        "brand_social_source_coverage_v1.json"
    ).read_bytes()


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _object(value, keys: frozenset[str], label: str) -> dict:
    if not isinstance(value, dict) or frozenset(value) != keys:
        raise ValidationError(f"Sosyal kaynak kapsam profilinde {label} bozuk.")
    return value


def _text(value, label: str, *, maximum: int = 1000) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValidationError(f"Sosyal kaynak kapsam profilinde {label} bozuk.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValidationError(f"Sosyal kaynak kapsam profilinde {label} bozuk.")
    return value


def _count(value, label: str, *, allow_zero: bool = True) -> int:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or not minimum <= value <= 1_000_000_000:
        raise ValidationError(f"Sosyal kaynak kapsam profilinde {label} bozuk.")
    return value


def _boolean(value, label: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"Sosyal kaynak kapsam profilinde {label} bozuk.")
    return value


def _texts(value, label: str, *, maximum: int = 100) -> tuple[str, ...]:
    if not isinstance(value, list) or not 0 <= len(value) <= maximum:
        raise ValidationError(f"Sosyal kaynak kapsam profilinde {label} bozuk.")
    result = tuple(_text(item, label) for item in value)
    if len(set(result)) != len(result):
        raise ValidationError(f"Sosyal kaynak kapsam profilinde {label} yineleniyor.")
    return result


def _https_url(value, label: str) -> str:
    result = _text(value, label)
    try:
        parsed = urlsplit(result)
        port = parsed.port
    except ValueError as error:
        raise ValidationError(
            f"Sosyal kaynak kapsam profilinde {label} bozuk."
        ) from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ValidationError(f"Sosyal kaynak kapsam profilinde {label} bozuk.")
    return result


class BrandSourceCoverageService:
    def __init__(
        self,
        profile_loader: Callable[[], bytes] = _packaged_profile,
        *,
        expected_sha256: str = PROFILE_SHA256,
    ) -> None:
        self.profile_loader = profile_loader
        self.expected_sha256 = expected_sha256

    def report(self) -> BrandSourceCoverageReport:
        payload = self.profile_loader()
        if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_PROFILE_BYTES:
            raise ValidationError("Sosyal kaynak kapsam profili güvenli boyutta değil.")
        digest = hashlib.sha256(payload).hexdigest()
        if digest != self.expected_sha256:
            raise ValidationError("Sosyal kaynak kapsam profili incelenen sürümle uyuşmuyor.")
        try:
            raw = json.loads(payload, object_pairs_hook=_no_duplicate_keys)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            raise ValidationError("Sosyal kaynak kapsam profili geçerli JSON değil.") from error
        root = _object(raw, frozenset({
            "schema_version", "profile_version", "evaluated_at",
            "matching_rule_version", "public_suffix_profile", "sources",
            "comparison", "criteria", "decision", "decision_reason", "shortlist",
            "next_step", "limitations", "reference_urls",
        }), "kök yapı")
        if root["schema_version"] != 1:
            raise ValidationError("Sosyal kaynak kapsam profili sürümü desteklenmiyor.")

        suffix = _object(root["public_suffix_profile"], frozenset({
            "version", "sha256",
        }), "Public Suffix List kanıtı")
        suffix_version = _text(suffix["version"], "Public Suffix List sürümü")
        suffix_sha256 = _text(suffix["sha256"], "Public Suffix List özeti")
        if _HEX_64.fullmatch(suffix_sha256) is None:
            raise ValidationError("Sosyal kaynak kapsam profilinde PSL özeti bozuk.")

        sources_raw = root["sources"]
        if not isinstance(sources_raw, list) or len(sources_raw) != 2:
            raise ValidationError("Sosyal kaynak kapsam profilinde kaynaklar bozuk.")
        sources = tuple(self._source(item) for item in sources_raw)
        if tuple(source.role for source in sources) != ("primary", "candidate"):
            raise ValidationError("Sosyal kaynak kapsam profilinde kaynak rolleri bozuk.")
        if len({source.identifier for source in sources}) != 2:
            raise ValidationError("Sosyal kaynak kapsam profilinde kaynak yineleniyor.")

        comparison = self._comparison(root["comparison"])
        primary, candidate = sources
        if candidate.eligible_entries != (
            comparison.shared_candidate_entries
            + comparison.candidate_unmatched_entries
        ):
            raise ValidationError("Sosyal kaynak kapsam profilinde aday toplamı tutarsız.")
        if not (
            comparison.candidate_unmatched_distinct_registrable_domains
            <= comparison.candidate_unmatched_distinct_hosts
            <= comparison.candidate_unmatched_entries
        ):
            raise ValidationError("Sosyal kaynak kapsam profilinde özgün kapsam tutarsız.")
        if primary.current_approved_platforms != (
            comparison.current_shared_platforms + len(comparison.current_primary_only)
        ) or candidate.current_approved_platforms != (
            comparison.current_shared_platforms + len(comparison.current_candidate_only)
        ):
            raise ValidationError("Sosyal kaynak kapsam profilinde güncel kapsam tutarsız.")
        if comparison.current_approved_total != primary.current_approved_platforms:
            raise ValidationError("Sosyal kaynak kapsam profilinde izinli toplam tutarsız.")

        criteria_raw = root["criteria"]
        if not isinstance(criteria_raw, list) or not 1 <= len(criteria_raw) <= 20:
            raise ValidationError("Sosyal kaynak kapsam profilinde ölçütler bozuk.")
        criteria = tuple(self._criterion(item) for item in criteria_raw)
        if len({item.key for item in criteria}) != len(criteria):
            raise ValidationError("Sosyal kaynak kapsam profilinde ölçüt yineleniyor.")
        if not all(item.passed for item in criteria if item.required):
            raise ValidationError("Sosyal kaynak kapsam profilinde zorunlu kapı geçilmedi.")

        shortlist_raw = root["shortlist"]
        if not isinstance(shortlist_raw, list) or not 1 <= len(shortlist_raw) <= 20:
            raise ValidationError("Sosyal kaynak kapsam profilinde kısa liste bozuk.")
        shortlist = tuple(self._shortlist(item) for item in shortlist_raw)
        if len({item.platform for item in shortlist}) != len(shortlist):
            raise ValidationError("Sosyal kaynak kapsam profilinde platform yineleniyor.")
        if len({item.host for item in shortlist}) != len(shortlist):
            raise ValidationError("Sosyal kaynak kapsam profilinde host yineleniyor.")

        limitations = _texts(root["limitations"], "sınırlama")
        references = tuple(
            _https_url(item, "başvuru adresi")
            for item in _texts(root["reference_urls"], "başvuru adresi")
        )
        decision = _text(root["decision"], "karar")
        if decision != "accepted_for_limited_adapter":
            raise ValidationError("Sosyal kaynak kapsam profilinde karar desteklenmiyor.")
        return BrandSourceCoverageReport(
            profile_version=_text(root["profile_version"], "profil sürümü"),
            profile_sha256=digest,
            evaluated_at=_text(root["evaluated_at"], "değerlendirme tarihi"),
            matching_rule_version=_text(root["matching_rule_version"], "eşleme sürümü"),
            public_suffix_version=suffix_version,
            public_suffix_sha256=suffix_sha256,
            sources=sources,
            comparison=comparison,
            criteria=criteria,
            decision=decision,
            decision_reason=_text(root["decision_reason"], "karar gerekçesi"),
            shortlist=shortlist,
            next_step=_text(root["next_step"], "sonraki adım"),
            limitations=limitations,
            reference_urls=references,
        )

    @staticmethod
    def _source(value) -> BrandSourceCoverageSource:
        raw = _object(value, frozenset({
            "identifier", "label", "role", "version", "upstream_commit",
            "catalog_sha256", "catalog_bytes", "catalog_entries",
            "eligible_entries", "current_approved_platforms", "license",
            "reference_url",
        }), "kaynak")
        commit = _text(raw["upstream_commit"], "upstream commit")
        digest = _text(raw["catalog_sha256"], "katalog özeti")
        if _HEX_40.fullmatch(commit) is None or _HEX_64.fullmatch(digest) is None:
            raise ValidationError("Sosyal kaynak kapsam profilinde kaynak özeti bozuk.")
        catalog_entries = _count(raw["catalog_entries"], "katalog toplamı", allow_zero=False)
        eligible_entries = _count(raw["eligible_entries"], "uygun tanım toplamı")
        if eligible_entries > catalog_entries:
            raise ValidationError("Sosyal kaynak kapsam profilinde kaynak toplamı tutarsız.")
        return BrandSourceCoverageSource(
            identifier=_text(raw["identifier"], "kaynak kimliği"),
            label=_text(raw["label"], "kaynak adı"),
            role=_text(raw["role"], "kaynak rolü"),
            version=_text(raw["version"], "kaynak sürümü"),
            upstream_commit=commit,
            catalog_sha256=digest,
            catalog_bytes=_count(raw["catalog_bytes"], "katalog boyutu", allow_zero=False),
            catalog_entries=catalog_entries,
            eligible_entries=eligible_entries,
            current_approved_platforms=_count(
                raw["current_approved_platforms"], "güncel platform toplamı",
            ),
            license=_text(raw["license"], "kaynak lisansı"),
            reference_url=_https_url(raw["reference_url"], "kaynak adresi"),
        )

    @staticmethod
    def _comparison(value) -> BrandSourceCoverageComparison:
        raw = _object(value, frozenset({
            "shared_candidate_entries", "candidate_unmatched_entries",
            "candidate_unmatched_distinct_hosts",
            "candidate_unmatched_distinct_registrable_domains",
            "current_approved_total", "current_shared_platforms",
            "current_primary_only", "current_candidate_only", "method_notes",
        }), "karşılaştırma")
        return BrandSourceCoverageComparison(
            shared_candidate_entries=_count(raw["shared_candidate_entries"], "ortak tanım"),
            candidate_unmatched_entries=_count(
                raw["candidate_unmatched_entries"], "özgün aday tanımı",
            ),
            candidate_unmatched_distinct_hosts=_count(
                raw["candidate_unmatched_distinct_hosts"], "özgün host",
            ),
            candidate_unmatched_distinct_registrable_domains=_count(
                raw["candidate_unmatched_distinct_registrable_domains"],
                "özgün kayıt kökü",
            ),
            current_approved_total=_count(raw["current_approved_total"], "izinli toplam"),
            current_shared_platforms=_count(
                raw["current_shared_platforms"], "ortak izinli platform",
            ),
            current_primary_only=_texts(raw["current_primary_only"], "ana kaynağa özgü"),
            current_candidate_only=_texts(
                raw["current_candidate_only"], "aday kaynağa özgü",
            ),
            method_notes=_texts(raw["method_notes"], "yöntem notu"),
        )

    @staticmethod
    def _criterion(value) -> BrandSourceCoverageCriterion:
        raw = _object(value, frozenset({
            "key", "label", "required", "passed", "evidence",
        }), "ölçüt")
        return BrandSourceCoverageCriterion(
            key=_text(raw["key"], "ölçüt kimliği"),
            label=_text(raw["label"], "ölçüt adı"),
            required=_boolean(raw["required"], "ölçüt zorunluluğu"),
            passed=_boolean(raw["passed"], "ölçüt sonucu"),
            evidence=_text(raw["evidence"], "ölçüt kanıtı"),
        )

    @staticmethod
    def _shortlist(value) -> BrandSourceCoverageShortlistItem:
        raw = _object(value, frozenset({
            "platform", "host", "purpose",
        }), "kısa liste öğesi")
        host = _text(raw["host"], "kısa liste hostu").lower()
        if _HOST.fullmatch(host) is None:
            raise ValidationError("Sosyal kaynak kapsam profilinde kısa liste hostu bozuk.")
        return BrandSourceCoverageShortlistItem(
            platform=_text(raw["platform"], "kısa liste platformu"),
            host=host,
            purpose=_text(raw["purpose"], "kısa liste amacı"),
        )
