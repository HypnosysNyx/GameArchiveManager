"""Read-only RAR5 embedded-header preflight for diagnosis.

This checks *structure only*. It cannot establish a correct password, archive
completeness, successful extraction, or file CRC. It never copies the host,
runs an external unpacker, or reads beyond the bounded RAR5 header parser.
No input path, raw header, password, or tool output is included in the report.
"""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import sys
from pathlib import Path


DEFAULT_DISK_RESERVE_BYTES = 1024 ** 3
VALID_STRUCTURE = frozenset({"VALID", "VALID_ENCRYPTED"})


def preflight(
    host: str | Path,
    offset: int,
    *,
    disk_free_bytes: int | None = None,
    reserve_bytes: int = DEFAULT_DISK_RESERVE_BYTES,
) -> dict[str, object]:
    """Inspect one known signature offset without carving any host data."""
    if reserve_bytes < 0:
        raise ValueError("reserve_bytes must be nonnegative")
    from analyzer.embedded_detector import EmbeddedArchiveDetector

    path = Path(host).expanduser()
    report: dict[str, object] = {
        "offset": offset,
        "structure": "NOT_CHECKED",
        "reason": "",
        "rar5_encrypted_header": False,
        "data_crc_verified": False,
        "password_verified": False,
        "carve_attempted": False,
    }
    try:
        details = path.lstat()
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if (not stat.S_ISREG(details.st_mode) or
                getattr(details, "st_file_attributes", 0) & reparse_flag):
            report["reason"] = "SOURCE_NOT_REGULAR"
            return report
        size = details.st_size
        report["file_size_bytes"] = size
        if not 0 < offset < size:
            report["reason"] = "OFFSET_OUT_OF_RANGE"
            return report

        tail_size = size - offset
        report["remaining_bytes_after_offset"] = tail_size
        free = disk_free_bytes if disk_free_bytes is not None else shutil.disk_usage(path.parent).free
        report["free_bytes_at_source"] = free
        report["full_tail_copy_plus_reserve_bytes"] = tail_size + reserve_bytes
        report["can_reserve_full_tail_copy"] = free >= tail_size + reserve_bytes

        # This exact-offset parser reads only the RAR signature, CRC and
        # bounded header fields; it never scans the gigabytes after offset.
        result, reason = EmbeddedArchiveDetector().validate_candidate(path, offset, "RAR")
        report["structure"] = result.value
        report["reason"] = reason.value
        report["rar5_encrypted_header"] = result.value == "VALID_ENCRYPTED"
        return report
    except OSError:
        report["reason"] = "SOURCE_READ_ERROR"
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded, read-only embedded RAR5 header preflight; NOT a decryption test.")
    parser.add_argument("host", help="Existing MP4/JPEG or other host file")
    parser.add_argument("--offset", type=int, action="append", required=True,
                        help="Known byte offset of a RAR signature; repeat for each candidate")
    args = parser.parse_args(argv)

    # Running as a source-tree script should work even when launched elsewhere.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    reports = [preflight(args.host, offset) for offset in args.offset]
    print(json.dumps({"candidates": reports,
                      "note": "Structural preflight only. Encrypted content and CRC remain unverified."},
                     ensure_ascii=False, indent=2))
    return 0 if all(item["structure"] in VALID_STRUCTURE for item in reports) else 2


if __name__ == "__main__":
    raise SystemExit(main())
