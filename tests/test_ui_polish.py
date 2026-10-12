"""User-facing regressions for clipped cells, icons and contextual actions."""
from types import SimpleNamespace
from concurrent.futures import Future
from tkinter import ttk
import unittest
from unittest.mock import patch
from PIL import Image

from note_organizer.icons import Button, ASSETS
from note_organizer.widgets import CellTooltip
from tests import test_ui_audit
from tests.test_preferences_ui import descendants
from tests.ui_helpers import settle_library


class UIPolishTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    tearDown = test_ui_audit.UIAuditTests.tearDown

    def show(self, tab=None, width=940, height=620):
        self.root.attributes("-alpha", 0)
        self.root.geometry(f"{width}x{height}+0+0")
        self.app.tabs.select(tab or self.app.remarkable_tab)
        self.root.deiconify()
        self.root.update()

    def add_paper(self):
        path = self.pc / "An unusually long scientific paper title with supplemental material.pdf"
        path.touch()
        project = self.store.add_project(self.pc)
        self.store.save_scan(project, path, "digest", "signature", "settings", {}, [])
        self.app.refresh()
        settle_library(self.app, self.root)
        return path

    def test_scrollbar_pans_long_paths_and_disappears_when_columns_fit(self):
        self.show()
        tree = self.app.cloud_folders
        self.assertTrue(tree.horizontal_scrollbar.winfo_ismapped())
        self.root.tk.call(tree.horizontal_scrollbar.cget("command"), "moveto", 1)
        self.root.update()
        self.assertGreater(tree.xview()[0], 0)
        self.assertAlmostEqual(tree.xview()[1], 1)
        for column in tree.cget("columns"):
            tree.column(column, width=60, minwidth=60, stretch=True)
        tree.xview_moveto(0)
        self.root.update()
        self.assertFalse(tree.horizontal_scrollbar.winfo_ismapped())
        self.assertFalse(self.errors)

    def test_hover_reveals_the_pointed_cell_and_resets_between_cells(self):
        self.show()
        tree = self.app.cloud_review
        text = "A long location that cannot fit in this deliberately narrow cell " * 4
        tree.insert("", "end", iid="hover", values=("Short", text, "Ready"))
        tree.column("name", width=65, minwidth=65, stretch=False)
        tree.column("folder", width=110, minwidth=110)
        tree.column("reason", width=90, minwidth=90)
        self.root.update()
        tip = tree.tooltip
        self.assertIsInstance(tip, CellTooltip)
        tip.value = None
        # This case exercises the generic clipped-cell behavior. Path-specific
        # hover help is checked separately in the path consistency tests.
        tip.extra = None
        def at(column):
            x, y, width, height = tree.bbox("hover", column)
            return x + 12, y + height // 2
        x, y = at("#2")
        tip.motion(SimpleNamespace(x=x, y=y))
        with patch.object(tree, "winfo_pointerxy", return_value=(tree.winfo_rootx() + x, tree.winfo_rooty() + y)):
            self.assertEqual(tip.cell_text(), text)
        first_pending = tip.pending
        x, y = at("#1")
        tip.motion(SimpleNamespace(x=x, y=y))
        self.assertNotEqual(tip.pending, first_pending)
        with patch.object(tree, "winfo_pointerxy", return_value=(tree.winfo_rootx() + x, tree.winfo_rooty() + y)):
            self.assertEqual(tip.cell_text(), "")
        tip.motion(SimpleNamespace(x=x, y=2))
        self.assertIsNone(tip.pending)
        self.assertIsNone(tip.cell)

    def test_hover_uses_displayed_column_order(self):
        self.show()
        tree = self.app.cloud_review
        tree.configure(displaycolumns=("reason", "name"))
        tree.insert("", "end", iid="reordered", values=("Paper", "Location", "Explanation"))
        self.root.update()
        x, y, _, height = tree.bbox("reordered", "#1")
        self.assertEqual(tree.tooltip.identify(x + 5, y + height // 2)[1], "reason")

    def test_note_cell_and_hover_preserve_the_complete_annotation(self):
        app = self.app
        app.query_cancel.set()
        app.query_generation += 1
        quote = "A complete annotation that is longer than the table excerpt. " * 12
        future = Future()
        future.set_result([{"document_id": "doc", "key": "mark", "path": str(self.pc / "paper.pdf"),
                            "kind": "highlight", "quote": quote, "page": 1}])
        app.finish_query(app.query_generation, None, future)
        self.assertEqual(app.notes.set("0", "text"), quote)
        self.assertEqual(app.note_cell_value("0", "text"), quote)

    def test_dragged_column_width_survives_background_refresh(self):
        self.show()
        tree = self.app.cloud_review
        tree.xview_moveto(0)
        self.root.update()
        x = tree.column("name", "width")
        tree.event_generate("<ButtonPress-1>", x=x, y=10)
        tree.event_generate("<ButtonRelease-1>", x=x, y=10)
        self.assertIn("name", tree.user_columns)
        self.assertEqual(tree.user_columns, {"name"})
        tree.column("name", width=210)
        self.app.update_rows(tree, [("new", ("Much longer paper title " * 12, "Cloud location", "Reason"))])
        self.assertEqual(tree.column("name", "width"), 210)

    def drag_divider(self, tree, display_column, delta):
        # Exercise the native press/motion/release sequence, including drop's
        # layout pass that used to undo the user's width or pin it at minimum.
        self.root.update()
        x = next(x for x in range(tree.winfo_width())
                 if tree.identify_region(x, 10) == "separator" and tree.identify_column(x) == display_column)
        tree.event_generate("<ButtonPress-1>", x=x, y=10)
        tree.event_generate("<B1-Motion>", x=x + delta, y=10, state=256)
        self.root.update()
        moved = tuple(tree.column(key, "width") for key in tree.cget("columns"))
        tree.event_generate("<ButtonRelease-1>", x=x + delta, y=10)
        self.root.update()
        selected = tree.cget("columns")[int(display_column[1:]) - 1]
        self.assertEqual(tree.column(selected, "width"), moved[int(display_column[1:]) - 1])
        return moved

    def test_review_dividers_move_both_directions_without_freezing_unselected_columns(self):
        self.show(width=1600, height=820)
        tree = self.app.cloud_review
        original = tuple(tree.column(key, "width") for key in tree.cget("columns"))
        left = self.drag_divider(tree, "#1", -100)
        self.assertLess(left[0], original[0] - 80)
        self.assertEqual(left[1], original[1])
        restored = self.drag_divider(tree, "#1", 100)
        self.assertGreater(restored[0], left[0] + 80)
        cloud_left = self.drag_divider(tree, "#2", -30)
        self.assertLess(cloud_left[1], restored[1] - 20)
        self.assertEqual(cloud_left[0], restored[0])
        cloud_right = self.drag_divider(tree, "#2", 80)
        self.assertGreater(cloud_right[1], cloud_left[1] + 60)
        self.assertEqual(cloud_right[0], restored[0])
        self.assertNotIn("reason", tree.user_columns)
        self.assertTrue(tree.column("reason", "stretch"))
        self.assertFalse(self.errors)

    def test_mapping_divider_recovers_from_minimum_and_scrolled_drag(self):
        self.show(width=1600, height=820)
        tree = self.app.cloud_folders
        minimum = tree.column("name", "minwidth")
        left = self.drag_divider(tree, "#1", -300)
        self.assertEqual(left[0], minimum)
        self.assertGreaterEqual(minimum, 90)
        right = self.drag_divider(tree, "#1", 140)
        self.assertGreater(right[0], left[0] + 120)
        self.assertNotIn("local", tree.user_columns)
        self.assertTrue(tree.column("local", "stretch"))
        # Responsive unselected columns can now fit the viewport. Create real
        # overflow before exercising a separator while horizontally scrolled.
        tree.column("local", minwidth=tree.winfo_width() + 200)
        self.root.update()
        tree.xview_scroll(4, "units")
        self.root.update()
        self.assertGreater(tree.xview()[0], 0)
        scrolled = self.drag_divider(tree, "#1", 50)
        self.assertGreater(scrolled[0], right[0] + 35)
        self.app.update_rows(tree, [("literature", ("A much longer source folder title " * 12, "Long PC path " * 20))])
        self.root.update()
        self.assertEqual(tree.column("name", "width"), scrolled[0])
        self.show(width=1250, height=780)
        self.assertEqual(tree.column("name", "width"), scrolled[0])
        self.assertFalse(self.errors)

    def test_selected_review_shows_full_reason_paths_and_copies_them(self):
        reason = "No matching PC folder. Map this cloud folder to a PC folder."
        path = str(self.pc / "review.pdf")
        self.store.save_remarkable_item("review", {"name": "Long paper", "state": "review", "parent": "missing",
                                        "cloud_path": "/Literature/Very long cloud folder path", "review_pdf": path,
                                        "target": str(self.pc / "Destination"), "reason": reason})
        self.app.refresh()
        settle_library(self.app, self.root)
        self.app.cloud_review.selection_set("review")
        self.app.cloud_review_selected()
        self.assertEqual(self.app.cloud_review.set("review", "reason"), "Needs mapping")
        details = self.app.review_details
        self.assertIn(reason, details.text.get("1.0", "end"))
        self.assertIn(path, details.value)
        self.assertIn("PC destination:", details.value)
        with patch.object(details, "clipboard_clear"), patch.object(details, "clipboard_append") as copy:
            details.copy_button.invoke()
        copy.assert_called_once_with(details.value)
        self.assertEqual(self.app.review_cell_value("review", "reason"), reason)
        self.assertEqual(self.app.review_heading.get(), "PDFs needing attention · 1")
        self.show(width=1250, height=780)
        box = self.app.cloud_review.bbox("review", "reason")
        self.assertTrue(box)
        self.assertLessEqual(box[0] + box[2], self.app.cloud_review.winfo_width())

    def test_library_source_action_works_for_a_selected_paper(self):
        path = self.add_paper()
        self.app.papers.selection_set(self.app.papers.get_children()[0])
        self.app.paper_selected()
        self.assertFalse(self.app.library_source_button.instate(["disabled"]))
        self.assertIn(str(path).lower(), self.app.paper_details.value.lower())
        self.assertIn(str(self.pc).lower(), self.app.folder_details.value.lower())
        with patch.object(self.app, "open_pdf") as open_pdf:
            self.app.library_source_button.invoke()
        self.assertEqual(open_pdf.call_args.args[0].lower(), str(path).lower())

    def test_source_route_can_be_unlinked_and_cancelling_changes_nothing(self):
        app = self.app
        app.cloud_folders.selection_set("literature")
        app.cloud_selection_changed()
        self.assertFalse(app.cloud_unmap_button.instate(["disabled"]))
        self.assertIn("automatic checks", app.cloud_unmap_help())
        original = app.cloud_pc_root.get()
        with patch("note_organizer.ui.messagebox.askyesno", return_value=False):
            app.cloud_unmap_button.invoke()
        self.assertEqual(app.cloud_pc_root.get(), original)
        self.assertTrue(app.service.commands.empty())
        with patch("note_organizer.ui.messagebox.askyesno", return_value=True) as confirm:
            app.cloud_unmap_button.invoke()
        self.assertIn("retained", confirm.call_args.args[1])
        self.assertEqual(app.service.commands.get_nowait(), ("remarkable_unlink", ("literature",)))
        self.assertEqual(app.cloud_pc_root.get(), "")
        self.assertFalse(app.cloud_enabled.get())
        self.assertTrue(app.cloud_setup_expanded)
        # The UI only queued the operation; the original library remains intact.
        self.assertTrue(self.pc.exists())
        self.assertEqual(self.store.preference("remarkable")["pc_root"], self.config["pc_root"])

    def test_folder_context_menu_targets_clicked_folder_and_requires_confirmation(self):
        app = self.app
        self.add_paper()
        first = app.selected_project()
        other_root = self.pc / "Another folder"
        other_root.mkdir()
        project_id = self.store.add_project(other_root)
        app.refresh()
        settle_library(app, self.root)
        self.show(app.library_tab)
        row = str(project_id)
        x, y, _, height = app.projects.bbox(row)
        with patch.object(app.folder_menu, "tk_popup") as popup:
            app.projects.event_generate("<Button-3>", x=x + 12, y=y + height // 2)
        self.assertEqual(popup.call_count, 1)
        self.assertEqual(app.projects.selection(), (row,))
        self.assertEqual(app.folder_menu.entrycget(0, "label"), "Rebuild notebook…")
        self.assertEqual(app.folder_menu.entrycget(1, "label"), "Remove folder…")
        project = app.selected_project()
        # A changed selection must not retarget the already-open menu.
        app.projects.selection_set(str(first["id"]))
        with patch("note_organizer.ui.messagebox.askyesno", return_value=False) as confirm:
            app.folder_menu.invoke(0)
        self.assertTrue(app.service.commands.empty())
        self.assertIn(project["output"], confirm.call_args.args[1])
        self.assertIn("Notebook backups", confirm.call_args.args[1])
        self.assertEqual(confirm.call_args.kwargs["default"], "no")
        with patch("note_organizer.ui.messagebox.askyesno", return_value=True):
            app.folder_menu.invoke(0)
        self.assertEqual(app.service.commands.get_nowait(), ("rebuild", (project_id,)))
        with patch("note_organizer.ui.messagebox.askyesno", return_value=False) as confirm:
            app.folder_menu.invoke(1)
        self.assertTrue(app.service.commands.empty())
        self.assertIn(str(other_root).casefold(), confirm.call_args.args[1].casefold())
        self.assertIn("remain on disk", confirm.call_args.args[1])
        with patch("note_organizer.ui.messagebox.askyesno", return_value=True):
            app.folder_menu.invoke(1)
        self.assertEqual(app.service.commands.get_nowait(), ("remove", (project_id,)))
        self.assertTrue(other_root.exists())
        self.assertFalse(self.errors)

    def test_folder_context_menu_ignores_blank_space_and_supports_keyboard(self):
        self.add_paper()
        self.show(self.app.library_tab)
        tree = self.app.projects
        with patch.object(self.app.folder_menu, "tk_popup") as popup:
            tree.event_generate("<Button-3>", x=15, y=tree.winfo_height()-10)
            self.assertEqual(popup.call_count, 0)
            self.app.show_folder_menu(SimpleNamespace(num=0))
            self.assertEqual(popup.call_count, 1)
        self.assertTrue(self.app.service.commands.empty())
        self.assertFalse(self.errors)

    def test_matched_descendant_without_override_explains_disabled_unlink(self):
        app = self.app
        app.cloud_folders.selection_set("matched")
        app.cloud_selection_changed()
        self.assertTrue(app.cloud_unmap_button.instate(["disabled"]))
        self.assertIn("no separate mapping", app.cloud_unmap_help())

    def test_cloud_controls_stay_together_in_a_wide_window(self):
        self.app.service.remarkable.vault.path.parent.mkdir(parents=True, exist_ok=True)
        self.app.service.remarkable.vault.path.touch()
        self.app.refresh()
        settle_library(self.app, self.root)
        self.show(width=1600, height=820)
        app = self.app
        for widget in (app.cloud_connection_button, app.cloud_setup_button, app.cloud_auto):
            self.assertTrue(widget.winfo_ismapped())
            self.assertLess(widget.winfo_rootx() - app.cloud_header.winfo_rootx(), 750)
            self.assertEqual(widget.master, app.cloud_browse_button.master)
        self.show(width=940, height=620)
        right_edge = app.cloud_header.winfo_rootx() + app.cloud_header.winfo_width()
        self.assertLessEqual(app.cloud_auto.winfo_rootx() + app.cloud_auto.winfo_width(), right_edge)
        alternate = self.folder / "Alternate"
        alternate.mkdir()
        app.cloud_pc_root.set(str(alternate))
        self.root.update()
        self.assertLessEqual(app.cloud_auto.winfo_rootx() + app.cloud_auto.winfo_width(), right_edge)
        # Labeled mapping actions remain reachable even in the narrow pane.
        unlink = app.cloud_unmap_button
        self.assertLessEqual(unlink.winfo_x() + unlink.winfo_width(), unlink.master.winfo_width())

    def test_help_icon_retains_its_question_mark_dot(self):
        with Image.open(ASSETS / "circle-help.png") as icon:
            self.assertTrue(icon.getchannel("A").crop((30, 46, 43, 57)).getbbox())
            small = icon.getchannel("A").resize((16, 16), Image.Resampling.LANCZOS)
            self.assertGreaterEqual(sum(pixel >= 180 for pixel in small.crop((7, 10, 9, 13)).getdata()), 2)

    def test_expand_and_navigation_actions_have_one_direction_indicator(self):
        app = self.app
        self.assertEqual(app.activity_toggle.cget("text"), "Show sync details")
        self.assertEqual(app.activity_toggle.icon_name, "chevron-down")
        app.activity_toggle.invoke()
        self.assertEqual(app.activity_toggle.cget("text"), "Hide sync details")
        self.assertEqual(app.activity_toggle.icon_name, "chevron-up")
        views = [w for w in descendants(self.root) if isinstance(w, Button) and w.cget("text") == "View notes"]
        self.assertEqual(len(views), 1)
        self.assertNotEqual(app.enlarge_button.icon_name, app.full_page_button.icon_name)

    def test_every_app_and_dialog_action_has_an_icon_and_keeps_its_label(self):
        self.add_paper()
        self.app.global_settings()
        self.app.settings()
        self.app.search_options()
        self.app.pair_remarkable()
        self.app.review_library()
        self.app.transfers()
        buttons = [w for w in descendants(self.root) if isinstance(w, ttk.Button)]
        self.assertGreater(len(buttons), 40)
        for button in buttons:
            with self.subTest(label=button.cget("text")):
                self.assertIsInstance(button, Button)
                self.assertTrue(button.cget("image"))
                self.assertTrue(button.cget("text"))
                self.assertTrue(hasattr(button, "tooltip"))
                if hasattr(button, "action_menu"):
                    menu = button.action_menu
                    for index in range(menu.index("end") + 1):
                        self.assertTrue(menu.entrycget(index, "image"))
        self.app.activity_toggle.configure(text="Hide sync details")
        self.assertEqual(self.app.activity_toggle.icon_name, "chevron-up")
        self.assertFalse(self.errors)

    def test_applying_and_resetting_search_filters_keeps_the_action_icon(self):
        self.app.search_options()
        match = next(w for w in descendants(self.root) if isinstance(w, ttk.Combobox)
                     and "Exact phrase" in w.cget("values"))
        window = match.winfo_toplevel()
        match.set("Exact phrase")
        apply = next(w for w in descendants(window) if isinstance(w, Button) and w.cget("text") == "Apply")
        apply.invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.app.search_mode, "Exact phrase")
        self.assertEqual(self.app.search_options_button.cget("text"), "Search in… •")
        self.assertEqual(self.app.search_options_button.icon_name, "list-filter")
        self.assertTrue(self.app.search_summary.get())
        self.app.search_options()
        reset = next(w for w in descendants(self.root) if isinstance(w, Button) and w.cget("text") == "Reset all")
        window = reset.winfo_toplevel()
        reset.invoke()
        apply = next(w for w in descendants(window) if isinstance(w, Button) and w.cget("text") == "Apply")
        apply.invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.app.search_options_button.cget("text"), "Search in…")
        self.assertEqual(self.app.search_options_button.icon_name, "list-filter")
        self.assertEqual(self.app.search_summary.get(), "")
        self.assertFalse(self.errors)

    def test_small_window_gives_review_priority_and_keeps_details_visible(self):
        self.show()
        app = self.app
        self.assertGreater(app.cloud_review.winfo_width(), app.cloud_folders.winfo_width() * 1.8)
        app.cloud_folders.selection_set("literature")
        app.cloud_selection_changed()
        self.root.update()
        self.assertTrue(app.mapping_details.winfo_ismapped())
        self.assertGreater(app.mapping_details.text.winfo_height(), 15)
        self.assertGreater(app.cloud_folders.winfo_height(), 40)
        self.show(app.library_tab)
        for button in app.library_actions:
            self.assertGreater(button.winfo_width(), 25)
        app.activity_toggle.invoke()
        self.root.update()
        self.assertTrue(app.activity_frame.winfo_ismapped())
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main()
