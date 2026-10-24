# Paper keywords, reviewable suggestions, and the review list: 0.5.0

## Import completion and authorization

Read-only checks at 17:35 UTC confirmed that the production Windows import
had finished: 486 plan records complete, 87 held back, zero pending eligible
routine records, and zero applying records. Its final native import status
reported pending=false and a completed attachment. Only then did implementation
begin. Production Zotero, its running plugin, its credentials, and the tablet
were not changed by this work. Existing live tags are not rewritten.

## Existing work checked before implementation

The existing PyMuPDF 1.28.2, pypdf 6.19.0, and bounded Office extraction provide
local text and document metadata. They are already packaged, with their licenses
in the existing notices. PyMuPDF is reused for fast, bounded PDF front matter;
printed keyword sections and explicit metadata are evidence, not model guesses.
A small parser is still needed to distinguish those stated terms from inferred
topics and stop at body headings. Scans without usable text produce no invented
keywords and do not trigger OCR or a network service.

[KeyBERT](https://github.com/MaartenGr/KeyBERT) and
[YAKE](https://github.com/INESCTEC/yake) were checked against their actual code,
metadata, and licenses. Both repositories were nonarchived. GitHub reported
KeyBERT pushed August 25, 2026, and YAKE pushed February 11, 2026. KeyBERT is MIT,
but its embedding-based method would introduce another model/runtime path.
It was not selected or independently Windows-tested here.

YAKE 0.7.3 was selected for small, local, unsupervised keyphrase extraction with
no training, model download, corpus download, account, or hosted endpoint.
Its actual wheel source, stopword data, KeywordExtractor API, and native Windows
dependencies were inspected and run on Python 3.13 x64. PyPI requires Python
3.10 or later. The wheel metadata says LGPLv3, whereas its actual LICENSE grants
AGPL-3.0-or-later. The actual LICENSE governs this record and is included without
modification. The companion source archive includes the installed YAKE source
and data, the helper's sources, its pinned requirements, and its build script.
No upstream Windows claim substitutes for the packaged Windows/Zotero tests.

The new dependencies are pinned in requirements-zotero-plugin.txt: YAKE 0.7.3,
Click 8.5.0, jellyfish 1.3.0, NetworkX 3.7, segtok 1.5.11, tabulate 0.10.0, and
regex 2026.9.29. Existing NumPy is retained. Exact licenses are included in the
worker and summarized in ZOTERO_PLUGIN_NOTICES.md. Primary sources:
[YAKE usage](https://inesctec.github.io/yake/),
[YAKE distribution](https://pypi.org/project/yake/),
[YAKE license](https://github.com/INESCTEC/yake/blob/master/LICENSE), and
[KeyBERT API](https://maartengr.github.io/KeyBERT/api/keybert.html).

## Product behavior

- Explicit future imports and filing actions add reliably found stated
  keywords as automatic whole-paper tags. Existing labels and their manual/
  automatic types remain intact. No topic suggestions are silently added.
- Review offers Paper keywords and suggested tags. Finding tags changes no
  native reference; selecting suggestions and saving records a private decision
  until that paper is filed. Keywords are distinct from statistical suggestions.
- Tags offers a title search for stored PDFs, including unlinked papers. The
  user explicitly saves keywords and selected topics for that one reference.
  No mass retroactive operation occurs merely by opening the plugin.
- The proposal records PDF hash, native tag state, source evidence, and a token.
  Saving rejects changed files/tags and unoffered topic names. Accepted labels
  merge additively. Page tags and ink are untouched; whole-paper tags use the
  existing two-way sync after linking. Choosing no suggestions adds no topics.
- Existing vocabulary labels are reused for matching spelling/case, and also
  offered when they occur in the paper. YAKE adds up to ten reviewable English
  text suggestions. These are literal keyphrases, not semantic AI judgments;
  generic terms and imperfect phrases remain possible, so review is required.
- The left review list uses existing CSS grid with size containment and its own
  overflow. The right panel determines its height. Selection/scroll position,
  Home/End and arrow navigation, dynamic detail height, and resizing are handled
  without a new UI library. At narrow widths, the stacked list has a bounded
  height instead of becoming another full-page list.
- The tablet SVG retains its rectangle and replaces its dot with R strokes.
  It reuses existing Lucide styling, attribution, accessibility, and tooltips.
  No logo, font, or image-generation dependency is introduced.

## Validation

The related suite passed 104 tests. New coverage checks keyword section bounds,
metadata provenance, unchanged PDF bytes, scanned/missing inputs, preserved tag
types, explicit acceptance, rejected stale files/tags, unoffered labels, deferred
cloud-review choices, and stated-keyword-only automatic intake. Existing bridge,
page-tag, connection, Unicode transport, and review tests remain passing.

The exact packaged helper/extension passed 30 native/workflow checks in a
disposable Zotero 10.0.6 profile. These include actual YAKE execution from the
frozen runtime, native manual/automatic tag representation, selected/unselected
suggestions, unchanged originals/stored PDFs, and a 160-paper review list with
matching heights, independent scrolling, preserved position, keyboard selection,
dynamic tag controls, and a bounded narrow layout. Zotero omits type=0 when
serializing manual tags; assertions correctly treat an omitted type as manual.

An additional packaged scan/import test verified that new explicit intake adds
two stated keywords and no unsolicited topics, with both original and stored
PDF hashes unchanged. The native title search found the intended stored PDF.
Thirty light/dark/narrow UI and native-menu checks passed. Review-list and R
toolbar screenshots were inspected at real runtime sizes. The final frozen
helper also returned all 140 retained Unicode review records intact.

Evidence is in `.test-tmp/zotero-050-native-02`,
`.test-tmp/zotero-050-unit-results.json`, and the release metadata. The earlier
native-01 fixture failed only an assertion that expected an explicit manual
type field; it is retained as diagnostic history and not counted as a pass.
The source archive contains the worker/extension sources, build scripts, pinned
requirements, original YAKE source/data/license, and tests. Frontend package
entries are checked against their final source bytes. There was no production
installation, live tag rewrite, or real cloud transfer during validation.

The progress-counter denominator remains explicitly deferred.
