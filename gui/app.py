"""Small desktop shell for starting one GameArchiveManager task."""

from __future__ import annotations

import re
import sys
import threading
from pathlib import Path


def _sharp_text() -> None:
    """Draw text at the monitor's real resolution instead of a stretched bitmap."""
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_sharp_text()

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, simpledialog

# ``py gui\\app.py`` places gui/ on sys.path, not the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from application.app_service import GameArchiveService
from application.runtime_paths import default_config_path
from gui import settings_panel, theme, window_place
from gui.password_library import PasswordLibraryDialog
from password.session_store import PasswordStoreError
from recovery.manual import ManualPasswordAction, ManualPasswordResponse


THEME_LABELS = {"auto": "自动", "light": "浅色", "dark": "深色"}
UI = {
    "zh_CN": {
        "language": "中/EN", "auto": "自动", "light": "浅色", "dark": "深色",
        "browse": "压缩包", "browse_folder": "文件夹", "start": "开始解压",
        "settings": "设置", "library": "密码库",
        "choose": "就绪",
        "select_archive": "选择压缩包", "select_folder": "选择文件夹",
        "select_first": "先选择资源",
        "preparing": "正在准备任务…", "processing": "正在{phase}{suffix}",
        "password_title": "需要密码", "password_prompt": "无法解压 {name}，请输入密码：",
        "completed": "任务完成。", "failed": "失败（{stage}）：{reason}",
        "settings_title": "设置", "save": "保存设置",
        "brand_subtitle": "游戏资源管理器 · 本地安全处理",
        "hero_title": "智能解压", "hero_subtitle": "自动识别压缩资源，递归处理并验证输出",
        "local_badge": "本地处理 · 不上传文件",
        "input_title": "智能解压", "input_hint": "",
        "path_label": "路径", "path_placeholder": "",
        "selected_empty": "未选择资源", "kind_empty": "",
        "kind_archive": "压缩包", "kind_folder": "文件夹", "kind_file": "文件",
        "input_archive": "压缩包", "input_folder": "文件夹",
        "input_note": "",
        "status_title": "进度", "status_hint": "",
        "status_ready": "等待开始", "status_running": "任务进行中", "status_done": "全部完成",
        "status_error": "需要处理", "status_waiting": "等待中",
        "stage_prepare": "准备任务", "stage_extract": "解压归档",
        "stage_scan": "扫描内容", "stage_validate": "验证结果", "stage_deliver": "整理交付",
        "stage_done": "已完成", "stage_active": "进行中", "stage_wait": "等待",
        "stage_failed": "未完成", "clear": "清除", "input_type": "输入类型",
        "status_footer": "安全校验 · 保留源文件 · 不显示虚假百分比",
    },
    "en": {
        "language": "中/EN", "auto": "Auto", "light": "Light", "dark": "Dark",
        "browse": "Archive", "browse_folder": "Folder", "start": "Extract",
        "settings": "Settings", "library": "Password library",
        "choose": "Ready",
        "select_archive": "Select archive", "select_folder": "Select folder",
        "select_first": "Select a resource first.",
        "preparing": "Preparing task…", "processing": "Processing {phase}{suffix}",
        "password_title": "Password required", "password_prompt": "Unable to extract {name}. Enter the password:",
        "completed": "Task completed.", "failed": "Failed ({stage}): {reason}",
        "settings_title": "Settings", "save": "Save settings",
        "brand_subtitle": "Game resource manager · local processing",
        "hero_title": "Smart extraction", "hero_subtitle": "Identify archives, process nested resources and verify output",
        "local_badge": "Local only · No uploads",
        "input_title": "Smart extraction", "input_hint": "",
        "path_label": "Path", "path_placeholder": "",
        "selected_empty": "No resource selected", "kind_empty": "",
        "kind_archive": "Archive", "kind_folder": "Folder", "kind_file": "File",
        "input_archive": "Archive", "input_folder": "Folder",
        "input_note": "",
        "status_title": "Progress", "status_hint": "",
        "status_ready": "Ready to start", "status_running": "Task in progress", "status_done": "All done",
        "status_error": "Action required", "status_waiting": "Waiting",
        "stage_prepare": "Prepare task", "stage_extract": "Extract archives",
        "stage_scan": "Scan contents", "stage_validate": "Verify results", "stage_deliver": "Organize delivery",
        "stage_done": "Done", "stage_active": "In progress", "stage_wait": "Waiting",
        "stage_failed": "Incomplete", "clear": "Clear", "input_type": "Input type",
        "status_footer": "Safety checks · Source preserved · No fake percentages",
    },
}


class GameArchiveApp:
    """Keep UI updates on tkinter's event loop while the task runs in a thread."""

    _BASE_WIDTH = 720
    _BASE_HEIGHT = 360

    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.config_path = default_config_path()
        values = settings_panel.load_form_values(self.config_path)
        self.theme_mode = tk.StringVar(value=values.get("theme_mode", "auto"))
        self.ui_language = tk.StringVar(value=values.get("ui_language", "zh_CN"))
        if self.ui_language.get() not in UI:
            self.ui_language.set("zh_CN")
        if self.theme_mode.get() not in THEME_LABELS:
            self.theme_mode.set("auto")
        self.path_value = tk.StringVar()
        self.status_value = tk.StringVar(value=self._text("choose"))
        self.running = False
        self._password_dialog: PasswordLibraryDialog | None = None
        self._verified_session_passwords: list[str] = []
        self._surfaces: list[tk.Widget] = []
        self._labels: list[tk.Label] = []
        self.theme_buttons: dict[str, tk.Button] = {}
        self._fitting = False
        self._resize_job = None
        self._last_size = (0, 0)
        self.window.withdraw()
        self._build()
        self.apply_theme()
        self.apply_language()
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        target_width = max(780, min(900, screen_width - 80))
        target_height = max(500, min(520, screen_height - 100))
        requested = window_place.geometry_for(
            "main", self.window, target_width, target_height
        )
        # Older versions remembered a much larger dashboard. Keep its position,
        # but cap its saved size so the concise layout actually opens compact.
        match = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", requested)
        if match:
            saved_width, saved_height, x, y = match.groups()
            requested = (
                f"{min(int(saved_width), target_width)}x"
                f"{min(int(saved_height), target_height)}{x}{y}"
            )
        self.window.geometry(
            window_place.fully_visible_geometry(self.window, requested)
        )
        self.window.update_idletasks()
        self._fit_to_window()
        self.window.update_idletasks()
        width = max(self.window.winfo_width(), self.window.minsize()[0])
        height = max(self.window.winfo_height(), self.window.minsize()[1])
        requested = (
            f"{width}x{height}{self.window.winfo_x():+d}{self.window.winfo_y():+d}"
        )
        self.window.geometry(
            window_place.fully_visible_geometry(self.window, requested)
        )
        self._last_size = (width, height)
        self.window.bind("<Configure>", self._on_window_configure)
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.window.deiconify()
        window_place.restore_maximized("main", self.window)

    def _build(self) -> None:
        """Build the redesigned dashboard while keeping the extraction core intact."""
        self.window.title("GameArchiveManager")
        self.window.minsize(780, 500)
        self.window.configure(bg="#f3f3f3")
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)

        self.font = tkfont.Font(family="Segoe UI", size=9)
        self.title_font = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        self.section_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self._surfaces: list[tk.Widget] = []
        self._cards: list[tk.Widget] = []
        self._insets: list[tk.Widget] = []
        self._accent_surfaces: list[tk.Widget] = []
        self._labels: list[tk.Label] = []
        self._label_roles: dict[tk.Label, str] = {}
        self._label_keys: dict[tk.Label, str] = {}
        self._button_keys: dict[tk.Button, str] = {}
        self._button_roles: dict[tk.Button, str] = {}
        self._all_buttons: list[tk.Button] = []
        self.theme_buttons: dict[str, tk.Button] = {}
        self.phase_steps: dict[str, dict[str, tk.Widget]] = {}
        self._active_phase_key: str | None = None
        self._task_finished = False
        self.colors = theme.palette("light")

        def frame(parent, *, role="surface", **kwargs):
            options = {"bd": 0, "highlightthickness": 0}
            options.update(kwargs)
            widget = tk.Frame(parent, **options)
            if role == "card":
                widget.configure(highlightthickness=1)
                self._cards.append(widget)
            elif role == "inset":
                widget.configure(highlightthickness=1)
                self._insets.append(widget)
            elif role == "accent":
                self._accent_surfaces.append(widget)
            else:
                self._surfaces.append(widget)
            return widget

        def label(parent, text_or_key, *, role="normal", font=None, variable=None, **kwargs):
            text_value = self._text(text_or_key) if variable is None else ""
            widget = tk.Label(
                parent, text=text_value, textvariable=variable,
                font=font or self.font, anchor="w", justify="left",
                bd=0, **kwargs,
            )
            self._labels.append(widget)
            self._label_roles[widget] = role
            if variable is None and text_or_key in UI[self.ui_language.get()]:
                self._label_keys[widget] = text_or_key
            return widget

        def button(parent, key, command, *, role="secondary", **kwargs):
            widget = tk.Button(
                parent, text=self._text(key), command=command, font=self.font,
                relief="flat", bd=0, padx=9, pady=5,
                highlightthickness=1, **kwargs,
            )
            self._all_buttons.append(widget)
            self._button_keys[widget] = key
            self._button_roles[widget] = role
            return widget

        # Top bar: product identity at left, language and appearance at right.
        self.header = frame(self.window)
        self.header.grid(row=0, column=0, sticky="ew", padx=18, pady=(10, 8))
        self.header.columnconfigure(2, weight=1)
        self.logo = frame(self.header, role="accent", width=32, height=32)
        self.logo.grid(row=0, column=0, sticky="w", padx=(0, 9))
        self.logo.grid_propagate(False)
        self.logo_label = label(self.logo, "GA", role="accent", font=("Segoe UI", 13, "bold"))
        self.logo_label.place(relx=0.5, rely=0.5, anchor="center")

        self.brand_title = label(
            self.header, "GameArchiveManager", font=("Segoe UI", 13, "bold")
        )
        self.brand_title.grid(row=0, column=1, sticky="w")

        self.choices = frame(self.header)
        self.choices.grid(row=0, column=3, sticky="e", padx=(12, 0))
        self.choices.columnconfigure(0, weight=1)
        self.language_button = button(self.choices, "language", self._toggle_language)
        self.language_button.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        for column, key in enumerate(THEME_LABELS, start=1):
            item = button(
                self.choices, key, lambda chosen=key: self._choose_theme(chosen),
                role="theme",
            )
            item.grid(row=0, column=column, sticky="ew", padx=(0, 7 if column < 3 else 0))
            self.theme_buttons[key] = item

        # Compact workspace: resource selection and live progress are primary.
        self.content = frame(self.window)
        self.content.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 8))
        self.content.columnconfigure(0, weight=1, uniform="main_card")
        self.content.columnconfigure(1, weight=1, uniform="main_card")
        self.content.rowconfigure(0, weight=1)

        self.input_panel = frame(self.content, role="card")
        self.input_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.input_panel.columnconfigure(0, weight=1)
        label(
            self.input_panel, "input_title", role="card", font=self.section_font
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 7))
        label(
            self.input_panel, "path_label", role="card_muted",
            font=("Segoe UI", 8, "bold")
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 3))
        self.path_entry = tk.Entry(
            self.input_panel, textvariable=self.path_value, font=("Segoe UI", 9),
            relief="flat", bd=0, highlightthickness=1,
        )
        self.path_entry.grid(row=2, column=0, sticky="ew", padx=14, ipady=5)
        self.selected_info = frame(self.input_panel, role="inset")
        self.selected_info.grid(row=3, column=0, sticky="ew", padx=14, pady=(6, 8))
        self.selected_info.columnconfigure(0, weight=1)
        self.selected_name_value = tk.StringVar(
            master=self.window, value=self._text("selected_empty")
        )
        self.selected_name_label = label(
            self.selected_info, "", role="inset",
            variable=self.selected_name_value, font=("Segoe UI", 9, "bold"),
        )
        self.selected_name_label.grid(
            row=0, column=0, sticky="ew", padx=9, pady=(6, 3)
        )
        self.input_kind_value = tk.StringVar(master=self.window, value="")
        self.input_kind_label = label(
            self.selected_info, "", role="badge", variable=self.input_kind_value,
            font=("Segoe UI", 8), padx=7, pady=2,
        )
        self.input_kind_label.grid(
            row=1, column=0, sticky="w", padx=9, pady=(0, 5)
        )

        self.input_buttons = frame(self.input_panel)
        self.input_buttons.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 7))
        self.input_buttons.columnconfigure(0, weight=1, uniform="input")
        self.input_buttons.columnconfigure(1, weight=1, uniform="input")
        self.browse_button = button(self.input_buttons, "input_archive", self.browse)
        self.folder_button = button(self.input_buttons, "input_folder", self.browse_folder)
        self.browse_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.folder_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.start_button = button(self.input_panel, "start", self.start, role="primary")
        self.start_button.grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 12))

        self.status_panel = frame(self.content, role="card")
        self.status_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.status_panel.columnconfigure(0, weight=1)
        label(
            self.status_panel, "status_title", role="card",
            font=self.section_font
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 7))
        self.status_banner = frame(self.status_panel, role="inset")
        self.status_banner.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        self.status_banner.columnconfigure(1, weight=1)
        self.status_dot = label(
            self.status_banner, "●", role="badge", font=("Segoe UI", 10, "bold")
        )
        self.status_dot.grid(row=0, column=0, sticky="w", padx=(9, 6), pady=5)
        self.status_label = label(
            self.status_banner, "", role="inset", variable=self.status_value,
            font=("Segoe UI", 9, "bold"), wraplength=240,
        )
        self.status_label.grid(row=0, column=1, sticky="ew", padx=(0, 9), pady=5)

        self.phase_viewport = frame(self.status_panel)
        self.phase_viewport.grid(row=2, column=0, sticky="nsew", padx=14)
        self.phase_viewport.columnconfigure(0, weight=1)
        self.phase_viewport.rowconfigure(0, weight=1)
        self.status_panel.rowconfigure(2, weight=1)
        self.phase_canvas = tk.Canvas(
            self.phase_viewport, highlightthickness=0, bd=0,
            yscrollincrement=24,
        )
        self.phase_canvas.grid(row=0, column=0, sticky="nsew")
        self.phase_scrollbar = tk.Scrollbar(
            self.phase_viewport, orient="vertical",
            command=self.phase_canvas.yview,
        )
        self.phase_canvas.configure(yscrollcommand=self.phase_scrollbar.set)
        self.phase_scrollbar.grid_remove()
        self.phase_list = frame(self.phase_canvas)
        self.phase_list.columnconfigure(0, weight=1)
        self.phase_window_id = self.phase_canvas.create_window(
            (0, 0), window=self.phase_list, anchor="nw",
        )
        self.phase_list.bind(
            "<Configure>", lambda event: self._update_phase_scrollregion()
        )
        self.phase_canvas.bind("<Configure>", self._on_phase_canvas_configure)
        self.phase_canvas.bind(
            "<MouseWheel>",
            lambda event: self.phase_canvas.yview_scroll(
                int(-event.delta / 120), "units"
            ),
        )
        phases = ("prepare", "extract", "scan", "validate", "deliver")
        for index, key in enumerate(phases):
            row = frame(self.phase_list, role="card")
            row.grid(row=index, column=0, sticky="ew", pady=(0, 3))
            row.columnconfigure(1, weight=1)
            row.rowconfigure(0, weight=1)
            number = label(row, f"{index + 1:02d}", role="step_badge", font=("Segoe UI", 8, "bold"))
            number.grid(row=0, column=0, sticky="w", padx=(8, 6), pady=4)
            title = label(row, f"stage_{key}", role="card", font=("Segoe UI", 9, "bold"))
            title.grid(row=0, column=1, sticky="w", pady=4)
            state = label(row, "stage_wait", role="card_muted", font=("Segoe UI", 8))
            state.grid(row=0, column=2, sticky="e", padx=(4, 8), pady=4)
            self.phase_steps[key] = {"row": row, "number": number, "title": title, "state": state}

        # Bottom utility bar stays visually separate from the primary action.
        self.utilities = frame(self.window)
        self.utilities.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))
        self.utilities.columnconfigure(0, weight=1)
        self.library_button = button(self.utilities, "library", self.open_password_library)
        self.settings_button = button(self.utilities, "settings", self.open_settings)
        self.library_button.grid(row=0, column=1, sticky="ew", padx=(8, 4))
        self.settings_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self.path_value.trace_add("write", lambda *_: self._update_selection_preview())
        self._update_selection_preview()

    def _on_phase_canvas_configure(self, event) -> None:
        self.phase_canvas.itemconfigure(self.phase_window_id, width=event.width)
        self._sync_phase_scrollbar()

    def _update_phase_scrollregion(self) -> None:
        self.phase_canvas.configure(scrollregion=self.phase_canvas.bbox("all"))
        self.window.after_idle(self._sync_phase_scrollbar)

    def _sync_phase_scrollbar(self) -> None:
        if not self.phase_canvas.winfo_exists():
            return
        bounds = self.phase_canvas.bbox("all")
        viewport_height = self.phase_canvas.winfo_height()
        if bounds and bounds[3] > viewport_height + 2:
            self.phase_scrollbar.grid(row=0, column=1, sticky="ns")
        else:
            self.phase_scrollbar.grid_remove()

    def _update_selection_preview(self) -> None:
        raw = self.path_value.get().strip().strip('"')
        if not raw:
            self.selected_name_value.set(self._text("selected_empty"))
            self.input_kind_value.set("")
            self.input_kind_label.grid_remove()
            return
        self.input_kind_label.grid(
            row=1, column=0, sticky="w", padx=9, pady=(0, 5)
        )
        path = Path(raw).expanduser()
        self.selected_name_value.set(path.name or raw)
        if path.is_dir():
            kind = "kind_folder"
        elif path.suffix:
            kind = "kind_archive"
        else:
            kind = "kind_file"
        suffix = path.suffix.upper().lstrip(".")
        kind_text = self._text(kind)
        self.input_kind_value.set(f"{kind_text} · {suffix}" if suffix and kind != "kind_folder" else kind_text)

    def _render_phase_steps(self, *, done: bool = False, failed: bool = False) -> None:
        colors = getattr(self, "colors", theme.palette("light"))
        keys = ("prepare", "extract", "scan", "validate", "deliver")
        active_index = keys.index(self._active_phase_key) if self._active_phase_key in keys else -1
        for index, key in enumerate(keys):
            item = self.phase_steps.get(key)
            if not item:
                continue
            if done:
                marker, state, role = "✓", "stage_done", "done"
            elif failed and index == active_index:
                marker, state, role = "!", "stage_failed", "failed"
            elif active_index >= 0 and index < active_index:
                marker, state, role = "✓", "stage_done", "done"
            elif active_index == index:
                marker, state, role = "●", "stage_active", "active"
            else:
                marker, state, role = f"{index + 1:02d}", "stage_wait", "wait"
            item["number"].configure(text=marker)
            item["state"].configure(text=self._text(state))
            if role == "active":
                bg, fg = colors["accent"], colors["accent_fg"]
                title_fg, state_fg = colors["fg"], colors["accent"]
            elif role == "done":
                bg, fg = colors["ok"], "#ffffff" if colors["bg"] != "#1e1e1e" else "#102a1d"
                title_fg, state_fg = colors["fg"], colors["ok"]
            elif role == "failed":
                bg, fg = colors["danger"], "#ffffff"
                title_fg, state_fg = colors["danger"], colors["danger"]
            else:
                bg, fg = colors["entry_bg"], colors["muted"]
                title_fg, state_fg = colors["fg"], colors["muted"]
            item["number"].configure(background=bg, foreground=fg)
            item["title"].configure(foreground=title_fg)
            item["state"].configure(foreground=state_fg)

    def _close(self) -> None:
        if self._resize_job is not None:
            try:
                self.window.after_cancel(self._resize_job)
            except tk.TclError:
                pass
            self._resize_job = None
        if self._password_dialog is not None and self._password_dialog.dialog.winfo_exists():
            self._password_dialog.close()
        window_place.remember("main", self.window)
        self.window.destroy()

    def _on_window_configure(self, event: tk.Event) -> None:
        if event.widget is not self.window or self._fitting:
            return
        size = (event.width, event.height)
        if size == self._last_size:
            return
        self._last_size = size
        if self._resize_job is not None:
            self.window.after_cancel(self._resize_job)
        self._resize_job = self.window.after(160, self._finish_resize)

    def _finish_resize(self) -> None:
        self._resize_job = None
        self._fit_to_window()
        self._last_size = (self.window.winfo_width(), self.window.winfo_height())

    def _fit_to_window(self) -> None:
        """Reflow header controls and text without jittering fonts during resize."""
        if self._fitting:
            return
        width = max(self.window.winfo_width(), 1)
        if width < 2:
            return
        self._fitting = True
        try:
            self._place_choices(width)
            inner = max(240, width - 36)
            self.selected_name_label.configure(wraplength=max(160, int(inner * 0.46)))
            self.status_label.configure(wraplength=max(160, int(inner * 0.38)))
            self.window.minsize(780, 500)
        finally:
            self._fitting = False


    def _action_button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            font=self.font,
            command=command,
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            highlightthickness=2,
        )

    def _place_choices(self, width: int) -> None:
        """Keep language and theme choices readable at every permitted width."""
        for widget in (self.language_button, *self.theme_buttons.values()):
            widget.grid_remove()
        theme_need = sum(self.font.measure(self._text(key)) + 28 for key in THEME_LABELS) + 16
        language_need = self.font.measure(self._text("language")) + 32
        available = max(1, width - 32)
        for column in range(4):
            self.choices.columnconfigure(column, weight=0, uniform="")
        if available >= language_need + theme_need + 8:
            self.language_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            self.choices.columnconfigure(0, weight=1)
            for column, button in enumerate(self.theme_buttons.values(), start=1):
                self.choices.columnconfigure(column, weight=1, uniform="theme")
                button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 1 else 8, 0))
        elif available >= theme_need:
            self.language_button.grid(row=0, column=0, columnspan=3, sticky="ew")
            for column in range(3):
                self.choices.columnconfigure(column, weight=1, uniform="theme")
            for column, button in enumerate(self.theme_buttons.values()):
                button.grid(row=1, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0), pady=(6, 0))
        else:
            self.language_button.grid(row=0, column=0, sticky="ew")
            self.choices.columnconfigure(0, weight=1)
            for row, button in enumerate(self.theme_buttons.values(), start=1):
                button.grid(row=row, column=0, sticky="ew", pady=(6, 0))

    def _choose_theme(self, choice: str) -> None:
        self.theme_mode.set(choice)
        values = settings_panel.load_form_values(self.config_path)
        values["theme_mode"] = choice
        warning = settings_panel.save_form_values(self.config_path, values)
        if warning:
            self.status_value.set(warning)
        self.apply_theme()

    def _text(self, key: str, **values) -> str:
        return UI[self.ui_language.get()].get(key, key).format(**values)

    def _toggle_language(self) -> None:
        self._choose_language("en" if self.ui_language.get() == "zh_CN" else "zh_CN")

    def _choose_language(self, choice: str) -> None:
        self.ui_language.set(choice)
        values = settings_panel.load_form_values(self.config_path)
        values["ui_language"] = choice
        warning = settings_panel.save_form_values(self.config_path, values)
        if warning:
            self.status_value.set(warning)
        self.apply_language()

    def apply_language(self) -> None:
        for widget, key in self._label_keys.items():
            widget.configure(text=self._text(key))
        for widget, key in self._button_keys.items():
            widget.configure(text=self._text(key))
        if not self.running and not self._task_finished:
            self.status_value.set(self._text("choose"))
        self._update_selection_preview()
        self._place_choices(self.window.winfo_width())
        self._fit_to_window()
        self._render_phase_steps()


    def apply_theme(self) -> None:
        colors = theme.palette(theme.resolved_appearance(self.theme_mode.get()))
        self.colors = colors
        self.window.configure(background=colors["bg"])
        for widget in self._surfaces:
            widget.configure(background=colors["bg"])
        for widget in self._cards:
            widget.configure(
                background=colors["surface"],
                highlightbackground=colors["border"],
                highlightcolor=colors["border"],
            )
        for widget in self._insets:
            widget.configure(
                background=colors["entry_bg"],
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
            )
        for widget in self._accent_surfaces:
            widget.configure(background=colors["accent"])
        self.phase_viewport.configure(background=colors["surface"])
        self.phase_list.configure(background=colors["surface"])
        self.phase_canvas.configure(
            background=colors["surface"],
            highlightbackground=colors["border"],
        )
        self.phase_scrollbar.configure(
            background=colors["surface"],
            troughcolor=colors["entry_bg"],
            activebackground=colors["accent"],
            highlightbackground=colors["border"],
            relief="flat",
            borderwidth=0,
        )
        for widget, role in self._label_roles.items():
            if role in {"card", "card_muted"}:
                background = colors["surface"]
            elif role in {"inset", "step_badge"}:
                background = colors["entry_bg"]
            elif role in {"accent", "badge"}:
                background = colors["accent"]
            else:
                background = colors["bg"]
            foreground = (
                colors["muted"] if role in {"muted", "card_muted"}
                else colors["accent_fg"] if role in {"accent", "badge"}
                else colors["accent"] if role == "step_badge"
                else colors["fg"]
            )
            widget.configure(background=background, foreground=foreground)
        self.path_entry.configure(
            background=colors["entry_bg"],
            foreground=colors["fg"],
            insertbackground=colors["fg"],
            highlightthickness=1,
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
        )
        for widget, role in self._button_roles.items():
            key = self._button_keys.get(widget, "")
            if role == "primary":
                background, foreground = colors["accent"], colors["accent_fg"]
                active_background = colors["accent"]
            elif role == "theme" and key == self.theme_mode.get():
                background, foreground = colors["accent"], colors["accent_fg"]
                active_background = colors["accent"]
            else:
                background, foreground = colors["surface"], colors["fg"]
                active_background = colors["entry_bg"]
            widget.configure(
                background=background,
                foreground=foreground,
                activebackground=active_background,
                activeforeground=foreground,
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
                cursor="hand2",
                disabledforeground=colors["muted"],
            )
        self._render_phase_steps()
        if self._password_dialog is not None and self._password_dialog.dialog.winfo_exists():
            self._password_dialog.apply_colors(colors)


    def open_password_library(self, parent=None) -> None:
        if self._password_dialog is not None and self._password_dialog.dialog.winfo_exists():
            self._password_dialog.dialog.lift()
            self._password_dialog.dialog.focus_force()
            return
        try:
            self._password_dialog = PasswordLibraryDialog(
                parent or self.window,
                language=self.ui_language.get(),
                colors=theme.palette(theme.resolved_appearance(self.theme_mode.get())),
            )
        except PasswordStoreError as error:
            self.status_value.set(str(error))
            messagebox.showerror(self._text("library"), str(error), parent=self.window)

    def browse(self) -> None:
        path = filedialog.askopenfilename(
            title=self._text("select_archive"),
            filetypes=(
                ("压缩包 / Archives", "*.zip *.7z *.rar *.tar *.gz *.bz2 *.xz *.lz4 *.zst *.cab *.iso *.wim *.001"),
                ("所有文件 / All files", "*.*"),
            ),
        )
        if path:
            self.path_value.set(path)

    def browse_folder(self) -> None:
        path = filedialog.askdirectory(title=self._text("select_folder"))
        if path:
            self.path_value.set(path)

    def start(self) -> None:
        path = self.path_value.get().strip().strip('"')
        if not path:
            self.status_value.set(self._text("select_first"))
            return
        if self.running:
            return
        self.running = True
        self._task_finished = False
        self._active_phase_key = "prepare"
        self.start_button.configure(state="disabled")
        self.status_value.set(self._text("preparing"))
        self._render_phase_steps()
        threading.Thread(target=self._run_task, args=(path,), daemon=True).start()

    def _run_task(self, path: str) -> None:
        try:
            # Reload settings for each task but preserve passwords verified
            # during this GUI session even when persistent saving is disabled.
            service = GameArchiveService(config_path=self.config_path)
            for password in self._verified_session_passwords:
                service.session_password_store.add_verified(password, persist=False)
            report = service.execute_task(
                path,
                progress_callback=self._progress,
                manual_password_callback=self._request_manual_password,
            )
            self._verified_session_passwords = service.session_password_store.verified_passwords()
            warning = service.session_password_store.last_persistence_error
            self.window.after(0, self._finish, report, warning)
        except Exception as error:
            self.window.after(0, self._fail, "APPLICATION", f"{type(error).__name__}: {error}")

    def _progress(self, update) -> None:
        phase = str(getattr(getattr(update, "phase", None), "value", getattr(update, "phase", "PROCESSING"))).upper()
        phase_map = {
            "EXTRACTING": "extract", "SCANNING": "scan",
            "VALIDATING": "validate", "ORGANIZING": "deliver",
            "DELIVERING": "deliver", "PREPARING": "prepare",
        }
        phase_key = phase_map.get(phase, self._active_phase_key or "prepare")
        archive = getattr(update, "current_archive", None)
        phase_label = self._text(f"stage_{phase_key}")
        message = self._text(
            "processing",
            phase=phase_label,
            suffix=f": {archive}" if archive else "…",
        )
        self.window.after(0, self._apply_progress, phase_key, message)

    def _apply_progress(self, phase_key: str, message: str) -> None:
        self._active_phase_key = phase_key
        self.status_value.set(message)
        self._render_phase_steps()

    def _request_manual_password(self, request) -> ManualPasswordResponse:
        """Ask on Tk's thread; the recovery engine stores only verified input."""
        answer: dict[str, str | None] = {"password": None}
        ready = threading.Event()

        def ask() -> None:
            answer["password"] = simpledialog.askstring(
                self._text("password_title"),
                self._text("password_prompt", name=request.archive_path.name),
                parent=self.window,
                show="*",
            )
            ready.set()

        self.window.after(0, ask)
        ready.wait()
        password = answer["password"]
        if password:
            return ManualPasswordResponse(ManualPasswordAction.INPUT_PASSWORD, password)
        return ManualPasswordResponse(ManualPasswordAction.SKIP_ARCHIVE)

    def _finish(self, report, password_warning: str | None = None) -> None:
        self.running = False
        self.start_button.configure(state="normal")
        if getattr(report, "failed_count", 0):
            detail = next(iter(getattr(report, "failure_details", [])), None)
            stage = getattr(detail, "stage", "UNKNOWN")
            reason = getattr(detail, "reason", getattr(report, "summary", "任务失败"))
            self._fail(stage, reason)
            return
        self._task_finished = True
        self._active_phase_key = "deliver"
        self.status_value.set(
            self._text("completed") + (f" {password_warning}" if password_warning else "")
        )
        self._render_phase_steps(done=True)
        self.status_dot.configure(foreground=self.colors["ok"])

    def _fail(self, stage: str, reason: str) -> None:
        self.running = False
        self._task_finished = False
        self.start_button.configure(state="normal")
        self.status_value.set(self._text("failed", stage=stage, reason=reason))
        stage_upper = str(stage).upper()
        phase_map = {
            "EXTRACTING": "extract", "SCANNING": "scan",
            "VALIDATING": "validate", "ORGANIZING": "deliver",
            "DELIVERY": "deliver", "APPLICATION": self._active_phase_key or "prepare",
        }
        self._active_phase_key = phase_map.get(stage_upper, self._active_phase_key or "prepare")
        self._render_phase_steps(failed=True)
        self.status_dot.configure(foreground=self.colors["danger"])

    def open_settings(self) -> None:
        dialog = tk.Toplevel(self.window)
        dialog.withdraw()
        dialog.title(self._text("settings_title"))
        dialog.columnconfigure(0, weight=1)
        # The form may scroll when the dialog is shortened, but its fixed save
        # bar must always remain visible.
        dialog.rowconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=0)
        colors = theme.palette(theme.resolved_appearance(self.theme_mode.get()))
        dialog.configure(background=colors["bg"])

        viewport = tk.Frame(dialog, bg=colors["bg"])
        viewport.grid(row=0, column=0, sticky="nsew")
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        canvas = tk.Canvas(viewport, highlightthickness=0, bd=0, background=colors["bg"])
        bar = tk.Scrollbar(viewport, command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        holder = tk.Frame(canvas, background=colors["bg"])
        holder.columnconfigure(0, weight=1)
        window_id = canvas.create_window((0, 0), window=holder, anchor="nw")

        def paint(next_colors: dict[str, str]) -> None:
            dialog.configure(background=next_colors["bg"])
            viewport.configure(background=next_colors["bg"])
            canvas.configure(background=next_colors["bg"])
            holder.configure(background=next_colors["bg"])
            save_bar.configure(background=next_colors["bg"])
            save_button.configure(
                background=next_colors["accent"],
                foreground=next_colors["accent_fg"],
                activebackground=next_colors["accent"],
                activeforeground=next_colors["accent_fg"],
                highlightthickness=2,
                highlightbackground=next_colors["border"],
                highlightcolor=next_colors["accent"],
            )
            form.apply_colors(next_colors)

        def on_theme(choice: str) -> None:
            self._choose_theme(choice)
            paint(theme.palette(theme.resolved_appearance(choice)))

        def on_language(choice: str) -> None:
            self._choose_language(choice)
            dialog.title(self._text("settings_title"))
            save_button.configure(text=self._text("save"))

        try:
            form = settings_panel.build(
                holder, self.config_path, colors, on_theme=on_theme,
                language=self.ui_language.get(), on_language=on_language,
                on_password_library=lambda: self.open_password_library(parent=dialog),
            )
        except PasswordStoreError as error:
            # A damaged library must not be presented as empty or saved over.
            dialog.destroy()
            self.status_value.set(str(error))
            messagebox.showerror(self._text("settings_title"), str(error), parent=self.window)
            return
        form.grid(row=0, column=0, sticky="ew")

        save_bar = tk.Frame(dialog, bg=colors["bg"], height=36)
        save_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        save_bar.grid_propagate(False)
        save_button = tk.Button(
            save_bar,
            text=self._text("save"),
            font=form.font,
            command=form.save,
            relief="flat",
            bd=0,
            highlightthickness=2,
        )
        save_button.place(relx=0, rely=0, relwidth=1, relheight=1)
        paint(colors)

        def resize_form(event: tk.Event) -> None:
            """Reflow controls at the live dialog width while a user drags."""
            if event.widget is not canvas:
                return
            width = max(form.min_width, event.width)
            canvas.itemconfigure(window_id, width=width)
            form.reflow(width)
            canvas.configure(scrollregion=canvas.bbox("all"))
            if event.height < form.winfo_reqheight():
                bar.grid(row=0, column=1, sticky="ns")
            else:
                bar.grid_remove()

        def fit_content_height(event: tk.Event | None = None) -> None:
            """Keep the active group and save bar visible; trim surplus on release."""
            dialog.update_idletasks()
            form.reflow(dialog.winfo_width())
            content_height = form.winfo_reqheight()
            fitted_height = min(content_height + form.band + 12, max(240, dialog.winfo_screenheight() - 80))
            dialog.minsize(form.min_width, fitted_height)
            canvas.configure(scrollregion=(0, 0, max(form.min_width, dialog.winfo_width()), content_height))
            if content_height + form.band + 12 > fitted_height:
                bar.grid(row=0, column=1, sticky="ns")
            else:
                bar.grid_remove()
            if dialog.winfo_height() != fitted_height:
                dialog.geometry(
                    f"{dialog.winfo_width()}x{fitted_height}+{dialog.winfo_x()}+{dialog.winfo_y()}"
                )

        canvas.bind("<Configure>", resize_form)
        dialog.bind("<ButtonRelease-1>", fit_content_height)
        form.bind("<<SettingsGroupChanged>>", fit_content_height)
        dialog.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"))
        screen_w = max(560, dialog.winfo_screenwidth() - 80)
        target = min(form.preferred_width(), screen_w)
        form.reflow(target)
        save_bar.configure(height=form.band)
        dialog.update_idletasks()
        content_h = form.winfo_reqheight()
        save_h = form.band + 12
        height = min(content_h + save_h, max(360, dialog.winfo_screenheight() - 80))
        if content_h + save_h > height:
            bar.grid(row=0, column=1, sticky="ns")
        else:
            bar.grid_remove()
        dialog.minsize(form.min_width, height)
        dialog.geometry(window_place.geometry_for("settings", dialog, target, height, anchor=self.window))
        canvas.itemconfigure(window_id, width=target)
        canvas.configure(scrollregion=(0, 0, target, content_h))
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_settings(dialog))
        dialog.deiconify()

    @staticmethod
    def _close_settings(dialog: tk.Toplevel) -> None:
        window_place.remember("settings", dialog)
        dialog.destroy()


def main() -> None:
    window = tk.Tk()
    GameArchiveApp(window)
    window.mainloop()


if __name__ == "__main__":
    main()
