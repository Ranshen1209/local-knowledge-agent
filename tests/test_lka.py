"""Green tests for index and search. The known-red eval is not run here."""

from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from lka.cli import main


class LkaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "index.sqlite"
        self.notes = self.root / "notes"
        self.notes.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        path = self.notes / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(list(args), db_path=self.db)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_index_search_rank_and_repeat(self) -> None:
        self.write("many.md", "alpha alpha alpha alpha alpha\n")
        self.write("one.md", "alpha sits among several other plain words here\n")
        self.write("sub/nested.md", "nestedtoken appears once\n")
        code, out, err = self.run_cli("index", str(self.notes))
        self.assertEqual(code, 0, err)
        self.assertIn("documents=3", out)
        code, first, err = self.run_cli("search", "alpha")
        self.assertEqual(code, 0, err)
        self.assertIn("rank=1", first.splitlines()[0])
        self.assertIn("path=many.md", first.splitlines()[0])
        self.assertLess(
            first.find("path=many.md"),
            first.find("path=one.md"),
        )
        code, nested, err = self.run_cli("search", "nestedtoken")
        self.assertEqual(code, 0, err)
        self.assertIn("path=sub/nested.md", nested)
        code, again, err = self.run_cli("index", str(self.notes))
        self.assertEqual(code, 0, err)
        self.assertIn("documents=3", again)
        self.assertIn("inserted=0", again)
        self.assertIn("unchanged=3", again)
        code, second, err = self.run_cli("search", "alpha")
        self.assertEqual(code, 0, err)
        self.assertEqual(first, second)

    def test_update_replaces_and_delete_removes(self) -> None:
        self.write("a.md", "oldword only\n")
        self.assertEqual(self.run_cli("index", str(self.notes))[0], 0)
        self.write("a.md", "newword only\n")
        code, out, err = self.run_cli("index", str(self.notes))
        self.assertEqual(code, 0, err)
        self.assertIn("updated=1", out)
        self.assertIn("documents=1", out)
        self.assertIn("（无结果）", self.run_cli("search", "oldword")[1])
        self.assertIn("path=a.md", self.run_cli("search", "newword")[1])
        (self.notes / "a.md").unlink()
        code, out, err = self.run_cli("index", str(self.notes))
        self.assertEqual(code, 0, err)
        self.assertIn("deleted=1", out)
        self.assertIn("documents=0", out)

    def test_quotes_and_operators_do_not_break_search(self) -> None:
        self.write("hello.md", "hello world stays indexed\n")
        self.assertEqual(self.run_cli("index", str(self.notes))[0], 0)
        queries = [
            '"',
            "'",
            '" OR 1=1; DROP TABLE documents; --',
            "***",
            "AND OR NOT NEAR",
            'hello:"world"',
            "(",
            ")",
            "\\",
            "tablet*",
            "(hello",
        ]
        for query in queries:
            code, _out, err = self.run_cli("search", query)
            self.assertEqual(code, 0, f"{query!r} -> {err}")
            self.assertNotIn("syntax error", err.lower())
            self.assertNotIn("traceback", err.lower())
        code, out, err = self.run_cli("search", '"hello"')
        self.assertEqual(code, 0, err)
        self.assertIn("path=hello.md", out)
        code, out, err = self.run_cli("search", "token-that-appears-nowhere-9f3c2a")
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "（无结果）\n")

    def test_bad_utf8_names_file_and_does_not_index(self) -> None:
        self.write("good.md", "goodword\n")
        (self.notes / "bad.txt").write_bytes(b"\xff\xfe not utf8")
        code, _out, err = self.run_cli("index", str(self.notes))
        self.assertEqual(code, 2)
        self.assertIn("bad.txt", err)
        self.assertIn("UTF-8", err)
        self.assertFalse(self.db.exists())

    def test_skips_hidden_vcs_symlink_and_outside(self) -> None:
        self.write("keep.md", "keepword\n")
        self.write(".secret.md", "dotword\n")
        hidden = self.notes / ".hidden"
        hidden.mkdir()
        (hidden / "note.md").write_text("hiddenword\n", encoding="utf-8")
        git_dir = self.notes / ".git"
        git_dir.mkdir()
        (git_dir / "objects.md").write_text("gitword\n", encoding="utf-8")
        outside = self.root / "outside.md"
        outside.write_text("outsideword\n", encoding="utf-8")
        (self.notes / "link.md").symlink_to(outside)
        linked_dir = self.root / "linked"
        linked_dir.mkdir()
        (linked_dir / "gone.md").write_text("linkedword\n", encoding="utf-8")
        (self.notes / "linked").symlink_to(linked_dir, target_is_directory=True)
        (self.notes / "skip.py").write_text("pythonword\n", encoding="utf-8")
        code, _out, err = self.run_cli("index", str(self.notes))
        self.assertEqual(code, 0, err)
        for word in ("dotword", "hiddenword", "gitword", "outsideword", "linkedword", "pythonword"):
            code, out, err = self.run_cli("search", word)
            self.assertEqual(code, 0, err)
            self.assertEqual(out, "（无结果）\n", word)
        code, out, err = self.run_cli("search", "keepword")
        self.assertIn("path=keep.md", out)
        self.assertEqual(out.count("path=keep.md"), 1)

    def test_search_before_index_is_not_an_empty_result(self) -> None:
        code, out, err = self.run_cli("search", "hello")
        self.assertEqual(code, 2)
        self.assertIn("尚未建立索引", err)
        self.assertIn("这不是检索评测失败", err)
        self.assertNotIn("无结果", out)

    def test_relative_path_and_hyphen_token(self) -> None:
        notes = self.root / "notes"
        (notes / "marker.md").write_text(
            "The retrieval baseline stores lexical tokens.\n"
            "Unique marker: xylophone-quartz-7741.\n",
            encoding="utf-8",
        )
        (notes / "calendar.txt").write_text(
            "Meeting notes about calendar export.\n"
            "The pain reliever tablet contains acetylsalicylic.\n",
            encoding="utf-8",
        )
        (notes / "zhongwen.md").write_text(
            "本地知识库只做词法索引不做语义扩展\n",
            encoding="utf-8",
        )
        previous = Path.cwd()
        os.chdir(self.root)
        try:
            code, _out, err = self.run_cli("index", "notes")
            self.assertEqual(code, 0, err)
            code, again, err = self.run_cli("index", "./notes")
            self.assertEqual(code, 0, err)
            self.assertIn("documents=3", again)
            self.assertIn("inserted=0", again)

            def search(query: str) -> tuple[int, str, str]:
                return self.run_cli("search", query)

            code, out, err = search("xylophone-quartz-7741")
            self.assertEqual(code, 0, err)
            self.assertEqual(out.count("notes/marker.md"), 1)
            self.assertNotIn("calendar.txt", out)
            self.assertNotIn("zhongwen.md", out)

            code, out, err = search("acetylsalicylic")
            self.assertEqual(code, 0, err)
            self.assertEqual(out.count("notes/calendar.txt"), 1)

            code, out, err = search("calendar")
            self.assertEqual(code, 0, err)
            self.assertEqual(out.count("notes/calendar.txt"), 1)

            for query in ('"xylophone-quartz-7741"', "(calendar", "reliever:", "tablet*"):
                code, out, err = search(query)
                self.assertEqual(code, 0, f"{query!r} {err}")
                self.assertNotIn("syntax error", err.lower())

            code, out, err = search("AND OR NOT")
            self.assertEqual(code, 0, err)
            self.assertEqual(out, "（无结果）\n")

            for query in ("aspirin", "schedule", "token-that-appears-nowhere-9f3c2a", "词法索引"):
                code, out, err = search(query)
                self.assertEqual(code, 0, err)
                self.assertEqual(out, "（无结果）\n", query)
                self.assertNotIn("syntax error", err.lower())

            code, out, err = search("本地知识库只做词法索引不做语义扩展")
            self.assertEqual(code, 0, err)
            self.assertIn("notes/zhongwen.md", out)
        finally:
            os.chdir(previous)

    def test_exact_cjk_token_hits(self) -> None:
        self.write("long.md", "今天泡了一杯龙井，茶香很浓。\n")
        self.assertEqual(self.run_cli("index", str(self.notes))[0], 0)
        code, out, err = self.run_cli("search", "茶香很浓")
        self.assertEqual(code, 0, err)
        self.assertIn("path=long.md", out)


if __name__ == "__main__":
    unittest.main()
