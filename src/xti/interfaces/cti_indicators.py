"""Safe terminal rendering for the local sourced IOC catalog."""

from xti.domain.cti_indicators import (
    CtiIndicatorAssertion,
    CtiIndicatorDetails,
    CtiIndicatorMutation,
    CtiIndicatorSummary,
)
from xti.interfaces.text import safe_text


_ACTION = {
    "added": "Kaynak iddiası eklendi",
    "observed": "Gözlem aralığı güncellendi",
    "updated": "Kaynak iddiası güncellendi",
    "reactivated": "Kaynak iddiası yeniden etkinleştirildi",
    "revoked": "Kaynak iddiası geri çekildi",
    "unchanged": "Değişiklik yok",
}


def _validity(assertion: CtiIndicatorAssertion) -> str:
    start = safe_text(assertion.valid_from) if assertion.valid_from else "sınır yok"
    end = safe_text(assertion.valid_until) if assertion.valid_until else "sınır yok"
    return f"{start} → {end}"


def mutation_lines(result: CtiIndicatorMutation) -> list[str]:
    indicator, assertion = result.indicator, result.assertion
    return [
        f"IOC işlemi: {_ACTION[result.action]}",
        f"Gösterge: {safe_text(indicator.indicator_type)} | {safe_text(indicator.value)}",
        f"Kaynak: {safe_text(assertion.source_name)} | "
        f"{safe_text(assertion.source_reference)}",
        f"Güven: {assertion.confidence}/100 | "
        f"Durum: {'Etkin' if assertion.active else 'Geri çekildi'}",
        f"Gözlem: {safe_text(assertion.first_seen_at)} → "
        f"{safe_text(assertion.last_seen_at)}",
        f"Geçerlilik: {_validity(assertion)}",
        f"Açıklama: {safe_text(assertion.description)}",
        f"IOC kimliği: {safe_text(indicator.id)}",
        f"Kaynak iddiası kimliği: {safe_text(assertion.id)}",
        "Bir IOC kaydı tek başına zararlı, güvenli veya kurumunu etkiliyor hükmü değildir.",
    ]


def list_lines(
    summaries: tuple[CtiIndicatorSummary, ...], *, active_only: bool,
) -> list[str]:
    scope = "geçerliliği süren kaynak iddiası olanlar" if active_only else "tüm geçmiş"
    lines = [f"Yerel IOC kataloğu ({len(summaries)} gösteriliyor; {scope}):"]
    if not summaries:
        lines.append("  Kayıt yok. Örnek: ./xti ioc add domain example.org --help")
        return lines
    for summary in summaries:
        indicator = summary.indicator
        confidence = (
            str(summary.max_current_confidence)
            if summary.max_current_confidence is not None else "yok"
        )
        lines.extend([
            f"  {safe_text(indicator.indicator_type)} | {safe_text(indicator.value)}",
            f"    güncel {summary.current_assertion_count} / etkin "
            f"{summary.active_assertion_count} / toplam {summary.total_assertion_count} kaynak; "
            f"en yüksek güncel güven {confidence}",
            f"    {safe_text(indicator.id)}",
        ])
    lines.append("Bir kaydı aç: ./xti ioc show IOC_KIMLIGI")
    return lines


def detail_lines(details: CtiIndicatorDetails) -> list[str]:
    indicator = details.indicator
    lines = [
        f"IOC: {safe_text(indicator.indicator_type)} | {safe_text(indicator.value)}",
        f"Kimlik: {safe_text(indicator.id)}",
        f"İlk kayıt: {safe_text(indicator.created_at)} | "
        f"Son değişiklik: {safe_text(indicator.updated_at)}",
        f"Kaynak iddiası: {details.total_assertion_count} toplam; "
        f"{len(details.assertions)} gösteriliyor",
        "Kaynaklar:",
    ]
    for assertion in details.assertions:
        lines.extend([
            f"  {safe_text(assertion.source_name)} | "
            f"{safe_text(assertion.source_reference)}",
            f"    güven {assertion.confidence}/100 | "
            f"{'etkin' if assertion.active else 'geri çekildi'} | "
            f"geçerlilik {_validity(assertion)}",
            f"    gözlem {safe_text(assertion.first_seen_at)} → "
            f"{safe_text(assertion.last_seen_at)}",
            f"    {safe_text(assertion.description)}",
            f"    kaynak iddiası: {safe_text(assertion.id)}",
        ])
    lines.extend([
        f"Geçmiş: {details.total_event_count} olay; {len(details.events)} gösteriliyor",
    ])
    for event in details.events:
        reason = f" | {safe_text(event.reason)}" if event.reason else ""
        lines.append(
            f"  {safe_text(event.recorded_at)} | {_ACTION[event.action]} | "
            f"{event.confidence}/100 | gözlem {safe_text(event.observed_at)}{reason}"
        )
    lines.extend([
        "",
        "Güncellik ve kaynak gerekçeleri: ./xti ioc lifecycle TUR DEGER",
        "Kaynak iddiaları birbirini ezmez; geri çekme geçmişi silmez.",
        "Güven puanı kaynak bağlamıdır; otomatik zararlılık veya etkilenme kararı değildir.",
    ])
    return lines
