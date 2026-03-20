"""Main application window for AutoDocumentator."""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from config import (
    APP_NAME, APP_DIR, WINDOW_WIDTH, WINDOW_HEIGHT,
    OUTPUT_DIR, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT,
)
from src.models import ActionType, Recording, Step
from src.recorder import Recorder
from src.step_builder import StepBuilder
from src.document_generator import DocumentGenerator
from src.ui.recording_overlay import RecordingOverlay


SETTINGS_PATH = APP_DIR / "settings.json"


class StepCard(ctk.CTkFrame):
    """A card widget displaying a single documentation step."""

    def __init__(self, parent, step: Step, on_delete=None, on_edit=None):
        super().__init__(parent, fg_color=("gray92", "gray17"), corner_radius=10)
        self.step = step
        self.on_delete = on_delete
        self.on_edit = on_edit

        self.grid_columnconfigure(1, weight=1)
        self._build()

    def _build(self):
        # Step number badge
        number_frame = ctk.CTkFrame(self, width=50, fg_color="transparent")
        number_frame.grid(row=0, column=0, rowspan=3, padx=(15, 10), pady=15, sticky="n")

        badge = ctk.CTkLabel(
            number_frame,
            text=str(self.step.number),
            width=40,
            height=40,
            corner_radius=20,
            fg_color="#e94560",
            text_color="white",
            font=("", 16, "bold"),
        )
        badge.pack()

        # Action type label
        type_colors = {
            ActionType.CLICK: ("#dbeafe", "#1e40af"),
            ActionType.DOUBLE_CLICK: ("#fce7f3", "#9d174d"),
            ActionType.RIGHT_CLICK: ("#fef3c7", "#92400e"),
            ActionType.TYPE: ("#d1fae5", "#065f46"),
            ActionType.HOTKEY: ("#ede9fe", "#5b21b6"),
            ActionType.SCROLL: ("#f3f4f6", "#374151"),
        }
        bg, fg = type_colors.get(self.step.action_type, ("#f3f4f6", "#374151"))
        type_label = ctk.CTkLabel(
            number_frame,
            text=self.step.action_type.value.replace("_", " ").title(),
            font=("", 9, "bold"),
            text_color=fg,
        )
        type_label.pack(pady=(5, 0))

        # Content area
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew", pady=15, padx=(0, 10))
        content.grid_columnconfigure(0, weight=1)

        # Editable description
        self.desc_entry = ctk.CTkEntry(
            content,
            placeholder_text="Enter step description...",
            font=("", 13),
            height=35,
        )
        self.desc_entry.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        # Set the current description
        desc = self.step.get_description()
        if desc:
            self.desc_entry.insert(0, desc)

        # Bind editing
        self.desc_entry.bind("<FocusOut>", self._on_desc_change)
        self.desc_entry.bind("<Return>", self._on_desc_change)

        # Screenshot thumbnail
        img_path = self.step.thumbnail_path or self.step.annotated_screenshot_path
        if img_path and img_path.exists():
            try:
                pil_img = Image.open(img_path)
                # Scale to fit within card
                display_w = min(THUMBNAIL_WIDTH, 380)
                ratio = display_w / pil_img.width
                display_h = int(pil_img.height * ratio)
                display_h = min(display_h, 280)

                ctk_img = ctk.CTkImage(
                    light_image=pil_img,
                    dark_image=pil_img,
                    size=(display_w, display_h),
                )
                img_label = ctk.CTkLabel(content, image=ctk_img, text="")
                img_label.grid(row=1, column=0, sticky="w", pady=(0, 5))
                # Keep reference to prevent garbage collection
                img_label._ctk_img = ctk_img
            except Exception:
                pass

        # Details row
        details_parts = []
        if self.step.typed_text:
            preview = self.step.typed_text[:60]
            if len(self.step.typed_text) > 60:
                preview += "..."
            details_parts.append(f"Text: {preview}")
        if self.step.hotkey_combo:
            details_parts.append(f"Keys: {self.step.hotkey_combo}")
        if self.step.window_title:
            details_parts.append(self.step.window_title)

        if details_parts:
            details_text = "  |  ".join(details_parts)
            details_label = ctk.CTkLabel(
                content,
                text=details_text,
                font=("", 11),
                text_color="gray",
                anchor="w",
            )
            details_label.grid(row=2, column=0, sticky="w")

        # Delete button
        delete_btn = ctk.CTkButton(
            self,
            text="X",
            width=30,
            height=30,
            font=("", 12, "bold"),
            fg_color="transparent",
            hover_color=("gray80", "gray30"),
            text_color=("gray50", "gray60"),
            command=self._on_delete,
        )
        delete_btn.grid(row=0, column=2, padx=10, pady=10, sticky="ne")

    def _on_desc_change(self, _event=None):
        """Handle description edit."""
        new_desc = self.desc_entry.get().strip()
        if new_desc and new_desc != self.step.get_description():
            self.step.description = new_desc
            if self.on_edit:
                self.on_edit(self.step)

    def _on_delete(self):
        if self.on_delete:
            self.on_delete(self.step)


class SettingsDialog(ctk.CTkToplevel):
    """Settings dialog with multi-provider AI configuration."""

    def __init__(self, parent, settings: dict, on_save=None):
        super().__init__(parent)
        self.settings = settings.copy()
        self.on_save = on_save
        self._field_widgets: dict[str, ctk.CTkEntry | ctk.CTkOptionMenu] = {}

        from src.ai_providers import PROVIDERS, get_default_config
        self._providers = PROVIDERS
        self._get_default_config = get_default_config

        self.title("Settings")
        self.geometry("520x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 520) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 520) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        # Scrollable main frame
        main = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=15)

        ctk.CTkLabel(
            main, text="Settings", font=("", 20, "bold")
        ).pack(anchor="w", pady=(0, 15))

        # ── AI Provider ──
        ctk.CTkLabel(
            main, text="AI Provider", font=("", 14, "bold")
        ).pack(anchor="w", pady=(0, 5))

        display_names = {k: v["display_name"] for k, v in self._providers.items()}
        display_list = list(display_names.values())
        current_provider = self.settings.get("provider", "anthropic")
        current_display = display_names.get(current_provider, display_list[0])

        self._provider_key_map = {v: k for k, v in display_names.items()}

        self.provider_var = ctk.StringVar(value=current_display)
        provider_menu = ctk.CTkOptionMenu(
            main,
            variable=self.provider_var,
            values=display_list,
            command=self._on_provider_change,
            font=("", 12),
            height=35,
        )
        provider_menu.pack(fill="x", pady=(0, 10))

        # Dynamic config fields container
        self.config_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.config_frame.pack(fill="x", pady=(0, 10))

        # Render fields for current provider
        self._render_provider_fields(current_provider)

        # ── Separator ──
        ctk.CTkFrame(main, height=1, fg_color=("gray80", "gray30")).pack(
            fill="x", pady=10
        )

        # ── Theme ──
        ctk.CTkLabel(
            main, text="Theme", font=("", 14, "bold")
        ).pack(anchor="w", pady=(0, 5))

        self.theme_var = ctk.StringVar(
            value=self.settings.get("theme", "dark")
        )
        ctk.CTkOptionMenu(
            main,
            variable=self.theme_var,
            values=["dark", "light", "system"],
            font=("", 12),
            height=35,
        ).pack(fill="x", pady=(0, 15))

        # ── Buttons ──
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(5, 0))

        ctk.CTkButton(
            btn_frame,
            text="Save",
            command=self._save,
            height=38,
            font=("", 13, "bold"),
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            command=self.destroy,
            height=38,
            font=("", 13),
            fg_color="transparent",
            text_color=("gray10", "gray90"),
        ).pack(side="right")

    def _on_provider_change(self, display_name: str):
        """Re-render fields when the provider selection changes."""
        provider_key = self._provider_key_map.get(display_name, "anthropic")
        self._render_provider_fields(provider_key)

    def _render_provider_fields(self, provider_key: str):
        """Render the configuration fields for a specific provider."""
        # Clear existing fields
        for widget in self.config_frame.winfo_children():
            widget.destroy()
        self._field_widgets = {}

        info = self._providers.get(provider_key, {})
        fields = info.get("fields", {})
        models = info.get("models", [])
        saved_config = self.settings.get("providers", {}).get(provider_key, {})
        defaults = self._get_default_config(provider_key)

        # Package requirement hint
        pkg = info.get("package")
        if pkg:
            ctk.CTkLabel(
                self.config_frame,
                text=f"Requires: pip install {pkg}",
                font=("", 10),
                text_color="gray",
            ).pack(anchor="w", pady=(0, 8))

        for field_name, field_info in fields.items():
            label_text = field_info.get("label", field_name.replace("_", " ").title())
            ctk.CTkLabel(
                self.config_frame, text=f"{label_text}:", font=("", 12)
            ).pack(anchor="w", pady=(2, 2))

            current_val = saved_config.get(field_name, defaults.get(field_name, ""))

            if field_info.get("type") == "dropdown" and models:
                # Dropdown for model selection
                var = ctk.StringVar(value=current_val or models[0])
                widget = ctk.CTkOptionMenu(
                    self.config_frame,
                    variable=var,
                    values=models,
                    font=("", 11),
                    height=32,
                )
                widget.pack(fill="x", pady=(0, 5))
                widget._string_var = var  # keep reference
                self._field_widgets[field_name] = widget
            else:
                # Text entry
                is_secret = field_info.get("secret", False)
                placeholder = field_info.get("placeholder", "")
                entry = ctk.CTkEntry(
                    self.config_frame,
                    placeholder_text=placeholder,
                    font=("", 11),
                    height=32,
                    show="*" if is_secret else "",
                )
                if current_val:
                    entry.insert(0, current_val)
                entry.pack(fill="x", pady=(0, 5))
                self._field_widgets[field_name] = entry

    def _save(self):
        """Collect all field values and save."""
        provider_display = self.provider_var.get()
        provider_key = self._provider_key_map.get(provider_display, "anthropic")

        # Ensure providers dict exists
        if "providers" not in self.settings:
            self.settings["providers"] = {}

        # Collect field values for the current provider
        provider_config = {}
        for field_name, widget in self._field_widgets.items():
            if isinstance(widget, ctk.CTkOptionMenu):
                provider_config[field_name] = widget._string_var.get()
            elif isinstance(widget, ctk.CTkEntry):
                provider_config[field_name] = widget.get().strip()

        self.settings["provider"] = provider_key
        self.settings["providers"][provider_key] = provider_config
        self.settings["theme"] = self.theme_var.get()

        if self.on_save:
            self.on_save(self.settings)
        self.destroy()


class MainWindow(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(800, 600)

        # State
        self.recording: Recording | None = None
        self.recorder: Recorder | None = None
        self.overlay: RecordingOverlay | None = None
        self._hotkey_listener = None
        self._step_cards: list[StepCard] = []
        self.settings = self._load_settings()

        # Apply theme
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        """Build the main window layout."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content()

    def _build_sidebar(self):
        """Build the left sidebar with controls."""
        sidebar = ctk.CTkFrame(self, width=260, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(6, weight=1)

        # App title
        title_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(25, 5))

        ctk.CTkLabel(
            title_frame,
            text="Auto",
            font=("", 22, "bold"),
            text_color="#e94560",
        ).pack(side="left")
        ctk.CTkLabel(
            title_frame,
            text="Documentator",
            font=("", 22, "bold"),
        ).pack(side="left")

        ctk.CTkLabel(
            sidebar,
            text="Record actions. Generate docs.",
            font=("", 11),
            text_color="gray",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 25))

        # Record button
        self.record_btn = ctk.CTkButton(
            sidebar,
            text="  Start Recording",
            command=self.start_recording,
            height=48,
            font=("", 15, "bold"),
            fg_color="#e94560",
            hover_color="#c53050",
            corner_radius=10,
        )
        self.record_btn.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))

        # Hotkey hint
        ctk.CTkLabel(
            sidebar,
            text="Stop: Ctrl+Shift+R",
            font=("", 10),
            text_color="gray",
        ).grid(row=3, column=0, padx=20, pady=(0, 20), sticky="w")

        # Separator
        ctk.CTkFrame(sidebar, height=1, fg_color=("gray80", "gray30")).grid(
            row=4, column=0, sticky="ew", padx=20, pady=(0, 15)
        )

        # Export section
        export_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        export_frame.grid(row=5, column=0, sticky="ew", padx=20)

        ctk.CTkLabel(
            export_frame, text="Export", font=("", 14, "bold")
        ).pack(anchor="w", pady=(0, 8))

        for fmt, label in [
            ("html", "HTML Document"),
            ("markdown", "Markdown"),
            ("docx", "Word Document"),
        ]:
            ctk.CTkButton(
                export_frame,
                text=f"  {label}",
                command=lambda f=fmt: self.export_document(f),
                height=36,
                font=("", 12),
                fg_color=("gray78", "gray25"),
                hover_color=("gray70", "gray35"),
                text_color=("gray10", "gray90"),
                anchor="w",
                corner_radius=8,
            ).pack(fill="x", pady=2)

        # Bottom section
        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.grid(row=6, column=0, sticky="sew", padx=20, pady=(10, 15))

        # AI section label
        ctk.CTkLabel(
            bottom, text="AI Tools", font=("", 14, "bold")
        ).pack(anchor="w", pady=(0, 8))

        # AI Analysis button (per-step with screenshots)
        self.ai_btn = ctk.CTkButton(
            bottom,
            text="  Analyze Steps",
            command=self.run_ai_analysis,
            height=38,
            font=("", 12, "bold"),
            fg_color="#6B21A8",
            hover_color="#7C3AED",
            corner_radius=8,
        )
        self.ai_btn.pack(fill="x", pady=(0, 4))

        # Generate Full SOP button (holistic analysis)
        self.sop_btn = ctk.CTkButton(
            bottom,
            text="  Generate Full SOP",
            command=self.generate_full_sop,
            height=38,
            font=("", 12, "bold"),
            fg_color="#0f3460",
            hover_color="#16213e",
            corner_radius=8,
        )
        self.sop_btn.pack(fill="x", pady=(0, 8))

        # Settings button
        ctk.CTkButton(
            bottom,
            text="  Settings",
            command=self.open_settings,
            height=36,
            font=("", 12),
            fg_color="transparent",
            hover_color=("gray80", "gray30"),
            text_color=("gray30", "gray70"),
            anchor="w",
            corner_radius=8,
        ).pack(fill="x", pady=(0, 5))

        # Step count
        self.step_count_label = ctk.CTkLabel(
            bottom,
            text="No recording yet",
            font=("", 11),
            text_color="gray",
        )
        self.step_count_label.pack(pady=(5, 0))

    def _build_content(self):
        """Build the main content area."""
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        # Title field
        self.title_entry = ctk.CTkEntry(
            content,
            placeholder_text="Enter procedure title...",
            font=("", 20, "bold"),
            height=50,
            corner_radius=10,
        )
        self.title_entry.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        # Description field
        self.desc_entry = ctk.CTkEntry(
            content,
            placeholder_text="Enter description (optional)...",
            font=("", 13),
            height=38,
            corner_radius=8,
        )
        self.desc_entry.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        # Scrollable step list
        self.step_list_frame = ctk.CTkScrollableFrame(
            content,
            corner_radius=10,
            fg_color=("gray95", "gray10"),
        )
        self.step_list_frame.grid(row=2, column=0, sticky="nsew")
        self.step_list_frame.grid_columnconfigure(0, weight=1)

        # Welcome message
        self.welcome_label = ctk.CTkLabel(
            self.step_list_frame,
            text=(
                "Welcome to AutoDocumentator!\n\n"
                "Click 'Start Recording' to begin.\n\n"
                "Perform the actions you want to document:\n"
                "  - Each mouse click is captured with a screenshot\n"
                "  - Keyboard input is recorded as typed text\n"
                "  - Keyboard shortcuts are detected automatically\n\n"
                "Click 'Stop Recording' or press Ctrl+Shift+R to finish.\n"
                "Then export your SOP as HTML, Markdown, or Word."
            ),
            font=("", 14),
            text_color="gray",
            justify="center",
        )
        self.welcome_label.grid(row=0, column=0, pady=80, padx=40)

    # ── Recording ────────────────────────────────────────────

    def start_recording(self):
        """Start a new recording session."""
        # Create a timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = OUTPUT_DIR / f"session_{timestamp}"
        session_dir.mkdir(parents=True, exist_ok=True)

        # Initialize recorder
        self.recorder = Recorder(session_dir)

        # Minimize main window
        self.withdraw()

        # Small delay to let the window minimize before showing overlay
        self.after(300, lambda: self._begin_recording(session_dir))

    def _begin_recording(self, session_dir):
        """Actually begin recording after window is hidden."""
        # Show recording overlay
        self.overlay = RecordingOverlay(self, on_stop_callback=self.stop_recording)

        # Start the global hotkey listener
        self._start_hotkey_listener()

        # Start recording
        self.recorder.start()

    def stop_recording(self):
        """Stop recording and process captured events."""
        if not self.recorder or not self.recorder.is_recording:
            return

        # Stop hotkey listener
        self._stop_hotkey_listener()

        # Get the overlay bounds before destroying it
        overlay_bounds = None
        if self.overlay:
            try:
                overlay_bounds = self.overlay.get_bounds()
            except Exception:
                pass
            try:
                self.overlay._timer_running = False
                self.overlay.destroy()
            except Exception:
                pass
            self.overlay = None

        # Stop recorder
        events = self.recorder.stop()
        session_dir = self.recorder.output_dir

        # Filter out the click on the stop button (last click event)
        if events and overlay_bounds:
            last_event = events[-1]
            if hasattr(last_event, "x") and hasattr(last_event, "y"):
                bx1, by1, bx2, by2 = overlay_bounds
                if bx1 <= last_event.x <= bx2 and by1 <= last_event.y <= by2:
                    events = events[:-1]

        # Show main window again
        self.deiconify()
        self.lift()
        self.focus_force()

        # Process events into steps
        if events:
            self._process_events(events, session_dir)
        else:
            messagebox.showinfo(
                "No Actions Recorded",
                "No actions were captured during the recording session.",
            )

    def _process_events(self, events, session_dir):
        """Process raw events into documentation steps."""
        self.step_count_label.configure(text="Processing...")
        self.update_idletasks()

        # Run step building in a thread to avoid freezing the UI
        def build():
            builder = StepBuilder()
            recording = builder.build_steps(events, session_dir)
            self.after(0, lambda: self._on_steps_ready(recording))

        threading.Thread(target=build, daemon=True).start()

    def _on_steps_ready(self, recording: Recording):
        """Called when step processing is complete."""
        self.recording = recording

        # Set title from entry or default
        title = self.title_entry.get().strip()
        if title:
            self.recording.title = title

        desc = self.desc_entry.get().strip()
        if desc:
            self.recording.description = desc

        # Display steps
        self._display_steps()
        self.step_count_label.configure(
            text=f"{len(recording.steps)} steps captured"
        )

    def _display_steps(self):
        """Display all steps in the scrollable list."""
        # Clear existing cards
        for card in self._step_cards:
            card.destroy()
        self._step_cards = []

        # Hide welcome message
        self.welcome_label.grid_forget()

        if not self.recording or not self.recording.steps:
            self.welcome_label.configure(text="No steps captured.")
            self.welcome_label.grid(row=0, column=0, pady=80)
            return

        for i, step in enumerate(self.recording.steps):
            card = StepCard(
                self.step_list_frame,
                step,
                on_delete=self._delete_step,
                on_edit=self._on_step_edited,
            )
            card.grid(row=i, column=0, sticky="ew", padx=5, pady=4)
            self._step_cards.append(card)

    def _delete_step(self, step: Step):
        """Delete a step from the recording."""
        if not self.recording:
            return

        self.recording.steps.remove(step)
        # Renumber remaining steps
        for i, s in enumerate(self.recording.steps, start=1):
            s.number = i

        self._display_steps()
        self.step_count_label.configure(
            text=f"{len(self.recording.steps)} steps"
        )

    def _on_step_edited(self, step: Step):
        """Handle step description edit."""
        pass  # Description is updated in-place on the Step object

    # ── Hotkey Listener ──────────────────────────────────────

    def _start_hotkey_listener(self):
        """Start listening for the stop-recording hotkey."""
        from pynput import keyboard

        def on_activate():
            # Schedule stop on the main thread
            self.after(0, self.stop_recording)

        self._hotkey_listener = keyboard.GlobalHotKeys({
            "<ctrl>+<shift>+r": on_activate
        })
        self._hotkey_listener.start()

    def _stop_hotkey_listener(self):
        """Stop the hotkey listener."""
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

    # ── Export ───────────────────────────────────────────────

    def export_document(self, fmt: str):
        """Export the recording as a document."""
        if not self.recording or not self.recording.steps:
            messagebox.showwarning(
                "No Recording",
                "Please record some actions before exporting.",
            )
            return

        # Update recording metadata from UI
        title = self.title_entry.get().strip()
        if title:
            self.recording.title = title
        desc = self.desc_entry.get().strip()
        if desc:
            self.recording.description = desc

        # Ask for save location
        extensions = {
            "html": ("HTML files", "*.html"),
            "markdown": ("Markdown files", "*.md"),
            "docx": ("Word documents", "*.docx"),
        }
        ext_name, ext_pattern = extensions[fmt]
        file_ext = ext_pattern.replace("*", "")

        default_name = self.recording.title.replace(" ", "_")[:50]
        output_path = filedialog.asksaveasfilename(
            title="Export Document",
            defaultextension=file_ext,
            filetypes=[(ext_name, ext_pattern), ("All files", "*.*")],
            initialfile=f"{default_name}{file_ext}",
            initialdir=str(OUTPUT_DIR),
        )

        if not output_path:
            return

        output_path = Path(output_path)

        try:
            generator = DocumentGenerator()

            if fmt == "html":
                result = generator.export_html(self.recording, output_path)
            elif fmt == "markdown":
                result = generator.export_markdown(self.recording, output_path)
            elif fmt == "docx":
                result = generator.export_docx(self.recording, output_path)
            else:
                return

            messagebox.showinfo(
                "Export Complete",
                f"Document saved to:\n{result}",
            )

            # Open the file
            os.startfile(str(result))

        except Exception as e:
            messagebox.showerror("Export Failed", f"Error exporting document:\n{e}")

    # ── AI Analysis ──────────────────────────────────────────

    def _create_ai_provider(self):
        """Create an AI provider from current settings.

        Returns the provider, or None if configuration is missing.
        Shows appropriate error dialogs.
        """
        from src.ai_providers import create_provider, PROVIDERS

        provider_key = self.settings.get("provider", "anthropic")
        provider_config = self.settings.get("providers", {}).get(provider_key, {})

        # Check that at least some config exists
        info = PROVIDERS.get(provider_key, {})
        required_fields = [
            f for f, meta in info.get("fields", {}).items()
            if meta.get("secret") or f in ("endpoint", "deployment")
        ]
        missing = [f for f in required_fields if not provider_config.get(f)]

        if missing:
            display = info.get("display_name", provider_key)
            messagebox.showwarning(
                "AI Not Configured",
                f"Please configure {display} in Settings first.\n\n"
                f"Missing: {', '.join(missing)}",
            )
            self.open_settings()
            return None

        try:
            return create_provider(provider_key, **provider_config)
        except ImportError as e:
            messagebox.showerror("Missing Package", str(e))
            return None
        except Exception as e:
            # Show only the exception type, never the message (may contain secrets)
            messagebox.showerror(
                "Provider Error",
                f"Failed to create AI provider.\n"
                f"Error type: {type(e).__name__}\n\n"
                "Check your configuration in Settings.",
            )
            return None

    def _show_progress_dialog(self, title: str) -> tuple:
        """Create and return (dialog, progress_bar, label) for AI operations."""
        progress = ctk.CTkToplevel(self)
        progress.title(title)
        progress.geometry("420x180")
        progress.resizable(False, False)
        progress.transient(self)
        progress.grab_set()

        progress.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 420) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        progress.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            progress, text=title, font=("", 15, "bold")
        ).pack(pady=(25, 15))

        bar = ctk.CTkProgressBar(progress, width=360)
        bar.pack(padx=30)
        bar.set(0)

        label = ctk.CTkLabel(
            progress, text="Preparing...", font=("", 12), text_color="gray"
        )
        label.pack(pady=10)

        return progress, bar, label

    def run_ai_analysis(self):
        """Run per-step AI analysis using the configured provider."""
        if not self.recording or not self.recording.steps:
            messagebox.showwarning(
                "No Recording",
                "Please record some actions before running AI analysis.",
            )
            return

        provider = self._create_ai_provider()
        if not provider:
            return

        progress, bar, label = self._show_progress_dialog("Analyzing Steps with AI")

        def update_progress(step_num, total, status):
            bar.set(step_num / total)
            label.configure(text=status)

        def analyze():
            try:
                from src.ai_analyzer import AIAnalyzer
                analyzer = AIAnalyzer(provider)
                analyzer.analyze_recording(
                    self.recording,
                    progress_callback=lambda s, t, msg: self.after(
                        0, update_progress, s, t, msg
                    ),
                )
                self.after(0, on_complete, None)
            except Exception as e:
                self.after(0, on_complete, f"{type(e).__name__}: check configuration")

        def on_complete(error):
            progress.destroy()
            if error:
                messagebox.showerror("Analysis Failed", f"AI analysis failed:\n{error}")
            else:
                self._display_steps()
                messagebox.showinfo(
                    "Analysis Complete",
                    "AI descriptions have been generated for all steps.",
                )

        threading.Thread(target=analyze, daemon=True).start()

    def generate_full_sop(self):
        """Run holistic SOP generation - AI reviews all steps together."""
        if not self.recording or not self.recording.steps:
            messagebox.showwarning(
                "No Recording",
                "Please record some actions before generating an SOP.",
            )
            return

        provider = self._create_ai_provider()
        if not provider:
            return

        progress, bar, label = self._show_progress_dialog("Generating Full SOP")

        def update_progress(step_num, total, status):
            if total > 0:
                bar.set(step_num / total)
            label.configure(text=status)

        def generate():
            try:
                from src.ai_analyzer import AIAnalyzer
                analyzer = AIAnalyzer(provider)
                analyzer.generate_full_sop(
                    self.recording,
                    progress_callback=lambda s, t, msg: self.after(
                        0, update_progress, s, t, msg
                    ),
                )
                self.after(0, on_complete, None)
            except Exception as e:
                self.after(0, on_complete, f"{type(e).__name__}: check configuration")

        def on_complete(error):
            progress.destroy()
            if error:
                messagebox.showerror("SOP Generation Failed", f"Error:\n{error}")
            else:
                # Update the title/description in the UI
                if self.recording.title and self.recording.title != "Untitled Procedure":
                    self.title_entry.delete(0, "end")
                    self.title_entry.insert(0, self.recording.title)
                if self.recording.description:
                    self.desc_entry.delete(0, "end")
                    self.desc_entry.insert(0, self.recording.description)
                self._display_steps()
                messagebox.showinfo(
                    "SOP Generated",
                    "The AI has generated a full SOP with improved step "
                    "descriptions, title, and summary.",
                )

        threading.Thread(target=generate, daemon=True).start()

    # ── Settings ─────────────────────────────────────────────

    # Fields whose values should be encrypted on disk
    _SENSITIVE_FIELDS = {"api_key"}

    def open_settings(self):
        """Open the settings dialog."""
        SettingsDialog(self, self.settings, on_save=self._save_settings)

    def _save_settings(self, new_settings: dict):
        """Save settings to disk (atomic write, encrypted secrets)."""
        self.settings = new_settings

        # Prepare a copy with sensitive fields encrypted
        save_data = json.loads(json.dumps(new_settings))  # deep copy
        for provider_cfg in save_data.get("providers", {}).values():
            for field in self._SENSITIVE_FIELDS:
                val = provider_cfg.get(field)
                if val and not val.startswith("enc:"):
                    provider_cfg[field] = self._encrypt_value(val)

        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: write to temp file, then rename
            tmp_path = SETTINGS_PATH.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(save_data, indent=2), encoding="utf-8"
            )
            tmp_path.replace(SETTINGS_PATH)
        except Exception as e:
            messagebox.showwarning("Settings", f"Failed to save settings: {e}")

        ctk.set_appearance_mode(self.settings.get("theme", "dark"))

    def _load_settings(self) -> dict:
        """Load settings from disk, migrating old format and decrypting secrets."""
        from src.ai_providers import get_default_config, get_provider_names

        defaults = {
            "provider": "segra_copilot",
            "theme": "dark",
            "providers": {
                name: get_default_config(name) for name in get_provider_names()
            },
        }

        try:
            if SETTINGS_PATH.exists():
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))

                # Migrate old single-provider format
                if "api_key" in data and "providers" not in data:
                    defaults["provider"] = "anthropic"
                    defaults["providers"]["anthropic"]["api_key"] = data["api_key"]
                    if data.get("ai_model"):
                        defaults["providers"]["anthropic"]["model"] = data["ai_model"]
                    if data.get("theme"):
                        defaults["theme"] = data["theme"]
                else:
                    if data.get("provider"):
                        defaults["provider"] = data["provider"]
                    if data.get("theme"):
                        defaults["theme"] = data["theme"]
                    if data.get("providers"):
                        for k, v in data["providers"].items():
                            if k in defaults["providers"]:
                                defaults["providers"][k].update(v)
                            else:
                                defaults["providers"][k] = v

                # Decrypt sensitive fields in memory
                for provider_cfg in defaults["providers"].values():
                    for field in self._SENSITIVE_FIELDS:
                        val = provider_cfg.get(field, "")
                        if val.startswith("enc:"):
                            provider_cfg[field] = self._decrypt_value(val)
        except json.JSONDecodeError:
            pass  # Corrupted settings file; use defaults
        except Exception:
            pass
        return defaults

    @staticmethod
    def _encrypt_value(value: str) -> str:
        """Encrypt a sensitive value using Windows DPAPI.

        Falls back to a base64 marker if DPAPI is unavailable.
        """
        try:
            import win32crypt
            encrypted = win32crypt.CryptProtectData(
                value.encode("utf-8"), "AutoDocumentator"
            )
            import base64 as b64
            return "enc:" + b64.b64encode(encrypted).decode("ascii")
        except Exception:
            # Non-Windows or pywin32 issue; store with marker but not encrypted
            import base64 as b64
            return "enc:" + b64.b64encode(value.encode("utf-8")).decode("ascii")

    @staticmethod
    def _decrypt_value(encrypted: str) -> str:
        """Decrypt a DPAPI-encrypted value (with enc: prefix)."""
        raw = encrypted.removeprefix("enc:")
        import base64 as b64
        data = b64.b64decode(raw)
        try:
            import win32crypt
            _, decrypted = win32crypt.CryptUnprotectData(data)
            return decrypted.decode("utf-8")
        except Exception:
            # Fallback: assume it was just base64-encoded (non-DPAPI path)
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return ""

    # ── Cleanup ──────────────────────────────────────────────

    def _on_close(self):
        """Handle window close with guaranteed cleanup."""
        try:
            if self.recorder and self.recorder.is_recording:
                self.stop_recording()
        finally:
            try:
                self._stop_hotkey_listener()
            finally:
                self.destroy()
