import os
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
                    link.lua_chart("lab", "lab"),
                    link.lua_say("[fk lab] transport-belt at 307.5,430.5: \"quoted\"")):
            link.assert_safe(lua)
            for line in lua.splitlines():
                code = line.strip()
                # RCON joins the Lua into one line, so a -- comment may only fill a whole line
                self.assertFalse("--" in code and not code.startswith("--"), code)

    def test_the_link_is_on_only_with_fk_link_on(self):
        with mock.patch.dict(os.environ, {"FK_LINK": "off"}):
            self.assertEqual(link.open_from_env(),
                             (None, "FK_LINK is not on (FK_LINK=on uses the game link)"))
        with mock.patch.dict(os.environ, {"FK_LINK": "on"}), \
                mock.patch.object(link, "Rcon", side_effect=OSError("connection refused")):
            self.assertEqual(link.open_from_env(), (None, "OSError: connection refused"))

    def test_a_statistics_window_is_checked_before_the_call(self):
        with self.assertRaises(link.LinkError):
            link.stats(None, "lab", "lab", window="2min")


if __name__ == "__main__":
    unittest.main()
