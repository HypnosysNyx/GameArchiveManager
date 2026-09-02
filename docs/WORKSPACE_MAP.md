# GameArchiveManager 工作区地图

最后整理：2026-08-28（Asia/Shanghai）

## 唯一入口

今后所有 agent 和人工维护统一从下面的路径进入项目：

```text
C:\Users\<redacted>\Documents\GameArchiveManager
```

该路径是一个 Windows 目录联接，固定指向实际 Git 工作树：

```text
C:\Users\<redacted>\Documents\GameArchiveManager0.1.0
```

不要再在 GrokWork、Documents\Codex 或带“副本”的目录中继续开发。它们的原始内容已经集中到主工作树的 `.project_archive`，仅供追溯。

## 集中后的目录

```text
.project_archive/
├── agents/
│   ├── grok/                 Grok 的交接、脚本、VM 记录、夹具和构建包
│   └── codex-online-20260824/ Codex 与 Antigravity 工作树、输出和协作记录
├── evidence/
│   └── GameArchiveManager_Evidence/ 真实样本证据
└── legacy/
    └── GameArchiveManager0.1.0-copy-20260721/ 早期无 Git 副本
```

`.project_archive/` 已加入 `.gitignore`：集中保存本地历史痕迹，但不会把数 GB 的证据、二进制工具、嵌套 Git 仓库或构建产物提交到产品仓库。

## 使用规则

1. 产品代码、正式文档和测试只修改唯一入口下的主 Git 工作树。
2. `.project_archive` 中的工作树和资料保持只读语义；需要吸收其中内容时，先复制到主仓库的正式位置并通过测试。
3. 新的 VM 截图、临时构建和 agent 交接材料直接放入主工作树既有的 `.vm_gate`、`handoff_output` 或 `.project_archive` 分类，不再创建新的项目副本。
4. 发布状态以 `project_state.json`、`docs/CURRENT_STATUS.md` 和主仓库 Git 历史为准。

## 整理前来源映射

| 原位置 | 集中后位置 | 说明 |
| --- | --- | --- |
| `C:\Users\<redacted>\GrokWork\projects\GameArchiveManager` | `.project_archive\agents\grok` | Grok 工作区 |
| `C:\Users\<redacted>\Documents\Codex\2026-08-24\gamearchivemanager-https-github-com-hypnosysnyx-gamearchivemanager` | `.project_archive\agents\codex-online-20260824` | Codex、Antigravity 与在线发布审计工作区 |
| `C:\Users\<redacted>\Documents\GameArchiveManager_Evidence` | `.project_archive\evidence\GameArchiveManager_Evidence` | 真实样本证据 |
| `C:\Users\<redacted>\Documents\GameArchiveManager0.1.0 - 副本` | `.project_archive\legacy\GameArchiveManager0.1.0-copy-20260721` | 早期源码副本 |

`C:\Users\<redacted>\Documents\GameArchiveManager` 本身不是重复副本，因此保留为稳定、无版本号的唯一入口。
