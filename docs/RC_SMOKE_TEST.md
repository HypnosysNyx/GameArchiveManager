# GameArchiveManager 0.1.0 RC2 干净 Windows VM 冒烟测试

> 历史 RC 记录；当前正式版为 `v0.1.0`。

## 测试目的

验证 RC 构建在没有项目源码和 Python 开发环境的 Windows 机器上能够启动、发现外部工具、安全执行真实任务，并保持源文件和历史输出不变。

本清单只验证现有功能，不扩展格式或业务规则。任何失败必须先记录，不得为了让结果变绿而修改测试数据或删除证据。

## 测试环境

### 环境 A（必须）

- Windows 11 x64 干净 VM
- 初始没有 Python
- 初始没有 7-Zip、WinRAR、LZ4
- 普通标准用户账户
- RC 目录放在桌面或下载目录

### 环境 B（条件允许时）

- Windows 10 x64，仍在目标支持范围内的最新补丁状态
- 其余条件与环境 A 相同

每个环境建议先创建干净快照。外部工具每增加一种后创建新快照，便于复现。

## 构建物完整性

复制整个目录，不能只复制 EXE：

```text
GameArchiveManager-0.1.0-RC2\
```

在开发机交付记录中核对 RC2 ZIP 与 EXE SHA256：

```powershell
Get-FileHash .\GameArchiveManager-0.1.0-RC2.zip -Algorithm SHA256
Get-FileHash .\GameArchiveManager-0.1.0-RC2\GameArchiveManager.exe -Algorithm SHA256
```

当前交付 RC2 实测值（开发机 staging 与 Win11-Sandbox 一致）：

```text
ZIP  BA3A9ADD4132EFF6188E3981C627400647941C572059F3D733347A3EE6823051
EXE  67DF840B832EE9072375A3A267DF220DBB546FD61EF8B048EA8C8C6B17D20F71
```

`9BFDE4CE679EDF819AB4CB19E7E29FC6B4D5206134BA63D5739C6F87E27D0AD0`
与 `F5F2DD823664AA2ABFE52A7C91597EA4FA3735E9C3EC8FF0E7A8813D9B92D83C`
属于 2026-08-24 的旧门禁包，不是当前交付 RC2 的身份哈希。

## 测试记录模板

```text
测试编号：
Windows 版本/Build：
VM 快照：
测试账户是否管理员：
Python 是否安装：
7-Zip 路径/版本：
WinRAR 路径/版本：
LZ4 路径/版本：
开始时间：
结束时间：
输入任务目录：
输入压缩包 SHA256：
实际步骤：
实际输出：
TaskStatus：
成功/失败/跳过：
密码尝试次数：
ORPHANED_TEMP：
最终输出路径：
运行后 SHA256：
日志位置：
history 位置：
截图位置：
PASS/FAIL/BLOCKED：
问题编号和说明：
```

## 1. 无 Python 启动

1. 打开“已安装的应用”确认没有 Python。
2. 不打开项目源码目录。
3. 双击 `GameArchiveManager.exe`。

预期：

- 程序打开控制台，不提示安装 Python。
- 不出现 `python.dll missing`、模块缺失或 Traceback。
- 不要求管理员权限。

## 2. RC 版本信息

确认启动顶部显示：

```text
GameArchiveManager
版本: 0.1.0
构建类型: Release Candidate
```

NO-GO：显示 Development、正式 Release、其他版本号或空版本。

## 3. 开发机路径独立性

在 VM 中搜索程序目录和 `%LOCALAPPDATA%\GameArchiveManager`：

```powershell
Get-ChildItem .\GameArchiveManager-0.1.0-RC2 -Recurse -File |
    Select-String -SimpleMatch $env:USERPROFILE -ErrorAction SilentlyContinue
```

预期无运行依赖命中。程序不应尝试访问构建机用户目录、`GameArchiveManager0.1.0` 或项目源码目录。

## 4. 无外部工具

初始 VM 不安装任何解压工具，也不创建 `config.json` 或 `tools` 目录。

启动程序，确认：

- 7-Zip：未找到
- WinRAR：未找到
- LZ4：未找到
- 程序仍能进入任务输入，不崩溃

选择一个 ZIP 任务并确认执行。预期报告明确显示工具缺失，任务失败，源 ZIP 不变。

## 5. 7-Zip 重新检测

1. 关闭程序。
2. 从合法来源安装 7-Zip。
3. 重新启动 RC。

预期：

- 显示实际 `7z.exe` 路径。
- 显示版本。
- 状态为“可用”。

也可通过 EXE 同级配置验证显式路径优先级：

```json
{
  "seven_zip_path": "C:\\Program Files\\7-Zip\\7z.exe"
}
```

测试后保存或移走配置，记录所用方案。

## 6. WinRAR CLI 检测

合法安装 WinRAR 后重新启动。

预期发现：

```text
C:\Program Files\WinRAR\Rar.exe
```

必须显示版本和“可用”。只发现 GUI 而不能执行 CLI 版本查询视为 FAIL。

## 7. LZ4 检测

RC 不捆绑 LZ4。使用来源与许可证均已确认的 `lz4.exe`，任选一种：

```text
GameArchiveManager-0.1.0-RC2\tools\lz4.exe
GameArchiveManager-0.1.0-RC2\tools\lz4_win64_v1_10_0\lz4.exe
```

或在 `config.json` 中写绝对路径：

```json
{
  "lz4_path": "C:\\Tools\\LZ4\\lz4.exe"
}
```

重新启动，确认实际路径、版本和“可用”。

## 8. 普通格式测试

分别准备由可信工具创建的小型测试包：

- `normal.zip`
- `normal.rar`
- `normal.7z`
- `normal.lz4`

每个包只包含一个可核对 SHA256 的文本或二进制文件。每种格式单独建立任务目录并执行。

预期：

- TaskStatus 为 COMPLETED。
- `failed_count=0`。
- 输出位于任务目录下 `GameArchive_Output`。
- 源压缩包 SHA256 不变。

## 9. 分卷测试

至少测试：

- 完整 `sample.7z.001/.002`
- 完整 `sample.part01.rar/.part02.rar`
- 缺少第二卷的独立任务

预期：

- 完整分卷只生成一个初始任务，以第一卷为入口并恢复文件。
- 缺卷不进入 Extractor。
- 缺卷报告包含 `VOLUME_DETECTION`、`MISSING_VOLUME` 和缺少文件列表。

## 10. 密码包测试

准备：

- 一个正确密码候选。
- 一个错误候选后跟正确候选。
- 全部候选错误。

不要把真实敏感密码写入截图、测试记录、文件名或问题报告。可使用一次性 RC 测试密码并单独保管。

预期：

- 正确密码恢复成功。
- 错误候选后继续尝试正确候选。
- 全错误最终是 WRONG_PASSWORD，不误报成功。
- 日志/history/report 只有尝试次数和状态，没有明文密码。

## 11. JPEG + embedded RAR

准备两个真实结构样本：

1. JPEG 宿主 + 普通 RAR。
2. JPEG 宿主 + 加密 RAR5。

预期：

- 识别 embedded RAR。
- 加密 RAR5 进入密码恢复。
- 最终文件恢复。
- 普通 JPEG、DLL、EXE 和 Unity `.assets` 不进入递归任务。

## 12. 中文路径

任务路径示例：

```text
C:\Users\<redacted>\Desktop\测试游戏3\游戏文件
```

压缩包、内部文件和输出目录都应包含中文。执行普通 ZIP 和至少一个递归任务。

预期：

- 输入不乱码。
- TaskStatus 正常结束。
- history JSON 使用 UTF-8，可正确读回中文路径。
- 控制台、日志和最终路径可辨认。

## 13. 重复运行

同一个任务连续执行 3 次，每次记录预览归档数量。

预期：

- 三次都能结束。
- 初始 archive task 数量不增长。
- 不扫描 `GameArchive_Output` 和旧内部目录。
- 最终输出名称安全递增，不覆盖旧目录。
- 源压缩包 SHA256 始终不变。

## 14. 中断后重新运行

分别在控制台显示以下阶段时按 Ctrl+C：

- EXTRACTING
- SCANNING
- VALIDATING

每次测试使用独立 VM 快照或独立任务目录。

预期：

- 源文件不变。
- 已创建但未确认可删的目录保留为 ORPHANED_TEMP。
- 如果中断时尚未创建目录，不应伪造残留记录。
- 下一次运行不扫描旧残留并可以结束。
- 只能通过显式安全清理处理残留。

强制关闭 VM 或结束进程不保证程序有机会写入状态，不等价于 Ctrl+C 测试。

## 15. 最终输出目录

检查：

```text
<任务目录>\GameArchive_Output
```

预期只包含用户最终结果，不包含：

- `password_attempt_x`
- 中间复合容器目录
- 临时扫描目录
- 源压缩包副本

重复执行不得覆盖旧输出。

## 16. history、日志和报告

运行数据位置：

```text
%LOCALAPPDATA%\GameArchiveManager\logs
%LOCALAPPDATA%\GameArchiveManager\history\task_history.json
```

检查：

- 程序目录没有新建 logs/history。
- 日志包含应用 `0.1.0 / Release Candidate`。
- history 每条新记录包含相同版本和构建类型。
- CLI TaskReport 显示相同版本。
- 中文路径 UTF-8 正常。
- 搜索一次性测试密码，无任何明文命中。

密码检查示例：

```powershell
Get-ChildItem "$env:LOCALAPPDATA\GameArchiveManager" -Recurse -File |
    Select-String -SimpleMatch '<一次性测试密码>'
```

预期无结果。

## 17. 安全核对

每个真实任务前后执行：

```powershell
Get-FileHash '<源压缩包路径>' -Algorithm SHA256
```

确认：

- 源文件哈希不变。
- 原始任务目录存在。
- 旧 `GameArchive_Output` 内容存在。
- 历史未知目录存在。
- 没有超出任务目录的清理操作。
- 没有非预期内部目录。

## Go / No-Go

### GO

- 应用正常启动且不要求 Python。
- 不依赖开发机绝对路径。
- 核心真实样本成功。
- 源文件不变。
- 密码未写入日志、报告和 history。
- 历史输出没有重复扫描。
- 没有非预期临时目录。
- 任务能够正常结束。
- 工具缺失提示明确。
- 中文路径正常。

### NO-GO

- 启动失败或缺少打包模块。
- 依赖开发机路径或源码目录。
- 静默覆盖、移动或删除用户文件。
- 密码明文进入持久化记录。
- Pipeline 无法结束。
- 真实任务误报成功。
- CleanupManager 清理越界。
- 打包版核心行为与源码版明显不同。

## 测试完成后的状态

2026-08-28 当前交付 RC2 的必选 Windows 11 VM 清单已完成：

- ZIP SHA256：`BA3A9ADD4132EFF6188E3981C627400647941C572059F3D733347A3EE6823051`
- EXE SHA256：`67DF840B832EE9072375A3A267DF220DBB546FD61EF8B048EA8C8C6B17D20F71`
- 清单 1–13、15–17：PASS，完整记录见 [`../rc2_smoke_codex.md`](../rc2_smoke_codex.md)。
- 清单 14：EXTRACTING、SCANNING、VALIDATING 三阶段真实 Ctrl+C 与中断后重跑均 PASS，见 [`../rc2_item14_codex.md`](../rc2_item14_codex.md)。
- VM 关机与残留宿主 GUI 清理时间线见 [`../rc2_vm_status.md`](../rc2_vm_status.md)。
- 被测 ZIP 内附带文档写有旧 EXE 哈希，但实际 ZIP/EXE 身份已在宿主、来宾和三份字节一致的 ZIP 副本间核对；原始被测 ZIP 未被修改。

结论：Clean Windows 11 RC gate **GO**。Windows 10 为可选未测。不要自行把 RC 改称正式 Release；仍须完成发布清单并等待仓库所有者批准任何 push、tag 或发布动作。
