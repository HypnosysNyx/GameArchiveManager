# GameArchiveManager 配置说明

## config.json 位置与优先级

程序优先读取应用目录中的 `config.json`；若不存在，再检查 `%LOCALAPPDATA%\GameArchiveManager\config.json`。两处都不存在时使用 Settings 默认值，不会自动生成配置文件。

配置优先级：

```text
显式传入 Settings > config.json > Settings 默认值
```

配置在 CLI Session 启动、创建 GameArchiveService 时加载；运行期间修改文件不会自动刷新，需要重启程序。`main.py` 的 Fast Path 和完整菜单共用该服务实例，因此都会应用当前 Session 已加载的配置。

## 完整示例

```json
{
  "max_recursive_depth": 50,
  "max_archive_tasks": 1000,
  "max_initial_archive_tasks": 1000,
  "max_embedded_candidates": 20,
  "max_password_attempts": 20,
  "extraction_timeout_seconds": 300,
  "max_archive_size_mb": 10240,
  "max_extracted_files": 100000,
  "max_total_extracted_size_mb": 102400,
  "ignore_android": false,
  "ignore_AZ": false,
  "seven_zip_path": null,
  "winrar_path": null,
  "lz4_path": null
}
```

JSON 不支持注释。字段名称区分大小写，例如 `ignore_AZ` 中的 `AZ` 必须大写。

## config.json 支持字段

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `max_recursive_depth` | 非负整数 | `50` | 单条 Pipeline 可接受的最大递归深度；初始压缩包深度为 0 |
| `max_archive_tasks` | 正整数 | `1000` | 单条 Pipeline 最多接受的压缩包任务数量 |
| `max_initial_archive_tasks` | 正整数 | `1000` | 单个任务在 INITIAL_SCAN 阶段允许创建的初始压缩包候选上限 |
| `max_embedded_candidates` | 非负整数 | `20` | 单条 Pipeline 可接受的嵌入归档候选数量上限 |
| `max_password_attempts` | 0～100 整数 | `20` | 单个密码恢复流程的最大候选尝试次数 |
| `extraction_timeout_seconds` | 正整数 | `300` | 单次外部解压工具调用及相关受限验证的超时秒数 |
| `max_archive_size_mb` | 非负整数 | `10240` | 单个输入压缩包的大小上限，单位为 MiB（1024×1024 字节） |
| `max_extracted_files` | 非负整数或 `null` | `100000` | ZIP 预计文件数和所有格式实际输出文件数上限；`null` 表示显式关闭 |
| `max_total_extracted_size_mb` | 非负整数或 `null` | `102400` | ZIP 预计总大小和所有格式实际输出总大小上限；`null` 表示显式关闭 |
| `ignore_android` | 布尔值 | `false` | 设为 `true` 时才忽略名称包含 Android 或安卓的内容；默认保留 |
| `ignore_AZ` | 布尔值 | `false` | 设为 `true` 时才忽略内容相对路径组件中的明确AZ标签token；默认保留，且不匹配普通英文单词内部的az |
| `seven_zip_path` | 字符串路径或 `null` | `null` | 7-Zip 可执行文件路径；相对路径按 config.json 所在目录解析 |
| `winrar_path` | 字符串路径或 `null` | `null` | WinRAR `Rar.exe` 路径；相对路径按 config.json 所在目录解析 |
| `lz4_path` | 字符串路径或 `null` | `null` | `lz4.exe` 路径；相对路径按 config.json 所在目录解析 |

平台过滤是 opt-in：缺少字段时使用 `false`，而已有配置中明确写入的 `true` 会继续被 ConfigLoader 尊重。当前 CLI 没有交互式设置页，用户通过 `config.json` 设置。

ConfigLoader 对未知字段、错误类型和越界值发出 warning，忽略该字段并使用默认值。字符串形式的数字不会自动转换。

## Settings 中尚未开放给 JSON 的字段

以下字段存在于 Settings，但当前 ConfigLoader 不接受它们；写入 config.json 会产生“不支持的配置字段”警告：

| 字段 | 默认值 | 当前用途 |
| --- | --- | --- |
| `default_platform` | `"PC"` | 默认平台标记，当前执行流程未用于自动分类 |
| `delete_archives` | `false` | 删除策略预留；当前不会自动删除压缩包 |
| `delete_empty_folders` | `false` | 删除策略预留；当前不会自动删除空目录 |
| `save_passwords` | `false` | 密码保存预留，当前不保存密码 |
| `auto_try_password` | `false` | 历史密码策略预留，当前分析流程不加载历史密码 |

## 错误处理

- 文件不存在：安静地使用全部默认值。
- JSON 无法解析：发出 warning，并使用全部默认值。
- 顶层不是 JSON 对象：发出 warning，并使用全部默认值。
- 字段缺失：该字段使用默认值。
- 字段非法：只忽略该字段，其他合法字段仍会加载。
- ConfigLoader 不创建、覆盖或修复 config.json。
