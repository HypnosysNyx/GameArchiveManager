# Linux 安装、运行与更新

Linux 与 Windows 使用同一套 Python 源码、GUI 和 CLI，没有单独的 Linux 分支。
本文面向原生 Ubuntu 24.04 LTS，使用发行版 Python 3.12；最低要求 Python 3.10。
GUI 需要图形桌面和 Tk，CLI 可在无桌面的终端运行。

当前跨平台预发布版本为 `0.3.0rc1`（Git 标签 `v0.3.0-rc.1`）。Linux wheel 和 Windows 便携版均在对应 GitHub Releases 页面提供。尚未上传 PyPI；从 Git 安装要求目标提交已包含 Linux 适配及打包文件，不能从旧 v0.2.0 标签获取这些功能。

## 安装系统依赖

```bash
sudo apt update
sudo apt install 7zip lz4 python3-tk python3-venv pipx git
pipx ensurepath
```

重新打开终端，让 pipx 命令目录进入 PATH。使用 `/usr/bin/python3`，确保与
`python3-tk` 匹配。不要使用 `sudo pip` 或 `--break-system-packages`。

7-Zip 使用原生 `7z` 或 `7zz`，LZ4 使用原生 `lz4`；无需 Wine 或 Windows EXE。
Linux 不运行 Windows 工具下载/安装流程。缺少工具时用系统包管理器安装后重启应用。
较旧 Ubuntu 的包名和 7-Zip 版本可能不同，本文不把它们视为已验证平台。

## 从现有本地源码安装和更新

适合当前含未提交改动的工作树。在已有项目根目录执行，不要为更新另建工程副本：

```bash
pipx install --python /usr/bin/python3 .
game-archive-manager-gui
# 或启动交互式命令行，输入 Q 退出：
game-archive-manager
```

两个入口由同一个包提供，安装后可从任意目录运行。GUI 需要当前图形会话；
CLI 没有 `--help`/`--version` 参数接口。

更新时先关闭应用，取得或编辑所需源码，再在同一个项目根目录执行：

```bash
pipx install --force --python /usr/bin/python3 .
pipx list
```

这是非 editable 安装：源码修改后需重新安装。`--force` 重装相同版本号下的变更；
仅运行 `pipx upgrade` 可能因版本未变化而保留旧代码。
不要用 Git reset/clean 丢弃本地修改来更新。安装和更新不迁移或清理用户数据。

## 从 Git 来源安装和更新

仅当远端 `main` 已包含本轮打包文件时使用：

```bash
pipx install --python /usr/bin/python3 'git+https://github.com/HypnosysNyx/GameArchiveManager.git@main'
```

Git 安装只有远端提交，不包含当前工作树未提交改动。`main` 会变化；可重复安装时，
将 `@main` 换为已审阅且包含 Linux 打包文件的完整提交 SHA。
不要假定历史标签包含这些文件。

关闭应用后重新安装最新远端源码，也适用于版本号未变化时：

```bash
pipx install --force --python /usr/bin/python3 'git+https://github.com/HypnosysNyx/GameArchiveManager.git@main'
pipx list
```

来源提供更高版本号时也可用 `pipx upgrade game-archive-manager`。
切换本地/Git 来源时明确传入所需来源。系统 Python 被替换后，可用
`pipx reinstall game-archive-manager --python /usr/bin/python3` 重建环境；
它会再次访问原安装来源，该来源必须仍可用。
`pipx uninstall game-archive-manager` 卸载程序，应用数据和输出单独保留。

来源安装和更新行为参见 pipx 的[官方示例](https://pipx.pypa.io/latest/reference/examples.html)
及[命令参考](https://pipx.pypa.io/stable/reference/cli.html)。

## 直接运行共享源码

```bash
bash scripts/linux_run.sh --gui
bash scripts/linux_run.sh --cli
# 省略选项默认启动 GUI，可指定解释器：
PYTHON=/usr/bin/python3 bash scripts/linux_run.sh
```

脚本定位自己的项目根目录，不要求调用者当前位于该目录，不安装依赖或下载工具。
运行时只有 Python 标准库依赖，系统 Tk、7-Zip 和 LZ4 另行安装。

## 数据与密码库

| 数据 | 默认位置 |
| --- | --- |
| 配置（含外观和语言） | `${XDG_CONFIG_HOME:-$HOME/.config}/GameArchiveManager/config.json` |
| GUI 窗口位置 | `${XDG_DATA_HOME:-$HOME/.local/share}/GameArchiveManager/window_place.json` |
| 历史记录 | `${XDG_DATA_HOME:-$HOME/.local/share}/GameArchiveManager/history/task_history.json` |
| 密码库后端标记 | `${XDG_DATA_HOME:-$HOME/.local/share}/GameArchiveManager/passwords.json` |
| 日志 | `${XDG_STATE_HOME:-$HOME/.local/state}/GameArchiveManager/logs` |
| 解压交付 | 任务目录下的 `GameArchive_Output`，已有目录时递增命名 |

XDG 变量须为绝对路径；空值/相对值回退到用户默认目录。Linux 不读取源码根目录的
Windows `config.json`。更新 pipx 环境不覆盖这些 XDG 文件。源归档、历史输出及用户目录
不会因安装/更新被删除；日志可能含完整任务路径，应按私人文件保管。

Linux 持久密码库通过桌面 Secret Service 保存，密码经管道传给 `secret-tool`，
不写入 JSON 标记。需要保存密码时可安装：

```bash
sudo apt install libsecret-tools gnome-keyring
```

还需当前桌面的 D-Bus 会话和已解锁的 Secret Service；仅安装包不保证服务可用。
没有密码库的新安装即使无服务也能启动，在当前进程中使用密码；持久保存会明确失败，
不会降级到明文文件。已有标记但服务不可用、锁定或数据异常时会拒绝读取，
应恢复原密钥环，不要删除标记或复制 Windows DPAPI 密码文件作为修复。

## 开发验证与边界

```bash
sudo apt install xvfb xauth
xvfb-run -a /usr/bin/python3 -B -m unittest tests.test_linux_support tests.test_password_candidate_boundaries tests.test_platform_default_policy tests.test_platform_filter_boundaries tests.test_release_build_config -v
xvfb-run -a /usr/bin/python3 -B scripts/linux_smoke.py
```

合成 smoke 使用临时 HOME/XDG 生成小型 7z，执行原生 `7z/7zz t`，通过共享
`GameArchiveService` 解压交付，对比内容/CRC 和源 SHA-256，并在 Xvfb 下实例化 GUI。
它不使用真实资源或真实桌面密码库。

Linux CI 使用 Ubuntu 系统 Python 和 apt Tk，运行 Linux 适用模块的专项测试、源码 smoke、wheel 构建；Windows 专属 DPAPI 与安装器用例由 Windows CI 全量测试覆盖。
再在新的 venv 中安装 wheel。在源码目录之外用隔离 Python 执行
`linux_smoke.py --installed`，检查导入位置、安装内容、CLI 启动及 GUI 短暂事件循环。
构建和测试不上传产物或发布版本。

这些检查不等同于真实资源回归、桌面视觉验收、真实密钥环持久化测试或干净机器发布验收。
归档处理限制仍见 [KNOWN_ISSUES.md](KNOWN_ISSUES.md)。
