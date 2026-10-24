# Local handwriting search pilot

The hybrid can now optionally recognize ink locally and index that machine text in Zotero. A real word written by the user on the reMarkable was found through Zotero's Everything search, including after restarting Zotero. The clean PDF does not contain that word. The [final integration result](2026-10-19-handwriting-search-results.json) contains **11 passing checks**; these extend and overlap the earlier nine physical-loop checks, so they must not be added as independent coverage.

This is a controlled developer pilot. Nothing was enabled on the production library, the installed Zotero 9 application was unchanged, no tablet writes occurred in the continuation, and no manually read transcript was injected into the index.

## Existing components evaluated

| Local route | Expected words recovered | One measured inference | Decision |
| --- | --- | --- | --- |
| Existing PyMuPDF/Tesseract English `tessdata_fast` baseline | 0 / 8 | Not timed in this handwriting probe | Retain for printed scans; this trial does not support its use for this handwriting |
| RapidOCR 3.10.0, default PaddleOCR PP-OCRv6 small detector/recognizer | 7 / 8 | 0.352 seconds | Selected for the optional pilot; suitable enough to test search, accuracy still imperfect |
| RapidOCR 3.10.0, PP-OCRv5 mobile detector plus English mobile recognizer | 6 / 8 | 0.380 seconds | Existing alternative, weaker on this single sample |

The [benchmark JSON](2026-10-19-handwriting-benchmark.json) records timings, model hashes and repeated-output checks. Initialization took 11.607 / 7.059 seconds respectively in those runs, including model preparation/loading. These are single-sample CPU observations, not library throughput claims. The metric is case-insensitive membership of each human reference word in recognized text, not word-error rate; it does not penalize extra/hallucinated words. One word was misread despite high confidence. No mathematical-notation accuracy is claimed.

Both recognizers received an isolated ink crop generated with the existing Notable `ink_only` helper; the paper's printed text and highlight were excluded. Python network connections were blocked during inference, and ONNX Runtime telemetry was disabled. The separate [actual-adapter offline check](2026-10-19-handwriting-offline-results.json) started the new adapter with explicit local models, recognized the handwriting-only keyword with network blocked, skipped recognition on cached repeat and verified unchanged PDF bytes.

The installed Windows x64 / Python 3.13.1 CPU runtime is RapidOCR **3.10.0** and ONNX Runtime **1.31.0**. The separate combined environment resolved `requirements-handwriting-pilot.txt` and passed `pip check`, including the existing PyMuPDF/Pillow/rmscene/Pyzotero pins. Pyzotero's bibliography parser required its normal source distribution; a preliminary binary-only dependency attempt failed before the successful normal installation. No runtime package was added to Notable's main virtual environment.

## Why reuse this route

[RapidOCR](https://github.com/RapidAI/RapidOCR) supplies the detector, line extraction, orientation classification, recognizer and CPU ONNX deployment. Its [3.10.0 release](https://github.com/RapidAI/RapidOCR/releases/tag/v3.10.0) was published October 8, 2026; this is a currently maintained release, not an abandoned copy. [PaddleOCR documents handwriting improvements in its models](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/module_usage/text_recognition.en.md). The actual Windows result above is the compatibility evidence; repository claims alone did not determine selection.

RapidOCR code and the selected default PaddleOCR-derived model artifacts are Apache-2.0 under the [upstream model attribution record](https://rapidai.github.io/RapidOCRDocs/main/model_licenses/). Model weights belong to Baidu/the respective upstream rights holders; RapidOCR supplies converted ONNX artifacts. The three selected files total **31,749,509 bytes**. [Pinned model provenance](2026-10-19-handwriting-model-provenance.json) records SHA-256 values that match the package's `default_models.yaml` and the upstream default-model attribution table. The explicit preparer retains the installed package's complete source/model license texts and attribution next to the models. Other dependencies retain their own terms, including the pre-existing PyMuPDF obligations.

This avoids building or training a recognizer. The application code is limited to model validation, existing ink isolation, separate transcript provenance/cache, and an attachment-index hook. The new dependency set is optional; default/saved-transcript workflows do not import the recognition runtime.

## Implemented behavior

- `note_organizer/handwriting_ocr.py` validates the three exact local models and the tested runtime versions before using them. It supplies every `model_path` explicitly, bypassing the upstream downloader. Ordinary recognition makes no model download and no hosted inference request.
- Ink is recognized per PDF page, separately from printed OCR. Retained records identify page, stroke IDs, crop region, pixel coordinate space, image/PDF/model/profile hashes, model confidence and unreviewed machine status. Corrections in existing Notable transcripts are not overwritten. Search text is labeled machine-read/unverified.
- The content-addressed cache invalidates when the PDF, model/runtime profile or ink extractor revision changes. Corrupt cache content is rebuilt. A failed/interrupted recognition does not commit a successful empty transcript. Pages with ink but no text result record a warning. The existing original PDF and tablet layers remain intact.
- The companion's optional `--handwriting-models` configuration supplies new text through the existing fulltext publisher. Its index profile triggers reindexing of an already published PDF without reuploading or changing its attachment key. This creates no native Zotero Ink note objects and does not add a second tag interface.

The broader regression run passed **252 tests in 131.476 seconds**. After the final small provenance/diagnostic refinements and an additional cache-profile test, the focused suite passed **72 tests in 17.275 seconds**. Counts overlap. The final real-Zotero integration used that refined adapter and passed all eleven checks.

## Developer setup and reproduction

Use an isolated environment and the separate Zotero 10 test profile described in the [companion guide](../ZOTERO_COMPANION.md):

```powershell
python -m pip install -r requirements-handwriting-pilot.txt
python tools/prepare_handwriting_models.py --output "<model directory>"
```

The explicit preparer reuses RapidOCR's downloader; it processes no paper or note. It checks resulting hashes, preserves the full installed license records and writes a provenance manifest. Existing files with unexpected hashes cause a stop rather than replacement. The ordinary companion accepts only already validated model files. Add `--handwriting-models "<model directory>"` when creating a new companion configuration. No Windows-login task or watcher is silently installed.

The final test command used the optional environment under `.test-tmp/handwriting-rapidocr/venv/` and:

```powershell
python tools/test_zotero_physical_roundtrip.py --trial .test-tmp/zotero-publisher-live-11 --output .test-tmp/zotero-handwriting-search-final-2026-10-19 --library .local-data/library.sqlite3 --cloud-cache .test-tmp/remarkable-bridge-readonly/blobs --zotero-exe .test-tmp/zotero10-preflight/app/Zotero_win-x64/zotero.exe --current-revision --handwriting-models .test-tmp/handwriting-rapidocr/models
```

For a new run choose a new output directory. The test requires that the recorded physical revision is still current; a newer tablet revision must first pass the fresh-revision route. Raw transcripts, cropped ink, full result files and the benchmark script stay in ignored private test directories. Published research JSON omits the note text and account credentials.

## Remaining limits

The sample contains one short sentence and an equation, not the user's scientific corpus. Detection, reading order, abbreviations, corrections, faint strokes, margin layout and equations require representative known-answer evaluation. A high confidence value is not a correctness guarantee. Users can retrieve recognized keywords but may miss misread words or obtain false hits. The primary ink remains the source of truth.

This adds optional handwriting search to the **companion pilot**; it does not retrofit a new recognition engine into the installed standalone Notable UI. Overall production setup/migration and broader device/search acceptance remain the separate gates in the companion guide. No flawless-recognition or migration-complete claim follows from this successful sample.
