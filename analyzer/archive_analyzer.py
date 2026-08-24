"""通过文件头识别压缩文件的真实格式。"""

from pathlib import Path

from analyzer.embedded_detector import EmbeddedArchiveDetector
from analyzer.models import ArchiveInfo
from analyzer.volume_detector import SplitArchiveDetector


class ArchiveAnalyzer:
    """读取有限的文件头数据，识别压缩格式和简单容器链。"""

    EMBEDDED_HOST_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".webp",
        ".mp4",
        ".mkv",
    }
    EMBEDDED_BLOCKED_EXTENSIONS = {
        ".exe",
        ".dll",
        ".sys",
        ".dat",
        ".bin",
        ".pak",
        ".assets",
        ".bundle",
        ".so",
    }

    FILE_SIGNATURES = {
        "ZIP": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
        "RAR": (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"),
        "7Z": (b"7z\xbc\xaf\x27\x1c",),
        "LZ4": (b"\x04\x22\x4d\x18",),
    }
    HEADER_SIZE = 8
    CONTENT_PROBE_SIZE = 1024 * 1024
    LZ4_SIGNATURE = b"\x04\x22\x4d\x18"
    RAR_MARKER = b"Rar!"

    def __init__(self) -> None:
        self.volume_detector = SplitArchiveDetector()
        self.embedded_detector = EmbeddedArchiveDetector()

    def analyze(self, file_path: str | Path) -> ArchiveInfo:
        """分析一个文件并返回真实格式信息。"""
        requested_path = Path(file_path).expanduser().resolve()
        volume_set = self.volume_detector.detect(requested_path)
        path = volume_set.entry_path if volume_set else requested_path

        if not path.exists() and volume_set is None:
            raise FileNotFoundError(f"文件不存在: {path}")
        if path.exists() and not path.is_file():
            raise IsADirectoryError(f"分析路径不是文件: {path}")

        if path.is_file():
            # 最多读取前 1 MiB，用于识别外层格式和有限的内层标记。
            with path.open("rb") as file:
                probe = file.read(self.CONTENT_PROBE_SIZE)
        else:
            probe = b""

        real_format = self._detect_format(probe[: self.HEADER_SIZE])
        if real_format == "UNKNOWN" and volume_set is not None:
            real_format = volume_set.archive_format
        embedded_match = None
        if real_format == "UNKNOWN" and path.is_file():
            if self._allows_embedded_scan(path):
                embedded_match = self.embedded_detector.detect(path)
            else:
                self.embedded_detector.record_host_type_disabled(path)
        container_chain = self._detect_container_chain(real_format, probe)
        if embedded_match is not None:
            container_chain = [
                self.embedded_detector.get_host_format(path),
                embedded_match.format,
            ]
        extension = path.suffix

        if real_format == "UNKNOWN":
            # 无法识别时不猜测扩展名是否伪装。
            is_fake_extension = False
            confidence = 0.0
        else:
            expected_extension = f".{real_format.lower()}"
            is_fake_extension = (
                False
                if volume_set is not None
                else extension.lower() != expected_extension
            )
            confidence = 1.0

        return ArchiveInfo(
            file_path=path,
            extension=extension,
            real_format=real_format,
            is_fake_extension=is_fake_extension,
            confidence=confidence,
            container_chain=container_chain,
            is_multi_volume=volume_set is not None,
            volume_group=volume_set.group_id if volume_set else "",
            volume_files=volume_set.volume_files if volume_set else [],
            missing_volume_files=(
                volume_set.missing_files if volume_set else []
            ),
            is_embedded_archive=embedded_match is not None,
            embedded_offset=(embedded_match.offset if embedded_match else None),
            embedded_container_format=(
                embedded_match.format if embedded_match else ""
            ),
            embedded_validation_status=(
                embedded_match.validation_result.value
                if embedded_match
                else ""
            ),
            embedded_validation_reason=(
                embedded_match.reason.value
                if embedded_match
                else (
                    self.embedded_detector.last_diagnostic.reason.value
                    if (
                        real_format == "UNKNOWN"
                        and self.embedded_detector.last_diagnostic is not None
                    )
                    else ""
                )
            ),
        )

    @classmethod
    def _allows_embedded_scan(cls, path: Path) -> bool:
        """Use an explicit media-host allowlist; UNKNOWN files stay disabled."""
        extension = path.suffix.casefold()
        if extension in cls.EMBEDDED_BLOCKED_EXTENSIONS:
            return False
        return extension in cls.EMBEDDED_HOST_EXTENSIONS

    @classmethod
    def _detect_format(cls, header: bytes) -> str:
        """将文件头与已知格式签名进行比较。"""
        for real_format, signatures in cls.FILE_SIGNATURES.items():
            if any(header.startswith(signature) for signature in signatures):
                return real_format
        return "UNKNOWN"

    @classmethod
    def _detect_container_chain(
        cls, real_format: str, probe: bytes
    ) -> list[str]:
        """识别外层 LZ4 后有限探测后续数据中的 RAR 标记。"""
        if real_format == "UNKNOWN":
            return []
        if real_format != "LZ4":
            return [real_format]

        chain = ["LZ4"]
        subsequent_data = probe[len(cls.LZ4_SIGNATURE) :]
        if cls.RAR_MARKER in subsequent_data:
            chain.append("RAR")
        return chain
