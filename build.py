"""Build script for AutoDocumentator EXE.

Usage:
    python build.py          Build the EXE
    python build.py clean    Remove build artifacts
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SPEC_FILE = ROOT / "AutoDocumentator.spec"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"


def clean():
    """Remove build artifacts."""
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            print(f"Removing {d}")
            shutil.rmtree(d)
    print("Clean complete.")


def build():
    """Build the EXE using PyInstaller."""
    print("=" * 50)
    print("  Building AutoDocumentator EXE")
    print("=" * 50)

    # Verify PyInstaller is available
    try:
        import PyInstaller
        print(f"  PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("ERROR: PyInstaller not found. Install with: pip install pyinstaller")
        sys.exit(1)

    # Run PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC_FILE),
        "--clean",
        "--noconfirm",
    ]

    print(f"\n  Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        print("\nBuild FAILED.")
        sys.exit(1)

    exe_path = DIST_DIR / "AutoDocumentator.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n{'=' * 50}")
        print(f"  BUILD SUCCESSFUL!")
        print(f"  EXE: {exe_path}")
        print(f"  Size: {size_mb:.1f} MB")
        print(f"{'=' * 50}")
    else:
        print("\nWARNING: EXE not found at expected path.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean()
    else:
        build()
