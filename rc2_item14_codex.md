# RC2 清单第 14 项：Win11-Sandbox 主机扫描码 Ctrl+C

## 结论

**PASS。** 当前 RC2 在 `EXTRACTING`、`SCANNING`、`VALIDATING` 三个阶段均由宿主机向 `Win11-Sandbox` GUI 会话发送真实 Ctrl+C 扫描码 `1d 2e ae 9d`。三次均由应用生成 `FAILED / KeyboardInterrupt` 报告并保留 `ORPHANED_TEMP`，不是强杀进程、关闭 VM、guestcontrol stdin 或用户手按。三个源压缩包 SHA256 均未改变；同目录重跑仍只发现 1 个初始压缩包并成功完成。

本次未修改 `project_state.json`，`clean_windows_11_vm` 仍为 `false`；未 push，未翻门禁。

## 环境与对象

| 项目 | 实际值 |
|---|---|
| 测试时间 | 2026-08-28 12:30–13:04 +08:00 |
| VM | `Win11-Sandbox`，可见 GUI 会话 |
| Guest OS | Windows 11 Home 25H2，10.0.26200.9168，x64 |
| Guest 用户 | `sandbox`，标准用户 |
| RC2 EXE | `C:\Users\sandbox\AppData\Local\Temp\rc2\GameArchiveManager-0.1.0-RC2\GameArchiveManager.exe` |
| EXE SHA256 | `67DF840B832EE9072375A3A267DF220DBB546FD61EF8B048EA8C8C6B17D20F71` |
| 新测试根 | `C:\Users\sandbox\AppData\Local\Temp\rc2_item14_20260828_1233` |
| 输入/中断通路 | `VBoxManage controlvm Win11-Sandbox keyboardputstring` + `keyboardputscancode 1d 2e ae 9d` |

交接路径最初只有 hash 正确的 EXE，缺少 `_internal\python312.dll` 等 onedir 同伴文件。通过可见 guest CMD 的 `robocopy`，从上一轮已核验的 `rc2_codex_20260827\GameArchiveManager-0.1.0-RC2` 恢复同一 RC2 onedir；恢复后重新计算的 EXE SHA256 仍为上述 `67DF840B…`。没有替换成 RC1 或旧 RC2 EXE。

## 源文件完整性

| 用例 | 源文件 | before SHA256 | after SHA256 | 结果 |
|---|---|---|---|---|
| EXTRACTING | `extracting\many.7z` | `4F8CA4EEC198DCBC188D0453353AB1FB3DBC12266CA4B35F137787DA30258B08` | 同 before | PASS |
| SCANNING | `scanning\outer.7z` | `9E566A0F12F6652F5850E7BF30EE30B788AB6E938366933AA77A4AA52C50A54F` | 同 before | PASS |
| VALIDATING | `validating\outer.7z` | `9E566A0F12F6652F5850E7BF30EE30B788AB6E938366933AA77A4AA52C50A54F` | 同 before | PASS |

before 截图：`.vm_gate/rc2_67df_item14_extract_hash_before.png`、`.vm_gate/rc2_67df_item14_scan_hash_before.png`、`.vm_gate/rc2_67df_item14_validate_hash_before.png`。
after 截图：`.vm_gate/rc2_67df_item14_extract_hash_after.png`、`.vm_gate/rc2_67df_item14_scan_hash_after.png`、`.vm_gate/rc2_67df_item14_validate_hash_after.png`。

## 三阶段中断结果

| 阶段 | 目标阶段证据 | Ctrl+C 后结果 | 残留记录 |
|---|---|---|---|
| EXTRACTING | `rc2_67df_item14_extraction_phase.png` 的最后进度为 `EXTRACTING` | `任务状态: FAILED`；摘要和错误类型均为 `KeyboardInterrupt` | `extracting\many_extracted`，`ORPHANED_TEMP` |
| SCANNING | `rc2_67df_item14_scanning_interrupt.png` 顶部保留中断时的 `当前阶段: SCANNING`，紧接应用失败报告 | `任务状态: FAILED`；摘要和错误类型均为 `KeyboardInterrupt` | `scanning\outer_extracted_2`，`ORPHANED_TEMP` |
| VALIDATING | `rc2_67df_item14_validating_nested2_phase_detected.png` 的最后进度为 `VALIDATING`（`inner39.zip`） | `任务状态: FAILED`；摘要和错误类型均为 `KeyboardInterrupt` | `validating\outer_extracted_2`，`ORPHANED_TEMP` |

对应失败报告截图：

- `.vm_gate/rc2_67df_item14_extraction_interrupt.png`
- `.vm_gate/rc2_67df_item14_scanning_interrupt.png`
- `.vm_gate/rc2_67df_item14_validating_nested2_interrupt_detected.png`

VALIDATING 使用 RC1 同类嵌套夹具：outer 解出 60 个 inner ZIP，流水线在第 39 个 inner ZIP 的 `VALIDATING` 阶段被捕获。宿主机截图匹配只负责确认可见阶段；确认后仍由 `VBoxManage ... keyboardputscancode 1d 2e ae 9d` 注入 Ctrl+C。

## 中断后重跑

| 阶段用例 | 初始预览 | 重跑结果 |
|---|---:|---|
| EXTRACTING | 1 | `COMPLETED`，成功 1、失败 0；输出安全递增为 `GameArchive_Output\many_2` |
| SCANNING | 1 | 61 个流水线压缩包全部成功、失败 0；输入 `61`（全部保留）后完成交付 |
| VALIDATING | 1 | 61 个流水线压缩包全部成功、失败 0；输入 `61`（全部保留）后完成交付 |

重跑证据：

- EXTRACTING：`.vm_gate/rc2_67df_item14_extraction_rerun_preview.png`、`.vm_gate/rc2_67df_item14_extraction_rerun.png`
- SCANNING：`.vm_gate/rc2_67df_item14_scanning_rerun_preview.png`、`.vm_gate/rc2_67df_item14_scanning_rerun.png`
- VALIDATING：`.vm_gate/rc2_67df_item14_validating_rerun_preview.png`、`.vm_gate/rc2_67df_item14_validating_rerun_status.png`、`.vm_gate/rc2_67df_item14_validating_rerun.png`

嵌套用例在交付选择前报告 `COMPLETED_NEEDS_SELECTION`，随后通过宿主机 `keyboardputstring` 选择“全部保留”；最终摘要为成功 61、失败 0。旧 `ORPHANED_TEMP` 未被误扫为新的初始任务，也未在取证期间手工删除。

## 范围确认

- 未使用 guestcontrol 重定向或管道 stdin。
- 未要求或使用用户键盘操作。
- 未强杀应用、VM 或 VirtualBox 进程。
- 未清理取证残留。
- 未修改业务代码、版本、构建类型或 release gate。
- 未 git push。
- 报告不含登录密码或测试密码。
