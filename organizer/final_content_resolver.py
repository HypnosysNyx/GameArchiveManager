"""Resolve user content roots independently from recursive archive leaves."""

from pathlib import Path

from organizer.game_content_classifier import GameContentClassifier
from organizer.models import ExtractionOutputSource, FinalContentCandidate


class FinalContentRootResolver:
    """Evaluate every successful output before selecting user-facing roots."""

    HIGH_GAME_CONFIDENCE = 60

    def __init__(
        self, classifier: GameContentClassifier | None = None
    ) -> None:
        self.classifier = classifier or GameContentClassifier()

    def resolve(
        self,
        outputs: list[ExtractionOutputSource],
        runtime_owned_paths: list[Path] | None = None,
    ) -> list[FinalContentCandidate]:
        normalized_outputs = self._normalize_outputs(outputs)
        owned = {
            Path(path).expanduser().resolve()
            for path in (runtime_owned_paths or [])
        }
        candidates: list[FinalContentCandidate] = []

        for output in normalized_outputs:
            source = output.physical_output_path
            descendants = [
                other.physical_output_path
                for other in normalized_outputs
                if other.physical_output_path != source
                and source in other.physical_output_path.parents
            ]
            logical_root, content_root = self._content_roots(output, owned)
            excluded = sorted(
                {
                    path
                    for path in owned
                    if path != source and content_root in path.parents
                },
                key=lambda path: (len(path.parts), str(path).casefold()),
            )
            meaningful, confidence = self._content_evidence(
                content_root, set(excluded)
            )
            candidates.append(
                FinalContentCandidate(
                    physical_root=source,
                    logical_root=logical_root,
                    content_root=content_root,
                    source_archive=output.archive_path,
                    depth=output.depth,
                    parent_archive=output.parent_archive,
                    status=output.status,
                    is_archive_leaf=not descendants,
                    has_meaningful_parent_content=meaningful,
                    game_confidence=confidence,
                    excluded_owned_outputs=excluded,
                )
            )

        self._select(candidates)
        return candidates

    @staticmethod
    def _normalize_outputs(
        outputs: list[ExtractionOutputSource],
    ) -> list[ExtractionOutputSource]:
        normalized: list[ExtractionOutputSource] = []
        seen: set[Path] = set()
        for output in outputs:
            source = Path(output.physical_output_path).expanduser().resolve()
            if source in seen:
                continue
            seen.add(source)
            normalized.append(
                ExtractionOutputSource(
                    physical_output_path=source,
                    archive_path=(
                        Path(output.archive_path).expanduser().resolve()
                        if output.archive_path is not None
                        else None
                    ),
                    depth=output.depth,
                    parent_archive=(
                        Path(output.parent_archive).expanduser().resolve()
                        if output.parent_archive is not None
                        else None
                    ),
                    status=output.status,
                    runtime_owned=output.runtime_owned,
                    is_intermediate_output=output.is_intermediate_output,
                )
            )
        return normalized

    def _content_roots(
        self,
        output: ExtractionOutputSource,
        owned: set[Path],
    ) -> tuple[Path, Path]:
        source = output.physical_output_path
        if not source.is_dir() or not output.is_intermediate_output:
            return source, source

        visible_children = self._visible_children(source, owned, source)
        directories = [path for path in visible_children if path.is_dir()]
        if len(visible_children) != 1 or len(directories) != 1:
            return source, source

        logical_root = directories[0]
        content_root = logical_root
        archive_stem = self._archive_stem(output.archive_path)
        nested = self._visible_children(logical_root, owned, source)
        nested_directories = [path for path in nested if path.is_dir()]
        if (
            len(nested) == 1
            and len(nested_directories) == 1
            and archive_stem
            and logical_root.name.casefold() == archive_stem.casefold()
        ):
            nested_root = nested_directories[0]
            _, current_score = self._content_evidence(logical_root, set())
            _, nested_score = self._content_evidence(nested_root, set())
            if self._is_embedded_stage(source, output.archive_path) or (
                nested_score > current_score
            ):
                content_root = nested_root

        return logical_root, content_root

    @staticmethod
    def _visible_children(
        directory: Path, owned: set[Path], source: Path
    ) -> list[Path]:
        return [
            child
            for child in directory.iterdir()
            if not (
                child.resolve() != source
                and child.resolve() in owned
            )
        ]

    def _content_evidence(
        self, root: Path, excluded: set[Path]
    ) -> tuple[bool, int]:
        evidence = self.classifier.classify(root, excluded)
        return evidence.meaningful, evidence.score

    def _select(self, candidates: list[FinalContentCandidate]) -> None:
        meaningful = [
            candidate
            for candidate in candidates
            if candidate.has_meaningful_parent_content
        ]
        high = [
            candidate
            for candidate in meaningful
            if candidate.game_confidence >= self.HIGH_GAME_CONFIDENCE
        ]

        if high:
            for candidate in high:
                candidate.is_final_content = True
                candidate.selection_status = "SELECTED"
                candidate.selection_reason = "HIGH_CONFIDENCE_GAME_CONTENT"
            for candidate in meaningful:
                if candidate in high:
                    continue
                ancestor = self._selected_ancestor(candidate, high)
                if ancestor is not None:
                    candidate.selection_status = "SUPPRESSED"
                    candidate.selection_reason = (
                        "DESCENDANT_OF_SELECTED_CONTENT_ROOT"
                    )
                    ancestor.suppressed_descendants.append(candidate.physical_root)
                else:
                    candidate.selection_status = "NEEDS_USER_SELECTION"
                    candidate.selection_reason = "AMBIGUOUS_INDEPENDENT_CONTENT"
            return

        if len(meaningful) == 1:
            candidate = meaningful[0]
            candidate.is_final_content = True
            candidate.selection_status = "SELECTED"
            candidate.selection_reason = "SINGLE_CONTENT_CANDIDATE"
            return

        for candidate in candidates:
            candidate.selection_status = "NEEDS_USER_SELECTION"
            candidate.selection_reason = "AMBIGUOUS_CONTENT_ROOTS"

    @staticmethod
    def _selected_ancestor(
        candidate: FinalContentCandidate,
        selected: list[FinalContentCandidate],
    ) -> FinalContentCandidate | None:
        archive = candidate.source_archive
        if archive is None:
            return None
        for ancestor in selected:
            if archive == ancestor.content_root or ancestor.content_root in archive.parents:
                return ancestor
        return None

    @staticmethod
    def _archive_stem(archive_path: Path | None) -> str:
        if archive_path is None:
            return ""
        stem = archive_path.stem
        if stem.casefold().endswith("_embedded"):
            stem = stem[: -len("_embedded")]
        candidate = Path(stem)
        while candidate.suffix.casefold() in {".zip", ".rar", ".7z", ".lz4"}:
            candidate = Path(candidate.stem)
        return candidate.name

    @staticmethod
    def _is_embedded_stage(source: Path, archive_path: Path | None) -> bool:
        return (
            "_embedded_extracted" in source.name.casefold()
            or (
                archive_path is not None
                and archive_path.stem.casefold().endswith("_embedded")
            )
        )
