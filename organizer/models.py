"""Data recorded while turning physical extraction output into user output."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ExtractionOutputSource:
    """One output directory explicitly produced by the current task run."""

    physical_output_path: Path
    archive_path: Path | None = None
    depth: int = 0
    parent_archive: Path | None = None
    status: str = "COMPLETED"
    runtime_owned: bool = False
    is_intermediate_output: bool = True


@dataclass
class FinalContentCandidate:
    """One successful archive output evaluated as possible user content."""

    physical_root: Path
    logical_root: Path
    content_root: Path
    source_archive: Path | None
    depth: int
    parent_archive: Path | None
    status: str
    is_archive_leaf: bool
    has_meaningful_parent_content: bool
    game_confidence: int
    selection_reason: str = ""
    selection_status: str = "CANDIDATE"
    is_final_content: bool = False
    suppressed_descendants: list[Path] = field(default_factory=list)
    excluded_owned_outputs: list[Path] = field(default_factory=list)
    final_output_path: Path | None = None
    duplicate_of: Path | None = None


@dataclass(frozen=True)
class OrganizedOutputRoot:
    """Trace the physical, logical, and final roots of one user output."""

    archive_path: Path | None
    physical_pipeline_output_path: Path
    logical_output_root: Path
    final_content_root: Path
    final_output_path: Path
    selection_reason: str = ""
