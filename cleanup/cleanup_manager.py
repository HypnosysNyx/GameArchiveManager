"""Discover and explicitly delete cleanup candidates within safe boundaries."""

import os
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Iterable

from cleanup.models import CleanupCandidate


class CleanupManager:
    """Authorize cleanup candidates; scanning alone never deletes anything."""

    PASSWORD_ATTEMPT_MARKER = "_password_attempt_"
    FAILED_MARKERS = ("failed_extraction", "extraction_failed")

    def __init__(
        self,
        task_output_directory: str | Path,
        task_root: str | Path | None = None,
        input_archives: Iterable[str | Path] | None = None,
        protected_paths: Iterable[str | Path] | None = None,
    ) -> None:
        self.task_output_directory = Path(
            task_output_directory
        ).expanduser().resolve()
        self.task_root = (
            Path(task_root).expanduser().resolve()
            if task_root is not None
            else self.task_output_directory
        )
        self.input_archives = {
            Path(path).expanduser().resolve()
            for path in (input_archives or [])
        }
        self.protected_paths = {
            Path(path).expanduser().resolve()
            for path in (protected_paths or [])
        }
        self._allowed_candidates: set[Path] = set()

    def scan(self) -> list[CleanupCandidate]:
        """Legacy suggestion scan; it never grants automatic run cleanup."""
        root = self.task_output_directory
        if not root.exists():
            raise FileNotFoundError(f"cleanup root does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"cleanup root is not a directory: {root}")

        candidates: list[CleanupCandidate] = []
        self._allowed_candidates.clear()
        for current_path, directory_names, file_names in os.walk(
            root, topdown=False, followlinks=False
        ):
            current = Path(current_path).resolve()
            if current == root or current.is_symlink():
                continue
            reason = self._get_candidate_reason(
                current, directory_names, file_names
            )
            if (
                reason is None
                or self._contains_input_archive(current)
                or self._is_protected(current)
            ):
                continue
            candidates.append(self._candidate(current, reason))
            self._allowed_candidates.add(current)
        candidates.sort(key=lambda item: str(item.path).casefold())
        return candidates

    def authorize_owned(
        self,
        owned_paths: Iterable[str | Path],
        reason: str,
    ) -> list[CleanupCandidate]:
        """Authorize exact run-owned directories without inspecting their names."""
        self._allowed_candidates.clear()
        resolved = {
            Path(path).expanduser().resolve() for path in owned_paths
        }
        top_level = [
            path
            for path in resolved
            if not any(
                other != path and other in path.parents for other in resolved
            )
        ]
        candidates: list[CleanupCandidate] = []
        for path in sorted(top_level, key=lambda item: str(item).casefold()):
            if not self._is_safe_owned_directory(path):
                continue
            candidates.append(self._candidate(path, reason))
            self._allowed_candidates.add(path)
        return candidates

    def delete(self, path: str | Path) -> bool:
        """Delete only a path authorized by the immediately preceding scan."""
        requested = Path(path).expanduser()
        if requested.is_symlink():
            raise ValueError("symbolic-link directories cannot be deleted")
        target = requested.resolve()
        if target == self.task_root:
            raise ValueError("task root cannot be deleted")
        if target == self.task_output_directory:
            raise ValueError("cleanup root cannot be deleted")
        if self.task_output_directory not in target.parents:
            raise ValueError("cleanup path is outside the authorized root")
        if target not in self._allowed_candidates:
            raise ValueError("path was not authorized by this cleanup scan")
        if self._contains_input_archive(target):
            raise ValueError("input archives and their containing directories are protected")
        if self._is_protected(target):
            raise ValueError("final output and protected paths cannot be deleted")
        if not target.exists():
            raise FileNotFoundError(f"cleanup candidate does not exist: {target}")
        if not target.is_dir():
            raise ValueError("CleanupManager deletes directories only")
        shutil.rmtree(target, onerror=self._retry_readonly_removal)
        self._allowed_candidates.discard(target)
        return True

    @staticmethod
    def _retry_readonly_removal(function, path, error_info) -> None:
        """Retry only Windows-style read-only removal failures."""
        error = error_info[1]
        if not isinstance(error, PermissionError):
            raise error
        os.chmod(path, stat.S_IWRITE)
        function(path)

    def _is_safe_owned_directory(self, path: Path) -> bool:
        if not path.exists() or not path.is_dir() or path.is_symlink():
            return False
        if path in {self.task_root, self.task_output_directory}:
            return False
        if self.task_root not in path.parents:
            return False
        if self._contains_input_archive(path) or self._is_protected(path):
            return False
        return True

    def _is_protected(self, path: Path) -> bool:
        return any(
            protected == path
            or protected in path.parents
            or path in protected.parents
            for protected in self.protected_paths
        )

    @classmethod
    def _get_candidate_reason(
        cls,
        directory: Path,
        directory_names: list[str],
        file_names: list[str],
    ) -> str | None:
        normalized_name = directory.name.casefold()
        if cls.PASSWORD_ATTEMPT_MARKER in normalized_name:
            return "password attempt residual directory"
        if (
            any(marker in normalized_name for marker in cls.FAILED_MARKERS)
            or normalized_name.endswith("_failed")
        ):
            return "failed extraction residual directory"
        if not directory_names and not file_names:
            return "empty residual directory"
        return None

    def _contains_input_archive(self, directory: Path) -> bool:
        return any(
            archive == directory or directory in archive.parents
            for archive in self.input_archives
        )

    @staticmethod
    def _candidate(path: Path, reason: str) -> CleanupCandidate:
        return CleanupCandidate(
            path=path,
            reason=reason,
            size=CleanupManager._directory_size(path),
            created_time=datetime.fromtimestamp(path.stat().st_ctime).astimezone(),
        )

    @staticmethod
    def _directory_size(directory: Path) -> int:
        total_size = 0
        for current_path, directory_names, file_names in os.walk(
            directory, topdown=True, followlinks=False
        ):
            current = Path(current_path)
            directory_names[:] = [
                name
                for name in directory_names
                if not (current / name).is_symlink()
            ]
            for file_name in file_names:
                try:
                    total_size += (current / file_name).lstat().st_size
                except OSError:
                    continue
        return total_size
