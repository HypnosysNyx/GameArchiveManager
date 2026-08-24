"""Safely carve a confirmed embedded archive into an internal output folder."""

from pathlib import Path

from analyzer.archive_analyzer import ArchiveAnalyzer
from cleanup.runtime_tracker import register_created_directory
from execution.models import ExtractionPlan
from extractor.extractor_models import ExtractionResult, ExtractionStatus


class EmbeddedExtractor:
    """Copy bytes from a confirmed offset, then verify the resulting archive."""

    EXTENSIONS = {
        "ZIP": ".zip",
        "RAR": ".rar",
        "7Z": ".7z",
    }
    COPY_CHUNK_SIZE = 1024 * 1024

    def __init__(self, analyzer: ArchiveAnalyzer | None = None) -> None:
        self.analyzer = analyzer or ArchiveAnalyzer()

    def extract(self, plan: ExtractionPlan) -> ExtractionResult:
        source = plan.archive_path.expanduser().resolve()
        output = plan.output_path.expanduser().resolve() if plan.output_path else None
        embedded_format = plan.embedded_container_format.upper()
        offset = plan.embedded_offset

        if not plan.is_embedded_archive or offset is None or offset <= 0:
            return self._failure(output, "内嵌压缩包计划缺少有效偏移量")
        if embedded_format not in self.EXTENSIONS:
            return self._failure(output, f"不支持的内嵌格式: {embedded_format}")
        if not source.is_file():
            return self._failure(output, f"源文件不存在: {source}")
        if output is None:
            return self._failure(None, "未设置内嵌压缩包输出目录")
        if output.exists():
            return self._failure(output, "输出目录已存在，不会覆盖")

        extracted_path = output / (
            f"{source.stem}_embedded{self.EXTENSIONS[embedded_format]}"
        )
        try:
            output.mkdir(parents=True, exist_ok=False)
            register_created_directory(output)
            with source.open("rb") as input_file, extracted_path.open("xb") as target:
                input_file.seek(offset)
                while True:
                    chunk = input_file.read(self.COPY_CHUNK_SIZE)
                    if not chunk:
                        break
                    target.write(chunk)

            verified_info = self.analyzer.analyze(extracted_path)
            if verified_info.real_format.upper() != embedded_format:
                return self._failure(
                    output,
                    "提取后的文件格式与内嵌签名不一致",
                )
        except OSError as error:
            return self._failure(output, f"无法提取内嵌压缩包: {error}")

        return ExtractionResult(
            success=True,
            message=f"内嵌 {embedded_format} 已提取并重新确认",
            output_path=output,
            status=ExtractionStatus.SUCCESS,
        )

    @staticmethod
    def _failure(output_path: Path | None, message: str) -> ExtractionResult:
        return ExtractionResult(
            success=False,
            message=message,
            output_path=output_path,
            error=message,
            status=ExtractionStatus.FAILED,
        )
