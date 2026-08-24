"""连接 Pipeline、Coordinator 和 ArchiveFinder 的递归执行器。"""

from pathlib import Path
from typing import Callable

from config.settings import Settings
from coordinator.extraction_coordinator import ExtractionCoordinator
from coordinator.models import CoordinatorResult
from password.models import PasswordCandidate
from pipeline.extraction_pipeline import ExtractionPipeline
from pipeline.models import (
    ArchiveExecutionRecord,
    ArchiveTaskItem,
    ArchiveTaskStatus,
    PipelinePhase,
    PipelineResult,
    PipelineProgress,
    SkippedArchiveRecord,
)
from rules.platform_filter import PlatformFilter
from scanner.archive_finder import ArchiveFinder, ArchiveScanMode
from security.extraction_safety import ExtractionSafetyChecker
from password.session_store import SessionPasswordStore
from recovery.manual import ManualPasswordCallback


class ExtractionPipelineRunner:
    """有限递归处理一个初始压缩包，不删除或清理任何文件。"""

    def __init__(
        self,
        coordinator: ExtractionCoordinator | None = None,
        archive_finder: ArchiveFinder | None = None,
        settings: Settings | None = None,
        platform_filter: PlatformFilter | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.coordinator = coordinator or ExtractionCoordinator(
            extraction_safety_checker=ExtractionSafetyChecker(self.settings),
            settings=self.settings,
        )
        self.archive_finder = archive_finder or ArchiveFinder()
        self.platform_filter = platform_filter or PlatformFilter(self.settings)

    def run(
        self,
        initial_archive: str | Path,
        password_candidates: list[PasswordCandidate] | None = None,
        max_depth: int | None = None,
        max_tasks: int | None = None,
        max_password_attempts: int | None = None,
        progress_callback: Callable[[PipelineProgress], None] | None = None,
        manual_password_callback: ManualPasswordCallback | None = None,
        session_password_store: SessionPasswordStore | None = None,
    ) -> PipelineResult:
        """从一个初始压缩包开始执行受限的递归解压流程。"""
        max_depth = (
            self.settings.max_recursive_depth if max_depth is None else max_depth
        )
        max_tasks = (
            self.settings.max_archive_tasks if max_tasks is None else max_tasks
        )
        max_password_attempts = (
            self.settings.max_password_attempts
            if max_password_attempts is None
            else max_password_attempts
        )

        if not 0 <= max_password_attempts <= 100:
            raise ValueError("max_password_attempts 必须在 0 到 100 之间")

        pipeline = ExtractionPipeline(
            max_depth=max_depth,
            max_tasks=max_tasks,
            settings=self.settings,
        )
        candidates = password_candidates.copy() if password_candidates else []
        platform_content_root = Path(initial_archive).expanduser().resolve().parent
        execution_records: list[ArchiveExecutionRecord] = []
        skipped_archives: list[SkippedArchiveRecord] = []
        container_role_decisions = []
        initial_item = pipeline.add_task(
            initial_archive,
            depth=0,
            parent_archive=None,
            is_initial=True,
        )
        archive_count = 1 if initial_item is not None else 0
        self._emit_progress(
            progress_callback,
            pipeline,
            archive_count,
            PipelinePhase.EXTRACTING,
            initial_archive,
        )

        while True:
            item = pipeline.get_next_task()
            if item is None:
                break
            self._emit_progress(
                progress_callback,
                pipeline,
                archive_count,
                PipelinePhase.EXTRACTING,
                item.archive_path,
            )

            try:
                process_arguments = {
                    "archive_path": item.archive_path,
                    "password_candidates": candidates,
                    "max_password_attempts": max_password_attempts,
                }
                if manual_password_callback is not None:
                    process_arguments["manual_password_callback"] = (
                        manual_password_callback
                    )
                if session_password_store is not None:
                    process_arguments["session_password_store"] = (
                        session_password_store
                    )
                coordinator_result = self.coordinator.process(**process_arguments)
            except (OSError, ValueError) as error:
                pipeline.steps.append(
                    f"协调任务异常: {item.archive_path} - {error}"
                )
                pipeline.mark_failed(item)
                execution_records.append(self._create_record(item, None))
                self._emit_progress(
                    progress_callback, pipeline, archive_count,
                    PipelinePhase.COMPLETED, item.archive_path
                )
                continue

            for step in coordinator_result.steps:
                pipeline.steps.append(f"[{item.archive_path.name}] {step}")

            if not coordinator_result.success:
                pipeline.steps.append(
                    f"协调任务失败: {item.archive_path} - "
                    f"{coordinator_result.error_message}"
                )
                pipeline.mark_failed(item)
                execution_records.append(
                    self._create_record(item, coordinator_result)
                )
                self._emit_progress(
                    progress_callback, pipeline, archive_count,
                    PipelinePhase.COMPLETED, item.archive_path
                )
                if coordinator_result.control_action == "CANCEL_TASK":
                    pipeline.steps.append("用户取消整个任务")
                    break
                continue

            extraction_result = coordinator_result.extraction_result
            output_path = (
                extraction_result.output_path if extraction_result else None
            )
            if output_path is None:
                pipeline.steps.append(
                    f"成功结果缺少输出目录: {item.archive_path}"
                )
                pipeline.mark_failed(item)
                execution_records.append(
                    self._create_record(item, coordinator_result)
                )
                self._emit_progress(
                    progress_callback, pipeline, archive_count,
                    PipelinePhase.COMPLETED, item.archive_path
                )
                continue

            pipeline.set_task_status(item, ArchiveTaskStatus.SCANNING)
            self._emit_progress(
                progress_callback,
                pipeline,
                archive_count,
                PipelinePhase.SCANNING,
                item.archive_path,
            )
            try:
                discovered_archives = self.archive_finder.find(
                    output_path,
                    scan_mode=ArchiveScanMode.PIPELINE_SCAN,
                )
                container_role_decisions.extend(
                    self.archive_finder.last_container_role_decisions
                )
            except OSError as error:
                pipeline.steps.append(
                    f"扫描输出目录失败: {output_path} - {error}"
                )
                pipeline.mark_failed(item)
                execution_records.append(
                    self._create_record(item, coordinator_result)
                )
                self._emit_progress(
                    progress_callback, pipeline, archive_count,
                    PipelinePhase.COMPLETED, item.archive_path
                )
                continue

            pipeline.set_task_status(item, ArchiveTaskStatus.VALIDATING)
            self._emit_progress(
                progress_callback,
                pipeline,
                archive_count,
                PipelinePhase.VALIDATING,
                item.archive_path,
            )
            pipeline.steps.append(
                f"发现新压缩包: {len(discovered_archives)} 个，"
                f"来源: {item.archive_path}"
            )
            for archive_info in discovered_archives:
                filter_result = self.platform_filter.check(
                    archive_info.file_path,
                    settings=self.settings,
                    root_path=platform_content_root,
                )
                if filter_result.skipped:
                    skipped_archives.append(
                        SkippedArchiveRecord(
                            archive_path=archive_info.file_path,
                            depth=item.depth + 1,
                            parent_archive=item.archive_path,
                            reason=filter_result.reason,
                        )
                    )
                    pipeline.steps.append(
                        f"平台规则跳过: {archive_info.file_path} - "
                        f"{filter_result.reason}"
                    )
                    continue

                added_item = pipeline.add_task(
                    archive_path=archive_info.file_path,
                    depth=item.depth + 1,
                    parent_archive=item.archive_path,
                    is_embedded_archive=archive_info.is_embedded_archive,
                )
                if added_item is not None:
                    archive_count += 1

            pipeline.mark_processed(item)
            execution_records.append(
                self._create_record(item, coordinator_result)
            )
            self._emit_progress(
                progress_callback, pipeline, archive_count,
                PipelinePhase.COMPLETED, item.archive_path
            )

        result = pipeline.get_result()
        result.execution_records = execution_records
        result.skipped_archives = skipped_archives
        result.container_role_decisions = container_role_decisions
        result.cancelled = any(
            record.coordinator_result is not None
            and record.coordinator_result.control_action == "CANCEL_TASK"
            for record in execution_records
        )
        return result

    @staticmethod
    def _emit_progress(
        callback: Callable[[PipelineProgress], None] | None,
        pipeline: ExtractionPipeline,
        archive_count: int,
        phase: PipelinePhase,
        current_archive: str | Path | None,
    ) -> None:
        if callback is None:
            return
        callback(
            PipelineProgress(
                archive_count=archive_count,
                completed_count=len(pipeline.processed_archives),
                failed_count=len(pipeline.failed_archives),
                phase=phase,
                current_archive=(
                    Path(current_archive).expanduser().resolve()
                    if current_archive is not None
                    else None
                ),
            )
        )

    @staticmethod
    def _create_record(
        item: ArchiveTaskItem,
        coordinator_result: CoordinatorResult | None,
    ) -> ArchiveExecutionRecord:
        """从最终任务状态和协调结果创建不可缺失的记录。"""
        extraction_result = (
            coordinator_result.extraction_result if coordinator_result else None
        )
        output_path = extraction_result.output_path if extraction_result else None
        return ArchiveExecutionRecord(
            archive_path=item.archive_path,
            depth=item.depth,
            parent_archive=item.parent_archive,
            status=item.status,
            coordinator_result=coordinator_result,
            output_path=output_path,
        )
