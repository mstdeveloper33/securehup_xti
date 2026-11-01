"""Bounded target checks and read-only review views over small ports."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.enrichment import Assessment, BatchCheckResult, EnrichedFinding, ProbeResult, QueueItem
from xti.domain.findings import Finding
from xti.domain.matching import normalize_for_matching
from xti.domain.priority import assess_priority, evidence_freshness, parse_timestamp
from xti.ports.enrichment import AssessmentRepository, TargetProbe
from xti.ports.findings import FindingRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_id(finding_id: str) -> None:
    if not isinstance(finding_id, str) or not finding_id or len(finding_id) > 64 or not finding_id.isprintable():
        raise ValidationError("Geçerli bir bulgu kimliği gerekli.")


def _validate_limit(limit: int, maximum: int) -> None:
    if type(limit) is not int or not 1 <= limit <= maximum:
        raise ValidationError(f"Bulgu sınırı 1–{maximum} arasında olmalı.")


_EARLIEST = datetime.min.replace(tzinfo=timezone.utc)


def _finding_order(finding: Finding) -> tuple[datetime, str]:
    return parse_timestamp(finding.created_at) or _EARLIEST, finding.id


class FindingEnrichmentService:
    def __init__(
        self, findings: FindingRepository, assessments: AssessmentRepository,
        probe: TargetProbe, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.findings = findings
        self.assessments = assessments
        self.probe = probe
        self.clock = clock or _utc_now

    def _probe(self, finding: Finding, progress: Callable[[str], None] | None = None) -> ProbeResult:
        domain = normalize_for_matching(finding.domain)
        if progress:
            progress(f"Hedef kontrol ediliyor: {domain}")
        result = self.probe.check(domain)
        if not isinstance(result, ProbeResult) or result.domain != domain:
            raise ValidationError("Hedef kontrolünün sonucu istenen alan adıyla eşleşmiyor; kaydedilmedi.")
        return result

    def check(self, finding_id: str) -> Assessment:
        """Explicit refresh always performs a new check, including closed findings."""
        _validate_id(finding_id)
        finding = self.findings.get_finding(finding_id).finding
        return self.assessments.append(finding.id, self._probe(finding))

    def check_pending(
        self, limit: int = 10, domains: Sequence[str] | None = None,
        *, progress: Callable[[str], None] | None = None,
    ) -> BatchCheckResult:
        """Check eligible findings; a shared domain is contacted only once per batch.

        The limit counts findings. Selected domains are exact watched asset names,
        not candidate names or suffix expansions. Completed records remain saved
        if a later probe or persistence operation fails.
        """
        _validate_limit(limit, 20)
        selected = None
        if domains is not None:
            if not isinstance(domains, Sequence) or isinstance(domains, (str, bytes)) or not 1 <= len(domains) <= 5:
                raise ValidationError("Kontrol için 1–5 izlenen alan adı seçilmeli.")
            selected = set()
            for domain in domains:
                normalized = normalize_for_matching(domain)
                if any(label.startswith("xn--") for label in normalized.split(".")):
                    raise ValidationError(
                        "Kontrol filtresi normal ASCII izlenen adreslerden oluşmalı."
                    )
                selected.add(normalized)
        now = self.clock()
        latest = self.assessments.latest_by_finding()
        pending: list[Finding] = []
        skipped_fresh = 0
        for finding in self.findings.list_findings():
            if finding.status == "dismissed" or (selected is not None and finding.asset_value not in selected):
                continue
            if evidence_freshness(latest.get(finding.id), now=now) == "current":
                skipped_fresh += 1
            else:
                pending.append(finding)

        def pending_order(finding: Finding) -> tuple[int, datetime, datetime, str]:
            assessment = latest.get(finding.id)
            checked_at = parse_timestamp(assessment.result.finished_at) if assessment else None
            # Unchecked and unusable times precede checks with a known age.
            group = 0 if assessment is None or evidence_freshness(assessment, now=now) == "clock_error" else 1
            return group, (checked_at or _EARLIEST) if group else _EARLIEST, *_finding_order(finding)

        pending.sort(key=pending_order)
        saved: list[Assessment] = []
        results: dict[str, ProbeResult] = {}
        for finding in pending[:limit]:
            result = results.get(finding.domain)
            if result is None:
                result = self._probe(finding, progress)
                results[finding.domain] = result
            saved.append(self.assessments.append(finding.id, result))
        return BatchCheckResult(tuple(saved), skipped_fresh, max(0, len(pending) - limit))


class ReviewQueueService:
    def __init__(
        self, findings: FindingRepository, assessments: AssessmentRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.findings = findings
        self.assessments = assessments
        self.clock = clock or _utc_now

    def list(self, include_dismissed: bool = False, limit: int = 100) -> tuple[QueueItem, ...]:
        _validate_limit(limit, 500)
        if type(include_dismissed) is not bool:
            raise ValidationError("Kapatılan bulguları gösterme seçimi doğru veya yanlış olmalı.")
        now = self.clock()
        latest = self.assessments.latest_by_finding()
        items = []
        for finding in self.findings.list_findings():
            if finding.status == "dismissed" and not include_dismissed:
                continue
            assessment = latest.get(finding.id)
            items.append(QueueItem(finding, assessment, assess_priority(finding, assessment, now=now)))
        priorities = {"soon": 0, "review": 1, "archived": 2}
        items.sort(key=lambda item: (priorities[item.priority.level], *_finding_order(item.finding)))
        return tuple(items[:limit])

    def show(self, finding_id: str) -> EnrichedFinding:
        _validate_id(finding_id)
        return self.assessments.details(finding_id)
