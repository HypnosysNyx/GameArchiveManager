# GameArchiveManager 用户指南

## 安装要求

- Windows 10 或 Windows 11
- Python 3.10 或更高版本
- Windows Python 启动器 `py`
- 真实解压需要至少一个与归档计划匹配的外部工具：7-Zip、WinRAR 或 LZ4

项目当前没有第三方 Python 依赖，`requirements.txt` 为空，不需要执行 pip 安装。

## 7-Zip 要求

ToolManager 默认查找：

```text
C:\Program Files\7-Zip\7z.exe
```

如果所需工具不存在，解压会返回`TOOL_NOT_FOUND`，程序不会崩溃。Settings与`config.json`都支持`seven_zip_path`、`winrar_path`和`lz4_path`；显式路径优先于项目tools目录、常见安装路径和Windows PATH。

当前 SevenZipExtractor 支持：

- ZIP
- RAR
- 7Z

WinRAR Adapter、LZ4 Adapter和LZ4→RAR composite已实现。RAR默认首选7-Zip，仅在允许fallback的工具失败下切换WinRAR；密码错误和损坏文件不会无限切换工具。

## 基本使用流程

### 1. 启动 CLI 会话

在项目根目录执行：

```powershell
py main.py
```

启动后首先显示Fast Path：

```text
GameArchiveManager 0.1.0 RC

输入文件或目录路径直接开始任务
M = 菜单
Q = 退出

>
```

直接粘贴目录、归档文件，或把路径拖入终端即可进入现有预览和确认流程，不需要先选择“新建任务”。带空格的拖放路径如`"C:\Downloads\Test Game"`会只移除整条路径的一对外层引号。输入`M`可打开完整菜单，其中仍保留批量任务、最近结果、工具状态和设置；输入`Q`退出。

选择`1`，输入一个真实任务目录或显式归档文件路径，例如：

```text
D:\Games\DownloadedGame
```

Fast Path适合单任务高频使用。需要批量输入时，使用`M → 1. 新建任务`；添加一个或多个路径后，输入空行进入预览。不存在的路径不会创建任务或history，而是立即返回路径输入。程序会显示：

- 任务路径
- 文件和文件夹数量
- 压缩包真实格式及伪装状态
- 空文件夹产生的密码候选
- Android、AZ、安卓忽略项目

确认`Y`后，CLI通过同一个`GameArchiveService`执行任务并显示报告。完成、失败或取消当前任务后，按Enter返回Fast Path，可以立即粘贴下一个路径；SessionPasswordStore和工具状态在同一程序会话中复用。输入`Q`才退出应用。

### 2. 可选 config.json

如需设置执行限制或外部工具路径，可在程序目录创建 `config.json`；也可以使用 `%LOCALAPPDATA%\GameArchiveManager\config.json`。程序目录配置优先。示例和字段见 [CONFIGURATION.md](CONFIGURATION.md)。配置文件不是必需的，程序也不会自动生成它。

### 3. 完整服务流程

当前完整自动流程已经在 `GameArchiveService` 中实现，供未来命令行、GUI 或 API 调用：

```text
创建任务
→ 扫描和分析
→ 跳过平台内容
→ 递归解压
→ 有限密码恢复
→ 安全检查
→ 生成报告
→ 保存历史和日志
```

该流程已连接到`main.py`的交互入口。CLI只负责用户交互，不直接调用Scanner、Extractor或PasswordRecovery。

### 4. 运行项目测试

```powershell
py -B -m unittest discover -s tests -v
```

测试使用临时目录并自动清理。真实普通 ZIP 测试会使用本机 7-Zip；未找到工具时该项会跳过。

## 输出和数据位置

- 解压器的物理中间目录通常使用 `<压缩包名称>_extracted`，密码重试可能使用 `_password_attempt_<次数>`；这些是技术目录，不是最终用户交付路径。
- 最终内容统一复制并校验到任务根目录的 `GameArchive_Output`。已有同名结果不会被覆盖，程序会安全使用 `_2`、`_3` 等唯一名称。
- 默认历史文件：`%LOCALAPPDATA%\GameArchiveManager\history\task_history.json`。
- 默认任务日志目录：`%LOCALAPPDATA%\GameArchiveManager\logs\`。
- 原始压缩包不会自动删除。

## 常见问题

### 为什么预览后没有解压？

预览后必须输入`Y`确认才会执行。输入`N`只取消当前任务并返回Fast Path，不会退出应用。

### 提示“未找到 7-Zip”怎么办？

确认 `C:\Program Files\7-Zip\7z.exe` 存在，或在 `config.json` 中设置 `seven_zip_path`。ToolManager 还会依次检查项目 `tools` 目录及其一级子目录、常见安装位置和 Windows PATH；找到后必须通过版本命令验证。

### 为什么重复运行后出现 `_2`、`_3`？

这是防覆盖保护。统一输出路径生成器不会复用、覆盖或删除已有目录，而是选择新的安全唯一名称。最终报告和历史会记录本次实际交付路径。

### 为什么 Android 或 AZ 文件被跳过？

默认 `ignore_android` 和 `ignore_AZ` 都是 `false`：PC、Android/安卓和AZ内容均保留。如需过滤，在 `config.json` 中将对应字段明确设为 `true`。过滤只检查任务内容根以下的相对组件；AZ使用明确标签token，不会因为用户名、临时父目录或`crazy/amazing`等普通名称包含字符`az`而跳过。

主菜单`4`可查看当前会话已加载的非敏感设置。如修改`config.json`，需重启程序后生效。自动目录扫描或递归扫描会完整保留 `.apk/.docx/.xlsx/.pptx/.epub/.jar`，不会仅因底层是 ZIP 就拆解。如果用户显式把这些文件本身作为文件任务输入，则明确意图优先，仍可按真实 ZIP 格式解包。

### 密码从哪里来？

当前自动分析会把真实空文件夹的名称作为候选，再由 PasswordScorer 排序。程序不会把普通文件名当作密码候选。

自动候选全部失败时，交互式CLI会显示：

- `I`：使用不回显的安全输入补充新密码；
- `S`：跳过当前需要密码的归档；
- `C`：取消当前任务。

人工密码只用于当前进程。只有实际解压成功后才会加入内存会话候选；程序退出后消失，不写入日志、报告或历史JSON。当前`save_passwords`和`auto_try_password`只是预留字段，项目没有持久密码库。

### 为什么 RAR 或 7Z 没有完整的解压前安全统计？

当前 ArchiveContentInspector 只使用 Python 标准库可靠读取 ZIP。RAR 和 7Z 会记录能力警告，仍依赖递归限制、工具超时和解压后检查。

### 安全检查失败后文件为什么还在？

系统默认不自动删除用户数据。解压后超限发生时，文件已经写入磁盘；程序会标记失败并保留现场，等待用户检查和确认清理。

### 当前有 GUI 或游戏自动整理吗？

没有 GUI。`organizer` 已实现最终内容根判断、技术归档链折叠、重复内容检查以及安全复制到 `GameArchive_Output`；它不会重排游戏内部文件，也不会修改源归档。
