import unittest


class GuiAppImportTests(unittest.TestCase):
    def test_module_imports_without_a_display(self):
        import gui.app

        self.assertEqual(gui.app.THEME_LABELS["auto"], "自动")

    def test_theme_choices_resolve_to_light_or_dark(self):
        from gui.theme import resolved_appearance

        for choice in ("auto", "light", "dark"):
            self.assertIn(resolved_appearance(choice), {"light", "dark"})


if __name__ == "__main__":
    unittest.main()
