"""CLI: index, search, eval-baseline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lka.core import (
    LkaError,
    connect,
    db_path_or_default,
    format_hits,
    format_stats,
    index_directory,
    search_hits,
)
from lka.evaluate import run_eval


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lka", description="本地笔记的词法索引与检索")
    sub = parser.add_subparsers(dest="cmd", required=True)

    index_cmd = sub.add_parser("index", help="索引目录内的 .md/.txt")
    index_cmd.add_argument("directory")

    search_cmd = sub.add_parser("search", help="用 unicode61 词法检索")
    search_cmd.add_argument("query")

    sub.add_parser("eval-baseline", help="对固定评测跑真实检索")
    return parser


def main(argv: list[str] | None = None, db_path: Path | None = None) -> int:
    try:
        return _main(argv, db_path)
    except LkaError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


def _main(argv: list[str] | None, db_path: Path | None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    path = db_path_or_default(db_path)
    if args.cmd == "index":
        stats = index_directory(args.directory, path)
        sys.stdout.write(format_stats(stats))
        return 0
    if args.cmd == "search":
        conn = connect(path, create=False)
        try:
            hits = search_hits(conn, args.query)
        finally:
            conn.close()
        sys.stdout.write(format_hits(hits))
        return 0
    if args.cmd == "eval-baseline":
        conn = connect(path, create=False)
        try:
            code, text = run_eval(conn)
        finally:
            conn.close()
        sys.stdout.write(text)
        return code
    parser.error(f"未知命令: {args.cmd}")
    return 2
