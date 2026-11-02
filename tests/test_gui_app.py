import unittest


class GuiAppImportTests(unittest.TestCase):
    def test_module_imports_without_a_display(self):
        import gui.app

        self.assertEqual(gui.app.THEME_LABELS["auto"], "自动")

    def test_theme_choices_resolve_to_light_or_dark(self):
        from gui.theme import resolved_appearance

        for choice in ("auto", "light", "dark"):
            self.assertIn(resolved_appearance(choice), {"light", "dark"})

    def test_main_window_has_a_standalone_password_library_entry(self):
        import tempfile
        import tkinter as tk
        from pathlib import Path
        from unittest.mock import patch

        from gui import app as module

        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk()
            try:
                with (
                    patch.object(module, "default_config_path", return_value=Path(folder) / "config.json"),
                    patch.object(module.window_place, "geometry_for", return_value="720x520+80+80"),
                    patch.object(module.window_place, "remember"),
                    patch.object(module.window_place, "restore_maximized"),
                    patch.object(module, "PasswordLibraryDialog") as manager,
                ):
                    app = module.GameArchiveApp(root)
                    root.update()
                    self.assertEqual("密码库", app.library_button.cget("text"))
                    self.assertGreater(app.library_button.winfo_width(), 50)
                    app.library_button.invoke()
                    manager.assert_called_once()
                    self.assertEqual("zh_CN", manager.call_args.kwargs["language"])
                    app._choose_language("en")
                    self.assertEqual("Password library", app.library_button.cget("text"))
                    app._choose_theme("dark")
                    self.assertEqual(app.library_button.cget("background"), "#2a2a2a")
            finally:
                if "app" in locals():
                    app._close()
                else:
                    root.destroy()

    def test_main_dashboard_is_compact_and_keeps_actions_and_stages_visible(self):
        import tempfile
        import tkinter as tk
        from pathlib import Path
        from unittest.mock import patch

        from gui import app as module

        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk()
            try:
                with (
                    patch.object(module, "default_config_path", return_value=Path(folder) / "config.json"),
                    patch.object(module.window_place, "geometry_for", return_value="1080x860+100+100"),
                    patch.object(module.window_place, "remember"),
                    patch.object(module.window_place, "restore_maximized"),
                ):
                    app = module.GameArchiveApp(root)
                    root.update()
                    self.assertLessEqual(root.winfo_width(), 900)
                    self.assertLessEqual(root.winfo_height(), 520)
                    self.assertFalse(hasattr(app, "hero_title_label"))
                    self.assertFalse(hasattr(app, "brand_subtitle_label"))
                    root.state("normal")
                    root.geometry("780x500+80+80")
                    root.update()
                    app._fit_to_window()
                    app._update_phase_scrollregion()
                    root.update_idletasks()
                    self.assertFalse(app.phase_scrollbar.winfo_ismapped())
                    self.assertGreaterEqual(app.start_button.winfo_height(), 28)
                    self.assertTrue(app.start_button.winfo_ismapped())
                    self.assertEqual(5, len(app.phase_steps))
                    for phase in app.phase_steps.values():
                        self.assertTrue(phase["row"].winfo_ismapped())
                        self.assertGreaterEqual(phase["row"].winfo_height(), 20)
                    root.geometry("1080x860+80+80")
                    root.update()
                    app._fit_to_window()
                    app._update_phase_scrollregion()
                    root.update_idletasks()
                    self.assertFalse(app.phase_scrollbar.winfo_ismapped())
                    app.path_value.set(r"C:\Temp\SampleGame.zip")
                    root.update_idletasks()
                    self.assertEqual("SampleGame.zip", app.selected_name_value.get())
                    self.assertIn("ZIP", app.input_kind_value.get())
                    self.assertTrue(app.input_kind_label.winfo_ismapped())
                    app._apply_progress("scan", "扫描")
                    self.assertEqual("scan", app._active_phase_key)
                    self.assertEqual("扫描", app.status_value.get())
                    app._choose_language("en")
                    self.assertEqual("Extract", app.start_button.cget("text"))
                    self.assertEqual("Archive", app.browse_button.cget("text"))
            finally:
                if "app" in locals():
                    app._close()
                else:
                    root.destroy()

    def test_bad_password_library_shows_error_instead_of_opening_empty_editor(self):
        from pathlib import Path
        from unittest.mock import Mock, patch

        from gui import app as module
        from password.session_store import PasswordStoreError

        app = module.GameArchiveApp.__new__(module.GameArchiveApp)
        app.window = object()
        app.config_path = Path("unused-config.json")
        app.theme_mode = Mock()
        app.theme_mode.get.return_value = "light"
        app.ui_language = Mock()
        app.ui_language.get.return_value = "zh_CN"
        app.status_value = Mock()

        with (
            patch.object(module.tk, "Toplevel") as dialog,
            patch.object(module.tk, "Frame"),
            patch.object(module.tk, "Canvas"),
            patch.object(module.tk, "Scrollbar"),
            patch.object(module.settings_panel, "build", side_effect=PasswordStoreError("密码库损坏")),
            patch.object(module.messagebox, "showerror") as show_error,
        ):
            app.open_settings()
            dialog.return_value.destroy.assert_called_once()
            show_error.assert_called_once()
            self.assertIs(show_error.call_args.kwargs["parent"], app.window)
            app.status_value.set.assert_called_once_with("密码库损坏")


if __name__ == "__main__":
    unittest.main()
