import unittest

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
                    link.lua_produced("lab", "lab", ["iron-gear-wheel"])):
            link.assert_safe(lua)
            for line in lua.splitlines():
                code = line.strip()
                # RCON joins the Lua into one line, so a -- comment may only fill a whole line
                self.assertFalse("--" in code and not code.startswith("--"), code)


if __name__ == "__main__":
    unittest.main()
