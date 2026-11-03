# GameArchiveManager Real-World Regression Samples

## 2026-11-03 空文件夹密码机制：真实发现、修复与验收边界

- **真实原因确认**：`TaskAnalyzer.analyze()` 对明确选中的压缩文件提前返回，之前没有执行空文件夹密码收集。此功能不依赖“自动尝试已保存密码”开关；后者为 false 只关闭历史库的自动候选，不能据此关闭从任务目录发现的文件夹密码。
- **资源7来源**：`C:\SampleArchives\样本7` 下有 1 个真正空文件夹（其名称为密码，密码值不进入文件、日志或交接报告）；`sample_group\PC` 下另有 2 个空目录但它们的名称在只读验证中都未解锁外层。上层真正候选的名称成功解锁 `sample_group\PC\sample_pc.7z.001` 加密目录（7-Zip 列表 exit 0），并**完整通过 PC 三卷外层 7-Zip 数据测试**（7z t / Everything is Ok / exit 0）。现有 `sample_pc_embedded.rar` 使用同一上层候选未列目录成功；因此只能记 **OUTER_7Z_CRC_PASS / INNER_RAR_NEEDS_VERIFICATION**，未运行新的完整应用端到端。
- **资源8来源**：`C:\SampleArchives\样本8` 根目录有 1 个真正空文件夹；对两份新 RAR 的明确单文件入口，修复前自动文件夹候选 0 个，修复后 `TaskAnalyzer` 的只读实测各 1 个。直接对 MP4 宿主用 7-Zip 当 RAR 列目录返回非零不能据此断定候选错误，因为真实内嵌 RAR 有非零偏移。
- **唯一生产修复切片**：Codex 只修改 `task/task_analyzer.py`，使明确压缩文件入口也会非递归收集该文件**直接父目录内真正空且不是符号链接/重解析点**的文件夹名，排序确定，不打开或遍历其他目录。新增 `tests/test_password_candidate_boundaries.py` 的 7 个回归场景，验证明确文件、显式文件路径、非空排除、链接/Windows junction 排除、不遍历输出子目录、确定顺序/不重复以及候选实际进入执行器的自动重试。**此切片不自动向任意祖先目录搜密码**；资源7应选择游戏资源根目录以获得上层密码来源，不能将直接选择 PC 首卷视为能获取祖先密码。
- **修复后资源8a真实程序复验**：通过当前源码 `GameArchiveService.execute_task` 再次处理 4.61 GB 的外层 RAR，`auto_try_password` 仍为 false / 用户配置未修改，日志 `.vm_gate/real_e2e_sibling_fix_8a.json` 明确记录 `password_attempt_count=1`（修复前 0），说明根目录空文件夹候选已传入后续加密 RAR 验证。外层 1 成功；内层仍 `EMBEDDED_INCOMPLETE` / 1 失败、未完成数据 CRC；最终任务 **FAILED / E2E=False**。不把一次自动尝试等同于正确密码。后续尚未对大 RAR 完成修复后的真实运行。
- **容量与保护**：测试未覆盖、修改或删除原始归档/密码库/历史输出；这次 8a 再试产生新的外层交付副本，磁盘可用空间降至约 33 GB，后续多 GB 内层解压前必须核算空间，禁止擅自清理旧结果。用户密码未打印、回显、持久化或写进命令行参数。无需更改当前 `config.json`。
- **本次测试执行结果**：Codex 在修复前先获得 7 个如期失败；修复后 ChatGPT 在本机使用 `.build_venv/Scripts/python.exe -B` 实际复跑相关聚焦 unittest **59/59 PASS，exit 0**，完整 unittest discover **329/329 PASS、0 skipped、exit 0**，`scripts/verify_project_state.py` **Overall PASS，exit 0**。环境：隔离 LOCALAPPDATA、VIRTUAL_ENV 指向 `.build_venv`、TCL_LIBRARY 和 TK_LIBRARY 分别设置为相对路径 `.vm_gate/tcl8.6`、`.vm_gate/tk8.6`。日志 `.vm_gate/explicit_password_final_focused.log`、`.vm_gate/explicit_password_final_full.log`、`.vm_gate/explicit_password_final_governance.log`；实测证据 `.vm_gate/sibling_empty_password_probe.json`、`.vm_gate/sample7_ancestor_empty_password_probe.json`、`.vm_gate/sample7_root_password_real_crc.json`、`.vm_gate/real_e2e_sibling_fix_8a.json`。
- **下一个单切片**：在不放宽扫描/加密校验前提下诊断资源8真实内嵌候选的最后验证状态和用户期望密码来源；先预留充足磁盘空间及确认之前新增重复输出的安全处置，再复验 8a/8b 全流程。对于资源7，正式从游戏根目录读取密码候选并在空间充足时全链路验证内嵌 RAR 的实际数据与交付；若要求直接选首卷也发现祖先密码，须单独设计受限且由用户明确选择的密码搜索根，而非任意向上搜索磁盘。



## 2026-11-02 自动密码功能补核对（当前真实样本不能标通过）

- 上轮真实测试确实**没有启动已保存密码自动尝试**：项目当前 `config.json` 的 `auto_try_password` 为 `false`；本次测试脚本 `.vm_gate/real_e2e_runner.py` 将 `LOCALAPPDATA` 指到 `.vm_gate/real_e2e_profile`，该隔离目录下无用户密码库。三项 `real_e2e_{7,8a,8b}.json` 都记录自动密码尝试次数为零。该结果不能评价正式密码库自动尝试功能。
- 原 Windows 用户密码库中仅确认存在 2 条已保存的加密密码记录，**未打印、未写出任何密码值**。通过 `.build_venv/Scripts/python.exe -B .vm_gate/sample7_saved_password_listing_check.py` 只在进程内读取该库、依次对资源7 PC 首卷执行只读 7-Zip 目录验证，结果 **2 次均 exit 2、0 次列目录成功**；证据 `.vm_gate/sample7_saved_password_listing_check.json`。这是只读的目录解锁检查，**不等同完整数据/CRC 验收**，也不能仅据 exit 2 断定源归档损坏。
- 源码 `task/task_executor.py` 确认：任务扫描发现的密码候选始终有机会被尝试；只有 `auto_try_password` 为 true 时，才自动加入本机存储的已保存密码。上一轮漏测本机密码自动匹配是测试方案的问题，而不是已证明软件功能不可用。Sample8 两份 RAR 的内嵌层尚未使用上述已保存密码实测。
- 不擅自修改用户长期配置、不将用户密码复制到隔离配置或测试日志。下一次完整验收需要安全地在单次运行中临时启用已保存密码候选、只在本机用密码、明确磁盘剩余空间和无覆盖输出，失败时通过本机遮盖密码弹窗恢复。此前所有 7/8 真实 E2E 仍为 NEEDS_VERIFICATION。



## 2026-11-02 内嵌候选代码修复证据边界

- **SYNTHETIC_REGRESSION_VERIFIED；Sample 8 / app end-to-end 仍为 NEEDS_VERIFICATION，不是 PASS。** 原 Sample 8 宿主已在输出验证后删除，无法重放，精确假阳性 offset 未证明。既有输出核验仅证明输出完整性。
- 合成宿主含 CRC 有效 RAR5 加密头诱饵，后接本机 RAR 工具生成的真实 RAR5。安装的 7-Zip 拒绝第一候选，选择第二 offset，完整解出正确内容，宿主 SHA-256 不变。另一个真实工具用例确认 listing exit 0 后数据 CRC 失败仍拒绝并回退。首个候选真正有效时不验证后续候选；ZIP/7Z 与既有 RAR4/RAR5、递归、分卷回归通过。
- 受控密码测试覆盖两个加密候选、共享自动预算、一次人工提交成功于后一个候选、错误后正确、全部错误、空提交、skip/cancel、仅成功后保存与敏感信息边界；既有真实工具加密 RAR5 自动密码回归通过。普通人工恢复与 GUI 接线未重写。
- 聚焦 142 项 / 完整 311 项，均 exit 0、0 skipped；命令与隔离环境见 CURRENT_STATUS。本次没有新 EXE、打包、发布或 clean VM 验收。
- 边界：512 MiB 搜索窗口、4096 raw hits、8 候选、48 GiB 累计切片、1 GiB 磁盘保留、300 秒活跃工作 / 60 秒单进程、256 次进程调用、4 MiB 单次工具输出。超限或不能完成校验记 EMBEDDED_INCOMPLETE，不标归档损坏。需要可保留原宿主的新样本才能补齐真实端到端验证。


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
- 当前结果：真实复测COMPLETED；当前桌面最终输出为`GameArchive_Output\【PC】示例游戏`；旧RC修复后记录ORPHANED_TEMP=0和源SHA256一致。
- 关键不变量：大文件不能整文件载入内存；扫描上限外候选不进入Pipeline；错误CRC仍拒绝；源分卷不变。
- 必须回归：EmbeddedDetector、RAR5验证、分卷、密码、RuntimeTracker或CleanupManager变更时。

## Sample 4 — 测试游戏4

**Status**：`ACTIVE_REGRESSION_SAMPLE` / 发布签字 `PASS`（2026-08-19）

- 场景：完整Ren'Py游戏、内部真实ZIP存档、outer/inner输入重复。
- 输入结构：`PC/PC/game.exe`、`game/saves/auto-*.save`、`lib/`、`renpy/`，以及`PC.rar`/`PC.rar.lz4`关系。
- 曾发现问题：
  - `archive leaf == final content`导致save支线被交付。
  - INITIAL_SCAN深入完整游戏根，产生10个save初始任务。
  - outer wrapper和已存在inner分别执行，产生两份相同游戏。
- 对应修复：GameContent boundary、INITIAL_SCAN/PIPELINE_SCAN分离、InputArchiveRelationship强验证、DuplicateContent后置保险。
- 2026-08-19真实CLI证据（task `[本地任务 ID 已脱敏]`）：任务COMPLETED，12个执行节点全部成功，最终仅交付`GameArchive_Output\PC`；该目录包含3094个文件、138个子目录、10个原始save和`game.exe`，没有技术输出目录。两个源outer的执行前后大小和SHA256均一致，ORPHANED_TEMP为0，日志/history未发现密码候选明文，CLI任务结束后成功返回主菜单。
- 本次INITIAL_SCAN只发现两个根级outer，10个save没有成为INITIAL_SCAN候选；它们在新解压内容的PIPELINE_SCAN中成为递归节点，但对应final candidates全部以`DESCENDANT_OF_SELECTED_CONTENT_ROOT`抑制，没有save-only最终交付。
- 发布阻断事实：两个独立outer都成功执行。PC候选被交付；Android分支成功得到APK并被ContainerRole识别为应保留的内容容器，但其FinalContentCandidate为`NEEDS_USER_SELECTION`、DeliveryUnit却仍为`CANDIDATE`。CLI没有形成选择闭环，task/history仍标`COMPLETED / DELIVERED`，Android唯一run-owned物理结果随后被清理，最终输出只有PC。这是成功独立内容静默不交付及状态误报，登记为`mixed_selected_and_ambiguous_content_silent_nondelivery`。
- 2026-08-19 P0 Fix Verification：task `[本地任务 ID 已脱敏]`经真实CLI完成12个执行节点并同时交付`GameArchive_Output\PC_2`与Android内容根。PC为3094文件/1,416,390,030 bytes并保留10个save；Android为1个完整APK/1,270,709,161 bytes。两边无技术包装目录，ORPHANED_TEMP=0，旧`PC`未覆盖，两个源SHA256与修复前一致，日志/history未发现密码明文，CLI正常返回主菜单。KI-P0-002据此RESOLVED。
- 2026-08-19 Existing Game Root Evidence（`CONTROLLED REAL-SAMPLE COPY`）：从已交付真实PC内容复制3094文件/1,416,390,030 bytes，保留`game.exe`、`game/lib/renpy`和10个真实save。10个save均由ArchiveAnalyzer识别为`ZIP / confidence=1.0`。TaskAnalyzer真实INITIAL_SCAN访问2个目录，以`ROOT_EXECUTABLE + RENPY_GAME_ROOT / HIGH`建立1个`GAME_CONTENT_BOUNDARY`并剪枝；10个save均0初始任务。边界外兄弟`wrapper.zip`仍以ZIP/confidence 1.0被发现，说明剪枝未越界。save副本与来源逐个SHA256一致。
- 2026-08-19 Outer/Inner Evidence（`CONTROLLED REAL-SAMPLE DERIVATIVE`）：复制原始`PC.rar.lz4`后，用项目当前LZ4 v1.10.0确定性解码得到`PC.rar`（1,193,009,102 bytes，SHA256 `[私人样本 SHA-256 已脱敏]`）。该inner是真实outer派生物，不是原始用户目录本来存在的文件。真实CLI Fast Path发现2个输入；`LZ4_DECODED_STREAM_SHA256`读取2,386,018,204 bytes并得到`VERIFIED / HIGH / CONFIRMED_OUTER_CONTAINS_EXISTING_INNER`，选择inner为canonical、suppress但不删除outer。Pipeline只以inner启动，11个节点（1 RAR + 10个新解压内容中的PIPELINE_SCAN save）全部成功；最终只有1个唯一PC content root和1个`GameArchive_Output\PC`。history中10条DeliveryUnit谱系诊断均指向同一PC root，不代表outer重复执行或10份交付。密码尝试1次，ORPHANED_TEMP=0，无密码持久化。
- Evidence Closure完整性：原始`PC.rar.lz4` SHA256 `[私人样本 SHA-256 已脱敏]`，原始Android outer SHA256 `[私人样本 SHA-256 已脱敏]`，前后一致。受控outer/inner前后SHA256亦一致，两文件均保留，最终内容为3094文件/1,416,390,030 bytes并含`game.exe`及10个save。
- Evidence Matrix：Original Real Sample证明PC+Android独立交付、源完整性、无save-only交付和混合交付cleanup安全；Controlled Real-Sample Copy证明Existing Game Root INITIAL_SCAN boundary；Controlled Real-Sample Derivative证明`PC.rar + PC.rar.lz4`强关系与唯一交付。三层正确性均PASS，Test Game 4正式从`NEEDS_VERIFICATION`升级为PASS。
- 关键不变量：save/mod不成为默认初始任务；显式save仍处理；outer/inner只有强哈希验证后才suppress；源SHA256不变。
- 必须回归：INITIAL_SCAN、GameContentClassifier、InputRelationship、Duplicate或Final Content变更时。

## Sample 5 — 测试游戏5

**Status**：`ACTIVE_REGRESSION_SAMPLE`

- 场景：无法仅靠高置信游戏分类交付的单一技术谱系。
- 关键链路：`RAR → ZIP → embedded/disguised → ZIP → Generic Content`。
- 终端结构：`sample_content/`包含补丁目录、控制台代码目录和带`SampleGame.exe/SampleGame_Data`的游戏目录。
- 曾发现问题：4个成功execution nodes生成4个meaningful candidates；系统误认为有4份独立内容，全部`NEEDS_USER_SELECTION`，最终`output_paths=[]`。
- 对应修复：DeliveryUnit按祖先/子孙执行关系折叠技术lineage；单一terminal unit使用`SINGLE_TERMINAL_DELIVERY_UNIT`交付Generic Content。
- 当前结果：桌面存在`GameArchive_Output\sample_content`；已核验记录为209个文件、总大小1,710,573,415 bytes。项目默认runtime history未包含这次独立验证记录，因此具体task_id标记`NEEDS_VERIFICATION`。
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

### 本次 ChatGPT + Codex 唯一代码切片：内嵌扫描诊断保留（合成回归通过）

- Codex 只改动未提交的 `coordinator/embedded_resolver.py` 和 `tests/test_embedded_candidate_resolution.py`：`EMBEDDED_INCOMPLETE` 在限制退出时同时报告扫描范围/停止原因和已处理候选的 offset、最新验证状态（例如 `PASSWORD_REQUIRED` 或 `FAILED`），不写原始工具输出或密码；安全扫描窗口、预算和最终数据 CRC 检查未改变。
- 测试驱动新增 5 条回归：失败优先时 4 条如预期失败、成功对照通过；改动后聚焦 `30/30 PASS`、全量 `322/322 PASS`、无跳过。Codex 的初次 Tcl 环境失败已用仓库内有效 Tcl/Tk 隔离路径重新执行通过；日志 `.vm_gate/sample8_diagnostic_20261102`。
- **实际三条真实样本解压发生在上述诊断小修补之前**；本补丁没有重跑 20+ GB 的真实解压，也不会让没有密码的加密数据自动解开。任何外层 CRC、合成回归或文案修复均不得记为真实完整 E2E PASS。
- Codex 首次治理检查误判了文档中一条 7-Zip 参数形式为敏感密码输出，已仅调整测试证据的文案表述而未修改治理规则。最终在文档修正后，使用 `.build_venv/Scripts/python.exe -B` 实际运行 `-m unittest tests.test_embedded_candidate_resolution -v`（30 PASS、exit 0）、`-m unittest discover -s tests -p test_*.py -v`（322 PASS、零跳过、exit 0）以及 `scripts/verify_project_state.py`（Overall PASS、exit 0）。证据日志为 `.vm_gate/real_samples_final_focused.log`、`.vm_gate/real_samples_final_full.log`、`.vm_gate/real_samples_final_governance.log`。

## 2026-11-02 新真实样本：Sample 7 + 新 Sample 8 两份 RAR（未通过完整 E2E）

**结论：OUTER_RAR_CRC_PASS / REAL_APP_INNER_BLOCKED；不是 FIXED / 完整解压成功。** 本节覆盖新路径 `C:\SampleArchives\样本8`，不是 2026-10-31 已删除的旧 Sample 8。

- 输入核对：Sample 7 `C:\SampleArchives\样本7\sample_group\PC\sample_pc.7z.001` 至 .003 三卷，合计 11,460,839,972 字节；新 Sample 8 的 4,606,279,750 字节 样本8a RAR 和 14,085,986,899 字节 样本8b RAR。所有输入保留，实测前后 SHA-256 一致；新 Sample 8 校验清单见 `.vm_gate/resource8_original_hashes.json`，Sample 7 原清单见 `.vm_gate/sample7_source_sha_before.json`。
- 独立 7-Zip 数据测试：两个新 RAR 均执行 7-Zip 数据完整性测试（禁用交互式密码输入），各 exit 0 / Everything is Ok，均有 1 项 warning（外层实体尺寸较文件长度少 3 字节）；这是**外层 CRC**，不等于隐藏 RAR 或 GameArchiveManager 全流程成功。`.vm_gate/resource8_crc_test.json` 保存 exit/时长。
- 使用当前源码（不是 `dist/0.1.0` EXE）真实执行 `GameArchiveService.execute_task`，参数是三个明确的首层归档文件，配置从项目 `config.json` 读取 `max_archive_size_mb=99999`、`auto_try_password=false`、`save_passwords=false`；`LOCALAPPDATA` 隔离到 `.vm_gate/real_e2e_profile`，未触碰/读取真实密码。操作脚本 `.vm_gate/real_e2e_runner.py`，报告 `.vm_gate/real_e2e_7.json`、`.vm_gate/real_e2e_8a.json`、`.vm_gate/real_e2e_8b.json`。
- **Sample 7**：实际应用运行 0 成功、1 失败，stage `PASSWORD_RECOVERY`，status `PASSWORD_REQUIRED` / error_type `PASSWORD_CANDIDATES_EXHAUSTED`；证明已越过之前的 10 GiB 错误配置拦截，但没有密码，本次不能开始解密和递归验证。
- **Sample 8 小 RAR（8a）**：实际应用外层解压 MP4 成功（1 success），内嵌验证 1 failed，stage `EMBEDDED_VALIDATION` / `EMBEDDED_INCOMPLETE`；内嵌宿主为 4,606,279,439 字节 MP4，512 MiB 前缀内存在结构有效但**尚未数据验证**的 RAR5 加密头，offset `72,684,880`。任务 `FAILED`，虽 `delivery_status=DELIVERED` 且复制外层 MP4，不能当完整 PASS。
- **Sample 8 大 RAR（8b）**：实际应用外层解压 MP4 成功（1 success），内嵌验证 1 failed，stage `EMBEDDED_VALIDATION` / `EMBEDDED_INCOMPLETE`；MP4 为 14,085,986,678 字节，候选 RAR5 加密头 offset `162,836,508`。任务 `FAILED`，已交付的只有外层内容，不能当完整 PASS。两份候选的 `VALID_ENCRYPTED` 仅证实首部结构和 CRC 合法，不证明内层归档实际可解密或数据完整。
- 手工密码交互：使用本机 session-1 Tk 遮盖输入框，对 8a 的已解出 MP4 再试了一次当前源码的手工恢复；窗口实际出现，最终未收到密码提交、没有任何密码尝试，因超时跳过（`USER_SKIPPED_PASSWORD_ARCHIVE` 是程序控制码，并非用户主动确认跳过），报告 `.vm_gate/interactive_inner_8a.json`。未猜测、读取、泄露、写入密码；没有打开自动尝试用户密码库的开关。
- 诊断缺陷：两份实际文件的候选都位于 512 MiB 范围内；但候选验证未通过后，扫描结束写入 `SCAN_LIMIT_REACHED` 会掩盖候选层的密码要求/拒绝原因。Codex 只读审查确认：不能简单将 `VALID_ENCRYPTED` 视为必然可解压；需要保留两类信息并在新测试中覆盖。不得把码 `EMBEDDED_INCOMPLETE` 简化解释成密码错误，也不得在未测试数据前标 FIXED。
- 输出安全：本次运行在 `C:\SampleArchives\样本8` 下新建两个 `*_extracted` 中间目录及 `GameArchive_Output` 下两份外层 MP4 交付副本，合计额外约 37.38 GB；**保留，没有删除或覆盖**。Windows C: 可用空间降到约 42.8 GB，执行资源 7 的再次完整展开前必须先核算更多空间并明确处理这些新生成的重复输出。两个新 RAR 的 SHA256 前后不变，Sample 7 三卷的 SHA256 前后不变；未发现遗留 `.gam_candidate_*` 目录。完整 E2E 的交付 / 内容 CRC / 新 EXE / VM 均 **NOT_VERIFIED**。
- 重新验收条件：由用户通过**本机**密码窗提交对应密码（不在聊天或日志中传输），确认真实内嵌 RAR 完整 7-Zip 数据/CRC，通过 GameArchiveManager 从原输入递归到最终内容并交付，报告 `failed_count=0`、输出清单及哈希、无陌生残留和足够剩余空间；其前一律 `NEEDS_VERIFICATION`。不得绕过原配置中 `auto_try_password=false` 的偏好，也不准擅自清理现有输出。

## Sample 7 — 样本7（PC/AZ 分卷）

**Status**：`NEEDS_VERIFICATION`（2026-10-29；被配置的归档大小上限拦截，尚未完成 PC 分支端到端验证）

- 输入结构：`sample_group/AZ/sample_android.7z.001/.002`；`sample_group/PC/sample_pc.7z.001/.002/.003`。
- 历史记录：任务 `[本地任务 ID 已脱敏]` 与 `[本地任务 ID 已脱敏]` 各报告 3 个归档成功、1 个失败；失败项均为 `sample_pc.7z.001`。任务 `[本地任务 ID 已脱敏]` 在 0.12 秒内以 0 成功、1 失败、1 跳过终止。
- 根因证据：`ArchiveSafetyChecker` 将三卷总大小 `11,460,839,972` bytes 与运行时限制 `10,737,418,240` bytes（10 GiB）比较，故在外部解压工具启动前拒绝，日志 `tool=NONE`。这是大小配额拦截，不是已证明的密码错误、缺卷或归档损坏。
- 配置差异：本机源码目录的本地 `config.json` 设置为 99999 MB，但该次任务实际使用 10240 MB 默认上限，说明运行任务的程序没有使用此源码配置（很可能是另一份打包程序/配置；具体 EXE 路径尚未确认）。
- 处理建议：在**实际运行任务的同一程序**的“设置 → 处理限制”中，将“最大归档大小（MB）”显式设为 `20480` 后保存；随后只选择 `sample_pc.7z.001` 作为输入，避免再次处理已尝试过的 AZ 分支。先确认磁盘有足够空间。
- 安全边界：诊断过程中没有再次启动解压，没有删除/覆盖原始分卷、已有输出或残留目录。前两次历史运行记录交付过 AZ 输出，重试可能产生重复输出目录；不要自动清理它们。
- 待完成：确认实际程序/配置路径；调整当前运行配置后，只处理 PC 首卷并检查 3 个分卷是否齐全；记录最终文件数、总大小、源分卷 SHA256 前后不变、输出交付状态和 ORPHANED_TEMP。未完成前不能标记 PASS。

### 2026-11-02 Sample 7 只读重新核验（实测，不代表端到端 PASS）

- 三个 PC 分卷依然存在，真实总大小 `11,460,839,972` 字节，未发现缺卷；原样的 SHA-256 已在 `docs/CURRENT_STATUS.md` 最新节记录，验证前后均相等。
- 当前源码实际选择的配置（canonical junction 的物理目录 `GameArchiveManager0.1.0/config.json`）设置 `max_archive_size_mb=99999`；在真实 ArchiveInfo 上大小限制 10240 MB 时安全拒绝，在 20480 / 99999 MB 时安全放行且生成可执行计划。这证明**当前源码不再被历史 10 GiB 大小门禁阻挡**，不证明实际解压成功；历史运行使用了哪一个 EXE/配置仍未独立确定。
- 检查旧的 `sample_pc.jpg`：真 JPEG，字节数 `11,460,839,730`，内嵌 RAR5 加密头候选 offset=23332；已有旧的 `sample_pc_embedded.rar` 长度 `11,460,816,398`。只读 `7z l -slt` 会要求密码，已停止进程，没有输入/保存/记录用户密码、没有真正解压或改动已有输出。
- Codex 补充设置界面的生效配置路径、实际大小限制和失效告警，并用精确三卷合计的模拟 stat 大小增加回归。ChatGPT 重跑正常完整 317 tests、GUI/集成 95 tests 和嵌入候选 25 tests 全部 PASS、无跳过，治理 PASS；这些都不是对真实完整交付的证明。旧 EXE 未修改/重建。
- 原始样本状态保持 **SIZE_GATE_VERIFIED / END_TO_END_NEEDS_VERIFICATION**。下一次只用当前源码 GUI 选 PC 首卷，并由用户通过本机密码框输入密码，完整复验递归内容、交付、报告、残留和 SHA256。不得自动删除原档或此前已存在的 `GameArchive_Output`、`*_extracted`。

## Sample 8 — 样本8（RAR → MP4 → embedded encrypted RAR）

**Status**：`OUTPUT_INTEGRITY_VERIFIED / APP_RUN_UNCONFIRMED`（2026-10-31；用户新解出的内层 RAR CRC 通过，输出文件完整性已核验；未找到本次 GameArchiveManager 任务历史）

- 原始输入：`samples/样本8/*.rar`，大小 `6,037,746,994` bytes。原始文件 SHA256：`[私人样本 SHA-256 已脱敏]`。
- 只读 7-Zip 测试：exit 0、`Everything is Ok`；仅警告归档末尾有 3 个额外字节。外层 RAR 没有加密。
- 旧失败运行的 GameArchiveManager 记录：外层 RAR 解出 MP4（`6,037,746,603` bytes，SHA256 `[私人样本 SHA-256 已脱敏]`），随后在 MP4 偏移 `289,052,481` 检测到一个旧副本（`5,748,694,122` bytes，SHA256 `[私人样本 SHA-256 已脱敏]`）。用户提供的密码能解开这个旧副本的目录头，但其数据校验失败。该旧副本不是用户后来成功解出的 RAR。
- 重要纠正：此前诊断选中了旧失败副本（`5,748,694,122` bytes），该副本确实会报校验错误；但它不是用户后来成功解出的那份 RAR。用户新输出中的正确内层 RAR 为 `5,746,925,296` bytes。对这份新 RAR 使用用户提供的密码执行 7-Zip `t`：exit 0，`Everything is Ok`，170 files，Size `5,825,318,514` bytes；仅警告归档末尾有 2 个额外字节（Physical Size `5,746,925,294`、Tail Size `2`）。因此此前把旧副本错误推广为整个样本损坏，是诊断失误。
- 用户新解出的最终目录包含 **168 个 MP4 + 2 个文本文件**，总计 `5,825,318,514` bytes；168 个 MP4 均非零字节，FFprobe **168/168 通过**。MP4 合计 `5,825,315,574` bytes，两个文本文件合计 `2,940` bytes，与 7-Zip 归档清单总大小完全一致。此前 TEMP 的 31,116 bytes 抢救文件属于旧失败副本，与本次成功输出无关。
- 最终输出已移动到 `samples/样本8_已解压`。移动前后均为 170 个文件、`5,825,318,514` bytes。随后按用户此前要求删除了旧 `样本8` 源目录，其中包括原始外层 RAR（`6,037,746,994` bytes）、中间 ZIP/RAR 副本和空 `[空文件夹名已脱敏]` 目录；独立的已验证输出保留。
- 原始外层 RAR 的 SHA256 在清理前与最初记录一致：`[私人样本 SHA-256 已脱敏]`。没有删除已验证输出。
- 归档输出完整性已通过；但没有匹配的 GameArchiveManager 任务历史记录，故不能把本次外部/用户操作记为 GameArchiveManager 自动流程 PASS。后续如要验证应用本身，需使用一份保留的副本重新运行并记录 TaskStatus、CRC、输出和 ORPHANED_TEMP；本次源目录已按用户要求清理，不再作为复测输入。


## Sample 8 失败根因调查（2026-10-31；代码修复尚未实施）

- 原失败任务：`[本地任务 ID 已脱敏]`。history 记录 3 个归档中 2 个成功、1 个失败；失败文件是 MP4 内提取出的旧内嵌 RAR（`5,748,694,122` bytes）；失败阶段 `PASSWORD_RECOVERY`，工具 `SEVEN_ZIP`，错误 `PASSWORD_CANDIDATES_EXHAUSTED`。当次尝试 2 个已保存候选，`manual_password_attempt_count=0`、`manual_password_used=false`，所以用户后来提供的正确密码并未在该次任务中输入。
- 源码机制：`EmbeddedArchiveDetector.find_candidates()` 按文件偏移顺序扫描；一旦某个候选被 `_validate_rar_details()` 标为 `VALID_ENCRYPTED`，就立即返回，不再检查后面的签名。`_validate_rar_details()` 对 RAR5 加密候选只校验首个头部 CRC、header type 和加密字段最小长度，并不验证完整归档是否能被 7-Zip/UnRAR 正常列举或测试。因此，MP4 内容中较早出现的偶然 RAR5 加密头可能被误判为真正内嵌归档。
- 尺寸证据：旧失败 carve 为 `5,748,694,122` bytes；用户后来成功的内嵌 RAR 为 `5,746,925,296` bytes，相差 `1,768,826` bytes。若二者均从 MP4 中某个偏移复制至 EOF，则旧候选比正确候选早 `1,768,826` bytes。旧副本在正确密码下仍有数据校验错误；新副本 CRC 测试通过。
- 结论：**失败的直接表现**是当次任务仅尝试了 2 个错误的已保存密码、未进行人工密码输入；**高度怀疑的程序根因**是嵌入式 RAR 扫描提前接受了较早的假阳性候选，导致 carve 出错误范围。由于用户要求在成功后删除原始样本，当前已没有原始 MP4 可供重扫，故无法把偏移假阳性提升为已实测证明。
- 修复状态：`NOT FIXED`。尚未修改检测器或递归处理逻辑，也尚未增加回归测试。下一步应制作小型合成 MP4/二进制宿主：在真正的可测试 RAR5 之前放入一个头部 CRC 正确、但完整归档无效的 RAR5 加密头；验证检测器不会只选第一个候选，并会继续尝试后续候选。应用层还应在密码候选耗尽后提供人工输入；人工密码失败时不能把当前候选直接等同于整个宿主无效。
- 不得把本次 Sample 8 输出验证记为 GameArchiveManager 自动流程通过；也不得声称上述检测器修复已完成。

## 真实样本使用规则

1. 运行前后计算源归档SHA256；任何变化都是NO-GO。
2. 记录开始/结束时间、TaskStatus、成功/失败/跳过、密码尝试数、Guard、ORPHANED_TEMP和最终输出。
3. 不把真实密码写入本文、测试名、日志、命令行记录或history。
4. 自动测试通过不能替代样本回归。
5. 样本不可访问、输出被人工移动或历史记录缺失时标`NEEDS_VERIFICATION`，不得补写猜测。
