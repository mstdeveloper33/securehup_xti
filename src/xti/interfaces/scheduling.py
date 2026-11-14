"""Argument declarations and escaped scheduling output; entry point wires adapters."""

from xti.interfaces.text import safe_text


def register_schedule_commands(subparsers):
    parser = subparsers.add_parser("schedule", help="Kayıtlı profil için Linux zamanlama dosyaları ve yerel bakım")
    commands = parser.add_subparsers(dest="schedule_command", required=True)
    generate = commands.add_parser("generate", help="Yeni klasöre hizmet/zamanlayıcı dosyaları üret; etkinleştirmez")
    generate.add_argument("profile")
    generate.add_argument("--output", required=True)
    generate.add_argument("--at", required=True)
    generate.add_argument("--timezone", default="UTC")
    generate.add_argument("--weekday", choices=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))
    generate.add_argument("--keep", type=int, default=7)
    prepare = commands.add_parser("prepare", help="Profil planını kontrol et, kesilmiş oturumu kapat ve doğrulanmış yerel yedek al")
    prepare.add_argument("profile")
    prepare.add_argument("--keep", type=int, default=7)


def generated_lines(result):
    return [
        "Linux zamanlama dosyaları hazır; hizmet etkinleştirilmedi.",
        f"Hizmet: {safe_text(result.service_file)}",
        f"Zamanlayıcı: {safe_text(result.timer_file)}",
        f"Takvim: {safe_text(result.calendar)}",
        f"İnceleme ve kurulum komutları: {safe_text(result.instructions_file)}",
        *(safe_text(note) for note in result.notes),
    ]


def preparation_lines(result):
    return [
        f"Zamanlama hazırlığı tamam: {safe_text(result.profile_name)} | revizyon {result.profile_revision}",
        f"Kapatılan kesilmiş oturum: {len(result.recovered_sessions)}",
        f"Yedek: {safe_text(result.backup.path)}",
        f"Yeni dosyaya kurtarma doğrulandı: {'evet' if result.backup.restore_verified else 'hayır'}",
        f"Yalnız yönetilen eski yedeklerden kaldırılan: {len(result.backup.retired_paths)}",
        *(safe_text(warning) for warning in result.backup.warnings),
    ]
