"""Periodic command wiring is read-only and keeps scope explicit."""

import unittest

from tests import test_collection_watch_cli as fixtures


class PeriodicChangesCLITests(unittest.TestCase):
    setUp = fixtures.CollectionWatchCLITests.setUp
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files
    add_social = fixtures.CollectionWatchCLITests.add_social

    def test_daily_and_weekly_json_and_terminal_are_readonly(self):
        self.add_social()
        before = self.files()
        for days in ("1", "7"):
            report = self.result("changes", "--days", days, "--limit", "1")
            self.assertEqual(report["window"]["days"], int(days))
            self.assertTrue(report["sections"])
            self.assertTrue(report["notes"])
        code, output, error = self.invoke("changes", "--days", "7", as_json=False)
        self.assertEqual((code, error), (0, ""))
        self.assertTrue(output.strip())
        self.assertEqual(self.files(), before)
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.maigret.calls, [])

    def test_domain_filter_does_not_claim_username_ownership(self):
        self.add_social()
        report = self.result("changes", "--domain", "example.com", "--days", "7")
        self.assertEqual(report["scope"]["domain"], "example.com")
        self.assertFalse(any("username" in section["family"] for section in report["sections"]))
        self.assertTrue(report["notes"])

    def test_unknown_domain_and_bad_limit_do_not_write(self):
        before = self.files()
        for options in (("--domain", "unknown.example"), ("--limit", "0"), ("--limit", "501")):
            code, _, _ = self.invoke("changes", *options)
            self.assertNotEqual(code, 0)
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
