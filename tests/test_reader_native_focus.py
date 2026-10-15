"""Deterministic contracts for the native reader's input handoff."""
from types import SimpleNamespace
import os
import threading
import unittest
from unittest.mock import Mock, patch

from note_organizer.reader_host import NativeChild, await_reader_ready


class ReaderStartupCancellationTests(unittest.TestCase):
    def test_close_cancels_initialization_before_browser_or_assets_are_ready(self):
        for shown in (False, True):
            with self.subTest(shown=shown):
                browser, assets, stopped = threading.Event(), threading.Event(), threading.Event()
                if shown:
                    browser.set()
                connection = Mock()
                connection.poll.return_value = True
                connection.recv.side_effect = [
                    {"command": "open", "payload": {"id": 1}},
                    {"command": "open", "payload": {"id": 2}},
                    {"command": "close"},
                ]
                self.assertIsNone(await_reader_ready(connection, browser, assets, stopped))
                self.assertEqual(connection.recv.call_count, 3)

    def test_pending_commands_preserve_order_when_assets_become_ready(self):
        shown, ready, stopped = threading.Event(), threading.Event(), threading.Event()
        shown.set()
        commands = [{"command": "open", "payload": {"id": 2}},
                    {"command": "match", "index": {"index": 3, "term": "tantalum"}}]
        connection = Mock()
        connection.poll.return_value = True
        def receive():
            command = commands.pop(0)
            if not commands:
                ready.set()
            return command
        connection.recv.side_effect = receive
        queued = await_reader_ready(connection, shown, ready, stopped)
        self.assertEqual([item["command"] for item in queued], ["open", "match"])
        self.assertEqual(queued[1]["index"]["term"], "tantalum")

    def test_broken_parent_connection_cannot_wait_for_asset_timeout(self):
        connection = Mock()
        connection.poll.return_value = True
        connection.recv.side_effect = EOFError
        with self.assertRaises(EOFError):
            await_reader_ready(connection, threading.Event(), threading.Event(), threading.Event())

    def test_stop_and_timeout_remain_distinct_outcomes(self):
        stopped = threading.Event()
        stopped.set()
        self.assertIsNone(await_reader_ready(Mock(), threading.Event(), threading.Event(), stopped))
        with self.assertRaisesRegex(RuntimeError, "could not initialize"):
            await_reader_ready(Mock(), threading.Event(), threading.Event(), threading.Event(), shown_timeout=0)


class NativeReaderFocusTests(unittest.TestCase):
    def setUp(self):
        self.native = NativeChild.__new__(NativeChild)
        self.native.hwnd = 20
        self.native.visible = True
        self.native.focus_binding = "reader-click"
        self.native.parent = Mock()
        self.native.parent.winfo_id.return_value = 11
        self.native.toplevel = Mock()
        self.native.user = Mock()
        self.native.user.IsWindow.return_value = True
        self.native.user.GetAncestor.return_value = 10
        self.native.user.GetForegroundWindow.return_value = 10
        self.native.user.GetFocus.return_value = 21
        self.native.user.IsChild.return_value = True
        self.target = Mock()
        self.target.winfo_id.return_value = 30
        self.target.winfo_toplevel.return_value = self.native.toplevel
        self.target.winfo_ismapped.return_value = True
        widget = Mock()
        widget.focus_get.return_value = self.target
        self.event = SimpleNamespace(widget=widget)

    def test_click_handoff_repairs_stale_tk_focus_left_in_reader(self):
        self.native.restore_tk_focus(self.event)
        self.native.user.SetFocus.assert_called_once_with(30)
        self.target.focus_force.assert_not_called()

    def test_background_app_is_never_activated(self):
        self.native.user.GetForegroundWindow.return_value = 999
        self.native.restore_tk_focus(self.event)
        self.native.user.GetFocus.assert_not_called()
        self.native.user.SetFocus.assert_not_called()

    def test_foreground_owner_for_hover_help_does_not_change_keyboard_focus(self):
        self.assertTrue(self.native.owner_is_foreground())
        self.native.user.GetForegroundWindow.return_value = 999
        self.assertFalse(self.native.owner_is_foreground())
        self.native.user.SetFocus.assert_not_called()

    def test_other_tk_widget_native_focus_is_preserved(self):
        self.native.user.IsChild.return_value = False
        self.native.restore_tk_focus(self.event)
        self.native.user.SetFocus.assert_not_called()

    def test_missing_focus_and_hidden_or_foreign_tk_targets_are_ignored(self):
        for change in ("missing-native", "non-input-click", "hidden", "foreign-root"):
            with self.subTest(change=change):
                self.setUp()
                if change == "missing-native":
                    self.native.user.GetFocus.return_value = None
                elif change == "non-input-click":
                    self.event.widget.focus_get.return_value = None
                    self.event.widget.winfo_class.return_value = "TButton"
                elif change == "hidden":
                    self.target.winfo_ismapped.return_value = False
                else:
                    self.target.winfo_toplevel.return_value = Mock()
                self.native.restore_tk_focus(self.event)
                self.native.user.SetFocus.assert_not_called()

    def test_clicking_entry_recovers_when_tk_reports_foreign_focus_as_none(self):
        self.event.widget = self.target
        self.target.focus_get.return_value = None
        self.target.winfo_class.return_value = "TEntry"
        self.native.restore_tk_focus(self.event)
        self.native.user.SetFocus.assert_called_once_with(30)

    def test_empty_input_hint_uses_its_entry_when_native_reader_has_focus(self):
        self.event.widget.focus_get.return_value = None
        self.event.widget.winfo_class.return_value = "Label"
        self.event.widget.master = self.target
        self.target.winfo_class.return_value = "TEntry"
        self.native.restore_tk_focus(self.event)
        self.native.user.SetFocus.assert_called_once_with(30)

    def test_reader_form_itself_can_relinquish_focus(self):
        self.native.user.GetFocus.return_value = 20
        self.native.restore_tk_focus(self.event)
        self.native.user.SetFocus.assert_called_once_with(30)

    def test_destroyed_widget_click_race_does_not_raise(self):
        import tkinter as tk
        self.event.widget.focus_get.side_effect = tk.TclError("widget destroyed")
        self.native.restore_tk_focus(self.event)
        self.native.user.SetFocus.assert_not_called()

    def test_detach_removes_only_its_own_binding_and_is_idempotent(self):
        self.native.user.GetWindowLongPtrW.return_value = 0x40000000
        self.native.detach()
        self.native.detach()
        self.native.toplevel.unbind.assert_called_once_with("<ButtonPress-1>", "reader-click")
        self.native.user.SetParent.assert_any_call(20, None)

    @unittest.skipUnless(os.name == "nt", "Win32 embedding contract")
    def test_embedding_removes_noactivate_and_appwindow_styles(self):
        user = Mock()
        user.GetWindowLongPtrW.side_effect = [0x80CC0000, 0x08040000]
        user.SetParent.return_value = 1
        parent = Mock()
        parent.winfo_id.return_value = 11
        parent.winfo_width.return_value = 800
        parent.winfo_height.return_value = 600
        with patch("ctypes.WinDLL", return_value=user):
            native = NativeChild(20, parent)
        extended = next(call.args[2] for call in user.SetWindowLongPtrW.call_args_list if call.args[1] == -20)
        self.assertFalse(extended & 0x08000000)
        self.assertFalse(extended & 0x00040000)
        self.assertTrue(extended & 0x00000080)
        parent.winfo_toplevel().bind.assert_called_once_with("<ButtonPress-1>", native.restore_tk_focus, add="+")


if __name__ == "__main__":
    unittest.main()
