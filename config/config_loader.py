"""从 JSON 文件安全加载 GameArchiveManager 设置。"""

import json
import warnings as python_warnings
from pathlib import Path
from typing import Callable

from config.settings import Settings


class ConfigLoader:
    """读取 config.json；缺失或无效配置始终回退到默认值。"""

    TOOL_PATH_FIELDS = {"seven_zip_path", "winrar_path", "lz4_path"}

    def __init__(self, config_path: str | Path = "config.json") -> None:
        self.config_path = Path(config_path).expanduser()
        self.warnings: list[str] = []

    def load(self, config_path: str | Path | None = None) -> Settings:
        """加载配置并返回 Settings，不创建或修改配置文件。"""
        self.warnings = []
        path = (
            Path(config_path).expanduser()
            if config_path is not None
            else self.config_path
        )

        if not path.exists():
            return Settings()
        if not path.is_file():
            self._warn(f"配置路径不是文件，已使用默认配置: {path}")
            return Settings()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            self._warn(f"配置文件无法读取，已使用默认配置: {error}")
            return Settings()

        if not isinstance(data, dict):
            self._warn("配置文件顶层必须是 JSON 对象，已使用默认配置")
            return Settings()

        valid_values: dict[str, object] = {}
        validators = self._validators()

        for field_name, value in data.items():
            validator = validators.get(field_name)
            if validator is None:
                self._warn(f"不支持的配置字段，已忽略: {field_name}")
                continue
            if not validator(value):
                self._warn(
                    f"配置值无效，已使用默认值: {field_name}={value!r}"
                )
                continue
            if field_name in self.TOOL_PATH_FIELDS and value is not None:
                tool_path = Path(value).expanduser()
                if not tool_path.is_absolute():
                    tool_path = path.parent / tool_path
                valid_values[field_name] = tool_path.resolve()
            else:
                valid_values[field_name] = value

        # 只传入验证通过的字段，其余字段自然保留 dataclass 默认值。
        return Settings(**valid_values)

    @staticmethod
    def _validators() -> dict[str, Callable[[object], bool]]:
        is_integer = lambda value: type(value) is int
        is_optional_non_negative_integer = lambda value: (
            value is None or (type(value) is int and value >= 0)
        )
        is_optional_path = lambda value: (
            value is None or (type(value) is str and bool(value.strip()))
        )

        return {
            "max_recursive_depth": lambda value: (
                is_integer(value) and value >= 0
            ),
            "max_archive_tasks": lambda value: (
                is_integer(value) and value > 0
            ),
            "max_initial_archive_tasks": lambda value: (
                is_integer(value) and value > 0
            ),
            "max_embedded_candidates": lambda value: (
                is_integer(value) and value >= 0
            ),
            "max_password_attempts": lambda value: (
                is_integer(value) and 0 <= value <= 100
            ),
            "extraction_timeout_seconds": lambda value: (
                is_integer(value) and value > 0
            ),
            "max_archive_size_mb": lambda value: (
                is_integer(value) and value >= 0
            ),
            "max_extracted_files": is_optional_non_negative_integer,
            "max_total_extracted_size_mb": is_optional_non_negative_integer,
            "ignore_android": lambda value: type(value) is bool,
            "ignore_AZ": lambda value: type(value) is bool,
            "seven_zip_path": is_optional_path,
            "winrar_path": is_optional_path,
            "lz4_path": is_optional_path,
        }

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        python_warnings.warn(message, UserWarning, stacklevel=3)


def load_settings(config_path: str | Path = "config.json") -> Settings:
    """为简单调用场景提供便捷加载函数。"""
    return ConfigLoader(config_path).load()
