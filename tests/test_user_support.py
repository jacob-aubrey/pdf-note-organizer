"""Synthetic private feedback and read-only release-check regressions."""
from io import BytesIO
import json
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from note_organizer import support


def release(tag="v2.6.0", **kwargs):
    return {"tag_name": tag, "draft": False, "prerelease": False, "body": "Changes\n\nReader improvements.",
            "html_url": f"{support.REPOSITORY_URL}/releases/tag/{tag}", "assets": [], **kwargs}


class UserSupportTests(unittest.TestCase):
    def test_environment_allowlist_excludes_paths_and_extra_diagnostic_fields(self):
        environment = support.environment_summary("2.5.0", frozen=False, system="Windows", release="11")
        self.assertEqual(environment, {"App version": "2.5.0", "Operating system": "Windows 11", "Install type": "Source code"})
        environment.update({"Library path": "C:/Users/Private/Library", "API key": "secret", "PDF": "private paper"})
        report = support.feedback_report("Suggestion", "Improve search", "Keep my own words.", environment)
        self.assertIn("Improve search", report)
        self.assertIn("Keep my own words.", report)
        self.assertIn("App version: 2.5.0", report)
        self.assertNotIn("Private", report)
        self.assertNotIn("secret", report)
        self.assertNotIn("private paper", report)

    def test_private_email_handoff_encodes_an_editable_draft_without_sending(self):
        report = support.feedback_report("Bug report", "Quotes & scrolling", "Steps:\n1. Search tantalum.\n2. Scroll.")
        url = support.feedback_handoff("help@example.org", "Notable feedback & question", report)
        parsed = urlsplit(url)
        self.assertEqual(parsed.scheme, "mailto")
        self.assertEqual(parsed.path, "help@example.org")
        query = parse_qs(parsed.query)
        self.assertEqual(query["body"], [report])
        self.assertEqual(query["subject"], ["Notable feedback & question"])

    def test_large_email_uses_full_copied_report_instead_of_truncating_it(self):
        url = support.feedback_handoff("help@example.org", "Long feedback", "Repeated details. " * 1000)
        self.assertLess(len(url), 1800)
        self.assertIn("clipboard", parse_qs(urlsplit(url).query)["body"][0])

    def test_destinations_reject_mail_header_injection_and_non_https_forms(self):
        for destination in (None, "", "help@example.org?bcc=other@example.org", "help@example.org\r\nBcc: other@example.org",
                            "http://example.org/form", "file:///private", "javascript:alert(1)", "https://user:secret@example.org"):
            with self.subTest(destination=destination):
                self.assertIsNone(support.feedback_destination(destination))
        self.assertEqual(support.feedback_destination("mailto:help@example.org"), ("email", "help@example.org"))
        self.assertEqual(support.feedback_handoff("https://example.org/private-form", "Hi", "report"), "https://example.org/private-form")

    def test_numeric_versions_and_prerelease_ordering(self):
        versions = ("v2.5.0-dev.2", "2.5a1", "2.5.0beta2", "2.5.0-rc.1", "2.5.0", "2.5.0.post1", "2.10.0")
        keys = [support.version_key(value) for value in versions]
        self.assertTrue(all(keys))
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(support.version_key("2.5"), support.version_key("v2.5.0+build.123"))
        self.assertIsNone(support.version_key("latest"))
        self.assertIsNone(support.version_key("version 2.5.0 surprise"))

    def test_release_comparison_covers_update_current_ahead_and_unknown(self):
        self.assertEqual(support.release_result(release(), "2.5.0").state, "update")
        self.assertEqual(support.release_result(release("v2.5.0"), "2.5").state, "current")
        self.assertEqual(support.release_result(release("v2.4.9"), "2.5.0").state, "ahead")
        self.assertEqual(support.release_result(release("latest"), "2.5.0").state, "unrecognized")
        self.assertEqual(support.release_result(release(), "development").state, "unrecognized")
        self.assertFalse(support.release_result(release(), "2.6.0").download_url)

    def test_source_download_uses_release_tag_and_never_source_checkout(self):
        result = support.release_result(release(), "2.5.0", frozen=False)
        self.assertEqual(result.download_label, "Download source…")
        self.assertEqual(result.download_url, support.REPOSITORY_URL + "/archive/refs/tags/v2.6.0.zip")
        self.assertIn("Reader improvements", result.notes)

    def test_draft_and_prereleases_are_not_offered(self):
        for data in (release(draft=True), release(prerelease=True), release("v2.6.0rc1")):
            with self.subTest(data=data):
                result = support.release_result(data, "2.5.0")
                self.assertEqual(result.state, "no_release")
                self.assertFalse(result.download_url)

    def test_packaged_asset_selection_respects_platform_and_architecture(self):
        assets = [{"name": name, "state": "uploaded", "browser_download_url": support.REPOSITORY_URL +
                   "/releases/download/v2.6.0/" + name} for name in
                  ("Notable-setup-arm64.exe", "Notable-setup-x64.exe", "Notable-win32.msi", "source.zip")]
        self.assertTrue(support.release_asset(assets, system="Windows", machine="AMD64").endswith("setup-x64.exe"))
        self.assertTrue(support.release_asset(assets, system="Windows", machine="ARM64").endswith("setup-arm64.exe"))
        self.assertTrue(support.release_asset(assets, system="Windows", machine="i386").endswith("win32.msi"))
        self.assertFalse(support.release_asset(assets, system="Linux", machine="x86_64"))
        result = support.release_result(release(assets=assets), "2.5.0", frozen=True, system="Windows", machine="AMD64")
        self.assertEqual(result.download_label, "Download update…")
        self.assertTrue(result.download_url.endswith("setup-x64.exe"))
        result = support.release_result(release(), "2.5.0", frozen=True)
        self.assertFalse(result.download_url)
        self.assertIn("No compatible", result.message)

    def test_official_release_and_asset_urls_are_validated(self):
        bad_urls = ("https://evil.example/update.exe", "http://github.com/" + support.REPOSITORY + "/releases/tag/v2.6.0",
                    "https://github.com/another/repo/releases/tag/v2.6.0", "javascript:alert(1)",
                    support.REPOSITORY_URL + "/releases/tag/../../../../../another/repo")
        for url in bad_urls:
            result = support.release_result(release(html_url=url), "2.5.0")
            self.assertEqual(result.release_url, support.RELEASES_URL)
            self.assertFalse(support.release_asset([{"name": "Notable.exe", "browser_download_url": url}], system="Windows", machine="AMD64"))

    def test_check_makes_one_bounded_public_metadata_request(self):
        opener = Mock(return_value=BytesIO(json.dumps(release()).encode("utf-8")))
        result = support.check_updates("2.5.0", opener=opener)
        self.assertEqual(result.state, "update")
        opener.assert_called_once()
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, support.RELEASE_API_URL)
        self.assertEqual(opener.call_args.kwargs["timeout"], 10)
        self.assertFalse(request.has_header("Authorization"))
        self.assertIsNone(request.data)

    def test_network_no_release_rate_limit_and_malformed_responses_are_readable(self):
        for error, state in ((HTTPError(support.RELEASE_API_URL, 404, "Missing", {}, None), "no_release"),
                             (HTTPError(support.RELEASE_API_URL, 403, "Limited", {}, None), "error"),
                             (HTTPError(support.RELEASE_API_URL, 500, "Error", {}, None), "error"),
                             (URLError("private proxy details"), "error"), (TimeoutError("host details"), "error")):
            with self.subTest(error=error):
                result = support.check_updates(opener=Mock(side_effect=error))
                self.assertEqual(result.state, state)
                self.assertNotIn("private proxy", result.message)
                self.assertFalse(result.download_url)
        for raw in (b"not JSON", b"[]", b"x" * (support.MAX_RESPONSE_BYTES + 1)):
            result = support.check_updates(opener=Mock(return_value=BytesIO(raw)))
            self.assertEqual(result.state, "error")


if __name__ == "__main__":
    unittest.main()
