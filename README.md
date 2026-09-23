# PDF Note Organizer 2

Collect PDF highlights, comments, drawings, and handwriting into searchable notes and Word notebooks. Processing stays on your computer. Source PDFs are opened read-only.

## Run

This version is being developed from Python source in VS Code. **The executable in `dist/` is the old version; no updated executable has been packaged.** Use the project's `.venv` (verified with Python 3.13):

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PDF_NOTES_DATA_DIR = Join-Path (Get-Location) '.local-data'
.\.venv\Scripts\python.exe "PDF Note Organizer.py"
```

Run these commands from the project folder. Creating `.venv` is only needed on first setup. Install Python 3.13 and the VS Code Python extension before using the launch profiles. The public repository contains source code and synthetic tests; personal libraries, PDFs, Word notebooks, logs, and executables are excluded.

In VS Code, open this project folder, select **PDF Notes - development library** in Run and Debug, and press **F5**. The launch profiles use `.venv/Scripts/python.exe` explicitly. This uses `.local-data/` inside the workspace and does not import old watched folders. **PDF Notes - synthetic example** opens a ready-made example containing highlights, handwriting, and an arrow. The third launch profile runs the regression suite, also available in VS Code's Testing panel.

The updated application has a `2.1.1` title and two main tabs, **Library** and **Notes**. The original source and executable are retained in `legacy/` for rollback. Do not run both versions against the same research folders. Packaging is deferred until the source version has been validated with real PDFs.

## Library and Notes

**Library** manages watched folders and PDF processing. Add folders, sync, change extraction settings, or select a paper and click **View notes →**. Double-clicking a paper also takes you to its notes. **More** contains notebook rebuilding, opening the selected PDF, and removing a watched folder. **Show activity** expands the processing log.

**Notes** is the reading workspace. Folder and paper selectors stay in sync with Library. Choose **All folders** to search the whole library. The notes list and the text/image preview have adjustable dividers; long note text can be scrolled. Open the folder's notebook or export the current filtered view from the toolbar. **More** contains editable copies and annotation history. Existing libraries open on Notes; an empty library opens on Library.

**Search in…** selects the fields to search: paper title, highlights/marked text, typed comments and replies, available handwriting OCR, surrounding printed text, filename, author, DOI, color, and page number. **Clear fields** makes it quick to choose only one field; **Reset all** restores the defaults. **Words / Boolean** matches search words across selected fields; **Exact phrase** requires the complete search text within one field and treats operators as ordinary text. Matching ignores capitalization and repeated whitespace. A note-type filter can show highlights, drawings/handwriting, or notes with typed comments, even without a search term. Active options remain applied as you switch papers during the session.

In **Words / Boolean** mode, use uppercase `AND`, `OR`, and `NOT`, double quotes for phrases, and parentheses for groups. For example:

```text
(iodine OR gold) AND "spectral CT" NOT phantom
```

Spaces between terms mean AND. Precedence is NOT, then AND, then OR; parentheses override it. Lowercase operator words are ordinary search terms, and `"OR"` searches literally for that text. All terms and exclusions apply only to selected fields within an individual note (including its paper metadata), not across different notes. Matching uses substrings, so `stent` also matches `stents`. Incomplete queries show an inline explanation and disable export until corrected.

Handwriting search requires a saved OCR transcription. Selecting that search field does not enable OCR or search the printed text beneath handwriting; printed context is a separate field. Enable optional transcription in Library Settings if Tesseract is installed. Drawings without transcriptions remain browsable with the drawings/handwriting filter. These classifications overlap: a highlight with a typed comment can match both Highlights and Typed notes.

## Opening source PDFs

**Source PDF** sends the selected note's actual PDF page position to the chosen viewer. This is independent of printed labels: printed page 233 may be the first page in the file. Change the viewer through **Notes → More → PDF viewer**. The choice is saved in that library and does not change Windows associations.

New libraries use **Windows default**. Explicit choices include Edge, Chrome, Firefox, Acrobat/Reader, and SumatraPDF, plus **Other application** with a Browse button for portable or unrecognized viewers. Browsers receive an encoded file URL with `#page=`, Acrobat/Reader receive `/A page=`, and SumatraPDF receives `-page` with instance reuse. The adapters follow [Adobe's documented PDF parameters](https://pdfobject.com/pdf/pdf_open_parameters_acro8.pdf) and [SumatraPDF's command-line options](https://www.sumatrapdfreader.org/docs/Command-line-arguments).

If the default or custom viewer is unrecognized, the original PDF still opens and the app explains which page to navigate to manually. A missing explicitly selected viewer produces a clear error and directions to change the preference; it does not silently switch applications. Page navigation ultimately depends on the viewer honoring its parameter. Automated tests verify routing, encoded paths, physical page numbers, saved preferences, and fallback/error behavior; live page-jump verification has not been completed for every viewer.

## Annotation images and context

The default image is a crop of the **original PDF page** with its text, figures, arrows, highlights, and handwriting intact. Nearby letters and strokes are joined into blocks even when their shapes do not overlap. Crops include a surrounding margin and complete intersecting text lines. Images are embedded in the Word notebook and retained in the library.

Select a folder and open **Settings**:

- **Nearby blocks** joins nearby letters and lines (default).
- **Nearby lines** reduces the vertical joining distance.
- **Whole page** combines all drawing annotations on each page and preserves the whole page, useful for arrows that connect distant items or complex diagrams.
- Increase the joining distance if a phrase is still split; decrease it if separate notes merge.
- Increase the context margin to show more surrounding material.

Use **Enlarge context** to view the retained image at its full resolution. These are heuristics: PDFs don't generally identify which separate pen strokes belong to one thought. Manual region selection and per-page overrides remain future work.

OCR is off by default. Optional Tesseract transcription runs on isolated ink so printed text is not mislabeled as handwriting. It requires the Tesseract executable on PATH. Its output is labeled a suggestion; handwriting recognition is not guaranteed. All visual context remains available without OCR.

## Notebook workflow

The default **Reading** layout groups passages under one heading per paper and page. Quotes use plain, readable type; your comments appear as **Note:** underneath. Repeated extraction labels, timestamps, folder paths, and warnings stay out of the reading document. Source and page links remain available. Select **Detailed** in folder Settings to retain the diagnostic layout. The app preview's **Details** checkbox reveals technical information when needed.

Annotations follow the PDF's internal text order to avoid mixing the two columns of journal articles. PDFs with incorrect internal reading order can still need manual organization. This is a collection of your selected passages, not an automatically written synthesis. An extraction update triggers a fresh scan even when the PDF itself has not changed; layout-only changes reuse saved notes.

The interface uses Paper Sorter's charcoal panels and blue accents, with rounded buttons and hover, pressed, and disabled states.

1. **Add folder** imports annotated PDFs recursively. Each watched folder is an independent project, including overlapping folders.
2. Changes are watched while the application is open. Startup and five-minute reconciliation scans catch changes made while it was closed. **Sync now** checks on demand.
3. **Open notebook** opens `Notes on <folder>.generated.docx`. Quotes, comments, source links, metadata, and drawing context are organized by paper and page.
4. **Save editable copy** creates a separate document for your own research writing. It is never regenerated by the app.
5. **Rebuild notebook** recreates the generated notebook from the saved library. It does not depend on re-reading the PDFs.
6. **Export this view** creates a separate Word notebook from the currently filtered papers/notes. Search can include all folders, publication metadata, annotation colors, comments, and highlighted text.

If you edit the generated notebook directly, the next regeneration first preserves your edited document in the adjacent **Notebook backups** folder. Those edits are **not merged** into the new generated notebook. Prefer an editable copy for ongoing writing. Old v1 notebooks are never selected as v2 export targets.

Word may lock an open document. Failed exports remain pending and retry every 30 seconds; extracted annotations remain safely saved. The project list and Activity tab show failures. No missing source is silently discarded: unavailable PDFs keep their last successful extracted notes. Removing a watched folder explicitly removes its library and history but leaves PDF and Word files untouched.

Page links work with viewers that support `file:` links and `#page=`. Some default Windows viewers ignore the page fragment; the PDF page number remains visible.

## Data and migration

- The library and rotating logs live in `%LOCALAPPDATA%/PDF Note Organizer/`, independent of launch directory.
- One instance runs per data directory.
- Existing `notes_watcher.db` files near the source or executable are read only to import watched folder paths on first launch. Their annotation hashes are not trusted; PDFs are re-extracted into the new library.
- The v1 databases and notebooks are left untouched. The entire v2 library, including images and annotation history, is in `library.sqlite3`.
- Back up that data directory while the application is closed. A test/development instance can use the `PDF_NOTES_DATA_DIR` environment variable to select an isolated library.
- Closing cancels extraction at the next page or annotation boundary, retains the last completed snapshot, and stops watching. There is no background service or automatic startup yet.

## Development and verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The regression suite uses synthetic PDFs and temporary notebooks: split pen strokes, arrows and underlying text, reply handling, edits/deletions, repeat saves, rename/copy cases, rotated pages, OCR absence, failed exports, external Word edits, rebuilding, and migration. `python -m tests.qa_app` opens an isolated visual test app under `tmp/qa/app`.

Implementation is split into extraction, SQLite storage, Word export, a serialized background service, and the Tk interface. PyMuPDF calls stay on the single background worker. Failed scans never replace a successful snapshot; Word writes use a temporary file followed by atomic replacement.

## Remaining enhancements

- Manual crop adjustment and stroke merge/split controls, with per-page settings.
- User-defined color categories and topic tags (colors are currently searchable).
- Rich editing of personal synthesis inside the app and integration with generated sections.
- Citation-manager integration and verified bibliographic enrichment (current metadata comes from the PDF).
- Optional source-linked summaries, additional export formats, and a tray/startup mode.

Automatic annotation grouping still needs validation with real examples from the PDF readers and pen workflows you use. Flattened annotations have become ordinary page content and cannot be separated reliably without a different workflow. Scanned highlights retain an image when no text layer is available.
