"""GameArchiveManager 基础集成测试。"""

import json
import subprocess
import tempfile
import unittest
import warnings
import zipfile
import zlib
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from analyzer.archive_analyzer import ArchiveAnalyzer
from analyzer.embedded_detector import (
    EmbeddedArchiveDetector,
    EmbeddedDiagnosticReason,
    EmbeddedValidationResult,
)
from application.app_service import GameArchiveService
from application.progress import BatchProgressEvent
from cleanup.cleanup_manager import CleanupManager
from config.config_loader import ConfigLoader
from config.settings import Settings
from coordinator.extraction_coordinator import ExtractionCoordinator
from coordinator.models import CoordinatorResult
from execution.models import ExtractionPlan
from execution.strategy import ExecutionStrategy
from extractor.dispatcher import ExtractorDispatcher
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from extractor.lz4 import Lz4Extractor
from extractor.seven_zip import SevenZipExtractor
from extractor.winrar import WinRarExtractor
from history.storage import HistoryStorage
from logging_system.logger import GameLogger
from organizer.output_organizer import OutputOrganizer
from password.models import PasswordCandidate, PasswordSource
from pipeline.extraction_runner import ExtractionPipelineRunner
from pipeline.extraction_pipeline import ExtractionPipeline
from pipeline.models import (
    ArchiveExecutionRecord,
    ArchiveTaskItem,
    ArchiveTaskStatus,
    PipelineResult,
    PipelineProgress,
    SkippedArchiveRecord,
)
from recovery.password_executor import PasswordRetryExecutor
from recovery.password_recovery import PasswordRecoveryEngine
from report.models import BatchTaskReport, FailureDetail, TaskReport
from report.task_report import ReportGenerator
from rules.platform_filter import PlatformFilter
from scanner.archive_finder import ArchiveFinder
from security.archive_content_inspector import ArchiveContentInspector
from security.archive_safety import ArchiveSafetyChecker
from security.extraction_safety import ExtractionSafetyChecker
from task.models import Task, TaskStatus
from task.task_analyzer import TaskAnalyzer
from task.task_executor import (
    SkippedArchiveResult,
    TaskExecutionResult,
    TaskExecutor,
)
from tools.models import ToolName
from tools.tool_manager import ToolManager


def create_zip(archive_path: Path, file_name: str, content: str) -> None:
    """使用标准库创建测试 ZIP。"""
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(file_name, content)


def create_rar5_encryption_header(*, valid_crc: bool = True) -> bytes:
    """Create a minimal structurally valid RAR5 archive-encryption header."""
    header_data = b"\x04\x00\x00\x01\x0f" + (b"\x11" * 16) + (b"\x22" * 12)
    size_bytes = bytes([len(header_data)])
    crc = zlib.crc32(size_bytes + header_data) & 0xFFFFFFFF
    if not valid_crc:
        crc ^= 0xFFFFFFFF
    return (
        b"Rar!\x1a\x07\x01\x00"
        + crc.to_bytes(4, "little")
        + size_bytes
        + header_data
    )


class FakePasswordExtractor:
    """模拟需要密码、密码错误和成功三种结果。"""

    def __init__(self, correct_password: str) -> None:
        self.correct_password = correct_password

    def extract(
        self, plan: ExtractionPlan, password: str | None = None
    ) -> ExtractionResult:
        if password is None:
            return ExtractionResult(
                success=False,
                message="需要密码",
                output_path=plan.output_path,
                status=ExtractionStatus.PASSWORD_REQUIRED,
            )
        if password != self.correct_password:
            return ExtractionResult(
                success=False,
                message="密码错误",
                output_path=plan.output_path,
                status=ExtractionStatus.WRONG_PASSWORD,
            )
        return ExtractionResult(
            success=True,
            message="解压成功",
            output_path=plan.output_path,
            tool_used=ToolName.SEVEN_ZIP,
            status=ExtractionStatus.SUCCESS,
        )


class FakeRecursiveCoordinator:
    """模拟首次解压产生一个新 ZIP，供真实 ArchiveFinder 发现。"""

    def __init__(self, root_archive: Path) -> None:
        self.root_archive = root_archive.resolve()

    def process(
        self,
        archive_path: str | Path,
        password_candidates=None,
        max_password_attempts: int = 20,
    ) -> CoordinatorResult:
        archive = Path(archive_path).resolve()
        output_path = archive.parent / f"{archive.stem}_extracted"
        output_path.mkdir()

        if archive == self.root_archive:
            android_dir = output_path / "Android"
            normal_dir = output_path / "normal"
            chinese_dir = output_path / "安卓资源"
            android_dir.mkdir()
            normal_dir.mkdir()
            chinese_dir.mkdir()
            create_zip(normal_dir / "nested.zip", "payload.txt", "nested")
            create_zip(
                android_dir / "data.zip", "android.txt", "ignored"
            )
            create_zip(output_path / "AZ_patch.zip", "az.txt", "ignored")
            create_zip(chinese_dir / "update.rar", "mobile.txt", "ignored")

        extraction_result = ExtractionResult(
            success=True,
            message="测试解压成功",
            output_path=output_path,
            tool_used=ToolName.SEVEN_ZIP,
            status=ExtractionStatus.SUCCESS,
        )
        return CoordinatorResult(
            success=True,
            archive_path=archive,
            extraction_result=extraction_result,
            steps=["测试协调流程完成"],
        )


class FullWorkflowExtractor:
    """模拟外部工具，保留完整业务编排和密码恢复流程。"""

    def __init__(self) -> None:
        self.password_attempt_count = 0
        self.password_recovery_succeeded = False

    def extract(
        self, plan: ExtractionPlan, password: str | None = None
    ) -> ExtractionResult:
        archive_name = plan.archive_path.name.casefold()

        if archive_name == "data.rar":
            if password is None:
                return ExtractionResult(
                    success=False,
                    message="压缩包需要密码",
                    output_path=plan.output_path,
                    tool_used=ToolName.SEVEN_ZIP,
                    status=ExtractionStatus.PASSWORD_REQUIRED,
                )

            self.password_attempt_count += 1
            if password != "123456":
                return ExtractionResult(
                    success=False,
                    message="密码错误",
                    output_path=plan.output_path,
                    tool_used=ToolName.SEVEN_ZIP,
                    status=ExtractionStatus.WRONG_PASSWORD,
                )
            self.password_recovery_succeeded = True

        if plan.output_path is None:
            return ExtractionResult(
                success=False,
                message="缺少输出目录",
                status=ExtractionStatus.FAILED,
            )

        plan.output_path.mkdir(parents=True, exist_ok=False)
        if archive_name == "game.zip":
            # 测试数据受控，使用标准库展开真正位于 ZIP 内的嵌套文件。
            with zipfile.ZipFile(plan.archive_path, "r") as archive:
                archive.extractall(plan.output_path)
        elif archive_name == "data.rar":
            # A successful terminal extraction must contain user content.
            (plan.output_path / "payload.txt").write_text(
                "recovered", encoding="utf-8"
            )

        return ExtractionResult(
            success=True,
            message="测试解压成功",
            output_path=plan.output_path,
            tool_used=ToolName.SEVEN_ZIP,
            status=ExtractionStatus.SUCCESS,
        )


class RecordingTaskExecutor(TaskExecutor):
    """记录服务传入的 Task，执行逻辑仍使用真实 TaskExecutor。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.last_task: Task | None = None
        self.last_result: TaskExecutionResult | None = None

    def execute(
        self, task: Task, max_password_attempts: int | None = None
    ) -> TaskExecutionResult:
        self.last_task = task
        self.last_result = super().execute(task, max_password_attempts)
        return self.last_result


class GameArchiveIntegrationTests(unittest.TestCase):
    """验证主要模块之间的基础连接。"""

    def test_archive_analyzer_detects_disguised_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_movie = Path(temp_dir) / "movie.mp4"
            create_zip(fake_movie, "game.txt", "content")

            info = ArchiveAnalyzer().analyze(fake_movie)

            self.assertEqual(info.extension, ".mp4")
            self.assertEqual(info.real_format, "ZIP")
            self.assertTrue(info.is_fake_extension)
            self.assertEqual(info.confidence, 1.0)

    def test_dll_with_random_pk_bytes_is_not_an_embedded_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dll_path = root / "game.dll"
            dll_path.write_bytes(b"MZ\x00\x00runtime-data-PK\x03\x04-not-a-zip")

            info = ArchiveAnalyzer().analyze(dll_path)
            discovered = ArchiveFinder().find(root)

            self.assertEqual(info.real_format, "UNKNOWN")
            self.assertFalse(info.is_embedded_archive)
            self.assertEqual(
                info.embedded_validation_reason,
                EmbeddedDiagnosticReason.HOST_TYPE_DISABLED.value,
            )
            self.assertEqual(discovered, [])

    def test_invalid_embedded_zip_marker_fails_structure_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image = Path(temp_dir) / "cover.jpg"
            image.write_bytes(b"\xff\xd8\xff\xe0image-PK\x03\x04-random-data")

            info = ArchiveAnalyzer().analyze(image)

            self.assertEqual(info.real_format, "UNKNOWN")
            self.assertFalse(info.is_embedded_archive)

            candidates = EmbeddedArchiveDetector().find_candidates(image)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].host_file, image.resolve())
            self.assertEqual(candidates[0].format, "ZIP")
            self.assertEqual(candidates[0].confidence, 0.0)
            self.assertIs(
                candidates[0].validation_result,
                EmbeddedValidationResult.INVALID_STRUCTURE,
            )

    def test_verified_embedded_zip_candidate_can_enter_archive_finder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "payload.zip"
            create_zip(archive, "payload.txt", "safe")
            host = root / "cover.jpg"
            host.write_bytes(b"\xff\xd8\xff\xe0host\xff\xd9" + archive.read_bytes())

            candidates = EmbeddedArchiveDetector().find_candidates(host)
            discovered = ArchiveFinder().find(root)

            valid_candidates = [
                item
                for item in candidates
                if item.validation_result is EmbeddedValidationResult.VALID
            ]
            self.assertEqual(len(valid_candidates), 1)
            self.assertEqual(valid_candidates[0].confidence, 1.0)
            self.assertIn(host.resolve(), [item.file_path for item in discovered])

    def test_large_host_finds_early_encrypted_rar_with_bounded_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            host = Path(temp_dir) / "large.jpg"
            rar_header = create_rar5_encryption_header()
            host.write_bytes(
                b"\xff\xd8\xff\xe0host" + rar_header + (b"x" * 256)
            )
            detector = EmbeddedArchiveDetector(max_scan_bytes=128)

            candidate = detector.detect(host)

            self.assertGreater(host.stat().st_size, detector.max_scan_bytes)
            self.assertIsNotNone(candidate)
            self.assertLess(candidate.offset, detector.max_scan_bytes)
            self.assertIs(
                candidate.validation_result,
                EmbeddedValidationResult.VALID_ENCRYPTED,
            )
            self.assertIs(
                detector.last_diagnostic.reason,
                EmbeddedDiagnosticReason.VALID_ENCRYPTED,
            )

    def test_candidate_beyond_scan_limit_is_not_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            host = Path(temp_dir) / "bounded.jpg"
            host.write_bytes(
                b"\xff\xd8\xff\xe0" + (b"x" * 128)
                + create_rar5_encryption_header()
            )
            detector = EmbeddedArchiveDetector(max_scan_bytes=64)

            candidate = detector.detect(host)

            self.assertIsNone(candidate)
            self.assertIs(
                detector.last_diagnostic.reason,
                EmbeddedDiagnosticReason.SCAN_LIMIT_REACHED,
            )
            self.assertEqual(detector.last_diagnostic.scanned_bytes, 64)

    def test_rar5_encryption_header_with_valid_crc_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            host = Path(temp_dir) / "encrypted.jpg"
            prefix = b"\xff\xd8\xff\xe0image"
            host.write_bytes(prefix + create_rar5_encryption_header())

            candidate = EmbeddedArchiveDetector().detect(host)

            self.assertIsNotNone(candidate)
            self.assertEqual(candidate.offset, len(prefix))
            self.assertIs(
                candidate.validation_result,
                EmbeddedValidationResult.VALID_ENCRYPTED,
            )

    def test_forged_rar5_encryption_headers_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bad_crc = root / "bad_crc.jpg"
            bad_crc.write_bytes(
                b"\xff\xd8\xff\xe0" + create_rar5_encryption_header(valid_crc=False)
            )

            malformed_data = b"\x04\x00\x00\x01"
            size_bytes = bytes([len(malformed_data)])
            crc = zlib.crc32(size_bytes + malformed_data) & 0xFFFFFFFF
            malformed = root / "malformed.jpg"
            malformed.write_bytes(
                b"\xff\xd8\xff\xe0"
                + b"Rar!\x1a\x07\x01\x00"
                + crc.to_bytes(4, "little")
                + size_bytes
                + malformed_data
            )

            bad_crc_candidates = EmbeddedArchiveDetector().find_candidates(
                bad_crc
            )
            malformed_candidates = EmbeddedArchiveDetector().find_candidates(
                malformed
            )

            self.assertEqual(
                bad_crc_candidates[0].reason,
                EmbeddedDiagnosticReason.INVALID_CRC,
            )
            self.assertEqual(
                malformed_candidates[0].reason,
                EmbeddedDiagnosticReason.INVALID_STRUCTURE,
            )
            self.assertTrue(
                all(
                    item.validation_result
                    is EmbeddedValidationResult.INVALID_STRUCTURE
                    for item in bad_crc_candidates + malformed_candidates
                )
            )

    def test_pipeline_guard_limits_embedded_candidate_growth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pipeline = ExtractionPipeline(
                settings=Settings(
                    max_recursive_depth=5,
                    max_archive_tasks=10,
                    max_embedded_candidates=1,
                )
            )
            pipeline.add_task(root / "root.zip", is_initial=True)
            first = pipeline.add_task(
                root / "first.jpg",
                depth=1,
                is_embedded_archive=True,
            )
            second = pipeline.add_task(
                root / "second.jpg",
                depth=1,
                is_embedded_archive=True,
            )

            self.assertIsNotNone(first)
            self.assertIsNone(second)
            self.assertEqual(len(pipeline.guard_errors), 1)
            self.assertEqual(
                pipeline.guard_errors[0].error_type.value,
                "MAX_EMBEDDED_CANDIDATES",
            )

    def test_task_analyzer_excludes_existing_final_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_archive = root / "game.zip"
            create_zip(source_archive, "source.txt", "source")
            final_root = root / "GameArchive_Output"
            final_root.mkdir()
            old_archive = final_root / "old.zip"
            create_zip(old_archive, "old.txt", "old")

            result = TaskAnalyzer().analyze(Task(task_path=root))

            self.assertEqual(
                [info.file_path for info in result.archive_results],
                [source_archive.resolve()],
            )

    def test_archive_finder_detects_lz4_rar_container_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            compound_archive = root / "PC.rar.lz4"
            compound_archive.write_bytes(
                b"\x04\x22\x4d\x18"
                + b"\x00" * 32
                + b"\x52\x61\x72\x21"
                + b"simulated-data"
            )

            archives = ArchiveFinder().find(root)

            self.assertEqual(len(archives), 1)
            archive_info = archives[0]
            self.assertEqual(archive_info.file_path, compound_archive.resolve())
            self.assertEqual(archive_info.real_format, "LZ4")
            self.assertEqual(archive_info.extension, ".lz4")
            self.assertEqual(archive_info.container_chain, ["LZ4", "RAR"])

    def test_complete_7z_volumes_create_one_task_and_use_first_volume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_volume = root / "PC14191.7z.001"
            second_volume = root / "PC14191.7z.002"
            first_volume.write_bytes(b"7z\xbc\xaf\x27\x1cfirst-volume")
            second_volume.write_bytes(b"second-volume")

            archives = ArchiveFinder().find(root)

            self.assertEqual(len(archives), 1)
            info = archives[0]
            self.assertEqual(info.file_path, first_volume.resolve())
            self.assertTrue(info.is_multi_volume)
            self.assertEqual(
                info.volume_files,
                [first_volume.resolve(), second_volume.resolve()],
            )
            self.assertEqual(info.missing_volume_files, [])

            seven_zip = Mock()

            def successful_extract(plan, password=None):
                plan.output_path.mkdir(parents=True, exist_ok=False)
                (plan.output_path / "game.exe").write_bytes(b"game")
                return ExtractionResult(
                    success=True,
                    message="split archive success",
                    output_path=plan.output_path,
                    tool_used=ToolName.SEVEN_ZIP,
                    status=ExtractionStatus.SUCCESS,
                )

            seven_zip.extract.side_effect = successful_extract
            coordinator = ExtractionCoordinator(
                dispatcher=ExtractorDispatcher(
                    seven_zip_extractor=seven_zip,
                    winrar_extractor=Mock(),
                    lz4_extractor=Mock(),
                )
            )

            result = coordinator.process(info.file_path)

            self.assertTrue(result.success, result.error_message)
            seven_zip.extract.assert_called_once()
            plan = seven_zip.extract.call_args.args[0]
            self.assertEqual(plan.archive_path, first_volume.resolve())
            self.assertTrue(plan.is_multi_volume)
            self.assertEqual(len(plan.volume_files), 2)

    def test_missing_first_7z_volume_returns_volume_failure_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            second_volume = root / "game.7z.002"
            second_volume.write_bytes(b"second-volume")

            archives = ArchiveFinder().find(root)

            self.assertEqual(len(archives), 1)
            info = archives[0]
            missing_first = (root / "game.7z.001").resolve()
            self.assertEqual(info.file_path, missing_first)
            self.assertEqual(info.missing_volume_files, [missing_first])

            coordinator_result = ExtractionCoordinator().process(
                info.file_path
            )
            self.assertFalse(coordinator_result.success)
            self.assertEqual(
                coordinator_result.extraction_result.message,
                "缺少分卷文件",
            )
            self.assertEqual(
                coordinator_result.failure_stage, "VOLUME_DETECTION"
            )
            self.assertEqual(coordinator_result.missing_files, [missing_first])

            report = ReportGenerator().generate(
                TaskExecutionResult(
                    task_id="missing-first-volume",
                    task_path=root,
                    success=False,
                    coordinator_results=[coordinator_result],
                )
            )
            detail = report.failure_details[0]
            self.assertEqual(detail.stage, "VOLUME_DETECTION")
            self.assertEqual(detail.missing_files, [missing_first])
            self.assertIn("缺少分卷文件", detail.reason)

    def test_missing_second_7z_volume_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_volume = root / "game.7z.001"
            third_volume = root / "game.7z.003"
            first_volume.write_bytes(b"7z\xbc\xaf\x27\x1cfirst-volume")
            third_volume.write_bytes(b"third-volume")

            archives = ArchiveFinder().find(root)

            self.assertEqual(len(archives), 1)
            missing_second = (root / "game.7z.002").resolve()
            self.assertEqual(
                archives[0].missing_volume_files, [missing_second]
            )
            plan = ExecutionStrategy().create_plan(archives[0])
            self.assertFalse(plan.can_execute)
            self.assertEqual(plan.archive_path, first_volume.resolve())
            self.assertEqual(plan.missing_volume_files, [missing_second])
            self.assertIn("缺少分卷文件", plan.message)

    def test_missing_second_part01_rar_does_not_reach_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_volume = root / "sample.part01.rar"
            first_volume.write_bytes(b"Rar!\x1a\x07\x00first-volume")
            missing_second = (root / "sample.part02.rar").resolve()

            archives = ArchiveFinder().find(root)

            self.assertEqual(len(archives), 1)
            info = archives[0]
            self.assertTrue(info.is_multi_volume)
            self.assertEqual(info.file_path, first_volume.resolve())
            self.assertEqual(info.missing_volume_files, [missing_second])

            plan = ExecutionStrategy().create_plan(info)
            self.assertFalse(plan.can_execute)
            self.assertEqual(plan.missing_volume_files, [missing_second])
            self.assertIn("缺少分卷文件", plan.message)

            winrar = Mock()
            seven_zip = Mock()
            coordinator = ExtractionCoordinator(
                dispatcher=ExtractorDispatcher(
                    seven_zip_extractor=seven_zip,
                    winrar_extractor=winrar,
                    lz4_extractor=Mock(),
                )
            )
            result = coordinator.process(info.file_path)
            self.assertFalse(result.success)
            self.assertEqual(result.failure_stage, "VOLUME_DETECTION")
            self.assertEqual(result.missing_files, [missing_second])
            seven_zip.extract.assert_not_called()
            winrar.extract.assert_not_called()
            self.assertFalse((root / "sample.part01.rar_extracted").exists())

    def test_missing_second_part1_rar_uses_matching_width(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_volume = root / "game.part1.rar"
            first_volume.write_bytes(b"Rar!\x1a\x07\x00first-volume")

            archives = ArchiveFinder().find(root)

            self.assertEqual(len(archives), 1)
            missing_second = (root / "game.part2.rar").resolve()
            self.assertEqual(
                archives[0].missing_volume_files, [missing_second]
            )
            plan = ExecutionStrategy().create_plan(archives[0])
            self.assertFalse(plan.can_execute)

    def test_complete_part01_rar_volumes_stay_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_volume = root / "sample.part01.rar"
            second_volume = root / "sample.part02.rar"
            first_volume.write_bytes(b"Rar!\x1a\x07\x00first-volume")
            second_volume.write_bytes(b"continuation")

            archives = ArchiveFinder().find(root)

            self.assertEqual(len(archives), 1)
            info = archives[0]
            self.assertEqual(
                info.volume_files,
                [first_volume.resolve(), second_volume.resolve()],
            )
            self.assertEqual(info.missing_volume_files, [])
            plan = ExecutionStrategy().create_plan(info)
            self.assertTrue(plan.can_execute)

    def test_archive_finder_groups_supported_rar_volume_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            groups = [
                ("legacy.rar", "legacy.r00"),
                ("one.part1.rar", "one.part2.rar"),
                ("two.part01.rar", "two.part02.rar"),
                ("zip.zip.001", "zip.zip.002"),
            ]
            for first_name, second_name in groups:
                first = root / first_name
                second = root / second_name
                if first_name.endswith(".zip.001"):
                    first.write_bytes(b"PK\x03\x04first")
                else:
                    first.write_bytes(b"Rar!\x1a\x07\x00first")
                second.write_bytes(b"continuation")

            archives = ArchiveFinder().find(root)

            self.assertEqual(len(archives), 4)
            self.assertTrue(all(info.is_multi_volume for info in archives))
            self.assertTrue(
                all(len(info.volume_files) == 2 for info in archives)
            )
            self.assertTrue(
                all(not info.missing_volume_files for info in archives)
            )

    def test_application_version_information_is_readable(self) -> None:
        from version import APP_NAME, APP_VERSION, BUILD_TYPE

        self.assertEqual(APP_NAME, "GameArchiveManager")
        self.assertEqual(APP_VERSION, "0.1.0")
        self.assertEqual(BUILD_TYPE, "Release Candidate")

    def test_main_confirmation_executes_application_service(self) -> None:
        import main as main_module

        task_path = str(Path.cwd())
        normal_archive = Mock(file_path=Path(task_path) / "game.zip")
        ignored_archive = Mock(
            file_path=Path(task_path) / "Android_game.zip"
        )
        analysis_result = Mock(
            analysis_status=main_module.AnalysisStatus.COMPLETED,
            error_message="",
            task_path=Path(task_path),
            archive_results=[normal_archive, ignored_archive],
            ignored_items=[ignored_archive.file_path],
        )
        fake_analyzer = Mock()
        fake_analyzer.analyze.return_value = analysis_result
        fake_report = TaskReport(
            task_path=Path(task_path),
            total_archives=3,
            success_count=2,
            failed_count=0,
            skipped_count=1,
            password_attempt_count=1,
            execution_time=0.5,
            output_paths=[Path(task_path) / "game_extracted"],
            summary="测试报告生成成功",
        )
        fake_service = Mock()
        fake_service.task_executor.task_analyzer = fake_analyzer
        fake_service.task_executor.input_relationship_resolver.resolve.return_value = Mock(
            relationships=[]
        )
        fake_service.execute_task.return_value = fake_report
        service_factory = Mock(return_value=fake_service)

        with (
            patch.object(
                main_module,
                "GameArchiveService",
                service_factory,
            ),
            patch(
                "builtins.input",
                side_effect=["1", task_path, "", "Y", "", "0"],
            ),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            main_module.main()

        service_factory.assert_called_once_with()
        fake_service.execute_task.assert_called_once_with(
            task_path,
            progress_callback=main_module.print_pipeline_progress,
        )
        output = stdout.getvalue()
        self.assertIn("GameArchiveManager", output)
        self.assertIn("版本: 0.1.0", output)
        self.assertIn("7-Zip:", output)
        self.assertIn("WinRAR:", output)
        self.assertIn("LZ4:", output)
        self.assertIn("GameArchiveManager 启动成功", output)
        self.assertIn(f"任务: {task_path}", output)
        self.assertIn("发现压缩包: 2", output)
        self.assertIn("跳过: 1", output)
        self.assertIn("即将开始解压", output)
        self.assertIn("任务状态: COMPLETED", output)
        self.assertIn("成功数量: 2", output)
        self.assertIn("失败数量: 0", output)
        self.assertIn("跳过数量: 1", output)
        self.assertIn("game_extracted", output)
        self.assertIn("测试报告生成成功", output)

    def test_main_cancellation_does_not_execute_task(self) -> None:
        import main as main_module

        task_path = str(Path.cwd())
        analysis_result = Mock(
            analysis_status=main_module.AnalysisStatus.COMPLETED,
            error_message="",
            task_path=Path(task_path),
            archive_results=[
                Mock(file_path=Path(task_path) / "game.zip")
            ],
            ignored_items=[],
        )
        fake_analyzer = Mock()
        fake_analyzer.analyze.return_value = analysis_result
        fake_service = Mock()
        fake_service.task_executor.task_analyzer = fake_analyzer
        fake_service.task_executor.input_relationship_resolver.resolve.return_value = Mock(
            relationships=[]
        )
        service_factory = Mock(return_value=fake_service)

        with (
            patch.object(
                main_module,
                "GameArchiveService",
                service_factory,
            ),
            patch(
                "builtins.input",
                side_effect=["1", task_path, "", "N", "", "0"],
            ),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            main_module.main()

        service_factory.assert_called_once_with()
        fake_service.execute_task.assert_not_called()
        output = stdout.getvalue()
        self.assertIn("发现压缩包: 1", output)
        self.assertIn("跳过: 0", output)
        self.assertIn("任务已取消，未执行解压", output)

    def test_main_executes_two_tasks_after_one_confirmation(self) -> None:
        import main as main_module

        task_paths = [str(Path.cwd()), str(Path.cwd() / "docs")]
        analyses = [
            Mock(
                analysis_status=main_module.AnalysisStatus.COMPLETED,
                error_message="",
                task_path=Path(task_path),
                archive_results=[
                    Mock(file_path=Path(task_path) / "game.zip")
                ],
                ignored_items=[],
            )
            for task_path in task_paths
        ]
        analyzer = Mock()
        analyzer.analyze.side_effect = analyses
        task_reports = [
            TaskReport(
                task_path=Path(task_path),
                total_archives=1,
                success_count=1,
                failed_count=0,
                skipped_count=0,
                password_attempt_count=0,
                execution_time=0.1,
                output_paths=[Path(task_path) / "GameArchive_Output"],
                summary="success",
            )
            for task_path in task_paths
        ]
        batch_report = BatchTaskReport(
            task_reports=task_reports,
            success_count=2,
            failed_count=0,
            skipped_count=0,
            output_paths=[
                output_path
                for report in task_reports
                for output_path in report.output_paths
            ],
        )
        service = Mock()

        def execute_tasks(paths, progress_callback=None):
            progress_callback(
                BatchProgressEvent(
                    event_type="TASK_STARTED",
                    current_task=1,
                    total_tasks=2,
                    task_path=Path(paths[0]),
                    status="RUNNING",
                )
            )
            progress_callback(
                BatchProgressEvent(
                    event_type="PIPELINE_PROGRESS",
                    current_task=1,
                    total_tasks=2,
                    task_path=Path(paths[0]),
                    status="RUNNING",
                    archive_count=3,
                    completed_count=2,
                    failed_count=1,
                )
            )
            progress_callback(
                BatchProgressEvent(
                    event_type="TASK_FINISHED",
                    current_task=1,
                    total_tasks=2,
                    task_path=Path(paths[0]),
                    status="COMPLETED",
                )
            )
            return batch_report

        service.execute_tasks.side_effect = execute_tasks
        service.task_executor.task_analyzer = analyzer
        service.task_executor.input_relationship_resolver.resolve.return_value = Mock(
            relationships=[]
        )
        service_factory = Mock(return_value=service)

        with (
            patch.object(main_module, "GameArchiveService", service_factory),
            patch(
                "builtins.input",
                side_effect=["1", *task_paths, "", "Y", "", "0"],
            ),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            main_module.main()

        service_factory.assert_called_once_with()
        service.execute_tasks.assert_called_once()
        call = service.execute_tasks.call_args
        self.assertEqual(call.args[0], task_paths)
        self.assertTrue(callable(call.kwargs["progress_callback"]))
        self.assertEqual(analyzer.analyze.call_count, 2)
        output = stdout.getvalue()
        self.assertIn("任务 1", output)
        self.assertIn("任务 2", output)
        self.assertIn("批量任务汇总", output)
        self.assertIn("成功数量: 2", output)
        self.assertIn("当前任务: 1/2", output)
        self.assertIn(f"当前任务路径: {task_paths[0]}", output)
        self.assertIn("当前处理压缩包数量: 3", output)
        self.assertIn("已完成数量: 2", output)
        self.assertIn("失败数量: 1", output)
        self.assertIn("当前任务完成状态: COMPLETED", output)

    def test_application_service_batch_keeps_success_and_failure_reports(self) -> None:
        task_paths = [Path(r"C:\Test\Good"), Path(r"C:\Test\Failed")]
        reports = [
            TaskReport(
                task_path=task_paths[0],
                total_archives=1,
                success_count=1,
                failed_count=0,
                skipped_count=0,
                password_attempt_count=0,
                execution_time=0.1,
                output_paths=[task_paths[0] / "GameArchive_Output"],
                summary="success",
            ),
            TaskReport(
                task_path=task_paths[1],
                total_archives=1,
                success_count=0,
                failed_count=1,
                skipped_count=1,
                password_attempt_count=0,
                execution_time=0.1,
                summary="failed",
            ),
        ]
        service = GameArchiveService(task_executor=Mock())

        with patch.object(
            service,
            "execute_task",
            side_effect=reports,
        ) as execute_task:
            batch_report = service.execute_tasks(task_paths)

        self.assertEqual(execute_task.call_count, 2)
        self.assertEqual(batch_report.task_reports, reports)
        self.assertEqual(batch_report.success_count, 1)
        self.assertEqual(batch_report.failed_count, 1)
        self.assertEqual(batch_report.skipped_count, 1)
        self.assertEqual(
            batch_report.output_paths,
            [task_paths[0] / "GameArchive_Output"],
        )

    def test_application_service_emits_multi_task_progress(self) -> None:
        task_paths = [Path(r"C:\Test\One"), Path(r"C:\Test\Two")]
        reports = [
            TaskReport(
                task_path=task_paths[0],
                total_archives=2,
                success_count=2,
                failed_count=0,
                skipped_count=0,
                password_attempt_count=0,
                execution_time=0.1,
            ),
            TaskReport(
                task_path=task_paths[1],
                total_archives=2,
                success_count=1,
                failed_count=1,
                skipped_count=0,
                password_attempt_count=0,
                execution_time=0.1,
            ),
        ]
        service = GameArchiveService(task_executor=Mock())
        events: list[BatchProgressEvent] = []

        def execute_task(path, progress_callback=None):
            index = task_paths.index(path)
            progress_callback(
                PipelineProgress(
                    archive_count=2,
                    completed_count=1,
                    failed_count=index,
                )
            )
            return reports[index]

        with patch.object(service, "execute_task", side_effect=execute_task):
            batch_report = service.execute_tasks(
                task_paths,
                progress_callback=events.append,
            )

        self.assertEqual(batch_report.task_reports, reports)
        self.assertEqual(
            [event.event_type for event in events],
            [
                "TASK_STARTED",
                "PIPELINE_PROGRESS",
                "TASK_FINISHED",
                "TASK_STARTED",
                "PIPELINE_PROGRESS",
                "TASK_FINISHED",
            ],
        )
        self.assertEqual(events[1].archive_count, 2)
        self.assertEqual(events[1].completed_count, 1)
        self.assertEqual(events[4].failed_count, 1)
        self.assertEqual(events[2].status, "COMPLETED")
        self.assertEqual(events[5].status, "FAILED")

    def test_batch_failure_still_emits_finished_status(self) -> None:
        task_path = Path(r"C:\Test\Broken")
        service = GameArchiveService(task_executor=Mock())
        events: list[BatchProgressEvent] = []

        with patch.object(
            service,
            "execute_task",
            side_effect=RuntimeError("controlled failure"),
        ):
            report = service.execute_tasks(
                [task_path],
                progress_callback=events.append,
            )

        self.assertEqual(report.failed_count, 1)
        self.assertEqual(events[0].event_type, "TASK_STARTED")
        self.assertEqual(events[-1].event_type, "TASK_FINISHED")
        self.assertEqual(events[-1].status, "FAILED")

    def test_single_task_execution_does_not_require_progress_callback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_executor = Mock()

            def execute(task, max_password_attempts=None):
                task.status = TaskStatus.COMPLETED
                return TaskExecutionResult(
                    task_id=task.task_id,
                    task_path=task.task_path,
                    success=True,
                )

            task_executor.execute.side_effect = execute
            service = GameArchiveService(
                task_executor=task_executor,
                history_storage=HistoryStorage(root / "history.json"),
                log_directory=root / "logs",
            )

            report = service.execute_task(root)

            self.assertEqual(report.failed_count, 0)
            call = task_executor.execute.call_args
            self.assertNotIn("progress_callback", call.kwargs)

    def test_main_batch_cancellation_does_not_execute_tasks(self) -> None:
        import main as main_module

        task_paths = [str(Path.cwd()), str(Path.cwd() / "docs")]
        analyses = [
            Mock(
                analysis_status=main_module.AnalysisStatus.COMPLETED,
                error_message="",
                task_path=Path(task_path),
                archive_results=[],
                ignored_items=[],
            )
            for task_path in task_paths
        ]
        analyzer = Mock()
        analyzer.analyze.side_effect = analyses
        fake_service = Mock()
        fake_service.task_executor.task_analyzer = analyzer
        fake_service.task_executor.input_relationship_resolver.resolve.return_value = Mock(
            relationships=[]
        )
        service_factory = Mock(return_value=fake_service)

        with (
            patch.object(main_module, "GameArchiveService", service_factory),
            patch(
                "builtins.input",
                side_effect=["1", *task_paths, "", "N", "", "0"],
            ),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            main_module.main()

        service_factory.assert_called_once_with()
        fake_service.execute_tasks.assert_not_called()
        output = stdout.getvalue()
        self.assertIn("任务 1", output)
        self.assertIn("任务 2", output)
        self.assertIn("任务已取消，未执行解压", output)

    def test_config_loader_reads_complete_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_data = {
                "max_recursive_depth": 8,
                "max_archive_tasks": 200,
                "max_password_attempts": 6,
                "extraction_timeout_seconds": 120,
                "max_archive_size_mb": 4096,
                "max_extracted_files": 5000,
                "max_total_extracted_size_mb": 20480,
                "ignore_android": False,
                "ignore_AZ": False,
            }
            config_path.write_text(
                json.dumps(config_data), encoding="utf-8"
            )

            settings = ConfigLoader(config_path).load()

            for field_name, expected_value in config_data.items():
                self.assertEqual(getattr(settings, field_name), expected_value)

    def test_config_loader_uses_defaults_for_missing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps({"max_recursive_depth": 3}), encoding="utf-8"
            )

            settings = ConfigLoader(config_path).load()
            defaults = Settings()

            self.assertEqual(settings.max_recursive_depth, 3)
            self.assertEqual(
                settings.max_archive_tasks, defaults.max_archive_tasks
            )
            self.assertEqual(settings.ignore_android, defaults.ignore_android)

    def test_config_loader_uses_defaults_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "missing_config.json"

            settings = ConfigLoader(config_path).load()

            self.assertEqual(settings, Settings())
            self.assertFalse(config_path.exists())

    def test_default_settings_enable_extracted_output_quotas(self) -> None:
        settings = Settings()

        self.assertEqual(settings.max_extracted_files, 100000)
        self.assertEqual(settings.max_total_extracted_size_mb, 102400)

    def test_config_loader_warns_and_ignores_invalid_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "max_recursive_depth": -1,
                        "max_password_attempts": 101,
                        "ignore_android": "yes",
                        "unknown_setting": 123,
                    }
                ),
                encoding="utf-8",
            )
            loader = ConfigLoader(config_path)

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                settings = loader.load()

            defaults = Settings()
            self.assertEqual(
                settings.max_recursive_depth, defaults.max_recursive_depth
            )
            self.assertEqual(
                settings.max_password_attempts,
                defaults.max_password_attempts,
            )
            self.assertEqual(settings.ignore_android, defaults.ignore_android)
            self.assertEqual(len(loader.warnings), 4)
            self.assertEqual(len(caught_warnings), 4)

    def test_tool_manager_reports_missing_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_tool = Path(temp_dir) / "missing" / "lz4.exe"
            manager = ToolManager()

            status = manager.set_tool_path(ToolName.LZ4, missing_tool)

            self.assertEqual(status.path, missing_tool.resolve())
            self.assertFalse(status.available)
            self.assertFalse(status.verified)
            self.assertEqual(status.version, "")

    def test_tool_manager_verifies_valid_tool_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_tool = root / "lz4.exe"
            fake_tool.touch()
            completed = Mock(
                returncode=0,
                stdout="LZ4 command line interface v1.9.4",
                stderr="",
            )

            with patch("tools.tool_manager.subprocess.run", return_value=completed):
                manager = ToolManager()
                status = manager.set_tool_path(ToolName.LZ4, fake_tool)

            self.assertTrue(status.available)
            self.assertTrue(status.verified)
            self.assertEqual(status.version, "1.9.4")

    def test_tool_manager_discovers_project_lz4(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_tool = root / "tools" / "lz4.exe"
            project_tool.parent.mkdir()
            project_tool.touch()
            completed = Mock(
                returncode=0,
                stdout="LZ4 command line interface 1.10.0",
                stderr="",
            )

            with patch(
                "tools.tool_manager.subprocess.run",
                return_value=completed,
            ):
                manager = ToolManager(project_root=root)

            status = manager.get_tool_status(ToolName.LZ4)
            self.assertEqual(status.path, project_tool.resolve())
            self.assertTrue(status.available)
            self.assertTrue(status.verified)
            self.assertEqual(status.version, "1.10.0")

    def test_tool_manager_discovers_lz4_in_project_child_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_tool = (
                root / "tools" / "lz4_win64_v1_10_0" / "lz4.exe"
            )
            project_tool.parent.mkdir(parents=True)
            project_tool.touch()
            completed = Mock(
                returncode=0,
                stdout="LZ4 command line interface 1.10.0",
                stderr="",
            )

            with patch(
                "tools.tool_manager.subprocess.run",
                return_value=completed,
            ):
                manager = ToolManager(project_root=root)

            status = manager.get_tool_status(ToolName.LZ4)
            self.assertEqual(status.path, project_tool.resolve())
            self.assertTrue(status.available)
            self.assertTrue(status.verified)
            self.assertEqual(status.version, "1.10.0")

    def test_configured_tool_path_has_priority_over_project_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_tool = root / "tools" / "lz4.exe"
            configured_tool = root / "configured" / "lz4.exe"
            project_tool.parent.mkdir()
            configured_tool.parent.mkdir()
            project_tool.touch()
            configured_tool.touch()
            completed = Mock(
                returncode=0,
                stdout="LZ4 command line interface 1.10.0",
                stderr="",
            )

            with patch(
                "tools.tool_manager.subprocess.run",
                return_value=completed,
            ):
                manager = ToolManager(
                    settings=Settings(lz4_path=configured_tool),
                    project_root=root,
                )

            status = manager.get_tool_status(ToolName.LZ4)
            self.assertEqual(status.path, configured_tool.resolve())
            self.assertNotEqual(status.path, project_tool.resolve())
            self.assertTrue(status.verified)

    def test_tool_manager_discovers_lz4_from_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path_tool = root / "path-bin" / "lz4.exe"
            path_tool.parent.mkdir()
            path_tool.touch()
            completed = Mock(
                returncode=0,
                stdout="LZ4 command line interface 1.10.0",
                stderr="",
            )

            def find_on_path(executable_name: str) -> str | None:
                if executable_name.casefold() == "lz4.exe":
                    return str(path_tool)
                return None

            with (
                patch.object(
                    ToolManager,
                    "_common_candidates",
                    return_value=[],
                ),
                patch(
                    "tools.tool_manager.shutil.which",
                    side_effect=find_on_path,
                ),
                patch(
                    "tools.tool_manager.subprocess.run",
                    return_value=completed,
                ),
            ):
                manager = ToolManager(project_root=root / "project")

            status = manager.get_tool_status(ToolName.LZ4)
            self.assertEqual(status.path, path_tool.resolve())
            self.assertTrue(status.available)
            self.assertTrue(status.verified)

    def test_startup_info_displays_all_tool_statuses(self) -> None:
        import main as main_module

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tool_paths = {
                ToolName.SEVEN_ZIP: root / "7z.exe",
                ToolName.WINRAR: root / "Rar.exe",
                ToolName.LZ4: root / "lz4.exe",
            }
            for tool_path in tool_paths.values():
                tool_path.touch()
            completed = Mock(
                returncode=0,
                stdout="Tool version 1.2.3",
                stderr="",
            )
            with patch(
                "tools.tool_manager.subprocess.run",
                return_value=completed,
            ):
                manager = ToolManager(
                    tool_paths=tool_paths,
                    project_root=root,
                )

            with patch("sys.stdout", new_callable=StringIO) as stdout:
                main_module.print_startup_info(manager)

            output = stdout.getvalue()
            self.assertIn("GameArchiveManager", output)
            self.assertIn("版本: 0.1.0", output)
            self.assertIn("构建类型: Release Candidate", output)
            for display_name, tool_path in (
                ("7-Zip", tool_paths[ToolName.SEVEN_ZIP]),
                ("WinRAR", tool_paths[ToolName.WINRAR]),
                ("LZ4", tool_paths[ToolName.LZ4]),
            ):
                self.assertIn(f"{display_name}:", output)
                self.assertIn(f"路径: {tool_path.resolve()}", output)
            self.assertEqual(output.count("版本: 1.2.3"), 3)
            self.assertEqual(output.count("状态: 可用"), 3)

    def test_application_service_applies_configured_tool_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tool_paths = {
                "seven_zip_path": root / "7z.exe",
                "winrar_path": root / "WinRAR.exe",
                "lz4_path": root / "lz4.exe",
            }
            for tool_path in tool_paths.values():
                tool_path.touch()
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {name: str(path) for name, path in tool_paths.items()}
                ),
                encoding="utf-8",
            )
            completed = Mock(
                returncode=0,
                stdout="Tool version 1.2.3",
                stderr="",
            )

            with patch("tools.tool_manager.subprocess.run", return_value=completed):
                service = GameArchiveService(config_path=config_path)

            expected_paths = {
                ToolName.SEVEN_ZIP: tool_paths["seven_zip_path"],
                ToolName.WINRAR: tool_paths["winrar_path"],
                ToolName.LZ4: tool_paths["lz4_path"],
            }
            for tool_name, expected_path in expected_paths.items():
                status = service.tool_manager.get_tool_status(tool_name)
                self.assertEqual(status.path, expected_path.resolve())
                self.assertTrue(status.available)
                self.assertTrue(status.verified)
                self.assertEqual(status.version, "1.2.3")

    def test_service_automatically_loads_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "max_recursive_depth": 7,
                        "max_archive_tasks": 77,
                        "ignore_android": False,
                    }
                ),
                encoding="utf-8",
            )

            service = GameArchiveService(config_path=config_path)

            self.assertEqual(service.settings.max_recursive_depth, 7)
            self.assertEqual(service.settings.max_archive_tasks, 77)
            self.assertFalse(service.settings.ignore_android)

    def test_service_uses_defaults_when_config_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "missing.json"

            service = GameArchiveService(config_path=config_path)

            self.assertEqual(service.settings, Settings())
            self.assertFalse(config_path.exists())

    def test_explicit_settings_override_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps({"max_recursive_depth": 1}), encoding="utf-8"
            )
            custom_settings = Settings(max_recursive_depth=99)

            service = GameArchiveService(
                settings=custom_settings,
                config_path=config_path,
            )

            self.assertIs(service.settings, custom_settings)
            self.assertEqual(service.settings.max_recursive_depth, 99)

    def test_cleanup_manager_discovers_residual_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            password_attempt = root / "game_extracted_password_attempt_1"
            failed_output = root / "data_failed_extraction"
            empty_residue = root / "empty_residue"
            normal_output = root / "normal_output"
            for directory in (
                password_attempt,
                failed_output,
                empty_residue,
                normal_output,
            ):
                directory.mkdir()
            (password_attempt / "partial.bin").write_bytes(b"partial")
            (failed_output / "partial.bin").write_bytes(b"failed")
            (normal_output / "game.exe").write_bytes(b"keep")

            candidates = CleanupManager(root).scan()

            candidate_paths = {candidate.path for candidate in candidates}
            self.assertIn(password_attempt.resolve(), candidate_paths)
            self.assertIn(failed_output.resolve(), candidate_paths)
            self.assertIn(empty_residue.resolve(), candidate_paths)
            self.assertNotIn(normal_output.resolve(), candidate_paths)

    def test_cleanup_scan_does_not_delete_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            password_attempt = root / "game_password_attempt_1"
            password_attempt.mkdir()
            partial_file = password_attempt / "partial.bin"
            partial_file.write_bytes(b"do not delete")

            candidates = CleanupManager(root).scan()

            self.assertEqual(len(candidates), 1)
            self.assertTrue(password_attempt.exists())
            self.assertTrue(partial_file.exists())

    def test_cleanup_delete_removes_only_allowed_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_archive = root / "game.zip"
            input_archive.write_bytes(b"archive")
            allowed = root / "game_password_attempt_1"
            allowed.mkdir()
            (allowed / "partial.bin").write_bytes(b"partial")
            normal = root / "normal_output"
            normal.mkdir()
            (normal / "game.exe").write_bytes(b"keep")
            manager = CleanupManager(
                root,
                task_root=root,
                input_archives=[input_archive],
            )
            manager.scan()

            self.assertTrue(manager.delete(allowed))

            self.assertFalse(allowed.exists())
            self.assertTrue(normal.exists())
            self.assertTrue(input_archive.exists())
            self.assertTrue(root.exists())
            with self.assertRaises(ValueError):
                manager.delete(normal)
            with self.assertRaises(ValueError):
                manager.delete(root)

    def test_game_logger_creates_sanitized_task_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_directory = Path(temp_dir) / "logs"
            test_password = "TestSecret123"

            with GameLogger("task-001", log_directory) as game_logger:
                game_logger.task_started(Path(temp_dir) / "game_folder")
                game_logger.analysis_started()
                game_logger.archives_found(2)
                game_logger.password_recovery_started("data.rar", 1)
                game_logger.info(f"password={test_password}")
                game_logger.password_recovery_finished(True, 1)
                log_path = game_logger.log_path

            self.assertTrue(log_path.is_file())
            content = log_path.read_text(encoding="utf-8")
            self.assertIn("任务开始", content)
            self.assertIn("密码恢复结果: 成功", content)
            self.assertIn("password=[REDACTED]", content)
            self.assertNotIn(test_password, content)

    def test_archive_safety_allows_small_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "small.zip"
            create_zip(archive_path, "game.txt", "small")
            archive_info = ArchiveAnalyzer().analyze(archive_path)

            result = ArchiveSafetyChecker(Settings()).check(archive_info)

            self.assertTrue(result.safe)
            self.assertEqual(result.reasons, [])

    def test_archive_content_inspector_reads_zip_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "content.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("folder/one.txt", b"one")
                archive.writestr("two.bin", b"12345")
            archive_info = ArchiveAnalyzer().analyze(archive_path)

            content_info = ArchiveContentInspector().inspect(archive_info)

            self.assertEqual(content_info.file_count, 2)
            self.assertEqual(content_info.estimated_size, 8)
            self.assertEqual(
                content_info.paths, ["folder/one.txt", "two.bin"]
            )
            self.assertEqual(content_info.warnings, [])

    def test_archive_content_inspector_blocks_unsafe_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", b"unsafe")
            archive_info = ArchiveAnalyzer().analyze(archive_path)
            content_info = ArchiveContentInspector().inspect(archive_info)

            plan = ExecutionStrategy().create_plan(
                archive_info, content_info
            )

            self.assertTrue(content_info.warnings)
            self.assertFalse(plan.can_execute)
            self.assertIn("不安全路径", plan.message)

    def test_seven_zip_listing_blocks_unsafe_rar_or_7z_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "unsafe.7z"
            archive_path.write_bytes(b"7z\xbc\xaf\x27\x1cplaceholder")
            archive_info = ArchiveAnalyzer().analyze(archive_path)
            tool_manager = Mock()
            tool_manager.get_tool_status.return_value = Mock(
                available=True,
                verified=True,
                path=Path(temp_dir) / "7z.exe",
            )
            listing = (
                "Path = safe.txt\n"
                "Size = 4\n"
                "Attributes = A\n\n"
                "Path = ../outside.txt\n"
                "Size = 6\n"
                "Attributes = A\n\n"
                "Path = linked.txt\n"
                "Size = 0\n"
                "Attributes = A\n"
                "Symbolic Link = ../secret.txt\n"
            )

            with patch(
                "security.archive_content_inspector.subprocess.run",
                return_value=Mock(returncode=0, stdout=listing, stderr=""),
            ):
                content_info = ArchiveContentInspector(
                    tool_manager=tool_manager
                ).inspect(archive_info)

            plan = ExecutionStrategy().create_plan(archive_info, content_info)
            self.assertEqual(content_info.file_count, 3)
            self.assertEqual(content_info.estimated_size, 10)
            self.assertFalse(plan.can_execute)
            self.assertTrue(
                any("父目录穿越" in warning for warning in content_info.warnings)
            )
            self.assertTrue(
                any("链接条目" in warning for warning in content_info.warnings)
            )

    def test_encrypted_7z_header_listing_falls_back_without_password_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "encrypted.7z"
            archive_path.write_bytes(b"7z\xbc\xaf\x27\x1cplaceholder")
            archive_info = ArchiveAnalyzer().analyze(archive_path)
            tool_manager = Mock()
            tool_manager.get_tool_status.return_value = Mock(
                available=True,
                verified=True,
                path=Path(temp_dir) / "7z.exe",
            )

            with patch(
                "security.archive_content_inspector.subprocess.run",
                return_value=Mock(
                    returncode=2,
                    stdout="",
                    stderr="Cannot open encrypted archive. Wrong password?",
                ),
            ) as process_run:
                content_info = ArchiveContentInspector(
                    tool_manager=tool_manager
                ).inspect(archive_info)

            command = process_run.call_args.args[0]
            self.assertIn("-p-", command)
            self.assertEqual(content_info.file_count, 0)
            self.assertTrue(
                any("获得正确密码前" in warning for warning in content_info.warnings)
            )

    def test_archive_content_inspector_applies_estimated_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "large_content.zip"
            with zipfile.ZipFile(
                archive_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr("one.txt", b"a")
                archive.writestr("two.bin", b"0" * (2 * 1024 * 1024))
            archive_info = ArchiveAnalyzer().analyze(archive_path)
            content_info = ArchiveContentInspector().inspect(archive_info)
            settings = Settings(
                max_extracted_files=1,
                max_total_extracted_size_mb=1,
            )

            plan = ExecutionStrategy(settings=settings).create_plan(
                archive_info, content_info
            )

            self.assertFalse(plan.can_execute)
            self.assertIn("文件数量超过限制", plan.message)
            self.assertIn("总大小超过限制", plan.message)

    def test_archive_safety_rejects_archive_over_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "large.zip"
            with archive_path.open("wb") as archive:
                archive.write(b"PK\x03\x04")
                archive.seek(2 * 1024 * 1024)
                archive.write(b"\0")
            archive_info = ArchiveAnalyzer().analyze(archive_path)
            settings = Settings(max_archive_size_mb=1)

            result = ArchiveSafetyChecker(settings).check(archive_info)
            plan = ExecutionStrategy(settings=settings).create_plan(archive_info)

            self.assertFalse(result.safe)
            self.assertTrue(result.reasons)
            self.assertIn("超过限制", result.reasons[0])
            self.assertFalse(plan.can_execute)
            self.assertIn("安全检查未通过", plan.message)

    def test_extraction_safety_allows_small_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output"
            output_path.mkdir()
            (output_path / "game.exe").write_bytes(b"small")
            settings = Settings(
                max_extracted_files=10,
                max_total_extracted_size_mb=10,
            )

            result = ExtractionSafetyChecker(settings).check(output_path)

            self.assertTrue(result.safe)
            self.assertEqual(result.reasons, [])

    def test_extraction_safety_rejects_too_many_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output"
            output_path.mkdir()
            (output_path / "one.txt").touch()
            (output_path / "two.txt").touch()
            settings = Settings(max_extracted_files=1)

            result = ExtractionSafetyChecker(settings).check(output_path)

            self.assertFalse(result.safe)
            self.assertTrue((output_path / "one.txt").exists())
            self.assertTrue((output_path / "two.txt").exists())
            self.assertIn("文件数量超过限制", result.reasons[0])

    def test_extraction_safety_rejects_total_size_over_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output"
            output_path.mkdir()
            large_file = output_path / "large.bin"
            with large_file.open("wb") as file:
                file.seek(2 * 1024 * 1024)
                file.write(b"\0")
            settings = Settings(max_total_extracted_size_mb=1)

            result = ExtractionSafetyChecker(settings).check(output_path)

            self.assertFalse(result.safe)
            self.assertTrue(large_file.exists())
            self.assertIn("总大小超过限制", result.reasons[0])

    def test_extraction_safety_rejects_file_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_path = root / "output"
            output_path.mkdir()
            linked_file = output_path / "linked-secret.txt"
            linked_file.write_text("simulated link target", encoding="utf-8")

            with patch.object(
                ExtractionSafetyChecker,
                "_is_link_or_reparse_point",
                side_effect=lambda path: Path(path).name == linked_file.name,
            ):
                result = ExtractionSafetyChecker().check(output_path)

            self.assertFalse(result.safe)
            self.assertTrue(
                any("文件符号链接或重解析点" in reason for reason in result.reasons)
            )

    def test_extraction_safety_recognizes_windows_reparse_attribute(self) -> None:
        path = Mock()
        path.is_symlink.return_value = False
        path.lstat.return_value = Mock(st_file_attributes=0x400)

        self.assertTrue(ExtractionSafetyChecker._is_link_or_reparse_point(path))

    def test_platform_filter_skips_archive_in_android_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "Android" / "data.zip"

            result = PlatformFilter().check(
                archive,
                Settings(ignore_android=True),
                root_path=Path(temp_dir),
            )

            self.assertTrue(result.skipped)
            self.assertIn("Android", result.reason)

    def test_platform_filter_allows_archive_in_normal_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "PC" / "data.zip"

            result = PlatformFilter().check(
                archive, Settings(ignore_AZ=True)
            )

            self.assertFalse(result.skipped)
            self.assertEqual(result.reason, "")

    def test_platform_filter_skips_az_archive_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "AZ_patch.zip"

            result = PlatformFilter().check(
                archive, Settings(ignore_AZ=True)
            )

            self.assertTrue(result.skipped)
            self.assertIn("AZ", result.reason)

    def test_seven_zip_extractor_extracts_normal_zip(self) -> None:
        tool_manager = ToolManager()
        if not tool_manager.check_tool(ToolName.SEVEN_ZIP):
            self.skipTest("本机未发现 7-Zip，跳过真实解压测试")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "normal.zip"
            create_zip(archive_path, "hello.txt", "hello integration")

            archive_info = ArchiveAnalyzer().analyze(archive_path)
            plan = ExecutionStrategy().create_plan(archive_info)
            result = SevenZipExtractor(tool_manager=tool_manager).extract(plan)

            self.assertTrue(result.success, result.error)
            self.assertIs(result.status, ExtractionStatus.SUCCESS)
            self.assertEqual(result.tool_used, ToolName.SEVEN_ZIP)
            self.assertEqual(
                (plan.output_path / "hello.txt").read_text(encoding="utf-8"),
                "hello integration",
            )

    def test_seven_zip_password_uses_stdin_not_process_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "protected.7z"
            archive_path.write_bytes(b"7z\xbc\xaf\x27\x1cplaceholder")
            tool_path = root / "7z.exe"
            tool_path.write_bytes(b"placeholder")
            tool_manager = Mock()
            tool_manager.get_tool_status.return_value = Mock(
                available=True,
                verified=True,
                path=tool_path,
            )
            plan = ExtractionPlan(
                archive_path=archive_path,
                detected_format="7Z",
                selected_tool=ToolName.SEVEN_ZIP,
                output_path=root / "protected_extracted",
            )
            password = "中文测试密码"
            completed = Mock(returncode=0, stdout="", stderr="")

            with patch(
                "extractor.seven_zip.subprocess.run", return_value=completed
            ) as process_run:
                result = SevenZipExtractor(tool_manager=tool_manager).extract(
                    plan, password=password
                )

            self.assertTrue(result.success)
            command = process_run.call_args.args[0]
            self.assertNotIn(password, " ".join(command))
            self.assertFalse(any(argument.startswith("-p") for argument in command))
            self.assertIn("-sccUTF-8", command)
            self.assertEqual(process_run.call_args.kwargs["input"], f"{password}\n")
            self.assertEqual(process_run.call_args.kwargs["encoding"], "utf-8")

    def test_lz4_extractor_returns_tool_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "data.lz4"
            archive_path.write_bytes(b"\x04\x22\x4d\x18test")
            missing_tool = root / "missing" / "lz4.exe"
            settings = Settings(lz4_path=missing_tool)
            plan = ExtractionPlan(
                archive_path=archive_path,
                detected_format="LZ4",
                selected_tool=ToolName.LZ4,
                output_path=root / "data_extracted",
            )

            result = Lz4Extractor(settings=settings).extract(plan)

            self.assertFalse(result.success)
            self.assertIs(result.status, ExtractionStatus.TOOL_NOT_FOUND)
            self.assertIs(result.tool_used, ToolName.LZ4)

    def test_settings_lz4_path_reaches_dispatcher_and_extractor(self) -> None:
        """Settings 路径应由共享 ToolManager 验证并用于真实 Adapter 调用。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            lz4_path = root / "lz4.exe"
            lz4_path.write_bytes(b"test executable placeholder")
            archive_path = root / "payload.lz4"
            archive_path.write_bytes(b"\x04\x22\x4d\x18payload")
            settings = Settings(lz4_path=lz4_path)

            version_result = Mock(
                returncode=0,
                stdout="LZ4 command line interface 1.10.0",
                stderr="",
            )
            extraction_result = Mock(returncode=0, stdout="", stderr="")
            with patch(
                "tools.tool_manager.subprocess.run",
                return_value=version_result,
            ) as version_run:
                executor = TaskExecutor(settings=settings)

            dispatcher = executor.coordinator.dispatcher
            tool_status = dispatcher.tool_manager.get_tool_status(ToolName.LZ4)
            self.assertEqual(tool_status.path, lz4_path.resolve())
            self.assertTrue(tool_status.available)
            self.assertTrue(tool_status.verified)
            version_run.assert_any_call(
                [str(lz4_path.resolve()), "--version"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
                timeout=ToolManager.VERSION_TIMEOUT_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            plan = ExtractionPlan(
                archive_path=archive_path,
                detected_format="LZ4",
                selected_tool=ToolName.LZ4,
                output_path=root / "payload_extracted",
            )
            with patch(
                "extractor.lz4.subprocess.run",
                return_value=extraction_result,
            ) as extract_run:
                result = dispatcher.extract(plan)

            self.assertIs(result.status, ExtractionStatus.SUCCESS, result.error)
            self.assertIs(result.tool_used, ToolName.LZ4)
            extract_run.assert_called_once_with(
                [
                    str(lz4_path.resolve()),
                    "-d",
                    str(archive_path.resolve()),
                    str((plan.output_path / "payload").resolve()),
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
                timeout=settings.extraction_timeout_seconds,
            )

    def test_dispatcher_selects_seven_zip_extractor(self) -> None:
        seven_zip = Mock()
        lz4 = Mock()
        expected = ExtractionResult(
            success=True,
            message="seven zip selected",
            status=ExtractionStatus.SUCCESS,
        )
        seven_zip.extract.return_value = expected
        plan = ExtractionPlan(
            archive_path=Path("test.zip"),
            detected_format="ZIP",
            selected_tool=ToolName.SEVEN_ZIP,
            output_path=Path("test_extracted"),
        )
        dispatcher = ExtractorDispatcher(
            seven_zip_extractor=seven_zip,
            lz4_extractor=lz4,
        )

        result = dispatcher.extract(plan)

        self.assertIs(result, expected)
        seven_zip.extract.assert_called_once_with(plan, password=None)
        lz4.extract.assert_not_called()

    def test_dispatcher_selects_lz4_extractor(self) -> None:
        seven_zip = Mock()
        lz4 = Mock()
        expected = ExtractionResult(
            success=True,
            message="lz4 selected",
            status=ExtractionStatus.SUCCESS,
        )
        lz4.extract.return_value = expected
        plan = ExtractionPlan(
            archive_path=Path("test.lz4"),
            detected_format="LZ4",
            selected_tool=ToolName.LZ4,
            output_path=Path("test_extracted"),
        )
        dispatcher = ExtractorDispatcher(
            seven_zip_extractor=seven_zip,
            lz4_extractor=lz4,
        )

        result = dispatcher.extract(plan)

        self.assertIs(result, expected)
        lz4.extract.assert_called_once_with(plan, password=None)
        seven_zip.extract.assert_not_called()

    def test_winrar_extractor_returns_tool_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "data.rar"
            archive_path.write_bytes(b"Rar!\x1a\x07\x00test")
            missing_tool = root / "missing" / "WinRAR.exe"
            plan = ExtractionPlan(
                archive_path=archive_path,
                detected_format="RAR",
                selected_tool=ToolName.WINRAR,
                output_path=root / "data_extracted",
            )

            result = WinRarExtractor(
                settings=Settings(winrar_path=missing_tool)
            ).extract(plan)

            self.assertFalse(result.success)
            self.assertIs(result.status, ExtractionStatus.TOOL_NOT_FOUND)
            self.assertIs(result.tool_used, ToolName.WINRAR)
            self.assertFalse(plan.output_path.exists())

    def test_dispatcher_selects_winrar_extractor(self) -> None:
        seven_zip = Mock()
        winrar = Mock()
        lz4 = Mock()
        expected = ExtractionResult(
            success=True,
            message="winrar selected",
            tool_used=ToolName.WINRAR,
            status=ExtractionStatus.SUCCESS,
        )
        winrar.extract.return_value = expected
        plan = ExtractionPlan(
            archive_path=Path("test.rar"),
            detected_format="RAR",
            selected_tool=ToolName.WINRAR,
            output_path=Path("test_extracted"),
        )
        dispatcher = ExtractorDispatcher(
            seven_zip_extractor=seven_zip,
            winrar_extractor=winrar,
            lz4_extractor=lz4,
        )

        result = dispatcher.extract(plan)

        self.assertIs(result, expected)
        winrar.extract.assert_called_once_with(plan, password=None)
        seven_zip.extract.assert_not_called()
        lz4.extract.assert_not_called()

    def test_rar_falls_back_to_winrar_after_seven_zip_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "game.rar"
            archive_path.write_bytes(b"Rar!\x1a\x07\x00test")
            seven_zip = Mock()
            winrar = Mock()
            lz4 = Mock()
            seven_zip.extract.return_value = ExtractionResult(
                success=False,
                message="7-Zip 执行失败",
                error="temporary tool failure",
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.FAILED,
            )

            def winrar_success(plan, password=None):
                plan.output_path.mkdir(parents=True, exist_ok=False)
                return ExtractionResult(
                    success=True,
                    message="WinRAR 解压成功",
                    output_path=plan.output_path,
                    tool_used=ToolName.WINRAR,
                    status=ExtractionStatus.SUCCESS,
                )

            winrar.extract.side_effect = winrar_success
            dispatcher = ExtractorDispatcher(
                seven_zip_extractor=seven_zip,
                winrar_extractor=winrar,
                lz4_extractor=lz4,
            )
            coordinator = ExtractionCoordinator(dispatcher=dispatcher)

            result = coordinator.process(archive_path)

            self.assertTrue(result.success, result.error_message)
            self.assertIs(
                result.extraction_result.tool_used, ToolName.WINRAR
            )
            primary_plan = seven_zip.extract.call_args.args[0]
            fallback_plan = winrar.extract.call_args.args[0]
            self.assertIs(primary_plan.primary_tool, ToolName.SEVEN_ZIP)
            self.assertEqual(primary_plan.fallback_tools, [ToolName.WINRAR])
            self.assertFalse(primary_plan.is_composite)
            self.assertIs(primary_plan.selected_tool, ToolName.SEVEN_ZIP)
            self.assertIs(fallback_plan.selected_tool, ToolName.WINRAR)
            self.assertIn("切换备用工具: WINRAR", result.steps)

    def test_zip_does_not_use_winrar_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "game.zip"
            create_zip(archive_path, "game.txt", "test")
            seven_zip = Mock()
            winrar = Mock()
            lz4 = Mock()
            seven_zip.extract.return_value = ExtractionResult(
                success=False,
                message="7-Zip 执行失败",
                error="temporary tool failure",
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.FAILED,
            )
            dispatcher = ExtractorDispatcher(
                seven_zip_extractor=seven_zip,
                winrar_extractor=winrar,
                lz4_extractor=lz4,
            )
            coordinator = ExtractionCoordinator(dispatcher=dispatcher)

            result = coordinator.process(archive_path)

            self.assertFalse(result.success)
            seven_zip.extract.assert_called_once()
            winrar.extract.assert_not_called()
            lz4.extract.assert_not_called()
            zip_plan = seven_zip.extract.call_args.args[0]
            self.assertEqual(zip_plan.fallback_tools, [])

    def test_composite_lz4_output_rar_continues_with_rar_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "PC.rar.lz4"
            archive_path.write_bytes(
                b"\x04\x22\x4d\x18outer-data-Rar!-hint"
            )
            lz4 = Mock()
            seven_zip = Mock()
            winrar = Mock()

            def extract_lz4(plan, password=None):
                plan.output_path.mkdir(parents=True, exist_ok=False)
                intermediate = plan.output_path / plan.archive_path.stem
                intermediate.write_bytes(b"Rar!\x1a\x07\x00inner-rar")
                return ExtractionResult(
                    True,
                    "LZ4 解压成功",
                    plan.output_path,
                    tool_used=ToolName.LZ4,
                    status=ExtractionStatus.SUCCESS,
                )

            def extract_rar(plan, password=None):
                plan.output_path.mkdir(parents=True, exist_ok=False)
                return ExtractionResult(
                    True,
                    "RAR 解压成功",
                    plan.output_path,
                    tool_used=ToolName.SEVEN_ZIP,
                    status=ExtractionStatus.SUCCESS,
                )

            lz4.extract.side_effect = extract_lz4
            seven_zip.extract.side_effect = extract_rar
            dispatcher = ExtractorDispatcher(
                seven_zip_extractor=seven_zip,
                winrar_extractor=winrar,
                lz4_extractor=lz4,
            )
            coordinator = ExtractionCoordinator(dispatcher=dispatcher)

            result = coordinator.process(archive_path)

            self.assertTrue(result.success, result.error_message)
            outer_plan = lz4.extract.call_args.args[0]
            inner_plan = seven_zip.extract.call_args.args[0]
            self.assertTrue(outer_plan.is_composite)
            self.assertEqual(outer_plan.container_chain, ["LZ4", "RAR"])
            self.assertEqual(len(outer_plan.stages), 2)
            self.assertTrue(outer_plan.stages[1].requires_reanalysis)
            self.assertEqual(inner_plan.detected_format, "RAR")
            self.assertEqual(inner_plan.fallback_tools, [ToolName.WINRAR])
            self.assertIs(
                result.extraction_result.tool_used, ToolName.SEVEN_ZIP
            )
            winrar.extract.assert_not_called()

    def test_incorrect_container_hint_uses_reanalyzed_format(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "wrong.rar.lz4"
            # 外层探测会得到 LZ4 → RAR 提示，但模拟解压结果实际是 ZIP。
            archive_path.write_bytes(
                b"\x04\x22\x4d\x18false-positive-Rar!-marker"
            )
            lz4 = Mock()
            seven_zip = Mock()
            winrar = Mock()

            def extract_lz4(plan, password=None):
                plan.output_path.mkdir(parents=True, exist_ok=False)
                intermediate = plan.output_path / plan.archive_path.stem
                create_zip(intermediate, "actual.txt", "actual zip")
                return ExtractionResult(
                    True,
                    "LZ4 解压成功",
                    plan.output_path,
                    tool_used=ToolName.LZ4,
                    status=ExtractionStatus.SUCCESS,
                )

            def extract_zip(plan, password=None):
                plan.output_path.mkdir(parents=True, exist_ok=False)
                return ExtractionResult(
                    True,
                    "ZIP 解压成功",
                    plan.output_path,
                    tool_used=ToolName.SEVEN_ZIP,
                    status=ExtractionStatus.SUCCESS,
                )

            lz4.extract.side_effect = extract_lz4
            seven_zip.extract.side_effect = extract_zip
            dispatcher = ExtractorDispatcher(
                seven_zip_extractor=seven_zip,
                winrar_extractor=winrar,
                lz4_extractor=lz4,
            )
            coordinator = ExtractionCoordinator(dispatcher=dispatcher)

            result = coordinator.process(archive_path)

            self.assertTrue(result.success, result.error_message)
            actual_inner_plan = seven_zip.extract.call_args.args[0]
            self.assertEqual(actual_inner_plan.detected_format, "ZIP")
            self.assertEqual(actual_inner_plan.fallback_tools, [])
            self.assertTrue(
                any("采用实际分析结果" in step for step in result.steps)
            )
            winrar.extract.assert_not_called()

    def test_password_recovery_flow_stops_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "protected.zip"
            archive_path.touch()
            output_path = root / "protected_extracted"
            plan = ExtractionPlan(
                archive_path=archive_path,
                detected_format="ZIP",
                selected_tool=ToolName.SEVEN_ZIP,
                output_path=output_path,
            )
            password_required = ExtractionResult(
                success=False,
                message="需要密码",
                output_path=output_path,
                status=ExtractionStatus.PASSWORD_REQUIRED,
            )
            candidates = [
                PasswordCandidate("bad_password", PasswordSource.USER_INPUT),
                PasswordCandidate("correct_password", PasswordSource.USER_INPUT),
            ]
            recovery_engine = PasswordRecoveryEngine(
                extraction_result=password_required,
                password_candidates=candidates,
                archive_path=archive_path,
                max_attempts=2,
            )
            executor = PasswordRetryExecutor(
                plan=plan,
                recovery_engine=recovery_engine,
                extractor=FakePasswordExtractor("correct_password"),
                max_password_attempts=2,
            )

            result = executor.execute()

            self.assertIs(result.status, ExtractionStatus.SUCCESS)
            self.assertEqual(
                [item.status for item in executor.attempt_results],
                [
                    ExtractionStatus.PASSWORD_REQUIRED,
                    ExtractionStatus.WRONG_PASSWORD,
                    ExtractionStatus.SUCCESS,
                ],
            )
            self.assertEqual(recovery_engine.plan.current_index, 2)

    def test_pipeline_runner_processes_discovered_nested_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            initial_archive = root / "game.zip"
            create_zip(initial_archive, "game.txt", "root")
            runner = ExtractionPipelineRunner(
                coordinator=FakeRecursiveCoordinator(initial_archive),
                settings=Settings(ignore_android=True, ignore_AZ=True),
            )
            progress_events: list[PipelineProgress] = []

            result = runner.run(
                initial_archive,
                max_depth=5,
                max_tasks=10,
                progress_callback=progress_events.append,
            )

            self.assertTrue(result.success)
            self.assertEqual(len(result.execution_records), 2)
            self.assertEqual(
                [record.depth for record in result.execution_records], [0, 1]
            )
            self.assertEqual(
                [record.archive_path.name for record in result.execution_records],
                ["game.zip", "nested.zip"],
            )
            self.assertEqual(
                {record.archive_path.name for record in result.skipped_archives},
                {"data.zip", "AZ_patch.zip", "update.rar"},
            )
            self.assertTrue(
                all(record.depth == 1 for record in result.skipped_archives)
            )
            self.assertTrue(
                all(
                    record.status is ArchiveTaskStatus.COMPLETED
                    for record in result.execution_records
                )
            )

            report = ReportGenerator().generate(result)
            self.assertEqual(report.skipped_count, 3)
            self.assertEqual(report.total_archives, 5)
            self.assertGreaterEqual(len(progress_events), 3)
            self.assertEqual(progress_events[0].archive_count, 1)
            self.assertEqual(progress_events[-1].archive_count, 2)
            self.assertEqual(progress_events[-1].completed_count, 2)
            self.assertEqual(progress_events[-1].failed_count, 0)
            self.assertEqual(
                {event.phase.value for event in progress_events},
                {"EXTRACTING", "SCANNING", "VALIDATING", "COMPLETED"},
            )

    def test_task_report_counts_initial_skipped_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_result = TaskExecutionResult(
                task_id="task-initial-skip",
                task_path=root,
                success=True,
                skipped_archives=[
                    SkippedArchiveResult(
                        archive_path=root / "Android_game.zip",
                        reason="初始平台规则跳过",
                    )
                ],
            )

            report = ReportGenerator().generate(task_result)

            self.assertEqual(report.skipped_count, 1)
            self.assertEqual(report.total_archives, 1)

    def test_task_report_counts_recursive_skipped_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recursive_skip = SkippedArchiveRecord(
                archive_path=root / "Android" / "data.zip",
                depth=1,
                parent_archive=root / "game.zip",
                reason="递归平台规则跳过",
            )
            task_result = TaskExecutionResult(
                task_id="task-recursive-skip",
                task_path=root,
                success=True,
                pipeline_results=[
                    PipelineResult(
                        success=True,
                        skipped_archives=[recursive_skip],
                    )
                ],
            )

            report = ReportGenerator().generate(task_result)

            self.assertEqual(report.skipped_count, 1)
            self.assertEqual(report.total_archives, 1)

    def test_report_generator_creates_pipeline_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            success_archive = root / "success.zip"
            failed_archive = root / "failed.rar"
            output_path = root / "success_extracted"
            success_extraction = ExtractionResult(
                success=True,
                message="解压成功",
                output_path=output_path,
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.SUCCESS,
            )
            failed_extraction = ExtractionResult(
                success=False,
                message="密码错误",
                status=ExtractionStatus.WRONG_PASSWORD,
            )
            success_coordinator = CoordinatorResult(
                success=True,
                archive_path=success_archive,
                extraction_result=success_extraction,
                steps=["密码尝试 1: SUCCESS - 解压成功"],
            )
            failed_coordinator = CoordinatorResult(
                success=False,
                archive_path=failed_archive,
                extraction_result=failed_extraction,
                steps=["解压失败"],
                error_message="密码错误",
            )
            success_item = ArchiveTaskItem(
                success_archive, 0, None, ArchiveTaskStatus.COMPLETED
            )
            failed_item = ArchiveTaskItem(
                failed_archive, 1, success_archive, ArchiveTaskStatus.FAILED
            )
            pipeline_result = PipelineResult(
                success=False,
                processed_archives=[success_item],
                failed_archives=[failed_item],
                execution_records=[
                    ArchiveExecutionRecord(
                        success_archive,
                        0,
                        None,
                        ArchiveTaskStatus.COMPLETED,
                        success_coordinator,
                        output_path,
                    ),
                    ArchiveExecutionRecord(
                        failed_archive,
                        1,
                        success_archive,
                        ArchiveTaskStatus.FAILED,
                        failed_coordinator,
                        None,
                    ),
                ],
                skipped_archives=[
                    SkippedArchiveRecord(
                        root / "Android_patch.zip",
                        1,
                        success_archive,
                        "平台规则跳过",
                    )
                ],
            )

            report = ReportGenerator().generate(
                pipeline_result, execution_time=1.25
            )

            self.assertEqual(report.total_archives, 3)
            self.assertEqual(report.success_count, 1)
            self.assertEqual(report.failed_count, 1)
            self.assertEqual(report.skipped_count, 1)
            self.assertEqual(report.password_attempt_count, 1)
            self.assertEqual(report.execution_time, 1.25)
            self.assertEqual(report.output_paths, [output_path])
            self.assertIn("成功 1 个", report.summary)
            self.assertIn("失败 1 个", report.summary)

    def test_report_failure_detail_for_missing_tool(self) -> None:
        archive = Path(r"C:\Games\missing-tool.rar")
        failed_output = Path(r"C:\Games\missing-tool_extracted")
        coordinator_result = CoordinatorResult(
            success=False,
            archive_path=archive,
            extraction_result=ExtractionResult(
                success=False,
                message="未找到解压工具",
                output_path=failed_output,
                error="7-Zip is not available",
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.TOOL_NOT_FOUND,
            ),
            error_message="7-Zip is not available",
        )
        task_result = TaskExecutionResult(
            task_id="missing-tool",
            task_path=archive.parent,
            success=False,
            coordinator_results=[coordinator_result],
        )

        report = ReportGenerator().generate(task_result)

        self.assertEqual(report.output_paths, [])
        self.assertEqual(len(report.failure_details), 1)
        detail = report.failure_details[0]
        self.assertEqual(detail.file_path, archive)
        self.assertEqual(detail.stage, "TOOL_DISCOVERY")
        self.assertIs(detail.tool, ToolName.SEVEN_ZIP)
        self.assertEqual(detail.error_type, "TOOL_NOT_FOUND")
        self.assertEqual(detail.reason, "7-Zip is not available")

    def test_report_failure_detail_for_wrong_password(self) -> None:
        archive = Path(r"C:\Games\protected.7z")
        coordinator_result = CoordinatorResult(
            success=False,
            archive_path=archive,
            extraction_result=ExtractionResult(
                success=False,
                message="密码错误",
                error="所有密码候选均失败",
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.WRONG_PASSWORD,
            ),
            error_message="所有密码候选均失败",
        )
        task_result = TaskExecutionResult(
            task_id="wrong-password",
            task_path=archive.parent,
            success=False,
            coordinator_results=[coordinator_result],
        )

        report = ReportGenerator().generate(task_result)

        detail = report.failure_details[0]
        self.assertEqual(detail.stage, "PASSWORD_RECOVERY")
        self.assertIs(detail.tool, ToolName.SEVEN_ZIP)
        self.assertEqual(detail.error_type, "WRONG_PASSWORD")
        self.assertIn("密码候选均失败", detail.reason)

    def test_report_failure_detail_for_corrupt_archive_and_cli_output(self) -> None:
        import main as main_module

        archive = Path(r"C:\Games\damaged.zip")
        coordinator_result = CoordinatorResult(
            success=False,
            archive_path=archive,
            extraction_result=ExtractionResult(
                success=False,
                message="解压失败",
                error="Data Error: archive is corrupt",
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.FAILED,
            ),
            error_message="Data Error: archive is corrupt",
        )
        task_result = TaskExecutionResult(
            task_id="corrupt-archive",
            task_path=archive.parent,
            success=False,
            coordinator_results=[coordinator_result],
        )
        report = ReportGenerator().generate(task_result)

        detail = report.failure_details[0]
        self.assertEqual(detail.stage, "EXTRACTION")
        self.assertEqual(detail.error_type, "FAILED")
        self.assertIn("corrupt", detail.reason)

        with patch("sys.stdout", new_callable=StringIO) as stdout:
            main_module.print_report(report)
        output = stdout.getvalue()
        self.assertIn(str(archive), output)
        self.assertIn("EXTRACTION", output)
        self.assertIn("SEVEN_ZIP", output)
        self.assertIn("Data Error: archive is corrupt", output)

    def test_output_organizer_keeps_only_clean_leaf_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_root = Path(temp_dir) / "game"
            task_root.mkdir()

            intermediate = task_root / "outer_extracted"
            final_nested = intermediate / "inner_extracted"
            final_nested.mkdir(parents=True)
            (final_nested / "game.exe").write_bytes(b"final")

            password_result = (
                task_root / "protected_extracted_password_attempt_2"
            )
            password_result.mkdir()
            (password_result / "payload.txt").write_text(
                "password success", encoding="utf-8"
            )

            temporary = task_root / "game_temp_extracted"
            temporary.mkdir()
            (temporary / "partial.bin").write_bytes(b"partial")

            final_paths = OutputOrganizer().organize(
                task_root,
                [intermediate, final_nested, password_result, temporary],
            )

            final_root = task_root.resolve() / "GameArchive_Output"
            # Two unrelated low-confidence outputs cannot be resolved safely.
            self.assertEqual(final_paths, [])
            self.assertFalse(final_root.exists())
            self.assertFalse(
                any("password_attempt" in path.name for path in final_paths)
            )
            self.assertFalse((final_root / temporary.name).exists())
            self.assertTrue(intermediate.exists())
            self.assertTrue(password_result.exists())
            self.assertTrue(temporary.exists())

    def test_service_organizes_single_output_and_preserves_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_root = root / "game"
            task_root.mkdir()
            archive_path = task_root / "game.zip"
            archive_content = b"original archive"
            archive_path.write_bytes(archive_content)
            source_output = task_root / "game_extracted"
            source_output.mkdir()
            (source_output / "payload.txt").write_text(
                "single output", encoding="utf-8"
            )
            extraction_result = ExtractionResult(
                success=True,
                message="success",
                output_path=source_output,
                tool_used=ToolName.SEVEN_ZIP,
                status=ExtractionStatus.SUCCESS,
            )
            coordinator_result = CoordinatorResult(
                success=True,
                archive_path=archive_path,
                extraction_result=extraction_result,
            )
            task_result = TaskExecutionResult(
                task_id="single-output",
                task_path=task_root,
                success=True,
                coordinator_results=[coordinator_result],
            )
            executor = Mock()

            def execute(task, max_password_attempts=None):
                task.status = TaskStatus.COMPLETED
                return task_result

            executor.execute.side_effect = execute
            history_storage = HistoryStorage(root / "history.json")
            log_directory = root / "logs"
            service = GameArchiveService(
                task_executor=executor,
                history_storage=history_storage,
                log_directory=log_directory,
            )

            report = service.execute_task(task_root)

            final_output = (
                task_root.resolve()
                / "GameArchive_Output"
                / "game"
            )
            self.assertEqual(report.output_paths, [final_output])
            self.assertEqual(
                (final_output / "payload.txt").read_text(encoding="utf-8"),
                "single output",
            )
            self.assertTrue(source_output.is_dir())
            self.assertEqual(archive_path.read_bytes(), archive_content)

            history_record = history_storage.read_all()[0]
            self.assertEqual(history_record.output_paths, [final_output])
            log_content = next(log_directory.glob("task_*.log")).read_text(
                encoding="utf-8"
            )
            self.assertIn(str(final_output), log_content)

    def test_service_organizes_same_named_outputs_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_root = root / "game"
            task_root.mkdir()
            archives: list[Path] = []
            coordinator_results: list[CoordinatorResult] = []
            for folder_name, content in (("first", "one"), ("second", "two")):
                source_parent = task_root / folder_name
                source_parent.mkdir()
                archive_path = source_parent / "game.zip"
                archive_path.write_bytes(f"archive-{content}".encode("ascii"))
                archives.append(archive_path)
                source_output = source_parent / "game_extracted"
                source_output.mkdir()
                (source_output / "payload.txt").write_text(
                    content, encoding="utf-8"
                )
                for directory_name in ("game", "lib", "renpy"):
                    (source_output / directory_name).mkdir()
                (source_output / "launcher.exe").write_bytes(b"launcher")
                coordinator_results.append(
                    CoordinatorResult(
                        success=True,
                        archive_path=archive_path,
                        extraction_result=ExtractionResult(
                            success=True,
                            message="success",
                            output_path=source_output,
                            tool_used=ToolName.SEVEN_ZIP,
                            status=ExtractionStatus.SUCCESS,
                        ),
                    )
                )

            task_result = TaskExecutionResult(
                task_id="duplicate-output",
                task_path=task_root,
                success=True,
                coordinator_results=coordinator_results,
            )
            executor = Mock()

            def execute(task, max_password_attempts=None):
                task.status = TaskStatus.COMPLETED
                return task_result

            executor.execute.side_effect = execute
            service = GameArchiveService(
                task_executor=executor,
                history_storage=HistoryStorage(root / "history.json"),
                log_directory=root / "logs",
            )

            report = service.execute_task(task_root)

            final_root = task_root.resolve() / "GameArchive_Output"
            self.assertEqual(
                report.output_paths,
                [
                    final_root / "game",
                    final_root / "game_2",
                ],
            )
            self.assertEqual(
                (report.output_paths[0] / "payload.txt").read_text(
                    encoding="utf-8"
                ),
                "one",
            )
            self.assertEqual(
                (report.output_paths[1] / "payload.txt").read_text(
                    encoding="utf-8"
                ),
                "two",
            )
            self.assertEqual(archives[0].read_bytes(), b"archive-one")
            self.assertEqual(archives[1].read_bytes(), b"archive-two")


class FullWorkflowTest(unittest.TestCase):
    """验证从用户任务目录到报告和历史记录的完整服务流程。"""

    def test_complete_game_archive_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_folder = root / "game_folder"
            game_folder.mkdir()

            with zipfile.ZipFile(game_folder / "game.zip", "w") as archive:
                # RAR 文件头使真实 ArchiveFinder/Analyzer 能识别嵌套文件。
                archive.writestr(
                    "data.rar", b"Rar!\x1a\x07\x00test-data"
                )
            create_zip(
                game_folder / "Android_game.zip",
                "mobile.txt",
                "android game",
            )
            # Scanner 会把真实空文件夹名称作为密码候选。
            (game_folder / "123456").mkdir()

            # 本场景只验证 Android 跳过；关闭 AZ 可避免临时目录随机名干扰。
            settings = Settings(
                ignore_android=True,
                ignore_AZ=False,
                max_password_attempts=5,
            )
            fake_extractor = FullWorkflowExtractor()
            coordinator = ExtractionCoordinator(
                strategy=ExecutionStrategy(settings=settings),
                extractor=fake_extractor,
            )
            pipeline_runner = ExtractionPipelineRunner(
                coordinator=coordinator,
                settings=settings,
            )
            task_executor = RecordingTaskExecutor(
                coordinator=coordinator,
                pipeline_runner=pipeline_runner,
                settings=settings,
            )
            history_file = root / "history" / "task_history.json"
            history_storage = HistoryStorage(history_file)
            log_directory = root / "task_logs"
            service = GameArchiveService(
                settings=settings,
                task_executor=task_executor,
                history_storage=history_storage,
                log_directory=log_directory,
            )

            report = service.execute_task(game_folder)

            self.assertIsNotNone(task_executor.last_task)
            self.assertIsNotNone(task_executor.last_result)
            self.assertIs(task_executor.last_task.status, TaskStatus.COMPLETED)
            self.assertTrue(task_executor.last_result.success)

            self.assertEqual(report.total_archives, 3)
            self.assertEqual(report.success_count, 2)
            self.assertEqual(report.failed_count, 0)
            self.assertEqual(report.skipped_count, 1)
            self.assertEqual(report.password_attempt_count, 1)
            self.assertEqual(len(report.output_paths), 1)
            self.assertIn("成功 2 个", report.summary)
            self.assertIn("跳过 1 个", report.summary)

            self.assertTrue(fake_extractor.password_recovery_succeeded)
            self.assertEqual(fake_extractor.password_attempt_count, 1)

            self.assertTrue(history_file.is_file())
            history_records = history_storage.read_all()
            self.assertEqual(len(history_records), 1)
            self.assertIs(history_records[0].status, TaskStatus.COMPLETED)
            self.assertTrue(history_records[0].success)
            self.assertEqual(history_records[0].summary, report.summary)

            log_files = list(log_directory.glob("task_*.log"))
            self.assertEqual(len(log_files), 1)
            log_content = log_files[0].read_text(encoding="utf-8")
            self.assertIn("任务开始", log_content)
            self.assertIn("Task 创建", log_content)
            self.assertIn("执行开始", log_content)
            self.assertIn("执行完成", log_content)
            self.assertIn("报告生成", log_content)
            self.assertIn("历史保存成功", log_content)
            self.assertNotIn("123456", log_content)


if __name__ == "__main__":
    unittest.main()
