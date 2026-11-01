"""Safe terminal rendering for local ransomware claim watches."""

from xti.domain.ransomware_watches import (
    RansomwareMonitorSession,
    RansomwareMonitorSessionDetails,
    RansomwareIdentityReviewDetails,
    RansomwareIdentityReviewMutation,
    RansomwareWatchDetails,
    RansomwareWatchIdentityCandidateReport,
    RansomwareWatchMonitorReport,
    RansomwareWatchMutation,
    RansomwareWatchRefreshReport,
    RansomwareWatchRunReport,
    RansomwareWatchSummary,
    RansomwareWatchTimelineReport,
)
from xti.interfaces.text import safe_text


_ACTIONS = {
    "added": "eklendi", "updated": "güncellendi",
    "reactivated": "yeniden etkinleştirildi", "revoked": "geri çekildi",
    "unchanged": "değişmedi", "removed": "kaynak penceresinden çıktı",
}


def mutation_lines(result: RansomwareWatchMutation) -> list[str]:
    watch = result.watch
    return [
        f"Ransomware izlemesi {_ACTIONS[result.action]}: {safe_text(watch.display_name)}",
        f"Tür: {safe_text(watch.kind)} | aranan: {safe_text(watch.query)} | "
        f"eşleşme: {safe_text(watch.match_mode)}",
        f"Kimlik: {safe_text(watch.id)}",
    ]


def list_lines(
    records: tuple[RansomwareWatchSummary, ...], *, active_only: bool,
) -> list[str]:
    lines = [
        f"Ransomware izlemeleri: {len(records)} | "
        f"{'yalnız etkin' if active_only else 'etkin + geri çekilmiş'}"
    ]
    for value in records:
        watch, last = value.watch, value.last_run
        lines.extend([
            f"  {safe_text(watch.display_name)} | {safe_text(watch.kind)} | "
            f"{safe_text(watch.query)} | {'etkin' if watch.active else 'geri çekilmiş'}",
            f"    çalışma: {value.run_count} | son: "
            f"{safe_text(last.executed_at) if last else 'henüz yok'} | {safe_text(watch.id)}",
        ])
    if not records:
        lines.append("  Kayıtlı izleme yok.")
    return lines


def detail_lines(details: RansomwareWatchDetails) -> list[str]:
    watch = details.watch
    lines = [
        f"Ransomware izlemesi: {safe_text(watch.display_name)}",
        f"Tür: {safe_text(watch.kind)} | aranan: {safe_text(watch.query)} | "
        f"{'etkin' if watch.active else 'geri çekilmiş'}",
        f"Çalışmalar: {details.total_run_count}; {len(details.runs)} gösteriliyor",
    ]
    for run in details.runs:
        lines.append(
            f"  {safe_text(run.executed_at)} | toplam {run.total_count} | "
            f"+{run.added_count} ~{run.updated_count} ={run.unchanged_count} "
            f"-{run.removed_count} | {safe_text(run.id)}"
        )
    lines.append(f"Tanım geçmişi: {details.total_event_count}; {len(details.events)} gösteriliyor")
    for event in details.events:
        reason = f" | {safe_text(event.reason)}" if event.reason else ""
        lines.append(f"  {safe_text(event.recorded_at)} | {_ACTIONS[event.action]}{reason}")
    return lines


def run_lines(report: RansomwareWatchRunReport) -> list[str]:
    run = report.run
    lines = [
        f"Ransomware izleme çalışması: {safe_text(report.watch.display_name)}",
        f"Toplam {run.total_count} | yeni {run.added_count} | değişen {run.updated_count} | "
        f"aynı {run.unchanged_count} | kaynak penceresinden çıkan {run.removed_count}",
        f"Sonuç kaydı: {report.total_item_count}; {len(report.items)} gösteriliyor | "
        f"çalışma {safe_text(run.id)}",
    ]
    if report.is_baseline:
        lines.append("İlk çalışma sessiz başlangıç ölçümüdür; bildirim üretilmedi.")
    elif report.notification_id is not None:
        lines.append(f"Yerel kutu bildirimi: {safe_text(report.notification_id)}")
    elif run.removed_count:
        lines.append(
            "Yalnız kaynak penceresinden çıkış var; bu kapatma kanıtı olmadığı için bildirim yok."
        )
    for item in report.items:
        claim, match = item.match.claim, item.match
        lines.extend([
            f"  {_ACTIONS[item.action]} | {safe_text(claim.victim)} | "
            f"grup {safe_text(claim.group)} | durum {safe_text(claim.status)}",
            f"    eşleşen {safe_text(match.matched_field)}={safe_text(match.matched_value)} | "
            f"{safe_text(match.match_type)} | ilk gözlem {safe_text(claim.discovered_at)}",
        ])
    if not report.items:
        lines.append("  Eşleşme ve fark yok.")
    elif report.total_item_count > len(report.items):
        lines.append(f"  {report.total_item_count - len(report.items)} kayıt görünüm sınırı dışında.")
    lines.extend([
        "Sonuç, kamuya açık grup iddiasıdır; doğrulanmış ihlal değildir.",
        "Kaynak penceresinden çıkmak sitenin kapandığını veya riskin bittiğini kanıtlamaz.",
    ])
    return lines


def refresh_all_lines(report: RansomwareWatchRefreshReport) -> list[str]:
    source = report.refresh.run
    if source.status == "failed":
        lines = [
            "Ransomware kaynağı yenilenemedi; etkin izlemeler çalıştırılmadı.",
            f"Hata: {safe_text(source.error or 'Bilinmeyen kaynak hatası')}",
            f"Kaynak çalışması: #{source.sequence} | {safe_text(source.finished_at)}",
            f"Çalıştırılmayan etkin izleme: {report.planned_watch_count}",
        ]
        lines.extend(f"Not: {safe_text(value)}" for value in report.notes)
        return lines

    lines = [
        "Ransomware kaynağı yenilendi ve etkin izlemeler tamamlandı.",
        f"Kaynak snapshot: #{source.sequence} | kayıt {source.claim_count} | "
        f"yeni {source.added_count} | değişen {source.updated_count} | "
        f"pencereden çıkan {source.removed_count}",
        f"Tamamlanan izleme: {report.completed_watch_count}/"
        f"{report.planned_watch_count} | sessiz başlangıç: "
        f"{report.baseline_watch_count}",
        f"Toplam eşleşme: {report.total_count} | yeni {report.added_count} | "
        f"değişen {report.updated_count} | aynı {report.unchanged_count} | "
        f"pencereden çıkan {report.removed_count}",
        f"Yerel bildirim: {report.notification_count}",
        "İzlemeler:",
    ]
    for item in report.items:
        baseline = " | sessiz başlangıç" if item.is_baseline else ""
        lines.append(
            f"  {item.position}. {safe_text(item.display_name)} | toplam "
            f"{item.total_count} | +{item.added_count} ~{item.updated_count} "
            f"={item.unchanged_count} -{item.removed_count}{baseline} | "
            f"{safe_text(item.run_id)}"
        )
    if not report.items:
        lines.append("  Çalıştırılacak etkin izleme yok; kaynak snapshot'ı yine güncellendi.")
    lines.extend(f"Not: {safe_text(value)}" for value in report.notes)
    lines.extend([
        "Sonuçlar doğrulanmış ihlal hükmü değildir.",
        "Yeni bildirimler: ./xti inbox",
    ])
    return lines


def monitor_lines(report: RansomwareWatchMonitorReport) -> list[str]:
    reason = "tur sınırı" if report.stop_reason == "cycles" else "süre sınırı"
    labels = {"complete": "Tamamlandı", "failed": "Başarısız"}
    lines = [
        "Ransomware ön plan izlemesi tamamlandı.",
        f"Bitiş nedeni: {reason} | tamamlanan tur: "
        f"{report.completed_cycles}/{report.planned_cycles}",
        f"Kaynak sonuçları: {report.successful_cycles} başarılı | "
        f"{report.failed_cycles} başarısız",
        f"Tamamlanan kuruluş/domain izlemesi: {report.completed_watch_runs} | "
        f"sessiz başlangıç: {report.baseline_watch_runs}",
        f"Tur bazlı eşleşme toplamı: {report.total_count} | yeni {report.added_count} | "
        f"değişen {report.updated_count} | aynı {report.unchanged_count} | "
        f"pencereden çıkan {report.removed_count}",
        f"Yerel bildirim: {report.notification_count} | "
        f"geçen süre: {report.elapsed_seconds:.1f} saniye",
        "Turlar:",
    ]
    if report.session_id is not None:
        lines.insert(1, f"Kalıcı oturum: {safe_text(report.session_id)}")
    for item in report.cycles:
        lines.append(
            f"  {item.cycle}. tur | {labels[item.source_status]} | kaynak kayıt "
            f"{item.source_record_count} | izleme "
            f"{item.completed_watch_count}/{item.planned_watch_count} "
            f"(sessiz başlangıç {item.baseline_watch_count}) | eşleşme "
            f"{item.total_count} | +{item.added_count} ~{item.updated_count} "
            f"={item.unchanged_count} -{item.removed_count} | bildirim "
            f"{item.notification_count} | {safe_text(item.source_run_id)}"
        )
        if item.source_error:
            lines.append(f"    Hata: {safe_text(item.source_error)}")
    if not report.cycles:
        lines.append("  Süre sınırı nedeniyle hiçbir tur başlatılmadı.")
    lines.extend(f"Not: {safe_text(value)}" for value in report.notes)
    lines.extend([
        "Oturum geçmişi: ./xti ransomware watch-monitor-list",
        "Kaynak geçmişi: ./xti ransomware status",
        "İzleme geçmişi: ./xti ransomware watch-list",
        "Yeni bildirimler: ./xti inbox",
    ])
    return lines


_MONITOR_SESSION_STATUS = {
    "running": "Açık / tamamlanmamış",
    "complete": "Tamamlandı",
    "partial": "Kaynak hatalarıyla tamamlandı",
    "interrupted": "Kullanıcı tarafından kesildi",
    "failed": "Hata ile durdu",
}

_MONITOR_STOP_REASON = {
    "": "henüz yok", "cycles": "tur sınırı", "duration": "süre sınırı",
    "interrupted": "Ctrl+C", "error": "çalışma veya kalıcı kayıt hatası",
}


def monitor_session_list_lines(
    records: tuple[RansomwareMonitorSession, ...],
) -> list[str]:
    lines = [f"Ransomware monitor oturumları: {len(records)}"]
    for session in records:
        finished = safe_text(session.finished_at) if session.finished_at else "bitmedi"
        lines.extend([
            f"  #{session.sequence} | {_MONITOR_SESSION_STATUS[session.status]} | "
            f"tur {session.completed_cycles}/{session.planned_cycles} | "
            f"kaynak hatası {session.failed_cycles}",
            f"    başlangıç {safe_text(session.started_at)} | bitiş {finished} | "
            f"{safe_text(session.id)}",
        ])
    if not records:
        lines.append("  Kayıtlı monitor oturumu yok.")
    lines.append("Açık oturum, işlemin beklenmedik biçimde kapandığı anlamına gelebilir.")
    return lines


def monitor_session_detail_lines(details: RansomwareMonitorSessionDetails) -> list[str]:
    session = details.session
    finished = safe_text(session.finished_at) if session.finished_at else "bitmedi"
    lines = [
        f"Ransomware monitor oturumu #{session.sequence}",
        f"Durum: {_MONITOR_SESSION_STATUS[session.status]} | "
        f"bitiş nedeni: {_MONITOR_STOP_REASON[session.stop_reason]}",
        f"Kimlik: {safe_text(session.id)}",
        f"Başlangıç: {safe_text(session.started_at)} | bitiş: {finished}",
        f"Plan: {session.planned_cycles} tur | aralık {session.interval_seconds} saniye | "
        f"süre {session.max_duration_seconds} saniye | izleme sınırı {session.max_watches}",
        f"Turlar: {session.completed_cycles}/{session.planned_cycles} | "
        f"başarılı {session.successful_cycles} | kaynak hatası {session.failed_cycles}",
        f"Kuruluş/domain çalışması: {session.completed_watch_runs} | "
        f"sessiz başlangıç {session.baseline_watch_runs} | "
        f"yerel bildirim {session.notification_count}",
        f"Tur bazlı eşleşme: {session.total_count} | +{session.added_count} "
        f"~{session.updated_count} ={session.unchanged_count} -{session.removed_count}",
        f"Kalıcı tur kanıtı: {details.total_cycle_count}; "
        f"{len(details.cycles)} gösteriliyor",
    ]
    if session.error:
        lines.append(f"Hata: {safe_text(session.error)}")
    for item in details.cycles:
        status = "Tamamlandı" if item.source_status == "complete" else "Başarısız"
        lines.append(
            f"  {item.cycle}. tur | {status} | kaynak kaydı "
            f"{item.source_record_count} | izleme {item.completed_watch_count}/"
            f"{item.planned_watch_count} (sessiz başlangıç {item.baseline_watch_count}) | "
            f"eşleşme {item.total_count} | bildirim {item.notification_count} | "
            f"{safe_text(item.source_run_id)}"
        )
        if item.source_error:
            lines.append(f"    Kaynak hatası: {safe_text(item.source_error)}")
    if not details.cycles:
        lines.append("  Tamamlanmış kalıcı tur yok.")
    lines.extend([
        "Açık durum tamamlandı demek değildir; ani kapanmada bilinmeyen durum korunur.",
        "Sayaçlar tur bazlıdır; aynı kayıt farklı turlarda yeniden sayılabilir.",
        "Ransomware kayıtları kamuya açık grup iddiasıdır; doğrulanmış ihlal değildir.",
    ])
    return lines


_TIMELINE_ACTIONS = {
    "first_seen": "İlk kez eşleşti",
    "updated": "Kaynak bilgisi değişti",
    "match_started": "Sonradan eşleşmeye başladı",
    "match_ended": "Eşleşme sona erdi",
    "removed": "Kaynak penceresinden çıktı",
    "reappeared": "Aynı iddia yeniden göründü",
}


def timeline_lines(report: RansomwareWatchTimelineReport) -> list[str]:
    watch = report.watch
    first = safe_text(report.first_complete_at) if report.first_complete_at else "yok"
    last = safe_text(report.last_complete_at) if report.last_complete_at else "yok"
    lines = [
        f"Ransomware iddia zaman çizelgesi: {safe_text(watch.display_name)}",
        f"Güncel tanım: {safe_text(watch.kind)} | {safe_text(watch.query)} | "
        f"{safe_text(watch.match_mode)} | {'etkin' if watch.active else 'geri çekilmiş'}",
        f"Kaynak kapsamı: {report.complete_source_run_count} başarılı snapshot | "
        f"{report.failed_source_run_count} kaynak hatası",
        f"İlk başarılı snapshot: {first} | son başarılı snapshot: {last}",
        f"Ayrı iddia kimliği: {report.distinct_claim_count} | son pencerede eşleşen: "
        f"{report.active_claim_count}",
        f"Değişmeden tekrar gözlem: {report.repeat_observation_count} | "
        f"yeniden görünme: {report.reappearance_count}",
        f"Olay: {report.total_event_count}; son {len(report.events)} olay "
        "zaman sırasıyla gösteriliyor",
    ]
    for event in report.events:
        claim = event.claim
        lines.extend([
            f"  {safe_text(event.observed_at)} | {_TIMELINE_ACTIONS[event.action]} | "
            f"{safe_text(claim.victim)}",
            f"    grup {safe_text(claim.group)} | iddia zamanı "
            f"{safe_text(claim.discovered_at)} | durum {safe_text(claim.status)} | "
            f"eşleşme {safe_text(event.matched_field)}="
            f"{safe_text(event.matched_value)}",
            f"    kaynak çalışması #{event.source_sequence} | "
            f"{safe_text(event.source_run_id)}",
        ])
    if not report.events:
        lines.append("  Kayıtlı kaynak geçmişinde bu güncel tanıma ait olay yok.")
    lines.extend(f"Not: {safe_text(value)}" for value in report.notes)
    return lines


_IDENTITY_EVIDENCE = {
    "group": "aynı grup",
    "victim": "aynı kuruluş adı",
    "discovered_at": "aynı kaynak keşif zamanı",
    "website": "aynı web alanı",
}

_IDENTITY_FIELDS = {
    "group": "grup",
    "victim": "kuruluş adı",
    "discovered_at": "kaynak keşif zamanı",
}


def identity_candidate_lines(
    report: RansomwareWatchIdentityCandidateReport,
) -> list[str]:
    watch = report.watch
    lines = [
        f"Ransomware olası aynı olay adayları: {safe_text(watch.display_name)}",
        f"Güncel tanım: {safe_text(watch.kind)} | {safe_text(watch.query)} | "
        f"{safe_text(watch.match_mode)} | "
        f"{'etkin' if watch.active else 'geri çekilmiş'}",
        f"Kaynak kapsamı: {report.complete_source_run_count} başarılı snapshot | "
        f"{report.failed_source_run_count} kaynak hatası",
        f"İncelenen açıklanabilir kimlik geçişi: {report.transition_pair_count}",
        f"Aday: {report.total_candidate_count}; son {len(report.candidates)} aday "
        "zaman sırasıyla gösteriliyor",
    ]
    for candidate in report.candidates:
        older, newer = candidate.older_claim, candidate.newer_claim
        common = ", ".join(
            _IDENTITY_EVIDENCE[value] for value in candidate.common_evidence
        )
        changed = ", ".join(
            _IDENTITY_FIELDS[value] for value in candidate.changed_identity_fields
        )
        gap = (
            "aynı snapshot geçişi" if candidate.successful_snapshot_gap == 0
            else "hemen sonraki başarılı snapshot"
        )
        match_state = (
            f"eski {'eşleşiyor' if candidate.older_matches_watch else 'eşleşmiyor'}, "
            f"yeni {'eşleşiyor' if candidate.newer_matches_watch else 'eşleşmiyor'}"
        )
        review = candidate.current_review
        review_text = (
            _IDENTITY_REVIEW_DECISIONS[review.decision]
            if review is not None else "henüz karar verilmedi"
        )
        lines.extend([
            f"  {safe_text(candidate.transition_observed_at)} | {gap} | {match_state}",
            f"    aday kimliği: {safe_text(candidate.id)} | karar: {review_text}",
            f"    eski: {safe_text(older.victim)} | grup {safe_text(older.group)} | "
            f"iddia zamanı {safe_text(older.discovered_at)}",
            f"    yeni: {safe_text(newer.victim)} | grup {safe_text(newer.group)} | "
            f"iddia zamanı {safe_text(newer.discovered_at)}",
            f"    ortak kanıt: {safe_text(common)} | değişen kimlik alanı: "
            f"{safe_text(changed)}",
            f"    kaynak çalışması #{candidate.transition_source_sequence} | "
            f"{safe_text(candidate.transition_source_run_id)}",
        ])
    if not report.candidates:
        lines.append("  Kayıtlı dönemde bu dar kurallara uyan aday yok.")
    lines.extend(f"Not: {safe_text(value)}" for value in report.notes)
    return lines


_IDENTITY_REVIEW_DECISIONS = {
    "possible_same": "aynı olay olabilir",
    "different": "farklı olay",
    "uncertain": "belirsiz",
}


def identity_review_detail_lines(
    details: RansomwareIdentityReviewDetails,
) -> list[str]:
    candidate, current = details.candidate, details.current
    older, newer = candidate.older_claim, candidate.newer_claim
    lines = [
        f"Ransomware kimlik adayı kararı: {safe_text(candidate.id)}",
        f"Güncel karar: {_IDENTITY_REVIEW_DECISIONS[current.decision]} | "
        f"{safe_text(current.reason)}",
        f"Son karar zamanı: {safe_text(current.reviewed_at)} | "
        f"karar olayı: {current.event_count}",
        f"Eski kayıt: {safe_text(older.victim)} | grup {safe_text(older.group)} | "
        f"iddia zamanı {safe_text(older.discovered_at)}",
        f"Yeni kayıt: {safe_text(newer.victim)} | grup {safe_text(newer.group)} | "
        f"iddia zamanı {safe_text(newer.discovered_at)}",
        f"Karar geçmişi: {details.total_event_count}; son {len(details.events)} olay "
        "zaman sırasıyla gösteriliyor",
    ]
    for event in details.events:
        lines.append(
            f"  {safe_text(event.recorded_at)} | "
            f"{_IDENTITY_REVIEW_DECISIONS[event.decision]} | {safe_text(event.reason)} | "
            f"{safe_text(event.id)}"
        )
    lines.extend([
        "Karar analist yorumudur; kaynak kimliklerini veya zaman çizelgesini birleştirmez.",
        "Aynı olay olabilir kararı doğrulanmış ihlal ya da kesin olay özdeşliği değildir.",
    ])
    return lines


def identity_review_mutation_lines(
    result: RansomwareIdentityReviewMutation,
) -> list[str]:
    labels = {
        "recorded": "Karar kaydedildi.",
        "updated": "Yeni karar olayı eklendi; önceki karar korundu.",
        "unchanged": "Aynı karar ve gerekçe zaten kayıtlı; yeni olay oluşturulmadı.",
    }
    return [labels[result.action], *identity_review_detail_lines(result.details)]
