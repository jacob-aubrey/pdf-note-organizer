# Executed Zotero 10.0.6 preliminary tests

Test date: October 18, 2026. Purpose: compare native Zotero behavior with the user's actual requirements before choosing whether to continue Notable, replace it, or reuse a smaller part behind Zotero.

## Isolation and provenance

- The PC's installed Zotero is 9.0.3. It was not upgraded. The successful trial used the official signed **portable Zotero 10.0.6**, extracted under `.test-tmp/zotero10-preflight/app/Zotero_win-x64/`. Download/hash/signature evidence is in the [package preflight](../preflight-plugins-2026-10-18.md).
- Explicit `-no-remote`, `-profile <disposable-profile>` and `-datadir <disposable-data>` arguments kept the test instance separate. The harness asserted its active data directory before testing. It was not signed in. Account sync, extension updates and automatic Word/LibreOffice integration installation were disabled in the disposable profile.
- All research documents, metadata, annotations and collections were synthetic. No real library, cloud credentials, tablet account, manuscript or real device was used. The temporary database is under this workspace only for testing; its OneDrive location is not a recommendation for production Zotero storage.
- A small test-only extension called Zotero's native JavaScript APIs. This was a headless model/search/export trial, **not an interactive UI usability test or a working Notable plugin**. Synthetic-record UI notifications were suppressed; real UI notification/lifecycle behavior still requires testing in an actual integration.
- The external Python API test used the same disposable instance on **127.0.0.1:23129**, with a request guard forbidding other destinations. Its permission prompt was simulated only in that profile. This does not claim a human authorization dialog was exercised.

## Reproducible inputs and execution

[prepare_probe.py](prepare_probe.py) creates a fresh profile, synthetic PDF inputs and a test extension from [bootstrap.js](bootstrap.js). [run-location.json](run-location.json) records the first successful trial's exact disposable directories; [restart-location.json](restart-location.json) records its follow-up configuration. The source scripts use the project's existing Python 3.13 environment and PyMuPDF.

The source generator was invoked as:

```powershell
.\.venv\Scripts\python.exe documentation/research/preflight-zotero-2026-10-18/prepare_probe.py
```

The portable executable was started with the following arguments, using `Start-Process -WindowStyle Hidden`, redirected standard output/error in the disposable run directory, and a bounded wait that stopped only the test process on timeout:

```text
-no-remote -profile "<recorded profile>" -datadir "<recorded data>" -headless -ZoteroDebugText
```

Follow-up launches added `-purgecaches` after changing the test extension. Both successful local test launches exited normally with code 0. The scripts and JSON are evidence/reproduction aids; they are not application changes.

The synthetic corpus includes PDFs with matching terms together on one page, terms separated across two pages, a sibling SI PDF, a thesis, an image-only version of a text page, and a 551-page sparse thesis with a unique final-page marker. A separate synthetic printed OCR output was imported in the follow-up trial.

## Initial results

[results.json](results.json) contains the successful initial run: **12 probes completed**. Nine report `PASS`; three deliberately confirm a limitation/default behavior rather than pretending that the requested feature passed.

| Probe | Measured result | Implication |
| --- | --- | --- |
| Disposable-profile assertion | Pass; correct directory, not signed in | Results are independent of the user's normal library. |
| Dissertation metadata | Pass; Thesis type retained title, author, year, `university`, `thesisType` | Native bibliography is richer than Notable's limited article-like citation schema. Automatic recognition of an arbitrary real thesis was not tested. |
| Main article + SI | Pass; two titled attachments retained under the same parent article | Meets the user's clarified logical association requirement. Reader-tab ergonomics and publisher-specific auto-discovery were not tested. |
| Nested collections and tags | Pass; a parent/subcollection, multi-collection membership and two item tags persisted in the model | Native organization exists without an external file organizer. Tablet mapping is separate. |
| External linked file | Pass; original external PDF path retained | An available option, but the user does not require this storage model. |
| PDF indexing | Pass; synthetic textual inputs indexed | Does not mean all possible pages/characters were included by default. |
| AND across pages | Pass; both same-page and separate-page terms matched the expected attachment | Whole-PDF Boolean behavior is closer to the requested paper-level search. |
| NOT across pages | Pass; attachments were excluded when a prohibited term appeared elsewhere in the PDF | Unlike the current Notable page-level exclusion behavior. |
| OR and phrase | Pass on the controlled corpus | These were explicit search conditions, not a claim that Zotero's quick-search box parses Notable's typed Boolean grammar. |
| Image-only PDF | Gap confirmed: zero extracted characters; no keyword match | Native Zotero needs an OCR text layer for this fixture. |
| Long thesis | Default limit confirmed: final-page marker not found with `pdfMaxPages=100`; found after complete reindex of all 551 pages | Configure coverage deliberately. `textMaxLength` was also 500,000; this sparse fixture tests the page limit rather than the character-limit path. |
| Native highlight and exported PDF | Pass with workflow limit: source bytes unchanged; export wrote one annotation | A native Zotero annotation is not automatically embedded into the original disk file. Automatic current-PDF publication remains a bridge responsibility. |

The highlight is a synthetic native annotation, explicitly labeled as a stand-in. It does **not** establish that reMarkable stroke/coordinate conversion works. An independent PyMuPDF check found **zero** annotations in the source and **one real PDF Highlight annotation** in the exported file, with matching page count/dimensions: [export-verification.json](export-verification.json).

## Restart, bibliography and OCR follow-up

[restart-results.json](restart-results.json) records four successful follow-up checks:

1. Thesis university metadata and two sibling main/SI attachments remained after shutdown/relaunch.
2. The complete 551-page index still found the final-page marker after restart.
3. Native CSL/APA bibliography output included the university and thesis type:
   `Researcher, T. (2026). Synthetic doctoral dissertation [Ph.D.]. Example University.`
4. Zotero imported the separate synthetic OCR-generated PDF, indexed it, and found `nanoparticle` through its full-text search API.

The first bibliography harness call had omitted `Zotero.Styles.init()` and raised “Styles not yet loaded.” That attempt is retained in [restart-first-attempt.json](restart-first-attempt.json). The corrected call initialized styles and passed. This was a test-initialization issue, not evidence that native thesis citation formatting is unavailable.

Earlier setup attempts exposed test-environment constraints: sandboxed temporary-file moves were denied; the minimal test manifest initially omitted Zotero's required `update_url`; and asynchronous startup/UI callbacks complicated headless synthetic collection creation. The successful run used the complete manifest, waited for UI readiness, and suppressed fixture notifications. An initial Zotero 9 sandbox startup also attempted automatic Word integration, which the sandbox denied; subsequent profiles explicitly disabled automatic Office integration before launch. No production Word integration was intentionally changed. These earlier attempts are not counted as passed capability tests.

## External helper feasibility

The separate [Pyzotero report](../preflight-pyzotero-api-2026-10-18.md) records actual localhost reads, simulated authorization, typed metadata/tag creation, item updates and PDF attachment upload with rereads. The [dependency preflight](../preflight-plugins-2026-10-18.md) records the isolated Pyzotero installation and a clean resolver dry-run alongside Notable requirements.

This establishes a useful supported-interface route for a Python helper. It does not establish stable device mappings, automatic tablet sync, plugin UI behavior, handwritten recognition, or production authorization/key storage.

## Interpretation and remaining limits

The executed tests support **Zotero as the library/bibliography/search front end**, subject to deliberate full-text indexing coverage. Native SI grouping is sufficient under the user's revised preference. An existing OCR component can provide searchable printed text; its orientation/reading-order limits are in the [OCR report](../preflight-ocr-2026-10-18.md).

The hardest remaining acceptance test is the live tablet loop: desktop/tablet organization and PDF additions in both directions, tablet annotation changes returned without duplicates or unwanted PC edits sent back, latest PDF available on PC, unified tags and recovery after disconnect/restart. None of these is established by a metadata/full-text API demo. No production migration should be inferred from this preflight.
