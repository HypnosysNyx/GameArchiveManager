"""GameArchiveManager Beta 阶段的真实工具与完整流程集成测试。"""

import os
import hashlib
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock

from analyzer.archive_analyzer import ArchiveAnalyzer
from application.app_service import GameArchiveService
from config.settings import Settings
from coordinator.extraction_coordinator import ExtractionCoordinator
from coordinator.models import CoordinatorResult
from execution.models import ExtractionPlan
from execution.strategy import ExecutionStrategy
from extractor.dispatcher import ExtractorDispatcher
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from extractor.lz4 import Lz4Extractor
from extractor.seven_zip import SevenZipExtractor
from history.storage import HistoryStorage
from password.models import PasswordCandidate, PasswordSource
from pipeline.extraction_runner import ExtractionPipelineRunner
from recovery.password_executor import PasswordRetryExecutor
from recovery.password_recovery import PasswordRecoveryEngine
from security.archive_content_inspector import ArchiveContentInspector
from tools.models import ToolName
from tools.tool_manager import ToolManager


def create_zip(archive_path: Path, entries: dict[str, bytes | str]) -> None:
    """使用标准库创建受控 ZIP 测试文件。"""
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def run_external(command: list[str], timeout: int = 30) -> None:
    """运行无密码测试命令；失败时保留有限诊断信息。"""
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        output = "\n".join(
            part
            for part in (completed.stderr.strip(), completed.stdout.strip())
            if part
        )
        raise AssertionError(
            f"外部工具退出代码 {completed.returncode}: {output[:1000]}"
        )


class ControlledPasswordExtractor:
    """测试密码流程的受控适配器，不把密码传给系统进程。"""

    def __init__(self, correct_password: str) -> None:
        self.correct_password = correct_password
        self.attempted_passwords: list[str | None] = []

    def extract(
        self, plan: ExtractionPlan, password: str | None = None
    ) -> ExtractionResult:
        self.attempted_passwords.append(password)
        if password is None:
            status = ExtractionStatus.PASSWORD_REQUIRED
            message = "需要密码"
        elif password == self.correct_password:
            status = ExtractionStatus.SUCCESS
            message = "密码正确"
        else:
            status = ExtractionStatus.WRONG_PASSWORD
            message = "密码错误"
        return ExtractionResult(
            success=status is ExtractionStatus.SUCCESS,
            message=message,
            output_path=plan.output_path,
            tool_used=ToolName.SEVEN_ZIP,
            status=status,
        )


class ThreeLevelCoordinator:
    """生成 ZIP → RAR → 7Z 三层受控输出，验证 Pipeline 深度记录。"""

    def process(
        self,
        archive_path: str | Path,
        password_candidates=None,
        max_password_attempts: int = 20,
    ) -> CoordinatorResult:
        archive = Path(archive_path).resolve()
        output_path = archive.parent / f"{archive.stem}_extracted"
        output_path.mkdir(parents=True, exist_ok=False)
        if archive.name == "test.zip":
            (output_path / "inner.rar").write_bytes(
                b"Rar!\x1a\x07\x00inner"
            )
        elif archive.name == "inner.rar":
            (output_path / "data.7z").write_bytes(
                b"7z\xbc\xaf\x27\x1cdata"
            )
        else:
            (output_path / "data.txt").write_text(
                "recursive beta", encoding="utf-8"
            )
        extraction_result = ExtractionResult(
            True,
            "受控递归阶段成功",
            output_path,
            tool_used=ToolName.SEVEN_ZIP,
            status=ExtractionStatus.SUCCESS,
        )
        return CoordinatorResult(
            success=True,
            archive_path=archive,
            extraction_result=extraction_result,
            steps=[f"处理 {archive.name}"],
        )


class BetaIntegrationTest(unittest.TestCase):
    """验证 Beta 版本的真实格式、恢复、递归、复合和安全流程。"""

    @staticmethod
    def _require_tool(
        manager: ToolManager, tool_name: ToolName
    ) -> Path:
        status = manager.get_tool_status(tool_name)
        if not status.available:
            raise unittest.SkipTest(
                f"{tool_name.value} 工具文件不存在，跳过真实工具测试"
            )
        if not status.verified or status.path is None:
            raise unittest.SkipTest(
                f"{tool_name.value} 工具无法通过版本验证，跳过真实工具测试"
            )
        return status.path

    @staticmethod
    def _manager_with_optional_lz4() -> ToolManager:
        manager = ToolManager()
        status = manager.get_tool_status(ToolName.LZ4)
        if not status.verified:
            discovered = shutil.which("lz4.exe") or shutil.which("lz4")
            if discovered:
                manager.set_tool_path(ToolName.LZ4, discovered)
        return manager

    def test_real_zip_extraction(self) -> None:
        manager = ToolManager()
        self._require_tool(manager, ToolName.SEVEN_ZIP)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "game.zip"
            create_zip(archive_path, {"game.txt": "beta zip"})
            info = ArchiveAnalyzer().analyze(archive_path)
            plan = ExecutionStrategy().create_plan(info)

            result = SevenZipExtractor(tool_manager=manager).extract(plan)

            self.assertIs(result.status, ExtractionStatus.SUCCESS, result.error)
            self.assertEqual(
                (result.output_path / "game.txt").read_text(encoding="utf-8"),
                "beta zip",
            )

    def test_real_7z_extraction(self) -> None:
        manager = ToolManager()
        seven_zip_path = self._require_tool(manager, ToolName.SEVEN_ZIP)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "payload.txt"
            source.write_text("beta 7z", encoding="utf-8")
            archive_path = root / "payload.7z"
            run_external(
                [str(seven_zip_path), "a", "-t7z", str(archive_path), str(source), "-y"]
            )
            info = ArchiveAnalyzer().analyze(archive_path)
            plan = ExecutionStrategy().create_plan(info)

            result = SevenZipExtractor(tool_manager=manager).extract(plan)

            self.assertIs(result.status, ExtractionStatus.SUCCESS, result.error)
            self.assertEqual(
                (result.output_path / "payload.txt").read_text(encoding="utf-8"),
                "beta 7z",
            )

    def test_application_service_extracts_complete_7z_volume_set_once(self) -> None:
        """The public application entry must group .001/.002 into one task."""
        manager = ToolManager()
        seven_zip_path = self._require_tool(manager, ToolName.SEVEN_ZIP)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_root = root / "game"
            task_root.mkdir()
            source = task_root / "payload.bin"
            payload = os.urandom(8192)
            source.write_bytes(payload)
            archive_base = task_root / "PC14191.7z"
            run_external(
                [
                    str(seven_zip_path),
                    "a",
                    "-t7z",
                    str(archive_base),
                    str(source),
                    "-v1k",
                    "-y",
                ]
            )
            volumes = sorted(task_root.glob("PC14191.7z.*"))
            self.assertGreaterEqual(len(volumes), 2)

            progress_updates = []
            service = GameArchiveService(
                settings=Settings(seven_zip_path=str(seven_zip_path)),
                history_storage=HistoryStorage(root / "history.json"),
                log_directory=root / "logs",
            )
            report = service.execute_task(
                task_root,
                progress_callback=progress_updates.append,
            )

            self.assertEqual(report.total_archives, 1)
            self.assertEqual(report.success_count, 1)
            self.assertEqual(report.failed_count, 0)
            self.assertTrue(progress_updates)
            self.assertEqual(max(item.archive_count for item in progress_updates), 1)
            self.assertEqual(len(report.output_paths), 1)
            restored = report.output_paths[0] / source.name
            self.assertEqual(restored.read_bytes(), payload)

    def test_application_service_reports_lone_001_as_missing_002(self) -> None:
        """A missing continuation fails in volume detection before extraction."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_root = root / "game"
            task_root.mkdir()
            first_volume = task_root / "PC14191.7z.001"
            first_volume.write_bytes(b"7z\xbc\xaf\x27\x1cpartial")

            service = GameArchiveService(
                settings=Settings(),
                history_storage=HistoryStorage(root / "history.json"),
                log_directory=root / "logs",
            )
            report = service.execute_task(task_root)

            self.assertEqual(report.total_archives, 1)
            self.assertEqual(report.success_count, 0)
            self.assertEqual(report.failed_count, 1)
            self.assertEqual(len(report.failure_details), 1)
            failure = report.failure_details[0]
            self.assertEqual(failure.stage, "VOLUME_DETECTION")
            self.assertEqual(failure.error_type, "MISSING_VOLUME")
            self.assertEqual(failure.reason, "缺少分卷文件")
            self.assertEqual(
                failure.missing_files,
                [(task_root / "PC14191.7z.002").resolve()],
            )
            self.assertFalse((task_root / "PC14191.7z_extracted").exists())

    def test_application_service_reports_lone_part01_rar_as_missing_part02(self) -> None:
        """A lone .part01.rar fails in volume detection before extraction."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_root = root / "game"
            task_root.mkdir()
            first_volume = task_root / "sample.part01.rar"
            first_volume.write_bytes(b"Rar!\x1a\x07\x00partial")

            service = GameArchiveService(
                settings=Settings(),
                history_storage=HistoryStorage(root / "history.json"),
                log_directory=root / "logs",
            )
            report = service.execute_task(task_root)

            self.assertEqual(report.total_archives, 1)
            self.assertEqual(report.success_count, 0)
            self.assertEqual(report.failed_count, 1)
            self.assertEqual(len(report.failure_details), 1)
            failure = report.failure_details[0]
            self.assertEqual(failure.stage, "VOLUME_DETECTION")
            self.assertEqual(failure.error_type, "MISSING_VOLUME")
            self.assertEqual(failure.reason, "缺少分卷文件")
            self.assertEqual(
                failure.missing_files,
                [(task_root / "sample.part02.rar").resolve()],
            )
            self.assertFalse((task_root / "sample.part01.rar_extracted").exists())

    def test_application_service_repeats_archive_without_overwrite(self) -> None:
        """Repeated public-service runs keep old output and archive bytes intact."""
        manager = ToolManager()
        seven_zip_path = self._require_tool(manager, ToolName.SEVEN_ZIP)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_root = root / "game"
            task_root.mkdir()
            archive_path = task_root / "game.zip"
            create_zip(archive_path, {"payload.txt": "same content"})
            before_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            history_storage = HistoryStorage(root / "history.json")
            service = GameArchiveService(
                settings=Settings(seven_zip_path=str(seven_zip_path)),
                history_storage=history_storage,
                log_directory=root / "logs",
            )

            first_report = service.execute_task(task_root)
            second_report = service.execute_task(task_root)

            first_internal = task_root / "game_extracted"
            second_internal = task_root / "game_extracted_2"
            self.assertEqual(first_report.success_count, 1)
            self.assertEqual(second_report.success_count, 1)
            # Successful run-owned execution directories are temporary and are
            # removed only after the final user output has been organized.
            self.assertFalse(first_internal.exists())
            self.assertFalse(second_internal.exists())
            final_root = task_root.resolve() / "GameArchive_Output"
            self.assertEqual(
                first_report.output_paths,
                [final_root / "game"],
            )
            self.assertEqual(
                second_report.output_paths,
                [final_root / "game_2"],
            )
            self.assertEqual(
                (first_report.output_paths[0] / "payload.txt").read_text(
                    encoding="utf-8"
                ),
                "same content",
            )
            self.assertEqual(
                (second_report.output_paths[0] / "payload.txt").read_text(
                    encoding="utf-8"
                ),
                "same content",
            )
            self.assertEqual(first_report.residual_internal_directories, [])
            self.assertEqual(second_report.residual_internal_directories, [])
            after_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            self.assertEqual(after_hash, before_hash)
            history = history_storage.read_all()
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0].output_paths, first_report.output_paths)
            self.assertEqual(history[1].output_paths, second_report.output_paths)

    def test_real_rar_flow_when_tools_are_available(self) -> None:
        manager = ToolManager()
        self._require_tool(manager, ToolName.SEVEN_ZIP)
        winrar_path = self._require_tool(manager, ToolName.WINRAR)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "rar_payload.txt"
            source.write_text("beta rar", encoding="utf-8")
            archive_path = root / "payload.rar"
            run_external(
                [
                    str(winrar_path),
                    "a",
                    "-ep1",
                    "-y",
                    str(archive_path),
                    str(source),
                ]
            )
            dispatcher = ExtractorDispatcher(tool_manager=manager)

            result = ExtractionCoordinator(dispatcher=dispatcher).process(
                archive_path
            )

            self.assertTrue(result.success, result.error_message)
            self.assertEqual(
                (result.extraction_result.output_path / "rar_payload.txt").read_text(
                    encoding="utf-8"
                ),
                "beta rar",
            )

    def test_disguised_mp4_is_detected_as_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            disguised = Path(temp_dir) / "movie.mp4"
            create_zip(disguised, {"real.txt": "zip data"})

            info = ArchiveAnalyzer().analyze(disguised)

            self.assertEqual(info.extension, ".mp4")
            self.assertEqual(info.real_format, "ZIP")
            self.assertTrue(info.is_fake_extension)

    def test_password_candidate_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "protected.zip"
            archive_path.touch()
            plan = ExtractionPlan(
                archive_path=archive_path,
                detected_format="ZIP",
                selected_tool=ToolName.SEVEN_ZIP,
                output_path=root / "protected_extracted",
            )
            required = ExtractionResult(
                False,
                "需要密码",
                plan.output_path,
                status=ExtractionStatus.PASSWORD_REQUIRED,
            )
            extractor = ControlledPasswordExtractor("correct-code")
            recovery = PasswordRecoveryEngine(
                required,
                [PasswordCandidate("correct-code", PasswordSource.USER_INPUT)],
                archive_path,
                max_attempts=1,
            )

            result = PasswordRetryExecutor(
                plan, recovery, extractor, max_password_attempts=1
            ).execute()

            self.assertIs(result.status, ExtractionStatus.SUCCESS)
            self.assertEqual(extractor.attempted_passwords, [None, "correct-code"])

    def test_wrong_password_continues_to_next_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "protected.zip"
            archive_path.touch()
            plan = ExtractionPlan(
                archive_path=archive_path,
                detected_format="ZIP",
                selected_tool=ToolName.SEVEN_ZIP,
                output_path=root / "protected_extracted",
            )
            required = ExtractionResult(
                False,
                "需要密码",
                plan.output_path,
                status=ExtractionStatus.PASSWORD_REQUIRED,
            )
            extractor = ControlledPasswordExtractor("correct-code")
            candidates = [
                PasswordCandidate("wrong-code", PasswordSource.USER_INPUT),
                PasswordCandidate("correct-code", PasswordSource.USER_INPUT),
            ]
            recovery = PasswordRecoveryEngine(
                required, candidates, archive_path, max_attempts=2
            )

            result = PasswordRetryExecutor(
                plan, recovery, extractor, max_password_attempts=2
            ).execute()

            self.assertIs(result.status, ExtractionStatus.SUCCESS)
            self.assertEqual(
                extractor.attempted_passwords,
                [None, "wrong-code", "correct-code"],
            )

    def test_real_recursive_zip_rar_7z_records_depth(self) -> None:
        manager = ToolManager()
        seven_zip_path = self._require_tool(manager, ToolName.SEVEN_ZIP)
        winrar_path = self._require_tool(manager, ToolName.WINRAR)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_file = root / "data.txt"
            data_file.write_text("recursive beta", encoding="utf-8")
            data_7z = root / "data.7z"
            run_external(
                [str(seven_zip_path), "a", "-t7z", str(data_7z), str(data_file), "-y"]
            )
            inner_rar = root / "inner.rar"
            run_external(
                [str(winrar_path), "a", "-y", str(inner_rar), str(data_7z)]
            )
            outer_zip = root / "test.zip"
            with zipfile.ZipFile(outer_zip, "w") as archive:
                archive.write(inner_rar, "inner.rar")

            settings = Settings(ignore_android=False, ignore_AZ=False)
            dispatcher = ExtractorDispatcher(
                tool_manager=manager, settings=settings
            )
            coordinator = ExtractionCoordinator(
                dispatcher=dispatcher, settings=settings
            )
            runner = ExtractionPipelineRunner(
                coordinator=coordinator, settings=settings
            )

            result = runner.run(outer_zip)

            self.assertTrue(result.success, result.steps)
            depths = {
                record.archive_path.name: record.depth
                for record in result.execution_records
            }
            self.assertEqual(depths["test.zip"], 0)
            self.assertEqual(depths["inner.rar"], 1)
            self.assertEqual(depths["data.7z"], 2)

    def test_pipeline_extracts_zip_disguised_as_jpg_inside_7z(self) -> None:
        """Recursive discovery must trust the ZIP header, not the .jpg suffix."""
        manager = ToolManager()
        seven_zip_path = self._require_tool(manager, ToolName.SEVEN_ZIP)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            staging = root / "staging"
            staging.mkdir()
            disguised_zip = staging / "payload.jpg"
            create_zip(disguised_zip, {"final.txt": "restored"})
            ordinary_image = staging / "cover.jpg"
            ordinary_image.write_bytes(b"\xff\xd8\xff\xe0ordinary-jpeg")
            outer_archive = root / "outer.7z"
            run_external(
                [
                    str(seven_zip_path),
                    "a",
                    "-t7z",
                    str(outer_archive),
                    str(disguised_zip),
                    str(ordinary_image),
                    "-y",
                ]
            )

            runner = ExtractionPipelineRunner(
                settings=Settings(seven_zip_path=str(seven_zip_path))
            )
            result = runner.run(outer_archive)

            self.assertTrue(result.success, result.steps)
            self.assertEqual(len(result.execution_records), 2)
            self.assertEqual(
                [record.depth for record in result.execution_records],
                [0, 1],
            )
            nested_record = result.execution_records[1]
            self.assertEqual(nested_record.archive_path.suffix, ".jpg")
            self.assertEqual(
                nested_record.coordinator_result.extraction_result.status,
                ExtractionStatus.SUCCESS,
            )
            self.assertEqual(
                (nested_record.output_path / "final.txt").read_text(
                    encoding="utf-8"
                ),
                "restored",
            )
            self.assertFalse(
                any(
                    record.archive_path.name == "cover.jpg"
                    for record in result.execution_records
                )
            )

    def test_pipeline_finishes_after_extracting_normal_game_files(self) -> None:
        """Executable/library marker bytes must not expand the recursive queue."""
        manager = ToolManager()
        self._require_tool(manager, ToolName.SEVEN_ZIP)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_archive = root / "game.zip"
            create_zip(
                game_archive,
                {
                    "Game.exe": b"MZ\x00\x00normal-executable",
                    "Game_Data/game.dll": (
                        b"MZ\x00library-PK\x03\x04-random-marker"
                    ),
                    "Game_Data/data.assets": b"unity-assets-Rar!-marker",
                },
            )
            settings = Settings(ignore_android=False, ignore_AZ=False)
            dispatcher = ExtractorDispatcher(
                tool_manager=manager,
                settings=settings,
            )
            coordinator = ExtractionCoordinator(
                dispatcher=dispatcher,
                settings=settings,
            )
            runner = ExtractionPipelineRunner(
                coordinator=coordinator,
                settings=settings,
            )

            result = runner.run(game_archive)

            self.assertTrue(result.success, result.steps)
            self.assertEqual(len(result.execution_records), 1)
            self.assertEqual(result.execution_records[0].depth, 0)
            output = result.execution_records[0].output_path
            self.assertTrue((output / "Game.exe").is_file())
            self.assertTrue((output / "Game_Data" / "game.dll").is_file())

    def test_embedded_jpeg_rar_is_carved_verified_and_extracted(self) -> None:
        """A JPEG prefix plus a real RAR must re-enter the normal pipeline."""
        manager = ToolManager()
        self._require_tool(manager, ToolName.SEVEN_ZIP)
        winrar_path = self._require_tool(manager, ToolName.WINRAR)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = root / "payload.txt"
            payload.write_text("embedded archive restored", encoding="utf-8")
            hidden_rar = root / "hidden.rar"
            run_external(
                [
                    str(winrar_path),
                    "a",
                    "-ep1",
                    "-y",
                    str(hidden_rar),
                    str(payload),
                ]
            )
            jpeg_rar = root / "picture.jpg"
            jpeg_prefix = b"\xff\xd8\xff\xe0embedded-test\xff\xd9"
            jpeg_rar.write_bytes(jpeg_prefix + hidden_rar.read_bytes())

            archive_info = ArchiveAnalyzer().analyze(jpeg_rar)
            plan = ExecutionStrategy().create_plan(archive_info)

            self.assertEqual(archive_info.real_format, "UNKNOWN")
            self.assertTrue(archive_info.is_embedded_archive)
            self.assertEqual(archive_info.embedded_offset, len(jpeg_prefix))
            self.assertEqual(archive_info.embedded_container_format, "RAR")
            self.assertEqual(archive_info.container_chain, ["JPEG", "RAR"])
            self.assertTrue(plan.is_composite)
            self.assertTrue(plan.is_embedded_archive)

            settings = Settings(ignore_android=False, ignore_AZ=False)
            dispatcher = ExtractorDispatcher(
                tool_manager=manager,
                settings=settings,
            )
            coordinator = ExtractionCoordinator(
                dispatcher=dispatcher,
                settings=settings,
            )
            runner = ExtractionPipelineRunner(
                coordinator=coordinator,
                settings=settings,
            )
            result = runner.run(jpeg_rar)

            self.assertTrue(result.success, result.steps)
            self.assertEqual(len(result.execution_records), 2)
            self.assertEqual(
                [record.depth for record in result.execution_records],
                [0, 1],
            )
            carved_record = result.execution_records[1]
            self.assertEqual(carved_record.archive_path.suffix, ".rar")
            self.assertEqual(
                (carved_record.output_path / "payload.txt").read_text(
                    encoding="utf-8"
                ),
                "embedded archive restored",
            )

    def test_encrypted_rar5_embedded_in_jpeg_uses_password_recovery(self) -> None:
        """A verified RAR5 encryption header must reach existing recovery."""
        manager = ToolManager()
        self._require_tool(manager, ToolName.SEVEN_ZIP)
        winrar_path = self._require_tool(manager, ToolName.WINRAR)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = root / "secret.txt"
            payload.write_text("encrypted embedded restored", encoding="utf-8")
            hidden_rar = root / "encrypted.rar"
            run_external(
                [
                    str(winrar_path),
                    "a",
                    "-ep1",
                    "-y",
                    "-hp123456",
                    str(hidden_rar),
                    str(payload),
                ]
            )
            jpeg_prefix = b"\xff\xd8\xff\xe0encrypted-host\xff\xd9"
            jpeg_rar = root / "encrypted.jpg"
            jpeg_rar.write_bytes(jpeg_prefix + hidden_rar.read_bytes())

            archive_info = ArchiveAnalyzer().analyze(jpeg_rar)

            self.assertTrue(archive_info.is_embedded_archive)
            self.assertEqual(archive_info.embedded_offset, len(jpeg_prefix))
            self.assertEqual(archive_info.embedded_container_format, "RAR")
            self.assertEqual(
                archive_info.embedded_validation_status,
                "VALID_ENCRYPTED",
            )

            settings = Settings(ignore_android=False, ignore_AZ=False)
            coordinator = ExtractionCoordinator(
                dispatcher=ExtractorDispatcher(
                    tool_manager=manager,
                    settings=settings,
                ),
                settings=settings,
            )
            result = ExtractionPipelineRunner(
                coordinator=coordinator,
                settings=settings,
            ).run(
                jpeg_rar,
                password_candidates=[
                    PasswordCandidate(
                        password="123456",
                        source=PasswordSource.USER_INPUT,
                    )
                ],
            )

            self.assertTrue(result.success, result.steps)
            restored_files = [
                record.output_path / "secret.txt"
                for record in result.execution_records
                if record.output_path is not None
                and (record.output_path / "secret.txt").is_file()
            ]
            self.assertEqual(len(restored_files), 1)
            self.assertEqual(
                restored_files[0].read_text(encoding="utf-8"),
                "encrypted embedded restored",
            )

    def test_recursive_zip_rar_7z_depth_is_always_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outer_zip = root / "test.zip"
            create_zip(outer_zip, {"placeholder.txt": "controlled"})
            settings = Settings(ignore_android=False, ignore_AZ=False)
            runner = ExtractionPipelineRunner(
                coordinator=ThreeLevelCoordinator(), settings=settings
            )

            result = runner.run(outer_zip)

            self.assertTrue(result.success, result.steps)
            self.assertEqual(
                [(record.archive_path.name, record.depth) for record in result.execution_records],
                [("test.zip", 0), ("inner.rar", 1), ("data.7z", 2)],
            )

    def test_real_lz4_extraction_when_tool_is_available(self) -> None:
        manager = self._manager_with_optional_lz4()
        lz4_path = self._require_tool(manager, ToolName.LZ4)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "payload"
            source.write_text("beta lz4", encoding="utf-8")
            archive_path = root / "payload.lz4"
            run_external(
                [str(lz4_path), "-f", str(source), str(archive_path)]
            )
            info = ArchiveAnalyzer().analyze(archive_path)
            plan = ExecutionStrategy().create_plan(info)

            result = Lz4Extractor(tool_manager=manager).extract(plan)

            self.assertIs(result.status, ExtractionStatus.SUCCESS, result.error)
            self.assertEqual(
                (result.output_path / "payload").read_text(encoding="utf-8"),
                "beta lz4",
            )

    def test_composite_simulated_lz4_output_rar(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outer = root / "PC.rar.lz4"
            outer.write_bytes(b"\x04\x22\x4d\x18hint-Rar!-data")
            lz4 = Mock()
            seven_zip = Mock()
            winrar = Mock()

            def lz4_success(plan, password=None):
                plan.output_path.mkdir()
                (plan.output_path / plan.archive_path.stem).write_bytes(
                    b"Rar!\x1a\x07\x00inner"
                )
                return ExtractionResult(
                    True,
                    "LZ4 success",
                    plan.output_path,
                    tool_used=ToolName.LZ4,
                    status=ExtractionStatus.SUCCESS,
                )

            def rar_success(plan, password=None):
                plan.output_path.mkdir()
                return ExtractionResult(
                    True,
                    "RAR success",
                    plan.output_path,
                    tool_used=ToolName.SEVEN_ZIP,
                    status=ExtractionStatus.SUCCESS,
                )

            lz4.extract.side_effect = lz4_success
            seven_zip.extract.side_effect = rar_success
            dispatcher = ExtractorDispatcher(
                seven_zip_extractor=seven_zip,
                winrar_extractor=winrar,
                lz4_extractor=lz4,
            )

            result = ExtractionCoordinator(dispatcher=dispatcher).process(outer)

            self.assertTrue(result.success, result.error_message)
            self.assertEqual(
                lz4.extract.call_args.args[0].container_chain,
                ["LZ4", "RAR"],
            )
            self.assertEqual(
                seven_zip.extract.call_args.args[0].detected_format, "RAR"
            )

    def test_path_traversal_zip_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "unsafe.zip"
            create_zip(archive_path, {"../escape.txt": "blocked"})
            info = ArchiveAnalyzer().analyze(archive_path)
            content = ArchiveContentInspector().inspect(info)

            plan = ExecutionStrategy().create_plan(info, content)

            self.assertFalse(plan.can_execute)
            self.assertFalse((root.parent / "escape.txt").exists())

    def test_archive_file_count_limit_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "many.zip"
            create_zip(
                archive_path,
                {"one.txt": "1", "two.txt": "2", "three.txt": "3"},
            )
            info = ArchiveAnalyzer().analyze(archive_path)
            content = ArchiveContentInspector().inspect(info)
            strategy = ExecutionStrategy(Settings(max_extracted_files=2))

            plan = strategy.create_plan(info, content)

            self.assertFalse(plan.can_execute)
            self.assertIn("文件数量", plan.message)

    def test_archive_size_limit_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "large.zip"
            create_zip(archive_path, {"data.bin": b"x" * 1024})
            info = ArchiveAnalyzer().analyze(archive_path)
            strategy = ExecutionStrategy(Settings(max_archive_size_mb=0))

            plan = strategy.create_plan(info)

            self.assertFalse(plan.can_execute)
            self.assertIn("大小超过限制", plan.message)


if __name__ == "__main__":
    unittest.main()
