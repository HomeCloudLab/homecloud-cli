# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — single-file homecloud binary (CLI + SDK core bundled)."""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)
SDK_ROOT = Path(os.environ.get("HOMECLOUD_SDK_ROOT", ROOT))

datas = []
binaries = []
hiddenimports = []

# Bundle first-party packages and CLI runtime deps that PyInstaller often misses.
for package in (
    "homecloud_core",
    "homecloud_sdk",
    "homecloud_cli",
    "click",
    "typer",
    "rich",
    "httpx",
    "httpcore",
    "anyio",
    "certifi",
    "yaml",
    "questionary",
):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception:
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules("homecloud_core") + collect_submodules("homecloud_sdk")
hiddenimports += collect_submodules("click")
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
    "questionary",
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
    # optimize>0 has dropped imports in past PyInstaller builds; keep 0 for reliability.
    optimize=0,
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
    # Never strip onefile binaries — strip corrupts the appended archive.
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
