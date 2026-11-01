"""Network boundaries for the pinned, fixed-plan TCP service probe."""

import socket
import ssl
import unittest

from xti.adapters.service_probe import BoundedServicePortProbe
from xti.domain.assets import ValidationError
from xti.domain.services import SERVICE_PORTS


ADDRESS = "93.184.216.34"


class Context:
    def __init__(self, *, valid=True):
        self.check_hostname = valid
        self.verify_mode = ssl.CERT_REQUIRED if valid else ssl.CERT_NONE
        self.alpn = None

    def set_alpn_protocols(self, value):
        self.alpn = value


class PortSocket:
    def __init__(self, states, calls):
        self.states = states
        self.calls = calls
        self.closed = False

    def settimeout(self, value):
        if value <= 0:
            raise TimeoutError("expired")

    def connect(self, target):
        self.calls.append(target)
        state = self.states.get(target[1], "closed")
        if state == "closed":
            raise ConnectionRefusedError("refused")
        if state == "unknown":
            raise TimeoutError("timeout")

    def close(self):
        self.closed = True


class FixtureProbe(BoundedServicePortProbe):
    def __init__(self, answers, states=None, *, context=None):
        self.answers = answers
        self.connections = []
        self.context = context or Context()
        states = states or {}
        super().__init__(
            socket_factory=lambda family, kind: PortSocket(states, self.connections),
            context_factory=lambda: self.context,
            monotonic=lambda: 100.0,
            now=lambda: "2026-10-29T12:00:00+00:00",
        )

    def _resolve(self, context, domain, record_type, overall_deadline):
        return self.answers[record_type]


class ServiceProbeTests(unittest.TestCase):
    def test_exact_fixed_plan_is_pinned_and_never_reads_banner(self):
        probe = FixtureProbe(
            {1: (0, (ADDRESS,)), 28: (0, ())},
            states={22: "open", 443: "open", 25: "unknown"},
        )
        result = probe.check("example.com", ADDRESS)
        self.assertEqual(result.dns_status, "resolved")
        self.assertEqual(result.checked_address, ADDRESS)
        self.assertEqual([item.port for item in result.ports], list(SERVICE_PORTS))
        self.assertEqual(
            [item.port for item in result.ports if item.state == "open"], [22, 443],
        )
        self.assertEqual(
            [item.port for item in result.ports if item.state == "unknown"], [25],
        )
        self.assertEqual(
            probe.connections, [(ADDRESS, port) for port in SERVICE_PORTS],
        )
        self.assertEqual(len(result.errors), 1)

    def test_unlisted_or_nonpublic_dns_address_blocks_every_target_connection(self):
        mismatch = FixtureProbe({1: (0, (ADDRESS,)), 28: (0, ())})
        result = mismatch.check("example.com", "8.8.8.8")
        self.assertEqual(result.dns_status, "address_mismatch")
        self.assertEqual(
            (result.checked_address, result.ports, mismatch.connections),
            (None, (), []),
        )

        private = FixtureProbe({1: (0, ("10.0.0.1", ADDRESS)), 28: (0, ())})
        result = private.check("example.com", ADDRESS)
        self.assertEqual(result.dns_status, "blocked")
        self.assertEqual(
            (result.checked_address, result.ports, private.connections),
            (None, (), []),
        )

    def test_dns_absence_and_tls_safety_failure_are_failed_evidence_without_target_calls(self):
        missing = FixtureProbe({1: (3, ()), 28: (3, ())})
        result = missing.check("example.com", ADDRESS)
        self.assertEqual(result.dns_status, "nxdomain")
        self.assertEqual(missing.connections, [])

        invalid_context = FixtureProbe(
            {1: (0, (ADDRESS,)), 28: (0, ())}, context=Context(valid=False),
        )
        result = invalid_context.check("example.com", ADDRESS)
        self.assertEqual(result.dns_status, "failed")
        self.assertEqual(invalid_context.connections, [])

    def test_invalid_requested_address_stops_before_context_or_socket(self):
        calls = []
        probe = BoundedServicePortProbe(
            socket_factory=lambda family, kind: calls.append("socket"),
            context_factory=lambda: calls.append("context"),
        )
        for value in ("127.0.0.1", "10.0.0.1", "not-an-ip"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                probe.check("example.com", value)
        self.assertEqual(calls, [])

    def test_ipv6_target_uses_numeric_ipv6_socket(self):
        address = "2606:2800:220:1:248:1893:25c8:1946"
        families = []

        def factory(family, kind):
            families.append((family, kind))
            return PortSocket({}, [])

        probe = FixtureProbe({1: (0, ()), 28: (0, (address,))})
        probe.socket_factory = factory
        result = probe.check("example.com", address)
        self.assertEqual(result.dns_status, "resolved")
        self.assertEqual(families, [(socket.AF_INET6, socket.SOCK_STREAM)] * len(SERVICE_PORTS))

    def test_local_socket_resource_failure_becomes_bounded_unknown_evidence(self):
        probe = FixtureProbe({1: (0, (ADDRESS,)), 28: (0, ())})

        def unavailable(family, kind):
            raise OSError("controlled local resource failure")

        probe.socket_factory = unavailable
        result = probe.check("example.com", ADDRESS)
        self.assertEqual([item.state for item in result.ports], ["unknown"] * len(SERVICE_PORTS))
        self.assertEqual(len(result.errors), len(SERVICE_PORTS))
