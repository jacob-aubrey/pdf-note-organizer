# Capability triage inventory

Prepared October 18, 2026. This is an inventory and decision aid, not a test report. Statements below derive from the conversation, the current README, the three existing October 18 research reports, and the small source check identified below. Alternative applications and plugins were **not newly installed or tested for this inventory**. Other preflight work must supply runtime evidence before a route is selected.

The subsequent [route decision](2026-10-18-triage-and-route-decision.md) and linked runtime reports now supply that evidence: 190 selected Notable regressions; isolated Zotero 10.0.6 model/search/export/restart trials; six successful Pyzotero local API checks; and synthetic printed OCR trials. Read the detailed cells below as capability descriptions, and use those reports for measured results and limitations. The inventory itself is not an additional test run.

The user's latest correction changes the comparison substantially: **SI only needs a clear association with the article and easy access nearby. Zotero child attachments satisfy that minimum in principle.** Identical physical directories, exact `_SI` suffixes, and a permanent reciprocal reader toolbar are preferences that may be dropped; they must not be used to justify substantial custom development.

During preflight the user further clarified that **the physical Windows folder layout/storage location does not matter**, provided papers remain organized and easy to access. Zotero desktop access or File Explorer access is acceptable. The user is comfortable with **Zotero as the main interface and a quiet, reliable background helper**. This supersedes the earlier folder-first inference: preserve conceptual organization/tablet correspondence, both-way additions and easy access, rather than requiring identical physical directory trees or linked-file storage.

Later triage answers narrow “all my notes” to **annotations on PDFs; native reMarkable notebooks are out of scope**. Automatic Word notebooks remain undecided because the user has not used the app enough to judge them: preserve them in the comparison, but do not make them a migration gate. Whole-document logical search is important; a single typed Scopus-style query has not been declared indispensable. The root preflight separately reports successful Zotero whole-attachment AND/NOT scenarios and Notable's page-level limitation; see that test report for runtime evidence.

The user also requires dissertation support. Current source contains `thesis_dissertation` type, aliases, and a local inference rule in `note_organizer/sorting/core_logic.py` (lines 55, 66, 83, and 842 at inspection). That does not establish that the user's dissertation workflow works. Describe the issue as **an unverified or inadequate dissertation workflow**, rather than asserting that Notable cannot open dissertation PDFs or has no dissertation type. Zotero has a dedicated Thesis bibliographic type; real records and long PDFs still need testing.

## Reading the inventory

Priority is provisional and must not be presented as a decision already made by the user:

- **E — essential:** explicitly emphasized outcome, or an unavoidable requirement for a trustworthy implementation of that outcome.
- **I — likely important:** expressly desired, but the user has not confirmed that it can veto a simpler route.
- **O — optional:** discussed as a possibility, convenience, or future addition; no requirement to implement it.
- **T — incidental technical capability:** current engineering/UI provision rather than a desired product feature in itself. Its *outcome* may remain essential even if its implementation disappears.
- **D — decision needed:** scope or policy is not established. Do not silently turn it into a requirement.

“Present” describes documented Notable behavior, not a successful real-device test. “Partial” means a material part of the desired outcome is missing. “Zotero” means native unless the cell names a plugin. “Candidate” is a documented/repository possibility, not a confirmed solution. Costs, cloud storage, recognition accuracy, Windows packaging, current Zotero compatibility, and firmware compatibility are separate checks.

## Workflow and ownership outcomes

| ID | Capability or policy | Priority and reason | Notable now | Zotero / other routes |
| --- | --- | --- | --- | --- |
| W01 | A simple research workflow with few recurring manual steps | E: repeatedly emphasized | Existing all-in-one interface; several workflows still need review | Zotero may remove duplicated bibliography/search UI; plugin count and repair burden must be measured |
| W02 | Read papers and write annotations primarily on reMarkable | E: explicit preference | Supports imported tablet PDFs | Zotero is a library/citation hub; tablet bridge remains necessary |
| W03 | Do not require PC annotation edits to travel back to the tablet | E: explicit scope reduction | Existing combined-source machinery supports a broader use case | Keep the pilot tablet-primary; two-way annotation editing is unnecessary |
| W04 | Papers stay organized and easy to access through Zotero desktop or File Explorer | E: latest clarification; physical storage layout is flexible | Originals retained in user-chosen folders | Native managed attachments are acceptable; linked files are an option, not a requirement |
| W05 | One visible collection of papers and their PDF annotations | E: explicitly requested; native tablet notebooks excluded by later answer | Logical paper registry combines linked sources | Zotero parent records, attachments, annotations, and notes overlap strongly |
| W06 | A normal PC PDF reflects new tablet annotations | E: explicit requirement | Combined reading cache and explicit export; ordinary original is not automatically rewritten | Zotero export can embed marks, but automatic durable refresh requires coordination |
| W07 | A clear relationship between main article and SI | I: explicit, recently relaxed | Relationship/discovery tools present | Native child attachments satisfy the minimum logical association |
| W08 | Handle dissertations as research sources | E: explicit source-type requirement | Synthetic PDF classification/naming/long-text search passed; university/degree bibliography fields absent | Native Thesis metadata and synthetic CSL bibliography passed; real-world automatic capture still needs checking |
| W09 | Work with normal papers, scans, and screenshot PDFs | E: explicit outlier requirement | PDFs render; textless search needs OCR | Zotero renders PDFs; OCR preprocessing is a separate addition |
| W10 | Keep authoritative citation metadata in one place | I: explicitly useful, citations may be delegated | Local reviewed citation records | Zotero is the strongest existing owner candidate; Mendeley can remain during a pilot |
| W11 | One user-facing tag system | I: explicit concern about confusion | Local tags only; no tablet tag merge | Zotero tags plus a bridge/import policy could become the single interface |
| W12 | Local/offline use for existing library and notes | I: fits stated local-library workflow | Present; cloud identification/tablet transfers optional | Zotero local library works offline; new tablet synchronization needs a connection |
| W13 | Open-source-first selection before substantial new coding | E: explicit instruction and AGENTS.md | Uses numerous existing components | Apply to both plugins and a standalone app; existing code must still fit the workflow |
| W14 | Avoid paying for cloud storage that the workflow does not require | O: storage questions, no zero-cost constraint declared | Local storage limited by disk; external services separate | Zotero local files/metadata differ from its attachment storage quota |
| W15 | Choose a single owner for files, names and visible library organization | E: derived requirement to prevent conflicts | Notable currently owns Inbox filing | Zotero main UI plus a quiet reliable helper is explicitly acceptable; managed storage can avoid competing movers |
| W16 | Preserve existing work and allow rollback when changing route | E: derived data-integrity requirement | Retained sources, histories, backups | Pilot copied files/profile before any actual migration; bibliography exchange alone is not a full transfer |

## Intake, identification, naming, and source types

| ID | Capability | Priority and reason | Notable now | Zotero / other routes |
| --- | --- | --- | --- | --- |
| I01 | Watch ToSort/Inbox for new documents | I: explicit existing workflow | Present using watchdog and persistent jobs | Watch-folder plugins/helpers are candidates; native attachment import alone is different |
| I02 | Wait for completed downloads; ignore temporary/Office lock files | T: supports reliable intake | Present | Retain if any watcher is used; Paperless-ngx offers ingestion patterns |
| I03 | Review a suggested filename before filing | I: explicit | Present | Native renaming/templates overlap; exact review workflow needs comparison |
| I04 | Choose a destination folder and file the document | I: explicit | Present | Attanger/ZotMoov are candidates; Zotero collection membership alone does not move a file |
| I05 | Identify PDF text and embedded metadata | I: naming dependency | Present with existing PDF libraries | Zotero PDF metadata recognition/translators provide alternative paths |
| I06 | Extract Word DOCX text for naming | I: explicitly mentioned | Present for sorting | Zotero can attach Office files; equivalent custom naming/review is not native |
| I07 | Extract PowerPoint PPTX text for naming | I: explicitly mentioned | Present for sorting | Existing Office parsers/helpers can be reused |
| I08 | Handle legacy PPT through fallback/review | I: existing supported input | Present with limitations | Must test actual format; do not assume any parser supports old binary PPT |
| I09 | Article, patent, SI, and other document-type naming rules | I: existing special sorting | Present | Zotero supports reference types; exact local filename policy is separate |
| I10 | Dissertation/thesis identification and appropriate naming | I: newly explicit | Synthetic classification/naming passed; representative real cases untested | Zotero Thesis metadata passed in preflight; automatic identification/naming of real cases remains to compare |
| I11 | Custom templates and safe Windows filenames | I: current naming convenience | Present | Native Zotero renaming and Attanger overlap; exact old spelling need not be preserved automatically |
| I12 | Exact DOI lookup through Crossref/DataCite | I: metadata/naming/search | Present and reviewed | Zotero identifier lookup and translators overlap |
| I13 | Optional AI-assisted identification when ordinary metadata fails | O: existing fallback | Gemini opt-in, with separate Office sharing permissions | Keep only if representative hard cases justify account/setup and privacy tradeoffs |
| I14 | Collision handling, copy verification, interrupted-filing recovery | T: supports trust | Present | Required outcome for any replacement file organizer; not a reason to retain duplicate UI |

The application currently sorts Office files but does **not** convert them to PDF or send them through note extraction/reMarkable transfer. Automatic Office-to-PDF conversion was not an established requirement and must not be inferred from “support Word/PowerPoint.” Sources: current README and the existing function map; [Zotero capture](https://www.zotero.org/support/adding_items_to_zotero), [renaming](https://www.zotero.org/support/file_renaming).

## Bibliographic records, attachments, SI, and citation writing

| ID | Capability | Priority and reason | Notable now | Zotero / other routes |
| --- | --- | --- | --- | --- |
| B01 | Store/review title, authors, year, journal, DOI and identifiers | I: naming and author search explicitly depend on it | Present with edited values preserved across scans | Native Zotero record editing; authoritative owner candidate |
| B02 | Rich metadata for theses, books, chapters, reports, proceedings, datasets, patents, websites | I for theses; O for remaining unused types | Sorting types exist; citation model is narrower than a full reference manager | Native type-specific records |
| B03 | Resolve disagreements between reviewed citations before linking/merging | T: protects metadata | Present | Native duplicate review offers overlap; a bridge still needs a conflict policy |
| B04 | RIS, BibTeX, and plain reference export | I: existing reference-manager handoff | Present | Native Zotero imports/exports many formats; Better BibTeX optional |
| B05 | Journal-style citations and bibliographies | I: user uses a citation manager | No complete style engine | Native Zotero/CSL; Mendeley also serves this role |
| B06 | Active Word, LibreOffice, and Google Docs citation fields | I for user's actual writing tool; others O | Not delivered | Native Zotero integrations; test existing Mendeley manuscripts as copies |
| B07 | Browser capture, multi-item capture, identifier lookup and PDF recognition | O/I: useful lower-effort intake, not an original veto | DOI/text identification, not a general browser connector | Native Zotero Connector/translators |
| B08 | Find available full text; attach local files, snapshots and other research artifacts | O: Zotero capabilities discussed | Local file/SI tools, not a general discovery service | Native Zotero with publisher/access limits |
| B09 | Keep main paper, SI, data and other files under one recognizable reference | I: SI association is explicit | Main/SI relationships present | Native Zotero child attachments; sufficient for the user's relaxed SI minimum |
| B10 | Discover SI from publisher/PDF links and DOI relations | O: useful existing extra, not a demanded project focus | Present with manual review | Zotero translator coverage/optional supplemental capture varies by publisher |
| B11 | Find existing local SI, retain URLs, download safely, avoid duplicates | O: existing convenience | Present | Child attachment/import workflow plus publisher translators; exact automation need not match |
| B12 | Same physical folder, `_SI` filename and nearby reciprocal reader controls | O: expressly demoted | Naming exists; co-location/always-visible navigation incomplete | Optional file rules/plugin; **not a route-selection gate** |
| B13 | Duplicate record detection and reviewed merge; related-item links | I: duplicate clutter undermines one library | File/source-link review exists | Native Zotero bibliographic merge/related records; overlay compatibility remains a separate check |
| B14 | Mendeley import and manuscript continuity | I: needed if switching | RIS/BibTeX handoff only | Official Zotero importer; legacy Mendeley Desktop and Mendeley Cite fields differ |

Sources: prior Zotero decision report; [attachments](https://www.zotero.org/support/attaching_files), [related records](https://www.zotero.org/support/related), [duplicates](https://www.zotero.org/support/duplicate_detection), [citation integration](https://www.zotero.org/support/word_processor_integration), [Mendeley import](https://www.zotero.org/support/kb/mendeley_import).

## reMarkable folders, papers, annotation transfer, and provenance

| ID | Capability | Priority and reason | Notable now | Zotero / other routes |
| --- | --- | --- | --- | --- |
| S01 | Connect to tablet/cloud without routine USB/manual export | E: synchronization outcome | Direct unofficial cloud connection; opt-in | Not native Zotero; existing community bridge candidates need compatibility evidence |
| S02 | Browse tablet folders and select a bounded root | I: existing scope control | Present | Bridge-specific requirement |
| S03 | Map stable tablet folder identities to corresponding desktop organization | E: preserve organization; physical Windows tree no longer required | Physical folder mapping present, with review for unmatched baseline folders | Zotero collection mapping is acceptable if correspondence and easy access work |
| S04 | A new desktop organizational folder/collection gets a tablet counterpart | E: earlier folder goal, storage flexibility now explicit | Physical folder counterpart creation present opt-in | Collection-to-tablet creation is a valid implementation to test |
| S05 | A new tablet folder appears in desktop organization | E: earlier folder goal, storage flexibility now explicit | Physical folder counterpart creation present opt-in | Tablet-to-Zotero collection creation is a valid implementation to test |
| S06 | New desktop PDF reaches the corresponding tablet folder without repeated manual work | E: explicit additions goal | Gap for arbitrary linked-tree drops; explicit sends and Inbox-filed auto-send exist | Zotero attachment intake/collection mapping plus bridge could replace a physical-tree watcher |
| S07 | New tablet PDF becomes accessible in corresponding desktop organization | E: explicit additions goal | Downloads to mapped PC folders for supported imported PDFs | Zotero managed attachment import is acceptable; verify bidirectional *new-file* handling |
| S08 | Special Inbox-filed PDF can be automatically queued | I: current shortcut | Present opt-in | Replaceable if a broader linked-tree watcher works |
| S09 | Manual send, destination review and visible transfer status | I: useful fallback | Present | Some bridges support manual transfer; exact behavior varies |
| S10 | Download annotation revisions without duplicate papers | E: explicit | Present for supported formats | Plugin claims require actual Zotero/device tests |
| S11 | Preserve highlights, comments, ink, colors and supported typed text | E: notes are the core asset | Present with format/geometry limits | rmscene/rmc/RCU/community bridges provide candidate parsers/renderers |
| S12 | Refresh a durable ordinary annotated PC PDF automatically | E: repeated explicit outcome | Gap: cached combined PDF + manual export only | Need a publication step, stable path, and loop prevention; simple file copying misses DB-only Zotero annotations |
| S13 | Native reMarkable notebook and EPUB import/search | O: PDF annotations only; native notebook support explicitly out of scope | Skipped by current cloud workflow | Broader external support is optional and must not drive current architecture |
| S14 | Mirror PC/tablet renames and moves | D: intuitive meaning of “synced,” but not explicitly settled | Not general behavior | Separate state/reconciliation feature; no assumption of safe automatic propagation |
| S15 | Propagate deletes, trash and restore across devices | D: deletion authority never established | Missing cloud item does not automatically delete saved local material | Define a safe policy before testing destructive behavior; additions do not imply deletes |
| S16 | Durable retries, cancellation, uncertain-send recovery and changed-destination review | T: supports reliable unattended sync | Present | Replacement must show equivalent user outcomes; queue implementation can differ |
| S17 | Retain tablet source/strokes and separate revision/source identities | T: protects rebuildability/history | Present | Preserve unless a replacement proves equivalent recovery; a flattened PDF is a different artifact |
| S18 | Verify edition/page compatibility before merging PC and tablet marks | T/E: essential if merging is used | Present; incompatible editions/page changes held for review | Tablet-only annotation authority can simplify this; never match layers by title/DOI alone |

Sources: README sync sections and existing function map; [experimental Zotero reMarkable Sync](https://github.com/bpiwowar/zotero-remarkable-sync), [rmapi](https://github.com/ddvk/rmapi), [rmscene](https://github.com/ricklupton/rmscene), [rmc](https://github.com/ricklupton/rmc), [RCU](https://www.davisr.me/projects/rcu/). These projects are evidence to investigate, not a tested complete solution.

## Search, handwriting, tags, and organization

| ID | Capability | Priority and reason | Notable now | Zotero / other routes |
| --- | --- | --- | --- | --- |
| Q01 | Find every local paper containing a keyword | E: repeatedly emphasized | Indexed PDF page text plus metadata | Native Zotero full-text indexing; coverage/configuration must be tested |
| Q02 | Phrase queries, AND/OR/NOT and grouped conditions | E for logical retrieval; typed single-box grammar is not a confirmed gate | Typed syntax present; PDF terms currently must match within one page | Zotero 10 advanced nested-condition builder; exact typed-query equivalence is not established |
| Q03 | Whole-paper Boolean matches when terms are on different pages | E: implied by searching papers, a material current gap | Across-page AND/NOT gap confirmed by synthetic probes | Zotero attachment-level AND/NOT passed synthetic preflight; real corpus and grouped-query usability still need comparison |
| Q04 | Search notes, full papers and metadata together or separately | E/I: collection/search goal | Notes/PDFs/All scopes present | Native Zotero searches across different item levels, with different UI/semantics |
| Q05 | Author, title, DOI, filename and page metadata search | I: explicit author-search use | Present in paper scopes | Native Zotero metadata search; filename/page-specific behavior needs comparison |
| Q06 | Search scans and screenshot-only printed pages | E: explicit outlier case | No full-document OCR; textless papers cannot match ordinary words | OCRmyPDF/Tesseract preprocessing candidates; not solved by switching reference manager alone |
| Q07 | Search handwritten scientific margin notes | I: explicit question/interest; quality threshold unsettled | Optional isolated-ink Tesseract suggestions, not reliable general handwriting search | PaddleOCR/TrOCR/other recognizers need sample accuracy testing |
| Q08 | Reuse reMarkable's handwriting-search index on the PC | O: proposed shortcut | No integration | No documented supported index API found; official support excludes PDF/EPUB handwriting search in the cited article |
| Q09 | Preserve image/strokes and source context beside uncertain transcripts | E if handwriting recognition is adopted | Ink images/context retained | A recognizer adapter must retain provenance; fluent text is not proof of correctness |
| Q10 | Filter notes by type, color, text/comment and surrounding printed text | I: current useful specificity | Present | Zotero 10 annotation-aware conditions overlap; tablet representation matters |
| Q11 | Match snippets and jump to exact source page/occurrence | I: makes retrieval useful | Present, with PDF highlighting/navigation | Native Zotero reader overlap; inspect actual result navigation |
| Q12 | Indexed/partial/unindexed visibility, stale-index refresh and long-document coverage | E: necessary to trust “all PDFs” | Background page indexing/refresh; failure messages | Zotero index controls and length limits; dissertations/SI are important coverage fixtures |
| Q13 | Local tags, colored tags, collections/subcollections and saved searches | I: organized notes explicitly desired | Local tags/collections/saved searches present | Native Zotero strong overlap; collections are not physical directories |
| Q14 | Import tablet document/page tags into one visible tag interface | I: explicit | Gap | Bridge/API extraction exists as a candidate; origin and page scope need a policy |
| Q15 | One paper result across several annotation-source copies | I: avoids confusing duplicates | Logical registry and source history present | Zotero parent attachment model helps; distinct editions and SI must remain distinct |
| Q16 | Difficult columns, tables, hyphens, page labels and source text order | I: scientific papers/search reliability | Current PDF engine behavior can be imperfect | Compare Zotero and existing parsers; Docling/GROBID only for demonstrated failures |

Sources: README search section and prior reports; [Zotero 10 search](https://www.zotero.org/blog/zotero-10/), [index settings](https://www.zotero.org/support/preferences/search), [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF), [handwriting support](https://support.remarkable.com/articles/Knowledge/Handwriting-search). Exact search semantics and recognition accuracy are test questions, not settled by a feature checklist.

## Reader, notes, exports, and synthesis

| ID | Capability | Priority and reason | Notable now | Zotero / other routes |
| --- | --- | --- | --- | --- |
| R01 | View PDF and extracted notes with source-page links | I: existing desktop retrieval tool | Present | Native Zotero reader/notes overlap; user still prefers tablet reading |
| R02 | Extract highlights, underlines, comments/replies and drawing/ink groups | I: searchable note collection | Present | Zotero can import supported embedded PDF annotations; tablet drawing conversion still matters |
| R03 | Enlarge/copy an ink close-up and inspect full-page context | I: helpful for unrecognized handwriting | Present | Native reader/image tools overlap but exact extraction/grouping may differ |
| R04 | Add margin space in generated reading/export PDFs | O: existing specialized capability | Present for supported geometry | Could retain a focused helper; not a stated veto on moving to Zotero |
| R05 | Read-only embedded PDF with reading mode, zoom and remembered position | O: desktop convenience | Present using PDF.js/WebView2 | Native Zotero reader provides its own implementation |
| R06 | Independent in-document Find versus library search | I: ordinary retrieval usability | Present | Native reader search overlaps; exact state/navigation differs |
| R07 | Open externally, jump to physical page and distinguish PDF labels | I: durable source access | Present with viewer-dependent limits | Zotero external-open/source navigation; actual Windows viewer must be checked |
| R08 | Collect folder notes into generated Word notebooks | O/D: user undecided; preserve comparison but not a migration gate | Present, Reading/Detailed layouts | Better Notes DOCX export is a candidate, not proven equivalent automation |
| R09 | Filtered Word export, editable copy and rebuild from saved notes | O/D: automatic Word notebook requirement undecided | Present | Better Notes/templates or a retained Python export helper |
| R10 | Protect edited notebooks and retry locked-file/atomic publication | T: matters if R08/R09 retained | Present | Any replacement automatic export needs a clear policy; simple DOCX export alone is insufficient |
| R11 | Preserve note revisions, unavailable-source notes and offline reconstruction | I/T: current safety outcome | Present | Zotero note/source model is not automatically an equivalent revision archive |
| R12 | Accessible reading snapshot, Markdown export, source-linked synthesis and Obsidian linking | O: accessibility/synthesis extras discussed | Accessible HTML exists; broad Markdown/synthesis/Obsidian integration is future | Better Notes/Obsidian and PDF annotation export can serve optional later writing workflows |

Sources: README reader/notebook sections; [Zotero reader](https://www.zotero.org/support/pdf_reader), [notes](https://www.zotero.org/support/notes), [annotation storage](https://www.zotero.org/support/kb/annotations_in_database), [Better Notes](https://github.com/windingwind/zotero-better-notes). Zotero database annotations must be exported to appear in an ordinary external PDF; the source disk file does not silently acquire them.

## Storage, recovery, platform, and support provisions

These remain visible in the inventory so “all capabilities” does not silently discard them. Most are acceptance outcomes, not reasons to reproduce Notable's exact implementation in a Zotero plugin.

| ID | Capability | Priority and reason | Notable now | Zotero / other routes |
| --- | --- | --- | --- | --- |
| P01 | Local library without an application-imposed paper/file quota | I: user asked storage questions | Disk-bound library; caches have separate budgets | Zotero local files are not limited by its 300 MB free cloud attachment quota |
| P02 | Optional attachment cloud sync and unlimited metadata sync | O: PC/tablet bridge may not need Zotero file sync | Tablet/cloud connection; no general bibliography-cloud service | Zotero Storage tiers; personal-library WebDAV alternative; linked-file limitations |
| P03 | Verified backup, complete tablet assets, independent restore and safe compaction | E outcome, T mechanism | Present | Compare full restore evidence; cloud sync alone is not a versioned independent backup |
| P04 | Retire extra reading copies/redundant source archives only when reconstructable | T: housekeeping | Present with review | New design may avoid these legacy copies; migration must retain evidence |
| P05 | Detect moved/renamed local paths and repair unavailable files | I if linked files or folder watching retained | Present | Managed Zotero attachments may remove some path-repair work; linked-file routes still need it |
| P06 | Background work, cooperative cancellation, progress and responsive UI | T: ordinary usability | Present | Zotero plus helper must remain responsive; do not preserve a specific scheduler merely for parity |
| P07 | Persistent settings, keyboard shortcuts, tooltips, pane/layout state and copyable paths | T: ordinary usability | Present | Zotero supplies its own UI; only actual usability losses should drive customization |
| P08 | Windows x64 distribution, drag/drop, shortcuts/taskbar identity and clipboard | I for Windows compatibility; T for exact packaging | Portable app and platform adapters present | Zotero Windows application; each candidate plugin/helper must be checked on this PC |
| P09 | Optional-service permissions and protected local credentials | E outcome, T mechanism | Separate opt-ins and Windows protection | Bridge/API keys must use a defined authorization/storage model |
| P10 | Diagnostic logs, manual update checks, feedback drafts and bundled guides | T | Present | Zotero support plus a small extension's diagnostics/manual may replace them |
| P11 | Pinned dependencies/assets, regression fixtures and packaged-release checks | T | Present | Evaluate maintenance/security/update responsibility for the selected stack |
| P12 | Portable/inspectable data and supported integration interfaces | I: open-source-first and exit path | SQLite/source archives/files; exports | Zotero local API/Pyzotero plus normal exports; avoid direct writes to Zotero SQLite |

Sources: README storage/platform sections; [Zotero storage](https://www.zotero.org/storage), [storage FAQ](https://www.zotero.org/support/storage_faq), [sync](https://www.zotero.org/support/sync), [local API](https://www.zotero.org/support/dev/web_api/v3/local_api), [Pyzotero](https://github.com/urschrei/pyzotero).

## Capabilities discussed because other applications offer them

These are explicitly included so a broad internet sweep is not mistaken for a request to add everything discovered.

| ID | Capability | Priority | Existing source / implication |
| --- | --- | --- | --- |
| O01 | RSS journal/site feeds and recently-read lists | O | Native Zotero; helpful discovery/return navigation, unrelated to core mirroring |
| O02 | PDF/EPUB/web snapshot reading, reflow and Read Aloud | O | Native Zotero; voice/service limits separate from local library features |
| O03 | Shared group libraries and collaboration | O | Native Zotero; linked local files have group limitations |
| O04 | Mobile apps and web-library access | O | Native Zotero; user primarily reads on reMarkable, so do not optimize for unused mobile cases |
| O05 | My Publications/public bibliography | O | Native Zotero; no relevance to a private library unless requested |
| O06 | Batch metadata editing, undo and citation keys | O | Native recent Zotero; Better BibTeX only if its additional workflows are needed |
| O07 | Backlinks, graphs, Markdown vaults and personal synthesis writing | O | Obsidian/Better Notes; adding another daily interface is a choice, not automatic improvement |
| O08 | Generic full-text desktop search | O | Recoll is a comparison tool; it does not itself solve tablet/cloud annotation synchronization |
| O09 | Advanced PDF navigation and ordinary annotation extraction | O | Sioyek/pdfannots can supply reference behavior; adding another reader is not a requirement |
| O10 | General scanned-document ingestion/workflow | O | Paperless-ngx supplies ingestion/OCR ideas; not automatically the best research-citation front end |
| O11 | Direct device SFTP/Syncthing or alternative tablet manager | O | E-Ink Sync/RCU/other tools; device/Windows/firmware setup must be evaluated before selection |
| O12 | Crop/stroke merge/split, per-page settings, custom colors, tray/startup and source-linked summaries | O/D | Discussed as future Notable work; retain only if a concrete current failure or workflow need appears |

## Seven decisions the user actually needs to make

The preliminary tests should reduce these questions to concrete tradeoffs. A long feature list alone should not be pushed back to the user as 114 independent settings.

1. **Organization and interface authority — now resolved enough for a pilot.** The user accepts Zotero collections/managed storage and Zotero as the main interface with a quiet reliable helper. Physical folder identity, linked-file storage and identical Windows directory layout are not gates. Test conceptual correspondence and easy access instead. See W04, W15, S03–S07, P05.
2. **Does “synced” mean additions plus annotation refresh, or also renames, moves and deletions?** Additions and tablet-to-PC annotations are explicit. Renames/moves/deletes need separate policy, not an assumed feature promise. See S04–S07 and S14–S15.
3. **PDF-only annotation scope — now resolved for the pilot.** Native reMarkable notebooks are explicitly out of scope. Do not enlarge capture, handwriting recognition or source-linking merely because another tool supports them. See S13, Q07–Q09.
4. **What is the acceptable search interaction and matching unit?** Whole-paper Boolean retrieval is the desired outcome. Zotero uses an advanced nested-condition builder; Notable accepts typed operators. Do not require typed grammar until the user says the builder is inadequate. Also decide whether main+SI can satisfy a condition across separate attachments or must match one attachment. See Q01–Q05 and B09.
5. **Word notebooks — undecided, not a pilot/migration gate.** The user needs more experience to judge automatic folder Word notebooks. Keep current exports available for comparison; defer exact parity unless the pilot exposes a need. See R08–R11.
6. **How much naming/Inbox specialization is worth preserving?** Keep recognition/review for the user's actual article, dissertation, patent and Office cases, but do not preserve every historical filename detail if Zotero makes intake simpler. SI naming is already optional. See I01–I14 and B12.
7. **What handwriting accuracy and setup burden are acceptable?** Searchable PDF text is essential; handwritten-note retrieval is desired but unproven. Decide from the user's own scientific ink whether an opt-in local model, a separately licensed service, or image-only fallback is acceptable. Built-in reMarkable search cannot currently be assumed to supply a PC PDF index. See Q06–Q09, W01, P08–P09.

## Route comparison: what each route must prove

| Route | Existing strengths | Main work still required | What would reject it |
| --- | --- | --- | --- |
| Continue standalone Notable; citation manager stays separate | Current Inbox/Office naming, note extraction, folder mappings, source history and Word notebooks | Essential sync/search gaps; verified dissertation workflow; ordinary annotated output; OCR; optional metadata handoff | Ongoing upkeep/duplicate UI exceeds benefit; citation workflow remains cumbersome |
| Native Zotero only | Bibliography/dissertations, article+SI attachments, citations, tags/collections and full-text search | No native reMarkable bridge or tablet/desktop organization correspondence | Cannot satisfy S03–S12, so it cannot meet the current full requirement on its own |
| Zotero plus existing plugins only | Existing attachment/note/plugin ecosystem could reduce custom work; managed storage is acceptable | Prove current Windows/Zotero/device compatibility and full synchronization contract | A send/download demo is insufficient if counterpart organization, additions or durable annotated output fail |
| Zotero plus a focused Notable Python helper/extension | Reuse Zotero library/citations and Notable tablet/file/ink code; avoid rewriting everything in JavaScript | Define data/file ownership, API identity mapping, helper lifecycle and missing sync publication | Two competing libraries/tag systems/file organizers, or more recurring setup than the standalone route |
| Another existing app/combination | Specialized OCR, search or tablet conversion may solve a bounded gap | Demonstrate the actual end-to-end Windows research workflow | More tools, copies, repairs and license/setup burden without a measured improvement |

No route wins merely because it has more features. A successful route preserves the explicitly desired outcomes with the least recurring user work and a supportable implementation. The preliminary work should select a **pilot route**, not promise a completed migration.

## Acceptance scenarios that expose the important differences

Use a small disposable/copied corpus, retain expected answers independently, and report pass/fail/partial/not-tested with the exact app/plugin/firmware versions. Do not use an existing private library as a scratch database.

| Scenario | Evidence required | Inventory IDs |
| --- | --- | --- |
| Normal article + dissertation + patent + Word + PPTX + legacy PPT intake | Correct type/metadata proposal; sensible reviewed name; correct destination; originals recoverable | I01–I14, B01–B02 |
| Thesis with no DOI and a long scanned dissertation | Thesis title/author/institution/type metadata; no false article match; searchable content beyond the index cutoff | W08, I10, Q06, Q12 |
| Main paper with one or several SI files | Clear relationship and a quick way to open each; no merge into article pages; exact suffix/co-location **not required** | W07, B09–B12 |
| Create a desktop collection/tablet folder and add a PDF on each side | Corresponding organized desktop/tablet entries; files open easily; no duplicate uploads/downloads after repeated scans/restart; identical Windows paths not required | S03–S10 |
| Add highlight, comment and handwriting on tablet; refresh twice | Correct PDF page/geometry; ordinary PC PDF actually changes; no second logical paper or update loop | W06, S10–S12, S18 |
| Rename/move, disconnect during send, restart and reconnect | Explicitly record what is supported; recovery preserves data; no silent destructive action | S14–S17, W16 |
| Synthetic two-page query plus human-selected research papers | `alpha AND beta` on different pages; phrase/OR/NOT/grouping; scanned page; negative controls; expected paper set and useful source jumps | Q01–Q06, Q11–Q12 |
| Main+SI split-term query | State whether matching is per attachment or article family; no accidental false match caused by cross-record conditions | B09, Q02–Q04 |
| Scientific handwriting with known keywords | Count recovered/missed/false keywords, show original ink next to transcript, record runtime/setup; do not judge by attractive prose | Q07–Q09 |
| Tag on tablet and browse/filter on PC | One visible name/filter, repeated sync idempotent, document versus page scope clear | W11, Q13–Q14 |
| Optional Word notebook and edited/locked notebook | Compare figures/context/page links and update policy; do not reject an otherwise suitable route solely on exact notebook parity | R08–R11 |
| Mendeley import and copied current manuscript | Counts/attachments/collections/metadata; citation field compatibility demonstrated separately | B14, W16 |
| Close app/offline/reopen and restore copied backup | Saved search/notes available; dependency on running Zotero/helper explicit; complete recoverable assets | W12, P03, P08–P12 |

## Omissions and bounds

- This inventory covers all **discussed capability families**, including the 80-family Notable function map and the Zotero/other-app capabilities discussed alongside it. It does not claim every menu command or every possible plugin feature.
- Exact speed targets, library size, handwriting tolerance, actual firmware, installed Zotero/plugin versions, dataset licensing and mobile/group needs were not established in the conversation. Tests should record available facts and leave unknowns explicit. Native notebook scope is now resolved; exact Word notebook needs remain undecided.
- Office-to-PDF conversion, synchronous two-way annotation editing, automatic deletion propagation and a new AI synthesis system are not authorized product requirements simply because adjacent capabilities exist.
- The latest SI relaxation supersedes the strict SI requirements in the earlier research documents. The accepted Zotero UI/managed-storage option supersedes the older folder-first inference. The dissertation source check supersedes any blanket claim in older notes that Notable has no type handling at all.
- No measurements or installation claims should be inferred from this document. Pair it with the other agents' preflight results and the root report before making a recommendation.
