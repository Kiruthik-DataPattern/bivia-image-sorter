#!/usr/bin/env python3
"""
Native Desktop Python GUI for System One (TypeSafe Jev) Image Sorter.
Built with Tkinter and Pillow (Zero additional pip dependencies).
"""

import os
import sys
import queue
import shutil
import threading
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

# Import sorter backend
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sorter import (
    PRESETS,
    get_config,
    prepare_image,
    classify_image,
    test_api_connection
)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = SCRIPT_DIR / "input_images"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "sorted_output"

DEFAULT_INPUT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class NativeImageSorterGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Articul8 Bivia — Native Image Sorter")
        self.geometry("1180x760")
        self.minsize(980, 640)

        # Config state
        self.api_key, self.api_url, self.model = get_config(SCRIPT_DIR)
        self.current_preset = "industrial_safety"
        self.current_categories: Dict[str, str] = dict(PRESETS["industrial_safety"]["categories"])
        desktop_raw = Path.home() / "Desktop" / "Raw_Images"
        desktop_sorted = Path.home() / "Desktop" / "Sorted_Images"
        self.input_dir = desktop_raw if desktop_raw.exists() else DEFAULT_INPUT_DIR
        self.output_dir = desktop_sorted if desktop_raw.exists() else DEFAULT_OUTPUT_DIR
        self.staged_files: List[Path] = []
        self.sorting_results: List[Dict] = []
        self.is_processing = False
        self.msg_queue = queue.Queue()

        # Thumbnail cache to prevent GC
        self.current_preview_photo: Optional[ImageTk.PhotoImage] = None

        # Setup Theme & Widgets
        self.setup_styles()
        self.create_widgets()
        self.scan_input_directory()

        # Check API status asynchronously
        self.after(200, self.async_test_connection)
        self.after(100, self.process_queue_events)

    def setup_styles(self):
        """Configure modern clean styling for ttk widgets."""
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Color palette
        self.c_bg = "#0f172a"          # Slate 900
        self.c_surface = "#1e293b"     # Slate 800
        self.c_surface_alt = "#334155" # Slate 700
        self.c_primary = "#2563eb"     # Blue 600
        self.c_primary_active = "#1d4ed8"
        self.c_text = "#f8fafc"
        self.c_text_muted = "#94a3b8"
        self.c_accent = "#10b981"      # Emerald

        self.configure(bg=self.c_bg)

        # Style TTK widgets
        self.style.configure(".", background=self.c_bg, foreground=self.c_text)
        self.style.configure("TFrame", background=self.c_bg)
        self.style.configure("Surface.TFrame", background=self.c_surface)
        self.style.configure("TLabel", background=self.c_bg, foreground=self.c_text, font=("Segoe UI", 9))
        self.style.configure("Surface.TLabel", background=self.c_surface, foreground=self.c_text, font=("Segoe UI", 9))
        self.style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground=self.c_text, background=self.c_surface)
        self.style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground=self.c_text_muted, background=self.c_surface)

        self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), background=self.c_primary, foreground="#ffffff", padding=6)
        self.style.map("Primary.TButton", background=[("active", self.c_primary_active), ("disabled", "#475569")])

        self.style.configure("Secondary.TButton", font=("Segoe UI", 9), background=self.c_surface_alt, foreground=self.c_text, padding=4)
        self.style.map("Secondary.TButton", background=[("active", "#475569")])

        self.style.configure("Treeview",
            background=self.c_surface,
            foreground=self.c_text,
            fieldbackground=self.c_surface,
            rowheight=26,
            font=("Segoe UI", 9)
        )
        self.style.configure("Treeview.Heading",
            background=self.c_surface_alt,
            foreground="#ffffff",
            font=("Segoe UI", 9, "bold")
        )
        self.style.map("Treeview", background=[("selected", self.c_primary)], foreground=[("selected", "#ffffff")])

        self.style.configure("Horizontal.TProgressbar", background=self.c_primary, troughcolor=self.c_surface)

    def create_widgets(self):
        """Construct the main GUI layout."""
        # Top Header Bar
        header_frame = ttk.Frame(self, style="Surface.TFrame", padding=(16, 12))
        header_frame.pack(fill="x", side="top", padx=14, pady=(12, 6))

        title_box = ttk.Frame(header_frame, style="Surface.TFrame")
        title_box.pack(side="left")

        ttk.Label(title_box, text="Articul8 Bivia — Image Sorter", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text=f"Decision Engine: {self.model} (bivia/decide)  |  Multimodal Context Categorization",
            style="Sub.TLabel"
        ).pack(anchor="w")

        # Header Right Controls
        header_right = ttk.Frame(header_frame, style="Surface.TFrame")
        header_right.pack(side="right")

        self.lbl_api_status = tk.Label(
            header_right,
            text="● Checking API...",
            font=("Segoe UI", 9, "bold"),
            bg="#334155",
            fg="#facc15",
            padx=10,
            pady=4,
            relief="flat",
            cursor="hand2"
        )
        self.lbl_api_status.pack(side="left", padx=6)
        self.lbl_api_status.bind("<Button-1>", lambda e: self.open_key_dialog())

        btn_settings = ttk.Button(header_right, text="🔑 API Key Settings", style="Secondary.TButton", command=self.open_key_dialog)
        btn_settings.pack(side="left", padx=4)

        btn_test = ttk.Button(header_right, text="Test Key", style="Secondary.TButton", command=self.async_test_connection)
        btn_test.pack(side="left", padx=4)

        btn_rescan = ttk.Button(header_right, text="🔄 Refresh", style="Secondary.TButton", command=self.scan_input_directory)
        btn_rescan.pack(side="left", padx=4)

        # Folder Path Ribbon
        folder_bar = ttk.Frame(self, style="Surface.TFrame", padding=(16, 8))
        folder_bar.pack(fill="x", side="top", padx=14, pady=4)

        # Input Path
        ttk.Label(folder_bar, text="Input:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.lbl_input_path = ttk.Label(folder_bar, text=str(self.input_dir), style="Surface.TLabel", foreground=self.c_text_muted)
        self.lbl_input_path.pack(side="left", padx=(0, 8))

        btn_browse_in = ttk.Button(folder_bar, text="Browse...", style="Secondary.TButton", command=self.browse_input_dir)
        btn_browse_in.pack(side="left", padx=4)

        btn_open_in = ttk.Button(folder_bar, text="Open Input Folder", style="Secondary.TButton", command=lambda: self.open_in_explorer(self.input_dir))
        btn_open_in.pack(side="left", padx=4)

        # Separator
        ttk.Separator(folder_bar, orient="vertical").pack(side="left", fill="y", padx=12)

        # Output Path
        ttk.Label(folder_bar, text="Output:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.lbl_output_path = ttk.Label(folder_bar, text=str(self.output_dir), style="Surface.TLabel", foreground=self.c_text_muted)
        self.lbl_output_path.pack(side="left", padx=(0, 8))

        btn_browse_out = ttk.Button(folder_bar, text="Browse...", style="Secondary.TButton", command=self.browse_output_dir)
        btn_browse_out.pack(side="left", padx=4)

        btn_open_out = ttk.Button(folder_bar, text="Open Output Folder", style="Secondary.TButton", command=lambda: self.open_in_explorer(self.output_dir))
        btn_open_out.pack(side="left", padx=4)

        # Main Body Splitter: Left Sidebar + Right Workspace
        main_split = ttk.PanedWindow(self, orient="horizontal")
        main_split.pack(fill="both", expand=True, padx=14, pady=8)

        # Left Panel (Controls & Taxonomy)
        left_panel = ttk.Frame(main_split, style="Surface.TFrame", padding=14)
        main_split.add(left_panel, weight=1)

        # Preset Dropdown
        ttk.Label(left_panel, text="1. CONTEXT PRESET", style="Surface.TLabel", font=("Segoe UI", 9, "bold"), foreground=self.c_text_muted).pack(anchor="w")
        
        self.preset_var = tk.StringVar(value="industrial_safety")
        self.cb_preset = ttk.Combobox(
            left_panel,
            textvariable=self.preset_var,
            values=["industrial_safety", "office", "general", "custom"],
            state="readonly",
            font=("Segoe UI", 9)
        )
        self.cb_preset.pack(fill="x", pady=(4, 10))
        self.cb_preset.bind("<<ComboboxSelected>>", self.on_preset_change)

        # Categories Listbox
        ttk.Label(left_panel, text="2. TARGET CATEGORIES", style="Surface.TLabel", font=("Segoe UI", 9, "bold"), foreground=self.c_text_muted).pack(anchor="w")
        
        cat_frame = ttk.Frame(left_panel, style="Surface.TFrame")
        cat_frame.pack(fill="both", expand=True, pady=(4, 8))

        self.lb_categories = tk.Listbox(
            cat_frame,
            bg="#0f172a",
            fg=self.c_text,
            selectbackground=self.c_primary,
            selectforeground="#ffffff",
            relief="flat",
            highlightthickness=1,
            highlightcolor=self.c_primary,
            font=("Segoe UI", 9)
        )
        self.lb_categories.pack(side="left", fill="both", expand=True)

        lb_scroll = ttk.Scrollbar(cat_frame, orient="vertical", command=self.lb_categories.yview)
        lb_scroll.pack(side="right", fill="y")
        self.lb_categories.config(yscrollcommand=lb_scroll.set)

        # Add/Remove category inputs
        add_box = ttk.Frame(left_panel, style="Surface.TFrame")
        add_box.pack(fill="x", pady=(0, 10))

        self.entry_new_cat = ttk.Entry(add_box, font=("Segoe UI", 9))
        self.entry_new_cat.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.entry_new_cat.insert(0, "custom_tag")

        btn_add = ttk.Button(add_box, text="+ Add", style="Secondary.TButton", command=self.add_custom_category)
        btn_add.pack(side="left", padx=2)

        btn_del = ttk.Button(add_box, text="- Remove", style="Secondary.TButton", command=self.remove_selected_category)
        btn_del.pack(side="left", padx=2)

        # Context Guidance Input
        ttk.Label(left_panel, text="3. CONTEXT GUIDANCE (OPTIONAL)", style="Surface.TLabel", font=("Segoe UI", 9, "bold"), foreground=self.c_text_muted).pack(anchor="w")
        self.entry_context = ttk.Entry(left_panel, font=("Segoe UI", 9))
        self.entry_context.pack(fill="x", pady=(4, 12))

        # Mode Selection
        ttk.Label(left_panel, text="4. EXECUTION MODE", style="Surface.TLabel", font=("Segoe UI", 9, "bold"), foreground=self.c_text_muted).pack(anchor="w")
        self.mode_var = tk.StringVar(value="copy")
        mode_box = ttk.Frame(left_panel, style="Surface.TFrame")
        mode_box.pack(fill="x", pady=2)

        rb_copy = tk.Radiobutton(mode_box, text="Copy files (Safe)", variable=self.mode_var, value="copy", bg=self.c_surface, fg=self.c_text, selectcolor="#0f172a", activebackground=self.c_surface, activeforeground=self.c_text)
        rb_copy.pack(side="left", padx=(0, 8))

        rb_move = tk.Radiobutton(mode_box, text="Move files", variable=self.mode_var, value="move", bg=self.c_surface, fg=self.c_text, selectcolor="#0f172a", activebackground=self.c_surface, activeforeground=self.c_text)
        rb_move.pack(side="left")

        self.dry_run_var = tk.BooleanVar(value=False)
        cb_dry = tk.Checkbutton(left_panel, text="Dry-run (simulate classification only)", variable=self.dry_run_var, bg=self.c_surface, fg=self.c_text, selectcolor="#0f172a", activebackground=self.c_surface, activeforeground=self.c_text)
        cb_dry.pack(anchor="w", pady=(4, 4))

        self.clean_output_var = tk.BooleanVar(value=True)
        cb_clean = tk.Checkbutton(left_panel, text="Clean output folder before start (strictly empty)", variable=self.clean_output_var, bg=self.c_surface, fg=self.c_text, selectcolor="#0f172a", activebackground=self.c_surface, activeforeground=self.c_text)
        cb_clean.pack(anchor="w", pady=(0, 10))

        # Main Action Button
        self.btn_sort = ttk.Button(
            left_panel,
            text="⚡ Start Sorting Images",
            style="Primary.TButton",
            command=self.start_sorting_thread
        )
        self.btn_sort.pack(fill="x", pady=(8, 4))

        # Progress bar & label
        self.lbl_progress = ttk.Label(left_panel, text="Ready", style="Surface.TLabel", foreground=self.c_text_muted)
        self.lbl_progress.pack(anchor="w", pady=(6, 2))

        self.progress_bar = ttk.Progressbar(left_panel, orient="horizontal", mode="determinate", style="Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x")

        # Right Panel (File Queue & Live Results)
        right_panel = ttk.Frame(main_split, padding=(10, 0))
        main_split.add(right_panel, weight=3)

        # Upper Queue & Preview Splitter
        upper_box = ttk.Frame(right_panel, style="Surface.TFrame", padding=10)
        upper_box.pack(fill="both", expand=True, pady=(0, 8))

        upper_split = ttk.PanedWindow(upper_box, orient="horizontal")
        upper_split.pack(fill="both", expand=True)

        # Staged Files List
        files_box = ttk.Frame(upper_split, style="Surface.TFrame")
        upper_split.add(files_box, weight=2)

        ttk.Label(files_box, text="STAGED INPUT QUEUE", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w")

        self.lb_files = tk.Listbox(
            files_box,
            bg="#0f172a",
            fg=self.c_text,
            selectbackground=self.c_primary,
            selectforeground="#ffffff",
            relief="flat",
            highlightthickness=1,
            highlightcolor=self.c_primary,
            font=("Segoe UI", 9)
        )
        self.lb_files.pack(side="left", fill="both", expand=True, pady=4)
        self.lb_files.bind("<<ListboxSelect>>", self.on_file_selected)

        files_scroll = ttk.Scrollbar(files_box, orient="vertical", command=self.lb_files.yview)
        files_scroll.pack(side="right", fill="y", pady=4)
        self.lb_files.config(yscrollcommand=files_scroll.set)

        # Preview Image Box
        preview_box = ttk.Frame(upper_split, style="Surface.TFrame", padding=(10, 0))
        upper_split.add(preview_box, weight=1)

        ttk.Label(preview_box, text="PREVIEW", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.lbl_preview_img = tk.Label(preview_box, bg="#0b0f17", text="No image selected", fg=self.c_text_muted)
        self.lbl_preview_img.pack(fill="both", expand=True, pady=4)

        self.lbl_preview_meta = ttk.Label(preview_box, text="", style="Sub.TLabel")
        self.lbl_preview_meta.pack(anchor="w")

        # Lower Results Treeview Table
        lower_box = ttk.Frame(right_panel, style="Surface.TFrame", padding=10)
        lower_box.pack(fill="both", expand=True)

        res_head = ttk.Frame(lower_box, style="Surface.TFrame")
        res_head.pack(fill="x", pady=(0, 4))

        ttk.Label(res_head, text="SYSTEM ONE SORTING RESULTS", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(side="left")

        self.lbl_result_count = ttk.Label(res_head, text="0 sorted", style="Sub.TLabel")
        self.lbl_result_count.pack(side="right")

        # Columns
        cols = ("file", "category", "confidence", "action", "destination")
        self.tree_results = ttk.Treeview(lower_box, columns=cols, show="headings", selectmode="browse")

        self.tree_results.heading("file", text="Image File")
        self.tree_results.heading("category", text="Assigned Category")
        self.tree_results.heading("confidence", text="Confidence")
        self.tree_results.heading("action", text="Action")
        self.tree_results.heading("destination", text="Destination Folder")

        self.tree_results.column("file", width=180, anchor="w")
        self.tree_results.column("category", width=160, anchor="w")
        self.tree_results.column("confidence", width=90, anchor="center")
        self.tree_results.column("action", width=80, anchor="center")
        self.tree_results.column("destination", width=260, anchor="w")

        tree_scroll_y = ttk.Scrollbar(lower_box, orient="vertical", command=self.tree_results.yview)
        tree_scroll_x = ttk.Scrollbar(lower_box, orient="horizontal", command=self.tree_results.xview)
        self.tree_results.config(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x.pack(side="bottom", fill="x")
        self.tree_results.pack(fill="both", expand=True)

        self.populate_categories_listbox()

    def populate_categories_listbox(self):
        """Update categories displayed in the listbox."""
        self.lb_categories.delete(0, tk.END)
        for cat in self.current_categories.keys():
            self.lb_categories.insert(tk.END, cat)

    def on_preset_change(self, event=None):
        """Handle preset selection changes."""
        preset = self.preset_var.get()
        self.current_preset = preset
        if preset in PRESETS:
            self.current_categories = dict(PRESETS[preset]["categories"])
            self.populate_categories_listbox()

    def add_custom_category(self):
        """Add new category to current categories."""
        val = self.entry_new_cat.get().strip().lower().replace(" ", "_")
        if val and val not in self.current_categories:
            self.current_categories[val] = f"Images depicting {val.replace('_', ' ')}"
            self.preset_var.set("custom")
            self.populate_categories_listbox()
            self.entry_new_cat.delete(0, tk.END)

    def remove_selected_category(self):
        """Remove highlighted category."""
        sel = self.lb_categories.curselection()
        if sel:
            cat = self.lb_categories.get(sel[0])
            del self.current_categories[cat]
            self.preset_var.set("custom")
            self.populate_categories_listbox()

    def browse_input_dir(self):
        """Choose custom input folder."""
        path = filedialog.askdirectory(initialdir=str(self.input_dir), title="Select Input Images Folder")
        if path:
            self.input_dir = Path(path)
            self.lbl_input_path.config(text=str(self.input_dir))
            self.scan_input_directory()

    def browse_output_dir(self):
        """Choose custom output folder."""
        path = filedialog.askdirectory(initialdir=str(self.output_dir), title="Select Output Folder")
        if path:
            self.output_dir = Path(path)
            self.lbl_output_path.config(text=str(self.output_dir))

    def open_in_explorer(self, target_path: Path):
        """Open directory in Windows Explorer."""
        try:
            target_path.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(target_path)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(target_path)])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder:\n{e}")

    def scan_input_directory(self):
        """Scan input directory and update listbox."""
        supported_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
        self.lb_files.delete(0, tk.END)
        self.staged_files = []

        if not self.input_dir.exists():
            return

        for f in sorted(self.input_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in supported_exts:
                self.staged_files.append(f)
                self.lb_files.insert(tk.END, f"{f.name} ({(f.stat().st_size/1024):.1f} KB)")

        if self.staged_files:
            self.lb_files.selection_set(0)
            self.display_image_preview(self.staged_files[0])
        else:
            self.lbl_preview_img.config(image="", text="No images in input directory")
            self.lbl_preview_meta.config(text="")

    def on_file_selected(self, event=None):
        """User clicked an image in the queue."""
        sel = self.lb_files.curselection()
        if sel and sel[0] < len(self.staged_files):
            self.display_image_preview(self.staged_files[sel[0]])

    def display_image_preview(self, file_path: Path):
        """Render scaled thumbnail preview in the preview box."""
        try:
            with Image.open(file_path) as img:
                w, h = img.size
                preview_copy = img.copy()
                preview_copy.thumbnail((260, 200))
                photo = ImageTk.PhotoImage(preview_copy)
                self.current_preview_photo = photo
                self.lbl_preview_img.config(image=photo, text="")
                self.lbl_preview_meta.config(text=f"Resolution: {w}x{h} px  |  {(file_path.stat().st_size/1024):.1f} KB")
        except Exception as e:
            self.lbl_preview_img.config(image="", text=f"Preview error:\n{e}")
            self.lbl_preview_meta.config(text="")

    def async_test_connection(self):
        """Run API connectivity test in background."""
        self.lbl_api_status.config(text="● Testing...", fg="#facc15", bg="#334155")

        def worker():
            ok, msg = test_api_connection(self.api_key, self.api_url, self.model)
            self.msg_queue.put(("test_api_result", ok, msg))

        threading.Thread(target=worker, daemon=True).start()

    def open_key_dialog(self):
        """Display dialog to update API Key, URL, or Model."""
        dlg = tk.Toplevel(self)
        dlg.title("Configure API Key & Endpoint")
        dlg.geometry("620x360")
        dlg.minsize(560, 320)
        dlg.configure(bg=self.c_bg)
        dlg.transient(self)
        dlg.grab_set()

        pad_frame = ttk.Frame(dlg, style="Surface.TFrame", padding=20)
        pad_frame.pack(fill="both", expand=True, padx=16, pady=16)

        ttk.Label(pad_frame, text="Articul8 Bivia API Configuration", style="Header.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(
            pad_frame,
            text="Endpoint: https://api.articul8.ai/bivia/decide\nModel: dec-1 | Authenticates using your Articul8 Ory API key.",
            style="Sub.TLabel",
            justify="left"
        ).pack(anchor="w", pady=(0, 14))

        # API Key
        ttk.Label(pad_frame, text="Articul8 API Key (A8_API_KEY):", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        entry_key = ttk.Entry(pad_frame, font=("Segoe UI", 9))
        entry_key.pack(fill="x", pady=(2, 10))
        entry_key.insert(0, self.api_key)

        # API URL
        ttk.Label(pad_frame, text="API Endpoint URL:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        entry_url = ttk.Entry(pad_frame, font=("Segoe UI", 9))
        entry_url.pack(fill="x", pady=(2, 10))
        entry_url.insert(0, self.api_url)

        # Model
        ttk.Label(pad_frame, text="Model Identifier:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        entry_model = ttk.Entry(pad_frame, font=("Segoe UI", 9))
        entry_model.pack(fill="x", pady=(2, 16))
        entry_model.insert(0, self.model)

        def save_and_close():
            new_key = entry_key.get().strip()
            new_url = entry_url.get().strip() or "https://api.articul8.ai/bivia/decide"
            new_model = entry_model.get().strip() or "dec-1"

            self.api_key = new_key
            self.api_url = new_url
            self.model = new_model

            # Save to .env
            env_file = SCRIPT_DIR / ".env"
            with open(env_file, "w", encoding="utf-8") as f:
                f.write("# Articul8 Bivia Model Configuration\n")
                f.write(f"A8_API_KEY={new_key}\n")
                f.write(f"A8_API_URL={new_url}\n")
                f.write(f"A8_MODEL={new_model}\n")

            dlg.destroy()
            self.async_test_connection()

        btn_box = ttk.Frame(pad_frame, style="Surface.TFrame")
        btn_box.pack(fill="x", side="bottom")

        btn_save = ttk.Button(btn_box, text="Save & Test Key", style="Primary.TButton", command=save_and_close)
        btn_save.pack(side="right", padx=(8, 0))

        btn_cancel = ttk.Button(btn_box, text="Cancel", style="Secondary.TButton", command=dlg.destroy)
        btn_cancel.pack(side="right")

    def start_sorting_thread(self):
        """Begin classification and filing on background thread."""
        if self.is_processing:
            return
        if not self.staged_files:
            messagebox.showinfo("Queue Empty", "No images found in input folder to sort.")
            return
        if not self.api_key:
            messagebox.showerror("Missing API Key", "No API key configured in .env!")
            return

        self.is_processing = True
        self.btn_sort.config(state="disabled")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(self.staged_files)
        self.lbl_progress.config(text="Starting System One decision engine...")

        files_to_process = list(self.staged_files)
        categories = dict(self.current_categories)
        context_hint = self.entry_context.get().strip()
        mode = self.mode_var.get()
        dry_run = self.dry_run_var.get()
        clean_out = self.clean_output_var.get()
        out_dir = self.output_dir

        if not dry_run and clean_out and out_dir.exists():
            for item in out_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            out_dir.mkdir(parents=True, exist_ok=True)

        def worker():
            for idx, img_path in enumerate(files_to_process, start=1):
                self.msg_queue.put(("progress", idx, len(files_to_process), img_path.name))
                try:
                    res = classify_image(
                        image_path=img_path,
                        categories=categories,
                        api_key=self.api_key,
                        api_url=self.api_url,
                        model=self.model,
                        context_note=context_hint
                    )
                    cat = res["category"]
                    conf = res["confidence"]
                    dest_folder = out_dir / cat
                    dest_file = dest_folder / img_path.name

                    if not dry_run:
                        dest_folder.mkdir(parents=True, exist_ok=True)
                        if mode == "move":
                            shutil.move(str(img_path), str(dest_file))
                            action = "MOVED"
                        else:
                            shutil.copy2(str(img_path), str(dest_file))
                            action = "COPIED"
                    else:
                        action = "DRY-RUN"

                    self.msg_queue.put(("item_done", {
                        "file": img_path.name,
                        "category": cat,
                        "confidence": f"{conf*100:.1f}%",
                        "action": action,
                        "destination": str(dest_file if not dry_run else dest_folder)
                    }))
                except Exception as err:
                    self.msg_queue.put(("item_done", {
                        "file": img_path.name,
                        "category": "ERROR",
                        "confidence": "0%",
                        "action": "FAILED",
                        "destination": str(err)
                    }))

            self.msg_queue.put(("all_done",))

        threading.Thread(target=worker, daemon=True).start()

    def process_queue_events(self):
        """Check for messages posted from background threads."""
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                msg_type = msg[0]

                if msg_type == "test_api_result":
                    ok = msg[1]
                    err_msg = msg[2] if len(msg) > 2 else ""
                    if ok:
                        self.lbl_api_status.config(text="● Connected (Articul8 Bivia)", fg="#34d399", bg="#064e3b")
                    else:
                        self.lbl_api_status.config(text="● Auth Error (Click to change key)", fg="#fb7185", bg="#4c0519")

                elif msg_type == "progress":
                    idx, total, name = msg[1], msg[2], msg[3]
                    self.progress_bar["value"] = idx - 1
                    self.lbl_progress.config(text=f"Analyzing [{idx}/{total}]: {name}")

                elif msg_type == "item_done":
                    item = msg[1]
                    self.sorting_results.append(item)
                    self.tree_results.insert("", "end", values=(
                        item["file"],
                        item["category"],
                        item["confidence"],
                        item["action"],
                        item["destination"]
                    ))
                    self.lbl_result_count.config(text=f"{len(self.sorting_results)} sorted")

                elif msg_type == "all_done":
                    self.is_processing = False
                    self.btn_sort.config(state="normal")
                    self.progress_bar["value"] = self.progress_bar["maximum"]
                    self.lbl_progress.config(text="Sorting complete! 🎉")
                    self.scan_input_directory()
                    messagebox.showinfo("Complete", f"Successfully categorized {len(self.sorting_results)} images!")

        except queue.Empty:
            pass

        self.after(100, self.process_queue_events)


def main():
    app = NativeImageSorterGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
