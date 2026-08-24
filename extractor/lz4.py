"""使用外部 lz4.exe 执行单个 LZ4 文件的解压。"""

import subprocess
from pathlib import Path

from config.settings import Settings
from cleanup.runtime_tracker import register_created_directory
from execution.models import ExtractionPlan
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from tools.models import ToolName
from tools.tool_manager import ToolManager


class Lz4Extractor:
    """调用 lz4.exe 解压外层 LZ4，不处理递归或后续容器。"""

    def __init__(
        self,
        tool_manager: ToolManager | None = None,
        timeout_seconds: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        active_settings = settings or Settings()
        self.process_timeout_seconds = (
            active_settings.extraction_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        if self.process_timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")

        self.tool_manager = tool_manager or ToolManager()
        if active_settings.lz4_path is not None:
            configured_path = Path(active_settings.lz4_path).expanduser().resolve()
            if self.tool_manager.get_tool_path(ToolName.LZ4) != configured_path:
                self.tool_manager.set_tool_path(ToolName.LZ4, configured_path)

    def extract(
        self, plan: ExtractionPlan, password: str | None = None
    ) -> ExtractionResult:
        """执行一个 LZ4 计划，输出目录中只生成一个解压文件。"""
        archive = plan.archive_path.expanduser().resolve()
        output = plan.output_path.expanduser().resolve() if plan.output_path else None

        if not plan.can_execute:
            return ExtractionResult(
                success=False,
                message="执行计划不可用",
                output_path=output,
                error=plan.message,
                status=ExtractionStatus.FAILED,
            )
        if plan.selected_tool is not ToolName.LZ4:
            return ExtractionResult(
                success=False,
                message="执行计划未选择 LZ4",
                output_path=output,
                error=str(plan.selected_tool),
                status=ExtractionStatus.FAILED,
            )
        if plan.detected_format.upper() != "LZ4":
            return ExtractionResult(
                success=False,
                message="LZ4 执行器不支持该格式",
                output_path=output,
                error=plan.detected_format,
                status=ExtractionStatus.FAILED,
            )
        if not archive.is_file():
            return ExtractionResult(
                success=False,
                message="压缩文件不存在",
                output_path=output,
                error=str(archive),
                status=ExtractionStatus.FAILED,
            )
        if output is None:
            return ExtractionResult(
                success=False,
                message="未设置输出目录",
                error="ExtractionPlan.output_path 不能为空",
                status=ExtractionStatus.FAILED,
            )
        if output.exists():
            return ExtractionResult(
                success=False,
                message="输出目录已存在，不会覆盖",
                output_path=output,
                error=str(output),
                status=ExtractionStatus.FAILED,
            )

        self.tool_manager.check_tool(ToolName.LZ4)
        tool_path = self.tool_manager.get_tool_path(ToolName.LZ4)
        tool_info = self.tool_manager.get_tool_status(ToolName.LZ4)
        if tool_path is None or not tool_info.available or not tool_info.verified:
            return ExtractionResult(
                success=False,
                message="未找到 LZ4 工具",
                output_path=output,
                error="请通过 Settings 或 ToolManager 配置有效的 lz4.exe 路径",
                tool_used=ToolName.LZ4,
                status=ExtractionStatus.TOOL_NOT_FOUND,
            )

        # lz4.exe 解压单个文件。输出目录用于保持现有 Pipeline 接口一致。
        output_file = output / self._output_file_name(archive)
        try:
            output.mkdir(parents=True, exist_ok=False)
            register_created_directory(output)
            completed = subprocess.run(
                [str(tool_path), "-d", str(archive), str(output_file)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
                timeout=self.process_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ExtractionResult(
                success=False,
                message="LZ4 执行超时",
                output_path=output,
                error=f"超过 {self.process_timeout_seconds} 秒",
                tool_used=ToolName.LZ4,
                status=ExtractionStatus.FAILED,
            )
        except FileNotFoundError as error:
            return ExtractionResult(
                success=False,
                message="LZ4 工具不存在",
                output_path=output,
                error=str(error),
                tool_used=ToolName.LZ4,
                status=ExtractionStatus.TOOL_NOT_FOUND,
            )
        except OSError as error:
            return ExtractionResult(
                success=False,
                message="无法启动 LZ4",
                output_path=output,
                error=str(error),
                tool_used=ToolName.LZ4,
                status=ExtractionStatus.FAILED,
            )

        if completed.returncode == 0:
            return ExtractionResult(
                success=True,
                message="LZ4 解压成功",
                output_path=output,
                tool_used=ToolName.LZ4,
                status=ExtractionStatus.SUCCESS,
            )

        error_message = "\n".join(
            part
            for part in (completed.stderr.strip(), completed.stdout.strip())
            if part
        )
        return ExtractionResult(
            success=False,
            message="LZ4 解压失败",
            output_path=output,
            error=error_message or f"LZ4 退出代码: {completed.returncode}",
            tool_used=ToolName.LZ4,
            status=ExtractionStatus.FAILED,
        )

    @staticmethod
    def _output_file_name(archive: Path) -> str:
        """去掉最外层 .lz4 后缀，保留可能存在的内层扩展名。"""
        return archive.stem or f"{archive.name}.out"
