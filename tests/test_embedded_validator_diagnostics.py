"""Synthetic tool responses exercise exact-start and full-data success gates."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from execution.models import ExtractionPlan
from extractor.embedded_validator import EmbeddedValidator
from extractor.extractor_models import ExtractionStatus as Status
from tools.models import ToolName


class EmbeddedValidatorDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        archive = self.root / "synthetic.rar"
        archive.write_bytes(b"Rar!\x1a\x07\x01\x00" + b"x" * 56)
        self.plan = ExtractionPlan(archive, "RAR", ToolName.SEVEN_ZIP, self.root / "out")
        safe = SimpleNamespace(safe=True)
        self.owner = SimpleNamespace(
            content_inspector=SimpleNamespace(tool_manager=Mock()),
            analyzer=Mock(), strategy=SimpleNamespace(safety_checker=Mock()),
            extraction_safety_checker=Mock())
        self.owner.content_inspector.tool_manager.get_tool_status.return_value = SimpleNamespace(
            available=True, verified=True, path=Path("synthetic-7z.exe"))
        self.owner.strategy.safety_checker.check.return_value = safe
        self.owner.extraction_safety_checker.check.return_value = safe
        self.work = Mock()
        self.listing = "Offset = 0\nPhysical Size = 64\n----------\nPath = payload.txt\nSize = 1\n"

    def test_every_nonzero_listing_or_data_exit_is_failure_with_sanitized_stage(self):
        secret = "synthetic-private-password"
        for stage in ("LISTING", "DATA_EXTRACTION"):
            for code in (1, 2, 7, 8, 255, -1):
                with self.subTest(stage=stage, code=code):
                    if self.plan.output_path.exists():
                        self.plan.output_path.rmdir()
                    failure = (code, "Data Error : private_payload.txt " + secret)
                    self.work.run.side_effect = ([failure] if stage == "LISTING" else
                                                 [(0, self.listing), failure])
                    result = EmbeddedValidator(self.owner, self.work)(self.plan, secret)
                    self.assertFalse(result.success)
                    self.assertEqual(result.status, Status.FAILED)
                    self.assertEqual(result.stage_diagnostics[0].stage, stage)
                    self.assertEqual(result.stage_diagnostics[0].error_type, "TOOL_NONZERO")
                    self.assertNotIn(secret, repr(result))
                    self.assertNotIn("private_payload.txt", repr(result))

    def test_password_classification_is_preserved_without_raw_output(self):
        for password, status in ((None, Status.PASSWORD_REQUIRED), ("synthetic", Status.WRONG_PASSWORD)):
            self.work.run.side_effect = [(2, "Wrong password : private_payload.txt")]
            result = EmbeddedValidator(self.owner, self.work)(self.plan, password)
            self.assertEqual(result.status, status)
            self.assertEqual(result.stage_diagnostics[0].stage, "LISTING")
            self.assertNotIn("private_payload.txt", repr(result))

    def test_listing_zero_requires_full_data_zero_and_exact_start(self):
        self.work.run.side_effect = [(0, self.listing), (0, "Everything is Ok")]
        result = EmbeddedValidator(self.owner, self.work)(self.plan)
        self.assertTrue(result.success)
        self.assertEqual([call.args[0][1] for call in self.work.run.call_args_list], ["l", "x"])
        for call in self.work.run.call_args_list:
            self.assertIn("-trar5:s0", call.args[0])

    def test_listing_at_nonzero_offset_never_runs_data_extraction(self):
        self.work.run.side_effect = [(0, self.listing.replace("Offset = 0", "Offset = 1"))]
        result = EmbeddedValidator(self.owner, self.work)(self.plan)
        self.assertFalse(result.success)
        self.assertEqual(self.work.run.call_count, 1)
        self.assertEqual(result.stage_diagnostics[0].stage, "LISTING")

    def test_success_markers_cannot_override_nonzero_exit(self):
        for responses, stage in (([(1, self.listing)], "LISTING"),
                                 ([(0, self.listing), (2, "Everything is Ok")], "DATA_EXTRACTION")):
            with self.subTest(stage=stage):
                self.work.run.side_effect = responses
                result = EmbeddedValidator(self.owner, self.work)(self.plan)
                self.assertFalse(result.success)
                self.assertEqual(result.status, Status.FAILED)
                self.assertEqual(result.stage_diagnostics[0].stage, stage)


if __name__ == "__main__":
    unittest.main()
