"""Terminal rendering for the pinned social-source coverage gate."""

from xti.domain.brand_source_coverage import BrandSourceCoverageReport


def report_lines(report: BrandSourceCoverageReport) -> list[str]:
    primary, candidate = report.sources
    comparison = report.comparison
    lines = [
        "İkinci ücretsiz sosyal kaynak kapsam kapısı",
        (
            f"Profil: {report.profile_version} | tarih {report.evaluated_at} | "
            f"eşleme {report.matching_rule_version}"
        ),
        (
            f"{primary.label} {primary.version}: {primary.catalog_entries} katalog, "
            f"{primary.eligible_entries} uygun tanım, mevcut platform "
            f"{primary.current_approved_platforms}/10"
        ),
        (
            f"{candidate.label} {candidate.version}: {candidate.catalog_entries} katalog, "
            f"{candidate.eligible_entries} uygun tanım, mevcut platform "
            f"{candidate.current_approved_platforms}/10"
        ),
        (
            f"Ortak aday tanımı: {comparison.shared_candidate_entries} | "
            f"eşleşmeyen aday tanımı: {comparison.candidate_unmatched_entries}"
        ),
        (
            "Aday kaynağa özgü ölçülen kapsam: "
            f"{comparison.candidate_unmatched_distinct_hosts} host / "
            f"{comparison.candidate_unmatched_distinct_registrable_domains} kayıt kökü"
        ),
        (
            f"Mevcut güvenli liste: {comparison.current_shared_platforms} ortak | "
            f"yalnız {primary.label}: "
            f"{', '.join(comparison.current_primary_only) or 'yok'} | "
            f"yalnız {candidate.label}: "
            f"{', '.join(comparison.current_candidate_only) or 'yok'}"
        ),
        "Karar: Sherlock yalnız sınırlı adaptör için kabul edildi.",
        f"Gerekçe: {report.decision_reason}",
        "İlk incelenecek platformlar:",
    ]
    lines.extend(
        f"  {item.platform} ({item.host}) — {item.purpose}"
        for item in report.shortlist
    )
    lines.append(f"Sonraki adım: {report.next_step}")
    lines.extend(f"Sınır: {item}" for item in report.limitations)
    return lines
