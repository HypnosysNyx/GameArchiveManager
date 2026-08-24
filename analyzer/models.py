"""Archive Analyzer 使用的数据模型。"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ArchiveInfo:
    """保存文件真实格式的分析结果。"""

    file_path: Path
    extension: str
    real_format: str
    is_fake_extension: bool
    confidence: float
    container_chain: list[str] = field(default_factory=list)
    is_multi_volume: bool = False
    volume_group: str = ""
    volume_files: list[Path] = field(default_factory=list)
    missing_volume_files: list[Path] = field(default_factory=list)
    is_embedded_archive: bool = False
    embedded_offset: int | None = None
    embedded_container_format: str = ""
    embedded_validation_status: str = ""
    embedded_validation_reason: str = ""
