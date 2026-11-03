# RC2 — Embedded RAR5 read-only preflight and acceptance boundary

**Status: diagnostic draft only. No extraction fix and no real large encrypted
resource has passed end-to-end validation in this slice.**

This note intentionally excludes user-specific paths, usernames, sample
filenames, passwords, hashes, and screenshots. Local evidence stays outside
Git in the ignored `.vm_gate/` tree.

## Why this slice

A large MP4/JPEG host can contain an encrypted RAR5 header at a nonzero offset.
A structurally valid RAR5 encryption header proves only that *the header*
has a valid checksum and plausible fields. It does not prove the remainder
is present, the password works, or the extracted files satisfy data CRC.

Today the embedded extraction path copies all bytes from a candidate offset
to host EOF before invoking the bounded exact-start 7-Zip validator. For a
multi-gigabyte host this can consume comparable temporary disk space on
each candidate, plus extraction output, within the configured carve budget.

## Read-only diagnostic workflow

From a checked-out project source tree (Python 3.10+):

```bash
python scripts/probe_embedded_rar5.py "/path/to/host.mp4" --offset 123456789
```

Use exact verified offsets from local diagnostic evidence, never a guessed
filename-to-offset mapping. Multiple `--offset` flags are supported.

The tool:
- Reads only basic file metadata and the bounded RAR header near each
  supplied byte offset; **it does not copy the file or run 7-Zip**.
- Refuses nonregular inputs and out-of-bounds offsets.
- Reports `VALID_ENCRYPTED`, `INVALID_CRC`, `INVALID_STRUCTURE`, or
  another structurally grounded status from the existing detector.
- Reports remaining bytes after the offset and compares the estimated
  full-tail copy plus 1 GiB reserve with source-volume free space.
- Always reports `data_crc_verified=false`, `password_verified=false`
  and `carve_attempted=false`. These are non-negotiable boundaries.
- Omits file paths, raw bytes, secret candidates and child-process output
  from its JSON result.

Do not upload raw local paths or data. Do not run the application on multi-GB
inputs when the disk reserve or required user password evidence is missing.

## Follow-up root-cause investigation

1. Read the existing local handoff and check Git status without altering
   the user's dirty worktree.
2. Use the read-only preflight on the known embedded offsets. Confirm
   candidate status, header CRC and projected disk requirement **without
   extracting the host**.
3. Review the saved, sanitized per-candidate statuses from the previous
   failed task, distinguishing `WRONG_PASSWORD`, `PASSWORD_REQUIRED`,
   `FAILED`, `TIMEOUT`, `CARVE_BUDGET_REACHED` and
   `DISK_RESERVE_REACHED`. One attempted candidate is **not proof**
   of a correct password.
4. If the source is incomplete or a genuine unsupported format, record that
   limit instead of defeating CRC, output boundary or file quotas.
5. Only after identifying the blocking condition, implement a narrow fix
   with synthetic positive, negative and interactive regressions, full
   Windows/Linux CI, and authorized real-sample end-to-end verification.
6. Real acceptance requires final decrypted content and data CRC, correct
   task/delivery status, original source SHA-256 unchanged, no passwords
   in logs, and no deletion of previous task outputs.

The current RC1 release remains the public build. Do not merge, tag or
publish an RC2 build on the strength of this diagnostic alone.
