"""Shared host-attempt work limits and cancellable subprocess transport."""

import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


class EmbeddedIncomplete(Exception):
    """Only bounded reason codes cross the resolver boundary."""


@dataclass
class EmbeddedWork:
    max_carved_bytes: int = 48 * 1024**3
    disk_reserve_bytes: int = 1024**3
    timeout_seconds: float = 300
    max_processes: int = 256
    process_timeout_seconds: float = 60
    cancelled: Callable[[], bool] = field(default=lambda: False, repr=False)
    carved_bytes: int = 0
    processes: int = 0
    started: float = field(default_factory=time.monotonic)

    def check(self, directory: Path | None = None, needed=0):
        if self.cancelled():
            raise EmbeddedIncomplete("CANCELLED")
        if time.monotonic() - self.started >= self.timeout_seconds:
            raise EmbeddedIncomplete("TIMEOUT")
        if directory is not None and shutil.disk_usage(directory).free < needed + self.disk_reserve_bytes:
            raise EmbeddedIncomplete("DISK_RESERVE_REACHED")

    def reserve_carve(self, size, directory):
        self.check(directory, size)
        if size < 0 or self.carved_bytes + size > self.max_carved_bytes:
            raise EmbeddedIncomplete("CARVE_BUDGET_REACHED")
        self.carved_bytes += size

    def run(self, command, directory, password=None, monitor=None):
        """No secrets in argv or errors; bounded output, disk, time and cancellation."""
        self.check(directory)
        if self.processes >= self.max_processes:
            raise EmbeddedIncomplete("PROCESS_LIMIT_REACHED")
        self.processes += 1
        started = time.monotonic()
        with tempfile.TemporaryFile(dir=directory) as output:
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE,
                    stdout=output, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError:
                raise EmbeddedIncomplete("TOOL_UNAVAILABLE") from None
            try:
                # Existing 7-Zip stdin transport; never use WinRAR password argv.
                if password is not None:
                    if len(password) > 1024 or "\n" in password or "\r" in password:
                        raise EmbeddedIncomplete("PASSWORD_TRANSPORT_UNSUPPORTED")
                    process.stdin.write((password + "\n").encode("utf-8"))
                    process.stdin.flush()
                process.stdin.close()
                while process.poll() is None:
                    self.check(directory)
                    if time.monotonic() - started >= self.process_timeout_seconds:
                        raise EmbeddedIncomplete("PROCESS_TIMEOUT")
                    if output.tell() > 4 * 1024**2:
                        raise EmbeddedIncomplete("TOOL_OUTPUT_LIMIT_REACHED")
                    if monitor is not None:
                        monitor()
                    time.sleep(0.05)
                self.check(directory)
                if output.tell() > 4 * 1024**2:
                    raise EmbeddedIncomplete("TOOL_OUTPUT_LIMIT_REACHED")
                output.seek(0)
                return process.returncode, output.read(4 * 1024**2).decode("utf-8", "replace")
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
