# RC2 — Embedded RAR5 read-only preflight and acceptance boundary

**Status: narrow diagnostics and manual-recovery context bugfix. No real large
encrypted resource has passed end-to-end validation in this slice.**

This note intentionally excludes user-specific paths, usernames, sample
filenames, passwords, hashes, and screenshots. Local evidence stays outside
Git in the ignored `.vm_gate/` tree.

## Actual local findings and limits

The existing sanitized local evidence records two MP4 hosts with structurally
valid encrypted RAR5 headers. A full-host signature census found exactly one
structurally valid RAR5 candidate in each host, both within the product's
512 MiB scan window. An additional raw signature in one host was not a valid
candidate. This census is prior diagnostic evidence; it does not expand the
product's scan window or prove data integrity.

With a folder-name credential candidate, bounded header probes from both
7-Zip and UnRAR changed from explicit wrong-password signals to truncated-input
signals. This suggests header unlocking, but does not prove a correct data
password or recoverable content.

For the smaller host, the prior complete-tail 7-Zip listing returned nonzero,
despite a listing separator and an in-range physical size. Its full data test
also failed with data-error/wrong-password signals. The independent UnRAR full
data test failed with checksum/corruption/wrong-password signals. **Both data
integrity tests failed; data was not recovered.** These signals alone do not
distinguish an incorrect data password from damaged or otherwise unreadable
data. The larger host has no complete data-integrity pass in this evidence.

The saved summaries report unchanged sources and removal of diagnostic scratch
copies in those prior investigations. For this bugfix, evidence review was
limited to the saved summaries and regression tests used synthetic fixtures;
no original resource or saved credential was accessed for this work. The
optional preflight tool described below reads supplied host headers when run;
it was not run against the original resources for this bugfix. Synthetic tests
do not replace real end-to-end acceptance or clean-VM evidence.

## Product diagnostics and recovery correction

Candidate outcomes retain sanitized offset, status and validation stage in
structured stage diagnostics, including `CANDIDATE_SAFETY` when a plan is
rejected before tool validation. A nonzero 7-Zip listing is recorded as `LISTING`;
a nonzero full extraction is recorded as `DATA_EXTRACTION`. Only fixed stage,
status and failure codes cross this diagnostic boundary; raw tool output,
internal filenames and plaintext passwords are not copied into results.
Every nonzero exit, including warnings, remains a failure.

Scan-stop reasons remain independent of candidate validation outcomes. An
`EMBEDDED_INCOMPLETE` result preserves the latest candidate stages and statuses
and explicitly states whether a password remains unresolved. The manual
password request uses the actual first pending candidate's latest status,
including when a later candidate failed at another stage. A user skip or cancel
still preserves its control outcome and the scan-stop step.

Exact-start listing, confirmed archive bounds, full data CRC, output safety and
quota checks, encryption handling, scan/work limits and success gates remain in
force. A listing separator, physical size, header checksum or header-unlocking
signal cannot establish extraction success.

## Local Windows regression verification

Using `.build_venv/Scripts/python.exe -B`, with `LOCALAPPDATA` isolated under
`.vm_gate/rc2_diagnostics_profile`, `VIRTUAL_ENV` pointing to `.build_venv`,
`TCL_LIBRARY=.vm_gate/tcl8.6` and `TK_LIBRARY=.vm_gate/tk8.6`:

- Focused: `-m unittest tests.test_embedded_candidate_resolution tests.test_embedded_validator_diagnostics -v`
  — 40 tests passed, no skips.
- Full: `-m unittest discover -s tests -p "test_*.py" -v`
  — 373 tests passed, no skips.
- `git diff --check` passed.

The initial full run used an absolute Tcl/Tk path and failed with 11 Tcl
initialization errors. Rerunning with the relative paths above passed without
changing GUI code or skipping tests. Logs remain in the ignored local evidence
tree. These results verify the encoded regression scenarios, not recovery of
the real resources, a packaged build or a clean Windows VM.

## Why this slice

A large MP4/JPEG host can contain an encrypted RAR5 header at a nonzero offset.
A structurally valid RAR5 encryption header proves only that *the header*
has a valid checksum and plausible fields. It does not prove the remainder
is present, the password works, or the extracted files satisfy data CRC.

The embedded extraction path copies all bytes from a candidate offset
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

This diagnostic slice does not publish an RC2 build. Do not merge, tag or
publish an RC2 build on the strength of this diagnostic alone.
