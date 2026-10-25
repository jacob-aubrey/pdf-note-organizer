# Dependency and asset provenance verification

Local verification completed October 25, 2026. Detailed machine-readable evidence is in `dependency-provenance.json`. No packages were downloaded or installed, and no product files were changed for these checks.

The current `dist/reMarkable-Sync-for-Zotero-0.8.4.xpi` runtime executable matches `.test-tmp/zotero-plugin-084-dist/notable-worker.exe` byte for byte and matches the runtime manifest's MD5. Its PE machine is AMD64 (`0x8664`); the archive includes Python 3.13. All 18 direct pins obtained recursively from `requirements-zotero-plugin.txt` match the actual packaged distribution metadata. Selected installed/extracted metadata versions also agree with the current packaged executable.

| Component | Packaged version | License evidence |
| --- | --- | --- |
| PyMuPDF | 1.28.2 | AGPL/commercial dual-license notice and COPYING |
| Pillow | 12.3.0 | MIT-CMU in metadata and actual LICENSE |
| rmscene | 0.8.0 | MIT |
| Pyzotero | 1.16.0 | BlueOak-1.0.0 |
| RapidOCR / ONNX Runtime | 3.10.0 / 1.31.0 | Apache-2.0 / MIT, model notices and third-party notices |
| pypdf / fontTools / python-docx | 6.19.0 / 4.66.1 / 1.2.0 | BSD-3-Clause / MIT / MIT |
| NumPy / OpenCV headless | 2.5.4 / 5.0.0.93 | NumPy composite license and bundled license files / Apache-2.0 and third-party notice |
| YAKE | 0.7.3 | Actual LICENSE says AGPL-3.0-or-later; metadata says LGPLv3, already explained by project notices |
| Click / jellyfish / NetworkX | 8.5.0 / 1.3.0 / 3.7 | BSD-3-Clause / MIT / BSD-3-Clause |
| segtok / tabulate / regex | 1.5.11 / 0.10.0 / 2026.9.29 | MIT / MIT / Apache-2.0 AND CNRI-Python |

All 21 selected runtime/build/transport distributions have license evidence in their metadata/package or the copied license collection (77 entries). Native wheel tags include `cp313-cp313-win_amd64`, or an appropriate stable-ABI Windows tag. Pure Python dependencies use `py3-none-any`; their declared Python ranges allow 3.13. This establishes platform metadata alignment, not that every native execution path works. The installed Zotero executable reports 10.0.6, agreeing with the integration target.

The three actual packaged handwriting ONNX files match both byte counts and SHA-256 digests in their accompanying model provenance. The packaged English Tesseract traineddata and tessdata_fast license are present; its current digest is recorded, without claiming independent authentication against an upstream release.

Vendored PDF.js reports 6.4.299 in both its local manifest and runtime source. Every one of the manifest's 285 files is present, with no unexpected files apart from the manifest itself. Ten component license files cover the main Apache license, Adobe CMaps, Foxit/Liberation fonts, and WASM components. The manifest records the npm archive URL and SHA-512 integrity, but has no per-file hashes; no upstream archive was downloaded, so this audit did not independently reauthenticate every vendored byte against the archive. This was inventory/provenance verification, not line-by-line review of third-party PDF.js or WASM implementation.

The plugin's icon SOURCE and ISC LICENSE are present and identify Lucide revision `f12b0de177fbc2a6795e99be065887e72b237123`. Twenty SVGs match the application's corresponding SVG bytes; `tablet.svg` contains the documented local R modification, and `tag.svg` has no corresponding app asset for local comparison. No independent upstream revision comparison was performed. Icon licenses and attribution are preserved.

One notice correction is warranted: `documentation/ZOTERO_PLUGIN_NOTICES.md` labels Pillow HPND, while Pillow 12.3.0's actual metadata and bundled LICENSE call it MIT-CMU. The full actual license is already packaged. No missing operational dependency or absent license evidence was found in the selected checks. This does not establish exhaustive transitive vulnerability clearance, independent current maintenance status for every upstream project, or readiness for public redistribution.
