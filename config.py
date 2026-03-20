"""Configuration constants for AutoDocumentator."""

import os
import sys
from pathlib import Path

# Application
APP_NAME = "AutoDocumentator"
APP_VERSION = "1.0.0"

# Paths — handle both normal Python and PyInstaller frozen EXE
if getattr(sys, "frozen", False):
    # Running as a PyInstaller bundle
    _BUNDLE_DIR = Path(sys._MEIPASS)          # extracted temp dir (read-only resources)
    _APP_DIR = Path(sys.executable).parent    # folder next to the .exe (user data)
else:
    _BUNDLE_DIR = Path(__file__).parent
    _APP_DIR = Path(__file__).parent

BASE_DIR = _BUNDLE_DIR
APP_DIR = _APP_DIR
OUTPUT_DIR = _APP_DIR / "output"
TEMPLATES_DIR = _BUNDLE_DIR / "templates"
ASSETS_DIR = _BUNDLE_DIR / "assets"

# Recording settings
SCREENSHOT_FORMAT = "png"
SCREENSHOT_QUALITY = 95
CROP_WIDTH = 800
CROP_HEIGHT = 600
DOUBLE_CLICK_THRESHOLD_MS = 400
DEBOUNCE_THRESHOLD_MS = 100
KEYBOARD_FLUSH_DELAY_S = 1.5  # Seconds of inactivity before flushing keyboard buffer

# Annotation settings
CIRCLE_RADIUS = 30
CIRCLE_COLOR = (255, 50, 50)  # Red
CIRCLE_OUTLINE_WIDTH = 4
CIRCLE_GLOW_COLOR = (255, 50, 50, 80)  # Semi-transparent red
CIRCLE_GLOW_RADIUS = 45
STEP_BADGE_SIZE = 32
STEP_BADGE_COLOR = (255, 50, 50)
STEP_BADGE_TEXT_COLOR = (255, 255, 255)

# AI Analysis
DEFAULT_AI_MODEL = "claude-sonnet-4-6-20250514"
AI_MAX_TOKENS = 1024

# Document generation
DEFAULT_EXPORT_FORMAT = "html"
SUPPORTED_FORMATS = ["html", "markdown", "docx"]

# UI settings
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
OVERLAY_WIDTH = 220
OVERLAY_HEIGHT = 80
THUMBNAIL_WIDTH = 400
THUMBNAIL_HEIGHT = 300

# Hotkeys
STOP_RECORDING_HOTKEY = "<ctrl>+<shift>+r"

# Ensure output directory exists
OUTPUT_DIR.mkdir(exist_ok=True)
