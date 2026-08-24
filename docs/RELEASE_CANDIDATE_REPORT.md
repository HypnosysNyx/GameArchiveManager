# GameArchiveManager 0.1.0 Release Candidate 验证报告

## 结论

**结论：有条件建议进入 0.1.0 RC（内部候选发布），暂不建议直接作为公开稳定版发布。**

核心解压、递归、复合容器、分卷、密码恢复、平台忽略、输出隔离和中断恢复均已通过自动或真实 Windows 文件系统验证。验证期间发现一个真实 Windows 清理缺陷：成功输出中包含只读文件时，`CleanupManager` 无法删除本次运行内部目录。该问题已作最小修复，并通过单元回归和 5GB 级真实样本复测。

公开 RC 前仍需确认构建元数据（当前 `BUILD_TYPE=Development`），并建议在干净 Windows 虚拟机再执行一次安装包级冒烟测试。

## 验证环境

| 项目 | 实际值 |
|---|---|
| App version | 0.1.0 |
| Build type | Development |
| 验证日期 | 2026-08-10（Asia/Shanghai） |
| Python | 3.13.2，64 位 |
| Windows | Windows 11，10.0.26200，64 位 |
| PowerShell 识别信息 | Windows 10 Pro / 2009（兼容性元数据，与 `platform` 报告不同） |
| 7-Zip | 24.09，verified |
| WinRAR CLI | RAR 7.12 x64，verified |
| LZ4 | 1.10.0 64-bit multithread，verified |

实际工具路径：

- 7-Zip：`C:\Program Files\7-Zip\7z.exe`
- WinRAR：`C:\Program Files\WinRAR\Rar.exe`
- LZ4：项目 `tools/lz4_win64_v1_10_0/lz4.exe`

## 自动测试结果

执行命令：

```text
py -B -m unittest discover -s tests -v
```

最终结果：

```text
Ran 103 tests in 1.414s

OK
```

本次没有删除或弱化失败断言。真实样本发现问题后，先记录根因，再修改 `CleanupManager` 并新增 Windows 只读文件回归测试。

## RC 回归清单

说明：`真实` 表示使用真实文件、真实文件系统和实际外部工具；`自动` 表示 unittest 覆盖；`可控` 表示使用临时目录或受控错误注入，不占满系统盘。

| # | 场景 | 结果 | 验证方式与证据 |
|---:|---|---|---|
| 1 | 普通 ZIP | PASS | 真实 7-Zip 解压测试 |
| 2 | 普通 RAR | PASS | WinRAR 创建真实 RAR，真实 Coordinator 解压 |
| 3 | 普通 7Z | PASS | 7-Zip 创建并真实解压 |
| 4 | LZ4 | PASS | LZ4 1.10.0 创建并真实解压 |
| 5 | RAR.LZ4 | PASS | 真实“测试游戏”执行 LZ4 → RAR，密码恢复后完成 |
| 6 | ZIP/RAR/7Z 递归嵌套 | PASS | 三种真实工具创建 ZIP → RAR → 7Z，Pipeline depth 为 0/1/2 |
| 7 | `7z.001` 多分卷 | PASS | ApplicationService 真实入口，仅产生一个任务并恢复文件 |
| 8 | `part01.rar` 多分卷 | PASS | RAR 创建 3 卷并使用 part01/02/03 命名；分析为一个任务、3 个 volume，恢复哈希一致 |
| 9 | 缺少分卷 | PASS | ApplicationService 端到端测试返回 `VOLUME_DETECTION/MISSING_VOLUME` |
| 10 | 密码正确 | PASS | 真实 Beta 样本及真实加密 RAR |
| 11 | 密码错误 | PASS | 真实加密 RAR，全部错误候选最终返回 `WRONG_PASSWORD` |
| 12 | 多个密码候选 | PASS | 真实加密 RAR，错误候选后正确候选恢复成功；真实样本密码尝试计数稳定 |
| 13 | JPEG + RAR | PASS | WinRAR 创建真实 RAR，与 JPEG 前缀拼接后识别、提取并恢复 |
| 14 | JPEG + 加密 RAR5 | PASS | 真实加密 RAR5，验证为 `VALID_ENCRYPTED` 并完成密码恢复 |
| 15 | 假扩展名 ZIP → JPG | PASS | ZIP 改名 JPG，放入真实 7Z 后 Pipeline 继续恢复最终文件 |
| 16 | DLL/EXE/Unity 资源不误判 | PASS | 真实解压目录含 EXE、DLL、assets 及随机签名字节，只生成一个归档任务 |
| 17 | Android/AZ 忽略 | PASS | 自动测试和三个真实样本；跳过计数分别稳定为 1 |
| 18 | 重复运行 | PASS | “测试游戏2”连续执行 3 次，均完成且任务数不增长 |
| 19 | 已存在 GameArchive_Output | PASS | 真实样本保留旧输出，新增安全唯一目录 |
| 20 | 用户主动中断 | PASS | EXTRACTING/SCANNING/VALIDATING 三阶段可控中断与恢复 |
| 21 | Extractor 超时 | PASS | 真实 7-Zip 极短超时返回 FAILED，输出被追踪，源哈希不变 |
| 22 | 工具缺失 | PASS | ToolManager、Dispatcher、各 Adapter 自动测试返回 TOOL_NOT_FOUND，不崩溃 |
| 23 | 磁盘输出路径冲突 | PASS | 重复执行唯一命名；输出创建/写入/磁盘不足均结构化失败 |
| 24 | 中文路径 | PASS | 三个真实中文任务目录及 UTF-8 history 往返 |
| 25 | 超长/复杂文件名 | PASS | 178 字符完整路径，含中文、空格、括号、方括号，真实解压成功 |

## 真实样本结果

### 测试游戏

| 项目 | 结果 |
|---|---|
| 开始时间 | 2026-08-10 08:38:09 +08:00 |
| 完成时间 | 2026-08-10 08:38:22 +08:00 |
| TaskStatus | COMPLETED |
| success | true |
| 成功 / 失败 / 跳过 | 1 / 0 / 1 |
| 密码尝试数量 | 1 |
| PipelineGuard | 未触发 |
| ORPHANED_TEMP | 0 |
| 最终输出 | `测试游戏\GameArchive_Output\PC_extracted` |
| 源文件 SHA256 | 前后一致（2 个初始候选文件） |
| 非预期内部目录 | 0 |

真实链路包含 `PC.rar.lz4`，确认 LZ4 → RAR → 密码恢复 → 最终输出。

### 测试游戏2

| 项目 | 结果 |
|---|---|
| 开始时间 | 2026-08-10 08:39:23 +08:00 |
| 完成时间 | 2026-08-10 08:39:38 +08:00 |
| TaskStatus | COMPLETED |
| success | true |
| 成功 / 失败 / 跳过 | 4 / 0 / 1 |
| 密码尝试数量 | 2 |
| PipelineGuard | 未触发 |
| ORPHANED_TEMP | 0 |
| 最终输出 | `测试游戏2\GameArchive_Output\auto-1-LT1_extracted` |
| 源文件 SHA256 | 前后一致（2 个初始候选文件） |
| 非预期内部目录 | 0 |

### 测试游戏3——首次 RC 执行

| 项目 | 结果 |
|---|---|
| 开始时间 | 2026-08-10 08:40:12 +08:00 |
| 完成时间 | 2026-08-10 08:41:47 +08:00 |
| TaskStatus | COMPLETED |
| success | true |
| 成功 / 失败 / 跳过 | 3 / 0 / 1 |
| 密码尝试数量 | 2 |
| PipelineGuard | 未触发 |
| ORPHANED_TEMP | 1 |
| 最终输出 | `测试游戏3\GameArchive_Output\PC14191_embedded_extracted_2` |
| 源文件 SHA256 | 前后一致（4 个分卷文件） |

首次执行成功恢复最终游戏文件，但安全清理本次内部目录时返回 `PermissionError`。只读诊断确认目录中存在 2 个带 Windows ReadOnly 属性的文本文件。该目录被正确保留并报告为：

```text
ORPHANED_TEMP: CLEANUP_PermissionError
```

未自动删除任何未知历史目录。修复后通过 `CleanupManager.authorize_owned()` 显式授权，只删除该次运行拥有的残留；源分卷和 `GameArchive_Output` 保持存在。

### 测试游戏3——修复后真实复测

| 项目 | 结果 |
|---|---|
| 开始时间 | 2026-08-10 08:43:52 +08:00 |
| 完成时间 | 2026-08-10 08:45:02 +08:00 |
| TaskStatus | COMPLETED |
| success | true |
| 成功 / 失败 / 跳过 | 3 / 0 / 1 |
| 密码尝试数量 | 2 |
| PipelineGuard | 未触发 |
| ORPHANED_TEMP | 0 |
| 最终输出 | `测试游戏3\GameArchive_Output\PC14191_embedded_extracted_3` |
| 源文件 SHA256 | 前后一致 |
| 初始 archive task 数量 | 执行前 2，执行后 2 |

该样本覆盖真实 `7z.001/.002`、5,148,990,402 字节 JPEG 宿主、offset 23332 的加密 RAR5、密码恢复、Unity 游戏文件以及 Windows 只读输出文件。

## 重复运行验证

“测试游戏2”连续执行 3 次：

| 运行 | TaskStatus | 成功/失败/跳过 | archive tasks 前/后 | ORPHANED_TEMP | 最终目录 |
|---:|---|---|---|---:|---|
| 1 | COMPLETED | 4/0/1 | 2/2 | 0 | `auto-1-LT1_extracted_2` |
| 2 | COMPLETED | 4/0/1 | 2/2 | 0 | `auto-1-LT1_extracted_3` |
| 3 | COMPLETED | 4/0/1 | 2/2 | 0 | `auto-1-LT1_extracted_4` |

验证结果：

- 三次输出路径互不重复，旧输出未覆盖。
- 所有最终输出均存在。
- 原始压缩文件 SHA256 前后一致。
- 初始 archive task 数量始终为 2，没有逐次增长。
- 历史输出和旧内部目录没有重新进入初始任务。

## 中断恢复验证

使用真实 ZIP 与真实 7-Zip，在临时任务目录通过进度回调分别中断：

| 中断阶段 | 中断状态 | ORPHANED_TEMP | 下一次运行 | 源哈希 | 历史未知目录 | 显式清理 |
|---|---|---:|---|---|---|---|
| EXTRACTING | FAILED | 0 | COMPLETED | 不变 | 保留 | 无目录需要清理 |
| SCANNING | FAILED | 1 | COMPLETED | 不变 | 保留 | 安全授权后成功 |
| VALIDATING | FAILED | 1 | COMPLETED | 不变 | 保留 | 安全授权后成功 |

EXTRACTING 测试在创建输出目录之前中断，因此没有虚构 ORPHANED_TEMP。SCANNING 和 VALIDATING 已产生的本次运行目录均被记录；下一次运行的初始归档数量仍为 1，旧残留中的嵌套 ZIP 未被误扫。

## 磁盘与输出失败验证

未填满系统盘。使用真实文件系统错误和受控子进程结果验证：

| 场景 | ExtractionStatus | Report.failed_count | failure_stage | 是否误报成功 |
|---|---|---:|---|---|
| 输出父路径是普通文件，目录创建失败 | FAILED | 1 | EXTRACTION | 否 |
| 子进程写入被拒绝 | FAILED | 1 | EXTRACTION | 否 |
| 子进程报告磁盘空间不足 | FAILED | 1 | EXTRACTION | 否 |
| 真实 7-Zip 超时 | FAILED | 1 | EXTRACTION | 否 |

真实超时测试中，源 ZIP SHA256 不变，已创建的输出目录被运行追踪器记录。

## 安全回归结果

- 原始压缩包及分卷 SHA256 在真实任务执行前后一致。
- 原始任务目录均保留。
- `GameArchive_Output` 使用唯一目录，不覆盖旧结果。
- 历史未知目录没有被自动删除。
- CleanupManager 自动清理仅接受本次运行追踪器记录且通过边界校验的目录。
- 中断和异常默认保留已创建目录并记录 ORPHANED_TEMP。
- 显式清理需要重新授权，输入压缩包、任务根目录和最终输出受保护。
- 日志、报告和 history 不保存实际尝试密码；密码尝试步骤只记录序号和状态。
- 发现一个诊断假阳性：空历史目录名也可能是 Scanner 密码候选，而该名字可能作为普通输出路径的一部分出现在报告中。这不代表尝试密码被记录，但路径与候选文本的重合需要在未来隐私设计中明确。

## 本次真实缺陷与修复

### Windows 只读文件导致安全清理失败

根因：Python 在 Windows 上删除带 ReadOnly 属性的文件时，`shutil.rmtree` 抛出 `PermissionError`。

最小修复：仅当目录已经通过本次运行所有权和 CleanupManager 安全验证后，对 `PermissionError` 对应路径移除只读属性并重试。其他错误继续抛出，不扩大删除范围。

验证：

- 新增只读文件显式清理回归测试。
- 稳定性定向测试 6/6 通过。
- 全量测试 103/103 通过。
- “测试游戏3”真实复测 ORPHANED_TEMP 从 1 降为 0。

## 已知限制

1. 当前构建元数据仍是 `Development`，尚未标记为 RC。
2. 本轮只在一台 Windows 11 主机验证，尚未完成干净虚拟机安装包级测试。
3. 强制结束进程、断电或 `TerminateProcess` 无法保证应用有机会写入 ORPHANED_TEMP；本轮验证的是可捕获的用户中断。
4. 磁盘空间不足当前会结构化为 `FAILED/EXTRACTION`，但没有单独的 `DISK_FULL` 错误枚举。
5. 磁盘不足使用安全错误注入，没有故意填满系统盘。
6. 文件夹名称可同时作为密码候选和合法路径组成部分；当前不会记录尝试密码，但完整路径可能与候选文本重合。
7. 真实验证会按安全唯一命名在三个样本的 `GameArchive_Output` 下保留新增最终结果；没有删除或覆盖旧结果。

## 未解决问题

| 级别 | 问题 | RC 影响 |
|---|---|---|
| Release metadata | `BUILD_TYPE=Development` | 公开 RC 打包前应确认 |
| Environment coverage | 尚未在干净 Windows VM 验证启动脚本和工具缺失组合 | 建议作为 RC 发布门槛 |
| Diagnostics | 磁盘不足没有独立错误类型 | 不会误报成功，但用户提示精度有限 |
| Privacy semantics | 路径文本与文件夹型密码候选可能重合 | 实际密码未持久化；建议后续定义脱敏策略 |
| Hard termination | 无法在进程被强杀时落盘本次残留记录 | 文档中需说明，下一次启动只能人工检查 |

## RC 建议

核心处理能力达到 0.1.0 RC 候选标准，建议进入**内部 RC**。公开分发前建议完成以下两个发布动作：

1. 在干净 Windows 虚拟机执行无工具、仅 7-Zip、仅 WinRAR、仅 LZ4、全工具五种启动冒烟环境。
2. 明确将构建类型从 Development 切换为 RC 的发布流程和版本标识。

在不扩大功能范围的前提下，当前没有发现会修改源压缩包、覆盖既有最终输出或让失败任务误报成功的未解决核心缺陷。
