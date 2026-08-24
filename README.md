# GameArchiveManager

[![CI](https://github.com/HypnosysNyx/GameArchiveManager/actions/workflows/ci.yml/badge.svg)](https://github.com/HypnosysNyx/GameArchiveManager/actions/workflows/ci.yml) [![CodeQL](https://github.com/HypnosysNyx/GameArchiveManager/actions/workflows/codeql.yml/badge.svg)](https://github.com/HypnosysNyx/GameArchiveManager/actions/workflows/codeql.yml) [![Latest release](https://img.shields.io/github/v/release/HypnosysNyx/GameArchiveManager)](https://github.com/HypnosysNyx/GameArchiveManager/releases/latest) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Windows CLI tool for messy **game download archives**: it looks at real file headers (not the extension), unpacks nested wrappers, tries a limited set of passwords, and copies the actual game (or generic content) to a safe output folder.

It is not a save-file manager, not a GUI, and not a replacement for 7-Zip. You still install 7-Zip; this program decides *what* to unpack and *what* to keep.

**Current version: 0.1.0 RC2 (Release Candidate)** — not a stable release.  
Automated tests and the Windows build smoke test passed. Clean Windows 10/11 VM revalidation for RC2 is still pending.

**[Download this program](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.1.0-rc2/GameArchiveManager-0.1.0-RC2.zip)** · [SHA-256 checksums](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.1.0-rc2/GameArchiveManager-0.1.0-RC2.sha256) · [中文说明](#gamearchivemanager-中文)

### Privacy and RC2 security note

- The application has no network, telemetry, analytics, crash-report upload, or cloud-sync logic.
- It processes only the file or directory you provide. A directory task recursively scans that selected tree.
- Logs and history stay under `%LOCALAPPDATA%\GameArchiveManager`, but they contain full local paths and should be treated as private data.
- Passwords are not persisted. Manual input is visible in the console; RC2 sends passwords to 7-Zip through redirected standard input instead of the process command line.
- RC2 rejects extracted symbolic links and Windows reparse points before hashing or final delivery. The executable is unsigned; verify the published SHA-256 checksum before running it.

---

## What it can do (all current features)

| Area | Behavior |
| --- | --- |
| Formats | ZIP, RAR, 7Z, LZ4 (LZ4 needs `lz4.exe`). Trusts headers, not `.jpg` / `.bin` names |
| Nested packs | Recursively unpacks wrappers (for example LZ4→RAR) |
| Disguise / embed | Fake extensions; JPEG host with an embedded RAR |
| Split volumes | Treats `file.7z.001` + `.002` or `file.part01.rar` + `part02` as one job; missing volume stops *before* extract |
| Passwords | Auto-tries **empty folder names** next to the archive; then you can type a password (visible, Chinese IME works). Success is remembered only until you quit |
| Delivery | Copies a game root or generic content into `GameArchive_Output`. Intermediate `*_extracted` folders are not the final product |
| Safety | Does not modify or delete source archives; does not overwrite previous output (`_2`, `_3`); does not delete user folders by name |
| Tools | Finds 7-Zip / WinRAR CLI / LZ4 at startup. Does not download or install them |
| Containers | Leaves APK / Word / Excel / PowerPoint / EPUB / JAR intact unless you drop that file itself as the task |
| Platform skip | Optional: ignore Android/安卓 or AZ-tagged paths via `config.json` (off by default) |
| Session | One window: many tasks in a row; menu for batch paths, last report, tool status, settings |

Not included: GUI, bundling 7-Zip/WinRAR/LZ4, persistent password vault, deleting source archives, save-game backup.

---

## Windows build (for most users)

1. Install 64-bit **[7-Zip](https://www.7-zip.org/)** to the default folder `C:\Program Files\7-Zip\`. That one tool is enough for ZIP, RAR, and 7Z. WinRAR is only a RAR fallback. LZ4 is only for `.lz4`.
2. **[Download this program](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.1.0-rc2/GameArchiveManager-0.1.0-RC2.zip)** (`GameArchiveManager-0.1.0-RC2.zip`). Unzip the **whole folder**. Do not copy the `.exe` alone. The executable is unsigned, so verify the accompanying [SHA-256 checksums](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.1.0-rc2/GameArchiveManager-0.1.0-RC2.sha256).
3. Double-click `GameArchiveManager.exe`. You do not need Python. If 7-Zip was just installed, **restart this program** so it can see `7z.exe`.
4. Startup should show `0.1.0` / `Release Candidate` and `7-Zip: 可用` (or FOUND).
5. Drag a **folder** (or one archive file) onto the black window, or paste the path, then Enter.
6. Read the preview. Type `Y` then Enter to run, `N` to cancel.
7. Results appear in that folder as `GameArchive_Output`. Press Enter to do another path. `Q` quits.

### Passwords

**Automatic:** next to the archive, create an **empty folder whose name is the password** (Chinese names are fine). The program tries that name. It does not use ordinary file names as passwords.

**Manual:** when automatic tries fail:

- `I` — type a password (it **is shown** on screen so any IME works). Not written to logs, reports, or history.
- `S` — skip this archive
- `C` — cancel the whole task

A password that actually worked is reused for later archives in the **same running window only**.

### Commands

| Input | Meaning |
| --- | --- |
| path / drag-drop | Start a task (quotes around paths with spaces are stripped) |
| `Y` / `N` | Confirm or cancel after preview |
| `M` | Full menu: `1` new/batch tasks, `2` last result, `3` tools, `4` settings, `0` back |
| `Q` | Quit |
| `Ctrl+C` | Interrupt the current task; source files stay; leftover temp dirs may be kept as `ORPHANED_TEMP`. Next run does not treat those as new archives |

If several game roots look equally valid, the program asks which ones to keep.

---

## Tools (how auto-detect works)

At **startup** it looks, in order: `config.json` path → `tools\7z.exe` (or one subfolder) beside the EXE → `C:\Program Files\7-Zip\7z.exe` → Windows PATH. Same idea for `Rar.exe` and `lz4.exe`.

Install 7-Zip, then restart GameArchiveManager. A 32-bit 7-Zip under `Program Files (x86)` is **not** searched; use the 64-bit installer or put `7z.exe` in this program’s `tools\` folder.

Missing tools do not crash the app; that job fails with `TOOL_NOT_FOUND`.

---

## Output locations

| What | Where |
| --- | --- |
| Final files | `<your task folder>\GameArchive_Output` (then `_2`, `_3` if you run again) |
| Logs / history | `%LOCALAPPDATA%\GameArchiveManager\` |
| Optional config | EXE folder `config.json`, else `%LOCALAPPDATA%\GameArchiveManager\config.json` |

The program never writes logs into the EXE folder. It never auto-creates `config.json`. Fields: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

---

## Run from source

Windows 10/11, Python 3.10+, `py`. Runtime has no third-party Python dependencies; build dependencies are listed in `requirements-build.txt`.

```powershell
py main.py
```

Or `start_game_archive_manager.bat`. Same CLI as the EXE. Tests: `py -B -m unittest discover -s tests -v`.

---

## License

Source is [MIT](LICENSE). 7-Zip, WinRAR, and LZ4 stay under their own licenses. The official LZ4 CLI is GPL-2.0-or-later; this repo does not ship `lz4.exe`.

More docs: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) · [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) · [`docs/SECURITY.md`](docs/SECURITY.md) · [`security audit`](docs/SECURITY_AUDIT_2026-08-24.md) · [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md) · [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)

Project policies: [`SECURITY.md`](SECURITY.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

---

# GameArchiveManager (中文)

面向 Windows 的**游戏下载资源包**整理工具：不看扩展名、看真实文件头，递归解开层层包装，有限次数试密码，把真正的游戏（或普通内容）安全复制出来。

它**不是**游戏存档管理器，**没有**图形界面，也**不能代替** 7-Zip。请先自己安装 7-Zip；本程序负责判断解什么、留下什么。

**当前版本：0.1.0 RC2 Release Candidate（候选版，不是正式版）。**  
自动化测试和 Windows 构建冒烟测试已通过；RC2 的干净 Windows 10/11 虚拟机复验仍待完成。

**[下载本程序](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.1.0-rc2/GameArchiveManager-0.1.0-RC2.zip)** · [SHA-256 校验文件](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.1.0-rc2/GameArchiveManager-0.1.0-RC2.sha256)

### 隐私与 RC2 安全说明

- 应用没有网络通信、遥测、分析、崩溃上报或云同步逻辑。
- 只处理用户提交的文件或目录；目录任务会递归扫描用户选择的目录树。
- 日志和历史只保存在 `%LOCALAPPDATA%\GameArchiveManager`，但其中包含完整本地路径，应视为私人数据。
- 密码不会持久化。手动密码会显示在控制台；RC2 通过重定向标准输入将密码传给 7-Zip，不再放入进程命令行。
- RC2 会在哈希和最终交付前拒绝解压结果中的符号链接与 Windows reparse point。当前 EXE 未签名，运行前请核对发布的 SHA-256。

## 介绍

网上的游戏资源经常是：假后缀、套了多层压缩、分卷、JPEG 里藏 RAR、带密码、里面还有安卓包或 Office 文件。直接用 7-Zip 全解开，容易得到一堆技术目录，或把不该拆的 APK 拆开。

本程序会：

1. 扫描你给出的文件夹或单个压缩包  
2. 按文件头识别 ZIP / RAR / 7Z / LZ4  
3. 把分卷当成一套、缺卷就停  
4. 递归解开包装层（例如 `.rar.lz4`）  
5. 用旁边空文件夹的名字自动试密码，不行再让你输入  
6. 把「游戏根目录」或「普通内容」拷到 `GameArchive_Output`  
7. 源压缩包原样不动，旧结果不被覆盖  

## 小白怎么用（推荐）

1. 安装 64 位 [7-Zip](https://www.7-zip.org/)，装到默认位置。  
   **只要这一个软件就够解 ZIP、RAR、7Z。** 不必为了 RAR 再装 WinRAR。只有 `.lz4` 才需要另备 `lz4.exe`。  
2. 点 **[下载本程序](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.1.0-rc2/GameArchiveManager-0.1.0-RC2.zip)**，得到 `GameArchiveManager-0.1.0-RC2.zip`（软件，不是系统镜像）。当前 EXE 未签名，请核对同页提供的 [SHA-256 校验文件](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.1.0-rc2/GameArchiveManager-0.1.0-RC2.sha256)。  
3. 解压后保留**整个文件夹**（里面有 `GameArchiveManager.exe` 和 `_internal`）。不要只拷一个 exe。  
4. 双击 `GameArchiveManager.exe`。刚装完 7-Zip 的话，请先关掉本程序再开一次，才会识别到。  
5. 启动时应看到版本 `0.1.0`、`Release Candidate`，以及 7-Zip 状态为「可用」。  
6. 把「游戏压缩包所在的文件夹」拖进黑窗口（或粘贴路径）回车。  
7. 预览后输入 `Y` 回车开始。结果在该文件夹下的 `GameArchive_Output`。  
8. 按 Enter 可以继续处理下一个路径。输入 `Q` 退出。

## 全部功能说明

### 启动与日常操作

| 你输入 | 作用 |
| --- | --- |
| 路径 / 拖放文件或文件夹 | 直接开始任务（带空格的路径若被包上英文引号，会自动去掉） |
| `Y` / `N` | 预览后确认执行 / 取消本次（不退出程序） |
| `M` | 打开完整菜单 |
| 菜单 `1` | 新建任务，可连续输入**多个路径**（批量）；空行开始预览 |
| 菜单 `2` | 查看本窗口内最近一次任务报告 |
| 菜单 `3` | 查看 7-Zip / WinRAR / LZ4 是否找到 |
| 菜单 `4` | 查看当前已加载的设置（改 `config.json` 后要重启才生效） |
| 菜单 `0` | 返回路径输入 |
| `Q` | 退出程序 |
| `Ctrl+C` | 中断当前任务。源文件不变；可能留下标记为 `ORPHANED_TEMP` 的临时目录。下次运行不会把这些临时目录当成新压缩包 |

若识别出多个都像「最终游戏」的目录，会让你选择保留哪几个。

### 识别与解压

- **不信扩展名**：`.jpg` 其实是 ZIP、JPEG 图片后面藏 RAR，都会按真实格式处理。  
- **支持**：ZIP、RAR、7Z；LZ4 需本机有 `lz4.exe`。  
- **分卷**：`xxx.7z.001` + `.002`，或 `xxx.part01.rar` + `part02`，只生成一个任务。缺第二卷会在解压前失败（`VOLUME_DETECTION` / `MISSING_VOLUME`）。  
- **套娃**：一层层解开直到游戏内容；例如 LZ4 包着 RAR。  
- **复合包装**：外层和内层其实是同一内容时，只解该解的那一层，外层文件仍保留在原处。  

RAR **优先用 7-Zip**；只有 7-Zip 解 RAR 失败时才尝试 WinRAR 的 `Rar.exe`（不是双击那个 WinRAR 窗口程序）。

### 密码

**自动（方便小白）：**  
在压缩包旁边建一个**空文件夹**，文件夹的名字写成密码（可以中文）。把整个目录拖进程序，会自动拿文件夹名去试。不会把普通文件名当成密码。

**手动：** 自动都失败后：

- `I`：输入密码（**会显示在屏幕上**，中文输入法可直接打，不用切英文）。不会写入日志、报告、history。  
- `S`：跳过这个加密包  
- `C`：取消整次任务  

解成功的密码只记在当前窗口内存里，关程序即消失。没有「记住密码」库。

### 交到哪里、不会做什么

- 最终结果：任务目录下的 `GameArchive_Output`。再跑一次会变成 `GameArchive_Output_2`，**不覆盖**旧结果。  
- 中间解压目录（如 `某包_extracted`）是技术目录，不是成品。  
- **不修改、不删除**你的源压缩包。  
- **不按名字乱删**你的文件夹。  
- 日志和历史：`%LOCALAPPDATA%\GameArchiveManager\`，不写在程序目录里。  

### 特殊文件

自动扫描时，下面这些即使底层是 ZIP 也**默认不拆**：APK、Word、Excel、PowerPoint、EPUB、JAR。  
如果你把其中一个文件**单独拖进去当任务**，则按你的明确意图，可以按 ZIP 去解。

默认**不会**因为名字带 Android / 安卓 / AZ 就跳过。若要跳过，需自己在 `config.json` 里把 `ignore_android` 或 `ignore_AZ` 设为 `true`。

### 工具如何自动识别

程序**启动时**按顺序找，不会在运行中途再扫硬盘：

1. `config.json` 里写的路径  
2. 程序目录 `tools\7z.exe` 或 `tools\某个子文件夹\7z.exe`  
3. `C:\Program Files\7-Zip\7z.exe`  
4. 系统 PATH  

WinRAR 找 `C:\Program Files\WinRAR\Rar.exe`；LZ4 找 `tools\lz4.exe` 等。  
装完 7-Zip 后必须**重启本软件**。32 位 7-Zip 装在 `Program Files (x86)` 时当前不会自动找到：请装 64 位，或把 `7z.exe` 放到本程序的 `tools\`。

缺工具时程序不崩溃，该任务会提示未找到工具。

### 可选配置

一般不用建配置文件。需要时在 EXE 同目录放 `config.json`（优先），或放在 `%LOCALAPPDATA%\GameArchiveManager\config.json`。程序**不会**自动生成。完整字段见 [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)。

## 常见问题

**预览完没解压？** 必须输入 `Y`。`N` 只取消这一次。  

**提示找不到 7-Zip？** 确认已安装 64 位 7-Zip，关掉本程序再开。或把 `7z.exe` 放到 `tools\`。  

**为什么出现 `_2`？** 防止覆盖上次的 `GameArchive_Output`。  

**密码中文打不进去？** 请使用本页下载的 RC2 版本（可见输入）。更旧的包会隐藏输入，中文输入法会失效。  

**只有 WinRAR、没有 7-Zip？** 不够。zip/7z 不会走 WinRAR。请装 7-Zip。  

## 源码运行

Windows 10/11，Python 3.10+，`py`。运行时没有第三方 Python 依赖；构建依赖见 `requirements-build.txt`。

```powershell
py main.py
```

或双击 `start_game_archive_manager.bat`。操作与打包版相同。

```powershell
py -B -m unittest discover -s tests -v
```

## 许可证

源码 [MIT](LICENSE)。你自己安装的 7-Zip、WinRAR、LZ4 仍用它们自己的许可证。官方 LZ4 命令行是 GPL-2.0-or-later，本仓库不附带 `lz4.exe`。

项目协作与安全：[`安全报告`](SECURITY.md) · [`贡献指南`](CONTRIBUTING.md) · [`行为准则`](CODE_OF_CONDUCT.md) · [`审计摘要`](docs/SECURITY_AUDIT_2026-08-24.md)
