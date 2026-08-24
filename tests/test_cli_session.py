"""CLI session-loop and application/task lifetime regression tests."""

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from analyzer.models import ArchiveInfo
from application.app_service import GameArchiveService
from cleanup.runtime_tracker import register_created_directory
from config.settings import Settings
from history.storage import HistoryStorage
from main import CliSessionController
from password.models import PasswordCandidate, PasswordSource
from password.session_store import SessionPasswordStore
from pipeline.models import PipelineResult
from report.models import TaskReport
from task.input_relationship import InputRelationshipResolution
from task.models import Task, TaskStatus
from task.task_analyzer import AnalysisStatus, TaskAnalysisResult
from task.task_executor import TaskExecutionResult, TaskExecutor


class EmptyRelationshipResolver:
    def resolve(self, archives, process_all_inputs=False):
        return InputRelationshipResolution(
            canonical_archives=list(archives)
        )


class PreviewAnalyzer:
    def analyze(self, task):
        return TaskAnalysisResult(
            task_id=task.task_id,
            task_path=task.task_path,
            analysis_status=AnalysisStatus.COMPLETED,
        )


class FakeSessionService:
    def __init__(self, reports):
        self.settings = Settings()
        self.tool_manager = Mock()
        self.task_executor = SimpleNamespace(
            task_analyzer=PreviewAnalyzer(),
            input_relationship_resolver=EmptyRelationshipResolver(),
        )
        self._reports = list(reports)
        self.executed_paths = []

    def execute_task(self, path, progress_callback=None):
        self.executed_paths.append(Path(path))
        return self._reports.pop(0)


def report(path: Path, status: str, *, failed: int = 0) -> TaskReport:
    return TaskReport(
        task_path=path,
        total_archives=1,
        success_count=0 if failed else 1,
        failed_count=failed,
        skipped_count=0,
        password_attempt_count=0,
        execution_time=0.01,
        summary=status,
        task_status=status,
    )


class CliSessionLoopTests(unittest.TestCase):
    def test_main_returns_nonzero_only_for_unrecoverable_initialization_failure(self):
        import main as main_module

        with (
            patch.object(
                main_module,
                "GameArchiveService",
                side_effect=RuntimeError("controlled initialization failure"),
            ),
            patch("sys.stdout", new_callable=StringIO),
        ):
            exit_code = main_module.main()

        self.assertEqual(exit_code, 1)

    def _run_two_tasks(self, first_status: str, second_status: str):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            service = FakeSessionService([
                report(first, first_status, failed=first_status == "FAILED"),
                report(second, second_status, failed=second_status == "FAILED"),
            ])
            inputs = [
                str(first), "Y", "",
                str(second), "Y", "",
                "Q",
            ]
            with (
                patch("builtins.input", side_effect=inputs),
                patch("sys.stdout", new_callable=StringIO) as stdout,
            ):
                controller = CliSessionController(service)
                controller.run_session()
            return service.executed_paths, controller, stdout.getvalue()

    def test_two_successful_tasks_run_in_one_session(self):
        paths, controller, output = self._run_two_tasks(
            "COMPLETED", "COMPLETED"
        )

        self.assertEqual(len(paths), 2)
        self.assertNotEqual(paths[0], paths[1])
        self.assertEqual(controller.last_task_reports[0].task_path, paths[1])
        self.assertIn("输入文件或目录路径直接开始任务", output)

    def test_failed_task_does_not_close_or_poison_session(self):
        paths, controller, _ = self._run_two_tasks("FAILED", "COMPLETED")

        self.assertEqual(len(paths), 2)
        self.assertEqual(
            controller.last_task_reports[0].task_status, "COMPLETED"
        )

    def test_cancelled_task_does_not_exit_application(self):
        paths, controller, _ = self._run_two_tasks(
            "CANCELLED", "COMPLETED"
        )

        self.assertEqual(len(paths), 2)
        self.assertEqual(
            controller.last_task_reports[0].task_status, "COMPLETED"
        )

    def test_blank_and_invalid_task_path_return_to_fast_prompt(self):
        service = FakeSessionService([])
        with (
            patch(
                "builtins.input",
                side_effect=["", "Z:\\missing\\game", "Q"],
            ),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            CliSessionController(service).run_session()

        self.assertEqual(service.executed_paths, [])
        self.assertIn("路径不存在", stdout.getvalue())

    def test_first_input_can_be_an_archive_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "game.rar"
            archive.write_bytes(b"archive")
            service = FakeSessionService([report(archive, "COMPLETED")])
            with (
                patch(
                    "builtins.input",
                    side_effect=[str(archive), "Y", "", "Q"],
                ),
                patch("sys.stdout", new_callable=StringIO),
            ):
                CliSessionController(service).run_session()

            self.assertEqual(service.executed_paths, [archive])

    def test_quoted_drag_drop_path_is_unwrapped_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir) / "Test Game"
            task.mkdir()
            service = FakeSessionService([report(task, "COMPLETED")])
            with (
                patch(
                    "builtins.input",
                    side_effect=[f'"{task}"', "Y", "", "Q"],
                ),
                patch("sys.stdout", new_callable=StringIO),
            ):
                CliSessionController(service).run_session()

            self.assertEqual(service.executed_paths, [task])

    def test_m_opens_full_menu_and_returns_to_fast_prompt(self):
        service = FakeSessionService([])
        with (
            patch("builtins.input", side_effect=["M", "0", "Q"]),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            CliSessionController(service).run_session()

        output = stdout.getvalue()
        self.assertIn("完整菜单", output)
        self.assertIn("0. 返回路径输入", output)
        self.assertEqual(service.executed_paths, [])

    def test_explicit_content_container_file_uses_same_fast_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            apk = Path(temp_dir) / "game.apk"
            apk.write_bytes(b"content-container")
            service = FakeSessionService([report(apk, "COMPLETED")])
            with (
                patch(
                    "builtins.input",
                    side_effect=[str(apk), "Y", "", "Q"],
                ),
                patch("sys.stdout", new_callable=StringIO),
            ):
                CliSessionController(service).run_session()

            self.assertEqual(service.executed_paths, [apk])

    def test_same_path_can_be_submitted_twice_from_fast_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            task = Path(temp_dir) / "task"
            task.mkdir()
            service = FakeSessionService(
                [report(task, "COMPLETED"), report(task, "COMPLETED")]
            )
            with (
                patch(
                    "builtins.input",
                    side_effect=[
                        str(task), "Y", "",
                        str(task), "Y", "",
                        "Q",
                    ],
                ),
                patch("sys.stdout", new_callable=StringIO),
            ):
                CliSessionController(service).run_session()

            self.assertEqual(service.executed_paths, [task, task])


class RecordingTaskExecutor:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.task_ids = []
        self.execution_arguments = []
        self.session_password_store = None

    def execute(self, task, max_password_attempts=None, **kwargs):
        self.task_ids.append(task.task_id)
        self.execution_arguments.append(
            (
                task.settings.ignore_android_az,
                max_password_attempts,
            )
        )
        status = self.statuses.pop(0)
        task.status = status
        return TaskExecutionResult(
            task_id=task.task_id,
            task_path=task.task_path,
            success=status is TaskStatus.COMPLETED,
            cancelled=status is TaskStatus.CANCELLED,
            error_message="controlled" if status is TaskStatus.FAILED else "",
        )


class ApplicationSessionLifetimeTests(unittest.TestCase):
    def test_one_service_creates_independent_tasks_and_history_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            history = HistoryStorage(root / "history.json")
            executor = RecordingTaskExecutor([
                TaskStatus.COMPLETED,
                TaskStatus.COMPLETED,
            ])
            service = GameArchiveService(
                task_executor=executor,
                history_storage=history,
                log_directory=root / "logs",
            )

            first_report = service.execute_task(first)
            second_report = service.execute_task(second)

            self.assertEqual(first_report.task_status, "COMPLETED")
            self.assertEqual(second_report.task_status, "COMPLETED")
            self.assertEqual(len(set(executor.task_ids)), 2)
            records = history.read_all()
            self.assertEqual(len(records), 2)
            self.assertEqual({record.task_id for record in records}, set(executor.task_ids))

    def test_failed_and_cancelled_tasks_do_not_poison_later_task_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            history = HistoryStorage(root / "history.json")
            executor = RecordingTaskExecutor([
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.COMPLETED,
            ])
            service = GameArchiveService(
                task_executor=executor,
                history_storage=history,
                log_directory=root / "logs",
            )

            reports = [
                service.execute_task(root / name)
                for name in ("failed", "cancelled", "success")
            ]

            self.assertEqual(
                [item.task_status for item in reports],
                ["FAILED", "CANCELLED", "COMPLETED"],
            )
            self.assertEqual(len(set(executor.task_ids)), 3)

    def test_explicit_settings_are_reused_for_every_task_in_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executor = RecordingTaskExecutor([
                TaskStatus.COMPLETED,
                TaskStatus.COMPLETED,
            ])
            settings = Settings(
                ignore_android=True,
                ignore_AZ=True,
                max_password_attempts=7,
            )
            service = GameArchiveService(
                settings=settings,
                task_executor=executor,
                history_storage=HistoryStorage(root / "history.json"),
                log_directory=root / "logs",
            )

            service.execute_task(root / "one")
            service.execute_task(root / "two")

            self.assertIs(service.settings, settings)
            self.assertEqual(executor.execution_arguments, [(True, 7), (True, 7)])

    def test_runtime_ownership_is_new_for_each_task(self):
        class OwnedDirectoryExecutor(RecordingTaskExecutor):
            def execute(inner_self, task, max_password_attempts=None, **kwargs):
                owned = task.task_path / "current_run_internal"
                owned.mkdir(parents=True)
                register_created_directory(owned)
                return super(OwnedDirectoryExecutor, inner_self).execute(
                    task,
                    max_password_attempts=max_password_attempts,
                    **kwargs,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "one"
            second = root / "two"
            first.mkdir()
            second.mkdir()
            executor = OwnedDirectoryExecutor([
                TaskStatus.FAILED,
                TaskStatus.FAILED,
            ])
            service = GameArchiveService(
                task_executor=executor,
                history_storage=HistoryStorage(root / "history.json"),
                log_directory=root / "logs",
            )

            first_report = service.execute_task(first)
            second_report = service.execute_task(second)

            self.assertEqual(
                [item.path for item in first_report.residual_internal_directories],
                [(first / "current_run_internal").resolve()],
            )
            self.assertEqual(
                [item.path for item in second_report.residual_internal_directories],
                [(second / "current_run_internal").resolve()],
            )


class CandidateRecordingRunner:
    def __init__(self):
        self.candidate_snapshots = []

    def run(self, **kwargs):
        self.candidate_snapshots.append(list(kwargs["password_candidates"]))
        return PipelineResult(success=True)


class PerTaskCandidateAnalyzer:
    def analyze(self, task):
        name = task.task_path.name
        archive = ArchiveInfo(
            file_path=task.task_path / f"{name}.rar",
            extension=".rar",
            real_format="RAR",
            is_fake_extension=False,
            confidence=1.0,
            container_chain=["RAR"],
        )
        return TaskAnalysisResult(
            task_id=task.task_id,
            task_path=task.task_path,
            archive_results=[archive],
            password_candidates=[
                PasswordCandidate(name, PasswordSource.FOLDER_NAME)
            ],
            analysis_status=AnalysisStatus.COMPLETED,
        )


class TaskCandidateIsolationTests(unittest.TestCase):
    def test_folder_candidates_are_task_scoped_but_verified_session_memory_reuses(self):
        store = SessionPasswordStore()
        store.add_verified("verified-session-value")
        runner = CandidateRecordingRunner()
        executor = TaskExecutor(
            task_analyzer=PerTaskCandidateAnalyzer(),
            pipeline_runner=runner,
            input_relationship_resolver=EmptyRelationshipResolver(),
            session_password_store=store,
        )

        executor.execute(Task(task_path=Path("TaskA")))
        executor.execute(Task(task_path=Path("TaskB")))

        first = {(item.password, item.source) for item in runner.candidate_snapshots[0]}
        second = {(item.password, item.source) for item in runner.candidate_snapshots[1]}
        self.assertIn(("TaskA", PasswordSource.FOLDER_NAME), first)
        self.assertNotIn(("TaskA", PasswordSource.FOLDER_NAME), second)
        self.assertIn(("TaskB", PasswordSource.FOLDER_NAME), second)
        self.assertIn(
            ("verified-session-value", PasswordSource.SESSION_MEMORY), second
        )


if __name__ == "__main__":
    unittest.main()
