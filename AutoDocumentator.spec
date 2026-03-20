# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for AutoDocumentator."""

import os
import importlib

block_cipher = None

# ── Locate package data directories ────────────────────────

def get_package_dir(pkg_name):
    """Return the installed package directory path."""
    mod = importlib.import_module(pkg_name)
    return os.path.dirname(mod.__file__)

customtkinter_dir = get_package_dir("customtkinter")

# ── Data files to bundle ──────────────────────────────────

datas = [
    # HTML template for SOP export
    ("templates", "templates"),
    # App icon
    ("assets", "assets"),
    # customtkinter theme/assets (required for UI to render)
    (customtkinter_dir, "customtkinter"),
]

# ── Hidden imports ────────────────────────────────────────

hiddenimports = [
    # pynput platform backends (Windows)
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    # pywin32
    "win32gui",
    "win32process",
    "win32api",
    "win32con",
    "pywintypes",
    "win32crypt",
    # PIL plugins
    "PIL._tkinter_finder",
    # mss platform backend
    "mss.windows",
    # Jinja2
    "jinja2.ext",
    # docx internals
    "docx",
    "lxml._elementpath",
    "lxml.etree",
    # AI providers
    "anthropic",
    "openai",
    "httpx",
    "httpcore",
    "anyio",
    "anyio._backends",
    "anyio._backends._asyncio",
    "sniffio",
    "certifi",
    "h11",
    "jiter",
    # Segra M365 Copilot
    "msal",
    "src.segra",
    "src.segra.auth",
    "src.segra.graph_client",
    "src.segra.copilot_provider",
    "src.segra.schemas",
    "src.segra.renderer",
    # psutil
    "psutil",
    # tkinter
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
]

# ── Excluded modules (reduce size) ────────────────────────

excludes = [
    "matplotlib",
    "numpy",
    "scipy",
    "pandas",
    "pytest",
    "notebook",
    "IPython",
    "sphinx",
    "unittest",
    "test",
    "setuptools",
    "wheel",
    "pip",
]

# ── Analysis ──────────────────────────────────────────────

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Directory-based build ────────────────────────────────
# --onedir is far less likely to be flagged by EDR/antivirus than --onefile.
# --onefile extracts to a random temp directory at runtime, which looks like
# malware unpacking to behavioral detection engines (CrowdStrike, Defender, etc).

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoDocumentator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # Disable UPX — compressed binaries trigger AV heuristics
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
    uac_admin=False,
    version="version_info.txt",   # Embedded version metadata — identifies publisher
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="AutoDocumentator",
)
