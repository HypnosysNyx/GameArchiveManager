# RC2 虚拟机与清单 14 任务状态

最后更新：2026-08-28 21:13 +08:00

## 结论

- **清单 14 的 Codex 任务已经正常结束，目前没有继续运行。** `rc2_item14_codex.md` 已于 2026-08-28 13:06:59 +08:00 完整写出，结论为 `PASS`，并记录三阶段中断取证及中断后重跑成功。宿主机进程检查未发现仍在运行的清单 14 `codex.exe` 或 `dispatch.py`；现有本仓库相关进程仅属于本次状态检查任务。综合现有证据，清单 14 是完成后退出，没有被强杀的迹象。
- **`Win11-Sandbox` 已结束运行，目前没有运行中的 VM。** 21:05 后先发送 ACPI 电源按钮，但来宾未响应；随后在已退出 GameArchiveManager、哈希证据已落盘的空闲 `cmd.exe` 中执行 Windows 自身的 `shutdown /s /t 0`。屏幕显示“正在关机”，VirtualBox 日志记录来宾服务正常结束、`RUNNING -> POWERING_OFF -> OFF`、统计结束和虚拟键盘卸载。来宾已关机后，VirtualBox GUI 外壳仍长时间卡在 `stopping`；经用户明确批准，只强制结束命令行精确匹配该 VM 的 3 个残留 `VirtualBoxVM.exe`。因此 VirtualBox 管理状态最终显示 `aborted`，但该标记发生在日志已经记录 VM `OFF` 之后，不代表测试过程中或来宾运行中被强杀。
- **可以并行运行不同工作目录的 Codex 任务，但不能让两套任务同时争用同一台 VM 的键盘注入。** 同一台 `Win11-Sandbox` 的 `keyboardputstring` / `keyboardputscancode` 属于共享输入通道；并行注入会造成按键交错、窗口焦点错位和取证失真。需要使用该 VM 的任务应串行执行，或分别使用不同 VM。

## 宿主机进程观察

检查时，本仓库路径相关的 `dispatch.py` / `codex.exe` 进程树只有正在生成本报告的状态检查任务（启动于 2026-08-28 13:20:15–13:20:16 +08:00）。未发现命令行属于清单 14 执行任务的存活进程。本状态检查任务写完报告后会自行退出。

关机收尾后，`VBoxManage list runningvms` 为空；命令行匹配 `Win11-Sandbox` UUID 的 `VirtualBoxVM.exe` 数量为 0。没有终止 `VBoxSVC`、其他 VM 或项目进程。

## 关机证据

- 来宾关机命令：Windows `shutdown /s /t 0`。
- VirtualBox 日志：`Changing the VM state from 'RUNNING' to 'POWERING_OFF'`，随后 `POWERING_OFF` 到 `OFF`。
- 最终运行列表：空。
- 最终残留 VM 进程：0。
- VDI 最后写入时间：2026-08-28 21:07:05 +08:00；残留 GUI 进程于 21:12:57 +08:00 清理。
- 未执行 `VBoxManage controlvm poweroff`，未在来宾仍运行时强制断电。

## 范围确认

- 未翻门禁，未修改 `project_state.json`。
- 未修改产品代码。
- 清单 14 执行阶段未关闭或控制 VM；本次后续收尾在用户明确批准后正常关闭来宾，并在来宾已经 OFF 后清理卡住的 VirtualBox GUI 外壳。
- 未运行测试。
- 未 git push。
