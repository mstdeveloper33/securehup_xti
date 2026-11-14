"""Generate user-unit files only; no activation or generated shell expressions."""

import os
from pathlib import Path
import shlex
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from xti.adapters.sqlite import StorageError
from xti.domain.assets import ValidationError
from xti.domain.scheduling import GeneratedSchedule, normalize_schedule


def unit_argument(value: str, *, environment: bool = True) -> str:
    """Quote one systemd argument, separately from shell command quoting."""
    if not isinstance(value, str) or not value or len(value) > 4096 or any(not char.isprintable() for char in value):
        raise ValidationError("Zamanlama yolu veya argümanı güvenli tek satır olmalı.")
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if environment:
        value = value.replace("$", "$$")
    return '"' + value + '"'


class SystemdScheduleWriter:
    def __init__(self, launcher: Path, database: Path):
        self.launcher = Path(launcher).expanduser().absolute()
        self.database = Path(database).expanduser().absolute()

    def publish(self, profile, *, output, spec):
        spec = normalize_schedule(spec)
        try:
            ZoneInfo(spec.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValidationError("Saat dilimi bulunamadı; UTC veya kurulu bir IANA saat dilimi seçin.") from error
        if self.launcher.is_symlink() or not self.launcher.is_file() or not os.access(self.launcher, os.X_OK):
            raise ValidationError("Zamanlama için çalıştırılabilir gerçek xti başlatıcı dosyası gerekli.")
        launcher = self.launcher.resolve(strict=True)
        database = self.database.parent.resolve(strict=True) / self.database.name
        if database.is_symlink() or not database.is_file():
            raise ValidationError("Zamanlama için mevcut gerçek veritabanı gerekli.")
        if str(UUID(profile.id)) != profile.id:
            raise ValidationError("Zamanlama profil kimliği geçersiz.")
        output_path = Path(output).expanduser().absolute()
        unit_argument(str(output_path), environment=False)
        if output_path.exists() or output_path.is_symlink():
            raise ValidationError("Zamanlama çıktı klasörü zaten var; yeni bir klasör seçin.")
        try:
            parent = output_path.parent.resolve(strict=True)
        except OSError as error:
            raise ValidationError("Zamanlama çıktısının üst klasörü mevcut olmalı.") from error
        output_path = parent / output_path.name
        unit_name = f"xti-collect-{profile.id}"
        service_path, timer_path = output_path / (unit_name + ".service"), output_path / (unit_name + ".timer")
        instructions = output_path / "README.txt"
        calendar = (spec.weekday + " " if spec.weekday else "") + f"*-*-* {spec.at}:00 {spec.timezone}"
        command = [str(launcher), "--data-dir", str(database.parent)]
        # systemd restricts characters in the executable pathname. The existing
        # POSIX launcher is passed as data to a fixed interpreter, never '-c'.
        # ':' suppresses environment expansion and keeps literal '$' in argv.
        executable = unit_argument(":/bin/sh", environment=False)
        def command_line(arguments):
            return executable + " " + " ".join(unit_argument(value, environment=False) for value in [str(launcher), *arguments])
        prepare = command_line([*command[1:], "schedule", "prepare", "--keep", str(spec.keep), "--", profile.display_name])
        collect = command_line([*command[1:], "collect", "--profile=" + profile.display_name])
        service = (
            "[Unit]\n" + f"Description=XTI saved profile {profile.id}\n\n"
            "[Service]\nType=oneshot\n"
            f"ExecStartPre={prepare}\nExecStart={collect}\n"
            "Restart=no\nTimeoutStartSec=infinity\nUMask=0077\n"
            "StandardOutput=journal\nStandardError=journal\n"
        )
        timer = (
            "[Unit]\n" + f"Description=XTI schedule {profile.id}\n\n"
            "[Timer]\n" + f"OnCalendar={calendar}\nUnit={unit_name}.service\n"
            "Persistent=true\nRandomizedDelaySec=30s\nFixedRandomDelay=true\nAccuracySec=1s\n\n"
            "[Install]\nWantedBy=timers.target\n"
        )
        lines = [
            "Bu dosyalar hizmeti başlatmadı. Linux ve systemd kullanıcı oturumu gerekir (systemd 247+).",
            "Önce dosyaları ve kayıtlı profilin güncel planını inceleyin; sonra aşağıdaki komutları çalıştırın:",
            shlex.join([*command, "collect", "--profile=" + profile.display_name, "--plan"]),
            shlex.join(["systemd-analyze", "--user", "verify", str(service_path), str(timer_path)]),
            shlex.join(["systemctl", "--user", "link", str(service_path), str(timer_path)]),
            "systemctl --user daemon-reload",
            shlex.join(["systemctl", "--user", "enable", "--now", unit_name + ".timer"]),
            "", "Durum ve kayıtlar:",
            shlex.join(["systemctl", "--user", "status", unit_name + ".timer", unit_name + ".service"]),
            shlex.join(["journalctl", "--user", "-u", unit_name + ".service", "-n", "100"]),
            "", "Durdurma:",
            shlex.join(["systemctl", "--user", "disable", "--now", unit_name + ".timer"]),
            "", "Aynı profilin saatini, yolunu veya yedek sayısını yenileme:",
            "Yeni bir çıktı klasörü üretin. Eski dosyalar değiştirilmez; profil kimliğine bağlı hizmet adları aynı kalır.",
            "Yeni dosyaları doğruladıktan sonra eski bağlantıları kaldırıp yukarıdaki link, daemon-reload ve enable komutlarını uygulayın:",
            shlex.join(["systemctl", "--user", "disable", "--now", unit_name + ".timer"]),
            shlex.join(["systemctl", "--user", "disable", unit_name + ".service"]),
            "Yalnız profil içeriğini güncellemek için profiles save yeterlidir; dosyaları yeniden üretmek gerekmez.",
            "", "Profilin sonraki kaydetmelerindeki güncel tanımı kullanılır. Profil geri çekilirse çalışma durur.",
            "Çalışma öncesi ortak kilit, plan, disk alanı, kesilmiş oturum ve doğrulanmış yerel yedek kontrol edilir.",
            f"Yalnız scheduled-backups içindeki sahiplik kaydı doğrulanan son {spec.keep} yedek tutulur.",
            "Elle alınmış/geçiş yedekleri silinmez. Aynı diskteki kopya disk arızasına karşı uzak yedek değildir.",
            "Kısmi/kaynak hatası kodu 3, kilit dolu kodu 4 olarak kalır; anında yeniden deneme yoktur.",
            "Bilgisayar kapalıyken kaçırılan zaman için açılışta bir çalışma yapılabilir; her kaçırılan tur tekrarlanmaz.",
            "Kullanıcı oturumu kapanınca kullanıcı hizmetlerinin çalışması sistemin linger ayarına bağlıdır.",
            "Bu üretim işlemi Linux hizmet çalışmasını doğrulamaz; otomatik etkinleştirme veya linger ayarı yapmaz.",
        ]
        try:
            output_path.mkdir(mode=0o700)
            for destination, content in ((service_path, service), (timer_path, timer), (instructions, "\n".join(lines) + "\n")):
                with destination.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(content)
                    stream.flush(); os.fsync(stream.fileno())
                destination.chmod(0o600)
        except OSError as error:
            # Leave partial generated files visible; never replace or remove an existing output.
            raise StorageError("Zamanlama dosyaları tamamlanamadı; mevcut dosyalar korunuyor. Yeni bir çıktı klasörü seçin.") from error
        return GeneratedSchedule(str(output_path), str(service_path), str(timer_path), str(instructions), unit_name, calendar, (
            "Yalnız dosyalar üretildi; Linux hizmeti etkinleştirilmedi.",
            "Zamanlayıcı kayıtlı profilin çalıştırma anındaki güncel tanımını kullanır.",
        ))
