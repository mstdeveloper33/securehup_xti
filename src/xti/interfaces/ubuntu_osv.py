"""Terminal rendering for Canonical Ubuntu OSV previews."""

from xti.domain.osv_advisory import OsvAdvisoryPreview
from xti.interfaces.osv_advisory import preview_lines


def ubuntu_preview_lines(report: OsvAdvisoryPreview) -> list[str]:
    lines = preview_lines(report)
    lines[0] = "Canonical Ubuntu OSV zafiyet önizlemesi"
    return lines
