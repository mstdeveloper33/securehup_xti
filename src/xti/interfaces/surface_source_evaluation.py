"""Terminal rendering for the passive surface-source acceptance gate."""

from xti.domain.surface_source_evaluation import SurfaceSourceEvaluationReport
from xti.interfaces.text import safe_text


_DECISIONS = {
    "active": "aktif ve kabul edildi",
    "deferred_contract": "sözleşme eksikleri nedeniyle ertelendi",
}


def report_lines(report: SurfaceSourceEvaluationReport) -> list[str]:
    lines = [
        "Pasif dış yüzey kaynak kabul kapısı",
        f"Profil: {safe_text(report.profile_version)} | tarih {safe_text(report.evaluated_at)}",
        "Aktif kaynaklar: " + ", ".join(safe_text(item) for item in report.active_identifiers),
        f"Sonraki adım: {safe_text(report.next_step)}",
    ]
    for candidate in report.candidates:
        passed = sum(item.passed for item in candidate.criteria if item.required)
        required = sum(item.required for item in candidate.criteria)
        lines.extend([
            "",
            f"{safe_text(candidate.label)} | {_DECISIONS[candidate.decision]} | "
            f"zorunlu kapı {passed}/{required}",
            f"  Sürüm: {safe_text(candidate.upstream_version)}",
            f"  Amaç: {safe_text(candidate.purpose)}",
            f"  Entegrasyon: {safe_text(candidate.integration_mode)}",
        ])
        for criterion in candidate.criteria:
            lines.append(
                f"  {'✓' if criterion.passed else '✗'} {safe_text(criterion.label)}: "
                f"{safe_text(criterion.evidence)}"
            )
        lines.extend(f"  Engel: {safe_text(item)}" for item in candidate.blockers)
    lines.extend(["", *(f"Not: {safe_text(note)}" for note in report.notes)])
    return lines
