"""Nmap TCP-connect adapter with exact targets and bounded process execution."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from http.client import HTTPException
import ipaddress
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tempfile
from xml.etree import ElementTree

from xti.adapters.https_probe import GoogleDnsJsonClient, _ProbeFailure, is_public_address
from xti.adapters.unicode_security import unicode_security_profile
from xti.domain.assets import ValidationError
from xti.domain.matching import normalize_for_matching
from xti.domain.nmap_scan import (
    NMAP_MAX_OPEN_PORT_RECORDS,
    NMAP_POLICY_VERSION,
    NmapOpenPort,
    NmapScanPlan,
    NmapScanResult,
    NmapStateCounts,
    port_spec_contains,
    validate_nmap_scan_plan,
    validate_nmap_scan_result,
)
from xti.domain.services import normalize_public_address


NMAP_DNS_TIMEOUT = 20.0
NMAP_PROCESS_GRACE_SECONDS = 10
NMAP_MAX_XML_BYTES = 16 * 1024 * 1024
NMAP_MAX_DIAGNOSTIC_BYTES = 64 * 1024
_VERSION_LINE = re.compile(r"^Nmap version (7\.[0-9]{1,3}(?:\.[0-9]{1,3})?)(?=\s|$)", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class NmapProcessResult:
    returncode: int | None
    xml: bytes
    diagnostic: bytes
    timed_out: bool


class SubprocessNmapRuntime:
    """Resolve and execute Nmap without a shell or caller-provided arguments."""

    def __init__(self, executable: str | None = None) -> None:
        selected = executable or shutil.which("nmap")
        self.executable = str(Path(selected).resolve()) if selected else None
        self._ready: tuple[str, str] | None = None

    def readiness(self) -> tuple[str, str]:
        if self._ready is not None:
            return self._ready
        if self.executable is None:
            raise ValidationError(
                "Nmap kurulu değil. Önce './scripts/setup-nmap' çalıştır."
            )
        try:
            completed = subprocess.run(
                [self.executable, "--version"], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                timeout=5, close_fds=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ValidationError("Nmap sürümü güvenli biçimde doğrulanamadı.") from error
        output = completed.stdout
        if completed.returncode != 0 or len(output) > NMAP_MAX_DIAGNOSTIC_BYTES:
            raise ValidationError("Nmap sürümü güvenli biçimde doğrulanamadı.")
        try:
            text = output.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            raise ValidationError("Nmap sürüm çıktısı beklenen metin biçiminde değil.") from error
        match = _VERSION_LINE.search(text)
        if match is None:
            raise ValidationError("Yalnız doğrulanmış Nmap 7.x sürümleri destekleniyor.")
        self._ready = (match.group(1), self.executable)
        return self._ready

    def scan(self, address: str, plan: NmapScanPlan) -> NmapProcessResult:
        _version, executable = self.readiness()
        parsed = ipaddress.ip_address(address)
        with tempfile.TemporaryDirectory(prefix="xti-nmap-") as directory:
            root = Path(directory)
            xml_path = root / "result.xml"
            diagnostic_path = root / "diagnostic.txt"
            command = [
                executable,
                "-sT", "-Pn", "-n", "--unprivileged", "--reason",
                "--max-rate", str(plan.limits.max_rate_pps),
                "--max-retries", str(plan.limits.max_retries),
                "--host-timeout", f"{plan.limits.timeout_seconds}s",
                "-p", plan.port_spec,
                "-oX", str(xml_path),
            ]
            if parsed.version == 6:
                command.append("-6")
            command.append(str(parsed))
            timed_out = False
            returncode: int | None = None
            try:
                with diagnostic_path.open("wb") as diagnostic:
                    completed = subprocess.run(
                        command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=diagnostic, check=False,
                        timeout=plan.limits.timeout_seconds + NMAP_PROCESS_GRACE_SECONDS,
                        close_fds=True,
                    )
                returncode = completed.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
            except OSError as error:
                raise ValidationError("Nmap işlemi başlatılamadı.") from error
            xml = self._bounded_read(xml_path, NMAP_MAX_XML_BYTES)
            diagnostic = self._bounded_read(
                diagnostic_path, NMAP_MAX_DIAGNOSTIC_BYTES,
            )
            return NmapProcessResult(returncode, xml, diagnostic, timed_out)

    @staticmethod
    def _bounded_read(path: Path, maximum: int) -> bytes:
        if not path.exists():
            return b""
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
                raise ValidationError("Nmap yerel çıktısı güvenli boyut sınırını aştı.")
            return path.read_bytes()
        except OSError as error:
            raise ValidationError("Nmap yerel çıktısı güvenli biçimde okunamadı.") from error


def _safe_reason(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 100 or not value.isprintable():
        return "nmap-state"
    return value


def _mapped_state(value: str) -> str:
    if value == "open":
        return "open"
    if value == "closed":
        return "closed"
    return "unknown"


def _parse_nmap_xml(
    content: bytes, requested_address: str, plan: NmapScanPlan,
) -> tuple[NmapStateCounts, tuple[NmapOpenPort, ...], bool, str]:
    port_count = plan.port_count
    xml = content.replace(b"<!DOCTYPE nmaprun>", b"", 1)
    if (
        not content or len(content) > NMAP_MAX_XML_BYTES
        or b"\x00" in xml or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper()
    ):
        raise ValidationError("Nmap XML kanıtı eksik veya güvenli değil.")
    try:
        root = ElementTree.fromstring(xml.decode("utf-8", "strict"))
    except (ElementTree.ParseError, ValueError, RecursionError) as error:
        raise ValidationError("Nmap XML kanıtı ayrıştırılamadı.") from error
    if root.tag != "nmaprun" or root.attrib.get("scanner") != "nmap":
        raise ValidationError("Nmap XML kökü beklenen biçimde değil.")
    hosts = root.findall("host")
    if len(hosts) != 1:
        raise ValidationError("Nmap yalnız tek kesin hedef sonucu üretmeli.")
    host = hosts[0]
    host_status = host.find("status")
    if host_status is None or host_status.attrib.get("state") != "up":
        raise ValidationError("Nmap XML hedefi erişilebilir hedef kanıtı taşımıyor.")
    finished = root.find("./runstats/finished")
    if finished is None or finished.attrib.get("exit") != "success":
        raise ValidationError("Nmap XML başarılı tamamlanma kanıtı taşımıyor.")
    addresses = {
        item.attrib.get("addr") for item in host.findall("address")
        if item.attrib.get("addrtype") in {"ipv4", "ipv6"}
    }
    if requested_address not in addresses:
        raise ValidationError("Nmap XML hedefi onaylanan kesin IP ile uyuşmuyor.")
    counts = {"open": 0, "closed": 0, "unknown": 0}
    seen_ports: set[int] = set()
    open_ports: list[NmapOpenPort] = []
    ports_node = host.find("ports")
    if ports_node is None:
        raise ValidationError("Nmap XML port özeti taşımıyor.")
    for extra in ports_node.findall("extraports"):
        try:
            count = int(extra.attrib["count"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValidationError("Nmap toplu port sayacı geçersiz.") from error
        if not 0 <= count <= port_count:
            raise ValidationError("Nmap toplu port sayacı kapsamı aşıyor.")
        counts[_mapped_state(extra.attrib.get("state", "unknown"))] += count
    for item in ports_node.findall("port"):
        if item.attrib.get("protocol") != "tcp":
            raise ValidationError("Nmap TCP planı TCP dışı sonuç taşıyamaz.")
        try:
            port = int(item.attrib["portid"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValidationError("Nmap port kimliği geçersiz.") from error
        if (
            not 1 <= port <= 65535 or port in seen_ports
            or not port_spec_contains(plan.port_spec, port)
        ):
            raise ValidationError("Nmap port listesi geçersiz veya yinelenmiş.")
        seen_ports.add(port)
        state_node = item.find("state")
        if state_node is None:
            raise ValidationError("Nmap port durumu eksik.")
        state = _mapped_state(state_node.attrib.get("state", "unknown"))
        counts[state] += 1
        if state == "open" and len(open_ports) < NMAP_MAX_OPEN_PORT_RECORDS:
            open_ports.append(NmapOpenPort(port, _safe_reason(state_node.attrib.get("reason"))))
    total = sum(counts.values())
    if total > port_count:
        raise ValidationError("Nmap port sayaçları seçilen kapsamı aşıyor.")
    if total < port_count:
        counts["unknown"] += port_count - total
    open_ports.sort(key=lambda item: item.port)
    truncated = counts["open"] > len(open_ports)
    digest = hashlib.sha256(content).hexdigest()
    return (
        NmapStateCounts(counts["open"], counts["closed"], counts["unknown"]),
        tuple(open_ports), truncated, digest,
    )


class NmapTcpConnectProbe(GoogleDnsJsonClient):
    """Verify DNS, then run one unprivileged Nmap TCP-connect process."""

    def __init__(self, *, runtime: SubprocessNmapRuntime | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.runtime = runtime or SubprocessNmapRuntime()

    def readiness(self) -> tuple[str, str]:
        return self.runtime.readiness()

    def check(
        self, domain: str, requested_address: str, plan: NmapScanPlan,
        execution_id: str,
    ) -> NmapScanResult:
        domain = normalize_for_matching(domain)
        unicode_security_profile().to_unicode(domain)
        requested = normalize_public_address(requested_address)
        plan = validate_nmap_scan_plan(plan)
        nmap_version, _executable = self.readiness()
        started_at = self.now()
        deadline = self.monotonic() + NMAP_DNS_TIMEOUT
        addresses: tuple[str, ...] = ()
        checked_address = None
        dns_status = "failed"
        status = "failed"
        counts = NmapStateCounts(0, 0, 0)
        open_ports: tuple[NmapOpenPort, ...] = ()
        truncated = False
        output_sha256 = None
        errors: list[str] = []
        notes = [
            "Yalnız açıkça belirtilen ve güncel DNS yanıtında bulunan kesin genel IP taranır.",
            "Nmap -sT, -Pn, -n ve --unprivileged kullanır; SYN/root, UDP, NSE, OS veya sürüm taraması yoktur.",
            "max-rate paket/saniye üst sınırıdır; kesin bayt kotası değildir.",
            "Açık port ürün, sürüm, zafiyet veya sahiplik kanıtı değildir.",
        ]

        def result() -> NmapScanResult:
            return validate_nmap_scan_result(NmapScanResult(
                execution_id, domain, requested, started_at, self.now(),
                NMAP_POLICY_VERSION, dns_status, addresses, checked_address,
                plan, status, nmap_version, counts, open_ports, truncated,
                output_sha256, tuple(errors), tuple(notes),
            ))

        try:
            context = self.context_factory()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                raise _ProbeFailure("TLS sertifika doğrulaması devre dışı bırakılamaz.")
            context.set_alpn_protocols(["http/1.1"])
            answer4 = self._resolve(context, domain, 1, deadline)
            answer6 = self._resolve(context, domain, 28, deadline)
            if answer4[0] != answer6[0]:
                raise _ProbeFailure("A ve AAAA sorguları çelişen DNS durumu bildirdi.")
            addresses = tuple(sorted(
                set(answer4[1] + answer6[1]),
                key=lambda value: (
                    ipaddress.ip_address(value).version, int(ipaddress.ip_address(value)),
                ),
            ))
            if len(addresses) > 16:
                raise _ProbeFailure("DNS yanıtı 16 adres sınırını aştı.")
            if answer4[0] == 3:
                dns_status = "nxdomain"
                errors.append("DNS sağlayıcısı domaini bulamadı; Nmap çalıştırılmadı.")
                return result()
            if not addresses:
                dns_status = "no_address"
                errors.append("A/AAAA adresi bulunamadı; Nmap çalıştırılmadı.")
                return result()
            if not all(is_public_address(address) for address in addresses):
                dns_status = "blocked"
                errors.append("Özel/yerel IP görüldü; Nmap çalıştırılmadı.")
                return result()
            if requested not in addresses:
                dns_status = "address_mismatch"
                errors.append("Onaylanan IP güncel DNS yanıtında yok; Nmap çalıştırılmadı.")
                return result()
            dns_status = "resolved"
            checked_address = requested
        except _ProbeFailure as error:
            addresses = ()
            errors.append(str(error))
            return result()
        except (OSError, HTTPException, ValueError, ValidationError):
            addresses = ()
            errors.append("DNS doğrulaması güvenli süre sınırı içinde tamamlanamadı.")
            return result()

        try:
            process = self.runtime.scan(requested, plan)
        except ValidationError:
            status = "failed"
            errors.append("Nmap işlemi güvenli sınırlar içinde tamamlanamadı.")
            return result()
        if process.timed_out:
            status = "timeout"
            errors.append("Nmap işlemi kesin süre sınırında sonlandırıldı.")
            return result()
        if process.returncode != 0:
            status = "failed"
            errors.append("Nmap işlemi başarı kodu üretmedi; port iddiası kaydedilmedi.")
            return result()
        try:
            counts, open_ports, truncated, output_sha256 = _parse_nmap_xml(
                process.xml, requested, plan,
            )
        except ValidationError:
            status = "failed"
            errors.append("Nmap XML kanıtı güvenli biçimde doğrulanamadı.")
            return result()
        status = "partial" if counts.unknown or truncated else "complete"
        if counts.unknown:
            errors.append(
                f"{counts.unknown} TCP portu filtreli veya belirsiz durumda kaldı."
            )
        if truncated:
            errors.append(
                f"Açık port ayrıntısı {NMAP_MAX_OPEN_PORT_RECORDS} kayıtla sınırlandı."
            )
        return result()
