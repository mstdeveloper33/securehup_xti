"""Terminal rendering for the additional ransomware-source gate."""

from xti.domain.ransomware_source_evaluation import RansomwareSourceEvaluationReport
from xti.interfaces.text import safe_text


def report_lines(report: RansomwareSourceEvaluationReport) -> list[str]:
    decisions = {
        "selected": "seçildi",
        "deferred": "ertelendi",
        "rejected_for_current_feed": "güncel akış için uygun değil",
    }
    maintenance_risks = {"low": "düşük", "medium": "orta", "high": "yüksek"}
    lines = [
        "İkinci açık ransomware kaynağı değerlendirmesi",
        f"Profil: {safe_text(report.profile_version)} | tarih {report.evaluated_at}",
        f"Seçilen kaynak: {safe_text(report.selected_identifier)}",
        f"Uygulama kararı: {safe_text(report.selected_next_step)}",
    ]
    for candidate in report.candidates:
        passed = sum(item.passed for item in candidate.criteria if item.required)
        required = sum(item.required for item in candidate.criteria)
        lines.append(
            f"{safe_text(candidate.label)} | {decisions[candidate.decision]} | "
            f"zorunlu kapı {passed}/{required} | bakım riski "
            f"{maintenance_risks.get(candidate.maintenance_risk, safe_text(candidate.maintenance_risk))}"
        )
        lines.append(
            f"  Erişim: {safe_text(candidate.access)} | biçim: "
            f"{safe_text(candidate.data_format)}"
        )
        lines.append(f"  Toplama: {safe_text(candidate.collection)}")
        for criterion in candidate.criteria:
            lines.append(
                f"  {'✓' if criterion.passed else '✗'} {safe_text(criterion.label)}: "
                f"{safe_text(criterion.evidence)}"
            )
        for blocker in candidate.blockers:
            lines.append(f"  Engel: {safe_text(blocker)}")
    lines.extend(f"Not: {safe_text(note)}" for note in report.notes)
    return lines
