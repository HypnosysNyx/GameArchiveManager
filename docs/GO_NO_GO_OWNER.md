# RC2 所有者 Go/No-Go 短包

核对时间：2026-09-02（Asia/Shanghai）。

## 结论

**现在不能称为正式版。** 当前身份仍为 `0.1.0 Release Candidate`。RC 门禁为 **GO**，仅表示具备所有者最终评审条件，不授权 push、tag、替换资产或正式发布。

## Git 与工作树

- 本地 `main` 相对 `origin/main` 超前 1；该提交尚未推送。
- 本轮新增未提交 `docs/GO_NO_GO_OWNER.md`，并在 `docs/CURRENT_STATUS.md` 增加一行 next action。
- 本轮未 push、未创建 tag、未改 VM、`BUILD_TYPE` 或发布门禁。

## 发布前剩余的所有者决策

1. 将隐私清理后的本地提交通过 push 或 PR 送出；送出后才可取得新的 Windows CI / CodeQL 结果。
2. 公开 RC2 ZIP 内嵌旧 EXE 哈希文档的处置：保留原资产并附勘误，或重新打包为新资产并发布新的 ZIP SHA-256。
3. 是否改为正式 Release（包括修改 `BUILD_TYPE`）；这必须在上述事项完成后另行明确批准。

## 默认建议

**不 push、不重打包、不改 `BUILD_TYPE`**，直到仓库所有者在本轮明确授权。原始 RC2 ZIP 保持不变。

## 依据与风险

- 发布审计：[`RELEASE_AUDIT_2026-08-28.md`](RELEASE_AUDIT_2026-08-28.md)。
- 机器状态：[`../project_state.json`](../project_state.json)，其中 Win11 必选门禁已关闭；Windows 10 是可选、未测试项。
- 原始 ZIP 内旧文档哈希与实际 EXE 哈希不一致；这不否定已测二进制，但在替换资产或正式发布前必须显式决策。
