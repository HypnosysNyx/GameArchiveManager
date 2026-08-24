"""Application service for execution, reporting, cleanup, and history."""

from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Callable

from application.progress import BatchProgressEvent
from application.runtime_paths import (
    default_config_path,
    default_history_file,
    default_log_directory,
)
from cleanup.cleanup_manager import CleanupManager
from cleanup.models import ResidualInternalDirectory
from cleanup.runtime_tracker import (
    TaskRunDirectoryTracker,
    activate_directory_tracker,
)
from config.config_loader import ConfigLoader
from config.settings import Settings
from coordinator.extraction_coordinator import ExtractionCoordinator
from execution.strategy import ExecutionStrategy
from extractor.dispatcher import ExtractorDispatcher
from extractor.lz4 import Lz4Extractor
from extractor.seven_zip import SevenZipExtractor
from extractor.winrar import WinRarExtractor
from history.models import TaskHistoryRecord
from history.storage import HistoryStorage
from logging_system.logger import GameLogger
from organizer.output_organizer import OutputOrganizer
from organizer.models import ExtractionOutputSource
from password.session_store import SessionPasswordStore
from pipeline.models import PipelineProgress
from report.models import BatchTaskReport, FailureDetail, TaskReport
from report.task_report import ReportGenerator
from security.extraction_safety import ExtractionSafetyChecker
from task.models import Task, TaskStatus
from task.task_analyzer import TaskAnalyzer
from task.input_relationship import InputArchiveRelationshipResolver
from task.task_executor import TaskExecutionResult, TaskExecutor
from tools.tool_manager import ToolManager
from recovery.manual import ManualPasswordCallback
from version import APP_NAME, APP_VERSION, BUILD_TYPE


class GameArchiveService:
    """Provide the shared entry point used by CLI, GUI, and future APIs."""

    def __init__(
        self,
        settings: Settings | None = None,
        task_executor: TaskExecutor | None = None,
        report_generator: ReportGenerator | None = None,
        history_storage: HistoryStorage | None = None,
        output_organizer: OutputOrganizer | None = None,
        log_directory: str | Path | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        active_config_path = (
            Path(config_path).expanduser()
            if config_path is not None
            else default_config_path()
        )
        if settings is not None:
            self.settings = settings
            self.config_warnings: list[str] = []
        else:
            config_loader = ConfigLoader(active_config_path)
            self.settings = config_loader.load()
            self.config_warnings = config_loader.warnings.copy()
        self.history_storage = history_storage or HistoryStorage(
            default_history_file()
        )
        self.session_password_store = SessionPasswordStore()
        self.tool_manager = self._create_tool_manager()
        self.task_executor = task_executor or self._create_task_executor(
            self.tool_manager
        )
        if (
            task_executor is not None
            and hasattr(task_executor, "session_password_store")
            and task_executor.session_password_store is None
        ):
            task_executor.session_password_store = self.session_password_store
        self.report_generator = report_generator or ReportGenerator()
        self.output_organizer = output_organizer or OutputOrganizer()
        self.content_selection_callback = None
        self.password_recovery_callback: ManualPasswordCallback | None = None
        self.log_directory = (
            Path(log_directory).expanduser()
            if log_directory is not None
            else default_log_directory()
        )

    def execute_task(
        self,
        task_path: str | Path,
        progress_callback: Callable[[PipelineProgress], None] | None = None,
        process_all_inputs: bool = False,
        content_selection_callback=None,
        manual_password_callback: ManualPasswordCallback | None = None,
    ) -> TaskReport:
        """Execute one task and apply run-owned temporary-directory rules."""
        requested_path = Path(task_path).expanduser()
        if requested_path.is_file():
            task = Task(
                task_path=requested_path.parent,
                explicit_archive_path=requested_path,
                process_all_inputs=process_all_inputs,
            )
        else:
            task = Task(
                task_path=requested_path,
                process_all_inputs=process_all_inputs,
            )
        task.settings.ignore_android_az = (
            self.settings.ignore_android or self.settings.ignore_AZ
        )
        task.settings.delete_archives = self.settings.delete_archives
        task.settings.delete_empty_folders = self.settings.delete_empty_folders
        tracker = TaskRunDirectoryTracker(task.task_path)
        started_at = perf_counter()

        with GameLogger(task.task_id, self.log_directory) as game_logger:
            game_logger.info(
                f"Application: {APP_NAME}; version: {APP_VERSION}; "
                f"build: {BUILD_TYPE}"
            )
            game_logger.task_started(task.task_path)
            game_logger.info(f"Task 创建: {task.task_id}")
            try:
                arguments = {
                    "max_password_attempts": self.settings.max_password_attempts,
                }
                if progress_callback is not None:
                    arguments["progress_callback"] = progress_callback
                active_password_callback = (
                    manual_password_callback or self.password_recovery_callback
                )
                if active_password_callback is not None:
                    arguments["manual_password_callback"] = (
                        active_password_callback
                    )
                game_logger.info("执行开始")
                with activate_directory_tracker(tracker):
                    execution_result = self.task_executor.execute(
                        task, **arguments
                    )
                execution_time = perf_counter() - started_at
                game_logger.info(f"执行完成: {task.status.value}")

                report = self.report_generator.generate(
                    execution_result, execution_time=execution_time
                )
                output_sources = self._extraction_output_sources(
                    execution_result, tracker
                )
                output_roots, final_candidates = (
                    self.output_organizer.resolve_and_organize(
                    task.task_path,
                    output_sources,
                    tracker.owned_directories(),
                    selection_callback=(
                        content_selection_callback
                        or self.content_selection_callback
                    ),
                    )
                )
                report.output_roots = output_roots
                report.final_content_candidates = final_candidates
                report.duplicate_contents = (
                    self.output_organizer.last_duplicate_records.copy()
                )
                report.delivery_units = self.output_organizer.last_delivery_units.copy()
                report.output_paths = [
                    output.final_output_path for output in output_roots
                ]
                unresolved_content_paths = self._unresolved_content_paths(
                    report.final_content_candidates,
                    report.delivery_units,
                )
                needs_selection = bool(unresolved_content_paths)
                if execution_result.success and needs_selection:
                    task.status = TaskStatus.COMPLETED_NEEDS_SELECTION
                    report.delivery_status = "NEEDS_USER_SELECTION"
                    report.summary += " 解压成功，仍有最终内容尚未选择和交付。"
                elif execution_result.success and not report.output_paths:
                    if output_sources:
                        task.status = TaskStatus.DELIVERY_FAILED
                        report.delivery_status = "DELIVERY_FAILED"
                        report.summary += " 解压成功，但最终内容交付失败。"
                elif report.output_paths:
                    report.delivery_status = "DELIVERED"
                report.task_status = task.status.value
                game_logger.info("报告生成")
                for output_path in report.output_paths:
                    game_logger.info(f"最终输出路径: {output_path}")
                for detail in report.failure_details:
                    game_logger.error(
                        "Execution failure: "
                        f"stage={detail.stage}; status={detail.extraction_status}; "
                        f"type={detail.error_type}; tool="
                        f"{detail.final_tool.value if detail.final_tool else 'NONE'}; "
                        f"reason={detail.normalized_reason or detail.reason}"
                    )

                if execution_result.success and report.failed_count == 0:
                    if task.status is TaskStatus.DELIVERY_FAILED:
                        residuals = self._orphaned_directories(
                            tracker, "ORPHANED_TEMP: DELIVERY_FAILED"
                        )
                    else:
                        residuals = self._cleanup_successful_run(
                            task.task_path,
                            tracker,
                            execution_result,
                            game_logger,
                            preserve_content_paths=unresolved_content_paths,
                        )
                else:
                    residuals = self._orphaned_directories(
                        tracker, "ORPHANED_TEMP: TASK_FAILED"
                    )
                report.residual_internal_directories = residuals
                self._append_residual_summary(report)
                self._save_history(
                    task,
                    report,
                    task.status is TaskStatus.COMPLETED,
                    datetime.now().astimezone(),
                )
                game_logger.info("历史保存成功")
                return report
            except (Exception, KeyboardInterrupt) as error:
                task.status = TaskStatus.FAILED
                residuals = self._orphaned_directories(
                    tracker, f"ORPHANED_TEMP: {type(error).__name__}"
                )
                report = TaskReport(
                    task_path=task.task_path,
                    total_archives=1,
                    success_count=0,
                    failed_count=1,
                    skipped_count=0,
                    password_attempt_count=0,
                    execution_time=perf_counter() - started_at,
                    failure_details=[
                        FailureDetail(
                            file_path=task.task_path,
                            stage="APPLICATION",
                            tool=None,
                            error_type=type(error).__name__,
                            reason="任务执行被中断，内部目录已安全保留",
                        )
                    ],
                    residual_internal_directories=residuals,
                    summary=f"任务执行失败: {type(error).__name__}。",
                )
                self._append_residual_summary(report)
                game_logger.error(f"Task exception: {type(error).__name__}")
                try:
                    self._save_history(
                        task,
                        report,
                        False,
                        datetime.now().astimezone(),
                    )
                except Exception as history_error:
                    game_logger.error(
                        f"History exception: {type(history_error).__name__}"
                    )
                return report

    @staticmethod
    def _extraction_output_sources(
        execution_result: TaskExecutionResult,
        tracker: TaskRunDirectoryTracker,
    ) -> list[ExtractionOutputSource]:
        """Keep archive/output metadata that the plain report path list loses."""
        sources: list[ExtractionOutputSource] = []
        seen: set[Path] = set()

        for pipeline_result in execution_result.pipeline_results:
            for record in pipeline_result.execution_records:
                coordinator_result = record.coordinator_result
                extraction_result = (
                    coordinator_result.extraction_result
                    if coordinator_result is not None
                    else None
                )
                if (
                    coordinator_result is None
                    or not coordinator_result.success
                    or extraction_result is None
                    or extraction_result.output_path is None
                ):
                    continue
                physical = Path(extraction_result.output_path).resolve()
                if physical in seen:
                    continue
                seen.add(physical)
                sources.append(
                    ExtractionOutputSource(
                        physical_output_path=physical,
                        archive_path=record.archive_path,
                        depth=record.depth,
                        parent_archive=record.parent_archive,
                        status=record.status.value,
                        runtime_owned=tracker.owns(physical),
                    )
                )

        # Preserve compatibility with task executors and tests that return
        # coordinator results without Pipeline execution records.
        for coordinator_result in execution_result.coordinator_results:
            extraction_result = coordinator_result.extraction_result
            if (
                not coordinator_result.success
                or extraction_result is None
                or extraction_result.output_path is None
            ):
                continue
            physical = Path(extraction_result.output_path).resolve()
            if physical in seen:
                continue
            seen.add(physical)
            sources.append(
                ExtractionOutputSource(
                    physical_output_path=physical,
                    archive_path=coordinator_result.archive_path,
                    runtime_owned=tracker.owns(physical),
                )
            )
        return sources

    def _cleanup_successful_run(
        self,
        task_path: Path,
        tracker: TaskRunDirectoryTracker,
        execution_result,
        game_logger: GameLogger,
        preserve_content_paths: list[Path] | None = None,
    ) -> list[ResidualInternalDirectory]:
        owned_paths = tracker.top_level_directories()
        if not owned_paths:
            return []
        preserve_content_paths = [
            Path(path).expanduser().resolve()
            for path in (preserve_content_paths or [])
        ]
        preserved_owned_paths = {
            owned
            for owned in owned_paths
            if any(
                content == owned or owned in content.parents
                for content in preserve_content_paths
            )
        }
        cleanup_paths = [
            path for path in owned_paths if path not in preserved_owned_paths
        ]
        input_archives: list[Path] = []
        analysis = execution_result.analysis_result
        if analysis is not None:
            for archive_info in analysis.archive_results:
                input_archives.append(archive_info.file_path)
                input_archives.extend(archive_info.volume_files)
        final_root = Path(task_path).expanduser().resolve() / "GameArchive_Output"
        manager = CleanupManager(
            task_output_directory=task_path,
            task_root=task_path,
            input_archives=input_archives,
            protected_paths=[final_root],
        )
        candidates = manager.authorize_owned(
            cleanup_paths, reason="RUN_TEMP_COMPLETED"
        )
        authorized = {candidate.path for candidate in candidates}
        residuals = [
            self._residual(path, "ORPHANED_TEMP: DELIVERY_PENDING")
            for path in preserved_owned_paths
            if path.exists()
        ]
        residuals.extend(
            self._residual(path, "ORPHANED_TEMP: SAFETY_VALIDATION_REJECTED")
            for path in cleanup_paths
            if path not in authorized and path.exists()
        )
        for candidate in candidates:
            try:
                manager.delete(candidate.path)
                game_logger.info(f"Run-owned temporary directory cleaned: {candidate.path}")
            except (OSError, ValueError) as error:
                residuals.append(
                    self._residual(
                        candidate.path,
                        f"ORPHANED_TEMP: CLEANUP_{type(error).__name__}",
                    )
                )
        return residuals

    @staticmethod
    def _unresolved_content_paths(
        candidates,
        delivery_units,
    ) -> list[Path]:
        """Return unique user-content roots still waiting for a decision."""
        pending_statuses = {
            "CANDIDATE",
            "NEEDS_USER_SELECTION",
            "AMBIGUOUS",
            "WAITING_USER_DECISION",
        }
        unit_roots = {
            Path(unit.terminal_content_root).expanduser().resolve()
            for unit in delivery_units
            if unit.terminal_content_root is not None
            and unit.selection_status in pending_statuses
        }
        candidate_roots = {
            Path(candidate.content_root).expanduser().resolve()
            for candidate in candidates
            if candidate.has_meaningful_parent_content
            and candidate.selection_status in pending_statuses
        }
        return sorted(
            unit_roots | candidate_roots,
            key=lambda path: str(path).casefold(),
        )

    @staticmethod
    def _orphaned_directories(
        tracker: TaskRunDirectoryTracker,
        reason: str,
    ) -> list[ResidualInternalDirectory]:
        return [
            GameArchiveService._residual(path, reason)
            for path in tracker.top_level_directories()
        ]

    @staticmethod
    def _residual(path: Path, reason: str) -> ResidualInternalDirectory:
        try:
            created_time = datetime.fromtimestamp(
                path.stat().st_ctime
            ).astimezone()
        except OSError:
            created_time = None
        return ResidualInternalDirectory(
            path=path,
            status="ORPHANED_TEMP",
            reason=reason,
            created_time=created_time,
        )

    @staticmethod
    def _append_residual_summary(report: TaskReport) -> None:
        if report.residual_internal_directories:
            report.summary += (
                " 保留内部目录 "
                f"{len(report.residual_internal_directories)} 个，"
                "状态 ORPHANED_TEMP。"
            )

    def _save_history(
        self,
        task: Task,
        report: TaskReport,
        success: bool,
        completed_time: datetime,
    ) -> None:
        self.history_storage.save(
            TaskHistoryRecord(
                task_id=task.task_id,
                task_path=task.task_path,
                status=task.status,
                created_time=task.created_time,
                completed_time=completed_time,
                success=success,
                summary=report.summary,
                app_version=report.app_version,
                build_type=report.build_type,
                output_paths=report.output_paths.copy(),
                final_content_candidates=(
                    report.final_content_candidates.copy()
                ),
                delivery_units=report.delivery_units.copy(),
                failure_details=report.failure_details.copy(),
                delivery_status=report.delivery_status,
                initial_scan_visited_directory_count=(
                    report.initial_scan_visited_directory_count
                ),
                initial_scan_boundaries=report.initial_scan_boundaries.copy(),
                initial_archive_candidates=(
                    report.initial_archive_candidates.copy()
                ),
                input_relationships=report.input_relationships.copy(),
                suppressed_redundant_inputs=(
                    report.suppressed_redundant_inputs.copy()
                ),
                duplicate_contents=report.duplicate_contents.copy(),
                residual_internal_directories=(
                    report.residual_internal_directories.copy()
                ),
                manual_password_attempt_count=(
                    report.manual_password_attempt_count
                ),
                manual_password_used=report.manual_password_used,
                password_recovery_result=report.password_recovery_result,
                container_role_decisions=(
                    report.container_role_decisions.copy()
                ),
            )
        )

    def execute_tasks(
        self,
        task_paths: list[str | Path],
        progress_callback: Callable[[BatchProgressEvent], None] | None = None,
        content_selection_callback=None,
    ) -> BatchTaskReport:
        """Execute multiple independent task roots in input order."""
        task_reports: list[TaskReport] = []
        total_tasks = len(task_paths)
        for current_task, task_path in enumerate(task_paths, start=1):
            normalized_path = Path(task_path).expanduser()
            self._emit_batch_progress(
                progress_callback,
                BatchProgressEvent(
                    "TASK_STARTED",
                    current_task,
                    total_tasks,
                    normalized_path,
                    "RUNNING",
                ),
            )

            def pipeline_progress(update: PipelineProgress) -> None:
                self._emit_batch_progress(
                    progress_callback,
                    BatchProgressEvent(
                        event_type="PIPELINE_PROGRESS",
                        current_task=current_task,
                        total_tasks=total_tasks,
                        task_path=normalized_path,
                        status="RUNNING",
                        archive_count=update.archive_count,
                        completed_count=update.completed_count,
                        failed_count=update.failed_count,
                        phase=update.phase.value,
                        current_archive=update.current_archive,
                    ),
                )

            try:
                arguments = {
                    "progress_callback": (
                        pipeline_progress if progress_callback is not None else None
                    )
                }
                if content_selection_callback is not None:
                    arguments["content_selection_callback"] = content_selection_callback
                task_report = self.execute_task(normalized_path, **arguments)
            except Exception as error:
                task_report = TaskReport(
                    task_path=normalized_path,
                    total_archives=1,
                    success_count=0,
                    failed_count=1,
                    skipped_count=0,
                    password_attempt_count=0,
                    execution_time=None,
                    failure_details=[
                        FailureDetail(
                            normalized_path,
                            "APPLICATION",
                            None,
                            type(error).__name__,
                            "任务执行发生异常",
                        )
                    ],
                    summary=f"任务执行失败: {type(error).__name__}",
                )
            task_reports.append(task_report)
            status = task_report.task_status or (
                "FAILED" if task_report.failed_count else "COMPLETED"
            )
            self._emit_batch_progress(
                progress_callback,
                BatchProgressEvent(
                    "TASK_FINISHED",
                    current_task,
                    total_tasks,
                    normalized_path,
                    status,
                ),
            )
        return self.report_generator.generate_batch(task_reports)

    @staticmethod
    def _emit_batch_progress(
        callback: Callable[[BatchProgressEvent], None] | None,
        event: BatchProgressEvent,
    ) -> None:
        if callback is not None:
            callback(event)

    def _create_tool_manager(self) -> ToolManager:
        return ToolManager(settings=self.settings)

    def _create_task_executor(self, tool_manager: ToolManager) -> TaskExecutor:
        seven_zip_extractor = SevenZipExtractor(
            tool_manager=tool_manager, settings=self.settings
        )
        lz4_extractor = Lz4Extractor(
            tool_manager=tool_manager, settings=self.settings
        )
        winrar_extractor = WinRarExtractor(
            tool_manager=tool_manager, settings=self.settings
        )
        dispatcher = ExtractorDispatcher(
            seven_zip_extractor=seven_zip_extractor,
            lz4_extractor=lz4_extractor,
            winrar_extractor=winrar_extractor,
            tool_manager=tool_manager,
            settings=self.settings,
        )
        coordinator = ExtractionCoordinator(
            strategy=ExecutionStrategy(settings=self.settings),
            dispatcher=dispatcher,
            extraction_safety_checker=ExtractionSafetyChecker(self.settings),
        )
        relationship_resolver = InputArchiveRelationshipResolver(
            settings=self.settings,
            tool_manager=tool_manager,
        )
        return TaskExecutor(
            task_analyzer=TaskAnalyzer(
                history_storage=self.history_storage,
                settings=self.settings,
            ),
            coordinator=coordinator,
            input_relationship_resolver=relationship_resolver,
            session_password_store=self.session_password_store,
            settings=self.settings,
        )
