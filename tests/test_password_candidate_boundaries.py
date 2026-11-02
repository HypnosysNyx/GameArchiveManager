"""INITIAL_SCAN password-candidate source boundary regressions."""

from __future__ import annotations

import tempfile
import os
import stat
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from application.app_service import GameArchiveService
from cleanup.models import ResidualInternalDirectory
from config.settings import Settings
from coordinator.extraction_coordinator import ExtractionCoordinator
from extractor.extractor_models import ExtractionStatus
from history.storage import HistoryStorage
from password.manager import PasswordManager
from password.models import PasswordSource
from scanner.archive_finder import ArchiveFinder, ArchiveScanMode
from scanner.initial_scan_boundary import InitialScanClassification
from task.models import Task
from task.task_analyzer import TaskAnalyzer
from task.task_executor import TaskExecutor
from tests.test_beta_integration import ControlledPasswordExtractor


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


class SyntheticPayloadExtractor(ControlledPasswordExtractor):
    """Materialize a tiny output after the fake tool accepts its password."""

    def extract(self, plan, password=None):
        result = super().extract(plan, password)
        if result.status is ExtractionStatus.SUCCESS:
            plan.output_path.mkdir(parents=True)
            (plan.output_path / "payload.txt").write_text("synthetic payload")
        return result


class PasswordCandidateBoundaryTests(unittest.TestCase):
    def _analyze_file(self, archive: Path, task_root: Path | None = None):
        return TaskAnalyzer(
            history_storage=StaticHistoryStorage(archive.parent, [])
        ).analyze(Task(
            task_path=task_root if task_root is not None else archive,
            explicit_archive_path=archive if task_root is not None else None,
        ))

    def test_explicit_file_collects_empty_siblings_once_in_sorted_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "selected.zip"
            self._zip(archive)
            for name in ("z-synthetic", "a-synthetic", "game.zip"):
                (root / name).mkdir()
            self._zip(root / "unselected.zip")

            for unused in range(2):
                analysis = self._analyze_file(archive)
                self.assertEqual(
                    [c.password for c in analysis.password_candidates],
                    ["a-synthetic", "game.zip", "z-synthetic"],
                )
                self.assertTrue(all(c.source is PasswordSource.FOLDER_NAME
                                    for c in analysis.password_candidates))
                self.assertEqual([a.file_path for a in analysis.archive_results],
                                 [archive.resolve()])
                self.assertEqual(analysis.initial_scan_visited_directory_count, 0)

    def test_parent_with_explicit_archive_uses_archive_adjacent_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "selected" / "archive.zip"
            self._zip(archive)
            expected = archive.parent / "synthetic-code"
            expected.mkdir()
            (root / "outside-selection").mkdir()
            analysis = self._analyze_file(archive, root)
            self.assertEqual(self._candidate_sources(analysis), {expected.resolve()})

    def test_explicit_file_excludes_nonempty_sibling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "archive.zip"
            self._zip(archive)
            expected = root / "synthetic-code"
            expected.mkdir()
            occupied = root / "occupied"
            occupied.mkdir()
            (occupied / "file.txt").write_text("synthetic")
            self.assertEqual(self._candidate_sources(self._analyze_file(archive)),
                             {expected.resolve()})

    def test_explicit_file_does_not_descend_into_nested_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "archive.zip"
            self._zip(archive)
            expected = root / "synthetic-code"
            expected.mkdir()
            output = root / "GameArchive_Output"
            nested = output / "nested" / "empty"
            nested.mkdir(parents=True)
            original = os.scandir
            visited = []
            def bounded_scandir(path):
                visited.append(Path(path))
                self.assertNotIn(Path(path), (output / "nested", nested))
                return original(path)
            with patch("os.scandir", side_effect=bounded_scandir):
                analysis = self._analyze_file(archive)
            self.assertEqual(self._candidate_sources(analysis), {expected.resolve()})
            self.assertEqual(set(visited), {root, expected, output})

    def test_explicit_file_excludes_symlinked_empty_sibling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "input" / "archive.zip"
            self._zip(archive)
            expected = archive.parent / "synthetic-code"
            expected.mkdir()
            target = root / "external-empty"
            target.mkdir()
            link = archive.parent / "linked-code"
            # Symlink creation requires a privilege on Windows; model only
            # its no-follow metadata, keeping the real directory scan intact.
            link.mkdir()
            original = Path.lstat
            def link_metadata(path, *args, **kwargs):
                if path == link:
                    return SimpleNamespace(st_mode=stat.S_IFLNK,
                                           st_file_attributes=0)
                return original(path, *args, **kwargs)
            with patch.object(Path, "lstat", link_metadata):
                analysis = self._analyze_file(archive)
            self.assertEqual(self._candidate_sources(analysis), {expected.resolve()})

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_explicit_file_excludes_junction_empty_sibling(self):
        import _winapi
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "input" / "archive.zip"
            self._zip(archive)
            expected = archive.parent / "synthetic-code"
            expected.mkdir()
            target = root / "external-empty"
            target.mkdir()
            link = archive.parent / "junction-code"
            _winapi.CreateJunction(str(target), str(link))
            try:
                analysis = self._analyze_file(archive)
                self.assertEqual(self._candidate_sources(analysis), {expected.resolve()})
            finally:
                link.rmdir()

    def test_explicit_file_candidates_drive_executor_retry_with_budget(self):
        # Real analysis, executor, pipeline and recovery; only the tool is fake.
        for budget in (0, 1):
            with self.subTest(budget=budget), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                archive = root / "input" / "archive.zip"
                self._zip(archive)
                (archive.parent / "synthetic-code").mkdir()
                original_archive = archive.read_bytes()
                extractor = SyntheticPayloadExtractor("synthetic-code")
                settings = Settings(max_password_attempts=budget,
                                    auto_try_password=False, save_passwords=False)
                history = HistoryStorage(root / "history.json")
                executor = TaskExecutor(
                    task_analyzer=TaskAnalyzer(history_storage=history, settings=settings),
                    coordinator=ExtractionCoordinator(extractor=extractor, settings=settings),
                    settings=settings,
                )
                service = GameArchiveService(
                    settings=settings, task_executor=executor,
                    history_storage=history, log_directory=root / "logs",
                )
                report = service.execute_task(archive)
                self.assertEqual(extractor.attempted_passwords,
                                 [None] if budget == 0 else [None, "synthetic-code"])
                self.assertEqual(report.password_attempt_count, budget)
                self.assertEqual(report.success_count, budget)
                self.assertEqual(report.failed_count, 1 - budget)
                self.assertEqual(archive.read_bytes(), original_archive)

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
