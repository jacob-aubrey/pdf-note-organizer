"""Saved local searches, paper tags and research collections."""
import tkinter as tk
from tkinter import ttk
from .icons import Button
from .theme import BACKGROUND
from .widgets import bind_dialog_close, fit_dialog, Tooltip, annotate_buttons, WrapToolbar
from .workflow_ui import background
from .storage import DEFAULT_SEARCH_FIELDS, SEARCH_FIELDS


def saved_search_options(value):
    """Read older saved searches with safe current defaults."""
    result = {"query": "", "mode": "Words / Boolean", "note_type": "All notes",
              "scope": "Notes", "label": "All papers", **value}
    fields = value.get("fields")
    selected = DEFAULT_SEARCH_FIELDS if fields is None else fields
    result["fields"] = [field for field in selected if field in SEARCH_FIELDS]
    return result


def labels(store):
    with store.connect() as db:
        return [f"{row[0]}: {row[1]}" for row in db.execute("SELECT DISTINCT kind,value FROM document_labels ORDER BY kind,value COLLATE NOCASE")]


def label_ids(store, value):
    if not value or value == "All papers":
        return None
    kind, separator, name = value.partition(": ")
    if not separator or kind not in {"tag", "collection"}:
        return set()
    with store.connect() as db:
        selected = {row[0] for row in db.execute("SELECT document_id FROM document_labels WHERE kind=? AND value=? COLLATE NOCASE", (kind, name))}
        if selected and db.execute("SELECT 1 FROM sqlite_master WHERE name='paper_document_sources'").fetchone():
            selected.update(row[0] for row in db.execute("""SELECT related.document_id FROM paper_document_sources selected
                JOIN paper_sources first ON first.id=selected.source_id JOIN paper_sources second ON second.paper_id=first.paper_id
                JOIN paper_document_sources related ON related.source_id=second.id WHERE selected.document_id IN (""" + ",".join("?" for _ in selected) + ")", tuple(selected)))
        return selected


def save_labels(store, document_id, values):
    documents = store.search_documents(document_id=document_id, whole_paper=True)
    if not documents:
        raise ValueError("This paper is no longer in the library.")
    with store.connect() as db:
        for document in documents:
            db.execute("DELETE FROM document_labels WHERE document_id=?", (document["id"],))
            for kind, names in values.items():
                if kind not in {"tag", "collection"}:
                    raise ValueError("Choose tags or collections.")
                unique = {" ".join(name.split()).casefold(): " ".join(name.split()) for name in names.split(";") if name.strip()}
                if len(unique) > 100 or any(len(name) > 160 for name in unique.values()):
                    raise ValueError("Use at most 100 labels, each no longer than 160 characters.")
                db.executemany("INSERT INTO document_labels VALUES(?,?,?)", [(document["id"], kind, name) for name in unique.values()])


def open_labels(app):
    paper = app.research_paper()
    if not paper:
        return
    window, frame = _window(app, "Tags & collections")
    ttk.Label(frame, text="Organize this paper and its linked copies. Collections group papers for a project or reading list; tags describe topics or follow-up tasks. Separate names with semicolons. These labels do not move or copy files.", wraplength=570).pack(anchor="w")
    variables, inputs = {}, []
    for kind, title in (("tag", "Tags"), ("collection", "Research collections")):
        ttk.Label(frame, text=title).pack(anchor="w", pady=(12, 4))
        variable = variables[kind] = tk.StringVar()
        field = ttk.Entry(frame, textvariable=variable, width=65, state="disabled")
        field.pack(fill="x")
        inputs.append(field)
        Tooltip(field, "Enter local " + title.lower() + " separated with semicolons. Labels apply to this paper and its linked copies.")
    status = tk.StringVar(value="Loading paper labels…")
    ttk.Label(frame, textvariable=status, wraplength=570).pack(fill="x", pady=12)
    saving = [False]
    def close():
        if not saving[0]:
            window.destroy()
    def failed(error):
        if window.winfo_exists():
            saving[0] = False
            save.configure(state="normal")
            for field in inputs:
                field.configure(state="normal")
            status.set(str(error))
    def save():
        if saving[0]:
            return
        draft = {key: variable.get() for key, variable in variables.items()}
        saving[0] = True
        for field in inputs:
            field.configure(state="disabled")
        save.configure(state="disabled")
        status.set("Saving labels…")
        def completed(_):
            app.query_signature = None
            app.refresh_notes()
            app.refresh_label_choices()
            window.destroy()
        background(app, lambda: save_labels(app.store, paper[0], draft), completed, failed, task='Saving paper tags and collections…')
    actions = ttk.Frame(frame)
    actions.pack(fill="x")
    save = Button(actions, text="Save labels", command=save, state="disabled", style="Primary.TButton")
    save.pack(side="right")
    cancel = Button(actions, text="Cancel", command=close)
    cancel.pack(side="right", padx=(0, 8))
    Tooltip(save, lambda: "Wait for the current label operation to finish." if save.instate(["disabled"]) else
            "Save local tags and research collections for this paper and its linked copies.")
    Tooltip(cancel, lambda: "Wait for labels to finish saving before closing." if saving[0] else
            "Close without saving changes to this paper's tags and collections.")
    annotate_buttons(window)
    bind_dialog_close(window, close)
    window.protocol("WM_DELETE_WINDOW", close)
    def load():
        ids = [row["id"] for row in app.store.search_documents(document_id=paper[0], whole_paper=True)]
        with app.store.connect() as db:
            return {kind: sorted({row[0] for doc in ids for row in db.execute("SELECT value FROM document_labels WHERE document_id=? AND kind=?", (doc, kind))}, key=str.casefold) for kind in variables}
    def loaded(values):
        if window.winfo_exists():
            for kind, names in values.items():
                variables[kind].set("; ".join(names))
            for field in inputs:
                field.configure(state="normal")
            save.configure(state="normal")
            status.set("Labels are local to this library. Use Collection or tag in Reader to filter notes and PDFs within your current folder and paper selection. All papers clears this label filter.")
    background(app, load, loaded, failed, task='Loading paper tags and collections…')
    fit_dialog(window, app.root)


def _window(app, title):
    window = tk.Toplevel(app.root)
    window.title(title)
    window.transient(app.root)
    window.configure(background=BACKGROUND)
    bind_dialog_close(window, window.destroy)
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    return window, frame


def open_saved_searches(app):
    window, frame = _window(app, "Saved searches")
    ttk.Label(frame, text="Save search text, Notes/PDFs/All scope, fields, note type and collection filter. Searches apply to the folder and paper currently selected.", wraplength=600).pack(anchor="w")
    list_frame = ttk.Frame(frame)
    list_frame.pack(fill="both", expand=True, pady=12)
    listing = tk.Listbox(list_frame, height=8, exportselection=False)
    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listing.yview)
    scrollbar.pack(side="right", fill="y")
    listing.pack(side="left", fill="both", expand=True)
    listing.configure(yscrollcommand=scrollbar.set)
    Tooltip(listing, "Select a saved search to apply it, update it with the current search, or delete it.")
    name = tk.StringVar()
    ttk.Label(frame, text="Search name").pack(anchor="w")
    name_entry = ttk.Entry(frame, textvariable=name, width=65)
    name_entry.pack(fill="x", pady=4)
    Tooltip(name_entry, "Name the current search to save it, or select a saved search to apply or remove it. Saving an existing name updates that saved search.")
    status = tk.StringVar(value="Loading saved searches…")
    ttk.Label(frame, textvariable=status, wraplength=600).pack(fill="x", pady=8)
    records, busy = {}, [True]
    def render(value):
        if not window.winfo_exists():
            return
        records.clear()
        records.update(value)
        listing.delete(0, "end")
        for key in sorted(records, key=str.casefold):
            listing.insert("end", key)
        if name.get() in records:
            index = listing.get(0, "end").index(name.get())
            listing.selection_set(index)
            listing.see(index)
        busy[0] = False
        status.set(f"{len(records)} saved search{'' if len(records) == 1 else 'es'}")
        update_controls()
    def selected():
        return listing.get(listing.curselection()[0]) if listing.curselection() else ""
    def update_controls(event=None):
        if event is not None:
            name.set(selected())
        save_button.configure(state="disabled" if busy[0] else "normal")
        for button in (apply_button, delete_button):
            button.configure(state="normal" if selected() and not busy[0] else "disabled")
    listing.bind("<<ListboxSelect>>", update_controls)
    def failed(error):
        busy[0] = False
        if window.winfo_exists():
            status.set(str(error))
            update_controls()
    def persist(remove=False):
        if busy[0]:
            return
        key = (selected() if remove else name.get()).strip()
        if not key or len(key) > 120:
            status.set("Enter a name from 1 to 120 characters.")
            return
        draft = {"query": app.search.get(), "mode": app.search_mode, "fields": app.search_fields,
                 "note_type": app.note_type, "scope": app.search_scope.get(), "label": app.label_filter.get()}
        busy[0] = True
        update_controls()
        def write():
            # Merge at execution time, preserving changes from another window.
            with app.store.connect() as db:
                import json
                row = db.execute("SELECT value FROM preferences WHERE key='saved_searches'").fetchone()
                saved = json.loads(row[0]) if row else {}
                if remove:
                    saved.pop(key, None)
                else:
                    saved[key] = draft
                db.execute("INSERT OR REPLACE INTO preferences VALUES('saved_searches',?)", (json.dumps(saved),))
            return saved
        background(app, write, render, failed, task='Saving searches…')
    def apply():
        if busy[0]:
            return
        value = records.get(selected())
        if value is None:
            status.set("Select a saved search first.")
            return
        value = saved_search_options(value)
        app.search_fields, app.search_mode, app.note_type = value["fields"], value["mode"], value["note_type"]
        app.update_search_options_summary()
        app.label_filter.set(value.get("label", "All papers"))
        app.search_scope.set(value["scope"])
        app.search.set(value["query"])
        app.tabs.select(app.notes_tab)
        app.query_signature = None
        app.refresh_notes()
        window.destroy()
    controls = WrapToolbar(frame)
    controls.pack(fill="x")
    save_button = controls.add(Button(controls, text="Save current search", command=persist, state="disabled"))
    apply_button = controls.add(Button(controls, text="Apply saved search", command=apply, state="disabled", style="Primary.TButton"))
    delete_button = controls.add(Button(controls, text="Delete saved search", command=lambda: persist(True), state="disabled"))
    Tooltip(save_button, lambda: "Wait for the current saved-search operation to finish." if busy[0] else
            "Save the current query, Notes/PDFs/All scope, matching rules, note fields, note type and collection filter under the entered name. An existing name is updated.")
    Tooltip(apply_button, lambda: "Wait for saved searches to finish loading or saving." if busy[0] else
            "Select a saved search from the list first." if not selected() else
            "Apply this saved query and its filters in Reader, keeping the folder and paper currently selected.")
    Tooltip(delete_button, lambda: "Wait for saved searches to finish loading or saving." if busy[0] else
            "Select a saved search from the list first." if not selected() else
            "Remove this saved search from the library. Notes and papers remain preserved.")
    close = Button(frame, text="Close", command=window.destroy)
    close.pack(anchor="e", pady=(12, 0))
    Tooltip(close, "Close this window without applying a saved search. Any save or deletion already requested will finish.")
    background(app, lambda: app.store.preference("saved_searches", {}), render, failed, task='Loading saved searches…')
    annotate_buttons(window)
    fit_dialog(window, app.root)
