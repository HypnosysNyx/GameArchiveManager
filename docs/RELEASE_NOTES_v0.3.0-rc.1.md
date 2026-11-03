# GameArchiveManager v0.3.0 RC1 — Windows + Linux

> **Newest packaged release / 最新可下载版本：v0.3.0 RC1（预发布）**。GitHub 的 “Latest” 目前仍指向较旧的 v0.2.0 源码版，因为 RC 预发布不能获得 Latest 标记。请下载此页的 Windows/Linux 安装包，不要从 v0.2.0 期待新版 EXE 或 wheel。
>
> **Newest downloads are below.** The older v0.2.0 is source-only; this release candidate is not yet a fully verified stable release.

| Platform / 平台 | Download / 下载 | SHA-256 |
| --- | --- | --- |
| **Windows x64** | [Portable GUI + CLI ZIP](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.3.0-rc.1/GameArchiveManager-0.3.0rc1-windows-x64.zip) | [Windows checksum](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.3.0-rc.1/GameArchiveManager-0.3.0rc1-windows-x64.zip.sha256) |
| **Linux** | [Python wheel](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.3.0-rc.1/game_archive_manager-0.3.0rc1-py3-none-any.whl) | [Linux SHA256SUMS](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.3.0-rc.1/SHA256SUMS) |

**Windows：**完整解压 ZIP，安装 7-Zip 后双击 `GameArchiveManager.exe` 打开图形界面；命令行版本为 `GameArchiveManager-CLI.exe`。不需要单独安装 Python。**Linux：**先安装原生 `7zip`、`lz4`、`python3-tk`、`python3-venv`、`pipx`，再运行 `pipx install --python /usr/bin/python3 ./game_archive_manager-0.3.0rc1-py3-none-any.whl`。详情见 [Linux 安装和更新指南](https://github.com/HypnosysNyx/GameArchiveManager/blob/main/docs/LINUX.md)。


This is a **public release candidate**, not a completed clean-machine or private-sample acceptance signoff.

## Downloads

- **Windows x64**: portable ZIP with `GameArchiveManager.exe` (no-console GUI) and `GameArchiveManager-CLI.exe` (console); extract the entire ZIP first. No Python installation is required.
- **Linux**: Python wheel, installable with `pipx` or a Python virtual environment. The CLI command is `game-archive-manager`, and the desktop command is `game-archive-manager-gui`.
- **Source**: the same repository and core Python code power both systems. See [Linux setup](https://github.com/HypnosysNyx/GameArchiveManager/blob/main/docs/LINUX.md).

Use the SHA-256 checksum files supplied beside each binary to verify downloads.

## New in this candidate

- Native Linux XDG config, history, log paths; native `7z` and `lz4`; no Wine required.
- Linux password persistence through Secret Service when available and unlocked. If no persistent library exists and the keyring is unavailable, session-only passwords still work. Existing locked/corrupted libraries fail closed rather than appearing empty.
- Windows password library remains encrypted via the current Windows user's DPAPI; saved secrets are not embedded in release assets.
- UI improvements, settings/config source visibility, and password-library access.
- Automatic candidate discovery from empty folders alongside an explicitly selected archive; the normal folder-level scan remains supported.
- Better embedded RAR5 candidate validation and error diagnostics. No bypass of content CRC, file-boundary checks, or size limits.
- Separate graphical and command-line entry points, plus automated cross-platform source/build verification.

## Installation prerequisites

Windows: install 7-Zip; LZ4 and WinRAR are optional depending on the source material. These third-party programs are **not** bundled with our ZIP. Windows x64 is the build target.

Linux: install system `7zip`, `lz4`, `python3-tk`, and `pipx`; on Ubuntu/Debian, read [Linux setup](https://github.com/HypnosysNyx/GameArchiveManager/blob/main/docs/LINUX.md) for commands. Python 3.10 or newer is required when running from source or wheel.

## Important acceptance limits

- The newest multi-GiB private nested/encrypted RAR test cases have **not** completed end-to-end extraction. Their outer layers, password clues and synthetic regression coverage do not prove the encrypted inner contents can be delivered successfully. Failures must remain visible.
- A fresh clean Windows 11 VM test of this new binary has **not** been completed. Windows 10 VM acceptance is likewise pending.
- Ubuntu native synthetic extraction and GUI smoke have been checked in WSL2, but a general Linux desktop visual review and unlocked Secret Service persistence roundtrip are still pending.
- The Windows EXE is not code signed; Windows SmartScreen may warn. Verify SHA-256 before running.
- Release assets must not contain user configuration, source archives, password vaults, local logs, or private diagnostic screenshots.

This candidate is suitable for evaluation with non-sensitive backup copies. **Do not delete the original archives or trust a partial outer archive delivery as completion.**

## Updates

Windows: download and extract the newest ZIP into a fresh program folder; retain your user data and existing outputs separately. Do not overwrite running files.

Linux: a single Git-based package can be refreshed with `pipx install --force --python /usr/bin/python3 'git+https://github.com/HypnosysNyx/GameArchiveManager.git@main'`, or install a reviewed tag/commit for reproducibility. See [Linux setup](https://github.com/HypnosysNyx/GameArchiveManager/blob/main/docs/LINUX.md) for isolation, data migration cautions and exact paths.

## Privacy and provenance

Published source and assets are restricted to reviewed application code, tests, non-identifying documentation and generated executables/wheel. Raw local handoffs, downloaded samples, personal paths, password-store data, local settings and screenshots are not shipped. Prior Git history is preserved and is not rewritten as part of this candidate.
