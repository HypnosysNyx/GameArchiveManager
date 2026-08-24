# GameArchiveManager Project Vision

> 本文描述产品希望长期演进成什么，不代表所有内容已经实现。功能状态以 `CURRENT_STATUS.md` 和当前代码为准。

## 状态标签

- **CURRENT**：0.1.0 RC 当前已实现或已确立的产品行为。
- **PLANNED**：已有方向，但尚未进入实现承诺。
- **EXPERIMENTAL**：需要真实样本验证的探索，不应成为默认行为。
- **LONG-TERM**：长期愿景，可能随证据和用户需求调整。

## 1. 当前产品定位 — CURRENT

GameArchiveManager 当前是面向 Windows 游戏下载资源的智能解压与最终内容整理工具。0.1.0 的目标不是替代 7-Zip、WinRAR 或 LZ4，而是连接分析、外部工具执行、递归恢复和安全交付。

用户给出一个或多个下载资源目录或明确归档后，程序尝试完成：

```text
识别真实归档
→ 识别分卷和外层 wrapper
→ 有限密码恢复
→ 递归解压新归档
→ 区分技术包装层与用户内容
→ 安全交付到 GameArchive_Output
```

默认不变量：

- 不修改或删除源归档。
- 不覆盖已有输出，冲突时使用安全唯一名称。
- 不自动删除未知历史目录。
- 不记录密码明文或完整含密码命令行。
- 分析与执行分离，危险决定必须可解释。

## 2. 长期产品方向

### CURRENT

0.1.0 仍以游戏资源为主要真实场景。RC 阶段只处理已证明的缺陷、回归和发布验证，不为未来设想大规模重构。

### LONG-TERM

项目可能从“游戏专用智能解压器”逐步演进为“智能归档内容恢复与整理工具”，可能处理：

- 视频集合
- 文档与课程资料
- 图片集
- 软件包和模组
- 通用资源集合
- 其他具有多层包装、伪装格式或复杂交付结构的内容

这不是当前功能承诺。每一种新内容类型都必须先有正例、反例、交互例和真实样本。

## 3. Content Root 抽象

### CURRENT

当前实现使用 `GameContentClassifier`、`FinalContentRootResolver`、`DeliveryUnitResolver` 和 Generic Content 兜底来识别可交付内容。

### PLANNED

未来可在保持兼容的前提下逐步抽象为 `ContentRootClassifier`：

```text
ContentRoot
├─ GAME_CONTENT
├─ VIDEO_COLLECTION
├─ DOCUMENT_COLLECTION
├─ COURSE_CONTENT
├─ IMAGE_COLLECTION
├─ SOFTWARE_CONTENT
├─ GENERIC_CONTENT
└─ AMBIGUOUS_CONTENT
```

真正的问题不是“有没有 EXE”或“最深的压缩包是什么”，而是：**何时已经从技术包装层进入用户真正需要保留的内容区域。**

## 4. 包装层与内容层

长期必须区分“真实压缩容器”和“默认需要继续解包的包装归档”。两者不等价。

- `ARCHIVE_WRAPPER`：RAR、7Z、用户下载的包装 ZIP、分卷和 LZ4 wrapper 等，通常应继续执行。
- `CONTENT_CONTAINER`：APK、DOCX、XLSX、PPTX、EPUB、某些 JAR，以及 Content Root 内部的 ZIP-based save。它们底层可能是 ZIP，但本身可能已是用户需要保留的最终文件。

当前 0.1.0 已有最小 `ContainerRolePolicy`，在不修改 ArchiveAnalyzer 事实的前提下区分 `ARCHIVE_WRAPPER`、`CONTENT_CONTAINER` 和 `AMBIGUOUS`。第一批明确内容容器为 APK、DOCX、XLSX、PPTX、EPUB 和 JAR；显式文件输入可覆盖自动保留。这是未来 ContentRootClassifier 的基础能力，但不是完整的通用内容分类体系。

```text
Archive wrapper
↓
Archive wrapper
↓
Archive wrapper
↓
Content Root
↓
User Content
```

默认产品原则：

- 在 Content Root 上方，继续处理已验证的包装层。
- 进入高置信 Content Root 后，默认不把内部归档自动提升为新的初始任务或独立最终交付结果。
- 用户显式指定内部归档时，显式意图优先。

示例：

```text
game.rar
└─ GameRoot
   ├─ Game.exe
   ├─ Data/
   └─ saves/save.zip
```

`save.zip` 即使是真 ZIP，默认也是已确认游戏内容区域内的数据，不应取代整个游戏根。

同样的原则可以应用于未来内容类型：

```text
course.rar                  documents.7z
└─ Course                   └─ ProjectDocs
   ├─ 01.mp4                   ├─ PDF/
   ├─ 02.mp4                   ├─ Excel/
   ├─ notes.pdf                └─ backup.zip
   └─ attachments.zip
```

## 5. EXE 不是游戏根必要条件

`.exe` 只能作为强信号之一，不能作为唯一条件。游戏内容可能表现为：

- Windows EXE
- Ren'Py、Unity、Unreal 结构
- JAR 或 HTML/Web 游戏
- Python 或脚本入口
- 模拟器 ROM 集合
- Linux/macOS 内容
- 安装型内容或纯数据包

因此禁止把 `EXE == GAME` 或 `没有 EXE == 不是游戏` 写成产品规则。

## 6. 智能化原则

智能化不是让程序越来越大胆地猜，而是让自动决定依赖越来越可靠的证据。证据优先级：

1. 用户显式意图
2. 强结构验证（文件头、CRC、完整哈希等）
3. 内容边界
4. 执行树和容器关系
5. 内容结构启发式
6. 文件名和扩展名

越靠后的证据越弱。任何会导致 `SKIP`、`SUPPRESS`、不执行、不交付或删除的行为，都应要求更高等级证据。验证失败时默认保留，而不是武断丢弃。

## 7. 自动化与保守模式

### PLANNED — SMART

默认智能模式：自动处理外层包装，到达高置信 Content Root 后停止继续拆内部用户内容，并安全交付。

### EXPERIMENTAL — DEEP

高级模式可允许深入 Content Root 内部寻找更多归档。它必须显式开启，并需要独立的任务数量、深度和安全限制。

### CURRENT — EXPLICIT

用户明确指定某个归档时，该显式意图覆盖自动内容边界：

```text
explicit user intent > automatic content boundary
```

## 8. 最终交付哲学

程序不应过度猜测“哪个内容最重要”。更可靠的顺序是先过滤：

- 当前运行明确拥有的技术中间目录
- 经强验证的重复内容
- 已确认属于父 Content Root 的附属归档
- wrapper 承接层

然后将剩余的独立 `DeliveryUnit` 默认保留；多根且无法安全区分时交给用户选择。

核心思想是：**过滤不能交付的技术内容，而不是猜唯一最值得交付的内容。**

## 9. 愿景约束

- 不因长期愿景破坏 0.1.0 RC 的 Core Freeze。
- 不把 PLANNED/EXPERIMENTAL 写成 CURRENT。
- 不用新抽象掩盖现有真实缺陷。
- 每次扩展都必须遵循 `DEBUGGING_PROTOCOL.md` 的三层正确性和证据要求。
