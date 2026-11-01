"""Terminal rendering for the official producer-source gate."""

from xti.domain.vendor_source_evaluation import VendorSourceEvaluationReport


def report_lines(report: VendorSourceEvaluationReport) -> list[str]:
    decisions = {
        "selected": "seçildi",
        "deferred": "ertelendi",
        "rejected_for_free_profile": "ücretsiz profil için uygun değil",
    }
    lines = [
        "Resmî üretici zafiyet kaynağı değerlendirmesi",
        f"Profil: {report.profile_version} | tarih {report.evaluated_at}",
        f"Seçilen kaynak: {report.selected_identifier}",
        f"Sonraki adım: {report.selected_next_step}",
    ]
    for candidate in report.candidates:
        passed = sum(item.passed for item in candidate.criteria if item.required)
        required = sum(item.required for item in candidate.criteria)
        lines.append(
            f"{candidate.label} | {decisions[candidate.decision]} | "
            f"zorunlu kapı {passed}/{required} | bakım riski {candidate.maintenance_risk}"
        )
        lines.append(
            f"  Erişim: {candidate.access} | biçim: {candidate.data_format} | "
            f"birim: {candidate.granularity}"
        )
        for criterion in candidate.criteria:
            lines.append(
                f"  {'✓' if criterion.passed else '✗'} {criterion.label}: "
                f"{criterion.evidence}"
            )
        for blocker in candidate.blockers:
            lines.append(f"  Engel: {blocker}")
    lines.extend(f"Not: {note}" for note in report.notes)
    return lines
