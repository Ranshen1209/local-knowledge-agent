"""Fixed lexical eval. Misses are real search results, not raised fakes."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from lka.core import LkaError, display_path, fts_tokens, search_hits

EVAL_FILE = Path(__file__).resolve().parents[1] / "evals" / "baseline.json"
ANALYSIS = {
    "hit": "命中",
    "no_shared_token": "无共享 token（同义或改写，unicode61 无法匹配）",
    "cjk_glue": "查询是更长汉字 token 的子串",
    "ranked_out": "文档能匹配但排名超出 k",
    "missing_doc": "期望文档不在索引中",
}


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def load_eval(path: Path = EVAL_FILE) -> tuple[int, list[dict[str, str]]]:
    if not path.is_file():
        raise LkaError("找不到评测文件 evals/baseline.json。这不是检索评测失败。", 2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LkaError(f"评测文件不是合法 JSON（{exc}）。", 2) from exc
    if not isinstance(data, dict) or "k" not in data or "cases" not in data:
        raise LkaError("评测文件格式错误: 需要 k 和 cases。", 2)
    k = data["k"]
    cases = data["cases"]
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise LkaError("评测文件格式错误: k 必须是正整数。", 2)
    if not isinstance(cases, list) or not cases:
        raise LkaError("评测文件格式错误: cases 不能为空。", 2)
    parsed: list[dict[str, str]] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or "query" not in case or "expected_doc" not in case:
            raise LkaError(f"评测文件格式错误: 第 {index} 条缺少 query 或 expected_doc。", 2)
        query = case["query"]
        expected = case["expected_doc"]
        if not isinstance(query, str) or not isinstance(expected, str):
            raise LkaError(f"评测文件格式错误: 第 {index} 条的 query 和 expected_doc 必须是字符串。", 2)
        case_id = case.get("id", f"case-{index}")
        if not isinstance(case_id, str):
            raise LkaError(f"评测文件格式错误: 第 {index} 条的 id 必须是字符串。", 2)
        parsed.append({"id": case_id, "query": query, "expected_doc": expected})
    return k, parsed


def _find_body(conn: sqlite3.Connection, expected: str) -> str | None:
    for row in conn.execute("SELECT root, path, body FROM documents"):
        shown = display_path(row["root"], row["path"])
        if shown == expected or row["path"] == expected:
            return row["body"]
    return None


def analyze(conn: sqlite3.Connection, query: str, expected: str, rank: int | None, k: int) -> str:
    if rank is not None and rank <= k:
        return "hit"
    if rank is not None and rank > k:
        return "ranked_out"
    body = _find_body(conn, expected)
    if body is None:
        return "missing_doc"
    query_tokens = fts_tokens(query)
    doc_tokens = fts_tokens(body)
    if any(token in doc_tokens for token in query_tokens):
        return "ranked_out"
    for token in query_tokens:
        if not _has_cjk(token):
            continue
        if any(token != doc and token in doc for doc in doc_tokens):
            return "cjk_glue"
    return "no_shared_token"


def run_eval(conn: sqlite3.Connection, path: Path = EVAL_FILE) -> tuple[int, str]:
    k, cases = load_eval(path)
    present = sum(1 for case in cases if _find_body(conn, case["expected_doc"]) is not None)
    if present == 0:
        raise LkaError(
            "索引里没有任何评测期望文档。请在仓库根目录执行: python3 -m lka index examples。这不是检索评测失败。",
            2,
        )
    blocks: list[str] = []
    hits = 0
    misses: list[str] = []
    for case in cases:
        found = search_hits(conn, case["query"], limit=max(k, 50))
        rank = next((hit.rank for hit in found if hit.path == case["expected_doc"]), None)
        success = rank is not None and rank <= k
        if success:
            hits += 1
            label = "命中"
        else:
            label = "未命中"
        kind = analyze(conn, case["query"], case["expected_doc"], rank, k)
        if not success:
            misses.append(kind)
        if found:
            actual = "; ".join(
                f"rank={hit.rank} bm25={hit.bm25:.6f} path={hit.path}" for hit in found[:5]
            )
        else:
            actual = "（无）"
        score = 1 if success else 0
        shown_rank = str(rank) if rank is not None and rank <= max(k, 50) else "未命中"
        lines = [
            f"[{label}] {case['id']}",
            f"  query={case['query']}",
            f"  expected={case['expected_doc']} expected_rank={shown_rank}",
            f"  actual={actual}",
            f"  hit@{k}={score} recall@{k}={score}",
        ]
        if not success:
            lines.append(f"  analysis={kind} {ANALYSIS[kind]}")
        blocks.append("\n".join(lines))
    total = len(cases)
    missed = total - hits
    rate = hits / total
    counts: dict[str, int] = {}
    for kind in misses:
        counts[kind] = counts.get(kind, 0) + 1
    summary = (
        f"总结: cases={total} hits={hits} misses={missed} "
        f"Hit@{k}={rate:.3f} Recall@{k}={rate:.3f}"
    )
    if counts:
        detail = " ".join(f"{name}={count}" for name, count in sorted(counts.items()))
        summary += f"\n未命中分析: {detail}"
    text = "\n".join(blocks) + "\n" + summary + "\n"
    return (0 if missed == 0 else 1), text
