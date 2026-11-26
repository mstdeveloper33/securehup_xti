#!/usr/bin/env python3
"""Offline, secret-safe team handoff report and disposable core acceptance."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from typing import Any

from xti import __version__
from xti.application.source_governance import SourceGovernanceService
from xti.domain.assets import ValidationError


PROJECT = Path(__file__).resolve().parents[1]
CONTRACT_VERSION = 1
STATES = ("pass", "blocked_requirement", "not_implemented", "fail")
SECRET_ENVIRONMENT = {
    "BRIGHTDATA_API_KEY", "TAVILY_API_KEY", "XON_API_KEY",
    "XTI_GITHUB_TOKEN", "XTI_GITLAB_TOKEN",
}


@dataclass(frozen=True, slots=True)
class Check:
    identifier: str
    title: str
    state: str
    required: bool
    detail: str
    action: str | None = None

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError("Unknown handoff state")


def _check(
    identifier: str,
    title: str,
    state: str,
    *,
    required: bool,
    detail: str,
    action: str | None = None,
) -> Check:
    return Check(identifier, title, state, required, detail, action)


def _safe_environment(root: Path) -> dict[str, str]:
    """Keep runtime selection but exclude credentials and user configuration."""
    environment = os.environ.copy()
    for name in SECRET_ENVIRONMENT:
        environment.pop(name, None)
    home = root / "home"
    config = root / "config"
    home.mkdir(mode=0o700)
    config.mkdir(mode=0o700)
    environment.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(config),
        "XTI_DATA_DIR": str(root / "data"),
        "PYTHONNOUSERSITE": "1",
    })
    return environment


def _run(
    arguments: list[str],
    *,
    environment: dict[str, str],
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=PROJECT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def _json_result(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    # Successful commands use stdout; the shared CLI deliberately writes its
    # single JSON error envelope to stderr. Never concatenate the two streams.
    content = result.stdout if result.stdout.strip() else result.stderr
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        raise ValueError("Command did not return one JSON object") from None
    if not isinstance(value, dict):
        raise ValueError("Command JSON must be an object")
    return value


def _failure_detail(result: subprocess.CompletedProcess[str], temporary: Path) -> str:
    value = (result.stderr or result.stdout or "Komut ayrıntı vermeden başarısız oldu.").strip()
    value = value.replace(str(temporary), "<temporary>")
    value = " ".join(value.split())
    return value[:500]


def _command_check(
    identifier: str,
    title: str,
    arguments: list[str],
    *,
    environment: dict[str, str],
    temporary: Path,
    assertion=None,
    timeout: int = 120,
) -> tuple[Check, dict[str, Any] | None]:
    try:
        result = _run(arguments, environment=environment, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return _check(
            identifier, title, "fail", required=True,
            detail="Kontrol güvenli süre içinde başlatılamadı veya tamamlanmadı.",
        ), None
    try:
        body = _json_result(result)
        valid = result.returncode == 0 and body.get("ok") is True
        if valid and assertion is not None:
            valid = bool(assertion(body.get("data")))
    except (ValueError, TypeError, KeyError):
        valid, body = False, None
    if not valid:
        return _check(
            identifier, title, "fail", required=True,
            detail=_failure_detail(result, temporary),
        ), body
    return _check(
        identifier, title, "pass", required=True,
        detail="Geçici ve anahtarsız kabul alanında doğrulandı.",
    ), body


def disposable_acceptance(*, full: bool) -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory(prefix="xti-handoff-") as directory:
        temporary = Path(directory).resolve()
        temporary.chmod(0o700)
        environment = _safe_environment(temporary)
        try:
            setup = _run(
                [str(PROJECT / "setup"), "--core-only"],
                environment=environment,
                timeout=180,
            )
        except (OSError, subprocess.TimeoutExpired):
            setup = None
        if setup is None or setup.returncode != 0:
            checks.append(_check(
                "smoke.setup", "Anahtarsız geçici kurulum", "fail", required=True,
                detail=("Kurulum başlatılamadı veya süre sınırını aştı." if setup is None
                        else _failure_detail(setup, temporary)),
                action="./setup",
            ))
            return checks
        checks.append(_check(
            "smoke.setup", "Anahtarsız geçici kurulum", "pass", required=True,
            detail="Kullanıcı verisine dokunmadan geçici alanda tekrar güvenli kuruldu.",
        ))

        command_specs = [
            (
                "smoke.doctor", "Şema ve veri bütünlüğü",
                [str(PROJECT / "xti"), "--json", "doctor"],
                lambda data: data["schema_version"] >= 1 and data["integrity"] == "ok",
            ),
            (
                "smoke.asset", "Örnek varlık yazma/okuma",
                [str(PROJECT / "xti"), "--json", "assets", "add", "example.com"],
                lambda data: data["asset"]["value"] == "example.com",
            ),
            (
                "smoke.sources", "Kaynak manifesti sözleşmesi",
                [str(PROJECT / "xti"), "--json", "sources", "validate"],
                lambda data: data["valid"] is True and data["source_count"] > 0,
            ),
        ]
        for identifier, title, arguments, assertion in command_specs:
            check, _body = _command_check(
                identifier, title, arguments, environment=environment,
                temporary=temporary, assertion=assertion,
            )
            checks.append(check)

        backup = temporary / "handoff-backup.db"
        check, _body = _command_check(
            "smoke.backup", "Üzerine yazmasız yedek",
            [str(PROJECT / "xti"), "--json", "backup", "--output", str(backup)],
            environment=environment, temporary=temporary,
            assertion=lambda data: Path(data["backup"]).resolve() == backup,
        )
        checks.append(check)
        if check.state == "pass":
            restored = temporary / "restored"
            restored_environment = dict(environment, XTI_DATA_DIR=str(restored))
            restore_check, _body = _command_check(
                "smoke.restore", "Boş alana geri dönüş",
                [str(PROJECT / "xti"), "--json", "restore", str(backup)],
                environment=restored_environment, temporary=temporary,
                assertion=lambda data: Path(data["database"]).resolve() == restored / "xti.db",
            )
            checks.append(restore_check)
            if restore_check.state == "pass":
                read_check, _body = _command_check(
                    "smoke.restore-read", "Geri dönen kaydı okuma",
                    [str(PROJECT / "xti"), "--json", "assets", "list"],
                    environment=restored_environment, temporary=temporary,
                    assertion=lambda data: [item["value"] for item in data["assets"]] == ["example.com"],
                )
                checks.append(read_check)

        if full:
            capability_check, _body = _command_check(
                "smoke.brand-capabilities", "Marka koruma yerel araçları",
                [str(PROJECT / "xti"), "--json", "brand", "protection", "capabilities"],
                environment=environment, temporary=temporary,
                assertion=lambda data: (
                    data["browser_state"] == "ready"
                    and data["privacy_scanner"]["state"] == "ready"
                    and all(item["state"] == "ready" for item in data["tools"])
                ),
            )
            checks.append(capability_check)
    return checks


def feature_catalog_check() -> tuple[Check, dict[str, int]]:
    path = PROJECT / "FEATURE_CATALOG.md"
    try:
        text = path.read_text(encoding="utf-8")
        version = re.search(r"\*\*Güncel sürüm:\*\*\s*([0-9.]+)", text)
        labels = {
            "active": "Aktif ve kullanılabilir",
            "requirement_bound": "Kodu hazır, gereksinim bekliyor",
            "waiting": "Beklemede, ertelenmiş veya kapsam dışı",
            "total": "Toplam izlenen özellik/durum",
        }
        counts = {}
        for key, label in labels.items():
            match = re.search(r"\|\s*" + re.escape(label) + r"\s*\|\s*([0-9]+)\s*\|", text)
            if match is None:
                raise ValueError("missing count")
            counts[key] = int(match.group(1))
        valid = (
            version is not None
            and version.group(1) == __version__
            and counts["active"] + counts["requirement_bound"] + counts["waiting"] == counts["total"]
        )
    except (OSError, UnicodeError, ValueError):
        valid, counts = False, {}
    return _check(
        "catalog.features", "Özellik kataloğu sürümü ve sayıları",
        "pass" if valid else "fail", required=True,
        detail=(f"Katalog XTI {__version__} ile tutarlı." if valid
                else "FEATURE_CATALOG.md eksik, bozuk veya çalışma sürümüyle uyumsuz."),
        action=None if valid else "FEATURE_CATALOG.md sürüm ve bölüm sayılarını güncelle.",
    ), counts


def repository_checks() -> list[Check]:
    expected = (
        "setup", "xti", "handoff", "FEATURE_CATALOG.md", "NOTES.md",
        "REQUIREMENTS.md", "CHANGELOG.md",
        "docs/GETTING_STARTED.md", "docs/ARCHITECTURE.md", "docs/STATUS.md",
        "docs/TEAM_HANDOFF.md",
        "docs/ABUSE_CONTACTS.md",
        "docs/decisions/0199-secret-safe-team-handoff.md",
        "docs/decisions/0200-reviewed-abuse-contact-routing.md",
        "docs/decisions/0201-retire-xposedornot-new-use.md",
        "docs/roadmap/MASTER_ROADMAP.md",
        "docs/roadmap/TEAM_HANDOFF_DELIVERY.md",
        "docs/roadmap/P06_ABUSE_CONTACT_DELIVERY.md",
    )
    missing = [name for name in expected if not (PROJECT / name).is_file()]
    checks = [_check(
        "repository.files", "Teslim dosyaları", "pass" if not missing else "fail",
        required=True,
        detail=("Kurulum, kullanım, durum ve katalog dosyaları mevcut." if not missing
                else "Eksik teslim dosyaları: " + ", ".join(missing)),
    )]
    checks.append(_check(
        "runtime.python", "Python çalışma zamanı",
        "pass" if sys.version_info >= (3, 11) else "fail", required=True,
        detail=f"Python {platform.python_version()} ({platform.system()} {platform.machine()}).",
        action=None if sys.version_info >= (3, 11) else "Python 3.11 veya daha yenisini kur.",
    ))
    catalog_check, _counts = feature_catalog_check()
    checks.append(catalog_check)
    version_markers = {
        "README.md": f"**{__version__} —",
        "CHANGELOG.md": f"## {__version__} —",
        "NOTES.md": f"Güncel çalışma: **{__version__} /",
        "docs/GETTING_STARTED.md": f"**Sürüm {__version__} ·",
        "docs/STATUS.md": f"— {__version__},",
        "docs/ARCHITECTURE.md": f"{__version__} P05 XposedOrNot emekliliği:",
        "docs/TEAM_HANDOFF.md": f"**Sürüm {__version__} ·",
        "docs/roadmap/MASTER_ROADMAP.md": f"**P05 bakım çalışması:** 0.185.0/{__version__}",
    }
    stale = []
    for name, marker in version_markers.items():
        try:
            current = (PROJECT / name).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            current = ""
        if marker not in current:
            stale.append(name)
    checks.append(_check(
        "documentation.version", "Teslim belgelerinin sürüm tutarlılığı",
        "pass" if not stale else "fail", required=True,
        detail=(f"Güncel teslim belgeleri XTI {__version__} sürümünü gösteriyor."
                if not stale else "Sürüm işareti eksik belgeler: " + ", ".join(stale)),
        action=None if not stale else "Teslim belgelerindeki güncel sürüm başlıklarını eşitle.",
    ))
    try:
        validation = SourceGovernanceService().validate()
        valid = validation["valid"] is True and validation["source_count"] > 0
    except (ValidationError, KeyError, TypeError, ValueError):
        valid, validation = False, {"source_count": 0}
    checks.append(_check(
        "catalog.sources", "Kaynak manifesti kataloğu",
        "pass" if valid else "fail", required=True,
        detail=(f"{validation['source_count']} kaynak manifesti ağsız doğrulandı." if valid
                else "Kaynak manifestleri doğrulanamadı."),
    ))
    return checks


def _secret_check(identifier: str, title: str, loader, action: str) -> Check:
    try:
        value = loader()
        ready = value is not None
    except (ValidationError, OSError):
        ready = False
    return _check(
        identifier, title, "pass" if ready else "blocked_requirement", required=False,
        detail=("Özel yapılandırma mevcut; canlı erişim ayrıca doğrulanmalıdır." if ready
                else "Bu isteğe bağlı kaynak için anahtar eksik veya güvenle okunamıyor."),
        action=None if ready else action,
    )


def optional_configuration_checks() -> list[Check]:
    from xti.adapters.brightdata_credentials import load_key as load_brightdata
    from xti.adapters.code_credentials import load_key as load_code_key
    from xti.adapters.tavily_search import load_tavily_api_key

    return [
        _secret_check(
            "optional.tavily", "Tavily firma içeriği araması", load_tavily_api_key,
            "./xti mentions configure",
        ),
        _secret_check(
            "optional.brightdata", "Bright Data LinkedIn ek kanıtı", load_brightdata,
            "./xti brand brightdata configure",
        ),
        _secret_check(
            "optional.github", "GitHub hesaplı kod araması",
            lambda: load_code_key("github"), "./xti code configure github",
        ),
        _secret_check(
            "optional.gitlab", "GitLab hesaplı kod araması",
            lambda: load_code_key("gitlab"), "./xti code configure gitlab",
        ),
        _check(
            "optional.channels", "Telegram/Discord kanal bağlantıları",
            "blocked_requirement", required=False,
            detail="Hesap ve seçilmiş kanal firma bazında ayrıca yapılandırılır.",
            action="./xti content configure --help",
        ),
        _check(
            "optional.active-scope", "Yetkili Nmap canlı kabulü",
            "blocked_requirement", required=False,
            detail="Kurulum tek başına hedef yetkisi değildir; kesin IP/CIDR ve port kapsamı gerekir.",
            action="./xti surface nmap readiness && ./xti surface nmap targets --help",
        ),
        _check(
            "optional.external-infrastructure", "AIL/Cowrie/CAPE dış altyapısı",
            "blocked_requirement", required=False,
            detail="Güvenli içe alma bağlantıları hazırdır; gerçek dış sistem işletimi ayrıca gerekir.",
            action="docs/DARKWEB_MONITORING.md ve docs/TELEMETRY.md dosyalarını incele.",
        ),
    ]


def component_checks(*, full: bool) -> list[Check]:
    from xti.interfaces.components import make_component_service

    try:
        report = make_component_service().list()
    except (ValidationError, OSError):
        return [_check(
            "components.catalog", "Yönetilen araç kurulumu", "fail", required=full,
            detail="Yönetilen bileşen kataloğu güvenle okunamadı.",
        )]
    required_ids = {"maigret", "sherlock", "betterleaks"} if full else set()
    checks = []
    for item in report["components"]:
        identifier = item["identifier"]
        required = identifier in required_ids
        state = item["installation"]["state"]
        if state == "ready":
            result = "pass"
        elif state == "missing":
            result = "blocked_requirement"
        else:
            result = "fail" if required else "blocked_requirement"
        setup = " ".join(item["setup_command"])
        checks.append(_check(
            "component." + identifier, item["label"] + " kurulumu", result,
            required=required,
            detail=("Sabitlenmiş yerel kurulum kaydı hazır." if state == "ready"
                    else "Kurulum durumu: " + state + "."),
            action=None if state == "ready" else setup,
        ))
    dependencies = {
        "feedparser": "6.0.14",
        "pypdf": "7.1.1",
        "Telethon": "1.46.0",
        "irctokens": "2.0.2",
    }
    for distribution, expected in dependencies.items():
        try:
            observed = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            observed = None
        ready = observed == expected
        checks.append(_check(
            "dependency." + distribution.lower(), distribution + " paketi",
            "pass" if ready else ("fail" if full else "blocked_requirement"),
            required=full,
            detail=(f"Sabit sürüm {observed} hazır." if ready else
                    f"Beklenen {expected}; gözlenen {observed or 'kurulu değil'}."),
            action=None if ready else "./scripts/setup-brand",
        ))
    return checks


def workspace_check(data_dir: Path) -> Check:
    database = data_dir.expanduser().resolve() / "xti.db"
    if not database.is_file():
        return _check(
            "workspace.database", "Seçilen çalışma alanı", "blocked_requirement",
            required=True, detail="Kayıt alanı henüz oluşturulmamış.", action="./setup",
        )
    environment = os.environ.copy()
    try:
        result = _run(
            [str(PROJECT / "xti"), "--data-dir", str(data_dir), "--json", "doctor"],
            environment=environment,
        )
        body = _json_result(result)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return _check(
            "workspace.database", "Seçilen çalışma alanı", "fail", required=True,
            detail="Kayıt alanı doctor çıktısı güvenle okunamadı.",
        )
    if result.returncode == 0 and body.get("ok") is True:
        return _check(
            "workspace.database", "Seçilen çalışma alanı", "pass", required=True,
            detail=f"Şema {body['data']['schema_version']} ve bütünlük kontrolü hazır.",
        )
    message = str(body.get("error", {}).get("message", ""))
    if "eski sürümde" in message:
        return _check(
            "workspace.database", "Seçilen çalışma alanı", "blocked_requirement",
            required=True, detail="Eski şema korundu; açık yedekli geçiş gerekiyor.",
            action="./xti migrate",
        )
    return _check(
        "workspace.database", "Seçilen çalışma alanı", "fail", required=True,
        detail="Kayıt alanı doctor kontrolünden geçmedi; veri değiştirilmedi.",
        action="./xti --json doctor",
    )


def source_requirements() -> dict[str, Any]:
    manifests = SourceGovernanceService().manifests
    rows = [{
        "identifier": item.identifier,
        "label": item.label,
        "integration_state": item.integration_state,
        "cost_model": item.cost_model,
        "credential_mode": item.credential_mode,
        "prerequisites": list(item.prerequisites),
        "commands": ["./xti " + command for command in item.commands],
        "reference_url": item.reference_url,
    } for item in manifests]
    return {
        "count": len(rows),
        "active": sum(item["integration_state"] == "active" for item in rows),
        "blocked_requirement": sum(item["integration_state"] == "conditional" for item in rows),
        "not_implemented": sum(item["integration_state"] == "disabled" for item in rows),
        "sources": rows,
    }


def overall_state(checks: list[Check]) -> str:
    required = [item.state for item in checks if item.required]
    if "fail" in required:
        return "fail"
    if "blocked_requirement" in required:
        return "blocked_requirement"
    if "not_implemented" in required:
        return "not_implemented"
    return "pass"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    checks = repository_checks()
    if not args.plan:
        checks.extend(component_checks(full=args.profile == "full"))
        checks.append(workspace_check(args.data_dir))
        if not args.no_smoke:
            checks.extend(disposable_acceptance(full=args.profile == "full"))
    checks.extend(optional_configuration_checks())
    requirements = source_requirements()
    feature_check, feature_counts = feature_catalog_check()
    # repository_checks already contains this check; this second call only extracts counts.
    del feature_check
    state = overall_state(checks)
    return {
        "kind": "xti-team-handoff",
        "contract_version": CONTRACT_VERSION,
        "xti_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "plan" if args.plan else "check",
        "profile": args.profile,
        "overall_state": state,
        "core_ready": state == "pass" if not args.plan else None,
        "checks": [asdict(item) for item in checks],
        "feature_catalog": feature_counts,
        "source_requirements": requirements,
        "notes": [
            "Bu kontrol ücretli çağrı, canlı kaynak sorgusu veya aktif hedef taraması yapmaz.",
            "İsteğe bağlı gereksinimlerin eksikliği anahtarsız temel kabulü başarısız yapmaz.",
            "Yapılandırılmış anahtar durumu canlı hesap, kota, sözleşme veya doğruluk kabulü değildir.",
            "Geçici kabul alanı işlem sonunda silinir; seçilen çalışma alanı yalnız doctor ile okunur.",
        ],
    }


def render(report: dict[str, Any], *, details: bool) -> list[str]:
    labels = {
        "pass": "PASS", "blocked_requirement": "GEREKSİNİM BEKLİYOR",
        "not_implemented": "UYGULANMADI", "fail": "FAIL",
    }
    lines = [
        "XTI ekip teslim kontrolü",
        f"Sürüm: {report['xti_version']} | Profil: {report['profile']} | Mod: {report['mode']}",
        f"Genel sonuç: {labels[report['overall_state']]}",
        "",
        "Zorunlu teslim kontrolleri:",
    ]
    required = [item for item in report["checks"] if item["required"]]
    optional = [item for item in report["checks"] if not item["required"]]
    for item in required:
        lines.append(f"  [{labels[item['state']]}] {item['title']}: {item['detail']}")
        if item["action"]:
            lines.append("    Çözüm: " + item["action"])
    lines.extend(["", "İsteğe bağlı özellikler:"])
    for item in optional:
        lines.append(f"  [{labels[item['state']]}] {item['title']}: {item['detail']}")
        if item["action"]:
            lines.append("    Açmak için: " + item["action"])
    sources = report["source_requirements"]
    lines.extend([
        "",
        "Kaynak kataloğu:",
        f"  Aktif={sources['active']} | Gereksinim bekliyor={sources['blocked_requirement']} | "
        f"Kapalı/uygulanmadı={sources['not_implemented']} | Toplam={sources['count']}",
    ])
    if details:
        for item in sources["sources"]:
            if item["integration_state"] == "active":
                continue
            lines.append(
                f"  - {item['identifier']}: "
                + ("GEREKSİNİM BEKLİYOR" if item["integration_state"] == "conditional" else "UYGULANMADI")
            )
            for value in item["prerequisites"]:
                lines.append("      " + value)
    lines.extend(["", *report["notes"]])
    return lines


def write_new_json(path: Path, report: dict[str, Any]) -> Path:
    destination = path.expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return destination


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        prog="handoff",
        description="Anahtar kullanmadan ekip teslim gereksinimlerini ve çekirdek kabulünü doğrula.",
    )
    value.add_argument("--plan", action="store_true", help="Kabul çalıştırmadan gereksinim planını göster.")
    value.add_argument("--profile", choices=("core", "full"), default="full",
                       help="core yalnız motoru, full normal ./setup araçlarını da zorunlu sayar.")
    value.add_argument("--data-dir", type=Path,
                       default=Path(os.environ.get("XTI_DATA_DIR", ".xti-data")),
                       help="Yalnız doctor ile okunacak çalışma alanı.")
    value.add_argument("--no-smoke", action="store_true",
                       help="Geçici anahtarsız kurulum/yedek/restore kabulünü atla.")
    value.add_argument("--details", action="store_true",
                       help="Koşullu ve kapalı bütün kaynak gereksinimlerini göster.")
    value.add_argument("--json", action="store_true", help="Makinece okunabilir tek JSON üret.")
    value.add_argument("--output", type=Path, help="JSON raporunu yeni dosyaya yaz; üzerine yazma.")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = build_report(args)
    if args.output is not None:
        try:
            write_new_json(args.output, report)
        except FileExistsError:
            print("Hata: Rapor hedefi zaten var; üzerine yazılmadı.", file=sys.stderr)
            return 1
        except OSError:
            print("Hata: Rapor güvenle yazılamadı.", file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    else:
        print("\n".join(render(report, details=args.details)))
        if args.output is not None:
            print("\nJSON raporu: " + str(args.output.expanduser().absolute()))
    return {"pass": 0, "blocked_requirement": 3, "not_implemented": 4, "fail": 1}[
        report["overall_state"]
    ]


if __name__ == "__main__":
    raise SystemExit(main())
