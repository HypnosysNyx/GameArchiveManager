"""Shared, read-only classification of possible game content roots."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class GameContentConfidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class GameContentEvidence:
    confidence: GameContentConfidence
    score: int
    meaningful: bool
    reasons: list[str] = field(default_factory=list)
    file_count: int = 0
    total_size: int = 0


class GameContentClassifier:
    """Score game structures without treating one EXE as sufficient proof."""

    HIGH_SCORE = 60
    MEDIUM_SCORE = 20
    AUXILIARY_NAMES = {
        "extra_info",
        "json",
        "log",
        "renpy_version",
        "screenshot.png",
        "signatures",
    }

    def classify(
        self,
        root: str | Path,
        excluded_paths: set[Path] | None = None,
        include_recursive_metrics: bool = True,
    ) -> GameContentEvidence:
        path = Path(root).expanduser().resolve()
        excluded = {
            Path(item).expanduser().resolve()
            for item in (excluded_paths or set())
        }
        if not path.exists():
            return GameContentEvidence(
                GameContentConfidence.LOW, 0, False, ["PATH_NOT_FOUND"]
            )
        if path.is_file():
            return GameContentEvidence(
                GameContentConfidence.LOW,
                5,
                True,
                ["SINGLE_FILE"],
                file_count=1,
                total_size=path.stat().st_size,
            )

        immediate = [
            child for child in path.iterdir() if child.resolve() not in excluded
        ]
        immediate_names = {child.name.casefold() for child in immediate}
        immediate_files = [child for child in immediate if child.is_file()]
        immediate_dirs = [child for child in immediate if child.is_dir()]
        root_executables = [
            child for child in immediate_files if child.suffix.casefold() == ".exe"
        ]
        file_count = 0
        total_size = 0
        any_executable = bool(root_executables)
        stack = [path] if include_recursive_metrics else []
        while stack and file_count < 100_000:
            current = stack.pop()
            try:
                children = list(current.iterdir())
            except OSError:
                continue
            for child in children:
                resolved = child.resolve()
                if resolved in excluded:
                    continue
                if child.is_dir():
                    stack.append(child)
                elif child.is_file():
                    file_count += 1
                    try:
                        total_size += child.stat().st_size
                    except OSError:
                        pass
                    if child.suffix.casefold() == ".exe":
                        any_executable = True

        score = 0
        reasons: list[str] = []
        if root_executables:
            score += 45
            reasons.append("ROOT_EXECUTABLE")
        elif any_executable:
            score += 15
            reasons.append("DESCENDANT_EXECUTABLE")
        if {"game", "lib", "renpy"}.issubset(immediate_names):
            score += 75
            reasons.append("RENPY_GAME_ROOT")
        if root_executables and any(
            name.endswith("_data") for name in immediate_names
        ):
            score += 60
            reasons.append("UNITY_GAME_ROOT")
        if root_executables and any(
            name in immediate_names
            for name in {"engine", "binaries", "content"}
        ):
            score += 45
            reasons.append("UNREAL_GAME_ROOT")
        if file_count >= 1_000:
            score += 25
            reasons.append("LARGE_FILE_SET")
        elif file_count >= 100:
            score += 15
            reasons.append("SUBSTANTIAL_FILE_SET")
        if total_size >= 100 * 1024 * 1024:
            score += 20
            reasons.append("SUBSTANTIAL_CONTENT_SIZE")

        file_names = {child.name.casefold() for child in immediate_files}
        if (
            not any_executable
            and file_count <= 20
            and file_names
            and file_names.issubset(self.AUXILIARY_NAMES)
        ):
            score -= 80
            reasons.append("AUXILIARY_METADATA_ONLY")

        meaningful = file_count > 0 or bool(immediate_dirs)
        if score >= self.HIGH_SCORE:
            confidence = GameContentConfidence.HIGH
        elif score >= self.MEDIUM_SCORE:
            confidence = GameContentConfidence.MEDIUM
        else:
            confidence = GameContentConfidence.LOW
        return GameContentEvidence(
            confidence=confidence,
            score=score,
            meaningful=meaningful,
            reasons=reasons or ["NO_GAME_STRUCTURE_SIGNAL"],
            file_count=file_count,
            total_size=total_size,
        )
