# Zotero plugin and bridge preflight

Reviewed October 18, 2026. Scope: current primary-source release, manifest, dependency, API, and workflow checks for choosing Notable, Zotero, or a hybrid. Read the project's AGENTS.md before evaluation. This report, a subsequently authorized official portable Zotero ZIP/extraction under `.test-tmp/zotero10-preflight/`, and a separate Pyzotero environment/results under `.test-tmp/pyzotero-preflight/` were created. Existing applications, dependencies, settings, accounts, and devices were not changed.

## Evidence level and decision

This includes **static compatibility, portable-package provenance, isolated Python dependencies, and a later synthetic local API runtime check**, not an end-to-end tablet sync test. Published release pages, tagged manifests where available, current source manifests, package metadata, and official documentation were inspected through the web tool. No third-party XPI was installed, no candidate test suite was executed, and no production Zotero/reMarkable library was connected by this investigation. The downloaded portable executable was launched separately by the root agent, using an isolated profile. A manifest permitting a version establishes declared install compatibility, not working behavior. Upstream test claims are attributed to their authors, not presented as tests run here.

The latest user clarification accepts organizing through Zotero rather than maintaining a particular Windows folder layout, and accepts a quiet, reliable local helper. Consequently **physical Windows co-location/mirroring is optional**, while correspondence between the organized research collection and the reMarkable tree still matters. The report retains file-layout findings as options rather than imposing an outdated requirement.

The shortest route merits an isolated trial: **Zotero 10.0.6 + Better Notes + upstream Zotero OCR**, with an attachment organizer only if ordinary Windows folders remain useful, while keeping Notable's tablet coordination available. The direct reMarkable plugin does **not** pass the current-stable version gate. No assessed combination establishes complete collection/tablet correspondence or unified tablet tags. A hybrid is therefore the leading test candidate, not a proven final choice.

## Current baseline

Zotero's official download page offers Zotero 10 for Windows, including x64 installer and ZIP distributions. Its release changelog lists **10.0.6, released October 7, 2026**, as the current release at this review. Use that exact version for a reproducible initial trial. [Download](https://www.zotero.org/download/), [release history](https://www.zotero.org/support/changelog).

Zotero 10 changed search/storage and plugin APIs. Passing the manifest gate alone does not resolve compatibility. Test new plugins against 10.0.6 in a separate profile and data directory; do not change a version limit solely to force installation. [Developer migration notes](https://www.zotero.org/support/dev/zotero_10_for_developers).

## Candidate audit

### reMarkable document and annotation transport

**Zotero reMarkable Sync, latest release v0.2.0 (June 8, 2026), AGPL-3.0-or-later.** Tagged source manifest permits `6.999` through `9.*`, so it excludes current Zotero 10.0.6. README describes experimental software, tag-selected PDF upload, scheduled pulls, and conversion of tablet highlights/ink to native Zotero annotations. Safe mode leaves device annotations alone. Package metadata uses TypeScript, `rmapi-js`, and Zotero plugin tooling rather than a platform-specific external transfer binary. Windows feasibility is plausible; Windows + Zotero 10 operation is **not established**. [Release](https://github.com/bpiwowar/zotero-remarkable-sync/releases/tag/v0.2.0), [tagged manifest](https://github.com/bpiwowar/zotero-remarkable-sync/blob/v0.2.0/addon/manifest.json), [README](https://github.com/bpiwowar/zotero-remarkable-sync), [package metadata](https://raw.githubusercontent.com/bpiwowar/zotero-remarkable-sync/main/package.json).

Its documented selection model is not proof of mirrored Windows/tablet trees, discovery of every device-only PDF, propagation of folder moves/renames, or import of the user's reMarkable research tags. Native annotation return is a candidate claim requiring device fixtures. A compatible updated release, or a small audited port with isolated tests, is a prerequisite for making this the default bridge.

The repository supplies parser/writer test commands, including `npm run test:parser` and `npm run test:writer`. These would test format logic after a separately authorized disposable checkout/dependency setup. They do not prove correct tablet geometry, cloud transport, or folder synchronization.

**zotRm**, MIT: useful alternative design reference. It describes Zotero subcollection-to-tablet hierarchy and refreshing an annotated PDF, but explicitly says Windows is unsupported. The returned marks are flattened rather than native Zotero annotation objects. This fails the user's present Windows replacement gate. [Repository](https://github.com/dipta007/zotRm).

### External filenames and directory layout

**Attanger, latest v1.5.5 (October 16, 2026), AGPL-3.0-or-later.** Current README documents Zotero 7–10 and Windows setup; current source manifest permits through `11.*`. The v1.5.5 tagged manifest could not be fetched through the available web channel, so the packaged release's manifest still needs inspection. Recent release notes show active work and report 360 upstream automated checks; those were not run here. [Release](https://github.com/MuiseDestiny/zotero-attanger/releases/tag/v1.5.5), [current manifest](https://raw.githubusercontent.com/MuiseDestiny/zotero-attanger/main/addon/manifest.json).

Attanger can keep managed storage, use external linked files, or maintain an organized external copy. Templates can use collections/years and attachment matching can distinguish main/SI candidates. External-copy mode is one-way and explicitly omits Zotero's database annotations. Thus it does not automatically provide the user's ordinary annotated PC PDF. Exact `_SI` and persistent reader navigation remain acceptance tests. [Workflow documentation](https://github.com/MuiseDestiny/zotero-attanger).

**ZotMoov, stable 1.2.32 (August 1, 2026), GPL-3.0.** Newer 1.2.33/1.2.34 entries are prereleases, not the stable baseline. The 1.2.32 tagged manifest permits `6.999` through `10.*`. Release notes specifically address Zotero 10 API changes. Windows build materials exist. [Releases](https://github.com/wileyyugioh/zotmoov/releases), [tagged manifest](https://raw.githubusercontent.com/wileyyugioh/zotmoov/1.2.32/manifest.json).

It moves/copies attachments to an external directory and supports attaching a recent download. Copy mode is not live tracked attachment synchronization. Linked-file mode has Zotero's normal mobile/group restrictions. It does not connect to the tablet. Evaluate **Attanger or ZotMoov**, not both concurrently as competing file movers. [README](https://github.com/wileyyugioh/zotmoov).

### Notes and exports

**Better Notes, stable v3.3.3 (August 24, 2026), AGPL-3.0-or-later.** Tagged manifest permits `8.0-beta.21` through `10.99.99`, which includes 10.0.6. Tagged package confirms that version/license and a DOCX conversion dependency. The project documents templates, linked notes, Markdown synchronization, DOCX export, and an API for other plugins. [Release](https://github.com/windingwind/zotero-better-notes/releases/tag/v3.3.3), [manifest](https://raw.githubusercontent.com/windingwind/zotero-better-notes/v3.3.3/addon/manifest.json), [package](https://raw.githubusercontent.com/windingwind/zotero-better-notes/v3.3.3/package.json), [capabilities](https://github.com/windingwind/zotero-better-notes).

Declared version compatibility passes. Exact Windows DOCX appearance, handwriting crops, source-page navigation, folder-wide assembly, and protection of manually edited exported notebooks remain untested. These are distinct requirements, not implied by a `.docx` export button.

### OCR for scanned printed text

Prefer **upstream UB-Mannheim Zotero OCR**, stable 0.9.6, AGPL-3.0, over the earlier survey's Dheia fork unless that fork establishes an additional needed fix. The 0.9.6 tagged manifest permits `6.999` through `10.*`. Upstream documents Windows prerequisites: Tesseract and Poppler's `pdftoppm`. It can create searchable output PDFs and text/hOCR attachments. Default outputs can add multiple files, so configure and test for a simple library. [Release](https://github.com/UB-Mannheim/zotero-ocr/releases/tag/0.9.6), [tagged manifest](https://raw.githubusercontent.com/UB-Mannheim/zotero-ocr/0.9.6/src/manifest.json), [README](https://github.com/UB-Mannheim/zotero-ocr).

This passes the declared Zotero-version and documented Windows route gates. It does not establish reliable scientific-handwriting recognition. Before any annotated PDF is replaced, test cropbox/rotation/geometry and compare visible pages plus annotation locations. Run preprocessing on copies first. An existing OCR plugin reduces integration work but does not remove the need to verify the actual output.

### Local Python integration

**Pyzotero 1.16.0 (October 13, 2026), BlueOak-1.0.0**, declares Python >=3.10 and OS independence. Its current docs support local reads, authorized local writes, and attachment uploads; it handles Zotero instance identity. Some convenience methods using `/items/new` remain unavailable locally. This is a stronger hybrid candidate than writing a new HTTP client. [Release](https://github.com/urschrei/pyzotero/releases/tag/v1.16.0), [tagged project metadata](https://raw.githubusercontent.com/urschrei/pyzotero/v1.16.0/pyproject.toml), [local API client documentation](https://pyzotero.readthedocs.io/en/latest/#the-local-zotero-api).

Zotero 10's official local API supports offline reads/writes and file/full-text operations. It must be enabled in Settings; write authorization is granted in Zotero, separately from cloud credentials. The bridge should retain Zotero server identity and object versions and leave the database schema to Zotero. [Official API](https://www.zotero.org/support/dev/web_api/v3/local_api).

The initial static review did not install Pyzotero. A later authorized isolated dependency probe, recorded below, installed 1.16.0 successfully and passed import/metadata checks. Its clean dependency resolution with `requirements.txt` also succeeded. This does not establish compatibility with every transitive pin in `requirements.lock`, packaging, or runtime behavior inside Notable.

## Workflow gates

| Gate | Static result | Next meaningful evidence |
| --- | --- | --- |
| Zotero stable on Windows | Official 10.0.6 Windows route available | Launch isolated profile/data directory and record actual version |
| Native full-text/Boolean library search | Zotero 10 has expanded nested search and FTS5 | Cross-page AND/OR/NOT and phrase corpus with known answers |
| Long dissertations | Thesis reference type and PDF attachments exist | End-of-document terms, complete index status, reading responsiveness |
| reMarkable PDF annotation return | Candidate exists; current stable version blocked | Compatible bridge + exact device/firmware + repeated annotation pulls |
| Organized collection/tablet correspondence | Not established by evaluated plugin route | New collection/subcollection/PDF and tablet-only folder/file appear at intended counterparts; physical Windows mirror optional |
| Folder moves/renames/deletion policy | Not established | Stable identity/no-duplicate scenarios and explicit deletion behavior |
| One tag system | Native Zotero tags usable; tablet mapping absent | Import tablet document/page tags, dedupe names, retain local-only tags |
| Current annotated PC-accessible PDF | Export possible; automatic publication not established | Open latest annotations from Zotero; optional File Explorer copy; repeat sync without re-upload/duplication |
| Main/SI association | Native common parent attachment model available | Correct main/SI relationship and `_SI` names, link accessible from both reader tabs; same physical directory optional |
| Folder Word notebook | Existing exporter candidate | Compare source links/ink crops/layout against the user's current output |
| Printed scans | Compatible OCR route documented | Known image-only text becomes searchable; visible geometry retained |
| Handwritten marginalia search | No pass established | Representative handwriting benchmark with image-backed results |

For dissertations, inspect **both PDF page and text limits**. The 10.0.6 tagged defaults retain `fulltext.pdfMaxPages = 100` and `fulltext.textMaxLength = 500000`. Its `indexPDF()` applies the page limit to PDF extraction; later cached-content processing also reads using the text limit. The documentation's broad 500,000-character description alone is insufficient to establish PDF coverage. Test unique terms beyond page 100 and near the end, then repeat after restart/reindex with deliberate limits. [Tagged defaults](https://raw.githubusercontent.com/zotero/zotero/10.0.6/defaults/preferences/zotero.js), [tagged full-text implementation](https://raw.githubusercontent.com/zotero/zotero/10.0.6/chrome/content/zotero/xpcom/fulltext.js), [Search settings](https://www.zotero.org/support/preferences/search). Zotero has a Thesis item type; metadata support alone does not prove complete indexing or automatic recognition. [Item types](https://www.zotero.org/support/kb/item_types_and_fields).

## Concrete isolated probes for the next trial

These are proposed runnable checks, **not executed results**. Use a new profile/data directory, no account sync, and copied or synthetic files. Keep it independent of the production Notable and Zotero libraries. Install one plugin at a time and retain the exact XPI/hash/version. Add a device test only after the local probes pass and using a dedicated test subtree.

1. **Launch and local API:** in a dedicated Zotero profile enable local communication. With Zotero running, the following PowerShell reads only the API root and records instance/version headers:

   ```powershell
   $probeResponse = Invoke-WebRequest -Uri 'http://127.0.0.1:23119/api/' -UseBasicParsing
   $probeResponse.StatusCode
   $probeResponse.Headers['Zotero-API-Version']
   $probeResponse.Headers['Zotero-Server-ID']
   ```

   Run with all other Zotero instances closed so the port belongs to the test profile. A disabled API or absent process is an environment result, not a failure of Zotero's research features. Later authenticated writes belong only in the test library.

2. **Search:** create A with `nanoparticle` on page 1 and `tantalum` on page 3; B with only `nanoparticle`; C with a quoted phrase; D with excluded terms; E as an image-only scan; F as a long thesis with a unique final-page marker beyond the configured index limit. Record expected matching item IDs before searching. Repeat after restart and after replacing a copied file with changed text. Test main and SI independently and as one parent item to expose whether search terms can accidentally match across separate attachments.

3. **Local metadata/attachment handoff:** in an independent Python environment with pinned Pyzotero 1.16.0, `Zotero('0', 'user', local=True).top(limit=1)` is a small read probe. Then authorize a disposable write through the documented API and create a test parent, tag, and attached PDF. Check UI visibility, restart, same-item update, and duplicate prevention. Do not use production keys or print key values.

4. **Organization/SI:** create one article with main and SI PDFs, plus a dissertation with an appendix. Confirm `_SI` suffix and relationship/navigation after restart. Change collection and item title; verify neither duplicate nor incorrect main/SI association appears. If optional external folders are retained, separately test organizer paths, collision behavior and rename propagation. A common parent record is enough for logical attachment grouping, but not proof of persistent reader navigation.

5. **Notebook export:** create printed highlights, comments, pen marks, and an image crop on copied papers. Generate the equivalent folder/collection note and DOCX. Open it in Word and verify images, page references, citations, order, and layout. Edit the exported document manually and repeat export to learn whether the current Notable protection behavior is retained.

6. **OCR:** run only on synthetic/copied scan fixtures, including rotated and cropped pages. Verify new text with an independent extractor, inspect rendered pages, and check crop/rotation/page count. Add annotations before one test to verify they remain aligned. Measure duplicates/intermediate attachments and processing time on a representative thesis.

7. **Device loop:** once a compatible bridge is available, use one clean test PDF, a scanned test PDF, and a main/SI pair inside one test root. Upload, annotate on tablet, pull twice, add another mark, pull again. Check pen/highlight placement, native-object versus flattened return, duplicates, stable identity, visibility from Zotero, and no unwanted annotation write-back. Run new Zotero collection/subcollection/PDF and tablet-only folder/file cases separately; tag-based selection alone cannot establish collection/tablet correspondence. Check an ordinary disk copy only if that remains desired.

## Claims this review does not support

- "Zotero plus existing plugins already replaces every Notable feature."
- "Zotero 9 plugin support implies Zotero 10 support."
- "An organized external copy contains Zotero's annotations."
- "A collection hierarchy is a two-way physical directory mirror."
- "OCR support establishes accurate handwritten chemistry/mathematics search."
- "Full-text search automatically indexes every character of a dissertation."
- "A passing plugin manifest proves Windows/device behavior."

These unresolved gates are the reason to retain the existing implementation during evaluation. A successful Zotero trial could reduce the Notable interface and duplicate indexing/citation work while preserving useful tablet rendering, folder identity, file publication, and naming components.

## Portable Zotero package acquired for the root agent's isolated trial

The root agent subsequently requested the official portable 10.0.6 ZIP for real runtime tests in a disposable profile. The package was downloaded and extracted only; no installer ran, no existing Zotero was updated, no file association/shortcut was registered, and this investigator did not launch the executable.

| Check | Observed result |
| --- | --- |
| Official download URL | `https://download.zotero.org/client/release/10.0.6/Zotero-10.0.6_win-x64.zip` |
| ZIP size | 137,840,430 bytes |
| ZIP SHA-256 | `264B8337B9B412D2B22C369E3885A9BB9331C56B7B46B77E90347D745B6CC132` |
| ZIP members | 96; member destinations validated to remain under the new extraction directory |
| ZIP path | `.test-tmp/zotero10-preflight/download/Zotero-10.0.6_win-x64.zip` |
| Extracted executable | `.test-tmp/zotero10-preflight/app/Zotero_win-x64/zotero.exe` |
| PE file/product versions | Both `10.0.6` |
| `app/application.ini` | `Version=10.0.6`, `BuildID=20261007153950` |
| Executable Authenticode | `Valid`, checked with `Get-AuthenticodeSignature` |
| Signer | Corporation for Digital Scholarship, Virginia, US |
| Certificate thumbprint | `1667BFAB98EFEB0E290B9B9C8EFF503AD1CFD33D` |

The SHA-256 is the locally measured identity of this download, not a comparison against a separately published upstream checksum. The valid executable signature and official HTTPS origin provide additional provenance evidence. This establishes package identity/version, not feature correctness. The ordinary sandbox network attempt failed DNS resolution; a normal policy-reviewed download of this authorized public portable ZIP then succeeded.

Absolute executable path supplied to the root agent:

```text
C:\Users\jdaub\OneDrive\Desktop\Documents\PhD\Bonitatibus Research\Python Code\PDF Note Organizer\.test-tmp\zotero10-preflight\app\Zotero_win-x64\zotero.exe
```

The portable executable still needs explicit disposable profile/data-directory launch arguments. A ZIP distribution is not itself proof of profile isolation. Runtime results belong in the root agent's trial record; none are claimed in this section.

## Executed Pyzotero dependency preflight

The root agent subsequently authorized creating a **new independent virtual environment** at `.test-tmp/pyzotero-preflight/venv`, installing pinned `pyzotero==1.16.0`, inspecting local API methods without calling them, and resolving the combined Notable requirements in dry-run mode. The project's `.venv` was not modified. No Zotero client was constructed and no library/account API was called during these checks.

### Commands and outcomes

The Python launcher returned no registered interpreters under the sandbox, but the direct interpreter recorded in the project's existing `pyvenv.cfg` was available: `C:\Users\jdaub\AppData\Local\Programs\Python\Python313\python.exe`, version **3.13.1**. This base executable created the new environment. The first sandboxed `ensurepip` stage failed on a temporary-directory permission error. The authorized policy-reviewed bootstrap/install succeeded; this was an environment restriction, not a Pyzotero dependency conflict.

Commands used (with the isolated executable in `$preflightPython`):

```powershell
& 'C:\Users\jdaub\AppData\Local\Programs\Python\Python313\python.exe' -m venv '.test-tmp\pyzotero-preflight\venv'
$preflightPython = Join-Path (Get-Location) '.test-tmp\pyzotero-preflight\venv\Scripts\python.exe'
& $preflightPython -m ensurepip --upgrade --default-pip
& $preflightPython -m pip install --disable-pip-version-check --no-cache-dir --index-url 'https://pypi.org/simple' 'pyzotero==1.16.0'
& $preflightPython -m pip check
& $preflightPython -m pip freeze
& $preflightPython -m pip install --dry-run --ignore-installed --disable-pip-version-check --no-cache-dir --index-url 'https://pypi.org/simple' --report '.test-tmp\pyzotero-preflight\notable-resolution.json' -r 'requirements.txt' 'pyzotero==1.16.0'
```

| Executed check | Result |
| --- | --- |
| Independent environment Python | 3.13.1, Windows x64 |
| Pinned Pyzotero install | Exit 0, installed 1.16.0 |
| `pip check` | Exit 0, `No broken requirements found.` |
| `from pyzotero import Zotero` | Import succeeded |
| Installed version lookup | `importlib.metadata.version('pyzotero')` returned `1.16.0` |
| Constructor source/signature | `_client.py`; `local`, `server_id`, and `local_api_key` parameters present |
| Method inspection | `authorize_local`, `top`, `collections`, `create_items`, `update_items`, `upload_attachments`, `set_fulltext`, `item_types`, `item_type_fields` all present |
| `requirements.txt` + Pyzotero clean dry-run | Exit 0; pip 24.3.1 resolved 51 packages; no declared dependency conflict |
| Whole Notable environment install | Not performed |
| Account/library/device sync | Not performed |

The installed Pyzotero dependency freeze is saved at `.test-tmp/pyzotero-preflight/installed-freeze.txt`. Resolved versions include Pyzotero 1.16.0, httpx2/httpcore2 2.14.0, feedparser 6.0.14, bibtexparser 1.4.4, whenever 0.11.0, and anyio 4.15.1. The complete 51-package prospective environment, download hashes, and platform metadata are in `.test-tmp/pyzotero-preflight/notable-resolution.json`. That dry run downloaded candidates/metadata but did not install Notable or those 51 packages.

- Requirements file SHA-256 at the check: `807DB4C37DE5EC135DB34126E7EB292F730AFF6EDF106444E73692F41CABB731`.
- Resolution report SHA-256: `2935E80E42F1AB4534482E800BC88957015E2DD46F34D13BA90251C88813F29A`.

These results establish that a small Python bridge is installable and importable on this machine and that the declared direct requirements admit a combined solution. They do not demonstrate working synchronization, annotation accuracy, the application's hashed production lock, or its executable packaging.

Absolute interpreter supplied to the root agent:

```text
C:\Users\jdaub\OneDrive\Desktop\Documents\PhD\Bonitatibus Research\Python Code\PDF Note Organizer\.test-tmp\pyzotero-preflight\venv\Scripts\python.exe
```

### Instance-only endpoint for a disposable API port

The root agent reserved port 23129 for a later isolated Zotero API test. Installed Pyzotero 1.16.0 source confirms that `local` is a boolean switch, not an endpoint URL: any truthy string would still select the default port. Its constructor makes no request. Before the first API method, a client can override only that instance's `endpoint`:

```python
from pyzotero import Zotero

zot = Zotero('0', 'user', local=True)
zot.endpoint = 'http://127.0.0.1:23129/api'
```

Read requests, server-identity discovery, and local authorization build URLs from that instance attribute. The default local HTTP client ignores proxy environment settings. This approach changes no global configuration or installed package. It was subsequently exercised against the root agent's disposable Zotero 10.0.6 server as recorded below.

## Executed synthetic local API trial

After the root agent launched an isolated, account-free Zotero 10.0.6 profile on **port 23129**, Pyzotero 1.16.0 completed six checks with **14 HTTP requests restricted by a request hook to `127.0.0.1:23129/api/`**:

1. Read an existing synthetic thesis and its attachment metadata.
2. Obtain a local write authorization through the harness's exact-name simulated consent.
3. Create a synthetic Thesis record with university/type/author/date and a tag, and read it back.
4. Update its title and verify the new value by rereading.
5. Upload a copied synthetic PDF as a stored attachment and verify the attachment through the API.
6. Write full-text content (HTTP 204) and read back its unique marker.

**All six final checks passed.** The simulated consent validates the authorization protocol, not the human dialog. No cloud/account/production-library endpoint was used. The client wrote a completion sentinel so the root harness could close its disposable Zotero process. Initial sandbox socket denial and a corrected harness assumption about `set_fulltext()` returning a decorated boolean are retained in the JSON attempt history; neither is presented as a product failure.

Results: [API trial report](preflight-pyzotero-api-2026-10-18.md), [machine-readable results](preflight-pyzotero-api-2026-10-18.json). Script: `.test-tmp/pyzotero-preflight/run-local-api.py`. This proves the exercised local Python handoff works on this machine; it does not prove reMarkable sync, annotation geometry, third-party plugin coexistence, or production packaging.
