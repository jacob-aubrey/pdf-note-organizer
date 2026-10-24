# Notable, Obsidian, and the research-software ecosystem

Research date: October 18, 2026. Research only; no integration was implemented.

## Decision

Continue optimizing the current app. There is a credible reason for Notable to exist, but that reason is the particular research workflow it brings together, not the novelty of PDF search, tags, metadata lookup, or annotation extraction individually.

Obsidian could be useful as a place to write and connect ideas after Notable collects the evidence. The first connection worth considering later is an ordinary Markdown export with images and source references. It does not require a custom Obsidian plugin, a new account, or continuous synchronization.

Zotero is the strongest existing alternative and potential companion. Zotero plus note/export and reMarkable extensions deserves a real comparison before we spend substantially more effort expanding Notable. Some of those extensions now overlap directly with work we have built. Their existence does not establish that they reproduce our workflow reliably, and this survey did not run them.

The appropriate conclusion about past work is conditional: **the specialized integration work appears useful; some general-purpose features duplicate existing software; neither the economic value of every development hour nor a complete replacement has been demonstrated.**

## Scope and evidence

This review examined official product documentation and public project repositories across reference management, PDF reading, linked notes, reMarkable conversion, annotation extraction, OCR, document parsing, search, and export. The catalog below contains 48 tools, projects, or standards. They are not 48 competing apps or 48 recommendations to install.

For Notable, I read the current README, requirements, and selected implementation code for extraction, exports, citations, paper identity, combined PDFs, and reMarkable rendering. Relevant local files are [README](../../README.md), [extraction](../../note_organizer/extraction.py), [exports](../../note_organizer/exporting.py), [citations](../../note_organizer/citations.py), [paper identity](../../note_organizer/paper_registry.py), [combined PDFs](../../note_organizer/combined_pdf.py), and [tablet conversion](../../note_organizer/remarkable_pdf.py).

External capabilities below are documented capabilities or project claims, not results from an independent hands-on trial. A public repository, feature list, or large star count is not evidence of compatibility with your actual papers. Some pages could not be fetched, and a documentation page can lag its software. Where maintenance or compatibility was unclear, the recommendation remains provisional. No alternative was installed, no private library was uploaded, and no live tablet or account was changed.

## What the current app actually contributes

| Current capability | Existing overlap | Where Notable's particular implementation matters |
| --- | --- | --- |
| Identify, rename, and file incoming documents | Zotero, JabRef, Paperlib, Papis | Review-driven Inbox; PDF/Word/PowerPoint handling; patent and supporting-information conventions. |
| Read PDFs and search printed text | Zotero, Sioyek, Okular, many others | Integrated results across paper metadata, saved annotations, and PDF pages. This is useful integration, not a novel viewer category. |
| Extract PDF highlights and comments | Zotero, pdfannots, pdfannots2json | Watched folders, persisted results, source-aware note identities, and subsequent notebook updates. |
| Retain drawings and handwriting context | Several note/annotation tools; tablet converters | Grouped drawing close-ups, original page context, and supported margin expansion. |
| Bring PC and tablet annotations under one paper | Some newer Zotero/reMarkable extensions | Independent source histories plus checks before producing a combined reading copy. |
| Produce Word notebooks | Better Notes overlaps; other exports can be converted | Folder-based notebooks with retained images and source-page links, plus handling of externally edited exports. |
| Tags, collections, saved searches | Common in reference and note managers | Already present; adding another organization system would need a clear benefit. |
| Citation exchange | Zotero/JabRef and standard formats | RIS and BibTeX export already exist. Citation formatting is intentionally limited. |
| Verified backup, recovery, retained tablet assets | General tools offer backup/export, with differing scope | App-specific relationships, note history, source material, and recovery workflows are saved together. |

The PC/tablet combination is more than matching titles. The current combined-PDF code checks page mappings and printed content and rejects incompatible editions or changed page sequences. The paper registry keeps independently annotated sources in separate identities. Those are concrete engineering contributions visible in the code. They do not prove that no competitor has similar safeguards.

There are also limits: the embedded reader is read-only; the reMarkable protocol is unofficial; handwritten OCR is optional Tesseract output labeled as a suggestion; printed-PDF search does not perform whole-document OCR. The README explicitly calls for wider real-device validation. These limits should also apply to claims we make about our own app.

## Obsidian, explained without the setup culture

Obsidian is a note editor that can connect notes to one another. A vault is an ordinary folder, and its notes are plain Markdown text files. Other programs can write those files and Obsidian notices the changes. This is why a simple file export can be a useful connection. [Obsidian storage documentation](https://help.obsidian.md/Files+and+folders/How+Obsidian+stores+data)

For example, a paper note could contain the extracted evidence. A separate note called “Potential explanations” could contain your interpretation and links to passages from several papers. Backlinks let you see which other notes refer to the current note. They expose relationships you recorded; they do not independently establish that two findings are scientifically related. [Backlinks](https://help.obsidian.md/Plugins/Backlinks)

It also supports images and PDF embeds, including a particular PDF page. This is relevant because your handwriting and drawings are not adequately represented by text alone. [Embedded files and PDF pages](https://help.obsidian.md/Linking+notes+and+files/Embed+files)

Obsidian is free to use, including for commercial purposes, but its application code is proprietary. Optional services and licenses are separate. We can exchange files with it; we should not assume its app code is available to incorporate. [Official license overview](https://obsidian.md/license)

### Where it could help you

- Writing your own conclusions beside, or separately from, the extracted evidence.
- Connecting one question or hypothesis to passages from multiple papers.
- Maintaining a literature-review outline that reuses those linked passages.
- Keeping text notes readable in ordinary editors if you later change applications.

If you mainly want to find a highlight, see the page, and export a Word notebook, another application may add little. Obsidian becomes more compelling when writing across papers is the missing step.

### A modest future connection

**First version: an explicit “Export Markdown…” action.** It would export one file per logical paper, associated image assets, citation metadata, quotations, comments, and physical source-page references. Obsidian could open that folder. So could other Markdown editors.

Implementation requirements, if this is pursued later:

1. Preserve the distinction between a quotation, your typed comment, handwriting image, and an uncertain OCR suggestion.
2. Give exported papers and note passages stable identifiers; do not identify a note only by a filename or a DOI.
3. Use durable image paths and source references. A temporary combined-PDF cache file must not become a permanent external link.
4. Explain whether a page link opens the original or an exported combined reading PDF. They may show different marks.
5. Start with a new export folder or an explicit refresh. If files become continuously updated later, separate app-generated content from your own writing and detect edits before replacement.
6. Test paths, spaces, renamed papers, duplicate titles, revised notes, and drawing assets. PDF page navigation depends on the receiving viewer; local desktop paths are not automatically mobile-friendly.

The first export need not solve two-way editing. That is a separate feature with conflict and deletion semantics. A text change in Obsidian should not silently alter the extracted evidence or original PDF.

Opening an exported note in Obsidian could later use its built-in URI mechanism. A link back into a specific Notable record would require a Notable link handler that does not currently exist. [Obsidian URI documentation](https://help.obsidian.md/Extending+Obsidian/Obsidian+URI)

### Ideas to borrow selectively

The most relevant ideas are a small personal-synthesis area, explicit links to related papers/passages, and reusable note templates. A graph display is much lower priority: the links and writing must first solve a real task. We already have tags, collections, and saved searches; borrowing those again would not fill a gap.

## The alternatives that most affect the build-versus-adopt decision

### Zotero and Better Notes

Zotero is the first replacement candidate to evaluate because it already handles a large part of ordinary research collection, organization, annotation, and citation work. Its built-in reader can turn annotations into notes with source links. [Zotero repository](https://github.com/zotero/zotero), [reader documentation](https://www.zotero.org/support/pdf_reader)

It can retrieve PDF metadata and rename attachments, so our sorter is not filling an otherwise empty category. Its Word integration also provides editable citations and bibliographies, which our plain citation export is not equivalent to. [PDF metadata](https://www.zotero.org/support/retrieve_pdf_metadata), [file renaming](https://www.zotero.org/support/file_renaming), [word processor integration](https://www.zotero.org/support/word_processor_integration)

Better Notes adds linked notes, templates, Markdown synchronization, and exports including DOCX. This makes it a more serious overlap than merely saying “Zotero manages references.” We would still need to compare its exported notebook organization, image/context retention, and refresh behavior against yours. [Better Notes](https://github.com/windingwind/zotero-better-notes)

A practical integration detail: Zotero's own annotations normally live in its database. Watching the underlying PDF alone does not capture every Zotero annotation. Exporting an annotated PDF or using an appropriate API/plugin is necessary. Conversely, importing external annotations into Zotero can remove those annotations from the PDF as part of transferring them into Zotero. Any future bridge needs an explicit ownership rule. [Zotero annotation storage and exchange](https://www.zotero.org/support/kb/annotations_in_database)

For now, Notable already exports RIS/BibTeX, which gives us a basic citation handoff without a new integration. That transfers bibliographic records, not a live shared annotation database. A future API connection should use supported interfaces rather than modifying Zotero's SQLite database directly. Zotero itself describes direct database access as more fragile. [Zotero API documentation](https://www.zotero.org/support/dev/client_coding/javascript_api)

### Tagged Sync for reMarkable

This Obsidian plugin documents tag-based routing, rendered handwriting, PDF quote extraction, and Zotero connections. Some advanced features are paid. Its code licensing is mixed: Apache-2.0 for the core plugin and different terms for its Pro directory. It is a strong future trial candidate because it directly targets a similar bridge, but this review did not verify its claims on your Windows machine or tablet. [Repository and license description](https://github.com/thomas-hochbichler/obsidian-remarkable-tagged-sync)

### Zotero reMarkable Sync

This project documents sending tagged PDFs and bringing tablet highlights/ink back into Zotero as native annotations. Its README explicitly labels it experimental, describes potential destructive effects, and enables a safer mode by default. It is evidence that a competing workflow exists, not evidence that replacing ours would be painless. Its documented annotation push-back is also broader than our current combined reading/export approach. [Project documentation](https://github.com/bpiwowar/zotero-remarkable-sync)

### reMarkable Connection Utility (RCU)

RCU is a substantial tablet-management and export tool, distributed as paid free software under AGPL terms. It documents real PDF highlight export and Markdown support, with firmware-specific rendering limitations. It could be useful as an external conversion/export companion. It does not establish a replacement for our entire library/search/notebook workflow. [RCU](https://www.davisr.me/projects/rcu/)

### Noteration and Paperlib

Noteration combines Markdown writing, PDFs, Papis literature management, search, and backlinks in a desktop app. It is architecturally close to a possible “research plus linked notes” direction for us. Its advertised features need a real trial; the survey did not establish an equivalent reMarkable workflow. [Noteration](https://github.com/lilamr/noteration)

Paperlib focuses on academic-paper metadata, organization, full-text search, notes, and extensions. It is especially relevant to the sorter/library side. A paper manager can be a good alternative without reproducing tablet-source history and our notebook output. [Paperlib](https://github.com/Future-Scholars/paperlib)

## Broad catalog

“Use” below is my assessment for your workflow, not an independently measured ranking. Links point to the primary project or official documentation. Components already in Notable are identified so they are not mistaken for new integration recommendations.

### Reference management and research writing

| # | Project | Relevant documented scope | Assessment for Notable |
| --- | --- | --- | --- |
| 1 | [Zotero](https://github.com/zotero/zotero) | Collection, organization, annotations, citations, sharing. | Strongest general alternative and citation companion. |
| 2 | [Better Notes](https://github.com/windingwind/zotero-better-notes) | Linked Zotero notes, templates, Markdown sync, several exports. | Strong overlap; compare exact notebook behavior. |
| 3 | [Better BibTeX](https://github.com/retorquere/zotero-better-bibtex) | Bibliographic workflows for LaTeX/Markdown and enhanced exports. | Use within Zotero when needed; match plugin and Zotero versions. |
| 4 | [JabRef](https://github.com/JabRef/jabref) | BibTeX/BibLaTeX reference libraries, metadata and attached documents. | Good citation companion, especially for LaTeX. |
| 5 | [Paperlib](https://github.com/Future-Scholars/paperlib) | Paper metadata, full-text search, organization, notes, extensions. | Strong sorter/library comparison. |
| 6 | [Papis](https://github.com/papis/papis) | Scriptable document/bibliography manager with readable YAML metadata. | Useful interoperability ideas; a CLI adds user burden here. |
| 7 | [Noteration](https://github.com/lilamr/noteration) | Markdown, PDFs, Papis, persistent search, backlinks, Git sync. | Interesting integrated alternative; validate maturity and exports. |
| 8 | [Qiqqa](https://github.com/jimmejardine/qiqqa-open-source) | Windows research manager released as open source. | Research comparison; its release/fork guidance needs care. |
| 9 | [Docear](https://docear.org/) | Literature organization with mind maps and PDF annotation integration. | Useful design precedent; current maintenance was not established. |

### Linked notes and Obsidian extensions

| # | Project | Relevant documented scope | Assessment for Notable |
| --- | --- | --- | --- |
| 10 | [Obsidian](https://obsidian.md/license) | Local notes and extensibility; proprietary application. | Optional synthesis companion through files. |
| 11 | [PDF++](https://github.com/RyotaUshio/obsidian-pdf-plus) | PDF selection links/backlinks, annotation and viewer improvements. | Good passage-linking ideas; some annotations are links rather than embedded PDF marks. |
| 12 | [Obsidian Zotero Integration](https://github.com/community-archive/obsidian-zotero-integration) | Import citations, notes, and annotations; requires Better BibTeX. | Existing bridge; original URL redirects to community-archive. Check support before depending on it. |
| 13 | [Zotero Manager for Obsidian](https://github.com/jsglazer/zotero-manager) | A documented replacement approach with citation and annotation imports. | Additional bridge candidate, not independently tested here. |
| 14 | [Joplin](https://github.com/laurent22/joplin) | General note taking and synchronization across platforms. | Open-source note companion; imported Markdown needs app-specific handling. |
| 15 | [Logseq](https://github.com/logseq/logseq) | Linked knowledge management, PDF annotation, tasks. | Relevant alternative, but distinguish file-based workflows from its newer database beta. |
| 16 | [Zettlr](https://github.com/Zettlr/Zettlr) | Academic Markdown writing, reference integration, exports. | Strong writing companion if linked-note graphs are unnecessary. |

### reMarkable bridges and conversion

| # | Project | Relevant documented scope | Assessment for Notable |
| --- | --- | --- | --- |
| 17 | [Tagged Sync](https://github.com/thomas-hochbichler/obsidian-remarkable-tagged-sync) | Tablet-to-note routing and extraction, with Zotero features. | High-interest trial candidate; mixed free/paid and license scope. |
| 18 | [Zotero reMarkable Sync](https://github.com/bpiwowar/zotero-remarkable-sync) | PDF transfer and native Zotero annotation exchange. | Direct overlap; explicitly experimental. |
| 19 | [remarkable-zotero-cli](https://github.com/Milofax/remarkable-zotero-cli) | Maps visible tablet-export highlights onto clean PDF/EPUB files. | Useful algorithm/reference tool; handwritten semantics remain limited. |
| 20 | [RCU](https://www.davisr.me/projects/rcu/) | Tablet management, backups and document export/conversion. | External companion candidate; check device/firmware features. |
| 21 | [Remy](https://github.com/bordaigorl/remy) | Local/SSH tablet manager. | README explicitly excludes software v3/v6 format; poor current replacement candidate. |
| 22 | [rmscene](https://github.com/ricklupton/rmscene) | Reads reMarkable v6 scene data. | Already a Notable dependency; continue benefiting from upstream fixes. |
| 23 | [rmc](https://github.com/ricklupton/rmc) | Converts v6 scene files to/from other representations. | Rendering/conversion reference; benchmark difficult pages before reuse. |
| 24 | [rmapi, ddvk fork](https://github.com/ddvk/rmapi) | Command-line access to tablet files through the cloud API. | Protocol/reference option; avoid adding a second sync engine without a need. |
| 25 | [reMarkable MCP](https://github.com/SamMorrowDrums/remarkable-mcp) | Tablet-data access, text extraction, cloud/local integrations. | Our README already credits its protocol documentation. |

### Reading, annotations, archiving, and search

| # | Project | Relevant documented scope | Assessment for Notable |
| --- | --- | --- | --- |
| 26 | [Sioyek](https://github.com/ahrm/sioyek) | Research PDF navigation, quick reference/figure access. | Borrow navigation ideas selectively or use externally. |
| 27 | [Okular](https://okular.kde.org/) | Document reading and annotation. | Existing external-reader option rather than an embedded rewrite. |
| 28 | [Xournal++](https://github.com/xournalpp/xournalpp) | Pen-oriented notes and PDF annotation. | Useful external handwriting tool; its native project/export semantics differ from PDF annotations. |
| 29 | [Librum](https://github.com/Librum-Reader/Librum) | Book library, reading, highlights and synchronization. | Lower research fit; distinguish advertised and “coming soon” features. |
| 30 | [Paperless-ngx](https://github.com/paperless-ngx/paperless-ngx) | Searchable document archive and ingestion. | Borrow ingestion/OCR ideas; deployment adds infrastructure. |
| 31 | [Paperwork / OpenPaperwork](https://github.com/openpaperwork) | Personal document management and OCR. | Adjacent scanner/archive workflow; GitHub projects point to GNOME GitLab. |
| 32 | [Hypothesis client](https://github.com/hypothesis/client) | Web-based annotation client. | Relevant if shared annotation becomes a requirement; different architecture. |
| 33 | [Recoll](https://www.recoll.org/) | Desktop full-text retrieval across document collections. | External search alternative; not a paper-source/notebook system. |

### Extraction, OCR, rendering, and export components

| # | Project | Relevant documented scope | Assessment for Notable |
| --- | --- | --- | --- |
| 34 | [pdfannots](https://github.com/0xabu/pdfannots) | PDF annotation extraction to Markdown/JSON. | Strong evidence that basic extraction need not be invented; useful comparator. |
| 35 | [pdfannots2json](https://github.com/mgmeyers/pdfannots2json) | Annotation JSON and image extraction. | Reference/comparison option; another binary and dependencies may not simplify our app. |
| 36 | [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) | Searchable text layers for scanned PDFs. | Best focused candidate if image-only papers become a frequent problem. |
| 37 | [Tesseract](https://github.com/tesseract-ocr/tesseract) | OCR engine. | Already optionally invoked by Notable for isolated ink. |
| 38 | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | OCR and document-understanding toolkit. | Benchmark candidate; do not assume handwriting accuracy or low deployment cost. |
| 39 | [Docling](https://github.com/docling-project/docling) | Layout, reading order, tables, OCR, structured exports. | Candidate for troublesome documents, not an automatic core replacement. |
| 40 | [GROBID](https://github.com/grobidOrg/grobid) | Scholarly metadata, references, sections and structured text. | Useful if DOI/metadata failures justify a service/model dependency. |
| 41 | [MinerU](https://github.com/opendatalab/MinerU) | Complex document conversion to structured representations. | Heavy optional parser; current license includes additional conditions. |
| 42 | [Marker](https://github.com/datalab-to/marker) | PDF-to-Markdown/JSON with layout and OCR models. | Benchmark only if needed; code and model-weight terms differ. |
| 43 | [PyMuPDF4LLM](https://github.com/pymupdf/PyMuPDF4LLM) | Markdown-oriented document extraction. | A possible structured-text addition; not annotation identity/history management. |
| 44 | [PDF.js](https://github.com/mozilla/pdf.js) | Browser PDF rendering/reading. | Already bundled in Notable; a major example of existing reuse. |
| 45 | [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF reading, extraction, rendering, manipulation. | Already our core PDF engine. |
| 46 | [pypdf](https://github.com/py-pdf/pypdf) | Python PDF operations, including annotation access. | Already a dependency; avoid introducing another parser without a concrete gain. |
| 47 | [Pandoc](https://github.com/jgm/pandoc) | Converts markup/document formats and supports publication workflows. | Potential future export aid; our existing tailored Word layout may still be preferable. |
| 48 | [Citation Style Language](https://citationstyles.org/) | Shared citation-style ecosystem. | Prefer established citation tools/styles over writing a new formatter. |

## What is worth incorporating, and when

| Priority after current optimization | Idea | Actual benefit | Cost or condition |
| --- | --- | --- | --- |
| First candidate | One-way Markdown plus images export | Portable notes; opens a route to Obsidian and other editors. | Define stable identities and refresh behavior; leave personal writing intact. |
| Use what exists | RIS/BibTeX handoff to Zotero or JabRef | Citation management without rebuilding it. | Metadata exchange is not annotation sync. |
| Evaluate before more expansion | Zotero + Better Notes + one tablet bridge | Tests whether an existing stack is sufficient. | A trial must use representative copies and the real output you need. |
| Only if writing is the bottleneck | Small synthesis area or related-passage links | Helps turn collected evidence into your own argument. | Keep distinct from source quotations and uncertain OCR. |
| Only if scanned papers are common | External/optional OCRmyPDF preprocessing | Makes image-only pages searchable. | Whole-document OCR and handwriting recognition are different problems; verify annotations/page coordinates after conversion. |
| Only after measured extraction failures | Docling or GROBID fallback | Better layout/metadata on hard documents. | Model/service footprint and startup/processing costs. |
| Selective ongoing learning | pdfannots, rmc, Sioyek | Comparison outputs, conversion edge cases, navigation ideas. | Adopt a specific improvement rather than integrating whole applications. |
| Defer | Two-way Obsidian/Zotero/tablet syncing, knowledge graph UI, always-on AI | Could support future workflows. | Multiple editing authorities, conflict handling, dependency burden, and distraction from current reliability. |

OCRmyPDF adds a text layer to scans and documents its external dependencies. It is not a promise of reliable handwritten scientific notation. [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF)

Docling and GROBID address different failures: document layout/structure versus scholarly metadata and references. We should collect actual failing examples before selecting either. [Docling features](https://github.com/docling-project/docling), [GROBID features](https://github.com/grobidOrg/grobid)

## Reuse without turning Notable into a collection of plugins

There are three different choices: exchange standard files with another app; run a focused external tool; or incorporate its code. The first often gives most of the benefit with the least maintenance. A separate command-line converter can still require installation, dependency updates, error handling, and compatibility work.

We are already reusing substantial open-source components: PDF.js, PyMuPDF, pypdf, python-docx, watchdog, Pillow, rmscene, and others. The custom work mostly joins these components into your workflow. “Use open source” does not require replacing that integration with someone else's whole app.

When incorporating actual code, inspect the selected version and its dependencies. Relevant examples from this survey:

- PDF++ and pdfannots identify MIT licenses; rmc also identifies MIT. [PDF++](https://github.com/RyotaUshio/obsidian-pdf-plus), [pdfannots](https://github.com/0xabu/pdfannots), [rmc](https://github.com/ricklupton/rmc)
- Better Notes and Zotero reMarkable Sync identify AGPL licenses; RCU describes AGPL terms as well. [Better Notes](https://github.com/windingwind/zotero-better-notes), [tablet sync](https://github.com/bpiwowar/zotero-remarkable-sync), [RCU](https://www.davisr.me/projects/rcu/)
- Tagged Sync distinguishes its Apache-licensed core from differently licensed Pro code. [Tagged Sync licensing](https://github.com/thomas-hochbichler/obsidian-remarkable-tagged-sync#license)
- Docling identifies an MIT code license; individual model terms still need checking. Marker documents separate code/model terms. MinerU currently describes an Apache-based license with additional conditions. [Docling](https://github.com/docling-project/docling), [Marker](https://github.com/datalab-to/marker#commercial-usage), [MinerU](https://github.com/opendatalab/MinerU#license-information)

These are selection considerations, not a full license audit or a reason to stop ordinary file interoperability.

## How to answer “Was it worth building?” later with evidence

The unfair comparison is Notable's whole development history against a competing product's download button. The useful comparison is the future effort and day-to-day friction from here.

If we later evaluate alternatives, use a small copied set of representative papers: some with PC highlights/comments, some with tablet handwriting/highlights, and some annotated in both places. Include a multi-column article, a figure-heavy page, margin writing, supporting information, and an intentionally mismatched edition.

Perform the same sequence in each workflow: identify/file, retrieve the paper, find an annotation across the collection, inspect its original context, bring PC/tablet evidence together, export the Word result you actually use, make another annotation, and refresh. Record manual steps, elapsed user time, omissions, duplicates, link failures, and recovery after an interrupted refresh.

Compare at least Notable, Zotero plus Better Notes, and the same Zotero stack with the most suitable tablet bridge. Add Obsidian only if synthesis writing is part of the task. Reject a replacement if it loses the evidence or requires more recurring manual repair, even if its feature list is longer. Prefer an existing stack if it produces the required result with substantially less future maintenance.

That experiment could support keeping Notable, narrowing it to a specialist bridge, or replacing more of it. Past effort alone should not decide. The present research supports finishing optimization and preserving a small future integration path; it does not support a rewrite or a broad feature expansion now.
