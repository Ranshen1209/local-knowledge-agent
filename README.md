# 本地笔记词法 baseline

这是一个本地个人笔记的**词法 baseline**，不是完整智能助手。它只用 SQLite FTS5 的 `unicode61` 做整词匹配和 bm25 排序，没有同义词、没有中文分词、没有向量，也不接 LLM。

`evals/baseline.json` 里有意留下真实未命中。评测变红是在暴露这个局限，不是宣称检索质量达标。

## 环境

只使用 Python 标准库（`sqlite3`、`argparse`、`unittest`），没有第三方运行依赖。

本机核实：

- Python 3.12.3
- SQLite 3.45.1，编译选项包含 `ENABLE_FTS5`

其他版本没有验证。启动时如果建不起 FTS5 表，命令会以退出码 2 报基础环境错误并退出。那不是检索评测失败。

本机没有名为 `python` 的命令，下面用 `python3`。

## 命令

在仓库根目录执行：

```bash
python3 -m lka index examples
python3 -m lka search unicode61
python3 -m lka eval-baseline
```

`index` 必须带目录。它只读取该目录里合法 UTF-8 的 `.md` 和 `.txt`，包含子目录，但不会越过这个目录。不跟随符号链接，不进入 `.git`、`.hg`、`.svn` 和隐藏目录，不索引点文件。非法 UTF-8 会指出相对路径并失败，不会静默跳过。再 index 同一目录不会插入重复文档。

`search` 把查询当普通文本：先用 unicode61 取出 token，再生成引号短语，并用 SQL 占位符绑定。引号、`AND`/`OR`/`NOT` 和 `*` 不会被当成 MATCH 语法。没有命中时打印「（无结果）」，退出码 0。

数据库在当前目录的 `.lka/index.sqlite`，已加入 `.gitignore`，不会提交。

## 排序

FTS5 的 `bm25()` 把常见 BM25 乘了 -1，所以**更好的命中分值更小、更负**。官方写法是 `ORDER BY bm25(ft)`，默认升序，最好的排在前面。本机 SQLite 3.45.1 上，`unicode61` 出现更多次的笔记分值更负，排名第 1。实现使用 `ORDER BY bm25(documents_fts) ASC`。

## 这次实际失败的原因

两条失败都是对真实索引跑出来的，不是写死的异常。

1. `bike` 期望 `examples/bicycle.md`。笔记里的词是 `bicycle`。`unicode61` 只做整词匹配，没有同义词，两个 token 对不上，结果为空。
2. `茶香` 期望 `examples/longjing-continuous.md`。正文里的 token 是整段 `茶香很浓`（逗号才切开）。`茶香` 只是这个 token 的子串，MATCH 不命中。同一篇笔记用完整 token `茶香很浓` 可以命中；分开写的 `龙井` 也可以命中 `examples/longjing-spaced.md`。

正例 `unicode61` 会命中，并且重复次数更多的 `examples/fts5-baseline.md` 排在第 1。

未做，也不在这次范围内：中文分词、同义词、向量。没有用 trigram 去掩盖上面的失败。FTS5 trigram 的全文查询里，少于 3 个 Unicode 字符的子串不命中；那是官方行为，这里没有启用 trigram。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | index 或 search 完成；search 无命中也是 0 |
| 1 | `eval-baseline` 有期望文档没有进前 k |
| 2 | 没有 FTS5、目录无效、文件不是 UTF-8，或还没索引。不是检索失败 |

正常测试：

```bash
python3 -m unittest
```

这组测试必须通过。它不包含上面那条已知红评测。

## 非目标

界面、登录、部署、LLM、联网采集、embedding、自动日报都不做。

## 来源

- SQLite FTS5：<https://sqlite.org/fts5.html>
- Python sqlite3：<https://docs.python.org/3/library/sqlite3.html>
