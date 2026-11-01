"""Safe terminal rendering for explicit OSV advisory operations."""

from xti.domain.osv_advisory import OsvAdvisoryEvidenceSelection, OsvAdvisoryPreview
from xti.interfaces.text import safe_text
from xti.interfaces.vulnerability_exposure_evidence import mutation_lines


def preview_lines(report: OsvAdvisoryPreview) -> list[str]:
    description = report.summary or report.details or "sağlanmadı"
    if len(description) > 1000:
        description = description[:1000] + "…"
    lines = [
        "OSV zafiyet duyurusu önizlemesi",
        f"CVE: {safe_text(report.queried_cve_id)} | OSV kaydı: {safe_text(report.record_id)}",
        f"Yayın: {safe_text(report.published_at or 'bilinmiyor')} | "
        f"Son değişiklik: {safe_text(report.modified_at)} | "
        f"Geri çekilme: {safe_text(report.withdrawn_at or 'yok')}",
        f"Açıklama: {safe_text(description)}",
        f"Etkilenen paket kaydı: {report.total_affected_count} | "
        f"Duyuru başvurusu: {report.total_advisory_reference_count} | "
        f"Diğer başvuru: {report.other_reference_count}",
    ]
    if report.aliases:
        lines.append("Alias: " + ", ".join(safe_text(value) for value in report.aliases))
    if report.upstream:
        lines.append("Upstream: " + ", ".join(safe_text(value) for value in report.upstream))
    lines.append("Etkilenen paket/sürüm bağlamı:")
    if not report.affected:
        lines.append("  OSV kaydında paket/sürüm bağlamı yok.")
    for item in report.affected:
        identity = (
            f"{safe_text(item.ecosystem)} / {safe_text(item.name)}"
            if item.ecosystem is not None and item.name is not None
            else "Git düzeyi kayıt"
        )
        lines.append(
            f"  {identity} | sürüm sayısı: {item.versions_count} | "
            f"aralık: {safe_text(', '.join(item.range_types) or 'yok')}"
        )
        if item.fixed_versions:
            lines.append(
                "    Düzeltilen sürüm sınırı: "
                + ", ".join(safe_text(value) for value in item.fixed_versions)
            )
        if item.last_affected_versions:
            lines.append(
                "    Son etkilenen sürüm: "
                + ", ".join(safe_text(value) for value in item.last_affected_versions)
            )
    if report.affected_truncated:
        lines.append(f"  İlk {len(report.affected)} paket kaydı gösterildi.")
    lines.append("Duyuru başvuruları:")
    if not report.advisory_references:
        lines.append("  OSV kaydında ADVISORY başvurusu yok.")
    else:
        lines.extend(f"  {safe_text(url)}" for url in report.advisory_references)
    if report.advisory_references_truncated:
        lines.append(f"  İlk {len(report.advisory_references)} duyuru gösterildi.")
    lines.extend(["", *report.notes])
    return lines


def evidence_selection_lines(report: OsvAdvisoryEvidenceSelection) -> list[str]:
    lines = [
        "OSV duyuru başvurusu açık seçimle destek kanıtına aktarıldı.",
        f"CVE: {safe_text(report.queried_cve_id)} | "
        f"OSV kaydı: {safe_text(report.record_id)}",
        f"Seçilen başvuru: {safe_text(report.selected_reference)}",
        f"Kaynak yanıt özeti: {safe_text(report.content_sha256)}",
        "",
        *mutation_lines(report.mutation),
        "",
        *report.notes,
    ]
    return lines
