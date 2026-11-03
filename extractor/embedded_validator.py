"""Validate the exact carved start using installed 7-Zip and full extraction."""

import re

from cleanup.runtime_tracker import register_created_directory
from extractor.embedded_work import EmbeddedIncomplete
from extractor.extractor_models import ExtractionResult, ExtractionStageDiagnostic, ExtractionStatus
from extractor.seven_zip import SevenZipExtractor
from security.archive_content_inspector import ArchiveContentInspector
from tools.models import ToolName


class EmbeddedValidator:
    # Only these fixed codes may cross the tool-output diagnostic boundary.
    VALIDATION_STAGES = frozenset({"LISTING", "DATA_EXTRACTION"})
    FAILURE_CODES = frozenset({"TOOL_NONZERO", "ARCHIVE_START_REJECTED", "UNSAFE_CONTENT"})

    def __init__(self, coordinator, work):
        self.coordinator = coordinator
        self.work = work

    def __call__(self, plan, password=None):
        manager = self.coordinator.content_inspector.tool_manager
        if manager is None:
            raise EmbeddedIncomplete("TOOL_UNAVAILABLE")
        tool = manager.get_tool_status(ToolName.SEVEN_ZIP)
        if not tool.available or not tool.verified or tool.path is None:
            raise EmbeddedIncomplete("TOOL_UNAVAILABLE")
        # s0 disables archive-start searching. Forcing the parser also prevents
        # a RAR decoy from being accepted as a different later container.
        parser = plan.detected_format.lower()
        if parser == "rar":
            with plan.archive_path.open("rb") as source:
                if source.read(8) == b"Rar!\x1a\x07\x01\x00":
                    parser = "rar5"
        options = [f"-t{parser}:s0", "-sccUTF-8"]
        code, text = self.work.run([str(tool.path), "l", "-slt", *options,
                                    str(plan.archive_path)], plan.archive_path.parent, password)
        if code:
            return self._failure(text, password, "LISTING")
        text = text.replace("\r\r\n", "\n").replace("\r\n", "\n")
        archive_header, separator, entries = text.partition("----------")
        if not separator or any(line.strip().startswith("Offset = ") and
                                line.strip() != "Offset = 0"
                                for line in archive_header.splitlines()):
            return self._failure("archive start rejected", password, "LISTING", "ARCHIVE_START_REJECTED")
        physical = re.search(r"(?m)^Physical Size = (\d+)\s*$", archive_header)
        if physical is None or not 0 < int(physical[1]) <= plan.archive_path.stat().st_size:
            raise EmbeddedIncomplete("ARCHIVE_RANGE_UNCONFIRMED")
        # Restrict the full data pass to the tool-confirmed range at offset 0.
        # Only the task-owned carve is truncated, never the original host.
        with plan.archive_path.open("r+b") as carved:
            carved.truncate(int(physical[1]))
        entries = re.sub(r"(?m)^Warnings: \d+\s*$", "", entries)
        inspector = ArchiveContentInspector()
        content = inspector._parse_seven_zip_listing(entries.lstrip("\r\n"))
        info = self.coordinator.analyzer.analyze(plan.archive_path)
        safety = self.coordinator.strategy.safety_checker.check(info, content)
        if not safety.safe:
            return self._failure("unsafe archive content", password, "LISTING", "UNSAFE_CONTENT")
        self.work.check(plan.archive_path.parent, content.estimated_size)
        plan.output_path.mkdir(exist_ok=False)
        register_created_directory(plan.output_path)

        def monitor():
            safety = self.coordinator.extraction_safety_checker.check(plan.output_path)
            if not safety.safe:
                raise EmbeddedIncomplete("OUTPUT_QUOTA_REACHED")

        code, text = self.work.run([str(tool.path), "x", *options,
            str(plan.archive_path), f"-o{plan.output_path}", "-aos", "-y"],
            plan.archive_path.parent, password, monitor)
        if code:
            return self._failure(text, password, "DATA_EXTRACTION")
        monitor()
        # x exit 0 verifies actual data/CRC. A successful listing never suffices.
        return ExtractionResult(True, "embedded data validation succeeded",
            plan.output_path, tool_used=ToolName.SEVEN_ZIP, status=ExtractionStatus.SUCCESS,
            stage_diagnostics=[ExtractionStageDiagnostic("DATA_EXTRACTION",
                tool=ToolName.SEVEN_ZIP, status=ExtractionStatus.SUCCESS,
                normalized_reason="SUCCESS")])

    @staticmethod
    def _failure(text, password, stage, code="TOOL_NONZERO"):
        status = SevenZipExtractor._classify_error(text)
        if password is None and status is ExtractionStatus.WRONG_PASSWORD:
            status = ExtractionStatus.PASSWORD_REQUIRED
        return ExtractionResult(False, "embedded validation rejected candidate",
            tool_used=ToolName.SEVEN_ZIP, status=status,
            stage_diagnostics=[ExtractionStageDiagnostic(stage,
                tool=ToolName.SEVEN_ZIP, status=status,
                error_type=code, normalized_reason=status.value)])
