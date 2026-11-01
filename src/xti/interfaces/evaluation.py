"""Plain-language terminal rendering for matching-quality measurements."""

from xti.domain.evaluation import EvaluationReport
from xti.interfaces.text import safe_text


def evaluation_lines(report: EvaluationReport) -> list[str]:
    lines = [
        f"Eşleştirme değerlendirmesi: {report.total} sürümlü sentetik örnek.",
        f"İncelemeye gönderilmesi beklenen: {report.expected_review}; "
        f"göz ardı edilmesi beklenen: {report.expected_ignore}.",
        f"Doğru yakalanan: {report.true_positive}; kaçırılan: {report.false_negative}.",
        f"Doğru elenen: {report.true_negative}; gereksiz alarm: {report.false_positive}.",
        f"İncelemeye gönderilenlerin isabeti: %{report.precision_percent:.2f}.",
        f"Beklenen inceleme örneklerini yakalama: %{report.recall_percent:.2f}.",
        f"Göz ardı edilmesi beklenenlerde gereksiz alarm oranı: "
        f"%{report.false_positive_rate_percent:.2f}.",
        f"Toplam doğru davranış: %{report.accuracy_percent:.2f}.",
        f"Bilinen kalite açığı: {report.known_gap_count}; "
        f"kayıtlı başlangıç davranışından değişim: {report.baseline_change_count}.",
    ]
    if report.quality_gaps:
        lines.append("İncelenecek kalite açıkları:")
    labels = {"review": "incelemeye gönder", "ignore": "göz ardı et"}
    for gap in report.quality_gaps:
        lines.append(
            f"  {safe_text(gap.case_id)} | Beklenen: {labels[gap.expected]} | "
            f"Sonuç: {labels[gap.predicted]} | {safe_text(gap.asset)} → "
            f"{safe_text(gap.input_domain)}"
        )
        lines.append(f"    {safe_text(gap.note)}")
    if report.baseline_changes:
        lines.append("Dikkat: Kural sonucu kayıtlı başlangıç davranışından ayrılan örnekler var.")
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
