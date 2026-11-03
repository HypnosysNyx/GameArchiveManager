"""Host-scoped embedded candidate regressions; no historical sample claims."""

import hashlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from analyzer.embedded_detector import EmbeddedArchiveDetector
from coordinator.extraction_coordinator import ExtractionCoordinator
from extractor.extractor_models import ExtractionResult, ExtractionStageDiagnostic, ExtractionStatus as Status
from password.models import PasswordCandidate, PasswordSource
from password.session_store import SessionPasswordStore
from recovery.manual import ManualPasswordAction as Action, ManualPasswordResponse
from tests.test_integration import create_rar5_encryption_header


SECRET = "embedded_manual_secret_85391"


class EmbeddedCandidateResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.host = self.root / "host.jpg"

    def require_rar_fixture_builder(self):
        """Explicitly skip environment-dependent RAR5 integration cases when unavailable."""
        rar = Path(r"C:\Program Files\WinRAR\Rar.exe")
        if not rar.is_file():
            self.skipTest("Optional WinRAR Rar.exe not installed: real RAR5 fixture NOT VERIFIED")
        return rar

    def host_with(self, count=2):
        header = create_rar5_encryption_header()
        self.host.write_bytes(b"\xff\xd8\xffhost" + (header + b"padding") * count)
        return [7 + i * (len(header) + 7) for i in range(count)]

    def coordinator(self, validator):
        coordinator = ExtractionCoordinator()
        coordinator.embedded_validator = validator
        return coordinator

    def successful(self, plan, password=None):
        plan.output_path.mkdir()
        (plan.output_path / "payload.txt").write_text("correct content")
        return ExtractionResult(True, "ok", plan.output_path, status=Status.SUCCESS)

    def test_crc_valid_decoy_then_real_rar5_uses_full_validation(self):
        rar = self.require_rar_fixture_builder()
        payload = self.root / "payload.txt"
        payload.write_text("correct content")
        archive = self.root / "real.rar"
        subprocess.run([str(rar), "a", "-ma5", "-ep1", str(archive), str(payload)],
                       check=True, capture_output=True, timeout=30)
        decoy = create_rar5_encryption_header() + b"decoy-not-an-archive"
        self.host.write_bytes(b"\xff\xd8\xffhost" + decoy + archive.read_bytes())
        before = hashlib.sha256(self.host.read_bytes()).digest()
        result = ExtractionCoordinator().process(self.host)
        self.assertTrue(result.success, result)
        self.assertEqual(result.extraction_result.embedded_offset, 7 + len(decoy))
        self.assertEqual((result.extraction_result.output_path / "payload.txt").read_text(),
                         "correct content")
        self.assertEqual(hashlib.sha256(self.host.read_bytes()).digest(), before)
        self.assertFalse(list(self.root.glob(".gam_candidate_*")))

    def test_real_header_encrypted_rar5_after_decoy_manual_password(self):
        """A real encrypted payload must remain reachable after a CRC-valid decoy."""
        rar = self.require_rar_fixture_builder()
        payload = self.root / "private_payload.txt"
        payload.write_text("verified encrypted payload", encoding="utf-8")
        archive = self.root / "encrypted.rar"
        # The password here is a synthetic test constant, never a user secret.
        subprocess.run([str(rar), "a", "-ma5", f"-hp{SECRET}", "-ep1",
                        str(archive), str(payload)],
                       check=True, capture_output=True, timeout=30)
        decoy = create_rar5_encryption_header() + b"decoy-not-an-archive"
        true_offset = 7 + len(decoy)
        self.host.write_bytes(b"\xff\xd8\xffhost" + decoy + archive.read_bytes())
        digest = hashlib.sha256(self.host.read_bytes()).digest()

        detector = EmbeddedArchiveDetector()
        candidates = list(detector.iter_candidates(self.host))
        self.assertEqual([candidate.offset for candidate in candidates], [7, true_offset])
        self.assertEqual(candidates[1].validation_result.value, "VALID_ENCRYPTED")

        callback = Mock(return_value=ManualPasswordResponse(Action.INPUT_PASSWORD, SECRET))
        store = SessionPasswordStore(self.root / "encrypted_store.json")
        result = ExtractionCoordinator().process(
            self.host, max_password_attempts=0,
            manual_password_callback=callback, session_password_store=store)
        self.assertTrue(result.success, result)
        self.assertEqual(callback.call_count, 1)
        self.assertEqual(result.password_attempt_count, 0)
        self.assertEqual(result.manual_password_attempt_count, 1)
        self.assertEqual(result.extraction_result.embedded_offset, true_offset)
        self.assertEqual((result.extraction_result.output_path / payload.name).read_text(
            encoding="utf-8"), "verified encrypted payload")
        self.assertEqual(hashlib.sha256(self.host.read_bytes()).digest(), digest)
        self.assertFalse(list(self.root.glob(".gam_candidate_*")))
        self.assertEqual(len(store), 1)

    def test_first_success_does_not_validate_later_signature(self):
        offsets = self.host_with()
        validator = Mock(side_effect=self.successful)
        coordinator = self.coordinator(validator)
        with patch.object(coordinator.analyzer.embedded_detector, "validate_candidate",
                          wraps=coordinator.analyzer.embedded_detector.validate_candidate) as local:
            result = coordinator.process(self.host)
        self.assertTrue(result.success)
        self.assertEqual(result.extraction_result.embedded_offset, offsets[0])
        self.assertTrue(all(call.args[1] == offsets[0] for call in local.call_args_list))
        self.assertEqual(validator.call_count, 1)

    def test_listing_success_data_crc_failure_falls_through(self):
        offsets = self.host_with()
        def validate(plan, password=None):
            if plan.embedded_offset == offsets[0]:
                return ExtractionResult(False, "listing ok; data CRC failed", status=Status.FAILED)
            return self.successful(plan)
        result = self.coordinator(validate).process(self.host)
        self.assertTrue(result.success)
        self.assertEqual(result.extraction_result.embedded_offset, offsets[1])

    def encrypted_run(self, responses, max_manual=100):
        offsets = self.host_with()
        attempts = []
        def validate(plan, password=None):
            attempts.append((plan.embedded_offset, password is not None))
            if plan.embedded_offset == offsets[1] and password == SECRET:
                return self.successful(plan)
            return ExtractionResult(False, "encrypted", status=(
                Status.PASSWORD_REQUIRED if password is None else Status.WRONG_PASSWORD))
        coordinator = self.coordinator(validate)
        coordinator.MAX_MANUAL_PASSWORD_ATTEMPTS = max_manual
        callback = Mock(side_effect=responses)
        store = SessionPasswordStore(self.root / "store.json")
        result = coordinator.process(self.host,
            [PasswordCandidate("wrong-auto", PasswordSource.USER_INPUT)],
            max_password_attempts=1, manual_password_callback=callback,
            session_password_store=store)
        self.assertNotIn(SECRET, repr(result))
        return result, callback, store, attempts

    def test_global_auto_budget_then_one_manual_submission_tries_both(self):
        result, callback, store, attempts = self.encrypted_run([
            ManualPasswordResponse(Action.INPUT_PASSWORD, SECRET)])
        self.assertTrue(result.success)
        self.assertEqual(result.password_attempt_count, 1)
        self.assertEqual(result.manual_password_attempt_count, 1)
        self.assertEqual(callback.call_count, 1)
        self.assertEqual(len(store), 1)
        self.assertEqual(len(attempts), 5)

    def test_wrong_then_correct(self):
        result, callback, store, _ = self.encrypted_run([
            ManualPasswordResponse(Action.INPUT_PASSWORD, "wrong-manual"),
            ManualPasswordResponse(Action.INPUT_PASSWORD, SECRET)])
        self.assertTrue(result.success)
        self.assertEqual(result.manual_password_attempt_count, 2)
        self.assertEqual(callback.call_count, 2)
        self.assertEqual(len(store), 1)

    def test_all_wrong(self):
        result, _, store, _ = self.encrypted_run([
            ManualPasswordResponse(Action.INPUT_PASSWORD, "wrong")], max_manual=1)
        self.assertFalse(result.success)
        self.assertEqual(result.manual_password_attempt_count, 1)
        self.assertEqual(len(store), 0)

    def test_skip_and_cancel(self):
        for action, control in [(Action.SKIP_ARCHIVE, "SKIP_ARCHIVE"),
                                (Action.CANCEL_TASK, "CANCEL_TASK")]:
            with self.subTest(action=action):
                result, callback, store, _ = self.encrypted_run([ManualPasswordResponse(action)])
                self.assertEqual(result.control_action, control)
                self.assertEqual(result.manual_password_attempt_count, 0)
                self.assertEqual(callback.call_count, 1)
                self.assertEqual(len(store), 0)

    def test_detector_resumes_in_order(self):
        offsets = self.host_with(3)
        detector = EmbeddedArchiveDetector()
        self.assertEqual([c.offset for c in detector.iter_candidates(self.host)], offsets)

    def test_candidate_raw_hit_scan_and_cancel_limits_are_explicit(self):
        self.host_with(10)
        for kwargs, reason in [({"max_candidates": 1}, "CANDIDATE_LIMIT_REACHED"),
                               ({"max_raw_hits": 1}, "RAW_HIT_LIMIT_REACHED"),
                               ({"max_scan_bytes": 5}, "SCAN_LIMIT_REACHED")]:
            with self.subTest(reason=reason):
                detector = EmbeddedArchiveDetector(**kwargs)
                list(detector.iter_candidates(self.host))
                self.assertEqual(detector.last_diagnostic.reason.value, reason)
        detector = EmbeddedArchiveDetector()
        list(detector.iter_candidates(self.host, cancelled=lambda: True))
        self.assertEqual(detector.last_diagnostic.reason.value, "CANCELLED")

    def test_carve_budget_disk_timeout_cancel_report_incomplete(self):
        self.host_with()
        for limit, reason in [("max_carved_bytes", "CARVE_BUDGET_REACHED"),
                              ("disk_reserve_bytes", "DISK_RESERVE_REACHED"),
                              ("timeout_seconds", "TIMEOUT")]:
            with self.subTest(limit=limit):
                coordinator = self.coordinator(Mock(side_effect=self.successful))
                coordinator.embedded_limits = {limit: (10**30 if limit == "disk_reserve_bytes" else 0)}
                result = coordinator.process(self.host)
                self.assertFalse(result.success)
                self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
                self.assertIn(reason, result.error_message)
        result = self.coordinator(Mock()).process(self.host, cancelled=lambda: True)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("CANCELLED", result.error_message)

    def test_no_candidate_within_scan_window_is_incomplete(self):
        self.host_with()
        coordinator = self.coordinator(Mock())
        coordinator.analyzer.embedded_detector.max_scan_bytes = 5
        result = coordinator.process(self.host)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("SCAN_LIMIT_REACHED", result.error_message)

    def scanlimited_fixture(self, validator):
        offsets = self.host_with()
        coordinator = self.coordinator(validator)
        coordinator.analyzer.embedded_detector.max_scan_bytes = self.host.stat().st_size - 1
        return coordinator, offsets

    def test_scanlimit_diagnostic_password_required_without_callback(self):
        validator = Mock(return_value=ExtractionResult(
            False, "raw tool output " + SECRET, status=Status.PASSWORD_REQUIRED))
        coordinator, offsets = self.scanlimited_fixture(validator)
        before = self.host.read_bytes()
        result = coordinator.process(self.host, max_password_attempts=0)
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("SCAN_LIMIT_REACHED", result.error_message)
        for offset in offsets:
            self.assertIn(f"offset={offset}; PASSWORD_REQUIRED", result.error_message)
        self.assertEqual(result.password_attempt_count, 0)
        self.assertEqual(result.manual_password_attempt_count, 0)
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn("raw tool output", repr(result))
        self.assertEqual(self.host.read_bytes(), before)
        self.assertFalse(list(self.root.glob(".gam_candidate_*")))

    def test_scanlimit_diagnostic_failed_candidate_keeps_each_status(self):
        validator = Mock(side_effect=[
            ExtractionResult(False, "raw " + SECRET, status=Status.PASSWORD_REQUIRED),
            ExtractionResult(False, "raw CRC output " + SECRET, status=Status.FAILED)])
        coordinator, offsets = self.scanlimited_fixture(validator)
        result = coordinator.process(self.host)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("SCAN_LIMIT_REACHED", result.error_message)
        self.assertIn(f"offset={offsets[0]}; PASSWORD_REQUIRED", result.error_message)
        self.assertIn(f"offset={offsets[1]}; FAILED", result.error_message)
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn("raw CRC output", repr(result))

    def test_scanlimit_diagnostic_no_candidate_is_explicit(self):
        coordinator, _ = self.scanlimited_fixture(Mock())
        coordinator.analyzer.embedded_detector.max_scan_bytes = 5
        result = coordinator.process(self.host)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("SCAN_LIMIT_REACHED", result.error_message)
        self.assertIn("candidates=none", result.error_message)
        self.assertTrue(any("SCAN_LIMIT_REACHED" in step and "scanned_bytes=5" in step
                            for step in result.steps))
        self.assertEqual(result.stage_diagnostics, [])

    def test_scanlimit_diagnostic_callback_still_reached(self):
        validator = Mock(return_value=ExtractionResult(
            False, "encrypted", status=Status.PASSWORD_REQUIRED))
        coordinator, _ = self.scanlimited_fixture(validator)
        callback = Mock(return_value=ManualPasswordResponse(Action.SKIP_ARCHIVE))
        result = coordinator.process(self.host, manual_password_callback=callback)
        self.assertEqual(callback.call_count, 1)
        self.assertEqual(result.control_action, "SKIP_ARCHIVE")
        self.assertFalse(result.success)
        self.assertTrue(any("SCAN_LIMIT_REACHED" in step for step in result.steps))
        self.assertEqual(result.manual_password_attempt_count, 0)

    def test_scanlimit_diagnostic_successful_candidate_unaffected(self):
        # The injected validator represents completed data validation, not
        # proof that a password can decrypt any real encrypted candidate.
        coordinator, offsets = self.scanlimited_fixture(self.successful)
        result = coordinator.process(self.host)
        self.assertTrue(result.success, result)
        self.assertEqual(result.extraction_result.embedded_offset, offsets[0])
        self.assertEqual(result.extraction_result.embedded_validation_state, "DATA_VALIDATED")
        self.assertEqual((result.extraction_result.output_path / "payload.txt").read_text(),
                         "correct content")
        self.assertFalse(result.error_message)
        self.assertFalse(any("SCAN_LIMIT_REACHED" in step for step in result.steps))

    def test_scan_cap_preserves_failed_stages_and_pending_password(self):
        validator = Mock(side_effect=[
            ExtractionResult(False, SECRET, status=Status.PASSWORD_REQUIRED,
                stage_diagnostics=[ExtractionStageDiagnostic("LISTING", status=Status.PASSWORD_REQUIRED,
                    error_type="TOOL_NONZERO", normalized_reason=SECRET)]),
            ExtractionResult(False, SECRET, status=Status.FAILED,
                stage_diagnostics=[ExtractionStageDiagnostic("DATA_EXTRACTION", status=Status.FAILED,
                    error_type="TOOL_NONZERO", normalized_reason="private_payload.txt " + SECRET)])])
        coordinator, offsets = self.scanlimited_fixture(validator)
        result = coordinator.process(self.host)
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("SCAN_LIMIT_REACHED", result.error_message)
        self.assertIn("PASSWORD_UNRESOLVED", result.error_message)
        self.assertEqual(result.password_recovery_result, "UNRESOLVED")
        self.assertEqual([d.stage for d in result.stage_diagnostics], ["LISTING", "DATA_EXTRACTION"])
        for diagnostic, offset in zip(result.stage_diagnostics, offsets):
            self.assertIn(f"offset={offset};", diagnostic.normalized_reason)
            self.assertEqual(diagnostic.error_type, "TOOL_NONZERO")
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn("private_payload.txt", repr(result))

    def test_scan_cap_preserves_candidate_rejected_before_tool_validation(self):
        validator = Mock()
        coordinator, offsets = self.scanlimited_fixture(validator)
        create_plan = coordinator.strategy.create_plan
        def reject_candidate(info, *args):
            plan = create_plan(info, *args)
            if plan.archive_path != self.host:
                return replace(plan, can_execute=False)
            return plan
        with patch.object(coordinator.strategy, "create_plan", side_effect=reject_candidate):
            result = coordinator.process(self.host)
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("SCAN_LIMIT_REACHED", result.error_message)
        self.assertEqual([d.stage for d in result.stage_diagnostics],
                         ["CANDIDATE_SAFETY", "CANDIDATE_SAFETY"])
        for offset, diagnostic in zip(offsets, result.stage_diagnostics):
            self.assertIn(f"offset={offset}; FAILED", diagnostic.normalized_reason)
            self.assertIn(f"offset={offset}; FAILED", result.error_message)
        validator.assert_not_called()

    def test_manual_prompt_uses_first_pending_status_after_later_failure(self):
        for later in (Status.FAILED, Status.PASSWORD_REQUIRED):
            with self.subTest(later=later):
                validator = Mock(side_effect=[
                    ExtractionResult(False, "encrypted", status=Status.PASSWORD_REQUIRED),
                    ExtractionResult(False, "wrong", status=Status.WRONG_PASSWORD),
                    ExtractionResult(False, "later", status=later)])
                coordinator, _ = self.scanlimited_fixture(validator)
                callback = Mock(return_value=ManualPasswordResponse(Action.SKIP_ARCHIVE))
                result = coordinator.process(self.host,
                    [PasswordCandidate(SECRET, PasswordSource.USER_INPUT)], max_password_attempts=1,
                    manual_password_callback=callback)
                self.assertEqual(callback.call_args.args[0].status, Status.WRONG_PASSWORD)
                self.assertFalse(result.success)
                self.assertEqual(result.control_action, "SKIP_ARCHIVE")
                self.assertNotIn(SECRET, repr(result))

    def test_scan_cap_manual_recovery_requires_validated_data(self):
        for data_valid in (False, True):
            with self.subTest(data_valid=data_valid):
                def validate(plan, password=None):
                    if password is None:
                        return ExtractionResult(False, "encrypted", status=Status.PASSWORD_REQUIRED,
                            stage_diagnostics=[ExtractionStageDiagnostic("LISTING")])
                    if data_valid:
                        return self.successful(plan)
                    return ExtractionResult(False, "CRC error " + SECRET, status=Status.FAILED,
                        stage_diagnostics=[ExtractionStageDiagnostic("DATA_EXTRACTION",
                            error_type="TOOL_NONZERO")])
                coordinator, _ = self.scanlimited_fixture(validate)
                store = SessionPasswordStore(self.root / "recovery_store.json")
                callback = Mock(return_value=ManualPasswordResponse(Action.INPUT_PASSWORD, SECRET))
                result = coordinator.process(self.host, max_password_attempts=0,
                    manual_password_callback=callback, session_password_store=store)
                self.assertEqual(result.success, data_valid)
                self.assertEqual(len(store), int(data_valid))
                self.assertEqual(result.manual_password_attempt_count, 1)
                self.assertTrue(any("SCAN_LIMIT_REACHED" in step for step in result.steps))
                if not data_valid:
                    self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
                    self.assertIn("password_status=NOT_PENDING", result.error_message)
                    self.assertEqual(result.password_recovery_result, "FAILED")
                    self.assertTrue(all(d.stage == "DATA_EXTRACTION"
                        for d in result.stage_diagnostics[-2:]))
                    self.assertTrue(all(d.status == Status.FAILED
                        for d in result.stage_diagnostics[-2:]))
                self.assertNotIn(SECRET, repr(result))

    def test_failed_candidate_without_scan_cap_does_not_leak_validator_details(self):
        self.host_with(1)
        validator = Mock(return_value=ExtractionResult(False, "private_payload.txt " + SECRET,
            error=SECRET, status=Status.FAILED,
            stage_diagnostics=[ExtractionStageDiagnostic(SECRET, error_type=SECRET,
                normalized_reason=SECRET)]))
        result = self.coordinator(validator).process(self.host)
        self.assertFalse(result.success)
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn("private_payload.txt", repr(result))

    def test_scan_checks_cancellation_even_without_signature_hits(self):
        self.host.write_bytes(b"x" * (4 * 1024**2))
        detector = EmbeddedArchiveDetector()
        cancelled = Mock(side_effect=[False, True, True, True])
        list(detector.iter_candidates(self.host, cancelled=cancelled))
        self.assertEqual(detector.last_diagnostic.reason.value, "CANCELLED")
        self.assertLess(detector.last_diagnostic.scanned_bytes, self.host.stat().st_size)

    def test_existing_output_is_preserved_and_promoted_output_tracked(self):
        from cleanup.runtime_tracker import TaskRunDirectoryTracker, activate_directory_tracker
        self.host_with()
        existing = self.root / "host_extracted"
        existing.mkdir()
        (existing / "keep.txt").write_text("keep")
        tracker = TaskRunDirectoryTracker(self.root)
        with activate_directory_tracker(tracker):
            result = self.coordinator(self.successful).process(self.host)
        self.assertTrue(result.success)
        self.assertEqual((existing / "keep.txt").read_text(), "keep")
        self.assertTrue(tracker.owns(result.extraction_result.output_path))
        self.assertFalse(list(self.root.glob(".gam_candidate_*")))

    def test_embedded_process_timeout_respects_configured_extraction_timeout(self):
        from config.settings import Settings
        coordinator = ExtractionCoordinator(settings=Settings(extraction_timeout_seconds=900))
        self.assertEqual(coordinator.embedded_limits["timeout_seconds"], 900)
        self.assertEqual(coordinator.embedded_limits["process_timeout_seconds"], 900)

    def test_process_timeout_cancellation_and_process_budget(self):
        from extractor.embedded_work import EmbeddedWork, EmbeddedIncomplete
        command = [sys.executable, "-B", "-c", "import time; time.sleep(10)"]
        for kwargs, reason in [({"process_timeout_seconds": 0.05}, "PROCESS_TIMEOUT"),
                               ({"cancelled": lambda: True}, "CANCELLED"),
                               ({"max_processes": 0}, "PROCESS_LIMIT_REACHED")]:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(EmbeddedIncomplete, reason):
                    EmbeddedWork(**kwargs).run(command, self.root)

    def test_source_changed_during_validation_never_accepted(self):
        self.host_with()
        def mutate(plan, password=None):
            self.host.write_bytes(self.host.read_bytes() + b"external change")
            return self.successful(plan)
        result = self.coordinator(mutate).process(self.host)
        self.assertFalse(result.success)
        self.assertIn("SOURCE_CHANGED", result.error_message)

    def test_real_rar_listing_success_but_data_crc_failure_is_rejected(self):
        from extractor.embedded_work import EmbeddedWork
        rar = self.require_rar_fixture_builder()
        payload = self.root / "payload.txt"
        payload.write_bytes(b"stored CRC regression payload" * 20)
        archive = self.root / "real.rar"
        subprocess.run([str(rar), "a", "-ma5", "-m0", "-ep1", str(archive), str(payload)],
                       check=True, capture_output=True, timeout=30)
        valid = archive.read_bytes()
        bad = bytearray(valid)
        bad[bad.index(b"stored CRC regression payload")] ^= 1
        self.host.write_bytes(b"\xff\xd8\xffhost" + bad + valid)
        statuses = []
        original = EmbeddedWork.run
        def run(work, command, *args, **kwargs):
            result = original(work, command, *args, **kwargs)
            statuses.append((command[1], result[0]))
            return result
        with patch.object(EmbeddedWork, "run", run):
            result = ExtractionCoordinator().process(self.host)
        self.assertTrue(result.success, result)
        self.assertEqual(result.extraction_result.embedded_offset, 7 + len(bad))
        self.assertEqual(statuses[0], ("l", 0))
        self.assertEqual(statuses[1][0], "x")
        self.assertNotEqual(statuses[1][1], 0)
        self.assertEqual((result.extraction_result.output_path / "payload.txt").read_bytes(), payload.read_bytes())

    def test_real_embedded_zip_and_7z(self):
        for fmt in ("zip", "7z"):
            with self.subTest(fmt=fmt):
                archive = self.root / f"real.{fmt}"
                if fmt == "zip":
                    with zipfile.ZipFile(archive, "w") as target:
                        target.writestr("payload.txt", "correct content")
                else:
                    payload = self.root / "input.txt"
                    payload.write_text("correct content")
                    subprocess.run([r"C:\Program Files\7-Zip\7z.exe", "a", str(archive), str(payload)],
                                   check=True, capture_output=True, timeout=30)
                self.host.write_bytes(b"\xff\xd8\xffhost" + archive.read_bytes())
                result = ExtractionCoordinator().process(self.host)
                self.assertTrue(result.success, result)
                self.assertEqual(result.extraction_result.embedded_offset, 7)
                self.assertEqual(result.extraction_result.embedded_format, fmt.upper())

    def test_external_process_receives_password_only_on_stdin(self):
        from extractor.embedded_work import EmbeddedWork
        # The helper receives secret data only through stdin. No plaintext
        # password is embedded in a generated script, argv or log.
        script = (
            "import hashlib, sys; "
            "print(hashlib.sha256(sys.stdin.buffer.readline()).hexdigest())"
        )
        command = [sys.executable, "-B", "-c", script]
        self.assertNotIn(SECRET, repr(command))
        code, output = EmbeddedWork().run(command, self.root, SECRET)
        self.assertEqual(code, 0)
        self.assertEqual(output.strip(), hashlib.sha256((SECRET + "\n").encode("utf-8")).hexdigest())
        self.assertNotIn(SECRET, output)

    def test_carve_budget_is_shared_by_later_candidates(self):
        offsets = self.host_with(3)
        size = self.host.stat().st_size
        validator = Mock(return_value=ExtractionResult(False, "bad CRC", status=Status.FAILED))
        coordinator = self.coordinator(validator)
        coordinator.embedded_limits = {"max_carved_bytes": (size - offsets[0]) + (size - offsets[1]) - 1}
        before = self.host.read_bytes()
        result = coordinator.process(self.host)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("CARVE_BUDGET_REACHED", result.error_message)
        self.assertEqual(validator.call_count, 1)
        self.assertEqual(before, self.host.read_bytes())
        self.assertFalse(list(self.root.glob(".gam_candidate_*")))

    def test_cancellation_during_copy_and_external_process(self):
        from extractor.embedded_work import EmbeddedWork, EmbeddedIncomplete
        self.host_with()
        coordinator = self.coordinator(Mock())
        coordinator.embedded_extractor.COPY_CHUNK_SIZE = 4
        checks = [0]
        def cancelled():
            checks[0] += 1
            return checks[0] >= 7
        result = coordinator.process(self.host, cancelled=cancelled)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("CANCELLED", result.error_message)
        self.assertEqual(coordinator.embedded_validator.call_count, 0)
        self.assertFalse(list(self.root.glob(".gam_candidate_*")))
        checks[0] = 0
        def process_cancelled():
            checks[0] += 1
            return checks[0] >= 3
        with self.assertRaisesRegex(EmbeddedIncomplete, "CANCELLED"):
            EmbeddedWork(cancelled=process_cancelled).run(
                [sys.executable, "-B", "-c", "import time; time.sleep(10)"], self.root)

    def test_raw_hits_are_bounded_and_resolver_reports_incomplete(self):
        self.host.write_bytes(b"\xff\xd8\xff" + b"Rar!\x1a\x07\x01\x00" * 4100)
        coordinator = self.coordinator(Mock())
        detector = coordinator.analyzer.embedded_detector
        with patch.object(detector, "validate_candidate", wraps=detector.validate_candidate) as local:
            result = coordinator.process(self.host)
        self.assertEqual(local.call_count, 4096)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("RAW_HIT_LIMIT_REACHED", result.error_message)

    def test_plausible_candidates_are_bounded_globally(self):
        self.host_with(10)
        validator = Mock(return_value=ExtractionResult(False, "bad CRC", status=Status.FAILED))
        result = self.coordinator(validator).process(self.host)
        self.assertEqual(validator.call_count, 8)
        self.assertEqual(result.error_type, "EMBEDDED_INCOMPLETE")
        self.assertIn("CANDIDATE_LIMIT_REACHED", result.error_message)

    def test_empty_manual_submission_does_not_count(self):
        result, callback, store, _ = self.encrypted_run([
            ManualPasswordResponse(Action.INPUT_PASSWORD, ""),
            ManualPasswordResponse(Action.INPUT_PASSWORD, SECRET)])
        self.assertTrue(result.success)
        self.assertEqual(result.manual_password_attempt_count, 1)
        self.assertEqual(callback.call_count, 2)
        self.assertEqual(len(store), 1)


if __name__ == "__main__":
    unittest.main()
