# Loading and progress indicator audit

Audit date: October 16, 2026. The initial implementation now covers PDF search/indexing, local PDF checks, pending notebook exports, and batched search-result display. These use completed-item bars and compact counts (for example, `143 / 520 PDFs`), without percentages or a redundant remaining count. Current filenames appear on hover. Other recommendations below remain an assessment.

## Recommendation

Use measured progress for finite batches: PDFs searched/indexed, files checked, documents filed, and exports processed. Keep the display compact: completed / total, with the current filename on hover. Keep an activity indicator for work without a trustworthy denominator, such as a network request or initial folder discovery.

PDF indexing now reports one completed item per processed PDF, with its total calculated after scope filtering and source deduplication. Cached PDFs and files that report issues are accounted for; existing warnings retain the failure details. Page extraction also returns batches of up to 12 pages, which could support a secondary page counter after exposing the page total.

The footer now uses an item bar when the service supplies both a completed count and a total, and switches to activity animation for unknown-duration phases. Local PDF sync discovers one inventory before processing it; notebooks advance after each export attempt. This is work completed, rather than a claim that all files succeeded or an estimate of time remaining.

## Inventory

| Surface / operation | Current indication | Honest progress available | Work involved / recommendation |
| --- | --- | --- | --- |
| Main PDF/All search and first-time text indexing | Compact item bar and completed / total PDFs | Completed PDFs out of the deduplicated, filtered batch | Implemented: latest worker snapshot is displayed on Tk's thread; superseded searches cannot overwrite new progress. |
| Text extraction inside a large PDF | Covered by the search indicator | Pages extracted out of the PDF's actual page count | Moderate: expose page totals and report existing extraction batches. Useful alongside the file counter. |
| Notes-only database search | Same animated search bar | No reliable fraction while the database query executes | Keep activity text. The later result-enrichment and display phases can count records if they are slow. |
| Inserting Reader results | Item bar during multi-batch insertion | Rows displayed out of returned results | Implemented using the existing batch position and final row count. |
| Startup library snapshot | “Loading saved library…” and footer activity bar | Separate loading, assembling, and displaying phases; no existing database-query fraction | Keep activity during the query; add counts to a slow assembly/display phase if needed. |
| Local folder/PDF sync | Discovery activity, then completed / total checks with an item bar | Files discovered, then checks completed out of that inventory | Implemented with one discovery walk per folder; failed checks remain in the existing issue summary. |
| Extracting saved PDF notes | “Reading PDF” / “Updating saved notes,” current filename | PDF pages, then notes/assets saved | Larger: extraction runs in a separate process and needs progress messages across that boundary. Worth doing for large documents. |
| Embedded PDF opening | “Preparing PDF…,” “Starting embedded PDF reader…,” and “Opening PDF…” | PDF.js can expose bytes loaded/total; rendering remains a separate phase | Moderate: report PDF.js loading progress and switch to rendering/preparation status where byte progress no longer applies. Do not call bytes loaded “pages ready.” |
| Find in PDF | “Searching…” followed by the match counter | Pages searched during the initial search | Moderate: PDF.js events/adapter work. Lower priority because navigation is already fast after extraction. |
| Drawing and full-page previews | Loading/preparation text | Mostly single rendering operations with no current intermediate callbacks | Keep activity text; page or image counts help only for a genuine batch. |
| External/combined PDF preparation and annotated export | Preparation/export status text | Separate source-checking, combining, and writing phases; source/page counts with new callbacks | Moderate to larger. Prefer named phases first, then measured work within each phase. |
| Word notebooks and selected-note export | Pending notebook exports now use an item bar; selected-note export retains activity | Notebook attempts completed out of the pending set | Notebook batch implemented. Within-notebook/selected-note progress still needs exporter callbacks. |
| Citation exports and accessible reading view | Preparation/export status text | Selected papers, notes, or images processed | Small to moderate: known lists, currently no progress callback. |
| Inbox discovery, identification, and filing | Task-specific text and disabled action controls | Documents discovered/processed; bytes copied for filing | Moderate for batch counts. Single-document online identification should retain activity status. |
| reMarkable listing, sync, and transfers | Footer animation and detailed service messages | Documents completed after listing; bytes transferred if the cloud API exposes totals | Moderate to larger. Listing and network waits require activity status; subsequent finite batches can have counts. |
| Library reconciliation / duplicate review | Checking/loading text | Source files inspected out of the collected set | Moderate: enumeration and inspection need progress callbacks. Worth doing for large libraries. |
| Backup, verification, restore, compaction, and cleanup | Task-specific text with controls disabled | Backup/restore file lists and byte sizes; verification entries; explicit cleanup plans | Moderate to larger. Report each phase separately. SQLite snapshot/compaction steps do not currently expose a useful fraction. High-value for long operations. |
| Supplement discovery, attachment loading, and downloads | Checking/downloading text | Downloaded bytes if a valid Content-Length is provided; attachment counts | Small to moderate for download byte progress. Unknown-length downloads and discovery keep activity status. |
| Citation lookup, update checks, and connection tests | Checking/loading text | No trustworthy fraction for a single remote request | Keep activity text. A percentage would imply information the app does not have. |
| Tags, saved searches, history, preferences, and library diagnostics | Short loading/saving/checking text | Usually single database operations | Keep lightweight status; extra bars are likely visual noise unless an operation proves slow. |
| Safe shutdown | Centered modal, animated indicator, named remaining task and file where available | Active cleanup phases; no reliable fraction of shutdown time | Keep task/phase reporting. “Three of five workers stopped” would be a count, not a meaningful estimate of time remaining. |

## Implementation order

1. Completed: PDF search/indexing, service snapshots with completed/total counts, local sync, pending notebook batches, and batched result display.
2. Future: counters within large exports, backups/restores, and reconciliation.
3. Add per-page or byte progress where it materially helps with one unusually large document or transfer.
4. Retain activity indicators for unknown-duration requests and short database operations.

## Guardrails

- Counts describe work completed, not time elapsed. One large PDF may take longer than many small PDFs.
- Do not repeatedly count the same files with extra directory walks. Build and process a single snapshot when a total is needed.
- A file that fails or is skipped is accounted for explicitly, so the bar can finish without implying successful indexing.
- Ignore progress from cancelled or superseded searches. UI updates must remain on Tk's thread and be throttled so reporting does not slow the work.
- Use a short display delay for brief operations to avoid flicker.
- Avoid a global “total progress” percentage across unrelated stages with very different costs.

## Code examined

- `ui.py`, `workspace_layouts.py`: search/footer indicators, batched result display, PDF previews, exports, and startup.
- `research_search.py`, `pdf_worker.py`: selected PDF lists, indexing cache, and page extraction batches.
- `service.py`, `remarkable_sync.py`: file discovery, extraction, notebooks, cloud work, and activity snapshots.
- `pdf_reader.py`, `assets/reader/reader.mjs`, `assets/reader/index.html`: native reader startup, PDF loading, and local Find.
- `inbox.py`, `workflow_ui.py`: discovery, document identification, filing, reconciliation, and background jobs.
- `maintenance.py`, `maintenance_ui.py`, `archive_ui.py`, `storage_ui.py`: backup, verification, restore, compaction, and cleanup.
- `research_ui.py`, `research_tools.py`, `supplements.py`, `accessible_reader.py`, `dialogs.py`, `support_ui.py`: research actions, downloads, preferences, diagnostics, and update checks.
- `shutdown.py`: safe-close progress and input blocking.
