# Implement

包名 `lka`，只依赖 Python 标准库。

- `lka/core.py`：FTS5 检测、目录遍历、写入、unicode61 查询和 bm25 检索
- `lka/evaluate.py`：读取 `evals/baseline.json`，对当前索引做真实查询，并按 token 比较写出未命中原因
- `lka/cli.py`：`index`、`search`、`eval-baseline`
- 验收语料在 `notes/`，正文与固定用例逐字一致
- 数据库是当前目录的 `.lka/index.sqlite`，已 gitignore，不提交

未命中原因是现场算的：查询 token 与目标正文 token 没有交集，记为 `no_shared_token`；查询里的汉字是某个更长 token 的子串，记为 `cjk_glue`。没有把失败写死。
