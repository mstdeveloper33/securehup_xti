"""Pure Unicode/IDNA security rules built from an injected reference profile.

The canonical DNS value is always an ASCII A-label.  Unicode is used only for
validation, comparison and a human-readable explanation; a confusable match is
an investigation candidate, never proof of abuse.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import re
import unicodedata

from xti.domain.assets import ValidationError, normalize_domain


UNICODE_VERSION = "18.0.0"
MAX_IDN_QUERY_VARIANTS = 4
_ASCII_SKELETON = re.compile(r"[a-z0-9]", re.ASCII)
_A_LABEL = re.compile(r"xn--[a-z0-9-]{1,59}", re.ASCII)
_RTL_CLASSES = frozenset({"R", "AL", "AN"})


@dataclass(frozen=True, slots=True)
class IdnaRange:
    start: int
    end: int
    status: str
    mapping: str


class UnicodeSecurityProfile:
    """Pinned UTS #39 skeletons and conservative UTS #46 nontransitional IDNA.

    This first profile intentionally declines right-to-left labels and joining
    controls.  It covers the Latin/Greek/Cyrillic homographs used by the query
    expansion without pretending to implement every IDNA context rule.
    """

    def __init__(
        self,
        confusables: dict[int, str],
        idna_ranges: tuple[IdnaRange, ...],
        *,
        version: str = UNICODE_VERSION,
    ) -> None:
        if not confusables or not idna_ranges:
            raise ValueError("Unicode güvenlik profili boş olamaz.")
        self.version = version
        self._confusables = confusables
        self._ranges = idna_ranges
        self._starts = tuple(item.start for item in idna_ranges)
        self._reverse = self._build_reverse_candidates()

    def _entry(self, character: str) -> IdnaRange | None:
        codepoint = ord(character)
        index = bisect_right(self._starts, codepoint) - 1
        if index < 0:
            return None
        item = self._ranges[index]
        return item if codepoint <= item.end else None

    def _map(self, value: str) -> str:
        mapped: list[str] = []
        for character in value:
            item = self._entry(character)
            if item is None:
                raise ValidationError("Alan adı Unicode profilinde tanımsız bir karakter içeriyor.")
            if item.status == "valid" or item.status == "deviation":
                mapped.append(character)
            elif item.status == "mapped":
                mapped.append(item.mapping)
            elif item.status == "ignored":
                continue
            else:
                # STD3 rules are deliberately enabled.  Therefore both
                # disallowed_STD3_* statuses are rejected rather than mapped.
                raise ValidationError("Alan adı IDNA güvenlik profilinde izin verilmeyen karakter içeriyor.")
        return unicodedata.normalize("NFC", "".join(mapped))

    def _validate_u_label(self, label: str) -> None:
        if not label or unicodedata.normalize("NFC", label) != label:
            raise ValidationError("Uluslararası alan adı NFC biçiminde olmalı.")
        if label.startswith("-") or label.endswith("-") or (
            len(label) >= 4 and label[2:4] == "--"
        ):
            raise ValidationError("Uluslararası alan adı geçersiz tire kullanımı içeriyor.")
        if unicodedata.category(label[0]).startswith("M"):
            raise ValidationError("Uluslararası alan adı bir birleştirme işaretiyle başlayamaz.")
        if any(character in {"\u200c", "\u200d"} for character in label):
            raise ValidationError("Bu sürüm birleştirme denetimli IDNA etiketlerini işlemiyor.")
        if any(unicodedata.bidirectional(character) in _RTL_CLASSES for character in label):
            raise ValidationError("Bu sürüm sağdan sola IDNA etiketlerini işlemiyor.")
        for character in label:
            item = self._entry(character)
            if item is None or item.status not in {"valid", "deviation"}:
                raise ValidationError("Uluslararası alan adı geçersiz bir IDNA karakteri içeriyor.")
            if unicodedata.category(character) == "Cn":
                raise ValidationError("Python çalışma ortamı bu Unicode karakterini tanımıyor.")

    def _decode_a_label(self, label: str) -> str:
        if _A_LABEL.fullmatch(label) is None:
            raise ValidationError("Geçersiz Punycode alan adı etiketi.")
        try:
            decoded = label[4:].encode("ascii").decode("punycode")
        except (UnicodeError, ValueError) as exc:
            raise ValidationError("Geçersiz Punycode alan adı etiketi.") from exc
        if decoded.isascii():
            raise ValidationError("Punycode etiketi en az bir Unicode karakter içermeli.")
        self._validate_u_label(decoded)
        try:
            canonical = "xn--" + decoded.encode("punycode").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValidationError("Punycode etiketi yeniden kodlanamadı.") from exc
        if canonical != label or len(canonical.encode("ascii")) > 63:
            raise ValidationError("Punycode etiketi kanonik veya geçerli uzunlukta değil.")
        return decoded

    def to_unicode(self, ascii_name: str) -> str:
        """Validate an ASCII DNS name and decode canonical A-labels for analysis."""
        normalized = normalize_domain(ascii_name)
        labels = []
        for label in normalized.split("."):
            labels.append(self._decode_a_label(label) if label.startswith("xn--") else label)
        return ".".join(labels)

    def decode_label(self, ascii_label: str) -> str:
        """Decode one canonical A-label after applying all profile checks."""
        label = ascii_label.lower()
        return self._decode_a_label(label) if label.startswith("xn--") else label

    def to_ascii(self, value: str, *, require_domain: bool = True) -> str:
        """Apply conservative UTS #46 mapping and return canonical DNS A-labels."""
        if not isinstance(value, str):
            raise ValidationError("Alan adı metin olarak verilmelidir.")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValidationError("Alan adı kontrol karakteri içeremez.")
        stripped = value.strip()
        if stripped.endswith("."):
            stripped = stripped[:-1]
        if not stripped:
            raise ValidationError("Alan adı boş olamaz.")

        if stripped.isascii():
            lowered = stripped.lower()
            # normalize_domain supplies the ordinary DNS syntax/IP/TLD checks.
            if require_domain:
                normalized = normalize_domain(lowered)
            else:
                if "." in lowered:
                    normalized = normalize_domain(lowered)
                elif not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", lowered):
                    raise ValidationError("Geçerli bir alan adı etiketi gerekli.")
                else:
                    normalized = lowered
            for label in normalized.split("."):
                if label.startswith("xn--"):
                    self._decode_a_label(label)
            return normalized

        mapped = self._map(stripped)
        labels = mapped.split(".")
        if require_domain and len(labels) < 2:
            raise ValidationError("Geçerli bir tam alan adı gerekli.")
        if any(not label for label in labels):
            raise ValidationError("Alan adı boş bir etiket içeremez.")
        encoded: list[str] = []
        for label in labels:
            self._validate_u_label(label)
            if label.isascii():
                ascii_label = label
            else:
                try:
                    ascii_label = "xn--" + label.encode("punycode").decode("ascii").lower()
                except UnicodeError as exc:
                    raise ValidationError("Uluslararası alan adı Punycode biçimine çevrilemedi.") from exc
            if len(ascii_label.encode("ascii")) > 63:
                raise ValidationError("Punycode alan adı etiketi 63 bayt sınırını aşıyor.")
            encoded.append(ascii_label)
        result = ".".join(encoded)
        if require_domain:
            normalize_domain(result)
        elif len(result) > 253:
            raise ValidationError("Alan adı 253 karakter sınırını aşıyor.")
        return result

    def skeleton(self, value: str) -> str:
        """Return the UTS #39 internal skeleton; never use this as display text."""
        source = unicodedata.normalize("NFD", value)
        mapped = "".join(self._confusables.get(ord(character), character) for character in source)
        return unicodedata.normalize("NFD", mapped)

    def confusable(self, watched_ascii: str, candidate_unicode: str) -> bool:
        return watched_ascii != candidate_unicode and (
            self.skeleton(watched_ascii) == self.skeleton(candidate_unicode)
        )

    def _build_reverse_candidates(self) -> dict[str, dict[str, tuple[str, ...]]]:
        reverse: dict[str, dict[str, list[str]]] = {}
        for codepoint in self._confusables:
            character = chr(codepoint)
            name = unicodedata.name(character, "")
            script = "CYRILLIC" if "CYRILLIC" in name else "GREEK" if "GREEK" in name else None
            if script is None or not unicodedata.category(character).startswith("L"):
                continue
            skeleton = self.skeleton(character)
            if _ASCII_SKELETON.fullmatch(skeleton) is None:
                continue
            item = self._entry(character)
            if item is None or item.status not in {"valid", "deviation"}:
                continue
            reverse.setdefault(skeleton, {}).setdefault(script, []).append(character)

        preferred = {
            "CYRILLIC": "аеіјорсхуѕԁԍһӏ",
            "GREEK": "αειορτυχκ",
        }
        result: dict[str, dict[str, tuple[str, ...]]] = {}
        for ascii_character, scripts in reverse.items():
            result[ascii_character] = {}
            for script, characters in scripts.items():
                order = {character: index for index, character in enumerate(preferred[script])}
                unique = sorted(set(characters), key=lambda item: (order.get(item, 10_000), ord(item)))
                result[ascii_character][script] = tuple(unique)
        return result

    def search_variants(self, ascii_label: str, *, limit: int = MAX_IDN_QUERY_VARIANTS) -> tuple[str, ...]:
        """Create a small deterministic search set; this is coverage, not enumeration."""
        if not 1 <= limit <= MAX_IDN_QUERY_VARIANTS:
            raise ValueError("IDN sorgu varyantı sınırı geçersiz.")
        if not ascii_label.isascii() or re.fullmatch(r"[a-z0-9-]+", ascii_label) is None:
            raise ValidationError("IDN sorgu üretimi için ASCII marka etiketi gerekli.")

        unicode_variants: list[str] = []
        for script in ("CYRILLIC", "GREEK"):
            replaced = []
            count = 0
            for character in ascii_label:
                options = self._reverse.get(character, {}).get(script, ())
                if options:
                    replaced.append(options[0])
                    count += 1
                else:
                    replaced.append(character)
            if count:
                unicode_variants.append("".join(replaced))

        for index, character in enumerate(ascii_label):
            for script in ("CYRILLIC", "GREEK"):
                options = self._reverse.get(character, {}).get(script, ())
                if options:
                    unicode_variants.append(ascii_label[:index] + options[0] + ascii_label[index + 1:])

        result: list[str] = []
        for variant in unicode_variants:
            try:
                encoded = self.to_ascii(variant, require_domain=False)
            except ValidationError:
                continue
            if not encoded.startswith("xn--") or encoded in result:
                continue
            result.append(encoded)
            if len(result) == limit:
                break
        return tuple(result)
