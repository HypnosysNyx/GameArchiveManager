import json
import tempfile
import unittest
from pathlib import Path

from gui.settings_panel import load_form_values, save_form_values


class SettingsPanelTests(unittest.TestCase):
    def test_config_source_snapshot_uses_resolved_path_and_loader_defaults(self):
        import warnings
        from gui import settings_panel

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "active.json"
            for content, expected, state in (
                (None, 10240, "missing"),
                ("{bad", 10240, "invalid"),
                ("[]", 10240, "invalid"),
                (b"\xff", 10240, "invalid"),
                ('{"theme_mode": []}', 10240, "invalid"),
                ('{"max_archive_size_mb": -1}', 10240, "invalid"),
                ('{"max_archive_size_mb": 20480}', 20480, "loaded"),
            ):
                with self.subTest(content=content):
                    if content is not None:
                        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        resolved, values, status = settings_panel.load_form_state(path)
                    self.assertEqual(path.resolve(), resolved)
                    self.assertEqual(expected, values["max_archive_size_mb"])
                    self.assertEqual(state, status)

    def test_active_config_source_and_effective_limit_are_visible(self):
        import tkinter as tk
        from unittest.mock import Mock, patch
        from gui import settings_panel, theme

        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            try:
                path = Path(directory) / "active settings.json"
                path.write_text('{"max_archive_size_mb": 20480}', encoding="utf-8")
                # A different copy's value must not leak into the active form.
                (Path(directory) / "config.json").write_text(
                    '{"max_archive_size_mb": 99999}', encoding="utf-8"
                )
                with patch.object(settings_panel, "SessionPasswordStore", return_value=Mock()):
                    form = settings_panel.build(root, path.parent / "." / path.name, theme.palette("light"))
                form.pack(fill="both", expand=True)
                root.update_idletasks()
                self.assertEqual(str(path.resolve()), form.config_path_entry.get())
                self.assertEqual("readonly", form.config_path_entry.cget("state"))
                self.assertIn("20480", form.config_status_label.cget("text"))
                self.assertNotIn("99999", form.config_status_label.cget("text"))
                for group in form._groups:
                    form._select_group(group)
                    self.assertTrue(form.config_source.winfo_manager())
                form.variables["max_archive_size_mb"].set("40960")
                self.assertIn("20480", form.config_status_label.cget("text"))
                with patch.object(settings_panel.messagebox, "showinfo"):
                    form.save()
                self.assertIn("40960", form.config_status_label.cget("text"))
                form.set_language("en")
                self.assertIn("max_archive_size_mb", form.config_status_label.cget("text"))
                self.assertIn("40960", form.config_status_label.cget("text"))
            finally:
                root.destroy()

    def test_config_fallback_warning_is_visible(self):
        import tkinter as tk
        import warnings
        from unittest.mock import Mock, patch
        from gui import settings_panel, theme

        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            try:
                path = Path(directory) / "active.json"
                for content in (None, "{invalid", "[]", '{"max_archive_size_mb": -1}'):
                    with self.subTest(content=content):
                        if content is not None:
                            path.write_text(content, encoding="utf-8")
                        with warnings.catch_warnings(), patch.object(
                            settings_panel, "SessionPasswordStore", return_value=Mock()
                        ):
                            warnings.simplefilter("ignore", UserWarning)
                            form = settings_panel.build(root, path, theme.palette("light"))
                        self.assertEqual(str(path.resolve()), form.config_path_entry.get())
                        self.assertEqual("10240", form.variables["max_archive_size_mb"].get())
                        self.assertIn("10240", form.config_status_label.cget("text"))
                        self.assertIn("警告", form.config_status_label.cget("text"))
                        self.assertIn("默认", form.config_status_label.cget("text"))
                        form.set_language("en")
                        self.assertIn("Warning", form.config_status_label.cget("text"))
                        self.assertIn("default", form.config_status_label.cget("text"))
                        form.destroy()
            finally:
                root.destroy()

    def test_load_and_save_preserves_valid_non_form_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"max_extracted_files": 12, "theme_mode": "dark"}), encoding="utf-8")
            values = load_form_values(path)
            self.assertEqual("dark", values["theme_mode"])
            self.assertIsNone(save_form_values(path, values))
            self.assertEqual(12, json.loads(path.read_text(encoding="utf-8"))["max_extracted_files"])

    def test_invalid_number_does_not_overwrite_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = '{"max_archive_tasks": 7}'
            path.write_text(original, encoding="utf-8")
            values = load_form_values(path)
            values["max_archive_tasks"] = "not a number"
            self.assertIsNotNone(save_form_values(path, values))
            self.assertEqual(original, path.read_text(encoding="utf-8"))

    def test_pc_filter_and_language_are_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            values = load_form_values(path)
            values["ignore_pc"] = True
            values["ui_language"] = "en"
            self.assertIsNone(save_form_values(path, values))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(saved["ignore_pc"])
            self.assertEqual("en", saved["ui_language"])

    def test_passwords_are_not_rendered_or_rewritten_by_settings_save(self):
        import tkinter as tk
        from unittest.mock import patch

        from gui import settings_panel, theme
        from password.session_store import SessionPasswordStore

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            store = SessionPasswordStore(Path(directory) / "passwords.json")
            store.replace(["fixture-secret"])
            before = store.path.read_bytes()
            root = tk.Tk()
            root.withdraw()
            opened = []
            try:
                with (
                    patch.object(settings_panel, "SessionPasswordStore", return_value=store),
                    patch.object(settings_panel.messagebox, "showinfo"),
                ):
                    form = settings_panel.build(
                        root, config, theme.palette("light"),
                        on_password_library=lambda: opened.append(True),
                    )
                    form.pack(fill="both", expand=True)
                    form._select_group("password_library")
                    root.update_idletasks()
                    self.assertFalse(hasattr(form, "password_text"))
                    self.assertNotIn("fixture-secret", form.password_label.cget("text"))
                    self.assertFalse(form.variables["save_passwords"].get())
                    self.assertFalse(form.variables["auto_try_password"].get())
                    form.manage_password_button.invoke()
                    self.assertEqual([True], opened)
                    form.variables["save_passwords"].set(True)
                    form.variables["auto_try_password"].set(True)
                    form.save()
                    self.assertEqual(before, store.path.read_bytes())
                    settings = settings_panel.load_form_values(config)
                    self.assertTrue(settings["save_passwords"])
                    self.assertTrue(settings["auto_try_password"])
                    form.set_language("en")
                    self.assertIn("Open", form.manage_password_button.cget("text"))
            finally:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
