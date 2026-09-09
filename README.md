# GameArchiveManager

整理游戏资源压缩包的小工具，跑在 Windows 命令行里。

网上下载的资源包经常不太规矩：扩展名是假的，外面套着好几层，分卷缺了一块，或者 JPEG 里面藏着 RAR。这个程序会先看文件头，再按层解包，最后把看起来像游戏根目录的内容复制到一个新的输出目录里。

它不是存档管理器，也没有图形界面，更不会替你安装 7-Zip。当前正式版本是 `0.1.0 Release`，可以从 [GitHub Releases](https://github.com/HypnosysNyx/GameArchiveManager/releases/latest) 下载。

## 先准备好

- Windows 10/11
- 64 位 [7-Zip](https://www.7-zip.org/)，装在默认位置即可
- 如果要处理 `.lz4`，再准备 `lz4.exe`
- 如果需要 RAR 的备用解包器，可以安装 WinRAR

下载后请把整个 `GameArchiveManager-0.1.0.zip` 解压出来，不要只拿走 exe。程序没有签名，运行前可以按发布页提供的 SHA-256 校验值检查文件。

## 怎么用

1. 双击 `GameArchiveManager.exe`。刚装好 7-Zip 的话，重启一次程序，让它重新寻找工具。
2. 把资源所在的文件夹，或者一个压缩包，拖进黑色窗口；也可以直接粘贴路径后回车。
3. 看预览，确认后输入 `Y` 回车。输入 `N` 取消这一次。
4. 结果会放在任务目录下的 `GameArchive_Output`。如果那里已经有同名目录，会使用 `_2`、`_3`，不会覆盖旧结果。
5. 按回车可以继续处理下一个路径，输入 `Q` 退出。

程序会识别 ZIP、RAR、7Z 和 LZ4，也能处理嵌套压缩包、常见分卷和伪装扩展名。APK、Office、EPUB、JAR 这类文件在目录扫描时默认保留原样；如果把它们单独交给程序，才会按你的操作处理。

### 密码包

最省事的办法是在压缩包旁边建一个空文件夹，把密码写成文件夹名。程序会自动尝试这个名字；普通文件名不会被当成密码。

自动尝试失败后，可以选择手动输入密码。密码会显示在屏幕上，方便中文输入法使用；它不会写进日志、报告或历史记录。成功的密码只在当前运行窗口里暂存，退出程序就忘了。

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

程序不会修改或删除源压缩包，也不会按名字乱删用户目录。日志里可能有完整的本地路径，请把它当作私人信息保存。程序不联网、不上传遥测，也不会保存密码。

## 从源码运行

需要 Python 3.10 或更新版本，运行时没有第三方 Python 依赖：

```powershell
py main.py
```

也可以运行 `start_game_archive_manager.bat`。构建依赖见 [`requirements-build.txt`](requirements-build.txt)。

## 许可

源码使用 [MIT License](LICENSE)。7-Zip、WinRAR 和 LZ4 各自遵循自己的许可协议；本仓库不附带 `lz4.exe`。

更多细节可以看：[`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)、[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)、[`docs/SECURITY.md`](docs/SECURITY.md)。
