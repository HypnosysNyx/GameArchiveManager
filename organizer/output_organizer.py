"""Safely copy successful extraction outputs into one task output directory."""

import shutil
import re
from pathlib import Path

from execution.output_paths import OutputPathGenerator
from organizer.final_content_resolver import FinalContentRootResolver
from organizer.delivery_units import DeliveryUnit, DeliveryUnitResolver
from organizer.duplicate_content import (
    DuplicateContentDetector,
    DuplicateContentRecord,
)
from organizer.models import (
    ExtractionOutputSource,
    FinalContentCandidate,
    OrganizedOutputRoot,
)


class OutputOrganizer:
    """Create user-facing final outputs without deleting extraction results."""

    OUTPUT_DIRECTORY_NAME = "GameArchive_Output"

    def __init__(
        self,
        resolver: FinalContentRootResolver | None = None,
        duplicate_detector: DuplicateContentDetector | None = None,
        delivery_unit_resolver: DeliveryUnitResolver | None = None,
    ) -> None:
        self.resolver = resolver or FinalContentRootResolver()
        self.duplicate_detector = duplicate_detector or DuplicateContentDetector()
        self.delivery_unit_resolver = delivery_unit_resolver or DeliveryUnitResolver()
        self.last_duplicate_records: list[DuplicateContentRecord] = []
        self.last_delivery_units: list[DeliveryUnit] = []

    def organize(
        self,
        task_path: str | Path,
        output_paths: list[Path],
    ) -> list[Path]:
        """Compatibility wrapper for callers that only have physical paths."""
        sources = [
            ExtractionOutputSource(physical_output_path=Path(output_path))
            for output_path in output_paths
        ]
        return [
            item.final_output_path
            for item in self.organize_with_details(task_path, sources)
        ]

    def organize_with_details(
        self,
        task_path: str | Path,
        outputs: list[ExtractionOutputSource],
        runtime_owned_paths: list[Path] | None = None,
    ) -> list[OrganizedOutputRoot]:
        """Compatibility API returning only organized roots."""
        organized, _ = self.resolve_and_organize(
            task_path, outputs, runtime_owned_paths
        )
        return organized

    def resolve_and_organize(
        self,
        task_path: str | Path,
        outputs: list[ExtractionOutputSource],
        runtime_owned_paths: list[Path] | None = None,
        selection_callback=None,
    ) -> tuple[list[OrganizedOutputRoot], list[FinalContentCandidate]]:
        """Resolve all candidates, copy selections, and verify each copy."""
        task_root = Path(task_path).expanduser().resolve()
        final_root = task_root / self.OUTPUT_DIRECTORY_NAME
        candidates = self.resolver.resolve(outputs, runtime_owned_paths)
        candidates, self.last_delivery_units = self.delivery_unit_resolver.resolve(
            candidates
        )
        if selection_callback is not None:
            selectable = [
                item
                for item in self.last_delivery_units
                if item.selection_status == "NEEDS_USER_SELECTION"
            ]
            if selectable:
                selected_indexes = {
                    index
                    for index in selection_callback(selectable)
                    if 0 <= index < len(selectable)
                }
                for index, unit in enumerate(selectable):
                    selected = index in selected_indexes
                    unit.selection_status = (
                        "SELECTED" if selected else "SUPPRESSED"
                    )
                    unit.selection_reason = (
                        "USER_SELECTED_DELIVERY_UNIT"
                        if selected
                        else "USER_REJECTED_DELIVERY_UNIT"
                    )
                    for candidate in candidates:
                        if candidate.content_root == unit.terminal_content_root:
                            candidate.is_final_content = selected
                            candidate.selection_status = unit.selection_status
                            candidate.selection_reason = unit.selection_reason
                            break
        self.last_duplicate_records = self.duplicate_detector.detect(candidates)
        selected = [item for item in candidates if item.is_final_content]
        if not selected:
            return [], candidates

        final_root.mkdir(parents=True, exist_ok=True)
        organized: list[OrganizedOutputRoot] = []
        for candidate in selected:
            source = candidate.content_root
            if not source.exists():
                raise FileNotFoundError(
                    f"Final content root does not exist: {source}"
                )

            # An already organized result does not need to be copied again.
            if source == final_root or final_root in source.parents:
                candidate.final_output_path = source
                organized.append(
                    OrganizedOutputRoot(
                        archive_path=candidate.source_archive,
                        physical_pipeline_output_path=candidate.physical_root,
                        logical_output_root=candidate.logical_root,
                        final_content_root=candidate.content_root,
                        final_output_path=source,
                        selection_reason=candidate.selection_reason,
                    )
                )
                continue

            base_name = self._destination_name(candidate)
            destination = self._available_destination(final_root, base_name)
            self._copy_candidate(candidate, destination)
            self._verify_copy(candidate, destination)
            candidate.final_output_path = destination
            organized.append(
                OrganizedOutputRoot(
                    archive_path=candidate.source_archive,
                    physical_pipeline_output_path=candidate.physical_root,
                    logical_output_root=candidate.logical_root,
                    final_content_root=candidate.content_root,
                    final_output_path=destination,
                    selection_reason=candidate.selection_reason,
                )
            )

        return organized, candidates

    def _destination_name(self, candidate: FinalContentCandidate) -> str:
        if candidate.content_root != candidate.physical_root:
            return candidate.content_root.name or "output"

        name = self.resolver._archive_stem(candidate.source_archive) or (
            candidate.content_root.name
            if candidate.content_root.is_dir()
            else candidate.content_root.stem
        )
        name = re.sub(
            r"_password_attempt_\d+$", "", name, flags=re.IGNORECASE
        )
        name = re.sub(
            r"_(?:embedded_)?extracted$", "", name, flags=re.IGNORECASE
        )
        return name or "output"

    def _copy_candidate(
        self, candidate: FinalContentCandidate, destination: Path
    ) -> None:
        source = candidate.content_root
        excluded = {path.resolve() for path in candidate.excluded_owned_outputs}
        if source.is_dir():
            def ignore(directory: str, names: list[str]) -> list[str]:
                current = Path(directory)
                return [
                    name
                    for name in names
                    if (current / name).resolve() in excluded
                ]

            shutil.copytree(source, destination, ignore=ignore)
        else:
            destination.mkdir(parents=False, exist_ok=False)
            shutil.copy2(source, destination / source.name)

    def _verify_copy(
        self, candidate: FinalContentCandidate, destination: Path
    ) -> None:
        source_manifest = self._manifest(
            candidate.content_root,
            set(candidate.excluded_owned_outputs),
        )
        destination_manifest = self._manifest(destination, set())
        if source_manifest != destination_manifest:
            raise OSError("Final output verification failed")

    @staticmethod
    def _manifest(root: Path, excluded: set[Path]) -> dict[str, int]:
        excluded = {path.resolve() for path in excluded}
        if root.is_file():
            return {root.name: root.stat().st_size}
        manifest: dict[str, int] = {}
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
                    manifest[str(child.relative_to(root))] = child.stat().st_size
        return manifest

    @staticmethod
    def _available_destination(final_root: Path, base_name: str) -> Path:
        """Return a non-existing directory name without overwriting old outputs."""
        return OutputPathGenerator.next_available(final_root / base_name)
