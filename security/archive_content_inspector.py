"""解压前读取压缩包内部元数据，不写入任何文件。"""

import zipfile
from pathlib import PurePosixPath, PureWindowsPath

from analyzer.models import ArchiveInfo
from security.models import ArchiveContentInfo


class ArchiveContentInspector:
    """第一版使用标准库读取 ZIP 的文件数、大小和内部路径。"""

    def inspect(self, archive_info: ArchiveInfo) -> ArchiveContentInfo:
        """返回压缩包内容信息；非 ZIP 格式暂时只返回能力警告。"""
        if archive_info.real_format.upper() != "ZIP":
            return ArchiveContentInfo(
                file_count=0,
                estimated_size=0,
                warnings=[
                    f"暂不支持 {archive_info.real_format} 内容预检查"
                ],
            )

        try:
            with zipfile.ZipFile(archive_info.file_path, "r") as archive:
                entries = archive.infolist()
        except (OSError, zipfile.BadZipFile) as error:
            raise ValueError(f"无法读取 ZIP 内容目录: {error}") from error

        file_count = 0
        estimated_size = 0
        paths: list[str] = []
        warnings: list[str] = []

        for entry in entries:
            entry_path = entry.filename
            paths.append(entry_path)
            unsafe_reason = self._get_unsafe_path_reason(entry_path)
            if unsafe_reason:
                warnings.append(
                    f"不安全路径: {entry_path}（{unsafe_reason}）"
                )

            if not entry.is_dir():
                file_count += 1
                estimated_size += max(entry.file_size, 0)

        return ArchiveContentInfo(
            file_count=file_count,
            estimated_size=estimated_size,
            paths=paths,
            warnings=warnings,
        )

    @staticmethod
    def _get_unsafe_path_reason(entry_path: str) -> str | None:
        """识别绝对路径、Windows 驱动器路径和父目录穿越。"""
        normalized = entry_path.replace("\\", "/")
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(entry_path)

        if posix_path.is_absolute() or windows_path.is_absolute():
            return "包含绝对路径"
        if windows_path.drive:
            return "包含驱动器路径"
        if ".." in posix_path.parts:
            return "包含父目录穿越"
        return None
