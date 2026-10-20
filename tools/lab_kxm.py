"""lab_kxm: the live check of games/lab-kxm (a k -> m sushi net) on the lab surface.

After ``fk build games/lab-kxm/lab.build.fkb`` has applied the plot (the diff says OK n/n), this
gives the plot what the lab lacks and watches the net work:

- power: an electric energy interface beside one of the design's poles (the lab surface has no
  generator; the lab bench measures the same way);
- the gear chest (a requester chest with no logistic network) is stocked once, by hand;
- every ``--every`` seconds, a snapshot of the plot: what each consumer chest holds. Done when
  every consumer holds every driver's item, or after ``--seconds``.

Run on the game host from a deployed v5 dir:  python3 tools/lab_kxm.py [--seconds 120]
Every game call is one RCON command with a 5 s timeout; nothing registers a handler or a
command (fkcore.link refuses that Lua); everything happens inside the plot, on the lab surface,
for the lab force. ``--say`` only prints a chat line ("[fk5 router] ...").
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from fkcore import compose, fkp, link  # noqa: E402
from fkcore.catalog import Catalog  # noqa: E402
from fkcore.elaborate import elaborate_file  # noqa: E402

GAME = os.path.join(os.path.dirname(HERE), "games", "lab-kxm")
SURF, FORCE = "lab", "lab"
TAG = "[fk5 router]"


def say(r, text):
    print(text, flush=True)
    r.lua(link.lua_say(f"{TAG} {text}"))


def design(cat):
    lay = fkp.load(os.path.join(GAME, "kxm.fkp"))
    surf = fkp.load(os.path.join(GAME, "lab.fkp"))
    s = compose.compose(surf, {"kxm": lay}, cat)
    flat = elaborate_file(os.path.join(GAME, "kxm.fk"), cat, layout=lay)
    return s, surf.plots["kxm"], flat


def eei_spot(s, plot, cat):
    """A 2x2 spot inside the plot, free in the design, within a pole's supply area."""
    x0, y0, x1, y1 = plot.box()
    poles = sorted((e for e in s.entities.values() if cat.kind(e.name) == "electric-pole"),
                   key=lambda e: (e.y, e.x))
    for p in poles:
        reach = cat.pole_supply(p.name)
        for dx in (1, -2, 2, -3):
            for dy in (-1, 1, -2, 0):
                cx, cy = math.floor(p.x) + dx + 1, math.floor(p.y) + dy + 1    # the 2x2 centre
                tiles = {(cx - 1, cy - 1), (cx, cy - 1), (cx - 1, cy), (cx, cy)}
                inside = all(x0 <= tx < x1 and y0 <= ty < y1 for tx, ty in tiles)
                near = abs(cx - p.x) <= reach and abs(cy - p.y) <= reach    # it overlaps
                if inside and near and not tiles & set(s.tiles):
                    return cx, cy
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--every", type=float, default=10.0)
    ap.add_argument("--stock", type=int, default=200)
    ap.add_argument("--say", default=None, help="only print this line in chat")
    a = ap.parse_args(argv)
    cat = Catalog.load()
    with link.Rcon() as r:
        if a.say:
            say(r, a.say)
            return 0
        s, plot, flat = design(cat)
        net = flat.nets["mix"]
        prefix = f"{SURF}:kxm/"
        sinks = {prefix + k: s.entities[prefix + k] for k, _i in net.consumers}
        src = {k: i for k, i in net.drivers}
        chest = next(s.entities[prefix + k] for k in src if s.entities[prefix + k].name ==
                     "requester-chest")
        spot = eei_spot(s, plot, cat)
        area = plot.box()
        say(r, f"kxm: powering the plot (an energy interface at {spot[0]},{spot[1]}), stocking "
               f"the gear chest; watching {', '.join(k.split('/')[1] for k in sinks)} for "
               f"{', '.join(sorted(set(src.values())))}")
        r.lua(f"""
local s = game.get_surface('{SURF}')
local ei = s.create_entity{{name = 'electric-energy-interface', position = {{{spot[0]}, {spot[1]}}}, force = '{FORCE}'}}
ei.power_production = 2000000
ei.electric_buffer_size = 2000000
local c = s.find_entity('requester-chest', {{{chest.x}, {chest.y}}})
rcon.print(c and c.insert{{name = 'iron-gear-wheel', count = {a.stock}}} or -1)""")
        t0, rows, done = time.time(), [], False
        want = set(src.values())
        while not done and time.time() - t0 < a.seconds:
            time.sleep(a.every)
            cap = link.snapshot(r, SURF, area, "kxm-measure")
            held = {}
            for t in cap["things"]:
                for key, e in sinks.items():
                    if t["n"] == e.name and float(t["x"]) == float(e.x) and \
                            float(t["y"]) == float(e.y):
                        held[key.split("/")[1]] = t.get("it") or {}
            rows.append({"tick": cap["tick"], "s": round(time.time() - t0), "held": held})
            print(json.dumps(rows[-1]), flush=True)
            done = len(held) == len(sinks) and all(want <= set(h) for h in held.values())
        last = rows[-1]["held"] if rows else {}
        text = "; ".join(f"{k}: " + ", ".join(f"{n} {c}" for n, c in sorted(v.items()))
                         for k, v in sorted(last.items()))
        say(r, f"kxm after {rows[-1]['s'] if rows else 0} s: "
               + ("every consumer holds every driver's item" if done else "NOT every item in "
                  "every consumer") + f" ({text})")
    os.makedirs(os.path.join(GAME, "out"), exist_ok=True)
    with open(os.path.join(GAME, "out", "lab_kxm.json"), "w") as fh:
        json.dump({"done": done, "rows": rows, "eei": spot}, fh, indent=1)
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main())
