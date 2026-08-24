"""使用外部 WinRAR.exe 执行单个 RAR 压缩包的解压。"""

import os
import subprocess
from pathlib import Path

from config.settings import Settings
from cleanup.runtime_tracker import register_created_directory
from execution.models import ExtractionPlan
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from tools.models import ToolName
from tools.tool_manager import ToolManager


class WinRarExtractor:
    """调用 WinRAR 解压无密码 RAR，不下载或安装任何工具。"""

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
        if active_settings.winrar_path is not None:
            configured_path = (
                Path(active_settings.winrar_path).expanduser().resolve()
            )
            if self.tool_manager.get_tool_path(ToolName.WINRAR) != configured_path:
                self.tool_manager.set_tool_path(ToolName.WINRAR, configured_path)

    def extract(
        self, plan: ExtractionPlan, password: str | None = None
    ) -> ExtractionResult:
        """执行 RAR 解压计划，保持原压缩包和已有输出目录不变。"""
        archive = plan.archive_path.expanduser().resolve()
        output = plan.output_path.expanduser().resolve() if plan.output_path else None

        # WinRAR 的 -p密码 形式会把明文暴露在进程命令行中，本适配器不使用它。
        if password is not None:
            return ExtractionResult(
                success=False,
                message="WinRAR 密码执行未启用",
                output_path=output,
                error="为避免命令行泄露密码，未向 WinRAR 传递密码",
                tool_used=ToolName.WINRAR,
                status=ExtractionStatus.FAILED,
            )

        invalid_result = self._validate_plan(plan, archive, output)
        if invalid_result is not None:
            return invalid_result

        self.tool_manager.check_tool(ToolName.WINRAR)
        tool_info = self.tool_manager.get_tool_status(ToolName.WINRAR)
        if (
            tool_info.path is None
            or not tool_info.available
            or not tool_info.verified
        ):
            return ExtractionResult(
                success=False,
                message="未找到或无法验证 WinRAR",
                output_path=output,
                error="请通过 Settings 或 ToolManager 配置有效的 WinRAR.exe 路径",
                tool_used=ToolName.WINRAR,
                status=ExtractionStatus.TOOL_NOT_FOUND,
            )

        try:
            output.mkdir(parents=True, exist_ok=False)
            register_created_directory(output)
            destination = f"{output}{os.sep}"
            command = [
                str(tool_info.path),
                "x",
                "-o-",  # 不覆盖同名文件。
                "-ibck",  # 后台运行，避免弹出 WinRAR 主窗口。
                "-y",
                "-p-",  # 禁止交互式密码提示，也不传递任何密码。
                str(archive),
                destination,
            ]
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
                timeout=self.process_timeout_seconds,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            return ExtractionResult(
                success=False,
                message="WinRAR 执行超时",
                output_path=output,
                error=f"超过 {self.process_timeout_seconds} 秒",
                tool_used=ToolName.WINRAR,
                status=ExtractionStatus.FAILED,
            )
        except FileNotFoundError as error:
            return ExtractionResult(
                success=False,
                message="WinRAR 工具不存在",
                output_path=output,
                error=str(error),
                tool_used=ToolName.WINRAR,
                status=ExtractionStatus.TOOL_NOT_FOUND,
            )
        except OSError as error:
            return ExtractionResult(
                success=False,
                message="无法启动 WinRAR",
                output_path=output,
                error=str(error),
                tool_used=ToolName.WINRAR,
                status=ExtractionStatus.FAILED,
            )

        if completed.returncode == 0:
            return ExtractionResult(
                success=True,
                message="WinRAR 解压成功",
                output_path=output,
                tool_used=ToolName.WINRAR,
                status=ExtractionStatus.SUCCESS,
            )

        error_message = "\n".join(
            part
            for part in (completed.stderr.strip(), completed.stdout.strip())
            if part
        )
        status = self._classify_error(completed.returncode, error_message)
        message = (
            "压缩包需要密码"
            if status is ExtractionStatus.PASSWORD_REQUIRED
            else "WinRAR 解压失败"
        )
        return ExtractionResult(
            success=False,
            message=message,
            output_path=output,
            error=error_message or f"WinRAR 退出代码: {completed.returncode}",
            tool_used=ToolName.WINRAR,
            status=status,
        )

    @staticmethod
    def _validate_plan(
        plan: ExtractionPlan, archive: Path, output: Path | None
    ) -> ExtractionResult | None:
        if not plan.can_execute:
            return ExtractionResult(
                False,
                "执行计划不可用",
                output,
                plan.message,
                status=ExtractionStatus.FAILED,
            )
        if plan.selected_tool is not ToolName.WINRAR:
            return ExtractionResult(
                False,
                "执行计划未选择 WinRAR",
                output,
                str(plan.selected_tool),
                status=ExtractionStatus.FAILED,
            )
        if plan.detected_format.upper() != "RAR":
            return ExtractionResult(
                False,
                "WinRAR 执行器当前只支持 RAR",
                output,
                plan.detected_format,
                status=ExtractionStatus.FAILED,
            )
        if not archive.is_file():
            return ExtractionResult(
                False,
                "压缩文件不存在",
                output,
                str(archive),
                status=ExtractionStatus.FAILED,
            )
        if output is None:
            return ExtractionResult(
                False,
                "未设置输出目录",
                error="ExtractionPlan.output_path 不能为空",
                status=ExtractionStatus.FAILED,
            )
        if output.exists():
            return ExtractionResult(
                False,
                "输出目录已存在，不会覆盖",
                output,
                str(output),
                status=ExtractionStatus.FAILED,
            )
        return None

    @staticmethod
    def _classify_error(
        return_code: int, error_message: str
    ) -> ExtractionStatus:
        normalized = error_message.casefold()
        password_markers = (
            "wrong password",
            "incorrect password",
            "password is required",
            "encrypted file",
            "密码错误",
            "需要密码",
        )
        if return_code == 11 or any(
            marker in normalized for marker in password_markers
        ):
            return ExtractionStatus.PASSWORD_REQUIRED
        return ExtractionStatus.FAILED
