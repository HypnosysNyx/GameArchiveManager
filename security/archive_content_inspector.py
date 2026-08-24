"""解压前读取压缩包内部元数据，不写入任何文件。"""

import subprocess
import zipfile
from pathlib import PurePosixPath, PureWindowsPath

from analyzer.models import ArchiveInfo
from security.models import ArchiveContentInfo
from tools.models import ToolName
from tools.tool_manager import ToolManager


class ArchiveContentInspector:
    """使用标准库检查 ZIP，并可用本地 7-Zip 只读列出 RAR/7Z。"""

    def __init__(
        self,
        tool_manager: ToolManager | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")
        self.tool_manager = tool_manager
        self.timeout_seconds = timeout_seconds

    def inspect(self, archive_info: ArchiveInfo) -> ArchiveContentInfo:
        """返回压缩包内容信息，不解压或写入用户文件。"""
        archive_format = archive_info.real_format.upper()
        if archive_format in {"RAR", "7Z"} and self.tool_manager is not None:
            return self._inspect_with_seven_zip(archive_info)
        if archive_format != "ZIP":
            return ArchiveContentInfo(
                file_count=0,
                estimated_size=0,
                warnings=[
                    f"暂不支持 {archive_info.real_format} 内容预检查"
                ],
            )

        try:
            with zipfile.ZipFile(archive_info.file_path, "r") as archive:
                entries = archive.infolist()
        except (OSError, zipfile.BadZipFile) as error:
            raise ValueError(f"无法读取 ZIP 内容目录: {error}") from error

        file_count = 0
        estimated_size = 0
        paths: list[str] = []
        warnings: list[str] = []

        for entry in entries:
            entry_path = entry.filename
            paths.append(entry_path)
            unsafe_reason = self._get_unsafe_path_reason(entry_path)
            if unsafe_reason:
                warnings.append(
                    f"不安全路径: {entry_path}（{unsafe_reason}）"
                )

            if not entry.is_dir():
                file_count += 1
                estimated_size += max(entry.file_size, 0)

        return ArchiveContentInfo(
            file_count=file_count,
            estimated_size=estimated_size,
            paths=paths,
            warnings=warnings,
        )

    def _inspect_with_seven_zip(
        self, archive_info: ArchiveInfo
    ) -> ArchiveContentInfo:
        """通过 7-Zip 的 list 模式读取 RAR/7Z 元数据。"""
        status = self.tool_manager.get_tool_status(ToolName.SEVEN_ZIP)
        if not status.available or not status.verified or status.path is None:
            return self._unsupported(archive_info.real_format, "7-Zip 不可用")

        command = [
            str(status.path),
            "l",
            "-slt",
            "-ba",
            "-sccUTF-8",
            "-p-",
            str(archive_info.file_path),
        ]
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.timeout_seconds,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            return self._unsupported(archive_info.real_format, "7-Zip 列表超时")
        except OSError as error:
            return self._unsupported(
                archive_info.real_format, f"7-Zip 无法启动: {error}"
            )

        if completed.returncode != 0:
            output = f"{completed.stdout}\n{completed.stderr}".casefold()
            if "encrypted archive" in output or "wrong password" in output:
                return self._unsupported(
                    archive_info.real_format,
                    "归档目录已加密，获得正确密码前无法预检查",
                )
            return self._unsupported(
                archive_info.real_format,
                f"7-Zip 列表失败（退出码 {completed.returncode}）",
            )

        return self._parse_seven_zip_listing(completed.stdout)

    def _parse_seven_zip_listing(self, output: str) -> ArchiveContentInfo:
        file_count = 0
        estimated_size = 0
        paths: list[str] = []
        warnings: list[str] = []
        current: dict[str, str] = {}

        def finish_record() -> None:
            nonlocal file_count, estimated_size
            entry_path = current.get("Path")
            if not entry_path:
                current.clear()
                return
            paths.append(entry_path)
            unsafe_reason = self._get_unsafe_path_reason(entry_path)
            if unsafe_reason:
                warnings.append(
                    f"不安全路径: {entry_path}（{unsafe_reason}）"
                )
            if current.get("Symbolic Link") or current.get("Hard Link"):
                warnings.append(f"不安全路径: {entry_path}（包含链接条目）")
            attributes = current.get("Attributes", "")
            if "D" not in attributes.upper():
                file_count += 1
                try:
                    estimated_size += max(int(current.get("Size", "0")), 0)
                except ValueError:
                    warnings.append(
                        f"不安全路径: {entry_path}（无法解析声明大小）"
                    )
            current.clear()

        for raw_line in output.splitlines():
            line = raw_line.strip("\r")
            if not line.strip():
                finish_record()
                continue
            if " = " not in line:
                warnings.append("不安全路径: 无法可靠解析 7-Zip 列表输出")
                continue
            key, value = line.split(" = ", 1)
            current[key] = value
        finish_record()
        return ArchiveContentInfo(
            file_count=file_count,
            estimated_size=estimated_size,
            paths=paths,
            warnings=warnings,
        )

    @staticmethod
    def _unsupported(archive_format: str, reason: str) -> ArchiveContentInfo:
        return ArchiveContentInfo(
            file_count=0,
            estimated_size=0,
            warnings=[f"暂不支持 {archive_format} 内容预检查: {reason}"],
        )

    @staticmethod
    def _get_unsafe_path_reason(entry_path: str) -> str | None:
        """识别绝对路径、Windows 驱动器路径和父目录穿越。"""
        normalized = entry_path.replace("\\", "/")
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(entry_path)

        if posix_path.is_absolute() or windows_path.is_absolute():
            return "包含绝对路径"
        if windows_path.drive:
            return "包含驱动器路径"
        if ".." in posix_path.parts:
            return "包含父目录穿越"
        return None
