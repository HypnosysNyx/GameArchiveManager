# GameArchiveManager Known Issues

> 当前优先级摘要以 `CURRENT_STATUS.md` 为准。每项必须记录Status、Affected modules、Real sample、Risk、Current workaround和Do not fix by。

## Resolved P0

### KI-P0-002：混合最终候选中的独立内容被静默不交付

- **Issue ID**：`mixed_selected_and_ambiguous_content_silent_nondelivery`
- **Status**：RESOLVED（2026-08-19）。
- **Affected modules**：FinalContentRootResolver、DeliveryUnit状态映射、OutputOrganizer选择回调、ApplicationService交付状态与Cleanup生命周期。
- **Real sample**：测试游戏4，task `6c12337c-1257-4337-a208-cc20430c35c2`。
- **Expected**：两个默认允许处理的独立输入都成功时，高置信游戏根可以自动交付；另一个独立Generic/Content Container结果必须被交付、进入明确的用户选择闭环，或使任务保留为未完成交付状态。未成功交付前不能清理它唯一的run-owned物理结果。
- **Actual**：PC分支被选中并交付；Android分支成功得到APK，FinalContentCandidate为`NEEDS_USER_SELECTION / AMBIGUOUS_INDEPENDENT_CONTENT`，但对应DeliveryUnit仍为`CANDIDATE`。选择回调没有收到该项，任务/history被标为`COMPLETED / DELIVERED`，唯一Android物理输出随后作为run-owned临时目录清理，最终`output_paths`只有PC。
- **Root cause**：FinalContentRootResolver正确产生`NEEDS_USER_SELECTION`，但DeliveryUnitResolver只在全局没有任何已选内容时处理pending unit；PC已选使Android unit停留在`CANDIDATE`。OutputOrganizer callback和ApplicationService状态聚合只读取DeliveryUnit的`NEEDS_USER_SELECTION`，PC单个输出又使任务误报DELIVERED。成功cleanup随后只看到run ownership，不知道该目录仍承载唯一未交付内容。
- **Fix**：DeliveryUnit按独立输入lineage决策；与已选游戏无父子/重复冲突的单一独立内容自动交付。同一lineage内多个竞争根继续复用原selection callback。非交互未决内容返回`COMPLETED_NEEDS_SELECTION`并按最小顶层run-owned边界保留；callback未选项只有在实际调用后才记录`USER_REJECTED_DELIVERY_UNIT`。ApplicationService同时聚合Candidate和DeliveryUnit状态，并在cleanup前保护pending content。
- **Regression evidence**：新增5项生命周期测试；相关16项专项通过；完整219项通过。真实Test Game 4 P0复测task `ce937e11-f0dd-4e60-830e-3dc1d7d5b26c`同时交付`PC_2`与Android内容根，APK完整，ORPHANED_TEMP=0，源SHA256不变，无密码泄漏，旧PC输出未覆盖。
- **Risk after fix**：同一lineage内真正竞争根仍需用户选择；非交互调用会保留run-owned物理结果并明确报告，不会静默清理。当前save PIPELINE_SCAN开销不属于本修复。
- **Current workaround**：无。Test Game 4 Evidence Closure已使用受控真实副本和确定性派生物补齐证据，整体发布签字已PASS。
- **Do not fix by**：不要自动选择所有模糊内容；不要把Android后缀硬编码为删除/跳过；不要关闭cleanup来隐藏状态错误；不要修改Analyzer、Extractor、PasswordRecovery或样本文件；不要把有一个成功输出等价为所有独立输入都已交付。

### KI-P0-001：历史技术目录污染 PasswordCandidate

- **Issue ID**：`password_candidate_history_pollution`
- **Status**：RESOLVED（2026-08-15）。
- **Affected modules**：`scanner/initial_scan_boundary.py`、`scanner/archive_finder.py`、`scanner/scanner.py`、`task/task_analyzer.py`及ApplicationService history注入。
- **Real sample**：测试游戏6。失败运行保留的`*_extracted`、`password_attempt_*`等空技术目录可能在后续分析中成为`FOLDER_NAME`候选；旧验证曾观察候选/尝试数随失败运行增长。
- **Root cause**：ArchiveFinder和Scanner分别遍历；ArchiveFinder的名称裁剪没有成为诊断boundary，Scanner只收到游戏内容边界，导致历史技术空目录重新进入候选。
- **Fix**：从history读取同一任务的run-owned residual paths，以`InitialScanSpaceResolver`生成`TECHNICAL_OUTPUT_BOUNDARY`；ArchiveFinder记录边界，Scanner复用同一精确pruned path集合。
- **Risk after fix**：缺少history ownership证据的遗留同名目录不能安全判定为技术输出，保守视为用户空间；这避免误丢合法候选。
- **Current workaround**：无需删除历史目录。未知legacy目录如需排除，应先建立明确ownership证据，不能按名称猜测。
- **Do not fix by**：不要修改PasswordRecovery算法或PasswordScorer来隐藏来源问题；不要按候选名称武断删除；不要删除历史残留；不要破坏空文件夹作为真实密码线索的现有语义。
- **Regression coverage**：真实空目录正例；GameArchive_Output、history-owned、password attempt、embedded负例；`my_extracted`反例；三次残留增长稳定性；不删除；PIPELINE_SCAN；显式密码API；ApplicationService自定义history注入。

## Resolved P1

### KI-P1-008：NEXT-2后CLI不能直接输入路径

- **Issue ID**：`cli_direct_path_entry_regression`
- **Status**：RESOLVED（2026-08-19）。
- **Affected modules**：`main.py`的CliSessionController导航。
- **Real sample**：不适用；来源为REAL USER EXPERIENCE AFTER NEXT-2。
- **Root cause**：`run_session`首个prompt只解析0～4菜单命令，合法路径在进入`run_new_task/_collect_task_paths`前被判为invalid menu input。
- **Fix**：首屏改为Fast Path，按Q/M/合法existing path顺序解析；合法文件或目录直接复用统一`_start_task_from_paths`预览、确认、执行链。完整菜单由M进入，菜单“新建任务”和Fast Path不维护两套业务逻辑；兼容数字快捷方式只在输入不是现有路径时生效。
- **Regression coverage**：首个目录、archive文件、APK显式文件、带空格拖放引号、M菜单、Q退出、空输入、无效路径、成功/失败/取消后继续、重复路径、SessionPasswordStore、Task隔离、平台设置、Content Container和KI-P0-002均通过。完整224项通过。
- **Do not regress by**：Persistent session不能在每个任务前强制菜单导航；路径输入是主交互，菜单是辅助入口。

### KI-P1-004：自动密码候选耗尽后的人工恢复闭环

- **Issue ID**：`manual_password_recovery_after_exhaustion`
- **Status**：RESOLVED（2026-08-15）。
- **Affected modules**：CLI安全输入、ApplicationService、Task/Pipeline编排、ExtractionCoordinator、Report/History安全摘要。
- **Root cause**：自动候选耗尽状态能够完整传播，但CLI只在任务终止后打印报告，没有在Coordinator仍持有失败`active_plan`时安全交还控制权。
- **Fix**：新增UI无关的人工恢复请求/响应协议；CLI 提供 I/S/C（2026-08-24 起密码默认可见输入，不再用 `getpass`）；Coordinator仅重试当前失败计划。支持INPUT、SKIP_ARCHIVE、CANCEL_TASK；非交互调用保持原结构化失败。
- **Composite/split evidence**：LZ4→RAR只执行一次outer并重试inner；分卷始终使用首卷入口，不分别执行后续卷。
- **Security**：密码不进入日志、report、history、stdout或对象repr；成功密码仅进入进程内`SessionPasswordStore`，错误密码不保存。
- **Do not fix by**：不要把`input()`放入业务层；不要持久化明文密码；不要在人工重试时重跑整个Task或已成功Composite outer。
- **Regression coverage**：10项专项测试覆盖auto success、manual success、wrong→correct、skip、cancel、Composite、split、non-interactive、泄漏、getpass和源SHA256。

### KI-P1-005：平台过滤被普通路径中的 `az` 子串误触发

- **Issue ID**：`platform_filter_absolute_path_az_collision`
- **Status**：RESOLVED（2026-08-15）。
- **Affected modules**：`rules/platform_rules.py`、`rules/platform_filter.py`、`scanner/scanner.py`、`pipeline/extraction_runner.py`。
- **Real sample**：完整回归曾因随机临时父目录名`tmpzppkazcw`命中宽泛`az`子串而偶发失败；确定性fixture覆盖`tmp_az_random`和`az_user`父组件。
- **Root cause**：INITIAL_SCAN对内容组件使用任意`az`子串；PIPELINE_SCAN还遍历完整绝对路径的全部组件，使用户名和临时父目录成为高影响suppress证据。
- **Fix**：AZ只接受独立ASCII token，支持`AZ`、`[AZ]`、`AZ版`、`AZ_`、`_AZ`、`AZ-xxx`；拒绝`crazy/amazing/blazer/gazette`。Pipeline调用方传入内容根，过滤器只检查其相对组件；无内容根时只把归档文件名当作安全证据。
- **Risk after fix**：没有边界的自定义连写形式不会再作为AZ标签；这是为避免弱子串导致用户内容被静默跳过而采用的保守语义。
- **Current workaround**：无。需要新增AZ命名形式时，必须先以明确token结构和正反例扩展共享规则。
- **Do not fix by**：不要恢复任意substring；不要扫描无关绝对父路径；不要为了兼容未知命名而降低suppress证据门槛。
- **Regression coverage**：12项确定性测试覆盖大小写、既有标签形式、普通英文反例、父路径/用户名、Android/安卓、INITIAL_SCAN、PIPELINE_SCAN、显式输入和结构化skip reason。

### KI-P1-006：APK 作为 ZIP-based Content Container 会进入递归解包

- **Issue ID**：`apk_content_container_recursive_unpack`
- **Status**：RESOLVED（2026-08-15）。
- **Affected modules**：ArchiveAnalyzer、ArchiveFinder、INITIAL_SCAN、PIPELINE_SCAN、ExecutionStrategy 和 Final Content 语义边界。
- **Deterministic evidence**：最小 `sample.apk` 内含 `AndroidManifest.xml` 和 `classes.dex`。ArchiveAnalyzer 返回 `real_format=ZIP`、`extension=.apk`、`confidence=1.0`；INITIAL_SCAN 和 PIPELINE_SCAN 均发现它；受控 Pipeline 执行记录显示它会成为 depth=1 的执行节点。
- **Root cause**：当前只有“真实归档格式”判断，没有通用 `ARCHIVE_WRAPPER` / `CONTENT_CONTAINER` 产品语义。ZIP magic 识别本身是正确的，但“是ZIP”被直接等价为“应继续解包”。
- **Fix**：新增 `rules/container_policy.py`。ArchiveFinder 在 Analyzer 确认真实归档后、创建自动任务前统一判定 `ARCHIVE_WRAPPER/CONTENT_CONTAINER/AMBIGUOUS`。ZIP 结构的 APK/DOCX/XLSX/PPTX/EPUB/JAR 自动保留；显式文件输入优先并可解包。
- **Risk after fix**：列表只包含当前有明确产品语义的第一批类型。未知 ZIP-based 格式仍沿用旧行为，避免在证据不足时扩大 suppression。`.save` 不在全局列表中，继续依赖 Game Content Boundary。
- **Do not fix by**：不要降低 ZIP 文件头识别可靠性；不要一次加入几十个后缀黑名单；不要破坏 JPG/MP4/TXT 伪装 ZIP 和 PIPELINE_SCAN 递归归档的既有正确性。
- **Regression coverage**：Analyzer 仍报 ZIP；INITIAL_SCAN/PIPELINE_SCAN 保留；显式 APK override；源字节不变；Office/EPUB/JAR 参数化测试；普通 nested ZIP、`.bin` 伪装 ZIP、JPEG embedded、Ren'Py save 边界和 DeliveryUnit 交付回归；Report/History诊断。

## P1

### KI-P1-009：单独 `.part01.rar` / `.part1.rar` 会进入 Extractor

- **Issue ID**：`lone_rar_part_volume_reaches_extractor`
- **Status**：CODE FIXED（2026-08-24）；Clean Windows 11 VM 复测为 `NEEDS_VERIFICATION`。
- **Affected modules**：`analyzer/volume_detector.py`（`_part_rar_set`）。
- **Real sample**：干净 Win11 VM 烟测夹具 `sample.part01.rar`（缺 `part02`）曾 FAILED 于 EXTRACTING/`SEVEN_ZIP`，无 `VOLUME_DETECTION`。
- **Expected**：与 `.7z.001` 相同，缺第二卷时 `can_execute=False`，失败阶段 `VOLUME_DETECTION`，`MISSING_VOLUME`，不调用 Extractor。
- **Root cause**：`.001` 在只有第一卷时强制补 `.002`；`.partN.rar` 的缺口只计算 `1..max(index)`，单独 part1/part01 的 missing 为空。
- **Fix**：`max(indexed)==1` 时补下一卷（保留现有宽度：`part2` 或 `part02`）。完整 `part01+part02` 仍可执行。
- **Do not fix by**：不要按扩展名猜测；不要把普通 `name.rar` 当成分卷；不要为过报告放宽 7z 缺卷规则。
- **Regression coverage**：`part01` 缺卷不进 Extractor；`part1` 宽度匹配 `part2`；完整 `part01+part02` 可执行；既有 RAR/7z/zip 分卷分组；ApplicationService 报告 `VOLUME_DETECTION`/`MISSING_VOLUME`。完整 228 项通过。
- **Remaining**：桌面 8/22 旧包未覆盖。Win10 可选未测。当前 RC2 已验证此缺卷修复，整包 Win11 门禁已完成。

### KI-P1-001：干净 Windows VM 最终门禁

- **Status**：RESOLVED for current RC2 on clean Windows 11（2026-08-28）；Windows 10 仍 OPTIONAL / NOT VERIFIED。
- **Affected modules**：RC构建、runtime paths、ToolManager、配置、日志/history。
- **Real sample**：测试游戏1～6中的可合法复制测试集合；RC 烟测夹具见 `.vm_gate` 记录。
- **Win11 evidence**：当前 RC2 EXE `67DF840B…`（ZIP `BA3A9ADD…`）的清单 1–13、15–17 见 `../rc2_smoke_codex.md`；清单 14 已在 `Win11-Sandbox` GUI 会话中向 EXTRACTING、SCANNING、VALIDATING 三阶段发送真实 Ctrl+C 扫描码，应用均报告 `KeyboardInterrupt`、保留 `ORPHANED_TEMP`，源哈希不变且随后重跑成功，见 `../rc2_item14_codex.md`。旧 EXE `9BFDE4CE…` 与 `F5F2DD82…` 不作为当前门禁替代证据。
- **Artifact note**：被测 ZIP 内附带的旧 Markdown 仍写有旧 EXE 哈希；实际 ZIP/EXE 哈希已由宿主 staging、VM 和三个字节一致的 ZIP 副本交叉确认。原始 ZIP 保持不变作为证据，源码权威文档已纠错。若以后重新打包，必须发布新 ZIP 哈希并确认 EXE 仍为 `67DF840B…`，不得把文档更新包装成原 ZIP 未变化。
- **Remaining**：Win10 可选未测。桌面 8/22 旧包未覆盖。正式 Release 仍需单独完成发布清单和仓库所有者批准。
- **Do not fix by**：不要因为 Win11 GO 就把 `BUILD_TYPE` 改成正式 Release；不要捆绑来源或许可未确认的外部工具。

### KI-P1-002：旧RC文档的历史基线已过时

- **Status**：OPEN/DOCUMENTATION HISTORY。
- **Affected modules**：`RELEASE_CANDIDATE_REPORT.md`、`RC_BUILD_NOTES.md`。
- **Real sample**：不适用。
- **Risk**：新接手者可能误认为当前仍是Development或只有103/107项测试。
- **Current workaround**：以`CURRENT_STATUS.md`、`project_state.json`和当前实测为准；当前是0.1.0 Release Candidate、234项测试。
- **Do not fix by**：不要静默改写历史报告使其看起来当时就是当前状态；应保留历史并明确时间点。

### KI-P1-003：测试游戏4发布签字前需要重新真实回归

- **Status**：RESOLVED（2026-08-19 Evidence Closure）。
- **Affected modules**：INITIAL_SCAN、InputRelationship、Final Content。
- **Real sample**：测试游戏4。
- **2026-08-19 evidence**：真实CLI任务COMPLETED并交付唯一`GameArchive_Output\PC`；最终内容、源SHA256、cleanup、密码泄漏和CLI会话均通过核验。10个真实ZIP save不是INITIAL_SCAN候选，也未成为save-only最终交付。
- **Resolution evidence**：在项目外受控工作区严格区分Original Real Sample、Controlled Real-Sample Copy和Controlled Real-Sample Derivative。真实PC交付副本中10个ZIP save被`HIGH / GAME_CONTENT_BOUNDARY`剪枝，兄弟wrapper仍被发现。真实outer确定性解码的inner与outer并存时，流式SHA256强验证通过，只执行canonical inner并只交付1份PC内容。源和派生输入前后哈希不变，ORPHANED_TEMP=0，无密码泄漏。
- **Remaining risk**：PIPELINE_SCAN仍会执行新解压游戏内的真实ZIP save；这是已知诊断/性能形态，本次没有顺手优化，且未导致save-only交付或outer重复执行。
- **Do not fix by**：不要根据旧输出名或文件名推断成功；不要重新创建伪造结果目录。

### KI-P1-007：NEXT-2后CLI启动延迟体验退化

- **Issue ID**：`cli_startup_latency_regression`
- **Status**：NEEDS_REAL_ENVIRONMENT_VERIFICATION。
- **Affected modules**：CLI启动编排、GameArchiveService初始化、ToolManager工具发现与版本验证。
- **Real sample**：不适用；真实用户反馈启动明显变慢。
- **Read-only timing**：修改前first prompt约`0.2087s`，但该prompt不能接收路径，T2还依赖一次人工菜单选择。Fast Path后fresh process测得T1=`0.1814s`、T2=`0.1814s`、有效路径提交到TaskAnalyzer开始T3=`0.000128s`；BAT启动并立即Q干净退出共`0.3358s`且无额外pause。分离测量中ToolManager发现/版本验证约`0.1236s`，Settings约`0.0003s`，HistoryStorage构造约`0.00001s`。
- **Risk**：外部进程版本查询在冷启动、杀毒扫描或慢磁盘环境可能放大首次提示延迟；当前开发机绝对延迟较小，不能直接外推用户机器。
- **Current workaround**：交互导航延迟已由Fast Path解决；当前开发机无法复现严重计算延迟。保留本P1等待真实用户环境或Clean Windows 11 VM测量冷启动。
- **Do not fix by**：不要为几十毫秒无证据重构GameArchiveService；不要删除工具验证；如未来lazy-load，必须保证Session只发现一次且任务前工具缺失仍结构化可解释。

## P2

### KI-P2-001：低置信多个Generic Content根的产品语义仍有限

- **Status**：OPEN/LIMITED UX。
- **Affected modules**：DeliveryUnit、CLI selection、Report。
- **Real sample**：测试游戏6提供多个高置信根的选择闭环；低置信多根仍缺少丰富真实样本。
- **Risk**：用户需要理解CLI候选才能避免遗漏；非交互调用方可能得到`COMPLETED_NEEDS_SELECTION`。
- **Current workaround**：保守标记`NEEDS_USER_SELECTION`，不自动只选最大/最深/带EXE的目录。
- **Do not fix by**：不要使用“单目录无限拍平”“最大目录获胜”或“最后leaf获胜”。

### KI-P2-002：部分失败原因仍使用通用枚举

- **Status**：OPEN。
- **Affected modules**：Report/failure normalization。
- **Real sample**：磁盘空间安全模拟。
- **Risk**：磁盘满或写入失败可能归类为通用`FAILED/EXTRACTION`，用户诊断精度有限。
- **Current workaround**：查看normalized reason和脱敏日志。
- **Do not fix by**：不要保存完整敏感stderr；不要把创建失败误报为成功。

### KI-P2-003：CLI Session Loop尚未设计（已解决）

- **Issue ID**：`cli_session_loop`
- **Status**：RESOLVED（2026-08-15）。
- **Affected modules**：`main.py`、`start_game_archive_manager.bat`及CLI/session回归测试。
- **Fix**：新增显式`CliSessionController`，单一`GameArchiveService`在主菜单生命周期内复用；完成、失败、CANCELLED或需选择后均返回菜单。
- **Isolation evidence**：连续成功、失败→成功、cancel→成功、task_id/history独立、Runtime ownership独立、task folder candidate隔离、Settings复用、Content Container复用和session password跨任务均有回归。
- **Security**：仅已验证成功密码在当前进程内复用；错误密码、任务空文件夹候选、cancel flag、Pipeline/Guard和Runtime ownership不跨任务。
- **Do not fix by**：不要跨任务复用Task、Pipeline/runtime state、TaskReport或task-level candidates。

## LIMITATION

### KI-L-001：RAR/7Z解压前内容预检查能力有限

- **Status**：KNOWN LIMITATION。
- **Affected modules**：ArchiveContentInspector、Security。
- **Real sample**：所有真实RAR/7Z流程，包括测试游戏3；当前依赖执行后检查补充。
- **Risk**：无法像ZIP一样在执行前可靠获得全部内部路径、数量和展开大小。
- **Current workaround**：归档大小限制、外部工具超时、解压后安全检查、PipelineGuard。
- **Do not fix by**：不要假造“已检查安全”；不要取消解压后检查。

### KI-L-002：强杀/断电时无法保证写入ORPHANED_TEMP

- **Status**：KNOWN LIMITATION。
- **Affected modules**：RuntimeTracker、ApplicationService、Cleanup。
- **Real sample**：没有安全方式自动制造断电样本；超时/异常保留行为有自动测试，强杀场景为`NEEDS_VERIFICATION`。
- **Risk**：进程没有执行finally/持久化的机会。
- **Current workaround**：下一次运行不扫描历史技术输出；通过显式CleanupManager处理已确认目录。
- **Do not fix by**：不要启动时按名称自动删除未知目录。

### KI-L-003：当前没有GUI

- **Status**：EXPECTED FOR 0.1.0。
- **Affected modules**：`ui/`为空包。
- **Real sample**：测试游戏6通过现有CLI人工选择PC/VR，证明闭环可用但不够直观。
- **Risk**：多候选和工具诊断对普通用户不够直观。
- **Current workaround**：CLI预览、一次确认、选择回调、Report和日志。
- **Do not fix by**：RC阶段不要直接开始大规模GUI开发。

### KI-L-004：工作区没有可用Git历史

- **Status**：ENVIRONMENT LIMITATION。
- **Affected modules**：整个项目维护流程。
- **Real sample**：当前工作区执行`git status`返回“not a git repository”。
- **Risk**：无法依赖git diff/status确认全部历史变更。
- **Current workaround**：修改前后用文件清单、时间、测试和小范围patch核验；重要知识写入docs。
- **Do not fix by**：不要假设`.git`名称意味着可恢复历史。

### KI-L-005：密码持久化相关Settings仍是legacy no-op

- **Status**：KNOWN LIMITATION / NOT IMPLEMENTED。
- **Affected modules**：`config/settings.py`中的`save_passwords`、`auto_try_password`。
- **Risk**：调用者可能从字段名称误以为项目存在加密的持久密码库或会自动加载历史密码。
- **Current behavior**：项目没有持久密码数据库；ConfigLoader不加载这两个字段；人工成功密码只进入进程内SessionPasswordStore。
- **Do not fix by**：不要直接把密码写入JSON/history/log；未来若实现必须单独设计用户同意、加密、生命周期和迁移方案。

## FUTURE

- ContentRootClassifier通用化，详见`PROJECT_VISION.md`和`ROADMAP.md`。
- 更丰富内容类型与DEEP模式。
- 用户确认后的官方工具来源引导；绝不静默下载/安装。

## Resolved / mitigated history

- **Embedded大宿主误拒绝**：已用流式`max_scan_bytes`修复，并支持CRC正确的RAR5 encrypted type 4。
- **Archive leaf误当最终内容**：已引入Final Content与DeliveryUnit语义。
- **技术execution candidate数量误当内容数量**：测试游戏5已由DeliveryUnit/Generic Content修复。
- **Composite失败不可解释**：已持久化outer/inner stage details、最终状态和normalized reason。
- **测试游戏6内容恢复**：最新真实任务已COMPLETED并由用户选择交付PC/VR。
- **password_candidate_history_pollution**：已通过共享INITIAL_SCAN技术边界解决；历史记录保留在KI-P0-001。
