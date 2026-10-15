"""Refresh the pinned, offline PDF.js runtime from Mozilla's npm distribution."""
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import tarfile
from urllib.request import urlopen

VERSION = "6.4.299"
DESTINATION = Path(__file__).resolve().parents[1] / "note_organizer" / "assets" / "pdfjs"


def main():
    metadata_url = f"https://registry.npmjs.org/pdfjs-dist/{VERSION}"
    with urlopen(metadata_url, timeout=30) as response:
        metadata = json.load(response)
    distribution = metadata["dist"]
    archive_url = distribution["tarball"]
    if not archive_url.startswith("https://registry.npmjs.org/pdfjs-dist/-/"):
        raise ValueError("Unexpected PDF.js distribution location")
    with urlopen(archive_url, timeout=60) as response:
        archive = response.read(40_000_001)
    if len(archive) > 40_000_000:
        raise ValueError("PDF.js archive exceeds its expected size")
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(archive).digest()).decode("ascii")
    if integrity != distribution["integrity"]:
        raise ValueError("PDF.js archive integrity check failed")
    files = []
    with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as package:
        for member in package.getmembers():
            relative = PurePosixPath(member.name).relative_to("package")
            if not member.isfile() or ".." in relative.parts:
                continue
            keep = (str(relative) in {"LICENSE", "build/pdf.mjs", "build/pdf.worker.mjs", "web/pdf_viewer.mjs", "web/pdf_viewer.css"}
                    or relative.parts[0] in {"cmaps", "standard_fonts", "wasm"}
                    or relative.parts[:2] == ("web", "images"))
            if not keep:
                continue
            destination = DESTINATION.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(package.extractfile(member).read())
            files.append(str(relative))
    required = {"LICENSE", "build/pdf.mjs", "build/pdf.worker.mjs", "web/pdf_viewer.mjs", "web/pdf_viewer.css"}
    if not required.issubset(files):
        raise ValueError("PDF.js archive is missing required viewer files")
    manifest = {"name": "pdfjs-dist", "version": VERSION, "source": metadata_url,
                "archive": archive_url, "integrity": integrity,
                "license": "Apache-2.0", "files": sorted(files)}
    (DESTINATION / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Vendored PDF.js {VERSION}: {len(files)} files, verified SHA-512")


if __name__ == "__main__":
    main()
