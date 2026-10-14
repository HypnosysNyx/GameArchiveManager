"""Find verified archives while keeping initial and pipeline scans distinct."""

import os
from enum import Enum
from pathlib import Path

from analyzer.archive_analyzer import ArchiveAnalyzer
from analyzer.models import ArchiveInfo
from rules.container_policy import (
    ContainerRoleDecision,
    ContainerRolePolicy,
)
from scanner.initial_scan_boundary import (
    InitialArchiveCandidate,
    InitialScanBoundaryResolver,
    InitialScanClassification,
    InitialScanDiagnostics,
    InitialScanSpaceResolver,
)
from scanner.scanner import Scanner


class ArchiveScanMode(str, Enum):
    """Control whether generated output and game-content boundaries apply."""

    INITIAL_SCAN = "INITIAL_SCAN"
    PIPELINE_SCAN = "PIPELINE_SCAN"


class ArchiveFinder:
    """Read files recursively and return only analyzer-confirmed archives."""

    SUPPORTED_EXTENSIONS = {".zip", ".rar", ".7z", ".lz4"}
    SUPPORTED_FORMATS = {"ZIP", "RAR", "7Z", "LZ4"}
    MIN_CONFIDENCE = 1.0

    def __init__(
        self,
        analyzer: ArchiveAnalyzer | None = None,
        initial_boundary_resolver: InitialScanBoundaryResolver | None = None,
        container_role_policy: ContainerRolePolicy | None = None,
    ) -> None:
        self.analyzer = analyzer or ArchiveAnalyzer()
        self.initial_boundary_resolver = (
            initial_boundary_resolver or InitialScanBoundaryResolver()
        )
        self.container_role_policy = container_role_policy or ContainerRolePolicy()
        self.last_scan_diagnostics = InitialScanDiagnostics()
        self.last_container_role_decisions: list[ContainerRoleDecision] = []
        self._analysis_cache: dict[Path, tuple[tuple[int, ...], ArchiveInfo]] = {}

    def find(
        self,
        folder_path: str | Path,
        scan_mode: ArchiveScanMode = ArchiveScanMode.PIPELINE_SCAN,
        exclude_generated_outputs: bool | None = None,
        initial_space_resolver: InitialScanSpaceResolver | None = None,
    ) -> list[ArchiveInfo]:
        """Find archives; only INITIAL_SCAN applies game-root pruning."""
        if exclude_generated_outputs is not None:
            scan_mode = (
                ArchiveScanMode.INITIAL_SCAN
                if exclude_generated_outputs
                else ArchiveScanMode.PIPELINE_SCAN
            )
        if not isinstance(scan_mode, ArchiveScanMode):
            scan_mode = ArchiveScanMode(scan_mode)

        root = Path(folder_path).expanduser().resolve()
        self.last_scan_diagnostics = InitialScanDiagnostics()
        self.last_container_role_decisions = []
        if not root.exists():
            raise FileNotFoundError(f"扫描目录不存在: {root}")
        if root.is_file():
            return self._find_explicit_file(root, scan_mode)
        if not root.is_dir():
            raise NotADirectoryError(f"扫描路径不是目录: {root}")

        scan_space = initial_space_resolver or InitialScanSpaceResolver(root)

        archives: list[ArchiveInfo] = []
        seen_volume_groups: set[str] = set()
        seen_files: set[Path] = set()
        walk_entries: list[
            tuple[Path, tuple[str, ...], tuple[str, ...], tuple[int, ...]]
        ] = []
        for current_path, directory_names, file_names in os.walk(root):
            current = Path(current_path)
            try:
                directory_fingerprint = Scanner._stat_fingerprint(current.stat())
            except OSError:
                directory_fingerprint = ()
            walk_entries.append(
                (
                    current,
                    tuple(directory_names),
                    tuple(file_names),
                    directory_fingerprint,
                )
            )
            if scan_mode is ArchiveScanMode.INITIAL_SCAN:
                self.last_scan_diagnostics.visited_directory_count += 1
                allowed_directories: list[str] = []
                for name in directory_names:
                    space_boundary = scan_space.resolve(current / name)
                    if space_boundary is None:
                        allowed_directories.append(name)
                    else:
                        self.last_scan_diagnostics.boundaries.append(
                            space_boundary
                        )
                directory_names[:] = allowed_directories
                boundary = self.initial_boundary_resolver.resolve(current)
                if (
                    boundary.classification
                    is not InitialScanClassification.NORMAL_DIRECTORY
                ):
                    self.last_scan_diagnostics.boundaries.append(boundary)
                if not boundary.should_descend:
                    directory_names[:] = []
                    boundary.descended = False
                    continue

            directory_names.sort()
            file_names.sort()
            for file_name in file_names:
                file_path = current / file_name
                seen_files.add(file_path)
                try:
                    archive_info = self._analyze(file_path)
                except OSError:
                    continue
                if not self._is_confirmed_archive(archive_info):
                    continue
                decision = self.container_role_policy.classify(
                    archive_info,
                    scan_mode=scan_mode,
                    explicit_input=False,
                )
                self.last_container_role_decisions.append(decision)
                if not decision.should_auto_extract:
                    continue
                if archive_info.volume_group:
                    if archive_info.volume_group in seen_volume_groups:
                        continue
                    seen_volume_groups.add(archive_info.volume_group)
                archives.append(archive_info)
                if scan_mode is ArchiveScanMode.INITIAL_SCAN:
                    self.last_scan_diagnostics.archive_candidates.append(
                        InitialArchiveCandidate(
                            path=archive_info.file_path,
                            reason=(
                                "DISCOVERED_REAL_FORMAT_"
                                f"{archive_info.real_format}"
                            ),
                            explicit=False,
                        )
                    )
        self._analysis_cache = {
            path: cached
            for path, cached in self._analysis_cache.items()
            if path in seen_files
        }
        pruned_directories = {
            boundary.path
            for boundary in self.last_scan_diagnostics.boundaries
            if not boundary.should_descend
        }
        Scanner._remember_walk(root, pruned_directories, walk_entries)
        return archives

    def _find_explicit_file(
        self, path: Path, scan_mode: ArchiveScanMode
    ) -> list[ArchiveInfo]:
        if scan_mode is not ArchiveScanMode.INITIAL_SCAN:
            raise NotADirectoryError(f"扫描路径不是目录: {path}")
        archive_info = self._analyze(path)
        if not self._is_confirmed_archive(archive_info):
            return []
        decision = self.container_role_policy.classify(
            archive_info,
            scan_mode=scan_mode,
            explicit_input=True,
        )
        self.last_container_role_decisions.append(decision)
        if not decision.should_auto_extract:
            return []
        self.last_scan_diagnostics.archive_candidates.append(
            InitialArchiveCandidate(
                path=archive_info.file_path,
                reason=f"EXPLICIT_REAL_FORMAT_{archive_info.real_format}",
                explicit=True,
            )
        )
        return [archive_info]

    def _analyze(self, path: Path) -> ArchiveInfo:
        """Reuse analysis only while the same path still identifies the same file."""
        before = path.stat()
        fingerprint = Scanner._stat_fingerprint(before)
        cached = self._analysis_cache.get(path)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]

        archive_info = self.analyzer.analyze(path)
        after_fingerprint = Scanner._stat_fingerprint(path.stat())
        if after_fingerprint == fingerprint:
            self._analysis_cache[path] = (fingerprint, archive_info)
        else:
            self._analysis_cache.pop(path, None)
        return archive_info

    @classmethod
    def _is_confirmed_archive(cls, archive_info: ArchiveInfo) -> bool:
        """Accept supported formats only at the analyzer's full confidence."""
        header_archive = (
            archive_info.real_format in cls.SUPPORTED_FORMATS
            and archive_info.confidence >= cls.MIN_CONFIDENCE
        )
        embedded_archive = (
            archive_info.is_embedded_archive
            and archive_info.embedded_offset is not None
            and archive_info.embedded_offset > 0
            and archive_info.embedded_container_format in cls.SUPPORTED_FORMATS
        )
        return header_archive or embedded_archive
