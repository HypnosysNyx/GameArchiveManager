"""Scanner 模块使用的数据模型。"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ScanResult:
    """保存一次目录扫描得到的结果。"""

    root: Path
    files: list[Path] = field(default_factory=list)
    folders: list[Path] = field(default_factory=list)
    archive_candidates: list[Path] = field(default_factory=list)
    ignored: list[Path] = field(default_factory=list)
    password_candidates: list[Path] = field(default_factory=list)
