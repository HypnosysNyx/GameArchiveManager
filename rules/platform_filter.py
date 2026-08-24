"""递归解压流程使用的平台内容过滤器。"""

from dataclasses import dataclass
from pathlib import Path

from config.settings import Settings
from rules.platform_rules import is_android_name, is_az_name


@dataclass(frozen=True)
class PlatformFilterResult:
    """保存一次平台过滤判断结果。"""

    skipped: bool
    reason: str = ""


class PlatformFilter:
    """根据 Settings 判断路径是否属于应跳过的平台内容。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def check(
        self,
        archive_path: str | Path,
        settings: Settings | None = None,
        root_path: str | Path | None = None,
    ) -> PlatformFilterResult:
        """检查内容根以下的相对组件，不让系统父路径影响分类。"""
        active_settings = settings or self.settings
        archive = Path(archive_path).expanduser().resolve()

        for part in self._content_parts(archive, root_path):
            if active_settings.ignore_android and is_android_name(part):
                return PlatformFilterResult(
                    skipped=True,
                    reason=f"路径名称命中 Android/安卓 忽略规则: {part}",
                )
            if active_settings.ignore_AZ and is_az_name(part):
                return PlatformFilterResult(
                    skipped=True,
                    reason=f"路径名称命中 AZ 忽略规则: {part}",
                )
        return PlatformFilterResult(skipped=False)

    def get_skip_reason(
        self, archive_path: str | Path, root_path: str | Path | None = None
    ) -> str | None:
        """兼容旧调用，并在提供内容根时限制父目录检查范围。"""
        result = self.check(archive_path, root_path=root_path)
        return result.reason if result.skipped else None

    @staticmethod
    def _content_parts(
        archive: Path, root_path: str | Path | None
    ) -> tuple[str, ...]:
        """Return only caller-scoped content components.

        Without a root, only the archive name is safe evidence. If a supplied
        root does not contain the archive, fall back to the same conservative
        behavior instead of inspecting unrelated absolute ancestors.
        """
        if root_path is None:
            return (archive.name,)
        root = Path(root_path).expanduser().resolve()
        try:
            relative = archive.relative_to(root)
        except ValueError:
            return (archive.name,)
        return relative.parts
