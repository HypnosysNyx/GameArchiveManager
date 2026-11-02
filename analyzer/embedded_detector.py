"""Detect structurally valid archives appended to approved host files."""

import struct
import zlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class EmbeddedValidationResult(str, Enum):
    """The execution eligibility of one embedded archive candidate."""

    VALID = "VALID"
    VALID_ENCRYPTED = "VALID_ENCRYPTED"
    INVALID_STRUCTURE = "INVALID_STRUCTURE"


class EmbeddedDiagnosticReason(str, Enum):
    """A bounded, password-free reason for the latest detector decision."""

    RAW_HIT_LIMIT_REACHED = "RAW_HIT_LIMIT_REACHED"
    CANDIDATE_LIMIT_REACHED = "CANDIDATE_LIMIT_REACHED"
    CANCELLED = "CANCELLED"
    VALIDATION_LIMIT_REACHED = "VALIDATION_LIMIT_REACHED"
    HOST_TYPE_DISABLED = "HOST_TYPE_DISABLED"
    NO_SIGNATURE = "NO_SIGNATURE"
    SCAN_LIMIT_REACHED = "SCAN_LIMIT_REACHED"
    INVALID_STRUCTURE = "INVALID_STRUCTURE"
    INVALID_CRC = "INVALID_CRC"
    UNSUPPORTED_HEADER = "UNSUPPORTED_HEADER"
    VALID = "VALID"
    VALID_ENCRYPTED = "VALID_ENCRYPTED"


@dataclass(frozen=True)
class EmbeddedArchiveCandidate:
    """Describe one signature candidate and its structural validation result."""

    host_file: Path
    offset: int
    format: str
    confidence: float
    validation_result: EmbeddedValidationResult
    reason: EmbeddedDiagnosticReason = EmbeddedDiagnosticReason.INVALID_STRUCTURE


@dataclass(frozen=True)
class EmbeddedDetectionDiagnostic:
    """Summarize the latest detector decision without sensitive tool output."""

    host_file: Path
    reason: EmbeddedDiagnosticReason
    file_size: int = 0
    scanned_bytes: int = 0
    offset: int | None = None
    format: str = ""


class EmbeddedArchiveDetector:
    """Stream a bounded prefix and validate candidates before returning them."""

    SIGNATURES = {
        "RAR": (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"),
        "ZIP": (b"PK\x03\x04",),
        "7Z": (b"7z\xbc\xaf\x27\x1c",),
    }
    CHUNK_SIZE = 1024 * 1024
    DEFAULT_MAX_SCAN_BYTES = 512 * 1024 * 1024
    # Kept as a compatibility alias. Total host size is no longer rejected.
    DEFAULT_MAX_FILE_SIZE_BYTES = DEFAULT_MAX_SCAN_BYTES
    VALID_RESULTS = {
        EmbeddedValidationResult.VALID,
        EmbeddedValidationResult.VALID_ENCRYPTED,
    }

    def __init__(
        self,
        max_file_size_bytes: int | None = None,
        max_scan_bytes: int | None = None,
        max_raw_hits: int = 4096,
        max_candidates: int = 8,
    ) -> None:
        # Older callers may still pass max_file_size_bytes. It is retained as
        # an attribute only; max_scan_bytes is the sole I/O bound.
        self.max_file_size_bytes = (
            self.DEFAULT_MAX_FILE_SIZE_BYTES
            if max_file_size_bytes is None
            else max_file_size_bytes
        )
        self.max_scan_bytes = (
            self.DEFAULT_MAX_SCAN_BYTES
            if max_scan_bytes is None
            else max_scan_bytes
        )
        if self.max_file_size_bytes <= 0 or self.max_scan_bytes <= 0:
            raise ValueError("embedded scan limits must be greater than zero")
        if max_raw_hits <= 0 or max_candidates <= 0:
            raise ValueError("candidate limits must be positive")
        self.max_raw_hits = min(max_raw_hits, 4096)
        self.max_candidates = min(max_candidates, 8)
        self.last_diagnostic: EmbeddedDetectionDiagnostic | None = None

    def detect(self, file_path: str | Path) -> EmbeddedArchiveCandidate | None:
        """Return the first structurally valid candidate within the scan bound."""
        candidates = self.find_candidates(file_path)
        return next(
            (
                candidate
                for candidate in candidates
                if candidate.validation_result in self.VALID_RESULTS
            ),
            None,
        )

    def find_candidates(self, file_path: str | Path) -> list[EmbeddedArchiveCandidate]:
        """Compatibility preview: stop at the first provisional candidate."""
        found = []
        for candidate in self.iter_candidates(file_path, include_invalid=True):
            found.append(candidate)
            if candidate.validation_result in self.VALID_RESULTS:
                break
        return found

    def iter_candidates(self, file_path, *, cancelled=lambda: False,
                        include_invalid=False):
        """Lazy host-scoped enumeration; resuming never resets hit/candidate budgets."""
        path = Path(file_path).expanduser().resolve()
        self.last_diagnostic = None
        if not path.is_file():
            self._record(path, EmbeddedDiagnosticReason.INVALID_STRUCTURE)
            return
        size = path.stat().st_size
        limit = min(size, self.max_scan_bytes)
        raw_hits = plausible = 0
        last_reason = EmbeddedDiagnosticReason.NO_SIGNATURE
        with path.open("rb") as source:
            for offset, fmt in self._signature_candidates(source, limit, cancelled):
                if cancelled():
                    self._record(path, EmbeddedDiagnosticReason.CANCELLED, file_size=size)
                    return
                if raw_hits >= self.max_raw_hits:
                    self._record(path, EmbeddedDiagnosticReason.RAW_HIT_LIMIT_REACHED,
                                 file_size=size, scanned_bytes=min(source.tell(), limit))
                    return
                raw_hits += 1
                result, reason = self.validate_candidate(path, offset, fmt, cancelled=cancelled)
                if reason in (EmbeddedDiagnosticReason.CANCELLED,
                              EmbeddedDiagnosticReason.VALIDATION_LIMIT_REACHED):
                    self._record(path, reason, file_size=size,
                                 scanned_bytes=min(source.tell(), limit))
                    return
                last_reason = reason
                candidate = EmbeddedArchiveCandidate(path, offset, fmt,
                    1.0 if result in self.VALID_RESULTS else 0.0, result, reason)
                if result in self.VALID_RESULTS:
                    if plausible >= self.max_candidates:
                        self._record(path, EmbeddedDiagnosticReason.CANDIDATE_LIMIT_REACHED,
                                     file_size=size, scanned_bytes=min(source.tell(), limit))
                        return
                    plausible += 1
                    self._record(path, reason, file_size=size,
                                 scanned_bytes=min(source.tell(), limit),
                                 offset=offset, archive_format=fmt)
                    yield candidate
                    if plausible >= self.max_candidates:
                        self._record(path, EmbeddedDiagnosticReason.CANDIDATE_LIMIT_REACHED,
                                     file_size=size, scanned_bytes=min(source.tell(), limit))
                        return
                elif include_invalid:
                    yield candidate
            scanned_bytes = min(source.tell(), limit)
        reason = (EmbeddedDiagnosticReason.CANCELLED if cancelled() else
                  EmbeddedDiagnosticReason.SCAN_LIMIT_REACHED if size > limit else last_reason)
        self._record(path, reason, file_size=size, scanned_bytes=scanned_bytes)

    def record_host_type_disabled(self, file_path: str | Path) -> None:
        """Record that ArchiveAnalyzer intentionally skipped this host type."""
        path = Path(file_path).expanduser().resolve()
        try:
            file_size = path.stat().st_size
        except OSError:
            file_size = 0
        self._record(
            path,
            EmbeddedDiagnosticReason.HOST_TYPE_DISABLED,
            file_size=file_size,
        )

    def validate_candidate(
        self, path: Path, offset: int, archive_format: str, *, cancelled=lambda: False
    ) -> tuple[EmbeddedValidationResult, EmbeddedDiagnosticReason]:
        """Validate one marker while preserving the exact bounded reason."""
        try:
            if archive_format == "ZIP":
                return (
                    (EmbeddedValidationResult.VALID, EmbeddedDiagnosticReason.VALID)
                    if self._validate_zip(path, offset)
                    else (
                        EmbeddedValidationResult.INVALID_STRUCTURE,
                        EmbeddedDiagnosticReason.INVALID_STRUCTURE,
                    )
                )
            if archive_format == "RAR":
                return self._validate_rar_details(path, offset)
            if archive_format == "7Z":
                return self._validate_7z_details(path, offset, cancelled)
        except (OSError, struct.error, ValueError):
            return (
                EmbeddedValidationResult.INVALID_STRUCTURE,
                EmbeddedDiagnosticReason.INVALID_STRUCTURE,
            )
        return (
            EmbeddedValidationResult.INVALID_STRUCTURE,
            EmbeddedDiagnosticReason.UNSUPPORTED_HEADER,
        )

    @classmethod
    def _validate_candidate(
        cls, path: Path, offset: int, archive_format: str
    ) -> bool:
        """Compatibility boolean wrapper around detailed validation."""
        result, _ = cls().validate_candidate(path, offset, archive_format)
        return result in cls.VALID_RESULTS

    def _record(
        self,
        path: Path,
        reason: EmbeddedDiagnosticReason,
        *,
        file_size: int = 0,
        scanned_bytes: int = 0,
        offset: int | None = None,
        archive_format: str = "",
    ) -> None:
        self.last_diagnostic = EmbeddedDetectionDiagnostic(
            host_file=path,
            reason=reason,
            file_size=file_size,
            scanned_bytes=scanned_bytes,
            offset=offset,
            format=archive_format,
        )

    @classmethod
    def get_host_format(cls, file_path: str | Path) -> str:
        path = Path(file_path).expanduser().resolve()
        try:
            with path.open("rb") as source:
                return cls._container_format(source.read(16))
        except OSError:
            return "UNKNOWN"

    @classmethod
    def _signature_candidates(cls, source, scan_limit: int, cancelled=lambda: False):
        """Yield marker positions in file order while retaining chunk overlap."""
        max_signature_size = max(
            len(signature)
            for signatures in cls.SIGNATURES.values()
            for signature in signatures
        )
        overlap = max_signature_size - 1
        carry = b""
        bytes_read = 0
        last_offset = -1
        while bytes_read < scan_limit:
            if cancelled():
                return
            chunk = source.read(min(cls.CHUNK_SIZE, scan_limit - bytes_read))
            if not chunk:
                break
            data = carry + chunk
            data_offset = bytes_read - len(carry)
            # One pending hit per signature, rather than collecting all hits
            # from hostile chunks before the raw-hit limit can be enforced.
            signatures = [(fmt, sig) for fmt, sigs in cls.SIGNATURES.items() for sig in sigs]
            positions = [data.find(sig) for _, sig in signatures]
            while any(pos >= 0 for pos in positions):
                pos, index = min((pos, i) for i, pos in enumerate(positions) if pos >= 0)
                fmt, sig = signatures[index]
                absolute = data_offset + pos
                if absolute > max(0, last_offset):
                    last_offset = absolute
                    yield absolute, fmt
                positions[index] = data.find(sig, pos + 1)
            carry = data[-overlap:] if overlap else b""
            bytes_read += len(chunk)

    @staticmethod
    def _validate_zip(path: Path, offset: int) -> bool:
        """Validate a local header and matching central directory/EOCD."""
        file_size = path.stat().st_size
        with path.open("rb") as source:
            source.seek(offset)
            local_header = source.read(30)
            if len(local_header) != 30 or not local_header.startswith(b"PK\x03\x04"):
                return False
            fields = struct.unpack("<4s5H3L2H", local_header)
            file_name_size, extra_size = fields[-2:]
            if file_name_size == 0 or offset + 30 + file_name_size + extra_size > file_size:
                return False
            tail_size = min(file_size - offset, 65557)
            source.seek(file_size - tail_size)
            tail = source.read(tail_size)
            eocd_position = tail.rfind(b"PK\x05\x06")
            if eocd_position < 0 or eocd_position + 22 > len(tail):
                return False
            eocd = struct.unpack("<4s4H2LH", tail[eocd_position : eocd_position + 22])
            entry_count, central_size, central_offset, comment_size = (
                eocd[4], eocd[5], eocd[6], eocd[7]
            )
            eocd_absolute = file_size - tail_size + eocd_position
            central_absolute = offset + central_offset
            if entry_count == 0 or eocd_position + 22 + comment_size > len(tail):
                return False
            if central_absolute + central_size > eocd_absolute:
                return False
            source.seek(central_absolute)
            return source.read(4) == b"PK\x01\x02"

    @classmethod
    def _validate_rar_details(
        cls, path: Path, offset: int
    ) -> tuple[EmbeddedValidationResult, EmbeddedDiagnosticReason]:
        file_size = path.stat().st_size
        with path.open("rb") as source:
            source.seek(offset)
            signature = source.read(8)
            if signature.startswith(b"Rar!\x1a\x07\x00"):
                source.seek(offset + 7)
                base_header = source.read(7)
                if len(base_header) != 7:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
                stored_crc, header_type, _, header_size = struct.unpack(
                    "<HBHH", base_header
                )
                if not 7 <= header_size <= 2 * 1024 * 1024:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
                if offset + 7 + header_size > file_size:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
                if header_type != 0x73:
                    return cls._invalid(EmbeddedDiagnosticReason.UNSUPPORTED_HEADER)
                source.seek(offset + 7)
                header = source.read(header_size)
                if len(header) != header_size:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
                if (zlib.crc32(header[2:]) & 0xFFFF) != stored_crc:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_CRC)
                return EmbeddedValidationResult.VALID, EmbeddedDiagnosticReason.VALID

            if signature == b"Rar!\x1a\x07\x01\x00":
                stored_crc_data = source.read(4)
                if len(stored_crc_data) != 4:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
                stored_crc = int.from_bytes(stored_crc_data, "little")
                size_value, size_bytes = cls._read_vint(source)
                if not 1 <= size_value <= 2 * 1024 * 1024:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
                if source.tell() + size_value > file_size:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
                header_data = source.read(size_value)
                if len(header_data) != size_value:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
                calculated = zlib.crc32(size_bytes + header_data) & 0xFFFFFFFF
                if calculated != stored_crc:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_CRC)

                header_type, cursor = cls._decode_vint(header_data)
                _, flags_size = cls._decode_vint(header_data[cursor:])
                cursor += flags_size
                if header_type == 1:
                    return EmbeddedValidationResult.VALID, EmbeddedDiagnosticReason.VALID
                if header_type == 4:
                    if not cls._validate_rar5_encryption_header(
                        header_data, cursor
                    ):
                        return cls._invalid(
                            EmbeddedDiagnosticReason.INVALID_STRUCTURE
                        )
                    return (
                        EmbeddedValidationResult.VALID_ENCRYPTED,
                        EmbeddedDiagnosticReason.VALID_ENCRYPTED,
                    )
                return cls._invalid(EmbeddedDiagnosticReason.UNSUPPORTED_HEADER)

        return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)

    @classmethod
    def _validate_rar5_encryption_header(
        cls, header_data: bytes, cursor: int
    ) -> bool:
        """Validate the bounded fields required by a RAR5 encryption header."""
        encryption_version, used = cls._decode_vint(header_data[cursor:])
        cursor += used
        encryption_flags, used = cls._decode_vint(header_data[cursor:])
        cursor += used
        if encryption_version != 0 or cursor >= len(header_data):
            return False
        # KDF count byte + 16-byte salt are mandatory. Flag bit 0 adds the
        # 8-byte password-check value and its 4-byte checksum.
        required = 1 + 16 + (12 if encryption_flags & 0x01 else 0)
        return cursor + required <= len(header_data)

    @classmethod
    def _validate_rar(cls, path: Path, offset: int) -> bool:
        result, _ = cls._validate_rar_details(path, offset)
        return result in cls.VALID_RESULTS

    @classmethod
    def _validate_7z_details(
        cls, path: Path, offset: int, cancelled=lambda: False
    ) -> tuple[EmbeddedValidationResult, EmbeddedDiagnosticReason]:
        with path.open("rb") as source:
            source.seek(offset)
            header = source.read(32)
            if len(header) != 32 or not header.startswith(b"7z\xbc\xaf\x27\x1c"):
                return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
            stored_crc = int.from_bytes(header[8:12], "little")
            if (zlib.crc32(header[12:32]) & 0xFFFFFFFF) != stored_crc:
                return cls._invalid(EmbeddedDiagnosticReason.INVALID_CRC)
            next_offset = int.from_bytes(header[12:20], "little")
            next_size = int.from_bytes(header[20:28], "little")
            next_crc = int.from_bytes(header[28:32], "little")
            next_position = offset + 32 + next_offset
            file_size = path.stat().st_size
            if next_size <= 0 or next_position + next_size > file_size:
                return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
            if next_size > cls.DEFAULT_MAX_SCAN_BYTES:
                return cls._invalid(EmbeddedDiagnosticReason.VALIDATION_LIMIT_REACHED)
            source.seek(next_position)
            calculated_crc = 0
            remaining = next_size
            while remaining:
                if cancelled():
                    return cls._invalid(EmbeddedDiagnosticReason.CANCELLED)
                chunk = source.read(min(cls.CHUNK_SIZE, remaining))
                if not chunk:
                    return cls._invalid(EmbeddedDiagnosticReason.INVALID_STRUCTURE)
                calculated_crc = zlib.crc32(chunk, calculated_crc)
                remaining -= len(chunk)
            if (calculated_crc & 0xFFFFFFFF) != next_crc:
                return cls._invalid(EmbeddedDiagnosticReason.INVALID_CRC)
            return EmbeddedValidationResult.VALID, EmbeddedDiagnosticReason.VALID

    @classmethod
    def _validate_7z(cls, path: Path, offset: int) -> bool:
        result, _ = cls._validate_7z_details(path, offset)
        return result is EmbeddedValidationResult.VALID

    @staticmethod
    def _invalid(
        reason: EmbeddedDiagnosticReason,
    ) -> tuple[EmbeddedValidationResult, EmbeddedDiagnosticReason]:
        return EmbeddedValidationResult.INVALID_STRUCTURE, reason

    @staticmethod
    def _read_vint(source) -> tuple[int, bytes]:
        encoded = bytearray()
        while len(encoded) < 10:
            byte = source.read(1)
            if not byte:
                raise ValueError("incomplete vint")
            encoded.extend(byte)
            if byte[0] & 0x80 == 0:
                value, _ = EmbeddedArchiveDetector._decode_vint(bytes(encoded))
                return value, bytes(encoded)
        raise ValueError("vint is too long")

    @staticmethod
    def _decode_vint(data: bytes) -> tuple[int, int]:
        value = 0
        shift = 0
        for index, byte in enumerate(data):
            value |= (byte & 0x7F) << shift
            if byte & 0x80 == 0:
                return value, index + 1
            shift += 7
        raise ValueError("incomplete vint")

    @staticmethod
    def _container_format(header: bytes) -> str:
        if header.startswith(b"\xff\xd8\xff"):
            return "JPEG"
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "PNG"
        if header.startswith(b"BM"):
            return "BMP"
        if header.startswith((b"GIF87a", b"GIF89a")):
            return "GIF"
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return "WEBP"
        if len(header) >= 8 and header[4:8] == b"ftyp":
            return "MP4"
        if header.startswith(b"\x1aE\xdf\xa3"):
            return "MKV"
        return "UNKNOWN"
