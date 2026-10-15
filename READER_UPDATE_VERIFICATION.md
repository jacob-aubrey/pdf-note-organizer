# Reader and workflow updates — October 15, 2026

The requested changes are implemented in the Python source. No executable was built.

| Request | Result |
| --- | --- |
| Prominent paper title in every Reader view | Note view and PDF view keep a bold document heading visible, including Reading mode. Long titles use at most two lines; hover shows the complete title. The redundant page line was removed. Selected-note page information remains in Document details. |
| Help launches documentation | Open manual launches the public user manual. Open README prefers the current Markdown README in source installations and uses the shipped PDF fallback when needed. Both use the computer's default document application. |
| Only actual main-search hits are marked | Note text uses enabled-field hit ranges. PDF view maps only the selected result's proven printed-text hits; unrelated title words and printed occurrences of comment/OCR/metadata terms are not marked. |
| Wrapped words count and navigate | Line-wrap hyphens and discretionary soft hyphens are normalized for matching, while original text offsets are retained. Counts and main-match navigation use those same occurrences. Ordinary inline hyphenated compounds retain their spelling. |
| Main navigation respects columns | Printed PDF and surrounding-text extraction use source text flow through columns, matching the PDF reader's reading order instead of row-wise geometric sorting. |
| Separate PDF Find behavior | Find in PDF searches the whole current PDF and keeps its ordinary document navigation. It does not change the main query, filters, or result list. Selecting a main result or using its arrows returns to main-search authority. |
| Distinct search colors | Main search uses light blue and royal blue for the active hit. Find in PDF uses light green and dark green for the active hit. Marks are temporary display overlays. |
| Explain Annotation color | This checkbox includes the original annotation color as searchable text. For example, `tantalum AND yellow` searches enabled text fields and the original note color. It does not choose a search-mark color. The dialog and tooltip explain this distinction. |
| Fix `KeyError: 'popdown'` | Entry placeholders fall back to the raw Tcl focus path for combobox popup windows that Tkinter cannot resolve as Python widgets. |
| Show when searches are running | A compact animated progress indicator and explicit searching/loading message stay visible until the current query and row insertion finish. Stale query completion cannot dismiss the current indicator. Inputs remain available. |
| Explain inconsistent paper titles | Saved paper titles and usable PDF metadata are preferred. Filename fallback remains when no usable title exists; tooltips and Document details identify the source. Citation details can save a better title. |
| Consistent larger clear controls | Main Reader search and Find in PDF use matching 20-pixel logical X icons, respecting display scaling. |
| Consistent mode default zoom | Reading mode entry, main-match arrows, Ctrl+double-click and Ctrl+0 use 125%. Normal mode uses Fit width. Manual zoom remains available between reset actions. Exiting Reading mode restores the prior zoom/layout and keeps the current reading page. |
| Use available Inbox height | The review details area expands into remaining vertical space. The surrounding form retains scrolling when the window is too short. |
| Select local copies directly in Library review | A selectable copy table replaces the dropdown. Its selection drives open, copy, details and Delete actions. Footer actions remain visible. |
| Delete a reviewed duplicate | Delete selected PDF confirms the exact local file, then requests Windows Recycle Bin through the serialized service worker. Digest checks reject stale confirmations. Saved notes, source identities and annotation history are retained; other copies and tablet documents are kept. There is no permanent-delete fallback. |

## Refresh existing data

Restart Notable to load the updated source. PDF indexes refresh automatically on the next relevant search. Use **Sync PDFs** to refresh saved note contexts with the latest extraction reading order.

## Validation

Verification uses disposable libraries and PDFs. GUI/native tests run on a private inactive Windows desktop; synthetic window captures verify the title, Inbox, Help and Library review layouts.

The checks include real App-to-WebView communication, view switches, title updates without reload, query cancellation, wrapped words, two-column text, scoped blue/green marks, mode-specific zoom/reset, hyperlinks and pan, recovery, and clean process shutdown. A real disposable-file Recycle Bin test verifies that the other copy and saved annotation history remain unchanged.

Reproduce the complete source suite on Windows:

```powershell
$env:TEMP = Join-Path (Get-Location) '.test-tmp'
$env:TMP = $env:TEMP
.venv/Scripts/python.exe tools/run_ui_tests.py tools/run_test_batches.py
.venv/Scripts/python.exe tools/run_ui_tests.py tests/reader_app_regression.py
.venv/Scripts/python.exe tools/run_ui_tests.py tests/reader_webview_regression.py
```

Windows recycling uses the documented [IFileOperation recycling flag](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperation-setoperationflags). The app reports errors instead of substituting permanent deletion.

These checks establish the tested behavior; they do not certify every possible PDF encoding or reMarkable format extension. Unrecognized tablet-file format warnings remain a separate diagnostic concern and have not been hidden.
