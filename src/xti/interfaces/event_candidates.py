"""Read-only candidate command and safe source-by-source terminal rendering."""

from dataclasses import asdict
import json
import shlex

from xti.domain.event_candidates import EventCandidateReport, EventEvidence
from xti.interfaces.text import safe_text


_KINDS = {
    "possible_same_event": "Aynı olay olabilir",
    "organization_context": "Ortak kuruluş/domain bağlamı",
}
_COVERAGE = {
    "not_collected": "Henüz toplanmadı",
    "unavailable": "Kullanılabilir başarılı kaynak kaydı yok",
    "last_attempt_failed": "Son deneme başarısız; önceki başarılı kayıtlar kullanılıyor",
    "available": "Başarılı kaynak kayıtları kullanılabilir",
}
_FRESHNESS = {
    "current": "Güncel", "stale": "Eski", "clock_error": "Zaman bilgisi tutarsız",
    "never": "Başarılı kayıt yok",
}


def register_event_candidates_parser(commands):
    parser = commands.add_parser("events", help="Kayıtlı kaynakları açıklanabilir olay adaylarıyla birlikte incele.")
    actions = parser.add_subparsers(dest="event_action", required=True)
    candidates = actions.add_parser("candidates", help="Kaynak kayıtlarını birleştirmeden ağsız aday karşılaştırması göster.")
    candidates.add_argument("--domain", help="Yalnız kanıtta tam domain eşleşmesi bulunan adaylar.")
    candidates.add_argument("--offset", type=int, default=0)
    candidates.add_argument("--limit", type=int, default=50)
    candidates.add_argument("--stale-hours", type=int, default=24,
                            help="Başarılı kaynak kaydının güncellik sınırı, saat (1–8760).")


def make_event_candidate_service(database):
    from xti.adapters.sqlite_event_candidates import SQLiteEventCandidateRepository
    from xti.application.event_candidates import EventCandidateService
    return EventCandidateService(SQLiteEventCandidateRepository(database))


def _field_value(value):
    if value is None:
        return "kayıtta yok"
    return safe_text(json.dumps(value, ensure_ascii=False))


def _evidence_lines(evidence: EventEvidence):
    lines = [
        f"  Kaynak: {safe_text(evidence.source_key)} | {safe_text(evidence.title)}",
        f"    Kayıt: {safe_text(evidence.source_key)}:{safe_text(evidence.record_type)}:{safe_text(evidence.record_id)}",
        f"    Kaynak çalışma kimliği: {safe_text(evidence.source_run_id)}",
        f"    Kayıt özeti (SHA-256): {safe_text(evidence.state_sha256)}",
        f"    Domain: {safe_text(evidence.domain) if evidence.domain else 'kayıtta yok'} | "
        f"grup: {safe_text(evidence.group) if evidence.group else 'kayıtta yok'}",
        f"    Kaynak adresi: {safe_text(evidence.source_url)}",
        "    Tarihler ve anlamları:",
    ]
    for date in evidence.dates:
        lines.append(f"      {safe_text(date.meaning)} ({safe_text(date.field)}): {safe_text(date.value)}")
    lines.append("    Kaynak kaydındaki alanlar:")
    lines.extend(f"      {safe_text(field)}: {_field_value(value)}" for field, value in asdict(evidence.record).items())
    return lines


def event_candidate_lines(report: EventCandidateReport):
    lines = [
        "Kaynaklar arası olay adayları — yalnız kayıtlı veri",
        f"Kontrol zamanı: {safe_text(report.checked_at)} | kural: {safe_text(report.rule_version)}",
        f"Domain filtresi: {safe_text(report.domain_filter) if report.domain_filter else 'yok'} | "
        f"güncellik sınırı: {report.stale_after_hours} saat",
        f"Toplam aday: {report.total_candidate_count} | gösterilen: {len(report.candidates)} | "
        f"başlangıç: {report.offset} | sınır: {report.limit}",
        f"Aynı olay olabilir: {report.possible_same_event_count} | "
        f"ortak kuruluş/domain bağlamı: {report.organization_context_count}",
        "Kaynak kapsamı:",
    ]
    for coverage in report.coverage:
        lines.extend((
            f"  {safe_text(coverage.source_name)} ({safe_text(coverage.source_key)}): "
            f"{safe_text(_COVERAGE.get(coverage.status, coverage.status))}",
            f"    Güncellik: {safe_text(_FRESHNESS.get(coverage.freshness, coverage.freshness))} | "
            f"başarılı snapshot kaydı: {coverage.record_count}",
            f"    Son deneme: {safe_text(coverage.latest_run_status)} | {safe_text(coverage.latest_run_at)} | "
            f"{safe_text(coverage.latest_run_id)}",
            f"    Son başarı: {safe_text(coverage.latest_success_at)} | {safe_text(coverage.latest_success_run_id)}",
            f"    Kaynak adresi: {safe_text(coverage.source_url)}",
            f"    Lisans/atıf: {safe_text(coverage.license)}",
        ))
        lines.extend("    Not: " + safe_text(note) for note in coverage.notes)
    if not report.candidates:
        lines.append("Seçilen kapsamda aday yok; kaynak durumlarını yukarıdan incele." if report.total_candidate_count == 0
                     else "Bu sayfada aday yok; başlangıç değeri toplam aday sayısının dışında.")
    for candidate in report.candidates:
        lines.extend(("", f"{safe_text(_KINDS.get(candidate.kind, candidate.kind))} | {safe_text(candidate.id)}",
                      f"  Dayanak: {safe_text(candidate.basis)}",
                      f"  Adayın kanıt özeti (SHA-256): {safe_text(candidate.evidence_sha256)}"))
        lines.extend("  Neden gösterildi: " + safe_text(reason) for reason in candidate.reasons)
        if candidate.discovery_gap_hours is not None:
            lines.append(f"  Kaynak keşif zamanları arası: {candidate.discovery_gap_hours:g} saat")
        lines.extend("  Dikkat: " + safe_text(caution) for caution in candidate.cautions)
        lines.extend(_evidence_lines(candidate.left))
        lines.extend(_evidence_lines(candidate.right))
        if candidate.legacy_review is not None:
            review = candidate.legacy_review
            lines.extend((
                "  Önceki kaynak karşılaştırması kararı:",
                f"    {safe_text(review.decision)} | {safe_text(review.reviewed_at)} | {safe_text(review.comparison_id)}",
                "    Gerekçe: " + safe_text(review.reason),
                "    Kararın kanıtı bu kayıtlarla eşleşiyor." if review.evidence_matches else
                "    Karar eski kanıta bağlı; güncel kaynak kanıtı değişmiş. Bu aday için yeni karar sayılmaz.",
                "    Karar geçmişi: " + safe_text(shlex.join(("./xti", "ransomware", "source-review-show", review.comparison_id))),
            ))
        elif candidate.legacy_comparison_id is not None:
            lines.extend((
                "  Önceki kaynak karşılaştırması kimliği: " + safe_text(candidate.legacy_comparison_id),
                "  Bu karşılaştırmaya kayıtlı insan kararı yok.",
                "  Kaynak karşılaştırmalarını oku: ./xti ransomware source-compare",
            ))
    if report.has_more:
        arguments = ["./xti", "events", "candidates", "--offset", str(report.offset + len(report.candidates)),
                     "--limit", str(report.limit), "--stale-hours", str(report.stale_after_hours)]
        if report.domain_filter:
            arguments.extend(("--domain", report.domain_filter))
        lines.append("Sonraki sayfa: " + safe_text(shlex.join(arguments)))
    lines.extend("Not: " + safe_text(note) for note in report.notes)
    return lines


def execute_event_candidates_command(service, args):
    report = service.candidates(domain=args.domain, offset=args.offset, limit=args.limit,
                                stale_after_hours=args.stale_hours)
    return asdict(report), event_candidate_lines(report)
