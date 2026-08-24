"""Load and validate GameArchiveManager's machine-readable project state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_PATH = DEFAULT_PROJECT_ROOT / "project_state.json"


class ProjectStateError(ValueError):
    """Raised when project_state.json is missing or structurally invalid."""


def _require_mapping(container: dict[str, Any], key: str) -> dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        raise ProjectStateError(f"Required object is missing or invalid: {key}")
    return value


def _require_fields(container: dict[str, Any], path: str, fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if field not in container]
    if missing:
        raise ProjectStateError(
            f"Missing required fields in {path}: {', '.join(missing)}"
        )


def validate_project_state(state: dict[str, Any]) -> None:
    """Validate the small governance schema without third-party libraries."""
    if not isinstance(state, dict):
        raise ProjectStateError("Project state root must be a JSON object")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ProjectStateError(
            f"Unsupported schema_version: {state.get('schema_version')!r}; "
            f"expected {SCHEMA_VERSION}"
        )
    _require_fields(state, "root", ("last_verified", "frozen_areas", "real_samples"))

    project = _require_mapping(state, "project")
    _require_fields(project, "project", ("name", "version", "build_type", "phase"))

    baseline = _require_mapping(state, "test_baseline")
    _require_fields(
        baseline,
        "test_baseline",
        (
            "command",
            "minimum_test_count",
            "last_verified_count",
            "last_verified_status",
        ),
    )
    for key in ("minimum_test_count", "last_verified_count"):
        value = baseline[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ProjectStateError(f"test_baseline.{key} must be a non-negative integer")
    if baseline["last_verified_count"] < baseline["minimum_test_count"]:
        raise ProjectStateError(
            "last_verified_count cannot be lower than minimum_test_count"
        )

    priorities = _require_mapping(state, "current_priorities")
    _require_fields(priorities, "current_priorities", ("p0", "p1"))
    if not isinstance(priorities["p0"], list) or not isinstance(priorities["p1"], list):
        raise ProjectStateError("current_priorities.p0 and p1 must be arrays")

    gates = _require_mapping(state, "release_gates")
    _require_fields(
        gates,
        "release_gates",
        (
            "full_test_suite",
            "real_sample_regression",
            "clean_windows_11_vm",
            "clean_windows_10_vm",
            "source_file_integrity",
            "password_leak_check",
            "documentation_current",
        ),
    )
    if not all(isinstance(value, bool) for value in gates.values()):
        raise ProjectStateError("Every release_gates value must be boolean")


def load_project_state(path: str | Path | None = None) -> dict[str, Any]:
    """Read and validate project state without modifying the source file."""
    state_path = Path(path) if path is not None else DEFAULT_STATE_PATH
    try:
        text = state_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ProjectStateError(f"Cannot read project state: {state_path}: {error}") from error
    try:
        state = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProjectStateError(f"Invalid JSON in {state_path}: {error}") from error
    validate_project_state(state)
    return state
