"""GameArchiveManager 的用户设置数据模型。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    """保存用户选择的处理策略和外部工具路径。"""

    # Platform settings：面向未知用户时默认保留所有平台内容。
    # 只有用户明确开启对应选项时才进行过滤。
    ignore_android: bool = False
    ignore_AZ: bool = False
    default_platform: str = "PC"

    # Cleanup settings：默认不删除任何用户文件。
    delete_archives: bool = False
    delete_empty_folders: bool = False

    # Tool settings：None 表示尚未配置对应工具路径。
    seven_zip_path: Path | None = None
    winrar_path: Path | None = None
    lz4_path: Path | None = None

    # Password settings：默认不保存或自动尝试历史密码。
    save_passwords: bool = False
    auto_try_password: bool = False

    # Runtime limits：限制递归规模、密码次数和外部工具运行时间。
    max_recursive_depth: int = 50
    max_archive_tasks: int = 1000
    max_initial_archive_tasks: int = 1000
    max_embedded_candidates: int = 20
    max_password_attempts: int = 20
    extraction_timeout_seconds: int = 300

    # Archive safety：解压前限制单个压缩包大小。
    max_archive_size_mb: int = 10240

    # 默认输出配额：处理不受信任归档时限制文件数量和磁盘占用。
    # 用户仍可在 config.json 中显式设为 null 关闭对应限制。
    max_extracted_files: int | None = 100000
    max_total_extracted_size_mb: int | None = 102400
