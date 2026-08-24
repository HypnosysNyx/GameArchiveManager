"""任务历史记录的数据模型。"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cleanup.models import ResidualInternalDirectory
from organizer.models import FinalContentCandidate
from organizer.duplicate_content import DuplicateContentRecord
from organizer.delivery_units import DeliveryUnit
from report.models import FailureDetail
from scanner.initial_scan_boundary import (
    InitialArchiveCandidate,
    InitialScanBoundaryResult,
)
from task.models import TaskStatus
from task.input_relationship import InputArchiveRelationship
from rules.container_policy import ContainerRoleDecision
from version import APP_VERSION, BUILD_TYPE


@dataclass
class TaskHistoryRecord:
    """保存一次任务执行的安全摘要。"""

    task_id: str
    task_path: Path
    status: TaskStatus
    created_time: datetime
    completed_time: datetime
    success: bool
    summary: str
    app_version: str = APP_VERSION
    build_type: str = BUILD_TYPE
    output_paths: list[Path] = field(default_factory=list)
    final_content_candidates: list[FinalContentCandidate] = field(
        default_factory=list
    )
    delivery_units: list[DeliveryUnit] = field(default_factory=list)
    failure_details: list[FailureDetail] = field(default_factory=list)
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
    residual_internal_directories: list[ResidualInternalDirectory] = field(
        default_factory=list
    )
    manual_password_attempt_count: int = 0
    manual_password_used: bool = False
    password_recovery_result: str = ""
    container_role_decisions: list[ContainerRoleDecision] = field(
        default_factory=list
    )
