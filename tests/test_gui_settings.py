import json
import tempfile
import unittest
from pathlib import Path

from gui.settings_panel import load_form_values, save_form_values


class SettingsPanelTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
