"""用户可读任务报告的数据模型。"""

from dataclasses import dataclass, field
from pathlib import Path

from cleanup.models import ResidualInternalDirectory
from organizer.models import FinalContentCandidate, OrganizedOutputRoot
from organizer.duplicate_content import DuplicateContentRecord
from organizer.delivery_units import DeliveryUnit
from scanner.initial_scan_boundary import (
    InitialArchiveCandidate,
    InitialScanBoundaryResult,
)
from tools.models import ToolName
from task.input_relationship import InputArchiveRelationship
from rules.container_policy import ContainerRoleDecision
from version import APP_VERSION, BUILD_TYPE


@dataclass
class FailureDetail:
    """One user-readable failure collected from an existing execution result."""

    file_path: Path
    stage: str
    tool: ToolName | None
    error_type: str
    reason: str
    missing_files: list[Path] = field(default_factory=list)
    depth: int = 0
    parent_archive: Path | None = None
    extraction_status: str = ""
    normalized_reason: str = ""
    password_attempt_count: int = 0
    manual_password_attempt_count: int = 0
    manual_password_used: bool = False
    password_recovery_result: str = ""
    fallback_tools_attempted: list[ToolName] = field(default_factory=list)
    final_tool: ToolName | None = None
    composite_stage: str = ""
    stage_details: list[dict[str, str]] = field(default_factory=list)


@dataclass
class TaskReport:
    """保存任务或递归 Pipeline 的汇总信息。"""

    task_path: Path | None
    total_archives: int
    success_count: int
    failed_count: int
    skipped_count: int
    password_attempt_count: int
    execution_time: float | None
    manual_password_attempt_count: int = 0
    manual_password_used: bool = False
    password_recovery_result: str = ""
    app_version: str = APP_VERSION
    build_type: str = BUILD_TYPE
    output_paths: list[Path] = field(default_factory=list)
    output_roots: list[OrganizedOutputRoot] = field(default_factory=list)
    final_content_candidates: list[FinalContentCandidate] = field(
        default_factory=list
    )
    delivery_units: list[DeliveryUnit] = field(default_factory=list)
    task_status: str = ""
    delivery_status: str = ""
    initial_scan_visited_directory_count: int = 0
    initial_scan_boundaries: list[InitialScanBoundaryResult] = field(
        default_factory=list
    )
    initial_archive_candidates: list[InitialArchiveCandidate] = field(
        default_factory=list
    )
    input_relationships: list[InputArchiveRelationship] = field(
        default_factory=list
    )
    suppressed_redundant_inputs: list[Path] = field(default_factory=list)
    duplicate_contents: list[DuplicateContentRecord] = field(default_factory=list)
    failure_details: list[FailureDetail] = field(default_factory=list)
    residual_internal_directories: list[ResidualInternalDirectory] = field(
        default_factory=list
    )
    container_role_decisions: list[ContainerRoleDecision] = field(
        default_factory=list
    )
    summary: str = ""


@dataclass
class BatchTaskReport:
    """汇总多个独立任务报告，不改变各任务自身的统计结果。"""

    task_reports: list[TaskReport] = field(default_factory=list)
    app_version: str = APP_VERSION
    build_type: str = BUILD_TYPE
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    output_paths: list[Path] = field(default_factory=list)
