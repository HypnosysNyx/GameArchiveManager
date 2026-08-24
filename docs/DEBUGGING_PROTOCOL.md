# GameArchiveManager Debugging / Validation Protocol v2

## 1. 为什么需要v2

历史上出现过：

- 自动测试全部通过，但真实样本失败。
- successful leaf output被误当final content。
- EmbeddedDetector仅凭签名字节误判DLL/游戏资源。
- 防误判条件过严，又漏掉真实5GB JPEG中的早期RAR。
- INITIAL_SCAN深入完整游戏目录，把真实ZIP格式save变成独立任务。
- 外层`PC.rar.lz4`和已存在内层`PC.rar`重复执行并交付两份相同游戏。
- Pipeline成功，但用户内容停留在技术`*_extracted`目录，没有交付。

结论：**模块局部正确，不等于产品整体正确。**

## 2. 三层正确性

每个bug必须分别判断：

### Extraction correctness

- 真实格式是否识别正确？
- 工具和fallback是否正确？
- 密码、分卷、Composite子阶段状态是否真实？
- 成功/失败是否与外部工具结果一致？

### Content correctness

- 恢复的是不是用户真正需要的完整内容？
- 是否把技术中间目录、archive leaf或单独支线误当最终结果？
- 是否丢失补丁、文档、资源等同一DeliveryUnit内容？
- 多内容根是否被错误只选一个？

### Safety/performance correctness

- 源文件SHA256是否不变？
- 是否覆盖、越界清理、重复扫描或任务爆炸？
- 密码和敏感工具输出是否泄漏？
- 大文件、重复运行和失败残留是否造成无界成本？

## 3. 标准诊断顺序

必须遵循：

```text
真实现象
→ 只读调用链
→ 找到具体阻断条件
→ 明确根因
→ 最小修复
→ 正例
→ 反例
→ 交互例
→ 完整自动测试
→ 真实样本回归
```

只读阶段至少检查实际入口、数据类型、状态枚举、parent/depth、physical output、logical root以及信息在哪一步丢失。不要先假设是Analyzer、Pipeline、Extractor或Resolver。

## 4. 禁止做法

禁止：

- 看到失败就直接改代码。
- 只依赖扩展名。
- 只依赖EXE。
- 只依赖leaf。
- 只依赖文件名或目录名。
- 只依赖目录大小。
- 自动删除未知目录。
- 为通过测试降低结构/CRC/完整头验证强度。
- 用测试数量代替覆盖质量。
- 把过去建议方案写成已实现事实。

## 5. 证据等级

### LOW

名字、扩展名、路径或stem猜测。可用于生成候选，不能单独用于删除、suppress或跳过用户输入。

### MEDIUM

目录结构、container_chain、内容特征、父子执行关系、GameContent组合信号。可用于排序和缩小强验证范围。

### HIGH

结构验证、边界检查、CRC、完整SHA256、真实外部工具执行记录、经过验证的RuntimeTracker所有权。

任何会`suppress`或`skip`用户输入的行为，原则上需要HIGH证据或明确、可解释的安全策略。验证失败时保守处理。

## 6. 可审计性要求

Report/history应尽量持久化：

- archive path
- parent archive
- depth
- physical output
- logical root / final content root
- delivery unit / execution lineage
- selection reason / suppressed reason
- input relationship
- verification method / bytes read / time
- failure stage
- final extraction status
- fallback tools / final tool
- Composite outer/inner阶段
- ORPHANED_TEMP原因

不得持久化：

- 实际密码。
- 完整含密码命令行。
- 无界完整外部工具错误输出。

## 7. 真实样本回归规则

核心逻辑修改后，至少回归与改动对应的真实样本，并记录：

- 开始/结束时间。
- TaskStatus及成功/失败/跳过数量。
- Pipeline节点、depth和Guard状态。
- physical/logical/final路径。
- ORPHANED_TEMP。
- 源文件修改前后SHA256。
- 最终文件数、总大小和关键结构。
- 日志/history是否包含密码。

不能因为`137 tests OK`、`141 tests OK`或任何更大数字就直接宣称稳定。自动测试证明已编码场景没有回归，不证明未知真实结构正确。

## 8. RC判定

RC GO必须同时满足：

- 自动测试通过且覆盖正例、反例、交互例。
- 相关真实样本通过。
- 最终内容正确，不只是工具返回成功。
- 源文件不变且旧输出不被覆盖。
- 无密码泄漏。
- 无越界或错误清理。
- 失败可解释并可在任务结束后恢复原因。
- clean Windows VM启动和工具组合测试通过。

任何一项不满足，都不能标正式Release。失败应先记录根因，不得为报告变绿而弱化测试或安全规则。

# Definition of Done

任何未来bugfix、feature或refactor只有同时满足适用条目，才算真正完成：

1. 已在issue、`KNOWN_ISSUES.md`、`REAL_WORLD_TESTS.md`或任务说明中记录真实问题/目标。
2. 已明确root cause；不能只记录表面错误或“改后能跑”。
3. 修改范围最小、可解释，并说明为什么没有扩大到冻结区。
4. 有正例测试，证明目标行为成立。
5. 有反例测试，证明相似但不应触发的输入不会误判。
6. 有交互测试，证明新规则与现有边界、显式意图或其他模块共同工作。
7. 完整自动测试通过，且测试数量不低于`project_state.json`基线。
8. 涉及真实样本时，完成对应`REAL_WORLD_TESTS.md`回归。
9. 可能影响输入/输出文件时，验证源文件SHA256不变。
10. 日志、报告、history和文档中不存在密码明文或完整含密码命令行。
11. 不违反Cleanup、Runtime ownership、ORPHANED_TEMP和最终交付安全边界。
12. 更新`CURRENT_STATUS.md`的最后核验、测试基线、P0和下一步（如发生变化）。
13. 产生新架构决策时更新`DECISIONS.md`。
14. 真实样本发现新问题或状态改变时更新`REAL_WORLD_TESTS.md`。
15. 新增、改变或解决限制时更新`KNOWN_ISSUES.md`。
16. 长期方向改变时更新`ROADMAP.md`和/或`PROJECT_VISION.md`。
17. `py scripts/verify_project_state.py`通过。

`tests OK`只是Definition of Done的一部分，不能单独等价于完成。真实样本不可用、VM未验证或证据不足时应标`NEEDS_VERIFICATION`，不得为了宣称完成而猜测。

## 项目知识自动维护原则

代码修改只是任务的一部分：

```text
架构决策改变       → DECISIONS.md
真实样本发现问题   → REAL_WORLD_TESTS.md
当前优先级变化     → CURRENT_STATUS.md + project_state.json
新增或改变限制     → KNOWN_ISSUES.md
长期方向变化       → ROADMAP.md / PROJECT_VISION.md
查错流程变化       → DEBUGGING_PROTOCOL.md
release gate变化   → project_state.json
```

重要知识不能只存在于聊天记录。机器状态与文档冲突时，先只读验证，不允许验证器自动修复业务状态。
