"""The lab scenario (scenario/fk-play), checked offline: no Lua interpreter and no game here.

A small Lua lexer checks the block structure (function/if/for/while/do/repeat ... end/until, and
bracket balance, with strings and comments skipped), then the rules the lab must keep.
"""
import json
import os
import re
import unittest

SCEN = os.path.join(os.path.dirname(__file__), "..", "scenario", "fk-play")
_TOKEN = re.compile(r"""
    (?P<comment_long>--\[(?P<eq1>=*)\[.*?\](?P=eq1)\])
  | (?P<comment>--[^\n]*)
  | (?P<string_long>\[(?P<eq2>=*)\[.*?\](?P=eq2)\])
  | (?P<string>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<number>0[xX][0-9a-fA-F]+|\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)
  | (?P<op>\.\.\.|\.\.|==|~=|<=|>=|::|[-+*/%^#&~|<>=(){}\[\];:,.])
  | (?P<space>\s+)
""", re.X | re.S)


def lex(text):
    out, pos, line = [], 0, 1
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise SyntaxError(f"line {line}: unexpected {text[pos]!r}")
        kind = next(k for k in ("comment_long", "comment", "string_long", "string", "name",
                                "number", "op", "space") if m.group(k) is not None)
        if kind in ("name", "op", "string", "string_long", "number"):
            out.append((kind, m.group(kind), line))
        line += m.group(0).count("\n")
        pos = m.end()
    return out


def check_blocks(tokens):
    """Raise SyntaxError unless every block and bracket closes, in order."""
    stack, expect_do, pairs = [], 0, {")": "(", "]": "[", "}": "{"}
    for kind, text, line in tokens:
        if kind == "op" and text in "([{":
            stack.append((text, line))
        elif kind == "op" and text in ")]}":
            if not stack or stack[-1][0] != pairs[text]:
                raise SyntaxError(f"line {line}: unbalanced {text}")
            stack.pop()
        elif kind != "name":
            continue
        elif text in ("function", "if", "repeat"):
            stack.append((text, line))
        elif text in ("for", "while"):
            stack.append((text, line))
            expect_do += 1
        elif text == "do":
            if expect_do:
                expect_do -= 1
            else:
                stack.append(("do", line))
        elif text == "end":
            if not stack or stack[-1][0] not in ("function", "if", "for", "while", "do"):
                raise SyntaxError(f"line {line}: 'end' closes {stack[-1] if stack else 'nothing'}")
            stack.pop()
        elif text == "until":
            if not stack or stack[-1][0] != "repeat":
                raise SyntaxError(f"line {line}: 'until' without repeat")
            stack.pop()
    if stack or expect_do:
        raise SyntaxError(f"unclosed {stack[-1][0]} from line {stack[-1][1]}" if stack
                          else "for/while without do")


def read(name):
    with open(os.path.join(SCEN, name), encoding="utf-8") as fh:
        return fh.read()


def code_only(text):
    """The text without comments (so a rule is checked on code, not on what a comment says)."""
    return " ".join(t for k, t, _l in lex(text))


class LexerTest(unittest.TestCase):
    def test_catches_broken_blocks(self):
        check_blocks(lex("local f = function(a) if a then return 1 end end"))
        check_blocks(lex("for i = 1, 2 do print(i) end while x do end repeat y() until z"))
        check_blocks(lex("local s = 'end' -- end\n--[[ end end ]] local t = [[ if ]]"))
        for bad in ("function f() if x then end", "if x then end end", "f(a", "for i=1,2 print(i) end"):
            with self.assertRaises(SyntaxError, msg=bad):
                check_blocks(lex(bad))


class LabScenarioTest(unittest.TestCase):
    def test_lua_files_are_well_formed(self):
        for name in ("control.lua", "fk_lab.lua", "fk_chat.lua", "fk_stats.lua"):
            check_blocks(lex(read(name)))

    def test_control_is_freeplay_plus_the_lab(self):
        code = code_only(read("control.lua"))
        libs = re.findall(r'add_lib \( require \( "([^"]+)" \) \)', code)
        self.assertEqual(libs, ["__base__/script/freeplay/freeplay", "space-finish-script",
                                "silo-script", "fk_lab", "fk_chat", "fk_stats"])
        self.assertIn('script . active_mods [ "space-age" ]', code)
        desc = json.loads(read("description.json"))
        self.assertTrue(desc["multiplayer-compatible"])

    def test_lab_rules(self):
        code = code_only(read("fk_lab.lua"))
        # /lab is registered in add_commands (event_handler: on_init and on_load), not at an event
        self.assertRegex(code, r'lab \. add_commands = function \( \) commands \. add_command \( "lab"')
        self.assertEqual(code.count("commands . add_command"), 1)
        self.assertNotRegex(code.lower(), r"\brcon\b")
        self.assertNotRegex(code, r"\bglobal\b")              # 2.0: storage, not global
        self.assertIn("storage . fk_lab", code)
        # its own surface: peaceful, no enemies, lab tiles; its own force with all research
        for needle in ('game . create_surface ( LAB', "peaceful_mode = true", "no_enemies_mode = true",
                       "generate_with_lab_tiles = true", "game . create_force ( LAB )",
                       "research_all_technologies ( )", "set_cease_fire ( player_force , true )"):
            self.assertIn(needle, code)
        self.assertIn('local LAB = "lab"', code)
        # the round trip: there as a spectator on the lab force, back to surface, position, force
        for needle in ("defines . controllers . spectator", "player . force = force",
                       "player . teleport ( { 0 , 0 } , surface )",
                       "player . teleport ( back . position , back . surface )",
                       "player . force = back . force", "defines . controllers . character",
                       "if not cmd . player_index then return"):
            self.assertIn(needle, code)
        # no event handlers: the lab registers nothing that runs on game events
        self.assertIn("lab . events = { }", code)

    def test_chat_journal_rules(self):
        code = code_only(read("fk_chat.lua"))
        # one handler, on console chat, through event_handler's events table (scenario code)
        self.assertIn("chat . events = { [ defines . events . on_console_chat ] = function", code)
        self.assertEqual(code.count("defines . events ."), 1)
        self.assertNotIn("script . on_event", code)
        self.assertNotIn("commands . add_command", code)
        self.assertNotRegex(code.lower(), r"\brcon\b")
        self.assertNotRegex(code, r"\bglobal\b")
        self.assertIn("storage . fk_chat", code)
        self.assertIn("local MAX = 200", code)
        self.assertIn("table . remove ( t , 1 )", code)        # a ring: the oldest goes first

    def test_stats_recorder_rules(self):
        """2.1: one on_nth_tick handler through event_handler (scenario code), every 5 game
        minutes, that only reads: its sample in a pcall, written on the server only."""
        code = code_only(read("fk_stats.lua"))
        self.assertIn("local EVERY = 5 * 60 * 60", code)
        self.assertIn("stats . on_nth_tick = { [ EVERY ] = function ( event )", code)
        self.assertNotIn("script . on_", code)
        self.assertNotIn("commands . add_command", code)
        self.assertNotIn("defines . events", code)
        self.assertNotRegex(code, r"\bstorage\b")         # nothing kept in the save
        self.assertNotRegex(code, r"\bglobal\b")
        self.assertIn("pcall ( fk_stats_sample , f , s )", code)
        self.assertIn("helpers . write_file ( FILE , helpers . table_to_json ( sample ) .. "
                      '"\\n" , true , 0 )', code)
        # what it reads, it only reads: no assignment to a game object's field
        for bad in ("create_entity", "destroy", ".insert", "set_recipe", "research_queue=",
                    "add_research", "tick_paused", ".speed="):
            self.assertNotIn(bad, code.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
