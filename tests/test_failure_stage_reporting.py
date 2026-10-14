from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from application.app_service import GameArchiveService


class _FailingExecutor:
    def execute(self, task, **arguments):
        arguments["progress_callback"](
            SimpleNamespace(phase=SimpleNamespace(value="SCANNING"))
        )
        raise RuntimeError("scanner unavailable")


class _HistoryStorage:
    def __init__(self):
        self.record = None

    def save(self, record):
        self.record = record


class FailureStageReportingTests(unittest.TestCase):
    def test_exception_uses_active_stage_for_report_and_history(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            history = _HistoryStorage()
            service = GameArchiveService.__new__(GameArchiveService)
            service.settings = SimpleNamespace(
                ignore_android=False,
                ignore_AZ=False,
                delete_archives=False,
                delete_empty_folders=False,
                max_password_attempts=1,
            )
            service.task_executor = _FailingExecutor()
            service.history_storage = history
            service.log_directory = root / "logs"
            service.password_recovery_callback = None

            report = service.execute_task(root)

            self.assertEqual("SCANNING", report.failure_details[0].stage)
            self.assertIn("扫描失败", report.failure_details[0].reason)
            self.assertEqual("SCANNING", history.record.failure_details[0].stage)
            self.assertEqual(
                report.failure_details[0].reason,
                history.record.failure_details[0].reason,
            )


if __name__ == "__main__":
    unittest.main()
