"""Human-readable review feedback with explicit interpretation limits."""

from xti.domain.feedback import FeedbackReport
from xti.interfaces.text import safe_text


def feedback_lines(report: FeedbackReport) -> list[str]:
    decisions = report.decision_counts
    lines = [
        "İnceleme geri bildirimi — yalnız kayıtlı kullanıcı kararları",
        f"Toplam aday: {report.total_findings}; incelenen: {report.reviewed_findings}; "
        f"bekleyen: {report.unreviewed_findings}.",
        f"İnceleme kapsamı: %{report.review_coverage_percent:.2f}.",
        f"Son kararlar: {decisions['suspicious']} şüpheli, {decisions['dismissed']} kapatılmış, "
        f"{decisions['uncertain']} kararsız.",
        f"Karar kaydı: {report.review_event_count}; birden çok kez incelenen bulgu: "
        f"{report.revisited_finding_count}.",
    ]
    if report.rules:
        lines.extend(["", "Kural sürümüne göre:"])
    for item in report.rules:
        lines.extend([
            f"  {safe_text(item.rule_version)}",
            f"    Toplam {item.total_findings}; incelenen {item.reviewed_findings}; "
            f"bekleyen {item.unreviewed_findings}; şüpheli {item.suspicious}; "
            f"kapatılmış {item.dismissed}; kararsız {item.uncertain}.",
        ])
    if not report.total_findings:
        lines.extend(["", "Henüz aday bulgu yok; internet araması için: ./xti scan example.com"])
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
