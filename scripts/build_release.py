"""Build a versioned executable and verify it against a disposable library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from note_organizer import __version__


def run(*command, **options):
    subprocess.run(command, cwd=ROOT, check=True, **options)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true", help="Use only after the complete suite has already passed for this checkout.")
    args = parser.parse_args()
    runtime = ROOT / "tmp" / "release-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "TEMP": str(runtime), "TMP": str(runtime)}
    run(sys.executable, "-m", "pip", "check", env=environment)
    run(sys.executable, "-m", "ruff", "check", "note_organizer", "--select", "F401,F841,F821", env=environment)
    if not args.skip_tests:
        run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q", env=environment)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--workpath", f"build/{__version__}",
        "PDF Note Organizer.spec", env=environment)
    executable = ROOT / "dist" / (f"Notable-{__version__}.exe")
    with tempfile.TemporaryDirectory(dir=runtime, prefix="smoke-") as temporary:
        smoke_environment = {**environment, "PDF_NOTES_DATA_DIR": temporary, "PDF_NOTES_SKIP_LEGACY_IMPORT": "1"}
        run(str(executable), "--smoke-test", env=smoke_environment, timeout=120)
        result = json.loads((Path(temporary) / "smoke-result.json").read_text(encoding="utf-8"))
        if not result.get("ok") or result.get("version") != __version__:
            raise RuntimeError(f"Packaged smoke test failed: {result}")
    with executable.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    manifest = {"version": __version__, "executable": executable.name, "sha256": digest, "source_commit": revision,
                "python": sys.version, "smoke_test": result,
                "runtime_lock_sha256": hashlib.sha256((ROOT / "requirements.lock").read_bytes()).hexdigest()}
    (executable.with_suffix(".manifest.json")).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
