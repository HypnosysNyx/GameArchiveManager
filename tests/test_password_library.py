"""Password library UI and persisted-option regression tests.

Only temporary fixture values are used; real profile credentials are untouched.
"""

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from config.config_loader import ConfigLoader
from gui.password_library import (
    PasswordLibraryConflict,
    PasswordLibraryController,
    PasswordLibraryDialog,
)
from gui.settings_panel import load_form_values, save_form_values
from password.session_store import PasswordStoreError, SessionPasswordStore


class PasswordLibraryControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "passwords.json"
        self.controller = PasswordLibraryController(SessionPasswordStore(self.path))

    def test_add_search_edit_delete_survives_restart(self):
        controller = self.controller
        controller.add("中文🔐abc")
        controller.add("Case")
        controller.add("case")
        self.assertEqual([0], controller.matching_indices("ABC"))
        self.assertEqual([1, 2], controller.matching_indices("case"))
        self.assertEqual([0, 1, 2], controller.matching_indices())
        self.assertTrue(controller.edit(0, "新密码✨"))
        self.assertFalse(controller.edit(0, "新密码✨"))
        controller.delete(1)
        self.assertEqual(["新密码✨", "case"], controller.passwords())
        self.assertEqual(
            ["新密码✨", "case"],
            SessionPasswordStore(self.path).passwords(),
        )
        self.assertNotIn("新密码", self.path.read_text(encoding="utf-8"))

    def test_blank_duplicate_and_existing_value_are_safe(self):
        controller = self.controller
        controller.add("only")
        for value in ("", "only"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    controller.add(value)
        controller.add("different")
        with self.assertRaises(ValueError):
            controller.edit(1, "only")
        self.assertEqual(["only", "different"], SessionPasswordStore(self.path).passwords())

    def test_stale_editor_refuses_to_overwrite_new_password(self):
        first = self.controller
        second = PasswordLibraryController(SessionPasswordStore(self.path))
        first.add("external-new")
        with self.assertRaises(PasswordLibraryConflict):
            second.add("would-lose-other-entry")
        self.assertEqual(["external-new"], SessionPasswordStore(self.path).passwords())
        second.refresh()
        second.add("now-valid")
        self.assertEqual(["external-new", "now-valid"], first.store.__class__(self.path).passwords())

    def test_atomic_storage_failure_retains_display_and_disk(self):
        self.controller.add("existing")
        old_bytes = self.path.read_bytes()
        with patch("password.session_store.os.replace", side_effect=OSError("private-input")):
            with self.assertRaises(PasswordStoreError) as raised:
                self.controller.edit(0, "new")
        self.assertNotIn("private-input", str(raised.exception))
        self.assertEqual(["existing"], self.controller.passwords())
        self.assertEqual(old_bytes, self.path.read_bytes())


class PasswordLibraryOptionTests(unittest.TestCase):
    def test_task_executor_passes_auto_try_setting_to_candidate_selection(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        from config.settings import Settings
        from task.models import Task
        from task.task_analyzer import AnalysisStatus, TaskAnalysisResult
        from task.task_executor import TaskExecutor

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = SessionPasswordStore(root / "passwords.json")
            store.replace(["saved-fixture"])
            store.add_verified("verified-session")
            analyzer = Mock()
            analyzer.analyze.side_effect = lambda task: TaskAnalysisResult(
                task_id=task.task_id, task_path=task.task_path,
                analysis_status=AnalysisStatus.COMPLETED,
            )
            relation = Mock()
            relation.resolve.return_value = SimpleNamespace(
                relationships=[], suppressed_paths=[], canonical_archives=[]
            )
            for enabled in (False, True):
                with self.subTest(auto_try=enabled):
                    executor = TaskExecutor(
                        task_analyzer=analyzer,
                        coordinator=Mock(),
                        pipeline_runner=Mock(),
                        input_relationship_resolver=relation,
                        session_password_store=store,
                        settings=Settings(auto_try_password=enabled),
                    )
                    with patch.object(store, "candidates", wraps=store.candidates) as spy:
                        result = executor.execute(Task(task_path=root))
                    self.assertTrue(result.success)
                    spy.assert_called_once_with(include_saved=enabled)

    def test_save_and_load_options_are_real_boolean_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            config_path = Path(folder) / "config.json"
            values = load_form_values(config_path)
            self.assertFalse(values["save_passwords"])
            self.assertFalse(values["auto_try_password"])
            values["save_passwords"] = True
            values["auto_try_password"] = True
            self.assertIsNone(save_form_values(config_path, values))
            settings = ConfigLoader(config_path).load()
            self.assertTrue(settings.save_passwords)
            self.assertTrue(settings.auto_try_password)
            values["save_passwords"] = "yes"
            self.assertIsNotNone(save_form_values(config_path, values))
            self.assertIs(json.loads(config_path.read_text(encoding="utf-8"))["save_passwords"], True)

    def test_verified_password_is_saved_only_when_opted_in(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "passwords.json"
            session = SessionPasswordStore(path)
            session.add_verified("not-persisted")
            self.assertFalse(path.exists())
            self.assertEqual(["not-persisted"], session.verified_passwords())
            auto = SessionPasswordStore(path, persist_verified=True)
            auto.add_verified("verified-and-saved")
            self.assertEqual(["verified-and-saved"], SessionPasswordStore(path).passwords())
            self.assertEqual(["verified-and-saved"], auto.verified_passwords())

    def test_saved_and_session_candidates_are_separately_selectable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "passwords.json"
            store = SessionPasswordStore(path)
            store.replace(["saved-one", "saved-two"])
            store.add_verified("verified-now")
            self.assertEqual(
                ["verified-now"],
                [value.password for value in store.candidates(include_saved=False)],
            )
            self.assertEqual(
                ["verified-now", "saved-one", "saved-two"],
                [value.password for value in store.candidates(include_saved=True)],
            )

    def test_persistence_failure_does_not_erase_session_password(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "passwords.json"
            store = SessionPasswordStore(path, persist_verified=True)
            with patch("password.session_store.os.replace", side_effect=OSError("fixture-secret")):
                store.add_verified("fixture-secret")
            self.assertEqual(["fixture-secret"], store.verified_passwords())
            self.assertNotIn("fixture-secret", store.last_persistence_error or "")
            self.assertFalse(path.exists())


class PasswordLibraryWindowTests(unittest.TestCase):
    def test_dialog_controls_fit_narrow_and_wide_windows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "passwords.json"
            SessionPasswordStore(path).replace(["demo-fixture"])
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("gui.password_library.window_place.geometry_for", return_value="660x510+100+100"),
                    patch("gui.password_library.window_place.remember"),
                    patch("gui.password_library.window_place.restore_maximized"),
                ):
                    editor = PasswordLibraryDialog(root, language="en", store=SessionPasswordStore(path))
                    for width, height in ((420, 420), (660, 510), (1100, 650)):
                        editor.dialog.geometry(f"{width}x{height}+100+100")
                        root.update()
                        # The old 510px dialog collapsed the list and hid the
                        # secondary actions at Windows DPI scaling.
                        self.assertGreaterEqual(editor.listbox.winfo_height(), 120)
                        self.assertGreater(
                            editor.list_panel.winfo_height(),
                            editor.search_panel.winfo_height(),
                        )
                        self.assertGreaterEqual(
                            editor.search_check.winfo_rooty(),
                            editor.search_entry.winfo_rooty() + editor.search_entry.winfo_height(),
                        )
                        self.assertTrue(editor._buttons["copy"].winfo_ismapped())
                        self.assertTrue(editor._buttons["reveal"].winfo_ismapped())
                        for widget in (
                            editor.search_entry, editor.listbox, editor.detail_label,
                            editor._buttons["delete"], editor._buttons["reveal"],
                            editor._buttons["close"],
                        ):
                            # Compare Tk widget coordinates within their
                            # own hierarchy, not asynchronous screen positions.
                            left = top = 0
                            node = widget
                            while node is not editor.dialog:
                                left += node.winfo_x()
                                top += node.winfo_y()
                                node = node.master
                            self.assertGreaterEqual(left, 0, widget)
                            self.assertGreaterEqual(top, 0, widget)
                            self.assertLessEqual(
                                left + widget.winfo_width(), editor.dialog.winfo_width() + 2, widget
                            )
                            self.assertLessEqual(
                                top + widget.winfo_height(), editor.dialog.winfo_height() + 2, widget
                            )
                    editor.close()
            finally:
                root.destroy()

    def test_empty_library_has_visible_placeholder(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "passwords.json"
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("gui.password_library.window_place.geometry_for", return_value="740x750+100+100"),
                    patch("gui.password_library.window_place.remember"),
                    patch("gui.password_library.window_place.restore_maximized"),
                ):
                    editor = PasswordLibraryDialog(
                        root, store=SessionPasswordStore(path)
                    )
                    root.update()
                    self.assertTrue(editor.empty_label.winfo_ismapped())
                    self.assertIn("新增", editor.empty_label.cget("text"))
                    self.assertGreaterEqual(editor.listbox.winfo_height(), 120)
                    self.assertEqual("•", editor.search_entry.cget("show"))
                    editor.close()
            finally:
                root.destroy()

    def test_offscreen_saved_position_is_clamped_to_monitor(self):
        from gui.window_place import fully_visible_geometry, _on_screen

        root = tk.Tk()
        root.withdraw()
        try:
            result = fully_visible_geometry(
                root, "740x760+99999+99999"
            )
            self.assertRegex(result, r"^740x760[+-][0-9]+[+-][0-9]+$")
            self.assertNotIn("99999", result)
            # Clamping must not change shared Win32 argtypes such that
            # the existing window-position check starts raising TypeError.
            self.assertTrue(_on_screen(100, 100))
        finally:
            root.destroy()

    def test_add_password_dialog_is_masked_and_not_cramped(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "passwords.json"
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("gui.password_library.window_place.geometry_for", return_value="740x760+100+100"),
                    patch("gui.password_library.window_place.remember"),
                    patch("gui.password_library.window_place.restore_maximized"),
                ):
                    editor = PasswordLibraryDialog(root, store=SessionPasswordStore(path))
                    observed = {}

                    def inspect() -> None:
                        dialogs = [
                            child for child in editor.dialog.winfo_children()
                            if isinstance(child, tk.Toplevel)
                        ]
                        if not dialogs:
                            return
                        popup = dialogs[0]
                        fields = [
                            child for child in popup.winfo_children()
                            if isinstance(child, tk.Entry)
                        ]
                        observed["width"] = popup.winfo_width()
                        observed["height"] = popup.winfo_height()
                        observed["masked"] = fields[0].cget("show")
                        popup.destroy()

                    root.after(100, inspect)
                    self.assertIsNone(editor._ask_password("add_title"))
                    self.assertGreaterEqual(observed["width"], 490)
                    self.assertGreaterEqual(observed["height"], 230)
                    self.assertEqual("•", observed["masked"])
                    editor.close()
            finally:
                root.destroy()

    def test_masked_list_reveal_and_live_search_use_fixture_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "passwords.json"
            store = SessionPasswordStore(path)
            store.replace(["demo-私密-1", "second-demo"])
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("gui.password_library.window_place.geometry_for", return_value="660x510+100+100"),
                    patch("gui.password_library.window_place.remember"),
                    patch("gui.password_library.window_place.restore_maximized"),
                ):
                    editor = PasswordLibraryDialog(root, store=store)
                    root.update_idletasks()
                    self.assertEqual(2, editor.listbox.size())
                    self.assertTrue(all("demo" not in editor.listbox.get(i) for i in range(2)))
                    self.assertEqual("•", editor.search_entry.cget("show"))
                    editor.listbox.selection_set(0)
                    editor.toggle_reveal()
                    self.assertEqual("demo-私密-1", editor.detail_value.get())
                    editor.search_value.set("SECOND")
                    self.assertNotIn("demo-私密-1", editor.detail_value.get())
                    self.assertEqual(1, editor.listbox.size())
                    editor.set_language("en")
                    editor.apply_colors({
                        "bg": "#1e1e1e", "fg": "#f2f2f2", "muted": "#bbbbbb",
                        "surface": "#2a2a2a", "entry_bg": "#141414",
                        "accent": "#4cc2ff", "accent_fg": "#06202b", "border": "#3a3a3a",
                    })
                    self.assertIn("password", editor.dialog.title().lower())
                    self.assertEqual("•", editor.search_entry.cget("show"))
                    editor.close()
            finally:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
