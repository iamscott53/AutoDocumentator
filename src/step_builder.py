"""Step builder - converts raw events into structured documentation steps."""

import logging
from pathlib import Path

from config import DOUBLE_CLICK_THRESHOLD_MS, KEYBOARD_FLUSH_DELAY_S

log = logging.getLogger(__name__)
from src.annotator import Annotator
from src.models import (
    ActionType, ClickButton, KeyPressEvent, MouseClickEvent,
    RawEvent, Recording, ScrollEvent, Step,
)


class StepBuilder:
    """Converts a list of raw recording events into logical documentation steps."""

    def __init__(self):
        self.annotator = Annotator()

    def build_steps(self, events: list[RawEvent], output_dir: Path) -> Recording:
        """Process raw events into a structured Recording with steps.

        Args:
            events: List of raw events from the recorder
            output_dir: Directory for saving annotated screenshots

        Returns:
            A Recording object with processed steps
        """
        if not events:
            return Recording(output_dir=output_dir)

        annotated_dir = output_dir / "annotated"
        annotated_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1: Group events into logical actions
        actions = self._group_events(events)

        # Phase 2: Convert actions into steps with annotations
        steps = []
        for i, action in enumerate(actions, start=1):
            step = self._action_to_step(action, i, annotated_dir)
            if step:
                steps.append(step)

        # Renumber steps sequentially
        for i, step in enumerate(steps, start=1):
            step.number = i

        recording = Recording(
            steps=steps,
            start_time=events[0].timestamp if events else 0,
            end_time=events[-1].timestamp if events else 0,
            output_dir=output_dir,
        )
        return recording

    def _group_events(self, events: list[RawEvent]) -> list[dict]:
        """Group raw events into logical action groups.

        Groups consecutive keyboard events into typing actions,
        detects double-clicks, and handles hotkeys.
        """
        actions = []
        key_buffer: list[KeyPressEvent] = []
        i = 0

        while i < len(events):
            event = events[i]

            if isinstance(event, MouseClickEvent):
                # Flush any pending keyboard buffer
                if key_buffer:
                    actions.append(self._flush_key_buffer(key_buffer))
                    key_buffer = []

                # Check for double-click
                if (i + 1 < len(events)
                        and isinstance(events[i + 1], MouseClickEvent)):
                    next_event = events[i + 1]
                    time_diff = (next_event.timestamp - event.timestamp) * 1000
                    dist = abs(next_event.x - event.x) + abs(next_event.y - event.y)
                    if (time_diff < DOUBLE_CLICK_THRESHOLD_MS
                            and dist < 10
                            and next_event.button == event.button):
                        actions.append({
                            "type": "double_click",
                            "event": next_event,  # Use the second click's screenshot
                            "first_event": event,
                        })
                        i += 2
                        continue

                # Single click or right-click
                if event.button == ClickButton.RIGHT:
                    actions.append({"type": "right_click", "event": event})
                else:
                    actions.append({"type": "click", "event": event})

            elif isinstance(event, KeyPressEvent):
                if event.is_special and "+" in event.key:
                    # Hotkey combination (e.g., ctrl+c)
                    if key_buffer:
                        actions.append(self._flush_key_buffer(key_buffer))
                        key_buffer = []
                    actions.append({"type": "hotkey", "event": event})
                else:
                    # Regular key or simple special key
                    # Check if there's a time gap suggesting a new typing session
                    if (key_buffer
                            and event.timestamp - key_buffer[-1].timestamp
                            > KEYBOARD_FLUSH_DELAY_S):
                        actions.append(self._flush_key_buffer(key_buffer))
                        key_buffer = []
                    key_buffer.append(event)

            elif isinstance(event, ScrollEvent):
                # Flush keyboard buffer
                if key_buffer:
                    actions.append(self._flush_key_buffer(key_buffer))
                    key_buffer = []

                # Merge consecutive scrolls in the same window
                scroll_events = [event]
                while (i + 1 < len(events)
                       and isinstance(events[i + 1], ScrollEvent)
                       and events[i + 1].timestamp - event.timestamp < 2.0):
                    i += 1
                    scroll_events.append(events[i])

                actions.append({
                    "type": "scroll",
                    "events": scroll_events,
                    "event": scroll_events[0],
                })

            i += 1

        # Flush remaining keyboard buffer
        if key_buffer:
            actions.append(self._flush_key_buffer(key_buffer))

        return actions

    def _flush_key_buffer(self, buffer: list[KeyPressEvent]) -> dict:
        """Convert a buffer of key events into a typing or hotkey action."""
        typed_text = []
        special_keys = []

        for event in buffer:
            if event.key_char is not None:
                typed_text.append(event.key_char)
            elif event.is_special:
                key_name = event.key
                # Map key names to readable forms
                readable = {
                    "backspace": "[Backspace]",
                    "delete": "[Delete]",
                    "enter": "[Enter]",
                    "return": "[Enter]",
                    "tab": "[Tab]",
                    "escape": "[Esc]",
                    "up": "[Up]",
                    "down": "[Down]",
                    "left": "[Left]",
                    "right": "[Right]",
                    "home": "[Home]",
                    "end": "[End]",
                    "page_up": "[PageUp]",
                    "page_down": "[PageDown]",
                    "caps_lock": "[CapsLock]",
                }
                display = readable.get(key_name, f"[{key_name}]")
                special_keys.append(display)

        text = "".join(typed_text)

        # If it's all special keys with no text, treat as individual actions
        if not text.strip() and special_keys:
            return {
                "type": "special_keys",
                "keys": special_keys,
                "events": buffer,
                "event": buffer[0],
            }

        return {
            "type": "type",
            "text": text,
            "special_keys": special_keys,
            "events": buffer,
            "event": buffer[0],
        }

    def _action_to_step(
        self, action: dict, step_number: int, annotated_dir: Path
    ) -> Step | None:
        """Convert a grouped action into a Step object."""
        action_type = action["type"]

        if action_type == "click":
            return self._build_click_step(action, step_number, annotated_dir)
        elif action_type == "double_click":
            return self._build_click_step(
                action, step_number, annotated_dir, double=True
            )
        elif action_type == "right_click":
            return self._build_click_step(
                action, step_number, annotated_dir, right=True
            )
        elif action_type == "type":
            return self._build_type_step(action, step_number)
        elif action_type == "special_keys":
            return self._build_special_keys_step(action, step_number)
        elif action_type == "hotkey":
            return self._build_hotkey_step(action, step_number)
        elif action_type == "scroll":
            return self._build_scroll_step(action, step_number)

        return None

    def _build_click_step(
        self,
        action: dict,
        step_number: int,
        annotated_dir: Path,
        double: bool = False,
        right: bool = False,
    ) -> Step:
        """Build a step for a click action."""
        event: MouseClickEvent = action["event"]

        # Determine action type
        if double:
            action_type = ActionType.DOUBLE_CLICK
        elif right:
            action_type = ActionType.RIGHT_CLICK
        else:
            action_type = ActionType.CLICK

        # Annotate the screenshot (tolerate failures for individual images)
        annotated_path = None
        thumbnail_path = None
        if event.screenshot_path and event.screenshot_path.exists():
            try:
                annotated_path, thumbnail_path = self.annotator.annotate_screenshot(
                    event.screenshot_path,
                    event.x,
                    event.y,
                    step_number,
                    annotated_dir,
                )
            except Exception as e:
                log.warning("Annotation failed for step %d: %s", step_number, e)

        return Step(
            number=step_number,
            action_type=action_type,
            screenshot_path=event.screenshot_path,
            annotated_screenshot_path=annotated_path,
            thumbnail_path=thumbnail_path,
            timestamp=event.timestamp,
            click_x=event.x,
            click_y=event.y,
            window_title=event.window_title,
            window_process=event.window_process,
        )

    def _build_type_step(self, action: dict, step_number: int) -> Step | None:
        """Build a step for a typing action."""
        text = action.get("text", "")
        if not text.strip():
            return None

        return Step(
            number=step_number,
            action_type=ActionType.TYPE,
            typed_text=text,
            timestamp=action["event"].timestamp,
        )

    def _build_special_keys_step(self, action: dict, step_number: int) -> Step | None:
        """Build a step for special key presses (Enter, Tab, etc.)."""
        keys = action.get("keys", [])
        if not keys:
            return None

        # Skip standalone modifier-only events
        skip_keys = {"[CapsLock]"}
        filtered = [k for k in keys if k not in skip_keys]
        if not filtered:
            return None

        return Step(
            number=step_number,
            action_type=ActionType.HOTKEY,
            hotkey_combo=" ".join(filtered),
            timestamp=action["event"].timestamp,
        )

    def _build_hotkey_step(self, action: dict, step_number: int) -> Step:
        """Build a step for a keyboard shortcut."""
        event: KeyPressEvent = action["event"]

        # Format the hotkey nicely: ctrl+c -> Ctrl+C
        parts = event.key.split("+")
        formatted = "+".join(p.capitalize() for p in parts)

        return Step(
            number=step_number,
            action_type=ActionType.HOTKEY,
            hotkey_combo=formatted,
            timestamp=event.timestamp,
        )

    def _build_scroll_step(self, action: dict, step_number: int) -> Step:
        """Build a step for a scroll action."""
        event: ScrollEvent = action["event"]
        events = action.get("events", [event])

        total_dy = sum(e.dy for e in events)
        direction = "down" if total_dy < 0 else "up"

        return Step(
            number=step_number,
            action_type=ActionType.SCROLL,
            timestamp=event.timestamp,
            window_title=event.window_title,
            details={"direction": direction, "amount": abs(total_dy)},
        )
