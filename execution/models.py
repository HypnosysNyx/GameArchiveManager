"""Execution Strategy 使用的数据模型。"""

from dataclasses import dataclass, field
from pathlib import Path

from tools.models import ToolName


@dataclass
class ExtractionStage:
    """描述复合计划中的一个阶段；内部阶段必须重新分析后才能执行。"""

    stage_index: int
    format_hint: str
    primary_tool: ToolName | None
    fallback_tools: list[ToolName] = field(default_factory=list)
    requires_reanalysis: bool = False


@dataclass
class ExtractionPlan:
    """描述一个解压计划，但不执行任何工具。"""

    archive_path: Path
    detected_format: str
    selected_tool: ToolName | None
    output_path: Path | None
    requires_password: bool = False
    can_execute: bool = True
    message: str = ""
    primary_tool: ToolName | None = None
    fallback_tools: list[ToolName] = field(default_factory=list)
    container_chain: list[str] = field(default_factory=list)
    stages: list[ExtractionStage] = field(default_factory=list)
    is_multi_volume: bool = False
    volume_files: list[Path] = field(default_factory=list)
    missing_volume_files: list[Path] = field(default_factory=list)
    is_embedded_archive: bool = False
    embedded_offset: int | None = None
    embedded_container_format: str = ""

    def __post_init__(self) -> None:
        """兼容旧调用方：selected_tool 默认就是计划的首选工具。"""
        if self.primary_tool is None:
            self.primary_tool = self.selected_tool
        if self.selected_tool is None and self.primary_tool is not None:
            self.selected_tool = self.primary_tool

    @property
    def is_composite(self) -> bool:
        """至少包含两个容器阶段时，计划需要复合执行协调。"""
        return len(self.stages) > 1
