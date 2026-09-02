# GameArchiveManager 0.1.0 RC2 — Win11-Sandbox guestcontrol smoke

> **Subsequent closure (2026-08-28):** This report preserves the initial partial-run verdict. Checklist item 14 was subsequently completed against the same EXE `67DF840B…` and passed in all three phases; see [`rc2_item14_codex.md`](rc2_item14_codex.md). The combined authoritative gate result is recorded in [`docs/RC_SMOKE_TEST.md`](docs/RC_SMOKE_TEST.md). The original tested ZIP remains unchanged, including its stale embedded Markdown hash text.

## Verdict

**Overall: BLOCKED / do not flip `clean_windows_11_vm` yet.**

The supplied RC2 passed startup, no-tool behavior, tool discovery, real formats, split volumes, password recovery, embedded RAR, Chinese paths, repeat runs, cleanup boundaries, source-integrity checks, and persistence checks. Checklist item 14 (real Ctrl+C during EXTRACTING / SCANNING / VALIDATING) could not be completed faithfully through this guestcontrol session. In addition, the EXE hash recorded in the packaged smoke document is stale relative to the supplied RC2 ZIP.

I did not change `project_state.json`, `BUILD_TYPE`, version data, frozen business code, tags, releases, or remote state. No push was performed. At the end of the run `project_state.json` still had `clean_windows_11_vm: false`.

## Environment and artifact identity

| Field | Observed value |
|---|---|
| Test window | 2026-08-27 21:35–22:15 +08:00 |
| VM | `Win11-Sandbox` (the forbidden `GAM-RC2-Test` VM was not used) |
| Transfer/execution channel | VirtualBox `guestcontrol` |
| OS | Microsoft Windows 11 Home, 25H2, 10.0.26200, build 26200.9168, x64 |
| VM snapshot | None |
| Guest account | Standard local user (`IsAdministrator=False`) |
| Python | No installed Python entries; `python --version` resolved only to the Microsoft Store alias and exited 9009; `py` not found |
| Fresh test root | `%LOCALAPPDATA%\Temp\rc2_codex_20260827` |
| Host repo HEAD | `85a95bc3ae60aafe816650e8df367fe5b11a86c6` |
| RC2 tag commit / ZIP `BUILD_INFO.txt` source | `a09e299b485d135046b49961c9a3212914579dc3` / `v0.1.0-rc2` |
| RC2 ZIP SHA256 | `BA3A9ADD4132EFF6188E3981C627400647941C572059F3D733347A3EE6823051` |
| RC2 EXE SHA256 | `67DF840B832EE9072375A3A267DF220DBB546FD61EF8B048EA8C8C6B17D20F71` |
| Extracted onedir | 67 files before adding test tools |

The ZIP and EXE hashes in the guest matched the host staging ZIP byte-for-byte. The ZIP is identified as RC2 by `BUILD_INFO.txt` and points to the RC2 tag commit; this is not the RC1 binary.

### Artifact documentation discrepancy

The supplied ZIP's `RC_SMOKE_TEST.md` records EXE SHA256 `9BFDE4CE679EDF819AB4CB19E7E29FC6B4D5206134BA63D5739C6F87E27D0AD0`, while the actual EXE in that ZIP is `67DF840B…`. Its `RC_BUILD_NOTES.md` also calls `F5F2DD82…` the build-time hash and lists `9BFDE4CE…` as an earlier gate build. The handoff explicitly identified `67DF840B…` as the supplied RC2 guest hash, so that exact binary was tested, but the packaged integrity record should be reconciled before release.

## Tool phases

The fresh extracted RC2 initially had no `tools` directory and no `config.json`. It reported all three tools as not found. A real ZIP task then ended `FAILED / TOOL_NOT_FOUND`, created no final output, and preserved source SHA256 `22A2E30E7B02681C59E161E5863C1CD476159A9AA6D64F60E760BB558267F79C`.

For the enabled phase, the previously license-recorded fixture tools were copied into the fresh onedir through guestcontrol:

| Tool | Version | SHA256 | Detection |
|---|---|---|---|
| 7-Zip | 26.02 x64 | `83967F1B02B43C4EFEDA302795722C809E0E81B8307DE73558D10484D5676A7D` | PASS |
| `7z.dll` | — | `69FD4DF057985C40E510E2FAC182881C7F85E90AA13EC703F763A8FDB2CE61F8` | PASS |
| WinRAR CLI `Rar.exe` | 7.23 x64 | `F561764BC3E9ED208744321A89A819B562EDEAF06E203C02A06976121FDA1991` | PASS |
| LZ4 | 1.10.0 x64 | `C2B1ECAB4289B72CE97257C699D497D3B34387E04F935FB7524C4FA17B05F248` | PASS |

## Checklist results

| # | Checklist item | Result | Evidence / observation |
|---:|---|---|---|
| 1 | No-Python startup | **PASS** | Standard user; no installed Python; Store alias exit 9009. EXE started with no `python.dll missing`, module error, traceback, UAC, or Python-install prompt. |
| 2 | RC version information | **PASS** | Startup showed `GameArchiveManager`, `0.1.0`, `Release Candidate`; tool-enabled runs also reported the same identity. |
| 3 | Development-machine path independence | **PASS** | No local Windows username, `GrokWork`, or development-tree marker in EXE/`_internal`. Two Markdown documents contain the expected example `GameArchiveManager0.1.0` text only; there were no runtime-binary hits or attempted host-path access. |
| 4 | No external tools | **PASS** | Fresh onedir showed 7-Zip/WinRAR/LZ4 `NOT FOUND`; a real ZIP failed explicitly with `TOOL_NOT_FOUND`, source hash unchanged, no final output. |
| 5 | 7-Zip re-detection | **PASS** | Fresh restart detected sibling `tools\7z.exe`, version 26.02, usable with matching `7z.dll`. |
| 6 | WinRAR CLI detection | **PASS** | Detected sibling `tools\Rar.exe`, version 7.23, usable CLI (not GUI-only discovery). |
| 7 | LZ4 detection | **PASS** | Detected sibling `tools\lz4.exe`, version 1.10.0, usable. |
| 8 | Ordinary formats | **PASS** | ZIP, 7Z, RAR, LZ4, and composite RAR.LZ4 each ended `COMPLETED`, `failed_count=0`; expected payload delivered; every source hash unchanged. |
| 9 | Split volumes | **PASS** | Complete 7z `.001`–`.004` previewed one archive and restored `large.bin` (180000 bytes). Complete RAR `part1`–`part4` previewed one archive and restored its 180000-byte payload. Lone first parts failed before extraction with both `VOLUME_DETECTION` and `MISSING_VOLUME`, no final output, source hashes unchanged. |
| 10 | Password archives | **PASS** | Automatic one-time candidate completed; wrong manual entry followed by correct entry completed with two manual attempts; all-wrong then skip ended `FAILED` with final `WRONG_PASSWORD` and no final output. Source hashes unchanged. Searches found zero plaintext password hits in logs, history, or captured stdout evidence. |
| 11 | JPEG + embedded RAR | **PASS** | JPEG+plain RAR and JPEG+encrypted RAR5 both detected embedded RAR and ended `COMPLETED`, recovering expected files with source hashes unchanged. A separate directory containing a normal JPEG, DLL, EXE, Unity `.assets`, and one ZIP previewed only one archive; the four non-archives remained untouched. |
| 12 | Chinese paths | **PASS** | Chinese task directory, archive name, and internal filename completed without mojibake; console echoed the correct path; two safe incremented output directories existed after repeat harness passes; source hash unchanged. History remained UTF-8-readable. |
| 13 | Repeat run | **PASS** | A fresh repeat case ran three consecutive times: all `COMPLETED`, preview count stayed `1, 1, 1`, outputs were `archive`, `archive_2`, `archive_3`, and source hash stayed unchanged. |
| 14 | Ctrl+C at EXTRACTING / SCANNING / VALIDATING | **BLOCKED** | Redirected guestcontrol stdin is not interactive in VirtualBox 7.2.16. A guest console-control harness failed to observe/send a verified phase-specific Ctrl+C and wedged the guestcontrol/COM session. No phase was claimed as PASS and no force-kill was substituted as evidence. The three current-RC2-hash interruption cases remain unproven in this run. |
| 15 | Final output directory | **PASS** | Final outputs were under each task's `GameArchive_Output`; repeated results incremented safely. No `password_attempt_*`, extracted-temporary, or scan-temporary directory appeared in final output. |
| 16 | History, logs, reports | **PASS** | Data remained under `%LOCALAPPDATA%\GameArchiveManager`; app onedir contained no `logs` or `history`. History was UTF-8-readable and new records/logs carried `0.1.0 / Release Candidate`; password searches had zero hits. |
| 17 | Safety verification | **PASS** | Tested source archives retained pre-run SHA256. Original task directories and old outputs remained present. The deliberately unknown `keep_extracted\user_file.txt` survived cleanup. No cleanup crossed a test-task boundary. |

Windows 10 (environment B) was not run; the checklist marks it conditional.

## Blocking infrastructure state

During item 14, allocating a console inside a guestcontrol-launched PowerShell process wedged the VirtualBox guestcontrol clients. I terminated only the stuck host-side `VBoxManage` client processes and restarted `VBoxSVC`; I did not hard-power-off the VM. The headless `Win11-Sandbox` VM process remained alive, but the new service could not reacquire its machine lock (`VBOX_E_VM_ERROR` / `E_FAIL`), and a non-destructive ACPI power-button request was refused for the same reason. Teardown therefore remains blocked; the VM process was intentionally left untouched rather than force-killed.

## Evidence locations

- Guest root: `%LOCALAPPDATA%\Temp\rc2_codex_20260827`
- Guest machine-readable summary: `%LOCALAPPDATA%\Temp\rc2_codex_20260827\evidence\core_summary.json`
- Guest per-case stdout: `%LOCALAPPDATA%\Temp\rc2_codex_20260827\evidence\*.output.txt`
- Local boot screenshot: `.vm_gate\rc2_codex_boot.png`
- Local guest runner source: `.vm_gate\rc2_codex_core.ps1`

No credential or test password is included in this report.

## Gate recommendation

**Do not check `clean_windows_11_vm` yet.** Re-run checklist item 14 against EXE `67DF840B…` using a restored guestcontrol session or an interactive console path, capture all three phase-specific Ctrl+C results plus reruns, and reconcile the packaged EXE hash documentation. If those checks pass without a product failure, the remaining results in this report support recommending the gate.
