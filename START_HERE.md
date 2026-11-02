# GameArchiveManager 统一接管入口

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



### 本次 ChatGPT + Codex 唯一代码切片：内嵌扫描诊断保留（合成回归通过）

- Codex 只改动未提交的 `coordinator/embedded_resolver.py` 和 `tests/test_embedded_candidate_resolution.py`：`EMBEDDED_INCOMPLETE` 在限制退出时同时报告扫描范围/停止原因和已处理候选的 offset、最新验证状态（例如 `PASSWORD_REQUIRED` 或 `FAILED`），不写原始工具输出或密码；安全扫描窗口、预算和最终数据 CRC 检查未改变。
- 测试驱动新增 5 条回归：失败优先时 4 条如预期失败、成功对照通过；改动后聚焦 `30/30 PASS`、全量 `322/322 PASS`、无跳过。Codex 的初次 Tcl 环境失败已用仓库内有效 Tcl/Tk 隔离路径重新执行通过；日志 `.vm_gate/sample8_diagnostic_20261102`。
- **实际三条真实样本解压发生在上述诊断小修补之前**；本补丁没有重跑 20+ GB 的真实解压，也不会让没有密码的加密数据自动解开。任何外层 CRC、合成回归或文案修复均不得记为真实完整 E2E PASS。
- Codex 首次治理检查误判了文档中一条 7-Zip 参数形式为敏感密码输出，已仅调整测试证据的文案表述而未修改治理规则。最终在文档修正后，使用 `.build_venv/Scripts/python.exe -B` 实际运行 `-m unittest tests.test_embedded_candidate_resolution -v`（30 PASS、exit 0）、`-m unittest discover -s tests -p test_*.py -v`（322 PASS、零跳过、exit 0）以及 `scripts/verify_project_state.py`（Overall PASS、exit 0）。证据日志为 `.vm_gate/real_samples_final_focused.log`、`.vm_gate/real_samples_final_full.log`、`.vm_gate/real_samples_final_governance.log`。

## 2026-11-02 晚间真实资源 7 / 新资源 8 接续（全部真实运行，但未完成加密内层验收）

- 本次直接使用 Remote Desktop Commander + 当前源码 `GameArchiveService` 实跑，而非旧 EXE。Sample 7 三卷均在，合计 11,460,839,972 B；新 `C:\SampleArchives\样本8` 包含两份不同于已删除旧样本的 RAR，分别 4,606,279,750 B 和 14,085,986,899 B。
- 外部 7-Zip `t` 两个 RAR 全数据校验 **exit 0 / Everything is Ok**（各有 warning，需保留提醒）。应用实际 run：Sample7 = `PASSWORD_REQUIRED` / 0 success, 1 failed；8a = 外层 1 success / 内层 `EMBEDDED_INCOMPLETE` 1 failed；8b 同。两个 MP4 内结构可信但未数据验证的加密 RAR5 offset 为 72,684,880 和 162,836,508；均不等于 E2E PASS。
- 本机 Tk 密码对话框对 8a 真实显示过，但未收到输入（超时，不是密码尝试成功）。原配置 `auto_try_password=false`，遵守该偏好；真实库未访问。Codex 审查证实内嵌诊断丢失候选层失败信息，优先补测试和可行动的诊断，不得放开 512 MiB 扫描界限。
- 源文件前后 SHA-256 全部不变，当前真实工作树的未提交改动全部保留；程序已生成的外层 MP4 和中间目录约额外占用 37.38 GB，**没有删除/覆盖**，现有 C: 空间约 42.8 GB；继续实解之前必须安排空间。
- 最新原始实测细节、失败结果、命令、校验边界和证据文件在 `docs/REAL_WORLD_TESTS.md` 与 `.vm_gate/real_e2e_*.json`。成功标准：原始输入一路完整解密、递归、CRC、最终交付且无失败；**目前未达成**。只允许用户在本机输入密码，不能在聊天要求明文密码，也不能把历史/合成测试当本次通过。



## 2026-11-02 继续开发：Sample 7 配置可见性与真实只读验证（尚未完成真实解压）

- ChatGPT + Codex 在**现有未提交工作树**推进一个切片，未生成其他工作树。HEAD 仍为 `b3b2fa6db8f20b6559fea06d348c005b02f360e8`，分支 main；保留原有 27 个已修改文件及 11 个未跟踪文件，未提交、reset、clean、push、发布。
- Codex 修改 `gui/settings_panel.py`、`tests/test_gui_settings.py`、`tests/test_integration.py`：设置窗口显示真正读取的配置文件完整路径、生效的 `max_archive_size_mb`，配置缺失/无效时显示回退警告；新增用 Sample 7 精确三卷总字节数模拟 10240 MB 拦截和 20480 MB 放行、保存后重载配置的回归。未修改安全默认值、源归档或 `config.json`。
- 本机真实样本（只读）`C:\SampleArchives\样本7\sample_group\PC\sample_pc.7z.001` + .002 + .003 合计 11,460,839,972 字节，3/3 存在。当前源码解析 `config.json` 的 99999 MB 设置并允许生成执行计划；若显式设置 20480 MB，同样通过大小门禁；10240 MB 按设计拦截。对已有 `sample_pc.jpg` 查到真实内嵌加密 RAR5 候选 offset=23332。直接运行 7-Zip 只读列表要求密码，随即终止；未执行真实解压、未调用用户密码。三个原始分卷 SHA-256 前后重算均一致。
- Codex 初次使用专用测试包装器导致 Tcl 环境报错及跳过（95 tests/3 errors/2 skipped；317 tests/10 errors/21 skipped），**不能作为通过证据**。ChatGPT 用正常标准 unittest + 正确隔离的 VIRTUAL_ENV、LOCALAPPDATA、TCL_LIBRARY、TK_LIBRARY 重新实测：`tests.test_gui_settings tests.test_integration` **95/95 PASS**；完整 `unittest discover -s tests -p test_*.py -v` **317/317 PASS、0 skipped**；`tests.test_embedded_candidate_resolution` **25/25 PASS**；`scripts/verify_project_state.py` **Overall PASS**，全部 exit 0。证据在 `.vm_gate/sample7_standard_*.log`、`.vm_gate/sample8_20261102_focused.log`、`.vm_gate/sample7_source_sha_before.json`。
- **未验证**：Sample 7 的真实密码输入→完整递归解压→GameArchive_Output 交付；原 Sample 8 宿主已删不可重放；新 EXE、干净虚拟机及真实 GUI 人工验收均未执行。不要把自动测试当作真实样本成功。下一单切片：用当前源码启动 GUI，由用户在本机输入密码后执行 **PC 首卷** 的真实完整链路并核对交付、日志和 SHA-256；不得再次用旧 0.1.0 EXE 冒充新源码。



## 2026-11-02 接手增量：真实加密 RAR5 诱饵后人工密码恢复回归（本机自动化 PASS，未提交）

- 接手机器：<machine-id>；工作入口：`C:\Users\<username>\Documents\GameArchiveManager`；分支 `main`；HEAD `b3b2fa6db8f20b6559fea06d348c005b02f360e8`。先检查了 git status / diff --stat / diff --check / 未跟踪文件；接手前有 27 个已跟踪修改、11 个未跟踪文件，没有进行 reset、clean、提交、push 或发布。
- `handoff_output/handoff_2026-10-31/HANDOFF.md` 的基准提交与 HEAD 一致，但快照不包含 11 月 2 日已经存在的 EmbeddedResolver 多候选修复，不得用旧快照覆盖当前工作树。
- 本次只推进一个切片：`tests/test_embedded_candidate_resolution.py` 新增 `test_real_header_encrypted_rar5_after_decoy_manual_password`；真实 WinRAR 创建加密 RAR5，前置 CRC 合法的假 RAR5 加密头；真实 7-Zip 验证跳过诱饵、自动密码预算为 0 后人工输入成功、正确 offset、内容、宿主 SHA-256 不变、候选临时目录清理、成功密码入库。未修改生产逻辑，未接触用户真实密码。
- 本次实际运行命令（位于项目根，使用 `.build_venv/Scripts/python.exe -B`，VIRTUAL_ENV 指向 `.build_venv`，LOCALAPPDATA 指向 `.vm_gate/embedded_test_profile`，TCL_LIBRARY/TK_LIBRARY 指向 `.vm_gate/tcl8.6` 和 `.vm_gate/tk8.6`）：`-m unittest tests.test_embedded_candidate_resolution.EmbeddedCandidateResolutionTests.test_real_header_encrypted_rar5_after_decoy_manual_password -v` = 1/1 PASS，exit 0；`-m unittest tests.test_embedded_candidate_resolution tests.test_integration tests.test_manual_password_recovery tests.test_beta_integration -v` = 144/144 PASS，exit 0；`-m unittest discover -s tests -p test_*.py -v` = 313/313 PASS，exit 0；`scripts/verify_project_state.py` = Overall PASS，exit 0。
- 本次日志：`.vm_gate/handoff_20261102_baseline.log`（代码切片前完整 312 PASS）、`.vm_gate/handoff_20261102_focused.log`、`.vm_gate/handoff_20261102_full.log`、`.vm_gate/handoff_20261102_governance.log`。日志置于忽略的本地验证目录。
- 验收边界：真实加密 RAR5 *合成宿主* 路径自动验证通过；原 Sample 8 宿主已经删除，不能重放，真实 Sample 8、正式 GUI 端到端、真实密码库手工使用、新打包 EXE、干净 VM、Sample 7 均为 **NEEDS_VERIFICATION**。不借用历史 VM/样本通过结论。本次没有构建或发布。
- 修改文件：`tests/test_embedded_candidate_resolution.py`（新增测试）、`START_HERE.md`、`docs/CURRENT_STATUS.md`（交接记录）；此前全部未提交生产代码和用户文件保留。下一切片建议：使用可保留的新真实嵌套加密样本验证 GUI 全流程、密码输入及最终交付，核验 SHA-256 / 无遗留临时目录；在证据出现前不得声明 Sample 8 FIXED。



> 2026-11-02 增量：内嵌候选解析已在本工作树修复并通过合成回归（聚焦 142 / 完整 311 项，无跳过）。下方 2026-10-31 的 NOT FIXED 是历史记录；原 Sample 8 宿主已删除，仍不可重放，未标 Sample 8 或应用端到端 PASS。最新证据边界与环境见 docs/CURRENT_STATUS.md 和 docs/REAL_WORLD_TESTS.md，旧交接快照未包含本次增量。

> 当前工作树核对日期：2026-10-31（Asia/Shanghai）。本文件是接管入口；当前代码事实以工作树、测试和本文件的“本地开发状态”为准，历史发布事实以 project_state.json 和发布证据为准。

## 1. 唯一项目入口

    C:\Users\<username>\Documents\GameArchiveManager

这是项目的 Windows 固定入口/junction。不要在 GrokWork、Documents\Codex、旧副本或 .project_archive 中继续开发。历史来源映射见 [docs/WORKSPACE_MAP.md](docs/WORKSPACE_MAP.md)。

## 2. 先判断你接手的是哪份代码

当前分支：main
接手补丁的基准提交：b3b2fa6db8f20b6559fea06d348c005b02f360e8
当前工作树：**有未提交的修改**，包含密码库、安全存储和主窗口 UI。不要运行 reset、clean、强制 checkout 或其他会丢弃修改的命令。

- 如果你正在用户的原电脑上继续工作，先运行 git status --short --branch，直接在现有工作树继续。
- 如果你是从 GitHub 新克隆的仓库开始，远端的基准提交**不包含当前工作树修改**。需要先取得并应用当前快照 `handoff_output/handoff_2026-10-31.zip`（包内 `HANDOFF.md` 记录精确基准提交和应用步骤），再开始开发。快照包含本次 Sample 8 诊断结果；若之后又有未提交修改，交接前必须重新生成。
- 不得将补丁包里的本地开发状态误认为已经提交或发布的版本。

## 3. 当前真实状态（本地开发，不等于发布）

- 已发布身份仍是 0.2.0 / Release 源码；此次本地开发没有生成新 EXE。旧 0.1.0 便携版保持不变。
- 密码库独立窗口：用户已确认“可以”，视觉验收通过；代码和 DPAPI 存储改动仍在未提交工作树。
- 主窗口：用户否定了第一版“大窗口、说明文案太多”的设计。当前源码已改为约 **900×520**、最小 **780×500** 的紧凑布局，去掉重复说明，保留资源选择、开始解压、五阶段进度、密码库和设置。Windows 临时配置渲染通过，但**用户尚未确认最新紧凑版视觉**。
- 最近一次完整本机自动化回归：`py -B -m unittest discover -s tests -p "test_*.py" -v` → **288 tests OK**（2026-10-29，含分卷大小上限错误提示回归）；本次 Sample 8 调查未修改代码，因此未重跑测试。
- py -B scripts/verify_project_state.py → PASS。最近的 scripts/rc_readiness.py 为 GO，但其 Windows 11 VM 门禁继承自历史发布证据，**不是当前工作树新 EXE 的验收**。
- Sample 8（样本8）：已找到并验证用户新解出的正确内层 RAR。7-Zip CRC 测试通过（170 文件，Everything is Ok，仅有 2 字节尾随数据）；最终输出 168 个 MP4 + 2 个文本文件，5,825,318,514 字节，168/168 均通过 FFprobe。原测试目录已按用户要求清理；完整输出保存在 `samples/样本8_已解压`。此前失败诊断误选了旧副本（5,748,694,122 字节），不代表新解出的归档损坏。失败任务记录显示只尝试了 2 个已保存密码、没有人工输入；源码检测器又会在第一个 RAR5 加密头通过基础 CRC 后提前停止，疑似选中 MP4 中较早的假阳性签名。该根因尚未在原始宿主上复验，检测器代码也尚未修复；状态 NOT FIXED。当前没有匹配的 GameArchiveManager 成功任务历史，因此样本输出完整性已验证，但不能据此宣称本轮是 GameArchiveManager 自动解压通过。Sample 7 的分卷总大小上限问题仍未完成复验。
- 尚未针对本轮工作树构建/发布新 EXE，未 push、tag 或创建 Release；真实密码库和真实归档的端到端手工验收仍需补做。

详细变更、证据和风险见 [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md)。产品目标和分阶段验收见 [docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md)。

## 4. 五分钟接手流程

先只读检查，不要立即改代码：

    git status --short --branch
    git diff --stat
    git diff --check
    py -B scripts/verify_project_state.py
    py -B -m unittest discover -s tests -p "test_*.py" -v

然后按需要阅读：

1. 本文件；
2. [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md) — 当前工作树、测试、下一步；
3. [project_state.json](project_state.json) — 已发布版本/正式门禁的历史状态，不能代替当前工作树状态；
4. [docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md) — 用户目标、已实现与未实现；
5. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 模块职责与数据流；
6. [docs/DEBUGGING_PROTOCOL.md](docs/DEBUGGING_PROTOCOL.md) — 缺陷诊断、真实样本和安全验收；
7. [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) 与 [docs/REAL_WORLD_TESTS.md](docs/REAL_WORLD_TESTS.md) — 限制和真实样本证据；
8. [docs/DECISIONS.md](docs/DECISIONS.md) — 重要设计决策；
9. [docs/SECURITY.md](docs/SECURITY.md) — 密码、文件系统和外部进程边界。

[docs/PROJECT_HANDOFF.md](docs/PROJECT_HANDOFF.md) 是较长的历史背景材料，部分版本/进度陈述已过时。不得用它覆盖本文件和 CURRENT_STATUS 的当前工作树事实。

## 5. 代码地图

| 路径 | 职责 |
| --- | --- |
| main.py | CLI 入口 |
| gui/app.py | Tk 桌面入口；用户交互、进度呈现、调用应用服务 |
| gui/settings_panel.py、gui/password_library.py | 设置与本机密码库界面 |
| application/app_service.py | 应用组装入口，连接配置、工具、任务、报告、历史和日志 |
| task/ | Task、任务分析与任务级执行编排 |
| scanner/、analyzer/、rules/ | 扫描输入、识别真实格式、决定容器是否应自动递归处理 |
| execution/、extractor/、tools/ | 生成解压计划、调用外部解压器、发现工具 |
| coordinator/、recovery/、password/ | 单归档处理协调、密码恢复和本机 DPAPI 密码库 |
| pipeline/ | 递归队列、深度/数量/重复路径守卫 |
| security/、cleanup/ | 输入/输出安全检查、运行时所有权与受控清理 |
| organizer/ | 最终内容根、DeliveryUnit、重复内容检测与安全交付 |
| report/、history/、logging_system/ | 统一报告、历史摘要和脱敏日志 |
| tests/ | 单元、集成、GUI 和回归测试 |
| scripts/ | 项目状态、发布就绪与治理验证脚本 |
| ui/ | 当前只有空的 __init__.py，没有运行时导入；桌面 UI 在 gui/。暂勿在未检查引用/历史前删除该占位包。 |

不要把扫描、格式识别、自动执行策略、单归档协调、递归队列和最终交付揉进一个模块。修改核心行为前先读 ARCHITECTURE 与 DEBUGGING_PROTOCOL。

## 6. 运行与测试

开发环境：Windows 10/11，Python 3.10+；当前机器使用 Python 3.13。运行时 Python 依赖为标准库；打包依赖单独列在 requirements-build.txt（PyInstaller）。外部归档工具 7-Zip、WinRAR、LZ4 有各自的可选/必需能力和许可证。

    pyw gui\app.py
    py main.py
    py -B -m unittest discover -s tests -p "test_*.py" -v
    py -B scripts/verify_project_state.py
    py -B scripts/rc_readiness.py

requirements.txt 为空是有意的：运行时没有第三方 Python 包。不要把 PyInstaller 或外部 EXE 混成运行时 pip 依赖。

## 7. 不可破坏的边界

- 不修改、移动或删除用户源归档；不覆盖已有输出。
- 不把密码明文写入日志、报告、历史或配置。
- 不按扩展名单独判定真实归档；保留结构、CRC、SHA-256 和路径边界验证。
- 不自动清理未知历史目录；清理只能针对本次运行拥有且通过边界验证的技术目录。
- 核心修改遵循 DEBUGGING_PROTOCOL：根因 → 正例 → 反例 → 交互例 → 完整自动测试 → 对应真实样本回归。
- 未经用户明确授权，不 push、merge、rebase、reset、clean、tag、发布 Release、上传产物或修改仓库设置。

## 8. 交接结束前必须留下

- 当前目标、根因/方案与明确的未实现范围；
- 修改文件列表，以及哪些是新增、修改或删除；
- 实际执行的命令与结果（不能只写“测试通过”）；
- 当前分支、基准提交、工作树是否干净；
- 真实样本、VM、打包和用户手工验收分别是什么状态；
- 下一步一个最小可执行任务；
- 是否有未包含在 Git 提交中的文件/补丁需要一并转交。
