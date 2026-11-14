"""Organization source views retain each explicit domain and provider denominator."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_organization_contribution import SQLiteOrganizationContributionRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.organization_contribution import OrganizationContributionService
from xti.application.organizations import OrganizationService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from tests import test_source_contribution as fixtures


class OrganizationContributionTests(unittest.TestCase):
    surface = fixtures.SourceContributionTests.surface
    scan = fixtures.SourceContributionTests.scan

    def setUp(self):
        fixtures.SourceContributionTests.setUp(self)
        self.organizations = OrganizationService(SQLiteOrganizationRepository(self.path), LocalExecutionLock(self.path))
        self.organization = self.organizations.add("Örnek kuruluş", reason="Açık kullanıcı gruplaması.").organization
        self.other_organization = self.organizations.add("Diğer kuruluş", reason="Ayrı kullanıcı gruplaması.").organization
        self.link = self.organizations.link(self.organization.id, kind="domain", value=self.asset.value, reason="Açık seçim.").link
        self.organizations.link(self.other_organization.id, kind="domain", value=self.other.value, reason="Ayrı seçim.")
        self.service = OrganizationContributionService(SQLiteOrganizationContributionRepository(self.path))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Read-only comparison")))

    def files(self):
        return {str(path.relative_to(self.path.parent)): path.read_bytes()
                for path in self.path.parent.rglob("*") if path.is_file()}

    def test_only_explicit_current_domains_and_evidence_are_returned_without_writes(self):
        own = self.surface("crt.sh", ["a.example.com"])
        self.surface("crt.sh", ["hidden.other.example"], asset=self.other)
        before = self.files()
        result = self.service.show(self.organization.id)
        self.assertEqual(result.total_domain_count, 1)
        self.assertEqual([value.asset_value for value in result.domains], ["example.com"])
        page = result.domains[0].groups[0].union_domains
        self.assertEqual([value.domain for value in page.items], ["a.example.com"])
        self.assertNotIn("hidden.other.example", repr(result))
        self.assertEqual(self.files(), before)

    def test_revoked_membership_and_organization_produce_empty_effective_scope(self):
        self.organizations.unlink(self.organization.id, self.link.id, reason="Artık izlenmiyor.")
        self.assertEqual(self.service.show(self.organization.id).total_domain_count, 0)
        self.organizations.link(self.organization.id, kind="domain", value=self.asset.value, reason="Tekrar seçildi.")
        self.organizations.revoke(self.organization.id, reason="Grup kapatıldı.")
        result = self.service.show(self.organization.id)
        self.assertEqual(result.total_domain_count, 0)
        self.assertEqual(result.scope.excluded_link_count, 1)

    def test_domain_and_evidence_paging_keep_true_counts_and_attempt_denominators(self):
        self.organizations.link(self.organization.id, kind="domain", value=self.other.value, reason="Açık ikinci seçim.")
        self.surface("crt.sh", ["a.example.com", "b.example.com"])
        self.surface("theharvester", ["b.example.com", "c.example.com"])
        self.scan("crt.sh", ["example-support.net"])
        self.scan("crt.sh", status="failed")
        first = self.service.show(self.organization.id, limit=1, detail_limit=1)
        second = self.service.show(self.organization.id, offset=1, limit=1)
        self.assertEqual((first.total_domain_count, second.total_domain_count), (2, 2))
        self.assertEqual([first.domains[0].asset_value, second.domains[0].asset_value], ["example.com", "other.example"])
        self.assertEqual(first.domains[0].groups[0].union_domains.total_count, 3)
        brand = next(group for group in first.domains[0].groups if group.family == "brand")
        outcome = next(item.outcomes for item in brand.sources if item.provider == "crt.sh")
        self.assertEqual((outcome.completion_numerator, outcome.completion_denominator), (1, 2))

    def test_invalid_selection_and_cli_conflicting_scope_fail_without_data_change(self):
        before = self.files()
        with self.assertRaises(ValidationError):
            self.service.show(self.organization.id, limit=0)
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(self.path.parent), "--json", "sources", "contribution", "example.com", "--organization", self.organization.id])
        self.assertEqual(code, 2)
        self.assertEqual(self.files(), before)

    def test_cli_reports_empty_history_as_unknown_and_keeps_domain_mode(self):
        before = self.files()
        for selection in (["--organization", self.organization.id], ["example.com"]):
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["--data-dir", str(self.path.parent), "--json", "sources", "contribution", *selection])
            self.assertEqual((code, stderr.getvalue()), (0, ""))
            payload = json.loads(stdout.getvalue())["data"]
            groups = payload["domains"][0]["groups"] if "domains" in payload else payload["groups"]
            self.assertEqual(groups[0]["comparison_state"], "insufficient_history")
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
