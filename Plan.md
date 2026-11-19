# Plan

本次只做词法 baseline。

1. 用一张外部内容表保存路径和正文，FTS5 表 `tokenize=unicode61`，触发器保持索引同步。
2. 同一目录再次 index 时按绝对根路径和相对路径去重；正文没变就不写；目录里消失的文件从该次索引范围删除。
3. 查询先交给 unicode61 取 token，再变成引号短语并用 `?` 绑定。没有 token 时直接空结果，不把原文送进 MATCH。
4. 排序用 `ORDER BY bm25(documents_fts) ASC`。分值越负越好。
5. 固定评测放在 `evals/baseline.json`，语料是 `notes/` 里的三篇原文。正例必须真命中；`aspirin` 必须真未命中。评测失败只反映检索结果，缺 FTS5 或未索引用退出码 2。
6. `python3 -m unittest` 不跑这条已知红评测。

不做 Web、导入导出、研究记录、定时任务和付费 API。
