"""Tool Manager 使用的数据模型。"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ToolName(str, Enum):
    """GameArchiveManager 支持管理的外部工具。"""

    SEVEN_ZIP = "SEVEN_ZIP"
    WINRAR = "WINRAR"
    LZ4 = "LZ4"


@dataclass
class ToolInfo:
    """保存一个外部工具的路径和可用状态。"""

    tool_name: ToolName
    path: Path | None = None
    available: bool = False
    version: str = ""
    verified: bool = False
