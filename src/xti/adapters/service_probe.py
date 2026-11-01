"""Pinned, bounded TCP-connect inventory for one approved public address."""

import ipaddress
from http.client import HTTPException
import socket
import ssl

from xti.adapters.https_probe import GoogleDnsJsonClient, _ProbeFailure, is_public_address
from xti.domain.assets import ValidationError
from xti.domain.matching import normalize_for_matching
from xti.adapters.unicode_security import unicode_security_profile
from xti.domain.services import (
    SERVICE_POLICY_VERSION,
    SERVICE_PORT_HINTS,
    SERVICE_PORTS,
    ServicePortResult,
    ServiceScanResult,
    normalize_public_address,
    validate_service_scan_result,
)


SERVICE_SCAN_TIMEOUT = 20.0
PORT_CONNECT_TIMEOUT = 1.0


class BoundedServicePortProbe(GoogleDnsJsonClient):
    """Resolve safely, pin one asserted IP and perform TCP connect only."""

    def _port_state(self, address: str, port: int, overall_deadline: float) -> str:
        parsed = ipaddress.ip_address(address)
        family = socket.AF_INET if parsed.version == 4 else socket.AF_INET6
        sock = None
        try:
            sock = self.socket_factory(family, socket.SOCK_STREAM)
            deadline = min(overall_deadline, self.monotonic() + PORT_CONNECT_TIMEOUT)
            sock.settimeout(self._remaining(deadline))
            sock.connect((str(parsed), port))
            return "open"
        except ConnectionRefusedError:
            return "closed"
        except (TimeoutError, OSError):
            return "unknown"
        finally:
            if sock is not None:
                sock.close()

    def check(self, domain: str, requested_address: str) -> ServiceScanResult:
        domain = normalize_for_matching(domain)
        unicode_security_profile().to_unicode(domain)
        requested = normalize_public_address(requested_address)
        started_at = self.now()
        overall_deadline = self.monotonic() + SERVICE_SCAN_TIMEOUT
        addresses: tuple[str, ...] = ()
        checked_address = None
        dns_status = "failed"
        ports: list[ServicePortResult] = []
        errors: list[str] = []
        notes = [
            "DNS: Google Public DNS; A ve AAAA birlikte kontrol edilir.",
            "Yalnız açıkça belirtilen ve DNS yanıtında bulunan genel IP kontrol edilir.",
            "Sabit 10 TCP portuna yalnız bağlantı denemesi yapılır; "
            "veri veya banner alınmaz.",
            "Açık port bir ürün, sürüm, zafiyet veya sahiplik kanıtı değildir.",
        ]

        def result() -> ServiceScanResult:
            return validate_service_scan_result(
                ServiceScanResult(
                    domain,
                    requested,
                    started_at,
                    self.now(),
                    SERVICE_POLICY_VERSION,
                    dns_status,
                    addresses,
                    checked_address,
                    tuple(ports),
                    tuple(errors),
                    tuple(notes),
                )
            )

        try:
            context = self.context_factory()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                raise _ProbeFailure("TLS sertifika doğrulaması devre dışı bırakılamaz.")
            context.set_alpn_protocols(["http/1.1"])
            answer4 = self._resolve(context, domain, 1, overall_deadline)
            answer6 = self._resolve(context, domain, 28, overall_deadline)
            if answer4[0] != answer6[0]:
                raise _ProbeFailure("A ve AAAA sorguları çelişen DNS durumu bildirdi.")
            addresses = tuple(
                sorted(
                    set(answer4[1] + answer6[1]),
                    key=lambda value: (
                        ipaddress.ip_address(value).version,
                        int(ipaddress.ip_address(value)),
                    ),
                )
            )
            if len(addresses) > 16:
                raise _ProbeFailure("DNS yanıtı 16 adres sınırını aştı.")
            if answer4[0] == 3:
                dns_status = "nxdomain"
                errors.append(
                    "DNS sağlayıcısı alan adını bulamadı; portlara bağlanılmadı."
                )
                return result()
            if not addresses:
                dns_status = "no_address"
                errors.append("A/AAAA adresi bulunamadı; portlara bağlanılmadı.")
                return result()
            if not all(is_public_address(address) for address in addresses):
                dns_status = "blocked"
                errors.append(
                    "Özel, yerel veya özel kullanım IP görüldü; "
                    "tüm bağlantılar engellendi."
                )
                return result()
            if requested not in addresses:
                dns_status = "address_mismatch"
                errors.append("Onaylanan IP güncel DNS yanıtında yok; portlara bağlanılmadı.")
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

        for port in SERVICE_PORTS:
            state = self._port_state(requested, port, overall_deadline)
            ports.append(ServicePortResult(port, state, SERVICE_PORT_HINTS[port]))
            if state == "unknown":
                errors.append(f"TCP {port}: bağlantı sonucu süre sınırında belirlenemedi.")
        return result()
