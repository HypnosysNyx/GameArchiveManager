# GAM 独立机器接口

通过 `scripts/gam-cli --machine-json` 调用 `pan_machine.py`，交互入口仍为 `main.py`。GAM 独立运行，不依赖 `pan_shared`。

```sh
scripts/gam-cli --machine-json --input '<PLACEHOLDER>' \
  --output '<PLACEHOLDER>' --result '<PLACEHOLDER>'
```

输入为单个归档或平铺文件目录；输出必须是尚不存在的专属目录。结果采用 schema_version=1，成功退出 0，失败退出 1。成功结果包括 files、SHA256/size manifest、request 源快照和 source_retained。同一 request 可在核验输出后恢复；已有输出而没有可信完成记录会失败保留。

机器模式复用 GameArchiveService 的扫描、分卷分析、递归解压、安全限制和交付。禁用历史密码自动尝试、密码保存、源包删除和运行后清理，不使用人工密码回调。递归深度 12，归档数 100，总解压配额最多 4 GiB，并根据可用空间收紧。7-Zip 路径从 SEVEN_ZIP 读取，未设置时在 PATH 查找 7z、7zz、7za。

日志位于专属输出目录，结果不包含后端正文。密码、缺卷或交付等失败通过 failure_types 返回；通用异常只返回 error_type。

现存 `test_machine.py` 只有缺失输入和原子结果权限两项测试，均使用临时目录，不执行归档工具或网络请求；没有完整上游测试，也没有成功解压集成测试。本次整理的验证结果见仓库外构建记录。
