"""Complete offline HTML, scoped evidence and no-overwrite file publication."""

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from xti.adapters.html_report_writer import AtomicHtmlReportWriter
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_organization_report import SQLiteOrganizationReportRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.organization_export import OrganizationExportService
from xti.domain.assets import ValidationError
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate
from xti.domain.cname import CnameHop
from xti.domain.organization_export import OrganizationExportPublicationError, validate_complete_export
from xti.interfaces.html_organization_report import HtmlOrganizationReportRenderer, safe_external_url
from tests import test_organization_report as fixtures
from tests.test_collection_public_notice_cli import public_catalog
from tests.test_public_notices import item
from tests.test_surface import result as surface_result, certificate
from tests.test_mail import result as mail_result
from tests.test_services import scan_result
from tests.test_cname import cname_result
from tests.test_brand_username_watches import github
from xti.ports.discovery import SourceError


class ParsedHtml(HTMLParser):
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.tags, self.hrefs, self.text = [], [], []
        self.feed(value)

    def handle_starttag(self, tag, attributes):
        self.tags.append(tag)
        self.hrefs.extend(value for name, value in attributes if name == "href")

    def handle_data(self, data):
        self.text.append(data)


class AtomicHtmlWriterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / "rapor.html"
        self.writer = AtomicHtmlReportWriter()

    def assert_no_temporary(self):
        self.assertEqual(tuple(self.root.glob(".xti-report-*.tmp")), ())

    def test_utf8_private_file_and_exact_checksum(self):
        content = "<!doctype html><html><p>Türkçe kuruluş kanıtı</p></html>"
        result = self.writer.write_new(str(self.output), (content[:15], content[15:]), max_bytes=1000)
        self.assertEqual(self.output.read_text(), content)
        self.assertEqual(result.byte_count, len(content.encode()))
        self.assertEqual(result.sha256, hashlib.sha256(content.encode()).hexdigest())
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assert_no_temporary()

    def test_existing_file_and_both_symlink_kinds_are_preserved(self):
        self.output.write_bytes(b"existing")
        for path in (self.output, self.root / "alias.html", self.root / "missing.html"):
            if path.name == "alias.html": path.symlink_to(self.output)
            if path.name == "missing.html": path.symlink_to(self.root / "missing-target")
            with self.subTest(path=path.name), self.assertRaises(ValidationError):
                self.writer.write_new(str(path), ("replacement",), max_bytes=1000)
        self.assertEqual(self.output.read_bytes(), b"existing")
        self.assertFalse((self.root / "missing-target").exists())
        self.assert_no_temporary()

    def test_symlink_parent_is_not_followed_and_missing_directory_not_created(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValidationError):
            self.writer.write_new(str(alias / "new.html"), ("data",), max_bytes=1000)
        with self.assertRaises(FileNotFoundError):
            self.writer.write_new(str(self.root / "missing" / "new.html"), ("data",), max_bytes=1000)
        self.assertFalse((self.root / "new.html").exists())
        self.assertFalse((self.root / "missing").exists())

    def test_concurrent_destination_creation_never_overwrites_winner(self):
        link = os.link
        def race(source, destination, **options):
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600,
                                 dir_fd=options["dst_dir_fd"])
            with os.fdopen(descriptor, "wb") as output:
                output.write(b"other writer")
            return link(source, destination, **options)
        with patch("xti.adapters.html_report_writer.os.link", side_effect=race), self.assertRaises(ValidationError):
            self.writer.write_new(str(self.output), ("our content",), max_bytes=1000)
        self.assertEqual(self.output.read_bytes(), b"other writer")
        self.assert_no_temporary()

    def test_size_limit_render_error_and_interrupt_leave_no_partial_output(self):
        def broken(error):
            yield "partial"
            raise error
        for chunks, error in ((("one", "too large"), ValidationError),
                              (broken(RuntimeError("render failed")), RuntimeError),
                              (broken(KeyboardInterrupt()), KeyboardInterrupt)):
            with self.subTest(error=error), self.assertRaises(error):
                self.writer.write_new(str(self.output), chunks, max_bytes=10)
            self.assertFalse(self.output.exists())
            self.assert_no_temporary()

    def test_sync_failure_before_publication_leaves_none_after_publication_keeps_complete_file(self):
        actual = os.fsync
        for failing in (1, 2):
            calls = 0
            def sync(descriptor):
                nonlocal calls
                calls += 1
                if calls == failing: raise OSError("controlled sync failure")
                return actual(descriptor)
            error = OSError if failing == 1 else OrganizationExportPublicationError
            with self.subTest(failing=failing), patch("xti.adapters.html_report_writer.os.fsync", side_effect=sync), self.assertRaises(error):
                self.writer.write_new(str(self.output), ("complete",), max_bytes=1000)
            if failing == 1:
                self.assertFalse(self.output.exists())
            else:
                self.assertEqual(self.output.read_text(), "complete")
            self.assert_no_temporary()

    def test_post_publication_failure_never_deletes_another_writers_replacement(self):
        actual = os.fsync
        calls = 0
        def sync(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                replacement = self.root / "replacement"
                replacement.write_bytes(b"other writer")
                os.replace(replacement, self.output)
                raise OSError("controlled directory sync failure")
            return actual(descriptor)
        with patch("xti.adapters.html_report_writer.os.fsync", side_effect=sync), self.assertRaises(OrganizationExportPublicationError):
            self.writer.write_new(str(self.output), ("complete",), max_bytes=1000)
        self.assertEqual(self.output.read_bytes(), b"other writer")
        self.assert_no_temporary()

    def test_cleanup_failure_preserves_specific_publication_error(self):
        with patch("xti.adapters.html_report_writer.os.unlink", side_effect=OSError("cleanup denied")), \
             self.assertRaises(OrganizationExportPublicationError) as raised:
            self.writer.write_new(str(self.output), ("complete",), max_bytes=1000)
        self.assertIn("Dosya mevcut olabilir", str(raised.exception))
        self.assertEqual(self.output.read_text(), "complete")


class OrganizationExportTests(unittest.TestCase):
    invoke = fixtures.OrganizationReportTests.invoke
    result = fixtures.OrganizationReportTests.result
    files = fixtures.OrganizationReportTests.files
    link = fixtures.OrganizationReportTests.link
    collect = fixtures.OrganizationReportTests.collect
    add_social = fixtures.OrganizationReportTests.add_social
    add_tc = fixtures.OrganizationReportTests.add_tc
    add_rl = fixtures.OrganizationReportTests.add_rl
    case_evidence_fixture = fixtures.OrganizationReportTests.case_evidence_fixture

    def setUp(self):
        fixtures.OrganizationReportTests.setUp(self)
        self.output = self.data.parent.resolve() / "kuruluş raporu.html"
        self.repository = SQLiteOrganizationReportRepository(self.database)
        self.renderer = HtmlOrganizationReportRenderer()
        self.exporter = OrganizationExportService(self.repository, self.renderer, AtomicHtmlReportWriter())

    def snapshot(self):
        return self.repository.read_complete(self.organization["id"],
            observed_at=datetime.now(timezone.utc).isoformat(), stale_after_hours=24)

    def test_all_records_beyond_default_page_export_without_network_lock_or_database_writes(self):
        self.link()
        asset, _ = SQLiteAssetRepository(self.database).add("example.com")
        domains = tuple(f"example-support-{index:03}.net" for index in range(63))
        SQLiteFindingRepository(self.database).save_import(
            ImportDocument("fixture:export", "export-all", tuple(DomainInput(value, value, index, None)
                for index, value in enumerate(domains, 1))),
            tuple(MatchCandidate(asset.id, asset.value, value, "rules-v1", ("Explicit test match",)) for value in domains),
        )
        before = self.files()
        with patch.object(LocalExecutionLock, "acquire", side_effect=AssertionError("No write lock")), \
             patch.object(SQLiteAssetRepository, "initialize", side_effect=AssertionError("No initialization")):
            result = self.exporter.export(self.organization["id"], destination=str(self.output))
        self.assertEqual(self.files(), before)
        parsed = ParsedHtml(self.output.read_text())
        text = " ".join(parsed.text)
        for domain in domains: self.assertIn(domain, text)
        self.assertIn("63 kayıt · tamamı", text)
        self.assertEqual(result.target_count, 1)
        self.assertGreaterEqual(result.record_count, 127)
        self.assertFalse(set(parsed.tags) & {"script", "img", "iframe", "object", "embed", "link", "form"})
        self.assertTrue(all(value.startswith(("#", "https://", "http://")) for value in parsed.hrefs))

    def test_html_escapes_untrusted_names_and_links_without_hidden_case_content(self):
        case, findings, evidence = self.case_evidence_fixture()
        self.result("organizations", "rename", self.organization["id"], '</h1><script>alert("x")</script>',
                    "--reason", "Unsafe-looking plain text fixture.")
        self.exporter.export(self.organization["id"], destination=str(self.output))
        html = self.output.read_text()
        parsed = ParsedHtml(html)
        self.assertNotIn("script", parsed.tags)
        self.assertIn('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;', html)
        self.assertNotIn("Private case title", html)
        self.assertNotIn("Private case content", html)
        self.assertIn(case["id"], html)
        self.assertIn(evidence["id"], html)
        self.assertIn("cases evidence-show", html)
        for value in ("javascript:alert(1)", "data:text/html,evil", "file:///private/file", "//evil.test", 
                      "https://user:secret@host.test/", "https://host.test\\@evil.test/", "https://host.test/\n"):
            self.assertIsNone(safe_external_url(value))
        self.assertEqual(safe_external_url("https://example.com/path?a=1&b=2"), "https://example.com/path?a=1&b=2")

    def test_public_watch_export_includes_full_before_after_history_and_exact_scope(self):
        self.link()
        self.result("notices", "watch", "enable", self.organization["id"])
        repository = SQLitePublicNoticeRepository(self.database)
        def apply(*records):
            now = datetime.now(timezone.utc).isoformat()
            return repository.apply(public_catalog(*records), started_at=now, finished_at=now, item_limit=20)
        apply(item())
        apply(item(PwnCount=23456), *(item(f"Event{index:02}") for index in range(24)), item("Other", "other.example"))
        self.result("organizations", "rename", self.organization["id"], "Current label", "--reason", "Preserve historical label.")
        before = self.files()
        result = self.exporter.export(self.organization["id"], destination=str(self.output))
        self.assertEqual(self.files(), before)
        html = self.output.read_text()
        for expected in ("12345", "23456", "Example group", "Current label", "Have I Been Pwned", "CC BY 4.0", "Event23"):
            self.assertIn(expected, html)
        self.assertNotIn("other.example", html)
        self.assertEqual(result.public_notice_watch_run_count, 2)
        self.assertIn("25 öğenin tamamı", html)

    def test_all_surface_evidence_and_selected_social_claims_remain_visible_with_source_gaps(self):
        social, tc, rl = self.add_social(), self.add_tc(), self.add_rl()
        for kind, value in (("domain", "example.com"), ("username-watch", social.id),
                            ("ransomware-watch", tc.id), ("ransomlook-watch", rl.id)):
            self.link(kind, value)
        self.maigret.responses.append({"GitHub": github()})
        self.collect("--username-watch", social.id, "--ransomware-watch", tc.id, "--ransomlook-watch", rl.id)
        self.maigret.responses.append(SourceError("Kaynağa geçici erişim hatası."))
        self.social.run(social.id)
        asset = SQLiteAssetRepository(self.database).list()[0]
        web = SQLiteSurfaceRepository(self.database)
        web.activate(asset.id, asset.value, "Stored authorized fixture only.", datetime.now(timezone.utc).isoformat())
        checks = [web.append_check(asset.id, replace(surface_result(), certificate=certificate()))]
        checks.append(SQLiteSurfaceMailRepository(self.database).append_check(asset.id, mail_result()))
        checks.append(SQLiteSurfaceServiceScanRepository(self.database).append_check(asset.id,
            "Explicit fixture IP authorization.", scan_result(opened=(443,))))
        cname = cname_result()
        checks.append(SQLiteSurfaceCnameRepository(self.database).append_check(asset.id,
            replace(cname, domain=asset.value, chain=(CnameHop(asset.value, cname.target),))))
        before = self.files()
        exported = self.exporter.export(self.organization["id"], destination=str(self.output))
        self.assertEqual(self.files(), before)
        html = self.output.read_text()
        self.assertEqual(exported.target_count, 4)
        for check in checks: self.assertIn(check.id, html)
        for value in ("Fixture CA", "01a2", "mail.example.com", "v=spf1 -all", "v=DMARC1; p=reject",
                      "443/tcp", "active.vendor.example", "GitHub", "Kaynak iddiaları",
                      "Kaynağa geçici erişim hatası.", "Son başarılı kayıt", "Stored authorized fixture only."):
            self.assertIn(value, html)
        self.assertIn(social.display_name, html)

    def test_service_rejects_partial_wrong_scope_or_incomplete_history_before_writer(self):
        self.link(); self.collect()
        snapshot = self.snapshot()
        target = snapshot.report.targets[0]
        section = target.sections[0]
        partial = replace(snapshot, report=replace(snapshot.report, targets=(
            replace(target, sections=(replace(section, total_count=section.total_count + 1), *target.sections[1:])),
        )))
        for invalid in (partial, replace(snapshot, report=replace(snapshot.report, has_more_targets=True))):
            repository = Mock(read_complete=Mock(return_value=invalid))
            writer = Mock()
            exporter = OrganizationExportService(repository, self.renderer, writer)
            with self.assertRaises(ValidationError):
                exporter.export(self.organization["id"], destination=str(self.output))
            writer.write_new.assert_not_called()
        with self.assertRaises(ValidationError):
            validate_complete_export(snapshot, "00000000-0000-0000-0000-000000000000")
        self.assertFalse(self.output.exists())

    def test_cli_exports_new_file_and_existing_file_error_preserves_database(self):
        self.link(); self.collect()
        before = self.files()
        exported = self.result("organizations", "export", self.organization["id"], "--output", str(self.output))
        self.assertEqual(exported["file"]["path"], str(self.output))
        self.assertEqual(self.files(), before)
        contents = self.output.read_bytes()
        code, _, _ = self.invoke("organizations", "export", self.organization["id"], "--output", str(self.output))
        self.assertEqual(code, 2)
        self.assertEqual(self.output.read_bytes(), contents)
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
