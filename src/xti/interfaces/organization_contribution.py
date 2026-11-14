"""Organization provider contribution output keeps each domain and rule separate."""

from xti.domain.organization_contribution import OrganizationContributionReport
from xti.interfaces.source_contribution import source_contribution_lines
from xti.interfaces.text import safe_text


def organization_contribution_lines(report: OrganizationContributionReport) -> list[str]:
    lines = [
        "Kuruluş kaynak katkısı: " + safe_text(report.scope.organization.display_name),
        f"Etkin domain: {report.total_domain_count}; bu sayfada {len(report.domains)}; etkin olmayan bağlantı: {report.scope.excluded_link_count}",
    ]
    for domain in report.domains:
        lines.extend(source_contribution_lines(domain))
    if report.offset + len(report.domains) < report.total_domain_count:
        lines.append(f"Sonraki domain sayfası: --offset {report.offset + len(report.domains)}")
    lines.extend(safe_text(note) for note in report.notes)
    return lines
