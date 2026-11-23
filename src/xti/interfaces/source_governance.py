"""Compact terminal rendering for the source-governance contract."""

from __future__ import annotations

from xti.interfaces.text import safe_text


_STATES = {
    "active": "Aktif",
    "conditional": "Gereksinim bekliyor",
    "disabled": "Kapalı",
}
_COSTS = {
    "free": "Ücretsiz",
    "free_tier": "Ücretsiz katman",
    "local": "Yerel kaynak",
    "mixed": "Ücretsiz/ücretli",
    "paid": "Ücretli",
}
_RIGHTS = {
    "allowed_with_terms": "Koşullara bağlı izinli",
    "attribution_required": "Kaynak gösterimi gerekli",
    "contract_required": "Sözleşme kararı gerekli",
    "disabled": "Kapalı",
    "metadata_only": "Yalnız metadata",
    "not_applicable": "Uygulanmaz",
    "not_enabled": "Açık değil",
    "review_required": "İnceleme gerekli",
}


def _join(values) -> str:
    return safe_text(", ".join(values) if values else "Yok")


def catalog_lines(report: dict) -> list[str]:
    lines = [
        "Kaynak ve feed kataloğu",
        f"Toplam manifest: {report['catalog_count']} | Filtre sonucu: {report['filtered_count']} | "
        f"Gösterilen: {len(report['sources'])}",
        f"Katalog özeti: {safe_text(report['catalog_sha256'])}",
        "",
    ]
    if not report["sources"]:
        lines.append("Bu filtrelerle eşleşen kaynak yok.")
    for item in report["sources"]:
        lines.append(
            f"{safe_text(item['identifier'])} — {safe_text(item['label'])}"
        )
        lines.append(
            f"  Durum: {_STATES[item['integration_state']]} | "
            f"Maliyet: {_COSTS[item['cost_model']]} | Tür: {safe_text(item['kind'])}"
        )
        lines.append(
            f"  Dil: {_join(item['languages'])} | Bölge: {_join(item['regions'])} | "
            f"Ticari kullanım: {_RIGHTS[item['commercial_use']]}"
        )
        if item.get("health"):
            lines.append(
                f"  Sağlık: {safe_text(item['health']['state'])} | "
                f"Kanıt modeli: {safe_text(item['health']['model'])}"
            )
        if item["prerequisites"]:
            lines.append(f"  Gereken: {safe_text(item['prerequisites'][0])}")
    if report["has_more"]:
        lines.extend([
            "",
            f"Sonraki sayfa: aynı komuta --offset {report['next_offset']} ekle.",
        ])
    lines.extend(["", *(safe_text(note) for note in report["notes"])])
    return lines


def show_lines(item: dict) -> list[str]:
    lines = [
        f"Kaynak: {safe_text(item['label'])}",
        f"Kimlik: {safe_text(item['identifier'])} | Manifest: {item['manifest_version']} | "
        f"Durum: {_STATES[item['integration_state']]}",
        f"Amaç: {safe_text(item['purpose'])}",
        f"Erişim: {safe_text(item['access'])}",
        f"Toplama: {safe_text(item['collection_mode'])} | Erişim modeli: "
        f"{safe_text(item['access_model'])} | Hedef teması: {safe_text(item['target_contact'])}",
        f"Kimlik bilgisi: {safe_text(item['credential_mode'])} | Maliyet: "
        f"{_COSTS[item['cost_model']]}",
        f"Dil: {_join(item['languages'])} | Bölge: {_join(item['regions'])}",
        f"Normalleştirilmiş kayıtlar: {_join(item['normalized_record_types'])}",
        f"Kanıt alanları: {_join(item['provenance_fields'])}",
        "",
        "Veri kullanım kararları:",
        f"  Ticari kullanım: {_RIGHTS[item['commercial_use']]}",
        f"  Saklama: {_RIGHTS[item['retention_policy']]}",
        f"  Müşteriye gösterim: {_RIGHTS[item['customer_display']]}",
        f"  Yeniden dağıtım: {_RIGHTS[item['redistribution']]}",
        f"  Son koşul incelemesi: {safe_text(item['terms_reviewed_at'] or 'Yapılmadı')}",
        "",
        "İşletim sözleşmesi:",
        f"  Kota: {safe_text(item['quota_policy'])}",
        f"  Tekrar: {safe_text(item['retry_policy'])}",
        f"  Hata: {safe_text(item['failure_policy'])}",
        f"  Sağlık: {safe_text(item['health_model'])} | {safe_text(item['health_command'])}",
    ]
    if item.get("health"):
        lines.append(f"  Kayıtlı sağlık durumu: {safe_text(item['health']['state'])}")
        for evidence in item["health"]["evidence"]:
            lines.append(
                f"    {safe_text(evidence['key'])}: {safe_text(evidence['state'])}"
            )
    lines.append("")
    lines.append("Ön koşullar:")
    lines.extend(
        f"  - {safe_text(value)}" for value in item["prerequisites"]
    )
    if not item["prerequisites"]:
        lines.append("  Yok.")
    lines.append("Komutlar:")
    lines.extend(f"  - ./xti {safe_text(value)}" for value in item["commands"])
    lines.append("Bilinçli sınırlar:")
    lines.extend(f"  - {safe_text(value)}" for value in item["limits"])
    lines.extend([
        f"Resmî başvuru: {safe_text(item['reference_url'])}",
        f"Manifest özeti: {safe_text(item['manifest_sha256'])}",
        "Bu kayıt canlı erişim testi veya sağlayıcı kullanım izni değildir.",
    ])
    return lines


def validate_lines(report: dict) -> list[str]:
    lines = [
        "Kaynak manifesti doğrulaması",
        f"Sonuç: {'Geçerli' if report['valid'] else 'Geçersiz'} | Kaynak: {report['source_count']}",
        f"Katalog özeti: {safe_text(report['catalog_sha256'])}",
        "Durumlar: " + ", ".join(
            f"{_STATES[key]}={value}" for key, value in report["integration_states"].items()
        ),
        f"Zorunlu kanıt alanları: {_join(report['required_provenance_fields'])}",
    ]
    if report["issues"]:
        lines.append("Sorunlar:")
        lines.extend(f"  - {safe_text(value)}" for value in report["issues"])
    lines.extend(["", *(safe_text(note) for note in report["notes"])])
    return lines
