"""Read-only cloud connectivity check; emits counts, never tokens or titles."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from note_organizer.remarkable_cloud import CloudClient, TokenVault


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = {"read_only": True, "status": "FAIL"}
    try:
        vault = args.library.resolve(strict=True).parent / "remarkable/device-token.dpapi"
        token = TokenVault(vault).load()
        if not token:
            raise ValueError("No saved pairing")
        catalog = CloudClient(token, cache_dir=args.output.parent / "blobs").library()
        result.update(status="PASS", items=len(catalog),
                      folders=sum(not r.deleted and r.kind == "CollectionType" for r in catalog),
                      pdfs=sum(not r.deleted and r.is_pdf for r in catalog))
    except Exception as error:
        result["error_type"] = type(error).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
