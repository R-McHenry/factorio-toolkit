"""The agent kit's texts: what a run tells its player (Rory, 2026-10-20). The brief is v4's
(C:\\fk-player\\prompts\\core.md: simple and encouraging) with only the V1 facts swapped in; the
rules against code and Lua are gone; the game rule is one plain sentence; save safety is the
link's to enforce, not the brief's."""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

from fkcore import __main__ as cli, link

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "kickoff"))
import new_run  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


BRIEF = read("agent", "prompts", "core-v1.md")
DROPPED = ("don't read files outside it", "no scripts of your own", "no ssh, no RCON",
           "needs debugging", "recipe_not_researched", "Two rules stay")


class AgentKitTest(unittest.TestCase):
    def test_no_rule_against_code_or_lua(self):
        for name, text in {"CLAUDE.md": new_run.CLAUDE, "first message": new_run.LAUNCH["first"],
                           "brief": BRIEF}.items():
            for phrase in DROPPED:
                self.assertNotIn(phrase, text, f"{name}: {phrase!r}")

    def test_the_brief_is_v4s_in_tone(self):
        for line in ("You're free to just build", "Something running beats something",
                     "Mistakes are cheap here", "Ways to get unstuck", "Have fun",
                     "Your goal file"):
            self.assertIn(line, BRIEF)
        self.assertIn("robots build what you plan", BRIEF)           # the game, said plainly
        self.assertIn("fk lua", BRIEF)
        self.assertLess(len(new_run.CLAUDE.splitlines()), 8)          # a pointer, not a rulebook
        self.assertIn("AGENTS.md", new_run.CLAUDE)

    def test_lua_refuses_registering_and_needs_the_link(self):
        with self.assertRaises(link.LinkError):
            link.assert_safe("script.on_event(defines.events.on_tick, function() end)")
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"FK_LINK": "off"}), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["lua", ".", "rcon.print(game.tick)"]), 2)
        self.assertIn("lua: skipped, no game link", out.getvalue())


if __name__ == "__main__":
    unittest.main()
