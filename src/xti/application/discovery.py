"""Search an external source and feed results into the existing finding workflow."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.discovery import QueryResult, ScanResult
from xti.domain.findings import ImportDocument, ImportSummary
from xti.domain.idn import UnicodeSecurityProfile
from xti.domain.matching import DomainMatcher, DomainResolver, normalize_for_matching
from xti.ports.assets import AssetRepository
from xti.ports.allowlist import AllowlistRepository
from xti.ports.discovery import DomainSource, SourceError
from xti.ports.findings import FindingRepository


MAX_TARGETS = 5
MAX_DOCUMENTS = 10_000
MAX_COMPARISONS = 250_000
MAX_TYPO_VARIANTS = 6


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_query_plan(
    domains: Sequence[str], resolver: DomainResolver, *, typos: bool = False,
    unicode_security: UnicodeSecurityProfile | None = None,
) -> tuple[str, ...]:
    """Bounded name searches; provider indexing does not ensure exhaustive recall."""
    domains = tuple(dict.fromkeys(normalize_for_matching(value) for value in domains))
    if not domains:
        raise ValidationError("İzlenecek bir adres gerekli. Örnek: ./xti scan markam.com")
    if len(domains) > MAX_TARGETS:
        raise ValidationError("Bir çalıştırmada en fazla 5 adres aranabilir.")
    patterns: dict[str, None] = {}
    for domain in domains:
        if any(label.startswith("xn--") for label in domain.split(".")):
            raise ValidationError(
                "İzlenen adres bu sürümde normal ASCII marka etiketi içermeli; "
                "Punycode yalnız bulunan adaylarda analiz edilir."
            )
        parts = resolver.parts(domain)
        if not parts.registrable_domain or not parts.brand:
            raise ValidationError("Yalnız uzantı yerine tam bir alan adı gir: markam.com")
        brand = parts.brand
        if len(brand) < 4:
            raise ValidationError(
                "Bu kaynakta çok geniş aramaları önlemek için adın uzantıdan önceki "
                "bölümü en az 4 karakter olmalı. Kısa ad araması henüz desteklenmiyor."
            )
        patterns[f"%{brand}%"] = None
        patterns[f"{brand}%"] = None
        if typos and unicode_security is not None:
            # A-labels do not visibly contain the watched brand.  Query a very
            # small, deterministic set rather than attempting an unbounded
            # Unicode permutation search.
            for variant in unicode_security.search_variants(brand):
                patterns[f"%{variant}%"] = None
                patterns[f"{variant}%"] = None
        if typos and len(brand) >= 5:
            variants: set[str] = set()
            for index in range(len(brand) - 1):
                variant = brand[:index] + brand[index + 1] + brand[index] + brand[index + 2:]
                if variant == brand or variant in variants or variant.startswith("-") or variant.endswith("-"):
                    continue
                variants.add(variant)
                patterns[f"{variant}%"] = None
                if len(variants) == MAX_TYPO_VARIANTS:
                    break
    return tuple(patterns)


def build_prefix_query_plan(
    domains: Sequence[str], resolver: DomainResolver, *, typos: bool = False,
    unicode_security: UnicodeSecurityProfile | None = None,
) -> tuple[str, ...]:
    """Use prefix terms only for providers whose anonymous search excludes infix queries."""
    return tuple(dict.fromkeys(
        pattern[:-1] + "*"
        for pattern in build_query_plan(
            domains, resolver, typos=typos, unicode_security=unicode_security,
        )
        if not pattern.startswith("%")
    ))


class DiscoveryService:
    def __init__(
        self, assets: AssetRepository, findings: FindingRepository,
        matcher: DomainMatcher, source: DomainSource,
        *, query_planner: Callable = build_query_plan,
        allowlist: AllowlistRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.assets = assets
        self.findings = findings
        self.matcher = matcher
        self.source = source
        self.query_planner = query_planner
        self.allowlist = allowlist
        self.clock = clock or _utc_now

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Arama zamanı saat dilimi bilgili olmalı.")
        return value.astimezone(timezone.utc).isoformat()

    def scan(
        self, domains: Sequence[str] | None = None, *, typos: bool = False,
        progress: Callable[[str], None] | None = None,
        on_query: Callable[[QueryResult], None] | None = None,
    ) -> ScanResult:
        started_at = self._now()
        selected, patterns, targets, known_roots = self._prepare(domains, typos=typos)

        documents: dict[str, ImportDocument] = {}
        query_results: list[QueryResult] = []
        for number, pattern in enumerate(patterns, start=1):
            if progress:
                progress(f"İnternette aranıyor ({number}/{len(patterns)}): {pattern}")
            url = self.source.search_url(pattern)
            try:
                batch = self.source.search(pattern)
            except SourceError as exc:
                query = QueryResult(pattern, url, "failed", 0, 0, str(exc), ())
                query_results.append(query)
                if on_query:
                    on_query(query)
                if progress:
                    progress(f"Kaynak bu sorguya cevap veremedi: {exc}")
                continue
            query = QueryResult(
                pattern, url, "partial" if batch.warnings or batch.skipped_names else "complete",
                batch.record_count, batch.skipped_names, None, batch.warnings,
                coverage_notes=batch.coverage_notes,
            )
            query_results.append(query)
            if on_query:
                on_query(query)
            for document in batch.documents:
                prior = documents.get(document.sha256)
                if prior is not None and prior != document:
                    raise ValidationError("Kaynak aynı gözlem için çelişen kayıt döndürdü.")
                documents[document.sha256] = document
                if len(documents) > MAX_DOCUMENTS:
                    raise ValidationError(
                        "Arama 10.000 kaynak kaydı sınırını aştı; gözlemler kaydedilmedi. "
                        "Daha az izlenen adresle yeniden dene."
                    )
            if progress:
                progress(
                    f"Kaynak yanıtı alındı: {batch.record_count} kaynak kaydı; "
                    f"{batch.skipped_names} desteklenmeyen ad."
                )
        domains_found = {record.domain for doc in documents.values() for record in doc.records}
        if len(domains_found) * len(targets) > MAX_COMPARISONS:
            raise ValidationError("Arama karşılaştırma sınırını aştı; gözlemler kaydedilmedi.")

        # Validate and calculate everything before the first observation write.
        prepared = []
        candidate_keys: set[tuple[str, str, str]] = set()
        candidate_domains: set[str] = set()
        suppressed_keys: set[tuple[str, str]] = set()
        policy_at = self._now()
        active_pairs = self.allowlist.active_pairs(
            tuple(asset.id for asset in targets), policy_at,
        ) if self.allowlist is not None else frozenset()
        for document in documents.values():
            candidates = []
            for domain in sorted({item.domain for item in document.records}):
                parts = self.matcher.resolver.parts(normalize_for_matching(domain))
                if parts.registrable_domain in known_roots:
                    continue
                for asset in targets:
                    candidate = self.matcher.match(asset, domain)
                    if candidate is not None:
                        pair = (candidate.asset_id, candidate.domain)
                        if pair in active_pairs:
                            suppressed_keys.add(pair)
                            continue
                        candidates.append(candidate)
                        candidate_domains.add(domain)
                        candidate_keys.add((candidate.asset_id, candidate.domain, candidate.rule_version))
            prepared.append((document, candidates))
        if progress:
            message = f"{len(domains_found)} farklı adres incelendi"
            if suppressed_keys:
                message += f"; {len(suppressed_keys)} tam adres istisnası uygulandı"
            progress(message + "; sonuçlar kaydediliyor.")
        records = created = existing = new_findings = enforced_suppressed = 0
        for document, candidates in prepared:
            # Each observation is atomic. Interrupted runs can be safely repeated.
            summary = self.findings.save_import(document, candidates)
            records += summary.total_records
            created += summary.observations_created
            existing += summary.observations_existing
            new_findings += summary.findings_created
            enforced_suppressed += summary.findings_suppressed
        successes = sum(result.status != "failed" for result in query_results)
        incomplete = any(result.warnings or result.skipped_names for result in query_results)
        status = "failed" if successes == 0 else (
            "partial" if successes < len(query_results) or incomplete else "complete"
        )
        return ScanResult(
            selected, started_at, self._now(), status,
            tuple(query_results),
            ImportSummary(
                records, created, existing, new_findings,
                max(0, len(candidate_keys) - new_findings - enforced_suppressed),
                len(suppressed_keys) + enforced_suppressed,
            ),
            tuple(sorted(candidate_domains)),
        )

    def validate_targets(
        self, domains: Sequence[str] | None = None, *, typos: bool = False,
    ) -> tuple[str, ...]:
        """Validate and snapshot the chosen registered targets without contacting a source."""
        return self._prepare(domains, typos=typos)[0]

    def _prepare(self, domains: Sequence[str] | None, *, typos: bool):
        watched = self.assets.list()
        by_domain = {asset.value: asset for asset in watched}
        selected = tuple(dict.fromkeys(
            normalize_for_matching(value) for value in domains
        )) if domains is not None else tuple(by_domain)
        patterns = self.query_planner(
            selected, self.matcher.resolver, typos=typos,
            unicode_security=self.matcher.unicode_security,
        )
        if any(domain not in by_domain for domain in selected):
            raise ValidationError("Önce izlenecek adresi kaydet: ./xti assets add markam.com")
        targets = [by_domain[domain] for domain in selected]
        # Every registered root is owned for the purposes of the external-lookalike rule.
        known_roots = set()
        for asset in watched:
            parts = self.matcher.resolver.parts(normalize_for_matching(asset.value))
            if not parts.registrable_domain:
                raise ValidationError("Kayıtlı adresler arasında yalnız uzantı içeren bir kayıt var.")
            known_roots.add(parts.registrable_domain)
        return selected, patterns, targets, known_roots
