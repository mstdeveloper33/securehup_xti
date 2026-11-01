"""Build a portable, versioned report from one stored finding snapshot."""

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable

from xti.application.findings import FindingService
from xti.domain.priority import assess_priority
from xti.ports.enrichment import AssessmentRepository


class FindingReportService:
    def __init__(
        self, assessments: AssessmentRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.assessments = assessments
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def build(self, finding_id: str) -> dict:
        FindingService._validate_id(finding_id)
        snapshot = self.assessments.details(finding_id)
        now = self.clock()
        latest = snapshot.assessments[-1] if snapshot.assessments else None
        return {
            "format": "xti-finding-report",
            "format_version": 1,
            "generated_at": now.isoformat(),
            "finding": asdict(snapshot.details.finding),
            "observations": [asdict(item) for item in snapshot.details.observations],
            "reviews": [asdict(item) for item in snapshot.details.reviews],
            "assessments": [asdict(item) for item in snapshot.assessments],
            "priority": asdict(assess_priority(snapshot.details.finding, latest, now=now)),
            "limitations": [
                "Bu rapor bir inceleme adayını belgeler; doğrulanmış phishing kararı değildir.",
                "Arşiv kaynakları bütün interneti kapsamaz; kaynak zamanı ilk görülme tarihi değildir.",
                "Hedef kontrolü tek IP üzerinde HTTPS başlıklarıyla sınırlıdır; içerik incelenmez.",
                "Yanıt gelmemesi güvenli olduğunu, yanıt gelmesi zararlı olduğunu göstermez.",
                "Öncelik raporun üretildiği zamana aittir; bir risk veya olasılık puanı değildir.",
            ],
        }
