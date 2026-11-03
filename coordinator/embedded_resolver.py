"""Resolve provisional candidates without losing their original host context."""

import shutil
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from analyzer.embedded_detector import EmbeddedDiagnosticReason
from cleanup.runtime_tracker import register_created_directory
from coordinator.models import CoordinatorResult
from execution.output_paths import OutputPathGenerator
from extractor.embedded_work import EmbeddedWork, EmbeddedIncomplete
from extractor.embedded_validator import EmbeddedValidator
from extractor.extractor_models import ExtractionResult, ExtractionStageDiagnostic, ExtractionStatus as Status
from recovery.manual import ManualPasswordAction, ManualPasswordRequest


class EmbeddedResolver:
    def __init__(self, coordinator, plan, passwords, max_attempts, callback, store,
                 steps, cancelled):
        self.owner = coordinator
        self.plan = plan
        self.passwords = passwords
        self.max_attempts = max_attempts
        self.callback = callback
        self.store = store
        self.steps = steps
        self.work = EmbeddedWork(cancelled=cancelled, **coordinator.embedded_limits)
        self.validator = coordinator.embedded_validator or EmbeddedValidator(coordinator, self.work)
        self.automatic = self.manual = 0
        self.unresolved = []
        self.directories = []
        self.diagnostics = []
        # One latest validator status per candidate; detector caps candidates at 8.
        self.candidate_statuses = {}
        self.last = ExtractionResult(False, "no validated embedded candidate", status=Status.FAILED)
        self.control = ""

    def run(self):
        try:
            return self._run()
        except EmbeddedIncomplete as error:
            candidates = ", ".join(
                f"offset={offset}; {status.value}"
                for offset, status in self.candidate_statuses.items()) or "none"
            message = f"embedded search/validation incomplete: {error}; candidates={candidates}"
            self.steps.append(message)
            return CoordinatorResult(False, self.plan.archive_path,
                steps=self.steps, error_message=message,
                failure_stage="EMBEDDED_VALIDATION", error_type="EMBEDDED_INCOMPLETE",
                user_message="内嵌归档搜索或验证未完成",
                password_attempt_count=self.automatic,
                manual_password_attempt_count=self.manual,
                stage_diagnostics=self.diagnostics.copy(),
                password_recovery_result=("ATTEMPTS_EXHAUSTED" if self.manual >= self.owner.MAX_MANUAL_PASSWORD_ATTEMPTS else "UNRESOLVED"),
                control_action="CANCEL_TASK" if str(error) == "CANCELLED" else "")
        finally:
            # These exact directories were minted by this attempt, never inferred
            # from existing output names or from a user-provided path.
            for directory in self.directories:
                if directory.is_dir() and not directory.is_symlink():
                    shutil.rmtree(directory)

    def _run(self):
        detector = self.owner.analyzer.embedded_detector
        self.snapshot = self._identity()
        incomplete = ""
        for candidate in detector.iter_candidates(self.plan.archive_path,
                                                   cancelled=self._scan_check):
            self.work.check()
            directory = Path(tempfile.mkdtemp(prefix=".gam_candidate_",
                                               dir=self.plan.archive_path.parent))
            self.directories.append(directory)
            register_created_directory(directory)
            carve = replace(self.plan, output_path=directory / "carve",
                embedded_offset=candidate.offset, embedded_container_format=candidate.format)
            carved = self.owner.embedded_extractor.extract(carve, work=self.work)
            if self._identity() != self.snapshot:
                raise EmbeddedIncomplete("SOURCE_CHANGED")
            if not carved.success:
                raise EmbeddedIncomplete("CARVE_FAILED")
            archive = next(carved.output_path.iterdir())
            info = self.owner.analyzer.analyze(archive)
            # Do not run unbounded listing in the ordinary inspector. The
            # validator owns bounded, exact-start listing and data extraction.
            plan = self.owner.strategy.create_plan(info)
            if not plan.can_execute:
                self.last = ExtractionResult(False, "candidate safety check rejected", status=Status.FAILED)
                continue
            plan = replace(plan, output_path=directory / "content", fallback_tools=[],
                embedded_offset=candidate.offset, embedded_container_format=candidate.format)
            self.steps.append(f"候选 offset={candidate.offset}, format={candidate.format}: PROVISIONAL")
            result = self._try(plan)
            if result.status is Status.SUCCESS:
                return self._success(plan, result, False)
            for password in self.passwords:
                if result.status not in (Status.PASSWORD_REQUIRED, Status.WRONG_PASSWORD):
                    break
                if self.automatic >= self.max_attempts:
                    break
                if not password.password:
                    continue
                self.automatic += 1
                result = self._try(plan, password.password)
                self.steps.append(f"密码尝试 {self.automatic}: {result.status.value}")
                if result.status is Status.SUCCESS:
                    return self._success(plan, result, False, password.password)
            if result.status in (Status.PASSWORD_REQUIRED, Status.WRONG_PASSWORD):
                self.unresolved.append(plan)
            else:
                shutil.rmtree(directory)
        diagnostic = detector.last_diagnostic
        if diagnostic and diagnostic.reason in (
            EmbeddedDiagnosticReason.SCAN_LIMIT_REACHED,
            EmbeddedDiagnosticReason.RAW_HIT_LIMIT_REACHED,
            EmbeddedDiagnosticReason.CANDIDATE_LIMIT_REACHED,
            EmbeddedDiagnosticReason.CANCELLED,
            EmbeddedDiagnosticReason.VALIDATION_LIMIT_REACHED,
        ):
            incomplete = diagnostic.reason.value
            self.steps.append(f"内嵌扫描: {incomplete}; scanned_bytes={diagnostic.scanned_bytes}; "
                              f"file_size={diagnostic.file_size}")
        while self.unresolved and self.callback and self.manual < self.owner.MAX_MANUAL_PASSWORD_ATTEMPTS:
            self.work.check()
            prompt_started = time.monotonic()
            try:
                response = self.callback(ManualPasswordRequest(self.plan.archive_path,
                    self.unresolved[0].detected_format, self.last.status,
                    self.automatic, self.manual, "EMBEDDED_VALIDATION"))
            except Exception:
                raise EmbeddedIncomplete("MANUAL_CALLBACK_ERROR") from None
            finally:
                # Human decision time does not consume the active-work budget.
                self.work.started += time.monotonic() - prompt_started
            if response.action is ManualPasswordAction.SKIP_ARCHIVE:
                self.control = "SKIP_ARCHIVE"
                break
            if response.action is ManualPasswordAction.CANCEL_TASK:
                self.control = "CANCEL_TASK"
                break
            if response.action is not ManualPasswordAction.INPUT_PASSWORD:
                raise EmbeddedIncomplete("INVALID_MANUAL_ACTION")
            if not response.password:
                continue
            self.manual += 1
            remaining = []
            for plan in self.unresolved:
                result = self._try(plan, response.password)
                self.steps.append(f"人工密码尝试 {self.manual}: offset={plan.embedded_offset}, {result.status.value}")
                if result.status is Status.SUCCESS:
                    return self._success(plan, result, True, response.password)
                if result.status in (Status.PASSWORD_REQUIRED, Status.WRONG_PASSWORD):
                    remaining.append(plan)
            self.unresolved = remaining
        if incomplete and not self.control:
            raise EmbeddedIncomplete(incomplete)
        if self.unresolved and not self.control:
            raise EmbeddedIncomplete("PASSWORD_UNRESOLVED")
        return self.owner._failed_result(self.plan.archive_path, self.last, self.steps,
            manual_password_attempt_count=self.manual, control_action=self.control,
            password_recovery_result=("CANCELLED" if self.control == "CANCEL_TASK" else "SKIPPED" if self.control else "FAILED"))

    def _identity(self):
        stat = self.plan.archive_path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    def _scan_check(self):
        self.work.check()
        return False

    def _try(self, plan, password=None):
        self.work.check(plan.archive_path.parent)
        attempt = replace(plan, output_path=OutputPathGenerator.next_available(plan.output_path))
        try:
            result = self.validator(attempt, password=password)
        except EmbeddedIncomplete:
            raise
        except (OSError, ValueError):
            raise EmbeddedIncomplete("VALIDATOR_ERROR") from None
        self.work.check(plan.archive_path.parent)
        if self._identity() != self.snapshot:
            raise EmbeddedIncomplete("SOURCE_CHANGED")
        if result.status is Status.SUCCESS:
            safety = self.owner.extraction_safety_checker.check(result.output_path)
            if not safety.safe:
                result = ExtractionResult(False, "candidate output safety rejected", status=Status.FAILED)
        if result.status is not Status.SUCCESS and attempt.output_path.is_dir():
            # Retain only the carve for manual recovery, not partial plaintext
            # from each rejected password/data pass.
            if not attempt.output_path.is_symlink():
                shutil.rmtree(attempt.output_path)
        self.diagnostics.append(ExtractionStageDiagnostic(
            stage="EMBEDDED_VALIDATION", detected_format=plan.detected_format,
            tool=result.tool_used, status=result.status,
            normalized_reason=f"offset={plan.embedded_offset}; {result.status.value}"))
        result = replace(result, embedded_host=self.plan.archive_path,
            embedded_offset=plan.embedded_offset, embedded_format=plan.detected_format,
            embedded_validation_state=("DATA_VALIDATED" if result.status is Status.SUCCESS else result.status.value),
            stage_diagnostics=self.diagnostics.copy())
        self.last = result
        self.candidate_statuses[plan.embedded_offset] = result.status
        self.steps.append(f"候选 offset={plan.embedded_offset}, format={plan.detected_format}: {result.status.value}")
        return result

    def _success(self, plan, result, manual, password=None):
        self.work.check()
        if self._identity() != self.snapshot:
            raise EmbeddedIncomplete("SOURCE_CHANGED")
        output = OutputPathGenerator.next_available(self.plan.output_path)
        # mkdir is exclusive: never merge with or overwrite an existing output.
        output.mkdir(exist_ok=False)
        register_created_directory(output)
        try:
            for child in result.output_path.iterdir():
                self.work.check()
                shutil.move(str(child), str(output / child.name))
        except (OSError, EmbeddedIncomplete):
            # Retain remaining validated content if promotion is interrupted.
            directory = next(d for d in self.directories if d in result.output_path.parents)
            self.directories.remove(directory)
            raise EmbeddedIncomplete("PROMOTION_INCOMPLETE") from None
        result = replace(result, output_path=output,
            embedded_host=self.plan.archive_path, embedded_offset=plan.embedded_offset,
            embedded_format=plan.detected_format, embedded_validation_state="DATA_VALIDATED")
        self.steps.append(f"候选 offset={plan.embedded_offset}, format={plan.detected_format}: DATA_VALIDATED")
        final = self.owner._validate_success_result(self.plan.archive_path, result, self.steps,
            manual_password_attempt_count=self.manual, manual_password_used=manual,
            password_recovery_result="SUCCESS" if manual else "")
        if final.success and password and self.store is not None:
            self.store.add_verified(password)
        return final
