"""协调单个压缩包的分析、计划、解压和有限密码重试。"""

from dataclasses import replace
from pathlib import Path

from analyzer.archive_analyzer import ArchiveAnalyzer
from config.settings import Settings
from execution.models import ExtractionPlan
from execution.output_paths import OutputPathGenerator
from execution.strategy import ExecutionStrategy
from extractor.composite import CompositeExtractor
from extractor.dispatcher import ExtractorAdapter, ExtractorDispatcher
from extractor.embedded import EmbeddedExtractor
from extractor.extractor_models import (
    ExtractionResult,
    ExtractionStatus,
)
from password.models import PasswordCandidate
from password.session_store import SessionPasswordStore
from recovery.manual import (
    ManualPasswordAction,
    ManualPasswordCallback,
    ManualPasswordRequest,
)
from recovery.password_executor import PasswordRetryExecutor
from recovery.password_recovery import PasswordRecoveryEngine
from security.archive_content_inspector import ArchiveContentInspector
from security.extraction_safety import ExtractionSafetyChecker
from tools.models import ToolName
from tools.tool_manager import ToolManager

from coordinator.models import CoordinatorResult


class _CachedFirstResultExtractor:
    """让 PasswordRetryExecutor 复用已经执行过的首次结果。"""

    def __init__(
        self, extractor: ExtractorAdapter, first_result: ExtractionResult
    ) -> None:
        self.extractor = extractor
        self.first_result = first_result
        self.first_result_returned = False

    def extract(self, plan, password=None) -> ExtractionResult:
        """首次无密码调用返回缓存，后续密码调用交给真实执行器。"""
        if password is None and not self.first_result_returned:
            self.first_result_returned = True
            return self.first_result
        return self.extractor.extract(plan, password=password)


class ExtractionCoordinator:
    """执行一个压缩包的单阶段协调流程。"""

    MAX_MANUAL_PASSWORD_ATTEMPTS = 100

    def __init__(
        self,
        analyzer: ArchiveAnalyzer | None = None,
        strategy: ExecutionStrategy | None = None,
        dispatcher: ExtractorDispatcher | None = None,
        extractor: ExtractorAdapter | None = None,
        extraction_safety_checker: ExtractionSafetyChecker | None = None,
        content_inspector: ArchiveContentInspector | None = None,
        composite_extractor: CompositeExtractor | None = None,
        embedded_extractor: EmbeddedExtractor | None = None,
        settings: Settings | None = None,
    ) -> None:
        active_settings = settings or Settings()
        self.analyzer = analyzer or ArchiveAnalyzer()
        self.strategy = strategy or ExecutionStrategy(active_settings)
        if dispatcher is not None and extractor is not None:
            raise ValueError("dispatcher 和兼容参数 extractor 不能同时传入")
        # extractor 参数只用于兼容旧调用方和测试替身，仍统一包装为 Dispatcher。
        self.dispatcher = dispatcher or ExtractorDispatcher(
            seven_zip_extractor=extractor,
            settings=active_settings,
        )
        self.extraction_safety_checker = (
            extraction_safety_checker or ExtractionSafetyChecker(active_settings)
        )
        dispatcher_tool_manager = getattr(self.dispatcher, "tool_manager", None)
        self.content_inspector = content_inspector or ArchiveContentInspector(
            tool_manager=(
                dispatcher_tool_manager
                if isinstance(dispatcher_tool_manager, ToolManager)
                else None
            ),
            timeout_seconds=min(active_settings.extraction_timeout_seconds, 30),
        )
        self.composite_extractor = composite_extractor or CompositeExtractor(
            analyzer=self.analyzer,
            strategy=self.strategy,
            content_inspector=self.content_inspector,
            extraction_safety_checker=self.extraction_safety_checker,
        )
        self.embedded_extractor = embedded_extractor or EmbeddedExtractor(
            analyzer=self.analyzer
        )

    def process(
        self,
        archive_path: str | Path,
        password_candidates: list[PasswordCandidate] | None = None,
        max_password_attempts: int = 20,
        manual_password_callback: ManualPasswordCallback | None = None,
        session_password_store: SessionPasswordStore | None = None,
    ) -> CoordinatorResult:
        """分析并处理一个压缩包，不递归、不整理、不删除文件。"""
        archive = Path(archive_path).expanduser().resolve()
        candidates = password_candidates.copy() if password_candidates else []
        steps: list[str] = []

        if not 0 <= max_password_attempts <= 100:
            return CoordinatorResult(
                success=False,
                archive_path=archive,
                steps=steps,
                error_message="max_password_attempts 必须在 0 到 100 之间",
            )

        try:
            steps.append("开始分析文件真实格式")
            archive_info = self.analyzer.analyze(archive)
            steps.append(
                f"分析结果: 扩展名={archive_info.extension or '无'}, "
                f"真实格式={archive_info.real_format}, "
                f"是否伪装={archive_info.is_fake_extension}"
            )

            if archive_info.is_multi_volume and archive_info.missing_volume_files:
                content_info = None
                steps.append("分卷不完整，跳过内容预检查")
            else:
                content_info = self.content_inspector.inspect(archive_info)
                steps.append(
                    "内容预检查: "
                    f"文件数量={content_info.file_count}, "
                    f"预计大小={content_info.estimated_size} 字节"
                )
                for warning in content_info.warnings:
                    steps.append(f"内容预检查警告: {warning}")

            plan = self.strategy.create_plan(archive_info, content_info)
            selected_tool = (
                plan.selected_tool.value if plan.selected_tool else "无"
            )
            steps.append(f"执行计划工具: {selected_tool}")
            steps.append(f"计划输出目录: {plan.output_path or '无'}")

            if plan.missing_volume_files:
                missing_names = ", ".join(
                    str(path) for path in plan.missing_volume_files
                )
                steps.append(f"缺少分卷文件: {missing_names}")
                failed_result = ExtractionResult(
                    success=False,
                    message="缺少分卷文件",
                    output_path=plan.output_path,
                    error=f"缺少分卷文件: {missing_names}",
                    tool_used=plan.selected_tool,
                    status=ExtractionStatus.FAILED,
                )
                return CoordinatorResult(
                    success=False,
                    archive_path=plan.archive_path,
                    extraction_result=failed_result,
                    steps=steps,
                    error_message=failed_result.error,
                    failure_stage="VOLUME_DETECTION",
                    error_type="MISSING_VOLUME",
                    user_message="缺少分卷文件",
                    missing_files=plan.missing_volume_files.copy(),
                )

            if plan.is_embedded_archive:
                steps.append(
                    "提取内嵌压缩包: "
                    f"offset={plan.embedded_offset}, "
                    f"format={plan.embedded_container_format}"
                )
                embedded_result = self.embedded_extractor.extract(plan)
                steps.append(
                    "内嵌压缩包提取状态: "
                    f"{embedded_result.status.value} - {embedded_result.message}"
                )
                if embedded_result.status is ExtractionStatus.SUCCESS:
                    return self._validate_success_result(
                        archive, embedded_result, steps
                    )
                return CoordinatorResult(
                    success=False,
                    archive_path=archive,
                    extraction_result=embedded_result,
                    steps=steps,
                    error_message=(
                        embedded_result.error or embedded_result.message
                    ),
                    failure_stage="EMBEDDED_EXTRACTION",
                    error_type="EMBEDDED_EXTRACTION_FAILED",
                    user_message="无法提取内嵌压缩包",
                )

            if plan.is_composite:
                composite_result = self.composite_extractor.extract(
                    plan, self._execute_plan_with_fallback
                )
                active_plan = composite_result.active_plan
                first_result = replace(
                    composite_result.extraction_result,
                    stage_diagnostics=composite_result.stage_diagnostics,
                )
                steps.extend(composite_result.steps)
            else:
                active_plan, first_result, execution_steps = (
                    self._execute_plan_with_fallback(plan)
                )
                steps.extend(execution_steps)

            if first_result.status is ExtractionStatus.SUCCESS:
                return self._validate_success_result(
                    archive, first_result, steps
                )

            if first_result.status is not ExtractionStatus.PASSWORD_REQUIRED:
                return self._failed_result(archive, first_result, steps)

            steps.append(f"进入密码恢复流程，候选数量: {len(candidates)}")
            recovery_engine = PasswordRecoveryEngine(
                extraction_result=first_result,
                password_candidates=candidates,
                archive_path=active_plan.archive_path,
                max_attempts=max_password_attempts,
            )
            cached_extractor = _CachedFirstResultExtractor(
                self.dispatcher, first_result
            )
            retry_executor = PasswordRetryExecutor(
                plan=active_plan,
                recovery_engine=recovery_engine,
                extractor=cached_extractor,
                max_password_attempts=max_password_attempts,
            )
            final_result = retry_executor.execute()

            for index, attempt_result in enumerate(
                retry_executor.attempt_results[1:], start=1
            ):
                steps.append(
                    f"密码尝试 {index}: {attempt_result.status.value}"
                    f" - {attempt_result.message}"
                )

            manual_attempt_count = 0
            manual_password_used = False
            password_recovery_result = ""
            control_action = ""
            if (
                final_result.status
                in (ExtractionStatus.PASSWORD_REQUIRED, ExtractionStatus.WRONG_PASSWORD)
                and manual_password_callback is not None
            ):
                (
                    final_result,
                    manual_attempt_count,
                    manual_password_used,
                    password_recovery_result,
                    control_action,
                ) = self._run_manual_password_recovery(
                    active_plan,
                    final_result,
                    manual_password_callback,
                    session_password_store,
                    steps,
                    automatic_attempt_count=len(
                        retry_executor.attempt_results[1:]
                    ),
                    composite_stage=self._composite_stage(first_result),
                )

            diagnostics = first_result.stage_diagnostics.copy()
            if diagnostics and diagnostics[-1].stage == "COMPOSITE_INNER":
                diagnostics[-1] = replace(
                    diagnostics[-1],
                    status=final_result.status,
                    error_type=final_result.status.value,
                    normalized_reason=self._normalized_reason(final_result),
                    tool=final_result.tool_used or diagnostics[-1].tool,
                )
            final_result = replace(
                final_result,
                stage_diagnostics=diagnostics,
                tools_attempted=(
                    final_result.tools_attempted
                    or first_result.tools_attempted.copy()
                ),
            )
            steps.append(f"最终解压状态: {final_result.status.value}")
            if final_result.status is ExtractionStatus.SUCCESS:
                return self._validate_success_result(
                    archive,
                    final_result,
                    steps,
                    manual_password_attempt_count=manual_attempt_count,
                    manual_password_used=manual_password_used,
                    password_recovery_result=password_recovery_result,
                )
            return self._failed_result(
                archive,
                final_result,
                steps,
                manual_password_attempt_count=manual_attempt_count,
                manual_password_used=manual_password_used,
                password_recovery_result=password_recovery_result,
                control_action=control_action,
            )
        except (OSError, ValueError) as error:
            steps.append(f"协调流程异常: {error}")
            return CoordinatorResult(
                success=False,
                archive_path=archive,
                steps=steps,
                error_message=str(error),
            )

    def _execute_plan_with_fallback(
        self, plan: ExtractionPlan
    ) -> tuple[ExtractionPlan, ExtractionResult, list[str]]:
        """执行一个已分析阶段，并按有限列表尝试允许的备用工具。"""
        execution_steps: list[str] = []
        active_plan = plan
        tools_attempted: list[ToolName] = []
        if active_plan.selected_tool is not None:
            tools_attempted.append(active_plan.selected_tool)
        result = self.dispatcher.extract(active_plan)
        execution_steps.append(
            f"工具 {active_plan.selected_tool.value if active_plan.selected_tool else '无'}"
            f" 执行状态: {result.status.value} - {result.message}"
        )

        for fallback_tool in plan.fallback_tools:
            if result.status in (
                ExtractionStatus.SUCCESS,
                ExtractionStatus.PASSWORD_REQUIRED,
                ExtractionStatus.WRONG_PASSWORD,
            ):
                break
            if not self._allows_fallback(result):
                execution_steps.append("当前失败类型不允许切换备用工具")
                break

            active_plan = self._create_fallback_plan(plan, fallback_tool)
            tools_attempted.append(fallback_tool)
            execution_steps.append(f"切换备用工具: {fallback_tool.value}")
            execution_steps.append(
                f"备用工具输出目录: {active_plan.output_path or '无'}"
            )
            result = self.dispatcher.extract(active_plan)
            execution_steps.append(
                f"备用工具状态: {result.status.value} - {result.message}"
            )

        result = replace(result, tools_attempted=tools_attempted)
        return active_plan, result, execution_steps

    @staticmethod
    def _allows_fallback(extraction_result: ExtractionResult) -> bool:
        """只允许工具缺失或非密码、非明显损坏的普通失败切换工具。"""
        if extraction_result.status is ExtractionStatus.TOOL_NOT_FOUND:
            return True
        if extraction_result.status is not ExtractionStatus.FAILED:
            return False

        error_text = (
            f"{extraction_result.message}\n{extraction_result.error}"
        ).casefold()
        blocked_markers = (
            "corrupt",
            "damaged",
            "crc error",
            "data error",
            "unexpected end",
            "headers error",
            "损坏",
            "校验错误",
            "数据错误",
            "意外结束",
            "输出目录已存在",
            "不会覆盖",
            "压缩文件不存在",
            "unsupported format",
            "不支持的压缩格式",
        )
        return not any(marker in error_text for marker in blocked_markers)

    @staticmethod
    def _create_fallback_plan(
        original_plan: ExtractionPlan, fallback_tool: ToolName
    ) -> ExtractionPlan:
        """为备用工具复制计划；已有输出目录时改用安全的独立目录。"""
        output_path = original_plan.output_path
        if output_path is not None and output_path.exists():
            output_path = OutputPathGenerator.next_available(
                output_path.with_name(
                    f"{output_path.name}_{fallback_tool.value.casefold()}"
                )
            )
        return replace(
            original_plan,
            selected_tool=fallback_tool,
            output_path=output_path,
        )

    def _validate_success_result(
        self,
        archive_path: Path,
        extraction_result: ExtractionResult,
        steps: list[str],
        manual_password_attempt_count: int = 0,
        manual_password_used: bool = False,
        password_recovery_result: str = "",
    ) -> CoordinatorResult:
        """解压成功后检查输出目录，超限时保留文件并标记失败。"""
        safety_result = self.extraction_safety_checker.check(
            extraction_result.output_path
        )
        for warning in safety_result.warnings:
            steps.append(f"解压后安全警告: {warning}")

        if not safety_result.safe:
            reason = "; ".join(safety_result.reasons)
            steps.append(f"解压后安全检查失败: {reason}")
            failed_result = replace(
                extraction_result,
                success=False,
                message="解压后安全检查失败",
                error=reason,
                status=ExtractionStatus.FAILED,
            )
            return self._failed_result(archive_path, failed_result, steps)

        steps.append("解压后安全检查通过")
        return CoordinatorResult(
            success=True,
            archive_path=archive_path,
            extraction_result=extraction_result,
            steps=steps,
            password_attempt_count=self._password_attempt_count(steps),
            fallback_tools_attempted=self._fallback_tools(extraction_result),
            final_tool=extraction_result.tool_used,
            composite_stage=self._composite_stage(extraction_result),
            stage_diagnostics=extraction_result.stage_diagnostics.copy(),
            manual_password_attempt_count=manual_password_attempt_count,
            manual_password_used=manual_password_used,
            password_recovery_result=password_recovery_result,
        )

    @classmethod
    def _failed_result(
        cls,
        archive_path: Path,
        extraction_result: ExtractionResult,
        steps: list[str],
        manual_password_attempt_count: int = 0,
        manual_password_used: bool = False,
        password_recovery_result: str = "",
        control_action: str = "",
    ) -> CoordinatorResult:
        """统一创建失败的协调结果。"""
        attempts = cls._password_attempt_count(steps)
        error_type = extraction_result.status.value
        if extraction_result.status in (
            ExtractionStatus.PASSWORD_REQUIRED,
            ExtractionStatus.WRONG_PASSWORD,
        ):
            error_type = "PASSWORD_CANDIDATES_EXHAUSTED"
        user_message = cls._normalized_reason(extraction_result)
        if control_action == "SKIP_ARCHIVE":
            error_type = "USER_SKIPPED_PASSWORD_ARCHIVE"
            user_message = "用户跳过需要密码的当前归档"
        elif control_action == "CANCEL_TASK":
            error_type = "USER_CANCELLED_TASK"
            user_message = "用户取消任务"
        return CoordinatorResult(
            success=False,
            archive_path=archive_path,
            extraction_result=extraction_result,
            steps=steps,
            error_message=extraction_result.error or extraction_result.message,
            failure_stage=(
                "PASSWORD_RECOVERY"
                if extraction_result.status
                in (ExtractionStatus.PASSWORD_REQUIRED, ExtractionStatus.WRONG_PASSWORD)
                else (
                    "COMPOSITE_EXTRACTION"
                    if extraction_result.stage_diagnostics
                    else "EXTRACTION"
                )
            ),
            error_type=error_type,
            user_message=user_message,
            password_attempt_count=attempts,
            fallback_tools_attempted=cls._fallback_tools(extraction_result),
            final_tool=extraction_result.tool_used,
            composite_stage=cls._composite_stage(extraction_result),
            stage_diagnostics=extraction_result.stage_diagnostics.copy(),
            manual_password_attempt_count=manual_password_attempt_count,
            manual_password_used=manual_password_used,
            password_recovery_result=password_recovery_result,
            control_action=control_action,
        )

    def _run_manual_password_recovery(
        self,
        plan: ExtractionPlan,
        last_result: ExtractionResult,
        callback: ManualPasswordCallback,
        session_store: SessionPasswordStore | None,
        steps: list[str],
        automatic_attempt_count: int,
        composite_stage: str,
    ) -> tuple[ExtractionResult, int, bool, str, str]:
        """Retry only the active failed stage using explicit UI decisions."""
        attempts = 0
        result = last_result
        while attempts < self.MAX_MANUAL_PASSWORD_ATTEMPTS:
            request = ManualPasswordRequest(
                archive_path=plan.archive_path,
                archive_format=plan.detected_format,
                status=result.status,
                automatic_attempt_count=automatic_attempt_count,
                manual_attempt_count=attempts,
                composite_stage=composite_stage,
            )
            response = callback(request)
            if response.action is ManualPasswordAction.SKIP_ARCHIVE:
                steps.append("用户跳过当前密码归档")
                return result, attempts, False, "SKIPPED", "SKIP_ARCHIVE"
            if response.action is ManualPasswordAction.CANCEL_TASK:
                steps.append("用户取消当前任务")
                return result, attempts, False, "CANCELLED", "CANCEL_TASK"
            if response.action is not ManualPasswordAction.INPUT_PASSWORD:
                raise ValueError("未知的人工密码恢复动作")
            if not response.password:
                steps.append("人工密码输入为空，未执行解压")
                continue

            attempts += 1
            retry_plan = replace(
                plan,
                output_path=self._manual_retry_output_path(plan),
                requires_password=False,
            )
            result = self.dispatcher.extract(
                retry_plan, password=response.password
            )
            steps.append(f"人工密码尝试 {attempts}: {result.status.value}")
            if result.status is ExtractionStatus.SUCCESS:
                if session_store is not None:
                    session_store.add_verified(response.password)
                return result, attempts, True, "SUCCESS", ""
            if result.status not in (
                ExtractionStatus.PASSWORD_REQUIRED,
                ExtractionStatus.WRONG_PASSWORD,
            ):
                return result, attempts, False, "FAILED", ""

        steps.append("人工密码尝试达到安全上限")
        return result, attempts, False, "ATTEMPTS_EXHAUSTED", ""

    @staticmethod
    def _manual_retry_output_path(plan: ExtractionPlan) -> Path | None:
        output = plan.output_path
        if output is None or not output.exists():
            return output
        return OutputPathGenerator.next_available(
            output.parent / f"{output.name}_manual_password_attempt"
        )

    @staticmethod
    def _password_attempt_count(steps: list[str]) -> int:
        return sum(step.startswith("密码尝试 ") for step in steps)

    @staticmethod
    def _fallback_tools(result: ExtractionResult) -> list[ToolName]:
        return result.tools_attempted[1:]

    @staticmethod
    def _composite_stage(result: ExtractionResult) -> str:
        if not result.stage_diagnostics:
            return ""
        return result.stage_diagnostics[-1].stage

    @staticmethod
    def _normalized_reason(result: ExtractionResult) -> str:
        if result.status is ExtractionStatus.WRONG_PASSWORD:
            return "密码错误；候选密码已耗尽"
        if result.status is ExtractionStatus.PASSWORD_REQUIRED:
            return "压缩包需要密码，但没有可用的成功候选"
        if result.status is ExtractionStatus.TOOL_NOT_FOUND:
            return "外部工具不存在或未通过验证"
        reason = " ".join((result.error or result.message).split())
        return reason[:500]
