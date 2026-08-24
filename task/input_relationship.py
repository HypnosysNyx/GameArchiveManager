"""Resolve relationships between confirmed INITIAL_SCAN archive inputs."""

import hashlib
import subprocess
from dataclasses import replace
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import perf_counter

from analyzer.models import ArchiveInfo
from config.settings import Settings
from tools.models import ToolName
from tools.tool_manager import ToolManager


class InputRelationshipType(str, Enum):
    INDEPENDENT_INPUT = "INDEPENDENT_INPUT"
    POSSIBLE_OUTER_INNER_CHAIN = "POSSIBLE_OUTER_INNER_CHAIN"
    CONFIRMED_OUTER_CONTAINS_EXISTING_INNER = (
        "CONFIRMED_OUTER_CONTAINS_EXISTING_INNER"
    )
    SAME_CONTENT_DIFFERENT_SOURCE = "SAME_CONTENT_DIFFERENT_SOURCE"
    UNKNOWN = "UNKNOWN"


class RelationshipConfidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RelationshipVerificationStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    FAILED = "FAILED"


@dataclass
class InputArchiveRelationship:
    source_path: Path
    related_path: Path | None
    relationship_type: InputRelationshipType
    confidence: RelationshipConfidence
    verification_method: str
    verification_status: RelationshipVerificationStatus
    canonical_input: Path | None = None
    suppressed_input: Path | None = None
    reason: str = ""
    verification_bytes_read: int = 0
    verification_time: float = 0.0


@dataclass
class InputRelationshipResolution:
    relationships: list[InputArchiveRelationship] = field(default_factory=list)
    canonical_archives: list[ArchiveInfo] = field(default_factory=list)
    suppressed_paths: set[Path] = field(default_factory=set)


class InputArchiveRelationshipResolver:
    """Use cheap chain matching, then bounded streaming verification."""

    def __init__(
        self,
        settings: Settings | None = None,
        tool_manager: ToolManager | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.tool_manager = tool_manager or ToolManager(settings=self.settings)
        self._verification_cache: dict[tuple, InputArchiveRelationship] = {}

    def resolve(
        self,
        archives: list[ArchiveInfo],
        process_all_inputs: bool = False,
    ) -> InputRelationshipResolution:
        relationships: list[InputArchiveRelationship] = []
        involved: set[Path] = set()
        suppressed: set[Path] = set()

        for outer in archives:
            if not self._is_lz4_single_stream_wrapper(outer):
                continue
            inner = self._matching_existing_inner(outer, archives)
            if inner is None:
                continue
            outer_path = outer.file_path.resolve()
            inner_path = inner.file_path.resolve()
            involved.update({outer_path, inner_path})
            relationship = self._verify_lz4_relationship(outer_path, inner_path)
            if (
                relationship.relationship_type
                is InputRelationshipType.CONFIRMED_OUTER_CONTAINS_EXISTING_INNER
                and not process_all_inputs
            ):
                suppressed.add(outer_path)
            elif process_all_inputs:
                relationship.suppressed_input = None
                relationship.reason += "; PROCESS_ALL_INPUTS_OVERRIDE"
            relationships.append(relationship)

        for archive in archives:
            path = archive.file_path.resolve()
            if path in involved:
                continue
            relationships.append(
                InputArchiveRelationship(
                    source_path=path,
                    related_path=None,
                    relationship_type=InputRelationshipType.INDEPENDENT_INPUT,
                    confidence=RelationshipConfidence.HIGH,
                    verification_method="NO_COMPATIBLE_WRAPPER_RELATION",
                    verification_status=RelationshipVerificationStatus.NOT_REQUIRED,
                    canonical_input=path,
                    reason="No compatible outer/inner input pair was found",
                )
            )

        canonical = [
            archive
            for archive in archives
            if archive.file_path.resolve() not in suppressed
        ]
        return InputRelationshipResolution(relationships, canonical, suppressed)

    @staticmethod
    def _is_lz4_single_stream_wrapper(archive: ArchiveInfo) -> bool:
        chain = [item.upper() for item in archive.container_chain]
        return len(chain) == 2 and chain[0] == "LZ4" and chain[1] in {
            "ZIP", "RAR", "7Z"
        }

    @staticmethod
    def _matching_existing_inner(
        outer: ArchiveInfo, archives: list[ArchiveInfo]
    ) -> ArchiveInfo | None:
        expected_name = outer.file_path.stem.casefold()
        expected_format = outer.container_chain[1].upper()
        matches = [
            candidate
            for candidate in archives
            if candidate.file_path.resolve() != outer.file_path.resolve()
            and candidate.file_path.parent.resolve()
            == outer.file_path.parent.resolve()
            and candidate.file_path.name.casefold() == expected_name
            and candidate.real_format.upper() == expected_format
        ]
        return matches[0] if len(matches) == 1 else None

    def _verify_lz4_relationship(
        self, outer_path: Path, inner_path: Path
    ) -> InputArchiveRelationship:
        try:
            outer_stat = outer_path.stat()
            inner_stat = inner_path.stat()
            cache_key = (
                outer_path,
                outer_stat.st_size,
                outer_stat.st_mtime_ns,
                inner_path,
                inner_stat.st_size,
                inner_stat.st_mtime_ns,
            )
        except OSError:
            cache_key = None
        if cache_key is not None and cache_key in self._verification_cache:
            return replace(self._verification_cache[cache_key])

        started = perf_counter()
        method = "LZ4_DECODED_STREAM_SHA256"
        info = self.tool_manager.get_tool_status(ToolName.LZ4)
        if not info.verified or info.path is None:
            relationship = InputArchiveRelationship(
                source_path=outer_path,
                related_path=inner_path,
                relationship_type=InputRelationshipType.POSSIBLE_OUTER_INNER_CHAIN,
                confidence=RelationshipConfidence.MEDIUM,
                verification_method=method,
                verification_status=RelationshipVerificationStatus.FAILED,
                reason="LZ4 tool is unavailable or unverified; kept both inputs",
                verification_time=perf_counter() - started,
            )
            return relationship

        bytes_read = 0
        process: subprocess.Popen | None = None
        try:
            inner_size = inner_path.stat().st_size
            inner_hash, inner_bytes = self._hash_file(inner_path)
            bytes_read += inner_bytes
            decoded_hash = hashlib.sha256()
            decoded_bytes = 0
            process = subprocess.Popen(
                [str(info.path), "-d", "-c", str(outer_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            assert process.stdout is not None
            try:
                while True:
                    block = process.stdout.read(8 * 1024 * 1024)
                    if not block:
                        break
                    decoded_hash.update(block)
                    decoded_bytes += len(block)
                    bytes_read += len(block)
                    if decoded_bytes > inner_size:
                        process.kill()
                        process.wait()
                        relationship = self._mismatch(
                            outer_path, inner_path, method, bytes_read, started,
                            "Decoded size differs from the existing inner archive",
                        )
                        return self._remember(cache_key, relationship)
                    if (
                        perf_counter() - started
                        > self.settings.extraction_timeout_seconds
                    ):
                        process.kill()
                        process.wait()
                        raise TimeoutError(
                            "LZ4 relationship verification timed out"
                        )
            finally:
                process.stdout.close()
            exit_code = process.wait()
            if exit_code != 0:
                raise OSError(f"LZ4 verification exited with code {exit_code}")
            if decoded_bytes != inner_size or decoded_hash.hexdigest() != inner_hash:
                relationship = self._mismatch(
                    outer_path, inner_path, method, bytes_read, started,
                    "Decoded content SHA256 differs; kept both inputs",
                )
                return self._remember(cache_key, relationship)
            relationship = InputArchiveRelationship(
                source_path=outer_path,
                related_path=inner_path,
                relationship_type=(
                    InputRelationshipType.CONFIRMED_OUTER_CONTAINS_EXISTING_INNER
                ),
                confidence=RelationshipConfidence.HIGH,
                verification_method=method,
                verification_status=RelationshipVerificationStatus.VERIFIED,
                canonical_input=inner_path,
                suppressed_input=outer_path,
                reason=(
                    "Decoded outer byte stream exactly matches existing inner "
                    "archive; verified inner is the lower-cost canonical input"
                ),
                verification_bytes_read=bytes_read,
                verification_time=perf_counter() - started,
            )
            return self._remember(cache_key, relationship)
        except (OSError, TimeoutError, subprocess.SubprocessError) as error:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            relationship = InputArchiveRelationship(
                source_path=outer_path,
                related_path=inner_path,
                relationship_type=InputRelationshipType.POSSIBLE_OUTER_INNER_CHAIN,
                confidence=RelationshipConfidence.MEDIUM,
                verification_method=method,
                verification_status=RelationshipVerificationStatus.FAILED,
                reason=(
                    f"Strong verification failed ({type(error).__name__}); "
                    "kept both inputs"
                ),
                verification_bytes_read=bytes_read,
                verification_time=perf_counter() - started,
            )
            return self._remember(cache_key, relationship)

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        bytes_read = 0
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
                bytes_read += len(block)
        return digest.hexdigest(), bytes_read

    @staticmethod
    def _mismatch(
        outer_path: Path,
        inner_path: Path,
        method: str,
        bytes_read: int,
        started: float,
        reason: str,
    ) -> InputArchiveRelationship:
        return InputArchiveRelationship(
            source_path=outer_path,
            related_path=inner_path,
            relationship_type=InputRelationshipType.INDEPENDENT_INPUT,
            confidence=RelationshipConfidence.HIGH,
            verification_method=method,
            verification_status=RelationshipVerificationStatus.MISMATCH,
            canonical_input=None,
            suppressed_input=None,
            reason=reason,
            verification_bytes_read=bytes_read,
            verification_time=perf_counter() - started,
        )

    def _remember(
        self,
        cache_key: tuple | None,
        relationship: InputArchiveRelationship,
    ) -> InputArchiveRelationship:
        if (
            cache_key is not None
            and relationship.verification_status
            in {
                RelationshipVerificationStatus.VERIFIED,
                RelationshipVerificationStatus.MISMATCH,
            }
        ):
            self._verification_cache[cache_key] = replace(relationship)
        return relationship

    def copy_verification_cache_from(
        self, other: "InputArchiveRelationshipResolver"
    ) -> None:
        """Reuse only results whose file size and mtime cache keys still match."""
        self._verification_cache.update(
            {
                key: replace(value)
                for key, value in other._verification_cache.items()
            }
        )
