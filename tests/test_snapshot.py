"""2.1.19: a build reads its source as it began (fkcore.snapshot): the live run's labs paste was
laid from a world.fk edited under it (~4300k)."""
import os
import tempfile
import unittest

from fkcore import elaborate, snapshot


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.fk = os.path.join(self.dir, "w.fk")
        _write(self.fk, "a = Assembler<recipe=iron-gear-wheel>\n")

    def test_outside_a_build_the_disk_is_read(self):
        self.assertIn("iron-gear-wheel", snapshot.read(self.fk))
        _write(self.fk, "a = Assembler<recipe=copper-cable>\n")
        self.assertIn("copper-cable", snapshot.read(self.fk))

    def test_a_build_keeps_its_first_read(self):
        with snapshot.held() as snap:
            f, _mods = elaborate.load(self.fk)
            _write(self.fk, "a = Assembler<recipe=copper-cable>\n")
            again, _mods = elaborate.load(self.fk)      # size reads the file again
            self.assertEqual(f.body, again.body)
            self.assertIn("iron-gear-wheel", snapshot.read(self.fk))
            self.assertEqual(snapshot.changed(snap), [os.path.abspath(self.fk)])
        self.assertIn("copper-cable", snapshot.read(self.fk))   # the next build reads the new one

    def test_imports_and_nesting(self):
        lib = os.path.join(self.dir, "lib.fk")
        _write(lib, "module M {\n  a = Assembler<recipe=iron-gear-wheel>\n}\n")
        _write(self.fk, 'import M from "lib.fk"\nm = M\n')
        with snapshot.held() as outer:
            elaborate.load(self.fk)
            _write(lib, "module M {\n  a = Assembler<recipe=copper-cable>\n}\n")
            with snapshot.held() as inner:              # fk lab runs a build inside its own
                self.assertIs(inner, outer)
                self.assertIn("iron-gear-wheel", snapshot.read(lib))
        self.assertIsNone(snapshot._HELD)

    def test_crlf_reads_as_open_does(self):
        with open(self.fk, "wb") as fh:
            fh.write(b"a = 1\r\nb = 2\r\n")
        with snapshot.held():
            self.assertEqual(snapshot.read(self.fk), "a = 1\nb = 2\n")


if __name__ == "__main__":
    unittest.main()
