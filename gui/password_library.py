"""Private, individually editable password library for the Tk desktop app.

The list never contains plaintext passwords. Only a deliberate reveal or
clipboard action exposes the selected value.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from gui import window_place
from password.session_store import PasswordStoreError, SessionPasswordStore


class PasswordLibraryConflict(ValueError):
    """Another window changed the encrypted library since it was opened."""


class PasswordLibraryController:
    """Testable operations, with a re-read before each encrypted write."""

    def __init__(self, store: SessionPasswordStore | None = None) -> None:
        self.store = store if store is not None else SessionPasswordStore()

    def passwords(self) -> list[str]:
        return self.store.passwords()

    def matching_indices(self, query: str = "") -> list[int]:
        needle = query.casefold()
        return [
            index for index, value in enumerate(self.store.passwords())
            if needle in value.casefold()
        ]

    def get(self, index: int) -> str:
        return self.store.passwords()[index]

    def refresh(self) -> None:
        self.store = SessionPasswordStore(self.store.path)

    def _write(self, updated: list[str]) -> None:
        # Prevent stale editor instances from silently undoing each other.
        current = SessionPasswordStore(self.store.path)
        if current.passwords() != self.store.passwords():
            raise PasswordLibraryConflict(
                "密码库已在其他窗口修改，请刷新后重试。"
            )
        current.replace(updated)
        self.store = current

    def add(self, value: str) -> bool:
        if not value:
            raise ValueError("密码不能为空。")
        values = self.store.passwords()
        if value in values:
            raise ValueError("此密码已经存在，无需重复添加。")
        self._write(values + [value])
        return True

    def edit(self, index: int, value: str) -> bool:
        if not value:
            raise ValueError("密码不能为空。")
        values = self.store.passwords()
        old = values[index]
        if value == old:
            return False
        if value in values:
            raise ValueError("此密码已经存在，无需重复添加。")
        values[index] = value
        self._write(values)
        return True

    def delete(self, index: int) -> None:
        values = self.store.passwords()
        del values[index]
        self._write(values)


LABELS = {
    "zh_CN": {
        "title": "本机密码库",
        "description": "密码由当前 Windows 用户加密保存；每次修改立即保存。",
        "search": "搜索密码",
        "list_title": "已保存的密码",
        "selected_title": "当前选择",
        "empty_library": "还没有保存的密码\n点击「新增」添加第一条",
        "empty_search": "没有匹配的密码",
        "search_show": "显示搜索输入",
        "refresh": "刷新",
        "add": "新增",
        "edit": "编辑",
        "delete": "删除",
        "reveal": "显示所选",
        "hide": "隐藏所选",
        "copy": "复制所选",
        "close": "关闭",
        "hidden": "所选密码：••••••••",
        "no_selection": "请选择一条密码。",
        "count": "已保存 {count} 条 · 当前显示 {shown} 条",
        "success": "密码库已安全保存。",
        "copied": "已复制；20 秒后会尝试清除未变更的剪贴板内容。",
        "confirm_delete": "确定删除这条已保存密码吗？此操作会立即保存。",
        "confirm_title": "确认删除",
        "add_title": "新增密码",
        "edit_title": "编辑密码",
        "password": "密码",
        "show_input": "显示输入",
        "save": "保存",
        "cancel": "取消",
        "error": "密码库操作失败",
        "empty": "请输入非空密码。",
        "reloaded": "已重新读取本机密码库。",
        "unchanged": "密码未改变。",
        "search_note": "仅在本窗口内搜索，不会把搜索内容写入设置或日志。",
    },
    "en": {
        "title": "Local password library",
        "description": "Encrypted for this Windows user. Each change is saved immediately.",
        "search": "Search passwords",
        "list_title": "Saved passwords",
        "selected_title": "Selected entry",
        "empty_library": "No saved passwords yet\nChoose Add to create one",
        "empty_search": "No matching passwords",
        "search_show": "Show search input",
        "refresh": "Refresh",
        "add": "Add",
        "edit": "Edit",
        "delete": "Delete",
        "reveal": "Reveal selected",
        "hide": "Hide selected",
        "copy": "Copy selected",
        "close": "Close",
        "hidden": "Selected password: ••••••••",
        "no_selection": "Select a password first.",
        "count": "{count} saved · {shown} shown",
        "success": "Password library saved securely.",
        "copied": "Copied. Unchanged clipboard will be cleared after 20 seconds.",
        "confirm_delete": "Delete this saved password? The change is saved immediately.",
        "confirm_title": "Confirm deletion",
        "add_title": "Add password",
        "edit_title": "Edit password",
        "password": "Password",
        "show_input": "Show input",
        "save": "Save",
        "cancel": "Cancel",
        "error": "Password library error",
        "empty": "Enter a password.",
        "reloaded": "Password library refreshed.",
        "unchanged": "Password unchanged.",
        "search_note": "Search stays in this window; it is not written to settings or logs.",
    },
}


class PasswordLibraryDialog:
    """A standalone library window; individual secrets stay masked by default."""

    CLIPBOARD_SECONDS = 20

    def __init__(
        self,
        parent: tk.Misc,
        language: str = "zh_CN",
        colors: dict[str, str] | None = None,
        store: SessionPasswordStore | None = None,
        on_changed=None,
    ) -> None:
        from gui import theme

        self.controller = PasswordLibraryController(store)
        self.parent = parent
        self.language = language if language in LABELS else "zh_CN"
        self.colors = colors or theme.palette("light")
        self.on_changed = on_changed
        self._shown_indices: list[int] = []
        self._revealed = False
        self._last_copied: str | None = None
        self._frames: list[tk.Frame] = []
        self._panels: list[tk.Frame] = []
        self._labels: list[tk.Label] = []
        self._buttons: dict[str, tk.Button] = {}
        self.dialog = tk.Toplevel(parent)
        self.dialog.withdraw()
        self.dialog.columnconfigure(0, weight=1)
        self.dialog.rowconfigure(2, weight=1)
        self.search_value = tk.StringVar(master=self.dialog)
        self.search_shown = tk.BooleanVar(master=self.dialog, value=False)
        self.detail_value = tk.StringVar(master=self.dialog)
        self.summary_value = tk.StringVar(master=self.dialog)
        self.status_value = tk.StringVar(master=self.dialog)
        self._build()
        self.set_language(self.language)
        self.apply_colors(self.colors)
        # 510 px cropped the list and secondary actions at Windows DPI scaling.
        # Size the dialog from actual widget requirements, not a fixed guess.
        self.dialog.update_idletasks()
        minimum_width = max(570, self.dialog.winfo_reqwidth())
        minimum_height = max(590, self.dialog.winfo_reqheight() + 28)
        self.dialog.minsize(minimum_width, minimum_height)
        width = max(740, minimum_width)
        height = max(720, minimum_height + 95)
        requested = window_place.geometry_for(
            "password_library", self.dialog, width, height, anchor=parent
        )
        self.dialog.geometry(
            window_place.fully_visible_geometry(self.dialog, requested)
        )
        self.dialog.protocol("WM_DELETE_WINDOW", self.close)
        self.dialog.bind("<Escape>", lambda event: self.close())
        self.dialog.bind("<Unmap>", lambda event: self._hide() if event.widget is self.dialog else None)
        self.dialog.deiconify()
        window_place.restore_maximized("password_library", self.dialog)
        self._render()
        self.search_entry.focus_set()

    def _tr(self, key: str, **kwargs) -> str:
        return LABELS[self.language][key].format(**kwargs)

    @staticmethod
    def _button_colors(colors: dict[str, str]) -> tuple[str, str]:
        """Vault-specific neutral button shades without changing shared palette keys."""
        if colors["bg"].lower() == "#1e1e1e":
            return "#383838", "#474747"
        return "#e5ebf3", "#d8e4f2"

    def _label(self, parent, key: str, *, font=None, muted=False) -> tk.Label:
        label = tk.Label(parent, anchor="w", justify="left", font=font or ("Segoe UI", 10))
        self._labels.append(label)
        label._library_key = key
        label._library_muted = muted
        return label

    def _button(self, parent, key: str, command) -> tk.Button:
        button = tk.Button(
            parent, command=command, font=("Segoe UI", 10), relief="flat",
            padx=10, pady=7, bd=0, highlightthickness=2,
        )
        self._buttons[key] = button
        return button

    def _build(self) -> None:
        """Use distinct cards and give the password list all flexible height."""
        header = tk.Frame(self.dialog)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(14, 8))
        header.columnconfigure(0, weight=1)
        self._frames.append(header)
        title = self._label(header, "title", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")
        self.description = self._label(header, "description", muted=True)
        self.description.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        # Search is its own section. The checkbox never competes for space
        # with the full-width search input.
        self.search_panel = tk.Frame(self.dialog, bd=0, highlightthickness=1)
        self.search_panel.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.search_panel.columnconfigure(0, weight=1)
        self._panels.append(self.search_panel)
        search_label = self._label(
            self.search_panel, "search", font=("Segoe UI", 10, "bold")
        )
        search_label.grid(row=0, column=0, sticky="w", padx=14, pady=(11, 6))
        self.search_entry = tk.Entry(
            self.search_panel, textvariable=self.search_value, show="•",
            font=("Segoe UI", 11), relief="flat", highlightthickness=1,
        )
        self.search_entry.grid(
            row=1, column=0, sticky="ew", padx=14, ipady=4
        )
        self.search_check = tk.Checkbutton(
            self.search_panel, variable=self.search_shown,
            command=self._toggle_search, font=("Segoe UI", 9),
            anchor="w", bd=0, padx=0, pady=2, highlightthickness=1,
        )
        self.search_check.grid(
            row=2, column=0, sticky="w", padx=14, pady=(6, 9)
        )

        # The list is the primary surface and the only row that expands.
        self.list_panel = tk.Frame(self.dialog, bd=0, highlightthickness=1)
        self.list_panel.grid(
            row=2, column=0, sticky="nsew", padx=20, pady=(0, 10)
        )
        self.list_panel.columnconfigure(0, weight=1)
        self.list_panel.rowconfigure(1, weight=1, minsize=140)
        self._panels.append(self.list_panel)
        self.list_title = self._label(
            self.list_panel, "list_title", font=("Segoe UI", 11, "bold")
        )
        self.list_title.grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 8)
        )
        self.summary_label = tk.Label(
            self.list_panel, textvariable=self.summary_value,
            anchor="e", font=("Segoe UI", 9)
        )
        self.summary_label.grid(
            row=0, column=1, sticky="e", padx=(8, 14), pady=(12, 8)
        )
        self.list_panel.columnconfigure(1, weight=0)
        list_frame = tk.Frame(self.list_panel)
        list_frame.grid(
            row=1, column=0, columnspan=2, sticky="nsew",
            padx=14, pady=(0, 12)
        )
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self._panels.append(list_frame)
        self.listbox = tk.Listbox(
            list_frame, height=5, width=18, font=("Consolas", 11),
            relief="flat", bd=0, selectborderwidth=0,
            highlightthickness=1, exportselection=False,
            activestyle="none", selectmode="browse",
        )
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.empty_label = tk.Label(
            list_frame, font=("Segoe UI", 10), justify="center",
            anchor="center", padx=10,
        )

        # A separate selected-item card gives actions a stable location.
        self.selection_panel = tk.Frame(
            self.dialog, bd=0, highlightthickness=1
        )
        self.selection_panel.grid(
            row=3, column=0, sticky="ew", padx=20, pady=(0, 9)
        )
        self.selection_panel.columnconfigure(0, weight=1)
        self._panels.append(self.selection_panel)
        selected_title = self._label(
            self.selection_panel, "selected_title",
            font=("Segoe UI", 10, "bold")
        )
        selected_title.grid(
            row=0, column=0, sticky="w", padx=14, pady=(10, 4)
        )
        self.detail_label = self._label(
            self.selection_panel, "", font=("Segoe UI", 10)
        )
        self.detail_label.configure(textvariable=self.detail_value)
        self.detail_label.grid(
            row=1, column=0, sticky="ew", padx=14, pady=(0, 10)
        )

        # Three primary actions then two secondary actions, with equal widths.
        primary = tk.Frame(self.selection_panel)
        primary.grid(
            row=2, column=0, sticky="ew", padx=14, pady=(0, 6)
        )
        self._panels.append(primary)
        for col, (key, action) in enumerate((
            ("add", self.add),
            ("edit", self.edit),
            ("delete", self.delete),
        )):
            primary.columnconfigure(col, weight=1, uniform="primary")
            self._button(primary, key, action).grid(
                row=0, column=col, sticky="ew",
                padx=(0 if col == 0 else 5, 0),
            )

        secondary = tk.Frame(self.selection_panel)
        secondary.grid(
            row=3, column=0, sticky="ew", padx=14, pady=(0, 12)
        )
        self._panels.append(secondary)
        for col, (key, action) in enumerate((
            ("reveal", self.toggle_reveal),
            ("copy", self.copy_selected),
        )):
            secondary.columnconfigure(col, weight=1, uniform="secondary")
            self._button(secondary, key, action).grid(
                row=0, column=col, sticky="ew",
                padx=(0 if col == 0 else 5, 0),
            )

        # Always-visible bottom bar, independent of list size.
        footer = tk.Frame(self.dialog)
        footer.grid(
            row=4, column=0, sticky="ew", padx=22, pady=(0, 13)
        )
        footer.columnconfigure(0, weight=1)
        self._frames.append(footer)
        self.status_label = tk.Label(
            footer, textvariable=self.status_value, anchor="w",
            font=("Segoe UI", 9), justify="left",
        )
        self.status_label.grid(
            row=0, column=0, sticky="ew", padx=(0, 10)
        )
        self._button(footer, "refresh", self.refresh).grid(
            row=0, column=1, padx=(0, 6)
        )
        self._button(footer, "close", self.close).grid(row=0, column=2)

        self.search_value.trace_add(
            "write", lambda *_: self._render()
        )
        self.listbox.bind(
            "<<ListboxSelect>>", lambda event: self._hide()
        )
        self.listbox.bind(
            "<Double-Button-1>", lambda event: self.edit()
        )
        self.selection_panel.bind(
            "<Configure>",
            lambda event: self.detail_label.configure(
                wraplength=max(180, event.width - 32)
            ),
        )


    def _toggle_search(self) -> None:
        self.search_entry.configure(show="" if self.search_shown.get() else "•")

    def _selected(self) -> int | None:
        selection = self.listbox.curselection()
        if not selection or selection[0] >= len(self._shown_indices):
            return None
        return self._shown_indices[selection[0]]

    def _render(self) -> None:
        self._hide()
        previously_selected = self._selected()
        self._shown_indices = self.controller.matching_indices(self.search_value.get())
        self.listbox.delete(0, tk.END)
        for index in self._shown_indices:
            self.listbox.insert(tk.END, f"{index + 1:03d}    ••••••••")
        if previously_selected in self._shown_indices:
            self.listbox.selection_set(self._shown_indices.index(previously_selected))
        self.summary_value.set(
            self._tr("count", count=len(self.controller.passwords()), shown=len(self._shown_indices))
        )
        if self._shown_indices:
            self.empty_label.place_forget()
        else:
            self.empty_label.configure(
                text=self._tr(
                    "empty_library" if not self.controller.passwords() else "empty_search"
                )
            )
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

    def _hide(self) -> None:
        self._revealed = False
        self.detail_value.set(
            self._tr("hidden" if self._selected() is not None else "no_selection")
        )
        if "reveal" in self._buttons:
            self._buttons["reveal"].configure(text=self._tr("reveal"))

    def _require_selected(self) -> int | None:
        index = self._selected()
        if index is None:
            self.status_value.set(self._tr("no_selection"))
        return index

    def _warn(self, error: Exception) -> None:
        # Errors from the store and controller must never include actual secrets.
        messagebox.showerror(self._tr("error"), str(error), parent=self.dialog)
        self.status_value.set(self._tr("error"))

    def _commit(self, callback) -> bool:
        try:
            callback()
        except (PasswordStoreError, PasswordLibraryConflict, ValueError, IndexError) as error:
            self._warn(error)
            return False
        self._render()
        self.status_value.set(self._tr("success"))
        if self.on_changed is not None:
            self.on_changed()
        return True

    def _ask_password(self, title_key: str, current: str = "") -> str | None:
        edit = tk.Toplevel(self.dialog)
        edit.title(self._tr(title_key))
        edit.configure(bg=self.colors["bg"])
        edit.transient(self.dialog)
        edit.resizable(True, False)
        edit.columnconfigure(0, weight=1)
        tk.Label(
            edit, text=self._tr("password"), bg=self.colors["bg"],
            fg=self.colors["fg"], font=("Segoe UI", 11),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        entry_value = tk.StringVar(master=edit, value=current)
        entry = tk.Entry(
            edit, textvariable=entry_value, show="•",
            bg=self.colors["entry_bg"], fg=self.colors["fg"],
            insertbackground=self.colors["fg"], font=("Segoe UI", 11),
            relief="flat", highlightthickness=1,
            highlightbackground=self.colors["border"], highlightcolor=self.colors["accent"],
        )
        entry.grid(row=1, column=0, sticky="ew", padx=16, ipady=5)
        shown = tk.BooleanVar(master=edit, value=False)
        tk.Checkbutton(
            edit, text=self._tr("show_input"), variable=shown,
            command=lambda: entry.configure(show="" if shown.get() else "•"),
            bg=self.colors["bg"], fg=self.colors["fg"],
            activebackground=self.colors["bg"], activeforeground=self.colors["fg"],
            selectcolor=self.colors["surface"],
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(6, 9))
        buttons = tk.Frame(edit, bg=self.colors["bg"])
        buttons.grid(row=3, column=0, sticky="e", padx=16, pady=(0, 14))
        result: list[str | None] = [None]
        def save() -> None:
            if not entry_value.get():
                messagebox.showwarning(self._tr("error"), self._tr("empty"), parent=edit)
                return
            result[0] = entry_value.get()
            edit.destroy()

        tk.Button(
            buttons, text=self._tr("save"), command=save,
            font=("Segoe UI", 10), relief="flat", bd=0,
            padx=18, pady=8, highlightthickness=2,
            bg=self.colors["accent"], fg=self.colors["accent_fg"],
            activebackground=self.colors["accent"],
            activeforeground=self.colors["accent_fg"],
            highlightbackground=self.colors["border"],
        ).grid(row=0, column=0, padx=(0, 8))
        tk.Button(
            buttons, text=self._tr("cancel"), command=edit.destroy,
            font=("Segoe UI", 10), relief="flat", bd=0,
            padx=18, pady=8, highlightthickness=2,
            bg=self._button_colors(self.colors)[0],
            fg=self.colors["fg"],
            activebackground=self._button_colors(self.colors)[1],
            activeforeground=self.colors["fg"],
            highlightbackground=self.colors["border"],
        ).grid(row=0, column=1)
        edit.bind("<Return>", lambda event: save())
        edit.bind("<Escape>", lambda event: edit.destroy())
        edit.update_idletasks()
        width = max(490, edit.winfo_reqwidth() + 26)
        height = max(230, edit.winfo_reqheight() + 20)
        edit.minsize(390, height)
        left = self.dialog.winfo_rootx() + (self.dialog.winfo_width() - width) // 2
        top = self.dialog.winfo_rooty() + (self.dialog.winfo_height() - height) // 2
        edit.geometry(
            window_place.fully_visible_geometry(
                edit, f"{width}x{height}{left:+d}{top:+d}"
            )
        )
        edit.grab_set()
        entry.focus_set()
        self.dialog.wait_window(edit)
        return result[0]

    def add(self) -> None:
        value = self._ask_password("add_title")
        if value is not None:
            self._commit(lambda: self.controller.add(value))

    def edit(self) -> None:
        index = self._require_selected()
        if index is None:
            return
        value = self._ask_password("edit_title", self.controller.get(index))
        if value is not None:
            if value == self.controller.get(index):
                self.status_value.set(self._tr("unchanged"))
            else:
                self._commit(lambda: self.controller.edit(index, value))

    def delete(self) -> None:
        index = self._require_selected()
        if index is None:
            return
        if messagebox.askyesno(
            self._tr("confirm_title"), self._tr("confirm_delete"), parent=self.dialog
        ):
            self._commit(lambda: self.controller.delete(index))

    def toggle_reveal(self) -> None:
        index = self._require_selected()
        if index is None:
            return
        self._revealed = not self._revealed
        self.detail_value.set(self.controller.get(index) if self._revealed else self._tr("hidden"))
        self._buttons["reveal"].configure(text=self._tr("hide") if self._revealed else self._tr("reveal"))

    def copy_selected(self) -> None:
        index = self._require_selected()
        if index is None:
            return
        value = self.controller.get(index)
        try:
            self.dialog.clipboard_clear()
            self.dialog.clipboard_append(value)
        except tk.TclError:
            self.status_value.set(self._tr("error"))
            return
        self._last_copied = value
        self.dialog.after(self.CLIPBOARD_SECONDS * 1000, lambda: self._clear_clipboard_if_same(value))
        self.status_value.set(self._tr("copied"))

    def _clear_clipboard_if_same(self, value: str) -> None:
        try:
            if self.dialog.clipboard_get() == value:
                self.dialog.clipboard_clear()
        except tk.TclError:
            pass
        if self._last_copied == value:
            self._last_copied = None

    def refresh(self) -> None:
        try:
            self.controller.refresh()
        except PasswordStoreError as error:
            self._warn(error)
            return
        self.search_value.set("")
        self._render()
        self.status_value.set(self._tr("reloaded"))

    def set_language(self, language: str) -> None:
        self.language = language if language in LABELS else "zh_CN"
        self.dialog.title(self._tr("title"))
        for label in self._labels:
            key = getattr(label, "_library_key", None)
            if key:
                label.configure(text=self._tr(key))
        for key, button in self._buttons.items():
            button.configure(text=self._tr(key))
        self.search_check.configure(text=self._tr("search_show"))
        self._hide()
        self._render()

    def apply_colors(self, colors: dict[str, str]) -> None:
        """Apply one theme to every panel, text, list and action control."""
        self.colors = colors
        self.dialog.configure(bg=colors["bg"])
        for frame in self._frames:
            frame.configure(bg=colors["bg"])
        for panel in self._panels:
            panel.configure(bg=colors["surface"])
            if int(panel.cget("highlightthickness")):
                panel.configure(
                    highlightbackground=colors["border"],
                    highlightcolor=colors["border"],
                )
        for label in self._labels:
            on_panel = label.master in self._panels
            label.configure(
                bg=colors["surface"] if on_panel else colors["bg"],
                fg=(
                    colors["muted"]
                    if getattr(label, "_library_muted", False)
                    else colors["fg"]
                ),
            )
        self.summary_label.configure(
            bg=colors["surface"], fg=colors["muted"]
        )
        self.detail_label.configure(
            bg=colors["surface"], fg=colors["fg"]
        )
        self.status_label.configure(bg=colors["bg"], fg=colors["muted"])
        self.empty_label.configure(
            bg=colors["entry_bg"], fg=colors["muted"],
        )
        button_bg, button_hover = self._button_colors(colors)
        for key, button in self._buttons.items():
            primary = key == "add"
            foreground = (
                colors["accent_fg"] if primary
                else colors.get("danger", colors["fg"]) if key == "delete"
                else colors["fg"]
            )
            button.configure(
                bg=(
                    colors["accent"] if primary
                    else button_bg
                ),
                fg=foreground,
                activebackground=(
                    colors["accent"] if primary
                    else button_hover
                ),
                activeforeground=foreground,
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
                cursor="hand2",
            )
        self.listbox.configure(
            bg=colors["entry_bg"], fg=colors["fg"],
            selectbackground=colors["accent"],
            selectforeground=colors["accent_fg"],
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
        )
        self.search_entry.configure(
            bg=colors["entry_bg"], fg=colors["fg"],
            insertbackground=colors["fg"],
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
        )
        self.search_check.configure(
            bg=colors["surface"], fg=colors["fg"],
            activebackground=colors["surface"],
            activeforeground=colors["fg"],
            selectcolor=colors["entry_bg"],
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
        )


    def close(self) -> None:
        if self._last_copied is not None:
            self._clear_clipboard_if_same(self._last_copied)
        self._hide()
        window_place.remember("password_library", self.dialog)
        self.dialog.destroy()
