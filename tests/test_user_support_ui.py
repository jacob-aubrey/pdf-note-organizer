"""Tk checks for intentional feedback handoff and async manual update checks."""
from types import SimpleNamespace
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from note_organizer import support, support_ui
from note_organizer.theme import apply_theme
from tests.test_user_support import release


class UserSupportUITests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.attributes("-alpha", 0.0)
        apply_theme(self.root)
        self.app = SimpleNamespace(root=self.root, closing=False)
        self.callback_errors = []
        self.root.report_callback_exception = lambda *args: self.callback_errors.append(args)

    def tearDown(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()
        self.assertFalse(self.callback_errors)

    def fill_feedback(self, dialog):
        dialog.kind.set("Suggestion")
        dialog.title.set("Keep my report editable")
        dialog.description.insert("1.0", "My reviewed description.\nA second line.")

    def test_feedback_open_is_local_and_handoff_needs_an_explicit_click(self):
        with patch.object(support_ui.webbrowser, "open", return_value=True) as browser:
            dialog = support_ui.open_feedback(self.app, "help@example.org")
            self.root.update()
            browser.assert_not_called()
            self.fill_feedback(dialog)
            dialog.copy_button.invoke()
            browser.assert_not_called()
            copied = self.root.clipboard_get()
            self.assertIn("My reviewed description", copied)
            self.assertIn("Source code", copied)
            self.assertNotIn("Library path", copied)
            dialog.open_button.invoke()
            browser.assert_called_once()
            url = browser.call_args.args[0]
            self.assertEqual(urlsplit(url).path, "help@example.org")
            self.assertEqual(parse_qs(urlsplit(url).query)["body"], [copied])
            self.assertIn("send it yourself", dialog.status.get())
            self.assertIs(support_ui.open_feedback(self.app), dialog)

    def test_feedback_validates_empty_draft_and_keeps_copy_when_route_missing(self):
        with patch.object(support_ui.webbrowser, "open") as browser:
            dialog = support_ui.open_feedback(self.app, destination=None)
            self.assertTrue(dialog.open_button.instate(["disabled"]))
            self.fill_feedback(dialog)
            dialog.copy_button.invoke()
            self.assertIn("My reviewed description", self.root.clipboard_get())
            browser.assert_not_called()
            dialog.window.destroy()
            dialog = support_ui.open_feedback(self.app, "help@example.org")
            dialog.open_button.invoke()
            browser.assert_not_called()
            self.assertIn("Add a summary", dialog.status.get())

    def test_long_email_and_missing_email_client_retain_complete_report(self):
        with patch.object(support_ui.webbrowser, "open", return_value=False) as browser:
            dialog = support_ui.open_feedback(self.app, "help@example.org")
            dialog.title.set("Long report")
            description = "Feedback details. " * 1000
            dialog.description.insert("1.0", description)
            dialog.open_button.invoke()
            self.assertIn(description.strip(), self.root.clipboard_get())
            self.assertLess(len(browser.call_args.args[0]), 1800)
            self.assertIn("help@example.org", dialog.status.get())

    def test_private_form_opens_only_configured_route_with_report_on_clipboard(self):
        with patch.object(support_ui.webbrowser, "open", return_value=True) as browser:
            dialog = support_ui.open_feedback(self.app, "https://example.org/private-feedback")
            self.fill_feedback(dialog)
            self.assertEqual(dialog.open_button.cget("text"), "Open feedback form…")
            dialog.open_button.invoke()
            browser.assert_called_once_with("https://example.org/private-feedback")
            self.assertIn("My reviewed description", self.root.clipboard_get())

    def test_update_check_is_async_and_download_is_browser_handoff_only(self):
        with patch.object(support_ui, "background") as background, patch.object(support_ui.webbrowser, "open", return_value=True) as browser:
            dialog = support_ui.open_updates(self.app)
            self.root.update()
            background.assert_called_once()
            browser.assert_not_called()
            self.assertTrue(dialog.check_button.instate(["disabled"]))
            self.assertIs(background.call_args.args[1], support_ui.check_updates)
            result = support.release_result(release(), "2.5.0")
            background.call_args.args[2](result)
            self.root.update()
            self.assertFalse(dialog.check_button.instate(["disabled"]))
            self.assertEqual(dialog.download_button.cget("text"), "Download source…")
            self.assertNotIn(dialog.download_button, dialog.controls.hidden)
            self.assertIn("Reader improvements", dialog.notes.value)
            browser.assert_not_called()
            dialog.download_button.invoke()
            browser.assert_called_once_with(result.download_url)
            dialog.release_button.invoke()
            self.assertEqual(browser.call_count, 2)
            self.assertEqual(browser.call_args.args, (result.release_url,))
            self.assertIs(support_ui.open_updates(self.app), dialog)

    def test_update_errors_keep_retry_and_release_access_without_download(self):
        with patch.object(support_ui, "background") as background, patch.object(support_ui.webbrowser, "open") as browser:
            dialog = support_ui.open_updates(self.app)
            background.call_args.args[3](RuntimeError("private path must not be shown"))
            self.root.update()
            self.assertIn("could not finish", dialog.status.get())
            self.assertNotIn("private path", dialog.status.get())
            self.assertFalse(dialog.check_button.instate(["disabled"]))
            self.assertFalse(dialog.release_button.instate(["disabled"]))
            self.assertIn(dialog.download_button, dialog.controls.hidden)
            browser.assert_not_called()
            dialog.check_button.invoke()
            self.assertEqual(background.call_count, 2)
            self.assertTrue(dialog.busy)

    def test_closing_during_update_check_ignores_late_completion(self):
        with patch.object(support_ui, "background") as background:
            dialog = support_ui.open_updates(self.app)
            success, error = background.call_args.args[2:4]
            dialog.window.destroy()
            success(support.release_result(release(), "2.5.0"))
            error(RuntimeError("finished after close"))

    def test_documentation_buttons_open_default_app_only_after_click(self):
        from note_organizer.widgets import WrapToolbar
        actions = WrapToolbar(self.root)
        actions.pack()
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / "User manual.pdf"
            pdf.write_bytes(b"disposable guide placeholder")
            with patch.object(support_ui, "documentation_path", return_value=pdf), \
                    patch.object(support_ui.os, "startfile") as opened:
                buttons = support_ui.add_documentation_buttons(self.app, actions)
                opened.assert_not_called()
                self.assertEqual([button.cget("text") for button in buttons], ["Open manual", "Open README"])
                self.assertIn(str(pdf), buttons[0].tooltip.text())
                buttons[0].invoke()
                buttons[1].invoke()
            self.assertEqual(opened.call_count, 2)
            self.assertTrue(all(call.args == (str(pdf),) for call in opened.call_args_list))

    def test_documentation_paths_support_checkout_and_bundle_without_current_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "documentation").mkdir()
            manual = root / "documentation" / "Notable-User-Manual.pdf"
            manual.write_bytes(b"guide")
            self.assertEqual(support_ui.documentation_path("manual", root=root), manual)
            self.assertIsNone(support_ui.documentation_path("readme", root=root))
            (root / "README.md").write_text("Source README", encoding="utf-8")
            self.assertEqual(support_ui.documentation_path("readme", root=root), root / "README.md")
            (root / "output" / "pdf").mkdir(parents=True)
            readme = root / "output" / "pdf" / "Notable-README.pdf"
            readme.write_bytes(b"PDF README")
            self.assertEqual(support_ui.documentation_path("readme", root=root), root / "README.md")
            with patch.object(support_ui.sys, "frozen", True, create=True):
                self.assertEqual(support_ui.documentation_path("readme", root=root), readme)

    def test_missing_documentation_or_default_application_has_clear_error(self):
        with patch.object(support_ui, "documentation_path", return_value=None), \
                patch.object(support_ui.messagebox, "showinfo") as message, \
                patch.object(support_ui.os, "startfile") as opened:
            self.assertFalse(support_ui.open_documentation(self.app, "manual"))
            message.assert_called_once()
            opened.assert_not_called()
        with patch.object(support_ui, "documentation_path", return_value=Path("C:/guide.pdf")), \
                patch.object(support_ui.messagebox, "showerror") as message, \
                patch.object(support_ui.os, "startfile", side_effect=OSError("No association")):
            self.assertFalse(support_ui.open_documentation(self.app, "manual"))
            self.assertIn("guide.pdf", message.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
