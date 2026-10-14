"""Small, embeddable Tkinter form for editing safe application settings."""

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from config.config_loader import ConfigLoader
from password.session_store import SessionPasswordStore


BOOLEAN_FIELDS = ("ignore_android", "ignore_AZ", "ignore_pc")
PATH_FIELDS = ("seven_zip_path", "winrar_path", "lz4_path")
NUMBER_FIELDS = (
    "max_recursive_depth",
    "max_archive_tasks",
    "max_initial_archive_tasks",
    "max_embedded_candidates",
    "max_password_attempts",
    "extraction_timeout_seconds",
    "max_archive_size_mb",
)

LABELS = {
    "ignore_android": "忽略 Android 内容",
    "ignore_AZ": "忽略 AZ 标签内容",
    "ignore_pc": "忽略 PC 标签内容",
    "seven_zip_path": "7-Zip 路径",
    "winrar_path": "WinRAR 路径",
    "lz4_path": "lz4 路径",
    "max_recursive_depth": "最大递归深度",
    "max_archive_tasks": "最大归档任务数",
    "max_initial_archive_tasks": "最大初始归档任务数",
    "max_embedded_candidates": "最大内嵌候选数",
    "max_password_attempts": "最大密码尝试次数",
    "extraction_timeout_seconds": "解压超时（秒）",
    "max_archive_size_mb": "最大归档大小（MB）",
}
LABELS_EN = {
    "ignore_android": "Ignore Android content", "ignore_AZ": "Ignore AZ-tagged content", "ignore_pc": "Ignore PC-tagged content",
    "seven_zip_path": "7-Zip path", "winrar_path": "WinRAR path", "lz4_path": "lz4 path",
    "max_recursive_depth": "Maximum recursion depth", "max_archive_tasks": "Maximum archive tasks",
    "max_initial_archive_tasks": "Maximum initial archive tasks", "max_embedded_candidates": "Maximum embedded candidates",
    "max_password_attempts": "Maximum password attempts", "extraction_timeout_seconds": "Extraction timeout (seconds)",
    "max_archive_size_mb": "Maximum archive size (MB)",
}

TEXT = {
    "zh_CN": {
        "appearance": "外观", "mode": "模式", "language": "语言", "scan_scope": "扫描范围",
        "tools": "解压工具", "password_library": "密码库（一行一个）", "limits": "处理限制",
        "browse": "浏览", "save_unsaved": "设置未保存", "password_save_failed": "密码库无法保存。",
        "saved_title": "设置", "saved": "设置和密码库已保存。", "invalid_appearance": "外观选项不合法，未保存。",
        "auto": "自动", "light": "浅色", "dark": "深色", "zh_CN": "中文", "en": "English",
    },
    "en": {
        "appearance": "Appearance", "mode": "Mode", "language": "Language", "scan_scope": "Scan scope",
        "tools": "Extraction tools", "password_library": "Password library (one per line)", "limits": "Processing limits",
        "browse": "Browse", "save_unsaved": "Settings not saved", "password_save_failed": "Password library could not be saved.",
        "saved_title": "Settings", "saved": "Settings and password library saved.", "invalid_appearance": "Invalid appearance option; settings were not saved.",
        "auto": "Auto", "light": "Light", "dark": "Dark", "zh_CN": "Chinese", "en": "English",
    },
}


def text(language: str, key: str) -> str:
    return TEXT.get(language, TEXT["zh_CN"])[key]


def field_label(language: str, field: str) -> str:
    return (LABELS_EN if language == "en" else LABELS)[field]


def load_form_values(path: str | Path) -> dict[str, object]:
    """Load editable values without creating a Tk window."""
    settings = ConfigLoader(path).load()
    values = {field: getattr(settings, field) for field in BOOLEAN_FIELDS + NUMBER_FIELDS}
    values.update(
        {
            field: "" if getattr(settings, field) is None else str(getattr(settings, field))
            for field in PATH_FIELDS
        }
    )
    values["theme_mode"] = getattr(settings, "theme_mode", "auto")
    values["ui_language"] = getattr(settings, "ui_language", "zh_CN")
    return values


def _normalise_values(values: dict[str, object]) -> tuple[dict[str, object] | None, str | None]:
    validators = ConfigLoader._validators()
    result: dict[str, object] = {}
    for field in BOOLEAN_FIELDS:
        value = values.get(field)
        if type(value) is not bool:
            return None, f"{LABELS[field]} 必须为开关值。"
        result[field] = value
    for field in PATH_FIELDS:
        value = values.get(field, "")
        result[field] = None if value is None or not str(value).strip() else str(value).strip()
    for field in NUMBER_FIELDS:
        value = values.get(field)
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return None, f"{LABELS[field]} 必须是整数，未保存。"
        if not validators[field](number):
            return None, f"{LABELS[field]} 的数值不合法，未保存。"
        result[field] = number
    theme_mode = values.get("theme_mode", "auto")
    if not validators["theme_mode"](theme_mode):
        return None, "外观选项不合法，未保存。"
    result["theme_mode"] = theme_mode
    ui_language = values.get("ui_language", "zh_CN")
    if not validators["ui_language"](ui_language):
        return None, "语言选项不合法，未保存。"
    result["ui_language"] = ui_language
    return result, None


def save_form_values(path: str | Path, values: dict[str, object]) -> str | None:
    """Save form values, returning a Chinese warning instead of corrupting a file."""
    updated, warning = _normalise_values(values)
    if warning:
        return warning

    config_path = Path(path)
    data: dict[str, object] = {}
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "配置文件无法读取，未保存。"
        if not isinstance(loaded, dict):
            return "配置文件格式不正确，未保存。"
        validators = ConfigLoader._validators()
        data = {key: value for key, value in loaded.items() if key in validators and validators[key](value)}

    data.update(updated)
    try:
        config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        return f"配置文件无法保存：{error}"
    return None


def build(
    parent: tk.Misc,
    config_path: str | Path,
    colors: dict[str, str],
    on_theme=None,
    language: str = "zh_CN",
    on_language=None,
) -> tk.Frame:
    """Build a compact settings form. Extra window height must not stretch these rows."""
    return _SettingsForm(parent, config_path, colors, on_theme, language, on_language)


class _SettingsForm(tk.Frame):
    """A left-hand settings navigator with one compact group shown at a time."""

    def __init__(self, parent: tk.Misc, config_path: str | Path, colors: dict[str, str], on_theme, language: str, on_language) -> None:
        super().__init__(parent, bg=colors["bg"])
        self.config_path = config_path
        self.colors = colors
        self._on_theme = on_theme
        self.language = language if language in TEXT else "zh_CN"
        self._on_language = on_language
        self.font = tkfont_from(parent)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self._frames: list[tk.Frame] = [self]
        self._labels: list[tk.Label] = []
        self._field_widgets: dict[str, tk.Widget] = {}
        self._section_titles: dict[str, tk.Label] = {}
        self._checks: list[tk.Checkbutton] = []
        self._entries: list[tk.Entry] = []
        self.browse_buttons: list[tk.Button] = []
        self.theme_buttons: dict[str, tk.Button] = {}
        self.path_entries: list[tk.Entry] = []
        self.number_cells: list[tk.Frame] = []
        self.variables: dict[str, tk.Variable] = {}
        values = load_form_values(config_path)

        self.band = self.font.metrics("linespace") + 12
        self.nav = tk.Frame(self, bg=colors["bg"])
        self.nav.grid(row=0, column=0, sticky="nsw", padx=(12, 8), pady=12)
        self.content = tk.Frame(self, bg=colors["bg"])
        self.content.grid(row=0, column=1, sticky="new", padx=(0, 16), pady=12)
        self.content.columnconfigure(0, weight=1)
        self._frames.extend((self.nav, self.content))
        self._nav_buttons: dict[str, tk.Button] = {}
        self._active_group = "appearance"
        self._groups: dict[str, list[tk.Widget]] = {}
        self._section_title("appearance", 0, (12, 4))
        self.theme_row = tk.Frame(self.content, bg=colors["bg"])
        self.theme_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._frames.append(self.theme_row)
        self.theme_label = self._label(self.theme_row, text(self.language, "mode"))
        theme_value = tk.StringVar(value=str(values["theme_mode"]))
        self.variables["theme_mode"] = theme_value
        self.theme_slots: list[tk.Frame] = []
        for key in ("auto", "light", "dark"):
            slot = self._slot(self.theme_row)
            self.theme_slots.append(slot)
            button = self._button(slot, text(self.language, key), lambda chosen=key: self._pick_theme(chosen))
            button.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.theme_buttons[key] = button

        self.language_row = tk.Frame(self.content, bg=colors["bg"])
        self.language_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._frames.append(self.language_row)
        self.language_label = self._label(self.language_row, text(self.language, "language"))
        language_value = tk.StringVar(value=self.language)
        self.variables["ui_language"] = language_value
        self.language_slots: list[tk.Frame] = []
        self.language_buttons: dict[str, tk.Button] = {}
        for key in ("zh_CN", "en"):
            slot = self._slot(self.language_row)
            self.language_slots.append(slot)
            button = self._button(slot, text(self.language, key), lambda chosen=key: self._pick_language(chosen))
            button.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.language_buttons[key] = button

        self._section_title("scan_scope", 3, (0, 4))
        self.checks = tk.Frame(self.content, bg=colors["bg"])
        self.checks.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._frames.append(self.checks)
        for field in BOOLEAN_FIELDS:
            variable = tk.BooleanVar(value=bool(values[field]))
            self.variables[field] = variable
            check = tk.Checkbutton(
                self.checks,
                text=field_label(self.language, field),
                variable=variable,
                font=self.font,
                anchor="w",
                highlightthickness=0,
                bd=0,
                padx=4,
                pady=0,
            )
            self._checks.append(check)
            self._field_widgets[field] = check

        self._section_title("tools", 5, (0, 4))
        self.path_rows = []
        self.path_labels = []
        self.path_entry_slots = []
        self.path_browse_slots = []
        for index, field in enumerate(PATH_FIELDS):
            variable = tk.StringVar(value=str(values[field]))
            self.variables[field] = variable
            row = tk.Frame(self.content, bg=colors["bg"])
            row.grid(row=6 + index, column=0, sticky="ew", padx=16, pady=(0, 8))
            self._frames.append(row)
            self.path_rows.append(row)
            label = self._label(row, field_label(self.language, field))
            self.path_labels.append(label)
            self._field_widgets[field] = label
            entry_slot = self._slot(row)
            self.path_entry_slots.append(entry_slot)
            entry = self._entry(entry_slot, variable)
            entry.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.path_entries.append(entry)
            browse_slot = self._slot(row)
            self.path_browse_slots.append(browse_slot)
            button = self._button(
                browse_slot,
                text(self.language, "browse"),
                lambda target=variable: target.set(filedialog.askopenfilename() or target.get()),
            )
            button.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.browse_buttons.append(button)

        self.password_store = SessionPasswordStore()
        self._section_title("password_library", 9, (0, 4))
        self.password_library = tk.Frame(self.content, bg=colors["bg"])
        self.password_library.grid(row=9, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._frames.append(self.password_library)
        self.password_library.columnconfigure(0, weight=1)
        self.password_label = self._label(self.password_library, text(self.language, "password_library"))
        self.password_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.password_text = tk.Text(self.password_library, height=5, font=self.font, relief="flat")
        self.password_text.grid(row=1, column=0, sticky="ew")
        self.password_text.insert("1.0", "\n".join(self.password_store.passwords()))

        self._section_title("limits", 10, (0, 4))
        self.numbers = tk.Frame(self.content, bg=colors["bg"])
        self.numbers.grid(row=11, column=0, sticky="ew", padx=16)
        self._frames.append(self.numbers)
        self.number_labels = []
        self.number_slots = []
        for field in NUMBER_FIELDS:
            variable = tk.StringVar(value=str(values[field]))
            self.variables[field] = variable
            cell = tk.Frame(self.numbers, bg=colors["bg"])
            self._frames.append(cell)
            self.number_cells.append(cell)
            label = self._label(cell, field_label(self.language, field))
            self.number_labels.append(label)
            self._field_widgets[field] = label
            slot = self._slot(cell)
            self.number_slots.append(slot)
            self._entry(slot, variable).place(relx=0, rely=0, relwidth=1, relheight=1)
        self._groups = {
            "appearance": [self._section_titles["appearance"], self.theme_row, self.language_row],
            "scan_scope": [self._section_titles["scan_scope"], self.checks],
            "tools": [self._section_titles["tools"], *self.path_rows],
            "password_library": [self._section_titles["password_library"], self.password_library],
            "limits": [self._section_titles["limits"], self.numbers],
        }
        for key in self._groups:
            # The navigation is deliberately shorter than the section heading:
            # "one per line" belongs to the password editor, not its tab.
            button = self._button(self.nav, self._nav_text(key), lambda chosen=key: self._select_group(chosen))
            button.grid(sticky="ew", pady=(0, 4))
            self._nav_buttons[key] = button
        self.apply_colors(colors)
        self.reflow(720)
        self._select_group("appearance")

    def save(self) -> None:
        warning = save_form_values(
            self.config_path,
            {name: variable.get() for name, variable in self.variables.items()},
        )
        parent = self.winfo_toplevel()
        if warning:
            messagebox.showwarning(text(self.language, "save_unsaved"), warning, parent=parent)
        else:
            try:
                self.password_store.replace(self.password_text.get("1.0", "end-1c").splitlines())
            except OSError:
                messagebox.showwarning(text(self.language, "save_unsaved"), text(self.language, "password_save_failed"), parent=parent)
                return
            messagebox.showinfo(text(self.language, "saved_title"), text(self.language, "saved"), parent=parent)

    def reflow(self, width: int) -> None:
        """Keep the visible group compact while its fields absorb extra width."""
        width = max(int(width), 1)
        self.font.configure(size=12)
        self.band = self.font.metrics("linespace") + 12
        for slot in (*self.theme_slots, *self.path_entry_slots, *self.path_browse_slots, *self.number_slots):
            slot.configure(height=self.band)
        for slot in self.language_slots:
            slot.configure(height=self.band)
        label_px = max(self.font.measure(field_label(self.language, field)) for field in NUMBER_FIELDS)
        path_px = max(self.font.measure(field_label(self.language, field)) for field in PATH_FIELDS)
        browse_w = self.font.measure(text(self.language, "browse")) + 28
        nav_width = max(self.font.measure(button.cget("text")) for button in self._nav_buttons.values()) + 32
        compact_nav = width < nav_width + 360
        self._place_navigation(width, compact_nav)
        inner = max(1, width - (32 if compact_nav else nav_width + 36))
        self._place_theme()
        self._place_language()
        self._place_checks(inner)
        for row, label, entry_slot, browse_slot in zip(
            self.path_rows, self.path_labels, self.path_entry_slots, self.path_browse_slots
        ):
            self._place_path(row, label, entry_slot, browse_slot, path_px, browse_w)
        self.numbers.columnconfigure(0, weight=1)
        self.numbers.columnconfigure(1, weight=0)
        for cell in self.number_cells:
            cell.grid_remove()
        for index, (cell, label, slot) in enumerate(zip(self.number_cells, self.number_labels, self.number_slots)):
            cell.grid(row=index, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 8))
            self._place_labeled_entry(cell, label, slot, label_px)
        self.two_columns = False
        self._column_width = label_px
        check_w = max(self.font.measure(check.cget("text")) for check in self._checks) + 36
        # Each active group may set the floor; do not keep a broad hidden group
        # from making a compact selected group unusable.
        active_floor = {
            "appearance": max(260, self.font.measure(text(self.language, "mode")) + 3 * 70),
            "scan_scope": max(260, check_w),
            "tools": path_px + browse_w + 140,
            "password_library": 280,
            "limits": label_px + 188,
        }[self._active_group]
        self.min_width = max(active_floor + (32 if compact_nav else nav_width + 36), 320)

    def preferred_width(self) -> int:
        """A single column wide enough for the label and a long entry."""
        self.font.configure(size=12)
        label_px = max(self.font.measure(field_label(self.language, field)) for field in NUMBER_FIELDS)
        nav_width = max(self.font.measure(button.cget("text")) for button in self._nav_buttons.values()) + 32
        return max(getattr(self, "min_width", 560), nav_width + 36 + label_px + 8 + 360)

    def _nav_text(self, key: str) -> str:
        if key == "password_library":
            return "Password library" if self.language == "en" else "密码库"
        return text(self.language, key)

    def _place_navigation(self, width: int, compact: bool) -> None:
        """Move tabs above the form before a narrow window can crush it."""
        self.nav.grid_remove()
        self.content.grid_remove()
        for button in self._nav_buttons.values():
            button.grid_remove()
        if not compact:
            self.nav.configure(width=max(self.font.measure(button.cget("text")) for button in self._nav_buttons.values()) + 32)
            self.nav.grid(row=0, column=0, sticky="nsw", padx=(12, 8), pady=12)
            self.content.grid(row=0, column=1, sticky="new", padx=(0, 16), pady=12)
            for button in self._nav_buttons.values():
                button.grid(sticky="ew", pady=(0, 4))
            return
        self.nav.configure(width=1)
        self.nav.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        self.content.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        remaining = max(1, width - 24)
        row = column = 0
        used = 0
        for button in self._nav_buttons.values():
            needed = self.font.measure(button.cget("text")) + 28
            if column and used + 8 + needed > remaining:
                row += 1
                column = used = 0
            button.grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0), pady=(0, 4))
            self.nav.columnconfigure(column, weight=1)
            used += (8 if column else 0) + needed
            column += 1

    def _place_theme(self) -> None:
        label = self.theme_label
        for widget in (label, *self.theme_slots):
            widget.grid_remove()
        self.theme_row.columnconfigure(0, weight=0, minsize=self.font.measure(text(self.language, "mode")) + 8)
        label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        for column, slot in enumerate(self.theme_slots, start=1):
            self.theme_row.columnconfigure(column, weight=1, uniform="theme")
            slot.grid(row=0, column=column, sticky="ew", padx=(0 if column == 1 else 8, 0))

    def _place_language(self) -> None:
        for widget in (self.language_label, *self.language_slots):
            widget.grid_remove()
        self.language_row.columnconfigure(0, weight=0, minsize=self.font.measure(text(self.language, "language")) + 8)
        self.language_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        for column, slot in enumerate(self.language_slots, start=1):
            self.language_row.columnconfigure(column, weight=1, uniform="language")
            slot.grid(row=0, column=column, sticky="ew", padx=(0 if column == 1 else 8, 0))

    def _place_checks(self, inner: int) -> None:
        for check in self._checks:
            check.grid_remove()
        widest = max(self.font.measure(check.cget("text")) for check in self._checks) + 36
        side_by_side = inner >= widest * 2 + 8
        for column, check in enumerate(self._checks):
            if side_by_side:
                self.checks.columnconfigure(column, weight=1, uniform="check")
                check.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
            else:
                self.checks.columnconfigure(column, weight=1 if column == 0 else 0, uniform="")
                check.grid(row=column, column=0, columnspan=2, sticky="w", pady=(0 if column == 0 else 4, 0))

    def _place_path(self, row, label, entry_slot, browse_slot, path_px, browse_w) -> None:
        for widget in (label, entry_slot, browse_slot):
            widget.grid_remove()
        browse_slot.configure(width=browse_w)
        row.columnconfigure(0, weight=0, minsize=path_px)
        row.columnconfigure(1, weight=1)
        row.columnconfigure(2, weight=0, minsize=browse_w)
        label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        entry_slot.grid(row=0, column=1, sticky="ew")
        browse_slot.grid(row=0, column=2, sticky="ew", padx=(8, 0))

    def _place_labeled_entry(self, cell, label, slot, label_px) -> None:
        label.grid_remove()
        slot.grid_remove()
        cell.columnconfigure(0, weight=0, minsize=label_px)
        cell.columnconfigure(1, weight=1)
        label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        slot.grid(row=0, column=1, sticky="ew")

    def apply_colors(self, colors: dict[str, str]) -> None:
        self.colors = colors
        for frame in self._frames:
            frame.configure(bg=colors["bg"])
        for label in self._labels:
            label.configure(bg=colors["bg"], fg=colors["fg"])
        for check in self._checks:
            check.configure(
                bg=colors["bg"],
                fg=colors["fg"],
                activebackground=colors["bg"],
                activeforeground=colors["fg"],
                selectcolor=colors["surface"],
                highlightthickness=2,
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
            )
        for entry in self._entries:
            entry.configure(
                bg=colors["entry_bg"],
                fg=colors["fg"],
                insertbackground=colors["fg"],
                highlightthickness=1,
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
                relief="flat",
            )
        self.password_text.configure(
            bg=colors["entry_bg"],
            fg=colors["fg"],
            insertbackground=colors["fg"],
            highlightthickness=1,
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
        )
        selected = self.variables["theme_mode"].get()
        for key, button in self.theme_buttons.items():
            chosen = key == selected
            button.configure(
                bg=colors["accent"] if chosen else colors["surface"],
                fg=colors["accent_fg"] if chosen else colors["fg"],
                activebackground=colors["accent"],
                activeforeground=colors["accent_fg"],
                highlightthickness=2,
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
            )
        for button in (*self.language_buttons.values(), *self.browse_buttons):
            button.configure(
                bg=colors["surface"],
                fg=colors["fg"],
                activebackground=colors["accent"],
                activeforeground=colors["accent_fg"],
                highlightthickness=2,
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
            )
        for key, button in self._nav_buttons.items():
            chosen = key == self._active_group
            button.configure(
                bg=colors["accent"] if chosen else colors["surface"],
                fg=colors["accent_fg"] if chosen else colors["fg"],
                activebackground=colors["accent"],
                activeforeground=colors["accent_fg"],
                highlightthickness=2,
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
            )

    def _pick_theme(self, choice: str) -> None:
        self.variables["theme_mode"].set(choice)
        self.apply_colors(self.colors)
        if self._on_theme is not None:
            self._on_theme(choice)

    def _pick_language(self, choice: str) -> None:
        self.variables["ui_language"].set(choice)
        self.set_language(choice)
        if self._on_language is not None:
            self._on_language(choice)

    def _label(self, parent: tk.Misc, text: str) -> tk.Label:
        label = tk.Label(parent, text=text, font=self.font, anchor="w")
        self._labels.append(label)
        return label

    def _section_title(self, key: str, row: int, pady: tuple[int, int]) -> None:
        title = self._label(self.content, text(self.language, key))
        self._section_titles[key] = title
        title.configure(font=("Segoe UI", 11, "bold"))
        title.grid(row=row, column=0, sticky="w", padx=16, pady=pady)

    def set_language(self, language: str) -> None:
        self.language = language if language in TEXT else "zh_CN"
        self.theme_label.configure(text=text(self.language, "mode"))
        self.language_label.configure(text=text(self.language, "language"))
        for key, title in self._section_titles.items():
            title.configure(text=text(self.language, key))
        for key, button in self._nav_buttons.items():
            button.configure(text=self._nav_text(key))
        for field, widget in self._field_widgets.items():
            widget.configure(text=field_label(self.language, field))
        for key, button in self.theme_buttons.items():
            button.configure(text=text(self.language, key))
        for key, button in self.language_buttons.items():
            button.configure(text=text(self.language, key))
        for button in self.browse_buttons:
            button.configure(text=text(self.language, "browse"))
        self.password_label.configure(text=text(self.language, "password_library"))
        self.reflow(self.winfo_width())

    def _select_group(self, group: str) -> None:
        """Show just one settings group, keeping every existing field available."""
        self._active_group = group
        for widgets in self._groups.values():
            for widget in widgets:
                widget.grid_remove()
        for row, widget in enumerate(self._groups[group]):
            widget.grid(row=row, column=0, sticky="ew" if widget is not self._section_titles.get(group) else "w", padx=0, pady=(0, 8))
        self.apply_colors(self.colors)
        self.event_generate("<<SettingsGroupChanged>>")

    def _entry(self, parent: tk.Misc, variable: tk.StringVar) -> tk.Entry:
        entry = tk.Entry(parent, textvariable=variable, font=self.font, relief="flat")
        self._entries.append(entry)
        return entry

    def _button(self, parent: tk.Misc, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            font=self.font,
            command=command,
            relief="flat",
            bd=0,
            padx=8,
            pady=0,
            highlightthickness=2,
        )

    def _slot(self, parent: tk.Misc) -> tk.Frame:
        slot = tk.Frame(parent, height=self.band, bg=self.colors["bg"])
        slot.grid_propagate(False)
        self._frames.append(slot)
        return slot


def tkfont_from(parent: tk.Misc):
    from tkinter import font as tkfont

    return tkfont.Font(root=parent, family="Segoe UI", size=12)
