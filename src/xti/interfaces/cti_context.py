"""Exact CTI context arguments and safe, actionable terminal output."""

import shlex

from xti.domain.cti_context import CtiContextReport
from xti.domain.cti_indicators import INDICATOR_TYPES
from xti.interfaces.text import safe_text


def register_cti_context_parser(commands) -> None:
    parser = commands.add_parser("context", help="Tam IOC veya CTI varlığının kayıtlı bağlantılarını kaynaklarıyla göster.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--entity", help="Kayıtlı CTI varlık kimliği.")
    selection.add_argument("--type", choices=(*INDICATOR_TYPES, "ip"), dest="indicator_type")
    parser.add_argument("--value", help="Tam gösterge değeri; --type ile birlikte kullanılır.")
    parser.add_argument("--all", action="store_true", dest="include_inactive", help="Geri çekilmiş ilişkileri de göster.")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--source-offset", type=int, default=0)
    parser.add_argument("--source-limit", type=int, default=20)


def _sources(lines, record, report) -> None:
    lines.append(f"    Kaynak iddiaları: güncel {record.current_source_count} / toplam {record.total_source_count}; bu sayfada {len(record.sources)}")
    for source in record.sources:
        state = "güncel" if source.current else "geçerli dönem dışında" if source.active else "geri çekilmiş"
        lines.extend([
            f"      {safe_text(source.source_name)} | {safe_text(source.source_reference)} | {state}",
            f"        {safe_text(source.description)}",
            f"        İddia {safe_text(source.assertion_id)} | kaynak güveni {source.confidence}/100 | son gözlem {safe_text(source.last_seen_at)}",
        ])
        if source.valid_from is not None or source.valid_until is not None:
            lines.append(f"        Geçerlilik: {safe_text(source.valid_from or 'başlangıç belirtilmedi')} → {safe_text(source.valid_until or 'bitiş belirtilmedi')}")
    if report.source_offset + len(record.sources) < record.total_source_count:
        lines.append(f"    Sonraki kaynak sayfası: --source-offset {report.source_offset + len(record.sources)}")


def cti_context_lines(report: CtiContextReport) -> list[str]:
    lines = ["Kayıtlı CTI bağlantıları; internet sorgusu yapılmadı."]
    if report.root is None:
        lines.append(f"Tam değer için yerel IOC kaydı bulunamadı: {safe_text(report.query.value)}")
    else:
        lines.extend([
            f"Başlangıç: {safe_text(report.root.record_type)} | {safe_text(report.root.value)} | {safe_text(report.root.id)}",
            f"Doğrudan ilişki: {report.total_relationship_count}; {len(report.relationships)} gösteriliyor; bağlı kayıt: {report.total_node_count}",
            f"Geri çekilmiş ilişki: {report.inactive_relationship_count}; {'görünümde' if report.query.include_inactive else '--all ile açılır'}",
        ])
        for node in report.nodes:
            lines.append(f"  Kayıt: {safe_text(node.record_type)} | {safe_text(node.value)} | {safe_text(node.id)}")
            _sources(lines, node, report)
            command = ["./xti", "cti", "context"]
            command += ["--entity", node.id] if node.kind == "entity" else ["--type", node.record_type, "--value", node.value]
            lines.append("    Bağlantıları aç: " + safe_text(shlex.join(command)))
        names = {(node.kind, node.id): node.value for node in report.nodes}
        for relation in report.relationships:
            left = names[("entity", relation.source_entity_id)]
            right = names[(relation.target_kind, relation.target_id)]
            lines.append(f"  {safe_text(left)} --{safe_text(relation.relationship_type)}--> {safe_text(right)}")
            _sources(lines, relation, report)
            lines.append("    Geçmiş: ./xti cti relation-show " + safe_text(relation.id))
        if report.offset + len(report.relationships) < report.total_relationship_count:
            lines.append(f"Sonraki ilişki sayfası: --offset {report.offset + len(report.relationships)}")
    lines.extend(safe_text(note) for note in report.notes)
    return lines
