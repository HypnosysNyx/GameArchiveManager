"""把文件夹任务交给递归解压 Pipeline 处理。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from config.settings import Settings
from coordinator.extraction_coordinator import ExtractionCoordinator
from coordinator.models import CoordinatorResult
from pipeline.extraction_runner import ExtractionPipelineRunner
from pipeline.models import PipelineProgress, PipelineResult
from security.extraction_safety import ExtractionSafetyChecker
from task.models import Task, TaskStatus
from task.input_relationship import InputArchiveRelationshipResolver
from task.task_analyzer import (
    AnalysisStatus,
    InitialArchiveGuardError,
    TaskAnalysisResult,
    TaskAnalyzer,
)
from password.models import PasswordCandidate
from password.session_store import SessionPasswordStore
from recovery.manual import ManualPasswordCallback


@dataclass
class SkippedArchiveResult:
    """记录一个因平台忽略规则而未执行的压缩包。"""

    archive_path: Path
    reason: str


@dataclass
class TaskExecutionResult:
    """保存一个文件夹任务的分析和解压结果。"""

    task_id: str
    task_path: Path
    success: bool
    analysis_result: TaskAnalysisResult | None = None
    coordinator_results: list[CoordinatorResult] = field(default_factory=list)
    skipped_archives: list[SkippedArchiveResult] = field(default_factory=list)
    error_message: str = ""
    pipeline_results: list[PipelineResult] = field(default_factory=list)
    suppressed_redundant_inputs: list[Path] = field(default_factory=list)
    cancelled: bool = False


class TaskExecutor:
    """分析一个任务，并递归处理其中发现的每个初始压缩包。"""

    def __init__(
        self,
        task_analyzer: TaskAnalyzer | None = None,
        coordinator: ExtractionCoordinator | None = None,
        pipeline_runner: ExtractionPipelineRunner | None = None,
        input_relationship_resolver: InputArchiveRelationshipResolver | None = None,
        session_password_store: SessionPasswordStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.task_analyzer = task_analyzer or TaskAnalyzer(settings=self.settings)
        self.coordinator = coordinator or ExtractionCoordinator(
            extraction_safety_checker=ExtractionSafetyChecker(self.settings),
            settings=self.settings,
        )
        self.pipeline_runner = pipeline_runner or ExtractionPipelineRunner(
            coordinator=self.coordinator,
            settings=self.settings,
        )
        self.input_relationship_resolver = (
            input_relationship_resolver
            or InputArchiveRelationshipResolver(settings=self.settings)
        )
        self.session_password_store = session_password_store

    def execute(
        self,
        task: Task,
        max_password_attempts: int | None = None,
        progress_callback: Callable[[PipelineProgress], None] | None = None,
        manual_password_callback: ManualPasswordCallback | None = None,
    ) -> TaskExecutionResult:
        """分析任务目录，并对每个初始压缩包执行有限递归流程。"""
        task.status = TaskStatus.CREATED
        task.error_message = ""
        max_password_attempts = (
            self.settings.max_password_attempts
            if max_password_attempts is None
            else max_password_attempts
        )

        if not 0 <= max_password_attempts <= 100:
            task.status = TaskStatus.FAILED
            task.error_message = "max_password_attempts 必须在 0 到 100 之间"
            return TaskExecutionResult(
                task_id=task.task_id,
                task_path=task.task_path,
                success=False,
                error_message=task.error_message,
            )

        task.status = TaskStatus.ANALYZING
        try:
            analysis = self.task_analyzer.analyze(task)
        except Exception as error:
            task.status = TaskStatus.FAILED
            task.error_message = str(error)
            raise

        if analysis.analysis_status is AnalysisStatus.FAILED:
            task.status = TaskStatus.FAILED
            task.error_message = analysis.error_message
            return TaskExecutionResult(
                task_id=task.task_id,
                task_path=task.task_path,
                success=False,
                analysis_result=analysis,
                error_message=analysis.error_message,
            )

        processable_initial_archives = [
            archive_info
            for archive_info in analysis.archive_results
            if self._get_skip_reason(
                archive_info.file_path, analysis.ignored_items
            )
            is None
        ]
        initial_limit = self.settings.max_initial_archive_tasks
        if len(processable_initial_archives) > initial_limit:
            actual = len(processable_initial_archives)
            message = (
                f"初始归档候选数量 {actual} 超过任务限制 {initial_limit}"
            )
            analysis.initial_archive_guard = InitialArchiveGuardError(
                error_type="MAX_INITIAL_ARCHIVE_TASKS",
                actual=actual,
                limit=initial_limit,
                message=message,
            )
            task.status = TaskStatus.FAILED
            task.error_message = message
            return TaskExecutionResult(
                task_id=task.task_id,
                task_path=task.task_path,
                success=False,
                analysis_result=analysis,
                error_message=message,
            )

        relationship_resolution = self.input_relationship_resolver.resolve(
            processable_initial_archives,
            process_all_inputs=task.process_all_inputs,
        )
        analysis.input_relationships = (
            relationship_resolution.relationships.copy()
        )
        analysis.suppressed_redundant_inputs = sorted(
            relationship_resolution.suppressed_paths,
            key=lambda path: str(path).casefold(),
        )
        active_initial_paths = {
            archive.file_path.resolve()
            for archive in relationship_resolution.canonical_archives
        }

        coordinator_results: list[CoordinatorResult] = []
        pipeline_results: list[PipelineResult] = []
        skipped_archives: list[SkippedArchiveResult] = []
        cancelled = False
        password_candidates: list[PasswordCandidate] = (
            analysis.password_candidates.copy()
        )
        if self.session_password_store is not None:
            password_candidates.extend(self.session_password_store.candidates())
        for archive_info in analysis.archive_results:
            skip_reason = self._get_skip_reason(
                archive_info.file_path, analysis.ignored_items
            )
            if skip_reason:
                skipped_archives.append(
                    SkippedArchiveResult(
                        archive_path=archive_info.file_path,
                        reason=skip_reason,
                    )
                )
                continue
            if archive_info.file_path.resolve() not in active_initial_paths:
                continue

            task.status = TaskStatus.EXECUTING
            try:
                run_arguments = {
                    "initial_archive": archive_info.file_path,
                    "password_candidates": password_candidates,
                    "max_password_attempts": max_password_attempts,
                }
                if manual_password_callback is not None:
                    run_arguments["manual_password_callback"] = (
                        manual_password_callback
                    )
                if self.session_password_store is not None:
                    run_arguments["session_password_store"] = (
                        self.session_password_store
                    )
                if progress_callback is not None:
                    run_arguments["progress_callback"] = progress_callback
                pipeline_result = self.pipeline_runner.run(**run_arguments)
            except Exception as error:
                task.status = TaskStatus.FAILED
                task.error_message = str(error)
                raise
            pipeline_results.append(pipeline_result)
            coordinator_results.extend(
                record.coordinator_result
                for record in pipeline_result.execution_records
                if record.coordinator_result is not None
            )
            if pipeline_result.cancelled:
                cancelled = True
                break

        failed_count = sum(not result.success for result in pipeline_results)
        error_message = ""
        if failed_count:
            error_message = (
                f"{failed_count} 个初始压缩包递归处理失败，"
                f"共处理 {len(pipeline_results)} 个"
            )
        task.error_message = error_message

        successful_count = len(pipeline_results) - failed_count
        if cancelled:
            task.status = TaskStatus.CANCELLED
            error_message = "用户取消任务"
            task.error_message = error_message
        elif pipeline_results and successful_count == 0:
            task.status = TaskStatus.FAILED
        else:
            task.status = TaskStatus.COMPLETED

        return TaskExecutionResult(
            task_id=task.task_id,
            task_path=task.task_path,
            success=failed_count == 0 and not cancelled,
            analysis_result=analysis,
            coordinator_results=coordinator_results,
            skipped_archives=skipped_archives,
            error_message=error_message,
            pipeline_results=pipeline_results,
            suppressed_redundant_inputs=(
                analysis.suppressed_redundant_inputs.copy()
            ),
            cancelled=cancelled,
        )

    @staticmethod
    def _get_skip_reason(
        archive_path: Path, ignored_items: list[Path]
    ) -> str | None:
        """判断压缩包本身或其父目录是否命中平台忽略规则。"""
        archive = archive_path.resolve()
        for ignored_item in ignored_items:
            ignored = ignored_item.resolve()
            if archive == ignored:
                return "压缩包名称命中 Android/AZ/安卓忽略规则"
            if ignored in archive.parents:
                return f"压缩包位于忽略目录: {ignored}"
        return None
