"""Monitor geometry and DPI layouts use mocked bounds and disposable Tk apps."""
from pathlib import Path
import re
import tempfile
import time
import tkinter as tk
from tkinter import font, ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from note_organizer.screens import popup_position, work_area
from note_organizer.service import Service
from note_organizer.storage import Store
from note_organizer.ui import App
from note_organizer.widgets import CellTooltip, Tooltip, fit_dialog
from tests.test_preferences_ui import descendants
from tests.ui_helpers import settle_library


class ScreenGeometryTests(unittest.TestCase):
    def test_popup_uses_negative_monitor_coordinates_near_cursor(self):
        bounds = (-1920, -1080, 0, -40)
        self.assertEqual(popup_position((-1400, -800), (300, 180), bounds), (-1386, -780))
        self.assertEqual(popup_position((-20, -60), (350, 120), bounds), (-384, -200))

    def test_popup_flips_at_right_and_bottom_work_area_edges(self):
        bounds = (0, 0, 1920, 1040)
        self.assertEqual(popup_position((1900, 990), (300, 140), bounds), (1586, 830))
        self.assertEqual(popup_position((900, 500), (300, 140), bounds), (914, 520))

    def test_taskbar_is_excluded_and_offscreen_cursor_is_clamped(self):
        bounds = (0, 0, 1920, 1040)
        x, y = popup_position((400, 1030), (300, 180), bounds)
        self.assertLessEqual(y + 180, bounds[3] - 8)
        self.assertEqual(popup_position((-100, -50), (300, 180), bounds), (8, 8))
        self.assertGreaterEqual(x, 8)

    def test_popup_larger_than_monitor_anchors_inside_work_area(self):
        # A position helper cannot shrink content, but must avoid placing its
        # top-left corner outside a small monitor when complete fitting is impossible.
        self.assertEqual(popup_position((-400, -200), (2000, 1400), (-1280, -720, 0, 0)), (-1272, -712))

    def test_both_tooltip_types_choose_pointer_monitor_instead_of_cell_or_owner_origin(self):
        pointer = (-1400, -800)
        widget = SimpleNamespace(winfo_pointerxy=lambda: pointer)
        popup = SimpleNamespace(winfo_reqwidth=lambda: 300, winfo_reqheight=lambda: 180)
        for tooltip_type in (Tooltip, CellTooltip):
            with self.subTest(tooltip=tooltip_type.__name__):
                tooltip = tooltip_type.__new__(tooltip_type)
                tooltip.widget, tooltip.window = widget, popup
                with patch("note_organizer.widgets.work_area", return_value=(-1920, -1080, 0, -40)) as monitor:
                    self.assertEqual(tooltip.popup_position(), (-1386, -780))
                monitor.assert_called_once_with(widget, pointer)

    def test_windows_work_area_selects_parent_monitor_and_uses_taskbar_bounds(self):
        def information(handle, pointer):
            rect = pointer._obj.work
            rect.left, rect.top, rect.right, rect.bottom = -1920, -1080, 0, -40
            return 1
        api = SimpleNamespace(MonitorFromPoint=Mock(return_value=7), GetMonitorInfoW=Mock(side_effect=information))
        parent = SimpleNamespace(winfo_rootx=lambda: -1800, winfo_rooty=lambda: -1000,
                                 winfo_width=lambda: 1000, winfo_height=lambda: 700)
        with patch("note_organizer.screens.os.name", "nt"), \
                patch("note_organizer.screens.ctypes.windll", SimpleNamespace(user32=api), create=True):
            self.assertEqual(work_area(parent), (-1920, -1080, 0, -40))
        point, nearest = api.MonitorFromPoint.call_args.args
        self.assertEqual((point.x, point.y, nearest), (-1300, -650, 2))

    def test_work_area_falls_back_to_virtual_desktop_when_native_lookup_fails(self):
        api = SimpleNamespace(MonitorFromPoint=Mock(side_effect=OSError("Synthetic unavailable API")),
                              GetMonitorInfoW=Mock())
        widget = SimpleNamespace(winfo_vrootx=lambda: -1920, winfo_vrooty=lambda: -1080,
                                 winfo_vrootwidth=lambda: 3840, winfo_vrootheight=lambda: 2160)
        with patch("note_organizer.screens.os.name", "nt"), \
                patch("note_organizer.screens.ctypes.windll", SimpleNamespace(user32=api), create=True):
            self.assertEqual(work_area(widget, (-1500, -700)), (-1920, -1080, 1920, 1080))

    def dialog_geometry(self, requested, parent_rect, bounds):
        window = SimpleNamespace(update_idletasks=Mock(), winfo_reqwidth=lambda: requested[0],
                                 winfo_reqheight=lambda: requested[1], geometry=Mock())
        parent = SimpleNamespace(winfo_rootx=lambda: parent_rect[0], winfo_rooty=lambda: parent_rect[1],
                                 winfo_width=lambda: parent_rect[2], winfo_height=lambda: parent_rect[3])
        with patch("note_organizer.widgets.work_area", return_value=bounds) as monitor:
            fit_dialog(window, parent)
        monitor.assert_called_once_with(parent)
        window.update_idletasks.assert_called_once()
        geometry = window.geometry.call_args.args[0]
        match = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geometry)
        self.assertIsNotNone(match, geometry)
        return geometry, tuple(map(int, match.groups()))

    def test_fit_dialog_centers_on_negative_origin_parent_monitor(self):
        geometry, dimensions = self.dialog_geometry((700, 500), (-1800, -1000, 1000, 700), (-1920, -1080, 0, -40))
        self.assertEqual(dimensions, (700, 500, -1650, -900))
        # Tk accepts + followed by a negative absolute coordinate. A bare
        # -offset would instead position relative to the right/bottom edge.
        root = tk.Tk()
        root.withdraw()
        try:
            window = tk.Toplevel(root)
            window.withdraw()
            window.geometry(geometry)
            window.update_idletasks()
            self.assertEqual(window.wm_geometry(), geometry)
        finally:
            root.destroy()

    def test_fit_dialog_clamps_to_parent_monitor_right_bottom_edges(self):
        _, dimensions = self.dialog_geometry((700, 500), (-10, -50, 1000, 700), (-1920, -1080, 0, -40))
        self.assertEqual(dimensions, (700, 500, -708, -548))

    def test_fit_dialog_caps_oversized_request_with_work_area_margin(self):
        _, dimensions = self.dialog_geometry((1000, 800), (350, 200, 900, 700), (100, 50, 420, 250))
        self.assertEqual(dimensions, (304, 184, 108, 58))


class ScaledLayoutTests(unittest.TestCase):
    def test_review_tables_and_transfer_actions_fit_at_100_125_150_percent(self):
        for scale in (1, 1.25, 1.5):
            with self.subTest(scale=scale), tempfile.TemporaryDirectory() as folder:
                root = tk.Tk()
                original_scaling = root.tk.call("tk", "scaling")
                app = None
                try:
                    root.withdraw()
                    root.attributes("-alpha", 0)
                    root.tk.call("tk", "scaling", (96 / 72) * scale)
                    errors = []
                    root.report_callback_exception = lambda *args: errors.append(args)
                    store = Store(Path(folder) / "data" / "notes.sqlite3")
                    library = Path(folder) / "Sorted"
                    library.mkdir()
                    store.set_preference("remarkable", {"integration_enabled": True, "pc_root": str(library)})
                    with patch.object(Service, "start"):
                        app = App(root, store, store.path.parent)
                        settle_library(app, root)
                    root.geometry("1250x820+0+0")
                    root.deiconify()
                    review = app.review_library()
                    review.window.attributes("-alpha", 0)
                    review.window.geometry("1000x700+0+0")
                    review.rows = {"example": {"id": "example", "kind": "local_duplicate", "title": "Synthetic paper",
                        "reason": "Compare both copies before linking.", "sources": [], "actions": [], "local_paths": []}}
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline and not hasattr(review, "undo_operation"):
                        root.update()
                        app.poll()
                        time.sleep(.005)
                    review.render()
                    root.update()
                    row = review.tree.bbox("example")
                    self.assertTrue(row, f"Review row disappeared at {scale:.0%} scaling")
                    face = app.style.lookup("Treeview", "font")
                    self.assertGreaterEqual(row[3], font.Font(root=root, font=face).metrics("linespace") + 2)
                    for button in (review.link_button, review.keep_button, review.again_button, review.undo_button):
                        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                             review.window.winfo_rooty() + review.window.winfo_height() + 2)
                    before = set(root.winfo_children())
                    app.transfers()
                    transfer = next(window for window in root.winfo_children() if window not in before and isinstance(window, tk.Toplevel))
                    transfer.attributes("-alpha", 0)
                    root.update()
                    buttons = [widget for widget in descendants(transfer) if isinstance(widget, ttk.Button)]
                    self.assertTrue(buttons)
                    for button in buttons:
                        self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                             transfer.winfo_rootx() + transfer.winfo_width() + 2)
                        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                             transfer.winfo_rooty() + transfer.winfo_height() + 2)
                    self.assertFalse(errors)
                finally:
                    try:
                        if app is not None:
                            app.closing = True
                            app.inbox.stop()
                            app.service.stop()
                            app.pdf_worker.shutdown(wait=True)
                            app.query_cancel.set()
                            app.preview_cancel.set()
                            app.workflow_executor.shutdown(wait=True, cancel_futures=True)
                            app.query_executor.shutdown(wait=True, cancel_futures=True)
                            app.context_executor.shutdown(wait=True, cancel_futures=True)
                        for callback in root.tk.call("after", "info"):
                            root.after_cancel(callback)
                    finally:
                        # Tk scaling can survive into later interpreters on Windows.
                        # Restore it even if app setup, an assertion, or cleanup fails.
                        try:
                            root.tk.call("tk", "scaling", original_scaling)
                        finally:
                            root.destroy()


if __name__ == "__main__":
    unittest.main()
