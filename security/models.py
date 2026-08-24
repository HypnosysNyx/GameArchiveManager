"""压缩包安全检查使用的数据模型。"""

from dataclasses import dataclass, field


@dataclass
class ArchiveSafetyResult:
    """保存解压前的压缩包安全检查结果。"""

    safe: bool
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass
class ArchiveContentInfo:
    """保存压缩包内部目录的只读预检查信息。"""

    file_count: int
    estimated_size: int
    paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExtractionSafetyResult:
    """保存解压输出目录的安全检查结果。"""

    safe: bool
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
