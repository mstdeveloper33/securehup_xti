"""Bounded Debian package version validation and comparison.

The comparison follows Debian Policy 5.6.12.  It is kept in the domain layer
so Ubuntu matching does not depend on a host ``dpkg`` executable.
"""

from dataclasses import dataclass
import re

from xti.domain.assets import ValidationError


MAX_DEBIAN_VERSION_LENGTH = 500
_UPSTREAM = re.compile(r"[A-Za-z0-9.+~-]+", re.ASCII)
_REVISION = re.compile(r"[A-Za-z0-9+.~]+", re.ASCII)


@dataclass(frozen=True, slots=True)
class DebianVersion:
    value: str
    epoch: int
    upstream: str
    revision: str


def parse_debian_version(value: str) -> DebianVersion:
    if not isinstance(value, str):
        raise ValidationError("Debian paket sürümü metin olarak gerekli.")
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_DEBIAN_VERSION_LENGTH:
        raise ValidationError("Debian paket sürümü 1–500 karakter arasında olmalı.")
    if not normalized.isascii() or any(character.isspace() for character in normalized):
        raise ValidationError("Debian paket sürümü boşluksuz ASCII biçiminde olmalı.")
    if normalized.count(":") > 1:
        raise ValidationError("Debian paket sürümünde en fazla bir epoch ayıracı olabilir.")
    if ":" in normalized:
        epoch_text, remainder = normalized.split(":", 1)
        if not epoch_text or not epoch_text.isdigit() or not remainder:
            raise ValidationError("Debian epoch değeri işaretsiz tam sayı olmalı.")
        epoch = int(epoch_text)
    else:
        epoch, remainder = 0, normalized

    if "-" in remainder:
        upstream, revision = remainder.rsplit("-", 1)
        if not revision or _REVISION.fullmatch(revision) is None:
            raise ValidationError("Debian revision bölümü geçersiz.")
    else:
        upstream, revision = remainder, "0"
    if not upstream or _UPSTREAM.fullmatch(upstream) is None:
        raise ValidationError("Debian upstream sürüm bölümü geçersiz.")
    return DebianVersion(
        value=normalized, epoch=epoch, upstream=upstream, revision=revision,
    )


def _non_digit_order(character: str | None) -> int:
    if character == "~":
        return -1
    if character is None:
        return 0
    if character.isalpha():
        return ord(character)
    return ord(character) + 256


def _compare_non_digits(left: str, right: str) -> int:
    length = max(len(left), len(right))
    for index in range(length):
        left_value = _non_digit_order(left[index] if index < len(left) else None)
        right_value = _non_digit_order(right[index] if index < len(right) else None)
        if left_value != right_value:
            return -1 if left_value < right_value else 1
    return 0


def _compare_numeric(left: str, right: str) -> int:
    left = left.lstrip("0")
    right = right.lstrip("0")
    if len(left) != len(right):
        return -1 if len(left) < len(right) else 1
    if left == right:
        return 0
    return -1 if left < right else 1


def _compare_part(left: str, right: str) -> int:
    left_index = right_index = 0
    while left_index < len(left) or right_index < len(right):
        left_non_start, right_non_start = left_index, right_index
        while left_index < len(left) and not left[left_index].isdigit():
            left_index += 1
        while right_index < len(right) and not right[right_index].isdigit():
            right_index += 1
        result = _compare_non_digits(
            left[left_non_start:left_index], right[right_non_start:right_index],
        )
        if result:
            return result

        left_digit_start, right_digit_start = left_index, right_index
        while left_index < len(left) and left[left_index].isdigit():
            left_index += 1
        while right_index < len(right) and right[right_index].isdigit():
            right_index += 1
        result = _compare_numeric(
            left[left_digit_start:left_index], right[right_digit_start:right_index],
        )
        if result:
            return result
    return 0


def compare_debian_versions(left: str, right: str) -> int:
    """Return -1, 0 or 1 using Debian's epoch/upstream/revision ordering."""

    left_version = parse_debian_version(left)
    right_version = parse_debian_version(right)
    if left_version.epoch != right_version.epoch:
        return -1 if left_version.epoch < right_version.epoch else 1
    result = _compare_part(left_version.upstream, right_version.upstream)
    if result:
        return result
    return _compare_part(left_version.revision, right_version.revision)
