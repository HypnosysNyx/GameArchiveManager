"""协调复合容器的分阶段执行，并重新验证每个中间文件。"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from analyzer.archive_analyzer import ArchiveAnalyzer
from execution.models import ExtractionPlan
from execution.strategy import ExecutionStrategy
from extractor.extractor_models import (
    ExtractionResult,
    ExtractionStageDiagnostic,
    ExtractionStatus,
)
from scanner.archive_finder import ArchiveFinder
from security.archive_content_inspector import ArchiveContentInspector
from security.extraction_safety import ExtractionSafetyChecker


StageExecutor = Callable[
    [ExtractionPlan], tuple[ExtractionPlan, ExtractionResult, list[str]]
]


@dataclass
class CompositeExecutionResult:
    """保存复合执行完成时实际使用的最后计划和结果。"""

    active_plan: ExtractionPlan
    extraction_result: ExtractionResult
    steps: list[str]
    stage_diagnostics: list[ExtractionStageDiagnostic]


class CompositeExtractor:
    """执行外层容器，重新分析中间文件，再执行真实的内层格式。"""

    def __init__(
        self,
        analyzer: ArchiveAnalyzer | None = None,
        archive_finder: ArchiveFinder | None = None,
        strategy: ExecutionStrategy | None = None,
        content_inspector: ArchiveContentInspector | None = None,
        extraction_safety_checker: ExtractionSafetyChecker | None = None,
    ) -> None:
        self.analyzer = analyzer or ArchiveAnalyzer()
        self.archive_finder = archive_finder or ArchiveFinder(self.analyzer)
        self.strategy = strategy or ExecutionStrategy()
        self.content_inspector = content_inspector or ArchiveContentInspector()
        self.extraction_safety_checker = (
            extraction_safety_checker or ExtractionSafetyChecker()
        )

    def extract(
        self,
        plan: ExtractionPlan,
        execute_stage: StageExecutor,
    ) -> CompositeExecutionResult:
        """执行两阶段复合计划；内部格式只采用重新分析的结果。"""
        steps = [f"复合容器计划: {' → '.join(plan.container_chain)}"]
        active_plan, outer_result, stage_steps = execute_stage(plan)
        steps.extend(stage_steps)
        diagnostics = [self._diagnostic("COMPOSITE_OUTER", active_plan, outer_result)]
        if outer_result.status is not ExtractionStatus.SUCCESS:
            return CompositeExecutionResult(active_plan, outer_result, steps, diagnostics)

        output_path = outer_result.output_path
        safety_result = self.extraction_safety_checker.check(output_path)
        if not safety_result.safe:
            reason = "; ".join(safety_result.reasons)
            steps.append(f"中间输出安全检查失败: {reason}")
            return CompositeExecutionResult(
                active_plan,
                replace(
                    outer_result,
                    success=False,
                    message="中间输出安全检查失败",
                    error=reason,
                    status=ExtractionStatus.FAILED,
                ),
                steps,
                diagnostics,
            )

        try:
            intermediate_path = self._find_intermediate_file(plan, output_path)
            archive_info = self.analyzer.analyze(intermediate_path)
        except (OSError, ValueError) as error:
            steps.append(f"无法确认中间文件真实格式: {error}")
            return CompositeExecutionResult(
                active_plan,
                ExtractionResult(
                    success=False,
                    message="无法确认复合容器的中间格式",
                    output_path=output_path,
                    error=str(error),
                    tool_used=outer_result.tool_used,
                    status=ExtractionStatus.FAILED,
                ),
                steps,
                diagnostics,
            )

        hinted_format = (
            plan.container_chain[1].upper()
            if len(plan.container_chain) > 1
            else "UNKNOWN"
        )
        steps.append(
            f"中间文件重新分析: {intermediate_path}，"
            f"真实格式={archive_info.real_format}"
        )
        if archive_info.real_format.upper() != hinted_format:
            steps.append(
                f"容器链提示不一致: 提示={hinted_format}，"
                f"实际={archive_info.real_format}；采用实际分析结果"
            )

        content_info = self.content_inspector.inspect(archive_info)
        inner_plan = self.strategy.create_plan(archive_info, content_info)
        if not inner_plan.can_execute or inner_plan.selected_tool is None:
            error = inner_plan.message or "中间文件格式无法执行"
            return CompositeExecutionResult(
                inner_plan,
                ExtractionResult(
                    success=False,
                    message="无法创建内层执行计划",
                    output_path=output_path,
                    error=error,
                    status=ExtractionStatus.FAILED,
                ),
                steps,
                diagnostics,
            )
        if inner_plan.is_composite:
            return CompositeExecutionResult(
                inner_plan,
                ExtractionResult(
                    success=False,
                    message="暂不在单次复合执行中嵌套更多复合容器",
                    output_path=output_path,
                    error="请交由受深度限制的 Pipeline 继续处理",
                    status=ExtractionStatus.FAILED,
                ),
                steps,
                diagnostics,
            )

        steps.append(
            f"内层计划采用重新分析结果: {inner_plan.detected_format}"
        )
        active_plan, inner_result, stage_steps = execute_stage(inner_plan)
        steps.extend(stage_steps)
        diagnostics.append(
            self._diagnostic("COMPOSITE_INNER", active_plan, inner_result)
        )
        return CompositeExecutionResult(
            active_plan, inner_result, steps, diagnostics
        )

    @staticmethod
    def _diagnostic(
        stage: str,
        plan: ExtractionPlan,
        result: ExtractionResult,
    ) -> ExtractionStageDiagnostic:
        reason = " ".join((result.error or result.message).split())[:500]
        return ExtractionStageDiagnostic(
            stage=stage,
            detected_format=plan.detected_format,
            tool=result.tool_used or plan.selected_tool,
            status=result.status,
            error_type=result.status.value,
            normalized_reason=reason,
        )

    def _find_intermediate_file(
        self, plan: ExtractionPlan, output_path: Path | None
    ) -> Path:
        """定位 LZ4 的单一输出文件，不根据内部格式提示选择文件。"""
        if output_path is None or not output_path.is_dir():
            raise FileNotFoundError("外层解压结果目录不存在")

        expected_path = output_path / plan.archive_path.stem
        if expected_path.is_file():
            return expected_path

        discovered = self.archive_finder.find(output_path)
        if len(discovered) != 1:
            raise ValueError(
                f"预期一个中间压缩文件，实际发现 {len(discovered)} 个"
            )
        return discovered[0].file_path
