"""Verify that code identity, documentation and governance state agree."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.project_state import ProjectStateError, load_project_state
except ModuleNotFoundError:  # Direct execution: py scripts/verify_project_state.py
    from project_state import ProjectStateError, load_project_state


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DOCS = (
    "PROJECT_HANDOFF.md",
    "CURRENT_STATUS.md",
    "DEBUGGING_PROTOCOL.md",
    "PROJECT_VISION.md",
    "ROADMAP.md",
    "DECISIONS.md",
    "REAL_WORLD_TESTS.md",
    "KNOWN_ISSUES.md",
    "ARCHITECTURE.md",
    "SECURITY.md",
)
HANDOFF_REFERENCES = REQUIRED_DOCS[1:8]
PROTOCOL_MARKERS = (
    "Extraction correctness",
    "Content correctness",
    "Safety/performance correctness",
    "Definition of Done",
)


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    details: tuple[str, ...] = ()


@dataclass
class VerificationReport:
    results: list[CheckResult]
    test_count: int | None = None

    @property
    def passed(self) -> bool:
        return all(result.status is not CheckStatus.FAIL for result in self.results)

    def find(self, name: str) -> CheckResult | None:
        return next((item for item in self.results if item.name == name), None)


def read_version_identity(path: Path) -> dict[str, str]:
    """Read literal version assignments without importing application code."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    identity: dict[str, str] = {}
    wanted = {"APP_NAME", "APP_VERSION", "BUILD_TYPE"}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in wanted:
            continue
        value = ast.literal_eval(node.value)
        if isinstance(value, str):
            identity[target.id] = value
    missing = wanted - identity.keys()
    if missing:
        raise ValueError(f"Missing version fields: {', '.join(sorted(missing))}")
    return identity


def evaluate_test_output(
    return_code: int, output: str, minimum_count: int, last_verified_count: int
) -> tuple[CheckResult, int | None]:
    matches = re.findall(r"Ran\s+(\d+)\s+tests?\s+in", output)
    count = int(matches[-1]) if matches else None
    if return_code != 0:
        return CheckResult("automated_tests", CheckStatus.FAIL, "Test process failed"), count
    if count is None:
        return CheckResult(
            "automated_tests", CheckStatus.FAIL, "Could not parse unittest test count"
        ), None
    required = max(minimum_count, last_verified_count)
    if count < required:
        return CheckResult(
            "automated_tests",
            CheckStatus.FAIL,
            f"Test count decreased: found {count}, required at least {required}",
        ), count
    return CheckResult(
        "automated_tests", CheckStatus.PASS, f"{count} tests passed"
    ), count


class ProjectVerifier:
    """Read-only verifier; it never repairs or deletes project files."""

    def __init__(
        self, project_root: str | Path = PROJECT_ROOT, state_path: str | Path | None = None
    ) -> None:
        self.root = Path(project_root).resolve()
        self.state_path = (
            Path(state_path).resolve()
            if state_path is not None
            else self.root / "project_state.json"
        )

    def verify(self, run_tests: bool = True) -> VerificationReport:
        try:
            state = load_project_state(self.state_path)
        except ProjectStateError as error:
            return VerificationReport(
                [CheckResult("project_state", CheckStatus.FAIL, str(error))]
            )

        results = [CheckResult("project_state", CheckStatus.PASS, "Schema valid")]
        results.extend(
            (
                self.check_version(state),
                self.check_documents(),
                self.check_current_status(state),
                self.check_handoff(),
                self.check_protocol(),
                self.check_sensitive_text(),
                self.check_developer_paths(),
                self.check_release_gate(state),
                self.check_known_issues(state),
            )
        )
        test_count = None
        if run_tests:
            test_result, test_count = self.check_tests(state)
            results.append(test_result)
        return VerificationReport(results, test_count=test_count)

    def check_version(self, state: dict[str, Any]) -> CheckResult:
        try:
            identity = read_version_identity(self.root / "version.py")
        except (OSError, SyntaxError, ValueError) as error:
            return CheckResult("version_identity", CheckStatus.FAIL, str(error))
        expected = state["project"]
        mismatches = []
        mapping = {
            "APP_NAME": "name",
            "APP_VERSION": "version",
            "BUILD_TYPE": "build_type",
        }
        for source_key, state_key in mapping.items():
            if identity[source_key] != expected[state_key]:
                mismatches.append(
                    f"{source_key}: version.py={identity[source_key]!r}, "
                    f"project_state={expected[state_key]!r}"
                )
        if mismatches:
            return CheckResult(
                "version_identity", CheckStatus.FAIL, "Version metadata mismatch", tuple(mismatches)
            )
        return CheckResult("version_identity", CheckStatus.PASS, "Version metadata agrees")

    def check_tests(self, state: dict[str, Any]) -> tuple[CheckResult, int | None]:
        command = [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError as error:
            return CheckResult("automated_tests", CheckStatus.FAIL, str(error)), None
        output = f"{completed.stdout}\n{completed.stderr}"
        baseline = state["test_baseline"]
        return evaluate_test_output(
            completed.returncode,
            output,
            baseline["minimum_test_count"],
            baseline["last_verified_count"],
        )

    def check_documents(self) -> CheckResult:
        missing = [name for name in REQUIRED_DOCS if not (self.root / "docs" / name).is_file()]
        if missing:
            return CheckResult(
                "documentation", CheckStatus.FAIL, "Required documents are missing", tuple(missing)
            )
        return CheckResult("documentation", CheckStatus.PASS, "Required documents exist")

    def check_current_status(self, state: dict[str, Any]) -> CheckResult:
        path = self.root / "docs" / "CURRENT_STATUS.md"
        if not path.is_file():
            return CheckResult("current_status", CheckStatus.FAIL, "CURRENT_STATUS.md is missing")
        text = path.read_text(encoding="utf-8")
        expected = (
            state["project"]["version"],
            state["project"]["build_type"],
            state["last_verified"],
        )
        missing = [value for value in expected if value not in text]
        if missing:
            return CheckResult(
                "current_status",
                CheckStatus.FAIL,
                "STALE_DOCUMENTATION: version/build/date not synchronized",
                tuple(missing),
            )
        return CheckResult("current_status", CheckStatus.PASS, "Status identity is current")

    def check_handoff(self) -> CheckResult:
        path = self.root / "docs" / "PROJECT_HANDOFF.md"
        if not path.is_file():
            return CheckResult("knowledge_entry", CheckStatus.FAIL, "PROJECT_HANDOFF.md is missing")
        text = path.read_text(encoding="utf-8")
        missing = [name for name in HANDOFF_REFERENCES if name not in text]
        if missing:
            return CheckResult(
                "knowledge_entry", CheckStatus.FAIL, "Knowledge entry is incomplete", tuple(missing)
            )
        return CheckResult("knowledge_entry", CheckStatus.PASS, "Knowledge navigation is complete")

    def check_protocol(self) -> CheckResult:
        path = self.root / "docs" / "DEBUGGING_PROTOCOL.md"
        if not path.is_file():
            return CheckResult("debugging_protocol", CheckStatus.FAIL, "Protocol is missing")
        text = path.read_text(encoding="utf-8")
        missing = [marker for marker in PROTOCOL_MARKERS if marker not in text]
        if missing:
            return CheckResult(
                "debugging_protocol", CheckStatus.FAIL, "Protocol markers are missing", tuple(missing)
            )
        return CheckResult("debugging_protocol", CheckStatus.PASS, "Protocol and DoD are present")

    def _text_files(self, roots: Iterable[Path]) -> Iterable[Path]:
        for root in roots:
            if root.is_file():
                yield root
            elif root.is_dir():
                for path in root.rglob("*"):
                    if path.is_file() and path.suffix.casefold() in {".md", ".log", ".json"}:
                        yield path

    def check_sensitive_text(self) -> CheckResult:
        roots = [self.root / "docs", self.root / "logs", self.state_path]
        assignment = re.compile(
            r"(?i)\b(?:password|actual_password|attempted_password)\s*=\s*"
            r"(?!\.\.\.|<redacted>|<password>|\*+|none\b|null\b)([^\s,;]+)"
        )
        cli_password = re.compile(
            r"(?i)(?<![\w-])-p(?!\.\.\.|<password>|<redacted>|\*+)([^\s`\"'<>]+)"
        )
        suspicious: list[str] = []
        for path in self._text_files(roots):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if assignment.search(line) or cli_password.search(line):
                    suspicious.append(f"{path.relative_to(self.root)}:{line_number}")
        if suspicious:
            return CheckResult(
                "password_leak", CheckStatus.FAIL, "Suspicious password persistence pattern", tuple(suspicious)
            )
        return CheckResult("password_leak", CheckStatus.PASS, "No obvious persisted password pattern")

    def check_developer_paths(self) -> CheckResult:
        marker = "C:\\Users\\<redacted>".casefold()
        candidates = [self.state_path, self.root / "GameArchiveManager.spec"]
        text_suffixes = {".py", ".json", ".toml", ".ini", ".cfg", ".txt"}
        for directory in (self.root / "config", self.root / "application"):
            if directory.is_dir():
                candidates.extend(
                    path
                    for path in directory.rglob("*")
                    if path.is_file() and path.suffix.casefold() in text_suffixes
                )
        config_json = self.root / "config.json"
        if config_json.is_file():
            candidates.append(config_json)
        found: list[str] = []
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if marker in text.casefold():
                found.append(str(path.relative_to(self.root)))
        if found:
            return CheckResult(
                "developer_paths", CheckStatus.FAIL, "Runtime/build dependency on developer path", tuple(found)
            )
        return CheckResult("developer_paths", CheckStatus.PASS, "No forbidden runtime developer path")

    def check_release_gate(self, state: dict[str, Any]) -> CheckResult:
        build = state["project"]["build_type"]
        vm_ready = state["release_gates"]["clean_windows_11_vm"]
        if build == "Release" and not vm_ready:
            return CheckResult(
                "build_release_gate",
                CheckStatus.FAIL,
                "Release requires clean_windows_11_vm=true",
            )
        if build == "Release Candidate" and not vm_ready:
            return CheckResult(
                "build_release_gate",
                CheckStatus.PASS,
                "Release Candidate may remain before VM verification",
            )
        return CheckResult("build_release_gate", CheckStatus.PASS, "Build gate is consistent")

    def check_known_issues(self, state: dict[str, Any]) -> CheckResult:
        p0 = state["current_priorities"]["p0"]
        if not p0:
            return CheckResult("known_issues", CheckStatus.PASS, "No active P0 in state")
        paths = (
            self.root / "docs" / "KNOWN_ISSUES.md",
            self.root / "docs" / "CURRENT_STATUS.md",
        )
        if not all(path.is_file() for path in paths):
            return CheckResult("known_issues", CheckStatus.FAIL, "P0 documentation is missing")
        texts = [path.read_text(encoding="utf-8") for path in paths]
        missing = [issue for issue in p0 if not all(issue in text for text in texts)]
        if missing:
            return CheckResult(
                "known_issues",
                CheckStatus.FAIL,
                "STALE_DOCUMENTATION: active P0 is not documented in both status files",
                tuple(missing),
            )
        return CheckResult("known_issues", CheckStatus.PASS, "Active P0 is documented")


def print_report(report: VerificationReport) -> None:
    print("GameArchiveManager Project State Verification")
    print()
    for result in report.results:
        print(f"[{result.status.value}] {result.name}: {result.message}")
        for detail in result.details:
            print(f"  - {detail}")
    print()
    print("Overall: PASS" if report.passed else "Overall: FAIL")


def main() -> int:
    report = ProjectVerifier().verify(run_tests=True)
    print_report(report)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
