# Documentation

在仓库根目录运行。本机核实的命令是 `python3`（Python 3.12.3，SQLite 3.45.1，已启用 FTS5）。

```bash
python3 -m lka index examples
python3 -m lka search unicode61
python3 -m lka eval-baseline
```

退出码：

- `0`：index 或 search 完成。search 没有命中也是 0
- `1`：`eval-baseline` 至少有一条期望文档没有进前 k
- `2`：没有 FTS5、目录无效、文件不是 UTF-8、或还没有索引。这不是检索失败

已知红评测是 `bike`（bicycle 的同义改写）和 `茶香`（token `茶香很浓` 的子串）。分词、同义词和向量都还没有做。这不是完整助手，也不表示检索质量达标。

路径相对于当前工作目录；在仓库根目录索引 `examples` 时，结果路径形如 `examples/bicycle.md`。
