# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
from pathlib import Path
from runpy import run_path

branding = run_path(str(Path(SPECPATH) / 'note_organizer' / '_version.py'))
APP_DISPLAY_NAME, __version__ = branding['APP_DISPLAY_NAME'], branding['__version__']

version_parts = tuple(int(part) for part in __version__.split('.')) + (0,)


a = Analysis(
    ['PDF Note Organizer.py'],
    pathex=[],
    binaries=[],
    datas=[('Note icon.ico', '.'), ('note_organizer/assets/icons', 'note_organizer/assets/icons'),
           ('note_organizer/assets/branding', 'note_organizer/assets/branding'),
           ('output/pdf/Notable-User-Manual.pdf', 'documentation'),
           ('output/pdf/Notable-README.pdf', 'documentation'),
           ('note_organizer/assets/reader', 'note_organizer/assets/reader'),
           ('note_organizer/assets/pdfjs', 'note_organizer/assets/pdfjs')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Notable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['Note icon.ico'],
    version=VSVersionInfo(
        ffi=FixedFileInfo(filevers=version_parts, prodvers=version_parts, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName', 'Notable'), StringStruct('FileDescription', APP_DISPLAY_NAME),
            StringStruct('FileVersion', __version__), StringStruct('ProductName', 'Notable'),
            StringStruct('ProductVersion', __version__), StringStruct('OriginalFilename', 'Notable.exe'),
        ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
    ),
)
