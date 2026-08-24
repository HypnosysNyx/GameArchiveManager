"""Central safety limits for recursive pipeline queue growth."""

from pathlib import Path

from pipeline.models import PipelineGuardError, PipelineGuardErrorType


class PipelineGuard:
    """Validate queue growth and return structured errors on limit breaches."""

    def __init__(
        self,
        max_depth: int,
        max_new_tasks: int,
        max_embedded_candidates: int,
    ) -> None:
        if max_depth < 0:
            raise ValueError("max_depth must not be negative")
        if max_new_tasks <= 0:
            raise ValueError("max_new_tasks must be greater than zero")
        if max_embedded_candidates < 0:
            raise ValueError("max_embedded_candidates must not be negative")
        self.max_depth = max_depth
        self.max_new_tasks = max_new_tasks
        self.max_embedded_candidates = max_embedded_candidates
        self.new_task_count = 0
        self.embedded_candidate_count = 0

    def check(
        self,
        archive_path: Path,
        depth: int,
        *,
        is_initial: bool,
        is_embedded_archive: bool,
    ) -> PipelineGuardError | None:
        """Return an error without changing counters, or reserve one task slot."""
        if depth > self.max_depth:
            return PipelineGuardError(
                PipelineGuardErrorType.MAX_RECURSIVE_DEPTH,
                archive_path,
                self.max_depth,
                depth,
                "超过最大递归深度",
            )
        if not is_initial and self.new_task_count >= self.max_new_tasks:
            return PipelineGuardError(
                PipelineGuardErrorType.MAX_NEW_TASKS,
                archive_path,
                self.max_new_tasks,
                self.new_task_count + 1,
                "超过最大新增任务数量",
            )
        if (
            is_embedded_archive
            and self.embedded_candidate_count >= self.max_embedded_candidates
        ):
            return PipelineGuardError(
                PipelineGuardErrorType.MAX_EMBEDDED_CANDIDATES,
                archive_path,
                self.max_embedded_candidates,
                self.embedded_candidate_count + 1,
                "超过最大嵌入候选数量",
            )

        if not is_initial:
            self.new_task_count += 1
        if is_embedded_archive:
            self.embedded_candidate_count += 1
        return None
