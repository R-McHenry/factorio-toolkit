"""check_ribbons: the eight-belt smelter bus routed as a ribbon, built on a laptop server's lab
surface and measured (2.1 ribbons, PLAN-2.1 "Bus routing: ribbons"; 3.1: was lab_ribbons).

    python tools/check_ribbons.py            # the bus as it is
    python tools/check_ribbons.py --rock     # a 2x2 rock on the last run's belts 2 and 3

``tests/nest/bus-ribbon.fk`` (its ore from three requesters here, 5/s each: one requester's
inserter brings about 6/s, and the eight columns take 15/s): eight SmeltColumns side by side (2.1.12's bus), ``net each
plates`` from column k to chest k of a row of eight, which stands south-east of them. The router
lays the eight plate nets as one ribbon: they join it one by one under the columns, run east, turn
south and end side by side on the chests' eight ports.

A laptop server ("ribbons", scenario fk-play) builds it with ``fk lab`` (``fkcore.lab.build``:
``fkcore.alone`` on the free lab surface, then the stand-ins power and stock), runs the game fast
for four minutes to start up (the belts fill) and then two minutes measured, the ore requester
topped up every 30 game seconds (``standin.lua_supply``), and reads:

- per column: the plates its three furnaces made (products_finished), per minute;
- per chest: the plates it took in, plus what the belt into it holds more than before;
- per chest, its belt traced back upstream in the game (belts, curves, undergrounds) to where it
  starts: which column it comes from, and the turns it takes on the way.

``--rock`` (2.1 ribbon tunnels) puts a 2x2 module in the way of two of the eight belts where
they run south to the chests: those two go under it on their own, and the others run on over the
surface beside it.

Belt k in order means chest k's belt traces back to column k, and chest k takes in what column k
makes. Every game call is one RCON command with the link's 5 s timeout, and nothing is registered.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from fkcore import alone, lab, standin  # noqa: E402
from fkcore.catalog import Catalog  # noqa: E402
from laptop_server import LaptopServer, _run_to  # noqa: E402

CAT = Catalog.load()
NEST = os.path.join(ROOT, "tests", "nest")
NAME = "ribbon"
SIZE = (112, 44)
WARM, MEASURE = 240, 120          # game seconds
ROCK = "--rock" in sys.argv[1:]
ROCK_SRC = """
rock = Rock @(102, 30)
module Rock size 2x2 {
  c = Chest<provider> @(0, 0)
}
"""
ORE_ONE = "ore  = Chest<requester, item=iron-ore, rate=15/s> @(0, 4)"
ORE_THREE = "\n".join(f"ore{k} = Chest<requester, item=iron-ore, rate=5/s> @(0, {1 + 3 * k})"
                      for k in range(3))
DIRS = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}
ARROW = {0: "^", 4: ">", 8: "v", 12: "<"}


def lua_read(box):
    x0, y0, x1, y1 = box
    return f"""
local s = game.get_surface('lab')
local area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}
local out = {{tick = game.tick, furnaces = {{}}, chests = {{}}, belts = {{}}}}
for _, f in pairs(s.find_entities_filtered{{area = area, type = 'furnace'}}) do
  out.furnaces[#out.furnaces + 1] = {{x = f.position.x, y = f.position.y, pf = f.products_finished}}
end
for _, c in pairs(s.find_entities_filtered{{area = area, name = 'passive-provider-chest'}}) do
  out.chests[#out.chests + 1] = {{x = c.position.x, y = c.position.y,
    n = c.get_inventory(defines.inventory.chest).get_item_count('iron-plate')}}
end
for _, b in pairs(s.find_entities_filtered{{area = area, type = {{'transport-belt', 'underground-belt'}}}}) do
  local n = 0
  for l = 1, 2 do n = n + b.get_transport_line(l).get_item_count('iron-plate') end
  out.belts[#out.belts + 1] = {{x = b.position.x, y = b.position.y, d = b.direction, t = b.type,
    u = b.type == 'underground-belt' and b.belt_to_ground_type or '', n = n}}
end
rcon.print(helpers.table_to_json(out))
"""


def _read(r, box):
    return json.loads(r.lua(lua_read(box)).strip())


def _tile(e):
    return (int(e["x"] // 1), int(e["y"] // 1))


def _trace(belts, start):
    """The belt chain into ``start`` (a tile), upstream as far as it goes: [(tile, direction)]
    from its first belt down to ``start``."""
    at = {_tile(b): b for b in belts}
    path, t, seen = [], start, set()
    while t in at and t not in seen:
        seen.add(t)
        b = at[t]
        d = b["d"] % 16
        path.append((t, d))
        if b["t"] == "underground-belt" and b["u"] == "output":
            dx, dy = DIRS[d]
            nxt = None
            for k in range(1, 12):
                q = (t[0] - dx * k, t[1] - dy * k)
                o = at.get(q)
                if o and o["t"] == "underground-belt" and o["u"] == "input" and o["d"] % 16 == d:
                    nxt = q
                    break
            if nxt is None:
                break
            t = nxt
            continue
        dx, dy = DIRS[d]
        behind = (t[0] - dx, t[1] - dy)
        feeds = []
        for q in (behind, (t[0] + dy, t[1] - dx), (t[0] - dy, t[1] + dx)):
            o = at.get(q)
            if o is None or (o["t"] == "underground-belt" and o["u"] == "input"):
                continue
            ox, oy = DIRS[o["d"] % 16]
            if (q[0] + ox, q[1] + oy) == t:
                feeds.append(q)
        if not feeds:
            break
        # a belt fed from behind takes that; one fed from its side only is a curve
        t = behind if behind in feeds else feeds[0] if len(feeds) == 1 else None
        if t is None:
            break
    path.reverse()
    return path


def main():
    run = tempfile.mkdtemp(prefix="fk-labrib-")
    game = os.path.join(run, "game")
    os.makedirs(game)
    with open(os.path.join(NEST, "bus-ribbon.fk"), encoding="utf-8") as fh:
        src = fh.read()
    # one requester's inserter brings about 6 ore/s: three of them, for the eight columns' 15/s
    src = src.replace(ORE_ONE, ORE_THREE).replace("net feed: ore ->", "net feed: ore0, ore1, ore2 ->")
    assert "ore2 ->" in src
    if ROCK:
        src += ROCK_SRC
    with open(os.path.join(game, f"{NAME}.fk"), "w", encoding="utf-8") as fh:
        fh.write(src)
    shutil.copy(os.path.join(NEST, "cells.fk"), os.path.join(game, "cells.fk"))
    out = []
    with LaptopServer("ribbons", scenario="fk-play") as srv:
        with srv.rcon() as r:
            lines = lab.build(r, game, NAME, size=SIZE, cat=CAT)
            out += lines
            x, y, w, h = lab.slots(game)[NAME]
            box = (x - 2, y - 2, x + SIZE[0] + 2, y + SIZE[1] + 2)
            r.lua("game.tick_paused = true rcon.print(1)")
            now = int(r.lua("rcon.print(game.tick)").strip())
            supply = standin.lua_supply(lab.SURFACE, lab.FORCE, alone.box(x, y, w, h))

            def go(ticks):
                # the ore requester holds about a minute's worth: topped up every 30 game s
                end = int(r.lua("rcon.print(game.tick)").strip()) + ticks
                while True:
                    r.lua(supply)
                    t = int(r.lua("rcon.print(game.tick)").strip())
                    if t >= end:
                        return
                    _run_to(r, min(end, t + 30 * 60))
            go(WARM * 60)                                  # to start up: every belt full
            a = _read(r, box)
            go(MEASURE * 60)
            b = _read(r, box)
    mins = (b["tick"] - a["tick"]) / 3600.0
    route = os.path.join(lab.workspace(game, NAME), "out", "route.txt")
    if os.path.exists(route):
        with open(route, encoding="utf-8") as fh:
            out += ["route: " + ln.rstrip() for ln in fh if ln.startswith(("ribbon", "FAILED"))
                    or "plates_" in ln.split(":")[0]]
    # the columns: furnaces by x, eight groups of three
    pf0 = {(f["x"], f["y"]): f["pf"] for f in a["furnaces"]}
    furn = sorted(b["furnaces"], key=lambda f: (f["x"], f["y"]))
    col_x = x + 4
    made = [0.0] * 8
    for f in furn:
        k = int((f["x"] - col_x) // 11)
        if 0 <= k < 8:
            made[k] += (f["pf"] - pf0.get((f["x"], f["y"]), f["pf"])) / mins
    low = max(c["y"] for c in b["chests"])              # the row of eight (not the rock's)
    chests = sorted((c for c in b["chests"] if c["y"] == low), key=lambda c: c["x"])
    c0 = {(c["x"], c["y"]): c["n"] for c in a["chests"]}
    belts_a = {_tile(e): e["n"] for e in a["belts"]}
    ok = len(chests) == 8 and any(" ok " in ln and ln.strip().startswith("diff") for ln in lines)
    out.append(f"measured over {mins * 60:.0f} game s (after {WARM} s to start up, the ore "
               "requester topped up every 30 s)")
    out.append("  belt  chest at   took/min  +belt/min  column made/min   traced back to       "
               "turns  tiles")
    order = []
    for k, c in enumerate(chests):
        tile = (int(c["x"] // 1), int(c["y"] // 1) - 1)
        # the chest's inserter is right above it; the belt it picks from above that
        path = _trace(b["belts"], (tile[0], tile[1] - 1))
        top = path[0][0] if path else None
        src = None if top is None else int((top[0] - col_x) // 11)
        turns = sum(1 for (_t1, d1), (_t2, d2) in zip(path, path[1:]) if d1 != d2)
        on = sum(belts_a.get(t, 0) for t, _d in path)
        on_b = sum(e["n"] for e in b["belts"] if (_tile(e) in {t for t, _d in path}))
        took = (c["n"] - c0.get((c["x"], c["y"]), 0)) / mins
        grew = (on_b - on) / mins
        order.append(src)
        out.append(f"  {k:>4}  {c['x']:>5.1f},{c['y']:<5.1f} {took:>8.1f}  {grew:>+9.1f}  "
                   f"{made[k]:>15.1f}   column {src} from {top}  {turns:>5}  {len(path):>5}")
        if src != k or abs(took + grew - made[k]) > max(3.0, 0.1 * made[k]):
            ok = False
    # the turn into the chests, as the game has it
    sx = [int(c["x"] // 1) for c in chests]
    at = {_tile(e): e for e in b["belts"]}
    ty = int(chests[0]["y"] // 1) if chests else y
    out.append("the ribbon's last turn, as the game has it (rows above the chests):")
    for yy in range(ty - 16, ty - 1):
        row = "".join(ARROW.get(at[(xx, yy)]["d"] % 16, "?") if (xx, yy) in at else "."
                      for xx in range(min(sx) - 14, max(sx) + 3))
        out.append("    " + row)
    ugs = [e for e in b["belts"] if e["t"] == "underground-belt"]
    out.append(f"underground ends in the slot: {len(ugs)} "
               + ", ".join(f"{e['u']} {e['x']},{e['y']}" for e in sorted(ugs, key=lambda e: (e["x"], e["y"]))))
    out.append(f"chest k fed from column k for every k: {order == list(range(8))}")
    print("\n".join(out))
    print("ribbon lab:", "OK" if ok else "NOT as designed")
    if os.environ.get("FK_LAB_KEEP"):
        print("kept:", run)
    else:
        shutil.rmtree(run, True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
