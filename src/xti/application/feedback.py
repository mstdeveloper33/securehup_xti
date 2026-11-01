"""Turn recorded review activity into bounded operational feedback."""

from xti.domain.feedback import FeedbackError, FeedbackReport
from xti.ports.feedback import FeedbackRepository


_STATUSES = frozenset({"new", "suspicious", "dismissed", "uncertain"})


class FeedbackService:
    def __init__(self, repository: FeedbackRepository) -> None:
        self.repository = repository

    def show(self) -> FeedbackReport:
        snapshot = self.repository.snapshot()
        if set(snapshot.finding_counts) != _STATUSES or any(
            type(value) is not int or value < 0 for value in snapshot.finding_counts.values()
        ):
            raise FeedbackError("Geri bildirim sayıları beklenen biçimde değil.")
        total = sum(snapshot.finding_counts.values())
        unreviewed = snapshot.finding_counts["new"]
        reviewed = total - unreviewed
        if type(snapshot.review_event_count) is not int or snapshot.review_event_count < reviewed:
            raise FeedbackError("İnceleme geçmişi ile geri bildirim sayıları uyuşmuyor.")
        if (
            type(snapshot.revisited_finding_count) is not int
            or not 0 <= snapshot.revisited_finding_count <= reviewed
        ):
            raise FeedbackError("Yeniden incelenen bulgu sayısı geçersiz.")
        if len(snapshot.rules) > 100 or tuple(
            item.rule_version for item in snapshot.rules
        ) != tuple(sorted({item.rule_version for item in snapshot.rules})):
            raise FeedbackError("Kural geri bildirim grupları geçersiz.")
        grouped_counts = dict.fromkeys(_STATUSES, 0)
        for item in snapshot.rules:
            values = (
                item.total_findings, item.reviewed_findings, item.unreviewed_findings,
                item.suspicious, item.dismissed, item.uncertain,
            )
            if (
                not isinstance(item.rule_version, str)
                or item.rule_version != item.rule_version.strip()
                or not item.rule_version or len(item.rule_version) > 512
                or not item.rule_version.isprintable()
                or any(type(value) is not int or value < 0 for value in values)
                or item.reviewed_findings != item.suspicious + item.dismissed + item.uncertain
                or item.total_findings != item.reviewed_findings + item.unreviewed_findings
            ):
                raise FeedbackError("Kural geri bildirim grubu beklenen biçimde değil.")
            grouped_counts["new"] += item.unreviewed_findings
            grouped_counts["suspicious"] += item.suspicious
            grouped_counts["dismissed"] += item.dismissed
            grouped_counts["uncertain"] += item.uncertain
        if grouped_counts != snapshot.finding_counts:
            raise FeedbackError("Kural geri bildirim toplamı bulgu sayısıyla uyuşmuyor.")
        return FeedbackReport(
            total_findings=total,
            reviewed_findings=reviewed,
            unreviewed_findings=unreviewed,
            review_coverage_percent=round(reviewed * 100 / total, 2) if total else 0.0,
            decision_counts={name: snapshot.finding_counts[name] for name in (
                "suspicious", "dismissed", "uncertain",
            )},
            review_event_count=snapshot.review_event_count,
            revisited_finding_count=snapshot.revisited_finding_count,
            rules=snapshot.rules,
            notes=(
                "Bu sayılar kullanıcının son inceleme kararlarını gösterir; doğrulanmış tehdit etiketi değildir.",
                "Kapatılan bir bulgu otomatik yanlış pozitif, şüpheli bir bulgu otomatik phishing sayılmaz.",
                "Kural kalitesi ancak kaynaklı ve ayrıca doğrulanmış etiketlerle ölçülmelidir.",
            ),
        )
