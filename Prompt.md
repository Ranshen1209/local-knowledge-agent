# Prompt

做本地个人笔记的词法 baseline，不是完整助手。

- 命令只有 `index <目录>`、`search <查询>`、`eval-baseline`
- Python 标准库 sqlite3，FTS5 unicode61，bm25 越负越好，排名第 1 是最好命中
- 查询当普通文本，用占位符和 tokenizer 转义，避免 MATCH 语法错误
- 只索引显式目录内合法 UTF-8 的 `.md`/`.txt`；不跟随符号链接，不读隐藏目录、点文件和 `.git`/`.hg`/`.svn`
- `eval-baseline` 里的同义查询和中文子串查询必须保持真实未命中
- 不做界面、登录、部署、LLM、联网采集、同义词表或中文分词
