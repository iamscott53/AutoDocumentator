"""Recording engine - captures mouse, keyboard, and screenshots."""

import logging
import time
import threading
from pathlib import Path

import mss
from PIL import Image
from pynput import mouse, keyboard

from src.models import (
    MouseClickEvent, KeyPressEvent, ScrollEvent,
    ClickButton, RawEvent
)

log = logging.getLogger(__name__)

# Make process DPI-aware so coordinates match screenshot pixels
try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except AttributeError:
    pass  # Non-Windows platform


class Recorder:
    """Records mouse clicks, keyboard input, and screenshots."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.screenshots_dir = output_dir / "screenshots"
        self.events: list[RawEvent] = []
        self.start_time = 0.0
        self._mouse_listener: mouse.Listener | None = None
        self._keyboard_listener: keyboard.Listener | None = None
        self._event_lock = threading.Lock()
        self._screenshot_lock = threading.Lock()
        self._modifier_lock = threading.Lock()
        self._recording_event = threading.Event()  # Thread-safe recording flag
        self._screenshot_counter = 0
        self._active_modifiers: set[str] = set()
        self._on_event_callback = None
        self._last_click_time = 0.0
        self._last_click_pos = (0, 0)

    @property
    def is_recording(self) -> bool:
        return self._recording_event.is_set()

    def start(self, on_event_callback=None):
        """Start recording all user actions."""
        self._recording_event.set()
        self.start_time = time.time()
        self.events = []
        self._screenshot_counter = 0
        with self._modifier_lock:
            self._active_modifiers = set()
        self._on_event_callback = on_event_callback
        self._last_click_time = 0.0
        self._last_click_pos = (0, 0)

        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self._mouse_listener.start()
        self._keyboard_listener.start()

    def stop(self) -> list[RawEvent]:
        """Stop recording and return captured events."""
        self._recording_event.clear()

        # Stop and join listeners so no more events arrive after this returns
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener.join(timeout=2.0)
            self._mouse_listener = None
        if self._keyboard_listener:
            self._keyboard_listener.stop()
            self._keyboard_listener.join(timeout=2.0)
            self._keyboard_listener = None

        with self._event_lock:
            return list(self.events)

    def _capture_screenshot(self) -> Path | None:
        """Capture a full-screen screenshot and save it."""
        with self._screenshot_lock:
            try:
                self._screenshot_counter += 1
                filename = f"screenshot_{self._screenshot_counter:04d}.png"
                filepath = self.screenshots_dir / filename

                with mss.mss() as sct:
                    monitor = sct.monitors[0]
                    raw = sct.grab(monitor)
                    img = Image.frombytes("RGB", raw.size, raw.rgb)
                    try:
                        img.save(str(filepath), "PNG", optimize=True)
                    finally:
                        img.close()

                return filepath
            except OSError as e:
                log.warning("Screenshot capture failed (I/O): %s", e)
                return None
            except Exception as e:
                log.warning("Screenshot capture failed: %s", e)
                return None

    def _get_active_window(self) -> tuple[str, str]:
        """Get the title and process name of the active window."""
        try:
            import win32gui
            import win32process
            import psutil

            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                process = psutil.Process(pid)
                process_name = process.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                process_name = "unknown"
            return title, process_name
        except Exception:
            return "Unknown Window", "unknown"

    def _on_click(self, x, y, button, pressed):
        """Handle mouse click events."""
        if not self._recording_event.is_set() or not pressed:
            return

        now = time.time()
        x_int = max(0, int(x))
        y_int = max(0, int(y))

        # Debounce: ignore clicks within 50ms of the last one at the same spot
        if (now - self._last_click_time < 0.05
                and abs(x_int - self._last_click_pos[0]) < 5
                and abs(y_int - self._last_click_pos[1]) < 5):
            return

        screenshot_path = self._capture_screenshot()
        window_title, window_process = self._get_active_window()

        btn = ClickButton.LEFT
        if button == mouse.Button.right:
            btn = ClickButton.RIGHT
        elif button == mouse.Button.middle:
            btn = ClickButton.MIDDLE

        event = MouseClickEvent(
            timestamp=now,
            event_type="mouse_click",
            x=x_int,
            y=y_int,
            button=btn,
            screenshot_path=screenshot_path,
            window_title=window_title,
            window_process=window_process,
        )

        self._last_click_time = now
        self._last_click_pos = (x_int, y_int)

        with self._event_lock:
            self.events.append(event)

        if self._on_event_callback:
            try:
                self._on_event_callback(event)
            except Exception as e:
                log.debug("Event callback error: %s", e)

    def _on_scroll(self, x, y, dx, dy):
        """Handle scroll events."""
        if not self._recording_event.is_set():
            return

        window_title, _ = self._get_active_window()

        event = ScrollEvent(
            timestamp=time.time(),
            event_type="scroll",
            x=max(0, int(x)),
            y=max(0, int(y)),
            dx=int(dx),
            dy=int(dy),
            window_title=window_title,
        )

        with self._event_lock:
            self.events.append(event)

    def _on_key_press(self, key):
        """Handle key press events."""
        if not self._recording_event.is_set():
            return

        key_name, key_char, is_special = self._parse_key(key)

        # Track modifier keys but don't record them as standalone events
        normalized = key_name.replace("_l", "").replace("_r", "")
        if normalized in ("ctrl", "alt", "shift", "cmd"):
            with self._modifier_lock:
                self._active_modifiers.add(normalized)
            return

        # Determine if this is a hotkey (modifier + key, excluding plain Shift)
        with self._modifier_lock:
            non_shift_modifiers = self._active_modifiers - {"shift"}
        is_hotkey = bool(non_shift_modifiers)

        event = KeyPressEvent(
            timestamp=time.time(),
            event_type="key_press",
            key=key_name,
            key_char=key_char,
            is_special=is_special or is_hotkey,
        )

        if is_hotkey:
            event.key = "+".join(sorted(non_shift_modifiers)) + "+" + key_name

        with self._event_lock:
            self.events.append(event)

    def _on_key_release(self, key):
        """Handle key release events."""
        if not self._recording_event.is_set():
            return

        key_name, _, _ = self._parse_key(key)
        normalized = key_name.replace("_l", "").replace("_r", "")
        with self._modifier_lock:
            self._active_modifiers.discard(normalized)

    @staticmethod
    def _parse_key(key) -> tuple[str, str | None, bool]:
        """Parse a pynput key into (key_name, printable_char, is_special)."""
        try:
            char = key.char
            if char is not None:
                return char, char, False
        except AttributeError:
            pass

        key_name = str(key).replace("Key.", "")

        char_map = {
            "space": " ",
            "enter": "\n",
            "return": "\n",
            "tab": "\t",
        }

        return key_name, char_map.get(key_name), True
