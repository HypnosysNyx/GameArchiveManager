"""Decide automatic extraction intent without changing real-format facts."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from analyzer.models import ArchiveInfo


class ContainerRole(str, Enum):
    """Product meaning of an analyzer-confirmed container."""

    ARCHIVE_WRAPPER = "ARCHIVE_WRAPPER"
    CONTENT_CONTAINER = "CONTENT_CONTAINER"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class ContainerRoleDecision:
    """Small diagnostic explaining why automatic discovery kept or queued it."""

    path: Path
    role: ContainerRole
    reason: str
    scan_mode: str
    explicit: bool
    extension: str
    real_format: str

    @property
    def should_auto_extract(self) -> bool:
        return self.role is ContainerRole.ARCHIVE_WRAPPER


class ContainerRolePolicy:
    """Classify known user containers after ArchiveAnalyzer has done its job."""

    # These formats have clear standalone product semantics even though their
    # technical representation is ZIP.  .save is intentionally context-bound
    # and is not included here.
    ZIP_CONTENT_CONTAINER_EXTENSIONS = {
        ".apk",
        ".docx",
        ".xlsx",
        ".pptx",
        ".epub",
        ".jar",
    }

    def classify(
        self,
        archive_info: ArchiveInfo,
        scan_mode: object,
        explicit_input: bool = False,
    ) -> ContainerRoleDecision:
        """Return execution intent while preserving analyzer format metadata."""
        mode = getattr(scan_mode, "value", str(scan_mode))
        path = archive_info.file_path

        if explicit_input:
            return self._decision(
                archive_info,
                ContainerRole.ARCHIVE_WRAPPER,
                "EXPLICIT_USER_INPUT",
                mode,
                True,
            )

        if archive_info.is_embedded_archive:
            return self._decision(
                archive_info,
                ContainerRole.ARCHIVE_WRAPPER,
                "VERIFIED_EMBEDDED_ARCHIVE",
                mode,
                False,
            )

        extension = path.suffix.casefold()
        if (
            archive_info.real_format == "ZIP"
            and extension in self.ZIP_CONTENT_CONTAINER_EXTENSIONS
        ):
            return self._decision(
                archive_info,
                ContainerRole.CONTENT_CONTAINER,
                "KNOWN_CONTENT_CONTAINER_EXTENSION",
                mode,
                False,
            )

        if archive_info.real_format != "UNKNOWN":
            return self._decision(
                archive_info,
                ContainerRole.ARCHIVE_WRAPPER,
                "STRONG_VERIFIED_ARCHIVE",
                mode,
                False,
            )

        return self._decision(
            archive_info,
            ContainerRole.AMBIGUOUS,
            "UNCONFIRMED_CONTAINER",
            mode,
            False,
        )

    @staticmethod
    def _decision(
        archive_info: ArchiveInfo,
        role: ContainerRole,
        reason: str,
        scan_mode: str,
        explicit: bool,
    ) -> ContainerRoleDecision:
        return ContainerRoleDecision(
            path=archive_info.file_path,
            role=role,
            reason=reason,
            scan_mode=scan_mode,
            explicit=explicit,
            extension=archive_info.extension,
            real_format=archive_info.real_format,
        )
