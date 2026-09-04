# GameArchiveManager 0.1.0 RC2 发布审计

> 历史 RC 记录；当前正式版为 `v0.1.0`。

审计日期：2026-08-28（Asia/Shanghai）

## 结论

**RC 门禁：GO，可提交仓库所有者最终 Go/No-Go 评审。**

这不是正式发布授权。当前仍是 `0.1.0 Release Candidate`。本轮集中化与门禁归并已形成一个本地 Git 提交；未执行 push、tag、GitHub Release 修改或资产替换。

## 被审计对象

| 对象 | 身份 |
| --- | --- |
| Git 已提交基线 | `85a95bc3ae60aafe816650e8df367fe5b11a86c6` |
| 原始 RC2 ZIP | `BA3A9ADD4132EFF6188E3981C627400647941C572059F3D733347A3EE6823051` |
| ZIP 内实际 EXE | `67DF840B832EE9072375A3A267DF220DBB546FD61EF8B048EA8C8C6B17D20F71` |
| 构建身份 | `0.1.0 / Release Candidate` |
| 必选 VM | `Win11-Sandbox`，Windows 11 Home 25H2，普通用户，无可用 Python 开发环境 |

三个保存位置中的原始 RC2 ZIP 字节一致，均为 `BA3A9ADD…`。被测原包保持不变。

## 证据分层

### 自动化与治理

- `py -B -m unittest discover -s tests -q`：`Ran 234 tests`，`OK`。
- `py -B scripts/verify_project_state.py`：`Overall: PASS`。
- `py -B scripts/rc_readiness.py`：Clean Windows 11 VM `PASS`，Overall `GO`。
- `py -B scripts/check_markdown_links.py`：33 个 Markdown 文件通过。
- `git diff --check`：无空白错误；仅有 Windows 工作树 LF/CRLF 提示。

自动化覆盖格式识别、真实 ZIP/RAR/7Z/LZ4、伪装文件、递归与分卷、密码恢复、工具缺失、解压前后配额、路径穿越、符号链接/reparse point、平台过滤、交付去重、Cleanup 边界、历史编码、日志脱敏、配置优先级和持续 CLI 会话。

### 干净 Windows 11 VM

- 清单 1–13、15–17：[`../rc2_smoke_codex.md`](../rc2_smoke_codex.md)。
- 清单 14 三阶段真实 Ctrl+C 与中断后重跑：[`../rc2_item14_codex.md`](../rc2_item14_codex.md)。
- 来宾正常关机和宿主 GUI 残留清理：[`../rc2_vm_status.md`](../rc2_vm_status.md)。
- 截图和受控夹具：本地 `.vm_gate/`，由 `.gitignore` 排除，不进入公开源码包。

VM 已验证：无 Python 启动、版本身份、开发机路径独立、无工具结构化失败、7-Zip/WinRAR/LZ4 发现、普通格式、复合包、分卷与缺卷、密码成功/错误/跳过、JPEG 内嵌 RAR、中文路径、重复运行、最终输出隔离、日志/history、源 SHA-256、Cleanup 边界以及 EXTRACTING/SCANNING/VALIDATING 中断。

### 本机静态与启动检查

- 源码环境：Python 3.13.2，满足 Python 3.10+。
- `requirements.txt` 为 0 字节；唯一构建依赖为 `pyinstaller==6.21.0`。
- 向 `py -B main.py` 输入 `Q`：显示 `0.1.0 / Release Candidate` 和工具状态，退出码 0。
- Git 跟踪文件中没有 EXE、DLL、归档、ISO、私钥或日志文件；开发路径扫描只命中 `<redacted>` 示例。
- `.project_archive/`、`.vm_gate/`、构建目录、日志和交接二进制均由 `.gitignore` 排除。
- ConfigLoader 的白名单与 `docs/CONFIGURATION.md` 一致：14 个字段；未知/非法/越界值告警，缺失值回退默认，相对工具路径按配置目录解析，输出配额允许显式 `null`。
- GameLogger 和 HistoryStorage 的目录/写入异常不会被静默吞掉；ApplicationService 会记录历史保存异常类型。密码与外部错误输出受脱敏和长度限制。
- `docs/SECURITY.md` 已明确 `CleanupManager.delete()` 是不经过回收站的永久删除，并记录授权边界。

## RC2 内嵌文档哈希差异

原始 ZIP 内的旧 `RC_BUILD_NOTES.md` / `RC_SMOKE_TEST.md` 分别引用 `F5F2DD82…`、`9BFDE4CE…`，而 ZIP 内实际 EXE 是 `67DF840B…`。处理原则：

1. 原始被测 ZIP 不修改，保持 VM 证据可复核；
2. 当前源码权威文档记录实际 ZIP/EXE 身份并明确旧哈希来源；
3. 不声称原 ZIP 内文档已经正确；
4. 若重新打包文档，即使 EXE 不变，ZIP SHA-256 也会变化，必须视为新的交付资产并发布新校验值。

该差异不否定已测试二进制的身份或运行结果，但必须在任何资产替换或正式发布决策中显式处理。

## 已知非阻断项

- Windows 10 VM：可选、未测试。
- `cli_startup_latency_regression`：P1，开发机无法复现严重延迟；等待更多真实用户环境证据。
- EXE 未代码签名，SmartScreen 可能显示未知发布者。
- 控制台应用，无 GUI、安装程序、持久密码库、暂停/恢复或持久 Pipeline 队列。
- LZ4 CLI、7-Zip 和 WinRAR 不随项目捆绑。

## 发布前仍需完成

1. 在 push 或 PR 后取得新的 Windows CI / CodeQL 结果；本地提交本身不会产生远端 CI 证据。
2. 由仓库所有者决定如何处理公开 RC2 ZIP 的内嵌旧哈希文档：保留原资产并附勘误，或发布具有新 ZIP 哈希的替代资产。
3. 任何 push、tag、GitHub Release 修改、资产上传或正式 Release 身份变更均需仓库所有者明确批准。

在以上事项完成前，可以称为“RC 门禁 GO、等待最终发布操作”，不能称为“正式稳定版已经发布”。
