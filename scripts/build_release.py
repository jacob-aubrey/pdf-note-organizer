"""Build a versioned Windows portable release without touching saved libraries."""
from pathlib import Path
import hashlib
import os
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from note_organizer import __version__


def main():
    if platform.system() != 'Windows' or platform.architecture()[0] != '64bit':
        raise SystemExit('Build this release with 64-bit Python on Windows.')
    output = ROOT / 'dist' / 'releases' / ('v' + __version__)
    work = ROOT / 'build' / 'releases' / ('v' + __version__)
    for name in ('Notable-User-Manual.pdf', 'Notable-README.pdf'):
        if not (ROOT / 'output' / 'pdf' / name).is_file():
            raise SystemExit('Generate the current bundled guides before building.')
    environment=dict(os.environ)
    environment.pop('PYTHONPATH',None)
    environment['PYTHONNOUSERSITE']='1'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--distpath', str(output),
                    '--workpath', str(work), str(ROOT / 'PDF Note Organizer.spec')], cwd=ROOT, env=environment, check=True)
    executable = output / f'Notable-{__version__}-windows-x64.exe'
    (output / 'Notable.exe').replace(executable)
    from PyInstaller.archive.readers import CArchiveReader
    archive=CArchiveReader(str(executable))
    for name in ('Notable-User-Manual.pdf', 'Notable-README.pdf'):
        if archive.extract('documentation\\'+name)!=(ROOT/'output'/'pdf'/name).read_bytes():
            raise SystemExit('Bundled guide changed during packaging. Finish documentation, then build again: '+name)
        shutil.copy2(ROOT / 'output' / 'pdf' / name, output / name)
    if any(name.endswith(('.sqlite3','.db','.dpapi','.env')) for name in archive.toc):
        raise SystemExit('Unexpected library or credential file in the release archive.')
    assets = [executable, output / 'Notable-User-Manual.pdf', output / 'Notable-README.pdf']
    checksums = []
    for path in assets:
        with path.open('rb') as stream:
            checksums.append(f'{hashlib.file_digest(stream, "sha256").hexdigest()}  {path.name}\n')
    sums = ''.join(checksums)
    (output / 'SHA256SUMS.txt').write_text(sums, encoding='ascii')
    for path in assets:
        print(f'{path.name}: {path.stat().st_size:,} bytes')
    print('Release files:', output)


if __name__ == '__main__':
    main()
