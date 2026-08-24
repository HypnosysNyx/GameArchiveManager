"""使用 JSON 文件保存和读取任务历史。"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from history.models import TaskHistoryRecord
from cleanup.models import ResidualInternalDirectory
from application.runtime_paths import default_history_file
from organizer.models import FinalContentCandidate
from organizer.delivery_units import DeliveryClassification, DeliveryUnit
from organizer.duplicate_content import (
    DuplicateContentRecord,
    DuplicateContentStatus,
)
from organizer.game_content_classifier import GameContentConfidence
from scanner.initial_scan_boundary import (
    InitialArchiveCandidate,
    InitialScanBoundaryResult,
    InitialScanClassification,
)
from task.models import TaskStatus
from task.input_relationship import (
    InputArchiveRelationship,
    InputRelationshipType,
    RelationshipConfidence,
    RelationshipVerificationStatus,
)
from report.models import FailureDetail
from tools.models import ToolName
from rules.container_policy import ContainerRole, ContainerRoleDecision


class HistoryStorage:
    """保存不含密码和完整错误日志的任务历史摘要。"""

    DEFAULT_FILE = default_history_file()
    MAX_SUMMARY_LENGTH = 500

    def __init__(self, history_file: str | Path | None = None) -> None:
        self.history_file = Path(history_file or self.DEFAULT_FILE).expanduser()
        self._last_read_encoding = "utf-8"

    def save(self, record: TaskHistoryRecord) -> None:
        """新增或按 task_id 更新一条历史记录。"""
        records = self.read_all()
        safe_record = TaskHistoryRecord(
            task_id=record.task_id,
            task_path=record.task_path,
            status=record.status,
            created_time=record.created_time,
            completed_time=record.completed_time,
            success=record.success,
            summary=self._sanitize_summary(record.summary),
            app_version=record.app_version,
            build_type=record.build_type,
            output_paths=[Path(path) for path in record.output_paths],
            final_content_candidates=record.final_content_candidates.copy(),
            delivery_units=record.delivery_units.copy(),
            failure_details=record.failure_details.copy(),
            delivery_status=record.delivery_status,
            initial_scan_visited_directory_count=(
                record.initial_scan_visited_directory_count
            ),
            initial_scan_boundaries=record.initial_scan_boundaries.copy(),
            initial_archive_candidates=(
                record.initial_archive_candidates.copy()
            ),
            input_relationships=record.input_relationships.copy(),
            suppressed_redundant_inputs=(
                record.suppressed_redundant_inputs.copy()
            ),
            duplicate_contents=record.duplicate_contents.copy(),
            residual_internal_directories=(
                record.residual_internal_directories.copy()
            ),
            container_role_decisions=record.container_role_decisions.copy(),
        )

        for index, existing in enumerate(records):
            if existing.task_id == safe_record.task_id:
                records[index] = safe_record
                break
        else:
            records.append(safe_record)

        self._write_all(records)

    def read_all(self) -> list[TaskHistoryRecord]:
        """读取全部历史；文件尚不存在时返回空列表。"""
        if not self.history_file.exists():
            return []

        try:
            raw_data = self.history_file.read_bytes()
            data = self._decode_json(raw_data)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"无法读取任务历史: {error}") from error

        if not isinstance(data, list):
            raise ValueError("任务历史 JSON 顶层必须是列表")
        return [self._record_from_dict(item) for item in data]

    def get_by_task_id(self, task_id: str) -> TaskHistoryRecord | None:
        """根据唯一任务编号查询记录。"""
        for record in self.read_all():
            if record.task_id == task_id:
                return record
        return None

    def _write_all(self, records: list[TaskHistoryRecord]) -> None:
        """先写临时文件，再替换正式 JSON 文件。"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = self.history_file.with_suffix(
            self.history_file.suffix + ".tmp"
        )
        if (
            self.history_file.exists()
            and self._last_read_encoding != "utf-8"
        ):
            backup_file = self.history_file.with_suffix(
                self.history_file.suffix + ".legacy.bak"
            )
            if not backup_file.exists():
                shutil.copy2(self.history_file, backup_file)
        payload = [self._record_to_dict(record) for record in records]
        temporary_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_file.replace(self.history_file)
        self._last_read_encoding = "utf-8"

    def _decode_json(self, raw_data: bytes):
        """Read UTF-8 first, then bounded legacy Windows Chinese encodings."""
        last_error: Exception | None = None
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                text = raw_data.decode(encoding)
                data = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                last_error = error
                continue
            self._last_read_encoding = encoding
            return data
        if last_error is not None:
            raise last_error
        raise UnicodeDecodeError("utf-8", raw_data, 0, 1, "unknown encoding")

    @classmethod
    def _sanitize_summary(cls, summary: str) -> str:
        """压缩摘要并遮盖常见的明文密码表达。"""
        safe = " ".join(str(summary).split())
        safe = re.sub(
            r"(?i)\b(password|pwd)\s*[:=]\s*\S+",
            r"\1=[REDACTED]",
            safe,
        )
        safe = re.sub(r"密码\s*[:：=]\s*\S+", "密码=[已隐藏]", safe)
        if len(safe) > cls.MAX_SUMMARY_LENGTH:
            safe = safe[: cls.MAX_SUMMARY_LENGTH] + "..."
        return safe

    @staticmethod
    def _record_to_dict(record: TaskHistoryRecord) -> dict:
        return {
            "task_id": record.task_id,
            "task_path": str(record.task_path),
            "status": record.status.value,
            "created_time": record.created_time.isoformat(),
            "completed_time": record.completed_time.isoformat(),
            "success": record.success,
            "summary": record.summary,
            "app_version": record.app_version,
            "build_type": record.build_type,
            "manual_password_attempt_count": (
                record.manual_password_attempt_count
            ),
            "manual_password_used": record.manual_password_used,
            "password_recovery_result": record.password_recovery_result,
            "output_paths": [str(path) for path in record.output_paths],
            "final_content_candidates": [
                {
                    "archive_path": (
                        str(item.source_archive)
                        if item.source_archive is not None
                        else None
                    ),
                    "depth": item.depth,
                    "status": item.status,
                    "parent_archive": (
                        str(item.parent_archive)
                        if item.parent_archive is not None
                        else None
                    ),
                    "physical_output": str(item.physical_root),
                    "logical_root": str(item.logical_root),
                    "final_content_root": str(item.content_root),
                    "is_archive_leaf": item.is_archive_leaf,
                    "is_final_content": item.is_final_content,
                    "selection_reason": item.selection_reason,
                    "selection_status": item.selection_status,
                    "game_confidence": item.game_confidence,
                    "final_output_path": (
                        str(item.final_output_path)
                        if item.final_output_path is not None
                        else None
                    ),
                    "suppressed_descendants": [
                        str(path) for path in item.suppressed_descendants
                    ],
                }
                for item in record.final_content_candidates
            ],
            "delivery_status": record.delivery_status,
            "delivery_units": [
                {
                    "root_execution_node": str(item.root_execution_node) if item.root_execution_node else None,
                    "terminal_execution_node": str(item.terminal_execution_node) if item.terminal_execution_node else None,
                    "execution_node_paths": [str(path) for path in item.execution_node_paths],
                    "terminal_content_root": str(item.terminal_content_root) if item.terminal_content_root else None,
                    "classification": item.classification.value,
                    "confidence": item.confidence,
                    "selection_status": item.selection_status,
                    "selection_reason": item.selection_reason,
                }
                for item in record.delivery_units
            ],
            "failure_details": [
                {
                    "file_path": str(item.file_path),
                    "depth": item.depth,
                    "parent_archive": str(item.parent_archive) if item.parent_archive else None,
                    "stage": item.stage,
                    "tool": item.tool.value if item.tool else None,
                    "extraction_status": item.extraction_status,
                    "error_type": item.error_type,
                    "normalized_reason": HistoryStorage._sanitize_summary(item.normalized_reason or item.reason),
                    "password_attempt_count": item.password_attempt_count,
                    "manual_password_attempt_count": (
                        item.manual_password_attempt_count
                    ),
                    "manual_password_used": item.manual_password_used,
                    "password_recovery_result": item.password_recovery_result,
                    "fallback_tools_attempted": [tool.value for tool in item.fallback_tools_attempted],
                    "final_tool": item.final_tool.value if item.final_tool else None,
                    "composite_stage": item.composite_stage,
                    "stage_details": [
                        {
                            key: (
                                HistoryStorage._sanitize_summary(str(value))
                                if key == "reason"
                                else str(value)
                            )
                            for key, value in stage.items()
                        }
                        for stage in item.stage_details
                    ],
                    "missing_files": [str(path) for path in item.missing_files],
                }
                for item in record.failure_details
            ],
            "initial_scan_visited_directory_count": (
                record.initial_scan_visited_directory_count
            ),
            "initial_scan_boundaries": [
                {
                    "path": str(item.path),
                    "classification": item.classification.value,
                    "confidence": item.confidence.value,
                    "reasons": item.reasons,
                    "descended": item.descended,
                    "pruned": not item.should_descend,
                }
                for item in record.initial_scan_boundaries
            ],
            "initial_archive_candidates": [
                {
                    "path": str(item.path),
                    "reason": item.reason,
                    "explicit": item.explicit,
                }
                for item in record.initial_archive_candidates
            ],
            "input_relationships": [
                {
                    "source": str(item.source_path),
                    "related_source": (
                        str(item.related_path)
                        if item.related_path is not None
                        else None
                    ),
                    "relationship": item.relationship_type.value,
                    "confidence": item.confidence.value,
                    "verification_method": item.verification_method,
                    "verification_status": item.verification_status.value,
                    "canonical": (
                        str(item.canonical_input)
                        if item.canonical_input is not None
                        else None
                    ),
                    "suppressed": (
                        str(item.suppressed_input)
                        if item.suppressed_input is not None
                        else None
                    ),
                    "reason": item.reason,
                    "verification_bytes_read": item.verification_bytes_read,
                    "verification_time": item.verification_time,
                }
                for item in record.input_relationships
            ],
            "suppressed_redundant_inputs": [
                str(path) for path in record.suppressed_redundant_inputs
            ],
            "duplicate_contents": [
                {
                    "content_path": str(item.content_path),
                    "duplicate_of": (
                        str(item.duplicate_of)
                        if item.duplicate_of is not None
                        else None
                    ),
                    "status": item.status.value,
                    "verification_method": item.verification_method,
                    "reason": item.reason,
                    "file_count": item.file_count,
                    "total_size": item.total_size,
                    "verification_bytes_read": item.verification_bytes_read,
                    "verification_time": item.verification_time,
                }
                for item in record.duplicate_contents
            ],
            "residual_internal_directories": [
                {
                    "path": str(item.path),
                    "status": item.status,
                    "reason": item.reason,
                    "created_time": (
                        item.created_time.isoformat()
                        if item.created_time is not None
                        else None
                    ),
                }
                for item in record.residual_internal_directories
            ],
            "container_role_decisions": [
                {
                    "path": str(item.path),
                    "role": item.role.value,
                    "reason": item.reason,
                    "scan_mode": item.scan_mode,
                    "explicit": item.explicit,
                    "extension": item.extension,
                    "real_format": item.real_format,
                }
                for item in record.container_role_decisions
            ],
        }

    @staticmethod
    def _record_from_dict(data: dict) -> TaskHistoryRecord:
        try:
            if not isinstance(data["success"], bool):
                raise ValueError("success 必须是布尔值")
            return TaskHistoryRecord(
                task_id=str(data["task_id"]),
                task_path=Path(data["task_path"]),
                status=TaskStatus(data["status"]),
                created_time=datetime.fromisoformat(data["created_time"]),
                completed_time=datetime.fromisoformat(data["completed_time"]),
                success=data["success"],
                summary=str(data["summary"]),
                app_version=str(data.get("app_version", "unknown")),
                build_type=str(data.get("build_type", "Legacy")),
                manual_password_attempt_count=int(
                    data.get("manual_password_attempt_count", 0)
                ),
                manual_password_used=bool(
                    data.get("manual_password_used", False)
                ),
                password_recovery_result=str(
                    data.get("password_recovery_result", "")
                ),
                output_paths=[
                    Path(path) for path in data.get("output_paths", [])
                ],
                final_content_candidates=[
                    FinalContentCandidate(
                        physical_root=Path(item["physical_output"]),
                        logical_root=Path(item["logical_root"]),
                        content_root=Path(item["final_content_root"]),
                        source_archive=(
                            Path(item["archive_path"])
                            if item.get("archive_path")
                            else None
                        ),
                        depth=int(item.get("depth", 0)),
                        parent_archive=(
                            Path(item["parent_archive"])
                            if item.get("parent_archive")
                            else None
                        ),
                        status=str(item.get("status", "COMPLETED")),
                        is_archive_leaf=bool(item.get("is_archive_leaf", False)),
                        has_meaningful_parent_content=True,
                        game_confidence=int(item.get("game_confidence", 0)),
                        selection_reason=str(item.get("selection_reason", "")),
                        selection_status=str(item.get("selection_status", "")),
                        is_final_content=bool(item.get("is_final_content", False)),
                        suppressed_descendants=[
                            Path(path)
                            for path in item.get("suppressed_descendants", [])
                        ],
                        final_output_path=(
                            Path(item["final_output_path"])
                            if item.get("final_output_path")
                            else None
                        ),
                    )
                    for item in data.get("final_content_candidates", [])
                ],
                delivery_status=str(data.get("delivery_status", "")),
                delivery_units=[
                    DeliveryUnit(
                        root_execution_node=(Path(item["root_execution_node"]) if item.get("root_execution_node") else None),
                        terminal_execution_node=(Path(item["terminal_execution_node"]) if item.get("terminal_execution_node") else None),
                        execution_node_paths=[Path(path) for path in item.get("execution_node_paths", [])],
                        terminal_content_root=(Path(item["terminal_content_root"]) if item.get("terminal_content_root") else None),
                        classification=DeliveryClassification(item.get("classification", "TECHNICAL_ONLY")),
                        confidence=int(item.get("confidence", 0)),
                        selection_status=str(item.get("selection_status", "CANDIDATE")),
                        selection_reason=str(item.get("selection_reason", "")),
                    )
                    for item in data.get("delivery_units", [])
                ],
                failure_details=[
                    FailureDetail(
                        file_path=Path(item["file_path"]),
                        stage=str(item.get("stage", "")),
                        tool=(ToolName(item["tool"]) if item.get("tool") else None),
                        error_type=str(item.get("error_type", "")),
                        reason=str(item.get("normalized_reason", "")),
                        missing_files=[Path(path) for path in item.get("missing_files", [])],
                        depth=int(item.get("depth", 0)),
                        parent_archive=(Path(item["parent_archive"]) if item.get("parent_archive") else None),
                        extraction_status=str(item.get("extraction_status", "")),
                        normalized_reason=str(item.get("normalized_reason", "")),
                        password_attempt_count=int(item.get("password_attempt_count", 0)),
                        manual_password_attempt_count=int(
                            item.get("manual_password_attempt_count", 0)
                        ),
                        manual_password_used=bool(
                            item.get("manual_password_used", False)
                        ),
                        password_recovery_result=str(
                            item.get("password_recovery_result", "")
                        ),
                        fallback_tools_attempted=[ToolName(tool) for tool in item.get("fallback_tools_attempted", [])],
                        final_tool=(ToolName(item["final_tool"]) if item.get("final_tool") else None),
                        composite_stage=str(item.get("composite_stage", "")),
                        stage_details=list(item.get("stage_details", [])),
                    )
                    for item in data.get("failure_details", [])
                ],
                initial_scan_visited_directory_count=int(
                    data.get("initial_scan_visited_directory_count", 0)
                ),
                initial_scan_boundaries=[
                    InitialScanBoundaryResult(
                        path=Path(item["path"]),
                        classification=InitialScanClassification(
                            item["classification"]
                        ),
                        confidence=GameContentConfidence(item["confidence"]),
                        reasons=[str(reason) for reason in item.get("reasons", [])],
                        should_descend=not bool(item.get("pruned", False)),
                        descended=bool(item.get("descended", True)),
                    )
                    for item in data.get("initial_scan_boundaries", [])
                ],
                initial_archive_candidates=[
                    InitialArchiveCandidate(
                        path=Path(item["path"]),
                        reason=str(item.get("reason", "")),
                        explicit=bool(item.get("explicit", False)),
                    )
                    for item in data.get("initial_archive_candidates", [])
                ],
                input_relationships=[
                    InputArchiveRelationship(
                        source_path=Path(item["source"]),
                        related_path=(
                            Path(item["related_source"])
                            if item.get("related_source")
                            else None
                        ),
                        relationship_type=InputRelationshipType(
                            item["relationship"]
                        ),
                        confidence=RelationshipConfidence(item["confidence"]),
                        verification_method=str(
                            item.get("verification_method", "")
                        ),
                        verification_status=RelationshipVerificationStatus(
                            item.get("verification_status", "NOT_ATTEMPTED")
                        ),
                        canonical_input=(
                            Path(item["canonical"])
                            if item.get("canonical")
                            else None
                        ),
                        suppressed_input=(
                            Path(item["suppressed"])
                            if item.get("suppressed")
                            else None
                        ),
                        reason=str(item.get("reason", "")),
                        verification_bytes_read=int(
                            item.get("verification_bytes_read", 0)
                        ),
                        verification_time=float(
                            item.get("verification_time", 0.0)
                        ),
                    )
                    for item in data.get("input_relationships", [])
                ],
                suppressed_redundant_inputs=[
                    Path(path)
                    for path in data.get("suppressed_redundant_inputs", [])
                ],
                duplicate_contents=[
                    DuplicateContentRecord(
                        content_path=Path(item["content_path"]),
                        duplicate_of=(
                            Path(item["duplicate_of"])
                            if item.get("duplicate_of")
                            else None
                        ),
                        status=DuplicateContentStatus(item["status"]),
                        verification_method=str(
                            item.get("verification_method", "")
                        ),
                        reason=str(item.get("reason", "")),
                        file_count=int(item.get("file_count", 0)),
                        total_size=int(item.get("total_size", 0)),
                        verification_bytes_read=int(
                            item.get("verification_bytes_read", 0)
                        ),
                        verification_time=float(
                            item.get("verification_time", 0.0)
                        ),
                    )
                    for item in data.get("duplicate_contents", [])
                ],
                residual_internal_directories=[
                    ResidualInternalDirectory(
                        path=Path(item["path"]),
                        status=str(item.get("status", "ORPHANED_TEMP")),
                        reason=str(item.get("reason", "")),
                        created_time=(
                            datetime.fromisoformat(item["created_time"])
                            if item.get("created_time")
                            else None
                        ),
                    )
                    for item in data.get(
                        "residual_internal_directories", []
                    )
                ],
                container_role_decisions=[
                    ContainerRoleDecision(
                        path=Path(item["path"]),
                        role=ContainerRole(item["role"]),
                        reason=str(item.get("reason", "")),
                        scan_mode=str(item.get("scan_mode", "")),
                        explicit=bool(item.get("explicit", False)),
                        extension=str(item.get("extension", "")),
                        real_format=str(item.get("real_format", "")),
                    )
                    for item in data.get("container_role_decisions", [])
                ],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"任务历史记录格式无效: {error}") from error
