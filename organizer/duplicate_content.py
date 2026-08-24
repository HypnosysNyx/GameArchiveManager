"""Conservative post-execution duplicate-content verification."""

import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from time import perf_counter

from organizer.models import FinalContentCandidate


class DuplicateContentStatus(str, Enum):
    UNIQUE = "UNIQUE"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


@dataclass
class DuplicateContentRecord:
    content_path: Path
    duplicate_of: Path | None
    status: DuplicateContentStatus
    verification_method: str
    reason: str
    file_count: int
    total_size: int
    verification_bytes_read: int = 0
    verification_time: float = 0.0


class DuplicateContentDetector:
    """Hash only final candidates whose cheap manifests exactly match."""

    def detect(
        self, candidates: list[FinalContentCandidate]
    ) -> list[DuplicateContentRecord]:
        selected = [candidate for candidate in candidates if candidate.is_final_content]
        records: list[DuplicateContentRecord] = []
        unique_candidates: list[FinalContentCandidate] = []
        quick_cache: dict[int, dict[str, int]] = {}
        strong_cache: dict[int, tuple[dict[str, str], int]] = {}

        for candidate in selected:
            started = perf_counter()
            try:
                quick = self._quick_manifest(candidate)
            except Exception as error:
                records.append(
                    DuplicateContentRecord(
                        content_path=candidate.content_root,
                        duplicate_of=None,
                        status=DuplicateContentStatus.VERIFICATION_FAILED,
                        verification_method="QUICK_MANIFEST",
                        reason=(
                            f"Quick manifest failed ({type(error).__name__}); "
                            "kept this result"
                        ),
                        file_count=0,
                        total_size=0,
                        verification_time=perf_counter() - started,
                    )
                )
                unique_candidates.append(candidate)
                continue

            quick_cache[id(candidate)] = quick
            matching = [
                existing
                for existing in unique_candidates
                if quick_cache.get(id(existing)) == quick
            ]
            if not matching:
                unique_candidates.append(candidate)
                records.append(self._unique_record(candidate, quick, started))
                continue

            duplicate_of: FinalContentCandidate | None = None
            verification_bytes = 0
            verification_error: Exception | None = None
            for existing in matching:
                try:
                    existing_hashes, existing_bytes = self._strong_manifest_cached(
                        existing, strong_cache
                    )
                    candidate_hashes, candidate_bytes = self._strong_manifest_cached(
                        candidate, strong_cache
                    )
                    verification_bytes += existing_bytes + candidate_bytes
                except Exception as error:
                    verification_error = error
                    break
                if existing_hashes == candidate_hashes:
                    duplicate_of = existing
                    break

            if verification_error is not None:
                unique_candidates.append(candidate)
                records.append(
                    DuplicateContentRecord(
                        content_path=candidate.content_root,
                        duplicate_of=None,
                        status=DuplicateContentStatus.VERIFICATION_FAILED,
                        verification_method="RELATIVE_PATH_SIZE_THEN_SHA256",
                        reason=(
                            f"Strong verification failed "
                            f"({type(verification_error).__name__}); kept both results"
                        ),
                        file_count=len(quick),
                        total_size=sum(quick.values()),
                        verification_bytes_read=verification_bytes,
                        verification_time=perf_counter() - started,
                    )
                )
            elif duplicate_of is not None:
                candidate.is_final_content = False
                candidate.selection_status = "SUPPRESSED"
                candidate.selection_reason = "DUPLICATE_CONTENT"
                candidate.duplicate_of = duplicate_of.content_root
                records.append(
                    DuplicateContentRecord(
                        content_path=candidate.content_root,
                        duplicate_of=duplicate_of.content_root,
                        status=DuplicateContentStatus.DUPLICATE_CONTENT,
                        verification_method="RELATIVE_PATH_SIZE_THEN_SHA256",
                        reason="All relative paths, sizes, and file SHA256 values match",
                        file_count=len(quick),
                        total_size=sum(quick.values()),
                        verification_bytes_read=verification_bytes,
                        verification_time=perf_counter() - started,
                    )
                )
            else:
                unique_candidates.append(candidate)
                records.append(self._unique_record(candidate, quick, started))
        return records

    @staticmethod
    def _unique_record(
        candidate: FinalContentCandidate,
        manifest: dict[str, int],
        started: float,
    ) -> DuplicateContentRecord:
        return DuplicateContentRecord(
            content_path=candidate.content_root,
            duplicate_of=None,
            status=DuplicateContentStatus.UNIQUE,
            verification_method="QUICK_MANIFEST",
            reason="No earlier selected result has the same quick manifest",
            file_count=len(manifest),
            total_size=sum(manifest.values()),
            verification_time=perf_counter() - started,
        )

    def _strong_manifest_cached(
        self,
        candidate: FinalContentCandidate,
        cache: dict[int, tuple[dict[str, str], int]],
    ) -> tuple[dict[str, str], int]:
        key = id(candidate)
        if key in cache:
            return cache[key][0], 0
        cache[key] = self._strong_manifest(candidate)
        return cache[key]

    @staticmethod
    def _iter_files(candidate: FinalContentCandidate):
        root = candidate.content_root
        excluded = {path.resolve() for path in candidate.excluded_owned_outputs}
        if root.is_file():
            yield root.name, root
            return
        stack = [root]
        while stack:
            current = stack.pop()
            for child in current.iterdir():
                resolved = child.resolve()
                if resolved in excluded:
                    continue
                if child.is_dir():
                    stack.append(child)
                elif child.is_file():
                    yield child.relative_to(root).as_posix(), child

    def _quick_manifest(self, candidate: FinalContentCandidate) -> dict[str, int]:
        return {
            relative: path.stat().st_size
            for relative, path in self._iter_files(candidate)
        }

    def _strong_manifest(
        self, candidate: FinalContentCandidate
    ) -> tuple[dict[str, str], int]:
        manifest: dict[str, str] = {}
        bytes_read = 0
        for relative, path in self._iter_files(candidate):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    digest.update(block)
                    bytes_read += len(block)
            manifest[relative] = digest.hexdigest()
        return manifest, bytes_read
