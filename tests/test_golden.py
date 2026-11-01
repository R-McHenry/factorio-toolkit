"""tools/golden.py, the 2.1 golden check: its corpus, a snapshot of one small file (stable and free
of the tree's path), and compare's verdicts. The whole corpus takes ~30 s, so it is not run here."""
import importlib.util
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PATH = os.path.join(ROOT, "tools", "golden.py")
_SPEC = importlib.util.spec_from_file_location("golden", _PATH)
golden = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(golden)


def _write(d, rel, text):
    p = os.path.join(d, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class GoldenTest(unittest.TestCase):
    def test_the_corpus(self):
        rels = [rel for rel, _root, _ in golden.corpus(ROOT)]
        self.assertEqual(rels, sorted(rels))
        for src in golden.SOURCES:
            self.assertTrue(any(r.startswith(src + "/") for r in rels), src)
        self.assertIn("kickoff/template/game/world.fk", rels)
        # the frozen live design: its ENTRY names world.fk alone (cells, kit, plant are imports)
        frozen = [r for r in rels if r.startswith("tests/golden/")]
        self.assertEqual(frozen, ["tests/golden/live-20261030/world.fk",
                                  "tests/golden/live-20261101/world.fk"])
        self.assertFalse(any("/out/" in r for r in rels))

    def test_a_snapshot_is_stable_and_has_no_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "a"), os.path.join(tmp, "b")
            for d in (a, b):
                n, _sec = golden.snapshot(ROOT, d, only="examples/gears.fk", quiet=True)
                self.assertEqual(n, 1)
            with open(os.path.join(a, "agent", "docs", "examples", "gears.fk.txt"),
                      encoding="utf-8") as fh:
                text = fh.read()
            for section in ("== elaborate", "== rates", "== layout"):
                self.assertIn(section, text)
            self.assertIn("status exit 0", text)
            self.assertRegex(text, r"\nm \S+ inst=")              # the machines
            self.assertRegex(text, r"\nn \S+ items=")             # the nets and their endpoints
            self.assertRegex(text, r"\ne \S+ \S+ ")               # the placements
            for form in (ROOT, ROOT.replace("\\", "/")):
                self.assertNotIn(form.lower(), text.lower())
            out = io.StringIO()
            self.assertEqual(golden.compare(a, b, out=out), 0)
            self.assertIn("1 of 1 identical", out.getvalue())

    def test_compare_masks_the_version_and_names_a_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "a"), os.path.join(tmp, "b")
            _write(a, golden.META, "version 2.0.43\n")
            _write(b, golden.META, "version 2.1.0\n")
            _write(a, "games/x/main.fk.txt", "rates main 2.0.43\nm a\n")
            _write(b, "games/x/main.fk.txt", "rates main 2.1.0\nm a\n")
            out = io.StringIO()
            self.assertEqual(golden.compare(a, b, out=out), 0)
            self.assertIn("identical  games/x/main.fk", out.getvalue())
            _write(b, "games/x/main.fk.txt", "rates main 2.1.0\nm b\n")
            _write(b, "games/y/new.fk.txt", "m c\n")
            out = io.StringIO()
            self.assertEqual(golden.compare(a, b, out=out), 2)
            text = out.getvalue()
            self.assertIn("different  games/x/main.fk", text)
            self.assertIn("-m a", text)
            self.assertIn("+m b", text)
            self.assertIn("only in B  games/y/new.fk", text)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(golden.main(["compare", a, b]), 1)


if __name__ == "__main__":
    unittest.main()
