"""Safe terminal rendering for local storage and recovery readiness."""

from xti.domain.storage_readiness import StorageReadinessReport
from xti.interfaces.text import safe_text


_DISK = {"sufficient": "Yeterli çalışma payı", "low": "Düşük boş alan"}
_BACKUP = {
    "missing": "Yönetilen yedek yok",
    "invalid": "Son yedek doğrulanamadı",
    "current": "Son yedek güncel ve doğrulandı",
    "stale": "Son doğrulanmış yedek eski",
    "clock_error": "Son yedek zamanı tutarsız",
}
_RECOVERY = {"ready": "Yerel hazırlık uygun", "attention": "İnceleme gerekiyor"}
_PERMISSIONS = {
    "private": "Yalnız sahibine açık",
    "missing": "Klasör henüz yok",
    "unknown": "İzinler doğrulanamadı",
    "unreadable": "İzinler okunamadı",
    "invalid_type": "Gerçek bir klasör değil",
    "foreign_owner": "Başka kullanıcıya ait",
    "writable_by_others": "Grup veya diğer kullanıcılar yazabilir",
    "accessible_by_others": "Grup veya diğer kullanıcılara erişim izni var",
}
_NEXT = {
    "create_backup": "Yeni tutarlı yedek oluştur: ./xti backup",
    "free_disk_space": "Yeni yazma/yedek öncesi diskte alan aç",
    "review_retention": "Saklama önizlemesini incele: ./xti storage cleanup",
    "copy_off_device": "Doğrulanmış yedeği ayrı fiziksel ortama kopyala",
    "test_restore": "Yedeği boş bir klasöre geri yükleyerek tatbikat yap",
    "review_directory_permissions": "Kayıt/yedek klasörlerinin sahibini ve izinlerini incele; kişisel klasörler için 0700 kullan",
}


def _size(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    unit = units[0]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    return f"{amount:.1f} {unit}"


def report_lines(report: StorageReadinessReport) -> list[str]:
    usage = report.usage
    lines = [
        "Depolama ve kurtarma hazırlığı",
        f"Kayıt klasörü: {safe_text(report.data_directory)}",
        f"Klasör kullanımı: {_size(report.data_directory_bytes)} | "
        f"Yedekler: {_size(report.backup_directory_bytes)}",
        f"Disk: {_DISK[report.disk_status]} | Kullanılabilir: "
        f"{_size(report.disk_available_bytes)} | Koruma eşiği: "
        f"{_size(report.required_free_bytes)}",
        f"Veritabanı: {_size(usage.database_bytes)} | SQLite yeniden kullanılabilir: "
        f"{_size(usage.reusable_bytes)}",
        f"Yönetilen yedek: {report.managed_backup_count} | {_BACKUP[report.backup_status]}",
    ]
    if report.latest_backup_path is not None:
        lines.append(
            f"Son yedek: {safe_text(report.latest_backup_path)} | "
            f"{_size(report.latest_backup_bytes or 0)} | "
            f"{safe_text(report.latest_backup_modified_at)}"
        )
    if report.backup_error is not None:
        lines.append(f"Yedek doğrulama hatası: {safe_text(report.backup_error)}")
    for item in report.directory_permissions:
        lines.append(
            f"Klasör izni: {safe_text(item.path)} | {safe_text(item.mode or 'bilinmiyor')} | "
            f"{_PERMISSIONS.get(item.status, 'İzinler doğrulanamadı')}"
        )
    lines.extend([
        f"Saklama ({report.retention_days} gün): temizliğe uygun "
        f"{report.cleanup_eligible_count}, korunan {report.cleanup_protected_count}, "
        f"zamanı sorunlu {report.cleanup_invalid_time_count}",
        f"Yerel kurtarma: {_RECOVERY[report.local_recovery_status]}",
        "Ayrı ortam yedeği: Bilinmiyor | Geri yükleme tatbikatı: Kaydedilmedi",
    ])
    if not report.scan_complete:
        lines.append("Klasör taraması güvenli dosya sınırına ulaştı; toplamlar eksik olabilir.")
    if report.ignored_entry_count:
        lines.append(
            f"Takip edilmeyen sembolik/özel veya yedek dışı öğe: "
            f"{report.ignored_entry_count}"
        )
    lines.append("Sonraki adımlar:")
    if not report.next_steps:
        lines.append("  Şu anda zorunlu yerel adım yok.")
    else:
        lines.extend(f"  {_NEXT[item]}" for item in report.next_steps)
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
