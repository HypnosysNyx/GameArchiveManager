"""Native synthetic Linux smoke. Run under xvfb-run; no real user inputs.

Default: shared source tree. --installed: require a wheel-installed package in
the active venv, without adding the source tree to sys.path, and run both apps.
All application state, archives and outputs live in one temporary directory.
"""

import argparse
import hashlib
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zlib


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(argv, **kwargs):
    result = subprocess.run(
        argv, capture_output=True, text=True, encoding="utf-8",
        timeout=90, **kwargs,
    )
    require(result.returncode == 0,
            f"Command failed ({result.returncode}): {argv}\n{result.stdout}\n{result.stderr}")
    return result


def check_entrypoints():
    expected = {("console_scripts", "game-archive-manager"): "main:main",
                ("gui_scripts", "game-archive-manager-gui"): "gui.app:main"}
    distribution = importlib.metadata.distribution("game-archive-manager")
    entries = {(ep.group, ep.name): ep for ep in distribution.entry_points}
    require({key: ep.value for key, ep in entries.items()} == expected,
            "Wheel must expose exactly the two supported entry points")
    from version import APP_VERSION
    require(distribution.version == APP_VERSION, "Installed version differs from shared source version")
    allowed = {"analyzer", "application", "cleanup", "config", "coordinator", "execution",
               "extractor", "gui", "history", "logging_system", "organizer", "password",
               "pipeline", "recovery", "report", "rules", "scanner", "security", "task", "tools"}
    for file in distribution.files or ():
        # Generated launchers and metadata are installation records, not product data.
        if file.parts[0] == ".." or file.parts[0].endswith(".dist-info"):
            continue
        if "__pycache__" in file.parts:
            continue
        require((file.parts[0] in allowed and file.suffix == ".py")
                or str(file) in {"main.py", "version.py"},
                f"Unexpected installed package data: {file}")
    for (_, name), ep in entries.items():
        require(callable(ep.load()), f"Not callable: {name}")
        script = Path(sys.executable).parent / name
        require(script.is_file() and os.access(script, os.X_OK), f"Missing executable: {script}")
    cli = run([str(Path(sys.executable).parent / "game-archive-manager")], input="Q\n")
    require("GameArchiveManager" in cli.stdout and "启动成功" in cli.stdout,
            "Installed CLI did not reach its interactive session")
    # Execute the generated GUI launcher with a bounded real Tk event loop.
    # Production main() still constructs GameArchiveApp; only loop duration changes.
    run([sys.executable, "-B", "-c", """
import runpy, sys, tkinter as tk
original = tk.Tk.mainloop
def bounded(self, *args, **kwargs):
    self.update_idletasks()
    assert self.title() == 'GameArchiveManager'
    assert self.winfo_children()
    self.after(150, self.destroy)
    return original(self, *args, **kwargs)
tk.Tk.mainloop = bounded
runpy.run_path(sys.argv[1], run_name='__main__')
""", str(Path(sys.executable).parent / "game-archive-manager-gui")])
    print("PASS installed CLI and GUI entry points")


def smoke(root, installed):
    if not installed:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from application.app_service import GameArchiveService
    from config.settings import Settings
    from tools.models import ToolName
    import application

    if installed:
        import main as cli_module
        import gui.app as gui_module
        import version
        for module in (application, cli_module, gui_module, version):
            require(Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()),
                    f"{module.__name__} was imported outside the installed venv")
    service = GameArchiveService(settings=Settings(extraction_timeout_seconds=60))
    for tool in (ToolName.SEVEN_ZIP, ToolName.LZ4):
        require(service.tool_manager.get_tool_status(tool).verified,
                f"Install verified native {tool.value} before running smoke")
    seven_zip = service.tool_manager.get_tool_path(ToolName.SEVEN_ZIP)
    fixture = root / "fixture"
    fixture.mkdir()
    payloads = {"readme.txt": b"Synthetic Linux archive smoke\n" * 128,
                "data/payload.bin": bytes(range(256)) * 32}
    for relative, data in payloads.items():
        target = fixture / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    task_dir = root / "task"
    task_dir.mkdir()
    archive = task_dir / "synthetic.7z"
    run([str(seven_zip), "a", "-t7z", str(archive), "."], cwd=fixture)
    original_hash = hashlib.sha256(archive.read_bytes()).digest()
    run([str(seven_zip), "t", str(archive)])  # Real archive data/CRC test.
    report = service.execute_task(archive)
    require(report.success_count == 1 and report.failed_count == 0
            and report.task_status == "COMPLETED" and report.output_paths,
            f"Service did not complete extraction/delivery: {report}")
    delivered = {}
    for output in report.output_paths:
        output = Path(output).resolve()
        require(output.is_relative_to(task_dir.resolve()), "Delivery escaped synthetic task")
        for file in ([output] if output.is_file() else output.rglob("*")):
            if file.is_file():
                relative = file.relative_to(output).as_posix()
                require(relative not in delivered, f"Duplicate delivered file: {relative}")
                delivered[relative] = file.read_bytes()
    require(set(delivered) == set(payloads), f"Unexpected delivered contents: {list(delivered)}")
    for relative, expected in payloads.items():
        actual = delivered[relative]
        require(zlib.crc32(actual) == zlib.crc32(expected) and actual == expected,
                f"Content/CRC mismatch: {relative}")
    require(hashlib.sha256(archive.read_bytes()).digest() == original_hash,
            "Synthetic source archive was modified")
    print("PASS native 7z CRC, GameArchiveService extraction/delivery, content CRC, source SHA-256")

    import tkinter as tk
    from gui.app import GameArchiveApp
    window = tk.Tk()
    try:
        app = GameArchiveApp(window)
        window.update()
        require(app.start_button.winfo_exists() and app.library_button.winfo_exists(),
                "GUI did not instantiate its controls")
    finally:
        window.destroy()
    print("PASS headless Tk GameArchiveApp instantiate")
    if installed:
        check_entrypoints()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    require(sys.platform.startswith("linux"), "This smoke requires native Linux Python")
    require(os.environ.get("DISPLAY"), "Run with xvfb-run -a python3 scripts/linux_smoke.py")
    previous_environment = os.environ.copy()
    previous_cwd = Path.cwd()
    try:
        with tempfile.TemporaryDirectory(prefix="gam-linux-smoke-") as directory:
            root = Path(directory).resolve()
            for name, suffix in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"),
                                 ("XDG_DATA_HOME", "data"), ("XDG_STATE_HOME", "state"),
                                 ("XDG_CACHE_HOME", "cache"), ("XDG_RUNTIME_DIR", "runtime")):
                location = root / suffix
                location.mkdir(mode=0o700)
                os.environ[name] = str(location)
            # Do not contact the user's real desktop keyring, even when installed.
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={root / 'no-session-bus'}"
            os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
            os.environ.pop("PYTHONPATH", None)
            os.chdir(root)
            smoke(root, args.installed)
    finally:
        os.chdir(previous_cwd)
        os.environ.clear()
        os.environ.update(previous_environment)
    print("Linux smoke PASS (synthetic temporary data only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
