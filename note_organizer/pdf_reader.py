"""A persistent PDF.js reader surface with cancellable source resolution."""
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlsplit
import webbrowser

from .icons import Button
from .reader_results import result_title
from .widgets import Tooltip


class PDFReader(ttk.Frame):
    def __init__(self, parent, resolver, external, expand):
        super().__init__(parent)
        self.resolver, self.external, self.expand = resolver, external, expand
        self.generation = 0
        self.identity = None
        self.entry = None
        self.title = ""
        self.terms = []
        self.cancelled = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PDF reader")
        self.results = queue.Queue()
        self.process = self.connection = self.native = None
        self.pending = None
        self.pending_match = None
        self.match_selection = None
        self.expanded = False
        self.awaiting_entry = False
        self.closed = False
        self.loaded = False
        self.state = {}
        self.last_warning = ""
        self.inspection = None
        self.poll_after = None
        self.reapers = []
        self.last_exitcode = None
        self.host = tk.Frame(self, background="#202224", width=1, height=1)
        self.host.pack(fill="both", expand=True)
        self.message = tk.StringVar(value="Select a paper or note to read its PDF.")
        self.placeholder = ttk.Frame(self.host, padding=20)
        self.placeholder.place(relx=.5, rely=.5, anchor="center", relwidth=.9)
        self.message_label = ttk.Label(self.placeholder, textvariable=self.message, anchor="center", justify="center", wraplength=350)
        self.message_label.pack(fill="x")
        self.retry = Button(self.placeholder, text="Retry reader", command=self.reload)
        Tooltip(self.retry, "Try loading this PDF again. Open externally remains available if the embedded reader cannot start.")
        self.host.bind("<Configure>", self.resize)
        self.host.bind("<Map>", self.mapped)
        self.host.bind("<Unmap>", lambda _: self.native.show(False) if self.native else None)
        self.bind("<Destroy>", self.destroyed, add="+")
        self.poll_after = self._root().after(40, self.poll)

    def set_entry(self, entry, terms=()):
        identity = (entry.get("document_id"), entry.get("key"), entry.get("path"), entry.get("page"),
                    entry.get("combined_view_page"), tuple(entry.get("rect") or ()), tuple(terms),
                    entry.get("missing"), entry.get("combined_view_unavailable"), entry.get("source_digest"),
                    entry.get("source_note_revision"), entry.get("logical_paper_id")) if entry else None
        title = result_title(entry) if entry else ""
        if identity == self.identity:
            # Citation edits may rename the current paper without changing its
            # PDF or selected note. Refresh the heading independently so the
            # reader keeps its zoom, position and active search.
            self.entry = dict(entry) if entry else None
            if self.pending is not None:
                self.pending["mainHits"] = entry.get("search_hits", []) if entry else []
            if title != self.title:
                self.title = title
                if self.pending is not None:
                    self.pending["title"] = title
                self.send({"command": "title", "title": title, "id": self.generation})
            return
        self.identity = identity
        self.entry = dict(entry) if entry else None
        self.title = title
        self.terms = list(terms)
        self.generation += 1
        generation = self.generation
        self.cancelled.set()
        self.cancelled = cancelled = threading.Event()
        self.loaded = False
        self.pending = None
        self.pending_match = None
        self.match_selection = None
        self.awaiting_entry = bool(entry)
        self.show_message("Loading PDF…" if entry else "Select a paper or note to read its PDF.")
        if not entry:
            self.send({"command": "clear", "id": generation, "message": self.message.get()})
            return
        if self.host.winfo_ismapped():
            self.load_entry()

    def load_entry(self):
        if not self.awaiting_entry or not self.entry:
            return
        self.awaiting_entry = False
        entry, cancelled, generation = dict(self.entry), self.cancelled, self.generation
        def resolve():
            return self.resolver(dict(entry), cancelled.is_set)
        future = self.executor.submit(resolve)
        future.add_done_callback(lambda result: self.results.put((generation, result)))

    def reload(self):
        selected_match = self.match_selection
        self.stop_host()
        self.identity = None
        self.set_entry(self.entry, self.terms)
        if selected_match is not None:
            self.select_match(selected_match)

    def mapped(self, event=None):
        self.load_entry()
        if self.pending and not self.process:
            self.start_host()
        if self.native:
            self.resize()
            self.native.show(self.loaded)

    def start_host(self):
        if self.closed or self.process or not self.pending:
            return
        if os.name != "nt":
            self.show_message("The embedded PDF reader currently requires Windows. Use Open externally to read this PDF.")
            return
        from .reader_host import run_reader_host, parent_dpi_awareness
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        self.connection = parent
        self.process = context.Process(target=run_reader_host, args=(child, parent_dpi_awareness(self.host)), name="Notable PDF reader", daemon=True)
        try:
            self.process.start()
            child.close()
            self.send({"command": "open", "payload": self.pending})
        except Exception as exc:
            child.close()
            self.stop_host()
            self.show_message(f"Could not start the PDF reader: {exc}", retry=True)

    def send(self, payload):
        if not self.connection:
            return
        try:
            self.connection.send(payload)
        except (OSError, EOFError):
            self.stop_host()
            self.show_message("The PDF reader stopped. Retry or open the PDF externally.", retry=True)

    def show_message(self, text, retry=False):
        self.message.set(text)
        if self.native:
            self.native.show(False)
        self.placeholder.place(relx=.5, rely=.5, anchor="center", relwidth=.9)
        if retry:
            self.retry.pack(pady=(12, 0))
        else:
            self.retry.pack_forget()

    def resize(self, event=None):
        self.message_label.configure(wraplength=max(120, self.host.winfo_width() - 60))
        if self.native:
            self.native.resize()

    def poll(self):
        self.poll_after = None
        if self.closed:
            return
        for _ in range(10):
            try:
                generation, future = self.results.get_nowait()
            except queue.Empty:
                break
            if generation != self.generation:
                continue
            try:
                payload = future.result()
                # A metadata edit can arrive while source resolution is still
                # running. Its latest title wins over the captured old entry.
                self.pending = {**payload, "title": self.title,
                                "mainHits": self.entry.get("search_hits", []) if self.entry else [], "id": generation,
                                "terms": self.terms, "expanded": self.expanded}
                if self.process:
                    self.send({"command": "open", "payload": self.pending})
                elif self.host.winfo_ismapped():
                    self.start_host()
            except InterruptedError:
                pass
            except Exception as exc:
                self.send({"command": "clear", "id": generation, "message": str(exc)})
                self.show_message(str(exc), retry=True)
        try:
            for _ in range(30):
                if not self.connection or not self.connection.poll():
                    break
                self.handle_event(self.connection.recv())
        except (OSError, EOFError):
            self.stop_host()
            self.show_message("The PDF reader stopped. Retry or open the PDF externally.", retry=True)
        self.poll_after = self._root().after(40, self.poll)

    def handle_event(self, event):
        kind = event.get("kind")
        if kind == "native":
            if event.get("hwnd") and os.name == "nt":
                from .reader_host import NativeChild
                try:
                    self.native = NativeChild(event["hwnd"], self.host)
                    self.native.show(self.loaded and bool(self.host.winfo_ismapped()))
                except OSError as exc:
                    self.stop_host()
                    self.show_message(f"Could not embed the PDF reader: {exc}", retry=True)
            return
        if kind == "inspection":
            self.inspection = event.get("state")
            return
        if event.get("id") not in (None, self.generation):
            return
        if kind == "state":
            self.state = event
            if event.get("loaded"):
                was_loaded = self.loaded
                self.loaded = True
                self.placeholder.place_forget()
                if self.native:
                    self.native.show(bool(self.host.winfo_ismapped()))
                if self.pending_match is not None:
                    match = self.pending_match
                    self.pending_match = None
                    self.send({"command": "match", "index": match})
                if not was_loaded and self.expanded:
                    self.send({"command": "expanded", "value": True})
        elif kind == "error":
            self.loaded = False
            if self.native is None:
                self.stop_host()
            self.show_message(event.get("message", "Unable to read this PDF."), retry=True)
        elif kind == "warning":
            # Browser layout notices and isolated control errors do not mean
            # the loaded PDF is unavailable. Keep the surface visible.
            self.last_warning = event.get("message", "PDF reader control issue")
            logging.warning("PDF reader: %s", self.last_warning)
        elif kind == "external":
            self.external()
        elif kind == "expand":
            self.expand()
        elif kind == "link":
            url = event.get("url", "")
            parsed = urlsplit(url)
            if parsed.scheme in {"https", "http"} and parsed.hostname:
                webbrowser.open(url)

    def select_match(self, index):
        self.match_selection = index
        if self.loaded:
            self.send({"command": "match", "index": index})
        elif self.entry:
            self.pending_match = index

    def set_expanded(self, value):
        value = bool(value)
        if value == self.expanded:
            return
        self.expanded = value
        if self.pending is not None:
            self.pending["expanded"] = value
        if self.loaded:
            self.send({"command": "expanded", "value": value})

    def stop_host(self):
        process, connection, native = self.process, self.connection, self.native
        self.process = self.connection = self.native = None
        if native:
            native.detach()
        if connection:
            try:
                connection.send({"command": "close"})
                connection.close()
            except OSError:
                pass
        if process:
            def reap():
                process.join(6)
                if process.is_alive():
                    process.terminate()
                    process.join(3)
                self.last_exitcode = process.exitcode
                process.close()
            reaper = threading.Thread(target=reap, name="PDF reader shutdown", daemon=True)
            self.reapers.append(reaper)
            reaper.start()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancelled.set()
        if self.poll_after:
            self._root().after_cancel(self.poll_after)
            self.poll_after = None
        self.stop_host()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def destroyed(self, event):
        if event.widget is self:
            self.close()

    def wait_closed(self):
        self.close()
        self.executor.shutdown(wait=True, cancel_futures=True)
        for reaper in self.reapers:
            reaper.join(10)
