"""Bounded, cancellable Nmap subprocess and strictly scoped XML evidence."""

from contextlib import contextmanager
import errno
import fcntl
import hashlib
import ipaddress
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import threading
import time
from xml.etree import ElementTree

from xti.adapters.nmap_scan import SubprocessNmapRuntime, NMAP_MAX_XML_BYTES, NMAP_MAX_DIAGNOSTIC_BYTES
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.assets import ValidationError
from xti.domain.nmap_execution import (PORT_STATES, MAX_RESULT_PORTS,
    MAX_SCRIPT_TEXT, bounded_text, empty_result, encoded, validate_result)
from xti.domain.nmap_execution import result_byte_limit
from xti.domain.nmap_management import normalize_managed_plan_definition, target_addresses
from xti.domain.nmap_options import NmapExecutionOptions
from xti.domain.nmap_scan import port_spec_contains
from xti.ports.jobs import WorkerBusyError


class NmapWorkerLock(LocalExecutionLock):
    @contextmanager
    def acquire(self):
        descriptor = self._open()
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in {errno.EACCES, errno.EAGAIN}:
                    raise WorkerBusyError("Başka bir motor/çocuk süreç çalışıyor; kurtarma veya yeni tarama beklemeli.") from error
                raise
            yield descriptor
        finally:
            os.close(descriptor)  # Child inherits flock; never explicitly unlock it.


def requires_privilege(plan):
    options = plan.definition.options or NmapExecutionOptions()
    return plan.definition.scan_type in {"tcp_syn", "udp"} or options.os_detection


@contextmanager
def _termination_guard():
    """Let normal worker termination run process cleanup and persist uncertainty."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGTERM)
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def build_command(executable, plan, address):
    value = normalize_managed_plan_definition(plan.definition)
    if address not in target_addresses(value.target_definition):
        raise ValidationError("Nmap hedefi plan kapsamında değil.")
    options = value.options or NmapExecutionOptions()
    command = [executable, {"tcp_connect": "-sT", "tcp_syn": "-sS", "udp": "-sU"}[value.scan_type],
        "-Pn", "-n", "--privileged" if requires_privilege(plan) else "--unprivileged", "--reason",
        "--max-rate", str(value.max_rate_pps), "--max-retries", str(value.max_retries),
        "--host-timeout", f"{value.timeout_seconds}s", "--scan-delay", f"{value.scan_delay_ms}ms",
        "--max-parallelism", str(value.max_parallelism), "--max-hostgroup", "1",
        "-p", value.port_spec, "-oX", "-"]
    if options.service_detection:
        command += ["-sV", "--version-intensity", str(options.version_intensity)]
    if options.os_detection:
        command += ["-O", "--osscan-limit", "--max-os-tries", "1"]
    if options.scripts:
        command += ["--script", ",".join(options.scripts), "--script-timeout", f"{options.script_timeout_seconds}s"]
        if "smb-vuln-ms17-010" in options.scripts:
            command += ["--script-args", "smbport=445"]
    if ipaddress.ip_address(address).version == 6:
        command.append("-6")
    command.append(address)
    return command


def parse_xml(content, plan, address, tool_version):
    if not content or len(content) > NMAP_MAX_XML_BYTES:
        raise ValidationError("Nmap XML boyutu geçersiz.")
    # Nmap itself writes this declaration. No external/internal subsets are accepted.
    xml = content.replace(b"<!DOCTYPE nmaprun>", b"", 1)
    if b"\x00" in xml or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValidationError("Nmap XML harici/iç varlık bildirimi içeremez.")
    try:
        root = ElementTree.fromstring(xml.decode("utf-8", "strict"))
    except (ValueError, ElementTree.ParseError, RecursionError) as error:
        raise ValidationError("Nmap XML ayrıştırılamadı.") from error
    nodes, pending = 0, [(root, 0)]
    while pending:
        node, depth = pending.pop()
        nodes += 1
        if nodes > 150000 or depth > 20:
            raise ValidationError("Nmap XML yapı sınırı aşıldı.")
        pending.extend((child, depth + 1) for child in node)
    hosts, finished = root.findall("host"), root.find("./runstats/finished")
    if (root.tag != "nmaprun" or root.get("scanner") != "nmap" or root.get("version") != tool_version
            or len(hosts) != 1 or finished is None or finished.get("exit") != "success"):
        raise ValidationError("Nmap tamamlanma/araç kanıtı geçersiz.")
    host = hosts[0]
    addresses = {a.get("addr") for a in host.findall("address") if a.get("addrtype") in {"ipv4", "ipv6"}}
    if addresses != {address}:
        raise ValidationError("Nmap XML onaylanan kesin IP ile eşleşmiyor.")
    value = plan.definition
    protocol = "udp" if value.scan_type == "udp" else "tcp"
    options = value.options or NmapExecutionOptions()
    info = root.findall("scaninfo")
    if len(info) != 1 or info[0].get("protocol") != protocol:
        raise ValidationError("Nmap XML tarama protokolü planla uyuşmuyor.")
    from xti.domain.nmap_scan import canonical_port_spec
    specification, count = canonical_port_spec(info[0].get("services", ""))
    if specification != value.port_spec or count != value.port_count:
        raise ValidationError("Nmap XML port kapsamı planla uyuşmuyor.")
    result = empty_result(address, "complete", "")
    result.update(tool_version=tool_version, xml_sha256=hashlib.sha256(content).hexdigest())
    counts, seen = {}, set()
    for extra in host.findall("./ports/extraports"):
        state = extra.get("state")
        try:
            count = int(extra.get("count", ""))
        except ValueError as error:
            raise ValidationError("Nmap toplu port sayısı geçersiz.") from error
        if state not in PORT_STATES or not 0 <= count <= value.port_count:
            raise ValidationError("Nmap toplu port durumu geçersiz.")
        counts[state] = counts.get(state, 0) + count

    script_nodes = []
    for item in host.findall("./ports/port"):
        try:
            port = int(item.get("portid", ""))
        except ValueError as error:
            raise ValidationError("Nmap port kimliği geçersiz.") from error
        state_node = item.find("state")
        state = state_node.get("state") if state_node is not None else None
        if (item.get("protocol") != protocol or port in seen or not port_spec_contains(value.port_spec, port)
                or state not in PORT_STATES):
            raise ValidationError("Nmap port sonucu planla uyuşmuyor.")
        seen.add(port)
        counts[state] = counts.get(state, 0) + 1
        if len(result["ports"]) < MAX_RESULT_PORTS:
            service_node = item.find("service")
            service = {}
            if service_node is not None:
                names = ["name", "method", "tunnel"]
                if options.service_detection:
                    names += ["product", "version", "extrainfo"]
                service = {k: bounded_text(service_node.get(k), 500) for k in names if service_node.get(k) is not None}
                if service_node.get("conf") is not None:
                    service["confidence"] = bounded_text(service_node.get("conf"), 500)
            result["ports"].append({"port": port, "protocol": protocol, "state": state,
                "reason": bounded_text(state_node.get("reason", ""), 100), "service": service})
        else:
            result["truncated"] = True
        script_nodes.extend((child, port) for child in item.findall("script"))
    script_nodes.extend((child, None) for child in host.findall("./hostscript/script"))
    for child, port in script_nodes:
        script_id = child.get("id")
        if script_id not in options.scripts:
            # -sV may produce automatic version-category script data. It is not a selected check.
            if options.service_detection:
                continue
            raise ValidationError("Nmap seçilmemiş NSE sonucu içeriyor.")
        if len(result["scripts"]) >= 128:
            result["truncated"] = True
            continue
        output = child.get("output", "")
        result["scripts"].append({"id": script_id, "port": port,
            "output": bounded_text(output, MAX_SCRIPT_TEXT), "truncated": len(output) > MAX_SCRIPT_TEXT})
        if len(output) > MAX_SCRIPT_TEXT:
            result["truncated"] = True
    if options.os_detection:
        matches = host.findall("./os/osmatch")
        if len(matches) > 16:
            result["truncated"] = True
        for match in matches[:16]:
            try:
                accuracy = int(match.get("accuracy", ""))
            except ValueError as error:
                raise ValidationError("Nmap OS olasılığı geçersiz.") from error
            result["os_matches"].append({"name": bounded_text(match.get("name", ""), 500), "accuracy": accuracy})
    total = sum(counts.values())
    if total > value.port_count:
        raise ValidationError("Nmap port sayısı kapsamı aşıyor.")
    if total < value.port_count:
        counts["unknown"] = counts.get("unknown", 0) + value.port_count - total
        result["status"] = "partial"
        result["reason"] = "Eksik port sonuçları bilinmiyor olarak korundu."
    result["port_states"] = counts
    result["ports"].sort(key=lambda item: item["port"])
    # Retain aggregate counts if individual records exceed the bounded evidence envelope.
    # Leave room for explicit missing-output metadata and the final status message.
    while len(encoded(result)) > result_byte_limit(plan) - 512 and (result["ports"] or result["scripts"] or result["os_matches"]):
        (result["ports"] if result["ports"] else result["scripts"] if result["scripts"] else result["os_matches"]).pop()
        result["truncated"] = True
    if result["truncated"]:
        result["status"] = "partial"
        result["reason"] = "Ayrıntı saklama sınırına ulaşıldı; port durum toplamları korundu."
    result["scripts_without_output"] = sorted(set(options.scripts) - {s["id"] for s in result["scripts"]})
    if host.get("timedout") == "true":
        result["status"] = "timeout"
        result["reason"] = "Nmap hedef süre sınırına ulaştı; görülen kısmi kanıt korundu."
    return validate_result(result, plan, address)


class ManagedNmapRuntime:
    def __init__(self, executable=None):
        self.runtime = SubprocessNmapRuntime(executable)

    def readiness(self, plan):
        version, executable = self.runtime.readiness()
        if requires_privilege(plan) and os.geteuid() != 0:
            raise ValidationError("SYN/UDP/OS için ayrı yetkili çalıştırıcı gerekiyor; motor otomatik sudo çalıştırmaz.")
        return {"version": version, "executable": executable,
                "privileged": requires_privilege(plan), "effective_hostgroup": 1}

    def run(self, plan, address, *, should_stop, lock_fd, duration_seconds):
        ready = self.readiness(plan)
        command = build_command(ready["executable"], plan, address)
        if should_stop():
            return empty_result(address, "cancelled", "İptal isteği alındı.")
        limit = min(duration_seconds, plan.definition.timeout_seconds + 10)
        deadline = time.monotonic() + limit
        buffers = {"xml": bytearray(), "diagnostic": bytearray()}
        process = None
        with _termination_guard(), tempfile.TemporaryDirectory(prefix="xti-managed-nmap-") as directory:
            directory = str(Path(directory).resolve())
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                    close_fds=True, pass_fds=(lock_fd,), cwd=directory,
                    env={"PATH": os.defpath, "HOME": directory, "LANG": "C", "LC_ALL": "C"})
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ, "xml")
                    selector.register(process.stderr, selectors.EVENT_READ, "diagnostic")
                    next_poll = 0.0
                    # EOF is not process completion. Keep checking cancellation
                    # if a child closes its output streams before it exits.
                    while selector.get_map() or process.poll() is None:
                        now = time.monotonic()
                        if now >= deadline:
                            return empty_result(address, "timeout", "Çalışma süre sınırına ulaşıldı.")
                        if now >= next_poll:
                            if should_stop():
                                return empty_result(address, "cancelled", "İptal isteği alındı.")
                            next_poll = now + 0.5
                        for key, _mask in selector.select(min(0.2, max(0, deadline - now))):
                            chunk = os.read(key.fd, 65536)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            buffers[key.data].extend(chunk)
                            maximum = NMAP_MAX_XML_BYTES if key.data == "xml" else NMAP_MAX_DIAGNOSTIC_BYTES
                            if len(buffers[key.data]) > maximum:
                                return empty_result(address, "failed", "Nmap çıktı sınırı aşıldı.")
                    try:
                        code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        return empty_result(address, "timeout", "Nmap süreç süre sınırı aşıldı.")
                    if code != 0:
                        return empty_result(address, "failed", "Nmap işlemi başarısız; sistem yetkisini ve kurulumu kontrol edin.")
                try:
                    return parse_xml(bytes(buffers["xml"]), plan, address, ready["version"])
                except ValidationError:
                    return empty_result(address, "failed", "Nmap XML kanıtı doğrulanamadı.")
            except OSError as error:
                raise ValidationError("Nmap işlemi başlatılamadı veya çıktısı okunamadı.") from error
            finally:
                if process is not None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)
                    process.stdout.close()
                    process.stderr.close()
