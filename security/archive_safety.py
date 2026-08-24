"""解压前的只读压缩包安全检查。"""

from analyzer.models import ArchiveInfo
from config.settings import Settings
from security.models import ArchiveContentInfo, ArchiveSafetyResult


class ArchiveSafetyChecker:
    """检查压缩包基础风险，不解压或修改文件。"""

    BYTES_PER_MB = 1024 * 1024

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        if self.settings.max_archive_size_mb < 0:
            raise ValueError("max_archive_size_mb 不能小于 0")
        if (
            self.settings.max_extracted_files is not None
            and self.settings.max_extracted_files < 0
        ):
            raise ValueError("max_extracted_files 不能小于 0")
        if (
            self.settings.max_total_extracted_size_mb is not None
            and self.settings.max_total_extracted_size_mb < 0
        ):
            raise ValueError("max_total_extracted_size_mb 不能小于 0")

    def check(
        self,
        archive_info: ArchiveInfo,
        content_info: ArchiveContentInfo | None = None,
    ) -> ArchiveSafetyResult:
        """执行当前可用检查，并返回所有警告和拒绝原因。"""
        reasons: list[str] = []
        warnings: list[str] = []

        files_to_measure = (
            archive_info.volume_files
            if archive_info.is_multi_volume and archive_info.volume_files
            else [archive_info.file_path]
        )
        try:
            file_size = sum(path.stat().st_size for path in files_to_measure)
        except OSError as error:
            reasons.append(f"无法读取压缩包文件信息: {error}")
        else:
            max_size = self.settings.max_archive_size_mb * self.BYTES_PER_MB
            if file_size > max_size:
                reasons.append(
                    "压缩包大小超过限制: "
                    f"{file_size} 字节 > {max_size} 字节"
                )

        if content_info is not None:
            warnings.extend(content_info.warnings)
            reasons.extend(
                warning
                for warning in content_info.warnings
                if warning.startswith("不安全路径:")
            )

            max_files = self.settings.max_extracted_files
            if max_files is not None and content_info.file_count > max_files:
                reasons.append(
                    "预计解压文件数量超过限制: "
                    f"{content_info.file_count} > {max_files}"
                )

            max_size_mb = self.settings.max_total_extracted_size_mb
            if max_size_mb is not None:
                max_size = max_size_mb * self.BYTES_PER_MB
                if content_info.estimated_size > max_size:
                    reasons.append(
                        "预计解压总大小超过限制: "
                        f"{content_info.estimated_size} 字节 > {max_size} 字节"
                    )

        return ArchiveSafetyResult(
            safe=not reasons,
            warnings=warnings,
            reasons=reasons,
        )
