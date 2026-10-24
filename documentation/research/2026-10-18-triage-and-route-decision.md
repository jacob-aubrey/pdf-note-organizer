# Notable / Zotero triage and preliminary route decision

This is the current decision document, prepared October 18, 2026. It incorporates the user's latest answers and supersedes earlier assumptions about identical Windows folders and exact SI filenames. It evaluates a direction; it does not announce a migration or a completed integration.

**Leading direction: Zotero as the main research library, with a focused, quiet helper reusing the useful Notable processing and reMarkable code.** Native Zotero alone cannot meet the tablet workflow. An existing-plugin-only replacement has not passed the current-version bridge gate. Continuing every standalone Notable library/citation/search feature would duplicate substantial existing functionality.

Keep the working Notable application available until the selected route passes the device and usability gates below. No production app code or library was migrated during this investigation.

Implementation update: the [current companion](../ZOTERO_COMPANION.md) implements scoped folder/PDF additions both ways, durable tablet-view refresh, saved transcripts, printed OCR, tag import, encrypted reconnection and a small annotation-support extension. A live cloud round-trip passed, and 28 eligible real cached annotated PDFs rendered after an erased-stroke compatibility fix. Physical tablet interaction, handwriting accuracy, end-user setup and production migration remain separate acceptance gates. See the guide and linked validation record for measured boundaries.

## The complete triage list

The [114-capability inventory](preflight-capability-inventory-2026-10-18.md) lists every discussed capability family, with stable IDs, provisional priority, current Notable behavior, native Zotero behavior, and other open-source candidates. It includes intake and Office documents, bibliography and dissertations, SI, synchronization, search/OCR/handwriting, reader and exports, data recovery, platform provisions, and optional ecosystem features. It separates a requested outcome from an incidental implementation detail.

The earlier [80-row Notable/open-source function map](2026-10-18-open-source-function-map.md) supplies the finer component comparisons; the [ecosystem review](2026-10-18-ecosystem-review.md) catalogs the wider survey. Their stricter SI/folder assumptions must not override the user's newer answers.

## Confirmed requirements and clarified non-requirements

| Outcome | Current triage | Consequence |
| --- | --- | --- |
| Papers organized and easy to access | Essential | Zotero collections and managed attachments are acceptable. A mirrored physical Windows folder tree is unnecessary. |
| reMarkable remains the place to read and write ink | Essential | Design around tablet annotation authority; PC-to-tablet annotation merging is unnecessary. |
| New organization and PDFs correspond between desktop and tablet, with additions from either side | Essential from the original request | Zotero collections may represent desktop organization; file paths do not have to imitate the tablet. Actual correspondence still needs testing. |
| New tablet annotations become available in the current PDF on the PC | Essential | A cache, manual export, database-only annotation, and automatically refreshed durable PDF are different behaviors. The original automatic-update request has not been waived by accepting Zotero storage. |
| Search local papers by words, phrases and Boolean conditions across entire papers | Essential | A term on page 2 must combine correctly with a term on page 20. Excluded terms anywhere in the paper must exclude it. |
| Scanned/screenshot PDF outliers | Essential | Rendering a scan is insufficient; add searchable printed text using existing OCR software. |
| Collect/search annotations on PDFs | Essential | Native reMarkable notebooks created from scratch are explicitly **out of scope**. |
| Dissertation bibliography and PDF handling | Required source-type support | Zotero's Thesis metadata is a clear benefit; long-document index coverage needs configuration. |
| Main article and SI stay associated and easy to find | Important, small feature | Native sibling child attachments satisfy the clarified minimum. Exact `_SI`, disk co-location and custom reciprocal toolbars are optional. |
| Citation metadata, author search and manuscript citations | Important | Prefer one authoritative bibliography in Zotero over expanding Notable into a reference manager. |
| Existing ToSort review and helpful naming for PDF, Word, PowerPoint, patents and difficult metadata | Important | Compare the actual useful review steps against Zotero intake. Retain only the missing steps in a helper. Office support currently means sorting, not PDF conversion or tablet transfer. |
| One visible tag system, including useful tablet tags | Desired | Zotero can own visible tags; a tablet import/mapping policy remains necessary. |
| Search handwriting in scientific marginalia | Desired, accuracy unproven | Separate recognition from printed OCR. Preserve the ink and benchmark retrieval on representative handwriting. |
| Automatically generated Word notebooks | Undecided | The user has not used them enough to establish their value. Do not make exact notebook parity a migration veto. Preserve comparison examples and the existing exporter. |
| Typed Boolean box versus Advanced Search controls | Semantics essential; interface not yet settled | Zotero already supports Boolean search. Its grouped Advanced Search differs from Notable's typed grammar. Judge result correctness and ease of use. |
| Zotero main window plus a quiet reliable helper | Explicitly acceptable | Avoid requiring two separate daily library interfaces. |
| Obsidian graphs, backlinks, synthesis; RSS/mobile/groups/Read Aloud; extra readers | Optional | Existing tools can supply these later. They do not justify increasing the initial stack. |
| Automatic propagation of renames, moves and deletions | Scope/policy not settled | Do not quietly equate additions plus annotation return with a complete destructive mirror. Preserve data until an explicit reconciliation policy is selected. |
| Open-source-first research, recoverability and a simple workflow | Essential | Prefer existing components and supported APIs; measure recurring effort, not feature count. |

## What the executed preliminary tests established

Detailed evidence is in the [Notable test report](preflight-notable-2026-10-18/evidence.md), [Zotero runtime report](preflight-zotero-2026-10-18/evidence.md), [plugin/dependency preflight](preflight-plugins-2026-10-18.md), [local API report](preflight-pyzotero-api-2026-10-18.md), and [printed OCR report](preflight-ocr-2026-10-18.md). These reports distinguish measured behavior, source inspection, upstream claims, and remaining tests.

| Area | Preliminary evidence | Decision implication |
| --- | --- | --- |
| Notable baseline | 190 selected existing tests passed; cloud/device clients in these suites are mocked | Existing processing and safety code has reusable value. This is not proof of current real-device compatibility. |
| Dissertation handling | Notable classified/named a synthetic thesis and indexed its final page at 140 pages / 672,075 characters; its citation model discarded university/thesis type and exported generic bibliography types | The deficiency is rich dissertation bibliography, rather than inability to open every dissertation PDF. Zotero should own this metadata. |
| Zotero native library | Signed official portable Zotero 10.0.6 ran in a disposable account-free profile; typed thesis metadata, sibling main/SI attachments, nested collections and tags passed model/API checks | Native Zotero covers core organization and reference management without an attachment-organization plugin. This was not a full interactive UI usability test. |
| Whole-paper Boolean | Zotero matched AND terms across PDF pages and applied NOT across the full attachment; OR/phrase probes passed. Notable's equivalent synthetic probes confirmed its page-level limitation | Use Zotero's existing search capability before developing another full-paper query engine. A typed Scopus parser is a separate UI choice. |
| Long PDF coverage | Zotero's initial defaults were 100 PDF pages / 500,000 text characters; a marker on page 551 was missing by default and found after complete reindex, then after restart | Set deliberate limits and verify coverage; a Thesis item type alone does not make every page searchable. |
| Scans | The same image-only fixture produced no searchable text in native Notable or Zotero | OCR remains required for either route. See the separate executable OCR feasibility results. |
| Existing OCR component | PyMuPDF 1.28.2 plus the official English Tesseract data made searchable copies; two synthetic page renders were pixel-identical at 144 DPI and originals unchanged. Raw rotated OCR failed; orientation normalization passed. Zotero indexed and found the resulting PDF text | A small preprocessing adapter is credible without writing a recognizer. Real scans, equations and column reading order still require evaluation. |
| PDF annotations on disk | Zotero saved a native annotation without changing the source PDF, then exported a PDF with one real highlight; independently verified with PyMuPDF | Native annotations/export are useful, but automatic publication of the latest tablet notes is still bridge work. |
| reMarkable plugin | Released Zotero reMarkable Sync 0.2.0 declares maximum Zotero 9.*, excluding current 10.0.6 | Do not count a current stable plugin-only replacement as ready. Do not force compatibility by merely editing its version limit. |
| Other plugin compatibility | Better Notes and upstream Zotero OCR have tagged manifests allowing Zotero 10; ZotMoov does too. Their end-to-end workflows were not runtime-tested here | They are candidates for specific needs, not a reason to install a large plugin bundle. File organizers are unnecessary under the relaxed storage preference. |
| Python companion dependency | Isolated Pyzotero 1.16.0 import and pip check passed on Python 3.13.1; clean dependency dry-run with Notable requirements.txt resolved without conflicts | Reusing Python processing behind Zotero is technically credible. Dependency resolution is not a working tablet integration. |
| Python companion actual API | Six local API checks passed: seeded reads, simulated permission grant, typed thesis/tag creation, update/reread, PDF upload/reread, and full-text write/readback; 14 guarded requests went only to the disposable localhost instance | The supported Python-to-Zotero integration works in this controlled test. Human consent UI, lifecycle, device synchronization and production key storage remain distinct tasks. |

Zotero's official [10 release description](https://www.zotero.org/blog/zotero-10/) documents grouped search improvements. The [annotation-storage explanation](https://www.zotero.org/support/kb/annotations_in_database) confirms why a copied source PDF does not automatically contain database annotations. The tagged [reMarkable plugin manifest](https://github.com/bpiwowar/zotero-remarkable-sync/blob/v0.2.0/addon/manifest.json) supplies the concrete version gate.

## Route decision

| Route | Preliminary verdict | Reason |
| --- | --- | --- |
| Native Zotero only | Does not meet the full brief | Strong library/citation/search base; no native reMarkable transport or organizational mapping. |
| Zotero plus existing released plugins only | Not ready as a supported current-version replacement | The obvious tablet plugin fails the Zotero 10 version gate; the complete two-direction additions/annotation contract is unproven. Other candidates add platform or workflow constraints. |
| Zotero main library plus focused Notable helper/extension | **Leading route for the next controlled pilot** | Matches the user's accepted interface/storage model, delegates the mature bibliography/search work, and reuses existing tablet/ink/intake code. The API and OCR preflights reduce technical uncertainty. |
| Continue standalone Notable plus citation manager | Keep as the working fallback | Preserves current workflow; still needs core Boolean, OCR, bibliography handoff, synchronization and annotated-PDF publication improvements. It creates more overlapping library/search functionality to maintain. |
| Obsidian, Paperless-ngx, Recoll or another broad combination | Specialist components only for now | Useful synthesis, ingestion or search tools; none of the assessed alternatives establishes the complete Windows/reMarkable research workflow with fewer moving parts. |

This is a recommended **pilot direction**, not a claim that a finished Zotero/Notable hybrid already exists or that migration is safe today. No numerical feature score can substitute for passing the tablet gate.

## The smallest proposed division of responsibility

1. **Zotero owns the visible library:** source types, dissertation fields, author/title/DOI metadata, collections, tags, paper/SI relationships, printed full-text index, notes, citations and bibliographies.
2. **One bridge owns tablet coordination:** stable Zotero-item ↔ tablet-document mappings; collection/folder correspondence; new-file additions; annotation refresh; retries; current annotated-PDF publication; useful tablet-tag import. Reuse an existing maintained bridge if it passes the required versions and workflow. Otherwise adapt the useful Notable engine behind supported Zotero interfaces.
3. **Reuse an OCR engine for scans:** preprocess copies, preserve page geometry and originals, reindex results. Benchmark orientation and reading-order outliers. This is independent of the library UI.
4. **Retain special intake only where it saves real effort:** Office naming, patent/dissertation identification, hard metadata review and the user's essential naming conventions. Do not recreate Zotero's native functions or carry forward the exact Notable UI for its own sake.
5. **Keep optional exports optional:** evaluate Word notebooks against grouped Zotero notes before adding Better Notes. Obsidian can be an ordinary future export destination, rather than another required daily application.

Zotero's [local API](https://www.zotero.org/support/dev/web_api/v3/local_api) and [plugin interface](https://www.zotero.org/support/dev/client_coding/plugin_development) provide integration routes. Do not write directly into its SQLite database. A helper must explicitly handle Zotero being closed: pause/queue and reconnect, rather than claiming that an unavailable local API is always running.

## Remaining gates before committing or migrating

These are acceptance tests, not requests to start broad new development:

- **Real tablet loop:** record device/firmware, use a dedicated test subtree and copied article/dissertation/scan, create organization/PDFs on each side, add real ink/highlights, refresh twice, restart, and check placement, latest-version access, duplicates, retries and unwanted annotation write-back. Source/manifest claims and mocked tests cannot replace this.
- **Real search corpus and usability:** use known-answer queries on representative scientific PDFs, long theses and OCR outliers; compare grouped Advanced Search with typed queries. Set index limits and surface partial/unindexed files. Confirm whether article+SI should match as one family or separate attachments.
- **Handwriting retrieval:** use representative scientific ink with known keywords; measure misses/false hits, preserve image/stroke provenance and state any external service/model requirements. No handwriting accuracy claim follows from the printed OCR trial.
- **Migration and recovery:** test copied Mendeley exports/attachments and a copied current manuscript, compare counts/fields/citation compatibility, and restore a test backup. Existing Mendeley Cite manuscript fields are a separate compatibility question from importing a library.
- **Only if valued after comparison:** exact ToSort steps, automatic Word notebook regeneration, and automatically published ordinary disk copies. The original current-PDF update requirement remains in scope until the user explicitly simplifies it.

Until those gates pass, continue ordinary work in the existing system. The useful Notable work is the tested reusable processing and coordination; the evaluation argues against spending further effort duplicating a mature reference manager's general library features.
