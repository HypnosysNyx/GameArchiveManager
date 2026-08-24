"""扫描游戏资源目录，不修改目录中的任何内容。"""

import os
from pathlib import Path

from config.settings import Settings
from rules.platform_rules import is_android_name, is_az_name
from scanner.models import ScanResult


class Scanner:
    """收集目录中的文件、文件夹和压缩包候选。"""

    ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".lz4"}

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def scan(
        self,
        directory: str | Path,
        pruned_directories: set[Path] | None = None,
    ) -> ScanResult:
        """扫描指定目录并返回结果对象。"""
        root = Path(directory).expanduser().resolve()

        if not root.exists():
            raise FileNotFoundError(f"扫描目录不存在: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"扫描路径不是目录: {root}")

        result = ScanResult(root=root)
        pruned = {
            Path(path).expanduser().resolve()
            for path in (pruned_directories or set())
        }

        for current_path, directory_names, file_names in os.walk(root):
            current = Path(current_path)

            # Apply the exact boundary paths resolved by INITIAL_SCAN before
            # entering them. Scanner does not infer technical ownership from
            # directory names.
            directory_names[:] = [
                name
                for name in directory_names
                if (current / name).resolve() not in pruned
            ]

            # Task analysis can provide boundaries already classified by the
            # INITIAL_SCAN resolver. Default Scanner calls remain full scans.
            if current.resolve() in pruned:
                directory_names.clear()

            # os.walk 返回的当前路径包括扫描根目录；根目录本身不计入发现的文件夹。
            if current != root:
                result.folders.append(current)
                if self._is_ignored(current.name):
                    result.ignored.append(current)

            # 只有真实存在的空文件夹才能成为密码候选。
            # 名称不参与过滤，所以名为 game.zip 或 readme.txt 的空文件夹也会保留。
            if self._is_password_candidate_source(current, directory_names, file_names):
                result.password_candidates.append(current)

            for file_name in file_names:
                file_path = current / file_name
                result.files.append(file_path)

                if self._is_ignored(file_name):
                    result.ignored.append(file_path)

                if file_path.suffix.lower() in self.ARCHIVE_EXTENSIONS:
                    result.archive_candidates.append(file_path)

        return result

    def _is_ignored(self, name: str) -> bool:
        """只在用户显式开启设置时应用共享平台规则。"""
        return (
            self.settings.ignore_android and is_android_name(name)
        ) or (self.settings.ignore_AZ and is_az_name(name))

    @staticmethod
    def _is_password_candidate_source(
        path: Path, directory_names: list[str], file_names: list[str]
    ) -> bool:
        """仅把真实存在的空文件夹记录为密码候选来源。"""
        # Scanner 只记录事实；候选的评分、排序和尝试顺序由 Password Manager 处理。
        return (
            path.exists()
            and path.is_dir()
            and not directory_names
            and not file_names
        )
