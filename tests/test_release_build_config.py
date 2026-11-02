"""Release build boundaries using synthetic files; no builds or network access."""

import contextlib
import io
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/release-build.yml").read_text(encoding="utf-8")
SCRIPT = (ROOT / "scripts/build_windows_release.ps1").read_text(encoding="utf-8")


def ps_python(name):
    return re.search(r"\$" + name + r" = @'\n(.*?)\n'@", SCRIPT, re.S).group(1)


def workflow_python():
    return [textwrap.dedent(block) for block in re.findall(
        r"          python -B - <<'PY'\n(.*?)\n          PY", WORKFLOW, re.S)]


class ReleaseBuildConfigTests(unittest.TestCase):
    def test_embedded_python_compiles(self):
        for name in ("versionCode", "stageCode", "inspectCode", "spec"):
            compile(ps_python(name), name, "exec")
        blocks = workflow_python()
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            compile(block, "workflow", "exec")

    def test_only_manual_read_only_artifact_build(self):
        trigger = WORKFLOW.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertNotRegex(trigger, r"(?m)^  (push|pull_request|release|schedule):")
        self.assertIn("  contents: read", WORKFLOW)
        self.assertNotIn("contents: write", WORKFLOW)
        self.assertNotIn("secrets.", WORKFLOW)
        self.assertNotIn("gh release", WORKFLOW)
        actions = re.findall(r"uses: ([^\s]+)", WORKFLOW)
        self.assertEqual(len(actions), 6)
        for action in actions:
            self.assertRegex(action, r"^actions/(checkout|setup-python|upload-artifact)@[a-f0-9]{40}$")
        self.assertIn('default: "0.3.0rc1"', WORKFLOW)
        self.assertIn('scripts/linux_smoke.py', WORKFLOW)
        self.assertIn('gam-release-smoke.py --installed', WORKFLOW)

    def test_staging_drops_private_data_and_external_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            root, stage = Path(temp) / "repo", Path(temp) / "stage"
            files = {"main.py": "", "version.py": "APP_VERSION = '1.2.3'\n", "LICENSE": "license",
                     "gui/app.py": "def main(): pass\n", "tools/__init__.py": "",
                     "config.json": "private", "tools/7z.exe": "binary", "tools/7z.dll": "binary",
                     "docs/private.md": "private", "tests/fixture.py": "private",
                     "gui/__pycache__/private.py": "private", "archive.zip": "private"}
            for name, contents in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contents)
            with patch.object(sys, "argv", ["-", str(root), str(stage)]):
                exec(compile(ps_python("stageCode"), "stageCode", "exec"), {})
            self.assertEqual({p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file()},
                             {"main.py", "version.py", "LICENSE", "gui/app.py", "tools/__init__.py", "gui_launcher.py"})
            self.assertEqual((root / "config.json").read_text(), "private")

    def test_wheel_inspection_rejects_extra_data_and_unsafe_paths(self):
        code = workflow_python()[1]
        metadata = f"game_archive_manager-{APP_VERSION}.dist-info"
        required = ["main.py", "version.py", "gui/app.py", f"{metadata}/entry_points.txt"]
        cases = (None, "config.json", "tools/7z.exe", "gui/private.json", "tests/test_x.py",
                 "../escape.py", "/main.py", "gui\\escape.py", f"{metadata}/private.txt")
        with tempfile.TemporaryDirectory() as temp:
            wheel = Path(temp) / "candidate.whl"
            for extra in cases:
                with self.subTest(extra=extra):
                    with ZipFile(wheel, "w") as archive:
                        for name in required + ([extra] if extra else []):
                            entry = ZipInfo(name)
                            # Preserve malicious backslashes even on Windows, where
                            # ZipInfo normally normalizes them during construction.
                            entry.filename = name
                            archive.writestr(entry, "")
                    # Read using native Linux ZIP path rules, matching the runner.
                    with patch.dict(os.environ, {"WHEEL_DIR": temp}), patch("zipfile.os.sep", "/"), contextlib.redirect_stdout(io.StringIO()):
                        if extra:
                            with self.assertRaises(AssertionError):
                                exec(compile(code, "wheel-inspection", "exec"), {})
                        else:
                            exec(compile(code, "wheel-inspection", "exec"), {})

    def test_pe_inspection_requires_x64_and_correct_gui_console_subsystems(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("_internal/_tkinter.pyd", "_internal/_tcl_data/init.tcl", "_internal/_tk_data/tk.tcl"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            def pe(subsystem):
                data = bytearray(256)
                data[:2] = b"MZ"
                struct.pack_into("<I", data, 0x3c, 64)
                data[64:68] = b"PE\0\0"
                struct.pack_into("<H", data, 68, 0x8664)
                struct.pack_into("<H", data, 64 + 24 + 68, subsystem)
                return data
            gui = root / "GameArchiveManager.exe"
            gui.write_bytes(pe(2))
            (root / "GameArchiveManager-CLI.exe").write_bytes(pe(3))
            code = compile(ps_python("inspectCode"), "inspectCode", "exec")
            with patch.object(sys, "argv", ["-", temp]), contextlib.redirect_stdout(io.StringIO()):
                exec(code, {})
                gui.write_bytes(pe(3))
                with self.assertRaises(AssertionError):
                    exec(code, {})
                gui.write_bytes(pe(2))
                (root / "7z.exe").write_bytes(b"MZ")
                with self.assertRaises(AssertionError):
                    exec(code, {})


if __name__ == "__main__":
    unittest.main()
