"""AI-powered step analysis and full SOP generation."""

import base64
import json
import logging
import re
from pathlib import Path

from src.ai_providers import AIProvider
from src.models import ActionType, Recording, Step

log = logging.getLogger(__name__)

# Characters that could be used for prompt injection
_PROMPT_FENCE = re.compile(r"[<>\[\]{}]")


def _sanitize_for_prompt(text: str, max_len: int = 500) -> str:
    """Sanitize user-provided text before embedding in an AI prompt.

    Truncates, strips control characters, and wraps in delimiters so the
    model can distinguish user data from instructions.
    """
    if not text:
        return ""
    # Truncate
    text = text[:max_len]
    # Remove null bytes and other C0 control chars except newline/tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text


class AIAnalyzer:
    """Analyzes recordings using any AI provider for intelligent descriptions."""

    def __init__(self, provider: AIProvider):
        self.provider = provider

    # ── Per-Step Analysis ────────────────────────────────────

    def analyze_recording(
        self, recording: Recording, progress_callback=None
    ) -> Recording:
        """Analyze each step individually using screenshots and context.

        Args:
            recording: The recording to analyze
            progress_callback: Optional callback(step_num, total, status_text)

        Returns:
            The recording with AI descriptions added
        """
        total = len(recording.steps)
        for i, step in enumerate(recording.steps):
            if progress_callback:
                progress_callback(i + 1, total, f"Analyzing step {i + 1}/{total}...")

            description = self._analyze_step(step, recording)
            if description:
                step.ai_description = description

        return recording

    def _analyze_step(self, step: Step, recording: Recording) -> str | None:
        """Generate an AI description for a single step."""
        try:
            if step.action_type in (
                ActionType.CLICK,
                ActionType.DOUBLE_CLICK,
                ActionType.RIGHT_CLICK,
            ):
                return self._analyze_click_step(step, recording)
            elif step.action_type == ActionType.TYPE:
                return self._analyze_type_step(step, recording)
            elif step.action_type == ActionType.HOTKEY:
                return self._describe_hotkey(step)
            elif step.action_type == ActionType.SCROLL:
                return self._describe_scroll(step)
        except Exception as e:
            log.warning("AI analysis failed for step %d: %s", step.number, e)
            return None
        return None

    def _analyze_click_step(self, step: Step, recording: Recording) -> str | None:
        """Analyze a click step using screenshot + context."""
        img_path = step.annotated_screenshot_path or step.screenshot_path
        if not img_path or not img_path.exists():
            return None

        # Validate the file is actually a PNG image
        if not self._is_valid_image(img_path):
            return None

        image_data = self._encode_image(img_path)

        click_type = {
            ActionType.CLICK: "clicked",
            ActionType.DOUBLE_CLICK: "double-clicked",
            ActionType.RIGHT_CLICK: "right-clicked",
        }.get(step.action_type, "clicked")

        # Sanitize user-controlled strings before embedding in prompt
        safe_title = _sanitize_for_prompt(step.window_title, max_len=200)
        safe_process = _sanitize_for_prompt(step.window_process, max_len=100)

        context_lines = self._get_step_context(step, recording)
        context_section = ""
        if context_lines:
            context_section = (
                "\n\nContext from surrounding steps:\n" + "\n".join(context_lines)
            )

        prompt = (
            f"This screenshot shows a user interface. The user {click_type} on the "
            f"element highlighted with a red circle (step {step.number}).\n\n"
            f"[WINDOW_TITLE_START]{safe_title}[WINDOW_TITLE_END]\n"
            f"[APP_NAME_START]{safe_process}[APP_NAME_END]"
            f"{context_section}\n\n"
            "Based on the screenshot, write a clear, concise instruction for this "
            "step in an SOP (Standard Operating Procedure). Use the format:\n"
            '- For buttons: "Click the [Button Name] button"\n'
            '- For menus: "Click on [Menu Item] in the [Menu Name] menu"\n'
            '- For fields: "Click on the [Field Name] field"\n'
            '- For links: "Click the [Link Text] link"\n'
            '- For icons: "Click the [Icon Description] icon"\n\n'
            "Respond with ONLY the step instruction, nothing else. "
            "Keep it concise and actionable."
        )

        if self.provider.supports_vision:
            return self.provider.analyze_image(image_data, prompt)

        # Fallback for text-only providers
        fallback = (
            f"A user {click_type} at position ({step.click_x}, {step.click_y}) "
            f"in the application [APP]{safe_title}[/APP] ({safe_process})."
            f"{context_section}\n\n"
            "Write a concise SOP instruction for this click action. "
            "Respond with ONLY the instruction."
        )
        return self.provider.complete(fallback)

    def _analyze_type_step(self, step: Step, recording: Recording) -> str | None:
        """Analyze a typing step with context from preceding clicks."""
        text = step.typed_text
        context_lines = self._get_step_context(step, recording)

        # Short text: generate locally without API call
        safe_text = _sanitize_for_prompt(text, max_len=200)
        if len(text) <= 80 and not context_lines:
            safe = safe_text.replace("\n", " ").strip()
            return f'Type "{safe}"'

        context_section = ""
        if context_lines:
            context_section = (
                "\n\nContext from surrounding steps:\n" + "\n".join(context_lines)
            )

        safe_text = _sanitize_for_prompt(text, max_len=500)
        prompt = (
            "A user typed the following text in a software application:\n\n"
            f"[USER_INPUT_START]{safe_text}[USER_INPUT_END]\n"
            f"{context_section}\n\n"
            "Write a concise SOP step instruction for this typing action. "
            "If the text looks like form input, mention what kind of data it is "
            "(e.g., 'Enter the customer email address'). "
            "Respond with ONLY the instruction."
        )
        return self.provider.complete(prompt)

    def _get_step_context(self, step: Step, recording: Recording) -> list[str]:
        """Get descriptions of the steps immediately before and after this one."""
        lines = []
        for s in recording.steps:
            if s.number == step.number - 1:
                desc = s.description or s._auto_description()
                lines.append(f"  Previous step: {desc}")
            elif s.number == step.number + 1:
                desc = s.description or s._auto_description()
                lines.append(f"  Next step: {desc}")
        return lines

    @staticmethod
    def _describe_hotkey(step: Step) -> str:
        """Generate a description for a hotkey step."""
        combo = step.hotkey_combo
        known = {
            "Ctrl+C": "Copy the selected content (Ctrl+C)",
            "Ctrl+V": "Paste from clipboard (Ctrl+V)",
            "Ctrl+X": "Cut the selected content (Ctrl+X)",
            "Ctrl+Z": "Undo the last action (Ctrl+Z)",
            "Ctrl+Y": "Redo the last action (Ctrl+Y)",
            "Ctrl+S": "Save the file (Ctrl+S)",
            "Ctrl+A": "Select all content (Ctrl+A)",
            "Ctrl+F": "Open the Find dialog (Ctrl+F)",
            "Ctrl+N": "Create a new file or window (Ctrl+N)",
            "Ctrl+O": "Open a file (Ctrl+O)",
            "Ctrl+P": "Print (Ctrl+P)",
            "Ctrl+W": "Close the current tab or window (Ctrl+W)",
            "Ctrl+T": "Open a new tab (Ctrl+T)",
            "Alt+Tab": "Switch to the next window (Alt+Tab)",
            "Alt+F4": "Close the application (Alt+F4)",
            "[Enter]": "Press Enter to confirm",
            "[Tab]": "Press Tab to move to the next field",
            "[Escape]": "Press Escape to cancel",
        }
        return known.get(combo, f"Press {combo}")

    @staticmethod
    def _describe_scroll(step: Step) -> str:
        """Generate a description for a scroll step."""
        direction = step.details.get("direction", "down")
        window = _sanitize_for_prompt(step.window_title, max_len=100) or "the window"
        return f"Scroll {direction} in {window}"

    @staticmethod
    def _is_valid_image(path: Path) -> bool:
        """Check that a file is actually a valid image before processing."""
        try:
            with open(path, "rb") as f:
                header = f.read(8)
            # PNG magic bytes
            return header[:4] == b"\x89PNG"
        except OSError:
            return False

    @staticmethod
    def _encode_image(image_path: Path) -> str:
        """Base64-encode an image file."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    # ── Full SOP Generation ──────────────────────────────────

    def generate_full_sop(
        self, recording: Recording, progress_callback=None
    ) -> Recording:
        """Holistic SOP generation: sends all steps to the AI for context-aware
        rewriting, title generation, and prerequisite identification.

        This is a second-pass analysis that improves on per-step descriptions
        by letting the AI see the complete workflow.

        Args:
            recording: Recording with existing (possibly AI-generated) descriptions
            progress_callback: Optional callback(step, total, status)

        Returns:
            The recording with improved descriptions and metadata
        """
        if progress_callback:
            progress_callback(0, 1, "Building procedure summary...")

        # Build a structured summary of all steps
        steps_summary = self._build_steps_summary(recording)

        # ── Segra Copilot path: strict schema + optional grounding ──
        from src.segra.copilot_provider import SegraCopilotProvider
        if isinstance(self.provider, SegraCopilotProvider):
            return self._generate_segra_sop(recording, steps_summary, progress_callback)

        # ── Generic provider path ──
        prompt = (
            "You are an SOP (Standard Operating Procedure) specialist. "
            "Analyze the following recorded computer procedure and generate "
            "a professional SOP document.\n\n"
            "RECORDED STEPS:\n"
            f"{json.dumps(steps_summary, indent=2)}\n\n"
            "Generate the following as a JSON object:\n"
            "1. 'title': A clear, professional title for this procedure\n"
            "2. 'purpose': A 1-3 sentence description of what this procedure accomplishes\n"
            "3. 'prerequisites': A list of requirements before starting "
            "(software, access, data needed)\n"
            "4. 'steps': An array of objects with 'number' and 'description' fields, "
            "where each description is a clear, professional instruction that:\n"
            "   - Uses imperative voice ('Click...', 'Enter...', 'Select...')\n"
            "   - References specific UI elements by name when known\n"
            "   - Includes the application name when the user switches windows\n"
            "   - Mentions what data to enter for typing steps\n"
            "   - Connects to surrounding steps naturally\n\n"
            "Respond with ONLY valid JSON, no markdown fences or other text.\n"
            "Example format:\n"
            '{"title": "How to Submit a Report", '
            '"purpose": "This procedure documents...", '
            '"prerequisites": ["Access to the reporting system"], '
            '"steps": [{"number": 1, "description": "Open the Reports application"}]}'
        )

        if progress_callback:
            progress_callback(0, 1, "AI is analyzing the full procedure...")

        raw_response = self.provider.complete(prompt)

        if progress_callback:
            progress_callback(1, 1, "Processing AI response...")

        data = self._parse_json_response(raw_response)
        if not data:
            return recording

        if data.get("title"):
            recording.title = data["title"]
        if data.get("purpose"):
            recording.description = data["purpose"]

        ai_steps = {s["number"]: s["description"] for s in data.get("steps", [])}
        for step in recording.steps:
            improved = ai_steps.get(step.number)
            if improved:
                step.ai_description = improved

        return recording

    def _generate_segra_sop(self, recording, steps_summary, progress_callback):
        """Segra Copilot path — strict schema, Graph grounding, validated output."""
        from src.segra.copilot_provider import SegraCopilotProvider

        provider: SegraCopilotProvider = self.provider

        if progress_callback:
            progress_callback(0, 1, "Generating SOP via Segra Copilot...")

        sop_doc = provider.generate_sop(steps_summary)

        if progress_callback:
            progress_callback(1, 1, "Applying SOP to recording...")

        # Apply the validated SOP data back to the recording
        recording.title = sop_doc.title
        recording.description = sop_doc.purpose

        # Map procedure_steps back to recording steps
        sop_steps = {s.step: s.action for s in sop_doc.procedure_steps}
        for step in recording.steps:
            improved = sop_steps.get(step.number)
            if improved:
                step.ai_description = improved

        # Store the full SOP document on the recording for export
        recording._sop_document = sop_doc

        return recording

    @staticmethod
    def _build_steps_summary(recording) -> list[dict]:
        """Build a sanitized step summary for AI consumption."""
        steps_summary = []
        for step in recording.steps:
            entry = {
                "number": step.number,
                "action_type": step.action_type.value,
                "current_description": step.get_description(),
                "window": _sanitize_for_prompt(step.window_title, 200),
                "application": _sanitize_for_prompt(step.window_process, 100),
            }
            if step.typed_text:
                entry["typed_text"] = _sanitize_for_prompt(step.typed_text, 200)
            if step.hotkey_combo:
                entry["hotkey"] = step.hotkey_combo
            if step.details:
                entry["details"] = step.details
            steps_summary.append(entry)
        return steps_summary

    @staticmethod
    def _parse_json_response(text: str) -> dict | None:
        """Parse a JSON response, handling markdown code fences."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract the first balanced JSON object (non-greedy)
        match = re.search(r"\{[\s\S]*?\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                # Try the outermost braces as last resort
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end > start:
                    try:
                        return json.loads(text[start : end + 1])
                    except json.JSONDecodeError:
                        pass

        log.warning("Failed to parse AI JSON response: %.200s...", text)
        return None
