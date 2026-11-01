"""Small, explainable domain-candidate rules without network or storage access.

These rules produce review candidates, not a finding of phishing or ownership.
Unicode comparison is injected as a pinned profile; the stored DNS identity
remains the canonical ASCII A-label.
"""

from dataclasses import dataclass
from typing import Protocol

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.findings import MatchCandidate
from xti.domain.idn import UnicodeSecurityProfile


RULE_VERSION = "domain-rules-v3"
LEGACY_RULE_VERSION = "domain-rules-v1"
EXPANDED_ASCII_RULE_VERSION = "domain-rules-v2"
IDN_RULE_VERSION = "idn-confusables-v1"


@dataclass(frozen=True, slots=True)
class DomainParts:
    registrable_domain: str | None
    brand: str | None
    suffix: str
    subdomain: str


class DomainResolver(Protocol):
    """Resolve registration boundaries using an explicit suffix data source."""

    def parts(self, domain: str) -> DomainParts:
        ...


def normalize_for_matching(domain: str) -> str:
    """Keep the canonical comparison/storage identity as an ASCII DNS name."""
    return normalize_domain(domain)


_SERVICE_WORDS = frozenset({
    "account", "auth", "billing", "destek", "giris", "help", "hesap", "login",
    "online", "portal", "secure", "support", "verify",
})

# Common service labels are weak evidence of a brand. A complete watched
# domain embedded in a different domain remains an explicit signal.
_COMMON_LABELS = frozenset({
    "account", "admin", "api", "app", "auth", "cdn", "demo", "help", "login",
    "mail", "online", "portal", "secure", "shop", "store", "support", "test", "www",
})

_EXPANDED_COMPACT_WORDS = frozenset({"shop"})


def _brand_extension(brand: str, candidate: str) -> bool:
    """Accept label boundaries or known additions, never arbitrary substrings."""
    if len(brand) < 4 or brand == candidate:
        return False
    if (
        candidate.startswith(brand + "-")
        or candidate.endswith("-" + brand)
        or ("-" + brand + "-") in candidate
    ):
        return True
    compact_brand = brand.replace("-", "")
    compact_candidate = candidate.replace("-", "")
    return any(
        compact_candidate == compact_brand + word
        or compact_candidate == word + compact_brand
        for word in _SERVICE_WORDS
    )


def _one_edit_apart(left: str, right: str) -> bool:
    """Check Levenshtein distance exactly one in linear time and bounded space."""
    difference = len(left) - len(right)
    if abs(difference) > 1 or left == right:
        return False
    if difference == 0:
        return sum(a != b for a, b in zip(left, right)) == 1
    shorter, longer = (left, right) if difference < 0 else (right, left)
    index = 0
    while index < len(shorter) and shorter[index] == longer[index]:
        index += 1
    return shorter[index:] == longer[index + 1:]


def _adjacent_swap(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    differences = [index for index, (a, b) in enumerate(zip(left, right)) if a != b]
    if len(differences) != 2:
        return False
    first, second = differences
    return (
        second == first + 1
        and left[first] == right[second]
        and left[second] == right[first]
    )


def _expanded_brand_extension(brand: str, candidate: str) -> bool:
    """Recognize a narrow second-generation compact service suffix."""
    compact_brand = brand.replace("-", "")
    compact_candidate = candidate.replace("-", "")
    if len(compact_brand) < 6 or "-" in candidate:
        return False
    return any(
        compact_candidate == compact_brand + word
        or compact_candidate == word + compact_brand
        for word in _EXPANDED_COMPACT_WORDS
    )


def _swapped_brand_with_service(brand: str, candidate: str) -> tuple[str, str] | None:
    """Match one adjacent swap followed by one known, explicit service token."""
    misspelling, separator, service = candidate.rpartition("-")
    if not separator or not misspelling or service not in _SERVICE_WORDS:
        return None
    if _adjacent_swap(brand, misspelling):
        return misspelling, service
    return None


class DomainMatcher:
    """Find lexical candidates outside the watched registration boundary."""

    def __init__(
        self,
        resolver: DomainResolver,
        *,
        rule_version: str = RULE_VERSION,
        unicode_security: UnicodeSecurityProfile | None = None,
        ascii_rule_version: str | None = None,
        expanded_ascii_rule_version: str | None = None,
        idn_rule_version: str | None = None,
    ) -> None:
        self.resolver = resolver
        # This version identifies the complete execution/query contract and is
        # persisted with jobs.  Candidate versions below preserve old ASCII
        # finding identity while allowing IDN findings to evolve separately.
        self.rule_version = rule_version
        self.unicode_security = unicode_security
        self.ascii_rule_version = ascii_rule_version or rule_version
        self.expanded_ascii_rule_version = (
            expanded_ascii_rule_version or self.ascii_rule_version
        )
        self.idn_rule_version = idn_rule_version or rule_version

    def match(self, asset: Asset, domain: str) -> MatchCandidate | None:
        watched = normalize_for_matching(asset.value)
        candidate = normalize_for_matching(domain)
        if any(label.startswith("xn--") for label in watched.split(".")):
            raise ValidationError("İzlenen adres bu sürümde normal ASCII marka etiketi içermeli.")
        has_idn = any(label.startswith("xn--") for label in candidate.split("."))
        if has_idn:
            if self.unicode_security is None:
                raise ValidationError(
                    "Punycode karşılaştırması için sürümlü Unicode güvenlik profili gerekli."
                )
            # Validate every A-label before registration-boundary or skeleton use.
            self.unicode_security.to_unicode(candidate)
        target = self.resolver.parts(watched)
        observed = self.resolver.parts(candidate)
        if not target.registrable_domain or not observed.registrable_domain:
            return None
        if target.registrable_domain == observed.registrable_domain:
            return None

        reasons: list[str] = []
        expanded_reasons: list[str] = []
        idn_reasons: list[str] = []
        if f".{target.registrable_domain}." in f".{candidate}.":
            reasons.append(
                "İzlenen adres bu adın içinde geçiyor; alan adının kayıt kökü farklı: "
                f"{observed.registrable_domain}."
            )

        brand = target.brand
        candidate_brand = observed.brand
        if brand is None or candidate_brand is None:
            return None
        distinctive = brand not in _COMMON_LABELS
        if distinctive and self.unicode_security is not None:
            if candidate_brand.startswith("xn--"):
                decoded = self.unicode_security.decode_label(candidate_brand)
                if self.unicode_security.confusable(brand, decoded):
                    idn_reasons.append(
                        f"Punycode etiketi '{decoded}', izlenen '{brand}' adıyla "
                        "Unicode benzer-harf iskeletini paylaşıyor."
                    )
            for label in observed.subdomain.split("."):
                if not label.startswith("xn--"):
                    continue
                decoded = self.unicode_security.decode_label(label)
                if self.unicode_security.confusable(brand, decoded):
                    idn_reasons.append(
                        f"Farklı kayıt kökündeki Punycode alt etiketi '{decoded}', izlenen "
                        f"'{brand}' adıyla Unicode benzer-harf iskeletini paylaşıyor."
                    )

        if distinctive and len(brand) >= 4:
            if any(
                label == brand or _brand_extension(brand, label)
                for label in observed.subdomain.split(".") if label
            ):
                reasons.append(
                    f"İzlenen '{brand}' ifadesi, farklı bir alan adının alt bölümünde kullanılıyor."
                )

        if distinctive and candidate_brand == brand:
            reasons.append(
                f"İzlenen '{brand}' adı farklı bir alan adı uzantısıyla kullanılıyor "
                f"({target.suffix} → {observed.suffix})."
            )
        elif distinctive and _brand_extension(brand, candidate_brand):
            reasons.append(
                f"İzlenen '{brand}' adına ek sözcük veya hizmet ifadesi eklenmiş: "
                f"{candidate_brand}."
            )
        elif distinctive and _expanded_brand_extension(brand, candidate_brand):
            expanded_reasons.append(
                f"İzlenen '{brand}' adına bitişik mağaza ifadesi eklenmiş: "
                f"{candidate_brand}."
            )
        elif distinctive and (combined := _swapped_brand_with_service(
            brand, candidate_brand,
        )) is not None:
            misspelling, service = combined
            expanded_reasons.append(
                f"İzlenen '{brand}' adında yan yana iki karakter değiştirilip "
                f"'{service}' hizmet eki kullanılmış: {misspelling}."
            )
        elif distinctive and len(brand) >= 5 and _one_edit_apart(brand, candidate_brand):
            reasons.append(
                f"İzlenen '{brand}' adıyla '{candidate_brand}' arasında tek karakter farkı var."
            )
        elif distinctive and len(brand) >= 5 and _adjacent_swap(brand, candidate_brand):
            reasons.append(
                f"İzlenen '{brand}' adındaki yan yana iki karakterin yeri değiştirilmiş: "
                f"{candidate_brand}."
            )

        reasons.extend(expanded_reasons)
        reasons.extend(idn_reasons)
        if not reasons:
            return None
        return MatchCandidate(
            asset_id=asset.id,
            asset_value=watched,
            domain=candidate,
            rule_version=(
                self.idn_rule_version if idn_reasons else
                self.expanded_ascii_rule_version if expanded_reasons else
                self.ascii_rule_version
            ),
            reasons=tuple(reasons),
        )

