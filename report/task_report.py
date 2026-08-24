"""将内部执行结果转换为统一的用户报告。"""

from pathlib import Path

from coordinator.models import CoordinatorResult
from pipeline.models import ArchiveTaskStatus, PipelineResult
from extractor.extractor_models import ExtractionStatus
from report.models import BatchTaskReport, FailureDetail, TaskReport
from task.task_executor import TaskExecutionResult


class ReportGenerator:
    """为 TaskExecutor 或 Pipeline 结果生成 TaskReport。"""

    def generate(
        self,
        result: TaskExecutionResult | PipelineResult,
        execution_time: float | None = None,
    ) -> TaskReport:
        """根据结果类型生成统一报告。"""
        if execution_time is not None and execution_time < 0:
            raise ValueError("execution_time 不能小于 0")

        if isinstance(result, TaskExecutionResult):
            return self._from_task_result(result, execution_time)
        if isinstance(result, PipelineResult):
            return self._from_pipeline_result(result, execution_time)
        raise TypeError("只支持 TaskExecutionResult 或 PipelineResult")

    def generate_batch(
        self, task_reports: list[TaskReport]
    ) -> BatchTaskReport:
        """按输入顺序汇总多个任务报告。"""
        return BatchTaskReport(
            task_reports=task_reports.copy(),
            success_count=sum(report.success_count for report in task_reports),
            failed_count=sum(report.failed_count for report in task_reports),
            skipped_count=sum(report.skipped_count for report in task_reports),
            output_paths=self._unique_paths(
                output_path
                for report in task_reports
                for output_path in report.output_paths
            ),
        )

    def _from_task_result(
        self,
        result: TaskExecutionResult,
        execution_time: float | None,
    ) -> TaskReport:
        coordinator_results = result.coordinator_results
        guard_errors = [
            error
            for pipeline_result in result.pipeline_results
            for error in pipeline_result.guard_errors
        ]
        success_count = sum(item.success for item in coordinator_results)
        failed_count = len(coordinator_results) - success_count + len(guard_errors)
        has_task_level_failure = not result.success and failed_count == 0
        analysis = result.analysis_result
        initial_guard = (
            analysis.initial_archive_guard if analysis is not None else None
        )
        if has_task_level_failure:
            failed_count = 1
        recursive_skipped_count = sum(
            len(pipeline_result.skipped_archives)
            for pipeline_result in result.pipeline_results
        )
        skipped_count = len(result.skipped_archives) + recursive_skipped_count
        total_archives = len(coordinator_results) + skipped_count + len(guard_errors)
        password_attempt_count = self._count_password_attempts(
            coordinator_results
        )
        manual_password_attempt_count = sum(
            item.manual_password_attempt_count for item in coordinator_results
        )
        manual_password_used = any(
            item.manual_password_used for item in coordinator_results
        )
        password_recovery_result = self._password_recovery_result(
            coordinator_results
        )
        output_paths = self._coordinator_output_paths(coordinator_results)
        failure_details = self._pipeline_failure_details(result.pipeline_results)
        represented = {detail.file_path for detail in failure_details}
        failure_details.extend(
            detail
            for detail in self._coordinator_failure_details(coordinator_results)
            if detail.file_path not in represented
        )
        failure_details.extend(self._guard_failure_details(guard_errors))
        if initial_guard is not None:
            failure_details.append(
                FailureDetail(
                    file_path=result.task_path,
                    stage="INITIAL_SCAN_GUARD",
                    tool=None,
                    error_type=initial_guard.error_type,
                    reason=initial_guard.message,
                )
            )
        if has_task_level_failure and initial_guard is None:
            failure_details.append(
                FailureDetail(
                    file_path=result.task_path,
                    stage="ANALYSIS",
                    tool=None,
                    error_type="TASK_FAILED",
                    reason=self._readable_reason(
                        result.error_message or "任务分析或执行失败"
                    ),
                )
            )
        summary = self._build_summary(
            total_archives,
            success_count,
            failed_count,
            skipped_count,
            password_attempt_count,
            execution_time,
        )
        if manual_password_attempt_count:
            summary += (
                f" 人工密码尝试 {manual_password_attempt_count} 次，"
                f"结果 {password_recovery_result or 'FAILED'}。"
            )
        if result.error_message:
            summary += f" 错误摘要：{result.error_message}"

        return TaskReport(
            task_path=result.task_path,
            total_archives=total_archives,
            success_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            password_attempt_count=password_attempt_count,
            execution_time=execution_time,
            manual_password_attempt_count=manual_password_attempt_count,
            manual_password_used=manual_password_used,
            password_recovery_result=password_recovery_result,
            output_paths=output_paths,
            failure_details=failure_details,
            initial_scan_visited_directory_count=(
                analysis.initial_scan_visited_directory_count
                if analysis is not None
                else 0
            ),
            initial_scan_boundaries=(
                analysis.initial_scan_boundaries.copy()
                if analysis is not None
                else []
            ),
            initial_archive_candidates=(
                analysis.initial_archive_candidates.copy()
                if analysis is not None
                else []
            ),
            input_relationships=(
                analysis.input_relationships.copy()
                if analysis is not None
                else []
            ),
            suppressed_redundant_inputs=(
                analysis.suppressed_redundant_inputs.copy()
                if analysis is not None
                else []
            ),
            container_role_decisions=self._container_role_decisions(
                analysis.container_role_decisions if analysis is not None else [],
                result.pipeline_results,
            ),
            summary=summary,
        )

    def _from_pipeline_result(
        self,
        result: PipelineResult,
        execution_time: float | None,
    ) -> TaskReport:
        records = result.execution_records
        guard_errors = result.guard_errors
        skipped_count = len(result.skipped_archives)
        if records:
            success_count = sum(
                record.status is ArchiveTaskStatus.COMPLETED for record in records
            )
            failed_count = sum(
                record.status is ArchiveTaskStatus.FAILED for record in records
            ) + len(guard_errors)
            total_archives = len(records) + skipped_count + len(guard_errors)
            coordinator_results = [
                record.coordinator_result
                for record in records
                if record.coordinator_result is not None
            ]
            failure_details = self._pipeline_failure_details([result])
            failure_details.extend(self._guard_failure_details(guard_errors))
            for record in records:
                if (
                    record.status is ArchiveTaskStatus.FAILED
                    and record.coordinator_result is None
                ):
                    failure_details.append(
                        FailureDetail(
                            file_path=record.archive_path,
                            stage="PIPELINE",
                            tool=None,
                            error_type="PIPELINE_FAILED",
                            reason="递归任务执行失败，未生成协调结果",
                        )
                    )
            output_paths = self._unique_paths(
                record.output_path
                for record in records
                if record.output_path is not None
            )
            root_record = min(records, key=lambda record: record.depth)
            task_path: Path | None = root_record.archive_path
        else:
            success_count = len(result.processed_archives)
            failed_count = len(result.failed_archives) + len(guard_errors)
            total_archives = success_count + failed_count + skipped_count
            coordinator_results = []
            output_paths = []
            failure_details = [
                FailureDetail(
                    file_path=item.archive_path,
                    stage="PIPELINE",
                    tool=None,
                    error_type="PIPELINE_FAILED",
                    reason="递归任务执行失败",
                )
                for item in result.failed_archives
            ]
            failure_details.extend(self._guard_failure_details(guard_errors))
            all_items = result.processed_archives + result.failed_archives
            task_path = all_items[0].archive_path if all_items else None

        password_attempt_count = self._count_password_attempts(
            coordinator_results
        )
        manual_password_attempt_count = sum(
            item.manual_password_attempt_count for item in coordinator_results
        )
        manual_password_used = any(
            item.manual_password_used for item in coordinator_results
        )
        password_recovery_result = self._password_recovery_result(
            coordinator_results
        )
        summary = self._build_summary(
            total_archives,
            success_count,
            failed_count,
            skipped_count=skipped_count,
            password_attempt_count=password_attempt_count,
            execution_time=execution_time,
        )
        if manual_password_attempt_count:
            summary += (
                f" 人工密码尝试 {manual_password_attempt_count} 次，"
                f"结果 {password_recovery_result or 'FAILED'}。"
            )
        if result.max_depth_reached:
            summary += " 已达到递归深度限制。"

        return TaskReport(
            task_path=task_path,
            total_archives=total_archives,
            success_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            password_attempt_count=password_attempt_count,
            execution_time=execution_time,
            manual_password_attempt_count=manual_password_attempt_count,
            manual_password_used=manual_password_used,
            password_recovery_result=password_recovery_result,
            output_paths=output_paths,
            failure_details=failure_details,
            container_role_decisions=result.container_role_decisions.copy(),
            summary=summary,
        )

    @staticmethod
    def _container_role_decisions(initial, pipeline_results):
        """Keep one bounded diagnostic record per path/mode/explicit tuple."""
        decisions = list(initial)
        decisions.extend(
            decision
            for pipeline_result in pipeline_results
            for decision in pipeline_result.container_role_decisions
        )
        unique = []
        seen = set()
        for decision in decisions:
            key = (decision.path, decision.scan_mode, decision.explicit)
            if key in seen:
                continue
            seen.add(key)
            unique.append(decision)
        return unique

    @staticmethod
    def _guard_failure_details(guard_errors) -> list[FailureDetail]:
        return [
            FailureDetail(
                file_path=error.archive_path,
                stage="PIPELINE_GUARD",
                tool=None,
                error_type=error.error_type.value,
                reason=error.message,
            )
            for error in guard_errors
        ]

    @staticmethod
    def _count_password_attempts(
        coordinator_results: list[CoordinatorResult],
    ) -> int:
        """根据 Coordinator 的步骤记录统计实际密码尝试次数。"""
        return sum(
            step.startswith("密码尝试 ")
            for result in coordinator_results
            for step in result.steps
        )

    @staticmethod
    def _password_recovery_result(
        coordinator_results: list[CoordinatorResult],
    ) -> str:
        values = [
            item.password_recovery_result
            for item in coordinator_results
            if item.password_recovery_result
        ]
        return values[-1] if values else ""

    @staticmethod
    def _coordinator_output_paths(
        coordinator_results: list[CoordinatorResult],
    ) -> list[Path]:
        paths = (
            result.extraction_result.output_path
            for result in coordinator_results
            if result.success
            and result.extraction_result is not None
            and result.extraction_result.success
            and result.extraction_result.output_path is not None
        )
        return ReportGenerator._unique_paths(paths)

    @classmethod
    def _coordinator_failure_details(
        cls,
        coordinator_results: list[CoordinatorResult],
    ) -> list[FailureDetail]:
        details: list[FailureDetail] = []
        for result in coordinator_results:
            if result.success:
                continue
            details.append(cls._failure_detail(result))
        return details

    @classmethod
    def _pipeline_failure_details(cls, pipeline_results) -> list[FailureDetail]:
        details: list[FailureDetail] = []
        for pipeline_result in pipeline_results:
            for record in pipeline_result.execution_records:
                coordinator = record.coordinator_result
                if record.status is not ArchiveTaskStatus.FAILED or coordinator is None:
                    continue
                details.append(
                    cls._failure_detail(
                        coordinator,
                        depth=record.depth,
                        parent_archive=record.parent_archive,
                    )
                )
        return details

    @classmethod
    def _failure_detail(
        cls,
        result: CoordinatorResult,
        depth: int = 0,
        parent_archive: Path | None = None,
    ) -> FailureDetail:
        extraction_result = result.extraction_result
        status = extraction_result.status if extraction_result else None
        reason = result.user_message or result.error_message
        if not reason and extraction_result is not None:
            reason = extraction_result.error or extraction_result.message
        diagnostics = result.stage_diagnostics or (
            extraction_result.stage_diagnostics
            if extraction_result is not None
            else []
        )
        normalized = cls._readable_reason(reason or "未知失败原因")
        return FailureDetail(
            file_path=result.archive_path,
            stage=cls._failure_stage(result, status),
            tool=(extraction_result.tool_used if extraction_result else None),
            error_type=(
                result.error_type
                or (status.value if status is not None else "COORDINATOR_FAILED")
            ),
            reason=normalized,
            missing_files=result.missing_files.copy(),
            depth=depth,
            parent_archive=parent_archive,
            extraction_status=(status.value if status is not None else ""),
            normalized_reason=normalized,
            password_attempt_count=result.password_attempt_count,
            manual_password_attempt_count=(
                result.manual_password_attempt_count
            ),
            manual_password_used=result.manual_password_used,
            password_recovery_result=result.password_recovery_result,
            fallback_tools_attempted=result.fallback_tools_attempted.copy(),
            final_tool=result.final_tool or (
                extraction_result.tool_used if extraction_result else None
            ),
            composite_stage=result.composite_stage,
            stage_details=[
                {
                    "stage": item.stage,
                    "format": item.detected_format,
                    "tool": item.tool.value if item.tool else "",
                    "status": item.status.value,
                    "error_type": item.error_type,
                    "reason": cls._readable_reason(item.normalized_reason),
                }
                for item in diagnostics
            ],
        )

    @staticmethod
    def _failure_stage(
        result: CoordinatorResult,
        status: ExtractionStatus | None,
    ) -> str:
        if result.failure_stage:
            return result.failure_stage
        if status is ExtractionStatus.TOOL_NOT_FOUND:
            return "TOOL_DISCOVERY"
        if status in (
            ExtractionStatus.PASSWORD_REQUIRED,
            ExtractionStatus.WRONG_PASSWORD,
        ):
            return "PASSWORD_RECOVERY"
        text = " ".join([result.error_message, *result.steps]).casefold()
        if "安全" in text or "safety" in text:
            return "SAFETY_CHECK"
        if "复合" in text or "composite" in text:
            return "COMPOSITE_EXTRACTION"
        if status is None:
            return "ANALYSIS_OR_PLANNING"
        return "EXTRACTION"

    @staticmethod
    def _readable_reason(reason: str) -> str:
        """Keep reports readable without retaining unbounded tool output."""
        readable = " ".join(str(reason).split())
        if len(readable) > 500:
            readable = readable[:500] + "..."
        return readable

    @staticmethod
    def _unique_paths(paths) -> list[Path]:
        """按首次出现顺序去除重复输出路径。"""
        unique: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            if path not in seen:
                seen.add(path)
                unique.append(path)
        return unique

    @staticmethod
    def _build_summary(
        total_archives: int,
        success_count: int,
        failed_count: int,
        skipped_count: int,
        password_attempt_count: int,
        execution_time: float | None,
    ) -> str:
        summary = (
            f"共发现 {total_archives} 个压缩包：成功 {success_count} 个，"
            f"失败 {failed_count} 个，跳过 {skipped_count} 个；"
            f"密码尝试 {password_attempt_count} 次。"
        )
        if execution_time is not None:
            summary += f" 执行耗时 {execution_time:.2f} 秒。"
        return summary
