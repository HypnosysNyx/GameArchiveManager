# GameArchiveManager 软件架构

## 当前范围

GameArchiveManager 是面向 Windows 的游戏资源扫描、分析和递归解压管理器。当前版本以 Python 标准库为主，通过外部 7-Zip、WinRAR 和 LZ4 Adapter执行已验证的解压计划；没有 GUI，不会自动下载或安装工具。

`main.py` 是纯CLI adapter：提供主菜单、批量路径收集、分析预览、用户确认和结果展示。完整的任务执行、报告、历史、日志和安全清理流程仍由`GameArchiveService`提供。

## 模块职责

| 模块 | 当前职责 |
| --- | --- |
| `application` | 提供 `GameArchiveService`，组装配置、任务执行、报告、历史和任务日志 |
| `task` | 定义 Task、任务状态、只读分析流程和任务级递归执行入口 |
| `scanner` | 扫描文件、目录、空目录密码线索；递归发现新压缩包 |
| `analyzer` | 读取文件头，识别 ZIP、RAR、7Z、LZ4、复合容器及受宿主策略约束的嵌入归档 |
| `rules` | 提供 Android/AZ/安卓平台规则，以及真实归档格式之上的 ContainerRole 自动执行策略 |
| `config` | 定义 Settings，并从可选 `config.json` 加载受支持字段 |
| `security` | 执行输入文件大小检查、ZIP 内容预检查和解压后目录检查 |
| `execution` | 根据真实格式生成 `ExtractionPlan`，不直接调用工具 |
| `tools` | 发现和保存 7-Zip、WinRAR、LZ4 的工具路径状态 |
| `extractor` | 通过 Dispatcher 调度 7-Zip、WinRAR、LZ4 Adapter，并执行受控复合容器阶段；不负责任务级递归、整理或删除 |
| `coordinator` | 串联单个压缩包的分析、安全检查、计划、解压和密码恢复 |
| `password` | 保存密码候选，计算候选分数并排序；不保存到数据库 |
| `recovery` | 有限次数选择密码并连接 Extractor；不记录成功密码 |
| `pipeline` | 管理递归压缩包队列、深度、数量、重复路径和执行记录 |
| `report` | 将 TaskExecutionResult 或 PipelineResult 转为统一 TaskReport |
| `history` | 将安全摘要保存为 JSON，不保存密码和完整错误日志 |
| `logging_system` | 为每个服务任务创建脱敏日志文件 |
| `cleanup` | RuntimeTracker 记录本次运行拥有的技术目录；CleanupManager 仅删除通过边界检查并已授权的目录 |
| `organizer` | 判断最终内容根、折叠技术执行 lineage 为 DeliveryUnit、检测重复内容，并安全交付到 `GameArchive_Output` |
| `ui` | 当前仅保留包结构；尚未实现 GUI |

## 数据流程

```text
用户任务目录
  ↓
GameArchiveService 创建 Task
  ↓
TaskExecutor → TaskAnalyzer
  ↓
Scanner → ArchiveAnalyzer → ContainerRolePolicy → PasswordManager
  ↓
初始扫描边界、压缩包候选、密码候选、忽略项目
  ↓
InputArchiveRelationshipResolver → 选择 canonical input / 保守保留独立输入
  ↓
ExtractionPipelineRunner（每个初始压缩包一条 Pipeline）
  ↓
ExtractionCoordinator
  ↓
安全检查 → 执行计划 → Dispatcher（7-Zip / WinRAR / LZ4）→ 解压后检查
  ↓
ArchiveFinder 发现真实容器
  ↓
ContainerRolePolicy → CONTENT_CONTAINER保留 / ARCHIVE_WRAPPER继续
  ↓
PlatformFilter → 加入队列或记录跳过
  ↓
TaskExecutionResult
  ↓
FinalContentRootResolver → DeliveryUnitResolver → DuplicateContentDetector
  ↓
OutputOrganizer → GameArchive_Output（安全唯一名称并校验复制）
  ↓
TaskReport → HistoryStorage；RuntimeTracker → 安全清理或 ORPHANED_TEMP
```

GameLogger 在 ApplicationService 层记录任务开始、Task 创建、执行开始、执行完成、报告生成、历史保存和异常类型。

## CLI Session 生命周期

```text
Application start
  → Settings / ToolManager / HistoryStorage / GameArchiveService
  → SessionPasswordStore
  → CliSessionController main menu
       → new Task (fresh TaskAnalysisResult / Pipeline / Guard / RuntimeTracker)
       → TaskReport
       → return to menu
       → next fresh Task
  → explicit exit (session memory naturally disappears)
```

Session-scoped对象：Settings、ToolManager、HistoryStorage、GameArchiveService、SessionPasswordStore、CLI controller。Task-scoped对象：Task、analysis result、Pipeline/queue/Guard、RuntimeTracker/cleanup ownership、TaskReport、task password candidates、cancel/progress/output planning state。`ExtractionPipelineRunner`可以作为无任务状态的协作对象复用，但其`run()`每次必须新建Pipeline和Guard计数。

只有实际解压成功的密码才进入当前进程的SessionPasswordStore。错误密码不保存；任务目录中的空文件夹候选每次重新分析，不跨任务复用。

## Task 生命周期

TaskExecutor 当前实际使用的生命周期为：

```text
CREATED
  ↓
ANALYZING
  ↓
EXECUTING
  ↓
COMPLETED / COMPLETED_NEEDS_SELECTION / DELIVERY_FAILED / CANCELLED / FAILED
```

- 分析失败或所有实际 Pipeline 都失败时，Task 为 `FAILED`。
- 没有压缩包、全部被跳过，或至少有一条 Pipeline 成功时，Task 为 `COMPLETED`。
- 部分 Pipeline 失败时，Task 可以是 `COMPLETED`，但 `TaskExecutionResult.success` 为 `False`。
- Pipeline 节点独立记录 `EXTRACTING`、`SCANNING`、`VALIDATING`、`COMPLETED` 等阶段；Task 级 `SCANNING`、`WAITING_CONFIRM`、`EXTRACTING`、`ORGANIZING` 仍主要作为枚举预留。
- 解压成功但存在尚未选择的多个最终内容单元时为 `COMPLETED_NEEDS_SELECTION`；交付复制或校验失败时为 `DELIVERY_FAILED`。

## 解压流程

单个压缩包由 ExtractionCoordinator 按以下顺序处理：

1. ArchiveAnalyzer 根据文件头判断真实格式。
2. ArchiveContentInspector 读取 ZIP 目录元数据。RAR 和 7Z 当前只产生能力警告。
3. ArchiveSafetyChecker 检查压缩包大小、ZIP 内部路径、预计文件数量和预计总大小。
4. ExecutionStrategy 为 ZIP、7Z 选择 7-Zip；RAR 首选 7-Zip并保留 WinRAR 回退；LZ4 选择 LZ4 Adapter。复合计划在每一阶段后重新分析实际中间输出，不盲信预报的内部格式。
5. Dispatcher 选择对应 Adapter。统一 OutputPathGenerator 在目标已存在时追加 `_2`、`_3` 等后缀；7-Zip 仍使用 `-aos` 防止覆盖文件。
6. 只有允许回退的工具失败才切换备用工具；密码错误和损坏归档不会无限切换。
7. 解压成功后，ExtractionSafetyChecker 检查输出目录、实际文件数量和实际总大小。
8. ArchiveFinder 扫描输出目录；Analyzer确认真实格式后，ContainerRolePolicy先判断自动执行意图。
9. `CONTENT_CONTAINER`（当前为 ZIP 结构的 APK/DOCX/XLSX/PPTX/EPUB/JAR）保留在物理输出和 DeliveryUnit 中，不新建递归任务。
10. `ARCHIVE_WRAPPER` 再经过 PlatformFilter 后加入 Pipeline。显式文件输入优先，可将 APK 按 ZIP 执行。
11. Pipeline 受最大递归深度、最大任务数量、嵌入候选数量和重复路径检查限制。

ArchiveAnalyzer 与 ContainerRolePolicy 的边界是强制架构约定：

```text
ArchiveAnalyzer: What is this file?
ContainerRolePolicy: Should it be automatically unpacked?
```

`REAL_FORMAT == ZIP` 不再直接意味着 `AUTO_EXTRACT == YES`。

原压缩包不会被删除、移动或重命名。解压后检查失败时，结果会标记失败，但已经生成的输出仍会保留。

## 密码恢复流程

```text
Scanner 发现空文件夹名称
  ↓
PasswordManager 创建 PasswordCandidate
  ↓
PasswordScorer 评分排序
  ↓
首次解压返回 PASSWORD_REQUIRED
  ↓
PasswordRecoveryEngine.next_password()
  ↓
PasswordRetryExecutor 有限重试
  ↓
SUCCESS 时停止；WRONG_PASSWORD 时继续
```

- 密码候选可来自用户输入、空文件夹名称、历史或文本文件模型；当前自动分析流程使用空文件夹名称。
- Android 来源候选不会删除，只会降低评分。
- 最大尝试次数由 `max_password_attempts` 限制，绝对上限为 100。
- 密码明文不会写入 TaskReport、HistoryStorage 或 GameLogger。
- 当前没有数据库密码库，也不会记录密码成功次数。

## 当前未实现

- GUI 和拖放操作
- 专用 GUI（当前 CLI 已完整连接 ApplicationService）
- 持久化密码库
- RAR、7Z 内部文件列表的可靠预检查
- 回收站删除和未经用户确认的历史目录清理
- 暂停、恢复和持久化 Pipeline 队列
