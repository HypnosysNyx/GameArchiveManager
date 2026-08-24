"""Regression tests for high-impact platform skip boundaries."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from config.settings import Settings
from coordinator.models import CoordinatorResult
from extractor.extractor_models import ExtractionResult, ExtractionStatus
from history.storage import HistoryStorage
from pipeline.extraction_runner import ExtractionPipelineRunner
from rules.platform_filter import PlatformFilter
from rules.platform_rules import is_az_name
from task.models import Task
from task.task_analyzer import TaskAnalyzer
from task.task_executor import TaskExecutor


def create_zip(path: Path, member: str = "payload.txt") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, "controlled")


class PlatformPipelineCoordinator:
    """Create one controlled recursive output tree without external tools."""

    def __init__(self, initial_archive: Path) -> None:
        self.initial_archive = initial_archive.resolve()

    def process(self, archive_path, password_candidates=None, **kwargs):
        archive = Path(archive_path).resolve()
        output = archive.parent / f"{archive.stem}_extracted"
        output.mkdir()
        if archive == self.initial_archive:
            create_zip(output / "AZ" / "mobile.zip")
            create_zip(output / "crazy_game" / "pc.zip")
            create_zip(output / "Android" / "android.zip")
            create_zip(output / "安卓资源" / "update.zip")
        return CoordinatorResult(
            success=True,
            archive_path=archive,
            extraction_result=ExtractionResult(
                success=True,
                message="controlled",
                output_path=output,
                status=ExtractionStatus.SUCCESS,
            ),
        )


class PlatformTokenTests(unittest.TestCase):
    def test_supported_az_labels_are_tokens(self) -> None:
        for value in ("AZ", "az", "[AZ]", "AZ版", "AZ版本", "AZ_", "_AZ", "AZ-patch"):
            with self.subTest(value=value):
                self.assertTrue(is_az_name(value))

    def test_ordinary_words_containing_az_are_not_tokens(self) -> None:
        for value in ("crazy", "amazing_game", "blazer", "gazette"):
            with self.subTest(value=value):
                self.assertFalse(is_az_name(value))


class PlatformFilterScopeTests(unittest.TestCase):
    def test_az_directory_is_skipped_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for directory in ("AZ", "az"):
                with self.subTest(directory=directory):
                    result = PlatformFilter(
                        Settings(ignore_AZ=True)
                    ).check(
                        root / directory / "game.rar", root_path=root
                    )
                    self.assertTrue(result.skipped)
                    self.assertIn(directory, result.reason)

    def test_az_tagged_archive_name_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = PlatformFilter(Settings(ignore_AZ=True)).check(
                root / "AZ_patch.zip", root_path=root
            )
            self.assertTrue(result.skipped)
            self.assertIn("AZ_patch.zip", result.reason)

    def test_ordinary_content_names_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for directory in ("crazy", "amazing_game", "blazer", "gazette"):
                with self.subTest(directory=directory):
                    result = PlatformFilter(
                        Settings(ignore_AZ=True)
                    ).check(
                        root / directory / "game.rar", root_path=root
                    )
                    self.assertFalse(result.skipped)

    def test_az_in_parent_outside_task_root_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_root = Path(temp_dir) / "tmp_az_random" / "task_root"
            archive = task_root / "PC" / "game.rar"
            result = PlatformFilter(Settings(ignore_AZ=True)).check(
                archive, root_path=task_root
            )
            self.assertFalse(result.skipped)

    def test_username_like_parent_outside_task_root_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_root = Path(temp_dir) / "az_user" / "Desktop" / "task_root"
            archive = task_root / "PC" / "game.rar"
            result = PlatformFilter(Settings(ignore_AZ=True)).check(
                archive, root_path=task_root
            )
            self.assertFalse(result.skipped)

    def test_without_root_only_archive_name_is_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "az_user" / "PC" / "game.rar"
            self.assertFalse(
                PlatformFilter(Settings(ignore_AZ=True)).check(archive).skipped
            )

    def test_android_and_chinese_android_behavior_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for directory in ("Android", "Android_game", "安卓资源"):
                with self.subTest(directory=directory):
                    result = PlatformFilter(
                        Settings(ignore_android=True)
                    ).check(
                        root / directory / "game.rar", root_path=root
                    )
                    self.assertTrue(result.skipped)
                    self.assertIn("Android/安卓", result.reason)


class PlatformScanInteractionTests(unittest.TestCase):
    def test_initial_scan_marks_real_az_but_not_crazy_or_amazing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "task_root"
            az_archive = root / "AZ" / "mobile.zip"
            crazy_archive = root / "crazy" / "game.zip"
            amazing_archive = root / "amazing_game" / "patch.zip"
            for archive in (az_archive, crazy_archive, amazing_archive):
                create_zip(archive)
            analyzer = TaskAnalyzer(
                history_storage=HistoryStorage(root / "history.json"),
                settings=Settings(ignore_AZ=True),
            )

            result = analyzer.analyze(Task(task_path=root))

            self.assertIsNotNone(
                TaskExecutor._get_skip_reason(az_archive, result.ignored_items)
            )
            self.assertIsNone(
                TaskExecutor._get_skip_reason(crazy_archive, result.ignored_items)
            )
            self.assertIsNone(
                TaskExecutor._get_skip_reason(amazing_archive, result.ignored_items)
            )

    def test_explicit_archive_input_keeps_existing_override_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "AZ" / "game.zip"
            create_zip(archive)
            analyzer = TaskAnalyzer(
                history_storage=HistoryStorage(Path(temp_dir) / "history.json")
            )

            result = analyzer.analyze(Task(task_path=archive))

            self.assertEqual([item.file_path for item in result.archive_results], [archive.resolve()])
            self.assertEqual(result.ignored_items, [])

    def test_pipeline_scan_skips_platform_tokens_and_runs_ordinary_word(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "tmp_az_random" / "task_root"
            initial = root / "root.zip"
            create_zip(initial)
            runner = ExtractionPipelineRunner(
                coordinator=PlatformPipelineCoordinator(initial),
                settings=Settings(ignore_android=True, ignore_AZ=True),
            )

            result = runner.run(initial)

            processed_names = {
                record.archive_path.name for record in result.execution_records
            }
            skipped_names = {
                record.archive_path.name for record in result.skipped_archives
            }
            self.assertEqual(processed_names, {"root.zip", "pc.zip"})
            self.assertEqual(
                skipped_names, {"mobile.zip", "android.zip", "update.zip"}
            )
            az_record = next(
                item for item in result.skipped_archives
                if item.archive_path.name == "mobile.zip"
            )
            self.assertIn("AZ", az_record.reason)
            self.assertNotIn("crazy", az_record.reason)


if __name__ == "__main__":
    unittest.main()
