"""根据文件真实格式制定解压计划。"""

from analyzer.models import ArchiveInfo
from config.settings import Settings
from execution.models import ExtractionPlan, ExtractionStage
from execution.output_paths import OutputPathGenerator
from security.archive_safety import ArchiveSafetyChecker
from security.models import ArchiveContentInfo
from tools.models import ToolName


class ExecutionStrategy:
    """选择外部工具并生成计划，不执行解压。"""

    TOOL_BY_FORMAT = {
        "ZIP": ToolName.SEVEN_ZIP,
        "RAR": ToolName.SEVEN_ZIP,
        "7Z": ToolName.SEVEN_ZIP,
        "LZ4": ToolName.LZ4,
    }
    FALLBACK_TOOLS_BY_FORMAT = {
        "RAR": [ToolName.WINRAR],
    }

    def __init__(
        self,
        settings: Settings | None = None,
        safety_checker: ArchiveSafetyChecker | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.safety_checker = safety_checker or ArchiveSafetyChecker(self.settings)

    def create_plan(
        self,
        archive_info: ArchiveInfo,
        content_info: ArchiveContentInfo | None = None,
    ) -> ExtractionPlan:
        """根据 ArchiveInfo 返回一个单阶段解压计划。"""
        detected_format = archive_info.real_format.upper()
        selected_tool = self.TOOL_BY_FORMAT.get(detected_format)
        output_path = OutputPathGenerator.for_archive(archive_info.file_path)
        if archive_info.missing_volume_files:
            missing_names = ", ".join(
                str(path) for path in archive_info.missing_volume_files
            )
            return ExtractionPlan(
                archive_path=archive_info.file_path,
                detected_format=detected_format,
                selected_tool=selected_tool,
                output_path=output_path,
                can_execute=False,
                message=f"缺少分卷文件: {missing_names}",
                primary_tool=selected_tool,
                fallback_tools=self.FALLBACK_TOOLS_BY_FORMAT.get(
                    detected_format, []
                ).copy(),
                container_chain=archive_info.container_chain.copy(),
                is_multi_volume=True,
                volume_files=archive_info.volume_files.copy(),
                missing_volume_files=archive_info.missing_volume_files.copy(),
            )

        safety_result = self.safety_checker.check(archive_info, content_info)
        if not safety_result.safe:
            return ExtractionPlan(
                archive_path=archive_info.file_path,
                detected_format=detected_format,
                selected_tool=None,
                output_path=None,
                can_execute=False,
                message="安全检查未通过: " + "; ".join(safety_result.reasons),
            )

        if archive_info.is_embedded_archive:
            embedded_format = archive_info.embedded_container_format.upper()
            embedded_tool = self.TOOL_BY_FORMAT.get(embedded_format)
            container_chain = archive_info.container_chain.copy()
            stages = [
                ExtractionStage(
                    stage_index=0,
                    format_hint=container_chain[0],
                    primary_tool=None,
                    requires_reanalysis=False,
                ),
                ExtractionStage(
                    stage_index=1,
                    format_hint=embedded_format,
                    primary_tool=embedded_tool,
                    fallback_tools=self.FALLBACK_TOOLS_BY_FORMAT.get(
                        embedded_format, []
                    ).copy(),
                    requires_reanalysis=True,
                ),
            ]
            return ExtractionPlan(
                archive_path=archive_info.file_path,
                detected_format=detected_format,
                selected_tool=embedded_tool,
                output_path=output_path,
                message="已创建内嵌压缩包提取计划",
                primary_tool=embedded_tool,
                fallback_tools=self.FALLBACK_TOOLS_BY_FORMAT.get(
                    embedded_format, []
                ).copy(),
                container_chain=container_chain,
                stages=stages,
                is_embedded_archive=True,
                embedded_offset=archive_info.embedded_offset,
                embedded_container_format=embedded_format,
            )

        if selected_tool is None:
            return ExtractionPlan(
                archive_path=archive_info.file_path,
                detected_format=detected_format,
                selected_tool=None,
                output_path=None,
                can_execute=False,
                message="无法为未知格式制定执行计划",
            )

        # 这里只计算建议路径，不创建目录，也不修改任何文件。
        container_chain = archive_info.container_chain.copy()
        if not container_chain and detected_format != "UNKNOWN":
            container_chain = [detected_format]
        stages = [
            ExtractionStage(
                stage_index=index,
                format_hint=format_hint.upper(),
                primary_tool=self.TOOL_BY_FORMAT.get(format_hint.upper()),
                fallback_tools=self.FALLBACK_TOOLS_BY_FORMAT.get(
                    format_hint.upper(), []
                ).copy(),
                requires_reanalysis=index > 0,
            )
            for index, format_hint in enumerate(container_chain)
        ]
        return ExtractionPlan(
            archive_path=archive_info.file_path,
            detected_format=detected_format,
            selected_tool=selected_tool,
            output_path=output_path,
            # ArchiveInfo 暂不包含加密信息，因此第一版保持 False。
            requires_password=False,
            message="执行计划已创建",
            primary_tool=selected_tool,
            fallback_tools=self.FALLBACK_TOOLS_BY_FORMAT.get(
                detected_format, []
            ).copy(),
            container_chain=container_chain,
            stages=stages,
            is_multi_volume=archive_info.is_multi_volume,
            volume_files=archive_info.volume_files.copy(),
            missing_volume_files=archive_info.missing_volume_files.copy(),
        )
