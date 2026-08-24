"""根据 ExtractionPlan 选择对应的外部工具执行器。"""

from typing import Protocol

from config.settings import Settings
from execution.models import ExtractionPlan
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from extractor.lz4 import Lz4Extractor
from extractor.seven_zip import SevenZipExtractor
from extractor.winrar import WinRarExtractor
from tools.models import ToolName
from tools.tool_manager import ToolManager


class ExtractorAdapter(Protocol):
    """所有工具适配器共同遵循的最小接口。"""

    def extract(
        self, plan: ExtractionPlan, password: str | None = None
    ) -> ExtractionResult:
        ...


class ExtractorDispatcher:
    """按计划中的 selected_tool 分派执行器，不执行工具下载。"""

    def __init__(
        self,
        seven_zip_extractor: ExtractorAdapter | None = None,
        lz4_extractor: ExtractorAdapter | None = None,
        winrar_extractor: ExtractorAdapter | None = None,
        tool_manager: ToolManager | None = None,
        settings: Settings | None = None,
    ) -> None:
        active_settings = settings or Settings()
        # Settings 在 Dispatcher 边界一次性注入 ToolManager，所有 Adapter
        # 共用同一份已经完成路径检测和版本验证的工具状态。
        shared_tool_manager = tool_manager or ToolManager(settings=active_settings)
        self.tool_manager = shared_tool_manager
        self._extractors: dict[ToolName, ExtractorAdapter | None] = {
            ToolName.SEVEN_ZIP: seven_zip_extractor
            or SevenZipExtractor(shared_tool_manager, settings=active_settings),
            ToolName.LZ4: lz4_extractor
            or Lz4Extractor(shared_tool_manager, settings=active_settings),
            ToolName.WINRAR: winrar_extractor
            or WinRarExtractor(shared_tool_manager, settings=active_settings),
        }

    def extract(
        self, plan: ExtractionPlan, password: str | None = None
    ) -> ExtractionResult:
        """选择并调用计划指定的执行器。"""
        selected_tool = plan.selected_tool
        if selected_tool is None:
            return ExtractionResult(
                success=False,
                message="执行计划未选择工具",
                output_path=plan.output_path,
                error=plan.message,
                status=ExtractionStatus.FAILED,
            )

        extractor = self._extractors.get(selected_tool)
        if extractor is None:
            return ExtractionResult(
                success=False,
                message=f"{selected_tool.value} 执行器尚未配置",
                output_path=plan.output_path,
                error="请配置对应的 Extractor Adapter",
                tool_used=selected_tool,
                status=ExtractionStatus.TOOL_NOT_FOUND,
            )
        return extractor.extract(plan, password=password)

    def register(
        self, tool_name: ToolName | str, extractor: ExtractorAdapter
    ) -> None:
        """注册或替换一个工具适配器。"""
        self._extractors[ToolName(tool_name)] = extractor
