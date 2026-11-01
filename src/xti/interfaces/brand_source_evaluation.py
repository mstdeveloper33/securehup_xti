"""Terminal rendering for the optional brand-OSINT tool gate."""

from xti.domain.brand_source_evaluation import BrandSourceEvaluationReport


def report_lines(report: BrandSourceEvaluationReport) -> list[str]:
    decisions = {
        "selected_for_adapter": "adaptör için seçildi",
        "deferred_duplicate": "yinelenen kaynak olarak ertelendi",
        "deferred_domain_expansion": "domain genişlemesine ertelendi",
        "rejected_overlap": "kapsam çakışması nedeniyle eklenmeyecek",
        "rejected_method": "yöntemi nedeniyle eklenmeyecek",
    }
    lines = [
        "Ücretsiz marka OSINT araçları değerlendirmesi",
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
        lines.append(f"  Amaç: {candidate.purpose}")
        lines.append(f"  Entegrasyon: {candidate.integration_mode}")
        for criterion in candidate.criteria:
            lines.append(
                f"  {'✓' if criterion.passed else '✗'} {criterion.label}: "
                f"{criterion.evidence}"
            )
        for blocker in candidate.blockers:
            lines.append(f"  Engel: {blocker}")
    lines.extend(f"Not: {note}" for note in report.notes)
    return lines
