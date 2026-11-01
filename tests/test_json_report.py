"""Atomic report publishing must not damage existing evidence or partial outputs."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.json_report import write_report
from xti.domain.assets import ValidationError


class JsonReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_json_round_trip_and_terminal_sequences_are_escaped(self):
        path = self.root / "report.json"
        content = {"reason": "Kontrol\x1b[31m\naldatıcı", "version": 1}
        self.assertEqual(write_report(content, path), path)
        self.assertEqual(json.loads(path.read_bytes()), content)
        self.assertNotIn(b"\x1b", path.read_bytes())
        self.assertEqual(list(self.root.glob(".xti-report-*")), [])

    def test_existing_file_or_dangling_symlink_is_not_replaced(self):
        existing = self.root / "existing"
        existing.write_bytes(b"important")
        link = self.root / "link"
        link.symlink_to(self.root / "absent")
        for path in (existing, link):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                write_report({}, path)
        self.assertEqual(existing.read_bytes(), b"important")
        self.assertTrue(link.is_symlink())
        self.assertFalse((self.root / "absent").exists())

    def test_race_creating_destination_keeps_other_file_and_cleans_temporary(self):
        target = self.root / "report.json"

        def concurrent_write(source, destination):
            destination.write_bytes(b"other report")
            raise FileExistsError("already exists")

        with patch("xti.adapters.json_report.os.link", side_effect=concurrent_write):
            with self.assertRaises(FileExistsError):
                write_report({"new": True}, target)
        self.assertEqual(target.read_bytes(), b"other report")
        self.assertEqual(list(self.root.glob(".xti-report-*")), [])

    def test_oversized_report_rejected_before_creating_directory(self):
        with patch("xti.adapters.json_report.MAX_REPORT_BYTES", 100):
            with self.assertRaises(ValidationError):
                write_report({"data": "x" * 101}, self.root / "new" / "report.json")
        self.assertFalse((self.root / "new").exists())

    def test_failed_write_does_not_publish_partial_file(self):
        path = self.root / "report.json"
        with patch("xti.adapters.json_report.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                write_report({}, path)
        self.assertFalse(path.exists())
        self.assertEqual(list(self.root.glob(".xti-report-*")), [])


if __name__ == "__main__":
    unittest.main()
