"""Extraction Coordinator 使用的数据模型。"""

from dataclasses import dataclass, field
from pathlib import Path

from extractor.extractor_models import ExtractionResult, ExtractionStageDiagnostic
from tools.models import ToolName


@dataclass
class CoordinatorResult:
    """保存单个压缩包协调流程的最终结果。"""

    success: bool
    archive_path: Path
    extraction_result: ExtractionResult | None = None
    steps: list[str] = field(default_factory=list)
    error_message: str = ""
    failure_stage: str = ""
    error_type: str = ""
    user_message: str = ""
    missing_files: list[Path] = field(default_factory=list)
    password_attempt_count: int = 0
    fallback_tools_attempted: list[ToolName] = field(default_factory=list)
    final_tool: ToolName | None = None
    composite_stage: str = ""
    stage_diagnostics: list[ExtractionStageDiagnostic] = field(default_factory=list)
    manual_password_attempt_count: int = 0
    manual_password_used: bool = False
    password_recovery_result: str = ""
    control_action: str = ""
