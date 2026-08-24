"""Report RC GO/NO-GO without changing project or release metadata."""

from __future__ import annotations

from pathlib import Path

try:
    from scripts.project_state import load_project_state
    from scripts.verify_project_state import CheckStatus, ProjectVerifier
except ModuleNotFoundError:  # Direct execution: py scripts/rc_readiness.py
    from project_state import load_project_state
    from verify_project_state import CheckStatus, ProjectVerifier


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def evaluate_readiness(state: dict, verifier_passed: bool) -> tuple[bool, list[str]]:
    """Evaluate required release gates; Windows 10 remains optional for 0.1.0."""
    reasons: list[str] = []
    p0 = state["current_priorities"]["p0"]
    reasons.extend(f"Active P0 issue: {issue}" for issue in p0)

    gates = state["release_gates"]
    required = {
        "full_test_suite": "Full automated test suite is not verified",
        "real_sample_regression": "Required real sample regression is not complete",
        "clean_windows_11_vm": "Clean Windows 11 VM is not verified",
        "source_file_integrity": "Source file integrity is not verified",
        "password_leak_check": "Password leak check is not verified",
        "documentation_current": "Documentation is not current",
    }
    reasons.extend(message for key, message in required.items() if not gates[key])
    if not verifier_passed:
        reasons.append("Project state verifier failed")
    return not reasons, reasons


def status_label(value: bool, false_label: str = "FAIL") -> str:
    return "PASS" if value else false_label


def main() -> int:
    state = load_project_state(PROJECT_ROOT / "project_state.json")
    report = ProjectVerifier(PROJECT_ROOT).verify(run_tests=True)
    results = {result.name: result for result in report.results}
    gates = state["release_gates"]
    ready, reasons = evaluate_readiness(state, report.passed)

    print("GameArchiveManager RC Readiness")
    print()
    print(f"Version: {state['project']['version']}")
    print(f"Build: {state['project']['build_type']}")
    print()
    test_result = results.get("automated_tests")
    print(
        "Automated tests: "
        + (test_result.status.value if test_result is not None else "NOT RUN")
    )
    print(f"Test count: {report.test_count if report.test_count is not None else 'UNKNOWN'}")
    print(
        "Documentation: "
        + results.get("documentation", results["project_state"]).status.value
    )
    print(
        "Debugging protocol: "
        + results.get("debugging_protocol", results["project_state"]).status.value
    )
    print("Known P0 issues: " + ("FAIL" if state["current_priorities"]["p0"] else "PASS"))
    print(
        "Clean Windows 11 VM: "
        + status_label(gates["clean_windows_11_vm"], "NOT VERIFIED")
    )
    print(
        "Clean Windows 10 VM: "
        + status_label(gates["clean_windows_10_vm"], "OPTIONAL / NOT VERIFIED")
    )
    print(
        "Real sample regression: "
        + status_label(gates["real_sample_regression"], "NOT VERIFIED")
    )
    print("Password leak check: " + results["password_leak"].status.value)
    print("Source integrity policy: " + status_label(gates["source_file_integrity"]))
    print()
    print("Overall:")
    print("GO" if ready else "NO-GO")
    if reasons:
        print()
        print("Reasons:")
        for reason in reasons:
            print(f"- {reason}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
