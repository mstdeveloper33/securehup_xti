"""Terminal rendering for exposure-scoped NVD refresh planning."""

from xti.domain.tracked_nvd_refresh import (
    TrackedNvdRefreshPlan,
    TrackedNvdRefreshResult,
)
from xti.interfaces.text import safe_text


def _age(seconds: int) -> str:
    if seconds < 0:
        return "sistem saatinden ileride"
    hours = seconds // 3600
    return f"{hours} saat"


def plan_lines(plan: TrackedNvdRefreshPlan) -> list[str]:
    lines = [
        "Maruziyetlerle ilgili NVD yenileme planı",
        f"İncelenen maruziyet: {plan.examined_exposure_count} | "
        f"İzlenen benzersiz CVE: {plan.tracked_cve_count}",
        f"Güncel: {plan.current_cve_count} | Yenileme zamanı gelen: "
        f"{plan.refresh_due_count} | Saat sorunu: {plan.clock_error_count}",
        f"Eşik: {plan.stale_after_hours} saat | "
        f"Kapanmış: {'dahil' if plan.include_closed else 'hariç'} | "
        f"Bastırılmış: {'dahil' if plan.include_suppressed else 'hariç'}",
    ]
    if not plan.items:
        lines.append("Yenileme gerektiren ilgili NVD kaydı yok.")
    for item in plan.items:
        state = "yenileme zamanı geldi" if item.freshness == "stale" else "sistem saati sorunu"
        lines.extend([
            "",
            f"{safe_text(item.cve_id)} | {state}",
            f"  Son başarılı kontrol: {safe_text(item.last_success_at)} | "
            f"Yaş: {_age(item.age_seconds)}",
            f"  Bağlı inceleme: {item.exposure_count} | Açık: "
            f"{item.open_exposure_count} | Kapanmış: {item.closed_exposure_count}",
        ])
    if plan.truncated:
        lines.append(f"İlk {len(plan.items)} dikkat kaydı gösterildi; sınırı artırabilirsin.")
    lines.extend(["", *plan.notes])
    return lines


def result_lines(result: TrackedNvdRefreshResult) -> list[str]:
    lines = [
        "İlgili NVD yenileme çalışması",
        f"Durum: {'Tamamlandı' if result.status == 'complete' else 'İlk hatada durdu'} | "
        f"Planlanan: {len(result.planned_candidates)} | Tamamlanan deneme: "
        f"{len(result.runs)}",
        f"Plandaki yenileme adayı: {result.plan_refresh_due_count} | "
        f"Bütün dikkat kayıtları: {result.plan_attention_count}",
        f"Anahtarsız istek aralığı: en az {result.minimum_interval_seconds} saniye",
    ]
    for run in result.runs:
        cve_id = run.source_url.rsplit("=", 1)[-1]
        lines.append(
            f"  {safe_text(cve_id)} | "
            f"{'tamamlandı' if run.status == 'complete' else 'başarısız'} | "
            f"yeni {run.created_count}, değişen {run.updated_count}, "
            f"aynı {run.unchanged_count}"
        )
        if run.error is not None:
            lines.append(f"    {safe_text(run.error)}")
    if not result.planned_candidates:
        lines.append("Ağ isteği gerektiren eski kayıt yoktu.")
    lines.extend(["", *result.notes])
    return lines
