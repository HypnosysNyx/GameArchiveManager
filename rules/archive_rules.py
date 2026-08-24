"""压缩文件格式判断的基础规则。"""

from pathlib import Path

# 支持的压缩格式。文件头签名供以后识别真实格式时使用。
SUPPORTED_ARCHIVE_FORMATS = ("zip", "rar", "7z", "lz4")
ARCHIVE_SIGNATURES = {
    "zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "rar": (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"),
    "7z": (b"7z\xbc\xaf\x27\x1c",),
    "lz4": (b"\x04\x22\x4d\x18",),
}


def format_from_extension(file_path: str | Path) -> str | None:
    """根据扩展名返回候选格式；真实格式以后再结合文件头确认。"""
    extension = Path(file_path).suffix.lower().lstrip(".")
    return extension if extension in SUPPORTED_ARCHIVE_FORMATS else None


def has_disguised_extension(file_path: str | Path, real_format: str) -> bool:
    """判断扩展名是否与文件头识别出的真实格式不一致。"""
    return format_from_extension(file_path) != real_format.lower()
