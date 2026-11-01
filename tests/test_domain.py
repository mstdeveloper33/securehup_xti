"""The first release accepts explicit ASCII domain names only."""

import unittest

from xti.domain.assets import ValidationError, normalize_domain


class DomainValidationTests(unittest.TestCase):
    def test_case_spaces_and_root_dot_share_a_canonical_value(self):
        self.assertEqual(normalize_domain("  EXAMPLE.COM.  "), "example.com")
        self.assertEqual(normalize_domain("support.example.com"), "support.example.com")

    def test_accepts_dns_length_boundary(self):
        value = ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 61])
        self.assertEqual(len(value), 253)
        self.assertEqual(normalize_domain(value), value)

    def test_rejects_ambiguous_or_unsafe_input(self):
        invalid = [
            "", "   ", "localhost", "https://example.com", "example.com/path",
            "example.com:443", "user@example.com", "*.example.com", "a_b.example.com",
            "127.0.0.1", "::1", "[::1]", "-example.com", "example-.com",
            "example..com", "example.com..", "ex ample.com", "örnek.com",
            "exa\x1bmple.com", "exa\nmple.com", "a" * 64 + ".com",
            ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 62]),
        ]
        for value in invalid:
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValidationError):
                    normalize_domain(value)


if __name__ == "__main__":
    unittest.main()
