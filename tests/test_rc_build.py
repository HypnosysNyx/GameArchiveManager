"""RC identity and frozen-runtime path regression tests."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from application.app_service import GameArchiveService
from application.runtime_paths import (
    application_directory,
    default_config_path,
    default_history_file,
    default_log_directory,
)
from history.storage import HistoryStorage
from report.models import TaskReport
from task.models import TaskStatus
from task.task_executor import TaskExecutionResult
from tools.models import ToolName
from tools.tool_manager import ToolManager
from version import APP_NAME, APP_VERSION, BUILD_TYPE


class ReleaseBuildTests(unittest.TestCase):
    def test_version_identity_is_consistent_in_report_history_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executor = Mock()

            def execute(task, **_kwargs):
                task.status = TaskStatus.COMPLETED
                return TaskExecutionResult(
                    task_id=task.task_id,
                    task_path=task.task_path,
                    success=True,
                )

            executor.execute.side_effect = execute
            history = HistoryStorage(root / "history.json")
            service = GameArchiveService(
                task_executor=executor,
                history_storage=history,
                log_directory=root / "logs",
            )

            report = service.execute_task(root)

            self.assertEqual(APP_NAME, "GameArchiveManager")
            self.assertEqual(APP_VERSION, "0.1.0")
            self.assertEqual(BUILD_TYPE, "Release")
            self.assertEqual(report.app_version, APP_VERSION)
            self.assertEqual(report.build_type, BUILD_TYPE)
            record = history.read_all()[0]
            self.assertEqual(record.app_version, APP_VERSION)
            self.assertEqual(record.build_type, BUILD_TYPE)
            raw_history = json.loads(
                (root / "history.json").read_text(encoding="utf-8")
            )[0]
            self.assertEqual(raw_history["app_version"], APP_VERSION)
            self.assertEqual(raw_history["build_type"], BUILD_TYPE)
            log_text = next((root / "logs").glob("*.log")).read_text(
                encoding="utf-8"
            )
            self.assertIn(f"version: {APP_VERSION}", log_text)
            self.assertIn(f"build: {BUILD_TYPE}", log_text)

    def test_default_runtime_data_paths_use_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            local_app_data = Path(temp_dir)
            with patch.dict(
                "os.environ", {"LOCALAPPDATA": str(local_app_data)}
            ):
                expected = local_app_data / APP_NAME
                self.assertEqual(default_log_directory(), expected / "logs")
                self.assertEqual(
                    default_history_file(),
                    expected / "history" / "task_history.json",
                )

    def test_frozen_runtime_uses_executable_directory_for_tools_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "GameArchiveManager.exe"
            executable.touch()
            tools_directory = root / "tools"
            tools_directory.mkdir()
            lz4 = tools_directory / "lz4.exe"
            lz4.touch()
            config = root / "config.json"
            config.write_text("{}", encoding="utf-8")

            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "executable", str(executable)
            ):
                self.assertEqual(application_directory(), root.resolve())
                self.assertEqual(default_config_path(), config.resolve())
                manager = ToolManager()

            self.assertEqual(
                manager.get_tool_path(ToolName.LZ4), lz4.resolve()
            )

    def test_task_report_defaults_to_authoritative_identity(self) -> None:
        report = TaskReport(
            task_path=None,
            total_archives=0,
            success_count=0,
            failed_count=0,
            skipped_count=0,
            password_attempt_count=0,
            execution_time=0,
        )
        self.assertEqual(report.app_version, APP_VERSION)
        self.assertEqual(report.build_type, BUILD_TYPE)


if __name__ == "__main__":
    unittest.main()
