# Physical tablet continuation

The user confirmed adding handwriting and a highlight to **Notable Zotero validation - safe to remove → Tablet folder → Synthetic tablet-side paper**. The existing recorded tablet UUID and original disposable Zotero profile were reused. No new cloud subtree or paper was created.

The [executed results](2026-10-19-physical-tablet-results.json) contain **nine passing checks** on Zotero 10.0.6:

1. A fresh tablet revision reached the real cloud.
2. The same durable Zotero attachment updated; the clean PDF baselines stayed unchanged.
3. Its PDF retained **37 Ink objects and one Highlight** on one page.
4. Zotero's native annotation list contained the actual selected highlight quotation.
5. The quotation appeared in persisted fulltext and the library's Everything search.
6. Repeating live synchronization reported unchanged publications and retained the same item keys.
7. The updated PDF and highlight search survived closing and restarting Zotero.
8. Replaying the saved source bundles with a transport containing no network client retained the same PDF and attachment without duplicates.
9. The production Notable SQLite file remained byte-identical.

The continuation used a cloud client whose `put` method always raises, and a separate offline replay transport with no upload implementation. Only the existing disposable Zotero profile/state was changed. The installed production Zotero 9 application/library was not upgraded or migrated. Background test processes shut down after the checks. No continuously running watcher or autostart task was installed.

## Visual and source checks

The returned page visibly contains the handwritten sentence, its equation and the yellow highlight over the selected printed text. The original PDF layout remains readable and marks are not clipped. Rasterizing the independent cloud render and the actual returned Zotero PDF at 110 DPI produced identical 910×1287 images, with no differing pixels. This is a visual sanity check for this sample, not a tablet screenshot overlay or a universal coordinate calibration.

The retained scene contains exactly **37 visible Line items and one GlyphRange**, matching the PDF annotation counts. The upstream parser emitted its newer-format warning for additional `SceneInfo` metadata. No unknown annotation payload was accepted: the existing renderer still rejects unknown SceneItem fields. Raw source bytes, including the metadata extension, remain archived. A visually successful sample does not establish support for every future metadata extension.

The user did not supply device model/firmware in this continuation. A fresh physical mark completing the loop is stronger evidence than the earlier cloud-created fixture, but remains one synthetic document on the user's device. Offline replay means use of retained bundles after a Zotero restart; it does not mean a new disconnected tablet edit was tested.

## Handwriting recognition baseline

Preserving Ink and recognizing the words are separate acceptance criteria. The existing Notable `ink_only` helper rendered all 37 ink annotations on a blank canvas, excluding the paper's printed text and highlight. Its crop was passed locally to PyMuPDF 1.28.2's Tesseract binding with the already tested official English `tessdata_fast` model. No document or ink was sent to a hosted recognition service.

A human reading of the eight ordinary words supplied the evaluation reference only. Case-insensitive exact word membership recovered **0 of 8 expected words**. This weak, single-sample keyword-recall metric is not a word-error-rate benchmark; it is sufficient to reject a claim that this baseline already supplies useful handwriting search for this note. Mathematical recognition was not claimed. The [sanitized source/recognition result](2026-10-19-physical-ocr-baseline.json) records the counts and engine; actual reference/transcript text stays in the ignored private trial directory.

No human-read transcript was inserted into Zotero. This initial nine-check run did not enable a recognizer. In the [subsequent handwriting pilot](2026-10-19-handwriting-pilot.md), the optional local RapidOCR adapter recognized a word absent from the clean PDF and Zotero retrieved it after restart; that continuation passed eleven checks on the same physical revision. The new recognizer remains optional and was not enabled on the production library. Its single-sample 7-of-8 word recall is imperfect and does not establish scientific-handwriting accuracy.

## Reproduction and retained artifacts

`tools/test_zotero_physical_roundtrip.py` resumes an existing, explicitly recorded disposable trial. It requires a **new** physical revision relative to that trial's saved mapping and a new output directory. The successful state has now advanced; running it unchanged correctly stops because no newer physical revision exists. Do not roll back the mapping or create another cloud root just to obtain a passing fresh-revision assertion.

The later `--current-revision` option explicitly rechecks the already received revision, with unchanged PDF bytes required. `--handwriting-models` adds the optional recognizer/search checks without requiring another physical pen stroke. That route is recorded separately rather than relabeling the original fresh-revision trial.

The successful command used the existing optional-dependency environment:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) '.test-tmp/pyzotero-preflight/venv/Lib/site-packages'
& .\.venv\Scripts\python.exe -B tools/test_zotero_physical_roundtrip.py --trial .test-tmp/zotero-publisher-live-11 --output .test-tmp/zotero-physical-complete-2026-10-19 --library .local-data/library.sqlite3 --cloud-cache .test-tmp/remarkable-bridge-readonly/blobs --zotero-exe .test-tmp/zotero10-preflight/app/Zotero_win-x64/zotero.exe
```

The ignored output directory retains the exact returned PDF, page image, logs, result JSON and private recognition evaluation. The separate initial read-only render is under `.test-tmp/zotero-physical-2026-10-19/`. Public research records omit account credentials, API keys and handwritten transcript text.

## Decision

The physical annotation-return gate now passes for this sample. The leading direction remains **Zotero for the library/citations, with the focused Python companion and thin Zotero support extension**. Optional automatic handwriting search has subsequently passed a real-sample integration trial. Broader scientific recognition/scan/device coverage, ordinary setup/status controls, copied Mendeley/manuscript migration validation and move/rename/deletion policy remain outstanding. It would be inaccurate to call the overall workflow flawless or production-migrated.
