# Printed scan OCR preflight

Tested October 18, 2026, on this Windows PC using the project's existing virtual environment. **Printed scan OCR is feasible using the already installed PyMuPDF/MuPDF 1.28.2 and a small official English language-data file.** This experiment did not install an OCR application, invoke a Tesseract executable, modify Notable, touch a real paper, or connect to any private account. It is a component feasibility result, not a completed product feature.

The initial direct-OCR test deliberately remains recorded as a partial failure: the upright page worked, but a page with 90-degree PDF rotation metadata produced garbled recognition. A follow-up that temporarily cleared rotation in an in-memory working copy recovered the expected words. A separately generated searchable PDF preserved the original geometry and displayed pixels in both fixtures.

## Existing work and exact environment

The [official PyMuPDF OCR recipe](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html) documents both page-level OCR and creation of a PDF with an invisible recognized-text layer from a pixmap. A page OCR `TextPage` is an in-memory result; it must be supplied explicitly to subsequent extraction/search calls. It does not automatically save a searchable text layer into the source file.

- Python 3.13.1; Windows 11 build 26100; 64-bit.
- PyMuPDF 1.28.2, MuPDF 1.28.2, already present in `.venv`.
- `shutil.which("tesseract")` returned `None`. Both OCR APIs nevertheless worked directly through the existing bindings with an explicit language-data directory. This does not prove that no executable exists anywhere on the machine; none was required or invoked by this test.
- Downloaded official [`tessdata_fast` English data](https://github.com/tesseract-ocr/tessdata_fast) into the isolated probe directory. The repository licenses its data under Apache 2.0; its license was saved beside the model. PyMuPDF's existing licensing/distribution obligations remain applicable; this is not a new license audit.
- No `pip install`, application installation, environment-variable change or system configuration change was performed. Network access was used only to retrieve the public model and its provenance/license, after the normal sandbox escalation.

| Model provenance | Value |
| --- | --- |
| Upstream commit | `87416418657359cb625c412a48b6e1d6d41c29bd` |
| Exact model | [Pinned official English model](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/eng.traineddata) |
| Download size | 4,113,088 bytes |
| SHA-256 | `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2` |
| Download time | 2026-10-18 22:07:00 UTC |
| Local directory | `.test-tmp/ocr-route-preflight/lang/` |

`tessdata_fast` describes its models as a speed/accuracy compromise, not the highest-accuracy option in every language. Choosing it proves a lightweight existing route can work; it does not establish the best engine/model for difficult papers. [Upstream explanation and data license](https://github.com/tesseract-ocr/tessdata_fast)

## Fixtures and methods

The probe created its own two-page PDF. It rendered generated printed text at 300 DPI into RGB images, inserted those images into a new PDF, and checked that ordinary text extraction initially returned zero characters on both pages. No source text objects were retained in the image-only fixture.

1. Letter-size page, no rotation, title and two sparse columns. Both columns contain `nanoparticle`; the left includes `gold` and the right includes `silver`.
2. Letter-size page with 90-degree PDF rotation metadata, containing the same three keywords. The intentionally sideways displayed text tests recognition orientation and rotation preservation; it does not represent all possible scan orientations.

Three methods were then exercised:

1. Direct `page.get_textpage_ocr(language="eng", dpi=300, full=True, tessdata=...)`, followed by `get_text(textpage=...)` and `search_for(..., textpage=...)`.
2. A searchable **new copy**: reopen the synthetic source bytes in memory, clear page rotation temporarily, render at 300 DPI, use `Pixmap.pdfocr_tobytes(...)`, then restore that page's PDF rotation in the output. The original file is never saved or overwritten.
3. Follow-up direct OCR after clearing rotation on an in-memory working copy. The initial failure was retained in `results.json`; the follow-up has its own `orientation-results.json`.

## Measured results

| Check | Result | Evidence |
| --- | --- | --- |
| Input is genuinely image-only | PASS | Initial extracted text lengths `[0, 0]` |
| Direct OCR of upright page | PASS | `nanoparticle`, `gold`, `silver`: two search hits each |
| Direct OCR of page with 90-degree rotation | **FAIL** | Garbled output; zero hits for all three keywords |
| Direct OCR after temporary rotation normalization | PASS, both pages | Upright page two hits each; rotated fixture one hit each |
| Searchable PDF copy opens with ordinary extraction/search | PASS, both pages | Same expected keyword counts; no `TextPage` override needed |
| Original PDF bytes unchanged | PASS | SHA-256 before and after `9b9b9a581de6a0d082c040cd568e95dd95ce088038bde70d1ee87401d161ada7` |
| Page count, MediaBox, CropBox, display rectangle and rotation retained | PASS, both pages | Letter MediaBox/CropBox `612×792`; output rotations `0` and `90`; exact geometry equality |
| Displayed pixels retained | PASS at the tested 144 DPI | Source/output RGB raster bytes exactly equal on both pages; zero differing color channels |
| Sparse two-column reading order | **LIMITATION** | OCR interleaves same-height lines across the columns rather than reading the entire left column first |
| Recognition of handwriting | NOT TESTED | Fixture contains printed text only |
| Notable/Zotero application indexing of this output | NOT TESTED by this component probe | Ordinary PDF text/search succeeds; application-level indexing is a separate preflight |

The direct page OCR calls took 0.696 and 0.666 seconds. Searchable-page generation OCR took 0.508 and 0.375 seconds. The two follow-up normalized direct calls took 0.423 and 0.334 seconds. The original complete probe took 6.142 seconds including fixture creation, rendering and verification. These are one-run timings on clean synthetic pages, not a library throughput benchmark.

The image-only PDF was 190,307 bytes; the searchable copy was 190,578 bytes. Those sizes are fixture-specific. Small incremental size here is not a promise about large real scans.

## Consequence for route selection

Printed OCR is **not a reason to build another OCR engine or choose standalone Notable over Zotero**. A quiet helper could use this existing dependency to produce searchable copies for either front end. That requires modest application integration and robust file/provenance policy, rather than a new recognition model. OCRmyPDF remains a useful existing alternative when preprocessing, correction and preservation features justify its larger installation footprint.

This probe also corrects the assumption that a separately installed `tesseract.exe` is necessarily required for every OCR approach on this machine. The current Notable isolated-ink implementation may invoke that executable, but the installed PyMuPDF bindings offer a distinct API that worked with explicit local language data.

An **index-only OCR transcript** can avoid changing paper bytes, though a PC PDF opened outside the application would remain textless. A **searchable PDF copy** offers ordinary search in other applications but creates a new file version. Select that behavior explicitly rather than treating the two as equivalent.

## Limits before actual product integration

- Clean synthetic print is easy. No real scans, screenshot compression, faint old text, skew, dense scientific layout, tables, formulas, subscripts, multiple languages or handwriting were evaluated.
- The rotated-page failure shows that calling the OCR API blindly is inadequate. The successful temporary-unrotation step addresses this fixture only; text physically rotated inside an image, unknown orientation and arbitrary CropBoxes need their own tests. Coordinate mapping from normalized direct OCR back into the displayed page was not implemented here.
- The searchable-copy path rasterizes pages. It is a narrow experiment for image-only originals and must not be applied indiscriminately to PDFs containing useful vectors, embedded text, links, forms, accessibility structure, bookmarks or existing annotations. This experiment did not test their preservation.
- Exact RGB equality at 144 DPI and unchanged geometry are strong evidence for these fixtures; they do not prove equivalence at every renderer/resolution or suitability for overlaying every reMarkable edition/page map. OCR before tablet annotation remains the simpler case.
- OCR reading order can alter phrase semantics or snippets even when individual keyword retrieval works. The two-column limitation must be retained in any search acceptance test.
- No OCR scheduling, cache/invalidation, retry UI, app indexing, automatic replacement, tablet upload or duplicate prevention was implemented. No performance claim for an entire dissertation or library is supported.
- Model files need a deliberate packaging/download policy, license notice and integrity check if shipped. This test stores them only under the ignored disposable probe directory.

## Reproduction and artifacts

All test artifacts are under `.test-tmp/ocr-route-preflight/`:

- `download_model.py`, `model-provenance.json`, and `lang/eng.traineddata` plus upstream license.
- `probe_printed_ocr.py`, `results.json`: initial partial failure plus successful searchable-copy checks.
- `probe_orientation.py`, `orientation-results.json`: separate successful orientation-normalized follow-up.
- `synthetic-image-only.pdf`, `synthetic-searchable-copy.pdf`, source/searchable PNG renders for both pages.

The initial script exits with code 1 because its deliberately broad success condition includes raw rotated direct OCR, which failed. Do not report that script as wholly passing. The follow-up exits 0; the searchable-copy branch passed all measured preservation/retrieval checks in the initial run.

```powershell
& .\.venv\Scripts\python.exe .test-tmp/ocr-route-preflight/probe_printed_ocr.py
& .\.venv\Scripts\python.exe .test-tmp/ocr-route-preflight/probe_orientation.py
```

The download script is needed only to reproduce the model fetch; rerunning it resolves the current upstream commit and records a new provenance file. To reproduce this precise model, use the pinned URL and SHA-256 recorded above.
