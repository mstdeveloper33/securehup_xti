"""Terminal views of recorded source work, without reinterpreting old evidence."""

from xti.application.collection_history import CollectionResumeResult
from xti.domain.collection_history import CollectionResumePlan, CollectionSessionDetails, CollectionSessionPage
from xti.interfaces.analysis import report_lines as analysis_lines
from xti.interfaces.text import safe_text

_STATUS = {
    "pending": "Bekliyor", "running": "Çalışıyor", "complete": "Tamamlandı",
    "partial": "Kısmi", "failed": "Başarısız", "interrupted": "Kesildi", "skipped": "Atlandı",
}


def _public_notice_lines(receipt) -> list[str]:
    if receipt.result_kind != "public_notice_run":
        return []
    lines = [
        "    Kaynak: " + safe_text(receipt.source_attribution or ""),
        "    Lisans: " + safe_text(receipt.source_license or ""),
        "    Kapsam: ortak kamu kataloğu; sayaçlar seçilen domainin bulguları değildir.",
        "    Kaynak çalışma ayrıntısı: ./xti notices run-show " + safe_text(receipt.result_id),
    ]
    if dict(receipt.summary).get("is_baseline") == 1:
        lines.append("    İlk başarılı katalog başlangıç çizgisidir; bugün yaşanmış yeni ihlaller değildir.")
    return lines


def register_history_parser(commands) -> None:
    parser = commands.add_parser("collections", help="Toplama geçmişini göster ve eksik işleri yeniden dene.")
    actions = parser.add_subparsers(dest="collection_action", required=True)
    listing = actions.add_parser("list", help="Kayıtlı toplama oturumlarını göster.")
    listing.add_argument("--limit", type=int, default=50)
    listing.add_argument("--before", type=int, help="Önceki sayfadaki devam sırası.")
    show = actions.add_parser("show", help="Kaynak çalışma kimliklerini ve tamamlanma durumlarını göster.")
    show.add_argument("session_id")
    resume = actions.add_parser("resume", help="Yalnız eksik adımları yeni yürütmede tekrar dene.")
    resume.add_argument("session_id")
    resume.add_argument("--plan", action="store_true", help="Yazmadan/ağ isteği olmadan yeniden deneme planı.")
    actions.add_parser("recover", help="Önceki kesilmiş çalışmaları kaynak kanıtını koruyarak kapat; arama yapmaz.")


def page_lines(page: CollectionSessionPage) -> list[str]:
    lines = ["Toplama geçmişi:"]
    for session in page.sessions:
        lines.append(
            f"  {safe_text(session.id)} | {safe_text(session.plan.definition.asset_value)} | "
            f"{_STATUS[session.status]} | {safe_text(session.started_at)} | yürütme {session.generation}"
        )
    if not page.sessions:
        lines.append("Kayıtlı toplama oturumu yok.")
    if page.next_before is not None:
        lines.append(f"Sonraki sayfa: ./xti collections list --before {page.next_before}")
    return lines


def detail_lines(details: CollectionSessionDetails) -> list[str]:
    session = details.session
    lines = [
        f"Toplama oturumu: {safe_text(session.id)} | {_STATUS[session.status]}",
        f"Domain: {safe_text(session.plan.definition.asset_value)} | yürütme: {session.generation}",
        f"Başlangıç: {safe_text(session.started_at)} | bitiş: {safe_text(session.finished_at or 'Henüz kapanmadı')}",
    ]
    if session.parent_id:
        lines.append(f"Önceki yürütme: {safe_text(session.parent_id)}")
    if session.plan.origin:
        origin = session.plan.origin
        lines.append(f"Kaynak profil: {safe_text(origin.display_name)} | sürüm {origin.revision}")
    receipts = {receipt.step_id: receipt for receipt in details.receipts}
    for step in details.steps:
        lines.append(f"  {safe_text(step.step_key)} | {_STATUS[step.status]}")
        receipt = receipts.get(step.id)
        if receipt:
            lines.append(f"    Kaynak kaydı: {safe_text(receipt.result_kind)} | {safe_text(receipt.result_id)}")
            lines.append(f"    Kayıt zamanı: {safe_text(receipt.recorded_at)}")
            if receipt.source_run_id:
                lines.append(f"    Bağlı kaynak yenilemesi: {safe_text(receipt.source_run_id)}")
            for name, value in receipt.summary:
                lines.append(f"    {safe_text(name)}: {value}")
            lines.extend(_public_notice_lines(receipt))
        if step.error_code:
            lines.append(f"    Durma nedeni: {safe_text(step.error_code)}")
    for retained in details.retained:
        lines.append(
            f"  Önceki yürütmeden korundu: {safe_text(retained.unit.step_key)} | "
            f"{safe_text(retained.receipt.result_id)} | {safe_text(retained.receipt.recorded_at)}"
        )
        lines.extend(_public_notice_lines(retained.receipt))
    lines.extend([
        f"Yerel analiz durumu: {_STATUS[session.analysis_status]}",
        "Bu görünüm kayıtlı geçmişi okur; yeni kaynak sorgusu veya yeni analiz üretmez.",
        "Sayaçlar ayrı kaynak kayıtlarıdır; benzersiz tehdit toplamı olarak toplanmaz.",
    ])
    if session.status == "running":
        lines.append("Çalışma artık sürmüyorsa: ./xti collections recover")
    elif session.status != "complete":
        lines.append(f"Tekrar planı: ./xti collections resume {safe_text(session.id)} --plan")
    return lines


def resume_plan_lines(plan: CollectionResumePlan) -> list[str]:
    lines = [
        f"Eksik işlerin yeniden deneme planı: {safe_text(plan.parent.id)}",
        "Bu önizleme ağ isteği veya veri yazımı yapmadı.",
    ]
    for unit in plan.units:
        lines.append(f"  Çalıştırılacak: {safe_text(unit.step_key)}")
    for retained in plan.retained:
        lines.append(f"  Korunacak: {safe_text(retained.unit.step_key)} | {safe_text(retained.receipt.result_id)}")
        lines.extend(_public_notice_lines(retained.receipt))
    if not plan.units:
        lines.append("Kaynaklar tamamlanmış; yalnız yerel analiz yeniden üretilecek.")
    return lines


def resume_result_lines(result: CollectionResumeResult) -> list[str]:
    return [
        *detail_lines(result.history), "", "Şimdiki yerel kayıtlardan analiz:",
        *analysis_lines(result.analysis, after_collection=True), "",
        *(safe_text(note) for note in result.notes),
    ]
