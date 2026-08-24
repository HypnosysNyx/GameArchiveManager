# GameArchiveManager Technical Decisions

> 本文记录已经确认的重要决策，防止未来开发者或 AI 在“优化”时重新引入真实发生过的缺陷。每项包含 Decision、Context、Reason、Rejected alternatives 和 Consequences。

## D-001：不相信扩展名

**Decision**：真实格式由文件头和结构验证决定，扩展名只作为弱提示。

**Context**：真实样本出现过 JPG 实际 ZIP、JPEG 后嵌入 RAR、`.save` 实际 ZIP、MP4/PDF 等伪装扩展名。

**Reason**：发布者命名、伪装和多层包装会让扩展名与真实格式不一致。

**Rejected alternatives**：只扫描 `.zip/.rar/.7z/.lz4`；直接按后缀选择工具。

**Consequences**：ArchiveAnalyzer必须保留文件头识别；Embedded候选还必须通过归档结构验证，不能只靠签名字节。

## D-002：Archive leaf 不等于 final content

**Decision**：Pipeline叶节点只是执行图事实，不直接代表最终用户内容。

**Context**：测试游戏4曾把完整 Ren'Py 游戏内部真实 ZIP 存档分支视作最终结果。

**Reason**：归档叶节点可以是存档、补丁、附件或技术支线。

**Rejected alternatives**：所有成功leaf均复制；最后一个leaf自动获胜；最大目录获胜。

**Consequences**：最终交付必须经过 Content Root、执行谱系、DeliveryUnit和重复内容判断。

## D-003：EXE 不等于 game root

**Decision**：EXE 是强信号之一，不是充分或必要条件。

**Context**：游戏可能使用 Ren'Py/Unity/Unreal、脚本、JAR、HTML、模拟器或数据包；普通软件和工具也有EXE。

**Reason**：单一EXE规则会同时产生误判和漏判。

**Rejected alternatives**：找到EXE即选根；没有EXE即不交付。

**Consequences**：`GameContentClassifier`使用组合证据；无法识别为游戏仍可能成为 Generic Content。

## D-004：清理必须基于 Runtime ownership

**Decision**：只有当前运行明确记录为owned且通过CleanupManager安全验证的目录才能清理。

**Context**：`*_extracted`等名称可能是用户目录或历史未知结果；中断时目录可能包含唯一可恢复数据。

**Reason**：名称模式不是所有权证据。

**Rejected alternatives**：按`*_extracted`、`password_attempt_*`批量删除；成功后删除所有空目录。

**Consequences**：超时、取消和异常默认保留并记录ORPHANED_TEMP；未知历史目录不得自动清理。

## D-005：不确定时保留

**Decision**：关系或重复验证失败时保守执行/保留，不武断 suppress。

**Context**：误重复会浪费空间，但误抑制可能丢失用户唯一内容。

**Reason**：数据保全优先于减少重复。

**Rejected alternatives**：按名称、大小或快速manifest直接去重。

**Consequences**：Input relationship验证失败时两者执行；Duplicate强验证失败时两份都保留；诊断需说明原因。

## D-006：输入关系去重必须强验证

**Decision**：`PC.rar.lz4`和`PC.rar`只有在outer解码字节流SHA256与existing inner完整SHA256相同时才可确认并抑制冗余wrapper。

**Context**：测试游戏4出现outer wrapper与已存在inner被重复执行并交付两份相同内容。

**Reason**：stem和container_chain只能产生possible pair，不能证明内容相同。

**Rejected alternatives**：相同stem即去重；最终目录名相同即去重。

**Consequences**：采用cheap filter→stream decode/hash→confirm；显式outer输入和process-all意图仍优先。

## D-007：INITIAL_SCAN 与 PIPELINE_SCAN 语义不同

**Decision**：INITIAL_SCAN寻找用户待处理输入；PIPELINE_SCAN发现本次解压产生的后续归档。

**Context**：扫描完整游戏根时，save/mod内部可能有数百个真实ZIP；但新解压输出中的嵌套归档又必须继续处理。

**Reason**：两种扫描处于不同信任边界和产品阶段。

**Rejected alternatives**：所有扫描统一全目录递归；所有扫描统一只看顶层。

**Consequences**：INITIAL_SCAN使用内容边界和历史输出排除；PIPELINE_SCAN保持现有递归发现；显式归档覆盖边界。

## D-008：高置信游戏内容形成 INITIAL_SCAN 边界

**Decision**：完整游戏根内部的save/mod/archive默认不成为独立初始任务。

**Context**：测试游戏4的Ren'Py存档是真ZIP，曾产生10个额外初始任务。

**Reason**：它们属于已有完整用户内容，不是下载目录中的待解压输入。

**Rejected alternatives**：禁止`.save`；只扫描固定层级。

**Consequences**：使用共享GameContentClassifier组合信号；模糊目录不武断裁剪；记录boundary诊断。

## D-009：Generic Content 是有效交付类型

**Decision**：无法达到高置信游戏评分不代表不能交付。

**Context**：测试游戏5的整个技术链成功，但多个execution candidate被误当多个独立内容，导致`output_paths=[]`。

**Reason**：用户明确要求解压的单一终端内容单元即使不是已知游戏引擎，也有交付价值。

**Rejected alternatives**：只有HIGH game才交付；任何单目录无限拍平。

**Consequences**：单一明确terminal DeliveryUnit可分类为GENERIC_CONTENT并交付；多独立根仍需用户选择。

## D-010：技术执行树与用户 DeliveryUnit 分离

**Decision**：execution node数量不等于独立用户内容单元数量。

**Context**：测试游戏5的RAR→ZIP→embedded→ZIP是4个执行节点，但只有1条技术谱系和1个终端交付单元。

**Reason**：中间节点是恢复过程证据，不应都成为最终内容候选。

**Rejected alternatives**：每个成功节点产生一个最终候选；只选择最深节点。

**Consequences**：DeliveryUnit按archive/parent/depth和Runtime ownership折叠lineage，同时保留完整执行诊断。

## D-011：自动测试通过不是RC唯一依据

**Decision**：RC判断必须同时包含自动测试、真实文件系统样本、安全不变量和干净VM。

**Context**：多项问题只在5GB宿主、真实RAR5、只读文件、历史残留和重复运行中出现。

**Reason**：mock和小临时文件无法覆盖Windows工具、权限、磁盘与长期状态。

**Rejected alternatives**：只报告测试总数；为了全绿修改失败断言。

**Consequences**：真实样本记录进入`REAL_WORLD_TESTS.md`；VM未GO前不标正式Release。

## D-012：0.1.0 Core Freeze

**Decision**：RC阶段不新增大功能，不重构核心识别/递归/解压/密码恢复逻辑，除非真实测试证明明确bug。

**Context**：当前核心链已复杂，广泛变更会扩大回归面并使真实问题难以定位。

**Reason**：发布候选阶段的目标是稳定和可审计，而不是功能扩张。

**Rejected alternatives**：借单个bug全面改造架构；立即开发GUI或新格式。

**Consequences**：修改前先只读定位；每个bug需要正例、反例、交互例和相关真实样本回归。

## D-013：密码候选发现共享INITIAL_SCAN用户空间边界

**Decision**：INITIAL_SCAN归档发现与空文件夹密码候选发现必须共享同一批精确boundary paths；历史技术输出依据持久化Runtime ownership/residual路径识别，而不是依据目录名。

**Context**：ArchiveFinder曾按名称裁剪`*_extracted`等目录，但没有把裁剪结果传给Scanner；Scanner第二次独立遍历后把历史技术空目录收集为密码候选，测试游戏6候选数曾随失败运行增长。

**Reason**：同一INITIAL_SCAN存在两套不同边界会产生rule drift；名称既不能证明技术ownership，也会误伤用户真实`my_extracted`目录。

**Rejected alternatives**：降低最大密码尝试数；删除历史输出；为Scanner复制`*_extracted/password_attempt`字符串黑名单；修改PasswordScorer掩盖低质量来源。

**Consequences**：history中的run-owned residual roots和固定最终输出根形成`TECHNICAL_OUTPUT_BOUNDARY`诊断；ArchiveFinder和Scanner共同裁剪。PIPELINE_SCAN继续发现新归档，显式用户密码API不受影响；没有history ownership证据的同名用户目录默认保留。

## D-014：高影响平台过滤只接受内容范围内的明确 token

**Decision**：AZ过滤必须使用内容相关相对路径组件中的独立ASCII token，不能使用任意绝对路径子串。Android/安卓保持既有名称包含语义。

**Context**：随机临时父目录名包含`az`时，旧Pipeline过滤会在完整绝对路径中误命中；INITIAL_SCAN也会把`crazy`、`amazing_game`等普通内容名称标为忽略。

**Reason**：平台过滤会直接suppress用户输入，弱字符串信号不能单独触发高影响操作。现有测试证明`AZ_patch`属于既有标签形式，因此规则不能简单收窄为仅等于`AZ`。

**Rejected alternatives**：继续使用`"az" in path.lower()`；仅匹配完整组件`AZ`；根据用户名或临时父目录推断内容平台；为修复AZ同时改变Android或显式输入语义。

**Consequences**：支持`AZ`、`[AZ]`、`AZ版`、`AZ_`、`_AZ`、`AZ-xxx`，拒绝英文单词内部的`az`。PIPELINE_SCAN必须传内容根并只检查相对组件；缺少根时只检查归档文件名。显式归档输入继续沿用现有override语义。

## D-015：自动候选耗尽不是交互环境中的必然终止状态

**Decision**：非交互业务调用继续返回`PASSWORD_CANDIDATES_EXHAUSTED`；交互CLI可以通过可选回调提供新密码、跳过当前归档或取消任务。人工重试必须发生在Coordinator仍持有当前失败`active_plan`时。

**Context**：旧CLI只能在Task失败后打印密码耗尽结果。Composite inner失败时若从任务入口重跑，会重复执行LZ4 outer并产生额外技术目录。

**Reason**：安全的显式用户输入可以补充自动发现无法获得的信息，但UI输入不应侵入可复用业务层。

**Rejected alternatives**：把`input()`放进PasswordRecovery；失败后重启整个Task；默认持久化用户密码；把用户取消记录为WRONG_PASSWORD。

**Consequences**：CLI默认用可见`input()`读人工密码，以便中文输入法直接使用；明文仍不写入日志、history、report。业务层只处理结构化请求/响应。密码默认仅存在内存，只有实际成功后才进入SessionPasswordStore。人工尝试有100次安全上限，每次继续均需用户显式动作。

## D-016：平台过滤默认为 opt-in

**Decision**：`ignore_android=False`、`ignore_AZ=False`是面向未知用户的发布默认值。Android/安卓/AZ 默认保留；只有用户在 Settings 或 `config.json` 中明确设置 `true` 才过滤。

**Context**：旧默认值来自项目早期的个人整理习惯，而不是对普通用户普遍有效的产品语义。Android APK 通常不大，不存在足以支持默认 suppression 的通用证据。

**Reason**：高影响的不执行规则必须由用户偏好触发。长期原则是 `Default = preserve`，`Optional user preference = suppress`。

**Rejected alternatives**：继续以开发者个人偏好默认丢弃 Android/AZ；删除平台过滤功能；强制覆盖用户已有的显式 `true` 配置。

**Consequences**：ConfigLoader 缺少字段时回退到新的 `false` 默认；已有 JSON 中的显式 `true` 仍然优先。INITIAL_SCAN 和 PIPELINE_SCAN 共享同一 Settings 语义，AZ 仍使用已验证的 token matching。

## D-017：真实归档格式不等于自动解包意图

**Decision**：ArchiveAnalyzer 只回答“这个文件技术上是什么”；`ContainerRolePolicy` 回答“自动发现时是否应继续拆解”。`REAL_FORMAT == ZIP` 不等于 `AUTO_EXTRACT == YES`。

**Context**：APK、Office Open XML、EPUB 和 JAR 的底层都可以是合法 ZIP，但文件本身是用户内容。旧 ArchiveFinder 把 Analyzer 确认的所有 ZIP 直接升级为自动任务。

**Reason**：保留文件头事实的正确性，同时避免把已经可用的内容容器拆成技术内部文件。显式用户意图优先于自动保留策略。

**Rejected alternatives**：让 Analyzer 对 `.apk` 伪报 `UNKNOWN`；禁止所有非标准后缀；全局禁止 `.save`；改写 EmbeddedArchiveDetector；为每种扫描模式复制一套规则。

**Consequences**：INITIAL_SCAN 和 PIPELINE_SCAN 在 ArchiveFinder 内共享同一策略。自动发现的 `.apk/.docx/.xlsx/.pptx/.epub/.jar` 且真实格式为 ZIP 时标记 `CONTENT_CONTAINER` 并保留；显式文件输入标记 `ARCHIVE_WRAPPER/EXPLICIT_USER_INPUT` 并可执行。未知但强验证的归档沿用原行为。

## D-018：Application lifetime 不等于 Task lifetime

**Decision**：CLI一次启动只创建一个`GameArchiveService`。Settings、ToolManager、HistoryStorage、ApplicationService、SessionPasswordStore和CLI controller是session-scoped；Task、TaskAnalysisResult、Pipeline/queue/Guard、RuntimeTracker/cleanup ownership、TaskReport、task password candidates和cancel/progress/output planning state是task-scoped。

**Reason**：用户需要在一个程序进程中连续处理任务，同时不能让上一任务的失败、取消、候选、Guard计数或Runtime ownership污染下一任务。

**Password rule**：只有实际验证成功的密码可以`SESSION_MEMORY`身份在当前进程中复用。错误密码不进入store；task-level folder candidates不跨任务；不写入磁盘、report、history或log。

**Consequences**：CLI只负责导航、预览、确认、启动和展示，业务继续通过ApplicationService。正常退出BAT不再二次`pause`；只在Python返回非零错误码时暂停窗口。

## D-019：交付决策按独立输入lineage聚合，cleanup服从用户内容生命周期

**Decision**：全局已有selected内容不能遮蔽另一独立输入的合法DeliveryUnit。与已选结果不存在父子或重复冲突、且该lineage只有一个有效终端内容时自动交付；同一lineage内多个竞争根继续进入现有selection callback。任何未决唯一内容在成功交付、用户明确拒绝或可恢复保留之前不得cleanup。

**Context**：Test Game 4中PC已选导致独立Android FinalContentCandidate为`NEEDS_USER_SELECTION`、DeliveryUnit却停留`CANDIDATE`；callback未触发，任务误报DELIVERED，run-owned Android唯一物理结果被正常cleanup。

**Reason**：`Execution Node != DeliveryUnit`，同时`one selected output != all inputs delivered`。Runtime ownership只能证明目录由本次创建，不能证明其中不再承载用户内容。选择状态必须在Candidate、DeliveryUnit、Report、TaskStatus和cleanup之间形成同一生命周期。

**Rejected alternatives**：修改CleanupManager扩大永久保留；把Android硬编码为自动选择；只要有一个output就标DELIVERED；把callback未返回的项当作隐式拒绝；对所有独立低置信多根无条件自动选择。

**Consequences**：mixed selected+independent single unit自动全部交付；真正竞争根由用户选择。非交互未决状态为`COMPLETED_NEEDS_SELECTION`，承载路径记录`ORPHANED_TEMP: DELIVERY_PENDING`；只有callback实际执行后未选项才记为`USER_REJECTED_DELIVERY_UNIT`。Copy失败继续保留本次run-owned树。

## D-020：CLI最高频动作使用Fast Path，菜单为辅助入口

**Decision**：持久CLI Session的首个prompt直接接受existing文件或目录路径；`M`进入完整菜单，`Q`退出。Fast Path和菜单批量入口必须共享同一预览、确认和执行函数，不能形成两套业务流程。

**Context**：NEXT-2 Session Loop解决了连续任务生命周期，但把`主菜单 → 1 → 路径`变成每个任务的强制导航，真实用户粘贴/拖入路径的高频流程退化。

**Reason**：The primary CLI interaction should optimize the highest-frequency action。对GameArchiveManager而言path input是primary，menu navigation是secondary；persistent application session不能为每个任务增加强制导航。

**Rejected alternatives**：删除Session Loop；绕过ApplicationService直接执行；为Fast Path复制一套任务逻辑；未经证据进行复杂lazy ToolManager重构；取消执行前确认。

**Consequences**：首屏按空白、Q/M、existing path、兼容命令顺序处理；Windows拖放只去掉整条输入的一对外层引号。单路径直接进入现有预览/确认；批量继续通过M→新建任务。任务无论成功、失败或取消，只要应用健康都返回Fast Path。当前开发机计算启动约0.18～0.21秒，ToolManager仍session初始化一次；冷启动体验P1等待真实环境验证。

## D-021：发布证据必须区分原始样本、受控副本和确定性派生物

**Decision**：Release evidence必须明确标记`ORIGINAL REAL SAMPLE`、`CONTROLLED REAL-SAMPLE COPY`或`CONTROLLED REAL-SAMPLE DERIVATIVE`。只有原始用户目录本来存在的结构才能记为Original observation；从真实源通过确定性工具得到的inner必须记为Derivative。

**Context**：Test Game 4当前原始目录不再同时具有“既有完整游戏根”和“独立inner RAR”，但这两个历史条件都曾暴露发布级问题。

**Reason**：受控副本可以保护原始样本并重建历史条件；确定性派生物可以强验证outer/inner字节关系。若不区分来源，会把“真实源派生验证”误写成“原始目录天然存在”。

**Rejected alternatives**：修改原始样本制造条件；用同名fake archive代替真实inner；只依赖helper或自动测试就宣称真实签字通过。

**Consequences**：受控工作区必须在项目外，原始样本只读并做前后SHA256。Derivative必须记录生成工具、大小、SHA256和真实调用链；验证失败时保守保留状态，不为关闭gate降低证据标准。
