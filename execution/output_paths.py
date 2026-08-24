"""Generate non-conflicting extraction and final-output paths."""

from pathlib import Path


class OutputPathGenerator:
    """Choose a new path while preserving every existing directory."""

    @classmethod
    def for_archive(cls, archive_path: str | Path) -> Path:
        """Return the next extraction directory for an archive."""
        archive = Path(archive_path).expanduser().resolve()
        preferred = archive.parent / f"{archive.stem}_extracted"
        return cls.next_available(preferred)

    @staticmethod
    def next_available(preferred_path: str | Path) -> Path:
        """Return preferred_path, or append _2, _3, ... until it is unused."""
        preferred = Path(preferred_path).expanduser()
        candidate = preferred
        suffix = 2
        while candidate.exists():
            candidate = preferred.with_name(f"{preferred.name}_{suffix}")
            suffix += 1
        return candidate
