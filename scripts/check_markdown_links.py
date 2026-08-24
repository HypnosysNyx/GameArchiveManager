"""Validate relative Markdown links without making network requests."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
REMOTE_PREFIXES = ("http://", "https://", "mailto:", "tel:")


def markdown_files() -> list[Path]:
    files = list(PROJECT_ROOT.glob("*.md"))
    files.extend((PROJECT_ROOT / "docs").rglob("*.md"))
    if (PROJECT_ROOT / ".github").is_dir():
        files.extend((PROJECT_ROOT / ".github").rglob("*.md"))
    return sorted(set(files))


def local_target(raw_target: str) -> str | None:
    target = raw_target.strip().strip("<>")
    if not target or target.startswith("#"):
        return None
    if target.casefold().startswith(REMOTE_PREFIXES):
        return None
    target = target.split("#", 1)[0].split("?", 1)[0]
    return unquote(target) or None


def check_links() -> list[str]:
    failures: list[str] = []
    for document in markdown_files():
        text = document.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in LINK_PATTERN.finditer(line):
                target = local_target(match.group(1))
                if target is None:
                    continue
                resolved = (document.parent / target).resolve()
                try:
                    resolved.relative_to(PROJECT_ROOT)
                except ValueError:
                    failures.append(
                        f"{document.relative_to(PROJECT_ROOT)}:{line_number}: "
                        f"link escapes repository: {target}"
                    )
                    continue
                if not resolved.exists():
                    failures.append(
                        f"{document.relative_to(PROJECT_ROOT)}:{line_number}: "
                        f"missing target: {target}"
                    )
    return failures


def main() -> int:
    failures = check_links()
    if failures:
        print("Markdown link check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Markdown link check passed for {len(markdown_files())} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
