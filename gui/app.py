"""Small desktop shell for starting one GameArchiveManager task."""

from __future__ import annotations

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
from tkinter import filedialog, font as tkfont, simpledialog

# ``py gui\\app.py`` places gui/ on sys.path, not the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from application.app_service import GameArchiveService
from application.runtime_paths import default_config_path
from gui import settings_panel, theme, window_place
from recovery.manual import ManualPasswordAction, ManualPasswordResponse


THEME_LABELS = {"auto": "自动", "light": "浅色", "dark": "深色"}
UI = {
    "zh_CN": {
        "language": "中文 / English", "auto": "自动", "light": "浅色", "dark": "深色",
        "browse": "浏览", "start": "开始", "settings": "设置", "choose": "请选择文件夹或压缩包，然后开始。",
        "select_archive": "选择压缩包", "select_folder": "选择文件夹", "select_first": "请先选择文件夹或压缩包。",
        "preparing": "正在准备任务…", "processing": "正在{phase}{suffix}", "password_title": "需要密码",
        "password_prompt": "无法解压 {name}，请输入密码：", "completed": "任务完成。", "failed": "失败（{stage}）：{reason}",
        "settings_title": "设置", "save": "保存设置",
    },
    "en": {
        "language": "English / 中文", "auto": "Auto", "light": "Light", "dark": "Dark",
        "browse": "Browse", "start": "Start", "settings": "Settings", "choose": "Choose a folder or archive, then start.",
        "select_archive": "Select archive", "select_folder": "Select folder", "select_first": "Choose a folder or archive first.",
        "preparing": "Preparing task…", "processing": "Processing {phase}{suffix}", "password_title": "Password required",
        "password_prompt": "Unable to extract {name}. Enter the password:", "completed": "Task completed.", "failed": "Failed ({stage}): {reason}",
        "settings_title": "Settings", "save": "Save settings",
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
        self.window.geometry(window_place.geometry_for("main", self.window, 720, 520))
        self.window.update_idletasks()
        self._fit_to_window()
        self.window.update_idletasks()
        width = max(self.window.winfo_width(), 720)
        height = max(self.window.winfo_reqheight(), self.window.minsize()[1])
        self.window.geometry(f"{width}x{height}+{self.window.winfo_x()}+{self.window.winfo_y()}")
        self._last_size = (width, height)
        self.window.bind("<Configure>", self._on_window_configure)
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.window.deiconify()
        window_place.restore_maximized("main", self.window)

    def _build(self) -> None:
        self.window.title("GameArchiveManager")
        self.window.minsize(320, 450)
        self.font = tkfont.Font(family="Segoe UI", size=12)
        self.title_font = tkfont.Font(family="Segoe UI", size=18, weight="bold")
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(4, weight=1)

        self.title_label = tk.Label(
            self.window,
            text="GameArchiveManager",
            font=self.title_font,
            anchor="w",
            justify="left",
        )
        self.title_label.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        self._labels.append(self.title_label)

        self.choices = tk.Frame(self.window)
        self.choices.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._surfaces.append(self.choices)
        self.language_button = tk.Button(
            self.choices, text=self._text("language"), font=self.font, command=self._toggle_language,
            relief="flat", bd=0, highlightthickness=2,
        )
        self.language_button.grid(row=0, column=0, sticky="nsew")
        for column, key in enumerate(THEME_LABELS, start=1):
            self.choices.columnconfigure(column, weight=1, uniform="theme")
            button = tk.Button(
                self.choices,
                text=self._text(key),
                font=self.font,
                command=lambda chosen=key: self._choose_theme(chosen),
                relief="flat",
                bd=0,
                highlightthickness=2,
            )
            button.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 0))
            self.theme_buttons[key] = button

        self.path_entry = tk.Entry(self.window, textvariable=self.path_value, font=self.font, relief="flat")
        self.path_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        self.actions = tk.Frame(self.window)
        self.actions.grid(row=3, column=0, sticky="ew", padx=16)
        self._surfaces.append(self.actions)
        self.actions.columnconfigure(0, weight=1, uniform="action")
        self.actions.columnconfigure(1, weight=1, uniform="action")
        self.browse_button = self._action_button(self.actions, self._text("browse"), self.browse)
        self.start_button = self._action_button(self.actions, self._text("start"), self.start)
        self.browse_button.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.start_button.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        self.status_panel = tk.Frame(self.window, padx=12, pady=8)
        self.status_panel.grid(row=4, column=0, sticky="nsew", padx=16, pady=(0, 8))
        self.status_panel.columnconfigure(0, weight=1)
        self.status_panel.rowconfigure(0, weight=1)
        self.status_label = tk.Label(
            self.status_panel,
            textvariable=self.status_value,
            font=self.font,
            justify="left",
            anchor="nw",
        )
        self.status_label.grid(row=0, column=0, sticky="nsew")

        self.settings_button = self._action_button(self.window, self._text("settings"), self.open_settings)
        self.settings_button.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 12))

    def _close(self) -> None:
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
        if self._fitting:
            return
        width = max(self.window.winfo_width(), 1)
        height = max(self.window.winfo_height(), 1)
        if width < 2:
            return
        self._fitting = True
        try:
            scale = max(0.9, min(width / 720, 1.45))
            self.font.configure(size=max(11, round(12 * scale)))
            self.title_font.configure(size=max(12, round(18 * scale)))
            band = max(34, round(40 * scale))
            for button in (self.language_button, *self.theme_buttons.values(), self.browse_button, self.start_button, self.settings_button):
                button.configure(pady=max(6, round(8 * scale)))
            self.choices.rowconfigure(0, minsize=band)
            self.actions.rowconfigure(0, minsize=band)
            self._place_choices(width)
            self.window.update_idletasks()
            entry_gap = max(0, self.browse_button.winfo_reqheight() - self.path_entry.winfo_reqheight())
            self.path_entry.grid_configure(ipady=entry_gap // 2)
            self.window.rowconfigure(2, minsize=self.browse_button.winfo_reqheight())
            inner = max(160, width - 32)
            # Never split the product name through the middle.  The title font
            # shrinks first, then its measured width becomes the resize floor.
            self.title_label.configure(wraplength=0)
            self.status_label.configure(wraplength=max(120, inner - 24))
            self.window.update_idletasks()
            status_h = self.status_label.winfo_reqheight() + 24
            self.window.rowconfigure(4, minsize=status_h)
            needed_h = (
                self.title_label.winfo_reqheight()
                + self.choices.winfo_reqheight()
                + self.path_entry.winfo_reqheight()
                + self.actions.winfo_reqheight()
                + status_h
                + self.settings_button.winfo_reqheight()
                + 64
            )
            title_floor = self.title_font.measure("GameArchiveManager") + 32
            button_floor = max(
                self.font.measure(self._text("language")) + 32,
                max(self.font.measure(self._text(key)) + 28 for key in THEME_LABELS),
                self.font.measure(self._text("browse")) + self.font.measure(self._text("start")) + 44,
            )
            self.window.minsize(max(320, title_floor, button_floor), needed_h)

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
        else:
            self.status_value.set(self._text("choose"))
        self.apply_language()

    def apply_language(self) -> None:
        self.language_button.configure(text=self._text("language"))
        for key, button in self.theme_buttons.items():
            button.configure(text=self._text(key))
        self.browse_button.configure(text=self._text("browse"))
        self.start_button.configure(text=self._text("start"))
        self.settings_button.configure(text=self._text("settings"))
        self._place_choices(self.window.winfo_width())

    def apply_theme(self) -> None:
        colors = theme.palette(theme.resolved_appearance(self.theme_mode.get()))
        self.window.configure(background=colors["bg"])
        for surface in self._surfaces:
            surface.configure(background=colors["bg"])
        for label in self._labels:
            label.configure(background=colors["bg"], foreground=colors["fg"])
        self.status_panel.configure(background=colors["surface"])
        self.status_label.configure(background=colors["surface"], foreground=colors["fg"])
        self.path_entry.configure(
            background=colors["entry_bg"],
            foreground=colors["fg"],
            insertbackground=colors["fg"],
            highlightthickness=1,
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
        )
        for key, button in self.theme_buttons.items():
            selected = key == self.theme_mode.get()
            button.configure(
                background=colors["accent"] if selected else colors["surface"],
                foreground=colors["accent_fg"] if selected else colors["fg"],
                activebackground=colors["accent"],
                activeforeground=colors["accent_fg"],
                highlightthickness=2,
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
            )
        for button in (self.language_button, self.browse_button, self.settings_button):
            button.configure(
                background=colors["surface"],
                foreground=colors["fg"],
                activebackground=colors["accent"],
                activeforeground=colors["accent_fg"],
                highlightthickness=2,
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
            )
        self.start_button.configure(
            background=colors["accent"],
            foreground="#ffffff",
            activebackground=colors["accent"],
            activeforeground=colors["accent_fg"],
            highlightthickness=2,
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
        )

    def browse(self) -> None:
        path = filedialog.askopenfilename(title=self._text("select_archive")) or filedialog.askdirectory(title=self._text("select_folder"))
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
        self.start_button.configure(state="disabled")
        self.status_value.set(self._text("preparing"))
        threading.Thread(target=self._run_task, args=(path,), daemon=True).start()

    def _run_task(self, path: str) -> None:
        try:
            report = GameArchiveService().execute_task(
                path,
                progress_callback=self._progress,
                manual_password_callback=self._request_manual_password,
            )
            self.window.after(0, self._finish, report)
        except Exception as error:
            self.window.after(0, self._fail, "APPLICATION", f"{type(error).__name__}: {error}")

    def _progress(self, update) -> None:
        phase = getattr(getattr(update, "phase", None), "value", getattr(update, "phase", "PROCESSING"))
        archive = getattr(update, "current_archive", None)
        message = self._text("processing", phase=phase, suffix=f": {archive}" if archive else "…")
        self.window.after(0, self.status_value.set, message)

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

    def _finish(self, report) -> None:
        self.running = False
        self.start_button.configure(state="normal")
        if getattr(report, "failed_count", 0):
            detail = next(iter(getattr(report, "failure_details", [])), None)
            stage = getattr(detail, "stage", "UNKNOWN")
            reason = getattr(detail, "reason", getattr(report, "summary", "任务失败"))
            self._fail(stage, reason)
            return
        self.status_value.set(self._text("completed"))

    def _fail(self, stage: str, reason: str) -> None:
        self.running = False
        self.start_button.configure(state="normal")
        self.status_value.set(self._text("failed", stage=stage, reason=reason))

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

        form = settings_panel.build(
            holder, self.config_path, colors, on_theme=on_theme,
            language=self.ui_language.get(), on_language=on_language,
        )
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
