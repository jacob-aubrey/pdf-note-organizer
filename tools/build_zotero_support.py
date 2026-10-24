"""Package the graphical extension and optional managed Windows runtime."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import zipfile


def build(output, runtime=None):
    source = Path(__file__).resolve().parents[1] / "zotero-support"
    data = BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        files = {p.relative_to(source).as_posix(): p for p in source.rglob('*') if p.is_file()}
        manifest = None
        if runtime:
            runtime = Path(runtime).resolve(strict=True)
            if not (runtime.is_file() and runtime.name == 'notable-worker.exe') and not (runtime / 'notable-worker.exe').is_file():
                raise ValueError('The managed worker executable is missing')
            entries = []
            for path in ([runtime] if runtime.is_file() else sorted(runtime.rglob('*'))):
                if path.is_file():
                    name = path.name if runtime.is_file() else path.relative_to(runtime).as_posix()
                    entries.append({'path': name, 'md5': hashlib.md5(path.read_bytes()).hexdigest()})
                    files['runtime/' + name] = path
            manifest = {'id': hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()[:24], 'files': entries}
        for name, path in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
        if manifest:
            info = zipfile.ZipInfo('runtime-manifest.json', date_time=(2026, 10, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, json.dumps(manifest, sort_keys=True))
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data.getvalue())
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path)
    args = parser.parse_args()
    print(build(args.output, args.runtime))
