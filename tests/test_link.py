import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import link


class LinkLuaTest(unittest.TestCase):
    def test_nothing_that_registers_is_ever_sent(self):
        for bad in ("script.on_event(defines.events.on_tick, f)", "script.on_nth_tick(60, f)",
                    "commands.add_command('lab', '', f)", "remote.add_interface('x', {})",
                    "script.register_on_object_destroyed(e)"):
            with self.assertRaises(link.LinkError):
                link.assert_safe(bad)

    def test_the_link_lua_is_safe_and_one_line_able(self):
        for lua in (link.lua_snapshot("lab", (0, 0, 10, 10)),
                    link.lua_paste("lab", "lab", "0eNq...", (5, 5)),
                    link.lua_revive("lab", (0, 0, 10, 10)),
                    link.lua_decon("lab", "lab", (0, 0, 10, 10)),
                    link.lua_destroy("lab", (0, 0, 10, 10), ["transport-belt"]),
                    link.lua_produced("lab", "lab", ["iron-gear-wheel"]),
                    link.lua_alerts("player", "alerts-1"),
                    link.lua_stats("lab", "lab", None, "1min", "stats-1"),
                    link.lua_stats("lab", "lab", ["iron-plate", "coal"], "1h", "stats-2"),
                    link.lua_stats("lab", "lab", ["water"], "10h", "stats-3", True, 30),
                    link.lua_chart("lab", "lab"),
                    link.lua_say("[fk lab] transport-belt at 307.5,430.5: \"quoted\""),
                    link.lua_ghosts("lab", "lab",
                                    [{"entity_number": 1, "name": "transport-belt"}],
                                    [[["transport-belt", 0.5, 0.5], 5,
                                      ["transport-belt", 1.5, 0.5], 5]]),
                    link.lua_generate_area("lab", "lab", (480, 416, 600, 540))):
            link.assert_safe(lua)
            for line in lua.splitlines():
                code = line.strip()
                # RCON joins the Lua into one line, so a -- comment may only fill a whole line
                self.assertFalse("--" in code and not code.startswith("--"), code)

    def test_the_snapshot_reads_an_underground_pair_for_unpaired(self):
        lua = link.lua_snapshot("lab", (0, 0, 10, 10))
        self.assertIn("e.belt_to_ground_type", lua)
        self.assertIn("e.neighbours", lua)
        self.assertIn("row.pair", lua)
        link.assert_safe(lua)

    def test_the_link_is_on_only_with_fk_link_on(self):
        with mock.patch.dict(os.environ, {"FK_LINK": "off"}):
            self.assertEqual(link.open_from_env(),
                             (None, "FK_LINK is not on (FK_LINK=on uses the game link)"))
        with mock.patch.dict(os.environ, {"FK_LINK": "on"}), \
                mock.patch.object(link, "Rcon", side_effect=OSError("connection refused")):
            self.assertEqual(link.open_from_env(), (None, "OSError: connection refused"))

    def test_alert_and_stats_reads_leave_no_file_behind(self):
        out = tempfile.mkdtemp(prefix="fkout-")
        self.addCleanup(shutil.rmtree, out, True)
        os.makedirs(os.path.join(out, "fk5"))

        class Game:
            """Writes what the Lua would write into script-output, replies with the count."""
            def lua(self, body):
                name = body.split("helpers.write_file('fk5/", 1)[1].split("'", 1)[0]
                with open(os.path.join(out, "fk5", name), "w", encoding="utf-8") as fh:
                    fh.write('{"tick": 7, "force": "lab", "alerts": {}, "items": {}}')
                return "0"
        with mock.patch.object(link, "OUT_DIR", out):
            self.assertEqual(link.alerts(Game(), "lab")["tick"], 7)
            self.assertEqual(link.stats(Game(), "lab", "lab")["tick"], 7)
            self.assertEqual(os.listdir(os.path.join(out, "fk5")), [])
            link.snapshot(Game(), "lab", (0, 0, 1, 1))              # a snapshot keeps its file
            self.assertEqual(len(os.listdir(os.path.join(out, "fk5"))), 1)

    def test_a_statistics_window_is_checked_before_the_call(self):
        with self.assertRaises(link.LinkError):
            link.stats(None, "lab", "lab", window="2min")


class GhostsTest(unittest.TestCase):
    """2.0.4 (A1): single ghosts go in RCON-sized calls, and their counts are summed."""

    class Rcon:
        def __init__(self):
            self.calls = []

        def lua(self, body):
            self.calls.append(body)
            return '{"n": 1, "missed": {"tags": %d}}' % len(self.calls)

    def test_entities_then_wires_in_batches_are_summed(self):
        r = self.Rcon()
        entities = [{"entity_number": i, "name": "transport-belt"} for i in range(1, 5)]
        wires = [[["transport-belt", 0.5, 0.5], 5, ["transport-belt", 1.5, 0.5], 5]]
        self.assertEqual(link.ghosts(r, "lab", "lab", entities, wires, chunk=1),
                         {"n": 5, "missed": {"tags": 15}, "landfill": 0})
        self.assertEqual(len(r.calls), 5)           # one entity a call, then the wire

    def test_luas_empty_missed_table_is_no_miss(self):
        class R:
            def lua(self, body):
                return '{"n": 2, "missed": []}'
        self.assertEqual(link.ghosts(R(), "lab", "lab",
                                     [{"entity_number": 1, "name": "stone-furnace"}]),
                         {"n": 2, "missed": {}, "landfill": 0})

    def test_a_reply_that_is_not_json_is_a_link_error(self):
        class R:
            def lua(self, body):
                return "no ghosts here"
        with self.assertRaises(link.LinkError):
            link.ghosts(R(), "lab", "lab", [{"entity_number": 1, "name": "stone-furnace"}])


if __name__ == "__main__":
    unittest.main()
