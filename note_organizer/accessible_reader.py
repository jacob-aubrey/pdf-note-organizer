"""Semantic browser reading view for screen readers and keyboard-only reading."""
import html
from pathlib import Path
import uuid
import webbrowser
from .pages import page_description
from .workflow_ui import background


def render(entries, image_loader=None):
    escape = html.escape
    articles = []
    for index, entry in enumerate(entries):
        title = entry.get("logical_paper_title") or entry.get("metadata", {}).get("title") or Path(entry["path"]).stem
        text = [str(entry.get(field) or "") for field in ("quote", "comment", "ocr", "context")]
        note = "".join(f"<p>{escape(value)}</p>" for value in dict.fromkeys(text) if value)
        if entry.get("kind") == "drawing" and image_loader:
            data = image_loader(entry)
            if data:
                note += f'<img alt="Drawing on {escape(page_description(entry))}. Transcription and surrounding text are listed with this note." src="data:image/png;base64,{escape(data, quote=True)}">'
        path = Path(entry.get("source_link_path") or entry["path"]).resolve()
        link = path.as_uri() + "#page=" + str(entry["page"])
        articles.append(f'<article tabindex="0"><h2 id="note-{index}">{escape(title)}</h2>'
                        f'<p class="location">{escape(page_description(entry))} · {escape(entry["kind"])}</p>{note}'
                        f'<a href="{escape(link, quote=True)}">Open source PDF at page {entry["page"]}</a></article>')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:">
<title>Notable accessible reading view</title><style>
body{max-width:64rem;margin:2rem auto;padding:0 1.5rem;background:#18191a;color:#f2f4f8;font:1.1rem/1.7 system-ui}
a{color:#9dd1ff}button,input{font:inherit;padding:.5rem;color:inherit;background:#343638;border:2px solid #aab0b5;border-radius:.3rem}
input{width:min(95%,36rem)}article{border-top:1px solid #aab0b5;padding:1rem 0}img{max-width:100%;background:white}h2{font-size:1.25rem}
*:focus-visible{outline:3px solid #ffd166;outline-offset:4px}.location{color:#c9ced6}p{white-space:pre-wrap}
@media(prefers-color-scheme:light){body{background:white;color:#111}a{color:#064c8c}.location{color:#444}button,input{background:white}}
@media print{header input,header button{display:none}body{background:white;color:black}article{break-inside:avoid}}
</style><header><h1>Research notes</h1><p>Snapshot of your current Notable search. Use your browser's headings navigation, Tab, zoom or print controls. Source links open your local PDFs.</p>
<label for="filter">Filter this reading view</label><br><input id="filter" type="search" autofocus>
<p id="count" role="status" aria-live="polite"></p><button onclick="window.print()">Print or save as PDF</button></header><main>''' + ("".join(articles) or "<p>No notes match the current search.</p>") + '''</main><script>
const input=document.querySelector('#filter'),notes=[...document.querySelectorAll('article')],count=document.querySelector('#count');
function filter(){const text=input.value.toLocaleLowerCase();let visible=0;for(const note of notes){note.hidden=!note.textContent.toLocaleLowerCase().includes(text);if(!note.hidden)visible++;}count.textContent=`${visible} of ${notes.length} notes shown`;}
input.addEventListener('input',filter);filter();</script></html>'''


def open_reader(app):
    entries = [dict(entry) for entry in app.entries]
    app.notify("Preparing accessible reading view…")
    def prepare():
        def image(entry):
            return app.store.entry_image(entry["document_id"], entry["key"], expected_digest=entry.get("source_digest"),
                                         expected_note_revision=entry.get("source_note_revision"))
        folder = app.data_dir / "accessible-reading"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ("notes-" + uuid.uuid4().hex + ".html")
        path.write_text(render(entries, image), encoding="utf-8")
        # Keep a bounded set of generated snapshots. They contain private notes.
        for old in sorted(folder.glob("notes-*.html"), key=lambda file: file.stat().st_mtime, reverse=True)[5:]:
            old.unlink(missing_ok=True)
        return path
    background(app, prepare, lambda path: (webbrowser.open(path.as_uri()), app.notify("Accessible reading view opened in your browser.")),
               lambda error: app.notify(f"Could not prepare reading view: {error}"))
