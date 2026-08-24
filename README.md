# GameArchiveManager

Windows 游戏资源包整理工具：按真实文件头识别格式，递归解压，有限密码尝试，安全交付最终内容。

**当前版本：0.1.0 Release Candidate。不是正式 Release。**  
干净 Windows 11 虚拟机门禁尚未勾选通过（`clean_windows_11_vm` 仍为 `false`）。

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

首屏直接粘贴/拖入文件或目录路径；`M` 菜单，`Q` 退出。真实解压需要本机已安装并被发现的 7-Zip / WinRAR CLI / LZ4。

可选配置见 [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)。日志与 history 默认在 `%LOCALAPPDATA%\GameArchiveManager`。

## 测试

```powershell
py -B -m unittest discover -s tests -v
py scripts/verify_project_state.py
py scripts/rc_readiness.py
```

当前自动测试基线见 `project_state.json`（不少于 224，最近核验 228）。`rc_readiness.py` 在 VM 门禁完成前应为 **NO-GO**。

## 打包 RC

见 [`docs/RC_BUILD_NOTES.md`](docs/RC_BUILD_NOTES.md) 与 [`docs/RC_SMOKE_TEST.md`](docs/RC_SMOKE_TEST.md)。必须复制整个 onedir，不能只拷 EXE。

## 文档

- 当前状态：[`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md)
- 交接入口：[`GROK_START_HERE.md`](GROK_START_HERE.md)
- 用户指南：[`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)
- 已知问题：[`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)

## 许可证

源码为 [MIT](LICENSE)。7-Zip、WinRAR、LZ4 各有自己的许可证，由你安装的那份二进制决定。
