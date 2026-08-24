"""Regression tests for the read-only project governance layer."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.project_state import load_project_state
from scripts.verify_project_state import (
    CheckStatus,
    ProjectVerifier,
    REQUIRED_DOCS,
    evaluate_test_output,
    read_version_identity,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = load_project_state(PROJECT_ROOT / "project_state.json")

    def _fixture(self, root: Path, state: dict | None = None) -> Path:
        docs = root / "docs"
        docs.mkdir(parents=True)
        active_state = copy.deepcopy(state or self.state)
        (root / "project_state.json").write_text(
            json.dumps(active_state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (root / "version.py").write_text(
            'APP_NAME = "GameArchiveManager"\n'
            'APP_VERSION = "0.1.0"\n'
            f'BUILD_TYPE = "{active_state["project"]["build_type"]}"\n',
            encoding="utf-8",
        )
        p0 = " ".join(active_state["current_priorities"]["p0"])
        for name in REQUIRED_DOCS:
            text = f"# {name}\n"
            if name == "CURRENT_STATUS.md":
                text += (
                    f"Last verified: {active_state['last_verified']}\n"
                    f"App version: {active_state['project']['version']}\n"
                    f"Build: {active_state['project']['build_type']}\n{p0}\n"
                )
            elif name == "PROJECT_HANDOFF.md":
                text += "\n".join(REQUIRED_DOCS[1:8])
            elif name == "DEBUGGING_PROTOCOL.md":
                text += (
                    "Extraction correctness\nContent correctness\n"
                    "Safety/performance correctness\nDefinition of Done\n"
                )
            elif name == "KNOWN_ISSUES.md":
                text += p0
            (docs / name).write_text(text, encoding="utf-8")
        return root / "project_state.json"

    def test_project_state_json_can_load(self) -> None:
        self.assertEqual(self.state["schema_version"], 1)
        self.assertEqual(self.state["project"]["name"], "GameArchiveManager")

    def test_app_version_matches_machine_state(self) -> None:
        identity = read_version_identity(PROJECT_ROOT / "version.py")
        self.assertEqual(identity["APP_VERSION"], self.state["project"]["version"])

    def test_build_type_matches_machine_state(self) -> None:
        identity = read_version_identity(PROJECT_ROOT / "version.py")
        self.assertEqual(identity["BUILD_TYPE"], self.state["project"]["build_type"])

    def test_test_baseline_cannot_drop_below_verified_count(self) -> None:
        baseline = self.state["test_baseline"]
        self.assertGreaterEqual(baseline["minimum_test_count"], 187)
        result, count = evaluate_test_output(
            0,
            "Ran 186 tests in 1.0s\nOK",
            baseline["minimum_test_count"],
            baseline["last_verified_count"],
        )
        self.assertEqual(count, 186)
        self.assertEqual(result.status, CheckStatus.FAIL)

    def test_missing_required_document_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = self._fixture(root)
            (root / "docs" / "SECURITY.md").unlink()
            result = ProjectVerifier(root, state_path).check_documents()
            self.assertEqual(result.status, CheckStatus.FAIL)

    def test_protocol_missing_correctness_layers_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = self._fixture(root)
            (root / "docs" / "DEBUGGING_PROTOCOL.md").write_text(
                "# Definition of Done\n", encoding="utf-8"
            )
            result = ProjectVerifier(root, state_path).check_protocol()
            self.assertEqual(result.status, CheckStatus.FAIL)

    def test_release_without_windows_11_vm_is_no_go(self) -> None:
        state = copy.deepcopy(self.state)
        state["project"]["build_type"] = "Release"
        state["release_gates"]["clean_windows_11_vm"] = False
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = self._fixture(root, state)
            result = ProjectVerifier(root, state_path).check_release_gate(state)
            self.assertEqual(result.status, CheckStatus.FAIL)

    def test_release_candidate_may_wait_for_windows_11_vm(self) -> None:
        state = copy.deepcopy(self.state)
        state["project"]["build_type"] = "Release Candidate"
        state["release_gates"]["clean_windows_11_vm"] = False
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = self._fixture(root, state)
            result = ProjectVerifier(root, state_path).check_release_gate(state)
            self.assertEqual(result.status, CheckStatus.PASS)

    def test_active_p0_missing_from_known_issues_fails(self) -> None:
        active_state = copy.deepcopy(self.state)
        active_state["current_priorities"]["p0"] = ["fixture_active_p0"]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = self._fixture(root, active_state)
            (root / "docs" / "KNOWN_ISSUES.md").write_text(
                "# Known Issues\n", encoding="utf-8"
            )
            result = ProjectVerifier(root, state_path).check_known_issues(
                active_state
            )
            self.assertEqual(result.status, CheckStatus.FAIL)

    def test_current_status_version_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = self._fixture(root)
            status_path = root / "docs" / "CURRENT_STATUS.md"
            status_path.write_text(
                status_path.read_text(encoding="utf-8").replace("0.1.0", "9.9.9"),
                encoding="utf-8",
            )
            result = ProjectVerifier(root, state_path).check_current_status(self.state)
            self.assertEqual(result.status, CheckStatus.FAIL)

    def test_developer_path_scan_ignores_binary_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = self._fixture(root)
            cache = root / "config" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "settings.pyc").write_bytes(
                b"binary\x00" + str(Path.home()).encode("utf-8") + b"\\source"
            )
            result = ProjectVerifier(root, state_path).check_developer_paths()
            self.assertEqual(result.status, CheckStatus.PASS)

    def test_project_state_loader_does_not_modify_file(self) -> None:
        path = PROJECT_ROOT / "project_state.json"
        before = path.read_bytes()
        load_project_state(path)
        self.assertEqual(path.read_bytes(), before)

    def test_verifier_does_not_delete_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = self._fixture(root)
            marker = root / "must_remain.txt"
            marker.write_text("user data", encoding="utf-8")
            before = {path.relative_to(root) for path in root.rglob("*")}
            ProjectVerifier(root, state_path).verify(run_tests=False)
            after = {path.relative_to(root) for path in root.rglob("*")}
            self.assertTrue(marker.exists())
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
