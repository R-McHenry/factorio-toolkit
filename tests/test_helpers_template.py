"""The player's helper codebase (kickoff/template/helpers; Rory, 2026-10-21: helpers grow as a
reusable library of features, not a pile of one-off scripts)."""
import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
TEMPLATE = os.path.join(ROOT, "kickoff", "template")
sys.path.insert(0, TEMPLATE)
import helpers  # noqa: E402
from helpers import __main__ as cli, game  # noqa: E402


class HelpersTest(unittest.TestCase):
    def test_the_seeds_are_listed_with_their_first_lines(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main([]), 0)
        text = out.getvalue()
        for name in ("grids", "machines", "stock", "labs"):
            self.assertIn(name, text)
        self.assertIn("every roboport without power", text)

    def test_a_feature_sends_its_chunk_through_fk_lua(self):
        sent = []

        def run(argv, **kw):
            sent.append(argv)
            return mock.Mock(stdout="iron-plate 5, coal 3", stderr="")

        with mock.patch.object(game.subprocess, "run", run):
            self.assertEqual(helpers.FEATURES["stock"]("iron-plate", "coal"), "iron-plate 5, coal 3")
        argv, = sent
        self.assertEqual(argv[1:3], [os.path.join(game.RUN, "bin", "fk.py"), "lua"])
        self.assertIn("string.gmatch('iron-plate,coal'", argv[3])     # the chunk, substituted

    def test_every_chunk_is_safe_for_the_link(self):
        from fkcore import link
        for name in os.listdir(game.LUA):
            with open(os.path.join(game.LUA, name), encoding="utf-8") as fh:
                link.assert_safe("/sc " + fh.read())

    def test_the_readme_says_fair_play_in_rorys_words(self):
        with open(os.path.join(TEMPLATE, "helpers", "README.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("must not manage the\nbase or keep everything stocked", text)


if __name__ == "__main__":
    unittest.main()
