"""Release-default platform policy and APK characterization tests."""

import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

from analyzer.archive_analyzer import ArchiveAnalyzer
from application.app_service import GameArchiveService
from config.config_loader import ConfigLoader
from config.settings import Settings
from coordinator.models import CoordinatorResult
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from execution.strategy import ExecutionStrategy
from history.storage import HistoryStorage
from history.models import TaskHistoryRecord
from organizer.models import ExtractionOutputSource
from organizer.output_organizer import OutputOrganizer
from pipeline.extraction_runner import ExtractionPipelineRunner
from report.task_report import ReportGenerator
from rules.container_policy import ContainerRole
from scanner.archive_finder import ArchiveFinder, ArchiveScanMode
from task.models import Task
from task.models import TaskStatus
from task.task_analyzer import TaskAnalyzer
from task.task_executor import TaskExecutor


def create_zip(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", "manifest")
        archive.writestr("classes.dex", b"dex")


class ApkCharacterizationCoordinator:
    """Expose which analyzer-confirmed files the Pipeline executes."""

    def __init__(self, initial_archive: Path) -> None:
        self.initial_archive = initial_archive.resolve()
        self.processed: list[Path] = []

    def process(self, archive_path, password_candidates=None, **kwargs):
        archive = Path(archive_path).resolve()
        self.processed.append(archive)
        output = archive.parent / f"{archive.name}_characterization_output"
        output.mkdir()
        if archive == self.initial_archive:
            create_zip(output / "Android" / "game.apk")
            create_zip(output / "nested.zip")
            (output / "Android" / "readme.txt").write_text(
                "keep apk", encoding="utf-8"
            )
        return CoordinatorResult(
            success=True,
            archive_path=archive,
            extraction_result=ExtractionResult(
                success=True,
                message="characterization",
                output_path=output,
                status=ExtractionStatus.SUCCESS,
            ),
        )


class DefaultPlatformPolicyTests(unittest.TestCase):
    def _analyze(self, root: Path, settings: Settings | None = None):
        return TaskAnalyzer(
            history_storage=HistoryStorage(root / "history.json"),
            settings=settings,
        ).analyze(Task(task_path=root))

    def test_default_settings_preserve_android_and_az(self) -> None:
        settings = Settings()

        self.assertFalse(settings.ignore_android)
        self.assertFalse(settings.ignore_AZ)

    def test_default_android_and_chinese_android_are_not_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            android = root / "Android" / "game.apk"
            chinese = root / "安卓" / "game.apk"
            create_zip(android)
            create_zip(chinese)

            result = self._analyze(root)

            self.assertEqual(result.ignored_items, [])
            self.assertEqual(result.archive_results, [])
            self.assertEqual(
                {item.path for item in result.container_role_decisions},
                {android.resolve(), chinese.resolve()},
            )
            self.assertTrue(
                all(
                    item.role is ContainerRole.CONTENT_CONTAINER
                    for item in result.container_role_decisions
                )
            )

    def test_default_az_is_not_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "AZ" / "game.rar"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"Rar!\x1a\x07\x00controlled")

            result = self._analyze(root)

            self.assertEqual(result.ignored_items, [])
            self.assertEqual(
                [item.file_path for item in result.archive_results],
                [archive.resolve()],
            )

    def test_explicit_android_ignore_remains_effective(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archives = [
                root / "Android" / "game.apk",
                root / "安卓资源" / "game.apk",
            ]
            for archive in archives:
                create_zip(archive)

            result = self._analyze(
                root, Settings(ignore_android=True, ignore_AZ=False)
            )

            for archive in archives:
                self.assertIsNotNone(
                    TaskExecutor._get_skip_reason(
                        archive, result.ignored_items
                    )
                )

    def test_explicit_az_ignore_keeps_token_matching_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skipped = [root / "AZ" / "one.zip", root / "AZ_patch.zip"]
            preserved = [
                root / name / "game.zip"
                for name in ("crazy", "amazing", "blazer", "gazette")
            ]
            for archive in [*skipped, *preserved]:
                create_zip(archive)

            result = self._analyze(
                root, Settings(ignore_android=False, ignore_AZ=True)
            )

            for archive in skipped:
                self.assertIsNotNone(
                    TaskExecutor._get_skip_reason(
                        archive, result.ignored_items
                    )
                )
            for archive in preserved:
                self.assertIsNone(
                    TaskExecutor._get_skip_reason(
                        archive, result.ignored_items
                    )
                )

    def test_config_explicit_true_overrides_new_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps({"ignore_android": True, "ignore_AZ": True}),
                encoding="utf-8",
            )

            settings = ConfigLoader(config_path).load()
            service = GameArchiveService(
                config_path=config_path,
                history_storage=HistoryStorage(
                    Path(temp_dir) / "service_history.json"
                ),
                log_directory=Path(temp_dir) / "logs",
            )

            self.assertTrue(settings.ignore_android)
            self.assertTrue(settings.ignore_AZ)
            self.assertTrue(service.settings.ignore_android)
            self.assertTrue(service.settings.ignore_AZ)
            self.assertTrue(
                service.task_executor.task_analyzer.settings.ignore_android
            )
            self.assertTrue(
                service.task_executor.task_analyzer.settings.ignore_AZ
            )


class ContentContainerPolicyTests(unittest.TestCase):
    def test_apk_analyzer_fact_remains_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            apk = Path(temp_dir) / "sample.apk"
            create_zip(apk)

            info = ArchiveAnalyzer().analyze(apk)

            self.assertEqual(info.real_format, "ZIP")
            self.assertEqual(info.extension, ".apk")
            self.assertTrue(info.is_fake_extension)
            self.assertEqual(info.confidence, 1.0)

    def test_apk_is_preserved_in_initial_and_pipeline_scans(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            apk = root / "Android" / "sample.apk"
            create_zip(apk)

            initial_finder = ArchiveFinder()
            pipeline_finder = ArchiveFinder()
            initial = initial_finder.find(root, ArchiveScanMode.INITIAL_SCAN)
            pipeline = pipeline_finder.find(root, ArchiveScanMode.PIPELINE_SCAN)

            self.assertEqual(initial, [])
            self.assertEqual(pipeline, [])
            for finder in (initial_finder, pipeline_finder):
                self.assertEqual(len(finder.last_container_role_decisions), 1)
                decision = finder.last_container_role_decisions[0]
                self.assertIs(decision.role, ContainerRole.CONTENT_CONTAINER)
                self.assertEqual(
                    decision.reason, "KNOWN_CONTENT_CONTAINER_EXTENSION"
                )

    def test_pipeline_preserves_apk_but_executes_normal_nested_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            initial = root / "Android.rar"
            initial.write_bytes(b"Rar!\x1a\x07\x00controlled")
            coordinator = ApkCharacterizationCoordinator(initial)
            runner = ExtractionPipelineRunner(
                coordinator=coordinator,
                settings=Settings(),
            )

            result = runner.run(initial)

            self.assertTrue(result.success)
            self.assertEqual(
                [path.name for path in coordinator.processed],
                ["Android.rar", "nested.zip"],
            )
            self.assertEqual(
                [record.depth for record in result.execution_records],
                [0, 1],
            )
            apk = next(initial.parent.rglob("game.apk"))
            self.assertTrue(apk.exists())
            self.assertTrue(
                any(
                    item.path == apk.resolve()
                    and item.role is ContainerRole.CONTENT_CONTAINER
                    for item in result.container_role_decisions
                )
            )
            report = ReportGenerator().generate(result)
            self.assertTrue(
                any(
                    item.path == apk.resolve()
                    and item.reason == "KNOWN_CONTENT_CONTAINER_EXTENSION"
                    for item in report.container_role_decisions
                )
            )

    def test_explicit_apk_overrides_automatic_preservation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            apk = Path(temp_dir) / "game.apk"
            create_zip(apk)
            finder = ArchiveFinder()

            found = finder.find(apk, ArchiveScanMode.INITIAL_SCAN)
            plan = ExecutionStrategy().create_plan(found[0])

            self.assertEqual([item.file_path for item in found], [apk.resolve()])
            self.assertEqual(plan.detected_format, "ZIP")
            self.assertTrue(plan.can_execute)
            self.assertTrue(finder.last_container_role_decisions[0].explicit)
            self.assertEqual(
                finder.last_container_role_decisions[0].reason,
                "EXPLICIT_USER_INPUT",
            )

    def test_known_zip_content_containers_are_preserved(self) -> None:
        for extension in (".docx", ".xlsx", ".pptx", ".epub", ".jar"):
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                container = root / f"content{extension}"
                create_zip(container)
                info = ArchiveAnalyzer().analyze(container)
                finder = ArchiveFinder()

                found = finder.find(root, ArchiveScanMode.PIPELINE_SCAN)
                decision = finder.last_container_role_decisions[0]

                self.assertEqual(info.real_format, "ZIP")
                self.assertEqual(found, [])
                self.assertIs(decision.role, ContainerRole.CONTENT_CONTAINER)
                self.assertTrue(container.exists())

    def test_reused_finder_keeps_content_container_decisions_task_local(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            apk = first / "game.apk"
            document = second / "guide.docx"
            create_zip(apk)
            create_zip(document)
            finder = ArchiveFinder()

            self.assertEqual(
                finder.find(first, ArchiveScanMode.PIPELINE_SCAN), []
            )
            first_decisions = finder.last_container_role_decisions.copy()
            self.assertEqual(
                finder.find(second, ArchiveScanMode.PIPELINE_SCAN), []
            )
            second_decisions = finder.last_container_role_decisions.copy()

            self.assertEqual([item.path for item in first_decisions], [apk.resolve()])
            self.assertEqual(
                [item.path for item in second_decisions], [document.resolve()]
            )
            self.assertTrue(
                all(
                    item.role is ContainerRole.CONTENT_CONTAINER
                    for item in first_decisions + second_decisions
                )
            )

    def test_save_is_not_globally_classified_as_content_container(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            save = root / "manual.save"
            create_zip(save)

            found = ArchiveFinder().find(root, ArchiveScanMode.INITIAL_SCAN)

            self.assertEqual([item.file_path for item in found], [save.resolve()])

    def test_fake_extension_zip_remains_archive_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            disguised = root / "payload.bin"
            create_zip(disguised)

            found = ArchiveFinder().find(root, ArchiveScanMode.PIPELINE_SCAN)

            self.assertEqual([item.file_path for item in found], [disguised.resolve()])

    def test_content_container_is_delivered_intact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "documents.rar"
            archive.write_bytes(b"Rar!\x1a\x07\x00controlled")
            physical = root / "documents.rar_extracted"
            physical.mkdir()
            apk = physical / "Android" / "game.apk"
            create_zip(apk)
            (physical / "Android" / "readme.txt").write_text(
                "user content", encoding="utf-8"
            )
            original_bytes = apk.read_bytes()

            organized, _ = OutputOrganizer().resolve_and_organize(
                root,
                [
                    ExtractionOutputSource(
                        physical_output_path=physical,
                        archive_path=archive,
                        runtime_owned=True,
                    )
                ],
                runtime_owned_paths=[physical],
            )

            self.assertEqual(len(organized), 1)
            delivered = list(organized[0].final_output_path.rglob("game.apk"))
            self.assertEqual(len(delivered), 1)
            self.assertEqual(delivered[0].read_bytes(), original_bytes)
            self.assertEqual(apk.read_bytes(), original_bytes)

    def test_container_role_diagnostic_round_trips_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            apk = root / "game.apk"
            create_zip(apk)
            finder = ArchiveFinder()
            finder.find(root, ArchiveScanMode.INITIAL_SCAN)
            decision = finder.last_container_role_decisions[0]
            storage = HistoryStorage(root / "history.json")
            now = datetime.now().astimezone()

            storage.save(
                TaskHistoryRecord(
                    task_id="container-role",
                    task_path=root,
                    status=TaskStatus.COMPLETED,
                    created_time=now,
                    completed_time=now,
                    success=True,
                    summary="content container preserved",
                    container_role_decisions=[decision],
                )
            )
            restored = storage.read_all()[0].container_role_decisions[0]

            self.assertEqual(restored, decision)


if __name__ == "__main__":
    unittest.main()
