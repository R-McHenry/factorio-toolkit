"""The agent kit's texts: what a run tells its player (Rory, 2026-10-20). The brief is v4's
(C:\\fk-player\\prompts\\core.md: simple and encouraging) with only the V1 facts swapped in; the
rules against code and Lua are gone; the game rule is one plain sentence; save safety is the
link's to enforce, not the brief's."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

from fkcore import __main__ as cli, link

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "kickoff"))
import new_run  # noqa: E402

_spec = importlib.util.spec_from_file_location("fk_agent", os.path.join(ROOT, "agent", "fk.py"))
fk_agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fk_agent)


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


def long_chunk():
    """A chunk shaped like the 0534 player's unjam script: 13 kB of JSON in single quotes."""
    rows = ", ".join(f'[{22.5 + i % 9}, {132.5 + i // 9}, ["iron-plate"]]' for i in range(400))
    return (f"local belts = helpers.json_to_table('[{rows}]')\n-- a comment line\n"
            "local s = game.surfaces['nauvis']\nrcon.print('ok ' .. #belts)\n")


class LuaTransportTest(unittest.TestCase):
    """1.2: fk lua's chunk goes over the ssh's stdin. Git for Windows' ssh (an MSYS program) got
    at most about 8 kB of one argument, so the 0534 player's 13 kB chunk arrived cut and its open
    single quote stopped the host's shell ("unexpected EOF while looking for matching")."""

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(prefix="fklua-")
        self.addCleanup(shutil.rmtree, self.run_dir, True)
        game = os.path.join(self.run_dir, "game")
        os.makedirs(os.path.join(game, "out"))
        with open(os.path.join(self.run_dir, "run.json"), "w", encoding="utf-8") as fh:
            json.dump({"host": "gamehost", "host_game": "/srv/run/game",
                       "host_toolkit": "/srv/tk"}, fh)
        stamp = os.path.join(game, "out", ".synced")
        with open(stamp, "w", encoding="utf-8") as fh:
            fh.write("synced\n")
        self.calls = []
        for name, value in (("RUN", self.run_dir), ("GAME", game), ("STAMP", stamp)):
            patcher = mock.patch.object(fk_agent, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_run(self, argv, input=None, stdout=None, **_kw):
        self.calls.append((argv, input))
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w"):
            pass                                     # the pull: an empty copy of game\
        return mock.Mock(returncode=0, stdout=buf.getvalue())

    def lua_call(self):
        (argv, data), = [(a, d) for a, d in self.calls if "fkcore lua" in a[-1]]
        return argv[-1], data

    def test_a_long_chunk_with_quotes_goes_over_stdin(self):
        code = long_chunk()
        self.assertGreater(len(code), 12000)
        with mock.patch.object(fk_agent.subprocess, "run", self.fake_run):
            self.assertEqual(fk_agent.main(["lua", code]), 0)
        command, data = self.lua_call()
        self.assertIn("python3 -m fkcore lua . --file -", command)
        self.assertLess(len(command), 400)
        self.assertNotIn("'", command.split("fkcore lua", 1)[1].split(";", 1)[0])
        self.assertEqual(data, code.encode("utf-8"))

    def test_a_file_goes_over_stdin_too(self):
        code = long_chunk()
        path = os.path.join(self.run_dir, "unjam.lua")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(code)
        with mock.patch.object(fk_agent.subprocess, "run", self.fake_run):
            self.assertEqual(fk_agent.main(["lua", "--file", path]), 0)
        self.assertEqual(self.lua_call()[1], code.encode("utf-8"))

    def test_fkcore_reads_the_chunk_from_stdin(self):
        code = long_chunk()
        sent = []

        class FakeRcon:
            def call(self, cmd):
                link.assert_safe(cmd)
                sent.append(cmd)
                return "ok 400"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        stdin = mock.Mock(buffer=io.BytesIO(code.encode("utf-8")))
        out = io.StringIO()
        with mock.patch.object(link, "open_from_env", lambda: (FakeRcon(), None)), \
                mock.patch.object(sys, "stdin", stdin), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["lua", ".", "--file", "-"]), 0)
        # as written, lines and all: joined with spaces, the comment line's "--" ate the rest
        self.assertEqual(sent, ["/sc " + code])
        self.assertIn("-- a comment line\nlocal s", sent[0])
        self.assertIn("ok 400", out.getvalue())


class SyncTest(unittest.TestCase):
    """1.4.2: the two copies of game\\ go by content. The 2005 player's background ``fk look``
    loop pulled the host's copy over fresh edits to base.fk; the stamp it wrote then made the next
    push skip them (older mtime), so the edits were silently undone."""

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(prefix="fksync-")
        self.addCleanup(shutil.rmtree, self.run_dir, True)
        self.game = os.path.join(self.run_dir, "game")
        os.makedirs(os.path.join(self.game, "out"))
        self.cfg = {"host": "gamehost", "host_game": "/srv/run/game", "host_toolkit": "/srv/tk"}
        self.host = {}                                # the host's copy: rel -> bytes
        self.sent = []                                # what each push sent
        for name, value in (("RUN", self.run_dir), ("GAME", self.game),
                            ("STAMP", os.path.join(self.game, "out", ".synced"))):
            patcher = mock.patch.object(fk_agent, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(fk_agent, "_ssh", self.fake_ssh)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_ssh(self, cfg, command, data=None, capture=False):
        if "tar -xf" in command:
            with tarfile.open(fileobj=io.BytesIO(data)) as tar:
                got = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
            self.host.update(got)
            self.sent.append(sorted(got))
            return mock.Mock(returncode=0)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for rel, body in self.host.items():
                info = tarfile.TarInfo("./" + rel)
                info.size = len(body)
                tar.addfile(info, io.BytesIO(body))
        return mock.Mock(returncode=0, stdout=buf.getvalue())

    def write(self, rel, text):
        with open(os.path.join(self.game, rel), "w", encoding="utf-8") as fh:
            fh.write(text)

    def text(self, rel):
        with open(os.path.join(self.game, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_a_pull_keeps_an_edit_made_since_the_last_sync(self):
        self.write("base.fk", "v1")
        fk_agent.push(self.cfg)
        fk_agent.pull(self.cfg)
        self.write("base.fk", "v2")                   # the player's edit, after a look's push
        self.host["out/look.txt"] = b"looked"         # ...and that look's host step
        fk_agent.pull(self.cfg)                       # the look's pull
        self.assertEqual(self.text("base.fk"), "v2")
        self.assertEqual(self.text("out/look.txt"), "looked")
        fk_agent.push(self.cfg)                       # the next command sends the edit
        self.assertEqual(self.sent[-1], ["base.fk"])
        self.assertEqual(self.host["base.fk"], b"v2")

    def test_a_pull_takes_what_the_host_wrote(self):
        self.write("base.fk", "v1")
        self.write("out/diff.txt", "old")
        fk_agent.push(self.cfg)
        self.host["out/diff.txt"] = b"new"
        self.host["out/alerts.json"] = b"[]"
        fk_agent.pull(self.cfg)
        self.assertEqual(self.text("out/diff.txt"), "new")
        self.assertEqual(self.text("out/alerts.json"), "[]")
        self.assertEqual(fk_agent.push(self.cfg), 0)  # nothing changed here: nothing to send

    def test_an_older_fks_stamp_pushes_by_mtime_once(self):
        self.write("old.fk", "synced long ago")
        os.utime(os.path.join(self.game, "old.fk"), (1, 1))
        self.write("out/.synced", "last sync with gamehost at some time\n")
        os.utime(os.path.join(self.game, "out", ".synced"), (100, 100))
        self.write("new.fk", "edited since")
        self.assertEqual(fk_agent.push(self.cfg), 1)
        self.assertEqual(self.sent, [["new.fk"]])
        self.write("old.fk", "edited now")            # by content from now on: its mtime is
        os.utime(os.path.join(self.game, "old.fk"), (1, 1))     # older than any stamp
        self.assertEqual(fk_agent.push(self.cfg), 1)
        self.assertEqual(self.sent[-1], ["old.fk"])
        self.assertNotIn("out/.synced", self.host)
        self.assertFalse([r for r in self.host if r.startswith("out/.synced")])


if __name__ == "__main__":
    unittest.main()
