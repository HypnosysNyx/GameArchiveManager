# 可直接复制给 Grok Build 的第一条指令

我已上传 `GameArchiveManager 0.1.0 RC` 自包含交接包。请你正式接管这个项目。

严格执行以下要求：

1. 首先完整阅读根目录 `GROK_START_HERE.md`，它是本次跨 AI 接管入口。
2. 然后按其中的 Agent Startup Protocol 阅读 `project_state.json` 与指定治理文档。
3. 在修改任何文件前，运行并报告：
   - `py -B -m unittest discover -s tests -v`
   - `py scripts/verify_project_state.py`
   - `py scripts/rc_readiness.py`
4. 当前权威基线是：0.1.0 / Release Candidate、Feature Freeze、测试最低 224、P0 为空、真实样本 1–6 已记录 PASS、Clean Windows 11 VM 仍为 false、RC 当前应为 NO-GO。
5. 不得把外部工具测试 skip 当成真实验证通过，不得把宿主机或 Linux 测试当成干净 Windows 11 VM 证据。
6. 不得新增功能。冻结核心只有在真实 VM 测试证明存在明确、可复现 bug 后，才能按 `DEBUGGING_PROTOCOL.md` 单独评估是否修改。
7. 不自动下载/安装工具，不删除或覆盖用户文件，不记录密码，不擅自把 RC 标成正式 Release。
8. 首次回复只做“接管一致性检查”：列出读取内容、命令结果、基线差异、Release Gate 和下一步；在我确认前不要修改业务代码。

接管检查通过后，继续当前唯一主线：按照 `docs/RC_SMOKE_TEST.md` 完成 Clean Windows 11 VM 最终门禁并保存可审计证据。不要重复已经完成且有证据的工作。
