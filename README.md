# Notable

The Zotero-first route now has a graphical plugin and a bundled Windows helper.
See [reMarkable Sync for Zotero setup and workflow](documentation/ZOTERO_PLUGIN.md).
The standalone application and its existing documentation below remain available
while that migration is evaluated.

Notable helps you organize research documents and collect your PDF annotations into searchable notes and Word notebooks. You can use it entirely on your PC. Document identification through online services and connection to a reMarkable tablet are optional.

For task-by-task walkthroughs with annotated screenshots, see the [Notable 2.6 user manual](output/pdf/Notable-User-Manual.pdf). Each procedure shows which control to click, what appears next, and how to check the result. It covers setup, filing, PDF reading and search, exports, optional tablet syncing, backups, troubleshooting, and keyboard shortcuts.

There are two related workflows:

- **Sorting documents:** review a suggested name and choose where an incoming PDF, Word document, or PowerPoint presentation belongs.
- **Reading PDF notes:** collect highlights, comments, drawings, and handwriting from watched PDF folders, then read, search, or export those notes.

Sorting supports `.pdf`, `.docx`, `.pptx`, and legacy `.ppt`. **Only PDFs enter note extraction, combined paper notes, Word notebooks, and reMarkable paper transfers.** Filing a Word or PowerPoint document does not turn it into a PDF or add it to the Reader tab.

This README starts with setup and ordinary use. The [existing-library cleanup walkthrough](#bring-an-existing-pc-and-tablet-library-together) explains how to work through disorganized collections a few papers at a time. Troubleshooting and technical reference follow afterward.

The current version is **Notable 2.6.0**. This release adds consistent Windows taskbar shortcut identities and corrects the Windows regression workflow. The previous release introduced verified backup and recovery, history-preserving storage compaction, indexed PDF search, tags and research collections, saved searches, an accessible reading view, explicit citation conflict review and faster background PDF scheduling. The [implementation report](AUDIT_IMPLEMENTATION.md) maps the audit recommendations to those changes and verification.

The [October 13 interface audit](UI_AUDIT_2026-10-13.md) documents the consistency and layout polish, scrollable Settings and Inbox forms, responsive action rows, readable tables and the new open-source notebook-and-pen app icon. Short Library panes condense details to their path controls; enlarge the pane to restore the full explanation and Copy details action.

## Download and open the Windows app

Download **Notable-2.6.0-windows-x64.exe** from the [Notable 2.6.0 release](https://github.com/jacob-aubrey/pdf-note-organizer/releases/tag/v2.6.0). Save it in a permanent folder and double-click it. This portable executable includes Python and the app's dependencies; it does not need a Python installation or an installer. Windows 10/11 x64 and the Microsoft Edge WebView2 Runtime are required for the embedded PDF reader. Most Windows 11 PCs already have WebView2.

On packaged launches, Notable creates or updates its **Notable** entry in your Windows Start menu. To pin it, launch it once, open Start, search for **Notable**, right-click that entry, and choose **Pin to taskbar** (under **More** on some Windows versions). The shortcut and running app share the same Windows identity. Existing desktop, Start menu and taskbar shortcuts pointing to this exact executable receive the same identity without changing their launch arguments. Notable does not pin itself automatically. Managed profiles can restrict shortcut updates; the app still opens if registration is unavailable.

When upgrading to a differently named executable or moving it, launch the new copy first so the Start entry updates. If an older pinned shortcut still opens the old version, unpin it and pin the current **Notable** Start entry. A shortcut's target remains a specific file; updating its identity does not redirect it to a different executable.

The executable is unsigned. Windows may show an unrecognized-app notice; check the download came from the project's release page and compare its SHA-256 hash with `SHA256SUMS.txt` before deciding whether to run it. The release also includes the user manual and PDF README, both accessible inside the app through **Help**.

The packaged app stores its library in `%LOCALAPPDATA%/PDF Note Organizer/`. Existing packaged libraries stay in that location. The source app normally uses the repository's `.local-data/` directory, so it can show a different collection. **Settings → Library & diagnostics** shows the active library. Set `PDF_NOTES_DATA_DIR` before launch only when you intentionally want a different library; keep the executable and its download folder separate from your data.

On launch, a branded splash identifies the startup task and then reveals the settled workspace. A one-file executable can take a few seconds to unpack its runtime before the splash appears. Local PDF checks and cloud sync continue in the background. To update, close Notable safely and replace the executable with a newer release; your separate library data remains in place.

## Set up and open the source app

### First setup on Windows

Use the source app when developing Notable or running it from VS Code. Release builds live under `dist/releases/v2.6.0/`; earlier releases remain separate rollback copies.

The project environment is configured for Python 3.13. Install Python 3.13, open PowerShell in the project folder, and run:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe "PDF Note Organizer.py"
```

The first command creates the project's own Python environment. The second installs the packages into that environment. Creating `.venv` is a first-time step; reinstalling requirements is useful when dependencies change.

`requirements.lock` includes hashes for the tested Windows x64/Python 3.13 wheels and every runtime dependency. `requirements.txt` lists the direct dependencies for other platforms; it is not the reproducible Windows environment.

### New in 2.5: reading, organizing and storage

**Actions ▾** exposes additional commands in each workspace. Library also has a visible **Folder actions ▾** menu. An unconfigured Inbox offers **Set up Inbox**. Advanced processing distances stay collapsed until needed; an example illustrates the grouping choices.

In Reader, use **Actions → Tags & collections…** to label the selected paper and its linked copies. Separate names with semicolons. Choose a tag or collection in the Reader filter to browse its notes and printed PDF matches. **Saved searches…** stores search text, fields, matching mode, note type, collection and Notes/PDFs/All scope. Applying a saved search uses your currently selected folder and paper.

**Accessible reading view…** opens the current results in your browser with semantic headings, searchable text, source links, zoom and print controls. It is a local snapshot; open it again after changing the results. This improves access to reading content. The full Tk application has not been certified with NVDA or other screen readers.

Reader has **Note view** and **PDF view** tabs sharing one result list and main search. A single compact header contains the view tabs, **Open externally**, **Reading mode**, and main-match arrows/counter. Note view displays each note passage once with inline matches, comments and drawing close-ups; additional excerpts identify matches in other fields. PDF view displays the complete selected document, including verified combined PC/reMarkable notes. Switching views keeps the selection, PDF position and zoom. Select a result to jump to its page; continue scrolling independently, then use **Back to selection** to return. That button is unavailable when browsing a PDF without a selected note or search hit. **Reading mode** hides the filters and results, opens PDF view, and starts at **125%**. Main-match arrows and reset gestures return to 125% while Reading mode is active. Manual zoom remains available. **Exit reading mode** restores the previous view, layout and zoom while retaining your current PDF reading place.

**Find in PDF** or **Ctrl+F while focused inside the PDF** searches only the open document. It never changes the main query, filters or result list. Selecting a result, using the shared main-search arrows, changing the main search, or closing Find returns navigation to the main search and its positive terms. Main-search arrows and PDF Find apply **125% in Reading mode** or **Fit width normally**, keep the page centered horizontally, and scroll to reveal the selected occurrence. Blue marks show only actual enabled-field hits for the selected main result; PDF Find uses green and searches the whole document. Wrapped words count and navigate as one occurrence; PDF results follow the document text flow through columns. **Ctrl + mouse wheel** zooms; **Ctrl+0** restores 125% in Reading mode or Fit width normally. **Ctrl + click-and-drag** pans from any PDF content, including hyperlink text and linked images. Ordinary clicks open links and plain dragging selects text. **Ctrl + double-click**, including on links, resets the same mode default and the current page's starting position. Image/full-page previews use the same gestures, resetting to their opening zoom and top-left position. Search marks are temporary; there are no selected-note bounding boxes. Muted placeholders explain search boxes without becoming part of their queries. A progress indicator beside Search identifies searches still running. Main-search and PDF Find clear buttons use the same larger X icon.

Main-search navigation keeps the PDF visible. Page matches in the same unchanged PDF reuse the open document; switching PDFs retains the previous painted page until the replacement is rendered. A small **Opening PDF…** message appears only if loading takes long enough to notice.

PDF search/indexing, local PDF checks, pending notebook exports, and batched search-result display use compact completed-item progress bars. A count such as **143 / 520 PDFs** advances after each PDF finishes; hover for the current filename. Files reporting issues count as processed and retain their existing warnings. Unknown-duration work keeps an activity indicator.

When a toolbar needs more room, button labels collapse to icons and return when space allows. Their action names, hover help, keyboard order and click targets remain available. Consequential actions retain text until other labels have collapsed. Reading mode uses an expand icon and Exit reading mode a collapse icon.

**Actions → Document details…** contains the selected paper's identity, page information, original source path and extraction diagnostics. Both views keep a prominent document title visible, with at most two lines and the full title on hover. Titles use saved paper/PDF metadata, falling back to the filename when no usable title exists; Citation details can save a better title. The title source is identified in result tooltips and Document details. The general reMarkable coordinate-conversion advisory appears there instead of in every note. Actual extraction issues remain visible. Legacy reMarkable highlight popups that only repeat the highlighted quotation are suppressed in the embedded reader; genuine comments are retained and source PDFs remain unchanged.

**Open externally** opens the original source PDF in your computer's default PDF application, where you can edit it. Use **Sync PDFs** afterwards to refresh extracted notes. Library **Open externally** and **Export annotated PDF** actions still provide the verified combined reading copy. The embedded reader is read-only; annotation creation, form editing and PDF scripting are disabled.

The embedded reader currently requires Windows and the **Microsoft Edge WebView2 Runtime**, normally present on Windows 11. Its pinned PDF.js runtime is bundled under `note_organizer/assets/pdfjs`; PDFs and viewer resources stay on the computer and need no CDN. A private loopback server serves only the selected PDF to the embedded browser. Source installations get the reader dependencies through `requirements.txt` / the Windows `requirements.lock`. If the runtime cannot start, the reader explains the issue and offers **Retry reader**; **Open externally** remains available.

Launching Notable shows a compact splash with its icon and current startup task. The workspace appears after the saved library, initial results and window layout are ready. Routine PDF and cloud checks continue in the background. Escape or the splash's close button cancels startup.

Closing Notable shows a centered **Closing Notable safely…** dialog. App interaction is blocked while active tasks finish, but the progress indicator and task details stay responsive. The dialog identifies the remaining save, PDF, Inbox, search or sync operation and closes automatically when shutdown is complete.

Other keyboard shortcuts include **Ctrl+F** outside the PDF for library search, **F5** to sync PDFs, **Ctrl+,** for Settings, **Alt+1/2/3** for Inbox/Library/Reader, **Ctrl+Shift+S** for saved searches, **Ctrl+Shift+T** for labels and **Ctrl+Shift+A** for the accessible reading view. Saved timestamps appear in local time.

**Help → Open manual** and **Open README** launch the bundled guides. The Inbox review details area expands to use available height while retaining scrolling in smaller windows.

**Help → Give feedback…** prepares an editable bug report or suggestion. **Open feedback email…** copies the complete report and opens a draft in your configured email application; you review and send it yourself. **Copy report** is available if no email application opens. Screenshots can be attached manually in the email. Only the app version, operating system, and source/packaged status are added automatically; no library paths, logs, PDFs, note contents, or credentials are attached.

**Help → Check for updates…** manually checks the repository's latest published stable GitHub release and shows its version and release notes. Source users can open a tagged source download; packaged users can open a compatible attached Windows download when available. Downloads open only after you choose them, in your browser. The app does not install updates or overwrite a source checkout. A repository without a public stable release, an unavailable connection, or an unrecognized version produces an explanatory result.

When linked copies have different reviewed citations, choose the citation to retain before linking or exporting. A citation draft must be saved to apply it to the linked paper. Undoing a link restores its previous citations when no later citation edit would be lost. Supplements use DOI and verified content matches to associate with their parent paper; attachments can be opened from the paper's supplement view.

Open **Library → Actions → Library storage & backups…**, also available in **Settings → Library & diagnostics**:

- **Create verified backup…** saves a SQLite snapshot, retained tablet sources, settings and available original PDFs/attachments in a hash-verified ZIP. Protect this archive as private library data: it may include encrypted local credentials. Keep a copy on separate storage for disaster recovery. Unavailable external files cannot be included.
- **Compact library…** creates and verifies that backup first, shares repeated note images, reclaims unused database pages and checks integrity. Note revisions remain. This is an explicit maintenance action; launching the upgrade does not compact the existing database.
- **Restore backup…** verifies the archive and creates a new independent directory. **Open restored library** launches it with recovered original snapshots. Inbox watching and cloud services start paused for setup review. Existing directories cannot be overwritten.
- **Review extra PDFs…** retains the existing reviewed cleanup workflow. **Review recovery archives…** removes a raw tablet archive only when every member is proven identical to retained baseline/layer assets and its notes have migrated. It requires review and a verified backup; uncertain archives remain with an explanation.

In **Search filters**, **Annotation color** includes original note color names as searchable fields; it does not choose the temporary search mark color. For example, `tantalum AND yellow` can match highlighted text and annotation color across enabled fields.

PDF text indexing builds as papers are searched. Older indexes refresh automatically; Sync PDFs refreshes stored note contexts for the latest source reading order. Short terms and negative queries retain the existing matching behavior through a conservative fallback. Reading PDFs retain the guarded cache budget. Large PDF text jobs yield between small page batches so a preview can run promptly; obsolete previews and searches cancel cooperatively.

Optional Gemini naming has a model selector and **Test connection** in Sorting settings. The test checks the selected model with your draft/saved key; it does not send a document or generate text. Existing configured libraries preserve their model compatibility. New setups default to `gemini-3.5-flash-lite`; availability still depends on your account.

### Verify the Python source

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe tools/run_ui_tests.py tools/run_test_batches.py
```

Windows CI installs the hashed runtime dependencies, checks Python compilation and runs the complete regression suite in process batches on its disposable GitHub-hosted VM. Local GUI checks use an inactive desktop; the hosted VM uses its own desktop for WebView2 compatibility. Failed runs retain batch logs as downloadable workflow artifacts. CI does not publish releases automatically. To build the portable Windows executable locally, install PyInstaller in the project environment and run `python scripts/build_release.py`. The script uses a dedicated versioned build/output directory, includes the bundled guides and PDF.js assets, and writes release checksums. Existing databases and older executables directly inside `dist/` are retained copies.

The release bundles the current user manual and README PDFs. Help opens these same bundled guides.

For later launches, run this from the project folder:

```powershell
& ".\Run PDF Note Organizer.ps1"
```

This script chooses the project's Python explicitly. It uses the same saved project library as a direct source launch, then restores the shell's previous environment settings when the app exits.

### Open it in VS Code

Open the project folder in VS Code and install its Python extension. In **Run and Debug**, select **Notable - development library**, then press **F5**. That profile explicitly uses `.venv/Scripts/python.exe` and the project's `.local-data` directory.

Two other profiles are available:

- **Notable - synthetic example** opens a disposable example with highlights, handwriting, and an arrow.
- **Notable - regression tests** runs the automated test suite. Tests are also available through VS Code's Testing panel.

Activating `.venv` in a terminal does not change the Python selected by VS Code's current-file debugger. If an error says `No module named 'docx'`, use the named development profile or the PowerShell launcher above. If it still fails, install `requirements.txt` using `.venv`'s Python.

### Know which saved library you opened

Your **paper folders** and the app's **saved data directory** serve different purposes. A paper folder contains your actual research files. The data directory contains Notable's database, settings, history, and retained tablet sources.

Direct source launches and the PowerShell launcher normally use `.local-data/` beside the source entry point. This location does not depend on the shell's current folder. The development F5 profile explicitly selects `.local-data` and skips importing old watched folders.

An explicitly set `PDF_NOTES_DATA_DIR` overrides the source app and launcher's default. The packaged app normally uses `%LOCALAPPDATA%/PDF Note Organizer/`; it may therefore show a different saved library from the source version.

Open **Settings → Library & diagnostics** to see the active location in a compact path box. Hover over it to see the whole path and an explanation of what it contains. The small copy button beside it copies the complete location. **Open data folder** opens it in File Explorer. The library summaries underneath can be scrolled and copied too.

File and folder paths use the same controls throughout the app: hover over the path to see its complete current value together with the explanation, and use the small copy button beside it to copy the full location. The button's tooltip says **Copy full path** and identifies the location it will copy. These actions do not change the folder or save draft settings. A blank or unselected location has its copy button disabled.

Some details panels contain several locations, such as an original file and its destination. Choose the location in the panel's small list, then use its copy button. **Copy details** copies the entire explanation and its paths together. You can reach the path copy buttons with Tab and activate them with Space or Enter. There is no separate right-click menu for paths.

In Reader, the folder copy button copies the selected watched folder. The paper copy button copies the chosen paper's location. When viewing **All papers**, it copies the selected note's source PDF; its tooltip identifies that source. In the expanded processing log, **Locations** lets you choose a recorded file, recovery copy, or watched folder to copy.

Read-only summaries may identify other project or installed libraries. Selecting a different data directory on launch loads that library's own watched folders, settings, and credentials. Diagnostics does not merge or move libraries.

One app instance can use a given data directory at a time. Original applications remain available for rollback. Close the old Paper Sorter before enabling Notable's automatic Inbox checks so both apps do not try to handle the same incoming file.

## Find your way around

The window title is **Notable**. **Settings** and **Help** sit at the right of the tab row.

| Place | Use it for | What the main action changes |
| --- | --- | --- |
| **Inbox** | Review incoming document names and destinations. | **File document** puts the selected file in its chosen library folder and removes the Inbox copy after successful filing. |
| **Library** | Choose watched PDF folders, inspect their papers, and manage processing. | **Add folder** registers an existing folder for PDF notes. It does not move its papers. |
| **Reader** | Read and search notes and printed PDF text; open papers and export notes. | Read saved notes, preview highlighted PDF matches, export Word documents, or save an annotated PDF. |
| **reMarkable** | Connect, download tablet PDF annotations, map folders, and review outgoing transfers. | Cloud actions use the connection and the separately enabled transfer permissions. |
| **Settings** | Choose naming permissions, PDF viewing, processing defaults, and optional connections. | **Save preferences** commits the draft; **Cancel** discards it. |

For a new library, reMarkable cloud services start **off**, and its tab is hidden. Enable them through **Settings → Connections** and save to reveal the tab. Turning the master switch off hides the tab and pauses cloud activity while keeping downloaded notes, pairing, and folder links. Existing configured libraries retain their saved connection choices.

An empty library normally opens on Inbox. A library with saved notes normally opens on Reader. **Folder actions ▾ → Open folder** in Library opens the selected watched folder in File Explorer. In Reader, **Open folder** opens the selected folder; select a specific folder first if you are viewing all folders.

The footer describes background work. **View sync details** appears when a check or recovery needs attention and takes you to Library's processing log. In Library, **Show sync details** expands that log and **Hide sync details** collapses it. Unavailable watched folders, PDF read failures, pending notebook exports, and retained previous PDF copies are reported separately. The log includes complete saved recovery paths so you can find those copies in File Explorer.

### Read long paths and explanations

Hover over a button for a short explanation. Path fields and path entries in tables show the complete location together with their explanation, even when the displayed filename fits. Other clipped table cells reveal their complete text. Long tooltips can widen to fit the available monitor space; moving away, switching tabs, or changing focus dismisses them.

Long filenames in Inbox also show their full current text on hover. Inbox metadata, Help, and annotation history have scrollbars so longer information stays readable. **Escape** follows the same action as a dialog's Cancel or Close button. In Settings, this discards draft changes, including a pending key removal; a save already in progress must finish first.

Double-click or press **Enter** on an actual local file/folder row to open that item: folders use File Explorer and PDFs use the default PDF viewer. With multiple copies selected, activation opens only the clicked or focused item. Library paper rows instead use the internal Reader shortcut described above. Review findings and interrupted filings reveal their copies or locations; cloud-only and unmapped items explain what is unavailable without starting a download. In Inbox, use **Review selected** for naming/filing; double-click opens the downloaded file. Library **Actions ▾ → Send selected PDF…** contains the explicit tablet transfer action.

Drag the divider between column headings to resize a column. **Double-click that divider** to fit the column to its current rows. A manually sized column keeps its size through refreshes. Horizontal scrollbars appear when needed; **Shift + mouse wheel** pans across a wide table. Dividers between the Reader list and preview can also be dragged.

## Sort new documents through Inbox

### Choose the two folders

Open **Settings → Sorting** and choose:

- An **incoming folder**, such as `C:\Incoming`, for downloads that still need review.
- A **library root**, such as `C:\Literature`, beneath which you will file finished documents.

These must be different folders. Neither can contain the other, and neither can be inside the app's private data, cache, or reMarkable review areas. When automatic checking is enabled, both folders must already exist.

You can instead use **Import sorter settings…** to load an old Paper Sorter JSON file into the Settings draft. Import brings in folders and naming choices. It does not import a Gemini key, enable Gemini, or start automatic checking. Inspect the draft, then choose **Save preferences**.

Automatic Inbox checks run while Notable is open. You can leave them off and use **Refresh inbox** whenever you want to review downloads. Scanning checks file readiness; it does not identify papers online, move files, or upload them.

### File one document

1. Put a supported document directly in the incoming folder, or use **Add documents…**. Dragging supported files onto the Inbox list also copies them into that folder. The externally selected source stays where it was.
2. Choose **Refresh inbox** if necessary. A file must finish downloading and stop changing before it becomes ready. Subfolders of the incoming folder are not scanned as new downloads. Office lock files and unsupported file types are ignored.
3. Select a ready document and choose **Review selected**. Notable reads its available text and metadata using your naming permissions, then suggests a filename.
4. Check the proposed title, authors, year, and any review explanation. Edit the filename if needed. Enter only the filename; the source extension is retained and added if omitted.
5. Choose an existing destination below the library root, or type a new subfolder path. A new destination folder is created only when you confirm filing.
6. Choose **File document**, check the name and destination in the confirmation, and confirm.

Filing saves a complete copy without overwriting an existing destination file. It keeps a recovery journal—a saved record of the source, destination, and copy progress—before removing the incoming source. If the source changes during review or filing, it must be reviewed again. A name collision leaves the incoming file and existing destination intact so you can choose another name.

Before removing the incoming file, the app verifies both copies and protects them from simultaneous edits or replacement. If a file changes or cannot be protected, the available copies stay in place for review. Adding a file that changes during copying can also leave a copy in Inbox; inspect it before retrying.

A confirmed PDF is handed to the local note library. DOCX, PPTX, and PPT remain locally filed documents and do not enter the PDF note pipeline. The sorting root can cover a broad collection while the optional tablet link covers only one selected portion of it.

**Skip** sets a document aside without moving it. You can review it again later; changed contents return it to the incoming queue. If identification fails, the document may still be named manually. **Retry lookup** retries identification and retains a filename you edited.

After an interruption, Notable recovers journaled copies before handing pending PDFs to the library. Uncertain copies remain for review, with their source and destination explained. Read the recovery issue before retrying a filename that may already exist at its destination.

Open **Inbox → Filing recovery…** to see retained filing issues. Select a row, read both complete paths, and use **Open inbox** and **Open containing folder** to inspect the available copies. This dialog does not automatically choose, move, or delete a copy.

### Choose how names are identified

**Local only** reads text and built-in metadata on your computer and makes no naming-service requests.

**Smart** can use two separately permitted services:

- A DOI lookup sends an exact DOI found in the document to Crossref or DataCite for citation details. A DOI is a permanent publication identifier. This lookup sends the identifier rather than the document text or file. The app checks that the returned title and other details fit the document.
- Optional Gemini identification can send extracted document text as a backup when citation information is incomplete. It requires **Use Gemini for document identification** and your own key. Word and PowerPoint also require their separate text-sharing permissions.

Gemini starts off. Each user supplies their own key, protected for their Windows account in that saved library. Ordinary sorter import does not bring in a key. A blank key field normally keeps an existing saved key.

**Remove saved key** is a draft action. It disables Gemini in the draft and changes the button to **Undo removal**. The key is still saved until **Save preferences** succeeds. **Undo removal**, **Cancel**, or closing Settings before saving preserves it. A successful save removes this library's key and turns Gemini off. Separate key files and the old sorter's settings are not changed.

All Settings tabs save together. If saving fails, the dialog stays open, the previous saved preferences and key remain, and you can correct or cancel the draft. If automatic Inbox checks cannot restart after a successful save, the app reports that separately: the preferences have been saved, and a manual refresh is still available.

DOCX and PPTX text each require their own Gemini permission. Legacy PPT files need local/manual review and are not sent to Gemini. Filename formats and a limited custom template let you choose a naming pattern; a custom template contains supported tokens, not a path or extension.

## Use Library, Reader, and notebooks

### Watch an existing PDF folder

Choose **Library → Add folder** and select an existing folder of PDFs. Notable reads annotated PDFs recursively and saves their notes. It reads source PDFs without editing them.

Each watched folder is an independent project with its own processing settings and generated notebook. Overlapping watched folders are supported, but can present the same files in more than one project. Start with non-overlapping folders if you do not need that arrangement.

Changes are watched while the app is open. Startup and periodic reconciliation scans catch changes made while it was closed. **Library → Sync PDFs** checks local folders on demand. The button in the reMarkable tab performs a separate cloud check.

Select a paper and choose **View in Reader**, double-click its row, or press Enter to load its PDF and notes in Reader. This explicit open clears the previous query, collection/tag and note-type filters, uses All scope, and selects the paper immediately, including papers without annotations. **Open externally** prepares one reading PDF with the paper's PC and reMarkable notes together and opens it in the Windows default PDF viewer. This happens in the background. Notable first checks that the printed pages and their positions match. Different editions, added or reordered tablet pages, and several independently annotated copies need review before they can be combined. Saved notes and their separate histories remain intact.

To keep or share that reading PDF, choose **More → Export annotated PDF…** in Library or Reader. Choose a separate destination. This is a lasting export with the combined annotations; the temporary reading view is not intended as your working original. Continue making PC annotations in your main original and tablet annotations on your tablet, then sync to refresh the combined view.

Handwriting can extend beyond an article's original page edge. Reading views and **Export annotated PDF** add white space around supported margin notes so the whole note stays visible, including handwriting already saved in a PC PDF or an older tablet reading copy. The article stays at its original size, and its text stays searchable. Only the generated reading or export PDF gets the extra space; your original file keeps its existing page size. A wider page can make the article look smaller when your viewer uses **Fit page** or **Fit width**; zoom in for a larger reading size. These reading PDFs use the same temporary cache as combined notes and can be rebuilt when needed.

The combined view belongs to Notable. Your tablet keeps its own editable document and tablet notes. PC annotations appear together with those notes in Notable and its PDF export; this update does not add them to the existing document on the tablet. Sending an exported combined PDF back would create another imported copy, so it is not part of the normal workflow.

The generated Word notebook collects linked PC and tablet notes under one paper. After a paper has been verified and refreshed for this version, its PDF links open the main original at the verified page, so those links do not depend on a temporary reading view. The original may not show newer tablet marks. Older tablet copies keep links to their retained reading PDFs until that refresh succeeds. Use **PDF view** in Notable, or **Export annotated PDF…**, when you want to see all marks on the page.

### Read and search notes

Choose a folder and paper in Reader. **All folders** searches the saved library across watched folders. Search and the available filters can narrow highlighted text, comments, handwriting transcription, annotation color, and note type. Paper title, author, filename, DOI, and page metadata are available through PDFs or All searches rather than being treated as note matches.

In **Reader**, the equal-width **Folder**, **Paper**, and **Collection or tag** dropdowns share one row, with Search immediately below. The dropdown beside **Search** chooses **Notes**, **PDFs**, or **All**. With an empty search, Notes lists saved annotations, PDFs lists one row per PDF document, and All includes both. Browsing documents does not extract or index PDF text. Entering a query filters notes and shows matching PDF pages. **Clear search** (the × beside the field), or Escape while typing there, clears only the query and restores browsing. Changing scope applies immediately to the current query and keeps the current display until replacement results are ready. Folder, paper, collection/tag, and other filters remain in effect.

**Search filters…** contains searchable note fields, note types, and matching rules. **Surrounding printed text** is off by default and after Reset all. Turn it on to include text near annotations; those results show **Match in surrounding text** with the actual matching excerpt. Annotation color searches the original note color and does not change temporary search-mark colors. Paper title, author, filename, DOI, and page metadata are not note fields; use PDFs or All to search the paper itself. Explicit saved-search choices are retained, with removed metadata fields ignored when an older saved search is loaded. Note controls are disabled for PDF-only searches. Spaces mean AND; uppercase AND, OR, NOT, quoted phrases, and parentheses are supported. PDF words must match within the same page. A summary appears only for nondefault options.

The first PDF search extracts text in the background and caches it locally in the active library. Later searches reuse the cache; changed PDFs are checked again. A file changed since its saved scan needs **Sync PDFs** before its contents can be searched. Missing, unreadable, and password-protected sources appear as search issues without removing saved notes. Image-only scans need a searchable text layer; this feature does not run whole-document OCR or send PDFs online.

Results show **Paper**, **Page**, **Type**, and **Match**. By default, each paper's results stay together, with notes before PDF results and pages ordered numerically. Alternating group backgrounds mark paper boundaries. Clicking **Type** sorts actual displayed types, such as Drawing, Highlight, Note, and PDF; clicking again reverses their order. Paper and numeric page break ties. Clicking **Paper** restores paper grouping. Sorting retains the selected result. Column minimum widths reserve space for both sort arrows at the active display scale. Hovering over any result identifies its actual paper title, author/year when available, filename, page, excerpt, and full source location. Separate sources with the same title include filenames in the Paper column.

Matches in the displayed note are highlighted directly in its text. Exactly identical enabled quote/comment/OCR passages share one set of navigation stops while retaining their matched-source identities. **Main search matches** adds labeled excerpts for other fields and printed PDF text. Nearby occurrences share an excerpt; overlapping phrase/word matches count once. Three additional excerpts show initially, with **Show all matches** for longer lists. The shared **Previous match** and **Next match** controls visit individual occurrences, then the next result, across papers in the displayed sort order. They update the selected row and work in either view. The **Main search** counter identifies this navigation separately from Find in PDF. Empty browsing and NOT-only searches still allow result navigation. If a typed note, OCR or metadata match is absent from printed PDF text, PDF view stays on the selected result's page; Note view shows the actual match.

Selecting a PDF document row opens its first page in PDF view; Note view shows its identity. Listing documents does not extract or index their text. Double-click or Enter opens the selected paper externally; **Full page context** loads an image preview on request. Selecting a matching PDF page renders the original page with its tables, columns, and figures intact. Positive search terms and quoted phrases are highlighted in excerpts and the PDF; excluded terms under NOT are not. For example, `tantalum AND PCCT NOT phantom` highlights tantalum and PCCT. A NOT-only search has no positive terms to highlight. Search marks are temporary and never saved to your PDF. **Full page context** supports fitting, panning, zooming, and copying the highlighted page. Opening a matching result in your external viewer navigates to its physical page; temporary search marks stay in Notable. **Export view…** exports matching annotations to Word; PDF document and page results are excluded.

Highlights and typed comments use text and source-page links. Drawings and handwriting also have retained context images. **Actions** offers an editable notebook copy and annotation history for the selected note's actual source. Choose **Note view** for the extracted content and **PDF view** for its document.

For a loaded drawing or handwriting image, choose **Copy image**, right-click the image, or click it and press **Ctrl+C**. The clipboard receives the complete retained image at its original resolution, with transparency flattened onto white. Enlarged images and Full page context offer the same copy actions. Text selection keeps its ordinary Ctrl+C behavior. Image copying currently requires Windows; a busy clipboard reports an error so you can retry.

### Keep and export citation information

In Library or Reader, select a paper or note and choose **Actions → Citation details…**. Review or edit its title, authors, year, journal, volume, issue, page range/article number, DOI, and URL. Separate authors with semicolons; commas can remain inside author names. Initial details reuse local PDF metadata and available Inbox filing information. A filename may supply a provisional title, so check the fields before exporting.

**Look up DOI** optionally sends only the entered DOI to Crossref/DataCite and fills available fields for review. It does not save automatically. **Save citation** retains reviewed details separately from PDF scans and shares them with currently linked paper sources. Rescanning a paper keeps these edits. Saved titles, authors, and DOIs participate in paper searches through PDFs or All scope; they are not annotation-text matches. **Cancel** discards draft edits. **Copy citation** copies the current fields as a plain-text reference, without applying a journal-specific citation style.

Choose **More → Export citations…** to save `.ris` or `.bib` (BibTeX). In Library, the export uses the selected paper, or all papers in the chosen folder when no paper is selected. In Reader, an active query, PDF/All browsing, or a collection/tag or note-type filter exports distinct papers represented by the displayed results. Otherwise the folder/paper filters determine the selection. All folders with no query or additional filters in Notes mode exports the active library. Linked source variants export once. No citation-service request is made during export. Import the resulting file into your reference manager; Zotero documents [RIS and BibTeX imports](https://www.zotero.org/support/kb/importing_standardized_formats).

### Find supplementary information

Select a paper and choose **More → Find supplementary files…**. **Find files** inspects explicit PDF hyperlinks, supplementary DOI relationships, and relevant links on the publisher's article page. This sends the DOI and requests public pages; it does not upload the PDF or notes. Publisher discovery is optional and starts only when you choose Find files.

Select a candidate to inspect its full URL. **Open selected link** opens it in your browser; **Open article** opens the paper's publisher page for a manual check. **Download selected…** saves a reviewed file to a new location and attaches it to the paper. Downloads keep existing files, reject HTML login/article pages masquerading as files, and support PDFs, ZIP archives, Office documents, and selected text/data formats up to 100 MB. Files are not extracted or executed. Closing the review stops a pending download before publishing its completed file.

Opening the dialog first checks the watched folders and sorted library locally. Existing attachments, reviewed parent DOI matches, and similar SI filenames appear as candidates. Select one and choose **Use existing file** to attach it in place. A similar filename is a review hint; it never attaches or merges papers automatically. **Add file…** can select another existing file manually.

Downloads propose the same parent citation, naming style, custom template, and `_SI` marker as the paper sorter, including ZIP and data attachments. The download checks library files for identical bytes before creating another copy; an unchanged attachment from the same URL can be reused immediately. Different files at an occupied destination are never overwritten. Reusing a file keeps its existing name and location.

Confirmed sorter filings with an explicit parent DOI attach SI automatically when exactly one library paper matches. If the parent arrives later, scanning or saving its citation retries the association. Ambiguous editions remain candidates for manual review. SI stays a separate document, and paper linking rejects a merge with its parent even when their title or DOI matches.

For a browser download into your configured **ToSort** Inbox, review and file it normally. If the file does not identify its parent, open the parent paper's supplementary dialog, choose **Add file…**, and select the file in ToSort. Review it again in the Inbox to pick up the parent citation and `_SI` name; filing preserves the attachment at its destination.

Attachments survive restarts and rescans. App-managed moves and watched-folder reconnection update their paths. A rescan repairs a moved PDF when its bytes identify one missing attachment; opening the SI dialog can similarly repair non-PDF attachments within the watched/sorted library. Multiple possible copies remain unresolved for review. Moves outside those folders need **Add file…** at the new location. Publisher access restrictions, dynamic pages, and missing metadata can prevent automatic discovery or download; use your browser and attach the file manually when needed.

Feedback beside a tab's controls describes your last action there and clears when you leave the tab. The footer continues to show background work.

### Understand the page number

**PDF page 3 of 12** means the physical, one-based position inside the PDF. That is the page sent to the viewer. An embedded label can appear separately as **PDF label 233**. A verified printed journal number appears as **Journal p. 233**; an embedded PDF label alone does not prove the journal numbering. Automatic verification of journal page numbering is not implemented.

All external PDF actions use the current Windows default application for `.pdf` files, including Reader **Open externally**, Library **Open externally**, and generated reading PDFs. Change that default in Windows Settings. Older per-library viewer choices no longer override it. Reader opens the original source file; Library can prepare a reading copy with saved notes.

The launcher asks the Windows association API for the effective PDF default each time, rather than reading a potentially stale registry handler. Recognized viewers receive the physical page position. An unrecognized default opens through Windows normally, with an explanation of the page to navigate to. Page jumps depend on the viewer honoring its parameter; every viewer has not been checked live.

### Inspect handwriting and drawing context

The PDF reader shows drawing and handwriting in their full page context. **Note view** also provides a saved close-up of the source page containing its text, figures, and marks. Nearby letters and strokes are grouped into blocks, with surrounding context. Library **Open externally** and **Full page context** use the combined reading view. Supported margin handwriting can expand that view's page boundaries without changing your original PDF.

**Enlarge image** opens the saved close-up. **Full page context** opens the complete physical PDF page, including supported margin context. In either image window:

- **Fit width** or **Fit height** follows window resizing.
- **Ctrl + mouse wheel** zooms around the pointer and chooses manual zoom.
- **Double-click** restores Fit width.
- **Ctrl + double-click** restores the opening zoom and resets both pan axes.
- Scroll vertically, **Ctrl + click-and-drag** to pan, or use **Shift + mouse wheel** horizontally.

Select the watched folder in Library and open **Folder settings** to adjust grouping:

| Setting | When it helps |
| --- | --- |
| **Nearby blocks** | The default; combines nearby letters and lines into readable notes. |
| **Nearby lines** | Uses less vertical joining when separate notes are being combined. |
| **Whole page** | Keeps all drawing marks on a page together, useful for diagrams or arrows joining distant items. |
| Joining distance | Increase it for a split phrase; decrease it when independent notes merge. |
| Context margin | Increase it to show more surrounding material. |

PDFs usually do not identify which separate pen strokes belong to one thought, so automatic grouping makes an informed estimate. Manual crop adjustment, merge/split controls, and per-page overrides are future work.

Optional OCR is off by default and requires Tesseract on `PATH`. It works on isolated ink to reduce confusion with printed text. Its transcription is labeled a suggestion. Visual context remains available without OCR, and handwriting recognition is not guaranteed.

### Work with generated Word notebooks

**Open notebook** opens `Notes on <folder>.generated.docx`. The default **Reading** layout groups selected passages under paper and page headings, with comments shown as **Note:**. **Detailed**, selected in Folder settings, includes more extraction information.

The notebook collects your annotations; it does not write a research synthesis for you. Notes follow the PDF's internal text order, which can still be incorrect in some two-column PDFs.

Use these actions for different purposes:

| Action | Result |
| --- | --- |
| **Open notebook** | Opens the folder's generated Word document. |
| **Save editable copy** | Creates a separate document for your own writing. The app does not regenerate that copy. |
| **Export view** | Writes a separate Word notebook for the currently filtered notes. |
| **Rebuild notebook…** | Regenerates the folder's notebook from saved annotations using current formatting. It does not re-read PDFs. |

**Rebuild notebook…** is in the watched-folder context menu. Its confirmation names the target and explains replacement. Run **Sync PDFs** first if the saved notes or screenshots need refreshing; formatting-only changes can reuse saved notes.

You can open the watched-folder context menu with a right-click, **Shift + F10**, or the keyboard Menu key. **Remove folder…** asks for confirmation and removes that project's saved library and history; PDFs and Word notebooks stay on disk.

If you edit a generated notebook directly, the next replacement preserves the edited document in the adjacent **Notebook backups** folder. Those edits are not merged into the new generated document. An editable copy is the clearer place for ongoing research writing. Old v1 notebooks are not selected as the new generated export target.

If the notebook changes while the app is saving, the app keeps that changed file and holds the export for another attempt. An interruption can also leave a complete previous copy beside it, named like `notes.docx.<identifier>.preserved`. Sometimes the new notebook has saved successfully and only removal of the previous copy failed. The log reports the retained copy's full location. Compare the available documents before deciding which to keep; changes made immediately after a successful save are still treated as your edits on the next update.

If Word locks a generated document, the export stays pending and retries periodically, normally every 30 seconds. Extracted notes remain in the database. Source links depend on the PDF viewer and Word honoring local file/page links; the physical page number is still written in the notebook.

## Bring an existing PC and tablet library together

You do not need to organize every folder before starting. Work on a small, understandable part of your collection, check the result, then move to the next part. Duplicate review combines the app's presentation of a paper; it does not delete disk copies or clean out the tablet automatically.

### 1. Choose one starting area

1. Identify one PC folder containing a few papers you recognize. Leave the remaining folders where they are for now.
2. Make a backup of your research files and Notable's data directory with Notable closed. The data directory does not replace a backup of your original paper folders.
3. Launch the source app and check **Settings → Library & diagnostics** so you know which saved library you are updating.
4. Keep automatic PDF sending and folder creation off while you learn the cleanup workflow. Confirm the saved switches if this is an already configured library.
5. Add the existing PC folder through **Library → Add folder**. Do not put the whole existing collection into Inbox merely to make it searchable. Inbox is for documents you intend to file.
6. Let the local scan finish, inspect a few notes, and open the generated notebook. This gives you a local starting point before adding tablet copies.

### 2. Load the tablet information you want to compare

If you are only organizing PC files, skip this step. **Review library…** can compare local PDFs without a cloud connection.

For tablet comparison, enable reMarkable in Connections, pair it, and choose the limited cloud source and PC destination described in the next section. **Refresh folders** loads the folder catalog; **Sync PDFs** downloads supported PDF sources and annotations. Keep outgoing transfers off until you decide which existing papers should be sent.

Review uses locally saved tablet information. A folder refresh is not the same as downloading each starting PDF and its tablet annotations. That starting PDF is called a **baseline**: the imported document before additional tablet marks are applied. An unmatched item in the saved tablet information does not prove that a paper is absent from the tablet. Recheck after a useful sync when the available information is incomplete.

### 3. Review a few findings

1. Open **Review library…** from Inbox, or **Library actions ▾ → Review library…** in Library.
2. Choose the PC folder to inspect and choose **Check library**. This scan uses local PDFs and saved tablet information; it does not download, upload, delete, move, or link papers.
3. Use the box marked **Search**, beside the magnifying glass, and the finding filter to work on one topic or type of finding. Search checks names, explanations, and file locations. Click a column heading to sort the rows.
4. Select one finding. Read its complete explanation, local paths, and tablet IDs in the scrollable details area. Select copies in the lower list; **Ctrl-click** toggles individual copies and **Shift-click** selects a range. **Link selected copies…** uses only selected sources, including selectable tablet sources. **Delete selected PDFs…**, beside Link, reviews the exact selected paths before moving files to Windows Recycle Bin; saved notes and history remain available. Related findings update using the completed check, without scanning the whole library again. Failed deletions remain listed with an explanation. Select one local PDF to use **Open PDF**; **More…** contains Open containing folder, Copy selected paths, Review again, and Undo last link.
5. Decide whether this is the same paper, a different edition, supplementary material, or an independent item. DOI/title similarity is a suggestion to inspect, not a reason to merge automatically. A matching baseline is stronger evidence, but different annotations still need preservation.

Generated **Notebook backups** and **notes_media** folders, plus the hidden **.git** folder used for source code history, are left out of these findings. The app's private tablet cache and review areas are also excluded. These support folders are not ordinary paper folders to link to the tablet.

Both lists display **Checking library…** while a check runs. The compact action row keeps **Map and sync…** visible when the selected finding needs a folder mapping; its folder picker names the tablet folder being mapped. **Send selected PDF…** also appears only for applicable findings. Review extra PDFs, supplementary-file lists, and filing recovery show loading messages inside their lists while their checks run.

Then choose the action that fits:

| Review action | What it means |
| --- | --- |
| **Link selected copies…** | Confirm that the selected sources belong to one paper. They share a paper entry and notebook heading; actual PDFs, source histories, and independent notes remain. |
| **Keep separate** | Record that this suggested match should stay separate. It does not delete either source or its notes. |
| **Review again** | Bring a previously kept-separate finding back into consideration when you want to reconsider it. |
| **Undo last link…** | Restore the paper memberships from the most recent supported link operation. It does not undo file moves or transfers, because linking did not perform those actions. |
| **Map and sync…** | Choose the corresponding existing PC folder beneath the linked root, then save that mapping and sync. Folder names may differ on PC and tablet. |
| **Send selected PDF…** | Explicitly review sending one existing local PDF to its linked tablet destination. Sending must be enabled in Connections. |

Linking combines the paper's entry, rather than removing duplicate files. Two disk files can remain even though Reader shows one paper. A text annotation appears once only when the app can prove that the same mark was carried over from another saved source. Uncertain overlap and drawings remain preserved. Do not remove a physical PDF just because the app now presents one heading.

Undo is available for the latest new link recorded by this version. Legacy links cannot be undone through this action. If affected paper memberships have changed afterward, the app can refuse an unsafe undo rather than overwrite later work.

### 4. Resolve folder differences gradually

Select the tablet folder and choose its PC counterpart beneath the linked PC root. A tablet folder named `Catalysts` can map to a PC folder named `Catalysis`; you do not need to rename both libraries to match.

The selected-folder **Map and sync…** action saves the mapping and starts a sync. Read the selected source and destination before confirming, because a sync can download changed PDFs and process any separately enabled transfer/folder queues. This is different from **Apply folder changes** in Sync setup, which saves the main source and PC root.

Missing PC destinations appear as **Needs mapping**. If the folder you want is outside the linked PC root, stop and decide whether that root is correct rather than trying to link an unrelated folder. Optional folder mirroring is for new additions; it does not resolve every pre-existing mismatch for you.

### 5. Check the result before the next batch

For each small batch, use this checklist:

- [ ] I checked the explanation and opened the relevant PDFs.
- [ ] I linked only copies whose paper identity I understand, or chose Keep separate.
- [ ] I checked the PC and tablet folder destinations before mapping or sending.
- [ ] I ran the appropriate local or cloud sync and inspected any review/transfer issue.
- [ ] I opened Notes or the generated notebook and checked that independent annotations remain.
- [ ] I left uncertain papers and physical duplicates in place for later review.

A few checked papers are a useful stopping point. You can close the review window and continue another day; confirmed links and review decisions remain saved.

### If a watched PC folder has moved

If you already moved a watched folder in File Explorer, find its old entry in Library, right-click it, and choose **Locate moved folder…**. Select the folder's existing new location and confirm.

This reconnects saved paths while keeping notes, annotation history, and folder settings together. It does not move or delete files. It is preferable to removing the old watched folder and adding a fresh one, because **Remove folder…** removes that project's saved library/history even though its disk files remain.

Choose the actual moved collection, not a similarly named replacement. A relocation can also affect linked roots and queued transfers. Transfers whose destination needs renewed confirmation remain for review; check their explanation before retrying. Use the normal folder mapping tools when you are linking a tablet folder, rather than relocating a watched folder that has not moved.

## Set up optional reMarkable PDF syncing

The connection is direct between Notable and reMarkable's cloud. It does not require OneDrive integration, a USB cable, or developer mode. It handles imported PDFs and their tablet annotations; native notebooks and EPUBs are skipped.

### Pair and choose a limited scope

1. Open **Settings → Connections**, enable cloud services, and choose **Save preferences**. The reMarkable tab becomes visible.
2. Choose **Connect reMarkable…**, open the pairing page, and sign in there. Generate the eight-character, single-use code and enter it in Notable. The app asks for that code, not your account password.
3. In **Sync setup**, choose the exact **Cloud source** and an existing **PC destination**. For example, tablet `Literature` can correspond directly to `C:\Literature`. Only that source and its descendants are in scope.
4. Choose **Apply folder changes** to save the source/root draft. Setup can collapse to a source-to-destination summary; **Edit setup** opens it again.
5. Choose **Sync PDFs** for an on-demand check. If root/source edits are pending, the button becomes **Apply & sync PDFs**, which saves them before checking.

The default source-name search looks for `Literature`. Choose the exact folder after connecting if that name is ambiguous. A blank source does not silently select the entire tablet library. Pairing credentials are protected for the current Windows account.

**Automatic checks (every 5 min)** controls PDF-download checks while the app is open. That checkbox applies immediately; it is separate from the source/root draft and from Settings' permission switches. Tablet marks appear after the tablet uploads them over Wi-Fi.

### Know what each cloud action can do

| Action or switch | Consequence |
| --- | --- |
| **Refresh folders** | Reads the cloud folder catalog without downloading PDFs. If folder mirroring is enabled, it can create PC counterparts or queue tablet folders. |
| **Sync PDFs** | Downloads changed supported PDFs/annotations, retries eligible review items, and processes enabled outgoing PDF/folder queues. |
| **Send newly filed PDFs in linked folders** | Allows newly filed PDFs within the linked PC root to enter the outgoing queue. Existing papers are not bulk uploaded merely by launching the app. |
| **Send selected PDF…** | Queues an explicitly chosen existing PDF, subject to sending permission and destination checks. |
| PC-to-tablet folder creation | Allows new PC folders beneath the linked root to receive tablet counterparts. Creating a folder does not upload all its existing papers. |
| Tablet-to-PC folder creation | Allows new tablet folders beneath the selected source to receive PC counterparts. |
| Master Connections switch off | Pauses cloud activity and hides the tab, retaining saved pairing, routes, PDFs, and notes. |
| **Disconnect** | Removes the active pairing; downloaded PDFs and notes remain. Reconnect needs a new pairing code. |

Folder creation switches are independent. Their first check records the folders already present, so old unmatched folders still need review. New nested folders are handled parent-first. Invalid names, collisions, missing parents, and ambiguous routes remain for review. The creation workflow does not propagate ordinary user-folder renames, moves, or deletions across both libraries.

Matching descendant paths route downloads to existing PC folders. Explicit mappings override that path matching, and use stable tablet folder IDs. **Unlink folder…** asks for confirmation. Unlinking the main source clears its PC destination and disables automatic checks; choosing a destination again resumes routing. Unlinking a descendant's explicit override returns it to source-path matching. Existing PDFs and notes remain in both cases.

### Handle downloads needing attention

Unmatched or unsupported conversions appear in **PDFs needing attention**. Their retained material is under `<library data directory>/reMarkable Review/<document ID>/`. Select an item to read its full reason, proposed destination, and retained PDF path. **Open PDF** opens a retained review PDF when one exists; **Copy details** copies the explanation and paths.

A folder mapping is usually the better way to direct future downloads. The app's private review/cache areas are excluded from note scanning, even if a watched parent contains them. If you manually copy a reviewed PDF into a normal watched folder, it becomes an independently analyzed local source; that does not create a reliable route for future tablet updates.

Repeated unchanged conversion failures are held for review instead of being reconverted every five minutes. A manual sync, changed routing, a renderer update, or a resolved local conflict can permit another attempt.

### Review outgoing transfers

Open **Transfer queue…** to see uploads and folder-creation work, including **Needs mapping**, review, retryable failures, completed transfers, and cancelled entries. Local filing completes independently of an offline cloud service.

Select a transfer to see its complete PC path, status, explanation, and any recorded destination paths in the details area. You can scroll and copy these details even after a transfer is sent or cancelled.

**Retry transfers** processes currently eligible work. **Retry selected…** asks you to confirm the chosen unfinished job's current file and linked destination. If the PDF changed after it was queued, this accepts its current contents. If the linked root/source or destination changed, it accepts the new destination. A changed PDF after an ambiguous earlier send can need a new additive transfer while retaining the earlier cloud item.

**Cancel selected transfer** cancels future work on the selected unfinished transfer. It does not delete the local file or folder, and it does not delete a cloud item that may already have been committed before cancellation. A completed transfer cannot be rolled back by queue cancellation.

Saved transfer IDs support retries after an uncertain cloud response. Confirmed links are reused when the app knows how the copies were related; uncertain matches remain for review. These protections are covered by offline tests, but the full workflow still needs a small real-device pilot before taking over an established watcher.

## Understand originals, app copies, and storage

Several files can represent one paper for different reasons. A link in Notable records their relationship; it does not erase those files.

| Stored material | Purpose and retention |
| --- | --- |
| Your original PC PDF | Your research file, possibly containing existing Acrobat/viewer annotations. Note extraction reads it without editing it. |
| Retained tablet baseline PDF | The unchanged imported PDF needed to reconstruct tablet annotations. Identical baselines share stored content using a digital fingerprint computed from the file's bytes. A baseline can still duplicate a user-owned PC original. |
| Tablet layers and source records | Tablet marks, page ordering, and reconstruction details kept separately from the baseline. Small records, called manifests in the code, identify the saved source files. |
| Temporary combined reading PDF | Created privately when you open a paper. It includes the verified PC and tablet annotations. It can be removed and rebuilt from the saved sources without losing notes. The normal budget is 128 MB. |
| Exported annotated PDF | A lasting combined copy saved only when you choose Export annotated PDF. You choose its location and whether to replace a previous export. |
| Database notes and history | Extracted note text, drawing context, saved processing state, paper links, and annotation history in `library.sqlite3`. |
| Generated Word notebook | A replaceable export beside its watched folder. Use an editable copy for personal writing. |
| Notebook backups | Preserved externally edited generated notebooks before replacement. |
| Temporary cloud download cache | Downloaded pieces that can be fetched again, with a default 64 MB budget. Retained annotation sources are stored elsewhere. |

New successful syncs do not put a `[reMarkable <ID>]` reading PDF beside every original. A verified existing main paper is reused. If a tablet paper has no PC counterpart, Notable saves its original PDF under its ordinary name. An occupied name or uncertain match goes to review. Your main original remains the place for PC annotations; Notable does not rewrite it with incoming tablet notes. Cloud renames or moves do not automatically move your originals, and cloud deletion keeps the saved sources and notes.

The 64 MB download cache and 128 MB reading cache are **not whole-library limits**. Originals, retained baselines, tablet layers, older sources, note history and explicit exports are kept separately. A retained baseline can still duplicate your editable PC original: this backup lets Notable reconstruct tablet notes even if the PC file is edited or goes missing. Identical tablet baselines share one private copy. This update removes the need for a permanent extra *annotated reading PDF* for each paper; it does not promise that all backup storage disappears.

Only unchanged, recognizable app-generated reading views are cleared from the temporary cache. A PDF you edited there is preserved. The currently requested PDF can exceed the budget on its own, and open files or files needing review can also keep the folder above its normal budget. This protects your work, but a temporary view should still be exported before you rely on it as a lasting document.

### Review existing extra reading copies

After a successful sync and notebook refresh, open **Library → More → Review extra PDFs…**. This lists the old `[reMarkable <ID>]` copies and explains which ones are ready for removal. Nothing is removed merely by opening the list or upgrading the app.

A copy is ready only when its saved tablet source is verified, its notes and histories have moved to the new private records, its main original is available, and current generated Word notebooks no longer link to the old copy. Edited copies, unverified tablet revisions and unresolved links remain blocked. An older reading copy can be ready when its exact tablet marks are still saved and came from the same imported original PDF. Read each explanation; you can work through a few papers at a time.

Select ready copies, read the warning about old links, and choose **Remove reviewed copies**. The app checks the selected files again before removing them. This removes only the verified old reading PDFs. It keeps your main originals, tablet source files, saved notes and histories. Links in exported notebooks, personal documents or old notebook backups may still point to the removed file; Notable cannot find every such document. Keep any old copy whose external links you still need.

Older image-bearing annotation history also remains saved even though new highlights and typed notes use text instead of screenshots. Changing that preview policy does not immediately shrink an existing database.

New tablet source storage separates shared baselines and annotation layers rather than repeating the baseline inside every raw archive. Older `.rmdoc` archives remain readable and untouched. Offline reconstruction and explicit portable `.rmdoc` export are supported by the source-storage code; these are not additional everyday buttons in the main interface.

### Back up the right things

Close Notable, then back up:

1. Your actual paper folders, personal Word documents, and any adjacent **Notebook backups** folders.
2. The **complete active data directory**, including `library.sqlite3`, private `remarkable/` material, and retained `reMarkable Review/` contents.

Copying only the database does not include all retained tablet source files. Copying only generated notebooks does not include saved annotation history. Windows-protected pairing and Gemini credentials may need to be entered again under a different Windows account.

## Troubleshooting

### The wrong folders or connection appeared

Check **Settings → Library & diagnostics**. Source and older installed versions can use separate data directories. Use the source launch commands above and check any explicit `PDF_NOTES_DATA_DIR`. Diagnostics does not merge two libraries. Do not point a temporary test run at your normal saved library.

### A watched folder is unavailable

Reconnect an offline drive first. If you already moved the folder, use **Locate moved folder…** on its existing Library entry. Saved notes remain readable while a source is unavailable. Removing the watched-folder entry is a different, explicit action that removes its saved project/history.

### An Inbox document stays Waiting

Let the download complete, then refresh again after it stops changing. The file must be supported and directly inside the incoming folder. Files such as `.crdownload`, Office lock files, and unsupported documents are ignored. If the file changed during identification, review its current version again.

### A PDF failed to read or its notes look wrong

Read the full error in **View sync details**. Restore a missing source or close an application that is holding it, then use **Library → Sync PDFs**. A failed scan does not replace the last successful saved notes.

Inspect **PDF view** to see the combined annotations. Flattened marks are ordinary page content and cannot reliably be separated from the printed page; different flattened versions need review. A highlight without extractable text keeps a source link and a review warning. For split/merged handwriting, adjust Folder settings and sync, then check a small sample before applying the approach broadly.

### The generated notebook did not update

Close it in Word and check Library's log. Locked or failed exports remain pending. **Rebuild notebook…** uses saved notes and current formatting; **Sync PDFs** is needed when extraction data should change. Check **Notebook backups** if you had edited the generated file directly.

### The tablet paper is missing or has Needs mapping

Confirm the Connections master switch, pairing, exact cloud source, available PC root, and selected folder mapping. Make sure the tablet has uploaded its changes over Wi-Fi. Refreshing folders alone does not download PDF annotations. Use **Sync PDFs**, then read the item's complete review explanation.

Missing or conflicting destinations do not authorize an unrelated location. Resolve the folder mapping, then retry. A local edit or unsupported scene can require manual review even when the route is correct.

A PDF update can leave a file beside the managed PDF named like `paper.pdf.<identifier>.preserved`. It contains the previous complete PDF. This can happen after an interruption, or after the new PDF was saved successfully but the previous copy could not be cleaned up. A recovery notice therefore does not always mean the new PDF failed to save.

Library's summary shows a count of **previous PDF copies retained for recovery**. Choose the footer's **View sync details** to open the log and read their complete saved paths. That clue stays available on later launches while the retained paths remain recorded. Open the containing folder, check the current PDF and retained copy, and compare them before deciding how to restore or organize them. The app does not blindly overwrite a retained previous copy or choose one for you.

### An upload is held for review

Open **Transfer queue…** and inspect the selected job. Restore a missing source or resolve **Needs mapping** first. If the PDF or destination changed, confirm the current contents/location through **Retry selected…**. Use **Cancel selected transfer** when you no longer want that queued intent; cancellation is not remote deletion.

### Save preferences failed

The dialog stays open with the error, and the previous saved settings/key remain. Correct the draft or cancel it. A key marked for removal can still be kept using Undo removal. If the message instead says preferences were saved but automatic checks could not restart, the save succeeded; use manual Inbox refresh and investigate that separate background error.

### Open PDF opens at the wrong page

The page shown by Notable is the physical file position, which can differ from printed journal numbering. Notable uses your current Windows PDF default. Some viewers ignore page parameters; navigate to the displayed physical page manually when necessary.

## Reference and development

### Data locations and migration

- Source default: `.local-data/` beside the source entry point.
- Packaged app default: `%LOCALAPPDATA%/PDF Note Organizer/`.
- Explicit override: `PDF_NOTES_DATA_DIR`.
- The project's `.local-data` skips legacy import by default. `PDF_NOTES_SKIP_LEGACY_IMPORT=1` disables it elsewhere; an explicit `0` permits it.
- Installed/custom libraries can import watched folder paths from nearby `notes_watcher.db` files on first migration. Old annotation hashes are not trusted; PDFs are re-extracted into the current library. The old databases and notebooks are left untouched.
- Local processing defaults in Settings apply to folders added later. Existing folders keep their own Folder settings.

Closing stops watchers and cancels extraction at supported page/annotation boundaries, retaining completed saved work. Automatic local/cloud tracking runs only while the app is open and catches up during later checks. There is no separate Windows service, tray mode, or automatic startup feature yet.

### reMarkable compatibility

The cloud protocol is unofficial and follows community-documented v3/v4 endpoints from the [reMarkable MCP client](https://github.com/SamMorrowDrums/remarkable-mcp). Annotation parsing uses [rmscene](https://github.com/ricklupton/rmscene). Rendering uses calibrated device coordinates and simplified brush widths rather than the tablet's native renderer.

Supported v6 scenes become highlight, ink, and text annotations in a separate reading PDF. Snap-selected quotations come from tablet scene text; freehand highlighter marks remain drawings. Legacy indexed colors use their palette rather than black placeholder values, and highlight appearances are translucent. Selected quotations and actual typed comments remain distinct.

Renderer revisions can refresh managed PDFs even when their cloud hash is unchanged. Ordinary supported margin writing can extend the converted page canvas. Rotated/cropped pages needing unsupported margins, unknown blocks/coordinate grids, legacy highlight JSON, and unsupported text-anchored strokes stay in review with retained source data. Firmware and every pen workflow still require broader real-device validation; synthetic tests are not a guarantee of live compatibility.

### Viewer and interface reference

Browsers receive encoded file URLs with `#page=`. Acrobat/Reader receive `/A page=`, and SumatraPDF receives `-page` with instance reuse. The adapters follow [Adobe's PDF parameter documentation](https://pdfobject.com/pdf/pdf_open_parameters_acro8.pdf) and [SumatraPDF's command-line options](https://www.sumatrapdfreader.org/docs/Command-line-arguments).

The interface uses charcoal panels and blue accents. Blue usually marks the main action or selection. Muted controls are unavailable until their requirements are met; hover help explains many disabled actions. An ellipsis generally means a further choice or confirmation is needed.

Action buttons and menus use locally bundled [Lucide icons](https://lucide.dev/). Icon-only utilities have hover help; workflow buttons combine icons and text. Icons scale with Tk display scaling and include disabled variants. Original SVGs, PNG renders, the pinned upstream revision, and license notices are under `note_organizer/assets/icons/`; no network request is needed to display them. The Windows release includes these assets, the app icon, PDF.js, and both guides.

### Tests and implementation

#### How notes, PDF search, and reMarkable sync work

1. **Notes live in a local SQLite database.** `library.sqlite3` stores extracted highlight text, comments, physical page locations, drawing previews, paper relationships, settings, and annotation history. Identical note images can share storage rather than being saved repeatedly. Generated Word notebooks are exports of that saved information; they are not the primary note database. Source PDFs and managed tablet source files remain separate from the generated notebooks.
2. **PDF search builds and reuses a local page-text index.** A background PDF worker extracts each page's text. SQLite's full-text index helps find candidate pages, and the app's matching rules check those pages and identify individual occurrences. Cached text is refreshed when the PDF or extraction version changes. Image-only scans need a searchable text layer. **Find in PDF** instead searches the document already loaded in the embedded PDF.js viewer, making navigation within that open PDF especially quick. Ordinary note and PDF searches do not upload the documents or query an online search service.
3. **reMarkable sync uses your cloud account and selected folder mappings.** Pairing exchanges a one-time code for a token protected by your Windows account. The app checks the chosen cloud scope, detects changed document revisions, downloads the original PDF and tablet annotation layers, and prepares local annotated reading views while retaining source material. Unresolved folder routes or conflicting versions go to review. Optional automatic checks run while Notable is open; explicit sending creates new tablet documents rather than continuously merging PC edits into existing tablet documents. PDF sending and folder creation require their separate connection settings.

#### Verification and release tooling

The illustrated manual is generated from [task definitions](documentation/manual_tasks.py) and current offline UI captures. To regenerate the guides, run `scripts/capture_manual.py` through `tools/run_ui_tests.py`, then run `scripts/build_guides.py` with ReportLab/Pillow and `scripts/verify_guides.py` with PyMuPDF/Pillow and Poppler. The verifier removes fixture paths from embedded screenshot pixels, renders every page, and checks for clipped text. Documentation dependencies are authoring tools rather than app runtime requirements.

Run the suite from the project folder:

```powershell
.\.venv\Scripts\python.exe tools/run_ui_tests.py tools/run_test_batches.py
```

The suite uses synthetic documents and temporary libraries, with cloud clients mocked. It covers PDF extraction/notebooks, document naming and Office exclusions, incomplete downloads, filing collisions/recovery, key removal and atomic preferences, paper links and independent history, source reconstruction, cloud transfer retries and changed destinations, folder scope, moved-folder recovery, and interface behavior.

On Windows, use the launcher above for the full suite. It runs GUI tests on a separate inactive desktop so they do not display windows or take keyboard focus from your work. Direct discovery bypasses that isolation and is rejected by screenshot tests. Individual native checks use the same launcher:

```powershell
.\.venv\Scripts\python.exe tools/run_ui_tests.py tests/reader_webview_regression.py
.\.venv\Scripts\python.exe tools/run_ui_tests.py tests/reader_app_regression.py
.\.venv\Scripts\python.exe tools/run_ui_tests.py tools/check_reader_focus.py
.\.venv\Scripts\python.exe tools/run_ui_tests.py tools/check_reader_startup.py
```

The batch runner releases native Tk/GDI resources between groups, avoiding bitmap exhaustion in very long single-process runs. The opt-in native checks require Windows WebView2 and local loopback access. They generate disposable documents, exercise the real embedded reader and cleanly close its process, including cancellation during startup. The focus check reproduces the native/Tk disagreement before checking the repair; its inactive desktop has no foreground window, so the foreground guard is separately tested with simulated handles. These checks do not switch the user's active desktop.

For disposable visual examples:

```powershell
.\.venv\Scripts\python.exe -m tests.qa_combined
.\.venv\Scripts\python.exe -m tests.qa_app
```

The combined preview uses `tmp/qa/combined`; the PDF preview example remains available. A small real pilot should include a clean PDF, a viewer-annotated PDF, and a tablet-annotated PDF before replacing an established workflow. [COMBINED_APP_PLAN.md](COMBINED_APP_PLAN.md) records scope and validation work. [AUDIT.md](AUDIT.md), [TOOLTIP_AUDIT.md](TOOLTIP_AUDIT.md), and [ICON_AUDIT.md](ICON_AUDIT.md) retain more technical review notes.

Implementation is split among extraction, SQLite database storage, Word export, a background service that coordinates changes one at a time, and the Tk interface. Desktop extraction, tablet conversion, and full-page rendering share a PDF worker in a separate Python process. The reader loads small saved-library views and performs searches separately from the window's controls. Word exports use a temporary file followed by replacement. Logs record processing times and unusually delayed interface updates for diagnosis.

Public source should be kept separate from private libraries, documents, logs, credentials, and built executables. Do not share `.local-data`, custom private data directories, or key files as part of the source project.

### Features still under consideration

Manual crop and stroke merge/split controls, per-page settings, topic tags and custom color categories, richer personal synthesis editing, citation-manager integration, source-linked summaries, additional exports, and tray/startup operation remain future work. Current grouping and PDF reading order still need checking against the documents and annotation styles you use.
