"""Data models for AutoDocumentator."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ActionType(Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE = "type"
    HOTKEY = "hotkey"
    SCROLL = "scroll"


class ClickButton(Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


@dataclass
class RawEvent:
    """A raw input event captured during recording."""
    timestamp: float
    event_type: str  # 'mouse_click', 'mouse_release', 'key_press', 'key_release', 'scroll'


@dataclass
class MouseClickEvent(RawEvent):
    x: int = 0
    y: int = 0
    button: ClickButton = ClickButton.LEFT
    screenshot_path: Optional[Path] = None
    window_title: str = ""
    window_process: str = ""


@dataclass
class KeyPressEvent(RawEvent):
    key: str = ""
    key_char: Optional[str] = None  # The actual character, if printable
    is_special: bool = False


@dataclass
class ScrollEvent(RawEvent):
    x: int = 0
    y: int = 0
    dx: int = 0
    dy: int = 0
    window_title: str = ""


@dataclass
class Step:
    """A single documented step in the procedure."""
    number: int
    action_type: ActionType
    description: str = ""
    ai_description: str = ""
    screenshot_path: Optional[Path] = None
    annotated_screenshot_path: Optional[Path] = None
    thumbnail_path: Optional[Path] = None
    timestamp: float = 0.0
    details: dict = field(default_factory=dict)
    # For click actions
    click_x: int = 0
    click_y: int = 0
    window_title: str = ""
    window_process: str = ""
    # For type actions
    typed_text: str = ""
    # For hotkey actions
    hotkey_combo: str = ""

    def get_description(self) -> str:
        """Return the best available description."""
        if self.ai_description:
            return self.ai_description
        if self.description:
            return self.description
        return self._auto_description()

    def _auto_description(self) -> str:
        """Generate an automatic description based on action type."""
        if self.action_type == ActionType.CLICK:
            return f"Click at ({self.click_x}, {self.click_y}) in {self.window_title}"
        elif self.action_type == ActionType.DOUBLE_CLICK:
            return f"Double-click at ({self.click_x}, {self.click_y}) in {self.window_title}"
        elif self.action_type == ActionType.RIGHT_CLICK:
            return f"Right-click at ({self.click_x}, {self.click_y}) in {self.window_title}"
        elif self.action_type == ActionType.TYPE:
            text_preview = self.typed_text[:50] + ("..." if len(self.typed_text) > 50 else "")
            return f'Type "{text_preview}"'
        elif self.action_type == ActionType.HOTKEY:
            return f"Press {self.hotkey_combo}"
        elif self.action_type == ActionType.SCROLL:
            return f"Scroll in {self.window_title}"
        return "Unknown action"


@dataclass
class Recording:
    """A complete recording session."""
    title: str = "Untitled Procedure"
    description: str = ""
    steps: list[Step] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    output_dir: Optional[Path] = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def step_count(self) -> int:
        return len(self.steps)
