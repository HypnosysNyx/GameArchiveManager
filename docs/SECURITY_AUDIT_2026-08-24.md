# Security and Privacy Audit Summary — 2026-08-24

Audited repository: <https://github.com/HypnosysNyx/GameArchiveManager>  
Audited release: [`v0.1.0-rc2`](https://github.com/HypnosysNyx/GameArchiveManager/releases/tag/v0.1.0-rc2)  
Audited source commit: `a09e299b485d135046b49961c9a3212914579dc3`

## Result

**Overall status: attention required, suitable for public release-candidate testing.**

No application runtime code was found that uploads user files, paths, game lists, logs, or telemetry. No identity or hardware fingerprint collection, whole-disk discovery, persistence, privilege escalation, DLL injection, background residency, or remote-code download behavior was found.

The audit identified and verified fixes for password exposure in 7-Zip process arguments, extracted link/reparse-point handling, RAR/7Z member pre-inspection where directory headers are readable, default extraction quotas, and private developer paths in reachable Git history.

This conclusion applies to the audited source commit and is not a formal proof or a third-party binary certification.

## Scope reviewed

- entry point, configuration, runtime paths, logs, and history;
- archive discovery, header analysis, embedded-content detection, and split volumes;
- ZIP, RAR, 7Z, LZ4, nested extraction, and password retry paths;
- pre-extraction and post-extraction safety checks;
- output organization, hashing, delivery, and cleanup;
- external-process invocation and tool discovery;
- build configuration, release workflow, checksums, tests, `.gitignore`, and reachable Git history.

## Verified findings

| Area | Status | Evidence |
| --- | --- | --- |
| Network, telemetry, and upload logic | Pass | No HTTP client, socket, webhook, analytics, telemetry, crash-upload, cloud-sync, or auto-update path found in application source |
| Identity and device collection | Pass | No username, host name, IP/MAC, WMI, registry hardware query, disk serial, UUID, CPU/GPU, or fingerprint collection found |
| Scan boundary | Attention | Only a user-supplied file or directory is processed; a selected directory is recursively scanned, so users must not select an unrelated broad tree |
| Local path privacy | Attention | Logs and history remain under `%LOCALAPPDATA%\GameArchiveManager` and may contain complete local paths |
| Password handling | Pass with limitation | Passwords are not persisted and 7-Zip input uses redirected standard input; manually typed passwords remain visible in the console |
| Archive traversal and links | Pass | Dangerous member paths, extracted symbolic links, junctions, and other Windows reparse points are rejected |
| Extraction limits | Pass with limitation | Default file-count and total-size limits are enforced; post-extraction rejection cannot undo disk space already consumed |
| Source files and deletion | Pass | Source archives are not modified or deleted; cleanup requires an owned, authorized output path |
| External tools | Attention | Locally installed 7-Zip, WinRAR, or LZ4 remains a supply-chain boundary |
| Persistence or elevation | Pass | No autostart, service/task installation, registry write, elevation, injection, or hidden resident process found |
| Release integrity | Pass with limitation | GitHub Actions produces SHA-256 manifests; the RC2 Windows executable is not Authenticode-signed |

## Code references

- Scan scope: [`scanner/scanner.py`](../scanner/scanner.py), [`scanner/archive_finder.py`](../scanner/archive_finder.py), [`scanner/initial_scan_boundary.py`](../scanner/initial_scan_boundary.py)
- Runtime data: [`application/runtime_paths.py`](../application/runtime_paths.py), [`logging_system/logger.py`](../logging_system/logger.py), [`history/storage.py`](../history/storage.py)
- Password execution: [`extractor/seven_zip.py`](../extractor/seven_zip.py), [`recovery/password_executor.py`](../recovery/password_executor.py)
- Archive inspection: [`security/archive_content_inspector.py`](../security/archive_content_inspector.py), [`security/archive_safety.py`](../security/archive_safety.py)
- Extracted-tree checks: [`security/extraction_safety.py`](../security/extraction_safety.py)
- Cleanup boundaries: [`cleanup/cleanup_manager.py`](../cleanup/cleanup_manager.py), [`cleanup/runtime_tracker.py`](../cleanup/runtime_tracker.py)
- External tools: [`tools/tool_manager.py`](../tools/tool_manager.py), [`extractor/dispatcher.py`](../extractor/dispatcher.py)
- Release workflow: [`.github/workflows/publish-release.yml`](../.github/workflows/publish-release.yml)

## Verification baseline

- Automated suite: 234 tests, 227 passed and 7 tool-dependent LZ4 tests skipped in the audit environment.
- Project governance verifier: `Overall PASS` at the audited commit.
- GitHub Actions release build, test, packaging, checksum, and upload workflow completed successfully.
- The public RC2 ZIP and executable matched the published SHA-256 manifest during re-download verification.
- The packaged executable started and exited normally in a non-interactive smoke check.

## Remaining work before a stable release

1. Complete the clean Windows 11 virtual-machine smoke test in [`RC_SMOKE_TEST.md`](RC_SMOKE_TEST.md).
2. Run trusted LZ4 end-to-end coverage.
3. Consider hidden manual password entry, configurable log/history retention, and path redaction.
4. Consider free-space-aware extraction isolation and a password-aware pre-list step for encrypted RAR/7Z directory headers.
5. Add Authenticode signing when a trustworthy signing process and certificate are available.

For current implementation guarantees, reporting instructions, and known limitations, see the top-level [`SECURITY.md`](../SECURITY.md) and the detailed security design in [`docs/SECURITY.md`](SECURITY.md).
