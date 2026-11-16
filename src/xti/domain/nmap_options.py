"""Versioned, transport-independent options for the managed Nmap runner."""

from dataclasses import dataclass

from xti.domain.assets import ValidationError


SCAN_TYPES = ("tcp_connect", "tcp_syn", "udp")
SCRIPT_CATALOG = {
    "banner": ("Servisin gönderdiği açılış metni", "discovery"),
    "ssh-hostkey": ("SSH sunucu anahtarı parmak izi", "discovery"),
    "ssl-cert": ("TLS sertifika bilgisi", "discovery"),
    "smb-vuln-ms17-010": ("SMB MS17-010 yanıt kontrolü; exploit çalıştırmaz", "vulnerability_check"),
}


@dataclass(frozen=True, slots=True)
class NmapExecutionOptions:
    service_detection: bool = False
    version_intensity: int = 2
    os_detection: bool = False
    scripts: tuple[str, ...] = ()
    script_timeout_seconds: int = 30
    max_duration_seconds: int = 3600


def normalize_options(value: NmapExecutionOptions) -> NmapExecutionOptions:
    if not isinstance(value, NmapExecutionOptions):
        raise ValidationError("Nmap çalışma seçenekleri geçersiz.")
    if type(value.service_detection) is not bool or type(value.os_detection) is not bool:
        raise ValidationError("Nmap servis/OS seçenekleri boolean olmalı.")
    for name, low, high in (("version_intensity", 0, 9),
                            ("script_timeout_seconds", 1, 300),
                            ("max_duration_seconds", 10, 86400)):
        item = getattr(value, name)
        if type(item) is not int or not low <= item <= high:
            raise ValidationError(f"Nmap {name} {low}–{high} arasında olmalı.")
    if not value.service_detection and value.version_intensity != 2:
        raise ValidationError("Sürüm yoğunluğu için servis tespiti etkin olmalı.")
    if (not isinstance(value.scripts, tuple) or len(value.scripts) > len(SCRIPT_CATALOG)
            or any(not isinstance(item, str) or item not in SCRIPT_CATALOG for item in value.scripts)
            or len(set(value.scripts)) != len(value.scripts)):
        raise ValidationError("Yalnız katalogdaki tekil NSE kontrol adları kullanılabilir.")
    return NmapExecutionOptions(value.service_detection, value.version_intensity,
        value.os_detection, tuple(sorted(value.scripts)), value.script_timeout_seconds,
        value.max_duration_seconds)


def nmap_capabilities() -> dict:
    return {
        "contract_version": 1,
        "scan_types": list(SCAN_TYPES),
        "privileged_options": ["tcp_syn", "udp", "os_detection"],
        "scripts": [{"id": key, "description": label, "kind": kind,
                     "source": f"https://nmap.org/nsedoc/scripts/{key}.html"}
                    for key, (label, kind) in SCRIPT_CATALOG.items()],
        "limits": {"targets": 4096, "ports": 65535, "rate_pps": [1, 1000],
                   "version_intensity": [0, 9], "script_timeout_seconds": [1, 300],
                   "max_duration_seconds": [10, 86400]},
        "execution": "one_target_at_a_time",
        "rate_scope": "port_scan_only_not_service_os_or_nse_traffic",
        "raw_arguments": False, "automatic_privilege_escalation": False,
        "script_output_is_authoritative_vulnerability_verdict": False,
    }
