# GameArchiveManager Real-World Regression Samples

> 这里记录脱敏后的真实文件系统样本。禁止记录密码。旧结果是历史证据，不自动代表当前版本；每次重大相关修改都应重新核验不变量。

## 状态说明

- `ACTIVE_REGRESSION_SAMPLE`：当前核心行为依赖它，相关修改必须回归。
- `HISTORICAL_SAMPLE`：保留历史价值，但当前样本/环境可能不完整。
- `NEEDS_VERIFICATION`：现有证据不足以做发布签字。

## Sample 1 — 测试游戏

**Status**：`ACTIVE_REGRESSION_SAMPLE`（历史真实验证）

- 场景：基础复合容器与密码恢复。
- 输入结构：目录中含PC资源和Android/AZ跳过项。
- 关键链路：`PC.rar.lz4 → LZ4 → RAR → password recovery → final output`。
- 曾发现问题：Settings到ToolManager/Dispatcher/Lz4Extractor路径注入曾断链；复合容器需要重新分析inner。
- 对应修复：统一工具路径传递、Dispatcher和Composite staged flow。
- 当前证据：旧RC真实报告记录COMPLETED，成功/失败/跳过为1/0/1，密码尝试1，源SHA256不变。
- 关键不变量：外层和源RAR不被修改；inner必须重新分析；日志/history不得含密码。
- 必须回归：工具注入、Composite、RAR fallback或密码执行器发生修改时。

## Sample 2 — 测试游戏2

**Status**：`ACTIVE_REGRESSION_SAMPLE`（历史真实验证）

- 场景：多归档、Android跳过、重复运行。
- 关键链路：多个初始归档和递归分支顺序执行。
- 曾发现问题：历史版本把save支线当最终内容；重复运行可能扫描旧输出或产生任务增长。
- 对应修复：INITIAL_SCAN历史输出排除、内容边界、唯一输出名称和Final Content模型。
- 当前证据：旧RC报告记录连续3次COMPLETED，archive task数量保持2，ORPHANED_TEMP=0，源SHA256不变。
- 关键不变量：旧`GameArchive_Output`不重扫、不覆盖；任务数不随运行次数增长。
- 必须回归：INITIAL_SCAN、输出命名、历史隔离或Final Content变更时。

## Sample 3 — 测试游戏3

**Status**：`ACTIVE_REGRESSION_SAMPLE`

- 场景：真实分卷、大型宿主、嵌入加密RAR5、密码恢复、Unity内容。
- 输入结构：真实`7z.001/.002`等分卷；解出5,148,990,402字节JPEG；RAR5签名offset 23332。
- 关键链路：`7z split → 5GB JPEG → embedded encrypted RAR5 → password recovery → Unity game`。
- 曾发现问题：
  - 512MiB同时被错误用作宿主总大小门槛和扫描量限制。
  - RAR5验证只接受header type 1，拒绝CRC正确的encrypted type 4。
  - Windows ReadOnly输出文件导致CleanupManager首次清理失败。
- 对应修复：流式限量扫描、`VALID_ENCRYPTED`、严格CRC/边界验证、显式owned清理处理只读属性。
- 当前结果：真实复测COMPLETED；当前桌面最终输出为`GameArchive_Output\【PC】Hail Dicktator`；旧RC修复后记录ORPHANED_TEMP=0和源SHA256一致。
- 关键不变量：大文件不能整文件载入内存；扫描上限外候选不进入Pipeline；错误CRC仍拒绝；源分卷不变。
- 必须回归：EmbeddedDetector、RAR5验证、分卷、密码、RuntimeTracker或CleanupManager变更时。

## Sample 4 — 测试游戏4

**Status**：`ACTIVE_REGRESSION_SAMPLE` / 发布签字 `PASS`（2026-08-19）

- 场景：完整Ren'Py游戏、内部真实ZIP存档、outer/inner输入重复。
- 输入结构：`PC/PC/DR2.exe`、`game/saves/auto-*.save`、`lib/`、`renpy/`，以及`PC.rar`/`PC.rar.lz4`关系。
- 曾发现问题：
  - `archive leaf == final content`导致save支线被交付。
  - INITIAL_SCAN深入完整游戏根，产生10个save初始任务。
  - outer wrapper和已存在inner分别执行，产生两份相同游戏。
- 对应修复：GameContent boundary、INITIAL_SCAN/PIPELINE_SCAN分离、InputArchiveRelationship强验证、DuplicateContent后置保险。
- 2026-08-19真实CLI证据（task `6c12337c-1257-4337-a208-cc20430c35c2`）：任务COMPLETED，12个执行节点全部成功，最终仅交付`GameArchive_Output\PC`；该目录包含3094个文件、138个子目录、10个原始save和`DR2.exe`，没有技术输出目录。两个源outer的执行前后大小和SHA256均一致，ORPHANED_TEMP为0，日志/history未发现密码候选明文，CLI任务结束后成功返回主菜单。
- 本次INITIAL_SCAN只发现两个根级outer，10个save没有成为INITIAL_SCAN候选；它们在新解压内容的PIPELINE_SCAN中成为递归节点，但对应final candidates全部以`DESCENDANT_OF_SELECTED_CONTENT_ROOT`抑制，没有save-only最终交付。
- 发布阻断事实：两个独立outer都成功执行。PC候选被交付；Android分支成功得到APK并被ContainerRole识别为应保留的内容容器，但其FinalContentCandidate为`NEEDS_USER_SELECTION`、DeliveryUnit却仍为`CANDIDATE`。CLI没有形成选择闭环，task/history仍标`COMPLETED / DELIVERED`，Android唯一run-owned物理结果随后被清理，最终输出只有PC。这是成功独立内容静默不交付及状态误报，登记为`mixed_selected_and_ambiguous_content_silent_nondelivery`。
- 2026-08-19 P0 Fix Verification：task `ce937e11-f0dd-4e60-830e-3dc1d7d5b26c`经真实CLI完成12个执行节点并同时交付`GameArchive_Output\PC_2`与Android内容根。PC为3094文件/1,416,390,030 bytes并保留10个save；Android为1个完整APK/1,270,709,161 bytes。两边无技术包装目录，ORPHANED_TEMP=0，旧`PC`未覆盖，两个源SHA256与修复前一致，日志/history未发现密码明文，CLI正常返回主菜单。KI-P0-002据此RESOLVED。
- 2026-08-19 Existing Game Root Evidence（`CONTROLLED REAL-SAMPLE COPY`）：从已交付真实PC内容复制3094文件/1,416,390,030 bytes，保留`DR2.exe`、`game/lib/renpy`和10个真实save。10个save均由ArchiveAnalyzer识别为`ZIP / confidence=1.0`。TaskAnalyzer真实INITIAL_SCAN访问2个目录，以`ROOT_EXECUTABLE + RENPY_GAME_ROOT / HIGH`建立1个`GAME_CONTENT_BOUNDARY`并剪枝；10个save均0初始任务。边界外兄弟`wrapper.zip`仍以ZIP/confidence 1.0被发现，说明剪枝未越界。save副本与来源逐个SHA256一致。
- 2026-08-19 Outer/Inner Evidence（`CONTROLLED REAL-SAMPLE DERIVATIVE`）：复制原始`PC.rar.lz4`后，用项目当前LZ4 v1.10.0确定性解码得到`PC.rar`（1,193,009,102 bytes，SHA256 `77127E31822F96AE415A54F3FA159CB7C5B5DB23F5B8BB379C12EF9D9B99A164`）。该inner是真实outer派生物，不是原始用户目录本来存在的文件。真实CLI Fast Path发现2个输入；`LZ4_DECODED_STREAM_SHA256`读取2,386,018,204 bytes并得到`VERIFIED / HIGH / CONFIRMED_OUTER_CONTAINS_EXISTING_INNER`，选择inner为canonical、suppress但不删除outer。Pipeline只以inner启动，11个节点（1 RAR + 10个新解压内容中的PIPELINE_SCAN save）全部成功；最终只有1个唯一PC content root和1个`GameArchive_Output\PC`。history中10条DeliveryUnit谱系诊断均指向同一PC root，不代表outer重复执行或10份交付。密码尝试1次，ORPHANED_TEMP=0，无密码持久化。
- Evidence Closure完整性：原始`PC.rar.lz4` SHA256 `92F8C8A267A562CD6AFCDAB77D94AF63BB1306C35DCCF82760AF936EC6D50633`，原始Android outer SHA256 `834B388C42FD70183E109E5B2314D459BC4B6D2A0422758BC33713C8A2712CDF`，前后一致。受控outer/inner前后SHA256亦一致，两文件均保留，最终内容为3094文件/1,416,390,030 bytes并含`DR2.exe`及10个save。
- Evidence Matrix：Original Real Sample证明PC+Android独立交付、源完整性、无save-only交付和混合交付cleanup安全；Controlled Real-Sample Copy证明Existing Game Root INITIAL_SCAN boundary；Controlled Real-Sample Derivative证明`PC.rar + PC.rar.lz4`强关系与唯一交付。三层正确性均PASS，Test Game 4正式从`NEEDS_VERIFICATION`升级为PASS。
- 关键不变量：save/mod不成为默认初始任务；显式save仍处理；outer/inner只有强哈希验证后才suppress；源SHA256不变。
- 必须回归：INITIAL_SCAN、GameContentClassifier、InputRelationship、Duplicate或Final Content变更时。

## Sample 5 — 测试游戏5

**Status**：`ACTIVE_REGRESSION_SAMPLE`

- 场景：无法仅靠高置信游戏分类交付的单一技术谱系。
- 关键链路：`RAR → ZIP → embedded/disguised → ZIP → Generic Content`。
- 终端结构：`B994000/`包含补丁目录、控制台代码目录和带`Mad Island.exe/Mad Island_Data`的游戏目录。
- 曾发现问题：4个成功execution nodes生成4个meaningful candidates；系统误认为有4份独立内容，全部`NEEDS_USER_SELECTION`，最终`output_paths=[]`。
- 对应修复：DeliveryUnit按祖先/子孙执行关系折叠技术lineage；单一terminal unit使用`SINGLE_TERMINAL_DELIVERY_UNIT`交付Generic Content。
- 当前结果：桌面存在`GameArchive_Output\B994000`；已核验记录为209个文件、总大小1,710,573,415 bytes。项目默认runtime history未包含这次独立验证记录，因此具体task_id标记`NEEDS_VERIFICATION`。
- 关键不变量：必须保留补丁与游戏共同顶层结构；不能只输出“生存游戏”；不能无限单目录拍平；源SHA256不变。
- 必须回归：DeliveryUnit、Generic Content、FinalContentRootResolver或OutputOrganizer变更时。

## Sample 6 — 测试游戏6

**Status**：`ACTIVE_REGRESSION_SAMPLE`

- 场景：`LZ4 → RAR → password/composite`失败诊断、候选污染和多内容根人工选择。
- 关键链路：外层LZ4成功，inner RAR需要密码；随后进入现有有限密码流程。
- 曾发现问题：Composite只保存`COMPOSITE_FAILED`，任务结束后无法知道inner真实失败；历史技术空目录又进入密码候选。
- 对应修复：stage_details持久化外层/内层状态、normalized failure reason、有限候选耗尽状态；历史run-owned残留通过共享INITIAL_SCAN技术边界排除，不再污染空目录候选。
- 当前实际状态（2026-08-15最新runtime history）：最新任务`COMPLETED`，成功1、失败0、跳过0、密码尝试1；用户通过CLI选择两个AMBIGUOUS_CONTENT DeliveryUnit，交付`GameArchive_Output\PC`和`GameArchive_Output\VR`。更早两次分别以`PASSWORD_REQUIRED/PASSWORD_CANDIDATES_EXHAUSTED`和`WRONG_PASSWORD/PASSWORD_CANDIDATES_EXHAUSTED`失败，并安全保留ORPHANED_TEMP。
- P0回归：修复后对当前真实目录只读分析为`candidate_count=1`、`technical_boundary_count=1`、`archive_count=1`、`COMPLETED`；未执行解压、未输出候选名称。
- 关键不变量：外层成功不能掩盖inner失败；失败记录不得含密码；未成功交付的唯一物理内容不能自动清理；多个根必须用户选择；重复失败不得增加候选集合。
- 必须回归：Composite、失败持久化、密码候选来源、CLI选择或Cleanup生命周期变更时。

## Platform filtering deterministic regression

**Status**：`PASS`（2026-08-15）

- 真实触发现象：随机临时父目录名包含`az`时，旧绝对路径substring规则可能误跳过正常内容。
- 确定性复现：父目录固定为`tmp_az_random`和`az_user`，任务根内部只有`PC/game.rar`；修复后均保留。
- AZ正例：`AZ/`、`az/`、`AZ_patch.zip`继续跳过并记录命中组件。
- 内容反例：`crazy`、`amazing_game`、`blazer`、`gazette`均保留。
- 交互：INITIAL_SCAN和PIPELINE_SCAN均验证；Android/安卓无回归；显式文件输入既有override语义不变。
- 安全不变量：测试只使用临时目录和受控归档，不删除、移动或修改用户文件。

## Manual password recovery deterministic regression

**Status**：`PASS`（2026-08-15）

- 自动候选正确时直接成功，不调用人工回调。
- 自动候选耗尽后支持manual correct及manual wrong→correct；只重试当前归档计划。
- Composite fixture验证LZ4 outer只执行一次，人工密码仅恢复inner RAR。
- 分卷fixture验证所有密码调用都使用第一分卷，后续卷不单独执行。
- skip返回`USER_SKIPPED_PASSWORD_ARCHIVE`；cancel传播为Task `CANCELLED`。
- 测试密码未出现在stdout、日志、report、history或repr；源SHA256前后一致。
- 这是受控文件系统回归，不替代测试游戏4签字或Clean Windows 11 VM。

## 真实样本使用规则

1. 运行前后计算源归档SHA256；任何变化都是NO-GO。
2. 记录开始/结束时间、TaskStatus、成功/失败/跳过、密码尝试数、Guard、ORPHANED_TEMP和最终输出。
3. 不把真实密码写入本文、测试名、日志、命令行记录或history。
4. 自动测试通过不能替代样本回归。
5. 样本不可访问、输出被人工移动或历史记录缺失时标`NEEDS_VERIFICATION`，不得补写猜测。
