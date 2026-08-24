"""Recognize common split archive naming schemes without reading file contents."""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VolumeSet:
    entry_path: Path
    archive_format: str
    group_id: str
    volume_files: list[Path] = field(default_factory=list)
    missing_files: list[Path] = field(default_factory=list)


class SplitArchiveDetector:
    """Describe one local volume set and its reliably detectable gaps."""

    NUMBERED_PATTERN = re.compile(
        r"^(?P<base>.+\.(?P<format>7z|zip))\.(?P<index>\d{3})$",
        re.IGNORECASE,
    )
    PART_RAR_PATTERN = re.compile(
        r"^(?P<base>.+)\.part(?P<index>\d+)\.rar$",
        re.IGNORECASE,
    )
    OLD_RAR_PATTERN = re.compile(
        r"^(?P<base>.+)\.r(?P<index>\d{2})$",
        re.IGNORECASE,
    )

    def detect(self, file_path: str | Path) -> VolumeSet | None:
        path = Path(file_path).expanduser().resolve()
        name = path.name

        numbered = self.NUMBERED_PATTERN.match(name)
        if numbered:
            return self._numbered_set(path, numbered)

        part_rar = self.PART_RAR_PATTERN.match(name)
        if part_rar:
            return self._part_rar_set(path, part_rar)

        old_rar = self.OLD_RAR_PATTERN.match(name)
        if old_rar:
            return self._old_rar_set(path, old_rar.group("base"))

        if path.suffix.casefold() == ".rar":
            base = path.name[:-4]
            if any(
                self.OLD_RAR_PATTERN.match(candidate.name)
                and self.OLD_RAR_PATTERN.match(candidate.name).group("base").casefold()
                == base.casefold()
                for candidate in self._siblings(path)
            ):
                return self._old_rar_set(path, base)
        return None

    def _numbered_set(self, path: Path, match: re.Match) -> VolumeSet:
        base = match.group("base")
        archive_format = match.group("format").upper()
        indexed: dict[int, Path] = {}
        for candidate in self._siblings(path):
            candidate_match = self.NUMBERED_PATTERN.match(candidate.name)
            if (
                candidate_match
                and candidate_match.group("base").casefold() == base.casefold()
            ):
                indexed[int(candidate_match.group("index"))] = candidate.resolve()

        entry_path = indexed.get(1, path.parent / f"{base}.001").resolve()
        missing = self._numbered_gaps(
            indexed,
            lambda index: (path.parent / f"{base}.{index:03d}").resolve(),
            first_index=1,
        )
        # A .001 name explicitly declares a split set. Require at least the
        # next volume so a lone first part never reaches an Extractor.
        if max(indexed, default=0) == 1:
            missing.append((path.parent / f"{base}.002").resolve())
        return VolumeSet(
            entry_path=entry_path,
            archive_format=archive_format,
            group_id=str(entry_path).casefold(),
            volume_files=[indexed[index] for index in sorted(indexed)],
            missing_files=missing,
        )

    def _part_rar_set(self, path: Path, match: re.Match) -> VolumeSet:
        base = match.group("base")
        indexed: dict[int, Path] = {}
        widths: list[int] = []
        for candidate in self._siblings(path):
            candidate_match = self.PART_RAR_PATTERN.match(candidate.name)
            if (
                candidate_match
                and candidate_match.group("base").casefold() == base.casefold()
            ):
                index_text = candidate_match.group("index")
                indexed[int(index_text)] = candidate.resolve()
                widths.append(len(index_text))

        width = max(widths or [len(match.group("index"))])
        name_for = lambda index: (
            path.parent / f"{base}.part{index:0{width}d}.rar"
        ).resolve()
        entry_path = indexed.get(1, name_for(1))
        missing = self._numbered_gaps(indexed, name_for, first_index=1)
        # A .part1 / .part01 name explicitly declares a split set. Require at
        # least the next volume so a lone first part never reaches an Extractor.
        if max(indexed, default=0) == 1:
            next_part = name_for(2)
            if next_part not in missing:
                missing.append(next_part)
        return VolumeSet(
            entry_path=entry_path,
            archive_format="RAR",
            group_id=str(entry_path).casefold(),
            volume_files=[indexed[index] for index in sorted(indexed)],
            missing_files=missing,
        )

    def _old_rar_set(self, path: Path, base: str) -> VolumeSet:
        indexed: dict[int, Path] = {}
        first_path = (path.parent / f"{base}.rar").resolve()
        if first_path.is_file():
            indexed[0] = first_path
        for candidate in self._siblings(path):
            candidate_match = self.OLD_RAR_PATTERN.match(candidate.name)
            if (
                candidate_match
                and candidate_match.group("base").casefold() == base.casefold()
            ):
                indexed[int(candidate_match.group("index")) + 1] = candidate.resolve()

        def name_for(index: int) -> Path:
            if index == 0:
                return first_path
            return (path.parent / f"{base}.r{index - 1:02d}").resolve()

        missing = self._numbered_gaps(indexed, name_for, first_index=0)
        return VolumeSet(
            entry_path=first_path,
            archive_format="RAR",
            group_id=str(first_path).casefold(),
            volume_files=[indexed[index] for index in sorted(indexed)],
            missing_files=missing,
        )

    @staticmethod
    def _numbered_gaps(indexed, name_for, first_index: int) -> list[Path]:
        if not indexed:
            return [name_for(first_index)]
        return [
            name_for(index)
            for index in range(first_index, max(indexed) + 1)
            if index not in indexed
        ]

    @staticmethod
    def _siblings(path: Path) -> list[Path]:
        try:
            return [item for item in path.parent.iterdir() if item.is_file()]
        except OSError:
            return []
