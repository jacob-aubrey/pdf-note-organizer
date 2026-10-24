# Notable preliminary testing evidence — October 18, 2026

## Result and scope

**190 selected existing tests passed, with no failures or skips reported.** Separate synthetic probes confirmed that Notable handles thesis/dissertation PDF classification, naming, reading text and full-text indexing, including a 140-page document with 672,075 extracted characters. Its bibliography schema does **not** provide a proper dissertation record: university, degree/thesis type and reference type are discarded, and citation export uses generic/article types.

These are preliminary, local tests of existing behavior. They do not establish live reMarkable compatibility, handwriting recognition accuracy, handling of every real dissertation, or an alternative application's parity. Passing a regression that expects page-level Boolean search confirms current behavior, even when that behavior falls short of the user's whole-paper requirement.

No application source was changed. No personal documents, existing app library, Zotero profile, tablet account or private credentials were used. Fixtures, SQLite databases, transcripts and scripts were written only within this new research directory. Python bytecode writes were disabled. Temporary test libraries were directed to its `scratch` subdirectory. No GUI suite was run. Cloud clients in the selected tablet suites are synthetic/mocked; those suites exercise coordination and rendering without pairing or performing actual cloud transfers.

Inspected: root `AGENTS.md`, current README, the three existing October 18 research reports, and selected implementation/test files. The existing open-source comparison remains the candidate inventory; this evaluation did not implement or replace a subsystem.

## Reproduction and complete transcripts

Working directory:

```text
C:\Users\jdaub\OneDrive\Desktop\Documents\PhD\Bonitatibus Research\Python Code\PDF Note Organizer
```

Commands executed:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; .\.venv\Scripts\python.exe -B documentation/research/preflight-notable-2026-10-18/run_preflight.py
$env:PYTHONDONTWRITEBYTECODE='1'; .\.venv\Scripts\python.exe -B documentation/research/preflight-notable-2026-10-18/probe_long_dissertation.py
```

The first script runs the following individual commands with the project's Python, `-B`, and isolated `TEMP`/`TMP`. Exact absolute executable arguments, elapsed process times and machine-readable probe output are in [results.json](results.json). Every selected test name and final status is retained in the corresponding log.

| Command after `python -B -m unittest` | Tests | Result | Process elapsed | Transcript |
| --- | ---: | --- | ---: | --- |
| `tests.test_research_features.ResearchTests -v` | 27 | Passed | 16.00 s | [group-1.log](group-1.log) |
| `tests.test_search_accuracy -v` | 11 | Passed | 3.74 s | [group-2.log](group-2.log) |
| `tests.test_supplement_integration.SupplementIntegrationTests -v` | 22 | Passed | 16.06 s | [group-3.log](group-3.log) |
| `tests.test_cloud_outbox -v` | 37 | Passed | 23.18 s | [group-4.log](group-4.log) |
| `tests.test_remarkable -v` | 45 | Passed | 49.67 s | [group-5.log](group-5.log) |
| `tests.test_combined_pdf -v` | 43 | Passed | 36.82 s | [group-6.log](group-6.log) |
| `tests.test_sorting_citations_and_recovery.CitationTests -v` | 5 | Passed | 5.00 s | [group-7.log](group-7.log) |
| **Total** | **190** | **All passed** | **150.47 s** | |

The SI Inbox test class was excluded because its existing setup explicitly creates its temporary libraries under the repository's separate `tmp` folder. The selected SI class instead uses standard temporary directories, redirected into this evidence folder. This is a deliberate isolation boundary, not a claim that the excluded tests fail.

## Direct synthetic requirement probes

The reproducible [run_preflight.py](run_preflight.py) creates a two-page dissertation: page 1 contains `nanoparticle`; page 2 contains `catalysis`.

| Probe | Actual result | Implication |
| --- | --- | --- |
| Local dissertation identification | `thesis_dissertation` | The sorter already recognizes the category. The heuristic checks the beginning of extracted text; it is not validated document understanding. |
| Default dissertation filename | `A_synthetic_nanoparticle_dissertation_2025_Thesis_or_Dissertation.pdf` | Generic reviewed naming works; rich bibliography remains a separate concern. |
| `nanoparticle` | Page 1 | Ordinary word search works. |
| `catalysis` | Page 2 | Both pages were indexed. |
| `nanoparticle AND catalysis` | No result | Current AND is evaluated within one page, so it does not satisfy whole-paper Boolean search. |
| `"synthetic nanoparticle"` | Page 1 | Quoted phrase search works in this fixture. |
| `nanoparticle NOT catalysis` | Page 1 | NOT is also page-level. A whole-paper query would exclude this paper, because page 2 contains the excluded term. |
| `nanoparticle OR catalysis` | Pages 1 and 2 | Results are matching pages, with source navigation. |
| A screenshot-only PDF containing the same visible text | No result; warning: “No searchable text layer. Scanned pages need OCR before PDF text search.” | Whole-document OCR preprocessing is required. A renderer displaying a scanned PDF does not make its text searchable. |
| Search does not change source bytes | True | These probes read/index originals without rewriting them. |
| Citation normalization preserves university and thesis type | False for both | The citation UI/schema currently retains title, authors, year, journal/venue, volume, issue, pages, DOI, URL. |
| Dissertation citation export | RIS `TY  - GEN`; BibTeX `@misc` for a record without a journal | There is no `THES`, `@phdthesis`, university/degree-aware citation export. A populated venue is treated as journal/article. |

The separate [probe_long_dissertation.py](probe_long_dissertation.py) generated a synthetic text-heavy dissertation and searched a unique token on its final page. Its [machine-readable output](long-dissertation-results.json) reports:

- 140 pages; 672,075 extracted characters; 667,252 characters before the last page.
- Correct `thesis_dissertation` classification and page 140 match; no search warnings.
- First indexing plus search: 1.206 seconds; cached search: 0.025 seconds; one extraction call across both queries.
- Source bytes unchanged.

This single generated document demonstrates coverage beyond 500,000 characters in this code path. It is **not** a performance benchmark for a large real library, scanned dissertations, difficult layouts, huge figures or handwriting. No general file-size ceiling or exhaustive large-document capacity guarantee is inferred. Source inspection also shows a 2,000 matching **PDF-page result** display limit in `research_search.py`; this is not a library storage limit.

## Current capabilities and decision-relevant gaps

The latest user clarification accepts an organized Zotero library and a quiet reliable helper; the exact disk folder arrangement and `_SI` naming are minor preferences. Therefore exact physical co-location, suffix rules and Notable's existing UI should not outweigh the core reading/search/sync workflow.

| Capability discussed | Current Notable position | Evidence in this preflight | Significance for the route decision |
| --- | --- | --- | --- |
| Incoming PDF/Word/PowerPoint review, metadata suggestions, custom names and filing | Implemented; only PDFs proceed to notes/tablet | README and sorter source; five focused citation/naming tests | Retain only naming/filing details the user actually needs. Exact UI parity is unnecessary. |
| Dissertations and theses | PDF handling, classification and generic names work; rich thesis bibliography absent | Direct two-page and 140-page probes; citation source/probe | Zotero can own typed bibliography without discarding useful PDF processing. Do not describe Notable as unable to open any dissertation PDF. |
| Bibliographic fields, DOI lookup, author/title search, reviewed citation conflicts, RIS/BibTeX | Implemented in a limited schema | Research suite and citation source | Consider delegation to the existing reference manager rather than broadening this schema. |
| Journal-style manuscript citations/bibliographies | Not implemented as a CSL citation manager | `citations.py` and prior comparison | A strong reason to use Zotero as bibliography owner. |
| Main text and SI association, persistent attachments and discovery/download | Implemented, with publisher/access limitations | 22 SI integration tests plus research tests | Meets the newly simplified association goal; strict filename/location/navigation parity is not a deciding requirement. |
| Folder hierarchy and collection/tag organization | Watched disk folders, local tags/collections/saved searches | Research suite and README | An organized Zotero UI may satisfy this preference; physical mirroring is no longer assumed essential. |
| Read PDFs and show collected comments/highlights/drawing close-ups and context | Implemented | Research, rendering and combined-PDF tests | Compare visual context and search access on real tablet examples before replacing. |
| Search printed PDF text and annotations | Implemented with scopes, phrase/Boolean parser, cached page text, field filtering | Research/search suites and direct probe | Ordinary search exists; whole-paper Boolean semantics are a material gap. |
| Whole-paper Scopus-like query across different pages | Not implemented | AND/NOT direct probe and existing regression | Core acceptance gate for any direction, including Zotero configuration. |
| Search scanned/screenshot printed PDFs | No built-in full-document OCR | Direct screenshot probe and warning | Reuse an OCR component; do not write a recognizer. |
| Search handwriting reliably | Optional isolated-ink Tesseract suggestions only; no demonstrated reliable recognition | README/source inspection; no handwriting benchmark run | Remains an unresolved recognizer/data-pipeline problem, regardless of library UI. |
| Send new Inbox-filed PDFs to tablet | Implemented, separately enabled | Outbox suite with synthetic cloud | The existing reliable queue may be reused behind a different front end. |
| Automatically send arbitrary new PDFs dropped anywhere in the watched PC tree | Not implemented | `service.enqueue` schedules local work; `filed_pdf`/explicit send call the outbox; outbox module documents no startup walk | A watched folder is not currently a full upload mirror. Zotero import events could provide a simpler future trigger if acceptable. |
| Download tablet PDFs and later annotation revisions | Implemented for supported imported PDF formats | 45 tablet tests using mocked clients and synthetic scene data | Promising reusable engine, subject to actual account/device pilot. |
| Create new corresponding folders in either direction | Implemented, opt-in; baseline old unmatched folders need review | Outbox tests for both directions, nested parent-first creation and stable links | Relevant only to the remaining organization contract. Initial setup and steady-state behavior must be distinguished. |
| Propagate arbitrary renames, moves and deletions as a full mirror | Not implemented | README and source inspection; remote deletion retention regression | New additions do not establish complete bidirectional synchronization. Deletion authority was never settled. |
| Tablet annotations automatically visible in an ordinary durable PC PDF | Not implemented as automatic original-file refresh | Combined suite; explicit export test; source-protection test | Current generated reading views and explicit export work. If easy Zotero access is now acceptable, automatic disk publication may become optional. |
| Native reMarkable notebooks and EPUB notes | Not downloaded into the supported PDF annotation pipeline | `test_mapping_promotes_review_and_skips_native_notebooks`, README | “All notes” requires clarification if it includes tablet-native notebooks, rather than only notes on literature PDFs. |
| Unified reMarkable and app tags | Local labels exist; tablet tag import absent | Source/README; cloud upload initializes tag arrays but no completed import UI | A shared visible tag system still requires integration. |
| Drawing grouping, margin expansion, original context, stable source identities, history | Implemented for supported geometry/formats | Combined and tablet regressions; research tests | Preserve the useful source/geometry protections in any reused engine. |
| Word folder notebooks, filtered exports, editable copies and safe regeneration | Implemented | README/source inspection only in this preflight | No notebook/export suite or Better Notes comparison was executed here; do not claim exact parity has been tested. |
| Plain Markdown/Obsidian synthesis connection | Proposed, not general delivered export | Prior research and README | Lower priority than core tablet reading/search; an ordinary export is preferable to another mandatory UI. |
| Verified backups, restore and history-preserving storage maintenance | Implemented in current app | README/source inventory, not backup suite in this run | Preserve recoverability in a migration plan; this preflight does not independently validate restores. |
| Windows portable launch, embedded reader and diagnostics | Implemented | Existing README; no native UI launch in this run | Windows compatibility of replacement plugins still needs a real isolated runtime trial. |

## Remaining tests that require other evidence

1. Use the current real reMarkable firmware and an isolated tablet test folder to round-trip one article, one scanned article and one dissertation PDF, add ink/highlights/tags, update and restart. The local synthetic suites cannot establish the current unofficial cloud API or every pen/geometry behavior.
2. Compare the chosen Zotero/plugin runtime with equivalent synthetic documents: typed thesis fields, full-paper AND/NOT across pages, SI association, search coverage, annotation import, ordinary access and restart behavior. Published capabilities and plugin manifests alone are not test results.
3. Benchmark handwriting with representative consented samples, including equations and scientific abbreviations; measure keyword retrieval, retain the original ink and distinguish uncertain transcripts. No accuracy result exists from this preflight.
4. Try an existing OCR pipeline on representative scans before/tablet annotation, checking both searchable text and page alignment. This run intentionally verified the present gap without installing a dependency or rewriting a source PDF.
5. Exercise actual export/update behavior if Word notebooks, standalone annotated disk PDFs or Obsidian become selected requirements. Those should not become migration blockers solely because Notable happens to contain them.

The evidence supports keeping the tested Notable processing pieces available while testing a Zotero-centered library. It does not yet justify declaring any full replacement proven, nor continuing every duplicate standalone Notable feature by default.
