"""Public breach-catalog metadata with visible attribution and honest source status."""

from xti.interfaces.text import safe_text


def register_public_notice_parser(commands) -> None:
    parser = commands.add_parser("notices", help="Ücretsiz kamu olay kataloğunu yenile ve yerel kayıtlarını araştır.")
    actions = parser.add_subparsers(dest="notice_action", required=True)
    refresh = actions.add_parser("refresh", help="HIBP kamu olay metadata kataloğunu internetten bir kez al.")
    refresh.add_argument("--limit", type=int, default=20, help="Gösterilecek değişiklik sayısı; toplama kapsamını kesmez.")
    status = actions.add_parser("status", help="Son deneme, başarılı katalog ve çalışma geçmişini ağsız göster.")
    status.add_argument("--limit", type=int, default=10)
    status.add_argument("--offset", type=int, default=0)
    search = actions.add_parser("search", help="Yerel olay adı/domain metninde ara; e-posta sorgulamaz.")
    search.add_argument("query", nargs="?")
    search.add_argument("--domain", help="Kaynakta bildirilen domain alanıyla tam eşleşme.")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--offset", type=int, default=0)
    show = actions.add_parser("show", help="Kaynağın kalıcı olay kimliğiyle yerel metadata kaydını göster.")
    show.add_argument("notice_id")
    run = actions.add_parser("run-show", help="Belirli toplamanın başlangıç/fark/hata sonucunu göster.")
    run.add_argument("run_id")
    run.add_argument("--limit", type=int, default=20)
    run.add_argument("--offset", type=int, default=0)


def _header(report) -> list[str]:
    return ["Kaynak: " + safe_text(report.attribution), "Lisans: " + safe_text(report.license)]


def _source_state(report) -> list[str]:
    latest, complete = report.latest_run, report.latest_complete_run
    lines = []
    if latest is None:
        lines.append("Kaynak henüz yenilenmedi; olay kapsamı bilinmiyor. Sonraki adım: ./xti notices refresh")
    else:
        lines.append(f"Son deneme: {safe_text(latest.status)} | {safe_text(latest.finished_at)} | {safe_text(latest.id)}")
        if latest.error:
            lines.append("Kaynak hatası: " + safe_text(latest.error))
    if complete is None:
        lines.append("Başarılı katalog yok; bu durum sıfır olay sonucu değildir.")
    else:
        lines.append(f"Kullanılan son başarılı katalog: {complete.notice_count} metadata kaydı | {safe_text(complete.fetched_at)} | {safe_text(complete.id)}")
        if latest is not None and latest.id != complete.id:
            lines.append("Son kaynak denemesi başarısız; önceki başarılı katalog gösteriliyor.")
    return lines


def _notice_lines(notice, *, detailed: bool = False) -> list[str]:
    flags = (
        ("is_verified", "kaynak doğrulanmış diyor"),
        ("is_fabricated", "kaynak uydurma/yanlış iddia diyor"),
        ("is_sensitive", "kaynak hassas diyor"),
        ("is_retired", "kaynak kaydı geri çekmiş"),
        ("is_spam_list", "kaynak spam listesi diyor"),
        ("is_malware", "kaynak malware bağlantılı diyor"),
        ("is_stealer_log", "kaynak stealer-log bağlantılı diyor"),
    )
    categories = [label for field, label in flags if getattr(notice, field)]
    if not notice.is_verified:
        categories.insert(0, "kaynak doğrulanmış olarak işaretlememiş")
    lines = [
        f"  {safe_text(notice.title)} | kimlik {safe_text(notice.id)} | domain {safe_text(notice.domain or 'belirtilmedi')}",
        f"    Kaynağın olay tarihi: {safe_text(notice.breach_date)} | kaynakta değişme: {safe_text(notice.modified_at)}",
        "    Kaynak sınıfları: " + safe_text("; ".join(categories)),
        "    Kaynak kaydı: " + safe_text(notice.source_url),
    ]
    if notice.source_attribution:
        lines.append("    Ek kaynak atfı: " + safe_text(notice.source_attribution))
    if detailed:
        lines.extend([
            "    Kataloğa eklenme: " + safe_text(notice.added_at),
            f"    HIBP'nin katalogladığı hesap sayısı: {notice.pwn_count}; XTI'nin saydığı benzersiz kişi değildir.",
            "    Kaynakta bildirilen veri kategorileri: " + safe_text(", ".join(notice.data_classes)),
            "    Kategori adları metadata bilgisidir; bu verilerin içeriği indirilmedi.",
        ])
    else:
        lines.append("    Ayrıntı: ./xti notices show " + safe_text(notice.id))
    return lines


def public_notice_status_lines(report) -> list[str]:
    lines = _header(report) + _source_state(report)
    lines.append(f"Çalışma geçmişi: toplam {report.total_run_count}; bu sayfada {len(report.recent_runs)}")
    for run in report.recent_runs:
        lines.append(f"  {safe_text(run.finished_at)} | {safe_text(run.status)} | {safe_text(run.id)}")
    if report.offset + len(report.recent_runs) < report.total_run_count:
        lines.append(f"Sonraki çalışma sayfası: --offset {report.offset + len(report.recent_runs)}")
    return lines + [safe_text(note) for note in report.notes]


def public_notice_refresh_lines(report) -> list[str]:
    run = report.run
    lines = _header(report) + [
        f"Katalog çalışması: {safe_text(run.status)} | {safe_text(run.id)}",
        f"Başlangıç: {safe_text(run.started_at)} | bitiş: {safe_text(run.finished_at)}",
    ]
    if run.error:
        lines.append("Kaynak hatası: " + safe_text(run.error))
    else:
        lines.append(f"Katalog: {run.notice_count}; eklenen {run.added_count}, değişen {run.updated_count}, aynı {run.unchanged_count}, listeden çıkan {run.removed_count}")
    if report.is_baseline:
        lines.append("İlk başarılı katalog başlangıç çizgisidir; bu kayıtlar bugün olmuş yeni ihlaller değildir.")
    lines.append(f"Başlangıç/değişim kayıtları: {report.total_change_count}; bu sayfada {len(report.changes)}")
    for item in report.changes:
        lines.append("  Katalog işlemi: " + safe_text(item.action))
        # Preserve the selected historical record, including removed entries.
        lines.extend(_notice_lines(item.notice, detailed=True))
    if report.offset + len(report.changes) < report.total_change_count:
        lines.append(f"Devamı: ./xti notices run-show {safe_text(run.id)} --offset {report.offset + len(report.changes)}")
    return lines + [safe_text(note) for note in report.notes]


def public_notice_search_lines(report) -> list[str]:
    lines = _header(report) + _source_state(report)
    lines.append(f"Yerel arama: {safe_text(report.query or 'bütün kayıtlar')} | tam domain: {safe_text(report.domain_filter or 'seçilmedi')}")
    lines.append(f"Eşleşen metadata kaydı: {report.matched_count}; bu sayfada {report.displayed_count}")
    for notice in report.notices:
        lines.extend(_notice_lines(notice))
    if report.has_more:
        lines.append(f"Sonraki sayfa: --offset {report.offset + report.displayed_count}")
    return lines + [safe_text(note) for note in report.notes]


def public_notice_detail_lines(report) -> list[str]:
    return _header(report) + _source_state(report) + _notice_lines(report.notice, detailed=True) + [safe_text(note) for note in report.notes]
