"""Content-aware boundaries used only by initial task discovery."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from organizer.game_content_classifier import (
    GameContentClassifier,
    GameContentConfidence,
)


class InitialScanClassification(str, Enum):
    NORMAL_DIRECTORY = "NORMAL_DIRECTORY"
    GAME_CONTENT_BOUNDARY = "GAME_CONTENT_BOUNDARY"
    AMBIGUOUS_CONTENT = "AMBIGUOUS_CONTENT"
    TECHNICAL_OUTPUT_BOUNDARY = "TECHNICAL_OUTPUT_BOUNDARY"


@dataclass
class InitialScanBoundaryResult:
    path: Path
    classification: InitialScanClassification
    confidence: GameContentConfidence
    reasons: list[str] = field(default_factory=list)
    should_descend: bool = True
    descended: bool = True


@dataclass(frozen=True)
class InitialArchiveCandidate:
    path: Path
    reason: str
    explicit: bool = False


@dataclass
class InitialScanDiagnostics:
    visited_directory_count: int = 0
    boundaries: list[InitialScanBoundaryResult] = field(default_factory=list)
    archive_candidates: list[InitialArchiveCandidate] = field(default_factory=list)


class InitialScanSpaceResolver:
    """Identify non-user INITIAL_SCAN space from strong path context."""

    FINAL_OUTPUT_DIRECTORY_NAME = "GameArchive_Output"

    def __init__(
        self,
        task_root: str | Path,
        historical_technical_roots: set[Path] | None = None,
    ) -> None:
        self.task_root = Path(task_root).expanduser().resolve()
        self.final_output_root = (
            self.task_root / self.FINAL_OUTPUT_DIRECTORY_NAME
        ).resolve()
        self.historical_technical_roots = {
            Path(path).expanduser().resolve()
            for path in (historical_technical_roots or set())
            if self._is_inside_task(Path(path).expanduser().resolve())
        }

    def resolve(self, directory: str | Path) -> InitialScanBoundaryResult | None:
        """Return a diagnostic only when a strong technical boundary exists."""
        path = Path(directory).expanduser().resolve()
        if path == self.task_root:
            # The user explicitly selected this directory as the task root.
            return None
        if path == self.final_output_root or self.final_output_root in path.parents:
            return self._boundary(path, "FINAL_OUTPUT_ROOT")
        for technical_root in self.historical_technical_roots:
            if path == technical_root or technical_root in path.parents:
                return self._boundary(
                    path, "HISTORICAL_RUNTIME_OWNED_OUTPUT"
                )
        return None

    def _is_inside_task(self, path: Path) -> bool:
        return path != self.task_root and self.task_root in path.parents

    @staticmethod
    def _boundary(path: Path, reason: str) -> InitialScanBoundaryResult:
        return InitialScanBoundaryResult(
            path=path,
            classification=(
                InitialScanClassification.TECHNICAL_OUTPUT_BOUNDARY
            ),
            confidence=GameContentConfidence.HIGH,
            reasons=[reason],
            should_descend=False,
            descended=False,
        )


class InitialScanBoundaryResolver:
    """Classify directories without changing archive format recognition."""

    def __init__(
        self, classifier: GameContentClassifier | None = None
    ) -> None:
        self.classifier = classifier or GameContentClassifier()

    def resolve(self, directory: str | Path) -> InitialScanBoundaryResult:
        path = Path(directory).expanduser().resolve()
        evidence = self.classifier.classify(
            path, include_recursive_metrics=False
        )
        if evidence.confidence is GameContentConfidence.HIGH:
            classification = InitialScanClassification.GAME_CONTENT_BOUNDARY
            should_descend = False
        elif evidence.confidence is GameContentConfidence.MEDIUM:
            classification = InitialScanClassification.AMBIGUOUS_CONTENT
            should_descend = True
        else:
            classification = InitialScanClassification.NORMAL_DIRECTORY
            should_descend = True
        return InitialScanBoundaryResult(
            path=path,
            classification=classification,
            confidence=evidence.confidence,
            reasons=evidence.reasons.copy(),
            should_descend=should_descend,
            descended=should_descend,
        )
