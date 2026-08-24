"""Safe, UI-neutral protocol for explicit manual password recovery."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from extractor.extractor_models import ExtractionStatus


class ManualPasswordAction(str, Enum):
    INPUT_PASSWORD = "INPUT_PASSWORD"
    SKIP_ARCHIVE = "SKIP_ARCHIVE"
    CANCEL_TASK = "CANCEL_TASK"


@dataclass(frozen=True)
class ManualPasswordRequest:
    """Non-sensitive context presented to an interactive adapter."""

    archive_path: Path
    archive_format: str
    status: ExtractionStatus
    automatic_attempt_count: int
    manual_attempt_count: int
    composite_stage: str = ""


@dataclass(frozen=True)
class ManualPasswordResponse:
    """One explicit user decision; password is intentionally hidden in repr."""

    action: ManualPasswordAction
    password: str | None = None  # repr is customized below

    def __repr__(self) -> str:
        return f"ManualPasswordResponse(action={self.action!r}, password=<redacted>)"


ManualPasswordCallback = Callable[
    [ManualPasswordRequest], ManualPasswordResponse
]
