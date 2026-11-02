# Current Status — 0.3.0rc1 Release Candidate

2026-11-03 verification: Windows automated suite 357/357 PASS, Linux native installed-wheel synthetic extraction and Tk GUI PASS. Clean Windows 11 VM and private multi-GiB encrypted inner archives remain NOT VERIFIED. RC is a preview, not a stable production signoff. Public release details: `docs/RELEASE_NOTES_v0.3.0-rc.1.md`.

Historical 0.2.0 source-update notes and earlier handoff evidence are retained below.

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

## 2026-11-02 晚间：Sample 7 与新 Sample 8 真实程序回归（BLOCKED）

- `main` 分支当前 HEAD `b3b2fa6db8f20b6559fea06d348c005b02f360e8`；原工作树大量未提交修改全部保留，不 reset/clean/commit/push/merge/tag/release。路径是 `C:\Users\<username>\Documents\GameArchiveManager` junction。
- 真正执行当前源码的 `GameArchiveService.execute_task`，输入三个文件：资源7的 PC 三分卷首卷（实际三卷存在）和 `C:\SampleArchives\样本8` 下两份新 RAR。Sample7 status `FAILED`、0 success/1 failure，`PASSWORD_REQUIRED`；新 8a、8b 均外层 1 success + 内层 1 failed `EMBEDDED_INCOMPLETE`，即便外层 MP4 交付也不是最终内容成功。外层 7-Zip t 两文件均 Everything is Ok / exit0 / 1 warning；原样本与所有新输入 SHA256 前后不变。
- 8a MP4 4,606,279,439 B 的 RAR5 加密候选 offset 72,684,880；8b MP4 14,085,986,678 B 的候选 offset 162,836,508。均位于默认 512 MiB 扫描前缀内，但 `VALID_ENCRYPTED` 仅表示局部结构/CRC、没有内容完整性证明。Codex 只读复核现有 `EmbeddedResolver` 会在扫描上限后覆盖候选诊断信息；密码需人工输入才能完成最后验证，但不能预设密码一定正确或归档一定完整。
- 本轮真实手工密码弹窗 8a 成功显示，但未收到输入（超时回退），报告 `.vm_gate/interactive_inner_8a.json` 为 `manual_attempts=0`，没有暴露任何密码；遵守 `auto_try_password=false`，未使用/更改本机密码库。
- 运行证据：`.vm_gate/resource8_original_hashes.json`、`.vm_gate/resource8_crc_test.json`、`.vm_gate/real_e2e_{7,8a,8b}.json`、`.vm_gate/interactive_inner_8a.json`，对应隔离运行日志在 `.vm_gate/real_e2e_profile/GameArchiveManager/logs`。测试脚本 `.vm_gate/real_test_feasibility.py`、`.vm_gate/resource8_crc_test.py`、`.vm_gate/real_e2e_runner.py`、`.vm_gate/scan_real_8a.py`、`.vm_gate/scan_real_8b.py`、`.vm_gate/interactive_inner_test.py`，全部只负责本地证据/真实程序调用而非用户源文件操作。
- 两个新资源 8 的外层解压副本与交付副本合计约 37.38 GB，占用 C:；没有擅自删除，剩余空间约 42.8 GB。使用者须先安排密码输入和可靠空间，再进行资源7/8完整端到端重跑。**实际测试均未达到完整 E2E 的成功验收标准**，不得将 SourceCRC PASS、目录列表、候选检测、部分交付视为完成。
- 本次无新增 EXE、虚拟机验证和任何发布；后续单一切片先修复保留完整失败原因的脱敏诊断，再在提供有效本机密码及磁盘预留后做三项 E2E 与最终 SHA256/CRC 对账。



## 2026-11-02 后续切片：Sample 7 运行配置透明化 + 本机真实归档只读门禁验证

- 工作树：`C:\Users\<username>\Documents\GameArchiveManager`（junction 到 `GameArchiveManager0.1.0`），`main`，HEAD `b3b2fa6db8f20b6559fea06d348c005b02f360e8`，沿用全部未提交修改；无 reset、clean、commit、push、merge、tag、release。旧 `handoff_output/handoff_2026-10-31.zip` 与当前工作树不同，不能用于覆盖。
- 改动：Codex 在 `gui/settings_panel.py` 增加只读配置文件绝对路径、生效 `max_archive_size_mb` 与配置缺失/非法回退提示，保存设置后更新显示，保持中英语言切换；`tests/test_gui_settings.py` 增加显示、保存、语言切换、无效配置测试；`tests/test_integration.py` 增加模拟精确 Sample 7 总尺寸的保存/重载/安全边界测试。ChatGPT 阅读 diff、运行标准测试并负责本次文档。未改既有默认 10240 MB，不自动放宽安全校验，未改真实用户 config.json。
- 本机只读实际对象：`C:\SampleArchives\样本7\sample_group\PC\sample_pc.7z.001`，后续 .002/.003 均在，大小分别 `4,089,446,400`、`4,089,446,400`、`3,281,947,172` 字节；当前源码 ArchiveAnalyzer 判定 7Z / multi-volume / no missing。由当前源码 `default_config_path()` 实际落到物理目标 `...\GameArchiveManager0.1.0\config.json`，有效限制 99999 MB；以默认 10240 MB 构建计划则因合计 11,460,839,972 字节拒绝；20,480 MB 与 99,999 MB 均允许（仅门禁层通过）。历史 2026-10-29 失败的 EXE 路径仍未被证实；现有 `dist\GameArchiveManager-0.1.0\GameArchiveManager.exe` 是旧产物，未经重建。
- 真实中间文件 `sample_group\PC\sample_pc.7z_extracted_password_attempt_1\sample_pc.jpg` 大小 `11,460,839,730` 字节，文件头为 JPEG，ArchiveAnalyzer 查得内嵌 RAR5 加密候选 offset `23,332`；已有 `sample_pc_embedded.rar` 为 `11,460,816,398` 字节，和剩余长度相等。只读 7-Zip `l -slt` 尝试提示密码输入，未输入密码，终止该 7z 进程；没运行实际解压或覆盖任何已有内容。
- 原始分卷 SHA256 前后不变：.001 `[私人样本 SHA-256 已脱敏]`；.002 `[私人样本 SHA-256 已脱敏]`；.003 `[私人样本 SHA-256 已脱敏]`。本次不删除 `GameArchive_Output` 及历史解压残留。
- 运行命令和证据：`git status --short --branch` / `git rev-parse HEAD` / `git diff --check`（无空白错误、只有原有 LF/CRLF 告警）；`.build_venv/Scripts/python.exe -B .vm_gate/sample7_readonly_preflight.py`、`.vm_gate/sample7_readonly_nested.py`（只读，exit 0）；`Get-FileHash -Algorithm SHA256`（三卷前后相等）；`7z.exe l -slt sample_pc.7z.001`（需密码而终止，exit 1，不是成功）。Codex 的自定义包装器运行结果 95 tests/3 errors/2 skipped 和 317 tests/10 errors/21 skipped 属于 Tk/Tcl 环境及保护跳过，**无效、不计 PASS**。
- ChatGPT 在设置 VIRTUAL_ENV=`.build_venv`、LOCALAPPDATA=`.vm_gate/embedded_test_profile`、TCL_LIBRARY=`.vm_gate/tcl8.6`、TK_LIBRARY=`.vm_gate/tk8.6` 的正常 Windows unittest 下重新验证：`-m unittest tests.test_gui_settings tests.test_integration -v` = **95 PASS，exit 0**；`-m unittest discover -s tests -p test_*.py -v` = **317 PASS、无 skipped，exit 0**；`-m unittest tests.test_embedded_candidate_resolution -v` = **25 PASS，exit 0**；`scripts/verify_project_state.py` = **Overall PASS，exit 0**。日志：`.vm_gate/sample7_standard_focused.log`、`.vm_gate/sample7_standard_full.log`、`.vm_gate/sample7_standard_governance.log`、`.vm_gate/sample8_20261102_focused.log`；原始分卷哈希在 `.vm_gate/sample7_source_sha_before.json`。
- 验收定义仍然严格：Sample 7 **SIZE_GATE_VERIFIED / FULL_APP_NEEDS_VERIFICATION**，需用户在当前源码 GUI 的密码弹窗输入有效密码、程序完成递归、最终交付根和文件清单、源 SHA256、残留目录、日志脱敏全部核验后才能标 PASS；Sample 8 仅合成回归 25 PASS，原宿主已删，真实流程 **NEEDS_VERIFICATION**。新 EXE / VM / 手工 UI 验收未执行。**下一切片**仅进行真实 Sample 7 GUI E2E，避免再次调试已证实的大小门禁。



## 2026-11-02 接手交接增量（当前自动化验证通过，未提交）

- 仓库：`C:\Users\<username>\Documents\GameArchiveManager`；设备 `<machine-id>`，分支 `main`，HEAD `b3b2fa6db8f20b6559fea06d348c005b02f360e8`。先实际检查 git status、未跟踪文件、git diff --stat、git diff --cached --stat、git diff --check 与快照基准。接手前 27 个已修改跟踪文件、11 个未跟踪文件，全部保留。旧快照 `handoff_output/handoff_2026-10-31.zip` 基于相同 HEAD，但不含 11 月 2 日先前修复。
- 单一开发切片：`tests/test_embedded_candidate_resolution.py` 新增 `test_real_header_encrypted_rar5_after_decoy_manual_password`：真实 WinRAR 生成加密 RAR5，前置基础 CRC 合法但不真实的加密头，验证 7-Zip 能跳过诱饵、通过一次人工密码输入恢复真实归档、选中正确 offset、内容一致、宿主 SHA-256 不变、清理候选目录、保存合成成功密码。没有修改生产逻辑。
- 实际执行：项目根以 `.build_venv/Scripts/python.exe -B` 运行 `-m unittest discover -s tests -p test_*.py -v`：修改前 312 PASS / exit 0，修改后 313 PASS / exit 0；`-m unittest tests.test_embedded_candidate_resolution.EmbeddedCandidateResolutionTests.test_real_header_encrypted_rar5_after_decoy_manual_password -v`：1 PASS / exit 0；`-m unittest tests.test_embedded_candidate_resolution tests.test_integration tests.test_manual_password_recovery tests.test_beta_integration -v`：144 PASS / exit 0；`scripts/verify_project_state.py`：Overall PASS / exit 0。隔离配置：VIRTUAL_ENV=`.build_venv`、LOCALAPPDATA=`.vm_gate/embedded_test_profile`、TCL_LIBRARY=`.vm_gate/tcl8.6`、TK_LIBRARY=`.vm_gate/tk8.6`。完整日志：`.vm_gate/handoff_20261102_baseline.log`、`.vm_gate/handoff_20261102_focused.log`、`.vm_gate/handoff_20261102_full.log`、`.vm_gate/handoff_20261102_governance.log`。
- 本次修改文件：`tests/test_embedded_candidate_resolution.py`、`START_HERE.md`、`docs/CURRENT_STATUS.md`。未 reset/clean/checkout/提交/push/merge/tag/发布。原始未提交工作树全部保留；修改后 `git diff --check` 无空白错误，只有原有 LF/CRLF 提示。
- 未验证：原始 Sample 8 宿主已删除，不能直接复现；真实样本、真实 GUI 端到端、用户密码库手工、多 GB 压力、新 EXE、干净 VM、Sample 7 均 **NEEDS_VERIFICATION**，历史结果不计本次通过。产品已有密码库 UI 经用户确认；紧凑主窗口仍待用户视觉确认；一键加密压缩尚未实现。
- 下一项单切片：在用户许可的、保留原件的真实嵌入加密资源上运行 GUI 完整链路，记录源 SHA-256、人工密码恢复、结果内容、脱敏日志、残留技术目录，再更新 `docs/REAL_WORLD_TESTS.md`。未经实际验收不得把 Sample 8 标为 FIXED。



## 2026-11-02 内嵌候选修复（未提交、未发布；仅合成回归验证）

本节记录最新代码状态；下方 2026-10-31 的 NOT FIXED / next action 保留为当时的历史记录。

- 唯一工作树 `C:\Users\<username>\Documents\GameArchiveManager`，HEAD `b3b2fa6db8f20b6559fea06d348c005b02f360e8`。保留原有 GUI、密码库、安全与文档未提交改动；没有暂存、提交、push、打包或发布。
- 宿主级 EmbeddedResolver 保留按 offset 升序的惰性候选流。局部 RAR5 header CRC 仅为 PROVISIONAL。已安装并验证的 7-Zip 使用指定格式及 `:s0` 禁止向后寻找归档起点；列表确认 offset 0 的 Physical Size 后，只裁剪任务拥有的切片，再实际解压验证数据/CRC 与现有安全检查。列表成功不算通过。首个完整有效候选成功后立即停止枚举。
- 每个候选使用唯一 `.gam_candidate_*` 目录；失败仅清理该候选目录。成功内容先移至宿主旁唯一输出目录，更新结果与 RuntimeTracker，再清理候选。宿主节点直接返回完整验证的内容，仅真正嵌套归档继续递归。
- 默认边界：扫描窗口 512 MiB，raw hits 4096，可信候选 8，累计切片 48 GiB，磁盘保留 1 GiB，活跃工作最多 300 秒 / 单进程最多 60 秒（同时遵守更小的 extraction_timeout_seconds），最多 256 次工具进程，单进程输出最多 4 MiB；7Z 局部 next-header CRC 读取最多 512 MiB。扫描、复制、进程均检查取消。到达上限、工具不可用或密码仍未解决返回 EMBEDDED_INCOMPLETE 及原因，不冒充损坏/无归档。人工等待不消耗活跃工作时间。
- 自动密码共享宿主预算；有界自动搜索后，每次非空人工提交按 offset 尝试尚未解决的候选，提交次数不按候选数累加；保留 skip/cancel，仅完整成功后保存密码。复用 7-Zip stdin，不新增 WinRAR 密码 argv；普通归档原有人工恢复与 GUI 接线不变。
- TDD 首批 10 项在旧代码失败（8 failures / 9 errors，含 subtests，exit 1）；第二批先暴露 3 个边界失败，再修复。最终新增 23 项，包含真实工具合成 RAR5 诱饵、列表成功但数据 CRC 失败、ZIP/7Z、受控密码/预算/取消交互。不声称复现原 Sample 8。
- 聚焦命令：`py -B -m unittest tests.test_embedded_candidate_resolution tests.test_integration tests.test_manual_password_recovery tests.test_beta_integration -v` → **142 tests OK，exit 0，0 skipped**。
- 完整命令：`py -B -m unittest discover -s tests -p "test_*.py" -v` → **311 tests OK，exit 0，0 skipped**。
- 环境：VIRTUAL_ENV 指向既有 `.build_venv`（Python 3.13.2）以便 py 选择解释器；LOCALAPPDATA 指向 `.vm_gate/embedded_test_profile`，避免读取执行账户无法解密的真实密码库；TCL_LIBRARY / TK_LIBRARY 使用 `.vm_gate/tcl8.6` / `.vm_gate/tk8.6` 相对路径副本。初次 py、未隔离密码库、Tcl 绝对路径运行有环境失败，以上是最终成功重跑，未跳过或削弱测试。日志：`.vm_gate/embedded_focused.log`、`.vm_gate/embedded_full.log`。
- **Sample 8：NEEDS_VERIFICATION / 原宿主不可重放**。原始宿主已在输出核验后删除，精确假阳性 offset 未证明；本次仅合成回归，不把 Sample 8、应用真实端到端、clean VM 或新 EXE 标为 PASS。多 GiB 性能、磁盘争用与真实 GUI 验收仍待新样本；轮询配额不是 OS 硬磁盘配额。旧交接快照未包含本次增量。


Published release baseline last verified: `2026-10-14`
App version: `0.2.0`
Build: `Release`
Published release test baseline: `py -B -m unittest discover -s tests -v` → `Ran 262 tests — OK`
Current P0: 无。

**Local development worktree checked: 2026-10-31 (not released).** Latest full suite after compact GUI and split-volume diagnostic changes: `py -B -m unittest discover -s tests -p "test_*.py" -v` → **288 tests OK**. Project-state verification: PASS. Current compact main window is still awaiting user visual approval. Sample 8 output was independently verified on 2026-10-31; no source code changed during that verification. These local changes do not replace the published release baseline or prove a new EXE/VM release.
Current verified handoff snapshot: `handoff_output/handoff_2026-10-31.zip`, based on `b3b2fa6db8f20b6559fea06d348c005b02f360e8`; contains the current tracked patch and all untracked files. Project-state verification PASS on 2026-10-31. Sample 8: user-created output was independently verified; the correct inner RAR passed 7-Zip CRC testing (170 files, Everything is Ok, only 2 trailing bytes). The preserved output contains 168 MP4 files and 2 text files, 5,825,318,514 bytes total; all 168 MP4 files passed FFprobe metadata checks and none is zero bytes. The original `样本8` directory, original outer RAR, intermediate ZIP/RAR copies, and empty `[空文件夹名已脱敏]` folder were removed only after the verified output was moved to `samples/样本8_已解压`. No matching GameArchiveManager task-history record was found, so this proves output integrity, not that the app itself completed the run. Previous diagnosis was wrong because it tested an older failed RAR copy (5,748,694,122 bytes) rather than the new valid RAR (5,746,925,296 bytes). The original failed task used 2 saved password candidates and no manual password; source review shows the embedded detector stops at the first RAR5 encrypted header that passes basic CRC/field checks, so a false-positive earlier signature in the MP4 is the leading suspected code root cause. This is NOT FIXED: no detector code or regression test has been changed yet, and the original host was deleted after output verification so the exact offset cannot be replayed. Next action: fix and test multi-candidate embedded RAR validation before calling Sample 8 resolved. Sample 7 remains blocked until its runtime archive-size limit is raised to 20480 MB in the exact app copy used by the user. `0.2.0` was published as source; the `0.1.0` portable package remains unchanged. Windows 10 remains optional/unverified.

## Current baseline

- 自动测试：`py -B -m unittest discover -s tests -v`
- 当前实际结果：`Ran 262 tests — OK`。2026-10-14 在新的 Windows 11 虚拟机里复跑，262 项通过，没有跳过。
- 当前状态：`0.2.0` / `Release`。这次发布的是源码，不是新的安装包或 exe。`clean_windows_11_vm` 保持原记录，不把这次虚拟机结果写成新的正式打包验收。Windows 10 可选未测。
- 核心冻结：否。0.2.0 增加了窗口、本机密码库、LZ4 安装询问、PC 标签开关和失败阶段记录。

## 2026-10-24 本机工作树进展（未发布）

**密码库第一阶段 A（安全存储）和阶段 B（独立管理 UI + 两个配置开关）已完成本机代码与自动化测试；真实用户手工验收尚未完成。** 这属于尚未提交的本机工作树改动，不代表原始 0.2.0 源码发布或历史 Windows 11 VM 被重新验收。

- `password/session_store.py`：旧版 version 1 DPAPI 存储兼容；先把加密内容写入同目录临时文件，flush/fsync 后 `os.replace`；保存失败时旧文件与内存候选列表不被主动覆盖。
- `password/session_store.py`：仅真正缺少文件时返回空库；格式损坏、错误版本、无法解密、读取失败抛出脱敏的 `PasswordStoreError`。
- `gui/app.py`：打开设置页遇到密码库异常时显示错误对话框和状态，不让损坏库伪装成空密码编辑器。
- `tests/test_password_store.py`、`tests/test_gui_app.py`：新增兼容、Unicode、区分大小写、原子写失败、加/解密错误、安全提示和会话隔离回归。
- 本机定向验证：`py -B -m unittest tests.test_password_store tests.test_gui_app tests.test_gui_settings -v` → **14 tests OK**。
- 本机全套回归：`py -B -m unittest discover -s tests -p "test_*.py" -v` → **270 tests OK，exit 0**。这是新增代码的本机证据；与 2026-10-14 的 **262 tests + clean Win11 VM** 历史发布证据是不同范围。
- `py -B scripts/verify_project_state.py` → **PASS，270 tests**；`py -B scripts/rc_readiness.py` → **GO（历史 Win11 VM 门禁继承，未重新运行 VM）**。
- 未执行新 EXE 构建、Windows VM 复验、真实用户密码库读写，也未 push、tag、release。
### 阶段 1B 代码与验证（2026-10-24，未发布）

- 新增 `gui/password_library.py`：独立 Tk 密码库窗口；主窗口直达，设置页密码分组也可打开；列表固定长度遮盖、默认遮盖搜索栏、明确按键显示/隐藏单项、复制并在 20 秒后尝试清除未变剪贴板；新增、编辑、删除、搜索、刷新、重复阻止和变更冲突提示。
- `gui/settings_panel.py`：彻底移除整库可见的多行明文编辑框；设置保存不会改写密码库。新增两个独立布尔开关，密码库修改在独立窗口中立即加密保存。
- `config/config_loader.py`、`task/task_executor.py`、`application/app_service.py`、`password/session_store.py`：正式接线 `save_passwords=False` 与 `auto_try_password=False`；前者开启时**人工成功验证的**密码才持久化；后者开启才自动选入已保存密码；无论后者是否开启，当前会话验证的密码仍可尝试。GUI 连续任务重新加载配置并复用会话验证密码。
- 新增 `tests/test_password_library.py` 并扩充 `tests/test_gui_app.py`、`tests/test_gui_settings.py`：使用临时虚构密码覆盖 DPAPI 存储、增删改查、并发修改保护、候选开关、输入遮盖、窗口 420/660/1100 宽度、主窗口入口、主题与语言响应。
- 2026-10-24 本机验证：`py -B -m unittest discover -s tests -p "test_*.py" -v` → **283 tests OK，exit 0**。新增 UI 的 Tk 控件布局测试通过；这**不是**用户本人点击体验、真实加密归档验证或干净 Win11 VM 复验。
- 尚存限制：仅人工成功验证密码自动入库，自动候选成功后是否持久化待后续设计；无备注/标签/跨账户导入导出；两个不同进程的严格原子更新锁尚未实现；复制后剪贴板仍可能被其他程序捕获。
- **下一步**：密码库 UI 已由用户确认“可以”，视觉验收通过。真实归档密码恢复、持久化行为和新版 EXE 仍未单独手工验收。主窗口第一版仪表板已实现，用户视觉验收待进行；未做新 EXE 构建、push、tag、release。

### 2026-10-24 密码库 UI 截图反馈与重排（本机修复，用户视觉验收通过）

- 用户截图明确显示旧版密码库窗口过矮（原固定约 660×510）：搜索框与显示开关挤在一行，密码列表被压没，第二排按钮不见。**该旧版 UI 视觉验收失败，即使功能测试通过也不能算合格。**
- 已直接重排 `gui/password_library.py`：标题说明、搜索卡片、中央可伸缩密码列表、选中密码与分组操作按钮、固定底栏；搜索框全宽，显示搜索开关独立一行；新增/编辑/删除一排，显示/复制另一排；卡片背景和按钮层级适配明暗模式；没有保存项时显示空状态提示。
- 新窗口尺寸按 Tk 实际控件请求计算，默认约 **740×763**（此机缩放环境），最小约 **570×668**；列表实测高度 **251px**。新增/编辑密码弹窗也有最小尺寸与默认遮盖。
- `gui/window_place.py` 新增按最近显示器工作区修正完整窗口位置的能力，避免沿用旧窗口坐标时底部跑出屏幕。
- 使用**仅含四个临时示例密码**的 Tk 窗口 + Windows `PrintWindow` 取得了当前重排后的真实窗口渲染图，确认中央列表和五个操作按钮可见；未打开或截图真实密码库。用户已确认密码库 UI 可以，视觉验收通过。
- `tests/test_password_library.py` 新增布局高度、最小窗口、空态、弹窗遮盖、旧保存位置屏幕边界测试。**最终完整回归：286 tests OK，exit 0**，前一版的 283 项仍只是较早的阶段性结果。未进行新 EXE、干净 VM 和真实加密样本复验。

### 2026-10-24 主窗口紧凑改版（本机源码，待用户视觉验收）

- 用户反馈首版主界面仍然“丑、废话多”。已移除重复的大标题/副标题、本地处理宣传徽标、输入说明、进度说明、底部安全宣传文案；压缩字号、按钮、卡片间距与窗口尺寸。
- 现在默认窗口约 **900×520**（最小 **780×500**）；保留顶部品牌/语言/主题，左侧资源路径与文件类型、两个选择按钮和主操作，右侧简洁状态与五阶段进度，底部仅保留密码库和设置。
- 旧版保存的较大窗口尺寸会在启动时限制到紧凑尺寸；未选择资源时只显示简短状态，不重复显示说明。原有解压执行、密码库、设置、主题/语言切换和阶段进度逻辑保留。
- 已在 Windows 本机使用隔离临时配置和示例路径渲染 **900×520** 深色界面；未读取真实配置、未运行解压任务。截图显示主要控件和五阶段均可见。
- GUI 专项：`py -B -m unittest tests.test_gui_app -v` → **5 tests OK**；完整回归：`py -B -m unittest discover -s tests -p "test_*.py" -v` → **287 tests OK，exit 0**。
- **当前紧凑版仍待用户视觉验收**。未构建新 EXE、未重新验收 VM、未发布；旧 EXE 保持不变。

### 2026-10-29 真实样本 Sample 7 失败诊断（未发布）

- 用户输入目录为“样本7”，历史记录中的失败归档是 `sample_pc.7z.001`。
- 两次完整目录尝试各有 3 个归档成功、1 个失败；失败项均为 PC 三分卷系列。第三次在 0.12 秒内失败，外部工具未启动。
- 根因：三卷总大小 `11,460,839,972` bytes 超过运行程序使用的 10 GiB 限制 `10,737,418,240` bytes。运行时限制与源码目录本地 config.json 的 99999 MB 不一致，实际使用的 EXE/配置路径尚未确认。
- 只改进了 `security/archive_safety.py` 的诊断文案，并在 `tests/test_integration.py` 增加分卷超限回归；没有放宽默认安全上限。
- 最新本机回归：**288 tests OK**；项目状态检查 PASS。未由助手重跑真实归档，未删除/覆盖源文件、已有输出或残留目录。
- 下一步：在用户实际运行的同一程序中把“最大归档大小（MB）”显式设为 20480；只选择 PC 首卷 `sample_pc.7z.001`，检查三卷齐全及目标磁盘空间后再由用户发起。Sample 7 仍为 `NEEDS_VERIFICATION`，不能标 PASS。

## Resolved P0

**历史失败技术目录污染 password candidates：RESOLVED。**

Issue ID：`password_candidate_history_pollution`

- 根因：ArchiveFinder与Scanner各自执行`os.walk`，前者的技术输出裁剪没有形成可共享boundary，后者只收到游戏根边界，导致rule drift。
- 修复：TaskAnalyzer读取同一任务history中的run-owned residual paths；`InitialScanSpaceResolver`将其和`GameArchive_Output`转为`TECHNICAL_OUTPUT_BOUNDARY`，ArchiveFinder与Scanner共享精确pruned paths。
- 保护：不按`*_extracted`名称过滤；普通`my_extracted/abc123`仍可提供候选；PIPELINE_SCAN不变；不删除历史目录。
- 回归：重复三次增加历史残留后，候选集合始终只有同一真实用户空目录。测试游戏6只读扫描结果为1个候选、1个技术边界、1个输入归档。

## P1

- 平台过滤已改为 opt-in：`ignore_android=False`、`ignore_AZ=False`。旧配置显式 `true` 仍然有效，INITIAL_SCAN/PIPELINE_SCAN都使用同一 Settings。
- `apk_content_container_recursive_unpack`：RESOLVED。ArchiveAnalyzer 仍如实报告 ZIP；ArchiveFinder 在自动创建任务前共享 ContainerRolePolicy。APK/Office/EPUB/JAR 默认保留，显式文件输入可覆盖。
- clean Windows 11 VM smoke test：当前交付 RC2 ZIP `BA3A9ADD…` / EXE `67DF840B…` 已 PASS。清单 1–13、15–17 见 `../rc2_smoke_codex.md`，三阶段真实 Ctrl+C 清单 14 见 `../rc2_item14_codex.md`；Windows 10 仍为可选未测。
- KI-P0-002已解决：独立PC与Android DeliveryUnits同时交付；真正竞争根保留现有选择闭环；未决唯一内容在非交互模式下保留并报告。
- `cli_direct_path_entry_regression`已解决：首屏直接接受文件/目录路径，M进入辅助菜单，Q退出；成功、失败或取消后返回Fast Path。
- `cli_startup_latency_regression`保留为NEEDS_REAL_ENVIRONMENT_VERIFICATION。开发机T1/T2约0.181秒、T3约0.000128秒，未采用lazy初始化。
- Test Game 4 Evidence Closure已完成，Required Real Sample Regression gate已PASS。
- NEXT-1人工密码恢复闭环已完成：非交互默认仍返回结构化失败；交互CLI支持安全输入、跳过和取消。
- AZ平台过滤误判已解决：只接受明确ASCII token，并只检查任务内容根以下的相对组件；历史记录保留在`KNOWN_ISSUES.md`。
- 历史 `RELEASE_CANDIDATE_REPORT.md` 仍保留当时的 `Development/103 tests` 证据；当前 RC 构建说明与基线以本文件、`RC_BUILD_NOTES.md` 和 `project_state.json` 为准。
- RC2 的 Win11 门禁已关闭；该门禁结果属于历史 RC 证据。当前正式版身份为 `BUILD_TYPE=Release`，版本 `0.1.0` 已发布。

## Known real samples

- 测试游戏3：通过。7z分卷→5GB JPEG→加密RAR5→密码恢复→Unity游戏，修复后ORPHANED_TEMP=0。
- 测试游戏4：PASS。原始真实样本已证明PC+Android独立交付、源完整性、无save-only交付和cleanup安全。2026-08-19 Evidence Closure另用项目外Controlled Real-Sample Copy证明既有Ren'Py游戏根建立INITIAL_SCAN boundary，用真实outer的确定性LZ4解码派生inner，证明`PC.rar + PC.rar.lz4`强关系只执行canonical inner并只交付1份PC内容。
- 测试游戏5：已修复并真实交付。DeliveryUnit折叠4节点技术链，输出sample_content共209文件、1,710,573,415 bytes。
- 测试游戏6：早期两次分别因无候选和错误候选耗尽而FAILED；最新runtime history（2026-08-15 15:12）为COMPLETED并交付`PC/VR`。P0修复后只读TaskAnalyzer得到1个合法候选，历史技术边界不再进入候选。

## 2026-10-29 历史失败记录与 2026-10-31 Sample 8 验证结果

- 外层 RAR：6,037,746,994 bytes；7-Zip test exit 0，只有末尾 3 bytes 额外数据警告。原始 SHA256 为 `[私人样本 SHA-256 已脱敏]`，两次 GameArchiveManager 运行前后不变。
- 2026-10-29 两次 GameArchiveManager 失败运行选中了一个旧嵌入式 RAR 副本（5,748,694,122 bytes），该副本的数据校验确实失败。后续诊断错误地把这个旧副本当成用户刚解出的正确归档；这是助手的样本选择/判断失误，不应推断整个原始资源损坏。
- 2026-10-31 用户新解出的正确内层 RAR 为 5,746,925,296 bytes；7-Zip CRC test exit 0、`Everything is Ok`，170 files，只有末尾 2 bytes 额外数据警告。最终目录含 168 个 MP4 + 2 个文本文件，共 5,825,318,514 bytes；168/168 MP4 通过 FFprobe，无零字节文件，文件总大小与归档清单完全一致。
- 最终输出已移到 `samples/样本8_已解压`。随后按用户要求删除旧 `样本8` 目录及原始 RAR、中间 ZIP/RAR 和空 `[空文件夹名已脱敏]` 目录；已验证输出保留。没有匹配本次成功操作的 GameArchiveManager task history，因此只记录输出完整性验证，不记为 GameArchiveManager 自动流程 PASS。详细证据见 [REAL_WORLD_TESTS.md](REAL_WORLD_TESTS.md) Sample 8。

## Password recovery status

- **NEXT-1 / `manual_password_recovery_after_exhaustion`**：RESOLVED。自动候选耗尽后，CLI提供I/S/C闭环；人工密码默认可见输入（中文输入法可用），明文不进日志/报告/history。业务层只接收可选回调。
- 只有实际成功的密码进入 `SessionPasswordStore`。密码库用当前 Windows 用户的 DPAPI 加密，保存在 `%LOCALAPPDATA%\GameArchiveManager\passwords.json`，重启后仍可作为候选。明文不进日志、报告或 history。
- `save_passwords` 与 `auto_try_password` 已接线，默认均为 false；前者控制成功验证密码是否持久保存，后者控制是否自动尝试已保存密码。Sample 8 的两条已保存候选仅在该次用户任务排查中临时尝试，持久设置未改变。
- **NEXT-2 / `cli_session_loop`**：COMPLETED（2026-08-15）。CLI启动后保持一个`GameArchiveService`会话，可连续新建单任务或批量任务、查看最近结果/工具/设置并主动退出。Settings、ToolManager、HistoryStorage、ApplicationService和SessionPasswordStore为会话级；Task、RuntimeTracker、Pipeline/Guard、report和task candidates每次重建。

## Do not do

- 不要在用户未同意时下载或安装工具。
- 不要把leaf当final content。
- 不要把EXE当唯一游戏证据。
- 不要仅按文件名、目录名或大小去重。
- 不要删除或修改源归档。
- 不要覆盖GameArchive_Output旧结果。
- 不要自动删除未知历史目录。
- 不要记录密码明文或完整含密码命令行。
- 不要为了测试通过降低结构/CRC/SHA256验证强度。
- 历史 clean VM 门禁证据不得单独扩展为新的发布承诺；当前正式版发布状态以 `project_state.json` 和本文件为准。

## Knowledge base

- 总入口：`PROJECT_HANDOFF.md`
- 长期愿景：`PROJECT_VISION.md`
- 路线图：`ROADMAP.md`
- 技术决策：`DECISIONS.md`
- 真实样本：`REAL_WORLD_TESTS.md`
- 已知问题：`KNOWN_ISSUES.md`
- 查错标准：`DEBUGGING_PROTOCOL.md`
- 机器状态：`../project_state.json`
- 自动验证：`../scripts/verify_project_state.py`
- RC门禁：`../scripts/rc_readiness.py`

完成任何影响版本、测试基线、P0或下一步的重要任务后，必须更新本文件；不要依赖聊天记录。

## Governance health

- `project_state.json`：schema v1，当前版本/构建/测试基线/P0/release gates已同步。
- `scripts/verify_project_state.py`：最终结果见本次治理检查；schema、版本、文档、协议、密码泄漏、开发机路径、P0和不少于 `project_state.json` 已核验数量的自动测试必须一致。当前已核验 234 项。
- `scripts/rc_readiness.py`：记录历史 RC2 机器门禁结果 **GO**；该结果仅作历史证据。当前正式版身份不由该脚本自动改变。
- Windows 10 VM当前为可选门禁，未验证不会单独阻止0.1.0 RC，但必须如实报告。
