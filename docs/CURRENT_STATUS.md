# Current Status – 0.1.0 Release

Last verified: `2026-08-28`
App version: `0.1.0`  
Build: `Release`
Test baseline: `py -B -m unittest discover -s tests -v` → `Ran 234 tests — OK (skipped=7)`
Current P0: 无。`mixed_selected_and_ambiguous_content_silent_nondelivery`已完成自动与真实P0修复验证。  
Current next action: 维护正式版文案与公开内容隐私审查；历史 RC2 ZIP 保留为归档，不作为当前下载对象，也不重打包或替换已发布资产。Windows 10 仍为可选未测。

## Current baseline

- 自动测试：`py -B -m unittest discover -s tests -v`
- 当前实际结果：`Ran 234 tests — OK (skipped=7)`。
- 当前状态：0.1.0 Release；自动化、本机构建和正式版交付的干净 Win11 VM 复验通过。Windows 10 可选未测。
- 核心冻结：是。当前不是新功能扩展阶段。

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
- RC2 的 Win11 门禁已关闭；仍保持 `BUILD_TYPE=Release Candidate`，只有完成最终发布清单并得到仓库所有者明确批准后才可评估正式 Release。

## Known real samples

- 测试游戏3：通过。7z分卷→5GB JPEG→加密RAR5→密码恢复→Unity游戏，修复后ORPHANED_TEMP=0。
- 测试游戏4：PASS。原始真实样本已证明PC+Android独立交付、源完整性、无save-only交付和cleanup安全。2026-08-19 Evidence Closure另用项目外Controlled Real-Sample Copy证明既有Ren'Py游戏根建立INITIAL_SCAN boundary，用真实outer的确定性LZ4解码派生inner，证明`PC.rar + PC.rar.lz4`强关系只执行canonical inner并只交付1份PC内容。
- 测试游戏5：已修复并真实交付。DeliveryUnit折叠4节点技术链，输出B994000共209文件、1,710,573,415 bytes。
- 测试游戏6：早期两次分别因无候选和错误候选耗尽而FAILED；最新runtime history（2026-08-15 15:12）为COMPLETED并交付`PC/VR`。P0修复后只读TaskAnalyzer得到1个合法候选，历史技术边界不再进入候选。

## Password recovery status

- **NEXT-1 / `manual_password_recovery_after_exhaustion`**：RESOLVED。自动候选耗尽后，CLI提供I/S/C闭环；人工密码默认可见输入（中文输入法可用），明文不进日志/报告/history。业务层只接收可选回调。
- 人工密码只存在内存；只有实际成功的密码进入`SessionPasswordStore`，程序退出即消失。
- `save_passwords`与`auto_try_password`仍是未接线的legacy设置，不代表存在持久密码库。
- **NEXT-2 / `cli_session_loop`**：COMPLETED（2026-08-15）。CLI启动后保持一个`GameArchiveService`会话，可连续新建单任务或批量任务、查看最近结果/工具/设置并主动退出。Settings、ToolManager、HistoryStorage、ApplicationService和SessionPasswordStore为会话级；Task、RuntimeTracker、Pipeline/Guard、report和task candidates每次重建。

## Do not do

- 不要新增GUI或自动下载/安装工具。
- 不要把leaf当final content。
- 不要把EXE当唯一游戏证据。
- 不要仅按文件名、目录名或大小去重。
- 不要删除或修改源归档。
- 不要覆盖GameArchive_Output旧结果。
- 不要自动删除未知历史目录。
- 不要记录密码明文或完整含密码命令行。
- 不要为了测试通过降低结构/CRC/SHA256验证强度。
- 不要仅凭 clean VM 门禁通过就标正式 Release；仍需完成发布清单和仓库所有者明确批准。

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
- `scripts/rc_readiness.py`：RC2 的必选机器门禁已同步，预期返回 **GO**。GO 表示 RC 发布门禁具备评审条件，不自动改变 Release Candidate 身份，也不授权 push、tag 或发布正式 Release。
- Windows 10 VM当前为可选门禁，未验证不会单独阻止0.1.0 RC，但必须如实报告。
