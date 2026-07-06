# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — single-file homecloud binary (CLI + SDK core bundled)."""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)
SDK_ROOT = Path(os.environ.get("HOMECLOUD_SDK_ROOT", ROOT.parent / "homecloud-sdk"))

datas = []
binaries = []
hiddenimports = []

for package in ("homecloud_core", "homecloud_sdk", "homecloud_cli"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules("homecloud_core") + collect_submodules("homecloud_sdk")
hiddenimports += [
    "typer",
    "click",
    "rich",
    "rich.console",
    "rich.table",
    "httpx",
    "yaml",
    "certifi",
    "anyio",
    "httpcore",
]

a = Analysis(
    ["scripts/pyinstaller_entry.py"],
    pathex=[str(ROOT), str(SDK_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="homecloud",
    debug=False,
    bootloader_ignore_signals=False,
    strip=sys.platform != "win32",
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
