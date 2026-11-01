"""Offline Public Suffix List adapter; no automatic downloads or DNS calls.

Both ICANN and PRIVATE sections are used.  The bundled original list remains
unchanged; an injected Unicode profile converts its U-label rules to canonical
A-labels so internationalized registration boundaries are not flattened.
"""

from functools import lru_cache
import hashlib
from importlib.resources import files

from xti.domain.matching import DomainParts, normalize_for_matching
from xti.domain.idn import UnicodeSecurityProfile


class PublicSuffixResolver:
    """Resolve the longest matching PSL rule, including wildcards and exceptions."""

    def __init__(
        self, rules_text: str | None = None, *,
        unicode_security: UnicodeSecurityProfile | None = None,
    ) -> None:
        if rules_text is None:
            rules_text = files("xti").joinpath("data").joinpath(
                "public_suffix_list.dat"
            ).read_text(encoding="utf-8")
        self.sha256 = hashlib.sha256(rules_text.encode("utf-8")).hexdigest()
        self.version = "unknown"
        self.commit = "unknown"
        exact: set[str] = set()
        wildcard: set[str] = set()
        exceptions: set[str] = set()
        for source_line in rules_text.splitlines():
            line = source_line.strip()
            if line.startswith("// VERSION:"):
                self.version = line.partition(":")[2].strip()
            elif line.startswith("// COMMIT:"):
                self.commit = line.partition(":")[2].strip()
            if not line or line.startswith("//"):
                continue
            rule = line.split()[0].lower()
            if not rule.isascii():
                if unicode_security is None:
                    continue
                marker = "!" if rule.startswith("!") else "*." if rule.startswith("*.") else ""
                value = rule[len(marker):]
                try:
                    rule = marker + unicode_security.to_ascii(value, require_domain=False)
                except ValueError:
                    # One malformed upstream rule must not weaken every ASCII
                    # boundary. Tests and metadata make skipped rules visible.
                    continue
            if rule.startswith("!"):
                exceptions.add(rule[1:])
            elif rule.startswith("*."):
                wildcard.add(rule[2:])
            elif rule != "*":
                exact.add(rule)
        self._exact = frozenset(exact)
        self._wildcard = frozenset(wildcard)
        self._exceptions = frozenset(exceptions)

    def parts(self, domain: str) -> DomainParts:
        return self._parts_normalized(normalize_for_matching(domain))

    @lru_cache(maxsize=8192)
    def _parts_normalized(self, domain: str) -> DomainParts:
        labels = domain.split(".")
        suffix_length = 1  # PSL's implicit '*' rule for unknown suffixes.
        exception_length: int | None = None
        for start in range(len(labels)):
            suffix = ".".join(labels[start:])
            count = len(labels) - start
            if suffix in self._exceptions:
                # The prevailing exception removes its left-most label.
                exception_length = max(exception_length or 0, count - 1)
            if suffix in self._exact:
                suffix_length = max(suffix_length, count)
            if start > 0 and suffix in self._wildcard:
                suffix_length = max(suffix_length, count + 1)
        if exception_length is not None:
            suffix_length = exception_length
        suffix = ".".join(labels[-suffix_length:])
        if len(labels) <= suffix_length:
            return DomainParts(None, None, suffix, "")
        root_start = len(labels) - suffix_length - 1
        return DomainParts(
            registrable_domain=".".join(labels[root_start:]),
            brand=labels[root_start],
            suffix=suffix,
            subdomain=".".join(labels[:root_start]),
        )

