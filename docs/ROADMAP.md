# GameArchiveManager Roadmap

> 路线图表达优先级和依赖，不承诺固定日期。当前状态以 `CURRENT_STATUS.md` 为准。

## Phase 0：0.1.0 RC 稳定

**当前阶段。**

优先事项：

- 修复真实样本证明的缺陷。
- 始终按查错机制 v2 分析 Extraction、Content、Safety/performance correctness。
- 保持已解决的密码候选历史污染回归不反弹。
- 保持测试游戏1～6长期回归记录。
- 在干净 Windows 11 VM 完成 RC 冒烟；条件允许时补 Windows 10。
- 核验打包版工具发现、中文路径、日志/history、重复运行和中断恢复。

本阶段禁止：

- 大规模架构重构。
- GUI 大开发。
- 一次性支持大量新格式。
- 为让测试变绿降低结构、CRC、SHA256或安全清理验证。

退出条件：

- P0 清零或有明确不可发布说明。
- 自动测试与真实样本回归通过。
- 干净 VM 满足 `RC_SMOKE_TEST.md` 的 GO 标准。
- 不存在源文件修改、密码泄漏、Pipeline不结束或清理越界。

## Phase 1：0.1.x 稳定性

目标是稳定现有游戏解压能力，而不是扩张产品边界。

候选工作：

- `apk_content_container_recursive_unpack`：已解决。最小 ContainerRole 策略已区分真实格式与自动执行意图；后续只在有真实样本证据时扩充内容类型。
- 更精确、可持久化的失败诊断。
- 扩充脱敏后的真实样本回归资产。
- 稳定 DeliveryUnit 和最终内容交付。
- 改进日志、报告和 history 的审计一致性。
- 在不降低安全性的前提下优化大文件扫描和关系验证性能。
- 改善工具缺失、未验证和命令失败时的用户提示。
- 完善 Windows portable/onedir 构建与升级说明。

## Phase 2：用户体验

在核心稳定后才评估：

- GUI 与拖放目录/归档
- 任务列表和批量处理
- 分阶段进度显示
- 分析结果和危险操作预览
- 模糊 DeliveryUnit 的可视化选择
- 普通/高级模式与设置页面
- 人工密码输入可设置显示或隐藏（默认隐藏/`getpass`；显示仅用于当前输入回显，不写入日志/history/report，也不等于持久密码库）

当前 CLI 已有批量任务、预览确认和模糊候选回调，但这些不是完整 GUI 体验。

### 已完成的交互基础

- **NEXT-1：密码失败后的人工恢复闭环**：已完成。自动候选耗尽后可由可选回调安全输入、跳过或取消；成功密码只在当前进程的 SessionPasswordStore 中保留。
- **NEXT-2：CLI Session Loop**：已完成。启动一次后可连续提交单/批量任务、查看最近结果、工具与设置并主动退出。Settings、ToolManager、HistoryStorage、ApplicationService和SessionPasswordStore复用；Task、Pipeline/Guard/runtime state、TaskReport及task-level candidates每次重建。

下一阶段不再增加0.1.0功能，进入Release Validation：测试游戏4签字级真实回归，必要时复跑3/5/6，然后执行clean Windows 11 VM并重新评估GO/NO-GO。

## Phase 3：Content Root 抽象

逐步从 `GameContentClassifier` 演进到兼容的 `ContentRootClassifier`。先提取共享证据模型和诊断结构，避免一次性替换整个 Final Content 流程。

进入条件：

- 0.1.x 游戏交付语义稳定。
- 至少存在多个非游戏真实样本，证明通用抽象有必要。
- 新旧分类可并行验证，不静默改变当前游戏结果。

## Phase 4：更多内容类型

可能探索：Video、Documents、Course、Images、Software 和 Generic bundles。

每增加一种类型必须具备：

- 正例：应识别并交付。
- 反例：结构相似但不应误判。
- 交互例：与已有游戏、通用内容或多个根共存。
- 真实样本：非纯 mock 的文件系统验证。
- 失败和不确定状态：不能静默丢内容。

## Phase 5：更智能的归档关系

当前 `InputArchiveRelationshipResolver` 重点覆盖 LZ4 wrapper 与已存在 inner 的强验证关系。

未来可能支持：

- 其他单流 wrapper
- 跨目录 outer/inner 关系
- 更复杂的 multi-container 关系
- 更低成本的重复候选预筛选

所有扩展必须保持：

```text
cheap candidate detection
→ strong verification
→ suppress
```

不能仅凭名称、stem、目录名或最终输出名去重。

## Phase 6：工具管理体验

未来可能提供：

```text
检测工具
→ 解释缺失/未验证状态
→ 提供官方来源信息
→ 用户明确确认后下载或安装
```

绝对禁止静默下载、静默安装或使用来源不明的二进制。任何捆绑工具都必须先完成来源、版本和许可审核。

## Roadmap 维护规则

- 已实现事项移入交接/架构文档，不把路线图当完成证明。
- 新阶段不能绕过前一阶段的退出条件。
- 优先级改变时同步 `CURRENT_STATUS.md`。
- 重大方向改变时同步 `DECISIONS.md` 和 `PROJECT_VISION.md`。
