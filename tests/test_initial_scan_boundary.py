"""INITIAL_SCAN boundary, explicit-input, and task-level guard tests."""

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock

from application.app_service import GameArchiveService
from config.settings import Settings
from history.storage import HistoryStorage
from report.task_report import ReportGenerator
from scanner.archive_finder import ArchiveFinder, ArchiveScanMode
from scanner.initial_scan_boundary import InitialScanClassification
from task.models import Task
from task.task_analyzer import TaskAnalyzer
from task.task_executor import TaskExecutor


class InitialScanBoundaryTests(unittest.TestCase):
    @staticmethod
    def _zip(path: Path, name: str = "payload.txt") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name, "payload")

    def _renpy_game(self, root: Path) -> Path:
        for name in ("game", "lib", "renpy"):
            (root / name).mkdir(parents=True, exist_ok=True)
        (root / "DR2.exe").write_bytes(b"launcher")
        save = root / "game" / "saves" / "auto-1.save"
        self._zip(save)
        return save

    def test_nested_download_archive_is_discovered_without_game_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Download"
            archive = root / "Publisher" / "PC" / "game.7z"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"7z\xbc\xaf\x27\x1c" + b"test")

            finder = ArchiveFinder()
            results = finder.find(root, ArchiveScanMode.INITIAL_SCAN)

            self.assertEqual([item.file_path for item in results], [archive.resolve()])
            self.assertGreaterEqual(
                finder.last_scan_diagnostics.visited_directory_count, 3
            )
            self.assertFalse(
                any(
                    item.classification
                    is InitialScanClassification.GAME_CONTENT_BOUNDARY
                    for item in finder.last_scan_diagnostics.boundaries
                )
            )

    def test_renpy_save_zip_is_pruned_from_initial_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            game = Path(temp_dir) / "PC"
            save = self._renpy_game(game)
            finder = ArchiveFinder()

            results = finder.find(game, ArchiveScanMode.INITIAL_SCAN)

            self.assertEqual(results, [])
            boundary = finder.last_scan_diagnostics.boundaries[0]
            self.assertEqual(boundary.path, game.resolve())
            self.assertIs(
                boundary.classification,
                InitialScanClassification.GAME_CONTENT_BOUNDARY,
            )
            self.assertFalse(boundary.descended)
            self.assertIn("RENPY_GAME_ROOT", boundary.reasons)
            self.assertTrue(save.is_file())

            analysis = TaskAnalyzer().analyze(Task(task_path=game))
            self.assertEqual(1, analysis.file_count)
            self.assertEqual([], analysis.password_candidates)

    def test_explicit_save_archive_overrides_game_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            game = Path(temp_dir) / "PC"
            save = self._renpy_game(game)

            analysis = TaskAnalyzer().analyze(Task(task_path=save))

            self.assertEqual(
                [item.file_path for item in analysis.archive_results],
                [save.resolve()],
            )
            self.assertTrue(analysis.initial_archive_candidates[0].explicit)

    def test_pipeline_scan_still_discovers_zip_inside_game_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            game = Path(temp_dir) / "new_output" / "PC"
            save = self._renpy_game(game)

            results = ArchiveFinder().find(
                game, ArchiveScanMode.PIPELINE_SCAN
            )

            self.assertEqual([item.file_path for item in results], [save.resolve()])

    def test_game_mod_archives_are_pruned_but_download_mods_are_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game = root / "installed_game"
            self._renpy_game(game)
            for index in range(120):
                self._zip(game / "mods" / f"mod-{index}.zip")
            downloads = root / "downloads" / "mods"
            expected = []
            for index in range(4):
                archive = downloads / f"mod-{index}.zip"
                self._zip(archive)
                expected.append(archive.resolve())

            results = ArchiveFinder().find(
                root, ArchiveScanMode.INITIAL_SCAN
            )

            self.assertEqual([item.file_path for item in results], expected)


class InitialArchiveTaskGuardTests(unittest.TestCase):
    @staticmethod
    def _zip(path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("payload.txt", "payload")

    def test_limit_fails_before_any_pipeline_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index in range(3):
                self._zip(root / f"archive-{index}.zip")
            runner = Mock()
            executor = TaskExecutor(
                pipeline_runner=runner,
                settings=Settings(max_initial_archive_tasks=2),
            )

            result = executor.execute(Task(task_path=root))
            report = ReportGenerator().generate(result)

            self.assertFalse(result.success)
            self.assertEqual(
                result.analysis_result.initial_archive_guard.error_type,
                "MAX_INITIAL_ARCHIVE_TASKS",
            )
            self.assertEqual(result.analysis_result.initial_archive_guard.actual, 3)
            self.assertEqual(result.analysis_result.initial_archive_guard.limit, 2)
            runner.run.assert_not_called()
            self.assertEqual(report.failure_details[0].stage, "INITIAL_SCAN_GUARD")

    def test_boundary_and_candidates_are_persisted_in_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game = root / "PC"
            for name in ("game", "lib", "renpy"):
                (game / name).mkdir(parents=True, exist_ok=True)
            (game / "DR2.exe").write_bytes(b"launcher")
            save = game / "game" / "saves" / "auto-1.save"
            save.parent.mkdir()
            self._zip(save)
            downloadable = root / "downloads" / "game.zip"
            downloadable.parent.mkdir()
            self._zip(downloadable)
            second_download = root / "downloads" / "patch.zip"
            self._zip(second_download)
            storage = HistoryStorage(root / "history.json")
            # Trigger the task-level guard so persistence can be tested without
            # invoking an extractor.
            service = GameArchiveService(
                task_executor=TaskExecutor(
                    pipeline_runner=Mock(),
                    settings=Settings(max_initial_archive_tasks=1),
                ),
                history_storage=storage,
                log_directory=root / "logs",
            )

            report = service.execute_task(root)
            history = storage.read_all()[0]

            self.assertGreater(report.initial_scan_visited_directory_count, 0)
            self.assertEqual(len(report.initial_scan_boundaries), 1)
            self.assertEqual(
                history.initial_scan_boundaries[0].classification,
                InitialScanClassification.GAME_CONTENT_BOUNDARY,
            )
            self.assertEqual(
                history.initial_archive_candidates[0].path,
                downloadable.resolve(),
            )


if __name__ == "__main__":
    unittest.main()
