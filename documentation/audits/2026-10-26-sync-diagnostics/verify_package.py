"""Verify a release artifact against source; no user library or network operations."""
import argparse
from pathlib import Path
import hashlib
import json
import marshal
import sys
import types
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from PyInstaller.archive.readers import CArchiveReader
from tools.build_zotero_support import validate_runtime


def normalized(code):
    return code.replace(co_filename='<source>', co_consts=tuple(
        normalized(value) if isinstance(value, types.CodeType) else value for value in code.co_consts))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default='0.9.2')
    args = parser.parse_args()
    digits = args.version.replace('.', '')
    helper = ROOT / f'.test-tmp/zotero-plugin-{digits}-dist/notable-worker.exe'
    xpi = ROOT / f'dist/reMarkable-Sync-for-Zotero-{args.version}.xpi'
    archive = CArchiveReader(str(helper))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    modules = []
    for name in sorted(n for n in pyz.toc if n == 'note_organizer' or n.startswith('note_organizer.')):
        source = ROOT / name.replace('.', '/')
        source = source / '__init__.py' if source.is_dir() else source.with_suffix('.py')
        equal = normalized(pyz.extract(name)) == normalized(compile(source.read_bytes(), str(source), 'exec'))
        assert equal, name
        modules.append({'module': name, 'equal': equal, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    with zipfile.ZipFile(xpi) as package:
        frontend = [{'file': str(p.relative_to(ROOT)), 'equal': package.read(p.relative_to(ROOT / 'zotero-support').as_posix()) == p.read_bytes()}
                    for p in (ROOT / 'zotero-support').rglob('*') if p.is_file()]
        assert all(row['equal'] for row in frontend)
        assert package.read('runtime/notable-worker.exe') == helper.read_bytes()
        manifest = json.loads(package.read('runtime-manifest.json'))
        assert all(hashlib.md5(package.read('runtime/' + row['path'])).hexdigest() == row['md5'] for row in manifest['files'])
    entry = ROOT / 'tools/notable_worker.py'
    assert normalized(marshal.loads(archive.extract('notable_worker'))) == normalized(compile(entry.read_bytes(), str(entry), 'exec'))
    health = validate_runtime(helper)
    result = {'xpi_sha256': hashlib.sha256(xpi.read_bytes()).hexdigest(),
              'helper_sha256': hashlib.sha256(helper.read_bytes()).hexdigest(), 'runtime_manifest': manifest,
              'runtime_health': health, 'source_modules': modules, 'frontend': frontend, 'entrypoint_equal': True}
    Path(__file__).with_name(f'package-{digits}-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'xpi_sha256': result['xpi_sha256'], 'helper_sha256': result['helper_sha256'],
                      'all_equal': True, 'modules': len(modules), 'frontend_files': len(frontend), 'health': health}, indent=2))


if __name__ == '__main__':
    main()
