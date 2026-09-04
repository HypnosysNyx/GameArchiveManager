# RC2 所有者 Go/No-Go 短包

核对时间：2026-09-02（Asia/Shanghai）。

## 结论

**当前正式版已发布。** 当前身份为 `0.1.0 / Release`。RC 门禁 **GO** 与本文件其余 RC 决策均为历史记录。

## Git 与工作树

- 本地 `main` 与 `origin/main` 对齐；本轮勘误改动尚未推送。
- 本轮新增 `docs/RC2_ASSET_ERRATA.md`，并更新 README、状态和所有者决策记录。
- 本轮未 push、未创建 tag、未改 VM、`BUILD_TYPE` 或发布门禁。

## 已落地的所有者决定

1. 保留原始 RC2 ZIP，发布勘误说明；不重打包、不替换 GitHub Release 资产。
2. 不修改 `BUILD_TYPE`，不创建 `v0.1.0` 正式 tag，不发布正式 Release。
3. 由编排方提交包含本次勘误文档、README 链接和状态说明的 PR；本地执行者不 push。

## 默认建议

**不重打包、不改 `BUILD_TYPE`、不打正式 tag**。原始 RC2 ZIP 保持不变；本轮交付目标是勘误文档和 PR。

## 依据与风险

- 发布审计：[`RELEASE_AUDIT_2026-08-28.md`](RELEASE_AUDIT_2026-08-28.md)。
- 机器状态：[`../project_state.json`](../project_state.json)，其中 Win11 必选门禁已关闭；Windows 10 是可选、未测试项。
- 原始 ZIP 内旧文档哈希与实际 EXE 哈希不一致；这不否定已测二进制，但在替换资产或正式发布前必须显式决策。
