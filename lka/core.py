"""SQLite FTS5 unicode61 index and search."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

VCS_DIRS = {".git", ".hg", ".svn"}
NOTE_SUFFIXES = {".md", ".txt"}


class LkaError(Exception):
    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def db_path_or_default(db_path: Path | None) -> Path:
    if db_path is None:
        return Path.cwd() / ".lka" / "index.sqlite"
    return Path(db_path)


def connect(db_path: Path, *, create: bool) -> sqlite3.Connection:
    if not create and not db_path.exists():
        raise LkaError(
            "尚未建立索引。请先运行: python3 -m lka index <目录>。这不是检索评测失败。",
            2,
        )
    if create:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_fts5(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS documents (
          id INTEGER PRIMARY KEY,
          root TEXT NOT NULL,
          path TEXT NOT NULL,
          body TEXT NOT NULL,
          UNIQUE (root, path)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
          body,
          content='documents',
          content_rowid='id',
          tokenize='unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
          INSERT INTO documents_fts(rowid, body) VALUES (new.id, new.body);
        END;

        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
          INSERT INTO documents_fts(documents_fts, rowid, body)
          VALUES ('delete', old.id, old.body);
        END;

        CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
          INSERT INTO documents_fts(documents_fts, rowid, body)
          VALUES ('delete', old.id, old.body);
          INSERT INTO documents_fts(rowid, body) VALUES (new.id, new.body);
        END;
        """
    )
    return conn


def ensure_fts5(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.lka_fts5_probe USING fts5(x)")
    except sqlite3.OperationalError as exc:
        text = str(exc).lower()
        if "fts5" in text or "no such module" in text:
            raise LkaError(
                f"基础环境错误: 当前 SQLite 无法创建 FTS5 表（{exc}）。这不是检索评测失败。",
                2,
            ) from exc
        raise
    conn.execute("DROP TABLE temp.lka_fts5_probe")


def fts_tokens(text: str) -> list[str]:
    """Tokens produced by FTS5 unicode61, in first-seen order."""
    conn = sqlite3.connect(":memory:")
    try:
        ensure_fts5(conn)
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(body, tokenize='unicode61')")
        conn.execute("INSERT INTO t(body) VALUES (?)", (text,))
        conn.execute("CREATE VIRTUAL TABLE tv USING fts5vocab(t, 'row')")
        terms: list[str] = []
        for (term,) in conn.execute("SELECT term FROM tv"):
            if term not in terms:
                terms.append(term)
        return terms
    finally:
        conn.close()


def match_query(text: str) -> str | None:
    """Bindable FTS5 expression. User text is never concatenated into SQL."""
    terms = fts_tokens(text)
    if not terms:
        return None
    return " ".join('"' + term.replace('"', '""') + '"' for term in terms)


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _read_utf8(path: Path, rel: str) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise LkaError(f"无法读取文件: {rel}（{exc.strerror}）", 2) from exc
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LkaError(f"编码错误: {rel} 不是合法 UTF-8（{exc}）", 2) from exc


def read_notes(dir_arg: str) -> tuple[Path, list[tuple[str, str]]]:
    raw = Path(dir_arg).expanduser()
    if not raw.exists() or not raw.is_dir():
        raise LkaError("指定路径不是可读目录。", 2)
    root = raw.resolve()
    docs: list[tuple[str, str]] = []

    def walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise LkaError(f"无法读取目录中的条目（{exc.strerror}）。", 2) from exc
        for entry in entries:
            name = entry.name
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if name.startswith(".") or name in VCS_DIRS:
                    continue
                resolved = entry.resolve()
                if not _inside(root, resolved):
                    raise LkaError(f"拒绝读取目录外路径: {name}", 2)
                walk(entry)
                continue
            if not entry.is_file():
                continue
            if name.startswith("."):
                continue
            if entry.suffix.lower() not in NOTE_SUFFIXES:
                continue
            resolved = entry.resolve()
            if not _inside(root, resolved):
                raise LkaError(f"拒绝读取目录外路径: {name}", 2)
            rel = entry.relative_to(root).as_posix()
            docs.append((rel, _read_utf8(entry, rel)))

    walk(root)
    return root, docs


def index_directory(dir_arg: str, db_path: Path) -> dict[str, int]:
    root, docs = read_notes(dir_arg)
    conn = connect(db_path, create=True)
    try:
        return sync_documents(conn, str(root), docs)
    finally:
        conn.close()


def sync_documents(
    conn: sqlite3.Connection, root: str, docs: list[tuple[str, str]]
) -> dict[str, int]:
    with conn:
        existing = {
            row["path"]: (row["id"], row["body"])
            for row in conn.execute(
                "SELECT id, path, body FROM documents WHERE root = ?",
                (root,),
            )
        }
        seen: set[str] = set()
        inserted = updated = unchanged = 0
        for rel, body in docs:
            seen.add(rel)
            current = existing.get(rel)
            if current is None:
                conn.execute(
                    "INSERT INTO documents(root, path, body) VALUES (?, ?, ?)",
                    (root, rel, body),
                )
                inserted += 1
            elif current[1] != body:
                conn.execute(
                    "UPDATE documents SET body = ? WHERE id = ?",
                    (body, current[0]),
                )
                updated += 1
            else:
                unchanged += 1
        deleted = 0
        for rel, (doc_id, _body) in existing.items():
            if rel not in seen:
                conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
                deleted += 1
        total = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
    return {
        "inserted": inserted,
        "updated": updated,
        "deleted": deleted,
        "unchanged": unchanged,
        "documents": total,
    }


def format_stats(stats: dict[str, int]) -> str:
    return (
        "inserted={inserted} updated={updated} deleted={deleted} "
        "unchanged={unchanged} documents={documents}\n"
    ).format(**stats)


def display_path(root: str, rel: str) -> str:
    full = Path(root) / rel
    try:
        return full.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return rel


def _find_token(body: str, token: str) -> int:
    folded = token.casefold()
    if not folded:
        return -1
    for index in range(len(body)):
        if body[index:].casefold().startswith(folded):
            return index
    return -1


def make_snippet(body: str, tokens: list[str]) -> str:
    best: tuple[int, int] | None = None
    for length in sorted({len(token) for token in tokens}, reverse=True):
        places: list[tuple[int, int]] = []
        for token in tokens:
            if len(token) != length:
                continue
            pos = _find_token(body, token)
            if pos >= 0:
                places.append((pos, length))
        if places:
            best = min(places)
            break
    if best is None:
        return body.replace("\n", " ")[:60]
    pos, length = best
    start = max(0, pos - 24)
    end = min(len(body), pos + length + 24)
    frag = body[start:end]
    rel = pos - start
    marked = frag[:rel] + "[" + frag[rel : rel + length] + "]" + frag[rel + length :]
    marked = marked.replace("\n", " ")
    if start > 0:
        marked = "…" + marked
    if end < len(body):
        marked = marked + "…"
    return marked


@dataclass
class Hit:
    rank: int
    bm25: float
    path: str
    snippet: str


def search_hits(conn: sqlite3.Connection, query: str, *, limit: int = 10) -> list[Hit]:
    if limit < 1:
        raise LkaError("limit 必须是正整数。", 2)
    expr = match_query(query)
    if expr is None:
        return []
    tokens = fts_tokens(query)
    rows = conn.execute(
        """
        SELECT d.root, d.path, d.body, bm25(documents_fts) AS score
        FROM documents_fts
        JOIN documents d ON d.id = documents_fts.rowid
        WHERE documents_fts MATCH ?
        ORDER BY bm25(documents_fts) ASC, d.path ASC
        LIMIT ?
        """,
        (expr, limit),
    ).fetchall()
    hits: list[Hit] = []
    for rank, row in enumerate(rows, start=1):
        hits.append(
            Hit(
                rank=rank,
                bm25=float(row["score"]),
                path=display_path(row["root"], row["path"]),
                snippet=make_snippet(row["body"], tokens),
            )
        )
    return hits


def format_hits(hits: list[Hit]) -> str:
    if not hits:
        return "（无结果）\n"
    lines: list[str] = []
    for hit in hits:
        lines.append(f"rank={hit.rank} bm25={hit.bm25:.6f} path={hit.path}")
        lines.append(hit.snippet)
    return "\n".join(lines) + "\n"
