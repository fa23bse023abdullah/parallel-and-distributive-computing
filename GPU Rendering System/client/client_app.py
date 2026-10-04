"""
client_app.py - Client Desktop GUI Application (Luxury White & Colorful Cards Edition)
======================================================================================

Ultra-premium, hardware-accelerated desktop application built with CustomTkinter
for submitting render/compute jobs to the remote GPU worker node.

Features:
- Crisp Studio White / Soft Slate Theme with Vibrant, Colorful Elevated Cards
- Live Dual-Wave Harmonic Sinusoidal Canvas Animation
- Length-prefixed TCP protocol & checksum-validated file offloading
- Real-time progress bar, speed metrics, and live log terminal
- Local CPU vs. Remote GPU benchmarking engine
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import time
import os
import sys
import json
import math
from PIL import Image

try:
    import winsound
except ImportError:
    winsound = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.protocol import (
    RENDER_PRESETS, RESOLUTIONS, BITRATES, DEFAULT_SERVER_PORT
)
from common.utils import (
    format_bytes, format_duration, is_supported_video,
    get_video_info, setup_logger, get_system_info,
    generate_video_thumbnail
)
from client.network_handler import NetworkHandler, ConnectionState


# ─── Theme Configuration ─────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ─── Dual Theme Design System (Light & Dark Studio Palettes) ─────
COLORS = {
    # Main Backdrop & Card Surfaces
    "bg_app":           ("#F1F5F9", "#0B0F19"),  # Modern Light Studio Pearl / Deep Cyber Obsidian
    "card_bg":          ("#FFFFFF", "#111827"),  # Pure Pristine White / Elevated Dark Slate Card
    "card_bg_subtle":   ("#F8FAFC", "#1E293B"),  # Subtle Fill / Dark Slate Surface
    "card_border":      ("#E2E8F0", "#243248"),  # Crisp Light Border / Dark Contrast Border
    "card_border_glow": ("#6366F1", "#818CF8"),  # Indigo Accent Border Glow

    # Text Hierarchy
    "text_title":       ("#0F172A", "#F8FAFC"),  # Deep Obsidian Navy / Crisp White
    "text_primary":     ("#1E293B", "#E2E8F0"),  # Slate Text / Soft White
    "text_secondary":   ("#64748B", "#94A3B8"),  # Muted Slate Gray / Clean Muted Gray
    "text_muted":       ("#94A3B8", "#64748B"),  # Dim Gray / Deep Dim Gray

    # Buttons & Active Surfaces (High contrast white text)
    "btn_primary":       ("#4F46E5", "#4F46E5"),
    "btn_primary_hover": ("#4338CA", "#4338CA"),
    "btn_cyan":          ("#0284C7", "#0284C7"),
    "btn_cyan_hover":    ("#0369A1", "#0369A1"),

    # Colorful Card Accent Palettes
    # Indigo / Violet (Worker Node Connection & Headers)
    "indigo_primary":   ("#4F46E5", "#818CF8"),
    "indigo_hover":     ("#4338CA", "#4F46E5"),
    "indigo_subtle":    ("#EEF2FF", "#1E1B4B"),
    "indigo_border":    ("#C7D2FE", "#3730A3"),

    # Sky Blue / Cyan (Input Media Asset)
    "cyan_primary":     ("#0284C7", "#38BDF8"),
    "cyan_hover":       ("#0369A1", "#0284C7"),
    "cyan_subtle":      ("#F0F9FF", "#082F49"),
    "cyan_border":      ("#BAE6FD", "#075985"),

    # Amber / Coral (Render Hardware Config Card)
    "amber_primary":    ("#D97706", "#FBBF24"),
    "amber_hover":      ("#B45309", "#D97706"),
    "amber_subtle":     ("#FFFBEB", "#451A03"),
    "amber_border":     ("#FDE68A", "#78350F"),

    # Emerald / Mint (Telemetry & Progress Card)
    "emerald_primary":  ("#059669", "#34D399"),
    "emerald_hover":    ("#047857", "#059669"),
    "emerald_subtle":   ("#ECFDF5", "#064E3B"),
    "emerald_border":   ("#A7F3D0", "#065F46"),

    # Rose / Coral (Alerts & Disconnect)
    "rose_primary":     ("#E11D48", "#FB7185"),
    "rose_hover":       ("#BE123C", "#E11D48"),
    "rose_subtle":      ("#FFF1F2", "#4C0519"),
    "rose_border":      ("#FDA4AF", "#881337"),

    # Purple / Lavender (Speed & Metrics)
    "purple_primary":   ("#7C3AED", "#C084FC"),
    "purple_hover":     ("#6D28D9", "#7C3AED"),
    "purple_subtle":    ("#FAF5FF", "#3B0764"),
    "purple_border":    ("#DDD6FE", "#581C87"),

    # Progress Bar
    "progress_bg":      ("#E2E8F0", "#1E293B"),
    "progress_fill":    ("#10B981", "#34D399"),

    # Terminal Specific (Obsidian Developer Console)
    "term_bg":          ("#0F172A", "#080C14"),
    "term_header":      ("#1E293B", "#0F172A"),
    "term_text":        ("#E2E8F0", "#E2E8F0"),
    "term_success":     ("#34D399", "#34D399"),
    "term_warning":     ("#FBBF24", "#FBBF24"),
    "term_error":       ("#F87171", "#F87171"),
    "term_accent":      ("#38BDF8", "#38BDF8"),
    "term_purple":      ("#C084FC", "#C084FC"),
    "term_timestamp":   ("#64748B", "#8B9BB4"),
}


def resolve_color(color):
    """Resolve a (light, dark) color tuple to a string for native Tkinter widgets."""
    if isinstance(color, (tuple, list)):
        mode = ctk.get_appearance_mode().lower()
        return color[1] if mode == "dark" else color[0]
    return color



class DistributedRenderGUI(ctk.CTk):
    """Main application window for the Distributed Task Offloading Client."""

    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("⚡ GPU Task Offloader Pro — Distributed Rendering System")
        self.geometry("1180x900")
        self.minsize(1000, 760)
        self.configure(fg_color=COLORS["bg_app"])

        # Logger
        self.logger = setup_logger("ClientGUI")

        # Network handler
        self.network = NetworkHandler(logger=self.logger)
        self.network.on_state_change = self._on_connection_state_change
        self.network.on_progress = self._on_job_progress
        self.network.on_job_complete = self._on_job_complete
        self.network.on_job_failed = self._on_job_failed
        self.network.on_log = self._on_log_message
        self.network.on_file_download_ready = self._on_download_ready
        self.network.on_gpu_stats = self._on_gpu_stats

        # State & Animation Variables
        self.selected_file = None
        self.current_job_id = None
        self.job_start_time = None
        self.benchmark_results = []
        self.batch_queue = []
        self.current_lower_tab = "console"
        self.history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_history.json")
        self.job_history = self._load_job_history()
        
        self.canvas_phase = 0.0
        self.animation_running = True

        # Build UI
        self._build_ui()

        # Start background canvas wave animation loop
        self._start_canvas_animation()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        """Construct the complete user interface."""
        # Main container
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=22, pady=18)

        # ── Header Navbar ─────────────────────────────────────────
        self._build_header()

        # ── Content Area (2-column layout) ────────────────────────
        self.content_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, pady=(14, 0))
        self.content_frame.grid_columnconfigure(0, weight=5)
        self.content_frame.grid_columnconfigure(1, weight=7)
        self.content_frame.grid_rowconfigure(0, weight=1)

        # Left column: Controls & Config Cards
        self._build_left_panel()

        # Right column: Progress & Live Terminal
        self._build_right_panel()

    # ═══════════════════════════════════════════════════════════════
    # HEADER (Modern Studio Navbar with Harmonic Canvas)
    # ═══════════════════════════════════════════════════════════════
    def _build_header(self):
        """Build the top luxury header navbar with live animated canvas."""
        header = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS["card_bg"],
            border_color=COLORS["card_border"],
            border_width=1,
            corner_radius=18,
            height=78
        )
        header.pack(fill="x", pady=(0, 4))
        header.pack_propagate(False)

        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="both", expand=True, padx=18, pady=8)

        # Left: Title + Subtitle
        title_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        title_frame.pack(side="left", fill="y")

        title_box = ctk.CTkFrame(title_frame, fg_color="transparent")
        title_box.pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text="⚡ GPU TASK OFFLOADER",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=COLORS["text_title"]
        ).pack(side="left")

        pro_badge = ctk.CTkFrame(
            title_box,
            fg_color=COLORS["indigo_subtle"],
            border_color=COLORS["indigo_border"],
            border_width=1,
            corner_radius=8
        )
        pro_badge.pack(side="left", padx=(10, 0))

        ctk.CTkLabel(
            pro_badge,
            text="PRO GPU CLUSTER",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["indigo_primary"]
        ).pack(padx=8, pady=2)

        ctk.CTkLabel(
            title_frame,
            text="CSC-334: High-Performance Distributed Task Offloading & Remote GPU Transcoding",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(2, 0))

        # Center: Live Animated Heartbeat Canvas
        self.canvas_frame = ctk.CTkFrame(header_inner, fg_color="transparent", width=240)
        self.canvas_frame.pack(side="left", fill="y", padx=16)
        self.canvas_frame.pack_propagate(False)

        self.wave_canvas = tk.Canvas(
            self.canvas_frame,
            bg=resolve_color(COLORS["card_bg"]),
            highlightthickness=0,
            bd=0
        )
        self.wave_canvas.pack(fill="both", expand=True)

        # Right: Status & Latency Badges
        status_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        status_frame.pack(side="right")

        # Connection status pill
        self.status_pill = ctk.CTkFrame(
            status_frame,
            fg_color=COLORS["rose_subtle"],
            border_color=COLORS["rose_border"],
            border_width=1,
            corner_radius=20,
            height=34
        )
        self.status_pill.pack(side="left", padx=(0, 8))

        self.status_dot = ctk.CTkLabel(
            self.status_pill, text="●",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["rose_primary"]
        )
        self.status_dot.pack(side="left", padx=(10, 4), pady=4)

        self.status_label = ctk.CTkLabel(
            self.status_pill, text="Disconnected",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["rose_primary"]
        )
        self.status_label.pack(side="left", padx=(0, 12), pady=4)

        # Latency pill
        self.latency_pill = ctk.CTkFrame(
            status_frame,
            fg_color=COLORS["card_bg_subtle"],
            border_color=COLORS["card_border"],
            border_width=1,
            corner_radius=20,
            height=34
        )
        self.latency_pill.pack(side="left")

        self.latency_label = ctk.CTkLabel(
            self.latency_pill, text="📡  Ping: --",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_secondary"]
        )
        self.latency_label.pack(padx=12, pady=4)

        # Theme toggle button
        self.theme_btn = ctk.CTkButton(
            status_frame,
            text="🌙 Dark",
            width=80,
            height=34,
            corner_radius=20,
            fg_color=COLORS["card_bg_subtle"],
            text_color=COLORS["text_primary"],
            hover_color=COLORS["indigo_subtle"],
            border_color=COLORS["card_border"],
            border_width=1,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._toggle_theme,
        )
        self.theme_btn.pack(side="left", padx=(8, 0))

    def _toggle_theme(self):
        """Toggle between Light and Dark mode seamlessly."""
        curr = ctk.get_appearance_mode()
        if curr.lower() == "light":
            ctk.set_appearance_mode("dark")
            self.theme_btn.configure(text="☀️ Light")
        else:
            ctk.set_appearance_mode("light")
            self.theme_btn.configure(text="🌙 Dark")

        self.configure(fg_color=COLORS["bg_app"])
        if hasattr(self, "wave_canvas"):
            self.wave_canvas.configure(bg=resolve_color(COLORS["card_bg"]))
        self._update_terminal_tags()
        self._switch_lower_tab(self.current_lower_tab)

    # ═══════════════════════════════════════════════════════════════
    # ANIMATION LOOP (Harmonic Wave Canvas)
    # ═══════════════════════════════════════════════════════════════
    def _start_canvas_animation(self):
        """Render continuous animated sine wave with harmonic curves."""
        if not self.animation_running:
            return

        try:
            w = self.wave_canvas.winfo_width()
            h = self.wave_canvas.winfo_height()

            if w > 10 and h > 10:
                self.wave_canvas.delete("all")
                self.canvas_phase += 0.12
                cy = h / 2

                # Wave color depends on connection state and active theme
                is_conn = (self.network.state == ConnectionState.CONNECTED)
                wave1_color = resolve_color(COLORS["emerald_primary"] if is_conn else COLORS["indigo_primary"])
                wave2_color = resolve_color(COLORS["cyan_primary"] if is_conn else COLORS["purple_primary"])

                # Wave 1: Primary sinusoidal wave
                pts1 = []
                for x in range(0, w, 4):
                    y = cy + math.sin(x * 0.045 + self.canvas_phase) * 9
                    pts1.append((x, y))

                for i in range(len(pts1) - 1):
                    self.wave_canvas.create_line(
                        pts1[i][0], pts1[i][1], pts1[i+1][0], pts1[i+1][1],
                        fill=wave1_color, width=2
                    )

                # Wave 2: Secondary harmonic wave
                pts2 = []
                for x in range(0, w, 4):
                    y = cy + math.cos(x * 0.035 - self.canvas_phase * 0.8) * 6
                    pts2.append((x, y))

                for i in range(len(pts2) - 1):
                    self.wave_canvas.create_line(
                        pts2[i][0], pts2[i][1], pts2[i+1][0], pts2[i+1][1],
                        fill=wave2_color, width=1.5
                    )

                # Floating glowing node particle
                px = (int(self.canvas_phase * 16) % w)
                py = cy + math.sin(px * 0.045 + self.canvas_phase) * 9
                self.wave_canvas.create_oval(
                    px - 4, py - 4, px + 4, py + 4,
                    fill=wave1_color, outline=resolve_color(COLORS["card_bg"]), width=1.5
                )
        except Exception:
            pass

        self.after(30, self._start_canvas_animation)

    # ═══════════════════════════════════════════════════════════════
    # LEFT PANEL — Colorful Control Cards
    # ═══════════════════════════════════════════════════════════════
    def _build_left_panel(self):
        """Build left panel containing control cards."""
        left_panel = ctk.CTkScrollableFrame(
            self.content_frame,
            fg_color="transparent",
            scrollbar_button_color=COLORS["card_border"],
            scrollbar_button_hover_color=COLORS["card_border_glow"],
        )
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        # ── Card 1: Worker Node Connection (Indigo Accent) ────────
        conn_card = ctk.CTkFrame(
            left_panel,
            fg_color=COLORS["card_bg"],
            border_color=COLORS["card_border"],
            border_width=1,
            corner_radius=16
        )
        conn_card.pack(fill="x", pady=(0, 14))

        self._build_card_header(
            conn_card, "🌐  WORKER NODE CONNECTION",
            "Target worker node IP & port specification",
            tag="NETWORK",
            tag_bg=COLORS["indigo_subtle"],
            tag_color=COLORS["indigo_primary"]
        )

        input_row = ctk.CTkFrame(conn_card, fg_color="transparent")
        input_row.pack(fill="x", padx=16, pady=(0, 12))

        # IP Address
        ip_col = ctk.CTkFrame(input_row, fg_color="transparent")
        ip_col.pack(side="left", expand=True, fill="x", padx=(0, 6))

        ctk.CTkLabel(
            ip_col, text="Server IP Address",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(0, 4))

        self.ip_entry = ctk.CTkEntry(
            ip_col,
            placeholder_text="127.0.0.1",
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["card_bg_subtle"],
            border_color=COLORS["card_border"],
            text_color=COLORS["text_title"],
            height=38,
            corner_radius=8
        )
        self.ip_entry.pack(fill="x")
        self.ip_entry.insert(0, "127.0.0.1")

        # Port
        port_col = ctk.CTkFrame(input_row, fg_color="transparent")
        port_col.pack(side="left", padx=(6, 0))

        ctk.CTkLabel(
            port_col, text="Port",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(0, 4))

        self.port_entry = ctk.CTkEntry(
            port_col,
            placeholder_text=str(DEFAULT_SERVER_PORT),
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["card_bg_subtle"],
            border_color=COLORS["card_border"],
            text_color=COLORS["text_title"],
            height=38,
            width=90,
            corner_radius=8
        )
        self.port_entry.pack()
        self.port_entry.insert(0, str(DEFAULT_SERVER_PORT))

        # Connection Buttons
        btn_row = ctk.CTkFrame(conn_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 16))

        self.connect_btn = ctk.CTkButton(
            btn_row, text="🔗  Connect Worker Node",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["btn_primary"],
            hover_color=COLORS["btn_primary_hover"],
            text_color="#FFFFFF",
            height=40,
            corner_radius=10,
            command=self._on_connect
        )
        self.connect_btn.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self.ping_btn = ctk.CTkButton(
            btn_row, text="⚡ Ping",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["indigo_subtle"],
            hover_color=COLORS["card_border"],
            text_color=COLORS["indigo_primary"],
            border_color=COLORS["indigo_border"],
            border_width=1,
            height=40,
            width=80,
            corner_radius=10,
            command=self._on_ping
        )
        self.ping_btn.pack(side="left", padx=(0, 6))

        self.speed_test_btn = ctk.CTkButton(
            btn_row, text="🚀 Speed Test",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["purple_subtle"],
            hover_color=COLORS["purple_border"],
            text_color=COLORS["purple_primary"],
            border_color=COLORS["purple_border"],
            border_width=1,
            height=40,
            width=100,
            corner_radius=10,
            state="disabled",
            command=self._on_speed_test
        )
        self.speed_test_btn.pack(side="left")

        # ── Card 2: Input Media Asset (Sky Blue Accent) ───────────
        file_card = ctk.CTkFrame(
            left_panel,
            fg_color=COLORS["card_bg"],
            border_color=COLORS["card_border"],
            border_width=1,
            corner_radius=16
        )
        file_card.pack(fill="x", pady=(0, 14))

        self._build_card_header(
            file_card, "📁  INPUT MEDIA ASSET",
            "Select high-res video file for remote GPU offloading",
            tag="ASSET",
            tag_bg=COLORS["cyan_subtle"],
            tag_color=COLORS["cyan_primary"]
        )

        # Dropzone Box
        self.file_zone = ctk.CTkFrame(
            file_card,
            fg_color=COLORS["cyan_subtle"],
            border_color=COLORS["cyan_border"],
            border_width=1.5,
            corner_radius=12
        )
        self.file_zone.pack(fill="x", padx=16, pady=(0, 12))

        self.file_label = ctk.CTkLabel(
            self.file_zone,
            text="📂  Drag & drop or browse video asset",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["cyan_primary"],
            wraplength=280
        )
        self.file_label.pack(padx=14, pady=(12, 2), anchor="w")

        self.file_info_label = ctk.CTkLabel(
            self.file_zone,
            text="Supports MP4, MKV, AVI, MOV, WEBM (Transcoding Engine Ready)",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_secondary"],
            justify="left",
            wraplength=280
        )
        self.file_info_label.pack(padx=14, pady=(0, 6), anchor="w")

        self.thumbnail_preview = ctk.CTkLabel(self.file_zone, text="")
        self.thumbnail_preview.pack(padx=14, pady=(0, 8))

        self.browse_btn = ctk.CTkButton(
            file_card, text="📁  Select Source Video",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["btn_cyan"],
            hover_color=COLORS["btn_cyan_hover"],
            text_color="#FFFFFF",
            height=38,
            corner_radius=10,
            command=self._on_browse
        )
        self.browse_btn.pack(fill="x", padx=16, pady=(0, 16))

        # ── Card 3: Render Hardware Config (Amber Accent) ─────────
        settings_card = ctk.CTkFrame(
            left_panel,
            fg_color=COLORS["card_bg"],
            border_color=COLORS["card_border"],
            border_width=1,
            corner_radius=16
        )
        settings_card.pack(fill="x", pady=(0, 14))

        self._build_card_header(
            settings_card, "⚙️  HARDWARE RENDER CONFIG",
            "Configure resolution, bitrate target & encoder preset",
            tag="PIPELINE",
            tag_bg=COLORS["amber_subtle"],
            tag_color=COLORS["amber_primary"]
        )

        settings_inner = ctk.CTkFrame(settings_card, fg_color="transparent")
        settings_inner.pack(fill="x", padx=16, pady=(0, 12))

        self._build_setting_dropdown(
            settings_inner, "Target Resolution", list(RESOLUTIONS.keys()),
            "resolution_var", default="1080p"
        )

        self._build_setting_dropdown(
            settings_inner, "Video Bitrate Target", list(BITRATES.keys()),
            "bitrate_var", default="Medium (5 Mbps)"
        )

        preset_labels = [
            f"{k.capitalize()} — {v['description']}"
            for k, v in RENDER_PRESETS.items()
        ]
        self._build_setting_dropdown(
            settings_inner, "NVENC / Hardware Preset", preset_labels,
            "preset_var", default="Medium — Balanced speed and quality"
        )

        self._build_setting_dropdown(
            settings_inner, "Output Video Container", ["mp4", "mkv", "avi", "webm"],
            "format_var", default="mp4"
        )

        # ── Primary Launch CTA Button ─────────────────────────────
        self.submit_btn = ctk.CTkButton(
            left_panel,
            text="🚀   LAUNCH REMOTE GPU RENDER",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=COLORS["btn_primary"],
            hover_color=COLORS["btn_primary_hover"],
            text_color="#FFFFFF",
            height=52,
            corner_radius=14,
            command=self._on_submit
        )
        self.submit_btn.pack(fill="x", pady=(4, 10))

        # ── Benchmark CTA Button ──────────────────────────────────
        self.benchmark_btn = ctk.CTkButton(
            left_panel,
            text="📊   Run Local CPU Benchmark",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["rose_subtle"],
            hover_color=COLORS["rose_hover"],
            text_color=COLORS["rose_primary"],
            border_color=COLORS["rose_border"],
            border_width=1,
            height=42,
            corner_radius=10,
            command=self._on_benchmark
        )
        self.benchmark_btn.pack(fill="x", pady=(0, 16))

    # ═══════════════════════════════════════════════════════════════
    # RIGHT PANEL — Progress & Obsidian Dark Terminal
    # ═══════════════════════════════════════════════════════════════
    def _build_right_panel(self):
        """Build right panel with progress bar and terminal."""
        right_panel = ctk.CTkFrame(
            self.content_frame,
            fg_color="transparent"
        )
        right_panel.grid(row=0, column=1, sticky="nsew")

        # ── Progress Card (Emerald Accent) ────────────────────────
        progress_card = ctk.CTkFrame(
            right_panel,
            fg_color=COLORS["card_bg"],
            border_color=COLORS["card_border"],
            border_width=1,
            corner_radius=16
        )
        progress_card.pack(fill="x", pady=(0, 14))

        prog_header = ctk.CTkFrame(progress_card, fg_color="transparent")
        prog_header.pack(fill="x", padx=20, pady=(16, 4))

        # Left tag + Title
        prog_left = ctk.CTkFrame(prog_header, fg_color="transparent")
        prog_left.pack(side="left")

        tag = ctk.CTkFrame(prog_left, fg_color=COLORS["emerald_subtle"], corner_radius=6)
        tag.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            tag, text="LIVE TELEMETRY",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=COLORS["emerald_primary"]
        ).pack(padx=6, pady=2)

        ctk.CTkLabel(
            prog_left, text="GPU Job Stream & Progress",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=COLORS["text_title"]
        ).pack(side="left")

        self.progress_pct_label = ctk.CTkLabel(
            prog_header, text="0.0%",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLORS["emerald_primary"]
        )
        self.progress_pct_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            progress_card,
            fg_color=COLORS["progress_bg"],
            progress_color=COLORS["progress_fill"],
            height=16,
            corner_radius=8,
        )
        self.progress_bar.pack(fill="x", padx=20, pady=(6, 4))
        self.progress_bar.set(0)

        self.progress_msg_label = ctk.CTkLabel(
            progress_card, text="Waiting for job submission...",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            anchor="w"
        )
        self.progress_msg_label.pack(fill="x", padx=20, pady=(2, 14))

        # 3 Colorful Stat Cards Grid
        stats_frame = ctk.CTkFrame(progress_card, fg_color="transparent")
        stats_frame.pack(fill="x", padx=16, pady=(0, 16))
        stats_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.stat_elapsed = self._build_stat_card(
            stats_frame, "⏱️  ELAPSED", "--:--", 0,
            bg_color=COLORS["indigo_subtle"],
            border_color=COLORS["indigo_border"],
            text_color=COLORS["indigo_primary"]
        )
        self.stat_speed = self._build_stat_card(
            stats_frame, "⚡  SPEED", "--", 1,
            bg_color=COLORS["amber_subtle"],
            border_color=COLORS["amber_border"],
            text_color=COLORS["amber_primary"]
        )
        self.stat_eta = self._build_stat_card(
            stats_frame, "🟢  STATUS", "Idle", 2,
            bg_color=COLORS["emerald_subtle"],
            border_color=COLORS["emerald_border"],
            text_color=COLORS["emerald_primary"]
        )

        # ── Hardware Telemetry Widget (GPU VRAM / Temp / Load) ───
        self.telemetry_frame = ctk.CTkFrame(
            progress_card,
            fg_color=COLORS["card_bg_subtle"],
            border_color=COLORS["card_border"],
            border_width=1,
            corner_radius=12
        )
        self.telemetry_frame.pack(fill="x", padx=16, pady=(0, 16))

        telem_header = ctk.CTkFrame(self.telemetry_frame, fg_color="transparent")
        telem_header.pack(fill="x", padx=12, pady=(10, 4))

        self.gpu_device_label = ctk.CTkLabel(
            telem_header,
            text="🎮  GPU / Host Telemetry: Standby",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        self.gpu_device_label.pack(side="left")

        self.gpu_temp_badge = ctk.CTkLabel(
            telem_header,
            text="🌡️ -- °C",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["amber_primary"]
        )
        self.gpu_temp_badge.pack(side="right")

        self.gpu_util_badge = ctk.CTkLabel(
            telem_header,
            text="⚡ Util: --%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["indigo_primary"]
        )
        self.gpu_util_badge.pack(side="right", padx=(0, 10))

        # VRAM / Memory bar and label
        vram_row = ctk.CTkFrame(self.telemetry_frame, fg_color="transparent")
        vram_row.pack(fill="x", padx=12, pady=(2, 10))

        self.vram_label = ctk.CTkLabel(
            vram_row,
            text="Memory / VRAM: -- MB / -- MB",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_secondary"]
        )
        self.vram_label.pack(side="left", padx=(0, 8))

        self.vram_bar = ctk.CTkProgressBar(
            vram_row,
            fg_color=COLORS["progress_bg"],
            progress_color=COLORS["indigo_primary"],
            height=8,
            corner_radius=4
        )
        self.vram_bar.pack(side="right", expand=True, fill="x")
        self.vram_bar.set(0)

        # ── Lower Container: Switchable Console & Job History ─────
        self.lower_container = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.lower_container.pack(fill="both", expand=True)

        tab_bar = ctk.CTkFrame(self.lower_container, fg_color="transparent")
        tab_bar.pack(fill="x", pady=(0, 6))

        self.tab_console_btn = ctk.CTkButton(
            tab_bar, text="💻  Live Console",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["indigo_primary"],
            hover_color=COLORS["indigo_hover"],
            text_color="#FFFFFF",
            width=120, height=32, corner_radius=8,
            command=lambda: self._switch_lower_tab("console")
        )
        self.tab_console_btn.pack(side="left", padx=(0, 8))

        self.tab_history_btn = ctk.CTkButton(
            tab_bar, text=f"📜  Job History ({len(self.job_history)})",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["card_bg_subtle"],
            hover_color=COLORS["card_border"],
            text_color=COLORS["text_secondary"],
            width=140, height=32, corner_radius=8,
            command=lambda: self._switch_lower_tab("history")
        )
        self.tab_history_btn.pack(side="left")

        # ── Developer Terminal Card (Obsidian Console) ────────────
        self.term_card = ctk.CTkFrame(
            self.lower_container,
            fg_color=COLORS["term_bg"],
            border_color=COLORS["card_border"],
            border_width=1,
            corner_radius=16
        )
        self.term_card.pack(fill="both", expand=True)

        term_bar = ctk.CTkFrame(self.term_card, fg_color=COLORS["term_header"], corner_radius=16, height=38)
        term_bar.pack(fill="x")
        term_bar.pack_propagate(False)

        dots_frame = ctk.CTkFrame(term_bar, fg_color="transparent")
        dots_frame.pack(side="left", padx=14)

        for color in ["#FF5F56", "#FFBD2E", "#27C93F"]:
            ctk.CTkLabel(
                dots_frame, text="●",
                font=ctk.CTkFont(size=11),
                text_color=color
            ).pack(side="left", padx=2)

        ctk.CTkLabel(
            term_bar, text="socket@gpu-cluster-worker ~ telemetry output",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=COLORS["term_timestamp"]
        ).pack(side="left", padx=10)

        self.clear_btn = ctk.CTkButton(
            term_bar, text="Clear",
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            hover_color=COLORS["term_bg"],
            text_color=COLORS["term_text"],
            width=50, height=24,
            corner_radius=4,
            command=self._clear_terminal
        )
        self.clear_btn.pack(side="right", padx=10)

        self.terminal = ctk.CTkTextbox(
            self.term_card,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=COLORS["term_bg"],
            text_color=COLORS["term_text"],
            border_width=0,
            wrap="word",
            state="disabled"
        )
        self.terminal.pack(fill="both", expand=True, padx=12, pady=12)

        self._update_terminal_tags()

        self._log_to_terminal("═" * 58, "header")
        self._log_to_terminal("  ⚡ GPU TASK OFFLOADER PRO — PARALLEL COMPUTING CLIENT", "header")
        self._log_to_terminal("  CSC-334: Distributed Task Offloading System", "header")
        self._log_to_terminal("═" * 58, "header")
        self._log_to_terminal("")
        self._log_to_terminal("Configure worker node IP and connect to begin.", "info")
        self._log_to_terminal("")

        # ── Job History View Card (Toggled via tab) ───────────────
        self.history_card = ctk.CTkFrame(
            self.lower_container,
            fg_color=COLORS["card_bg"],
            border_color=COLORS["card_border"],
            border_width=1,
            corner_radius=16
        )

        hist_header = ctk.CTkFrame(self.history_card, fg_color="transparent")
        hist_header.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(
            hist_header,
            text="📜  Offload Execution History",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_title"]
        ).pack(side="left")

        self.clear_hist_btn = ctk.CTkButton(
            hist_header, text="Clear All",
            font=ctk.CTkFont(size=11),
            fg_color=COLORS["card_bg_subtle"],
            hover_color=COLORS["rose_subtle"],
            text_color=COLORS["rose_primary"],
            width=65, height=26, corner_radius=6,
            command=self._clear_history
        )
        self.clear_hist_btn.pack(side="right")

        self.history_scroll = ctk.CTkScrollableFrame(
            self.history_card,
            fg_color="transparent",
            scrollbar_button_color=COLORS["card_border"]
        )
        self.history_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ═══════════════════════════════════════════════════════════════
    # UI BUILD HELPERS
    # ═══════════════════════════════════════════════════════════════
    def _build_card_header(self, parent, title: str, subtitle: str,
                           tag: str = None, tag_bg: str = None, tag_color: str = None):
        """Build card header label with optional pill tag."""
        header_frame = ctk.CTkFrame(parent, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(14, 10))

        title_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_row.pack(anchor="w")

        if tag:
            pill = ctk.CTkFrame(title_row, fg_color=tag_bg or COLORS["indigo_subtle"], corner_radius=6)
            pill.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                pill, text=tag,
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=tag_color or COLORS["indigo_primary"]
            ).pack(padx=6, pady=1)

        ctk.CTkLabel(
            title_row, text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_title"]
        ).pack(side="left")

        ctk.CTkLabel(
            header_frame, text=subtitle,
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(2, 0))

    def _build_setting_dropdown(self, parent, label: str, options: list,
                                 var_name: str, default: str = None):
        """Build dropdown setting with modern styling."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=(4, 6))

        ctk.CTkLabel(
            frame, text=label,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(0, 2))

        var = ctk.StringVar(value=default or options[0])
        setattr(self, var_name, var)

        dropdown = ctk.CTkOptionMenu(
            frame, variable=var, values=options,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["card_bg_subtle"],
            button_color=COLORS["card_border"],
            button_hover_color=COLORS["card_border_glow"],
            dropdown_fg_color=COLORS["card_bg"],
            dropdown_hover_color=COLORS["card_bg_subtle"],
            text_color=COLORS["text_title"],
            dropdown_text_color=COLORS["text_title"],
            height=36,
            corner_radius=8,
        )
        dropdown.pack(fill="x")

    def _build_stat_card(self, parent, title: str, value: str, col: int,
                         bg_color: str, border_color: str, text_color: str):
        """Build mini stat card with vibrant color theme."""
        card = ctk.CTkFrame(
            parent,
            fg_color=bg_color,
            border_color=border_color,
            border_width=1,
            corner_radius=12,
            height=66
        )
        card.grid(row=0, column=col, sticky="nsew", padx=4, pady=2)

        ctk.CTkLabel(
            card, text=title,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(pady=(8, 0))

        value_label = ctk.CTkLabel(
            card, text=value,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=text_color
        )
        value_label.pack(pady=(2, 8))

        return value_label

    # ═══════════════════════════════════════════════════════════════
    # EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════════
    def _on_connect(self):
        """Handle connect/disconnect."""
        if self.network.state == ConnectionState.CONNECTED:
            self.network.disconnect()
            self.connect_btn.configure(
                text="🔗  Connect Worker Node",
                fg_color=COLORS["btn_primary"],
                hover_color=COLORS["btn_primary_hover"]
            )
            return

        host = self.ip_entry.get().strip()
        port_str = self.port_entry.get().strip()

        if not host:
            messagebox.showwarning("Input Required", "Please enter the server IP address.")
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showwarning("Invalid Port", "Port must be a valid number.")
            return

        self.connect_btn.configure(
            text="⏳ Connecting...", state="disabled",
            fg_color=COLORS["amber_primary"]
        )
        self._log_to_terminal(f"Connecting to {host}:{port}...", "accent")

        def connect_thread():
            success = self.network.connect(host, port)
            self.after(0, lambda: self._on_connect_result(success))

        threading.Thread(target=connect_thread, daemon=True).start()

    def _on_connect_result(self, success: bool):
        """Handle connection result."""
        if success:
            self.connect_btn.configure(
                text="🔌  Disconnect Worker",
                fg_color=COLORS["rose_primary"],
                hover_color=COLORS["rose_hover"],
                state="normal"
            )
            self.speed_test_btn.configure(state="normal")
            self._on_ping()
            # Fetch server hardware stats immediately
            threading.Thread(target=self.network.get_gpu_stats, daemon=True).start()
        else:
            self.connect_btn.configure(
                text="🔗  Connect Worker Node",
                fg_color=COLORS["btn_primary"],
                hover_color=COLORS["btn_primary_hover"],
                state="normal"
            )
            self.speed_test_btn.configure(state="disabled")

    def _on_speed_test(self):
        """Run active link speed test with connected worker node."""
        if self.network.state != ConnectionState.CONNECTED:
            messagebox.showwarning("Not Connected", "Please connect to the worker node first.")
            return

        self.speed_test_btn.configure(state="disabled", text="Testing...")
        self._log_to_terminal("═" * 50, "accent")
        self._log_to_terminal("  🚀 RUNNING ACTIVE NETWORK SPEED TEST", "accent")
        self._log_to_terminal("═" * 50, "accent")

        def run_test():
            res = self.network.run_speed_test(test_size_kb=512)
            def update_ui():
                self.speed_test_btn.configure(state="normal", text="🚀 Speed Test")
                if "error" not in res:
                    mbs = res.get("speed_mbs", 0)
                    mbps = res.get("throughput_mbps", 0)
                    lat = res.get("latency_ms", 0)
                    self.stat_speed.configure(text=f"{mbs:.1f} MB/s")
                    self.latency_label.configure(text=f"📡 {lat:.0f}ms | 🚀 {mbps:.0f}M")
                    messagebox.showinfo(
                        "Speed Test Complete",
                        f"Network Link Performance:\n\n"
                        f"• Throughput: {mbps:.2f} Mbps ({mbs:.2f} MB/s)\n"
                        f"• Round-trip Latency: {lat:.1f} ms\n"
                        f"• Payload Transferred: {format_bytes(res.get('bytes_sent', 0) + res.get('bytes_recv', 0))}\n"
                        f"• Test Duration: {res.get('elapsed_s', 0):.2f}s"
                    )
            self.after(0, update_ui)

        threading.Thread(target=run_test, daemon=True).start()

    def _on_gpu_stats(self, stats: dict):
        """Update live hardware telemetry metrics from server."""
        if not stats or not stats.get("available"):
            return

        def update():
            name = stats.get("name", "GPU Node")
            gpu_util = stats.get("gpu_util", 0)
            mem_util = stats.get("mem_util", 0)
            temp = stats.get("temperature", 0)
            used = stats.get("vram_used", 0)
            total = stats.get("vram_total", 0)

            device_prefix = "💻 " if stats.get("is_fallback") else "🎮 "
            self.gpu_device_label.configure(text=f"{device_prefix} {name}")
            self.gpu_temp_badge.configure(text=f"🌡️ {temp}°C")
            self.gpu_util_badge.configure(text=f"⚡ Load: {gpu_util}%")

            if total > 0:
                ratio = min(used / total, 1.0)
                self.vram_bar.set(ratio)
                self.vram_label.configure(
                    text=f"Memory/VRAM: {used} MB / {total} MB ({int(ratio*100)}%)"
                )

        self.after(0, update)

    def _on_ping(self):
        """Measure latency to server."""
        def ping_thread():
            latency = self.network.ping()
            self.after(0, lambda: self._update_latency(latency))

        threading.Thread(target=ping_thread, daemon=True).start()

    def _update_latency(self, latency_ms: float):
        """Update latency pill."""
        if latency_ms > 0:
            color = COLORS["emerald_primary"]
            if latency_ms > 50:
                color = COLORS["amber_primary"]
            if latency_ms > 200:
                color = COLORS["rose_primary"]
            self.latency_label.configure(
                text=f"📡  Ping: {latency_ms:.1f} ms",
                text_color=color
            )
        else:
            self.latency_label.configure(text="📡  Ping: --", text_color=COLORS["text_secondary"])

    def _on_browse(self):
        """Open file picker with multi-file queue and thumbnail generation."""
        filetypes = [
            ("Video files", "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v *.mpeg *.ts"),
            ("All files", "*.*")
        ]
        filepaths = filedialog.askopenfilenames(
            title="Select Input File(s) — Multi-select supported for batch queue",
            filetypes=filetypes
        )

        if filepaths:
            self.batch_queue = list(filepaths)
            filepath = self.batch_queue[0]
            self.selected_file = filepath
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)

            batch_text = f" (Batch: {len(self.batch_queue)} videos queued)" if len(self.batch_queue) > 1 else ""
            self.file_label.configure(
                text=f"📄  {filename}{batch_text}",
                text_color=COLORS["cyan_primary"]
            )

            info = get_video_info(filepath)
            if info:
                info_text = (
                    f"Size: {format_bytes(filesize)} | "
                    f"Duration: {format_duration(info.get('duration', 0))}\n"
                    f"Resolution: {info.get('width', '?')}x{info.get('height', '?')} | "
                    f"Codec: {info.get('codec', '?')} | "
                    f"FPS: {info.get('fps', '?')}"
                )
            else:
                info_text = f"Size: {format_bytes(filesize)}"

            self.file_info_label.configure(text=info_text, text_color=COLORS["text_primary"])
            self._log_to_terminal(f"Selected Asset: {filename} ({format_bytes(filesize)}){batch_text}", "info")

            # Asynchronously generate video thumbnail preview
            def gen_thumb():
                try:
                    thumb_path = generate_video_thumbnail(filepath)
                    if thumb_path and os.path.exists(thumb_path):
                        pil_img = Image.open(thumb_path)
                        pil_img.thumbnail((260, 130))
                        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
                        def set_thumb():
                            self.thumbnail_preview.configure(image=ctk_img, text="")
                            self.thumbnail_preview.image = ctk_img
                        self.after(0, set_thumb)
                except Exception:
                    pass

            threading.Thread(target=gen_thumb, daemon=True).start()

    def _on_submit(self):
        """Submit render job."""
        if self.network.state != ConnectionState.CONNECTED:
            messagebox.showwarning("Not Connected", "Please connect to the worker node first.")
            return

        if not self.selected_file:
            messagebox.showwarning("No File", "Please select an input video file.")
            return

        if not os.path.exists(self.selected_file):
            messagebox.showwarning("File Not Found", "The selected file no longer exists.")
            return

        preset_raw = self.preset_var.get()
        preset_key = preset_raw.split(" — ")[0].lower() if " — " in preset_raw else "medium"

        config = {
            "resolution": self.resolution_var.get(),
            "bitrate": BITRATES.get(self.bitrate_var.get(), "5M"),
            "preset": preset_key,
            "output_format": self.format_var.get(),
        }

        self._log_to_terminal("", "info")
        self._log_to_terminal("═" * 58, "accent")
        self._log_to_terminal("  🚀 SUBMITTING REMOTE GPU RENDER JOB", "accent")
        self._log_to_terminal("═" * 58, "accent")
        self._log_to_terminal(f"  File: {os.path.basename(self.selected_file)}", "info")
        self._log_to_terminal(f"  Resolution: {config['resolution']}", "info")
        self._log_to_terminal(f"  Bitrate: {config['bitrate']}", "info")
        self._log_to_terminal(f"  Preset: {config['preset']}", "info")
        self._log_to_terminal(f"  Format: {config['output_format']}", "info")
        self._log_to_terminal("", "info")

        self.progress_bar.set(0)
        self.progress_pct_label.configure(text="0.0%")
        self.progress_msg_label.configure(text="Submitting job to remote worker queue...")
        self.stat_eta.configure(text="Processing")
        self.job_start_time = time.time()

        self.submit_btn.configure(state="disabled", text="⏳ Processing Remote Job...")

        def submit_thread():
            output_dir = os.path.join(
                os.path.dirname(self.selected_file), "rendered_output"
            )
            job_id = self.network.submit_job(
                self.selected_file, "transcode", config, output_dir
            )
            self.after(0, lambda: self._on_submit_result(job_id))

        threading.Thread(target=submit_thread, daemon=True).start()

    def _on_submit_result(self, job_id):
        """Handle job submission result."""
        if job_id:
            self.current_job_id = job_id
            self._log_to_terminal(f"Job successfully queued: {job_id}", "success")
        else:
            self.submit_btn.configure(state="normal", text="🚀   LAUNCH REMOTE GPU RENDER")
            self.stat_eta.configure(text="Failed")

    def _on_benchmark(self):
        """Run local CPU benchmark."""
        if not self.selected_file:
            messagebox.showwarning("No File", "Please select an input file for benchmarking.")
            return

        if not os.path.exists(self.selected_file):
            messagebox.showwarning("File Not Found", "The selected file no longer exists.")
            return

        self.benchmark_btn.configure(state="disabled", text="⏳ Benchmarking Local CPU...")
        self._log_to_terminal("", "info")
        self._log_to_terminal("═" * 58, "header")
        self._log_to_terminal("  📊 LOCAL CPU BENCHMARK INITIATED", "header")
        self._log_to_terminal("═" * 58, "header")

        def benchmark_thread():
            self._run_local_benchmark()

        threading.Thread(target=benchmark_thread, daemon=True).start()

    def _run_local_benchmark(self):
        """Execute local benchmark."""
        import subprocess
        import shutil

        input_path = self.selected_file
        filename = os.path.basename(input_path)
        output_dir = os.path.join(os.path.dirname(input_path), "benchmark_output")
        os.makedirs(output_dir, exist_ok=True)

        preset_raw = self.preset_var.get()
        preset_key = preset_raw.split(" — ")[0].lower() if " — " in preset_raw else "medium"
        resolution = RESOLUTIONS.get(self.resolution_var.get(), RESOLUTIONS["1080p"])
        bitrate = BITRATES.get(self.bitrate_var.get(), "5M")

        base_name = os.path.splitext(filename)[0]
        output_path = os.path.join(output_dir, f"{base_name}_local_benchmark.mp4")

        local_app_data = os.environ.get("LOCALAPPDATA", "")
        possible_paths = [
            shutil.which("ffmpeg"),
            r"C:\ffmpeg\bin\ffmpeg.exe",
            os.path.join(local_app_data, r"Microsoft\WinGet\Links\ffmpeg.exe"),
            os.path.join(local_app_data, r"Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-7.1-full_build\bin\ffmpeg.exe"),
        ]

        ffmpeg_bin = None
        for p in possible_paths:
            if p and os.path.exists(p):
                ffmpeg_bin = p
                break

        if not ffmpeg_bin:
            self.after(0, lambda: self._log_to_terminal(
                "FFmpeg not found locally. Cannot run local benchmark.", "error"
            ))
            self.after(0, lambda: self.benchmark_btn.configure(
                state="normal", text="📊   Run Local CPU Benchmark"
            ))
            return

        cpu_preset_map = {
            "ultrafast": "ultrafast", "fast": "fast",
            "medium": "medium", "slow": "slow", "quality": "veryslow",
        }
        cpu_preset = cpu_preset_map.get(preset_key, "medium")

        cmd = [
            ffmpeg_bin, "-y",
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", cpu_preset,
            "-b:v", bitrate,
            "-vf", f"scale={resolution['width']}:{resolution['height']}",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path
        ]

        self.after(0, lambda: self._log_to_terminal(
            f"Running local transcode with libx264 software encoder ({cpu_preset})...", "info"
        ))

        start_time = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            elapsed = time.time() - start_time

            if result.returncode == 0:
                output_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
                input_size = os.path.getsize(input_path)

                benchmark_data = {
                    "type": "local_cpu",
                    "elapsed": elapsed,
                    "input_size": input_size,
                    "output_size": output_size,
                    "preset": cpu_preset,
                    "encoder": "libx264",
                }
                self.benchmark_results.append(benchmark_data)

                def update_ui():
                    self._log_to_terminal("", "info")
                    self._log_to_terminal("  ✅ LOCAL BENCHMARK COMPLETED:", "success")
                    self._log_to_terminal(f"  Encoder: libx264 (CPU Software)", "info")
                    self._log_to_terminal(f"  Preset: {cpu_preset}", "info")
                    self._log_to_terminal(f"  Time: {format_duration(elapsed)}", "success")
                    self._log_to_terminal(f"  Input: {format_bytes(input_size)}", "info")
                    self._log_to_terminal(f"  Output: {format_bytes(output_size)}", "info")
                    self._log_to_terminal("", "info")

                    remote_results = [r for r in self.benchmark_results if r["type"] == "remote_gpu"]
                    if remote_results:
                        remote = remote_results[-1]
                        speedup = elapsed / remote["elapsed"] if remote["elapsed"] > 0 else 0
                        self._log_to_terminal("  ⚡ PERFORMANCE COMPARISON:", "header")
                        self._log_to_terminal(f"  Local CPU:  {format_duration(elapsed)}", "warning")
                        self._log_to_terminal(f"  Remote GPU: {format_duration(remote['elapsed'])}", "success")
                        self._log_to_terminal(f"  Speedup:    {speedup:.2f}x FASTER ON REMOTE GPU", "accent")
                        self._log_to_terminal("", "info")

                    self.benchmark_btn.configure(
                        state="normal", text="📊   Run Local CPU Benchmark"
                    )

                self.after(0, update_ui)
            else:
                self.after(0, lambda: self._log_to_terminal(
                    f"Benchmark failed: {result.stderr[-200:]}", "error"
                ))
                self.after(0, lambda: self.benchmark_btn.configure(
                    state="normal", text="📊   Run Local CPU Benchmark"
                ))

        except subprocess.TimeoutExpired:
            self.after(0, lambda: self._log_to_terminal(
                "Benchmark timed out (10 min limit)", "error"
            ))
            self.after(0, lambda: self.benchmark_btn.configure(
                state="normal", text="📊   Run Local CPU Benchmark"
            ))
        except Exception as e:
            self.after(0, lambda: self._log_to_terminal(
                f"Benchmark error: {e}", "error"
            ))
            self.after(0, lambda: self.benchmark_btn.configure(
                state="normal", text="📊   Run Local CPU Benchmark"
            ))

    # ═══════════════════════════════════════════════════════════════
    # NETWORK CALLBACKS
    # ═══════════════════════════════════════════════════════════════
    def _on_connection_state_change(self, state: str):
        """Handle connection state change."""
        def update():
            if state == ConnectionState.CONNECTED:
                self.status_pill.configure(fg_color=COLORS["emerald_subtle"], border_color=COLORS["emerald_border"])
                self.status_dot.configure(text_color=COLORS["emerald_primary"])
                self.status_label.configure(text="Connected", text_color=COLORS["emerald_primary"])
            elif state in (ConnectionState.CONNECTING, ConnectionState.HANDSHAKING):
                self.status_pill.configure(fg_color=COLORS["amber_subtle"], border_color=COLORS["amber_border"])
                self.status_dot.configure(text_color=COLORS["amber_primary"])
                self.status_label.configure(text="Connecting...", text_color=COLORS["amber_primary"])
            elif state == ConnectionState.ERROR:
                self.status_pill.configure(fg_color=COLORS["rose_subtle"], border_color=COLORS["rose_border"])
                self.status_dot.configure(text_color=COLORS["rose_primary"])
                self.status_label.configure(text="Error", text_color=COLORS["rose_primary"])
            else:
                self.status_pill.configure(fg_color=COLORS["rose_subtle"], border_color=COLORS["rose_border"])
                self.status_dot.configure(text_color=COLORS["rose_primary"])
                self.status_label.configure(text="Disconnected", text_color=COLORS["rose_primary"])

        self.after(0, update)

    def _on_job_progress(self, job_id: str, progress: float, message: str):
        """Handle progress update."""
        def update():
            bar_val = max(0, min(progress / 100, 1.0))
            self.progress_bar.set(bar_val)
            self.progress_pct_label.configure(text=f"{progress:.1f}%")
            self.progress_msg_label.configure(text=message)

            if self.job_start_time:
                elapsed = time.time() - self.job_start_time
                self.stat_elapsed.configure(text=format_duration(elapsed))

        self.after(0, update)

    def _on_job_complete(self, job_id: str, result_info: dict):
        """Handle job completion with audio chime and history logging."""
        def update():
            self.progress_bar.set(1.0)
            self.progress_pct_label.configure(text="100.0%")
            self.progress_msg_label.configure(text="Job completed successfully!")
            self.stat_eta.configure(text="Complete")

            elapsed = result_info.get("elapsed_seconds", 0)
            self.stat_elapsed.configure(text=format_duration(elapsed))

            if result_info.get("encoder"):
                self.stat_speed.configure(text=result_info["encoder"])

            self.benchmark_results.append({
                "type": "remote_gpu",
                "elapsed": elapsed,
                "input_size": result_info.get("input_size", 0),
                "output_size": result_info.get("output_size", 0),
                "encoder": result_info.get("encoder", "unknown"),
            })

            # Record in Job History
            job_record = {
                "job_id": job_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "filename": os.path.basename(self.selected_file) if self.selected_file else "video",
                "resolution": self.resolution_var.get(),
                "preset": self.preset_var.get().split(" — ")[0],
                "elapsed": result_info.get("elapsed_formatted", "--"),
                "output_size": result_info.get("output_size_formatted", "--"),
                "compression_ratio": result_info.get("compression_ratio", "--"),
                "output_file": result_info.get("output_file", ""),
                "status": "Complete",
            }
            self.job_history.insert(0, job_record)
            self._save_job_history()
            self._refresh_history_ui()

            # Play audio chime
            self._play_completion_sound(True)

            self.submit_btn.configure(state="normal", text="🚀   LAUNCH REMOTE GPU RENDER")

            # Check for next queued batch job
            if self.batch_queue:
                self.batch_queue.pop(0)
                if self.batch_queue:
                    next_file = self.batch_queue[0]
                    self.selected_file = next_file
                    self.file_label.configure(
                        text=f"📄  {os.path.basename(next_file)} (Batch: {len(self.batch_queue)} remaining)"
                    )
                    self._log_to_terminal(f"📋 Auto-starting next batch job: {os.path.basename(next_file)}", "accent")
                    self.after(1500, self._on_submit)

        self.after(0, update)

    def _on_job_failed(self, job_id: str, error: str):
        """Handle job failure."""
        def update():
            self.progress_msg_label.configure(text=f"Failed: {error}")
            self.stat_eta.configure(text="Failed")
            self.submit_btn.configure(state="normal", text="🚀   LAUNCH REMOTE GPU RENDER")
            self._log_to_terminal(f"JOB FAILED: {error}", "error")

            # Record failed job in history
            job_record = {
                "job_id": job_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "filename": os.path.basename(self.selected_file) if self.selected_file else "video",
                "resolution": self.resolution_var.get(),
                "preset": self.preset_var.get().split(" — ")[0],
                "elapsed": "--",
                "output_size": "--",
                "compression_ratio": "--",
                "output_file": "",
                "status": "Failed",
            }
            self.job_history.insert(0, job_record)
            self._save_job_history()
            self._refresh_history_ui()

            # Play alert chime
            self._play_completion_sound(False)

        self.after(0, update)

    def _play_completion_sound(self, success: bool = True):
        """Play completion chime on Windows."""
        try:
            if winsound:
                if success:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                else:
                    winsound.MessageBeep(winsound.MB_ICONHAND)
        except Exception:
            pass

    def _load_job_history(self) -> list:
        """Load job history from disk."""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_job_history(self):
        """Persist job history to disk."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.job_history, f, indent=2)
        except Exception:
            pass

    def _clear_history(self):
        """Clear all historical records."""
        self.job_history = []
        self._save_job_history()
        self._refresh_history_ui()

    def _switch_lower_tab(self, tab: str):
        """Switch between Live Console and Job History."""
        self.current_lower_tab = tab
        if tab == "console":
            self.history_card.pack_forget()
            self.term_card.pack(fill="both", expand=True)
            self.tab_console_btn.configure(
                fg_color=COLORS["indigo_primary"],
                text_color="#FFFFFF"
            )
            self.tab_history_btn.configure(
                fg_color=COLORS["card_bg_subtle"],
                text_color=COLORS["text_secondary"]
            )
        else:
            self.term_card.pack_forget()
            self.history_card.pack(fill="both", expand=True)
            self.tab_history_btn.configure(
                fg_color=COLORS["indigo_primary"],
                text_color="#FFFFFF"
            )
            self.tab_console_btn.configure(
                fg_color=COLORS["card_bg_subtle"],
                text_color=COLORS["text_secondary"]
            )
            self._refresh_history_ui()

    def _refresh_history_ui(self):
        """Update job history list items."""
        self.tab_history_btn.configure(text=f"📜  Job History ({len(self.job_history)})")

        for w in self.history_scroll.winfo_children():
            w.destroy()

        if not self.job_history:
            empty_lbl = ctk.CTkLabel(
                self.history_scroll,
                text="No jobs recorded yet. Launch a render job to see results here.",
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_muted"]
            )
            empty_lbl.pack(pady=40)
            return

        for job in self.job_history:
            item = ctk.CTkFrame(
                self.history_scroll,
                fg_color=COLORS["card_bg_subtle"],
                border_color=COLORS["card_border"],
                border_width=1,
                corner_radius=10
            )
            item.pack(fill="x", pady=4, padx=2)

            top_row = ctk.CTkFrame(item, fg_color="transparent")
            top_row.pack(fill="x", padx=12, pady=(8, 2))

            status = job.get("status", "Unknown")
            is_ok = status == "Complete"
            pill_color = COLORS["emerald_primary"] if is_ok else COLORS["rose_primary"]
            pill_bg = COLORS["emerald_subtle"] if is_ok else COLORS["rose_subtle"]

            st_pill = ctk.CTkFrame(top_row, fg_color=pill_bg, corner_radius=6)
            st_pill.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                st_pill, text=f"● {status}",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=pill_color
            ).pack(padx=6, pady=2)

            fname = job.get("filename", "unknown")
            ctk.CTkLabel(
                top_row, text=fname,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLORS["text_title"]
            ).pack(side="left")

            ctk.CTkLabel(
                top_row, text=job.get("timestamp", ""),
                font=ctk.CTkFont(size=10),
                text_color=COLORS["text_muted"]
            ).pack(side="right")

            # Detail row
            det_row = ctk.CTkFrame(item, fg_color="transparent")
            det_row.pack(fill="x", padx=12, pady=(2, 8))

            details = f"Config: {job.get('resolution')} @ {job.get('preset')} | Time: {job.get('elapsed')} | Ratio: {job.get('compression_ratio')}x"
            ctk.CTkLabel(
                det_row, text=details,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_secondary"]
            ).pack(side="left")

            out_file = job.get("output_file")
            if out_file and os.path.exists(out_file):
                open_btn = ctk.CTkButton(
                    det_row, text="📁 Open File",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    fg_color=COLORS["indigo_subtle"],
                    hover_color=COLORS["indigo_border"],
                    text_color=COLORS["indigo_primary"],
                    width=75, height=22, corner_radius=6,
                    command=lambda p=out_file: os.startfile(p) if hasattr(os, "startfile") else None
                )
                open_btn.pack(side="right")

    def _on_log_message(self, message: str, level: str):
        """Handle log message."""
        self.after(0, lambda: self._log_to_terminal(message, level))

    def _on_download_ready(self, job_id: str, filepath: str):
        """Handle downloaded output file."""
        def update():
            self._log_to_terminal("", "info")
            self._log_to_terminal("✅ OUTPUT RENDERED ASSET READY:", "success")
            self._log_to_terminal(f"   {filepath}", "success")
            self._log_to_terminal("", "info")

        self.after(0, update)

    # ═══════════════════════════════════════════════════════════════
    # TERMINAL
    # ═══════════════════════════════════════════════════════════════
    def _update_terminal_tags(self):
        """Configure syntax tags for the terminal based on appearance mode."""
        if not hasattr(self, "terminal"):
            return
        self.terminal._textbox.tag_configure("info", foreground=resolve_color(COLORS["term_text"]))
        self.terminal._textbox.tag_configure("success", foreground=resolve_color(COLORS["term_success"]))
        self.terminal._textbox.tag_configure("warning", foreground=resolve_color(COLORS["term_warning"]))
        self.terminal._textbox.tag_configure("error", foreground=resolve_color(COLORS["term_error"]))
        self.terminal._textbox.tag_configure("accent", foreground=resolve_color(COLORS["term_accent"]))
        self.terminal._textbox.tag_configure("header", foreground=resolve_color(COLORS["term_purple"]))
        self.terminal._textbox.tag_configure("timestamp", foreground=resolve_color(COLORS["term_timestamp"]))

    def _log_to_terminal(self, message: str, tag: str = "info"):
        """Log message to terminal textbox."""
        try:
            timestamp = time.strftime("%H:%M:%S")
            self.terminal.configure(state="normal")
            if message:
                self.terminal.insert("end", f"[{timestamp}] ", "timestamp")
                self.terminal.insert("end", f"{message}\n", tag)
            else:
                self.terminal.insert("end", "\n")
            self.terminal.see("end")
            self.terminal.configure(state="disabled")
        except Exception:
            pass

    def _clear_terminal(self):
        """Clear all terminal contents."""
        self.terminal.configure(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.configure(state="disabled")

    def _on_close(self):
        """Handle window closing."""
        self.animation_running = False
        try:
            if self.network.state == ConnectionState.CONNECTED:
                self.network.disconnect()
        except Exception:
            pass
        self.destroy()


def main():
    """Main entry point."""
    app = DistributedRenderGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
