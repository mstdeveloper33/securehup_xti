"""Plain terminal rendering for bounded STIX 2.1 exports."""

from xti.adapters.stix_json import StixArtifact
from xti.application.stix_export import StixExportBuild
from xti.interfaces.text import safe_text


def export_lines(build: StixExportBuild, artifact: StixArtifact) -> list[str]:
    scope = build.indicator_type or "bütün güncel IOC türleri"
    return [
        "STIX 2.1 paketi oluşturuldu.",
        f"Kapsam: {safe_text(scope)}",
        f"IOC nesnesi: {build.indicator_count}",
        f"Dosya: {safe_text(artifact.destination)}",
        f"Boyut: {artifact.byte_count} bayt",
        f"SHA-256: {safe_text(artifact.sha256)}",
        "Yalnız dışa aktarma yapıldı; internet, otomatik engelleme veya tehdit hükmü yok.",
    ]
