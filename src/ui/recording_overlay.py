"""Recording overlay - floating indicator shown during recording."""

import time
import customtkinter as ctk

from config import OVERLAY_WIDTH, OVERLAY_HEIGHT


class RecordingOverlay(ctk.CTkToplevel):
    """A small floating overlay that shows recording status and a stop button."""

    def __init__(self, parent, on_stop_callback):
        super().__init__(parent)
        self.on_stop_callback = on_stop_callback
        self._start_time = time.time()
        self._timer_running = True
        self._after_id = None  # Track the scheduled callback for cancellation

        self._setup_window()
        self._setup_ui()
        self._update_timer()

    def _setup_window(self):
        """Configure the overlay window properties."""
        self.title("")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.92)

        screen_w = self.winfo_screenwidth()
        x = screen_w - OVERLAY_WIDTH - 20
        y = 20
        self.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+{x}+{y}")

        self._drag_x = 0
        self._drag_y = 0
        self.bind("<Button-1>", self._start_drag)
        self.bind("<B1-Motion>", self._do_drag)

    def _setup_ui(self):
        """Build the overlay UI."""
        self.configure(fg_color="#1a1a2e", corner_radius=12)

        main_frame = ctk.CTkFrame(self, fg_color="#1a1a2e", corner_radius=12)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)

        top_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        top_frame.pack(fill="x", padx=12, pady=(10, 5))

        self.dot_label = ctk.CTkLabel(
            top_frame,
            text="\u2b24",
            font=("", 14),
            text_color="#e94560",
            width=20,
        )
        self.dot_label.pack(side="left")

        ctk.CTkLabel(
            top_frame,
            text="Recording",
            font=("", 13, "bold"),
            text_color="white",
        ).pack(side="left", padx=(4, 0))

        self.timer_label = ctk.CTkLabel(
            top_frame,
            text="00:00",
            font=("Consolas", 13),
            text_color="#aaa",
        )
        self.timer_label.pack(side="right")

        ctk.CTkButton(
            main_frame,
            text="\u25a0  Stop Recording",
            command=self._on_stop,
            height=30,
            font=("", 12, "bold"),
            fg_color="#e94560",
            hover_color="#c53050",
            corner_radius=6,
        ).pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(
            main_frame,
            text="or press Ctrl+Shift+R",
            font=("", 9),
            text_color="#666",
        ).pack(pady=(0, 6))

    def _update_timer(self):
        """Update the elapsed time display."""
        if not self._timer_running:
            return

        try:
            elapsed = time.time() - self._start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            self.timer_label.configure(text=f"{minutes:02d}:{seconds:02d}")

            current_color = self.dot_label.cget("text_color")
            new_color = "#1a1a2e" if current_color == "#e94560" else "#e94560"
            self.dot_label.configure(text_color=new_color)

            self._after_id = self.after(500, self._update_timer)
        except Exception:
            # Widget was destroyed between check and update
            self._timer_running = False

    def _on_stop(self):
        """Handle the stop button click."""
        self._timer_running = False
        # Cancel any pending timer callback to prevent use-after-destroy
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self.on_stop_callback:
            self.on_stop_callback()
        try:
            self.destroy()
        except Exception:
            pass

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event):
        x = self.winfo_x() + event.x - self._drag_x
        y = self.winfo_y() + event.y - self._drag_y
        self.geometry(f"+{x}+{y}")

    def get_bounds(self) -> tuple[int, int, int, int]:
        """Return the overlay's screen bounds (x1, y1, x2, y2)."""
        x = self.winfo_x()
        y = self.winfo_y()
        return (x, y, x + OVERLAY_WIDTH, y + OVERLAY_HEIGHT)
