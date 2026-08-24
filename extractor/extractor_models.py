"""解压模块使用的数据模型。"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from tools.models import ToolName


class ExtractionStatus(str, Enum):
    """一次解压操作的明确状态。"""

    SUCCESS = "SUCCESS"
    PASSWORD_REQUIRED = "PASSWORD_REQUIRED"
    WRONG_PASSWORD = "WRONG_PASSWORD"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    FAILED = "FAILED"


@dataclass
class ExtractionStageDiagnostic:
    """Sanitized status for one stage; never stores passwords or commands."""

    stage: str
    detected_format: str = ""
    tool: ToolName | None = None
    status: ExtractionStatus = ExtractionStatus.FAILED
    error_type: str = ""
    normalized_reason: str = ""


@dataclass
class ExtractionResult:
    """保存一次解压操作的结果。"""

    success: bool
    message: str
    output_path: Path | None = None
    error: str = ""
    tool_used: ToolName | None = None
    status: ExtractionStatus = ExtractionStatus.FAILED
    stage_diagnostics: list[ExtractionStageDiagnostic] = field(
        default_factory=list
    )
    tools_attempted: list[ToolName] = field(default_factory=list)
