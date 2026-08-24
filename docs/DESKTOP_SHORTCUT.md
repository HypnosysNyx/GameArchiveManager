# GameArchiveManager 桌面快捷方式说明

项目不会自动修改桌面。用户可以按下面步骤手动创建快捷方式。

## 创建方法

1. 打开 GameArchiveManager 项目目录。
2. 找到 `start_game_archive_manager.bat`。
3. 右键该文件，选择“显示更多选项”。
4. 选择“发送到” → “桌面快捷方式”。
5. 可以在桌面上把快捷方式重命名为 `GameArchiveManager`。

以后双击桌面快捷方式即可启动程序，不需要先打开 PowerShell。

## 快捷方式属性检查

如果需要手动创建快捷方式，请把“目标”设置为项目中的启动脚本完整路径，例如：

```text
C:\GameArchiveManager\start_game_archive_manager.bat
```

把“起始位置”设置为项目根目录，例如：

```text
C:\GameArchiveManager
```

实际路径应以用户保存项目的位置为准。不要把快捷方式目标直接设置为 `main.py`。

## 注意事项

- 启动脚本会自动进入项目目录并调用 Windows Python 启动器。
- 需要先安装 Python，并确保命令 `py` 可用。
- 外部解压工具可以放入项目的 `tools` 目录，或安装在支持的常见路径。
- 启动脚本不会下载、安装或移动任何解压工具。
- 命令窗口会等待用户按键后关闭，便于查看错误信息。
