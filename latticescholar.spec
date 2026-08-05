# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for LatticeScholar desktop build.

Build:
    pip install pyinstaller
    pyinstaller latticescholar.spec

Output:  dist/LatticeScholar/  (onedir mode)
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = Path(SPECPATH)
SRC = ROOT / "src"

block_cipher = None

# ---------------------------------------------------------------------------
# Hidden imports — modules that PyInstaller cannot discover via static analysis
# ---------------------------------------------------------------------------
hidden = []
hidden += collect_submodules("uvicorn")
hidden += collect_submodules("anyio")
hidden += collect_submodules("starlette")
hidden += collect_submodules("fastapi")
hidden += collect_submodules("pydantic")
hidden += collect_submodules("httpx")
hidden += collect_submodules("httpcore")
hidden += [
    "h11",
    "multipart",
    "multipart.multipart",
    "email.mime.text",
    "email.mime.multipart",
    "email.mime.nonmultipart",
    "cryptography",
    "cryptography.fernet",
    "cryptography.hazmat.primitives.kdf.pbkdf2",
    "pdfplumber",
    "pypdf",
    "latticescholar",
    "latticescholar.main",
    "latticescholar.cli",
    "latticescholar.config",
    "latticescholar.db",
    "latticescholar.models",
    "latticescholar.text_utils",
]
hidden += collect_submodules("latticescholar.services")

# ---------------------------------------------------------------------------
# Data files — static assets and bundled JSON shipped with the package
# ---------------------------------------------------------------------------
datas = [
    (str(SRC / "latticescholar" / "static"), "latticescholar/static"),
    (str(SRC / "latticescholar" / "data"), "latticescholar/data"),
]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(ROOT / "scripts" / "desktop_entry.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "PIL.ImageTk",
        "pytest",
        "ruff",
        "reportlab",
        "pymupdf",
        "pymupdf4llm",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LatticeScholar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(SRC / "latticescholar" / "static" / "favicon.svg")
    if sys.platform != "win32"
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LatticeScholar",
)
