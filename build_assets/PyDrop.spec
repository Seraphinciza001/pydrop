# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += [m for m in collect_submodules('webview') if not m.startswith(('webview.platforms.qt', 'webview.platforms.gtk', 'webview.platforms.cocoa', 'webview.platforms.android'))]


a = Analysis(
    ['../app/pydrop.py'],
    pathex=[],
    binaries=[],
    datas=[('E:/pydrop ok/app/ui', 'app/ui'), ('E:/pydrop ok/mob/index.html', 'mob'), ('E:/pydrop ok/mob/envelope.js', 'mob'), ('E:/pydrop ok/mob/splash.js', 'mob'), ('E:/pydrop ok/app/shell/PyDropSend.exe', 'app/shell'), ('E:/pydrop ok/mob/SVG Mobile', 'mob/SVG Mobile')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'pygame', 'kivy', 'kivymd', 'PIL', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'qtpy', 'gi', 'IPython', 'jupyter', 'notebook', 'scipy', 'cv2', 'torch', 'tensorflow', 'webview.platforms.qt', 'webview.platforms.gtk', 'webview.platforms.cocoa', 'webview.platforms.android'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PyDrop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['E:/pydrop ok/build_assets/pydrop.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PyDrop',
)
