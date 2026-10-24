# Zotero, handwriting search, and the future scope of Notable

Research date: October 18, 2026. No software was installed, no library was migrated, and no application behavior was changed. The companion function map covers Notable's documented workflows and supporting capabilities separately.

## Recommendation

Zotero is close enough to the desired workflow that it should be evaluated before substantial new Notable development. It is my preferred future citation companion for this project, especially because of its open source, supported local API, and established plugin ecosystem. That is a recommendation for this workflow, not a claim that Mendeley is generally incapable or that an immediate migration is required.

The most promising allocation is:

- reMarkable: authoritative place for handwriting and paper annotation.
- Zotero: authoritative bibliographic records, citation formatting, manuscript integration, and reference relationships.
- Notable, if still needed after a pilot: the particular Inbox rules, physical PC/tablet folder and document coordination, durable annotated PC PDFs, strict SI naming/location, and any note-search behavior the existing stack does not provide.

Obsidian is optional and lower priority for the requirements expressed here. No third full reference manager is needed inside Notable.

## Evidence and limits

The official version history lists Zotero 10.0.6, released October 7, 2026. Its August 2026 major release materially changes the search comparison: nested conditions, annotation-aware searches, and more capable local integration are current features. Some older help pages and plugin READMEs still describe earlier releases. Prefer the versioned announcement and manifest when they disagree with an older overview. [Version history](https://www.zotero.org/support/changelog), [Zotero 10 announcement](https://www.zotero.org/blog/zotero-10/)

This is a documentation and selected-source review, not a complete code/security/license audit or an independent performance benchmark. The existing local README and selected modules were inspected. External code was read where relevant, including Zotero's full-text implementation and plugin manifests. A manifest declaring compatibility does not demonstrate reliability with the user's library. A repository's default branch is not necessarily the code in its latest stable binary.

## Zotero capabilities: comprehensive practical inventory

This inventory covers the main native capabilities and separately identifies extensions. It does not claim to enumerate every menu command or all third-party plugins.

### Collect and identify sources

| Capability | What it provides | Boundary |
| --- | --- | --- |
| Many reference types | Journal articles, books/chapters, reports, theses, proceedings, datasets, patents, web pages, and other records. | Metadata fields depend on record type. |
| Browser capture | Zotero Connector for Chrome, Firefox, Edge, and Safari captures publication metadata and available files. | Publisher/site support varies. |
| Multiple-item capture | Select several records from a supported search-results or catalog page. | Not a license to obtain inaccessible full texts. |
| Identifier lookup | Add records by identifiers such as DOI, ISBN, and PubMed ID, including batches. | An identifier or match still needs to be correct. |
| PDF recognition | Retrieve metadata and create a parent reference for a recognizable imported PDF. | A scan with poor text or an obscure source may need review. |
| Find available full text | Locate available PDFs for existing references. | Availability and institutional/browser access matter. |
| File import | Drag/drop or attach local files; import bibliographic exchange formats. | Plain reference exchange is not a full migration of every annotation and relationship. |
| Manual records | Create or correct bibliographic records yourself. | No tool guarantees correct metadata on every item. |
| Web snapshots | Save a local copy of a web page for later reading. | A snapshot is separate from the live site. |
| RSS feeds | Follow journals/sites and save interesting feed entries. | Discovery beyond the local library, rather than a Scopus replacement. |

Sources: [adding items](https://www.zotero.org/support/adding_items_to_zotero), [PDF recognition](https://www.zotero.org/support/retrieve_pdf_metadata), [feeds](https://www.zotero.org/support/feeds), [basic reference types](https://www.zotero.org/support/quick_start_guide).

### Organize references and files

| Capability | What it provides | Boundary |
| --- | --- | --- |
| Collections/subcollections | Hierarchical project/topic organization; one reference can belong to multiple collections. | Collections are not Windows directories. |
| Tags | Manual/automatic labels, tag filtering, bulk tag changes, and colored tags. | reMarkable tags need a bridge. |
| Saved searches | Automatically updated views of records meeting criteria. | Different from copying files into a folder. |
| Duplicate detection/merge | Identify likely duplicate references and combine reviewed records. | Not a guarantee that two annotated PDFs have identical page geometry. |
| Related items | Link references to other references. | Related records do not automatically acquire a specific on-disk layout. |
| Child attachments | Main PDF, SI, datasets, images, other files, and notes can live under one bibliographic item. | Physical files can still be stored separately. |
| Stored or linked files | Let Zotero manage file copies or link to files at user-chosen paths. | Linked files have sync/group/mobile limitations. |
| Metadata-based renaming | Custom file-name templates and updates following metadata changes. | Does not implement the entire Notable Inbox or strict SI conventions by default. |
| Batch editing and undo | Zotero 10 adds editing across selected records and undo for many operations. | Not every operation is undoable. |
| Recently read | Quickly return to recently read material. | A reading history, not annotation revision history. |

Sources: [collections/tags](https://www.zotero.org/support/collections_and_tags), [duplicates](https://www.zotero.org/support/duplicate_detection), [related items](https://www.zotero.org/support/related), [attachments](https://www.zotero.org/support/attaching_files), [renaming](https://www.zotero.org/support/file_renaming), [Zotero 10](https://www.zotero.org/blog/zotero-10/), [Zotero 9](https://www.zotero.org/blog/zotero-9/).

### Read, annotate, take notes, and search

| Capability | What it provides | Boundary |
| --- | --- | --- |
| PDF/EPUB/web-snapshot reading | Integrated reader and navigation, with external viewers also available. | Does not replace the user's preferred e-ink reading experience. |
| Annotations | Highlights, underlines, comments and other reader annotation tools. | Standard embedded annotations and Zotero database annotations have different storage. |
| Source-linked notes | Build notes from selected annotations or a paper's annotations, retaining citations and source navigation. | A Zotero note is not necessarily the same as Notable's generated folder notebook. |
| Rich-text notes | Child and standalone notes, with formatting and links. | A transcript must first exist to make handwriting searchable. |
| Library full-text search | Search indexed PDF/EPUB/HTML/plain-text content as well as bibliographic information. | Scans need text recognition; Office attachments are not automatically full-text indexed. |
| Advanced logical search | In Zotero 10, nested conditions across records, attachments, notes, and annotations. | Do not assume Scopus's exact typed syntax is accepted in Zotero's quick-search box. |
| Annotation-aware search | Conditions such as annotation type/color/author and relationships to the parent reference. | Imported tablet annotations must be represented appropriately. |
| Index controls | Reindex individual files, rebuild the index, and inspect indexed/partial/unindexed status. | Documented text-length limits need checking for long SI and books. |
| Reflowable PDF Reading Mode | Zotero 10 can present cleaner text while keeping figures/tables and linked annotations. | Layout extraction may need inspection on difficult papers. |
| Read Aloud | Text-to-speech with navigation and annotation-related controls. | High-quality voices have account/network/usage conditions. |

Sources: [reader](https://www.zotero.org/support/pdf_reader), [notes](https://www.zotero.org/support/notes), [search modes](https://www.zotero.org/support/searching), [index settings](https://www.zotero.org/support/preferences/search), [new search/reading features](https://www.zotero.org/blog/zotero-10/), [Read Aloud](https://www.zotero.org/blog/zotero-9/).

### Cite, export, share, and integrate

| Capability | What it provides | Boundary |
| --- | --- | --- |
| Word/LibreOffice/Google Docs integration | Active citations, bibliographies, style changes and updates after metadata corrections. | Existing documents from other citation tools need migration checks. |
| CSL citation styles | Established journal and disciplinary styles, with style installation/editing. | Better to reuse than implement our own style engine. |
| Quick Copy/bibliographies | Copy or drag formatted references/citations; generate a bibliography. | A formatted citation alone is not a live manuscript field. |
| Bibliographic export | Formats such as RIS and BibTeX for exchange and writing tools. | Format-specific fields and relationships may be lost. |
| Annotation/PDF export | Export PDFs with Zotero annotations embedded. | Watching only the original PDF misses annotations stored in Zotero's database. |
| Reports and note export | Generate readable item/notes/attachment reports and export notes. | General DOCX notebook automation is an extension/comparison topic. |
| Data synchronization | Synchronize reference information and notes between Zotero installations and web access. | Separate from attachment file sync. |
| File synchronization | Zotero Storage; WebDAV for supported personal-library workflows. | File storage/service terms are separate from the open-source application. |
| Mobile/web access | Official mobile apps and web-library access. | Features and linked-file support differ from desktop. |
| Group libraries | Shared research libraries and collaboration. | Linked local attachments are not supported in groups. |
| My Publications | Publish a bibliography and selected own research material. | Optional; irrelevant to private literature mirroring. |
| Local/web APIs and plugins | Supported routes for other tools to read and, with appropriate authorization/version, write data. | Prefer supported interfaces over editing Zotero's database. |

Sources: [word processor plugins](https://www.zotero.org/support/word_processor_integration), [citation styles](https://www.zotero.org/support/styles), [bibliographies](https://www.zotero.org/support/creating_bibliographies), [reports](https://www.zotero.org/support/reports), [annotation storage/export](https://www.zotero.org/support/kb/annotations_in_database), [sync](https://www.zotero.org/support/sync), [mobile](https://www.zotero.org/support/mobile), [groups](https://www.zotero.org/support/groups), [My Publications](https://www.zotero.org/support/my_publications), [local API](https://www.zotero.org/support/dev/web_api/v3/local_api).

### Extensions: useful, but not native Zotero guarantees

- [Better Notes](https://github.com/windingwind/zotero-better-notes): templates, linked note workflows, Markdown synchronization, and exports including DOCX.
- [Better BibTeX](https://github.com/retorquere/zotero-better-bibtex): enhanced text-based citation/export workflows. Recent Zotero versions also have native citation-key functionality, so do not install it solely on outdated advice.
- [ZotMoov](https://github.com/wileyyugioh/zotmoov): move/link attachments into chosen directories. Its current source manifest declares support through Zotero 10; that is compatibility metadata, not a tested complete workflow.
- [Attanger](https://github.com/MuiseDestiny/zotero-attanger): attachment matching, naming, and directory organization. It would overlap with Notable's file-management role; select one owner for moves/renames.
- [Pyzotero](https://github.com/urschrei/pyzotero): an existing Python client, including documented local access. This is a much better starting point for a Notable bridge than writing a Zotero client from scratch.
- [Zotero reMarkable Sync](https://github.com/bpiwowar/zotero-remarkable-sync): an experimental tablet bridge. Its README advertises support through Zotero 9, so Zotero 10 compatibility remains to be established.

## How close is Zotero to the user's requirements?

| Requirement | Native Zotero | Remaining question |
| --- | --- | --- |
| Reliable citation library | Strong fit. | Verify imported metadata and manuscript behavior. |
| Search local literature | Strong fit with indexed text and current search improvements. | Exact query semantics, coverage, and source-page result behavior. |
| Search collected annotations | Strong fit when annotations/notes exist in Zotero. | Tablet import and handwriting recognition. |
| Keep article and SI related | Strong logical fit through shared parent item/attachments. | Same disk folder, exact `_SI` names, persistent nearby navigation. |
| Organize by topic/project/tag | Strong fit. | Collections need not correspond one-to-one to physical folders. |
| Two-way creation of PC/tablet folders and PDFs | Not a native feature. | A bridge must meet the complete directory/document contract. |
| Updated annotated PDF visible in normal PC folder | Export capability exists. | Automatic durable refresh is a separate workflow. |
| Special ToSort naming/review for PDF/Office/patent/SI | Pieces overlap. | The precise Inbox workflow remains customized. |
| Scanned/screenshot documents | Readable; searchable if text is present. | Add OCR preprocessing rather than a new OCR engine. |
| Handwriting inside research PDFs | Not a complete native handwriting-search pipeline. | Recognize the tablet ink, index it, and link results to the source. |

Zotero is close to the research-library part and less close to the physical PC/reMarkable coordination. Do not equate Zotero's own cross-device sync with reMarkable sync.

## Handwriting search: existing work and realistic reuse

### reMarkable's own search

The current official support article says handwriting search is for Connect subscribers on software 3.22 or later, uses MyScript, requires network access for new sync/indexing, and can search previously indexed notes offline. Crucially, it says notebooks/note pages are supported but PDFs and EPUBs are excluded. A broader marketing page mentions documents/books, so the public wording is inconsistent; PDF-margin handwriting must be checked on the actual firmware rather than assumed to work. [Support article](https://support.remarkable.com/articles/Knowledge/Handwriting-search), [broader marketing wording](https://remarkable.com/whats-new-connect)

I did not find a documented supported API that exposes the built-in handwriting-search index to third-party desktop applications. That is a search result, not proof that no undocumented endpoint or future export exists. A Connect subscription does not establish permission or a technical mechanism to embed MyScript or reuse reMarkable's search index in Notable.

There are three distinct possibilities:

1. Search directly on the tablet when supported: already useful, but it does not produce a unified PC search.
2. Import text the user explicitly converts/exports: useful where an export is available; its connection to original pages and annotations must be retained.
3. Use a separate recognizer: an open-source local engine, an opt-in hosted service, or a separately licensed MyScript developer integration.

The open-source [reScript](https://github.com/akeil/rescript) demonstrates a tablet/MyScript bridge using its own developer credentials. It does not demonstrate free access to the user's built-in search index or current-firmware compatibility. MyScript's published REST examples show stroke-based inputs. [MyScript example](https://developer.myscript.com/docs/files/rest-text-example.json)

### Existing recognizers and pipelines

| Candidate | Relevant existing work | How to assess it for Notable |
| --- | --- | --- |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | OCR toolkit; published PP-OCRv5 material explicitly evaluates handwriting. | Strong candidate for a local benchmark. Do not extrapolate published datasets to scientific margin notes. |
| [TrOCR handwritten model](https://huggingface.co/microsoft/trocr-base-handwritten) | Model fine-tuned for handwriting, MIT model-card license. | Its intended input is a single line; requires line detection/segmentation around our ink. |
| [Kraken](https://github.com/mittagessen/kraken) | Trainable recognition/layout tools and model ecosystem. | Useful if adaptation becomes necessary; documented platform and model selection add deployment work. |
| [Tagged Sync](https://github.com/thomas-hochbichler/obsidian-remarkable-tagged-sync) | Existing reMarkable transcription/export pipeline with local-model options. | Learn from incremental processing and source-linked output; some code/features have different licensing. |
| [E-Ink Sync](https://github.com/hwangso595/eink-sync) | Tablet extraction with optional local OCR. | A useful integration reference, not proof of cursive accuracy or a reason to change the device configuration. |
| [reMarkable OCR handwriting](https://github.com/delize/remarkable-ocr-handwriting) | Local Ollama-based transcription pipeline with page/source metadata. | Pipeline reference; verify license, model terms, hardware, Windows setup and actual accuracy. |
| [reMarkable MCP](https://github.com/SamMorrowDrums/remarkable-mcp) | Rendering and optional OCR with separate typed/highlight/OCR output. | Already relevant upstream; learn from content provenance rather than interpreting OCR as native text. |
| Tesseract, already optional here | A working existing integration for isolated ink. | Retain as a baseline; do not treat it as a guarantee of cursive recognition. |

The recommended architecture is ink image/strokes → existing recognizer → separate transcript record → existing search index. Keep the source image, page, region, source revision, engine/model version, and correction history. Reprocess changed ink rather than the whole library every time. Search results should open the original image/context and identify the transcript as machine-read text.

The choice should be based on retrieval of the user's scientific words, symbols, numbers and abbreviations, not a generic demonstration. Measure missed keywords and misleading matches as well as transcription accuracy, speed and memory. A model can produce fluent but incorrect text; confidence scores from different engines are not interchangeable.

Printed-scan OCR is a separate task. [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) is the focused reuse candidate for adding a searchable layer to scanned papers. Prefer preprocessing before tablet annotation. A previously annotated paper needs geometry checks if OCR rotates, deskews, or otherwise transforms pages.

## Zotero versus Mendeley as Notable's companion

| Concern | Assessment |
| --- | --- |
| Existing citation work | Both already support the user's basic reference-management purpose. No need to disparage Mendeley or duplicate working citations. |
| Open-source-first requirement | Zotero's application and ecosystem offer an inspectable basis for extensions and bug investigation. |
| Local desktop connection | Zotero documents a local HTTP API; current versions support authorized local writes. Pyzotero already implements access. |
| Mendeley integration | Mendeley has a developer API too. The distinction is not “API versus no API”; Zotero's local/open integration is a better fit here. |
| Tag/attachment/reference relationships | Zotero provides a useful data model for a small companion bridge. |
| File ownership | Choose one application to own physical moves/names. Do not let Notable and an attachment-moving plugin independently organize the same files. |
| Migration | Zotero provides an online Mendeley importer. Test item counts, attachments, annotations, collections, and important manuscripts before switching daily work. |

Sources: [Zotero local API](https://www.zotero.org/support/dev/web_api/v3/local_api), [Pyzotero](https://github.com/urschrei/pyzotero), [Mendeley developer portal](https://dev.mendeley.com/), [official importer](https://www.zotero.org/support/kb/mendeley_import).

A specific migration distinction matters: Zotero documents relinking citations created by the older Mendeley Desktop word-processor plugins; citations created with Mendeley Cite are not readable by Zotero according to that documentation. Existing manuscripts should be evaluated as copies and can continue using their original citation tool. This research does not authorize or perform a migration.

For the user's folder-first preference, Zotero's linked attachments are promising: Notable could own a durable directory tree while Zotero links to those files. The tradeoff is that linked files are not synchronized by Zotero's normal attachment service and are not supported in group libraries or the mobile workflows described in its attachment documentation. The user primarily reads on reMarkable, which may make that tradeoff acceptable, but it is a decision to evaluate. [Attachment storage choices](https://www.zotero.org/support/attaching_files)

## SI as a first-class requirement

The user's desired contract is:

```text
Literature/Topic/
    Author_Year_Article.pdf
    Author_Year_Article_SI.pdf
```

If a paper has several SI files of the same type, keep `_SI` as the final stem suffix:

```text
Author_Year_Article_Spectra_SI.pdf
Author_Year_Article_Methods_SI.pdf
```

The qualifier distinguishes attachments while preserving the suffix requirement. Multiple naming variants need not be added to the ordinary UI unless actually needed.

Zotero can keep the article and SI as child attachments of one parent reference. Supported publisher translators can also collect SI with the appropriate preference, but site coverage varies. Its default managed storage gives each attachment its own directory, so it does not satisfy physical co-location by default. Automatic renaming also normally avoids additional attachments to preserve SI filenames. [Attachments](https://www.zotero.org/support/attaching_files), [supplemental preferences](https://www.zotero.org/support/preferences/hidden_preferences), [renaming](https://www.zotero.org/support/file_renaming)

Notable already has meaningful SI functionality: reviewed attachment relationships, local candidate discovery, explicit parent DOI association, publisher-link discovery, downloads, duplicate checks, and shared naming with an `_SI` marker. It keeps SI as a separate document rather than merging it into the main paper's page sequence. However, attaching an existing file does not force it into the main article's folder or rename it, and persistent reciprocal reader navigation is not established as an always-visible feature. Those are remaining requirements, not already-delivered guarantees.

The user-facing improvement would be a compact “Main article / Supporting information” control near the current document. The relationship should be stored by identity, not guessed from a similar filename on every open. Main-to-SI and SI-to-main navigation should survive renames and sync refreshes. The pair can share one Zotero parent record while retaining separate Notable file/page identities and tablet document IDs.

No claim is made that the reMarkable device itself can expose the same cross-document controls without additional device support. On the tablet, co-location and matching names already help; direct document links would need a separate verified capability.

## Avoiding duplicated systems

The most important choice is ownership:

| Information/action | Preferred owner to evaluate |
| --- | --- |
| Bibliographic record, journal citation style, manuscript citations | Zotero. |
| File name, physical topic folder, main/SI co-location | One file-management owner: initially Notable, or a proven Zotero plugin workflow. |
| Handwritten annotations | reMarkable. |
| Durable annotated PC PDF publication | One bridge, with retained clean source and tablet layers. |
| Imported tablet tags and local additions | One visible tag interface; retain origin internally. |
| Full-text/annotation search | Try Zotero 10 first; retain Notable's search only for demonstrated gaps or a preferable unified experience. |
| Handwriting transcription | Existing recognizer behind a small adapter. |

For a Zotero bridge, map stable Zotero library/item/attachment keys to Notable's paper/source IDs and the tablet document ID. A DOI identifies a publication imperfectly; it does not identify every file, edition, SI attachment, or annotation. Start with citation exchange or read-only metadata retrieval and add narrowly scoped writes only when needed. Avoid continuously syncing two independent full reference databases.

## What to do before the next substantial implementation

1. Evaluate Zotero 10 natively on a copied sample: article search, notes, SI attachments, citation editing, and source navigation.
2. Evaluate an existing compatible tablet bridge against the actual folder/addition/annotation requirements. Verify the selected released plugin and firmware; the experimental bridge currently advertises an older maximum Zotero version.
3. Evaluate linked attachments and one file-management owner against same-folder SI and exact naming.
4. Benchmark two existing local handwriting recognizers on representative ink before selecting one.
5. Keep or implement only the gaps. Record what was evaluated and why reuse/adaptation/custom glue was chosen.

There is plausible value in continuing Notable as a focused bridge. There is not a good case for rebuilding Zotero's citation library, CSL formatting, publisher capture, or general reference-management interface. If an existing stack passes the full workflow, narrowing or retiring corresponding Notable features is a valid successful outcome.
