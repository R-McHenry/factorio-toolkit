"""lab_bench: exercise the V1 core against the live game, on the lab surface only (no play).

Run on the game host from a deployed v5 dir:  python3 tools/lab_bench.py [--plot X,Y] [--steps ...]
Every game call is one RCON command with a 5 s timeout; nothing registers a handler or a
command (fkcore.link refuses that Lua). Everything happens on the ``lab`` surface for the ``lab``
force, whose rules allow direct building and free materials; nauvis is only read (alerts check).

Steps (each prints numbers; all of them go into the JSON report):
  info     the map: tick, scenario, surfaces, forces, the lab force's research, players
  link     snapshot an empty area; a named paste of a 3-entity blueprint (where it lands); decon
  apply    compose games/redgreen/main.fkp onto a lab plot, one superforced paste (offset measured
           and corrected), revive the ghosts (lab: free materials), snapshot, sense: the diff
  look     the live area and the design area rendered with the same renderer: the tiles that differ
  watch    a raw belt in sanctioned space and a raw fix inside the plot next to a net: marks and
           keep; the same look with strict policy counts NOBODY; adopt the fix, sense again
  measure  a gear assembler fed by an infinity chest, on an energy interface: produced per second
           against the nominal model, over two samples
  alerts   players, and what LuaPlayer.get_alerts gives for each
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

from fkcore import adopt, codec, compose, fkp, lang, link, rates, scene, sense  # noqa: E402
from fkcore.catalog import Catalog  # noqa: E402
from fkcore.elaborate import elaborate, elaborate_file  # noqa: E402

SURF, FORCE = "lab", "lab"
LAB_POLICY = {"plots": "keep", "sanctioned": "mark 2h", "notify": "all"}
REPORT = {}


def out(step, **kw):
    REPORT.setdefault(step, {}).update(kw)
    print(f"[{step}] " + ", ".join(f"{k}={v}" for k, v in kw.items()), flush=True)


def bbox_center(rows, cat):
    xs, ys = [], []
    for r in rows:
        for x, y in cat.tiles(r["name"], float(r["x"]), float(r["y"]), r["direction"] or 0):
            xs.append(x)
            ys.append(y)
    return (min(xs) + max(xs) + 1) / 2, (min(ys) + max(ys) + 1) / 2


def lua_json(r, body):
    text = r.lua(body)
    try:
        return json.loads(text)
    except ValueError:
        raise link.LinkError(f"not JSON: {text[:200]}")


def step_info(r, cat, a):
    info = lua_json(r, """
local surfaces, forces = {}, {}
for _, s in pairs(game.surfaces) do surfaces[#surfaces + 1] = s.name end
for _, f in pairs(game.forces) do forces[#forces + 1] = f.name end
local lab = game.forces['lab']
local done, total = 0, 0
if lab then for _, t in pairs(lab.technologies) do total = total + 1 if t.researched then done = done + 1 end end end
local ls = game.get_surface('lab')
rcon.print(helpers.table_to_json({tick = game.tick, level = script.level.level_name,
  surfaces = surfaces, forces = forces, lab_researched = done, lab_techs = total,
  lab_tiles = ls and ls.generate_with_lab_tiles or false, lab_peaceful = ls and ls.peaceful_mode or false,
  players = #game.players, connected = #game.connected_players}))""")
    if "lab" in info.get("surfaces", []):
        info["lab_chunks"] = int(r.lua(link.lua_generate(SURF, FORCE, (a.plot[0] + 20, a.plot[1] + 25),
                                                          4)).strip())
    out("info", **info)
    return info


def step_link(r, cat, a):
    ax, ay = a.plot[0] - 40, a.plot[1]
    area = (ax - 2, ay - 2, ax + 8, ay + 4)
    empty = link.snapshot(r, SURF, area, "bench-empty")
    rows = [{"src": "t/b0", "name": "transport-belt", "x": ax + 0.5, "y": ay + 0.5, "direction": 4,
             "attrs": {}},
            {"src": "t/b1", "name": "transport-belt", "x": ax + 1.5, "y": ay + 0.5, "direction": 4,
             "attrs": {}},
            {"src": "t/c0", "name": "wooden-chest", "x": ax + 2.5, "y": ay + 0.5, "direction": None,
             "attrs": {}}]
    at = bbox_center(rows, cat)
    built = r.lua(link.lua_paste(SURF, FORCE, codec.blueprint(rows), at))
    cap = link.snapshot(r, SURF, area, "bench-paste")
    got = {(t["n"], t["x"], t["y"]) for t in cap["things"] if t["g"]}
    want = {(row["name"], row["x"], row["y"]) for row in rows}
    dx = dy = None
    if got:
        gb = min(t for t in got if t[0] == "transport-belt")
        dx, dy = gb[1] - (ax + 0.5), gb[2] - (ay + 0.5)
    revived = r.lua(link.lua_revive(SURF, area))
    marked = r.lua(link.lua_decon(SURF, FORCE, area))
    removed = r.lua(link.lua_destroy(SURF, area))
    left = link.snapshot(r, SURF, area, "bench-after")
    out("link", empty=len(empty["things"]), pasted=built.strip(), ghosts=len(got),
        exact=got == want, offset=(dx, dy), revived=revived.strip(), decon_marked=marked.strip(),
        destroyed=removed.strip(), left=len(left["things"]), paste_at=at)
    return (dx or 0.0, dy or 0.0)


def _surface(cat, a):
    game = os.path.join(os.path.dirname(HERE), "games", "redgreen")
    main = fkp.load(os.path.join(game, "main.fkp"))
    main.name = "main"
    w, h = main.size
    lay = fkp.loads(f"fkp 1 surface lab\nplot main at {a.plot[0]},{a.plot[1]} rot 0 size {w}x{h}\n")
    flat = elaborate_file(os.path.join(game, "main.fk"), cat)
    nets = {f"main/{n}": net.items for n, net in flat.nets.items()}
    return lay, main, compose.compose(lay, {"main": main}, cat), nets, (a.plot[0], a.plot[1],
                                                                         a.plot[0] + w, a.plot[1] + h)


def step_apply(r, cat, a, offset):
    lay, main, s, nets, box = _surface(cat, a)
    rows = s.rows()
    bp = codec.blueprint(rows, label="apply main (redgreen) on lab")
    at = bbox_center(rows, cat)
    area = (box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2)
    t0 = time.time()
    # a clean plot for every run, and lab terrain: the ore each drill row is designed for
    cleared = r.lua(link.lua_destroy(SURF, area)).strip()
    ore = {}
    for e in s.entities.values():
        if e.attrs.get("resource") and cat.kind(e.name) == "mining-drill":
            ore.setdefault(e.attrs["resource"], []).extend(e.tiles)
    seeded = r.lua(link.lua_seed(SURF, ore)).strip()
    built = link.paste(r, SURF, FORCE, bp, (at[0] - offset[0], at[1] - offset[1]))
    cap = link.snapshot(r, SURF, area, "bench-apply-ghosts")
    want = {(row["name"], float(row["x"]), float(row["y"])) for row in rows}
    got = {(t["n"], float(t["x"]), float(t["y"])) for t in cap["things"] if t["g"]}
    corrected = None
    if want != got and got:
        # measure where it landed (the most common shift of same-name entities) and re-paste
        shifts = {}
        for n, x, y in got:
            for wn, wx, wy in want:
                if wn == n and abs(wx - x) <= 3 and abs(wy - y) <= 3:
                    shifts[(x - wx, y - wy)] = shifts.get((x - wx, y - wy), 0) + 1
        corrected = max(shifts, key=shifts.get) if shifts else None
        r.lua(link.lua_destroy(SURF, area))
        if corrected:
            link.paste(r, SURF, FORCE, bp, (at[0] - offset[0] - corrected[0],
                                            at[1] - offset[1] - corrected[1]))
        cap = link.snapshot(r, SURF, area, "bench-apply-ghosts")
        got = {(t["n"], float(t["x"]), float(t["y"])) for t in cap["things"] if t["g"]}
    revived = r.lua(link.lua_revive(SURF, area)).split()
    live = scene.from_capture(link.snapshot(r, SURF, area, "bench-apply-built"))
    rep = sense.sense(s, live, cat, list(area), LAB_POLICY, net_items=nets)
    with open("/tmp/fk5-bench-apply.txt", "w") as fh:
        fh.write("\n".join(rep.lines()) + "\n")
    out("apply", cleared=cleared, ore_tiles=seeded, design=len(rows), pasted=built.strip(),
        ghosts_where_designed=len(want & got),
        corrected=corrected, revived=revived[0] if revived else "?",
        revive_failed=revived[1] if len(revived) > 1 else "?",
        verdicts=rep.counts(), changes=len(rep.changes), seconds=round(time.time() - t0, 1))
    return lay, main, s, nets, box, area, live


def step_look(r, cat, a, s, area, live):
    design = scene.design_scene(s, cat, list(area))
    d_txt = compose.render_scene(design, cat, area)
    l_txt = compose.render_scene(live, cat, area)
    diff = sum(1 for dl, ll in zip(d_txt.splitlines(), l_txt.splitlines()) for x, y in
               zip(dl.ljust(area[2] - area[0], "."), ll.ljust(area[2] - area[0], ".")) if x != y)
    with open("/tmp/fk5-bench-look.txt", "w") as fh:
        fh.write("--source design\n" + d_txt + "\n\n--source live\n" + l_txt + "\n")
    out("look", rows=len(d_txt.splitlines()), identical=d_txt == l_txt, tiles_differ=diff)


def _free_next_to_route(s, box):
    """A free tile inside the plot, next to a route belt, outside every row frame: (tile, net)."""
    for key in sorted(s.entities):
        e = s.entities[key]
        if "/~" not in key or e.name != "transport-belt":
            continue
        for tx, ty in e.tiles:
            for nx, ny in ((tx + 1, ty), (tx - 1, ty), (tx, ty + 1), (tx, ty - 1)):
                if (nx, ny) in s.tiles or not (box[0] <= nx < box[2] and box[1] <= ny < box[3]):
                    continue
                return (nx, ny), e.attrs["net"]
    return None, None


def step_watch(r, cat, a, lay, main, s, nets, box, area):
    outside = (box[0] - 3, box[1] + 3)
    fix_tile, fix_net = _free_next_to_route(s, box)
    r.lua(f"""
local s = game.get_surface('lab')
s.create_entity{{name = 'transport-belt', position = {{{outside[0] + 0.5}, {outside[1] + 0.5}}}, direction = defines.direction.east, force = 'lab'}}
s.create_entity{{name = 'transport-belt', position = {{{fix_tile[0] + 0.5}, {fix_tile[1] + 0.5}}}, direction = defines.direction.south, force = 'lab'}}
rcon.print('ok')""")
    live = scene.from_capture(link.snapshot(r, SURF, area, "bench-watch"))
    kept = sense.sense(s, live, cat, list(area), LAB_POLICY, net_items=nets)
    strict = sense.sense(s, live, cat, list(area), {"plots": "strict", "sanctioned": "strict"},
                         net_items=nets)
    fix = next(t for t in live["things"] if (math.floor(t["x"]), math.floor(t["y"])) == fix_tile)
    for m in kept.marks:
        lay.marks[m.name] = m
    keys, covered = adopt.adopt(main, lay.plots["main"], [fix], fix_net, cat, lay.marks)
    for name in covered:
        lay.marks.pop(name, None)
    s2 = compose.compose(lay, {"main": main}, cat)
    after = sense.sense(s2, live, cat, list(area), LAB_POLICY, net_items=nets)
    out("watch", marks=[(m.name, len(m.tiles), m.until) for m in kept.marks],
        kept=kept.counts().get("MARKED", 0), strict_nobody=strict.counts().get("NOBODY", 0),
        pushed=len(kept.push), changes=kept.changes, adopted=keys, adopted_net=fix_net,
        after_adopt=after.counts(), invariants_after=len(fkp.invariants(main, cat)))
    r.lua(link.lua_destroy(SURF, (outside[0], outside[1], outside[0] + 1, outside[1] + 1)))


MEASURE_FK = """
src  = Chest<requester, item=iron-plate>
gears = Assembler<recipe=iron-gear-wheel>
box  = Chest<provider>
net plates: src -> gears
net gear:   gears -> box
"""


def step_measure(r, cat, a):
    f = lang.parse(MEASURE_FK, "measure.fk")
    model = rates.solve(elaborate(f, {}, cat, "measure"))
    want = model.inst_rate("gears")
    x, y = a.plot[0] - 40, a.plot[1] + 20
    r.lua(f"""
local s = game.get_surface('lab')
local c = s.create_entity{{name = 'infinity-chest', position = {{{x + 0.5}, {y + 1.5}}}, force = 'lab'}}
c.set_infinity_container_filter(1, {{name = 'iron-plate', count = 100, mode = 'at-least'}})
s.create_entity{{name = 'fast-inserter', position = {{{x + 1.5}, {y + 1.5}}}, direction = defines.direction.west, force = 'lab'}}
s.create_entity{{name = 'assembling-machine-1', position = {{{x + 3.5}, {y + 1.5}}}, recipe = 'iron-gear-wheel', force = 'lab'}}
s.create_entity{{name = 'fast-inserter', position = {{{x + 5.5}, {y + 1.5}}}, direction = defines.direction.west, force = 'lab'}}
s.create_entity{{name = 'iron-chest', position = {{{x + 6.5}, {y + 1.5}}}, force = 'lab'}}
local ei = s.create_entity{{name = 'electric-energy-interface', position = {{{x + 3}, {y + 5}}}, force = 'lab'}}
ei.power_production = 1000000
ei.electric_buffer_size = 1000000
s.create_entity{{name = 'medium-electric-pole', position = {{{x + 3.5}, {y + 3.5}}}, force = 'lab'}}
rcon.print('ok')""")
    time.sleep(4)
    s0 = lua_json(r, link.lua_produced(FORCE, SURF, ["iron-gear-wheel"]))
    time.sleep(a.measure_s)
    s1 = lua_json(r, link.lua_produced(FORCE, SURF, ["iron-gear-wheel"]))
    ticks = s1["tick"] - s0["tick"]
    got = (s1["iron-gear-wheel"] - s0["iron-gear-wheel"]) / (ticks / 60.0) if ticks else 0.0
    out("measure", model_per_s=round(want, 4), measured_per_s=round(got, 4), ticks=ticks,
        crafted=s1["iron-gear-wheel"] - s0["iron-gear-wheel"],
        ratio=round(got / want, 3) if want else None)
    r.lua(link.lua_destroy(SURF, (x - 1, y - 1, x + 9, y + 8)))


def step_alerts(r, cat, a):
    res = lua_json(r, """
local rows = {}
for _, p in pairs(game.players) do
  local n = 0
  for _, by_surface in pairs(p.get_alerts{}) do
    for _, by_type in pairs(by_surface) do n = n + #by_type end
  end
  rows[#rows + 1] = {name = p.name, connected = p.connected, force = p.force.name,
    character = p.character ~= nil, alerts = n}
end
rcon.print(helpers.table_to_json({players = rows, count = #game.players}))""")
    out("alerts", **res)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plot", default="200,200")
    ap.add_argument("--steps", default="info,link,apply,look,watch,measure,alerts")
    ap.add_argument("--measure-s", type=float, default=10.0)
    a = ap.parse_args(argv)
    a.plot = tuple(int(v) for v in a.plot.split(","))
    steps = a.steps.split(",")
    cat = Catalog.load()
    with link.Rcon() as r:
        info = step_info(r, cat, a)
        if SURF not in info.get("surfaces", []):
            print("no lab surface on this map: is it the fk-play scenario?")
            return 2
        offset = step_link(r, cat, a) if "link" in steps else (0.0, 0.0)
        if "apply" in steps:
            lay, main, s, nets, box, area, live = step_apply(r, cat, a, offset)
            if "look" in steps:
                step_look(r, cat, a, s, area, live)
            if "watch" in steps:
                step_watch(r, cat, a, lay, main, s, nets, box, area)
        if "measure" in steps:
            step_measure(r, cat, a)
        if "alerts" in steps:
            step_alerts(r, cat, a)
    with open("/tmp/fk5-bench.json", "w") as fh:
        json.dump(REPORT, fh, indent=1, default=str)
    print("report: /tmp/fk5-bench.json, /tmp/fk5-bench-apply.txt, /tmp/fk5-bench-look.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
