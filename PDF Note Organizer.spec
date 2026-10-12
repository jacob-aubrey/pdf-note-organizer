# -*- mode: python ; coding: utf-8 -*-
from note_organizer import __version__
from PyInstaller.utils.hooks import collect_data_files


a = Analysis(
    ['PDF Note Organizer.py'],
    pathex=[],
    binaries=[],
    datas=[('Note icon.ico', '.'), ('note_organizer/assets', 'note_organizer/assets')] + collect_data_files('tkinterdnd2'),
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
    name='Notable-' + __version__,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['Note icon.ico'],
)
