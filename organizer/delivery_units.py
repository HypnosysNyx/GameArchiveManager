"""Collapse technical archive execution lineages into user delivery units."""

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

from organizer.game_content_classifier import GameContentClassifier
from organizer.models import FinalContentCandidate


class DeliveryClassification(str, Enum):
    GAME_CONTENT = "GAME_CONTENT"
    GENERIC_CONTENT = "GENERIC_CONTENT"
    AMBIGUOUS_CONTENT = "AMBIGUOUS_CONTENT"
    TECHNICAL_ONLY = "TECHNICAL_ONLY"


@dataclass
class DeliveryUnit:
    root_execution_node: Path | None
    terminal_execution_node: Path | None
    execution_node_paths: list[Path] = field(default_factory=list)
    terminal_content_root: Path | None = None
    classification: DeliveryClassification = DeliveryClassification.TECHNICAL_ONLY
    confidence: int = 0
    selection_status: str = "CANDIDATE"
    selection_reason: str = ""


class DeliveryUnitResolver:
    """Use execution ancestry, not raw candidate count, for final delivery."""

    ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z", ".lz4"}

    def __init__(self, classifier: GameContentClassifier | None = None) -> None:
        self.classifier = classifier or GameContentClassifier()

    def resolve(
        self, candidates: list[FinalContentCandidate]
    ) -> tuple[list[FinalContentCandidate], list[DeliveryUnit]]:
        if not candidates:
            return candidates, []

        by_archive = {
            item.source_archive.resolve(): item
            for item in candidates
            if item.source_archive is not None
        }
        child_archives = {
            item.parent_archive.resolve()
            for item in candidates
            if item.parent_archive is not None
        }
        terminals = [
            item
            for item in candidates
            if item.source_archive is not None
            and item.source_archive.resolve() not in child_archives
        ]
        if not terminals:
            terminals = candidates.copy()

        units: list[DeliveryUnit] = []
        expanded = candidates.copy()
        for terminal in terminals:
            lineage = self._lineage(terminal, by_archive)
            provisional = [
                item
                for item in lineage
                if item.is_final_content
                and item.selection_reason == "SINGLE_CONTENT_CANDIDATE"
                and item.game_confidence < 60
            ]
            for item in provisional:
                item.is_final_content = False
                item.selection_status = "CANDIDATE"
                item.selection_reason = "PENDING_DELIVERY_UNIT_RESOLUTION"
            selected = [item for item in lineage if item.is_final_content]
            if selected:
                for item in selected:
                    units.append(
                        self._unit(
                            lineage,
                            item,
                            DeliveryClassification.GAME_CONTENT,
                            item.selection_status,
                            item.selection_reason,
                        )
                    )
                continue

            split_candidates = self._independent_game_roots(terminal)
            if len(split_candidates) > 1:
                terminal.selection_status = "SUPPRESSED"
                terminal.selection_reason = "MULTIPLE_INDEPENDENT_CONTENT_ROOTS"
                for child in split_candidates:
                    expanded.append(child)
                    units.append(
                        self._unit(
                            lineage,
                            child,
                            DeliveryClassification.AMBIGUOUS_CONTENT,
                            "NEEDS_USER_SELECTION",
                            "MULTIPLE_TERMINAL_DELIVERY_UNITS",
                        )
                    )
                continue

            if self._contains_user_content(terminal.content_root):
                units.append(
                    self._unit(
                        lineage,
                        terminal,
                        DeliveryClassification.GENERIC_CONTENT,
                        "CANDIDATE",
                        "TERMINAL_USER_CONTENT",
                    )
                )
            else:
                units.append(
                    self._unit(
                        lineage,
                        terminal,
                        DeliveryClassification.TECHNICAL_ONLY,
                        "SUPPRESSED",
                        "TERMINAL_CONTAINS_ONLY_TECHNICAL_CONTENT",
                    )
                )

        deliverable = [
            unit
            for unit in units
            if unit.classification is not DeliveryClassification.TECHNICAL_ONLY
            and unit.selection_status != "SELECTED"
        ]
        # Selection is scoped to one independent input lineage.  A selected
        # game from one input must not hide a valid generic result from a
        # different input.  Only competing roots inside the same lineage need
        # a user decision.
        by_root: dict[Path | None, list[DeliveryUnit]] = {}
        for unit in deliverable:
            by_root.setdefault(unit.root_execution_node, []).append(unit)
        initially_selected = [item for item in expanded if item.is_final_content]

        for lineage_units in by_root.values():
            if len(lineage_units) == 1:
                unit = lineage_units[0]
                target = self._candidate_for_unit(expanded, unit)
                selected_descendant = any(
                    target.physical_root != selected.physical_root
                    and target.physical_root in selected.physical_root.parents
                    for selected in initially_selected
                )
                is_single_task_unit = (
                    not initially_selected and len(deliverable) == 1
                )
                is_independent_of_selected = (
                    bool(initially_selected)
                    and target.selection_reason
                    == "AMBIGUOUS_INDEPENDENT_CONTENT"
                    and not selected_descendant
                )
                if not (is_single_task_unit or is_independent_of_selected):
                    unit.selection_status = "NEEDS_USER_SELECTION"
                    unit.selection_reason = "MULTIPLE_TERMINAL_DELIVERY_UNITS"
                    target.is_final_content = False
                    target.selection_status = unit.selection_status
                    target.selection_reason = unit.selection_reason
                    continue

                unit.selection_status = "SELECTED"
                unit.selection_reason = "SINGLE_TERMINAL_DELIVERY_UNIT"
                target.is_final_content = True
                target.selection_status = "SELECTED"
                target.selection_reason = unit.selection_reason
                for ancestor in candidates:
                    if (
                        ancestor is target
                        or ancestor not in self._lineage(target, by_archive)
                    ):
                        continue
                    ancestor.is_final_content = False
                    ancestor.selection_status = "SUPPRESSED"
                    ancestor.selection_reason = (
                        "TECHNICAL_ANCESTOR_IN_DELIVERY_LINEAGE"
                    )
                continue

            for unit in lineage_units:
                unit.selection_status = "NEEDS_USER_SELECTION"
                unit.selection_reason = "MULTIPLE_TERMINAL_DELIVERY_UNITS"
                target = self._candidate_for_unit(expanded, unit)
                target.is_final_content = False
                target.selection_status = unit.selection_status
                target.selection_reason = unit.selection_reason

        return expanded, units

    def _lineage(
        self,
        terminal: FinalContentCandidate,
        by_archive: dict[Path, FinalContentCandidate],
    ) -> list[FinalContentCandidate]:
        lineage = [terminal]
        current = terminal
        seen: set[Path] = set()
        while current.parent_archive is not None:
            parent_path = current.parent_archive.resolve()
            if parent_path in seen or parent_path not in by_archive:
                break
            seen.add(parent_path)
            current = by_archive[parent_path]
            lineage.append(current)
        lineage.reverse()
        return lineage

    def _independent_game_roots(
        self, terminal: FinalContentCandidate
    ) -> list[FinalContentCandidate]:
        root = terminal.content_root
        if not root.is_dir():
            return []
        high: list[FinalContentCandidate] = []
        for child in root.iterdir():
            if not child.is_dir():
                continue
            evidence = self.classifier.classify(child, set())
            if evidence.score < 60:
                continue
            high.append(
                replace(
                    terminal,
                    logical_root=child,
                    content_root=child,
                    game_confidence=evidence.score,
                    is_final_content=False,
                    selection_status="NEEDS_USER_SELECTION",
                    selection_reason="MULTIPLE_TERMINAL_DELIVERY_UNITS",
                    suppressed_descendants=[],
                    excluded_owned_outputs=[],
                    final_output_path=None,
                )
            )
        return high

    def _contains_user_content(self, root: Path) -> bool:
        if root.is_file():
            return root.suffix.casefold() not in self.ARCHIVE_SUFFIXES
        if not root.is_dir():
            return False
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.casefold() not in self.ARCHIVE_SUFFIXES:
                return True
        return False

    @staticmethod
    def _candidate_for_unit(
        candidates: list[FinalContentCandidate], unit: DeliveryUnit
    ) -> FinalContentCandidate:
        for candidate in candidates:
            if candidate.content_root == unit.terminal_content_root:
                return candidate
        raise ValueError("Delivery unit has no matching final content candidate")

    @staticmethod
    def _unit(
        lineage: list[FinalContentCandidate],
        target: FinalContentCandidate,
        classification: DeliveryClassification,
        status: str,
        reason: str,
    ) -> DeliveryUnit:
        paths = [
            item.source_archive
            for item in lineage
            if item.source_archive is not None
        ]
        return DeliveryUnit(
            root_execution_node=paths[0] if paths else None,
            terminal_execution_node=(
                target.source_archive or (paths[-1] if paths else None)
            ),
            execution_node_paths=paths,
            terminal_content_root=target.content_root,
            classification=classification,
            confidence=target.game_confidence,
            selection_status=status,
            selection_reason=reason,
        )
