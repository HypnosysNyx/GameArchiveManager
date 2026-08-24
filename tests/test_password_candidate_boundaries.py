"""INITIAL_SCAN password-candidate source boundary regressions."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from application.app_service import GameArchiveService
from cleanup.models import ResidualInternalDirectory
from password.manager import PasswordManager
from password.models import PasswordSource
from scanner.archive_finder import ArchiveFinder, ArchiveScanMode
from scanner.initial_scan_boundary import InitialScanClassification
from task.models import Task
from task.task_analyzer import TaskAnalyzer


class StaticHistoryStorage:
    """Small read-only history provider used to express ownership context."""

    def __init__(self, task_root: Path, technical_roots: list[Path]) -> None:
        self.task_root = task_root
        self.technical_roots = technical_roots

    def read_all(self):
        return [
            SimpleNamespace(
                task_path=self.task_root,
                residual_internal_directories=[
                    ResidualInternalDirectory(path=path)
                    for path in self.technical_roots
                ],
            )
        ]


class PasswordCandidateBoundaryTests(unittest.TestCase):
    @staticmethod
    def _candidate_sources(analysis) -> set[Path]:
        return {
            candidate.source_path
            for candidate in analysis.password_candidates
            if candidate.source_path is not None
        }

    @staticmethod
    def _zip(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("payload.txt", "payload")

    def test_user_empty_folder_remains_password_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = root / "luoxiang"
            expected.mkdir()

            analysis = TaskAnalyzer(
                history_storage=StaticHistoryStorage(root, [])
            ).analyze(Task(task_path=root))

            self.assertEqual(self._candidate_sources(analysis), {expected.resolve()})

    def test_game_archive_output_empty_folder_is_not_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            excluded = root / "GameArchive_Output" / "wrong_password"
            excluded.mkdir(parents=True)

            analysis = TaskAnalyzer(
                history_storage=StaticHistoryStorage(root, [])
            ).analyze(Task(task_path=root))

            self.assertNotIn(excluded.resolve(), self._candidate_sources(analysis))
            self.assertTrue(excluded.is_dir())

    def test_history_owned_output_excludes_empty_folder_and_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            technical = root / "ordinary_runtime_area"
            empty = technical / "candidate"
            empty.mkdir(parents=True)
            nested_archive = technical / "nested.zip"
            self._zip(nested_archive)

            analysis = TaskAnalyzer(
                history_storage=StaticHistoryStorage(root, [technical])
            ).analyze(Task(task_path=root))

            self.assertNotIn(empty.resolve(), self._candidate_sources(analysis))
            self.assertEqual(analysis.archive_results, [])
            boundary = next(
                item
                for item in analysis.initial_scan_boundaries
                if item.path == technical.resolve()
            )
            self.assertIs(
                boundary.classification,
                InitialScanClassification.TECHNICAL_OUTPUT_BOUNDARY,
            )
            self.assertIn("HISTORICAL_RUNTIME_OWNED_OUTPUT", boundary.reasons)

    def test_password_attempt_inside_owned_output_is_not_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            technical = root / "owned_outer"
            empty = technical / "password_attempt_1" / "candidate"
            empty.mkdir(parents=True)

            analysis = TaskAnalyzer(
                history_storage=StaticHistoryStorage(root, [technical])
            ).analyze(Task(task_path=root))

            self.assertNotIn(empty.resolve(), self._candidate_sources(analysis))

    def test_embedded_runtime_owned_output_is_not_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            technical = root / "embedded_runtime_area"
            empty = technical / "candidate"
            empty.mkdir(parents=True)

            analysis = TaskAnalyzer(
                history_storage=StaticHistoryStorage(root, [technical])
            ).analyze(Task(task_path=root))

            self.assertNotIn(empty.resolve(), self._candidate_sources(analysis))

    def test_similarly_named_user_directory_is_not_blacklisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = root / "my_extracted" / "abc123"
            expected.mkdir(parents=True)

            analysis = TaskAnalyzer(
                history_storage=StaticHistoryStorage(root, [])
            ).analyze(Task(task_path=root))

            self.assertIn(expected.resolve(), self._candidate_sources(analysis))

    def test_repeated_failed_residuals_do_not_grow_candidate_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            real_candidate = root / "luoxiang"
            real_candidate.mkdir()
            technical_roots: list[Path] = []
            observed: list[set[Path]] = []

            for run_number in range(1, 4):
                technical = root / f"run_{run_number}_technical"
                (technical / "password_attempt_1" / "empty").mkdir(
                    parents=True
                )
                technical_roots.append(technical)
                analysis = TaskAnalyzer(
                    history_storage=StaticHistoryStorage(
                        root, technical_roots.copy()
                    )
                ).analyze(Task(task_path=root))
                observed.append(self._candidate_sources(analysis))

            self.assertEqual(
                observed,
                [{real_candidate.resolve()}] * 3,
            )

    def test_boundary_filter_never_deletes_historical_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            technical = root / "owned_runtime_output"
            empty = technical / "empty"
            empty.mkdir(parents=True)

            TaskAnalyzer(
                history_storage=StaticHistoryStorage(root, [technical])
            ).analyze(Task(task_path=root))

            self.assertTrue(technical.is_dir())
            self.assertTrue(empty.is_dir())

    def test_pipeline_scan_still_finds_archive_in_technical_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            technical = Path(temp_dir) / "owned_runtime_output"
            archive = technical / "nested.zip"
            self._zip(archive)

            results = ArchiveFinder().find(
                technical, scan_mode=ArchiveScanMode.PIPELINE_SCAN
            )

            self.assertEqual(
                [item.file_path for item in results], [archive.resolve()]
            )

    def test_explicit_user_password_api_is_unaffected(self) -> None:
        manager = PasswordManager()
        candidate = manager.add_user_password("technical-looking-password")

        self.assertIs(candidate.source, PasswordSource.USER_INPUT)
        self.assertEqual(
            manager.get_candidates_by_priority()[0].password,
            "technical-looking-password",
        )

    def test_application_service_injects_its_history_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            technical = root / "owned_by_custom_history"
            empty = technical / "candidate"
            empty.mkdir(parents=True)
            history = StaticHistoryStorage(root, [technical])
            service = GameArchiveService(history_storage=history)

            analysis = service.task_executor.task_analyzer.analyze(
                Task(task_path=root)
            )

            self.assertIs(
                service.task_executor.task_analyzer.history_storage, history
            )
            self.assertNotIn(empty.resolve(), self._candidate_sources(analysis))


if __name__ == "__main__":
    unittest.main()
