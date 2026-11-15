"""Keep reviewed pins, separate installers and metadata checks consistent."""

import ast
from contextlib import redirect_stderr
from dataclasses import FrozenInstanceError
import hashlib
import importlib.util
from io import StringIO
import json
from pathlib import Path
import re
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from xti.adapters import maigret_username, sherlock_username, theharvester_archive
from xti.adapters.source_readiness import LocalSourceInstallationInspector
from xti.domain.component_pins import (
    HARVESTER_PIN,
    MAIGRET_PIN,
    REVIEWED_COMPONENT_PINS,
    SHERLOCK_PIN,
    component_pin,
)


PROJECT = Path(__file__).resolve().parents[1]
VERIFIER_SPEC = importlib.util.spec_from_file_location(
    "xti_test_brand_verifier", PROJECT / "scripts" / "verify_brand_install.py"
)
VERIFIER = importlib.util.module_from_spec(VERIFIER_SPEC)
VERIFIER_SPEC.loader.exec_module(VERIFIER)


class ReviewedComponentPinTests(unittest.TestCase):
    def test_lookup_is_exact_and_pins_are_immutable(self):
        self.assertEqual(
            tuple(pin.identifier for pin in REVIEWED_COMPONENT_PINS),
            ("maigret", "sherlock", "theharvester"),
        )
        for pin in REVIEWED_COMPONENT_PINS:
            self.assertIs(component_pin(pin.identifier), pin)
        with self.assertRaises(ValueError):
            component_pin("Maigret")
        with self.assertRaises(ValueError):
            component_pin("unknown")
        with self.assertRaises(FrozenInstanceError):
            MAIGRET_PIN.version = "unreviewed"

    def test_reviewed_metadata_preserves_license_and_verification_boundaries(self):
        notices = (PROJECT / "THIRD_PARTY_NOTICES.md").read_text()
        for pin in REVIEWED_COMPONENT_PINS:
            with self.subTest(component=pin.identifier):
                self.assertRegex(pin.commit, r"^[a-f0-9]{40}$")
                self.assertIn(pin.commit, notices)
                self.assertIn(f"Lisans: {pin.license_spdx}", notices)
                self.assertEqual(
                    pin.license_reference_url,
                    f"{pin.repository.removesuffix('.git')}/blob/{pin.commit}/LICENSE",
                )
                self.assertTrue((PROJECT / pin.setup_command[0]).is_file())
        for pin in (MAIGRET_PIN, SHERLOCK_PIN):
            self.assertEqual(pin.license_spdx, "MIT")
            self.assertEqual(pin.python_requirement, ">=3.11")
            self.assertEqual(pin.deployment, "project-venv")
            self.assertGreater(pin.catalog_size, 0)
            self.assertRegex(pin.catalog_sha256, r"^[a-f0-9]{64}$")
            self.assertEqual(pin.verify_command, ("./scripts/setup-brand", "--check"))
        self.assertEqual(HARVESTER_PIN.license_spdx, "GPL-2.0-only")
        self.assertEqual(HARVESTER_PIN.python_requirement, ">=3.14")
        self.assertEqual(HARVESTER_PIN.deployment, "isolated-tool-venv")
        self.assertIsNone(HARVESTER_PIN.version)
        self.assertIsNone(HARVESTER_PIN.catalog_size)
        self.assertIsNone(HARVESTER_PIN.catalog_sha256)
        self.assertEqual(HARVESTER_PIN.verify_command, ())

    def test_adapter_aliases_preserve_historical_profiles(self):
        for adapter, pin, profile in (
            (maigret_username, MAIGRET_PIN, "maigret-0.6.6-b8747b98820f-safe-v1"),
            (sherlock_username, SHERLOCK_PIN, "sherlock-0.16.2-a38ba54fda79-safe-v1"),
            (theharvester_archive, HARVESTER_PIN, "theharvester-6790b147f523-p0-archives-v3"),
        ):
            with self.subTest(component=pin.identifier):
                self.assertEqual(adapter.INTEGRATION_PROFILE, profile)
                self.assertEqual(pin.integration_profile, profile)
                self.assertEqual(adapter.REVIEWED_UPSTREAM_COMMIT, pin.commit)
        for adapter, pin in ((maigret_username, MAIGRET_PIN), (sherlock_username, SHERLOCK_PIN)):
            self.assertEqual(adapter.SOURCE_NAME, pin.label)
            self.assertEqual(adapter.SOURCE_VERSION, pin.version)
            self.assertEqual(adapter.REVIEWED_DATABASE_SHA256, pin.catalog_sha256)
        self.assertEqual(theharvester_archive.SOURCE_NAME, "theHarvester P0 arşivleri")
        self.assertEqual(theharvester_archive.PROVIDER, HARVESTER_PIN.identifier)

    def test_packaging_pins_match_registry(self):
        with (PROJECT / "pyproject.toml").open("rb") as stream:
            metadata = tomllib.load(stream)
        self.assertEqual(
            metadata["project"]["optional-dependencies"]["brand"],
            [
                f"{pin.distribution} @ git+{pin.repository}@{pin.commit}"
                for pin in (MAIGRET_PIN, SHERLOCK_PIN)
            ],
        )
        self.assertEqual(metadata["project"]["requires-python"], MAIGRET_PIN.python_requirement)

    def test_separate_harvester_installer_pins_match_registry(self):
        script = (PROJECT / "scripts" / "setup-harvester").read_text()
        for variable, expected in (
            ("XTI_UPSTREAM", HARVESTER_PIN.repository),
            ("XTI_COMMIT", HARVESTER_PIN.commit),
        ):
            self.assertEqual(
                re.findall(rf'^{variable}="([^"\n]+)"$', script, re.MULTILINE),
                [expected],
            )

    def test_isolated_sherlock_worker_version_guard_matches_registry(self):
        worker = PROJECT / "src" / "xti" / "adapters" / "sherlock_username_worker.py"
        tree = ast.parse(worker.read_text())
        version_guards = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name) and node.left.id == "__version__"
        ]
        self.assertEqual(len(version_guards), 1)
        guard = version_guards[0]
        self.assertEqual(len(guard.ops), 1)
        self.assertIsInstance(guard.ops[0], ast.NotEq)
        self.assertEqual(ast.literal_eval(guard.comparators[0]), SHERLOCK_PIN.version)


class BrandVerifierMetadataTests(unittest.TestCase):
    def test_verifier_consumes_reviewed_brand_pins(self):
        self.assertEqual(len(VERIFIER.TOOLS), 2)
        for tool, pin in zip(VERIFIER.TOOLS, (MAIGRET_PIN, SHERLOCK_PIN), strict=True):
            self.assertEqual(tool["name"], pin.label)
            for field in (
                "distribution", "package", "version", "repository", "commit",
                "catalog_size", "catalog_sha256",
            ):
                self.assertEqual(tool[field], getattr(pin, field))

    @staticmethod
    def installed(tool, prefix, raw):
        class Installed:
            metadata = {"Name": tool["distribution"]}
            version = tool["version"]

            def locate_file(self, value):
                return prefix / value

            def read_text(self, _name):
                return raw

        return Installed()

    def test_non_object_and_malformed_git_records_are_controlled_failures(self):
        invalid_records = (
            None, "[]", "null", "42", "true", '"metadata"', "[{}]", "{",
            '{}', '{"url":"first","url":"second"}',
        )
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            for tool in VERIFIER.TOOLS:
                nested_records = tuple(
                    json.dumps({"url": tool["repository"], "vcs_info": vcs})
                    for vcs in (None, [], "git", 1, {})
                )
                for raw in invalid_records + nested_records:
                    with self.subTest(tool=tool["name"], record=raw), \
                         patch.object(VERIFIER, "distribution", return_value=self.installed(tool, prefix, raw)), \
                         patch.object(VERIFIER, "files") as package_files:
                        with self.assertRaises(VERIFIER.VerificationError):
                            VERIFIER._verify_distribution(tool, prefix)
                        package_files.assert_not_called()

    def test_valid_commit_and_catalog_pass_then_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            payload = b'{"sites":{}}'
            for reviewed_tool in VERIFIER.TOOLS:
                tool = dict(reviewed_tool, catalog_size=len(payload), catalog_sha256=hashlib.sha256(payload).hexdigest())
                package = prefix / tool["package"]
                catalog = package / "resources" / "data.json"
                catalog.parent.mkdir(parents=True)
                catalog.write_bytes(payload)
                record = {
                    "url": tool["repository"],
                    "vcs_info": {"vcs": "git", "commit_id": tool["commit"], "requested_revision": tool["commit"]},
                }
                installed = self.installed(tool, prefix, json.dumps(record))
                with self.subTest(tool=tool["name"]), \
                     patch.object(VERIFIER, "distribution", return_value=installed), \
                     patch.object(VERIFIER, "files", return_value=package):
                    VERIFIER._verify_distribution(tool, prefix)
                    catalog.write_bytes(b"x" * len(payload))
                    with self.assertRaisesRegex(VERIFIER.VerificationError, "özeti"):
                        VERIFIER._verify_distribution(tool, prefix)
                    catalog.write_bytes(payload)
                    record["vcs_info"]["commit_id"] = "0" * 40
                    wrong_commit = self.installed(tool, prefix, json.dumps(record))
                    with patch.object(VERIFIER, "distribution", return_value=wrong_commit):
                        with self.assertRaisesRegex(VERIFIER.VerificationError, "commit"):
                            VERIFIER._verify_distribution(tool, prefix)

    def test_invalid_record_returns_friendly_command_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            tool = VERIFIER.TOOLS[0]
            installed = self.installed(tool, prefix, "[]")
            stderr = StringIO()
            with patch.object(VERIFIER, "distribution", return_value=installed), \
                 patch.object(VERIFIER, "verify", side_effect=lambda path: VERIFIER._verify_distribution(tool, path)), \
                 redirect_stderr(stderr):
                self.assertEqual(VERIFIER.main(["--prefix", str(prefix)]), 1)
            self.assertIn("Marka araçları doğrulanamadı", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_inspector_rejects_non_object_metadata_without_executing_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            venv = project / ".venv"
            site = venv / "lib" / "python3.11" / "site-packages"
            site.mkdir(parents=True)
            executable = venv / "bin" / "python"
            executable.parent.mkdir()
            executable.write_text("metadata fixture; must not execute")
            executable.chmod(0o700)
            inspector = LocalSourceInstallationInspector(project)
            for tool, pin in zip(VERIFIER.TOOLS, (MAIGRET_PIN, SHERLOCK_PIN), strict=True):
                for raw in ("[]", "null", "42", "true", '"metadata"'):
                    installed = self.installed(tool, site, raw)
                    with self.subTest(component=pin.identifier, record=raw), \
                         patch("xti.adapters.source_readiness.distributions", return_value=(installed,)), \
                         patch("subprocess.run", side_effect=AssertionError("tool executed")):
                        state, reason = inspector.inspect(pin.identifier)
                        self.assertEqual(state, "invalid")
                        self.assertIn("commit", reason)


if __name__ == "__main__":
    unittest.main()
