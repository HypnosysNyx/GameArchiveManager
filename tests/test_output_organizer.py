"""Regression tests for controlled final-content-root selection."""

import tempfile
import unittest
from pathlib import Path

from organizer.models import ExtractionOutputSource
from organizer.output_organizer import OutputOrganizer


class OutputOrganizerRootTests(unittest.TestCase):
    def _organize(
        self, task_root: Path, physical: Path, archive: Path
    ):
        return OutputOrganizer().organize_with_details(
            task_root,
            [ExtractionOutputSource(physical, archive)],
        )[0]

    def test_embedded_and_archive_stem_wrappers_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir)
            physical = task / "PC14191_embedded_extracted_password_attempt_1"
            logical = physical / "PC14191"
            content = logical / "【PC】Hail Dicktator"
            content.mkdir(parents=True)
            (content / "game.exe").write_bytes(b"game")

            result = self._organize(
                task, physical, task / "PC14191_embedded.rar"
            )

            self.assertEqual(result.physical_pipeline_output_path, physical.resolve())
            self.assertEqual(result.logical_output_root, logical.resolve())
            self.assertEqual(result.final_content_root, content.resolve())
            self.assertEqual(
                result.final_output_path,
                (task / "GameArchive_Output" / "【PC】Hail Dicktator").resolve(),
            )
            self.assertTrue((result.final_output_path / "game.exe").is_file())

    def test_normal_archive_removes_only_recorded_output_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir)
            physical = task / "archive_extracted"
            content = physical / "game_folder"
            content.mkdir(parents=True)
            (content / "game.exe").write_bytes(b"game")

            result = self._organize(task, physical, task / "archive.zip")

            self.assertEqual(result.final_content_root, content.resolve())
            self.assertEqual(
                result.final_output_path,
                (task / "GameArchive_Output" / "game_folder").resolve(),
            )

    def test_user_game_data_structure_is_not_recursively_flattened(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir)
            physical = task / "game_extracted"
            game = physical / "Game"
            data = game / "Data"
            data.mkdir(parents=True)
            (data / "asset.bin").write_bytes(b"asset")

            result = self._organize(task, physical, task / "game.zip")

            self.assertEqual(result.final_content_root, game.resolve())
            self.assertTrue(
                (result.final_output_path / "Data" / "asset.bin").is_file()
            )
            self.assertFalse(
                (task / "GameArchive_Output" / "Data").exists()
            )

    def test_multiple_top_level_entries_are_kept_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir)
            physical = task / "game_extracted"
            (physical / "Data").mkdir(parents=True)
            (physical / "game.exe").write_bytes(b"game")
            (physical / "README.txt").write_text("read me", encoding="utf-8")

            result = self._organize(task, physical, task / "game.zip")

            self.assertEqual(result.final_content_root, physical.resolve())
            self.assertEqual(result.final_output_path.name, "game")
            self.assertTrue((result.final_output_path / "game.exe").is_file())
            self.assertTrue((result.final_output_path / "Data").is_dir())
            self.assertTrue((result.final_output_path / "README.txt").is_file())

    def test_repeat_run_uses_unique_final_content_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir)
            physical = task / "PC14191_embedded_extracted"
            content = physical / "PC14191" / "【PC】Hail Dicktator"
            content.mkdir(parents=True)
            (content / "game.exe").write_bytes(b"game")
            source = ExtractionOutputSource(
                physical, task / "PC14191_embedded.rar"
            )
            organizer = OutputOrganizer()

            first = organizer.organize_with_details(task, [source])[0]
            second = organizer.organize_with_details(task, [source])[0]

            self.assertEqual(first.final_output_path.name, "【PC】Hail Dicktator")
            self.assertEqual(second.final_output_path.name, "【PC】Hail Dicktator_2")
            for result in (first, second):
                final_text = str(result.final_output_path).casefold()
                self.assertNotIn("_embedded_extracted", final_text)
                self.assertNotIn("password_attempt", final_text)


if __name__ == "__main__":
    unittest.main()
