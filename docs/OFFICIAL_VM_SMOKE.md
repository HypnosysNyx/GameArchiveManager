# Official 0.1.0 VM smoke — format/password/Chinese path

Time: 2026-09-03T17:15:00+08:00

- VM: `Win11-Sandbox` was already running; it was left running.
- Guest Additions: available; guest user: `sandbox`.
- Formal package: `dist\GameArchiveManager-0.1.0.zip`; guest copy completed with `.vm_gate\guestcontrol.passwordfile`.
- Guest execution: `.vm_gate\rc2_codex_core.ps1`, with the staged fixture payload and tools.
- Formats: ZIP, 7Z, RAR, LZ4, RAR.LZ4, nested archives, and complete/missing-volume cases passed.
- Passwords: automatic password, wrong-then-correct, and all-wrong handling passed; source archives unchanged and password evidence hits were `0`.
- Chinese path: `中文路径_测试游戏` completed; source archive unchanged and two output files were produced.
- Repeat/cleanup checks also completed; no unexpected final directories were found.

Result: **PASS** — the requested official VM second pass completed without human interaction. The VM was not shut down.
