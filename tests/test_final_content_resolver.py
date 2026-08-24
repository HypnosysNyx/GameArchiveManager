"""Regression tests separating archive leaves from final user content."""

import tempfile
import unittest
from pathlib import Path

from application.app_service import GameArchiveService
from cleanup.runtime_tracker import register_created_directory
from coordinator.models import CoordinatorResult
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from history.storage import HistoryStorage
from organizer.models import ExtractionOutputSource
from organizer.output_organizer import OutputOrganizer
from task.models import TaskStatus
from task.task_executor import TaskExecutionResult
from tools.models import ToolName


class FinalContentResolverTests(unittest.TestCase):
    def _renpy_game(self, root: Path, executable: str = "DR2.exe") -> None:
        for directory_name in ("game", "lib", "renpy"):
            (root / directory_name).mkdir(parents=True, exist_ok=True)
        (root / executable).write_bytes(b"launcher")
        (root / "game" / "script.rpyc").write_bytes(b"game data")

    def _game_with_saves(self, task: Path):
        physical = task / "PC.rar_extracted" / "PC_extracted"
        logical = physical / "PC"
        game = logical / "PC"
        self._renpy_game(game)
        saves = game / "game" / "saves"
        saves.mkdir()
        sources = [
            ExtractionOutputSource(
                physical,
                task / "PC.rar.lz4",
                depth=0,
                runtime_owned=True,
            )
        ]
        owned = [task / "PC.rar_extracted", physical]
        for index in range(1, 11):
            save = saves / f"auto-{index}-LT1.save"
            save.write_bytes(b"PK\x03\x04original save")
            child_output = saves / f"auto-{index}-LT1_extracted"
            child_output.mkdir()
            for name in (
                "extra_info",
                "json",
                "log",
                "renpy_version",
                "screenshot.png",
                "signatures",
            ):
                (child_output / name).write_bytes(b"metadata")
            sources.append(
                ExtractionOutputSource(
                    child_output,
                    save,
                    depth=1,
                    parent_archive=task / "PC.rar.lz4",
                    runtime_owned=True,
                )
            )
            owned.append(child_output)
        return physical, game, sources, owned

    def test_renpy_parent_wins_while_ten_save_archives_stay_processed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir)
            _, game, sources, owned = self._game_with_saves(task)

            roots, candidates = OutputOrganizer().resolve_and_organize(
                task, sources, owned
            )

            self.assertEqual(len(candidates), 11)
            self.assertEqual(sum(item.is_archive_leaf for item in candidates), 10)
            self.assertEqual(len(roots), 1)
            self.assertEqual(roots[0].final_content_root, game.resolve())
            self.assertEqual(len(candidates[0].suppressed_descendants), 10)
            self.assertTrue((roots[0].final_output_path / "DR2.exe").is_file())
            for index in range(1, 11):
                self.assertTrue(
                    (
                        roots[0].final_output_path
                        / "game"
                        / "saves"
                        / f"auto-{index}-LT1.save"
                    ).is_file()
                )
                self.assertFalse(
                    (
                        roots[0].final_output_path
                        / "game"
                        / "saves"
                        / f"auto-{index}-LT1_extracted"
                    ).exists()
                )

    def test_independent_complete_child_game_is_not_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir)
            parent_output = task / "bundle_extracted"
            parent_game = parent_output / "GameA"
            self._renpy_game(parent_game, "GameA.exe")
            child_archive = parent_game / "bonus.zip"
            child_archive.write_bytes(b"archive")
            child_output = parent_game / "bonus_extracted"
            child_game = child_output / "GameB"
            self._renpy_game(child_game, "GameB.exe")
            sources = [
                ExtractionOutputSource(parent_output, task / "bundle.zip"),
                ExtractionOutputSource(
                    child_output,
                    child_archive,
                    depth=1,
                    parent_archive=task / "bundle.zip",
                ),
            ]

            roots, candidates = OutputOrganizer().resolve_and_organize(
                task, sources, [parent_output, child_output]
            )

            self.assertEqual(len(roots), 2)
            self.assertTrue(all(item.is_final_content for item in candidates))

    def test_child_game_is_selected_when_parent_is_not_game_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir)
            parent = task / "bundle_extracted"
            parent.mkdir()
            (parent / "README.txt").write_text("bundle", encoding="utf-8")
            archive = parent / "game.zip"
            archive.write_bytes(b"archive")
            child = parent / "game_extracted"
            game = child / "Game"
            self._renpy_game(game)

            roots, candidates = OutputOrganizer().resolve_and_organize(
                task,
                [
                    ExtractionOutputSource(parent, task / "bundle.zip"),
                    ExtractionOutputSource(child, archive, depth=1),
                ],
                [parent, child],
            )

            self.assertEqual(len(roots), 1)
            self.assertEqual(roots[0].final_content_root, game.resolve())
            self.assertEqual(candidates[0].selection_status, "NEEDS_USER_SELECTION")

    def test_two_independent_complete_games_return_two_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir)
            sources = []
            for name in ("GameA", "GameB"):
                output = task / f"{name}_extracted"
                game = output / name
                self._renpy_game(game, f"{name}.exe")
                sources.append(
                    ExtractionOutputSource(output, task / f"{name}.zip")
                )

            roots, _ = OutputOrganizer().resolve_and_organize(
                task, sources, [item.physical_output_path for item in sources]
            )

            self.assertEqual({item.final_output_path.name for item in roots}, {"GameA", "GameB"})

    def test_ambiguous_low_confidence_candidates_are_not_chosen(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir)
            sources = []
            for name in ("A", "B"):
                output = task / f"{name}_extracted"
                output.mkdir()
                (output / "payload.bin").write_bytes(b"data")
                sources.append(
                    ExtractionOutputSource(output, task / f"{name}.zip")
                )

            roots, candidates = OutputOrganizer().resolve_and_organize(
                task, sources, [item.physical_output_path for item in sources]
            )

            self.assertEqual(roots, [])
            self.assertTrue(
                all(item.selection_status == "NEEDS_USER_SELECTION" for item in candidates)
            )


class _FailingCopyOrganizer(OutputOrganizer):
    def _copy_candidate(self, candidate, destination) -> None:
        raise OSError("simulated copy failure")


class _OwnedGameExecutor:
    def execute(self, task, **_kwargs):
        output = task.task_path / "game_extracted"
        output.mkdir()
        register_created_directory(output)
        for name in ("game", "lib", "renpy"):
            (output / name).mkdir()
        (output / "game.exe").write_bytes(b"launcher")
        extraction = ExtractionResult(
            True,
            "success",
            output_path=output,
            tool_used=ToolName.SEVEN_ZIP,
            status=ExtractionStatus.SUCCESS,
        )
        coordinator = CoordinatorResult(
            True, task.task_path / "game.zip", extraction_result=extraction
        )
        task.status = TaskStatus.COMPLETED
        return TaskExecutionResult(
            task.task_id,
            task.task_path,
            True,
            coordinator_results=[coordinator],
        )


class FinalContentCopySafetyTests(unittest.TestCase):
    def test_copy_failure_preserves_runtime_owned_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task = root / "task"
            task.mkdir()
            service = GameArchiveService(
                task_executor=_OwnedGameExecutor(),
                output_organizer=_FailingCopyOrganizer(),
                history_storage=HistoryStorage(root / "history.json"),
                log_directory=root / "logs",
            )

            report = service.execute_task(task)

            self.assertEqual(report.failed_count, 1)
            self.assertTrue((task / "game_extracted").is_dir())
            self.assertEqual(
                report.residual_internal_directories[0].status,
                "ORPHANED_TEMP",
            )

    def test_selected_execution_tree_is_persisted_without_file_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task = root / "task"
            task.mkdir()
            storage = HistoryStorage(root / "history.json")
            service = GameArchiveService(
                task_executor=_OwnedGameExecutor(),
                history_storage=storage,
                log_directory=root / "logs",
            )

            report = service.execute_task(task)
            history = storage.read_all()[0]

            self.assertEqual(len(report.final_content_candidates), 1)
            self.assertEqual(len(history.final_content_candidates), 1)
            candidate = history.final_content_candidates[0]
            self.assertTrue(candidate.is_final_content)
            self.assertEqual(candidate.depth, 0)
            self.assertEqual(
                candidate.selection_reason,
                "HIGH_CONFIDENCE_GAME_CONTENT",
            )


if __name__ == "__main__":
    unittest.main()
