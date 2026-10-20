"""fkcore.fresh: belts that carry stale items are taken up, and the next build lays them fresh.

    python -m fkcore fresh GAME_DIR --area X0,Y0,X1,Y1        (with the game link)

1.1 (Rory, 2026-10-20): a rebuilt factory can leave items its net doesn't carry on belts laid on
the same tiles, and they jam the new machines. A scripted fix is fine when it goes through the
game: it breaks the connectors with stale items and replaces them. ``run`` looks at the area as
``fk look`` does and orders deconstruction of every carrier with a ``WRONG_ITEM`` (an item its net
doesn't carry): robots carry the belt and what is on it to storage, nothing is moved or created by
script, and the next ``fk build`` lays the belt again (it is ``MISSING`` by then). Belts are found
by name and position, in batches that fit one RCON command.
"""
from __future__ import annotations

from . import link, look
from . import surface as surfacemod
from .apply import force_for

__all__ = ["run"]

#: belts per RCON command (pastes go in 3000-character chunks for the same reason)
BATCH = 60
#: belts listed in the report
SHOWN = 40


def run(r, game, cat, area):
    """Order the stale belts in ``area`` up; -> the report lines."""
    sf = surfacemod.load_game(game)
    force = getattr(sf, "force", None) or force_for(sf.mode)
    lk = look.run(r, game, cat, area=area, notify="off", tag="fresh")
    stale = [v for v in lk.rep.verdicts if v.wrong_items]
    a = ",".join(str(int(v)) for v in area)
    if not stale:
        return [f"fresh {sf.name} area {a}: no belt here carries an item its net doesn't"]
    things = [(v.name, v.x, v.y) for v in stale]
    ordered = 0
    for i in range(0, len(things), BATCH):
        got = r.lua(link.lua_decon_list(sf.name, force, things[i:i + BATCH])).strip()
        ordered += int(got) if got.isdigit() else 0
    items = sorted({i for v in stale for i in v.wrong_items})
    out = [f"fresh {sf.name} area {a}: {ordered} of {len(stale)} belts with stale items "
           f"({', '.join(items)}) ordered up. Robots carry them and what is on them to storage; "
           "the next fk build lays them fresh"]
    out += [f"  {v}" for v in stale[:SHOWN]]
    if len(stale) > SHOWN:
        out.append(f"  ... and {len(stale) - SHOWN} more")
    return out
