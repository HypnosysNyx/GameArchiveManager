# GameArchiveManager — Grok Build 接管入口

> 本文件是 Grok Build 接管本项目时的第一阅读入口。不要依赖聊天记录推断项目状态。

## 1. 当前权威状态

- 项目：GameArchiveManager
- 版本：`0.1.0`
- 构建类型：`Release Candidate`
- 阶段：RC / Core Feature Freeze
- 自动测试最低基线：224（当前已核验 228）
- 本次交接前验证：224 tests / PASS；2026-08-24 源码核验 228 tests / PASS
- 项目治理校验：PASS
- 真实样本 Test Game 1–6：项目状态记录为 PASS
- Clean Windows 11 VM：`NOT VERIFIED`
- 当前发布结论：`NO-GO`

`version.py` 是应用版本信息的唯一代码权威来源；`project_state.json` 是项目状态、测试基线和 Release Gate 的机器可读权威来源。不要把 RC 改成正式 Release，也不要把尚未完成的 VM 检查标成通过。

## 2. 接管后的强制启动协议

在修改任何文件前，按顺序执行：

1. 阅读本文件。
2. 阅读 `project_state.json`。
3. 阅读 `docs/CURRENT_STATUS.md`。
4. 阅读 `docs/PROJECT_HANDOFF.md`。
5. 阅读 `docs/KNOWN_ISSUES.md`、`docs/DECISIONS.md`、`docs/DEBUGGING_PROTOCOL.md`。
6. 阅读 `docs/RC_SMOKE_TEST.md` 和 `docs/RC_BUILD_NOTES.md`。
7. 运行：

```powershell
py -B -m unittest discover -s tests -v
py scripts/verify_project_state.py
py scripts/rc_readiness.py
```

预期结果：

- 测试不少于 224 项并全部通过；外部工具相关跳过必须逐项说明，不能当作真实工具验证通过。
- `verify_project_state.py` 返回 PASS。
- `rc_readiness.py` 在 Clean Windows 11 VM 完成前应返回 `NO-GO`，这是正确状态，不是需要绕过的失败。

如果实际结果与以上基线不同：停止发布动作，按 `docs/DEBUGGING_PROTOCOL.md` 做只读定位，先报告差异和证据，再决定是否修改。

## 3. 当前唯一发布主线

继续完成干净 Windows 11 VM 冒烟测试，按照 `docs/RC_SMOKE_TEST.md` 收集证据。当前不是新增功能阶段。

已经获得但尚不足以关闭门禁的部分证据：

- 已在独立 VirtualBox Windows 11 虚拟机启动 RC EXE，VM 中没有可用 Python 开发环境。
- EXE 能启动并显示 `0.1.0 / Release Candidate`。
- 无外部工具时不会崩溃；ZIP 执行返回结构化 `TOOL_NOT_FOUND`。
- 两次可比冷启动到菜单约 3.07 秒和 3.06 秒。
- 单独复制 7-Zip 26.02 的 `7z.exe` 不构成有效工具部署；该版本还需要同目录 `7z.dll`。这属于测试工具准备问题，不是已证明的业务代码缺陷。
- VirtualBox 共享剪贴板不稳定；曾使用只读虚拟光盘和键盘扫描码完成操作。
- VM 会偶发停在 `Stopping`，此前在确认 Guest 已进入 OFF/DESTROYING 后才强制结束卡住的 `VirtualBoxVM` 进程。

仍需完成并持久化的关键证据：

- 合法完整部署的 7-Zip、WinRAR CLI、LZ4 检测与真实执行。
- 普通 ZIP/RAR/7Z/LZ4、分卷、密码包、JPEG embedded RAR、中文路径、重复运行和中断恢复。
- 输出、history、log、report、源文件 SHA256、不泄露密码、不扫描历史输出、不留下非预期临时目录。
- 完成后才可将 `project_state.json` 的 `clean_windows_11_vm` 更新为 true，并重新运行三条门禁命令。

## 4. Feature Freeze 与禁止事项

除非真实测试提供可复现证据并确认是明确 bug，否则不得修改：

- `analyzer/archive_analyzer.py`
- `analyzer/embedded_detector.py`
- `pipeline/`
- `extractor/`
- `recovery/password_recovery.py`
- `organizer/game_content_classifier.py`
- `organizer/final_content_resolver.py`
- `cleanup/cleanup_manager.py`

同时遵守：

- 不新增功能，不为了让报告变绿而放宽测试或安全检查。
- 不自动下载或安装 7-Zip、WinRAR、LZ4。
- 不删除、覆盖或修改用户源压缩包。
- 不在日志、报告、history、命令行或交接材料中记录明文密码。
- 不把 Linux/宿主机测试冒充 Clean Windows 11 VM 证据。
- 任何失败先按三层正确性报告：Extraction correctness、Content correctness、Safety/performance correctness。

## 5. 外部工具与构建边界

外部解压工具不属于项目源码，也不应无许可捆绑。ToolManager 负责从显式 Settings/config、项目 `tools/`、常见安装目录和 PATH 发现并验证工具。

本交接包特意不包含：

- 7-Zip、WinRAR、LZ4 二进制及其库文件
- `.vm_gate` 虚拟机材料和受控密码测试夹具
- 运行日志、history 数据和用户配置
- 构建虚拟环境、build/dist 产物、缓存
- Git 元数据

RC 构建物需要按 `docs/RC_BUILD_NOTES.md` 在目标环境重新生成或从经过校验的独立发布渠道传递。

## 6. 当前已知构建证据

最近一次本机 RC 验证构建记录：

- RC ZIP SHA256：`90945C67D5FC4F2EF618D158E63A5D1815815872AB339A11F011CB12BA9ABF08`
- RC EXE SHA256（2026-08-24 缺卷修复后重建）：`9BFDE4CE679EDF819AB4CB19E7E29FC6B4D5206134BA63D5739C6F87E27D0AD0`
- 此前 2026-08-22 EXE SHA256：`F825C3859C85B1FDA9BE5809E1DB6BA447FC3478316870EEB2813F46AF472490`

这些哈希仅用于识别此前测试过的构建，不表示 Clean Windows 11 VM Gate 已完成；本源码交接包不携带该二进制构建物。

## 7. 接管报告格式

Grok Build 完成首次只读接管检查后，应先报告：

1. 实际读取的权威文件。
2. 实际运行的三条命令和结果。
3. 测试总数、失败数、跳过数及跳过原因。
4. Feature Freeze 是否保持。
5. Release Gate 当前值。
6. 与本文件基线的任何差异。
7. 下一步只执行 Clean Windows 11 VM Gate，或说明为什么必须先阻断。

在这份报告完成前，不要修改业务代码。
