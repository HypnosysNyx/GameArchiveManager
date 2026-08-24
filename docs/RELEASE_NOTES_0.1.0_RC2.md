# GameArchiveManager 0.1.0 RC2

Latest public RC2 build with security and privacy hardening.

## Security fixes

- 7-Zip passwords are sent through redirected standard input and no longer appear in the child-process command line.
- Extracted file and directory symbolic links, including Windows reparse points, are rejected before hashing or final delivery.
- RAR/7Z archives with readable headers are listed in read-only mode before extraction; path traversal, link entries and declared output limits are checked.
- Extracted-output quotas are enabled by default: 100,000 files and 100 GiB per extraction result.
- `.gitignore` now covers common local environment, history, coverage, key and certificate files.

## Privacy

- The application contains no HTTP, socket, telemetry, analytics, crash-report upload or cloud-sync logic.
- Tasks operate only on the file or directory explicitly supplied by the user. A directory task recursively inspects that selected tree.
- Logs and task history remain local under `%LOCALAPPDATA%\GameArchiveManager`; they contain full local paths and should be treated as private data.
- Passwords are not persisted. Manual password input remains visible in the console for Chinese IME compatibility.

## Verification

- 234 automated tests executed: 227 passed, 7 skipped because an LZ4 CLI was unavailable.
- Project-state verification: PASS.
- Windows onedir build and non-interactive startup/exit smoke test: PASS on the build machine.
- The executable is not Authenticode signed. Verify the published SHA-256 checksum before running it.

## Release-candidate limitations

- RC2 remains a release-candidate build. It is marked GitHub Latest by owner confirmation, but that label does not mean the clean-VM stability gate has passed.
- The security-hardened RC2 build has not yet been revalidated on a clean Windows 11 or Windows 10 VM.
- RAR/7Z archives whose directory headers are encrypted cannot receive full pre-extraction member inspection until a correct password is available; default quotas and post-extraction checks still apply.
- LZ4 end-to-end tests require a separately installed trusted `lz4.exe` and were skipped in this build environment.

See [README](../README.md), [Security](SECURITY.md), and [Configuration](CONFIGURATION.md) for complete behavior and boundaries.
