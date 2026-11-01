"""Terminal rendering for durable social username watch evidence."""

from xti.domain.brand_username_watches import (
    BrandUsernameWatchBatchReport,
    BrandUsernameWatchDetails,
    BrandUsernameWatchMonitorReport,
    BrandUsernameWatchMutation,
    BrandUsernameWatchRunReport,
    BrandUsernameWatchSummary,
)
from xti.domain.brand_username_reviews import (
    BrandUsernameReviewDetails,
    BrandUsernameReviewMutation,
    brand_username_review_candidate_id,
)
from xti.interfaces.text import safe_text


_ACTIONS = {
    "added": "eklendi",
    "updated": "güncellendi",
    "reactivated": "yeniden etkinleştirildi",
    "revoked": "geri çekildi",
    "baseline_found": "başlangıçta bulundu, doğrulanmadı",
    "baseline_unreported": "başlangıçta raporlanmadı",
    "newly_found": "yeni bulundu, doğrulanmadı",
    "changed": "profil adresi değişti",
    "unchanged_found": "bulundu, değişmedi",
    "no_longer_reported": "artık raporlanmadı",
    "unchanged_unreported": "raporlanmadı, değişmedi",
}

_DECISIONS = {
    "known_official": "resmî / meşru olarak işaretlendi",
    "possible_impersonation": "olası taklit olarak işaretlendi",
    "uncertain": "belirsiz olarak işaretlendi",
}

_SOURCES = {"maigret": "Maigret", "sherlock": "Sherlock"}


def mutation_lines(result: BrandUsernameWatchMutation) -> list[str]:
    watch = result.watch
    return [
        f"Sosyal kullanıcı adı izlemesi {_ACTIONS[result.action]}: "
        f"{safe_text(watch.display_name)}",
        f"Kullanıcı adı: {safe_text(watch.username)}",
        f"Kaynak: {_SOURCES[watch.source_key]}",
        "Platformlar: " + ", ".join(safe_text(item) for item in watch.platforms),
        f"Kimlik: {safe_text(watch.id)}",
        "İzleme yalnız açık kullanıcı adı profil işaretlerini kullanır.",
    ]


def list_lines(
    records: tuple[BrandUsernameWatchSummary, ...], *, active_only: bool,
) -> list[str]:
    lines = [
        f"Sosyal kullanıcı adı izlemeleri: {len(records)} | "
        f"{'yalnız etkin' if active_only else 'etkin + geri çekilmiş'}"
    ]
    for value in records:
        watch, last = value.watch, value.last_run
        lines.extend([
            f"  {safe_text(watch.display_name)} | @{safe_text(watch.username)} | "
            f"{_SOURCES[watch.source_key]} | "
            f"{'etkin' if watch.active else 'geri çekilmiş'}",
            f"    platform: {len(watch.platforms)} | çalışma: {value.run_count} | "
            f"son: {safe_text(last.recorded_at) if last else 'henüz yok'} | "
            f"{safe_text(watch.id)}",
        ])
    if not records:
        lines.append("  Kayıtlı sosyal kullanıcı adı izlemesi yok.")
    return lines


def detail_lines(details: BrandUsernameWatchDetails) -> list[str]:
    watch = details.watch
    lines = [
        f"Sosyal kullanıcı adı izlemesi: {safe_text(watch.display_name)}",
        f"Kullanıcı adı: @{safe_text(watch.username)} | "
        f"{'etkin' if watch.active else 'geri çekilmiş'}",
        f"Kaynak: {_SOURCES[watch.source_key]}",
        "Platformlar: " + ", ".join(safe_text(item) for item in watch.platforms),
        f"Çalışmalar: {details.total_run_count}; {len(details.runs)} gösteriliyor",
    ]
    for run in details.runs:
        if run.status == "failed":
            lines.append(
                f"  {safe_text(run.recorded_at)} | kaynak hatası | "
                f"{safe_text(run.error or '')} | {safe_text(run.id)}"
            )
        else:
            lines.append(
                f"  {safe_text(run.recorded_at)} | bulunan {run.found_count} | "
                f"yeni {run.newly_found_count} | artık raporlanmayan "
                f"{run.no_longer_reported_count} | {safe_text(run.id)}"
            )
    lines.append(
        f"Tanım geçmişi: {details.total_event_count}; {len(details.events)} gösteriliyor"
    )
    for event in details.events:
        reason = f" | {safe_text(event.reason)}" if event.reason else ""
        lines.append(
            f"  {safe_text(event.recorded_at)} | {_ACTIONS[event.action]}{reason}"
        )
    return lines


def run_lines(report: BrandUsernameWatchRunReport) -> list[str]:
    run = report.run
    lines = [
        f"Sosyal kullanıcı adı izleme çalışması: "
        f"{safe_text(report.watch.display_name)}",
        f"Kullanıcı adı: @{safe_text(report.watch.username)} | "
        f"kaynak {_SOURCES[report.watch.source_key]} | çalışma {safe_text(run.id)}",
    ]
    if run.status == "failed":
        lines.extend([
            f"Kaynak hatası: {safe_text(run.error or '')}",
            "Önceki başarılı ölçüm korunmuştur; bu hata hesap yok veya kaldırıldı değildir.",
        ])
        return lines
    lines.extend([
        f"Platform {run.platform_count} | bulunan {run.found_count} | "
        f"raporlanmayan {run.unreported_count}",
        f"Yeni bulunan {run.newly_found_count} | değişen {run.changed_count} | "
        f"artık raporlanmayan {run.no_longer_reported_count} | "
        f"bulunup değişmeyen {run.unchanged_found_count}",
        f"Sonuç kaydı: {report.total_item_count}; {len(report.items)} gösteriliyor",
    ])
    if report.is_baseline:
        lines.append(
            "İlk başarılı çalışma sessiz başlangıçtır; bulunan profiller yeni alarm değildir."
        )
    elif report.attention_count:
        lines.append(f"İnsan inceleme adayı değişiklik: {report.attention_count}")
    for item in report.items:
        suffix = f" | {safe_text(item.profile_url)}" if item.profile_url else ""
        lines.append(
            f"  {safe_text(item.platform)} | {_ACTIONS[item.action]}{suffix}"
        )
        if item.status == "found_unverified":
            candidate_id = brand_username_review_candidate_id(
                watch_id=report.watch.id,
                definition_sha256=run.definition_sha256,
                platform=item.platform,
                state_sha256=item.state_sha256,
            )
            lines.append(f"    inceleme adayı: {safe_text(candidate_id)}")
            if item.current_review is None:
                lines.append("    kullanıcı kararı: henüz yok")
            else:
                review = item.current_review
                lines.append(
                    f"    kullanıcı kararı: {_DECISIONS[review.decision]} | "
                    f"{safe_text(review.reason)} | {safe_text(review.reviewed_at)}"
                )
    if not report.items:
        lines.append("  Sonuç öğesi yok.")
    elif report.total_item_count > len(report.items):
        lines.append(
            f"  {report.total_item_count - len(report.items)} kayıt görünüm sınırı dışında."
        )
    lines.extend([
        "Raporlanmadı; hesap yok, silindi veya güvenli anlamına gelmez.",
        "Bulunan profil sahiplik veya taklit kanıtı değildir; insan incelemesi gerekir.",
    ])
    return lines


def batch_lines(report: BrandUsernameWatchBatchReport) -> list[str]:
    lines = [
        "Sosyal kullanıcı adı toplu izlemesi tamamlandı.",
        f"Tamamlanan izleme: {report.completed_watch_count}/"
        f"{report.planned_watch_count} | başarılı {report.successful_watch_count} | "
        f"kaynak hatası {report.failed_watch_count}",
        f"Planlanan platform: {report.platform_count} | "
        f"bulunan {report.found_count}",
        f"Yeni bulunan {report.newly_found_count} | değişen {report.changed_count} | "
        f"artık raporlanmayan {report.no_longer_reported_count} | "
        f"inceleme adayı değişiklik {report.attention_count}",
        "İzlemeler:",
    ]
    for item in report.items:
        if item.status == "failed":
            lines.append(
                f"  {item.position}. {safe_text(item.display_name)} | "
                f"{_SOURCES[item.source_key]} | kaynak hatası | "
                f"{safe_text(item.error or '')} | {safe_text(item.run_id)}"
            )
        else:
            lines.append(
                f"  {item.position}. {safe_text(item.display_name)} | "
                f"{_SOURCES[item.source_key]} | platform "
                f"{item.platform_count} | bulunan {item.found_count} | yeni "
                f"{item.newly_found_count} | değişen {item.changed_count} | "
                f"{safe_text(item.run_id)}"
            )
    if not report.items:
        lines.append("  Çalıştırılacak etkin sosyal kullanıcı adı izlemesi yok.")
    lines.extend(f"Not: {safe_text(value)}" for value in report.notes)
    lines.append("Çalışma geçmişi: ./xti brand watch-list")
    return lines


def monitor_lines(report: BrandUsernameWatchMonitorReport) -> list[str]:
    reason = "tur sınırı" if report.stop_reason == "cycles" else "süre sınırı"
    lines = [
        f"Sosyal kullanıcı adı izlemesi tamamlandı: "
        f"{safe_text(report.watch.display_name)}",
        f"Kaynak: {_SOURCES[report.watch.source_key]}",
        f"Bitiş nedeni: {reason} | tamamlanan tur: "
        f"{report.completed_cycles}/{report.planned_cycles}",
        f"Başarılı tur: {report.successful_cycles} | "
        f"kaynak hatası: {report.failed_cycles} | "
        f"geçen süre: {report.elapsed_seconds:.1f} saniye",
        f"Toplam bulunan: {report.found_count} | yeni {report.newly_found_count} | "
        f"değişen {report.changed_count} | artık raporlanmayan "
        f"{report.no_longer_reported_count} | inceleme adayı değişiklik "
        f"{report.attention_count}",
        "Turlar:",
    ]
    for cycle in report.cycles:
        if cycle.status == "failed":
            lines.append(
                f"  {cycle.cycle}. tur | kaynak hatası | "
                f"{safe_text(cycle.error or '')} | {safe_text(cycle.run_id)}"
            )
        else:
            lines.append(
                f"  {cycle.cycle}. tur | platform {cycle.platform_count} | "
                f"bulunan {cycle.found_count} | yeni {cycle.newly_found_count} | "
                f"değişen {cycle.changed_count} | {safe_text(cycle.run_id)}"
            )
    if not report.cycles:
        lines.append("  Süre sınırı nedeniyle çalışma turu başlatılmadı.")
    lines.extend(f"Not: {safe_text(value)}" for value in report.notes)
    lines.append(
        f"İzleme geçmişi: ./xti brand watch-show {safe_text(report.watch.id)}"
    )
    return lines


def review_mutation_lines(result: BrandUsernameReviewMutation) -> list[str]:
    details = result.details
    action = {
        "recorded": "kaydedildi",
        "updated": "güncellendi",
        "unchanged": "değişmedi",
    }[result.action]
    lines = [
        f"Profil kullanıcı kararı {action}: {_DECISIONS[details.current.decision]}",
        f"Platform: {safe_text(details.candidate.platform)} | "
        f"@{safe_text(details.candidate.username)}",
        f"Profil: {safe_text(details.candidate.profile_url)}",
        f"Gerekçe: {safe_text(details.current.reason)}",
        f"İnceleme adayı: {safe_text(details.candidate.id)}",
        "Karar yalnız bu tam profil adresi ve gözlem durumuna bağlıdır.",
    ]
    if result.notification_created:
        lines.extend([
            f"Ortak yerel kutuya bildirim eklendi: {safe_text(result.notification_id)}",
            "Bildirim yalnız açık olası taklit kullanıcı kararına dayanır.",
        ])
    elif result.notification_id is not None:
        lines.extend([
            f"Bu tam profil için önceki bildirim korundu: "
            f"{safe_text(result.notification_id)}",
            "Yeni veya yinelenen bildirim oluşturulmadı.",
        ])
    else:
        lines.append("Resmî/meşru veya belirsiz karar ortak kutu bildirimi üretmez.")
    lines.append("Kullanıcı kararı teknik sahiplik doğrulaması değildir.")
    return lines


def review_detail_lines(details: BrandUsernameReviewDetails) -> list[str]:
    candidate = details.candidate
    lines = [
        f"Profil inceleme adayı: {safe_text(candidate.id)}",
        f"Platform: {safe_text(candidate.platform)} | @{safe_text(candidate.username)}",
        f"Profil: {safe_text(candidate.profile_url)}",
        f"Gözlem: {safe_text(candidate.observed_at)} | çalışma {safe_text(candidate.run_id)}",
        f"Güncel kullanıcı kararı: {_DECISIONS[details.current.decision]}",
        f"Gerekçe: {safe_text(details.current.reason)}",
        f"Karar geçmişi: {details.total_event_count}; {len(details.events)} gösteriliyor",
    ]
    for event in details.events:
        lines.append(
            f"  {safe_text(event.recorded_at)} | {_DECISIONS[event.decision]} | "
            f"{safe_text(event.reason)}"
        )
    lines.append("Karar yalnız kayıtlı tam profil kanıtına bağlıdır; otomatik alarm değildir.")
    return lines
