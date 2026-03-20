"""AutoDocumentator - Automatic action documentation tool.

Records mouse clicks, keyboard input, and screenshots to generate
step-by-step documentation (SOPs) automatically.

Usage:
    python main.py
"""

import os
import sys
from pathlib import Path

# PyInstaller windowed mode sets sys.stdout/stderr to None.
# Redirect to devnull so libraries that write warnings don't crash.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def main():
    # Ensure DPI awareness on Windows for correct screenshot coordinates
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

    from src.ui.main_window import MainWindow

    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
