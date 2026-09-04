# Official VM item 14 — guest hash and three-phase Ctrl+C

结论：**PASS**（仅依据已核截图）。

- VM：`Win11-Sandbox`；guest 用户：`sandbox`。
- guest 内使用正式 EXE；EXE SHA-256 前缀：`62D404EA…`。ZIP/EXE 哈希不同是正常的 PyInstaller onedir 现象。
- 可见正式 `0.1.0 Release` 的三阶段截图：
  - EXTRACTING：`.vm_gate/official_62d404_item14_extracting.png`（p_08，16:35，`big.zip`）；另有 `.vm_gate/official_62d404_item14_scanning.png`（a_15，18:19，`scan.zip` 最后一行仍为 `SCANNING`）。
  - SCANNING：`.vm_gate/official_62d404_item14_scanning.png`（a_15，18:19，`scan.zip` 最后一行仍为 `SCANNING`）。
  - VALIDATING：`.vm_gate/official_62d404_item14_validating.png`（18:10，`scan.zip`）。
- 中断截图：
  - EXTRACTING：`.vm_gate/official_62d404_item14_extracting_interrupt.png`（17:04，仍在 `EXTRACTING`）。
  - SCANNING：`.vm_gate/official_62d404_item14_scanning_interrupt.png`（10:37，`^C`、`FAILED KeyboardInterrupt`、`scan_extracted_9`，任务被中断）。
  - VALIDATING：`.vm_gate/official_62d404_item14_validating_interrupt.png`（10:38，`KeyboardInterrupt`、`scan_extracted_10`）。
- Ctrl+C 由 guest 内 `timeout + WScript.Shell.SendKeys('^c')` 产生；不记录 VBox scancode。失败阶段字段显示为 `APPLICATION`，残留目录为解压中的 `scan.zip`；不将其写成 `COMPLETED`。

未使用后续启动到 `COMPLETED` 的截图作为阶段或中断证据；未声称 ZIP 内容被修改。VM 关闭及提交动作不属于本项结论。
