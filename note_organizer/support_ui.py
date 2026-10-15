"""Reviewable feedback drafts and manual release-check dialogs."""
from pathlib import Path
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from . import APP_NAME, __version__
from .icons import Button
from .support import (FEEDBACK_DESTINATION, UpdateResult, check_updates, environment_summary,
                      feedback_destination, feedback_handoff, feedback_report)
from .theme import BACKGROUND, text_options
from .widgets import (ReadOnlyText, ScrollFrame, Tooltip, WrapToolbar, annotate_buttons,
                      bind_dialog_close, fit_dialog)
from .workflow_ui import background


def documentation_path(kind, *, root=None):
    """Find the shipped PDF guide without depending on the launch directory."""
    root = Path(root) if root is not None else Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    filename = {"manual": "Notable-User-Manual.pdf", "readme": "Notable-README.pdf"}[kind]
    if kind == "readme" and not getattr(sys, "frozen", False) and (root / "README.md").is_file():
        return (root / "README.md").resolve()
    for candidate in (root / "output" / "pdf" / filename, root / "documentation" / filename):
        if candidate.is_file():
            return candidate.resolve()
    # Retain a Markdown fallback for bundles that include it instead of a PDF.
    if kind == "readme" and (root / "README.md").is_file():
        return (root / "README.md").resolve()
    return None


def open_documentation(app, kind):
    path = documentation_path(kind)
    label = "user manual" if kind == "manual" else "README"
    if path is None:
        messagebox.showinfo("Documentation unavailable", f"The {label} is not included in this copy of Notable.",
                            parent=getattr(app, "help_window", None) or app.root)
        return False
    try:
        if os.name == "nt":
            os.startfile(str(path))
        elif not webbrowser.open(path.as_uri()):
            raise OSError("No document application opened.")
    except (OSError, webbrowser.Error) as error:
        messagebox.showerror("Could not open documentation", f"Open this file with your preferred application:\n\n{path}\n\n{error}",
                             parent=getattr(app, "help_window", None) or app.root)
        return False
    return True


def add_documentation_buttons(app, actions):
    buttons = []
    for kind, label in (("manual", "Open manual"), ("readme", "Open README")):
        button = actions.add(Button(actions, text=label, command=lambda selected=kind: open_documentation(app, selected)))
        Tooltip(button, lambda selected=kind: (
            f"Open the {'step-by-step user manual' if selected == 'manual' else 'README'} in your computer's default document application.\n\n"
            + str(documentation_path(selected) or "This documentation file is not included in the current installation.")))
        buttons.append(button)
    return tuple(buttons)


class FeedbackWindow:
    def __init__(self, app, destination=FEEDBACK_DESTINATION):
        self.app, self.destination = app, destination
        self.environment = environment_summary()
        self.window = window = tk.Toplevel(app.root)
        window.title("Give feedback")
        window.configure(background=BACKGROUND)
        window.transient(app.root)
        bind_dialog_close(window, window.destroy)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        footer = WrapToolbar(frame)
        footer.pack(side="bottom", fill="x", pady=(12, 0))
        form = ScrollFrame(frame, width=660, height=470, padding=(0, 0, 14, 0))
        form.pack(fill="both", expand=True)
        content = form.content
        self.target = feedback_destination(destination)
        address = self.target[1] if self.target else "No feedback destination is configured."
        ttk.Label(content, text="Give feedback", style="Section.TLabel").pack(anchor="w")
        destination_label = ttk.Label(content, text=address, wraplength=630)
        destination_label.pack(anchor="w", pady=(6, 8))
        destination_label.bind("<Configure>", lambda event: destination_label.configure(wraplength=max(100, event.width)))
        explanation = ttk.Label(content, text="Review your draft, then open the feedback email or form, or copy the report. "
            "You send it yourself. Attach screenshots in your email or feedback form if useful.",
            style="Muted.TLabel", wraplength=630)
        explanation.pack(fill="x", pady=(0, 12))
        explanation.bind("<Configure>", lambda event: explanation.configure(wraplength=max(100, event.width)))
        row = ttk.Frame(content)
        row.pack(fill="x", pady=(0, 10))
        ttk.Label(row, text="Feedback type").pack(side="left", padx=(0, 12))
        self.kind = tk.StringVar(value="Bug report")
        kind_picker = ttk.Combobox(row, textvariable=self.kind, state="readonly", values=("Bug report", "Suggestion"), width=18)
        kind_picker.pack(side="left")
        Tooltip(kind_picker, "Choose Bug report for a problem or Suggestion for an improvement.")
        ttk.Label(content, text="Summary").pack(anchor="w")
        self.title = tk.StringVar()
        self.title_entry = ttk.Entry(content, textvariable=self.title)
        self.title_entry.pack(fill="x", pady=(4, 10))
        Tooltip(self.title_entry, "Briefly describe the problem or improvement in your own words.")
        ttk.Label(content, text="Description, steps, and expected behavior").pack(anchor="w")
        editor = ttk.Frame(content)
        editor.pack(fill="both", expand=True, pady=(4, 10))
        self.description = tk.Text(editor, width=1, height=10, wrap="word", undo=True, **text_options())
        scroll = ttk.Scrollbar(editor, orient="vertical", command=self.description.yview)
        scroll.pack(side="right", fill="y")
        self.description.pack(fill="both", expand=True)
        self.description.configure(yscrollcommand=scroll.set)
        self.description.bind("<Control-a>", self.select_all)
        ttk.Label(content, text="Included app details", style="Muted.TLabel").pack(anchor="w")
        details = "\n".join(f"{name}: {value}" for name, value in self.environment.items())
        self.details = ReadOnlyText(content, details, height=3)
        self.details.pack(fill="x", pady=(4, 6))
        privacy = ttk.Label(content, text="Only the app version, operating system, and source/packaged status are added. "
            "Library paths, logs, PDFs, and note contents are not attached. Review anything you type before sending.",
            style="Muted.TLabel", wraplength=630)
        privacy.pack(fill="x", pady=(0, 8))
        privacy.bind("<Configure>", lambda event: privacy.configure(wraplength=max(100, event.width)))
        self.status = tk.StringVar(value="" if self.target else "Copy report is available while the feedback destination is being configured.")
        status_label = ttk.Label(content, textvariable=self.status, wraplength=630)
        status_label.pack(fill="x", pady=(4, 0))
        status_label.bind("<Configure>", lambda event: status_label.configure(wraplength=max(100, event.width)))
        self.copy_button = footer.add(Button(footer, text="Copy report", command=self.copy_report))
        Tooltip(self.copy_button, "Copy your complete draft and the app details shown above. Nothing is sent.")
        route_label = "Open feedback email…" if self.target and self.target[0] == "email" else "Open feedback form…"
        self.open_button = footer.add(Button(footer, text=route_label, command=self.open_destination,
                                            state="normal" if self.target else "disabled", style="Primary.TButton"))
        Tooltip(self.open_button, lambda: "Add a summary and description, then copy the report and open " +
            (f"an email draft addressed to {self.target[1]}. You review and send it yourself; paste long reports from the clipboard."
             if self.target and self.target[0] == "email" else
             "the configured feedback form. Paste the report into the form, then review and submit it yourself."
             if self.target else "a feedback destination after one is configured. Copy report remains available."))
        footer.add(Button(footer, text="Close", command=window.destroy))
        annotate_buttons(window)
        form.bind_content()
        fit_dialog(window, app.root)
        # Keep the recipient and explanation visible when the form first opens.
        window.focus_set()

    def select_all(self, event=None):
        self.description.tag_add("sel", "1.0", "end-1c")
        return "break"

    def report(self):
        return feedback_report(self.kind.get(), self.title.get(), self.description.get("1.0", "end-1c"), self.environment)

    def copy_report(self):
        try:
            self.window.clipboard_clear()
            self.window.clipboard_append(self.report())
        except tk.TclError:
            self.status.set("The clipboard is unavailable. Select and copy the description manually.")
            return False
        self.status.set("Report copied. Paste it into your email or feedback form and review before sending.")
        return True

    def open_destination(self):
        if not self.target:
            return
        if not self.title.get().strip() or not self.description.get("1.0", "end-1c").strip():
            self.status.set("Add a summary and description before opening your feedback draft.")
            self.title_entry.focus_set()
            return
        if not self.copy_report():
            return
        url = feedback_handoff(self.destination, f"{APP_NAME} {self.kind.get()}: {self.title.get()}", self.report())
        try:
            opened = webbrowser.open(url)
        except (OSError, webbrowser.Error):
            opened = False
        if opened:
            self.status.set("Report copied and the feedback destination opened. Review the draft, paste if needed, and send it yourself.")
        else:
            self.status.set(f"No email/browser app opened. The report is copied; send it to {self.target[1]} using your preferred app.")


class UpdatesWindow:
    def __init__(self, app):
        self.app, self.busy = app, False
        self.result = None
        self.window = window = tk.Toplevel(app.root)
        window.title("Check for updates")
        window.configure(background=BACKGROUND)
        window.transient(app.root)
        bind_dialog_close(window, window.destroy)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"{APP_NAME} {__version__}", style="Section.TLabel").pack(anchor="w")
        self.status = tk.StringVar(value="Checking GitHub for the latest published stable release…")
        status_label = ttk.Label(frame, textvariable=self.status, wraplength=660)
        status_label.pack(fill="x", pady=(10, 12))
        status_label.bind("<Configure>", lambda event: status_label.configure(wraplength=max(100, event.width)))
        self.notes = ReadOnlyText(frame, "", height=14, width=75)
        self.notes.pack(fill="both", expand=True)
        ttk.Label(frame, text="Checks run only when requested and contact GitHub for public release information. "
            "Download opens your browser. Installation and replacement of source files remain manual.",
            wraplength=660, style="Muted.TLabel").pack(fill="x", pady=(12, 0))
        controls = WrapToolbar(frame)
        controls.pack(fill="x", pady=(12, 0))
        self.check_button = controls.add(Button(controls, text="Check again", command=self.check))
        Tooltip(self.check_button, lambda: "Checking GitHub's latest stable release metadata…" if self.busy else
                "Read GitHub's latest stable release metadata. This does not send library content or download application files.")
        self.release_button = controls.add(Button(controls, text="Open release…", command=self.open_release, state="disabled"))
        Tooltip(self.release_button, lambda: "Wait for the update check to finish, then open the official GitHub release page."
                if self.busy else "Open the official GitHub release page in your browser.")
        self.download_button = controls.add(Button(controls, text="Download source…", command=self.download,
                                                   state="disabled", style="Primary.TButton"), visible=False)
        Tooltip(self.download_button, lambda: "Wait for the update check to find an available download." if self.busy or
            not self.result or not self.result.download_url else
            "Open the offered release download in your browser. Review the release instructions before installing. "
            "The app does not install it or replace your current source files or local edits.")
        controls.add(Button(controls, text="Close", command=window.destroy))
        self.controls = controls
        annotate_buttons(window)
        fit_dialog(window, app.root)
        self.check()

    def alive(self):
        return not getattr(self.app, "closing", False) and self.window.winfo_exists()

    def check(self):
        if self.busy or not self.alive():
            return
        self.busy = True
        self.result = None
        self.status.set("Checking GitHub for the latest published stable release…")
        self.check_button.configure(state="disabled")
        self.release_button.configure(state="disabled")
        self.download_button.configure(state="disabled")
        self.notes.set("")
        background(self.app, check_updates, self.loaded, self.failed)

    def loaded(self, result):
        if not self.alive():
            return
        self.busy, self.result = False, result
        self.check_button.configure(state="normal")
        self.release_button.configure(state="normal")
        self.status.set(result.message)
        self.notes.set((f"Release {result.latest_version}\n\n" if result.latest_version else "") + result.notes)
        if result.download_url:
            self.download_button.configure(text=result.download_label, state="normal")
            self.controls.set_visible(self.download_button, True)
        else:
            self.controls.set_visible(self.download_button, False)

    def failed(self, error):
        self.loaded(UpdateResult("error", __version__, "The update check could not finish. Try again later."))

    def open_url(self, url):
        if not url:
            return
        try:
            opened = webbrowser.open(url)
        except (OSError, webbrowser.Error):
            opened = False
        if not opened:
            self.status.set(f"Could not open your browser. Open this address manually: {url}")

    def open_release(self):
        if self.result:
            self.open_url(self.result.release_url)

    def download(self):
        if self.result:
            self.open_url(self.result.download_url)


def open_feedback(app, destination=FEEDBACK_DESTINATION):
    existing = getattr(app, "feedback_dialog", None)
    if existing and existing.window.winfo_exists():
        existing.window.lift()
        return existing
    app.feedback_dialog = FeedbackWindow(app, destination)
    return app.feedback_dialog


def open_updates(app):
    existing = getattr(app, "updates_dialog", None)
    if existing and existing.window.winfo_exists():
        existing.window.lift()
        return existing
    app.updates_dialog = UpdatesWindow(app)
    return app.updates_dialog
