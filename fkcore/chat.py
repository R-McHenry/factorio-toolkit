"""fkcore.chat: the game chat as the player's channel to the agent (CORE-V1.md 6.5).

The fk-play scenario keeps every chat line in ``storage.fk_chat`` (``scenario/fk-play/fk_chat.lua``:
registered in scenario code, never through RCON). ``read(r, since)`` is one RCON read of the lines
after a tick; ``new_lines(r, game_dir)`` keeps a cursor in ``<game>/out/chat-cursor.json`` and
returns only what arrived since the last call, as ``chat <name>: <message>`` lines for the end of
every agent command. ``say(r, text)`` writes one line to the game chat. A map made from another
scenario has no journal: ``read`` says so instead of failing.
"""
from __future__ import annotations

import json
import os

from . import link

__all__ = ["lua_read", "read", "new_lines", "say", "CURSOR"]

CURSOR = os.path.join("out", "chat-cursor.json")


def lua_read(since):
    return f"""
local out = {{}}
for _, m in ipairs(storage.fk_chat or {{}}) do
  if m.tick > {int(since)} then out[#out + 1] = m end
end
rcon.print(helpers.table_to_json({{tick = game.tick, journal = storage.fk_chat ~= nil, messages = out}}))
"""


def read(r, since=0):
    """-> {tick, journal, messages: [{tick, name, message}]}."""
    text = r.lua(lua_read(since))
    try:
        got = json.loads(text)
    except ValueError:
        raise link.LinkError(f"chat read: not JSON: {text[:200]}")
    msgs = got.get("messages") or []
    if isinstance(msgs, dict):                   # an empty Lua table comes back as {}
        msgs = list(msgs.values())
    got["messages"] = sorted(msgs, key=lambda m: m.get("tick", 0))
    return got


def _cursor(game_dir):
    try:
        with open(os.path.join(game_dir, CURSOR), encoding="utf-8") as fh:
            return int(json.load(fh).get("tick") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def _save_cursor(game_dir, tick):
    path = os.path.join(game_dir, CURSOR)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"tick": int(tick)}, fh)


def new_lines(r, game_dir):
    """The chat lines since the last call (and move the cursor). Empty when nothing is new."""
    got = read(r, _cursor(game_dir))
    if not got.get("journal"):
        return ["chat: this map keeps no chat journal (it was not made from the fk-play scenario)"]
    msgs = got["messages"]
    if msgs:
        _save_cursor(game_dir, max(int(m.get("tick", 0)) for m in msgs))
    return [f"chat {m.get('name') or '?'}: {m.get('message', '')}" for m in msgs]


def say(r, text):
    return r.lua(link.lua_say(f"[agent] {text}"))
