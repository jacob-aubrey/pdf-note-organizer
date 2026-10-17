# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct


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
        ffi=FixedFileInfo(filevers=(2, 6, 0, 0), prodvers=(2, 6, 0, 0), mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName', 'Notable'), StringStruct('FileDescription', 'Notable research document organizer'),
            StringStruct('FileVersion', '2.6.0'), StringStruct('ProductName', 'Notable'),
            StringStruct('ProductVersion', '2.6.0'), StringStruct('OriginalFilename', 'Notable.exe'),
        ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
    ),
)
