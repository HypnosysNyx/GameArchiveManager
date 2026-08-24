# GameArchiveManager

面向 Windows 的本地游戏资源包识别、递归解压与整理工具。

> [!IMPORTANT]
> 名称中的 “Archive” 指压缩归档。本项目不是游戏存档（save file）备份工具，不读取 Steam `userdata`，也不会自动寻找游戏安装目录。

当前版本：**0.1.0 Release Candidate 2**。本轮自动化与本机 Windows 构建验证已通过；安全修复后的干净 Windows 11/10 虚拟机复验仍待完成。

[下载 0.1.0 RC2](https://github.com/HypnosysNyx/GameArchiveManager/releases/download/v0.1.0-rc2/GameArchiveManager-0.1.0-RC2.zip) · [全部 Releases](https://github.com/HypnosysNyx/GameArchiveManager/releases) · [English](#english)

> [!WARNING]
> `v0.1.0-rc1` 早于本轮安全审计，不包含“密码通过标准输入传递”和“拒绝文件符号链接/reparse point”两项加固。请使用 `v0.1.0-rc2` 或更新版本；RC2 仍是预发布版。

## 目录

- [项目简介](#项目简介)
- [功能](#功能)
- [隐私与本地数据](#隐私与本地数据)
- [安装](#安装)
- [使用](#使用)
- [配置与安全限制](#配置与安全限制)
- [从源码运行](#从源码运行)
- [安全边界](#安全边界)
- [文档](#文档)
- [License](#license)
- [English](#english)

## 项目简介

游戏下载资源常见假扩展名、多层压缩、分卷、嵌入式归档和加密归档。GameArchiveManager 根据文件内容判断真实格式，按受限队列递归处理归档，再把识别到的最终内容复制到独立输出目录。

程序本身不替代解压软件。ZIP、RAR、7Z 需要本机安装 7-Zip；RAR 可选用 WinRAR 作为有限回退；LZ4 需要 `lz4.exe`。本仓库不捆绑、不下载这些第三方程序。

## 功能

| 功能 | 当前行为 |
| --- | --- |
| 格式识别 | 根据文件头识别 ZIP、RAR、7Z、LZ4，不盲信扩展名 |
| 多层归档 | 受最大深度和任务数限制地递归处理，例如 LZ4 → RAR |
| 伪装与嵌入 | 识别假扩展名，以及受支持媒体文件中的结构有效归档 |
| 分卷 | 支持 `.7z.001`、`.part01.rar` 等；缺卷时在解压前停止 |
| 密码 | 有限尝试空文件夹名称；允许用户手动输入；成功密码仅在本次进程内存中复用 |
| 内容交付 | 将最终游戏根或普通内容复制到 `GameArchive_Output` |
| 防覆盖 | 已有输出不会覆盖，自动使用 `_2`、`_3` 等新名称 |
| 内容容器 | 自动扫描时保留 APK、DOCX、XLSX、PPTX、EPUB、JAR，不把它们当普通 ZIP 展开 |
| 平台过滤 | Android/安卓与 AZ 过滤默认关闭，只能通过配置显式开启 |
| 会话 | 同一 CLI 会话可连续执行单个或批量任务并查看最近结果 |

当前没有 GUI，也没有游戏存档备份、云同步、持久密码库或自动删除源压缩包功能。

## 隐私与本地数据

以下说明以本 README 所在源码版本为准；旧 Release 构建可能早于这里描述的安全修复：

- **无网络通信**：应用代码没有 HTTP、Socket、Webhook、遥测、分析、崩溃上报或自动更新逻辑；不会上传文件、游戏列表、日志或历史。
- **不主动查询身份或硬件**：没有调用用户名、真实姓名、邮箱、主机名、IP、MAC、CPU/GPU、硬盘序列号或设备指纹查询 API。程序会使用 `%LOCALAPPDATA%`（缺失时回退到用户主目录）定位本地运行数据。
- **扫描范围由用户输入决定**：目录任务会递归枚举用户提交目录中的文件和子目录；单文件任务分析用户提交的文件，并在分卷识别需要时检查同目录的相关分卷。程序不会主动扫描整个磁盘、Documents、Desktop、浏览器目录、Steam `userdata` 或游戏安装目录。
- **扫描并非只读取扩展名**：为识别伪装归档，程序会读取所选目录内文件的有限头部；对允许的媒体宿主，嵌入归档检测最多扫描前 512 MiB。重复内容验证可能读取并计算候选输出文件的 SHA-256。
- **本地路径会被记录**：任务日志和历史 JSON 会保存任务、归档、失败项及输出的完整路径。完整路径可能自然包含 Windows 用户目录名，因此这些文件应视为本地隐私数据。
- **密码不持久化**：密码不会写入日志、报告或历史 JSON。手动密码会显示在当前控制台；传给 7-Zip 时通过标准输入管道发送，不放入子进程命令行。成功密码只保留在当前进程内存，退出后消失。
- **全部处理在本机完成**：除启动受信任的本地 7-Zip、`Rar.exe` 或 `lz4.exe` 外，没有远程服务参与。

本地数据位置：

| 数据 | 位置 | 内容 |
| --- | --- | --- |
| 最终输出 | `<任务目录>\GameArchive_Output` | 用户选择交付的解压内容 |
| 中间目录 | `<任务目录>\*_extracted*` | 解压中间结果；异常或中断时可能保留 |
| 日志 | `%LOCALAPPDATA%\GameArchiveManager\logs\` | 时间、任务 ID、完整任务/归档/输出路径、状态与脱敏错误摘要 |
| 历史 | `%LOCALAPPDATA%\GameArchiveManager\history\task_history.json` | 完整路径、时间、任务状态和诊断摘要，不含文件内容清单或密码 |
| 可选配置 | EXE 同目录 `config.json`，否则 `%LOCALAPPDATA%\GameArchiveManager\config.json` | 限制与本地工具路径 |

项目当前没有自动清理日志/历史的保留周期。需要清除本地记录时，请先退出程序，再由用户自行删除 `%LOCALAPPDATA%\GameArchiveManager`；这不会删除任务目录中的源归档或最终输出。

## 安装

### 使用 Windows 构建

1. 从 [7-Zip 官方网站](https://www.7-zip.org/) 安装 64 位版本到默认目录。仅处理 ZIP、RAR、7Z 时通常只需要 7-Zip。
2. 从 [Releases 页面](https://github.com/HypnosysNyx/GameArchiveManager/releases)下载 `v0.1.0-rc2` 或更新版本。`v0.1.0-rc1` 仅保留作历史候选版，不建议用于不受信任的归档。
3. 解压完整文件夹，不要只复制 `GameArchiveManager.exe`。
4. 双击 `GameArchiveManager.exe`。安装或更换外部工具后请重启程序。

发布文件与第三方工具来自不同项目。请只使用可信来源，并保持 7-Zip、WinRAR、LZ4 为受支持的新版本。

## 使用

1. 启动程序后，拖入或粘贴一个归档文件或目录路径。
2. 阅读预览。目录任务会递归扫描该目录；范围过大时请取消并改选更小的目录。
3. 输入 `Y` 确认执行，或输入 `N` 取消。
4. 完成后到任务目录中的 `GameArchive_Output` 查看结果。
5. 按 Enter 继续下一个任务；输入 `M` 打开完整菜单，输入 `Q` 退出。

批量任务通过 `M` → `1` 添加多个路径。`Ctrl+C` 会中断当前任务；源归档保持不变，但已生成的中间目录可能以 `ORPHANED_TEMP` 状态保留。

### 加密归档

- 自动候选仅来自所选目录中的**空文件夹名称**，普通文件名不会用作密码。
- 自动候选失败后，输入 `I` 可手动输入密码，`S` 跳过当前归档，`C` 取消整个任务。
- 手动密码会显示在控制台，以支持中文输入法。请避免在屏幕共享或录屏时输入敏感密码。

## 配置与安全限制

配置文件不是必需的，程序也不会自动创建。可在 EXE 同目录放置 `config.json`；若不存在，再读取 `%LOCALAPPDATA%\GameArchiveManager\config.json`。

建议处理不受信任归档时显式启用解压文件数和总大小限制：

```json
{
  "max_archive_size_mb": 10240,
  "max_extracted_files": 100000,
  "max_total_extracted_size_mb": 102400,
  "max_recursive_depth": 50,
  "max_archive_tasks": 1000,
  "max_initial_archive_tasks": 1000,
  "max_embedded_candidates": 20,
  "max_password_attempts": 20,
  "extraction_timeout_seconds": 300,
  "ignore_android": false,
  "ignore_AZ": false
}
```

默认限制中，单个归档最大 10 GiB、递归深度 50、递归任务 1000、初始归档 1000、嵌入候选 20、密码尝试 20、单次外部工具超时 300 秒、解压文件数 100,000、总输出大小 100 GiB。可在配置中显式使用 `null` 关闭文件数或总大小限制，但不建议对来源不明的归档这样做。

完整字段见 [配置说明](docs/CONFIGURATION.md)。

## 从源码运行

要求：Windows 10/11、Python 3.10+、Windows Python Launcher。运行时没有第三方 Python 依赖。

```powershell
py main.py
```

也可运行 `start_game_archive_manager.bat`。执行测试：

```powershell
py -B -m unittest discover -s tests -v
```

构建依赖单独列在 `requirements-build.txt`。

## 安全边界

- 源归档不会被修改、移动或自动删除；最终交付使用新目录，不覆盖已有输出。
- ZIP 使用标准库在解压前检查绝对路径、驱动器路径和 `..` 路径穿越；7-Zip 可用时，未加密目录的 RAR/7Z 也会通过只读列表模式检查路径、声明大小和链接条目。目录本身加密时，获得正确密码前仍无法完成同等级预检查。
- 解压后的符号链接和 Windows reparse point 会阻断后续交付，避免后续哈希或复制读取任务目录外文件。
- 解压后大小检查发生在外部工具已经写入文件之后；它能标记失败，但不能预防磁盘空间已被消耗。
- 默认启用总输出大小和文件数限制；RAR/7Z 的准确统计仍主要发生在写盘后的安全检查。处理来源不明的归档时，仍建议在低权限账户、虚拟机或其他隔离环境中运行。
- `tools` 目录、`config.json` 和系统 `PATH` 中发现的可执行文件会被启动并读取版本。不要放入来源不明的 `7z.exe`、`Rar.exe` 或 `lz4.exe`。

更详细的实现边界见 [安全设计](docs/SECURITY.md) 与 [已知问题](docs/KNOWN_ISSUES.md)。安全问题请通过 GitHub 仓库的私密漏洞报告渠道提交；如果该渠道未启用，请先联系维护者，不要公开密码、令牌或私人路径。

## 文档

- [用户指南](docs/USER_GUIDE.md)
- [配置说明](docs/CONFIGURATION.md)
- [安全设计](docs/SECURITY.md)
- [架构](docs/ARCHITECTURE.md)
- [当前状态](docs/CURRENT_STATUS.md)
- [已知问题](docs/KNOWN_ISSUES.md)
- [0.1.0 RC2 发布说明](docs/RELEASE_NOTES_0.1.0_RC2.md)

## License

本项目采用 [MIT License](LICENSE)。7-Zip、WinRAR 和 LZ4 由各自许可证约束，本仓库不分发它们的二进制文件。

---

## English

GameArchiveManager is a local Windows CLI for identifying, recursively extracting, and organizing downloaded game archive packages. Despite the name, it is **not a game-save backup manager**: it does not inspect Steam `userdata`, discover installed games, or scan disks on its own.

### Highlights

- Detects ZIP, RAR, 7Z, and LZ4 by content rather than filename extension.
- Handles bounded recursive wrappers, split volumes, disguised extensions, and validated embedded archives.
- Delivers selected game or generic content to `GameArchive_Output` without overwriting earlier results.
- Keeps source archives unchanged and does not download third-party tools.
- Uses 7-Zip for ZIP/RAR/7Z, optional WinRAR fallback for RAR, and `lz4.exe` for LZ4.

### Quick start

1. Install trusted 64-bit [7-Zip](https://www.7-zip.org/).
2. Download `v0.1.0-rc2` or newer from the [Releases page](https://github.com/HypnosysNyx/GameArchiveManager/releases), then extract the entire folder. The older `v0.1.0-rc1` predates the audit fixes.
3. Run `GameArchiveManager.exe`, paste or drag in one archive or directory, review the preview, and confirm with `Y`.
4. Find delivered content under `GameArchive_Output` in the selected task directory.

### Privacy summary

- No HTTP, sockets, telemetry, analytics, crash reporting, cloud sync, or file upload exists in the current application code.
- A directory task recursively enumerates the directory explicitly supplied by the user. It does not proactively scan Documents, Desktop, browsers, Steam data, installed games, or an entire drive.
- Logs and history remain under `%LOCALAPPDATA%\GameArchiveManager`, but they contain full local paths that may include the Windows profile name. Treat them as private local data.
- Passwords are not written to logs, reports, or history. Manual input is visible in the console; 7-Zip receives it through redirected standard input, not its process command line. Successful passwords remain only in process memory until exit.
- ZIP is inspected with the Python standard library. When 7-Zip is available, RAR/7Z with readable headers are also listed before extraction to check paths, declared sizes, and link entries; encrypted headers cannot be fully inspected before a correct password is available. Default output quotas and post-extraction checks still apply.

See [Security](docs/SECURITY.md), [Configuration](docs/CONFIGURATION.md), and [User Guide](docs/USER_GUIDE.md) for details. Source runs with Python 3.10+ and has no third-party runtime package requirements:

```powershell
py main.py
py -B -m unittest discover -s tests -v
```

Licensed under the [MIT License](LICENSE).
