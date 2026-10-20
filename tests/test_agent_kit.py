"""The agent kit's texts: what a run tells its player (Rory, 2026-10-20: the rules against code and
Lua kept the player from investigating; they are gone, the game rule and the save-safety rule stay)."""
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


DROPPED = ("don't read files outside it", "no scripts of your own", "no ssh, no RCON",
           "does not mean something needs debugging", "recipe_not_researched")


class AgentKitTest(unittest.TestCase):
    def test_no_rule_against_code_or_lua(self):
        texts = {"CLAUDE.md": new_run.CLAUDE, "first message": new_run.LAUNCH["first"],
                 "brief": read("agent", "prompts", "core-v1.md"),
                 "TOOLKIT": read("agent", "docs", "TOOLKIT.md")}
        for name, text in texts.items():
            for phrase in DROPPED:
                self.assertNotIn(phrase, text, f"{name}: {phrase!r}")

    def test_the_rules_that_stay(self):
        for name, text in (("CLAUDE.md", new_run.CLAUDE), ("brief", read("agent", "prompts",
                                                                          "core-v1.md"))):
            self.assertIn("fk lua", text, name)
            self.assertIn("ghosts and robots", text, name)            # the game rule
            self.assertIn("script.on_event", text, name)              # save safety
        self.assertIn("find out why", new_run.LAUNCH["first"])

    def test_lua_refuses_registering_and_needs_the_link(self):
        with self.assertRaises(link.LinkError):
            link.assert_safe("script.on_event(defines.events.on_tick, function() end)")
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"FK_LINK": "off"}), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["lua", ".", "rcon.print(game.tick)"]), 2)
        self.assertIn("lua: skipped, no game link", out.getvalue())


if __name__ == "__main__":
    unittest.main()
