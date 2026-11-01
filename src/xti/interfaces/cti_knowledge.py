"""Safe terminal rendering for source-preserving CTI knowledge."""

from xti.domain.cti_knowledge import (
    CtiEntityDetails,
    CtiEntityMutation,
    CtiEntitySummary,
    CtiRelationshipDetails,
    CtiRelationshipMutation,
    CtiRelationshipSummary,
    CtiSearchReport,
)
from xti.interfaces.text import safe_text


_ACTION = {
    "added": "Eklendi", "observed": "Gözlem aralığı güncellendi",
    "updated": "Kaynak iddiası güncellendi",
    "reactivated": "Yeniden etkinleştirildi", "revoked": "Geri çekildi",
    "unchanged": "Değişiklik yok",
}


def entity_mutation_lines(result: CtiEntityMutation) -> list[str]:
    aliases = ", ".join(safe_text(value) for value in result.assertion.aliases) or "yok"
    return [
        f"CTI varlık işlemi: {_ACTION[result.action]}",
        f"Varlık: {safe_text(result.entity.entity_type)} | "
        f"{safe_text(result.entity.display_name)}",
        f"Alternatif adlar: {aliases}",
        f"Kaynak: {safe_text(result.assertion.source_name)} | "
        f"{safe_text(result.assertion.source_reference)}",
        f"Güven: {result.assertion.confidence}/100 | "
        f"{'Etkin' if result.assertion.active else 'Geri çekildi'}",
        f"Varlık kimliği: {safe_text(result.entity.id)}",
        f"Kaynak iddiası kimliği: {safe_text(result.assertion.id)}",
        "Bu kayıt otomatik atıf, birleşim veya doğrulanmış tehdit hükmü değildir.",
    ]


def entity_list_lines(
    records: tuple[CtiEntitySummary, ...], *, active_only: bool,
) -> list[str]:
    lines = [
        f"CTI varlıkları ({len(records)} gösteriliyor; "
        f"{'etkin kaynaklı' if active_only else 'tüm geçmiş'}):"
    ]
    if not records:
        lines.append("  Kayıt yok. Örnek: ./xti cti entity-add malware NAME --help")
    for record in records:
        lines.extend([
            f"  {safe_text(record.entity.entity_type)} | "
            f"{safe_text(record.entity.display_name)}",
            f"    etkin {record.active_assertion_count} / toplam "
            f"{record.total_assertion_count} kaynak | en yüksek güven "
            f"{record.max_active_confidence if record.max_active_confidence is not None else 'yok'}",
            f"    {safe_text(record.entity.id)}",
        ])
    return lines


def entity_detail_lines(details: CtiEntityDetails) -> list[str]:
    lines = [
        f"CTI varlığı: {safe_text(details.entity.entity_type)} | "
        f"{safe_text(details.entity.display_name)}",
        f"Kimlik: {safe_text(details.entity.id)}",
        f"Kaynak iddiası: {details.total_assertion_count}; "
        f"{len(details.assertions)} gösteriliyor",
    ]
    for assertion in details.assertions:
        aliases = ", ".join(safe_text(value) for value in assertion.aliases) or "yok"
        lines.extend([
            f"  {safe_text(assertion.source_name)} | "
            f"{safe_text(assertion.source_reference)} | {assertion.confidence}/100 | "
            f"{'etkin' if assertion.active else 'geri çekildi'}",
            f"    alternatif adlar: {aliases}",
            f"    {safe_text(assertion.description)}",
            f"    iddia: {safe_text(assertion.id)}",
        ])
    lines.append(f"Olay geçmişi: {details.total_event_count}; {len(details.events)} gösteriliyor")
    for event in details.events:
        reason = f" | {safe_text(event.reason)}" if event.reason else ""
        lines.append(
            f"  {safe_text(event.recorded_at)} | {_ACTION[event.action]} | "
            f"{event.confidence}/100{reason}"
        )
    lines.append("Alternatif adlar kaynak iddiasıdır; varlıkları otomatik birleştirmez.")
    return lines


def _relation_label(record: CtiRelationshipSummary) -> str:
    source = f"{record.source_entity.entity_type}:{record.source_entity.display_name}"
    if record.target_entity is not None:
        target = f"{record.target_entity.entity_type}:{record.target_entity.display_name}"
    else:
        target = f"{record.target_indicator_type}:{record.target_indicator_value}"
    return f"{safe_text(source)} --{safe_text(record.relationship.relationship_type)}--> {safe_text(target)}"


def relationship_mutation_lines(result: CtiRelationshipMutation) -> list[str]:
    return [
        f"CTI ilişki işlemi: {_ACTION[result.action]}",
        f"İlişki: {safe_text(result.relationship.relationship_type)} | "
        f"hedef {safe_text(result.relationship.target_kind)}",
        f"Kaynak: {safe_text(result.assertion.source_name)} | "
        f"{safe_text(result.assertion.source_reference)}",
        f"Güven: {result.assertion.confidence}/100 | "
        f"{'Etkin' if result.assertion.active else 'Geri çekildi'}",
        f"İlişki kimliği: {safe_text(result.relationship.id)}",
        f"Kaynak iddiası kimliği: {safe_text(result.assertion.id)}",
        "İlişki bir kaynak iddiasıdır; otomatik atıf veya nedensellik kararı değildir.",
    ]


def relationship_list_lines(
    records: tuple[CtiRelationshipSummary, ...], *, active_only: bool,
) -> list[str]:
    lines = [
        f"CTI ilişkileri ({len(records)} gösteriliyor; "
        f"{'etkin kaynaklı' if active_only else 'tüm geçmiş'}):"
    ]
    if not records:
        lines.append("  Kayıt yok. Örnek: ./xti cti relation-add --help")
    for record in records:
        lines.extend([
            f"  {_relation_label(record)}",
            f"    etkin {record.active_assertion_count} / toplam "
            f"{record.total_assertion_count} kaynak | en yüksek güven "
            f"{record.max_active_confidence if record.max_active_confidence is not None else 'yok'}",
            f"    {safe_text(record.relationship.id)}",
        ])
    return lines


def relationship_detail_lines(details: CtiRelationshipDetails) -> list[str]:
    lines = [
        f"CTI ilişkisi: {_relation_label(details.summary)}",
        f"Kimlik: {safe_text(details.summary.relationship.id)}",
        f"Kaynak iddiası: {details.total_assertion_count}; "
        f"{len(details.assertions)} gösteriliyor",
    ]
    for assertion in details.assertions:
        lines.extend([
            f"  {safe_text(assertion.source_name)} | "
            f"{safe_text(assertion.source_reference)} | {assertion.confidence}/100 | "
            f"{'etkin' if assertion.active else 'geri çekildi'}",
            f"    {safe_text(assertion.description)}",
            f"    iddia: {safe_text(assertion.id)}",
        ])
    lines.append(f"Olay geçmişi: {details.total_event_count}; {len(details.events)} gösteriliyor")
    for event in details.events:
        reason = f" | {safe_text(event.reason)}" if event.reason else ""
        lines.append(
            f"  {safe_text(event.recorded_at)} | {_ACTION[event.action]} | "
            f"{event.confidence}/100{reason}"
        )
    lines.append("Çelişen kaynak ilişkileri korunur; biri diğerini otomatik geçersiz kılmaz.")
    return lines


def search_lines(report: CtiSearchReport) -> list[str]:
    scope = {"all": "varlık + IOC", "entity": "yalnız varlık", "indicator": "yalnız IOC"}
    lines = [
        f"CTI araması: {safe_text(report.query)} | {scope[report.kind]} | "
        f"{report.total_match_count} eşleşme, {len(report.results)} gösteriliyor",
        f"Kapsam: {'yalnız etkin/güncel kaynaklar' if report.active_only else 'bütün geçmiş'}",
    ]
    labels = {"exact": "tam", "prefix": "başlangıç", "contains": "içerme"}
    for result in report.results:
        lines.extend([
            f"  {safe_text(result.kind)} | {safe_text(result.record_type)} | "
            f"{safe_text(result.display_value)}",
            f"    {labels[result.match_type]} eşleşme: "
            f"{safe_text(result.matched_field)}={safe_text(result.matched_value)}",
            f"    güncel kaynak {result.current_assertion_count} / toplam "
            f"{result.total_assertion_count} | en yüksek güncel güven "
            f"{result.max_current_confidence if result.max_current_confidence is not None else 'yok'}",
            f"    {safe_text(result.record_id)}",
        ])
    if not report.results:
        lines.append("  Eşleşme yok. Bu sonuç verinin güvenli olduğunu veya kaynağın tam olduğunu göstermez.")
    elif report.total_match_count > len(report.results):
        lines.append(f"  {report.total_match_count - len(report.results)} kayıt görünüm sınırı dışında.")
    lines.append("Arama yerel ve salt okunurdur; sonuçlar doğrulanmış tehdit hükmü değildir.")
    return lines

