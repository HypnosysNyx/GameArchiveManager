import unittest

from gui.theme import palette, resolved_appearance


class ResolvedAppearanceTests(unittest.TestCase):
    def test_explicit_choices_are_preserved(self):
        self.assertEqual("light", resolved_appearance("light"))
        self.assertEqual("dark", resolved_appearance("dark"))

    def test_auto_follows_a_dark_system_preference(self):
        self.assertEqual("dark", resolved_appearance("auto", prefers_dark=True))

    def test_auto_follows_a_light_system_preference(self):
        self.assertEqual("light", resolved_appearance("auto", prefers_dark=False))


class PaletteTests(unittest.TestCase):
    required_keys = {"bg", "fg", "muted", "border", "accent", "accent_fg", "surface", "entry_bg", "corner_radius", "danger", "ok"}

    def test_light_palette_has_all_required_colours(self):
        self.assertEqual(self.required_keys, set(palette("light")))

    def test_dark_palette_has_all_required_colours(self):
        self.assertEqual(self.required_keys, set(palette("dark")))

    def test_light_palette_is_qingkong(self):
        colors = palette("light")
        self.assertEqual("#f3f3f3", colors["bg"])
        self.assertEqual("#0067c0", colors["accent"])
        self.assertEqual("#ffffff", colors["accent_fg"])
        self.assertEqual(8, colors["corner_radius"])

    def test_dark_palette_is_motai(self):
        colors = palette("dark")
        self.assertEqual("#1e1e1e", colors["bg"])
        self.assertEqual("#4cc2ff", colors["accent"])
        self.assertEqual("#06202b", colors["accent_fg"])
        self.assertEqual(4, colors["corner_radius"])


if __name__ == "__main__":
    unittest.main()
