# GameArchiveManager 统一接管入口

本文件面向任何后续维护者或 AI agent，不依赖旧聊天记录。最后核对：2026-08-28（Asia/Shanghai）。

## 1. 只打开这个目录

```text
C:\Users\<redacted>\Documents\GameArchiveManager
```

它是固定入口，指向当前 Git 主工作树 `GameArchiveManager0.1.0`。不要去 GrokWork、Documents\Codex、旧副本或 `.project_archive` 中继续开发。历史材料的位置见 [`docs/WORKSPACE_MAP.md`](docs/WORKSPACE_MAP.md)。

## 2. 五分钟接管检查

先执行只读检查：

```powershell
git status --short --branch
py -B scripts/verify_project_state.py
py -B scripts/rc_readiness.py
```

然后按顺序阅读：

1. 本文件；
2. [`project_state.json`](project_state.json)；
3. [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md)；
4. [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)；
5. [`docs/RC_SMOKE_TEST.md`](docs/RC_SMOKE_TEST.md)；
6. 需要理解架构时再读 [`docs/PROJECT_HANDOFF.md`](docs/PROJECT_HANDOFF.md) 和 [`docs/DEBUGGING_PROTOCOL.md`](docs/DEBUGGING_PROTOCOL.md)。

如果代码、Git 状态、机器状态文件和叙述文档冲突，不要猜测，也不要自动采用日期最新的文件。先核对原始测试或 VM 证据，并把冲突标成 `NEEDS_VERIFICATION`。

## 3. 当前真实状态

- 产品：GameArchiveManager `0.1.0` 正式 Release，当前发布身份为 `0.1.0 / Release`。
- Git 基线：`main` 的已提交 HEAD 为 `85a95bc`；远端发布动作不属于默认授权范围。
- 自动化测试：2026-08-28 实跑 `234 tests — OK`。
- 项目治理验证：2026-08-28 实跑 `Overall: PASS`。
- `project_state.json` 已在 2026-08-28 归并证据后将 `clean_windows_11_vm=true`；`scripts/rc_readiness.py` 的预期结果为 `GO`。
- 真实样本回归、密码泄漏检查和源文件完整性策略均已通过现有治理检查。
- Windows 10 VM 是可选未验证项；不得谎报为 PASS。

## 4. 当前唯一工作主线

RC2 的干净 Windows 11 必选门禁已经归并并关闭：

1. [`rc2_smoke_codex.md`](rc2_smoke_codex.md) 覆盖清单 1–13、15–17；其中原始 `BLOCKED` 是清单 14 尚未补做时的阶段性结论。
2. [`rc2_item14_codex.md`](rc2_item14_codex.md) 已用宿主机 GUI 扫描码完成 EXTRACTING、SCANNING、VALIDATING 三阶段真实 Ctrl+C，源哈希未变，中断后重跑成功。
3. [`rc2_vm_status.md`](rc2_vm_status.md) 记录任务结束和来宾正常关机；VirtualBox GUI 外壳只在日志已经记录 VM `OFF` 后才经用户批准清理。
4. 被测原始 ZIP `BA3A9ADD…` 保持不变；其内附带旧 Markdown 写错 EXE 哈希，源码权威文档已明确实际 EXE 为 `67DF840B…`。不得声称原 ZIP 内文档已经被修改。

当前正式版已发布；历史 RC2 文档与资产仅作归档参考，不作为当前下载对象。后续维护以正式版状态、公开内容隐私审查和已知问题记录为准；不在本次工作中 push、tag 或重打包。`cli_startup_latency_regression` 仍是非阻断 P1，等待进一步真实用户环境证据。

## 5. 当前工作树注意事项

接管时工作树可能包含尚未提交的 RC2 验收文档。2026-08-28 整理时已有：

```text
docs/KNOWN_ISSUES.md
docs/RC_BUILD_NOTES.md
docs/RC_SMOKE_TEST.md
rc2_item14_codex.md
rc2_smoke_codex.md
rc2_vm_status.md
```

这些属于已有工作，不得丢弃、reset 或覆盖。先阅读 `git diff`，再做增量归并。工作区集中化新增的 `AGENTS.md`、`START_HERE.md`、`docs/WORKSPACE_MAP.md` 和 `.gitignore` 修改同样可能尚未提交。

## 6. 验证与完成标准

代码或权威状态变更完成后至少执行：

```powershell
py -B -m unittest discover -s tests -p "test_*.py" -v
py -B scripts/verify_project_state.py
py -B scripts/rc_readiness.py
```

接手者结束工作前必须留下：

- 当前结论与下一步；
- 修改文件清单；
- 实际执行的验证命令和结果；
- 尚未解决的风险或证据缺口；
- 是否触及发布、push、tag、VM 或外部工具状态。

未经用户明确授权，不得 push、merge、rebase、reset、clean、tag、发布 Release、上传产物或修改仓库设置。
