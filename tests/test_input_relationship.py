"""Regression tests for input relationships and duplicate final content."""

import subprocess
import tempfile
import unittest
from io import StringIO
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from analyzer.models import ArchiveInfo
from history.models import TaskHistoryRecord
from history.storage import HistoryStorage
from organizer.duplicate_content import (
    DuplicateContentRecord,
    DuplicateContentDetector,
    DuplicateContentStatus,
)
from organizer.models import ExtractionOutputSource
from organizer.output_organizer import OutputOrganizer
from pipeline.models import PipelineResult
from task.input_relationship import (
    InputArchiveRelationship,
    InputArchiveRelationshipResolver,
    InputRelationshipResolution,
    InputRelationshipType,
    RelationshipConfidence,
    RelationshipVerificationStatus,
)
from task.models import Task, TaskStatus
from task.task_analyzer import AnalysisStatus, TaskAnalysisResult
from task.task_executor import TaskExecutor
from tools.models import ToolName
from tools.tool_manager import ToolManager


def archive_info(path: Path, real_format: str, chain: list[str]) -> ArchiveInfo:
    return ArchiveInfo(
        file_path=path.resolve(),
        extension=path.suffix,
        real_format=real_format,
        is_fake_extension=False,
        confidence=1.0,
        container_chain=chain,
    )


class StaticAnalyzer:
    def __init__(self, archives: list[ArchiveInfo]) -> None:
        self.archives = archives

    def analyze(self, task: Task) -> TaskAnalysisResult:
        selected = self.archives
        if task.explicit_archive_path is not None:
            selected = [
                item
                for item in self.archives
                if item.file_path == task.explicit_archive_path.resolve()
            ]
        return TaskAnalysisResult(
            task_id=task.task_id,
            task_path=task.task_path,
            archive_results=selected.copy(),
            analysis_status=AnalysisStatus.COMPLETED,
        )


class RecordingPipelineRunner:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def run(self, initial_archive, **_kwargs) -> PipelineResult:
        self.paths.append(Path(initial_archive).resolve())
        return PipelineResult(success=True)


class InputRelationshipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool_manager = ToolManager()
        info = self.tool_manager.get_tool_status(ToolName.LZ4)
        if not info.verified or info.path is None:
            self.skipTest("A verified LZ4 tool is required for stream verification")
        self.lz4_path = info.path

    def _pair(self, root: Path, same: bool = True):
        inner = root / "inner.rar"
        decoded_source = root / "decoded.rar"
        outer = root / "inner.rar.lz4"
        inner.write_bytes(b"Rar!\x1a\x07\x01\x00" + b"A" * 4096)
        decoded_source.write_bytes(
            inner.read_bytes() if same else b"Rar!\x1a\x07\x01\x00" + b"B" * 4096
        )
        subprocess.run(
            [str(self.lz4_path), "-f", str(decoded_source), str(outer)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        decoded_source.unlink()
        return (
            archive_info(inner, "RAR", ["RAR"]),
            archive_info(outer, "LZ4", ["LZ4", "RAR"]),
        )

    def _executor(self, archives):
        runner = RecordingPipelineRunner()
        resolver = InputArchiveRelationshipResolver(
            tool_manager=self.tool_manager
        )
        executor = TaskExecutor(
            task_analyzer=StaticAnalyzer(archives),
            pipeline_runner=runner,
            input_relationship_resolver=resolver,
        )
        return executor, runner

    def test_confirmed_outer_inner_uses_one_canonical_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inner, outer = self._pair(root)
            executor, runner = self._executor([inner, outer])

            result = executor.execute(Task(task_path=root))

            self.assertEqual([inner.file_path], runner.paths)
            self.assertEqual([outer.file_path], result.suppressed_redundant_inputs)
            relationship = result.analysis_result.input_relationships[0]
            self.assertIs(
                relationship.relationship_type,
                InputRelationshipType.CONFIRMED_OUTER_CONTAINS_EXISTING_INNER,
            )
            self.assertIs(
                relationship.verification_status,
                RelationshipVerificationStatus.VERIFIED,
            )
            self.assertGreater(relationship.verification_bytes_read, 0)

    def test_explicit_outer_overrides_sibling_relationship(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inner, outer = self._pair(root)
            executor, runner = self._executor([inner, outer])

            executor.execute(
                Task(task_path=root, explicit_archive_path=outer.file_path)
            )

            self.assertEqual([outer.file_path], runner.paths)

    def test_process_all_inputs_executes_both(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inner, outer = self._pair(root)
            executor, runner = self._executor([inner, outer])

            result = executor.execute(Task(task_path=root, process_all_inputs=True))

            self.assertEqual([inner.file_path, outer.file_path], runner.paths)
            self.assertEqual([], result.suppressed_redundant_inputs)

    def test_similar_names_with_different_decoded_content_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inner, outer = self._pair(root, same=False)
            executor, runner = self._executor([inner, outer])

            result = executor.execute(Task(task_path=root))

            self.assertEqual([inner.file_path, outer.file_path], runner.paths)
            relationship = result.analysis_result.input_relationships[0]
            self.assertIs(
                relationship.relationship_type,
                InputRelationshipType.INDEPENDENT_INPUT,
            )
            self.assertIs(
                relationship.verification_status,
                RelationshipVerificationStatus.MISMATCH,
            )

    def test_unavailable_strong_verification_conservatively_executes_both(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inner, outer = self._pair(root)
            missing_tools = ToolManager(
                tool_paths={ToolName.LZ4: root / "missing-lz4.exe"}
            )
            resolver = InputArchiveRelationshipResolver(
                tool_manager=missing_tools
            )
            runner = RecordingPipelineRunner()
            executor = TaskExecutor(
                task_analyzer=StaticAnalyzer([inner, outer]),
                pipeline_runner=runner,
                input_relationship_resolver=resolver,
            )

            result = executor.execute(Task(task_path=root))

            self.assertEqual([inner.file_path, outer.file_path], runner.paths)
            relationship = result.analysis_result.input_relationships[0]
            self.assertIs(
                relationship.relationship_type,
                InputRelationshipType.POSSIBLE_OUTER_INNER_CHAIN,
            )
            self.assertIs(
                relationship.verification_status,
                RelationshipVerificationStatus.FAILED,
            )

    def test_cli_preview_displays_confirmed_chain_before_confirmation(self):
        import main as main_module

        root = Path.cwd()
        inner = archive_info(root / "PC.rar", "RAR", ["RAR"])
        outer = archive_info(
            root / "PC.rar.lz4", "LZ4", ["LZ4", "RAR"]
        )
        analysis = TaskAnalysisResult(
            task_id="preview",
            task_path=root,
            archive_results=[inner, outer],
            analysis_status=AnalysisStatus.COMPLETED,
        )
        relationship = InputArchiveRelationship(
            source_path=outer.file_path,
            related_path=inner.file_path,
            relationship_type=(
                InputRelationshipType.CONFIRMED_OUTER_CONTAINS_EXISTING_INNER
            ),
            confidence=RelationshipConfidence.HIGH,
            verification_method="LZ4_DECODED_STREAM_SHA256",
            verification_status=RelationshipVerificationStatus.VERIFIED,
            canonical_input=inner.file_path,
            suppressed_input=outer.file_path,
            reason="verified",
        )
        resolver = Mock()
        resolver.resolve.return_value = InputRelationshipResolution(
            relationships=[relationship],
            canonical_archives=[inner],
            suppressed_paths={outer.file_path},
        )
        analyzer = Mock()
        analyzer.analyze.return_value = analysis
        service = Mock()
        service.task_executor.task_analyzer = analyzer
        service.task_executor.input_relationship_resolver = resolver

        with (
            patch.object(main_module, "print_startup_info"),
            patch.object(
                main_module, "GameArchiveService", return_value=service
            ),
            patch(
                "builtins.input",
                side_effect=["1", str(root), "", "N", "", "0"],
            ),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            main_module.main()

        output = stdout.getvalue()
        self.assertIn("检测到同一归档链", output)
        self.assertIn("内容已强验证相同", output)
        self.assertIn(str(inner.file_path), output)


class FailingDuplicateDetector(DuplicateContentDetector):
    def _strong_manifest(self, candidate):
        raise OSError("simulated read failure")


class DuplicateContentTests(unittest.TestCase):
    @staticmethod
    def _game(root: Path, payload: bytes) -> None:
        for name in ("game", "lib", "renpy"):
            (root / name).mkdir(parents=True, exist_ok=True)
        (root / "Game.exe").write_bytes(b"launcher")
        (root / "game" / "data.bin").write_bytes(payload)

    def _sources(self, root: Path, payload_a: bytes, payload_b: bytes):
        first = root / "branch_a" / "Game"
        second = root / "branch_b" / "Game"
        self._game(first, payload_a)
        self._game(second, payload_b)
        return [
            ExtractionOutputSource(
                first, root / "one.rar", is_intermediate_output=False
            ),
            ExtractionOutputSource(
                second, root / "two.rar", is_intermediate_output=False
            ),
        ]

    def test_unrecognized_input_relation_delivers_only_one_verified_duplicate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = self._sources(root, b"same", b"same")

            outputs, candidates = OutputOrganizer().resolve_and_organize(
                root, sources
            )

            self.assertEqual(1, len(outputs))
            duplicate = [item for item in candidates if item.duplicate_of]
            self.assertEqual(1, len(duplicate))

    def test_same_quick_manifest_but_different_bytes_is_not_duplicate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = self._sources(root, b"A", b"B")
            organizer = OutputOrganizer()

            outputs, _ = organizer.resolve_and_organize(root, sources)

            self.assertEqual(2, len(outputs))
            self.assertFalse(
                any(
                    item.status is DuplicateContentStatus.DUPLICATE_CONTENT
                    for item in organizer.last_duplicate_records
                )
            )

    def test_same_directory_names_with_different_content_are_both_kept(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = self._sources(root, b"left", b"right")

            outputs, _ = OutputOrganizer().resolve_and_organize(root, sources)

            self.assertEqual(2, len(outputs))

    def test_strong_verification_exception_keeps_both_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = self._sources(root, b"same", b"same")
            organizer = OutputOrganizer(
                duplicate_detector=FailingDuplicateDetector()
            )

            outputs, _ = organizer.resolve_and_organize(root, sources)

            self.assertEqual(2, len(outputs))
            self.assertTrue(
                any(
                    item.status is DuplicateContentStatus.VERIFICATION_FAILED
                    for item in organizer.last_duplicate_records
                )
            )

    def test_relationship_and_duplicate_diagnostics_round_trip_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inner = root / "inner.rar"
            outer = root / "inner.rar.lz4"
            # Persistence is format-only; use the already tested model shape.
            relation = InputArchiveRelationship(
                source_path=outer,
                related_path=inner,
                relationship_type=(
                    InputRelationshipType.CONFIRMED_OUTER_CONTAINS_EXISTING_INNER
                ),
                confidence=RelationshipConfidence.HIGH,
                verification_method="LZ4_DECODED_STREAM_SHA256",
                verification_status=RelationshipVerificationStatus.VERIFIED,
                canonical_input=inner,
                suppressed_input=outer,
                reason="verified",
                verification_bytes_read=100,
                verification_time=0.1,
            )
            duplicate = DuplicateContentRecord(
                content_path=root / "two",
                duplicate_of=root / "one",
                status=DuplicateContentStatus.DUPLICATE_CONTENT,
                verification_method="RELATIVE_PATH_SIZE_THEN_SHA256",
                reason="same",
                file_count=1,
                total_size=4,
                verification_bytes_read=8,
                verification_time=0.2,
            )
            storage = HistoryStorage(root / "history.json")
            now = datetime.now().astimezone()
            storage.save(
                TaskHistoryRecord(
                    task_id="relationship-history",
                    task_path=root,
                    status=TaskStatus.COMPLETED,
                    created_time=now,
                    completed_time=now,
                    success=True,
                    summary="safe",
                    input_relationships=[relation],
                    suppressed_redundant_inputs=[outer],
                    duplicate_contents=[duplicate],
                )
            )

            loaded = storage.read_all()[0]
            self.assertEqual(outer, loaded.suppressed_redundant_inputs[0])
            self.assertIs(
                loaded.input_relationships[0].relationship_type,
                InputRelationshipType.CONFIRMED_OUTER_CONTAINS_EXISTING_INNER,
            )
            self.assertIs(
                loaded.duplicate_contents[0].status,
                DuplicateContentStatus.DUPLICATE_CONTENT,
            )


if __name__ == "__main__":
    unittest.main()
