"""使用外部 7z.exe 执行一个 ExtractionPlan。"""

import subprocess

from config.settings import Settings
from cleanup.runtime_tracker import register_created_directory
from execution.models import ExtractionPlan
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from tools.models import ToolName
from tools.tool_manager import ToolManager


class SevenZipExtractor:
    """调用 7-Zip 执行单个 ZIP、RAR 或 7Z 解压计划。"""

    SUPPORTED_FORMATS = {"ZIP", "RAR", "7Z"}
    PROCESS_TIMEOUT_SECONDS = 300

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

    def extract(
        self, plan: ExtractionPlan, password: str | None = None
    ) -> ExtractionResult:
        """执行一个单阶段计划并返回统一结果。"""
        archive = plan.archive_path.expanduser().resolve()
        output = plan.output_path.expanduser().resolve() if plan.output_path else None
        detected_format = plan.detected_format.upper()

        if not plan.can_execute:
            return ExtractionResult(
                success=False,
                message="执行计划不可用",
                output_path=output,
                error=plan.message,
                status=ExtractionStatus.FAILED,
            )

        if plan.selected_tool is not ToolName.SEVEN_ZIP:
            return ExtractionResult(
                success=False,
                message="执行计划未选择 7-Zip",
                output_path=output,
                error=str(plan.selected_tool),
                status=ExtractionStatus.FAILED,
            )

        if detected_format not in self.SUPPORTED_FORMATS:
            return ExtractionResult(
                success=False,
                message="不支持的压缩格式",
                output_path=output,
                error=f"仅支持 ZIP、RAR 和 7Z: {detected_format}",
                status=ExtractionStatus.FAILED,
            )

        if plan.requires_password and password is None:
            return ExtractionResult(
                success=False,
                message="压缩包需要密码",
                output_path=output,
                error="计划标记为需要密码",
                status=ExtractionStatus.PASSWORD_REQUIRED,
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

        self.tool_manager.check_tool(ToolName.SEVEN_ZIP)
        tool_info = self.tool_manager.get_tool_status(ToolName.SEVEN_ZIP)
        if (
            not tool_info.available
            or not tool_info.verified
            or tool_info.path is None
        ):
            return ExtractionResult(
                success=False,
                message="未找到 7-Zip",
                output_path=output,
                error="请通过 ToolManager 配置有效的 7-Zip 路径",
                status=ExtractionStatus.TOOL_NOT_FOUND,
            )

        try:
            # exist_ok=False 防止并发情况下意外使用已存在目录。
            output.mkdir(parents=True, exist_ok=False)
            register_created_directory(output)
            command = [
                str(tool_info.path),
                "x",
                str(archive),
                f"-o{output}",
                "-aos",  # 双重保护：不覆盖同名文件。
                "-y",
            ]
            if password is not None:
                command.append(f"-p{password}")

            completed = subprocess.run(
                command,
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
                message="7-Zip 执行超时",
                output_path=output,
                error=f"超过 {self.process_timeout_seconds} 秒",
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.FAILED,
            )
        except FileNotFoundError as exc:
            return ExtractionResult(
                success=False,
                message="7-Zip 工具不存在",
                output_path=output,
                error=str(exc),
                status=ExtractionStatus.TOOL_NOT_FOUND,
            )
        except OSError as exc:
            return ExtractionResult(
                success=False,
                message="无法启动 7-Zip",
                output_path=output,
                error=str(exc),
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.FAILED,
            )

        if completed.returncode == 0:
            return ExtractionResult(
                success=True,
                message="解压成功",
                output_path=output,
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.SUCCESS,
            )

        error_message = "\n".join(
            part
            for part in (completed.stderr.strip(), completed.stdout.strip())
            if part
        )
        status = self._classify_error(error_message)
        if status is ExtractionStatus.WRONG_PASSWORD and password is None:
            status = ExtractionStatus.PASSWORD_REQUIRED

        if status is ExtractionStatus.PASSWORD_REQUIRED:
            message = "压缩包需要密码"
        elif status is ExtractionStatus.WRONG_PASSWORD:
            message = "密码错误"
        else:
            message = "7-Zip 解压失败"

        return ExtractionResult(
            success=False,
            message=message,
            output_path=output,
            error=error_message or f"7-Zip 退出代码: {completed.returncode}",
            tool_used=ToolName.SEVEN_ZIP,
            status=status,
        )

    @staticmethod
    def _classify_error(error_message: str) -> ExtractionStatus:
        """根据 7-Zip 的明确错误文字分类，不尝试任何密码。"""
        normalized = error_message.casefold()
        wrong_password_markers = (
            "wrong password",
            "incorrect password",
            "密码错误",
            "密码不正确",
        )
        password_required_markers = (
            "password is required",
            "password required",
            "enter password",
            "encrypted archive",
            "需要密码",
            "输入密码",
        )

        if any(marker in normalized for marker in wrong_password_markers):
            return ExtractionStatus.WRONG_PASSWORD
        if any(marker in normalized for marker in password_required_markers):
            return ExtractionStatus.PASSWORD_REQUIRED
        return ExtractionStatus.FAILED
