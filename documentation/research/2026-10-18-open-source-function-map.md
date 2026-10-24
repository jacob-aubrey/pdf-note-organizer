# Notable: function-by-function open-source comparison

Reviewed October 18, 2026, against the current README, dependency list, tests inventory, and selected implementation modules. This expands the earlier ecosystem survey around the user's actual workflow.

## Scope and reading guide

“Every function” here means every documented user-facing capability family and its supporting platform/storage functions, decomposed into the 80 rows below. It does not mean every Python helper, every button, or a formal audit of all source statements. Future requirements are marked separately from delivered behavior. The selected local modules and external source/manifests were inspected; most alternative projects were evaluated through official documentation and repository descriptions. No alternative was installed, benchmarked, or connected to a private account.

An existing app with a similar feature is not necessarily a reusable library. A reference pattern is not a drop-in replacement. The proposed action is one of: **keep existing reuse**, **delegate/integrate**, **benchmark an adapter**, **learn from a pattern**, or **retain small custom coordination**. Lack of an exact match in this survey is not proof of novelty.

The engineering rule is to investigate existing open-source work before a new capability or major subsystem replacement. The project AGENTS.md now records that user instruction. Routine fixes do not require repeating this whole survey.

## Intake, identification, naming, and filing

| # | Function and current position | Notable implementation | Existing open-source work | Reuse decision / remaining need |
| --- | --- | --- | --- | --- |
| 1 | Watch ToSort and notice new work; present | `inbox.py`, `service.py` | [watchdog][watchdog], already used | Keep its event handling. App-owned persistent jobs and periodic reconciliation still matter. |
| 2 | Wait for complete downloads and ignore temporary/Office lock files; present | `inbox.py`, `sorting/document_types.py` | [Paperless-ngx][paperless] ingestion patterns; [watchdog][watchdog] events | Learn from ingestion/retry patterns. A filesystem event alone does not prove a file is complete. |
| 3 | Extract PDF text/metadata for identification; present | `sorting/core_logic.py`, PDF libraries | [PyMuPDF][pymupdf], [pypdf][pypdf], already used | Keep existing engines; benchmark parser failures before adding another. |
| 4 | Extract Word text for naming; present | `sorting/core_logic.py` | [python-docx][docx], already used; [Docling][docling] broader parsing | Keep lightweight extraction unless a failing document justifies an adapter. |
| 5 | Extract PPTX content for naming; present | `sorting/presentation_extraction.py` | [python-pptx][pptx], [Docling][docling] | Compare bounded text extraction with a library before expanding custom OOXML logic. |
| 6 | Handle legacy PPT through review/fallback; present, limited | `sorting/presentation_extraction.py` | [Docling][docling] documents Office parsing | Verify the exact legacy format and runtime. No confirmed drop-in conversion is claimed. |
| 7 | Resolve DOI metadata through Crossref/DataCite; present | `sorting/metadata_lookup.py` | [Zotero translators][translators], [GROBID][grobid] metadata workflows | Prefer Zotero metadata for a linked record; retain exact DOI resolution when it is the smallest route. |
| 8 | Optional Gemini identification and connection test; present | `sorting/core_logic.py`, settings | [Google Gen AI Python SDK][genai], already used | SDK is reused; recognition is a hosted model service. Compare non-generative metadata first. |
| 9 | Distinguish articles, patents, and SI; present | `sorting/patent_metadata.py`, `core_logic.py` | [Zotero translators][translators], [GROBID][grobid] | Reuse available fields/parsers; retain the user's reviewed naming policy. |
| 10 | Special filenames, custom templates, sanitation; present | `sorting/core_logic.py` | [Zotero native renaming][rename], [Attanger][attanger] | Compare template coverage. Exact existing names and `_SI` policy are still acceptance criteria. |
| 11 | Choose/confirm a destination; present | Inbox UI/controller | [Attanger][attanger], [ZotMoov][zotmoov] | A possible replacement for generic attachment routing, not automatically the existing review workflow. |
| 12 | Avoid collisions, verify copies, recover incomplete filings; present | `inbox.py` | [CPython][python] file primitives; [Syncthing][syncthing] transaction/retry patterns | Retain small coordination and verify source identity; importing a whole sync engine is unnecessary. |

## Local library, identity, citations, and supporting information

| # | Function and current position | Notable implementation | Existing open-source work | Reuse decision / remaining need |
| --- | --- | --- | --- | --- |
| 13 | Watch existing PDF folders and reconcile changes; present | `service.py`, `storage.py` | [watchdog][watchdog], already used | Keep; a reference-manager attachment list and a watched folder have different semantics. |
| 14 | Model one paper with multiple annotated sources; present | `paper_registry.py`, `paper_projection.py` | [Zotero attachment model][attachments] | Integrate a Zotero parent key while retaining separate file/tablet source identities. |
| 15 | Suggest duplicate links and review mismatches; present | `reconciliation.py` | [Zotero duplicates][duplicates] | Learn from candidate matching. Metadata equality does not prove overlay compatibility. |
| 16 | Link/unlink sources while retaining history; present | `paper_registry.py`, `cloud_notes.py` | [Zotero][zotero] data-model/merge patterns | No exact replacement established for current history guarantees; retain focused coordination. |
| 17 | Locate moved folders and repair paths; present | `library_paths.py`, `library_files.py` | [Zotero linked-attachment base paths][attachments], [ZotMoov][zotmoov] | Reuse path-model ideas; only one app should own relocation. |
| 18 | Store title, authors, year, journal, identifiers; present | `citations.py`, `storage.py` | [Zotero][zotero], [Pyzotero][pyzotero] | Delegate authoritative bibliography to Zotero, retain a small searchable cache. |
| 19 | Review/save citation edits and conflicts; present | `citations.py`, research UI | [Zotero duplicate-field review][duplicates], [local API][localapi] | Keep explicit conflict handling; do not silently overwrite a reviewed Zotero record with filename-derived data. |
| 20 | RIS/BibTeX and plain citation export; present | `citations.py` | [Zotero translators][translators], [Better BibTeX][bbt] | Existing exports already provide a basic handoff. Avoid implementing a larger format ecosystem ourselves. |
| 21 | Journal-specific formatted citations; gap | Plain references only | [CSL styles][csl], [citeproc-js][citeproc], Zotero | Delegate to an established citation manager/processor. |
| 22 | Find SI from PDF/publisher links and DOI relations; present | `supplements.py` | [Zotero translators][translators]; [supplement preferences][supprefs] | Publisher-specific translators are a stronger reuse source than accumulating custom site scrapers. |
| 23 | Find existing local SI and associate reviewed parent; present | `supplement_library.py` | [Zotero child attachments][attachments], [Attanger][attanger] matching | Keep explicit identity/parent relationships; filename similarity alone remains a suggestion. |
| 24 | Download/reuse attachments and retain URLs; present | `supplements.py` | [Zotero attachment source][attachmentcode] | Reuse design ideas for publication/retry, not arbitrary code copying. Preserve current bounded file handling. |
| 25 | Produce `_SI` names from parent naming rules; present | `supplement_library.py` | [native renaming][rename], [Attanger][attanger] | Verify exact suffix and parent-base consistency; general renaming alone is insufficient. |
| 26 | Keep main/SI in the same physical directory; partial | Existing-file attachment need not move/rename | [ZotMoov][zotmoov], [Attanger][attanger] | Select one file owner. Native Zotero stored attachments use separate directories. |
| 27 | Always-visible main↔SI navigation; gap in requested form | Attachment dialog exists | [Zotero reader][reader] context/attachment UI | Small custom reader control is plausible; do not merge SI pages into the article. |

## Tablet connection, folder and document synchronization

| # | Function and current position | Notable implementation | Existing open-source work | Reuse decision / remaining need |
| --- | --- | --- | --- | --- |
| 28 | Pair and protect cloud credentials; present | `remarkable_cloud.py`, sync setup | [rmapi][rmapi], [reMarkable MCP][rmmcp] | Already informed by community protocol work. Keep the local Windows credential protection adapter. |
| 29 | Browse cloud folders and limit sync scope; present | `remarkable_sync.py` | [rmapi][rmapi], [reMarkable MCP][rmmcp] | Follow upstream protocol fixes; preserve explicit selected-root scope. |
| 30 | Map tablet folder IDs to PC destinations; present | `remarkable_sync.py` | [Tagged Sync][tagged], [rMsync][rmsync] routing ideas | Name-based correspondence needs stable identities and reviewed exceptions. No direct drop-in proven. |
| 31 | Create counterparts for new folders in either direction; present, opt-in | `remarkable_outbox.py` | [rmapi][rmapi] operations; [rMsync][rmsync] older mirroring concept | Reuse protocol primitives; compare actual hierarchy behavior before replacing the coordinator. |
| 32 | Mirror renames and moves in both directions; gap | Not fully propagated | [Syncthing][syncthing] state/reconciliation patterns | Design separately from additions. Generic disk synchronization is not a tablet API adapter. |
| 33 | Propagate deletions; separate undecided requirement | Current cloud absence retains local material | [Syncthing][syncthing] versioning/conflict ideas | Do not infer deletion authority from a request for new-folder mirroring. |
| 34 | Upload newly filed Inbox PDFs; present, opt-in | `service.py`, `remarkable_outbox.py` | [rmapi][rmapi], [Zotero reMarkable Sync][zrm] | A bridge candidate exists; verify Zotero/device version and duplicate handling. |
| 35 | Upload arbitrary PDFs newly added anywhere in linked PC tree; gap | Explicit sends and Inbox handoff exist | [rMsync][rmsync], [watchdog][watchdog], [rmapi][rmapi] | Older scripts demonstrate the concept; current integration still requires identity and loop prevention. |
| 36 | Download new tablet PDFs into mapped PC folders; present | `remarkable_sync.py`, `cloud_notes.py` | [rmapi][rmapi], [RCU][rcu] | Reuse upstream transfer/rendering where appropriate; preserve current route checks. |
| 37 | Detect revisions and refresh supported annotations; present | Sync manifests/source bundles | [reMarkable MCP][rmmcp], [Zotero reMarkable Sync][zrm] | Compare stable document/revision identities rather than matching only filenames. |
| 38 | Parse v6 scene files and map PDF pages; present | `remarkable_pdf.py` | [rmscene][rmscene], already used; [rmc][rmc] | Continue upstream reuse; benchmark device geometries and page-map changes. |
| 39 | Render strokes, colors, highlights, typed text; present with format limits | `remarkable_pdf.py` | [rmc][rmc], [RCU][rcu], [reMarkable MCP][rmmcp] | Compare difficult fixtures; do not claim any renderer is native-equivalent without verification. |
| 40 | Durable outgoing queue, retry, cancellation, uncertain-send recovery; present | `remarkable_outbox.py` | [Syncthing][syncthing] retry/state ideas; [zrm][zrm] workflow comparison | Mostly app-specific coordination; keep identities persisted before sends. |
| 41 | Retain source PDF/layers for offline reconstruction; present | `remarkable_sources.py`, storage modules | [rmscene][rmscene], [RCU][rcu] archives/conversion | Keep immutable inputs; render formats should be rebuildable outputs. |
| 42 | Combine PC/tablet marks with compatibility checks; present | `combined_pdf.py` | [PyMuPDF][pymupdf], [remarkable-zotero-cli][rmcli] annotation-transfer comparison | Retain page/edition checks. User's tablet-primary workflow can reduce future PC-edit complexity. |
| 43 | Automatically refresh the normal, durable annotated PC PDF; gap | Temporary reading views and explicit exports exist | [RCU][rcu] export; [rMsync][rmsync] annotated-output concept | A small publication adapter may remain necessary; generated outputs must not re-upload as new originals. |
| 44 | Import tablet tags into one visible tag interface; gap | Local tags exist; tablet tags not integrated | [rmapi tag output][rmapi], [reMarkable MCP][rmmcp] | Reuse existing tag extraction. Keep origin internally, deduplicate names, preserve page-tag scope. |

## Annotation extraction, handwriting, and library search

| # | Function and current position | Notable implementation | Existing open-source work | Reuse decision / remaining need |
| --- | --- | --- | --- | --- |
| 45 | Extract highlights, underlines, comments and replies; present | `extraction.py` | [PyMuPDF][pymupdf], already used; [pdfannots][pdfannots] | Keep core engine; use a second extractor as a comparison on failures. |
| 46 | Group ink/drawings and retain close-up plus page context; present | `extraction.py`, viewport/render modules | [PyMuPDF][pymupdf], [Pillow][pillow], already used | Generic rendering exists; scientific marginalia grouping still needs representative examples. |
| 47 | Add margin space to generated reading/export PDFs; present for supported geometry | `pdf_margins.py` | [PyMuPDF][pymupdf], [rmc][rmc] coordinate reference | Small custom geometry adapter is justified only by verified cases. |
| 48 | Optional isolated-ink OCR; present with uncertain accuracy | `extraction.py` | Tesseract already invoked; [E-Ink Sync][eink] pipeline | Keep as baseline and preserve source images. |
| 49 | Reliable searchable handwriting; gap as a general guarantee | OCR suggestions and images exist | [PaddleOCR][paddle], [TrOCR][trocr], [Kraken][kraken], [Tagged Sync][tagged] | Benchmark existing recognizers, do not invent/train an engine by default. |
| 50 | Search image-only printed scans; gap without text layer | Warns that OCR is required | [OCRmyPDF][ocrmypdf] | Preferred focused preprocessing candidate; verify geometry before publishing annotated results. |
| 51 | Improve difficult reading order/tables; partial PDF-engine extraction | `extraction.py`, worker | [Docling][docling], [GROBID][grobid] | Use only for observed failures; model/service footprint may outweigh the gain. |
| 52 | Indexed PDF page text and refresh on changes; present | `search_index.py`, `research_search.py` | [SQLite FTS5][fts], already used; [Zotero full-text source][fulltextcode] | Existing robust building blocks. Compare coverage and stale-index handling before changing engines. |
| 53 | Words, phrases, Boolean expressions, negative terms; present at page level | `search.py`, `research_search.py` | [FTS5][fts], [Zotero 10 search][z10] | Keep clear semantics; whole-document matching is a separate requirement. |
| 54 | Whole-paper Boolean matches across pages; gap | Current PDF terms must match within a page | [Zotero 10][z10], [full-text source][fulltextcode] | Try Zotero's attachment-level query first; adapt Notable's indexing only for a demonstrated benefit. |
| 55 | Search notes/printed content/metadata with separate scopes; present | `research_search.py`, `research_tools.py` | [Zotero search levels][z10], [search modes][zsearch] | Strong existing overlap; evaluate an integrated Zotero result handoff. |
| 56 | Match excerpts, occurrence navigation and PDF highlights; present | `reader_results.py`, navigation, viewer assets | [PDF.js][pdfjs], already used; [Zotero reader][reader], [Sioyek][sioyek] | Borrow selected navigation behavior, not an entire new reader. |
| 57 | Local tags, collections and saved searches; present | `research_tools.py`, `storage.py` | [Zotero collections/tags][tags] and saved queries | Prefer one visible organization system; map external identities without duplicating UI. |
| 58 | Note revision history, missing-source retention, logical-paper deduplication; present | `storage.py`, `cloud_notes.py`, registry | [Zotero][zotero] item/annotation versioning patterns | Not equivalent to Notable's exact history rules; retain those guarantees unless a replacement proves them. |

## Reader, exports, and accessibility

| # | Function and current position | Notable implementation | Existing open-source work | Reuse decision / remaining need |
| --- | --- | --- | --- | --- |
| 59 | Embedded read-only PDF, page/zoom/scroll state, reading mode; present | `pdf_reader.py`, `reader_host.py`, assets | [PDF.js][pdfjs] and [pywebview][webview], already used | Keep upstream rendering; application navigation/state remains a thin adapter. |
| 60 | Separate in-document Find from library search; present | Reader assets and navigation | [PDF.js][pdfjs], [Zotero reader][reader] | Already built on established viewer primitives; avoid mixing the two query states. |
| 61 | Open external viewer at a physical page; present with viewer-specific limits | `viewers.py`, page helpers | [Zotero reader][reader] external-open patterns | Retain a small Windows/viewer adapter; no universal page-jump guarantee. |
| 62 | Physical versus embedded/journal page labels; present, journal verification limited | `pages.py` | [PyMuPDF][pymupdf], [pypdf][pypdf] | Reuse PDF labels; do not infer journal pagination solely from labels. |
| 63 | Enlarge/copy drawing/full-page images and navigate context; present | `image_viewport.py`, `clipboard.py` | [Pillow][pillow], [Tk][tk], already used | Keep simple UI/OS adapters; no new image application needed. |
| 64 | Generate folder Word notebooks in reading/detailed layouts; present | `exporting.py`, `service.py` | [python-docx][docx], already used; [Better Notes][bn] | Compare exact output before expanding Notable's notebook system. |
| 65 | Filtered Word exports, editable copies, rebuild without rescanning; present | Export/UI/service modules | [Better Notes][bn], [python-docx][docx] | Existing overlap; retain source-page/image requirements as the test. |
| 66 | Preserve edited notebooks, locked-file retry and atomic replacement; present | `exporting.py`, `service.py` | [CPython][python] file primitives; [docx][docx] serialization | Small app-specific publication policy; a document-writing library alone does not replace it. |
| 67 | Export lasting annotated PDFs; present, explicit action | `combined_pdf.py` | [PyMuPDF][pymupdf], [RCU][rcu], Zotero exports | Already reuse PDF engine. Automatic normal-file refresh remains row 43. |
| 68 | Accessible browser reading snapshot; present | `accessible_reader.py` | [Zotero reader][reader] semantic/reflow ideas; [CPython][python] HTML generation | Keep semantic HTML; this does not certify the complete Tk interface with screen readers. |
| 69 | Markdown/Obsidian export; proposed | Not currently a general export | [pdfannots][pdfannots], [Better Notes][bn], [reMarkable MCP][rmmcp] | Reuse formats/patterns if still needed; lower priority than sync/search. |

## Storage, platform, diagnostics, and release support

| # | Function and current position | Notable implementation | Existing open-source work | Reuse decision / remaining need |
| --- | --- | --- | --- | --- |
| 70 | SQLite library, migrations, persisted settings/history; present | `storage.py` | [SQLite/Python sqlite3][sqlite], already used | Keep transactional foundations; Zotero integration should use its API. |
| 71 | Shared image/baseline content and bounded rebuildable caches; present | Image/source/cache modules | [CPython][python] hashing/storage; [Syncthing][syncthing] content-identity patterns | Retain focused content-addressed records; do not introduce a distributed storage service. |
| 72 | Verified backup, independent restore, safe compaction; present | `maintenance.py` | [SQLite backup API][sqlite], [CPython][python] ZIP/hash tools, already used | Existing primitives suffice. Restore must include tablet assets, not only the DB. |
| 73 | Review/retire old reading copies and redundant archives; present | `source_storage.py`, `archive_storage.py` | [CPython][python] primitives; no exact application-level equivalent established | Keep explicit ownership/reconstruction proofs. Generic duplicate-file deletion is not equivalent. |
| 74 | Background PDF process, scheduling, cancellation, progress; present | `pdf_worker.py`, `service.py` | [CPython concurrent futures][python], already used | Improve measured bottlenecks; no replacement framework justified by this survey. |
| 75 | Private local viewer serving and environment retry; present | `reader_server.py`, reader host | [PDF.js][pdfjs], [pywebview][webview], [CPython][python] | Keep a narrow local adapter. Preserve page loading and startup behavior. |
| 76 | Settings, responsive toolbars, keyboard shortcuts, tooltips, layout persistence; present | Tk UI/workspace/widgets modules | [Tk][tk], already used; [Zotero reader][reader] interaction reference | Learn targeted interaction patterns. A GUI rewrite is outside the identified need. |
| 77 | Drag/drop, Windows identity/shortcuts and clipboard; present | DnD/Windows/clipboard adapters | [tkinterdnd2][dnd], already used; [CPython][python] OS interfaces | Keep OS-specific adapters; platform APIs are not replaced by a reference manager. |
| 78 | Portable Windows build, pinned assets, dependency verification; present | Build scripts/spec/lock files | [PyInstaller][pyinstaller], already used | Continue upstream tooling and verify the packaged app. |
| 79 | Feedback drafts, manual update check, logs/diagnostics; present | `support.py`, support UI | [CPython][python] browser/mail/HTTP/logging facilities; open-source [Zotero][zotero] support patterns | Existing small implementation is appropriate; no new support platform or updater needed. |
| 80 | Regression tests, synthetic samples, isolated UI checks, manuals; present | Tests/tools/documentation/scripts | [CPython unittest][python], [Pillow][pillow], [PyMuPDF][pymupdf] | Reuse test/render tools. Add real-device evidence before assuming sync compatibility. |

## Specific source-level lessons found

1. **Zotero full-text code:** its current `fulltext.js` uses SQLite FTS5, separates attachment and note indexes, tracks index versions, and handles stale/short-query cases. Notable already uses FTS5 trigram candidates with its own final query checks. The useful next step is comparing semantics, coverage and invalidation, not claiming a new indexing invention. The default branch may be ahead of stable releases. [Source][fulltextcode]
2. **Pyzotero local support:** the README includes a local-client example and authorized write flow. A Python bridge already has a substantial starting point. [Client][pyzotero]
3. **ZotMoov version check:** its current source manifest declares Zotero `10.*`, despite its older README wording about Zotero 7. A version claim must be checked against the actual selected release. [Manifest][zotmoovmanifest]
4. **Experimental tablet bridge:** the Zotero reMarkable Sync README describes safe-mode behavior but advertises support only through Zotero 9. It is not a verified Zotero 10 solution. [Project][zrm]
5. **SI preferences:** Zotero translators can attach supplementary material for supporting sites. This gives us publisher-specific open-source work to inspect before expanding custom discovery. [Preferences][supprefs]
6. **Handwriting model boundary:** TrOCR's handwritten model card specifies single text-line inputs. It needs segmentation, not just a model download pointed at a whole annotated page. [Model][trocr]

## Selection rather than accumulation

The highest-priority candidates are Zotero/Pyzotero for citation metadata; an existing tablet bridge or upstream rmapi/rmscene/rmc for protocol/conversion; Zotero translators for publisher/SI capture; OCRmyPDF for scans; and a measured PaddleOCR/TrOCR handwriting adapter. Better Notes and ZotMoov are evaluation alternatives, not mandatory dependencies to pile on top of Notable.

For each future change, record a short evidence note: user task, existing candidates, actual tested version, Windows/firmware constraints, license/model terms, acceptance sample, and why integration/adaptation/custom coordination was selected. Prefer a supported API or ordinary file exchange when copying a larger application would add maintenance.

Some candidates are copyleft; some are permissive; some projects include differently licensed models or paid features. Repository access is not blanket permission to combine arbitrary source. Inspect the selected files/dependencies before reuse. This is not a completed license audit. Protocol APIs and external application interfaces are separate from incorporation of code.

## Suggested comparison before more implementation

Use copies of representative material: a normal article, a scan, a screenshot PDF, a multi-column paper, scientific handwriting, margin notes, main+SI, several SI attachments, a moved/renamed file, an interrupted transfer, and a revised tablet document. Compare native Zotero 10 first, then one compatible tablet bridge, against current Notable. Test same-attachment versus whole article-family search explicitly.

The decision can be to keep Notable, reduce it to a bridge, or retire duplicated functions. Success is less user effort with the required evidence preserved, rather than a larger feature count.

[zotero]: https://github.com/zotero/zotero
[z10]: https://www.zotero.org/blog/zotero-10/
[zsearch]: https://www.zotero.org/support/searching
[localapi]: https://www.zotero.org/support/dev/web_api/v3/local_api
[pyzotero]: https://github.com/urschrei/pyzotero
[fulltextcode]: https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/fulltext.js
[attachmentcode]: https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/attachments.js
[attachments]: https://www.zotero.org/support/attaching_files
[duplicates]: https://www.zotero.org/support/duplicate_detection
[tags]: https://www.zotero.org/support/collections_and_tags
[rename]: https://www.zotero.org/support/file_renaming
[supprefs]: https://www.zotero.org/support/preferences/hidden_preferences
[translators]: https://github.com/zotero/translators
[reader]: https://github.com/zotero/reader
[bn]: https://github.com/windingwind/zotero-better-notes
[bbt]: https://github.com/retorquere/zotero-better-bibtex
[zotmoov]: https://github.com/wileyyugioh/zotmoov
[zotmoovmanifest]: https://github.com/wileyyugioh/zotmoov/blob/master/manifest.json
[attanger]: https://github.com/MuiseDestiny/zotero-attanger
[zrm]: https://github.com/bpiwowar/zotero-remarkable-sync
[tagged]: https://github.com/thomas-hochbichler/obsidian-remarkable-tagged-sync
[rmcli]: https://github.com/Milofax/remarkable-zotero-cli
[rmapi]: https://github.com/ddvk/rmapi
[rmmcp]: https://github.com/SamMorrowDrums/remarkable-mcp
[rmscene]: https://github.com/ricklupton/rmscene
[rmc]: https://github.com/ricklupton/rmc
[rmsync]: https://github.com/lschwetlick/rMsync
[rcu]: https://www.davisr.me/projects/rcu/
[eink]: https://github.com/hwangso595/eink-sync
[watchdog]: https://github.com/gorakhargosh/watchdog
[paperless]: https://github.com/paperless-ngx/paperless-ngx
[syncthing]: https://github.com/syncthing/syncthing
[pymupdf]: https://github.com/pymupdf/PyMuPDF
[pypdf]: https://github.com/py-pdf/pypdf
[docx]: https://github.com/python-openxml/python-docx
[pptx]: https://github.com/scanny/python-pptx
[genai]: https://github.com/googleapis/python-genai
[docling]: https://github.com/docling-project/docling
[grobid]: https://github.com/grobidOrg/grobid
[pdfannots]: https://github.com/0xabu/pdfannots
[ocrmypdf]: https://github.com/ocrmypdf/OCRmyPDF
[paddle]: https://github.com/PaddlePaddle/PaddleOCR
[trocr]: https://huggingface.co/microsoft/trocr-base-handwritten
[kraken]: https://github.com/mittagessen/kraken
[fts]: https://www.sqlite.org/fts5.html
[sqlite]: https://docs.python.org/3/library/sqlite3.html
[python]: https://github.com/python/cpython
[pillow]: https://github.com/python-pillow/Pillow
[pdfjs]: https://github.com/mozilla/pdf.js
[webview]: https://github.com/r0x0r/pywebview
[sioyek]: https://github.com/ahrm/sioyek
[tk]: https://github.com/tcltk/tk
[dnd]: https://github.com/pmgagne/tkinterdnd2
[pyinstaller]: https://github.com/pyinstaller/pyinstaller
[csl]: https://github.com/citation-style-language/styles
[citeproc]: https://github.com/Juris-M/citeproc-js
