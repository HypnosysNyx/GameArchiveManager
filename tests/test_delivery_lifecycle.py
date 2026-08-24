"""Regression tests for delivery decisions and run-owned content lifetime."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from application.app_service import GameArchiveService
from cleanup.runtime_tracker import (
    TaskRunDirectoryTracker,
    register_created_directory,
)
from coordinator.models import CoordinatorResult
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from history.storage import HistoryStorage
from task.models import TaskStatus
from task.task_executor import TaskExecutionResult
from tools.models import ToolName


class _TwoIndependentOutputsExecutor:
    """Produce one game and one generic content result from separate inputs."""

    def execute(self, task, **_kwargs):
        pc_output = task.task_path / "pc_extracted"
        android_output = task.task_path / "android_extracted"
        for directory in (pc_output, android_output):
            directory.mkdir()
            register_created_directory(directory)

        for name in ("game", "lib", "renpy"):
            (pc_output / name).mkdir()
        (pc_output / "PC.exe").write_bytes(b"launcher")
        (android_output / "game.apk").write_bytes(b"apk-content")

        results = []
        for archive_name, output in (
            ("PC.rar.lz4", pc_output),
            ("Android.rar.lz4", android_output),
        ):
            extraction = ExtractionResult(
                True,
                "success",
                output_path=output,
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.SUCCESS,
            )
            results.append(
                CoordinatorResult(
                    True,
                    task.task_path / archive_name,
                    extraction_result=extraction,
                )
            )
        task.status = TaskStatus.COMPLETED
        return TaskExecutionResult(
            task.task_id,
            task.task_path,
            True,
            coordinator_results=results,
        )


class _CompetingRootsExecutor:
    """Produce two competing game roots from one archive lineage."""

    def execute(self, task, **_kwargs):
        output = task.task_path / "release_extracted"
        output.mkdir()
        register_created_directory(output)
        for name in ("GameA", "GameB"):
            game = output / name
            (game / f"{name}_Data").mkdir(parents=True)
            (game / f"{name}.exe").write_bytes(b"MZ")
            (game / f"{name}_Data" / "data.bin").write_bytes(name.encode())
        extraction = ExtractionResult(
            True,
            "success",
            output_path=output,
            tool_used=ToolName.SEVEN_ZIP,
            status=ExtractionStatus.SUCCESS,
        )
        coordinator = CoordinatorResult(
            True,
            task.task_path / "release.rar",
            extraction_result=extraction,
        )
        task.status = TaskStatus.COMPLETED
        return TaskExecutionResult(
            task.task_id,
            task.task_path,
            True,
            coordinator_results=[coordinator],
        )


class DeliveryLifecycleTests(unittest.TestCase):
    def _service(self, root: Path, executor) -> GameArchiveService:
        return GameArchiveService(
            task_executor=executor,
            history_storage=HistoryStorage(root / "history.json"),
            log_directory=root / "logs",
        )

    def test_mixed_pc_and_android_are_both_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = root / "task"
            task.mkdir()
            (task / "PC.rar.lz4").write_bytes(b"pc-source")
            (task / "Android.rar.lz4").write_bytes(b"android-source")
            before = {
                path.name: path.read_bytes()
                for path in task.glob("*.lz4")
            }

            report = self._service(
                root, _TwoIndependentOutputsExecutor()
            ).execute_task(task)

            self.assertEqual(report.task_status, TaskStatus.COMPLETED.value)
            self.assertEqual(report.delivery_status, "DELIVERED")
            self.assertEqual(len(report.output_paths), 2)
            delivered_files = {
                path.name
                for output in report.output_paths
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertIn("PC.exe", delivered_files)
            self.assertIn("game.apk", delivered_files)
            self.assertFalse((task / "pc_extracted").exists())
            self.assertFalse((task / "android_extracted").exists())
            self.assertEqual(
                before,
                {path.name: path.read_bytes() for path in task.glob("*.lz4")},
            )

    def test_noninteractive_ambiguous_content_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = root / "task"
            task.mkdir()

            report = self._service(
                root, _CompetingRootsExecutor()
            ).execute_task(task)

            self.assertEqual(
                report.task_status,
                TaskStatus.COMPLETED_NEEDS_SELECTION.value,
            )
            self.assertEqual(report.delivery_status, "NEEDS_USER_SELECTION")
            self.assertEqual(report.output_paths, [])
            self.assertTrue((task / "release_extracted" / "GameA").is_dir())
            self.assertTrue((task / "release_extracted" / "GameB").is_dir())
            self.assertTrue(
                any(
                    item.reason == "ORPHANED_TEMP: DELIVERY_PENDING"
                    for item in report.residual_internal_directories
                )
            )

    def test_user_selects_one_and_explicitly_rejects_other(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = root / "task"
            task.mkdir()
            report = self._service(
                root, _CompetingRootsExecutor()
            ).execute_task(task, content_selection_callback=lambda _units: [0])

            self.assertEqual(report.delivery_status, "DELIVERED")
            self.assertEqual(len(report.output_paths), 1)
            self.assertFalse((task / "release_extracted").exists())
            self.assertTrue(
                any(
                    unit.selection_reason == "USER_REJECTED_DELIVERY_UNIT"
                    for unit in report.delivery_units
                )
            )

    def test_user_selects_all_delivery_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = root / "task"
            task.mkdir()
            report = self._service(
                root, _CompetingRootsExecutor()
            ).execute_task(
                task,
                content_selection_callback=lambda units: list(range(len(units))),
            )

            self.assertEqual(report.delivery_status, "DELIVERED")
            self.assertEqual(len(report.output_paths), 2)
            self.assertFalse((task / "release_extracted").exists())

    def test_pending_content_protects_shared_top_level_owned_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = root / "task"
            task.mkdir()
            owned = task / "shared_extracted"
            delivered = owned / "delivered"
            pending = owned / "pending"
            delivered.mkdir(parents=True)
            pending.mkdir()
            (pending / "content.bin").write_bytes(b"keep")
            tracker = TaskRunDirectoryTracker(task)
            tracker.register(owned)

            service = self._service(root, _TwoIndependentOutputsExecutor())
            residuals = service._cleanup_successful_run(
                task,
                tracker,
                SimpleNamespace(analysis_result=None),
                Mock(),
                preserve_content_paths=[pending],
            )

            self.assertTrue(owned.is_dir())
            self.assertTrue((pending / "content.bin").is_file())
            self.assertEqual(len(residuals), 1)
            self.assertEqual(
                residuals[0].reason,
                "ORPHANED_TEMP: DELIVERY_PENDING",
            )


if __name__ == "__main__":
    unittest.main()
