"""One worker owns all extraction and export; Tk only receives messages."""
import json
import logging
import os
from pathlib import Path
import queue
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .extraction import extract, signature, scan_fingerprint
from .exporting import export_notebook
from .storage import canonical


class EventHandler(FileSystemEventHandler):
    def __init__(self, service):
        self.service = service

    def on_created(self, event):
        if event.is_directory:
            self.service.request_sync()
        else:
            self.service.enqueue(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.service.enqueue(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            self.service.request_sync()
        elif any(Path(p).suffix.lower() == ".pdf" for p in (event.src_path, event.dest_path)):
            self.service.enqueue(event.dest_path)
            self.service.request_sync()

    def on_deleted(self, event):
        if event.is_directory or Path(event.src_path).suffix.lower() == ".pdf":
            self.service.request_sync()


class Service:
    def __init__(self, store, debounce=2.0, interval=300):
        self.store = store
        self.debounce, self.interval = debounce, interval
        self.messages = queue.Queue()
        self.commands = queue.Queue()
        self.pending = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.observer = None
        self.thread = None
        self.status = {}
        self.sync_requested = False

    def post(self, text, refresh=False):
        self.messages.put((text, refresh))

    def start(self):
        self.thread = threading.Thread(target=self.run, name="PDF notebook worker", daemon=False)
        self.thread.start()
        self.command("watch")
        self.request_sync()

    def command(self, name, *args):
        self.commands.put((name, args))
        self.wake.set()

    def request_sync(self):
        with self.lock:
            self.sync_requested = True
        self.wake.set()

    def enqueue(self, path):
        if Path(path).suffix.lower() != ".pdf":
            return
        with self.lock:
            self.pending[canonical(path)] = (time.monotonic() + self.debounce, 0)
        self.wake.set()

    def due(self, now):
        with self.lock:
            ready = [(p, attempt) for p, (deadline, attempt) in self.pending.items() if deadline <= now]
            for p, _ in ready:
                del self.pending[p]
        return ready

    def watch(self):
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=3)
        self.observer = Observer()
        handler = EventHandler(self)
        for p in self.store.projects():
            if Path(p["root"]).is_dir():
                try:
                    self.observer.schedule(handler, p["root"], recursive=True)
                except OSError as exc:
                    self.post(f"Watching unavailable for {p['root']}: {exc}. Periodic scans remain active.")
        try:
            self.observer.start()
        except OSError as exc:
            self.post(f"Live watching failed: {exc}. Periodic scans remain active.")

    def projects_for(self, path):
        # A paper can belong to both a parent and child project, independently.
        return [p for p in self.store.projects() if Path(path).is_relative_to(Path(p["root"]))]

    def scan(self, project, path, force=False):
        settings = json.loads(project["settings"])
        fingerprint = scan_fingerprint(settings)
        old = self.store.document_at(project["id"], path)
        previous_error = any(r["path"] == canonical(path) for r in self.store.errors(project["id"]))
        if not force and not previous_error and old and not old["missing"] and old["signature"] == signature(path) and old["settings"] == fingerprint:
            return
        self.post(f"Reading {Path(path).name}…")
        digest, sig, metadata, entries = extract(path, settings, self.stop_event.is_set)
        counts = self.store.save_scan(project["id"], path, digest, sig, fingerprint, metadata, entries)
        self.store.scan_result(project["id"], path)
        self.post(f"{Path(path).name}: {len(entries)} annotations; {counts['added']} added, "
                  f"{counts['updated']} updated, {counts['removed']} removed.", True)
        for warning in metadata.get("warnings", []):
            self.post(f"{Path(path).name}: {warning}")

    def scan_path(self, path, attempt=0):
        for project in self.projects_for(path):
            try:
                self.scan(project, path)
            except Exception as exc:
                if self.stop_event.is_set():
                    return
                logging.exception("Scan failed: %s", path)
                self.store.scan_result(project["id"], path, str(exc))
                self.post(f"Could not read {Path(path).name}: {exc}", True)
                if attempt < 4 and Path(path).exists():
                    with self.lock:
                        if path not in self.pending:
                            self.pending[path] = (time.monotonic() + min(60, 2 ** (attempt+1)), attempt+1)

    def sync(self, project_id=None, force=False):
        failures = 0
        projects = [p for p in self.store.projects() if not project_id or p["id"] == project_id]
        for project in projects:
            if self.stop_event.is_set():
                return
            if not Path(project["root"]).is_dir():
                failures += 1
                self.post(f"Folder unavailable: {project['root']}. Saved notes retained.")
                continue
            seen, walk_errors = set(), []
            for folder, dirs, files in os.walk(project["root"], onerror=walk_errors.append):
                dirs[:] = [d for d in dirs if d not in {"Notebook backups", "notes_media", ".git"}]
                for name in files:
                    if self.stop_event.is_set():
                        return
                    if Path(name).suffix.lower() != ".pdf":
                        continue
                    path = canonical(Path(folder) / name)
                    seen.add(path)
                    try:
                        self.scan(project, path, force)
                    except Exception as exc:
                        if self.stop_event.is_set():
                            return
                        failures += 1
                        logging.exception("Scan failed: %s", path)
                        self.store.scan_result(project["id"], path, str(exc))
                        self.post(f"Could not read {name}: {exc}")
                        self.enqueue(path)
            if walk_errors:
                failures += len(walk_errors)
                self.post(f"Some folders could not be read under {project['root']}; saved notes retained.")
            else:
                self.store.mark_missing(project["id"], seen)
        self.export_pending()
        pending = sum(bool(p["error"]) for p in self.store.projects())
        issues = []
        if failures:
            issues.append(f"{failures} PDF read errors")
        if pending:
            issues.append(f"{pending} notebooks waiting to save")
        self.post("Sync finished" + ("; " + ", ".join(issues) + ". See Activity." if issues else "."), True)

    def export_pending(self):
        for project in self.store.projects():
            if self.stop_event.is_set():
                return
            if not project["dirty"] and Path(project["output"]).exists():
                continue
            # Do not recreate an offline/missing watched root merely to export.
            if not Path(project["root"]).is_dir():
                continue
            try:
                entries = self.store.entries(project_id=project["id"])
                value, backup = export_notebook(project["output"], f"Notes on {Path(project['root']).name}", entries, project["export_hash"],
                                               layout=json.loads(project["settings"]).get("notebook_style", "Reading"))
                self.store.export_result(project["id"], value)
                self.post(f"Notebook saved: {project['output']}", True)
                if backup:
                    self.post(f"Your edited notebook was preserved at {backup}", True)
            except Exception as exc:
                logging.exception("Export failed")
                error = f"Export pending: {exc}. Close Word if it has this file open; retry is automatic."
                self.store.export_result(project["id"], error=error)
                self.post(error, True)

    def run(self):
        next_sync = time.monotonic() + self.interval
        next_export = time.monotonic() + 30
        try:
            while not self.stop_event.is_set():
                try:
                    while not self.commands.empty() and not self.stop_event.is_set():
                        name, args = self.commands.get_nowait()
                        if name == "watch":
                            self.watch()
                        elif name == "sync":
                            self.sync(*args)
                        elif name == "rebuild":
                            self.store.mark_dirty(args[0])
                            self.export_pending()
                        elif name == "settings":
                            self.store.set_settings(*args)
                            self.sync(args[0])
                        elif name == "remove":
                            self.store.remove_project(args[0])
                            self.watch()
                            self.post("Folder removed from the library. Exported files remain on disk.", True)
                        elif name == "add":
                            self.store.add_project(args[0])
                            self.watch()
                            self.sync()
                        elif name == "export_view":
                            target, entries = args
                            _, backup = export_notebook(target, "Selected research notes", entries)
                            self.post(f"Exported {len(entries)} annotations to {target}" +
                                      (f". Previous file preserved at {backup}" if backup else ""))
                    with self.lock:
                        sync = self.sync_requested
                        self.sync_requested = False
                    now = time.monotonic()
                    if sync or now >= next_sync:
                        self.sync()
                        next_sync = time.monotonic() + self.interval
                    for path, attempt in self.due(time.monotonic()):
                        if self.stop_event.is_set():
                            break
                        self.scan_path(path, attempt)
                    if now >= next_export:
                        self.export_pending()
                        next_export = time.monotonic() + 30
                    # Batch export after a burst has settled.
                    with self.lock:
                        quiet = not self.pending
                    if quiet and any(p["dirty"] and not p["error"] for p in self.store.projects()):
                        self.export_pending()
                except Exception as exc:
                    logging.exception("Background operation failed")
                    self.post(f"Background operation failed: {exc}", True)
                self.wake.wait(.25)
                self.wake.clear()
        finally:
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=3)

    def stop(self):
        self.stop_event.set()
        self.wake.set()
