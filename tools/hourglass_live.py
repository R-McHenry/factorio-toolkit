"""hourglass_live: the hourglass bench in a real game, on a laptop server's lab surface
(DESIGN-M2M.md, release 3: "the lab"; 3.1: was hourglass_lab).

    python tools/hourglass_live.py [--only NAME[,NAME]] [--routers m2m,today,balancer] [--big]
                                  [--warm 120] [--secs 180] [--step 2]

Each case's layout (``tools/hourglass.py``) is pasted on a laptop server's lab surface
(``tools/laptop_server.py``: never the live game), one beside the other, as the toolkit pastes a
design (a superforced blueprint, the ghosts revived), its chests as steel chests, powered by an
electric energy interface and substations of its own. The game then runs ``--step`` seconds at a
time, and between steps the script meters the chests over RCON (nothing registered):

- a producer gets its rate's worth of plates into its chest (the fraction carried over), so it
  makes exactly what the case says; what its inserters can't put on the belt stays in its chest;
- a consumer gives up at most its rate's worth from its chest (what the case asks of it), so it
  takes at most that; what reaches it beyond waits in its chest (a stack, then its inserter stops).

After ``--warm`` seconds the plates each consumer gave up over ``--secs`` seconds are its rate. The
table: per layout the demand, the model's max-flow, the total the consumers took, the lowest and
the highest consumer against its rate, the spread (the population standard deviation over the
mean, the coefficient of variation), the producers' plates left waiting at the end, and the time.
Balanced is every consumer at its rate: a short total is the network short of its max-flow (a
splitter's even split, a side-load's priority), a low consumer is one the network starves.
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
sys.path.insert(0, HERE)

import hourglass                                                 # noqa: E402
from laptop_server import LaptopServer, _run_to                  # noqa: E402

from fkcore import codec, link                                   # noqa: E402
from fkcore.apply import _anchor, scope_area                     # noqa: E402
from fkcore.catalog import Catalog                               # noqa: E402

SURFACE, FORCE = "lab", "lab"
PITCH = 64           # tiles from one layout's origin to the next one's
CHESTS = ("requester-chest", "passive-provider-chest")
SUB_REACH = 9        # a substation powers 18 x 18 tiles around its centre


def layouts(cases, routers, cat):
    """[(case, router, row dict, rows)] of every case laid by every router."""
    out = []
    for name in cases:
        for router in routers:
            m = hourglass.measure(name, cat, router=router)
            if m["failed"]:
                print(f"{name} {router}: not laid ({m['line'][:80]})")
                continue
            rows = []
            for r in codec.rows_of(m["layout"]):
                if r["name"] in CHESTS:
                    r = dict(r, name="steel-chest", attrs={})
                rows.append(r)
            out.append((name, router, m, rows))
    return out


def _free_spots(rows, cat, box):
    """Substation + energy interface spots (each 2 x 2, side by side) on a grid over ``box``, on
    tiles no row takes."""
    taken = set()
    for r in rows:
        taken |= set(cat.tiles(r["name"], float(r["x"]), float(r["y"]), r["direction"] or 0))
    x0, y0, x1, y1 = box
    spots = []
    for cy in range(y0 + 6, y1 + 6, 14):
        for cx in range(x0 + 6, x1 + 6, 14):
            best = None
            for dy in range(-5, 6):
                for dx in range(-5, 6):
                    x, y = cx + dx, cy + dy
                    need = {(x + i, y + j) for i in range(4) for j in range(2)}
                    if not need & taken and (best is None or abs(dx) + abs(dy) < best[0]):
                        best = (abs(dx) + abs(dy), x, y)
            if best:
                _d, x, y = best
                spots.append((x, y))
                taken |= {(x + i, y + j) for i in range(4) for j in range(2)}
    return spots


def lua_power(spots):
    lines = [f"local s, f = game.get_surface('{SURFACE}'), game.forces['{FORCE}'] local n = 0"]
    for x, y in spots:
        lines.append(
            f"do local e = s.create_entity{{name = 'electric-energy-interface', position = "
            f"{{{x + 1}, {y + 1}}}, force = f}} if e then e.electric_buffer_size = 1e10 "
            f"e.power_production = 1e8 e.energy = 1e10 n = n + 1 end "
            f"s.create_entity{{name = 'substation', position = {{{x + 3}, {y + 1}}}, force = f}} end")
    lines.append("rcon.print(n)")
    return "\n".join(lines)


def build(r, cat, plan):
    """Paste every layout at its origin, power it; -> {(case, router): {producers, consumers}}
    with the chests' unit numbers."""
    xs = list(range(len(plan)))
    span = (-16, -16, len(plan) * PITCH + 16, 120)
    r.lua(f"local s = game.get_surface('{SURFACE}') s.request_to_generate_chunks("
          f"{{{span[2] // 2}, 40}}, {math.ceil(span[2] / 64) + 2}) "
          "s.force_generate_chunk_requests() rcon.print(1)")
    placed = {}
    for k, (name, router, m, rows) in enumerate(plan):
        ox = xs[k] * PITCH
        moved = [dict(row, x=float(row["x"]) + ox, y=float(row["y"])) for row in rows]
        at = _anchor(moved, cat)
        bp = codec.blueprint(moved, label=f"hourglass {name} {router}")
        got = r.lua(link.lua_paste(SURFACE, FORCE, bp, at)).strip()
        area = scope_area(moved, cat, margin=2)
        rev = r.lua(link.lua_revive(SURFACE, area)).split()
        box = tuple(int(v) for v in scope_area(moved, cat, margin=4))
        spots = _free_spots(moved, cat, box)
        n = r.lua(lua_power(spots)).strip()
        units = json.loads(r.lua(
            f"local s = game.get_surface('{SURFACE}') local o = {{}} "
            f"for _, e in pairs(s.find_entities_filtered{{area = {{{{{area[0]}, {area[1]}}}, "
            f"{{{area[2]}, {area[3]}}}}}, name = 'steel-chest'}}) do "
            "o[#o + 1] = {e.position.x, e.position.y, e.unit_number} end "
            "local dark = 0 for _, e in pairs(s.find_entities_filtered{area = "
            f"{{{{{area[0]}, {area[1]}}}, {{{area[2]}, {area[3]}}}}}, type = 'inserter'}}) do "
            "if not e.is_connected_to_electric_network() then dark = dark + 1 end end "
            "rcon.print(helpers.table_to_json({chests = o, dark = dark}))").strip())
        by_pos = {(float(x), float(y)): (float(x), float(y)) for x, y, _u in units["chests"]}
        prod, cons = [], []
        for row in moved:
            if row["name"] != "steel-chest":
                continue
            u = by_pos.get((float(row["x"]), float(row["y"])))
            (prod if row["src"].startswith("p") else cons).append((row["src"], u,
                                                                    _rate(name, row["src"])))
        # a consumer's chest holds one stack: past that its inserter stops (it takes at its rate)
        r.lua(f"local s, n = game.get_surface('{SURFACE}'), 0 for _, p in pairs({{"
              + ", ".join(f"{{{u[0]}, {u[1]}}}" for _s, u, _r in cons if u)
              + "}) do local e = s.find_entity('steel-chest', p) "
              "e.get_inventory(defines.inventory.chest).set_bar(2) "
              "e.insert{name = 'iron-plate', count = 100} n = n + 1 end rcon.print(n)")
        placed[(name, router)] = {"producers": prod, "consumers": cons, "m": m}
        print(f"{name:7} {router:8} at x {ox}: pasted {got}, revived {rev[0] if rev else '?'}"
              f"{' (' + rev[1] + ' failed)' if len(rev) > 1 and rev[1] != '0' else ''}, "
              f"{n} power spots, {units['dark']} inserters without power, "
              f"{len(prod)} producers, {len(cons)} consumers")
    return placed


def _rate(case, src):
    """A chest's rate in its case (``hourglass.source``: a consumer takes its share)."""
    key = src.split("/")[0]
    rates, consumers, _w = hourglass.spec(case)
    if key.startswith("p"):
        return rates[int(key[1:])]
    return round(sum(rates) / consumers, 4)


def _id(u):
    return f"{u[0]:g},{u[1]:g}"


def lua_meter(give, take):
    """Insert ``give`` {chest position: n} plates, remove up to ``take`` {position: n}; -> the
    plates removed and every chest's count, by ``_id`` of its position."""
    def entries(d, every=False):
        return ", ".join(f"{{{u[0]}, {u[1]}, {n}, '{_id(u)}'}}" for u, n in d.items()
                         if every or n > 0)
    return f"""
local s, out, have = game.get_surface('{SURFACE}'), {{}}, {{}}
for _, g in pairs({{{entries(give)}}}) do local e = s.find_entity('steel-chest', {{g[1], g[2]}})
  if e then e.insert{{name = 'iron-plate', count = g[3]}} end end
for _, t in pairs({{{entries(take)}}}) do local e = s.find_entity('steel-chest', {{t[1], t[2]}})
  out[t[4]] = e and e.remove_item{{name = 'iron-plate', count = t[3]}} or 0 end
for _, c in pairs({{{entries({**give, **take}, True)}}}) do
  local e = s.find_entity('steel-chest', {{c[1], c[2]}})
  have[c[4]] = e and e.get_item_count('iron-plate') or -1 end
rcon.print(helpers.table_to_json({{took = out, have = have}}))
"""


def run(r, placed, warm, secs, step):
    """Meter the chests every ``step`` seconds for ``warm + secs``; -> {(case, router): stats}."""
    acc_give, acc_take, took = {}, {}, {}
    chests = [(k, c) for k, v in placed.items() for c in v["producers"] + v["consumers"]]
    tick = int(r.lua("rcon.print(game.tick)").strip())
    r.lua("game.tick_paused = true rcon.print(1)")
    t0, have, first = time.time(), {}, {}
    i0, last = warm // step, (warm + secs) // step
    for i in range(last + 1):
        give, take = {}, {}
        for k, (src, u, rate) in chests:
            if u is None:
                continue
            if src.startswith("p"):
                acc_give[u] = acc_give.get(u, 0.0) + rate * step
                give[u] = int(acc_give[u])
                acc_give[u] -= give[u]
            else:
                acc_take[u] = acc_take.get(u, 0.0) + rate * step
                take[u] = int(acc_take[u])
        got = json.loads(r.lua(lua_meter(give, take)).strip())
        have = got["have"] if isinstance(got["have"], dict) else {}
        ids = {_id(u): u for u in take}
        for su, n in (got["took"] if isinstance(got["took"], dict) else {}).items():
            u = ids[su]
            acc_take[u] -= n
            acc_take[u] = min(acc_take[u], 1.0)         # unused allowance is not saved up
            if i > i0:
                took[u] = took.get(u, 0) + n
        if i == i0:
            first = dict(have)
        if i < last:
            tick += step * 60
            _run_to(r, tick, speed=64)
    secs = (last - i0) * step
    stats = {}
    for k, v in placed.items():
        m = v["m"]
        rows = []
        for src, u, rate in v["consumers"]:
            # what reached it: what it gave up, and what its chest gained (it starts a stack full,
            # so a consumer the network starves shows as one, not as one the others got ahead of)
            got = took.get(u, 0) + have.get(_id(u), 0) - first.get(_id(u), 0)
            rows.append((src, got / secs, rate))
        total = sum(g for _s, g, _r in rows)
        ratios = [g / rt for _s, g, rt in rows if rt]
        mean = sum(ratios) / len(ratios) if ratios else 0.0
        sd = math.sqrt(sum((x - mean) ** 2 for x in ratios) / len(ratios)) if ratios else 0.0
        waiting = sum(max(0, have.get(_id(u), 0)) for _s, u, _r in v["producers"] if u)
        stats[k] = {"demand": m["demand"], "maxflow": m["maxflow"], "total": total,
                    "low": min(ratios) if ratios else 0.0, "high": max(ratios) if ratios else 0.0,
                    "cv": sd / mean if mean else 0.0, "waiting": waiting, "consumers": rows}
    print(f"ran {warm + secs} game seconds in {time.time() - t0:.0f} s")
    return stats


def table(stats):
    head = ("case", "router", "demand", "maxflow", "took", "took%", "low", "high", "spread",
            "waiting")
    rows = [head]
    for (name, router), s in stats.items():
        rows.append((name, router, f"{s['demand']:.1f}", f"{s['maxflow']:.1f}",
                     f"{s['total']:.1f}", f"{100 * s['total'] / s['demand']:.0f}%",
                     f"{s['low']:.2f}", f"{s['high']:.2f}", f"{s['cv']:.3f}",
                     str(s["waiting"])))
    w = [max(len(r[i]) for r in rows) for i in range(len(head))]
    lines = ["  ".join(c.ljust(w[i]) if i < 2 else c.rjust(w[i]) for i, c in enumerate(r))
             for r in rows]
    lines.insert(1, "  ".join("-" * x for x in w))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only")
    ap.add_argument("--routers", default="m2m,today,balancer")
    ap.add_argument("--big", action="store_true")
    ap.add_argument("--warm", type=int, default=120)
    ap.add_argument("--secs", type=int, default=180)
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    cat = Catalog.load()
    cases = a.only.split(",") if a.only else list(hourglass.CASES) + (
        list(hourglass.BIG) if a.big else [])
    plan = layouts(cases, a.routers.split(","), cat)
    with LaptopServer("hourglass", scenario="fk-play") as srv:
        with srv.rcon() as r:
            bonus = r.lua(f"rcon.print(game.forces['{FORCE}'].inserter_stack_size_bonus .. ' ' .. "
                          f"game.forces['{FORCE}'].belt_stack_size_bonus)").strip()
            print(f"the lab force's inserter stack bonus, belt stack bonus: {bonus}")
            placed = build(r, cat, plan)
            stats = run(r, placed, a.warm, a.secs, a.step)
    text = table(stats)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n\n")
            for (name, router), s in stats.items():
                fh.write(f"{name} {router}: " + ", ".join(
                    f"{src.split('/')[0]} {g:.2f}/{rt:g}" for src, g, rt in s["consumers"]) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
