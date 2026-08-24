"""Regression coverage for delivery lineages and sanitized failure details."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from coordinator.models import CoordinatorResult
from extractor.extractor_models import (
    ExtractionResult,
    ExtractionStageDiagnostic,
    ExtractionStatus,
)
from history.models import TaskHistoryRecord
from history.storage import HistoryStorage
from organizer.delivery_units import DeliveryClassification
from organizer.models import ExtractionOutputSource
from organizer.output_organizer import OutputOrganizer
from pipeline.models import (
    ArchiveExecutionRecord,
    ArchiveTaskStatus,
    PipelineResult,
)
from report.task_report import ReportGenerator
from task.models import TaskStatus
from tools.models import ToolName


class DeliveryUnitRegressionTests(unittest.TestCase):
    def test_technical_archive_lineage_delivers_one_terminal_generic_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archives = [
                root / "B994000.rar",
                root / "stage1" / "B994000.zip",
                root / "stage2" / "B994000.jpg",
                root / "stage3" / "B994000.zip",
            ]
            outputs = [
                root / "B994000_extracted",
                root / "B994000_extracted" / "B994000_extracted",
                root / "B994000_extracted" / "B994000_extracted" / "B994000_extracted",
                root / "B994000_extracted" / "B994000_extracted" / "B994000_extracted" / "B994000_extracted",
            ]
            content = outputs[-1] / "B994000"
            for name in ("B9940补丁", "B9940补丁+控制台代码", "生存游戏"):
                (content / name).mkdir(parents=True, exist_ok=True)
                (content / name / "payload.bin").write_bytes(name.encode("utf-8"))

            sources = [
                ExtractionOutputSource(
                    physical_output_path=output,
                    archive_path=archives[index],
                    depth=index,
                    parent_archive=(archives[index - 1] if index else None),
                    runtime_owned=True,
                )
                for index, output in enumerate(outputs)
            ]
            organized, candidates = OutputOrganizer().resolve_and_organize(
                root, sources, outputs
            )

            self.assertEqual(len(organized), 1)
            self.assertEqual(organized[0].final_content_root, content.resolve())
            delivered = organized[0].final_output_path
            self.assertEqual(
                {path.name for path in delivered.iterdir()},
                {"B9940补丁", "B9940补丁+控制台代码", "生存游戏"},
            )
            selected = [item for item in candidates if item.is_final_content]
            self.assertEqual(len(selected), 1)
            self.assertEqual(
                selected[0].selection_reason,
                "SINGLE_TERMINAL_DELIVERY_UNIT",
            )

    def test_two_independent_game_roots_still_need_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "release_extracted"
            for game in ("GameA", "GameB"):
                game_root = output / game
                (game_root / f"{game}_Data").mkdir(parents=True)
                (game_root / f"{game}.exe").write_bytes(b"MZ")
                (game_root / f"{game}_Data" / "data.bin").write_bytes(b"x")
            organizer = OutputOrganizer()
            organized, _ = organizer.resolve_and_organize(
                root,
                [
                    ExtractionOutputSource(
                        physical_output_path=output,
                        archive_path=root / "release.rar",
                        runtime_owned=True,
                    )
                ],
                [output],
            )
            self.assertEqual(organized, [])
            self.assertEqual(len(organizer.last_delivery_units), 2)
            self.assertTrue(
                all(
                    item.classification is DeliveryClassification.AMBIGUOUS_CONTENT
                    and item.selection_status == "NEEDS_USER_SELECTION"
                    for item in organizer.last_delivery_units
                )
            )

    def test_ambiguous_delivery_units_can_be_selected_by_cli_callback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "release_extracted"
            # Intentionally create these in reverse name order.  Candidate order
            # may differ across filesystems, while the callback contract is based
            # on the exact list presented to the user.
            for game in ("GameB", "GameA"):
                game_root = output / game
                (game_root / f"{game}_Data").mkdir(parents=True)
                (game_root / f"{game}.exe").write_bytes(b"MZ")
                (game_root / f"{game}_Data" / "data.bin").write_bytes(b"x")

            callback_units = []

            def select_game_a(units):
                callback_units.extend(units)
                return [
                    next(
                        index
                        for index, unit in enumerate(units)
                        if unit.terminal_content_root.name == "GameA"
                    )
                ]

            organizer = OutputOrganizer()
            organized, _ = organizer.resolve_and_organize(
                root,
                [
                    ExtractionOutputSource(
                        output,
                        root / "release.rar",
                        runtime_owned=True,
                    )
                ],
                [output],
                selection_callback=select_game_a,
            )
            self.assertEqual(
                {unit.terminal_content_root.name for unit in callback_units},
                {"GameA", "GameB"},
            )
            self.assertEqual(len(organized), 1)
            self.assertEqual(organized[0].final_content_root.name, "GameA")
            self.assertFalse((root / "GameArchive_Output" / "GameB").exists())


class FailureDiagnosticRegressionTests(unittest.TestCase):
    def test_composite_stage_failure_round_trips_history_without_password(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "course.lz4"
            diagnostics = [
                ExtractionStageDiagnostic(
                    stage="COMPOSITE_OUTER",
                    detected_format="LZ4",
                    tool=ToolName.LZ4,
                    status=ExtractionStatus.SUCCESS,
                    error_type="SUCCESS",
                    normalized_reason="LZ4 stage completed",
                ),
                ExtractionStageDiagnostic(
                    stage="COMPOSITE_INNER",
                    detected_format="RAR",
                    tool=ToolName.SEVEN_ZIP,
                    status=ExtractionStatus.WRONG_PASSWORD,
                    error_type="WRONG_PASSWORD",
                    normalized_reason="password=secret was rejected",
                ),
            ]
            extraction = ExtractionResult(
                False,
                "Password candidates exhausted",
                root / "course_extracted",
                "Wrong password",
                ToolName.SEVEN_ZIP,
                ExtractionStatus.WRONG_PASSWORD,
                diagnostics,
            )
            coordinator = CoordinatorResult(
                success=False,
                archive_path=archive,
                extraction_result=extraction,
                error_message="Wrong password",
                failure_stage="PASSWORD_RECOVERY",
                error_type="PASSWORD_CANDIDATES_EXHAUSTED",
                user_message="Password candidates exhausted",
                password_attempt_count=3,
                fallback_tools_attempted=[ToolName.WINRAR],
                final_tool=ToolName.SEVEN_ZIP,
                composite_stage="COMPOSITE_INNER",
                stage_diagnostics=diagnostics,
            )
            pipeline = PipelineResult(
                success=False,
                execution_records=[
                    ArchiveExecutionRecord(
                        archive,
                        0,
                        None,
                        ArchiveTaskStatus.FAILED,
                        coordinator,
                        extraction.output_path,
                    )
                ],
            )
            report = ReportGenerator().generate(pipeline)
            self.assertEqual(report.failure_details[0].password_attempt_count, 3)
            self.assertEqual(report.failure_details[0].composite_stage, "COMPOSITE_INNER")
            self.assertEqual(len(report.failure_details[0].stage_details), 2)

            storage = HistoryStorage(root / "history.json")
            now = datetime.now().astimezone()
            storage.save(
                TaskHistoryRecord(
                    "task-diagnostic",
                    root,
                    TaskStatus.FAILED,
                    now,
                    now,
                    False,
                    "failed",
                    failure_details=report.failure_details,
                )
            )
            raw = (root / "history.json").read_text(encoding="utf-8")
            self.assertNotIn("secret", raw)
            restored = storage.read_all()[0].failure_details[0]
            self.assertEqual(restored.error_type, "PASSWORD_CANDIDATES_EXHAUSTED")
            self.assertEqual(restored.stage_details[0]["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
