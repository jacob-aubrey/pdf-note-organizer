"""Package the graphical extension and optional managed Windows runtime."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import zipfile
import subprocess
import tempfile


def validate_build_environment():
    """Fail before freezing when the private runtime is incomplete."""
    import importlib
    required = ('pyzotero', 'httpx2', 'httpcore2', 'rapidocr', 'onnxruntime', 'numpy', 'pymupdf', 'rmscene', 'pypdf', 'PIL', 'docx', 'fontTools', 'yake')
    for name in required:
        try:
            importlib.import_module(name)
        except ImportError as error:
            raise RuntimeError('Build requires the complete requirements-zotero-plugin.txt environment; missing ' + name) from error
    return required


def validate_runtime(runtime):
    """Exercise the exact frozen imports without opening Zotero or the cloud."""
    executable = Path(runtime)
    if executable.is_dir():
        executable = executable / 'notable-worker.exe'
    request = {'id': 1, 'method': 'runtime_health', 'params': {'optional': True}}
    with tempfile.TemporaryDirectory(prefix='notable-runtime-health-') as state:
        result = subprocess.run([str(executable.resolve(strict=True)), '--state', state],
                                input=json.dumps(request) + '\n', capture_output=True, text=True, timeout=90)
    try:
        packets = [json.loads(line) for line in result.stdout.splitlines()]
        health = next(row['result'] for row in packets if row.get('id') == 1)
        valid = result.returncode == 0 and health['sync_ready'] and all(row['available'] for row in health['optional_ocr'].values())
        valid = valid and set(health['optional_ocr']) == {'rapidocr', 'onnxruntime', 'numpy'}
    except (ValueError, KeyError, StopIteration, TypeError):
        valid = False
    if not valid:
        raise RuntimeError('The frozen helper failed its required/optional runtime import check; package was not created.')
    return health


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
    parser.add_argument("--verify-runtime", action='store_true', help='Required release gate: exercise frozen runtime imports before packaging')
    args = parser.parse_args()
    if args.verify_runtime and not args.runtime:
        parser.error('--verify-runtime requires --runtime')
    if args.runtime:
        validate_runtime(args.runtime)
    print(build(args.output, args.runtime))
