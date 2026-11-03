"""把现有分析模块组织成只读的任务分析流程。"""

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
import stat

from analyzer.archive_analyzer import ArchiveAnalyzer
from analyzer.models import ArchiveInfo
from config.settings import Settings
from history.storage import HistoryStorage
from password.manager import PasswordManager
from password.models import PasswordCandidate, PlatformHint
from scanner.scanner import Scanner
from scanner.archive_finder import ArchiveFinder, ArchiveScanMode
from scanner.initial_scan_boundary import (
    InitialArchiveCandidate,
    InitialScanBoundaryResult,
    InitialScanSpaceResolver,
)
from rules.container_policy import ContainerRoleDecision
from task.models import Task
from task.input_relationship import InputArchiveRelationship


class AnalysisStatus(str, Enum):
    """任务分析流程的状态。"""

    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class InitialArchiveGuardError:
    """A task-level refusal before any independent Pipeline is created."""

    error_type: str
    actual: int
    limit: int
    message: str


@dataclass
class TaskAnalysisResult:
    """保存一次任务分析得到的信息。"""

    task_id: str
    task_path: Path
    file_count: int = 0
    folder_count: int = 0
    archive_results: list[ArchiveInfo] = field(default_factory=list)
    password_candidates: list[PasswordCandidate] = field(default_factory=list)
    ignored_items: list[Path] = field(default_factory=list)
    analysis_status: AnalysisStatus = AnalysisStatus.ANALYZING
    error_message: str = ""
    initial_scan_visited_directory_count: int = 0
    initial_scan_boundaries: list[InitialScanBoundaryResult] = field(
        default_factory=list
    )
    initial_archive_candidates: list[InitialArchiveCandidate] = field(
        default_factory=list
    )
    initial_archive_guard: InitialArchiveGuardError | None = None
    input_relationships: list[InputArchiveRelationship] = field(
        default_factory=list
    )
    suppressed_redundant_inputs: list[Path] = field(default_factory=list)
    container_role_decisions: list[ContainerRoleDecision] = field(
        default_factory=list
    )


class TaskAnalyzer:
    """协调扫描和分析模块，但不执行解压或文件操作。"""

    def __init__(
        self,
        history_storage: HistoryStorage | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.scanner = Scanner(self.settings)
        self.archive_analyzer = ArchiveAnalyzer()
        self.archive_finder = ArchiveFinder(self.archive_analyzer)
        self.history_storage = history_storage or HistoryStorage()

    def analyze(self, task: Task) -> TaskAnalysisResult:
        """分析一个任务目录并返回结构化结果。"""
        result = TaskAnalysisResult(
            task_id=task.task_id,
            task_path=task.task_path,
        )

        try:
            explicit_archive = task.explicit_archive_path
            if explicit_archive is None and task.task_path.is_file():
                explicit_archive = task.task_path
            if explicit_archive is not None:
                result.file_count = 1
                result.archive_results = self.archive_finder.find(
                    explicit_archive,
                    scan_mode=ArchiveScanMode.INITIAL_SCAN,
                )
                self._copy_initial_scan_diagnostics(result)
                result.password_candidates = self._explicit_sibling_passwords(
                    explicit_archive
                )
                result.analysis_status = AnalysisStatus.COMPLETED
                return result

            historical_roots = self._historical_technical_roots(task.task_path)
            scan_space = InitialScanSpaceResolver(
                task.task_path,
                historical_technical_roots=historical_roots,
            )
            # Resolve archive candidates and all INITIAL_SCAN boundaries first
            # so metadata/password discovery observes the same user space.
            result.archive_results = self.archive_finder.find(
                task.task_path,
                scan_mode=ArchiveScanMode.INITIAL_SCAN,
                initial_space_resolver=scan_space,
            )
            self._copy_initial_scan_diagnostics(result)
            pruned_directories = {
                boundary.path
                for boundary in result.initial_scan_boundaries
                if not boundary.should_descend
            }
            scan_result = self.scanner.scan(
                task.task_path,
                pruned_directories=pruned_directories,
            )
            result.file_count = len(scan_result.files)
            result.folder_count = len(scan_result.folders)
            result.ignored_items = scan_result.ignored.copy()

            # Scanner 只发现空文件夹；Password Manager 负责候选优先级。
            password_manager = PasswordManager()
            ignored_paths = set(scan_result.ignored)
            for folder_path in scan_result.password_candidates:
                platform_hint = (
                    PlatformHint.ANDROID
                    if folder_path in ignored_paths
                    else PlatformHint.UNKNOWN
                )
                password_manager.add_folder_name_candidate(
                    folder_path,
                    platform_hint=platform_hint,
                )
            result.password_candidates = password_manager.get_candidates_by_priority()

            result.analysis_status = AnalysisStatus.COMPLETED
        except OSError as error:
            # 返回已收集的信息，交给上层决定是否重试或人工接管。
            result.analysis_status = AnalysisStatus.FAILED
            result.error_message = str(error)

        return result

    def _explicit_sibling_passwords(
        self, archive_path: Path
    ) -> list[PasswordCandidate]:
        """Collect only immediate empty real directories beside the selection."""
        parent = Path(archive_path).expanduser().absolute().parent
        password_manager = PasswordManager()
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        try:
            parent_stat = parent.lstat()
            if (not stat.S_ISDIR(parent_stat.st_mode)
                    or getattr(parent_stat, "st_file_attributes", 0) & reparse_flag):
                return []
            with os.scandir(parent) as entries:
                siblings = sorted(
                    (Path(entry.path) for entry in entries),
                    key=lambda path: (path.name.casefold(), path.name),
                )
        except OSError:
            return []

        for sibling in siblings:
            try:
                metadata = sibling.lstat()
                if (not stat.S_ISDIR(metadata.st_mode)
                        or getattr(metadata, "st_file_attributes", 0) & reparse_flag):
                    continue
                # Read at most one entry; never recurse or open file contents.
                with os.scandir(sibling) as entries:
                    if next(entries, None) is not None:
                        continue
                password_manager.add_folder_name_candidate(
                    sibling,
                    platform_hint=(
                        PlatformHint.ANDROID
                        if self.scanner._is_ignored(sibling.name)
                        else PlatformHint.UNKNOWN
                    ),
                )
            except OSError:
                # Unreadable/disappearing siblings are not proven empty.
                continue
        return password_manager.get_candidates_by_priority()

    def _historical_technical_roots(self, task_path: Path) -> set[Path]:
        """Load only persisted run-owned residual paths for this task root."""
        root = Path(task_path).expanduser().resolve()
        technical_roots: set[Path] = set()
        try:
            records = self.history_storage.read_all()
        except (OSError, ValueError):
            # Invalid/unavailable history must not make analysis destructive.
            return technical_roots
        for record in records:
            if Path(record.task_path).expanduser().resolve() != root:
                continue
            for residual in record.residual_internal_directories:
                path = Path(residual.path).expanduser().resolve()
                if path != root and root in path.parents:
                    technical_roots.add(path)
        return technical_roots

    def _copy_initial_scan_diagnostics(
        self, result: TaskAnalysisResult
    ) -> None:
        diagnostics = self.archive_finder.last_scan_diagnostics
        result.initial_scan_visited_directory_count = (
            diagnostics.visited_directory_count
        )
        result.initial_scan_boundaries = diagnostics.boundaries.copy()
        result.initial_archive_candidates = (
            diagnostics.archive_candidates.copy()
        )
        result.container_role_decisions = (
            self.archive_finder.last_container_role_decisions.copy()
        )
