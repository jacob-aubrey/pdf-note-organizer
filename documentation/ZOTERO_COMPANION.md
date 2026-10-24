# Zotero companion: implementation and validation

**Superseded user interface:** the October 20 implementation is a graphical
Zotero plugin with a bundled helper. See [Notable for Zotero](ZOTERO_PLUGIN.md).
The CLI examples below are historical developer-pilot instructions, not the
intended user setup or everyday workflow.

Updated October 19, 2026. The proposed route now has working code: **Zotero owns the library and citations; a Python companion handles the tablet workflow; a tiny Zotero extension supplies safe annotation refresh.** The first physical-tablet annotation round trip has passed. This is a controlled developer pilot. The installed Zotero 9 application and production library have not been upgraded or migrated.

The [114-capability triage](research/preflight-capability-inventory-2026-10-18.md) and [open-source function map](research/2026-10-18-open-source-function-map.md) remain the scope comparison. Existing Notable Inbox/Office naming and exporters remain available. Optional Word notebooks and Obsidian are not migration requirements; native tablet notebooks are outside the agreed scope.

## Implemented behavior

| User outcome | Implementation and measured boundary |
| --- | --- |
| Corresponding collections/folders | Explicit Zotero/tablet roots; parent-first additions both ways; stable IDs; unique same-name sibling folders can link. Nested and live cloud trials passed. |
| New PDFs in either direction | Zotero child PDFs upload once; tablet PDFs create Zotero references/attachments. Repetition did not create duplicates or feed returned PDFs back to the tablet. |
| A current PC PDF with tablet notes | Later tablet revisions refresh the same managed Zotero attachment key. The physical-tablet sample returned 37 ink objects and one highlight, survived repeat/restart and offline saved-source replay. Original baselines, raw layers and previous prepared versions remain separate. |
| Main text and SI nearby | Existing Zotero child PDFs, including SI, return under their original bibliographic parent. A Thesis record and its two PDFs were tested. |
| Citation/dissertation metadata | Existing Zotero metadata stays authoritative, including native Thesis fields. New tablet-only papers initially get a generic reference/title unless explicit metadata is supplied; automatic recognition is not implemented here. |
| Whole-paper and annotation text search | Every PDF page, highlight quotations, typed comments and saved Notable transcripts enter Attachment Content/Everything. A 125-page, 700,020-character fixture and restart retrieval passed. |
| Optional automatic handwriting search | Local RapidOCR/PaddleOCR transcription supplies unverified search text. Zotero retrieved a word appearing only in the user's real handwriting, including after restart. The selected model recovered 7 of 8 reference words in this one sample; precision on scientific notes is not established. |
| Native highlights/comments | The extension invokes Zotero's own external-annotation importer after upload; repeated import and later refresh were tested. |
| Scanned/screenshot PDF search | Optional cached PyMuPDF/Tesseract OCR supplies index text without changing PDF bytes. Upright and metadata-rotated scans were retrieved in real Zotero. |
| One visible tag selector | Tablet document/page tag names enter Zotero's existing tags; user tags are preserved. Page tags currently become paper-level discovery labels. |
| Quiet operation | Remembered Zotero grants use Windows DPAPI. Connect is interactive; watch never opens authorization dialogs. Stop, bounded backoff, expired permission and interrupted upload/index/reader recovery have tests. |
| Opening the paper reaches current notes | The extension substitutes the explicitly linked tablet view for the original PDF Zotero would otherwise open. Unrelated references retain native ordering. Originals and SI remain accessible. |

The [validation record](research/2026-10-18-companion-validation.md) links executable results and distinguishes actual cloud/Zotero trials from synthetic cases. It does not establish a finished user interface or a completed production migration.

## Why a small extension is included

Runtime testing found that `/children` does not enumerate annotation objects. An explicit annotation-item query returns them but omits the internal `annotationIsExternal` flag. A plain local API client therefore cannot distinguish embedded tablet marks from independent desktop annotations reliably. Blocking every annotation also blocked ordinary refresh after opening the PDF.

The two-file [support extension](../zotero-support/bootstrap.js) exposes only managed-attachment counts and invokes **Zotero's existing PDF importer**. It inherits local API enablement, normal write authorization and instance checks; its read endpoint also requires a pinned instance. POST requires the user's write grant. It adds no remote service, account token, competing tag screen, direct database access or citation engine.

The extension also adjusts native preferred-attachment lookup only for an explicit original-to-tablet-view link. This preserves Zotero's original choice between main text and other PDFs while opening the current notes. These internal hooks are version-sensitive: the manifest is deliberately limited to Zotero **10.0.*** and must be retested before widening compatibility.

External PDF **ink stays embedded in the PDF**. Zotero 10.0.6 imported the fixture's highlight and typed sticky note as native external annotations, but did not create a native ink annotation from its Ink object. This matches the [upstream explanation of external Ink/FreeText imports](https://forums.zotero.org/discussion/126434/import-annotations-doesnt-work-for-freehand-markup-and-text-notes). Native ink-only filtering is not provided. Saved transcripts and optional machine transcription remain searchable through the separate attachment index.

## Handwriting and printed OCR

Notable can search saved handwriting/OCR text and has optional isolated-ink OCR. The companion preserves that text and source/page provenance. It does not imply that all pen strokes already have an accurate transcript.

A read-only check found **28 eligible annotated cached PDFs, 604 pages, 1,711 highlight objects and 5,306 Ink objects, with zero saved handwriting transcripts in that sample**. The source library stayed byte-identical. The ink is available, but the sample is not evidence of successful recognition. Scientific handwriting needs a known-answer evaluation before a retrieval-accuracy promise. The earlier research did not establish a supported way to export reMarkable's notebook handwriting-search index for annotated PDFs.

The [October 19 handwriting pilot](research/2026-10-19-handwriting-pilot.md) now reuses RapidOCR 3.10.0 / PaddleOCR PP-OCRv6 small on CPU, with ONNX Runtime 1.31.0. It requires an explicit optional setting and three local checksum-validated models, totaling 31,749,509 bytes. The normal helper does not download models. It isolates the ink from printed paper content, retains machine status/page/stroke IDs/regions/confidence/model provenance separately, caches by PDF/model/engine hashes and keeps original PDF bytes unchanged. Recognition failures leave the index operation retryable. A handwriting-only keyword was retrieved in real Zotero and survived restart; its transcript is a search aid, not a reviewed note or reliable mathematics conversion.

Printed OCR is a separate capability. It recognizes substantial raster images/tiles, retains native text, normalizes rotation metadata only in memory, caches complete results by PDF/engine/model hashes, retries failures and checks cancellation between pages. Index-only text does not make PDF Find work in an external reader. Recognition of faint print, equations, difficult columns and physically sideways image content still needs evaluation. Missing printed-text pages appear in publication results.

## Sync and preservation policy

- A selected pair of roots bounds the workflow. State is pinned to that pair and Zotero's actual server ID. Paper identities are never guessed from titles or DOIs.
- Folder and PDF **additions** travel both ways. Confirmed deletions are not recreated. Moves, renames, changed editions and ambiguous primary collections require review; this is not a destructive mirror.
- A Zotero PDF remains the clean original and uploads once. A marked child attachment holds its current tablet view. Returning that marked view never queues another tablet upload. Main/SI stay under one reference.
- Existing Notable source storage retains complete baselines, raw layers, hashes and revision manifests. Previous prepared PDF versions survive interrupted transfers.
- Independently edited PDF bytes and native Zotero reader annotations block replacement at the next check. These checks and API MD5 preconditions are not a universal lock against another editor changing a file during upload; tablet-primary annotation remains the intended workflow.
- Tablet tag removal does not erase reviewed Zotero tags. A user removing an imported tag is respected until it is newly added on the tablet. Exact page-tag navigation and Zotero-to-tablet tag edits are not implemented.
- Offline/closed-app conditions retry quietly. Revoked Zotero permission records `connect_required`; expired tablet pairing records `pair_required`. There is no automatic Windows-login registration.

## Reuse and compatibility

The implementation follows the open-source-first rule. [Pyzotero 1.16.0](https://github.com/urschrei/pyzotero/tree/v1.16.0), BlueOak-1.0.0, supplies the API/upload protocol. [Zotero's supported local API](https://www.zotero.org/support/dev/web_api/v3/local_api) supplies grants, instance IDs, versioned records, file uploads and fulltext writes. Existing Notable cloud CAS, archives, PDF renderer, quotation extraction and source registry supply the tablet processing. Runtime dependencies remain PyMuPDF 1.28.2, Pillow 12.3.0, rmscene 0.8.0 and Pyzotero 1.16.0, without the full GUI/Office/AI stack.

The real-source check exposed compressed erased-stroke records that rmscene 0.8.0 parses but its tree builder omits. Renderer revision **4** now adapts those parsed deletions using the upstream `expand_text_item` ID expansion. Deleted placeholders preserve ordering and stay invisible. Unknown annotation payloads still fail closed, with raw data retained. See the [upstream parser/tree builder](https://github.com/ricklupton/rmscene/blob/v0.8.0/src/rmscene/scene_stream.py) and [ID expansion](https://github.com/ricklupton/rmscene/blob/v0.8.0/src/rmscene/text.py). Regression fixtures cover compressed ranges, author isolation, ordering, erased groups and malformed records.

A short bounded retry handles transient Windows metadata-rename locks. It retries the same atomic rename without deleting the destination or weakening digest-guarded user-file replacement.

The test English model is official `tessdata_fast`, commit `87416418657359cb625c412a48b6e1d6d41c29bd`, SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. Its Apache 2.0 notice/provenance are retained under `.test-tmp/ocr-route-preflight/`. Models are not silently downloaded or bundled. Existing PyMuPDF distribution obligations still apply.

## Developer setup

Use `requirements-zotero-pilot.txt` in a separate environment and a **separate Zotero 10 test profile**. The installed 9.0.3 application was not upgraded. Build the extension using only Python's standard library:

```powershell
python tools/build_zotero_support.py --output ".test-tmp/artifacts/notable-companion-support-0.1.0.xpi"
```

Install it in the selected test profile through Tools → Plugins → Install Plugin From File. Enable local application communication in Zotero's Advanced settings. The automated harness installs/simulates consent only in its own disposable profile.

The current setup surface is a developer CLI. Select existing collection/folder IDs explicitly; the Notable library supplies its saved encrypted tablet pairing and transcripts through read-only access:

```powershell
python tools/zotero_companion.py --state-dir ".test-tmp/my-companion" configure --zotero-root "<collection key>" --tablet-root "<folder UUID>" --notable-library "<Notable library.sqlite3>" --port 23129 --tessdata ".test-tmp/ocr-route-preflight/lang"
python tools/zotero_companion.py --state-dir ".test-tmp/my-companion" connect
python tools/zotero_companion.py --state-dir ".test-tmp/my-companion" run
python tools/zotero_companion.py --state-dir ".test-tmp/my-companion" run --apply
python tools/zotero_companion.py --state-dir ".test-tmp/my-companion" watch
```

Choose **Always Allow** in Zotero's real Connect dialog. Only remembered grants enter the DPAPI vault. `inspect` reads local configuration/status; `stop` requests orderly shutdown via a STOP file. Default polling is 60 seconds, bounded backoff reaches five minutes, and `--cycles` permits a finite diagnostic run. Normal Zotero uses port 23119; disposable trials use 23129. Never configure two helpers against the same roots with different state directories.

Earlier `tools/zotero_pilot.py prepare/publish` commands remain available for one selected Notable logical paper, explicit native bibliographic fields, and main/SI manifest grouping. Publication accepts optional `--tessdata`.

To include optional local handwriting, use `requirements-handwriting-pilot.txt` in the **separate** pilot environment. Run `python tools/prepare_handwriting_models.py --output "<model directory>"` explicitly to prepare the three pinned models with license/provenance files, then add `--handwriting-models "<model directory>"` to the companion's `configure` command. This is a developer setup; it does not enable handwriting recognition in the installed standalone Notable UI. The disabled/default route still imports any saved Notable transcripts.

## Remaining acceptance work

The live trial left one clearly labeled folder, **Notable Zotero validation - safe to remove**, containing two dummy PDFs and two child folders. All pre-existing cloud item hashes stayed unchanged during creation. On October 19, the user confirmed adding physical handwriting and a highlight to its tablet-side PDF. [Nine physical-loop checks passed](research/2026-10-19-physical-tablet-validation.md): the existing Zotero attachment updated, the highlight entered native annotations and library search, repeat sync made no duplicate items, and restart plus offline saved-source replay preserved the result. The continuation rejected all cloud writes. Visual inspection showed the handwritten sentence, equation and correctly placed highlight.

A separate local Tesseract baseline recovered **0 of 8 expected handwritten words** from that sample. The follow-up selected local RapidOCR model recovered **7 of 8**, and [11 checks passed with actual handwriting search enabled](research/2026-10-19-handwriting-search-results.json). No manually read transcript was inserted to make the test pass. These results do not establish accuracy over the whole corpus or reliable equation recognition.

Before switching production: benchmark the selected handwriting recognizer on representative scientific notes; evaluate difficult real scans and more device/page cases; finish a small setup/status experience; verify a copied Mendeley export and actual manuscript; and decide remaining move/rename/deletion policies. The physical device model/firmware was not recorded. Keep Notable for useful special intake and optional exports. **The evidence supports this route, not a “flawless” or migration-complete claim.**
