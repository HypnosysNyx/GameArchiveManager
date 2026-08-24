"""GameArchiveManager 简单命令行入口。"""

import getpass
from pathlib import Path

from application.app_service import GameArchiveService
from application.progress import BatchProgressEvent
from application.runtime_paths import default_config_path
from config.config_loader import ConfigLoader
from report.models import BatchTaskReport, TaskReport
from pipeline.models import PipelineProgress
from task.models import Task
from task.task_analyzer import AnalysisStatus, TaskAnalysisResult, TaskAnalyzer
from task.input_relationship import (
    InputArchiveRelationshipResolver,
    InputRelationshipType,
)
from tools.models import ToolName
from tools.tool_manager import ToolManager
from version import APP_NAME, APP_VERSION, BUILD_TYPE
from organizer.delivery_units import DeliveryUnit
from recovery.manual import (
    ManualPasswordAction,
    ManualPasswordRequest,
    ManualPasswordResponse,
)
from rules.container_policy import ContainerRole


def print_startup_info(tool_manager: ToolManager | None = None) -> None:
    """显示应用版本和三种外部工具的只读状态。"""
    if tool_manager is None:
        settings = ConfigLoader(default_config_path()).load()
        tool_manager = ToolManager(settings=settings)

    print(APP_NAME)
    print(f"版本: {APP_VERSION}")
    print(f"构建类型: {BUILD_TYPE}")
    print("\n工具状态:")
    for tool_name, display_name in (
        (ToolName.SEVEN_ZIP, "7-Zip"),
        (ToolName.WINRAR, "WinRAR"),
        (ToolName.LZ4, "LZ4"),
    ):
        tool_info = tool_manager.get_tool_status(tool_name)
        if tool_info.verified:
            status = "可用"
        elif tool_info.available:
            status = "验证失败"
        else:
            status = "未找到"
        print(f"\n{display_name}:")
        print(f"路径: {tool_info.path or '未找到'}")
        print(f"版本: {tool_info.version or '未知'}")
        print(f"状态: {status}")


def count_skipped_archives(result: TaskAnalysisResult) -> int:
    """按当前任务执行规则统计会被跳过的初始压缩包。"""
    ignored_paths = [path.resolve() for path in result.ignored_items]
    skipped_count = 0

    for archive_info in result.archive_results:
        archive = archive_info.file_path.resolve()
        if any(
            archive == ignored or ignored in archive.parents
            for ignored in ignored_paths
        ):
            skipped_count += 1
    return skipped_count


def print_report(report: TaskReport) -> None:
    """把 TaskReport 转换为简洁的控制台输出。"""
    print(f"\n{APP_NAME} {report.app_version} ({report.build_type})")
    status = report.task_status or (
        "FAILED"
        if report.failed_count > 0 and report.success_count == 0
        else "COMPLETED"
    )

    print("\n任务报告")
    print(f"任务状态: {status}")
    print(f"成功数量: {report.success_count}")
    print(f"失败数量: {report.failed_count}")
    print(f"跳过数量: {report.skipped_count}")
    print(f"人工密码尝试次数: {report.manual_password_attempt_count}")
    if report.password_recovery_result:
        print(f"密码恢复结果: {report.password_recovery_result}")
    print(f"输出路径（{len(report.output_paths)}）:")
    if report.output_paths:
        for output_path in report.output_paths:
            print(f"  - {output_path}")
    else:
        print("  无")
    print(f"摘要: {report.summary}")
    if report.input_relationships:
        print("输入归档关系:")
        for relationship in report.input_relationships:
            if relationship.related_path is None:
                continue
            print(f"  来源: {relationship.source_path}")
            print(f"  关联来源: {relationship.related_path}")
            print(f"  关系: {relationship.relationship_type.value}")
            print(f"  验证: {relationship.verification_status.value}")
            if relationship.canonical_input is not None:
                print(f"  默认执行: {relationship.canonical_input}")
            if relationship.suppressed_input is not None:
                print(f"  保留但不重复执行: {relationship.suppressed_input}")
    duplicate_records = [
        item
        for item in report.duplicate_contents
        if item.status.value == "DUPLICATE_CONTENT"
    ]
    if duplicate_records:
        print("最终重复内容:")
        for item in duplicate_records:
            print(f"  内容: {item.content_path}")
            print(f"  与以下结果相同: {item.duplicate_of}")
            print("  已保留执行记录，未重复复制最终内容")
    if report.failure_details:
        print("失败详情:")
        for detail in report.failure_details:
            tool_name = detail.tool.value if detail.tool else "无"
            print(f"  文件路径: {detail.file_path}")
            print(f"  失败阶段: {detail.stage}")
            print(f"  工具: {tool_name}")
            print(f"  错误类型: {detail.error_type}")
            print(f"  原因: {detail.reason}")
            if detail.composite_stage:
                print(f"  复合阶段: {detail.composite_stage}")
            if detail.extraction_status:
                print(f"  最终解压状态: {detail.extraction_status}")
            print(f"  密码尝试次数: {detail.password_attempt_count}")
            print(f"  人工密码尝试次数: {detail.manual_password_attempt_count}")
            if detail.password_recovery_result:
                print(f"  密码恢复结果: {detail.password_recovery_result}")
            if detail.fallback_tools_attempted:
                print(
                    "  已尝试备用工具: "
                    + ", ".join(tool.value for tool in detail.fallback_tools_attempted)
                )
            for stage in detail.stage_details:
                print(
                    "  子阶段: "
                    f"{stage.get('stage')} / {stage.get('format')} / "
                    f"{stage.get('tool') or '无'} / {stage.get('status')}"
                )
            if detail.missing_files:
                print("  缺少文件列表:")
                for missing_file in detail.missing_files:
                    print(f"    - {missing_file}")
    if report.residual_internal_directories:
        print("残留内部目录:")
        for residual in report.residual_internal_directories:
            print(f"  路径: {residual.path}")
            print(f"  状态: {residual.status}")
            print(f"  原因: {residual.reason}")
    preserved_containers = [
        decision
        for decision in report.container_role_decisions
        if decision.role is ContainerRole.CONTENT_CONTAINER
    ]
    if preserved_containers:
        print("已保留的内容容器（未自动拆解）:")
        for decision in preserved_containers:
            print(f"  文件: {decision.path}")
            print(f"  容器角色: {decision.role.value}")
            print(f"  原因: {decision.reason}")


def print_batch_report(report: BatchTaskReport) -> None:
    """显示多个任务的统一汇总。"""
    print("\n批量任务汇总")
    print(f"成功数量: {report.success_count}")
    print(f"失败数量: {report.failed_count}")
    print(f"跳过数量: {report.skipped_count}")
    print(f"输出路径（{len(report.output_paths)}）:")
    if report.output_paths:
        for output_path in report.output_paths:
            print(f"  - {output_path}")
    else:
        print("  无")


def print_batch_progress(event: BatchProgressEvent) -> None:
    """Display one batch progress event without changing task execution."""
    print(f"\n当前任务: {event.current_task}/{event.total_tasks}")
    print(f"当前任务路径: {event.task_path}")
    if event.event_type == "PIPELINE_PROGRESS":
        if event.phase:
            print(f"当前阶段: {event.phase}")
        if event.current_archive is not None:
            print(f"当前压缩包: {event.current_archive}")
        print(f"当前处理压缩包数量: {event.archive_count}")
        print(f"已完成数量: {event.completed_count}")
        print(f"失败数量: {event.failed_count}")
    elif event.event_type == "TASK_FINISHED":
        print(f"当前任务完成状态: {event.status}")
    else:
        print("当前任务完成状态: RUNNING")


def print_pipeline_progress(event: PipelineProgress) -> None:
    """Display the current recursive processing phase for one task."""
    print(f"\n当前阶段: {event.phase.value}")
    if event.current_archive is not None:
        print(f"当前压缩包: {event.current_archive}")
    print(f"当前处理压缩包数量: {event.archive_count}")
    print(f"已完成数量: {event.completed_count}")
    print(f"失败数量: {event.failed_count}")


def select_delivery_units(units: list[DeliveryUnit]) -> list[int]:
    """Close the CLI selection loop for genuinely competing content roots."""
    print("\n发现多个最终内容候选：")
    for index, unit in enumerate(units, start=1):
        print(f"[{index}] {unit.terminal_content_root}")
    all_index = len(units) + 1
    print(f"[{all_index}] 全部保留")
    while True:
        value = input("请选择: ").strip()
        if value.isdigit():
            selected = int(value)
            if selected == all_index:
                return list(range(len(units)))
            if 1 <= selected <= len(units):
                return [selected - 1]
        print("请输入有效编号。")


def prompt_manual_password(
    request: ManualPasswordRequest,
) -> ManualPasswordResponse:
    """Interactive adapter; passwords are read without normal terminal echo."""
    print("\n自动密码均未成功。")
    print(f"当前归档: {request.archive_path}")
    print(f"归档格式: {request.archive_format}")
    if request.composite_stage:
        print(f"当前复合阶段: {request.composite_stage}")
    if request.manual_attempt_count:
        print("上一次人工密码尝试未成功。")
    while True:
        print("[I] 输入新密码")
        print("[S] 跳过当前归档")
        print("[C] 取消整个任务")
        choice = input("请选择: ").strip().upper()
        if choice == "I":
            password = getpass.getpass("请输入密码（不会回显）: ")
            if not password:
                print("密码不能为空。")
                continue
            return ManualPasswordResponse(
                ManualPasswordAction.INPUT_PASSWORD, password=password
            )
        if choice == "S":
            return ManualPasswordResponse(ManualPasswordAction.SKIP_ARCHIVE)
        if choice == "C":
            return ManualPasswordResponse(ManualPasswordAction.CANCEL_TASK)
        print("请输入 I、S 或 C。")


class CliSessionController:
    """Keep CLI navigation alive while task execution stays in the service."""

    EXIT_CHOICES = {"0", "Q", "QUIT", "EXIT"}

    def __init__(self, service: GameArchiveService) -> None:
        self.service = service
        self.analyzer = service.task_executor.task_analyzer
        self.relationship_resolver = (
            service.task_executor.input_relationship_resolver
        )
        self.last_task_reports: list[TaskReport] = []
        self.last_batch_report: BatchTaskReport | None = None

    def run_session(self) -> None:
        """Accept a path immediately; keep the full menu as a secondary tool."""
        self._show_fast_path_help()
        while True:
            try:
                raw_value = input("> ")
            except (EOFError, KeyboardInterrupt, StopIteration):
                print("\n已退出 GameArchiveManager。")
                return

            value = self._normalize_path_input(raw_value)
            if not value:
                continue
            command = value.upper()
            if command in self.EXIT_CHOICES:
                print("已退出 GameArchiveManager。")
                return
            if command in {"M", "MENU"}:
                self._run_menu()
                continue

            candidate = Path(value).expanduser()
            if candidate.exists():
                self._start_task_from_paths([value])
                continue

            # Preserve the previous numeric shortcuts without making them the
            # primary interaction. Existing paths always win over shortcuts.
            if command == "1":
                self.run_new_task()
            elif command == "2":
                self.show_last_result()
            elif command == "3":
                self.show_tool_status()
            elif command == "4":
                self.show_settings()
            else:
                print("路径不存在或命令无效，请重新输入。")

    @staticmethod
    def _show_fast_path_help() -> None:
        print(f"\n{APP_NAME} {APP_VERSION} RC")
        print("输入文件或目录路径直接开始任务")
        print("M = 菜单")
        print("Q = 退出")

    def _run_menu(self) -> None:
        """Run one secondary menu action, then return to the fast prompt."""
        self._show_main_menu()
        try:
            choice = input("请选择: ").strip().upper()
        except (EOFError, KeyboardInterrupt, StopIteration):
            print("\n已返回路径输入。")
            return
        if choice in {"0", "B", "BACK"}:
            return
        if choice == "1":
            self.run_new_task()
        elif choice == "2":
            self.show_last_result()
        elif choice == "3":
            self.show_tool_status()
        elif choice == "4":
            self.show_settings()
        else:
            print("请输入有效菜单编号。")

    def _show_main_menu(self) -> None:
        print("\n完整菜单")
        print("1. 新建任务")
        print("2. 查看最近任务结果")
        print("3. 查看工具状态")
        print("4. 查看当前设置")
        print("0. 返回路径输入")

    def run_new_task(self) -> None:
        """Collect, preview, confirm, and execute one task batch."""
        task_paths = self._collect_task_paths()
        if not task_paths:
            return

        self._start_task_from_paths(task_paths)

    def _start_task_from_paths(self, task_paths: list[str]) -> None:
        """Shared preview/confirmation/execution path for fast and menu input."""

        self._preview_tasks(task_paths)
        if not self._confirm_execution():
            print("任务已取消，未执行解压。")
            self._wait_for_fast_prompt()
            return

        try:
            if len(task_paths) == 1:
                report = self.service.execute_task(
                    task_paths[0],
                    progress_callback=print_pipeline_progress,
                )
                self.last_task_reports = [report]
                self.last_batch_report = None
                print_report(report)
            else:
                batch_report = self.service.execute_tasks(
                    task_paths,
                    progress_callback=print_batch_progress,
                )
                self.last_task_reports = list(batch_report.task_reports)
                self.last_batch_report = batch_report
                for index, report in enumerate(
                    batch_report.task_reports, start=1
                ):
                    print(f"\n任务 {index} 报告")
                    print_report(report)
                print_batch_report(batch_report)
        except KeyboardInterrupt:
            print("\n当前任务已中断；程序会返回路径输入。")
        except Exception as error:
            print(f"任务执行失败: {type(error).__name__}")
        self._wait_for_fast_prompt()

    def _collect_task_paths(self) -> list[str]:
        print("请输入一个或多个任务路径。")
        print("第一个路径留空返回主菜单；添加后留空开始预览。")
        task_paths: list[str] = []
        while True:
            try:
                value = self._normalize_path_input(input("任务路径: "))
            except (EOFError, KeyboardInterrupt, StopIteration):
                print("\n已返回主菜单。")
                return []
            if not value:
                return task_paths
            if not Path(value).expanduser().exists():
                print("路径不存在，请重新输入；留空可返回主菜单。")
                continue
            task_paths.append(value)

    def _preview_tasks(self, task_paths: list[str]) -> None:
        print("\n全部任务预览")
        for index, task_path in enumerate(task_paths, start=1):
            print(f"\n任务 {index}")
            print(f"任务: {task_path}")
            try:
                analysis = self.analyzer.analyze(
                    Task(task_path=Path(task_path))
                )
            except Exception as error:
                print(f"分析失败: {type(error).__name__}")
                continue

            if analysis.analysis_status is AnalysisStatus.FAILED:
                print(f"分析失败: {analysis.error_message}")
                continue
            print(f"发现压缩包: {len(analysis.archive_results)}")
            print(f"跳过: {count_skipped_archives(analysis)}")
            self._preview_input_relationships(analysis)
        print("即将开始解压。")

    def _preview_input_relationships(
        self, analysis: TaskAnalysisResult
    ) -> None:
        try:
            ignored = [path.resolve() for path in analysis.ignored_items]
            processable = [
                item
                for item in analysis.archive_results
                if not any(
                    item.file_path.resolve() == path
                    or path in item.file_path.resolve().parents
                    for path in ignored
                )
            ]
            preview = self.relationship_resolver.resolve(processable)
            for relationship in preview.relationships:
                if relationship.relationship_type is not (
                    InputRelationshipType.CONFIRMED_OUTER_CONTAINS_EXISTING_INNER
                ):
                    continue
                print("检测到同一归档链:")
                print(f"  外层: {relationship.source_path}")
                print(f"  内层: {relationship.related_path}（内容已强验证相同）")
                print(f"  默认执行: {relationship.canonical_input}")
                print("  外层文件会保留，不会删除")
        except (OSError, ValueError, TypeError):
            print("输入归档关系预览暂时无法完成，将保守处理全部输入")

    @staticmethod
    def _confirm_execution() -> bool:
        while True:
            try:
                confirmation = input("是否继续？(Y/N): ").strip().upper()
            except (EOFError, KeyboardInterrupt, StopIteration):
                return False
            if confirmation == "Y":
                return True
            if confirmation == "N":
                return False
            print("请输入 Y 或 N。")

    def show_last_result(self) -> None:
        if not self.last_task_reports:
            print("当前会话还没有任务结果。")
            return
        for report in self.last_task_reports:
            print_report(report)
        if self.last_batch_report is not None:
            print_batch_report(self.last_batch_report)

    def show_tool_status(self) -> None:
        print("\n工具状态")
        for tool_name, display_name in (
            (ToolName.SEVEN_ZIP, "7-Zip"),
            (ToolName.WINRAR, "WinRAR"),
            (ToolName.LZ4, "LZ4"),
        ):
            info = self.service.tool_manager.get_tool_status(tool_name)
            status = "FOUND" if info.verified else "NOT FOUND"
            print(f"{display_name}: {status}")
            if info.path is not None:
                print(f"  路径: {info.path}")

    def show_settings(self) -> None:
        settings = self.service.settings
        print("\n当前设置（config.json 修改后需重启生效）")
        for field_name in (
            "ignore_android",
            "ignore_AZ",
            "max_recursive_depth",
            "max_archive_tasks",
            "max_initial_archive_tasks",
            "max_password_attempts",
            "seven_zip_path",
            "winrar_path",
            "lz4_path",
        ):
            print(f"{field_name}: {getattr(settings, field_name)}")

    @staticmethod
    def _normalize_path_input(value: str) -> str:
        """Trim whitespace and one pair of drag-and-drop wrapper quotes."""
        normalized = value.strip()
        if (
            len(normalized) >= 2
            and normalized[0] == '"'
            and normalized[-1] == '"'
        ):
            normalized = normalized[1:-1]
        return normalized

    @staticmethod
    def _wait_for_fast_prompt() -> None:
        try:
            input("\n[Enter] 返回路径输入")
        except (EOFError, KeyboardInterrupt, StopIteration):
            pass


def main() -> int:
    """Create one application session; every task remains service-managed."""
    try:
        service = GameArchiveService()
    except Exception as error:
        print(f"程序初始化失败: {type(error).__name__}")
        return 1

    service.content_selection_callback = select_delivery_units
    service.password_recovery_callback = prompt_manual_password
    print_startup_info(service.tool_manager)
    print("GameArchiveManager 启动成功")
    CliSessionController(service).run_session()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
