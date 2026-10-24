"""Read-only render checks against real saved tablet sources; counts only.

No account writes, library migrations, names, note text or document copies.
"""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf
from note_organizer.remarkable_cloud import CloudItem
from note_organizer.remarkable_pdf import annotated_pdf, UnsupportedAnnotations
from note_organizer.remarkable_sources import source_info, source_bundle
from tools.zotero_pilot import read_source, tablet_saved_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()
    logging.getLogger("rmscene").setLevel(logging.ERROR)
    if not 1 <= args.limit <= 200:
        parser.error("Choose 1–200 cached PDFs per run")
    store = read_source(args.library)
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    directory = store.path.parent / "remarkable/sources"
    identities = sorted({p.stem for pattern in ("*.json", "*.rmdoc") for p in directory.glob(pattern)})
    result = {"scope": "existing cached sources only; read-only", "cases": [], "available": len(identities)}
    for identity in identities:
        if len(result["cases"]) >= args.limit:
            break
        case = {"case": len(result["cases"]) + 1, "status": "FAIL"}
        try:
            info = source_info(store, identity)
            if not info or not info.get("annotations_cached"):
                continue
            if Path(info.get("baseline_path") or info["layers_path"]).stat().st_size > 30_000_000:
                continue
            bundle = source_bundle(store, identity)
            baseline = hashlib.sha256(bundle[identity + ".pdf"]).hexdigest()
            item = CloudItem(identity, info.get("cloud_hash", ""), "Saved source", "", "DocumentType", False,
                             [{"id": name} for name in bundle])
            rendered = annotated_pdf(item, bundle)
            with pymupdf.open(stream=rendered, filetype="pdf") as document:
                counts = {}
                for page in document:
                    for annotation in page.annots() or ():
                        kind = annotation.type[1]
                        counts[kind] = counts.get(kind, 0) + 1
                case.update(status="PASS", pages=len(document), annotations=counts)
            texts = tablet_saved_text(store.path, identity)
            case["saved_transcripts"] = sum(bool(a.get("ocr")) for a in texts)
            assert hashlib.sha256(source_bundle(store, identity)[identity + ".pdf"]).hexdigest() == baseline
        except Exception as error:
            case["error_type"] = type(error).__name__
            if isinstance(error, UnsupportedAnnotations):
                case["reason"] = str(error)
        result["cases"].append(case)
    result["library_unchanged"] = hashlib.sha256(store.path.read_bytes()).hexdigest() == before
    result["passed"] = sum(c["status"] == "PASS" for c in result["cases"])
    result["failed"] = len(result["cases"]) - result["passed"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["library_unchanged"] and result["cases"] and not result["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
