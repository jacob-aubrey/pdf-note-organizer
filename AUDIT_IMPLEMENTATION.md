# Notable 2.5.0 audit implementation

This report covers the implementation pass requested after the application audit, including correctness, performance, storage, maintenance, interface consistency and usability. Development remains Python/VS Code; packaging is explicitly deferred at the user's request. Work and destructive-operation tests use disposable synthetic libraries. The normal research library, original papers, preferences and live cloud account were not used as write targets.

## Recommendation coverage

| Audit area | Implemented result |
| --- | --- |
| Conflicting citations on linked sources | Deterministic lookup and explicit conflict review; one reviewed record is applied to linked sources. Conflicting records cannot silently choose an export citation. Linking snapshots citations; undo protects later edits. |
| Supplement association costs and long write locks | Indexed normalized DOI and content digests, batch reconciliation, filesystem hashing outside write transactions and one rename catalog per batch. Catalog hashes are limited by pending file sizes. |
| Duplicate images and database free space | Lossless content-addressed binary images shared by current notes/history. Explicit compaction migrates existing images and vacuums unused pages after verified backup. Public note/history payloads retain their original image representation. |
| Recoverability and storage visibility | Storage dashboard, hash-verified SQLite/private-source/original-file backups, independent restore with rebased paths, paused integrations on recovery, integrity and foreign-key checks. Existing destinations are preserved. |
| Raw tablet recovery archive duplication | Byte-for-byte archive member review against retained immutable baseline/layers, migration eligibility, change guards and backup before reviewed deletion. Unknown or nonidentical archives stay. |
| Reading cache hit overhead | Direct cache-key lookup; throttled bounded maintenance; hashing only lookup candidates or eviction victims; Windows guarded deletion preserves edited/replaced files. |
| PDF queue latency and stale work | One prioritized native process, cooperative per-job cancellation, preview priority and 12-page text batches. File identity and digest checks guard the complete search extraction. |
| Search speed while preserving semantics | Local FTS5 trigram candidates plus the existing Boolean/substring matcher. Short/negative queries conservatively fall back. Text cache avoids a third JSON copy and keeps extraction version guards. |
| History and relationship lookup costs | History, DOI, supplement digest, project/content and attachment lookup indexes. Logical paper sources and histories remain separate. |
| Citation Save/Cancel race | Guarded Cancel, Escape and window close while saving; recoverable error state. Maintenance and label saves use equivalent close protection. |
| Simpler navigation and visible actions | Direct Inbox setup, named Actions and Folder actions menus, consistent tooltips, explicit recovery actions, status and selection preservation. Inbox secondary actions grouped to fit the minimum window. |
| Preview layout and processing complexity | Text and drawing images share one scrolling preview, with the image directly below the last paragraph. Preview action buttons wrap according to their measured widths and return to one row as space permits. Advanced processing controls collapsed by default with a grouping illustration. |
| Graphic consistency | Shared darker primary blue, distinct disabled icon state, consistent button labels, spacing, menus and local timestamps. Existing icon assets reused. |
| Keyboard and reading accessibility | Workspace/search/settings/research shortcuts, keyboard-operable menus and browser reading snapshots with semantic headings, text search, live result counts, source links, zoom and print. |
| Research organization functions | Persistent paper tags and collections, combined note/PDF label filtering, saved searches and existing supplement attachment opening. Labels span linked copies. |
| Optional AI maintenance | Configurable Gemini model and metadata-only connection test; model changes invalidate old naming proposals. Existing saved setups preserve compatibility; new default updated. |
| Dependency updates | PyMuPDF 1.28.2 and Pillow 12.3.0, tested independently and in the regression suite. Direct pins plus a complete Windows runtime lock with wheel integrity hashes. |
| Ghost code and module size | Unused imports/locals removed; undefined names checked. Workspace layouts and new storage, indexing, research, accessibility and cleanup functions isolated in focused modules. Legacy source remains an intentional rollback reference. |
| Stale executable and development reliability | Source-only Windows CI checks compilation and regression tests using hashed dependencies. README identifies the old executable as outdated. Packaging is deferred by user instruction; newly generated executable/build files and added packaging automation were removed. |

## Maintenance behavior

New scans use shared image storage. Existing image-bearing records remain readable before compaction. Compaction is explicit because it performs a substantial database rewrite; it preserves all revisions and first produces a verified full backup. The amount reclaimed depends on the library's duplicate images and free pages.

Backups contain available registered originals and attachments plus retained private recovery data. Missing external originals cannot be recovered from a backup that never contained them. Settings can include locally encrypted credentials; encryption may be tied to the Windows user/device. A restored library starts remote integrations and Inbox watching paused, and uses recovered files rather than pointing back to the originals. The original active library remains independent.

Existing extra PDFs and raw tablet archives require reviewed cleanup. No bulk deletion of personal research, legacy source, old executable or saved database is part of the upgrade. Approximately 101 MB of temporary dependency-download staging and the new packaging outputs were removed. Generated PDFs and database maintenance are separate from original research files.

## Validation and remaining external checks

The new regression cases exercise image/history fidelity, verified compaction, independent backup recovery, corrupt/unsafe archives, canonical citation selection and undo, query parity including Unicode/negative/short terms, labels, hashing outside write transactions, escaped accessible HTML, queue priority/cancellation and raw-archive cleanup.

The complete application suite passed **851 tests in 557.872 seconds**, covering rendering, margin geometry, exports, service queues, cloud and filing recovery, paper links, storage, search, tooltips, display scaling and UI responsiveness. After the final automatic-sync label shortening, all **19 interface and screen-geometry tests** passed. Dependency checks, unused/undefined-name lint, compilation and whitespace checks passed. The native synthetic demo confirmed that text-only notes fill their preview pane. The earlier full run exposed an outdated Inbox test fixture; it was corrected before the successful complete run. Packaging was stopped/deferred by user instruction, and its generated outputs and added automation were removed.

Runtime packages passed the known-vulnerability audit at implementation time. This is a point-in-time dependency result, not a guarantee about unknown vulnerabilities. Current package/model information was checked against [PyMuPDF on PyPI](https://pypi.org/project/pymupdf/), [Pillow on PyPI](https://pypi.org/project/pillow/) and [Google's Gemini model documentation](https://ai.google.dev/gemini-api/docs/models). CI uses the current documented major versions of GitHub's [checkout](https://github.com/actions/checkout) and [Python setup](https://github.com/actions/setup-python) actions.

Live Gemini generation, real cloud transfers/tablet firmware, multiple physical monitors and full native screen-reader operation were not exercised. The browser reading view improves access to results; the full Tk shell is not certified for UI Automation or NVDA. Unproven PDF editions, geometry and tablet formats continue to require review. Existing physical-device pilot checks in AUDIT.md remain applicable.

## 2026-10-12 preview layout follow-up

The user's layout feedback replaces the split text/image pane with an inline drawing image directly after the note text. One scrollbar covers both; the image fits the available width without clipping tall handwriting. Preview actions now use a reusable wrapping toolbar, returning to one row when space permits. Text selection/copy, original-resolution image copying, enlargement, asynchronous loading and stale-preview protection remain supported. All 45 affected preview, research-interface, responsiveness, screen-geometry and theme tests passed in 53.022 seconds; lint and whitespace checks passed. This remains a Python source update with no executable packaging.
