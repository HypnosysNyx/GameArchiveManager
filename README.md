# GameArchiveManager

Windows tool for game archive recovery: identify real formats from file headers, extract recursively, try a limited set of passwords, and deliver final content safely.

**Current version: 0.1.0 Release Candidate. This is not a stable Release.**  
The clean Windows 11 VM gate is still `false` (`clean_windows_11_vm` in `project_state.json`).

[中文说明](#gamearchivemanager-中文)

## What it does

- Does not trust extensions: ZIP / RAR / 7Z / LZ4, disguised files, JPEG-embedded RAR, split volumes
- Recursive unpack and composite wrappers (for example LZ4→RAR)
- Automatic password candidates plus interactive CLI recovery (`getpass`; secrets are not written to logs, reports, or history)
- Delivers a game root or generic content, not leftover technical folders
- Does not modify source files, overwrite old output, or delete user directories by name

## What it does not include

- No bundled 7-Zip, WinRAR, or LZ4 binaries (install them yourself or set paths in `config.json`)
- No silent download/install of tools
- No GUI in 0.1.0

The official LZ4 CLI is GPL-2.0-or-later; this repository does not ship `lz4.exe`.

## Run from source

Windows 10/11, Python 3.10+, `py` launcher. No third-party pip packages (`requirements.txt` is empty).

```powershell
py main.py
```

Or double-click `start_game_archive_manager.bat`.

Paste or drop a file/folder path at the first prompt; `M` opens the menu; `Q` quits. Real extraction needs a discovered 7-Zip, WinRAR CLI, or LZ4 install.

Optional config: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md). Logs and history default to `%LOCALAPPDATA%\GameArchiveManager`.

## Tests

```powershell
py -B -m unittest discover -s tests -v
py scripts/verify_project_state.py
py scripts/rc_readiness.py
```

See `project_state.json` for the test baseline (minimum 224; last verified 228). `rc_readiness.py` should report **NO-GO** until the VM gate is complete.

## RC build

[`docs/RC_BUILD_NOTES.md`](docs/RC_BUILD_NOTES.md) and [`docs/RC_SMOKE_TEST.md`](docs/RC_SMOKE_TEST.md). Copy the full onedir; never ship the EXE alone.

## Docs

- Status: [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md)
- Handoff: [`GROK_START_HERE.md`](GROK_START_HERE.md)
- User guide: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)
- Known issues: [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)

## License

Source is [MIT](LICENSE). 7-Zip, WinRAR, and LZ4 keep their own licenses on whatever binaries you install.

---

# GameArchiveManager (中文)

Windows 游戏资源包整理工具：按真实文件头识别格式，递归解压，有限密码尝试，安全交付最终内容。

**当前版本：0.1.0 Release Candidate。不是正式 Release。**  
干净 Windows 11 虚拟机门禁尚未勾选通过。

## 能做什么

- 不信扩展名：ZIP / RAR / 7Z / LZ4、伪装、JPEG 内嵌 RAR、分卷
- 递归解压与复合包装（例如 LZ4→RAR）
- 自动密码候选 + 交互 CLI 人工补密（明文不进日志 / 报告 / history）
- 交付游戏根或 Generic Content，而不是把中间目录当成品
- 不修改源文件、不覆盖旧输出、不按名字乱删用户目录

## 不包含

- 不捆绑 7-Zip、WinRAR、LZ4 可执行文件（请自行合法安装或在 `config.json` 里写路径）
- 不自动下载/安装外部工具
- 当前没有 GUI

LZ4 官方 CLI 是 GPL-2.0-or-later，本仓库不附带 `lz4.exe`。

## 运行（源码）

要求：Windows 10/11，Python 3.10+，启动器 `py`。无第三方 pip 依赖。

```powershell
py main.py
```

或双击 `start_game_archive_manager.bat`。

首屏直接粘贴/拖入路径；`M` 菜单，`Q` 退出。真实解压需要本机已安装并被发现的 7-Zip / WinRAR CLI / LZ4。

可选配置见 [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)。日志与 history 默认在 `%LOCALAPPDATA%\GameArchiveManager`。

## 测试与打包

命令与英文部分相同。基线见 `project_state.json`。打包说明见 `docs/RC_BUILD_NOTES.md`。必须复制整个 onedir。
