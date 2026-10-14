# GameArchiveManager

[English](#english) · [中文说明](#gamearchivemanager-中文)

## English

A small Windows tool for sorting out game-resource archives.

Downloaded resource packs are often messy: the extension may be wrong, several archive layers may be wrapped together, a split volume may be missing, or a RAR may be hiding inside a JPEG. GameArchiveManager checks file signatures, extracts archives layer by layer, and copies content that looks like a game root into a fresh output directory.

It is not a save-game manager. It has a desktop window and a command-line window. If 7-Zip or the LZ4 command-line tool is missing, the program asks before downloading it from the official site; it never connects in the background. The current update is `0.2.0` source code on [GitHub Releases](https://github.com/HypnosysNyx/GameArchiveManager/releases/tag/v0.2.0). This update does not include a new installer or a new executable. The older `0.1.0` portable zip is the previous packaged build and does not contain this update.

## Before you start

- Windows 10 or 11
- 64-bit [7-Zip](https://www.7-zip.org/), installed in its default location
- `lz4.exe` if you need to process `.lz4` files
- WinRAR as an optional fallback extractor for RAR archives

This `0.2.0` publication is source code. It does not add a portable zip or an executable. To run it, install Python 3.10 or newer, then use the commands in “Running from source”. The older packaged program remains `GameArchiveManager-0.1.0` and does not include the changes below.

## Usage

The window is `pyw gui\app.py`. Choose a folder or archive, then start. Appearance, language, window placement, and settings are in that window. If you have just installed 7-Zip or LZ4, restart the program so it can find the tool.

The command line is `py main.py`. The numbered steps below are that command line. They also describe the older `0.1.0` executable:

1. Start `py main.py`, or double-click `GameArchiveManager.exe` from the older `0.1.0` package. If you have just installed 7-Zip, restart the program so it can find the tool again.
2. Drag in the folder containing the resources or a single archive, or paste a path into the black window and press Enter.
3. Review the preview, then type `Y` and press Enter to confirm. Type `N` to cancel this run.
4. Results are written to `GameArchive_Output` under the task directory. If a directory with that name already exists, the program uses `_2`, `_3`, and so on instead of overwriting it.
5. Press Enter to process another path, or type `Q` to quit.

The program recognizes ZIP, RAR, 7Z, and LZ4 files. It can also handle nested archives, common split volumes, and misleading extensions. APK, Office, EPUB, and JAR files are kept as-is during directory scans; if you pass one to the program directly, it is handled according to your choices.

### Password-protected archives

The easiest option is to create an empty folder beside the archive and use the password as the folder name. The program will try that name; ordinary file names are never treated as passwords.

If that attempt fails, you can enter a password manually. The password is shown on screen to make Chinese input methods usable, but it is not written to logs, reports, or history. A successful password can be kept in a local library encrypted with Windows DPAPI for the current Windows user, at `%LOCALAPPDATA%\GameArchiveManager\passwords.json`. It stays on this computer and is not uploaded.

### Common input

| Input | Action |
| --- | --- |
| Path / drag and drop | Start a task |
| `Y` / `N` | Confirm / cancel |
| `M` | Open the menu: new task, previous result, tool status, settings |
| `I` / `S` / `C` | Enter a password / skip the current archive / cancel the whole task |
| `Q` | Quit |
| `Ctrl+C` | Interrupt the current task; source files are not modified |

## Tools and output locations

At startup, the program looks for tools in this order: paths in `config.json`, `tools` beside the program, the system's default installation locations, and PATH. Restart the program after installing or moving 7-Zip.

Final files: `<task directory>\GameArchive_Output`

Logs and history: `%LOCALAPPDATA%\GameArchiveManager\`

Optional configuration: `config.json` beside the program or `%LOCALAPPDATA%\GameArchiveManager\config.json`. See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for the full list of fields.

The program does not modify or delete source archives and does not delete user directories by name. Logs may contain complete local paths, so treat them as private information. The program does not upload telemetry. It connects to the network only after you agree to install a missing 7-Zip or LZ4 tool. Saved passwords stay in the local DPAPI library and are not written to logs, reports, or history.

## Running from source

Python 3.10 or newer is required. There are no third-party Python dependencies at runtime:

```powershell
pyw gui\app.py
py main.py
```

`pyw gui\app.py` opens the window without a black console. `py main.py` opens the command line. You can also run `start_game_archive_manager.bat` for the command line. Build dependencies are listed in [`requirements-build.txt`](requirements-build.txt).

### What changed in 0.2.0

- A desktop window, with no black console when started by `pyw`.
- Light, dark, and automatic appearance, applied immediately and remembered. Chinese and English are remembered too.
- The window opens centered the first time, then restores the last position, size, and maximized state. A window left off-screen comes back into view.
- Settings are grouped into appearance, scan scope, extraction tools, password library, and processing limits.
- New switch: ignore PC tags. It is off by default. Ignore Android and ignore AZ stay off by default. PC and AZ match a whole tag, not letters inside another word.
- A local password library that can be viewed, edited, and saved. It is used during extraction. Logs, reports, and history do not contain the password.
- If 7-Zip is missing, the program asks, then installs it from the official site.
- If `lz4.exe` is missing, the program asks, then installs the official Windows build.
- A failed task records the stage and the reason in the log, the report, and history.
- Scanning is faster. Signature, CRC, and SHA-256 checks remain.

## License

The source code is released under the [MIT License](LICENSE). 7-Zip, WinRAR, and LZ4 each have their own license terms; this repository does not include `lz4.exe`.

For more detail, see [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md), [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md), and [`docs/SECURITY.md`](docs/SECURITY.md).

---

# GameArchiveManager (中文)

[English](#english)

整理游戏资源压缩包的小工具，可以开窗口，也可以用命令行。

网上下载的资源包经常不太规矩：扩展名是假的，外面套着好几层，分卷缺了一块，或者 JPEG 里面藏着 RAR。这个程序会先看文件头，再按层解包，最后把看起来像游戏根目录的内容复制到一个新的输出目录里。

它不是存档管理器。可以开桌面窗口，也可以用命令行。缺少 7-Zip 或 LZ4 命令行工具时会先问你，同意后才从官方地址下载，不会在后台偷偷联网。这次更新是 `0.2.0` 源码，在 [GitHub Releases](https://github.com/HypnosysNyx/GameArchiveManager/releases/tag/v0.2.0)。这次不附带新的安装包，也不附带新的 exe。以前的 `0.1.0` 便携压缩包是上一版打包结果，里面没有这次的改动。

## 先准备好

- Windows 10/11
- 64 位 [7-Zip](https://www.7-zip.org/)，装在默认位置即可
- 如果要处理 `.lz4`，再准备 `lz4.exe`
- 如果需要 RAR 的备用解包器，可以安装 WinRAR

这次 `0.2.0` 发布的是源码，没有新的便携压缩包，也没有新的 exe。要运行这次更新，请安装 Python 3.10 或更新版本，再用下面「从源码运行」里的命令。旧的 `GameArchiveManager-0.1.0` 打包程序不包含下面这些改动。

## 怎么用

窗口用 `pyw gui\app.py` 打开。选好文件夹或压缩包后开始。外观、语言、窗口位置和设置都在这个窗口里。刚装好 7-Zip 或 LZ4 的话，重启一次程序，让它重新寻找工具。

命令行用 `py main.py`。下面的编号步骤说的是命令行，也适用于旧的 `0.1.0` 打包程序：

1. 运行 `py main.py`，或双击旧版 `0.1.0` 里的 `GameArchiveManager.exe`。刚装好 7-Zip 的话，重启一次程序，让它重新寻找工具。
2. 把资源所在的文件夹，或者一个压缩包，拖进黑色窗口；也可以直接粘贴路径后回车。
3. 看预览，确认后输入 `Y` 回车。输入 `N` 取消这一次。
4. 结果会放在任务目录下的 `GameArchive_Output`。如果那里已经有同名目录，会使用 `_2`、`_3`，不会覆盖旧结果。
5. 按回车可以继续处理下一个路径，输入 `Q` 退出。

程序会识别 ZIP、RAR、7Z 和 LZ4，也能处理嵌套压缩包、常见分卷和伪装扩展名。APK、Office、EPUB、JAR 这类文件在目录扫描时默认保留原样；如果把它们单独交给程序，才会按你的操作处理。

### 密码包

最省事的办法是在压缩包旁边建一个空文件夹，把密码写成文件夹名。程序会自动尝试这个名字；普通文件名不会被当成密码。

自动尝试失败后，可以选择手动输入密码。密码会显示在屏幕上，方便中文输入法使用；它不会写进日志、报告或历史记录。成功的密码可以留在本机密码库里。密码库用当前 Windows 用户的 DPAPI 加密，放在 `%LOCALAPPDATA%\GameArchiveManager\passwords.json`，只留在这台电脑上，不上传。

### 常用输入

| 输入 | 作用 |
| --- | --- |
| 路径 / 拖放 | 开始一个任务 |
| `Y` / `N` | 确认 / 取消 |
| `M` | 打开菜单：新任务、上次结果、工具状态、设置 |
| `I` / `S` / `C` | 手动输入密码 / 跳过当前包 / 取消整个任务 |
| `Q` | 退出 |
| `Ctrl+C` | 中断当前任务；源文件不会被修改 |

## 工具和输出位置

程序启动时按这个顺序寻找工具：`config.json` 中的路径、程序目录下的 `tools`、系统默认安装位置、PATH。安装或移动 7-Zip 后，请重启程序。

最终文件：`<任务目录>\GameArchive_Output`

日志和历史：`%LOCALAPPDATA%\GameArchiveManager\`

可选配置：程序目录下的 `config.json`，或者 `%LOCALAPPDATA%\GameArchiveManager\config.json`。完整字段见 [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)。

程序不会修改或删除源压缩包，也不会按名字乱删用户目录。日志里可能有完整的本地路径，请把它当作私人信息保存。程序不上传遥测。只有在你同意安装缺少的 7-Zip 或 LZ4 时才会联网。保存的密码留在本机 DPAPI 密码库里，不会写进日志、报告或历史。

## 从源码运行

需要 Python 3.10 或更新版本，运行时没有第三方 Python 依赖：

```powershell
pyw gui\app.py
py main.py
```

`pyw gui\app.py` 打开窗口，不带黑色控制台。`py main.py` 打开命令行。命令行也可以运行 `start_game_archive_manager.bat`。构建依赖见 [`requirements-build.txt`](requirements-build.txt)。

### 0.2.0 改了什么

- 有桌面窗口。用 `pyw` 打开时没有黑色控制台。
- 浅色、深色、自动三种外观，一点就变，并且会记住。中文和 English 也会记住。
- 第一次打开在屏幕中间。之后记住位置、大小和是否最大化。窗口跑出屏幕时会挪回来。
- 设置分成外观、扫描范围、解压工具、密码库、处理限制。
- 新增「忽略 PC 标签」，默认不勾。忽略 Android、忽略 AZ 仍默认不勾。PC 和 AZ 只认完整标签，不认别的单词里的字母。
- 本机密码库可以查看、修改和保存，解压时会用。日志、报告和历史里不写密码。
- 缺少 7-Zip 时先问，同意后从官网安装。
- 缺少 `lz4.exe` 时先问，同意后安装官方 Windows 版本。
- 任务失败时，日志、报告和历史会写明阶段和原因。
- 扫描更快。文件头、CRC 和 SHA-256 校验还在。

## 许可

源码使用 [MIT License](LICENSE)。7-Zip、WinRAR 和 LZ4 各自遵循自己的许可协议；本仓库不附带 `lz4.exe`。

更多细节可以看：[`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)、[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)、[`docs/SECURITY.md`](docs/SECURITY.md)。
