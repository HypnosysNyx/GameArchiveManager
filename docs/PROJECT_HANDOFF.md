# GameArchiveManager 项目交接文档

> 最后核验：2026-08-19（Asia/Shanghai）

# New Developer / AI Start Here

本文件是项目知识总入口。没有任何聊天上下文时，按以下顺序阅读：

1. [`CURRENT_STATUS.md`](CURRENT_STATUS.md) — 当前版本、测试基线、P0和下一步。
2. [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md) — 当前架构、代码状态和完整交接。
3. [`DEBUGGING_PROTOCOL.md`](DEBUGGING_PROTOCOL.md) — 查错机制v2和证据要求。
4. [`PROJECT_VISION.md`](PROJECT_VISION.md) — 长期产品目标；不要误当当前功能。
5. [`ROADMAP.md`](ROADMAP.md) — 分阶段方向和进入/退出条件。
6. [`DECISIONS.md`](DECISIONS.md) — 不能随意推翻的重要技术决策。
7. [`REAL_WORLD_TESTS.md`](REAL_WORLD_TESTS.md) — 测试游戏1～6真实回归资产。
8. [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) — P0/P1/P2、限制和历史已解决问题。
9. [`ARCHITECTURE.md`](ARCHITECTURE.md) — 模块职责与设计架构。
10. [`SECURITY.md`](SECURITY.md) — 输入、执行、密码和清理安全边界。

辅助文档：[`CONFIGURATION.md`](CONFIGURATION.md)、[`USER_GUIDE.md`](USER_GUIDE.md)、[`RC_SMOKE_TEST.md`](RC_SMOKE_TEST.md)、[`RC_BUILD_NOTES.md`](RC_BUILD_NOTES.md)和历史[`RELEASE_CANDIDATE_REPORT.md`](RELEASE_CANDIDATE_REPORT.md)。

文档冲突时采用以下调查优先级：

```text
CURRENT_STATUS
>
当前代码 / 当前测试 / 当前runtime事实
>
PROJECT_HANDOFF
>
历史文档
```

这不是“静默选择谁正确”的授权。代码、测试、runtime数据和文档互相矛盾时，必须先做只读验证，记录时间点、证据来源和`NEEDS_VERIFICATION`，再决定是否修复代码或文档。

## 1. 项目概述

- 项目名称：GameArchiveManager
- 一句话目标：为 Windows 游戏资源提供真实格式识别、智能解压、递归恢复、有限密码尝试、安全整理和最终内容交付。
- 当前版本：`0.1.0`
- 当前 `BUILD_TYPE`：`Release`（正式版 `0.1.0` 已发布）
- 整体进度估计：约 90%
- 当前阶段：RC / 稳定性验证
- 当前不是新功能扩展阶段；核心功能已冻结，优先处理真实缺陷、回归和干净 VM 验证。

核心目标是：**Windows 游戏资源智能解压、递归恢复、密码尝试、安全整理和最终内容交付。**

默认安全原则：

- 不修改源文件。
- 不覆盖现有输出。
- 不自动删除未知历史目录。
- 不记录密码明文或含密码命令行。

## 2. 技术栈与运行环境

### Python 与依赖

- 语言：Python 3
- 当前开发机实际版本：Python 3.13.2
- 当前 Windows：Windows 11 专业版，`10.0.26200`，64-bit
- `requirements.txt`：空；运行时只使用 Python 标准库。
- `requirements-build.txt`：`pyinstaller==6.21.0`
- 无数据库、无 GUI 框架、无自动下载器。

主要标准库：`pathlib`、`dataclasses`、`enum`、`subprocess`、`json`、`logging`、`hashlib`、`shutil`、`zipfile`、`unittest`。

### 外部工具

当前支持：

- 7-Zip：ZIP、RAR、7Z；开发机检测版本 24.09，verified。
- WinRAR CLI（`Rar.exe`）：RAR 备用；开发机检测版本 7.12，verified。
- LZ4（`lz4.exe`）：LZ4 单流；开发机检测版本 1.10.0，verified。

工具发现优先级：

1. `Settings` / `config.json` 显式路径。
2. 应用目录 `tools/<tool>.exe`。
3. 应用目录 `tools/*/<tool>.exe`（只扫描一级子目录）。
4. Windows 常见安装目录。
5. Windows `PATH`。

找到文件后还必须成功执行版本查询才会标记 `verified=True`。

### 工作区 Junction

工作区：

```text
C:\Users\<redacted>\Documents\GameArchiveManager
```

实际指向：

```text
C:\Users\<redacted>\Documents\GameArchiveManager0.1.0
```

这是 Junction/目录映射，不是两个不同代码版本。`Path.resolve()` 或工具状态可能显示实际目标路径。

公开快照使用真实 git 仓库；不要把本地运行日志、VM 门禁材料或第三方解压工具二进制提交进库。

### 运行、测试和构建

源码运行：

```powershell
cd C:\Users\<redacted>\Documents\GameArchiveManager
py main.py
```

BAT 启动：双击 `start_game_archive_manager.bat`，内容为：

```bat
@echo off
cd /d "%~dp0"
py main.py
if errorlevel 1 pause
```

完整测试：

```powershell
py -B -m unittest discover -s tests -v
```

2026-08-15 当前基线：

```text
Ran 224 tests
OK
```

RC 构建：

```powershell
py -m venv .build_venv
& .\.build_venv\Scripts\python.exe -m pip install -r requirements-build.txt
& .\.build_venv\Scripts\python.exe -m PyInstaller --noconfirm --clean GameArchiveManager.spec
Copy-Item docs\RC_BUILD_NOTES.md dist\GameArchiveManager-0.1.0-RC2\
Copy-Item docs\RC_SMOKE_TEST.md dist\GameArchiveManager-0.1.0-RC2\
```

已存在 onedir RC 构建和 ZIP；打包版不要求 VM 安装 Python。日志/history 默认写入 `%LOCALAPPDATA%\GameArchiveManager`，最终内容写入任务根的 `GameArchive_Output`。

## 3. 项目结构

以下从真实工作区读取，生成目录和第三方 LZ4 包内部文件做了折叠：

```text
GameArchiveManager/
├─ analyzer/
│  ├─ archive_analyzer.py
│  ├─ embedded_detector.py
│  ├─ volume_detector.py
│  └─ models.py
├─ application/
│  ├─ app_service.py
│  ├─ progress.py
│  └─ runtime_paths.py
├─ cleanup/
│  ├─ cleanup_manager.py
│  ├─ runtime_tracker.py
│  └─ models.py
├─ config/
│  ├─ config_loader.py
│  └─ settings.py
├─ coordinator/
│  ├─ extraction_coordinator.py
│  └─ models.py
├─ execution/
│  ├─ strategy.py
│  ├─ output_paths.py
│  └─ models.py
├─ extractor/
│  ├─ dispatcher.py
│  ├─ seven_zip.py
│  ├─ winrar.py
│  ├─ lz4.py
│  ├─ composite.py
│  ├─ embedded.py
│  └─ extractor_models.py
├─ history/
│  ├─ storage.py
│  └─ models.py
├─ logging_system/
│  └─ logger.py
├─ organizer/
│  ├─ game_content_classifier.py
│  ├─ final_content_resolver.py
│  ├─ delivery_units.py
│  ├─ duplicate_content.py
│  ├─ output_organizer.py
│  └─ models.py
├─ password/
│  ├─ manager.py
│  ├─ scoring.py
│  └─ models.py
├─ pipeline/
│  ├─ extraction_pipeline.py
│  ├─ extraction_runner.py
│  ├─ guard.py
│  └─ models.py
├─ recovery/
│  ├─ password_recovery.py
│  ├─ password_executor.py
│  └─ models.py
├─ report/
│  ├─ task_report.py
│  └─ models.py
├─ rules/
│  ├─ archive_rules.py
│  ├─ password_rules.py
│  ├─ platform_rules.py
│  └─ platform_filter.py
├─ scanner/
│  ├─ scanner.py
│  ├─ archive_finder.py
│  ├─ initial_scan_boundary.py
│  └─ models.py
├─ security/
│  ├─ archive_safety.py
│  ├─ archive_content_inspector.py
│  ├─ extraction_safety.py
│  └─ models.py
├─ scripts/
│  ├─ project_state.py
│  ├─ verify_project_state.py
│  └─ rc_readiness.py
├─ task/
│  ├─ task_manager.py
│  ├─ task_analyzer.py
│  ├─ task_executor.py
│  ├─ input_relationship.py
│  └─ models.py
├─ tools/
│  ├─ tool_manager.py
│  ├─ models.py
│  └─ lz4_win64_v1_10_0/...
├─ ui/
│  └─ __init__.py               # 当前为空；没有GUI
├─ docs/
├─ tests/
│  ├─ test_integration.py
│  ├─ test_beta_integration.py
│  ├─ test_final_content_resolver.py
│  ├─ test_initial_scan_boundary.py
│  ├─ test_input_relationship.py
│  ├─ test_delivery_and_diagnostics.py
│  ├─ test_output_organizer.py
│  ├─ test_stability.py
│  ├─ test_rc_build.py
│  ├─ test_project_governance.py
│  └─ test_password_flow.py
├─ main.py
├─ version.py
├─ project_state.json           # 机器可读项目状态和release gates
├─ GameArchiveManager.spec
├─ requirements.txt
├─ requirements-build.txt
├─ start_game_archive_manager.bat
├─ build/                       # PyInstaller生成物
├─ dist/                        # RC onedir和ZIP
└─ logs/                        # 旧开发期日志/history；新运行默认写LOCALAPPDATA
```

目录职责：

| 目录 | 职责 |
|---|---|
| `scanner` | 文件夹扫描、INITIAL_SCAN 边界、发现归档 |
| `analyzer` | 文件头、伪装、分卷、复合容器、内嵌归档分析 |
| `task` | 任务分析、输入关系去重、任务级执行 |
| `execution` | 生成工具无关执行计划和安全输出路径 |
| `tools` | 外部工具发现、版本验证、状态管理 |
| `extractor` | 7-Zip/WinRAR/LZ4 Adapter，以及 Composite/Embedded 执行 |
| `pipeline` | 有限递归队列、状态和 Guard |
| `password` / `recovery` | 密码候选、评分、有限尝试 |
| `security` | 解压前内容检查和解压后限制 |
| `organizer` | 内容分类、DeliveryUnit、去重、最终输出 |
| `cleanup` | 本次运行目录所有权和显式安全清理 |
| `report` / `history` / `logging_system` | 可审计结果、历史和安全日志 |
| `application` | CLI、未来 GUI/API 共用服务层 |

## 4. 已完成功能

- **Scanner**：扫描文件/文件夹/空文件夹候选；关键文件 `scanner/scanner.py`。
- **ArchiveAnalyzer**：ZIP/RAR/7Z/LZ4 文件头识别；`analyzer/archive_analyzer.py`。
- **fake extension**：JPG/MP4/TXT 等扩展名与真实格式不一致时仍识别。
- **ContainerRolePolicy**：在 Analyzer 之后区分真实格式与自动执行意图。APK/DOCX/XLSX/PPTX/EPUB/JAR 自动保留，显式文件输入可执行。
- **EmbeddedArchiveDetector**：对允许的宿主类型流式查找并结构验证内嵌归档；`analyzer/embedded_detector.py`。
- **RAR5 `VALID_ENCRYPTED`**：有效 type 4 加密头可进入现有密码恢复；伪造CRC仍拒绝。
- **LZ4 → RAR composite**：LZ4 解码后重新分析中间文件，再进入普通 RAR 链；`extractor/composite.py`。
- **分卷压缩**：支持 `7z.001`、`zip.001`、`part01.rar`、`r00/r01`，只创建一个任务，缺卷在 Extractor 前失败。
- **平台过滤**：Android/安卓/AZ，初始和递归阶段均支持；发布默认保留，用户显式开启才过滤。
- **ToolManager**：配置、项目目录、常见路径和 PATH 发现，版本验证；`tools/tool_manager.py`。
- **执行 Adapter**：7-Zip、WinRAR、LZ4；RAR 首选 7-Zip，允许的失败才切 WinRAR。
- **PasswordCandidate**：密码、来源、完整来源路径、平台提示、优先级和成功次数模型。
- **PasswordScorer**：用户输入、历史成功、空文件夹、数字特征和 Android 降权等基础评分。
- **PasswordRecovery**：有限自动候选顺序；耗尽后可由UI无关回调原地人工恢复、跳过或取消；不保存明文密码。
- **SessionPasswordStore**：只保存当前进程中已实际成功的人工密码，退出即消失；不是持久密码库。
- **Pipeline 递归**：成功解压后用 `ArchiveFinder + ArchiveAnalyzer` 发现下一层，不只看扩展名。
- **PipelineGuard**：最大深度、新任务数、Embedded候选数和重复路径保护。
- **INITIAL_SCAN 边界**：高置信完整游戏根停止向内创建初始归档任务；显式归档输入可覆盖。
- **GameContentClassifier**：Ren'Py、Unity、Unreal和通用结构组合信号；EXE不是唯一条件。
- **InputArchiveRelationshipResolver**：识别 outer/inner 候选，并对 LZ4 wrapper 流式强验证 SHA256。
- **FinalContentRootResolver**：区分物理输出、逻辑根和最终内容根。
- **DeliveryUnit**：按 `archive_path/parent_archive/depth` 折叠纯技术执行谱系。
- **Generic Content**：只有一个明确 terminal delivery unit 时，即使不是高置信游戏也可交付。
- **DuplicateContentDetector**：quick manifest 后按需做完整 SHA256，失败时保守保留两份。
- **OutputOrganizer**：复制到 `GameArchive_Output`，验证清单，不覆盖，使用 `_2/_3` 唯一名称。
- **RuntimeTracker**：记录本次运行实际创建的目录。
- **CleanupManager**：只清理本次拥有且通过边界验证的目录；未知历史目录不自动删除。
- **Report**：统计、失败详情、阶段、工具、分卷缺失、DeliveryUnit和残留目录。
- **History**：UTF-8 JSON、`ensure_ascii=False`、旧 GB18030 兼容、不保存密码。
- **日志**：任务过程、版本、最终路径和标准化失败；不记录密码明文。
- **批量任务**：一次输入多个任务根，统一确认，顺序执行，独立报告和汇总。
- **CLI进度**：任务编号以及 EXTRACTING/SCANNING/VALIDATING 进度。
- **CLI人工选择**：多个最终内容候选可选择一个或“全部保留”。
- **CLI Session Loop**：一次启动复用单一ApplicationService/Settings/ToolManager/SessionPasswordStore，任务完成、失败或取消后返回主菜单；Task、Pipeline/Guard、Runtime ownership、report和task candidates每次独立。
- **RC构建**：PyInstaller onedir 和 ZIP 已生成；没有捆绑外部解压工具。

特别注意：

- `archive leaf` 不等于 `final content root`。
- `high-confidence game` 不等于唯一可交付内容；单一明确 Generic Content 也必须交付。

当前正确模型：

```text
Archive identification
→ Input relationship
→ Execution
→ DeliveryUnit
→ Final content
→ Duplicate check
→ OutputOrganizer
```

## 5. 当前关键代码状态

### `version.py` 完整内容

```python
"""GameArchiveManager 应用版本信息。"""

APP_NAME = "GameArchiveManager"
APP_VERSION = "0.1.0"
BUILD_TYPE = "Release"
```

### `config/settings.py` 完整内容

```python
"""GameArchiveManager 的用户设置数据模型。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    """保存用户选择的处理策略和外部工具路径。"""

    # Platform settings：默认保留所有平台内容。
    ignore_android: bool = False
    ignore_AZ: bool = False
    default_platform: str = "PC"

    # Cleanup settings：默认不删除任何用户文件。
    delete_archives: bool = False
    delete_empty_folders: bool = False

    # Tool settings：None 表示尚未配置对应工具路径。
    seven_zip_path: Path | None = None
    winrar_path: Path | None = None
    lz4_path: Path | None = None

    # Password settings：默认不保存或自动尝试历史密码。
    save_passwords: bool = False
    auto_try_password: bool = False

    # Runtime limits：限制递归规模、密码次数和外部工具运行时间。
    max_recursive_depth: int = 50
    max_archive_tasks: int = 1000
    max_initial_archive_tasks: int = 1000
    max_embedded_candidates: int = 20
    max_password_attempts: int = 20
    extraction_timeout_seconds: int = 300

    # Archive safety：解压前限制单个压缩包大小。
    max_archive_size_mb: int = 10240

    # 预留限制：None 表示第一版尚未启用对应检查。
    max_extracted_files: int | None = None
    max_total_extracted_size_mb: int | None = None
```

### TaskStatus

```python
class TaskStatus(str, Enum):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    EXECUTING = "EXECUTING"
    SCANNING = "SCANNING"
    WAITING_CONFIRM = "WAITING_CONFIRM"
    EXTRACTING = "EXTRACTING"
    ORGANIZING = "ORGANIZING"
    COMPLETED = "COMPLETED"
    COMPLETED_NEEDS_SELECTION = "COMPLETED_NEEDS_SELECTION"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    FAILED = "FAILED"
```

### ArchiveInfo 核心模型

```python
@dataclass
class ArchiveInfo:
    file_path: Path
    extension: str
    real_format: str
    is_fake_extension: bool
    confidence: float
    container_chain: list[str] = field(default_factory=list)
    is_multi_volume: bool = False
    volume_group: str = ""
    volume_files: list[Path] = field(default_factory=list)
    missing_volume_files: list[Path] = field(default_factory=list)
    is_embedded_archive: bool = False
    embedded_offset: int | None = None
    embedded_container_format: str = ""
    embedded_validation_status: str = ""
    embedded_validation_reason: str = ""
```

### ExtractionPlan 核心模型

```python
@dataclass
class ExtractionPlan:
    archive_path: Path
    detected_format: str
    selected_tool: ToolName | None
    output_path: Path | None
    requires_password: bool = False
    can_execute: bool = True
    message: str = ""
    primary_tool: ToolName | None = None
    fallback_tools: list[ToolName] = field(default_factory=list)
    container_chain: list[str] = field(default_factory=list)
    stages: list[ExtractionStage] = field(default_factory=list)
    is_multi_volume: bool = False
    volume_files: list[Path] = field(default_factory=list)
    missing_volume_files: list[Path] = field(default_factory=list)
    is_embedded_archive: bool = False
    embedded_offset: int | None = None
    embedded_container_format: str = ""
```

### DeliveryClassification

```python
class DeliveryClassification(str, Enum):
    GAME_CONTENT = "GAME_CONTENT"
    GENERIC_CONTENT = "GENERIC_CONTENT"
    AMBIGUOUS_CONTENT = "AMBIGUOUS_CONTENT"
    TECHNICAL_ONLY = "TECHNICAL_ONLY"
```

### FailureDetail

```python
@dataclass
class FailureDetail:
    file_path: Path
    stage: str
    tool: ToolName | None
    error_type: str
    reason: str
    missing_files: list[Path] = field(default_factory=list)
    depth: int = 0
    parent_archive: Path | None = None
    extraction_status: str = ""
    normalized_reason: str = ""
    password_attempt_count: int = 0
    fallback_tools_attempted: list[ToolName] = field(default_factory=list)
    final_tool: ToolName | None = None
    composite_stage: str = ""
    stage_details: list[dict[str, str]] = field(default_factory=list)
```

### ApplicationService 核心调用链伪代码

```python
settings = explicit_settings or ConfigLoader(config_path).load()
tool_manager = ToolManager(settings=settings)
task = Task(user_input)

with activate_directory_tracker(run_tracker):
    execution_result = TaskExecutor.execute(task)

report = ReportGenerator.generate(execution_result)
sources = successful_pipeline_outputs(execution_result, run_tracker)
roots, candidates = OutputOrganizer.resolve_and_organize(
    task.task_path,
    sources,
    run_tracker.owned_directories(),
    selection_callback,
)

update_delivery_status(report, task)
cleanup_only_verified_current_run_directories()
save_sanitized_history_and_log()
return report
```

### 新 AI 优先阅读顺序

1. `application/app_service.py`
2. `task/task_executor.py`
3. `task/task_analyzer.py`
4. `scanner/archive_finder.py`
5. `analyzer/archive_analyzer.py`
6. `pipeline/extraction_runner.py`
7. `coordinator/extraction_coordinator.py`
8. `organizer/delivery_units.py`
9. `organizer/final_content_resolver.py`
10. `organizer/output_organizer.py`
11. `task/input_relationship.py`
12. `report/task_report.py`
13. `history/storage.py`
14. `main.py`

## 6. 当前真实样本回归状态

状态以当前代码、2026-08-19测试、现有history和实际输出为准；旧RC报告中的测试数和构建类型不是当前基线。

| 样本 | 主要场景 | 当前结果 | 通过 | 已发现过的问题 | 当前用途 |
|---|---|---|---|---|---|
| 测试游戏1（旧报告称“测试游戏”） | `RAR.LZ4 → RAR → password recovery` | 历史真实记录为 COMPLETED，源哈希不变；当前代码自动回归覆盖该链 | 是（历史验证） | 工具注入、复合容器连接曾有问题 | 基础复合/密码真实回归 |
| 测试游戏2 | 多归档、重复运行、Android跳过 | 历史真实重复运行3次均完成且任务数不增长 | 是（历史验证） | 旧结果曾把save支线当最终内容，之后由测试游戏4推动边界/最终内容模型修复 | 重复运行和历史输出隔离 |
| 测试游戏3 | `7z.001 → 5GB JPEG → embedded RAR5 → password → Unity游戏` | 修复后真实 COMPLETED、ORPHANED_TEMP=0；当前桌面仍有最终输出 | 是 | 512MiB错误总大小限制、RAR5 type4拒绝、只读文件清理 | 大宿主、加密RAR5、分卷、清理回归 |
| 测试游戏4 | 完整游戏内真实ZIP save；`PC.rar` 与 `PC.rar.lz4` outer/inner重复 | Original Real Sample已验证PC+Android交付；项目外Controlled Copy已验证Existing Game Root boundary；真实outer的Deterministic Derivative已验证强关系只执行canonical inner | 是（2026-08-19 Evidence Closure） | save过度INITIAL_SCAN、leaf误选、outer/inner重复执行、混合候选静默不交付 | 游戏内容边界、输入关系和混合候选交付回归 |
| 测试游戏5 | `RAR → ZIP → JPG/embedded → ZIP → Generic Content` | 当前代码已实现DeliveryUnit；最新独立history为 DELIVERED；实际输出 `GameArchive_Output\B994000` 为209文件、1,710,573,415 bytes | 是 | 4个执行节点被误当4份内容，导致0输出 | DeliveryUnit / Generic Content核心回归 |
| 测试游戏6 | `LZ4 → inner RAR → password/composite → ambiguous roots` | 早期两次FAILED并正确记录耗尽原因；最新runtime history为COMPLETED并交付`PC/VR`；P0修复后只读分析只保留1个用户候选 | 内容恢复、失败诊断和候选边界均有证据 | 未记录ownership的legacy同名目录保守保留，不能按名称过滤 | 密码候选边界、Composite失败和多根选择回归 |

测试游戏5确认：过去有“COMPLETED但无输出”的旧记录；当前桌面实际存在`GameArchive_Output\B994000`，代码和自动回归也证明DeliveryUnit修复已生效。独立验证history不在默认runtime history中，具体task_id仍标`NEEDS_VERIFICATION`。

测试游戏6确认：Composite失败详情已持久化，最新真实运行已恢复并交付内容；历史技术目录候选污染已通过共享INITIAL_SCAN边界修复，真实目录只读分析为1个候选/1个技术边界。

## 7. 当前进度和待办

### 已完成

- 核心格式识别、真实执行、递归、密码恢复、安全、交付和可审计性。
- DeliveryUnit / Generic Content / CLI人工选择。
- Composite分阶段失败详情进入Report/history/log/CLI。
- PyInstaller RC构建。
- 当前自动测试224项（最终状态和耗时以`CURRENT_STATUS.md`为准）。

### Resolved P0：历史失败技术目录污染密码候选

历史现象：失败任务保留的技术目录空文件夹曾在下一次分析中进入`password_candidates`，候选数曾由3增长到7再到15。

根因：ArchiveFinder和Scanner存在两次独立遍历，归档裁剪没有形成Scanner可复用的boundary，属于password candidate source boundary rule drift。

修复：history中run-owned residual paths与`GameArchive_Output`形成`TECHNICAL_OUTPUT_BOUNDARY`，由ArchiveFinder和Scanner共享；没有增加`*_extracted`字符串黑名单，没有删除历史目录，也没有修改PasswordRecovery/PasswordScorer。

### P1

- `cli_startup_latency_regression`：NEEDS_REAL_ENVIRONMENT_VERIFICATION。Fast Path后开发机T1/T2约0.181秒；ToolManager仍占service init主要部分，但无严重计算延迟复现。
- `cli_direct_path_entry_regression`：RESOLVED。路径可在首屏直接粘贴/拖入；M菜单和Fast Path共享任务启动链。
- Test Game 4 Evidence Closure已通过，Required Real Sample Regression gate已闭合。
- 干净 Windows 11 VM 冒烟PAUSED；有条件补 Windows 10。
- 历史 `RELEASE_CANDIDATE_REPORT.md` 仍保留当时的 `Development/103 tests` 证据；当前事实以 `CURRENT_STATUS.md` 和 `project_state.json` 的正式版身份为准。
- 历史 RC VM 门禁记录保持不变；当前 `BUILD_TYPE="Release"`。

### P2

- Generic低置信多根语义：不能简单按子目录数、最大目录或EXE选根。
- 根据VM和真实样本决定是否进入正式0.1.0 Release。

## 8. 已知问题和限制

1. 当前无活动P0；历史候选污染已解决，详见`KNOWN_ISSUES.md`的Resolved P0。
2. 人工密码恢复闭环已实现；`save_passwords/auto_try_password`仍是未接线legacy设置，不代表持久密码库。
3. CLI Session Loop已完成；业务层不依赖CLI，未来GUI可复用同一ApplicationService和回调协议。
4. 已有最小 ContainerRole 语义层，但不是完整 ContentRootClassifier。当前明确支持 APK、JAR、Office Open XML 和 EPUB；`.save` 仍由游戏内容边界处理，不做全局判定。
5. 多个低置信Generic内容根的语义仍可能模糊；高置信多游戏根已有人工选择。
6. 强杀进程、断电或系统崩溃时，应用无法保证有机会写ORPHANED_TEMP。
7. 磁盘满能结构化失败但仍多归为`FAILED/EXTRACTION`，没有独立`DISK_FULL`枚举。
8. 工作区含LZ4二进制，但RC不捆绑；正式捆绑前必须完成来源和GPL义务审核。
9. README仍很简略，详细信息依赖docs。
10. 当前没有GUI，`ui`只是空包。
11. Windows干净VM尚未最终完成，因此不能标正式Release。
12. 部分旧history中文曾受编码影响；当前写入统一UTF-8且兼容读取GB18030，但旧内容的显示可能仍是历史数据本身问题。
13. 工作区没有可用Git仓库历史，修改前应额外谨慎保留用户文件。

## 9. 核心冻结区

除非真实样本证明存在明确bug，不要随意修改：

- `ArchiveAnalyzer`
- `EmbeddedArchiveDetector`
- `PIPELINE_SCAN`
- Extractor正常逻辑
- `PasswordRecovery`算法
- `GameContentClassifier`评分
- `CleanupManager`安全边界

允许修复明确bug，但必须先只读定位具体阻断条件，并保持正例、反例和交互例。

## 10. 安全原则

不确定时保守：

- 输入关系验证失败 → 两者都执行。
- Duplicate验证失败 → 两份都保留。
- 多内容根无法判断 → 用户选择。
- 最终内容未确认交付 → 不清理唯一物理输出。

禁止：

- 删除或修改源文件。
- 静默覆盖已有输出。
- 在日志/history/report中保存密码明文。
- 根据名称猜测并删除目录。
- `leaf = final`。
- `EXE = game`。
- `same name = duplicate`。

## 11. 给下一个AI的工作方式

1. 先读 `PROJECT_HANDOFF.md`、`CURRENT_STATUS.md`、`DEBUGGING_PROTOCOL.md`。
2. 先只读诊断，再修改。
3. 每个bug分别判断 Extraction correctness、Content correctness、Safety/performance correctness。
4. 每个新规则至少有正例、反例、交互例。
5. 修改后运行：`py -B -m unittest discover -s tests -v`。
6. 自动测试通过不是唯一完成标准。
7. 核心逻辑修改后必须回归相关真实样本，并验证源SHA256。
8. 不为让测试变绿而降低结构、CRC、SHA256或清理边界条件。

## Project Knowledge Maintenance Rules

项目知识必须随仓库存在，聊天记录不是项目事实的唯一来源。任何未来开发Agent或真人完成以下工作后，都必须在同一任务中维护对应文档：

| 发生的变化 | 必须更新 |
|---|---|
| 新增或改变架构决策 | `DECISIONS.md` |
| 真实样本发现新bug、修复或状态变化 | `REAL_WORLD_TESTS.md` |
| 增加长期方向或阶段计划 | `PROJECT_VISION.md` / `ROADMAP.md` |
| 当前P0、版本、测试基线或下一步变化 | `CURRENT_STATUS.md` |
| 发现、解决或重新分类限制 | `KNOWN_ISSUES.md` |
| 查错步骤、证据等级或RC判定变化 | `DEBUGGING_PROTOCOL.md` |
| 模块职责、数据流或边界变化 | `ARCHITECTURE.md` |
| 配置字段变化 | `CONFIGURATION.md` |
| 安全不变量或清理边界变化 | `SECURITY.md` |

维护方式：

- 日常重要任务只更新受影响文档，不要每次重写整份交接。
- `CURRENT_STATUS.md`必须短、可快速确认，并包含最后核验时间。
- 历史报告可以保留当时事实，不要为了当前一致性伪造历史；应注明其基线已过时。
- 未来规划必须标记CURRENT、PLANNED、EXPERIMENTAL或LONG-TERM。
- 无法从当前代码、测试、runtime记录或真实文件系统确认的内容统一标`NEEDS_VERIFICATION`。
- 任何会删除、抑制、不执行或不交付用户内容的规则，都要在决策和测试文档中留下高等级证据。

## Agent Startup Protocol

任何新的AI、Agent或真人开发者开始工作前：

1. 阅读`CURRENT_STATUS.md`。
2. 阅读`PROJECT_HANDOFF.md`。
3. 阅读`DEBUGGING_PROTOCOL.md`。
4. 运行：

   ```powershell
   py scripts/verify_project_state.py
   ```

5. 如果verifier返回FAIL，不允许直接开始新功能；先理解版本、文档、测试、P0或release gate为何不一致。
6. 当前任务涉及真实bug时，先按Debugging Protocol v2进行只读诊断。
7. 修改完成后再次运行完整测试和`py scripts/verify_project_state.py`。
8. 如果改变项目状态，同步`project_state.json`、`CURRENT_STATUS.md`及知识维护表指定的文档。

验证器是只读健康检查，不会自动修改`BUILD_TYPE`、修复issue、删除文件或执行真实5GB样本。
