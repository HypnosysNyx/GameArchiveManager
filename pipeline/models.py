"""Extraction Pipeline 使用的数据模型。"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from coordinator.models import CoordinatorResult
from rules.container_policy import ContainerRoleDecision


class PipelinePhase(str, Enum):
    """Current user-visible stage of recursive archive processing."""

    EXTRACTING = "EXTRACTING"
    SCANNING = "SCANNING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True)
class PipelineProgress:
    """A read-only queue snapshot emitted without changing execution flow."""

    archive_count: int
    completed_count: int
    failed_count: int
    phase: PipelinePhase = PipelinePhase.COMPLETED
    current_archive: Path | None = None


class PipelineGuardErrorType(str, Enum):
    """Structured reasons why a candidate was refused by the queue guard."""

    MAX_RECURSIVE_DEPTH = "MAX_RECURSIVE_DEPTH"
    MAX_NEW_TASKS = "MAX_NEW_TASKS"
    MAX_EMBEDDED_CANDIDATES = "MAX_EMBEDDED_CANDIDATES"


@dataclass(frozen=True)
class PipelineGuardError:
    """One guard limit violation that callers can report without parsing text."""

    error_type: PipelineGuardErrorType
    archive_path: Path
    limit: int
    actual: int
    message: str


class ArchiveTaskStatus(str, Enum):
    """压缩包队列任务的状态。"""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    EXTRACTING = "EXTRACTING"
    SCANNING = "SCANNING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ArchiveTaskItem:
    """表示队列中的一个压缩包任务。"""

    archive_path: Path
    depth: int
    parent_archive: Path | None
    status: ArchiveTaskStatus = ArchiveTaskStatus.PENDING


@dataclass
class ArchiveExecutionRecord:
    """保存递归树中一个压缩包的详细执行结果。"""

    archive_path: Path
    depth: int
    parent_archive: Path | None
    status: ArchiveTaskStatus
    coordinator_result: CoordinatorResult | None
    output_path: Path | None


@dataclass
class SkippedArchiveRecord:
    """保存一个因平台规则未加入递归队列的压缩包。"""

    archive_path: Path
    depth: int
    parent_archive: Path | None
    reason: str


@dataclass
class PipelineResult:
    """保存当前 Pipeline 的汇总结果。"""

    success: bool
    processed_archives: list[ArchiveTaskItem] = field(default_factory=list)
    failed_archives: list[ArchiveTaskItem] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    max_depth_reached: bool = False
    execution_records: list[ArchiveExecutionRecord] = field(default_factory=list)
    skipped_archives: list[SkippedArchiveRecord] = field(default_factory=list)
    guard_errors: list[PipelineGuardError] = field(default_factory=list)
    cancelled: bool = False
    container_role_decisions: list[ContainerRoleDecision] = field(
        default_factory=list
    )
