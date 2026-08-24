# GameArchiveManager 0.1.0 RC1 构建说明

## 构建身份

- 应用名称：GameArchiveManager
- 应用版本：0.1.0
- 构建类型：Release Candidate
- 构建标签：RC1
- 当前重建日期：2026-08-24（Asia/Shanghai）
- 状态：供干净 Windows VM 冒烟测试使用，不是正式 Release

`version.py` 是应用名称、版本号和构建类型的唯一权威来源。CLI、TaskReport、BatchTaskReport、history JSON 和任务日志均从该模块取得版本信息。

## 打包方式

本 RC 使用 **PyInstaller 6.21.0 onedir** 模式，在 Windows 11、Python 3.13.2 x64 上构建。

选择 onedir 的原因：

- 打包 Python 解释器与标准库，目标 VM 不需要安装 Python。
- 相比 onefile，没有每次启动时释放整套运行时到临时目录的过程。
- 便于检查 DLL、运行依赖和开发机路径泄漏。
- 便于在 EXE 同级放置可选 `config.json` 或用户自行提供的 `tools` 目录。

PyInstaller 官方说明 onedir 会生成一个包含 EXE 和运行依赖的目录，打包应用不要求目标机器另装 Python：

- <https://pyinstaller.org/en/stable/index.html>
- <https://pyinstaller.org/en/stable/usage.html>

## 构建产物

目录：

```text
dist/
└── GameArchiveManager-0.1.0-RC1/
    ├── GameArchiveManager.exe
    ├── RC_BUILD_NOTES.md
    ├── RC_SMOKE_TEST.md
    └── _internal/
```

主程序：

```text
dist\GameArchiveManager-0.1.0-RC1\GameArchiveManager.exe
```

构建时 EXE SHA256：

```text
9BFDE4CE679EDF819AB4CB19E7E29FC6B4D5206134BA63D5739C6F87E27D0AD0
```

此前 2026-08-22 构建（缺卷修复前）EXE SHA256：

```text
F825C3859C85B1FDA9BE5809E1DB6BA447FC3478316870EEB2813F46AF472490
```

如果重新构建，哈希可能变化，交付前必须重新计算并更新测试记录。

## 构建依赖

运行依赖仍保持为空；`requirements.txt` 没有增加第三方运行库。

构建专用依赖位于：

```text
requirements-build.txt
```

当前固定：

```text
pyinstaller==6.21.0
```

## 可重复构建命令

在项目根目录执行：

```powershell
py -m venv .build_venv
& .\.build_venv\Scripts\python.exe -m pip install -r requirements-build.txt
& .\.build_venv\Scripts\python.exe -m PyInstaller --noconfirm --clean GameArchiveManager.spec
Copy-Item docs\RC_BUILD_NOTES.md dist\GameArchiveManager-0.1.0-RC1\
Copy-Item docs\RC_SMOKE_TEST.md dist\GameArchiveManager-0.1.0-RC1\
```

构建配置文件：`GameArchiveManager.spec`。

PyInstaller 必须在 Windows 上构建 Windows 产物；它不是跨平台交叉编译器。

## 管理员权限与 Python 要求

- 构建机：创建虚拟环境和打包不要求管理员权限。
- 测试 VM：启动 GameArchiveManager 不要求管理员权限。
- 测试 VM：不要求安装 Python。
- 安装 7-Zip 或 WinRAR 是否弹出管理员确认由各工具安装程序决定。
- 推荐将 RC 目录放在普通用户可读取的位置，例如桌面或下载目录，不要放在系统保护目录内修改文件。

## 运行数据位置

打包版不会把日志和 history 写入程序目录：

```text
%LOCALAPPDATA%\GameArchiveManager\logs\
%LOCALAPPDATA%\GameArchiveManager\history\task_history.json
```

最终游戏输出仍位于每个任务根目录：

```text
<任务根目录>\GameArchive_Output\
```

配置读取顺序：

1. EXE 同级 `config.json`（如果存在）。
2. `%LOCALAPPDATA%\GameArchiveManager\config.json`（如果存在）。
3. 两者都不存在时使用 Settings 安全默认值。

程序不会自动创建或覆盖 `config.json`。

## 外部工具策略

本 RC **没有捆绑**：

- `7z.exe`
- `Rar.exe` / `WinRAR.exe`
- `lz4.exe`

ToolManager 在打包版中继续按以下优先级发现工具：

1. `config.json` 的显式路径。
2. EXE 同级 `tools\<tool>.exe`。
3. EXE 同级 `tools\*\<tool>.exe`，仅扫描一级子目录。
4. Windows 常见安装位置。
5. Windows PATH。

工具状态必须通过文件存在和版本命令验证。

### LZ4 许可说明

本构建没有携带项目开发目录中的 LZ4 二进制。LZ4 官方项目说明 library 使用 BSD-2-Clause，而 CLI/test programs 的许可已经明确为 GPL-2.0-or-later。若以后随发行包提供 `lz4.exe`，必须确认该二进制的准确来源、对应版本和许可义务，并随构建提供所需许可证及源代码获取方式。本 RC 在完成该合规审核前不捆绑 LZ4 CLI。

参考：<https://github.com/lz4/lz4/releases>

## 动态导入和资源审计

- 项目没有业务层动态导入、插件加载或运行时 Python 源码搜索。
- PyInstaller 分析不需要额外 hidden import。
- `config.json` 是可选外部配置，不打入 `_internal`。
- 外部解压工具是独立进程，不打入 `_internal`。
- 日志、history 和任务输出都不是静态资源，不打入构建目录。
- PyInstaller warning 文件仅包含 Windows 上预期缺失的 POSIX/Java 条件模块，没有发现项目业务模块缺失。

## 当前重建前后的开发机验证

重建前按项目治理入口执行源码与真实工具完整回归：

```text
Ran 228 tests
OK
```

`py scripts/verify_project_state.py`：`Overall: PASS`。

当前 staging onedir 基础检查：

1. 无任务输入启动并输入 `Q`：退出码 0，显示 `0.1.0 / Release Candidate`。
2. 构建产物不包含 `7z.exe`、`Rar.exe`、`WinRAR.exe` 或 `lz4.exe`。
3. EXE 和 `_internal` 运行文件未发现当前开发机用户目录、`GameArchiveManager0.1.0` 或源码目录依赖字符串。
4. PyInstaller warning 仅包含 Windows 下预期的 POSIX/Java/VMS 条件模块，没有发现项目业务模块缺失。
5. 当前 onedir 共 19 个文件，约 16.6 MB。

以上是开发机构建检查，不替代干净 Windows 11 VM 门禁。

## 开发机路径泄漏扫描

在复制测试文档前，对 EXE 和 `_internal` 运行时二进制目录执行 ASCII 扫描：

```text
<developer user profile>   NO_MATCH
GameArchiveManager0.1.0    NO_MATCH
GameArchiveManager\        NO_MATCH
```

复制文档后，`RC_BUILD_NOTES.md` 和 `RC_SMOKE_TEST.md` 会按检查要求有意包含上述搜索字符串；这些命中必须限定在 Markdown 文档。测试代码和文档中允许出现示例路径，但 EXE、`_internal`、运行时配置和程序逻辑不得包含这些开发机绝对路径。

## 已知限制

- 当前是控制台 RC，没有 GUI。
- 外部工具需用户合法安装或配置。
- LZ4 未随 RC 捆绑。
- 打包版仅在当前 Windows 11 开发机完成首次冒烟，仍需干净 VM 结果。
- Windows 10 尚未实际验证。
- 没有代码签名，Windows SmartScreen 可能显示未知发布者提示。
- 没有安装程序；必须整体复制 onedir，不能只复制 EXE。
- 本构建不是正式 Release，不得对外宣称稳定正式版。

## VM 测试结论状态

当前状态：**等待干净 Windows VM 测试，不自行宣称发布完成。**
