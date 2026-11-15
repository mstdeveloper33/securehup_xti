"""File-only Linux scheduling for budgeted company-content groups."""

import os
from pathlib import Path
import shlex
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from xti.adapters.sqlite import StorageError
from xti.adapters.systemd_schedule import unit_argument
from xti.adapters.tavily_search import default_tavily_key_path
from xti.domain.assets import ValidationError
from xti.domain.mentions import mention_uuid
from xti.domain.scheduling import GeneratedSchedule, normalize_schedule


class SystemdMentionScheduleWriter:
    """Publish inspectable user units; never read a key or activate a service."""

    def __init__(self, launcher: Path, database: Path):
        self.launcher = Path(launcher).expanduser().absolute()
        self.database = Path(database).expanduser().absolute()

    def publish(self, group, *, output, spec, api_key_file=None):
        spec = normalize_schedule(spec)
        identifier = mention_uuid(group.id)
        if getattr(group, "active", None) is not True:
            raise ValidationError("Kapalı içerik izleme grubu için zamanlama üretilemez.")
        calendar_hours = 168 if spec.weekday is not None else 24
        interval_hours = group.definition.interval_hours
        if type(interval_hours) is not int or not 1 <= interval_hours < calendar_hours:
            example = "haftalık için en çok 167 saat" if spec.weekday is not None else "günlük için 23 saat"
            raise ValidationError(f"Takvim aralığından kısa grup aralığı seçin ({example}).")
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
        try:
            key_path = Path(api_key_file if api_key_file is not None else default_tavily_key_path()).expanduser().absolute()
            output_path = Path(output).expanduser().absolute()
        except (TypeError, ValueError, RuntimeError) as error:
            raise ValidationError("Anahtar ve zamanlama çıktı yolları geçerli dosya yolları olmalı.") from error
        # Validate only the path. The key may be configured after generation;
        # its content and access permissions are checked by the collection run.
        unit_argument(str(key_path), environment=False)
        unit_argument(str(output_path), environment=False)
        if output_path.exists() or output_path.is_symlink():
            raise ValidationError("Zamanlama çıktı klasörü zaten var; yeni bir klasör seçin.")
        try:
            parent = output_path.parent.resolve(strict=True)
        except OSError as error:
            raise ValidationError("Zamanlama çıktısının üst klasörü mevcut olmalı.") from error
        output_path = parent / output_path.name
        unit_name = f"xti-mentions-{identifier}"
        service_path = output_path / (unit_name + ".service")
        timer_path = output_path / (unit_name + ".timer")
        instructions_path = output_path / "README.txt"
        calendar = (spec.weekday + " " if spec.weekday else "") + f"*-*-* {spec.at}:00 {spec.timezone}"
        command = [str(launcher), "--data-dir", str(database.parent), "mentions", "groups"]

        def unit_command(arguments):
            # A fixed interpreter receives the launcher path as data. No '-c',
            # shell expansion or systemd environment expansion is used.
            values = [str(launcher), *command[1:], *arguments]
            return unit_argument(":/bin/sh", environment=False) + " " + " ".join(
                unit_argument(value, environment=False) for value in values)

        prepare = unit_command(["prepare", identifier, "--keep", str(spec.keep),
                                "--calendar-hours", str(calendar_hours)])
        run = unit_command(["run", identifier, "--api-key-file", str(key_path)])
        service = (
            "[Unit]\n" + f"Description=XTI content monitoring group {identifier}\n\n"
            "[Service]\nType=oneshot\n"
            f"ExecStartPre={prepare}\nExecStart={run}\n"
            "Restart=no\nTimeoutStartSec=infinity\nUMask=0077\n"
            "StandardOutput=journal\nStandardError=journal\n"
        )
        timer = (
            "[Unit]\n" + f"Description=XTI content monitoring schedule {identifier}\n\n"
            "[Timer]\n" + f"OnCalendar={calendar}\nUnit={unit_name}.service\n"
            "Persistent=true\nRandomizedDelaySec=30s\nFixedRandomDelay=true\nAccuracySec=1s\n\n"
            "[Install]\nWantedBy=timers.target\n"
        )
        lines = [
            "Bu dosyalar hizmeti başlatmadı. Linux ve systemd kullanıcı oturumu gerekir (systemd 247+).",
            "Önce grubun güncel planını ve bu dosyaları inceleyin:",
            shlex.join([*command, "plan", identifier]),
            "", "Anahtar dosyası açık yoluyla seçilir; TAVILY_API_KEY ortam değişkeni kullanılmaz.",
            "Anahtar içeriği bu dosyalara alınmadı ve üretim sırasında okunmadı.",
            "Anahtarı henüz tanımlamadıysanız aşağıdaki komutla gizli terminal girişini kullanın:",
            shlex.join([str(launcher), "mentions", "configure", "--api-key-file", str(key_path)]),
            "Var olan anahtar dosyasının üzerine yazılmaz. Özel dosyanın izinleri çalışma anında kontrol edilir.",
            "", "Dosyaları doğrulayıp zamanlayıcıyı etkinleştirmek için:",
            shlex.join(["systemd-analyze", "--user", "verify", str(service_path), str(timer_path)]),
            shlex.join(["systemctl", "--user", "link", str(service_path), str(timer_path)]),
            "systemctl --user daemon-reload",
            shlex.join(["systemctl", "--user", "enable", "--now", unit_name + ".timer"]),
            "", "Durum ve kayıtlar:",
            shlex.join(["systemctl", "--user", "status", unit_name + ".timer", unit_name + ".service"]),
            shlex.join(["journalctl", "--user", "-u", unit_name + ".service", "-n", "100"]),
            "", "Durdurma:",
            shlex.join(["systemctl", "--user", "disable", "--now", unit_name + ".timer"]),
            "", "Saati, yolları veya yedek sayısını değiştirme:",
            "Yeni bir çıktı klasörü üretin ve dosyaları doğrulayın. Eski dosyalar değiştirilmez; grup kimliğine bağlı hizmet adı korunur.",
            "Eski bağlantıları kaldırıp yeni dosyalar için link, daemon-reload ve enable komutlarını uygulayın:",
            shlex.join(["systemctl", "--user", "disable", "--now", unit_name + ".timer"]),
            shlex.join(["systemctl", "--user", "disable", unit_name + ".service"]),
            "", "Her tetiklemede grubun güncel tanımı, sorgu bütçesi ve kayıtlı en az çalışma aralığı uygulanır.",
            "Takvim tetiklemesi ve en az çalışma aralığı ayrı kontrollerdir. Saat diliminin yaz saati değişimi veya önceki işin uzun gecikmesi bir tetiklemenin atlanmasına yol açabilir.",
            "Her hazırlıkta grubun güncel aralığının takvimden kısa olduğu doğrulanır. Sonradan eşit veya uzun aralık kaydedilirse hizmet arama yapmadan durur; grup aralığını veya takvimi yeniden düzenleyin.",
            "Grup kapatılırsa yeni arama yapılmaz. Hizmet anında yeniden deneme yapmaz.",
            "Çalışma öncesi ortak kilit, plan ve doğrulanmış yerel yedek kontrol edilir.",
            f"Yalnız scheduled-backups sahiplik kaydıyla yönetilen son {spec.keep} yedek tutulur.",
            "Elle alınmış/geçiş yedekleri korunur. Aynı diskteki kopya uzak yedek değildir.",
            "Makine kapalıyken kaçırılan takvim için açılışta bir tetikleme olabilir; bütün kaçırılmış turlar tekrarlanmaz.",
            "Kullanıcı oturumu kapanınca hizmetin çalışması sistemin linger ayarına bağlıdır.",
            "Dosya üretimi canlı Tavily erişimini veya Linux hizmetinin çalışmasını doğrulamaz; linger ayarı değiştirmez.",
        ]
        try:
            output_path.mkdir(mode=0o700)
            for destination, content in ((service_path, service), (timer_path, timer),
                                         (instructions_path, "\n".join(lines) + "\n")):
                with destination.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                destination.chmod(0o600)
        except OSError as error:
            raise StorageError("Zamanlama dosyaları tamamlanamadı; mevcut dosyalar korunuyor. Yeni bir çıktı klasörü seçin.") from error
        return GeneratedSchedule(
            str(output_path), str(service_path), str(timer_path), str(instructions_path),
            unit_name, calendar, (
                "Yalnız dosyalar üretildi; Linux hizmeti etkinleştirilmedi.",
                "Grubun çalışma anındaki güncel kapsamı, bütçesi ve en az çalışma aralığı geçerlidir.",
                "Anahtar dosyasının yalnız yolu kaydedildi; anahtar okunmadı.",
            ),
        )
