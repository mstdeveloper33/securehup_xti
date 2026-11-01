"""Terminal rendering for a bounded social username preview."""

from xti.domain.brand_username import BrandUsernamePreview
from xti.interfaces.text import safe_text


def preview_lines(report: BrandUsernamePreview) -> list[str]:
    lines = [
        "Sosyal kullanıcı adı önizlemesi",
        f"Kullanıcı adı: {safe_text(report.username)}",
        (
            f"Kaynak: {safe_text(report.source)} {safe_text(report.source_version)} | "
            f"profil {safe_text(report.integration_profile)}"
        ),
        f"Kontrol zamanı: {safe_text(report.checked_at)}",
        "Seçilen platformlar: " + ", ".join(
            safe_text(item) for item in report.requested_platforms
        ),
        f"Bulunan doğrulanmamış profil: {len(report.matches)}",
    ]
    for match in report.matches:
        lines.append(
            f"  {safe_text(match.platform)} | bulundu, doğrulanmadı | "
            f"{safe_text(match.profile_url)}"
        )
    if not report.matches:
        lines.append("  Bulunan profil yok.")
    lines.append(
        f"Raporlanmayan platform: {len(report.unreported_platforms)}"
    )
    if report.unreported_platforms:
        lines.append(
            "  " + ", ".join(safe_text(item) for item in report.unreported_platforms)
        )
    lines.extend(f"Not: {safe_text(note)}" for note in report.notes)
    return lines
