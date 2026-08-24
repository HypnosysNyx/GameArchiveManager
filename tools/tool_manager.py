"""发现并管理外部工具，不执行任何解压命令。"""

import os
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from config.settings import Settings
from application.runtime_paths import application_directory
from tools.models import ToolInfo, ToolName


class ToolManager:
    """保存 7-Zip、WinRAR 和 LZ4 的工具信息。"""

    VERSION_TIMEOUT_SECONDS = 5
    VERSION_ARGUMENTS = {
        ToolName.SEVEN_ZIP: ("i",),
        ToolName.WINRAR: ("-iver",),
        ToolName.LZ4: ("--version",),
    }
    PROJECT_TOOL_NAMES = {
        ToolName.SEVEN_ZIP: "7z.exe",
        ToolName.WINRAR: "Rar.exe",
        ToolName.LZ4: "lz4.exe",
    }
    _verification_cache: dict[
        tuple[ToolName, Path, int, int], tuple[bool, str]
    ] = {}

    def __init__(
        self,
        tool_paths: dict[ToolName | str, str | Path | None] | None = None,
        settings: Settings | None = None,
        project_root: str | Path | None = None,
    ) -> None:
        self._tools: dict[ToolName, ToolInfo] = {
            tool_name: ToolInfo(tool_name=tool_name) for tool_name in ToolName
        }
        self.project_root = (
            Path(project_root).expanduser().resolve()
            if project_root is not None
            else application_directory()
        )

        configured_paths: dict[ToolName | str, str | Path | None] = {}
        if settings is not None:
            configured_paths.update(
                {
                    ToolName.SEVEN_ZIP: settings.seven_zip_path,
                    ToolName.WINRAR: settings.winrar_path,
                    ToolName.LZ4: settings.lz4_path,
                }
            )
        # 显式 tool_paths 比 Settings 优先，便于测试或调用方临时覆盖。
        configured_paths.update(tool_paths or {})
        normalized_paths = {
            ToolName(tool_name): configured_path
            for tool_name, configured_path in configured_paths.items()
        }
        for tool_name in ToolName:
            self._tools[tool_name].path = self._discover_tool_path(
                tool_name,
                normalized_paths.get(tool_name),
            )
        self.check_all_tools()

    def _discover_tool_path(
        self,
        tool_name: ToolName,
        configured_path: str | Path | None,
    ) -> Path | None:
        """按手动配置、项目目录、常见目录和 PATH 的顺序发现工具。"""
        if configured_path is not None:
            manual_path = Path(configured_path).expanduser().resolve()
            # 手动配置始终优先；即使无效也保留路径供状态和错误诊断使用。
            return manual_path

        executable_name = self.PROJECT_TOOL_NAMES[tool_name]
        candidates = [
            *self._project_candidates(executable_name),
            *self._common_candidates(tool_name),
        ]
        for candidate in candidates:
            resolved = candidate.expanduser().resolve()
            if resolved.is_file():
                return resolved

        path_match = shutil.which(executable_name)
        if path_match:
            return Path(path_match).expanduser().resolve()
        return None

    def _project_candidates(self, executable_name: str) -> list[Path]:
        """检查 tools 根目录和一级子目录，不进行递归或磁盘扫描。"""
        tools_directory = self.project_root / "tools"
        candidates = [tools_directory / executable_name]
        if not tools_directory.is_dir():
            return candidates

        try:
            child_candidates = sorted(
                tools_directory.glob(f"*/{executable_name}"),
                key=lambda path: str(path).casefold(),
            )
        except OSError:
            return candidates
        candidates.extend(child_candidates)
        return candidates

    @staticmethod
    def _common_candidates(tool_name: ToolName) -> list[Path]:
        """返回 Windows 常见安装位置，不下载或安装任何工具。"""
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates = {
            ToolName.SEVEN_ZIP: [program_files / "7-Zip" / "7z.exe"],
            ToolName.WINRAR: [program_files / "WinRAR" / "Rar.exe"],
            ToolName.LZ4: [
                program_files / "LZ4" / "lz4.exe",
                Path(r"C:\Tools\LZ4\lz4.exe"),
            ],
        }
        return candidates[tool_name]

    def set_tool_path(
        self, tool_name: ToolName | str, path: str | Path
    ) -> ToolInfo:
        """设置工具路径并更新它的可用状态。"""
        name = ToolName(tool_name)
        tool_path = Path(path).expanduser().resolve()
        info = self._tools[name]
        info.path = tool_path
        self.check_tool(name, force=True)
        return replace(info)

    def check_tool(
        self, tool_name: ToolName | str, force: bool = False
    ) -> bool:
        """检查工具文件是否存在，并通过版本命令确认它可以启动。"""
        name = ToolName(tool_name)
        info = self._tools[name]
        info.available = info.path is not None and info.path.is_file()
        info.version = ""
        info.verified = False
        if not info.available or info.path is None:
            return False

        try:
            file_status = info.path.stat()
        except OSError:
            info.available = False
            return False
        cache_key = (
            name,
            info.path,
            file_status.st_mtime_ns,
            file_status.st_size,
        )
        if not force and cache_key in self._verification_cache:
            info.verified, info.version = self._verification_cache[cache_key]
            return info.verified

        command = [str(info.path), *self.VERSION_ARGUMENTS[name]]
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
                timeout=self.VERSION_TIMEOUT_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            self._verification_cache[cache_key] = (False, "")
            return False

        if completed.returncode != 0:
            self._verification_cache[cache_key] = (False, "")
            return False

        version_output = "\n".join(
            part
            for part in (completed.stdout.strip(), completed.stderr.strip())
            if part
        )
        info.version = self._extract_version(version_output)
        info.verified = True
        self._verification_cache[cache_key] = (True, info.version)
        return True

    def check_all_tools(self, force: bool = False) -> None:
        """刷新所有工具的可用状态。"""
        for tool_name in self._tools:
            self.check_tool(tool_name, force=force)

    def get_tool_status(self, tool_name: ToolName | str) -> ToolInfo:
        """返回指定工具的状态副本。"""
        return replace(self._tools[ToolName(tool_name)])

    def get_tool_path(self, tool_name: ToolName | str) -> Path | None:
        """统一返回工具路径；尚未配置路径时返回 None。"""
        return self._tools[ToolName(tool_name)].path

    def get_all_tool_statuses(self) -> list[ToolInfo]:
        """返回所有工具的状态副本。"""
        return [replace(info) for info in self._tools.values()]

    @staticmethod
    def _extract_version(output: str) -> str:
        """从版本命令输出提取版本号，不保存完整的外部工具输出。"""
        match = re.search(r"(?<!\d)(\d+(?:\.\d+)+)(?!\d)", output)
        if match:
            return match.group(1)
        return ""
