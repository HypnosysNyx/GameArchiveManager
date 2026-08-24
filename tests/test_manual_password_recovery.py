"""Safe interactive password-recovery regression tests."""

import hashlib
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import main as main_module
from analyzer.models import ArchiveInfo
from config.settings import Settings
from coordinator.extraction_coordinator import ExtractionCoordinator
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from history.models import TaskHistoryRecord
from history.storage import HistoryStorage
from logging_system.logger import GameLogger
from password.models import PasswordCandidate, PasswordSource
from password.session_store import SessionPasswordStore
from pipeline.extraction_runner import ExtractionPipelineRunner
from pipeline.models import PipelineResult
from recovery.manual import (
    ManualPasswordAction,
    ManualPasswordRequest,
    ManualPasswordResponse,
)
from report.task_report import ReportGenerator
from task.models import Task, TaskStatus
from task.task_analyzer import AnalysisStatus, TaskAnalysisResult
from task.task_executor import TaskExecutionResult, TaskExecutor
from tools.models import ToolName


TEST_PASSWORD = "DO_NOT_LEAK_TEST_PASSWORD_93827"


class FixedAnalyzer:
    def __init__(self, archive_format: str, container_chain=None, volume_files=None):
        self.archive_format = archive_format
        self.container_chain = container_chain or [archive_format]
        self.volume_files = volume_files or []

    def analyze(self, path):
        archive = Path(path).resolve()
        detected = "LZ4" if archive.suffix.casefold() == ".lz4" else self.archive_format
        chain = self.container_chain if detected == "LZ4" else [self.archive_format]
        return ArchiveInfo(
            file_path=archive,
            extension=archive.suffix.casefold(),
            real_format=detected,
            is_fake_extension=False,
            confidence=1.0,
            container_chain=chain.copy(),
            is_multi_volume=bool(self.volume_files),
            volume_group="controlled" if self.volume_files else "",
            volume_files=self.volume_files.copy(),
        )


class PasswordDispatcher:
    """Controlled extractor that never writes passwords into result text."""

    def __init__(self, valid_password=TEST_PASSWORD):
        self.valid_password = valid_password
        self.calls = []

    def extract(self, plan, password=None):
        self.calls.append((plan.detected_format, plan.archive_path, password is not None))
        if plan.detected_format == "LZ4":
            plan.output_path.mkdir(parents=True)
            (plan.output_path / plan.archive_path.stem).write_bytes(
                b"Rar!\x1a\x07\x00controlled-inner"
            )
            return ExtractionResult(
                True,
                "outer success",
                plan.output_path,
                tool_used=ToolName.LZ4,
                status=ExtractionStatus.SUCCESS,
            )
        if password == self.valid_password:
            plan.output_path.mkdir(parents=True, exist_ok=True)
            (plan.output_path / "payload.txt").write_text(
                "recovered", encoding="utf-8"
            )
            return ExtractionResult(
                True,
                "password accepted",
                plan.output_path,
                tool_used=plan.selected_tool,
                status=ExtractionStatus.SUCCESS,
            )
        return ExtractionResult(
            False,
            "password required" if password is None else "password rejected",
            plan.output_path,
            tool_used=plan.selected_tool,
            status=(
                ExtractionStatus.PASSWORD_REQUIRED
                if password is None
                else ExtractionStatus.WRONG_PASSWORD
            ),
        )


def callback_from(responses):
    queued = list(responses)
    requests = []

    def callback(request):
        requests.append(request)
        return queued.pop(0)

    callback.requests = requests
    return callback


class StaticTaskAnalyzer:
    def __init__(self, archive: Path):
        self.archive = archive

    def analyze(self, task):
        return TaskAnalysisResult(
            task_id=task.task_id,
            task_path=task.task_path,
            archive_results=[
                ArchiveInfo(
                    self.archive,
                    self.archive.suffix,
                    "RAR",
                    False,
                    1.0,
                    ["RAR"],
                )
            ],
            analysis_status=AnalysisStatus.COMPLETED,
        )


class CancelledPipelineRunner:
    def run(self, **kwargs):
        return PipelineResult(success=False, cancelled=True)


class ManualPasswordRecoveryTests(unittest.TestCase):
    def _archive(self, root: Path, name="game.rar") -> Path:
        archive = root / name
        archive.write_bytes(b"Rar!\x1a\x07\x00source-bytes")
        return archive

    def _coordinator(self, archive_format="RAR", chain=None, volume_files=None):
        dispatcher = PasswordDispatcher()
        coordinator = ExtractionCoordinator(
            analyzer=FixedAnalyzer(archive_format, chain, volume_files),
            dispatcher=dispatcher,
            settings=Settings(),
        )
        return coordinator, dispatcher

    def test_automatic_candidate_success_never_requests_manual_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = self._archive(Path(temp_dir))
            coordinator, _ = self._coordinator()

            result = coordinator.process(
                archive,
                [PasswordCandidate(TEST_PASSWORD, PasswordSource.USER_INPUT)],
                manual_password_callback=lambda request: self.fail(
                    "manual callback must not run"
                ),
            )

            self.assertTrue(result.success)
            self.assertEqual(result.manual_password_attempt_count, 0)

    def test_auto_exhausted_then_manual_correct_recovers_current_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = self._archive(root)
            before = hashlib.sha256(archive.read_bytes()).hexdigest()
            coordinator, dispatcher = self._coordinator()
            store = SessionPasswordStore()
            callback = callback_from([
                ManualPasswordResponse(
                    ManualPasswordAction.INPUT_PASSWORD, TEST_PASSWORD
                )
            ])

            result = coordinator.process(
                archive,
                [PasswordCandidate("wrong-auto", PasswordSource.FOLDER_NAME)],
                manual_password_callback=callback,
                session_password_store=store,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.manual_password_attempt_count, 1)
            self.assertTrue(result.manual_password_used)
            self.assertEqual(result.password_recovery_result, "SUCCESS")
            self.assertEqual(len(store), 1)
            self.assertEqual(before, hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertTrue(
                all(call[1].samefile(archive) for call in dispatcher.calls)
            )

    def test_manual_wrong_then_correct_does_not_restart_initial_stage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = self._archive(Path(temp_dir))
            coordinator, dispatcher = self._coordinator()
            store = SessionPasswordStore()
            callback = callback_from([
                ManualPasswordResponse(ManualPasswordAction.INPUT_PASSWORD, "wrong"),
                ManualPasswordResponse(
                    ManualPasswordAction.INPUT_PASSWORD, TEST_PASSWORD
                ),
            ])

            result = coordinator.process(
                archive,
                [],
                manual_password_callback=callback,
                session_password_store=store,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.manual_password_attempt_count, 2)
            self.assertEqual(len(callback.requests), 2)
            self.assertEqual(
                [request.manual_attempt_count for request in callback.requests],
                [0, 1],
            )
            self.assertEqual(sum(not has_password for _, _, has_password in dispatcher.calls), 1)
            self.assertEqual(len(store), 1)
            self.assertEqual(store.candidates()[0].password, TEST_PASSWORD)
            self.assertNotIn(
                "wrong", [item.password for item in store.candidates()]
            )

    def test_verified_password_is_reused_by_second_task_in_same_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_root = root / "task_one"
            second_root = root / "task_two"
            first_root.mkdir()
            second_root.mkdir()
            first_archive = self._archive(first_root)
            second_archive = self._archive(second_root)
            coordinator, _ = self._coordinator()
            store = SessionPasswordStore()
            analyzer = StaticTaskAnalyzer(first_archive)
            runner = ExtractionPipelineRunner(coordinator=coordinator)
            executor = TaskExecutor(
                task_analyzer=analyzer,
                coordinator=coordinator,
                pipeline_runner=runner,
                session_password_store=store,
            )

            first_result = executor.execute(
                Task(task_path=first_root),
                manual_password_callback=callback_from([
                    ManualPasswordResponse(
                        ManualPasswordAction.INPUT_PASSWORD, TEST_PASSWORD
                    )
                ]),
            )
            analyzer.archive = second_archive
            second_result = executor.execute(
                Task(task_path=second_root),
                manual_password_callback=lambda request: self.fail(
                    "verified session password should avoid another prompt"
                ),
            )

            self.assertTrue(first_result.success)
            self.assertTrue(second_result.success)
            self.assertEqual(len(store), 1)
            self.assertEqual(
                store.candidates()[0].source,
                PasswordSource.SESSION_MEMORY,
            )

    def test_user_skip_returns_structured_failure_without_loop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = self._archive(Path(temp_dir))
            coordinator, _ = self._coordinator()
            callback = callback_from([
                ManualPasswordResponse(ManualPasswordAction.SKIP_ARCHIVE)
            ])

            result = coordinator.process(
                archive, [], manual_password_callback=callback
            )

            self.assertFalse(result.success)
            self.assertEqual(result.control_action, "SKIP_ARCHIVE")
            self.assertEqual(result.error_type, "USER_SKIPPED_PASSWORD_ARCHIVE")
            self.assertEqual(len(callback.requests), 1)

    def test_user_cancel_stops_pipeline_and_marks_task_cancelled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = self._archive(root)
            coordinator, _ = self._coordinator()
            runner = ExtractionPipelineRunner(coordinator=coordinator)
            callback = callback_from([
                ManualPasswordResponse(ManualPasswordAction.CANCEL_TASK)
            ])

            pipeline_result = runner.run(
                archive, manual_password_callback=callback
            )
            self.assertTrue(pipeline_result.cancelled)
            self.assertEqual(
                pipeline_result.execution_records[0].coordinator_result.error_type,
                "USER_CANCELLED_TASK",
            )

            task = Task(task_path=root)
            executor = TaskExecutor(
                task_analyzer=StaticTaskAnalyzer(archive),
                pipeline_runner=CancelledPipelineRunner(),
            )
            task_result = executor.execute(task)
            self.assertTrue(task_result.cancelled)
            self.assertIs(task.status, TaskStatus.CANCELLED)

    def test_composite_manual_retry_runs_lz4_only_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = self._archive(root, "game.rar.lz4")
            archive.write_bytes(b"\x04\x22\x4d\x18wrapper")
            coordinator, dispatcher = self._coordinator(
                "RAR", ["LZ4", "RAR"]
            )
            callback = callback_from([
                ManualPasswordResponse(
                    ManualPasswordAction.INPUT_PASSWORD, TEST_PASSWORD
                )
            ])

            result = coordinator.process(
                archive, [], manual_password_callback=callback
            )

            self.assertTrue(result.success)
            self.assertEqual(
                sum(fmt == "LZ4" for fmt, _, _ in dispatcher.calls), 1
            )
            self.assertEqual(callback.requests[0].composite_stage, "COMPOSITE_INNER")
            self.assertEqual(callback.requests[0].archive_path.name, "game.rar")

    def test_split_archive_retries_first_volume_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = self._archive(root, "game.7z.001")
            second = root / "game.7z.002"
            second.write_bytes(b"continuation")
            coordinator, dispatcher = self._coordinator(
                "7Z", ["7Z"], [first, second]
            )
            callback = callback_from([
                ManualPasswordResponse(
                    ManualPasswordAction.INPUT_PASSWORD, TEST_PASSWORD
                )
            ])

            result = coordinator.process(
                first, [], manual_password_callback=callback
            )

            self.assertTrue(result.success)
            self.assertTrue(
                all(path.samefile(first) for _, path, _ in dispatcher.calls)
            )
            self.assertFalse(
                any(path.samefile(second) for _, path, _ in dispatcher.calls)
            )

    def test_noninteractive_mode_keeps_structured_exhaustion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = self._archive(Path(temp_dir))
            coordinator, _ = self._coordinator()

            result = coordinator.process(archive, [])

            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "PASSWORD_CANDIDATES_EXHAUSTED")
            self.assertEqual(result.manual_password_attempt_count, 0)

    def test_password_never_enters_report_history_stdout_log_or_repr(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = self._archive(root)
            coordinator, _ = self._coordinator()
            callback = callback_from([
                ManualPasswordResponse(
                    ManualPasswordAction.INPUT_PASSWORD, TEST_PASSWORD
                )
            ])
            result = coordinator.process(
                archive, [], manual_password_callback=callback
            )
            task_result = TaskExecutionResult(
                "task-safe", root, True, coordinator_results=[result]
            )
            report = ReportGenerator().generate(task_result)
            history_file = root / "history.json"
            HistoryStorage(history_file).save(
                TaskHistoryRecord(
                    "task-safe",
                    root,
                    TaskStatus.COMPLETED,
                    datetime.now().astimezone(),
                    datetime.now().astimezone(),
                    True,
                    report.summary,
                    manual_password_attempt_count=report.manual_password_attempt_count,
                    manual_password_used=report.manual_password_used,
                    password_recovery_result=report.password_recovery_result,
                )
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                main_module.print_report(report)
            with GameLogger("task-safe", root / "logs") as logger:
                logger.info(
                    f"Password recovery result: {report.password_recovery_result}"
                )
            persisted = history_file.read_text(encoding="utf-8")
            log_text = "".join(
                path.read_text(encoding="utf-8")
                for path in (root / "logs").glob("*.log")
            )
            combined = "\n".join(
                [
                    repr(callback.responses) if hasattr(callback, "responses") else "",
                    repr(result),
                    repr(report),
                    persisted,
                    stdout.getvalue(),
                    log_text,
                ]
            )
            self.assertNotIn(TEST_PASSWORD, combined)
            self.assertEqual(report.manual_password_attempt_count, 1)
            self.assertTrue(report.manual_password_used)

    def test_cli_adapter_visible_input_keeps_password_out_of_repr(self):
        request = ManualPasswordRequest(
            Path("inner.rar"),
            "RAR",
            ExtractionStatus.WRONG_PASSWORD,
            2,
            0,
            "COMPOSITE_INNER",
        )
        stdout = StringIO()
        with patch(
            "builtins.input", side_effect=["I", TEST_PASSWORD]
        ), redirect_stdout(stdout):
            response = main_module.prompt_manual_password(request)

        self.assertIs(response.action, ManualPasswordAction.INPUT_PASSWORD)
        self.assertEqual(response.password, TEST_PASSWORD)
        self.assertIn("会显示", stdout.getvalue())
        self.assertNotIn(TEST_PASSWORD, repr(response))


if __name__ == "__main__":
    unittest.main()
