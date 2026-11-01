"""Terminal rendering for the pinned MITRE ATT&CK subset sync."""

from xti.domain.cti_attack import AttackSyncResult
from xti.interfaces.text import safe_text


def attack_sync_lines(result: AttackSyncResult) -> list[str]:
    return [
        f"MITRE ATT&CK Enterprise v{safe_text(result.version)} senkronu tamamlandı.",
        f"Kaynak STIX nesnesi: {result.source_object_count}",
        f"Yerel varlık: {result.entity_count} | ilişki: {result.relationship_count}",
        (
            "Varlık işlemleri: "
            f"yeni {result.entity_added}, gözlem {result.entity_observed}, "
            f"güncellenen {result.entity_updated}, aynı {result.entity_unchanged}, "
            f"yeniden etkin {result.entity_reactivated}, geri çekilen {result.entity_revoked}"
        ),
        (
            "İlişki işlemleri: "
            f"yeni {result.relationship_added}, gözlem {result.relationship_observed}, "
            f"güncellenen {result.relationship_updated}, "
            f"aynı {result.relationship_unchanged}, yeniden etkin "
            f"{result.relationship_reactivated}, geri çekilen "
            f"{result.relationship_revoked}"
        ),
        "Kapsam: etkin grup, kampanya, malware ve aralarındaki uses/attributed-to ilişkileri.",
        "ATT&CK grup kaydı yerelde threat-actor etiketiyle tutulur; bu otomatik atıf hükmü değildir.",
        "Ara: ./xti cti search \"APT29\"",
    ]
