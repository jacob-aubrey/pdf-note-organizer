# Sorting source provenance

The following modules were adapted from the user's existing source tree at
`C:\Paper Sorter\src` on October 7, 2026:

- `core_logic.py`: extraction, DOI-first metadata, optional Gemini fallback,
  patent/supporting-information detection, filename formats and validation.
- `document_types.py`: supported documents and Office temporary-file exclusion.
- `metadata_lookup.py`: exact DOI resolution through Crossref and DataCite.
- `patent_metadata.py`: front-page patent fields.
- `presentation_extraction.py`: bounded, safe PPTX extraction and legacy PPT review.
- `key_protection.py`: the Windows DPAPI helper functions from `settings.py`.

Internal imports now use the `note_organizer.sorting` namespace. The existing
sorter's UI, watcher, AppData settings manager, packaging, and executable were
not copied. The combined Inbox owns its own settings and persistent jobs and
never activates the previous sorter's personal folders automatically.

`tests/test_sorting_*.py` ports the existing core, metadata, patent,
presentation, and DOI/AI boundary tests into the same namespace. These tests
use synthetic documents and mocked metadata services; they do not scan the
user's library or contact Gemini/Crossref/DataCite.

The citation and bounded AI retry cases from the original release 1.3.1/1.3.2
tests are also retained. `tests/sorting_fixtures.py` contains only the synthetic
patent-PDF helper from `diagnostics.py`; the packaged-app diagnostics UI was
not ported. The 1,169-byte synthetic CFF font fixture from
`C:\Paper Sorter\assets\diagnostics\cff-font.pdf` is retained as a base64
synthetic fixture in `tests/sorting_fixtures.py` for an offline font-decoding
regression test.
