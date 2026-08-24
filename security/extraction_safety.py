"""解压完成后的只读输出目录安全检查。"""

import os
import stat
from pathlib import Path

from config.settings import Settings
from security.models import ExtractionSafetyResult


class ExtractionSafetyChecker:
    """统计输出文件数量和总大小，不删除或修改任何文件。"""

    BYTES_PER_MB = 1024 * 1024

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._validate_limit(
            "max_extracted_files", self.settings.max_extracted_files
        )
        self._validate_limit(
            "max_total_extracted_size_mb",
            self.settings.max_total_extracted_size_mb,
        )

    def check(self, output_path: str | Path | None) -> ExtractionSafetyResult:
        """递归检查输出目录，并返回所有警告和失败原因。"""
        warnings: list[str] = []
        reasons: list[str] = []

        if output_path is None:
            return ExtractionSafetyResult(
                safe=False,
                reasons=["解压结果没有输出目录"],
            )

        root_path = Path(output_path).expanduser()
        if self._is_link_or_reparse_point(root_path):
            reasons.append("输出目录是符号链接或重解析点，无法安全验证实际范围")
        root = root_path.resolve()
        if not root.exists():
            return ExtractionSafetyResult(
                safe=False,
                reasons=[f"输出目录不存在: {root}"],
            )
        if not root.is_dir():
            return ExtractionSafetyResult(
                safe=False,
                reasons=[f"输出路径不是目录: {root}"],
            )
        file_count = 0
        total_size = 0

        def record_walk_error(error: OSError) -> None:
            reasons.append(f"无法读取输出目录内容: {error}")

        for current_path, directory_names, file_names in os.walk(
            root, topdown=True, onerror=record_walk_error, followlinks=False
        ):
            current = Path(current_path)

            # 不跟随目录符号链接，避免统计到输出目录之外。
            for directory_name in directory_names.copy():
                directory_path = current / directory_name
                if self._is_link_or_reparse_point(directory_path):
                    directory_names.remove(directory_name)
                    reasons.append(
                        f"输出包含目录符号链接或重解析点: {directory_path}"
                    )

            for file_name in file_names:
                file_path = current / file_name
                if self._is_link_or_reparse_point(file_path):
                    reasons.append(
                        f"输出包含文件符号链接或重解析点: {file_path}"
                    )
                    continue
                file_count += 1
                try:
                    # lstat 不跟随文件符号链接。
                    total_size += file_path.lstat().st_size
                except OSError as error:
                    reasons.append(f"无法读取输出文件信息: {error}")

        max_files = self.settings.max_extracted_files
        if max_files is not None and file_count > max_files:
            reasons.append(
                f"解压文件数量超过限制: {file_count} > {max_files}"
            )

        max_size_mb = self.settings.max_total_extracted_size_mb
        if max_size_mb is not None:
            max_size = max_size_mb * self.BYTES_PER_MB
            if total_size > max_size:
                reasons.append(
                    "解压文件总大小超过限制: "
                    f"{total_size} 字节 > {max_size} 字节"
                )

        return ExtractionSafetyResult(
            safe=not reasons,
            warnings=warnings,
            reasons=reasons,
        )

    @staticmethod
    def _is_link_or_reparse_point(path: Path) -> bool:
        """Reject links and Windows reparse points before later copy/hash steps."""
        if path.is_symlink():
            return True
        try:
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
        except OSError:
            return False
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_flag)

    @staticmethod
    def _validate_limit(name: str, value: int | None) -> None:
        if value is not None and value < 0:
            raise ValueError(f"{name} 不能小于 0")
