# GameArchiveManager 安全设计

## 基本原则

- 默认不删除、移动或重命名用户输入文件。
- 分析、安全检查和执行计划先于外部工具调用。
- 输出路径由统一生成器选择安全唯一名称；已有目录不会被覆盖或删除。
- 危险清理必须先扫描，再由调用方显式确认删除。
- 密码不写入报告、历史或任务日志。

## 输入安全检查

ArchiveAnalyzer 只读取少量文件头，识别 ZIP、RAR、7Z 真实格式，不信任扩展名，也不修改原文件。

ArchiveSafetyChecker 使用 `max_archive_size_mb` 限制单个压缩包大小。无法读取文件信息或超过限制时，ExecutionStrategy 返回不可执行计划，不调用 Extractor。

平台过滤默认关闭。只有用户明确启用 `ignore_android` 或 `ignore_AZ` 时，平台规则才会检查任务内容根以下的文件名和父目录组件。Android/安卓按明确标记识别；AZ 按独立标签 token 识别，不匹配普通英文单词内部的 `az`。跳过不是删除，记录仍保存在任务或 Pipeline 结果中。

## 解压前内容检查

ArchiveContentInspector 当前使用 Python 标准库读取 ZIP 的：

- 文件数量
- ZIP 元数据声明的预计解压大小
- 内部路径列表
- 绝对路径、Windows 驱动器路径和 `..` 父目录穿越

ArchiveSafetyChecker 使用 `max_extracted_files` 和 `max_total_extracted_size_mb` 判断是否生成可执行计划。危险内部路径会直接阻断。

当前不能可靠读取 RAR 和 7Z 的内部目录，只会记录能力警告并继续原有流程。ZIP 元数据也可能被恶意伪造，所以解压前检查不能代替解压后检查。

## 解压执行保护

Extractor Dispatcher 当前可调度 SevenZipExtractor、WinRarExtractor 和 Lz4Extractor；RAR 首选 7-Zip，并只在允许回退的工具失败下尝试 WinRAR。LZ4 以及 LZ4→RAR 复合容器使用独立适配器和复合流程。所有适配器遵守以下保护：

- 所选外部工具必须存在并通过版本命令验证。
- 输入必须是实际文件。
- 统一输出路径生成器使用 `_2`、`_3` 等后缀避开已有目录。
- 7-Zip 使用 `-aos` 参数避免覆盖同名文件。
- 外部进程受 `extraction_timeout_seconds` 限制。
- 原压缩包保持不变。

## 解压后检查

ExtractionSafetyChecker 在每次成功结果返回前检查：

- 输出路径存在且为目录
- 实际文件数量
- 实际文件总大小
- 目录符号链接不被递归跟随

超过限制时，Coordinator 把该次操作标记为失败，但不会删除已经生成的文件。这意味着解压后检查可以发现问题，却不能避免问题文件在检查前占用磁盘。

## 密码保护

- Scanner 只把真实空文件夹名称作为密码候选，不把普通文件名当作候选。
- PasswordScorer 只排序，不删除候选。
- PasswordRecoveryEngine 和 PasswordRetryExecutor 有有限尝试次数。
- PasswordRetryExecutor 的执行记录只保存状态和原因，不保存对应密码。
- HistoryStorage 对摘要中的常见密码表达进行遮盖。
- GameLogger 对 `password=...`、`pwd=...`、中文密码表达和 7-Zip `-p...` 参数进行脱敏，并截断长消息。
- 当前没有数据库密码存储，Settings 的 `save_passwords` 尚未实现。

## 清理策略

任务运行期间，RuntimeTracker 精确记录本次运行实际创建的内部目录。正常完成并成功交付后，ApplicationService 只把这些“本次运行拥有”的技术目录交给 CleanupManager 授权；未知历史目录不会因为名称相似而被自动清理。超时、取消、异常、交付待选择或安全验证拒绝时，目录默认保留并记录为 `ORPHANED_TEMP`。

CleanupManager 另保留旧式的只读建议扫描，可发现以下候选，但扫描本身不会授权自动清理：

- 名称包含 `_password_attempt_` 的目录
- 名称包含 `failed_extraction`、`extraction_failed` 或以 `_failed` 结尾的目录
- 真实空目录

只有路径先通过本次扫描或 `authorize_owned()` 的授权，并显式调用 `delete(path)`，才会永久删除。删除前会检查：

- 路径是本次扫描得到的候选
- 路径位于任务输出目录内部
- 路径不是任务根目录或输出根目录
- 路径不是符号链接
- 路径不是输入压缩包，也不包含已登记的输入压缩包

CleanupManager 不使用回收站。输入压缩包、任务根、`GameArchive_Output`、最终交付路径和其他受保护路径不能被删除。调用方必须完整传入输入压缩包列表；人工清理必须在用户确认后调用 `delete()`。

## 为什么不自动删除

失败目录可能包含可恢复文件、诊断线索或用户唯一的数据；空文件夹名称可能是密码线索；安全检查超限不代表所有输出都无价值。自动判断这些内容“无用”存在误删风险，因此当前系统选择保留数据，将清理决定交给用户。

## 已知限制

- RAR、7Z 尚无可靠的解压前内容检查。
- 解压后超限时不会自动释放磁盘空间。
- 文件可能在检查完成后被其他进程改变。
- RAR、7Z 的解压前检查能力弱于 ZIP，仍需依赖工具、运行限制和解压后检查。
- 日志仍会记录任务路径，路径本身可能包含隐私信息。
