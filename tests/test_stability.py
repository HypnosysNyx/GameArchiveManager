"""Stability regression tests for run-owned cleanup and history encoding."""

import json
import os
import stat
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from application.app_service import GameArchiveService
from cleanup.cleanup_manager import CleanupManager
from cleanup.runtime_tracker import register_created_directory
from coordinator.models import CoordinatorResult
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from history.models import TaskHistoryRecord
from history.storage import HistoryStorage
from task.models import TaskStatus
from task.task_executor import TaskExecutionResult
from tools.models import ToolName


class _LifecycleExecutor:
    """Create one run-owned directory and optionally interrupt the task."""

    def __init__(self, outcome: str = "success") -> None:
        self.outcome = outcome

    def execute(self, task, **_kwargs) -> TaskExecutionResult:
        internal = task.task_path / "runtime-session-cache"
        internal.mkdir()
        register_created_directory(internal)
        (internal / "payload.txt").write_text("game", encoding="utf-8")

        if self.outcome == "timeout":
            raise TimeoutError("simulated timeout")
        if self.outcome == "exception":
            raise RuntimeError("simulated exception")

        task.status = TaskStatus.COMPLETED
        extraction = ExtractionResult(
            success=True,
            message="success",
            output_path=internal,
            tool_used=ToolName.SEVEN_ZIP,
            status=ExtractionStatus.SUCCESS,
        )
        coordinator = CoordinatorResult(
            success=True,
            archive_path=task.task_path / "source.zip",
            extraction_result=extraction,
        )
        return TaskExecutionResult(
            task_id=task.task_id,
            task_path=task.task_path,
            success=True,
            coordinator_results=[coordinator],
        )


class RunOwnedDirectoryLifecycleTests(unittest.TestCase):
    def _service(self, root: Path, outcome: str) -> GameArchiveService:
        return GameArchiveService(
            task_executor=_LifecycleExecutor(outcome),
            history_storage=HistoryStorage(root / "history.json"),
            log_directory=root / "logs",
        )

    def test_normal_completion_cleans_only_current_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_root = root / "task"
            task_root.mkdir()
            source = task_root / "source.zip"
            source.write_bytes(b"source archive")
            unknown_history = task_root / "old_extracted"
            unknown_history.mkdir()
            (unknown_history / "keep.txt").write_text("keep", encoding="utf-8")

            report = self._service(root, "success").execute_task(task_root)

            self.assertEqual(report.failed_count, 0)
            self.assertEqual(report.residual_internal_directories, [])
            self.assertFalse((task_root / "runtime-session-cache").exists())
            self.assertTrue(unknown_history.is_dir())
            self.assertEqual(source.read_bytes(), b"source archive")
            self.assertEqual(len(report.output_paths), 1)
            self.assertEqual(
                (report.output_paths[0] / "payload.txt").read_text(
                    encoding="utf-8"
                ),
                "game",
            )

    def test_timeout_retains_and_reports_current_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_root = root / "task"
            task_root.mkdir()
            source = task_root / "source.zip"
            source.write_bytes(b"source archive")

            report = self._service(root, "timeout").execute_task(task_root)

            residual = task_root / "runtime-session-cache"
            self.assertEqual(report.failed_count, 1)
            self.assertTrue(residual.is_dir())
            self.assertEqual(len(report.residual_internal_directories), 1)
            self.assertEqual(
                report.residual_internal_directories[0].status,
                "ORPHANED_TEMP",
            )
            self.assertIn(
                "TimeoutError",
                report.residual_internal_directories[0].reason,
            )
            history = HistoryStorage(root / "history.json").read_all()
            self.assertEqual(
                history[0].residual_internal_directories[0].path,
                residual.resolve(),
            )

            manager = CleanupManager(
                task_root,
                task_root=task_root,
                input_archives=[source],
                protected_paths=[task_root / "GameArchive_Output"],
            )
            candidates = manager.authorize_owned(
                [residual], reason="USER_CONFIRMED"
            )
            self.assertEqual([item.path for item in candidates], [residual.resolve()])
            self.assertTrue(manager.delete(residual))
            self.assertFalse(residual.exists())
            self.assertTrue(source.is_file())

    def test_exception_retains_and_reports_current_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_root = root / "task"
            task_root.mkdir()

            report = self._service(root, "exception").execute_task(task_root)

            residual = task_root / "runtime-session-cache"
            self.assertEqual(report.failed_count, 1)
            self.assertTrue(residual.is_dir())
            self.assertEqual(len(report.residual_internal_directories), 1)
            self.assertIn(
                "RuntimeError",
                report.residual_internal_directories[0].reason,
            )

    def test_explicit_cleanup_handles_readonly_run_owned_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            owned = root / "runtime-session-cache"
            owned.mkdir()
            readonly_file = owned / "readonly.txt"
            readonly_file.write_text("temporary", encoding="utf-8")
            os.chmod(readonly_file, stat.S_IREAD)
            manager = CleanupManager(root, task_root=root)
            manager.authorize_owned([owned], reason="USER_CONFIRMED")

            self.assertTrue(manager.delete(owned))

            self.assertFalse(owned.exists())


class HistoryEncodingTests(unittest.TestCase):
    @staticmethod
    def _record(task_id: str, task_path: Path) -> TaskHistoryRecord:
        now = datetime.now().astimezone()
        return TaskHistoryRecord(
            task_id=task_id,
            task_path=task_path,
            status=TaskStatus.COMPLETED,
            created_time=now,
            completed_time=now,
            success=True,
            summary="中文路径往返成功",
        )

    def test_chinese_paths_round_trip_as_utf8_without_ascii_escaping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_file = Path(temp_dir) / "history.json"
            storage = HistoryStorage(history_file)
            chinese_path = Path(
                r"C:\Users\<redacted>\Desktop\测试游戏3\游戏文件"
            )

            storage.save(self._record("utf8", chinese_path))

            raw = history_file.read_bytes()
            decoded = raw.decode("utf-8")
            self.assertIn("测试游戏3", decoded)
            self.assertNotIn(r"\u6d4b", decoded)
            self.assertEqual(storage.read_all()[0].task_path, chinese_path)

    def test_legacy_gb18030_is_read_without_rewriting_then_backed_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_file = Path(temp_dir) / "history.json"
            now = datetime.now().astimezone().isoformat()
            chinese_path = r"C:\Users\<redacted>\Desktop\测试游戏3\游戏文件"
            legacy_payload = [
                {
                    "task_id": "legacy",
                    "task_path": chinese_path,
                    "status": TaskStatus.COMPLETED.value,
                    "created_time": now,
                    "completed_time": now,
                    "success": True,
                    "summary": "旧中文记录",
                    "output_paths": [],
                }
            ]
            original = json.dumps(
                legacy_payload, ensure_ascii=False, indent=2
            ).encode("gb18030")
            history_file.write_bytes(original)
            storage = HistoryStorage(history_file)

            records = storage.read_all()

            self.assertEqual(records[0].task_path, Path(chinese_path))
            self.assertEqual(history_file.read_bytes(), original)
            storage.save(self._record("new", Path(chinese_path)))
            backup = history_file.with_suffix(".json.legacy.bak")
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(len(storage.read_all()), 2)
            self.assertIn("测试游戏3", history_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
