"""check_library: the 2.1 library's cells built alone on a laptop server's lab surface, each against
the row it replaces, and the sushi mall built from them (PLAN-2.1, "Rows in 2.1" and "G. Buffers";
3.1: was lab_library).

    python tools/check_library.py [cells|labs|acid|mall|all] [--minutes N] [--only a,b]

Every design is a file of ``tests/library``, built beside a copy of the kickoff template's
``game/cells.fk`` on a laptop server ("library", scenario fk-play) with ``fk lab``
(``fkcore.lab.build``: ``fkcore.alone`` on the lab surface, then the stand-ins power and stock). Then the game runs fast,
paused between reads (``ticks_to_run``), and each slot is read: what its crafters finished, what
its chests hold. The provider chests are emptied and the requesters topped up at every read.

- ``cells``: the smelting and assembling lines, cell against row, over ``--minutes`` (10) game
  minutes after two to start up, against the rate model (``rates.solve``).
- ``labs``: the lab lines; the lab force's research reset to logistics-2 and its progress held
  at 0 so the labs never finish it; each lab's working share over a game minute.
- ``acid``: the acid drill cells and the uranium MinerRow on laid uranium, the infinity pipes set
  to sulfuric acid by script (the lab flow doesn't set them); the ore into each chest.
- ``mall``: the sushi mall (``mall.fk``, a BeltEndBuffer) and ``mall_chest.fk`` (a
  ChestEndBuffer), 30 game minutes, read every 2: each maker's rate, what the loop holds of each
  item against its gate, and that every maker crafted in every window.

The lab force has +30% mining productivity (its research is done), so the drills' model is given
with it beside the base rate. Every game call is one RCON command with the link's 5 s timeout,
and nothing is registered.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from fkcore import lab, rates, standin  # noqa: E402
from fkcore.catalog import Catalog  # noqa: E402
from fkcore.elaborate import elaborate_file  # noqa: E402
from laptop_server import LaptopServer, _run_to  # noqa: E402

CAT = Catalog.load()
LIB = os.path.join(ROOT, "tests", "library")
CELLS = os.path.join(ROOT, "kickoff", "template", "game", "cells.fk")

#: (cell design, row design): the row each cell replaces
CELL_PAIRS = (("cu_pair", "cu_array"), ("steel_pair", "steel_array"), ("brick_cell", "brick_row"),
              ("cu_fcell", "cu_frow"), ("steel_fpair", "steel_frow"), ("col_bus", "col_row"),
              ("belt_cell", "belt_row"), ("gear_cell", "gear_row"))
LAB_PAIRS = (("lab_cell", "lab_row"), ("lab_field", "lab_field_row"))
ACID_PAIRS = (("acid_cells", "acid_row"),)
MALLS = ("mall", "mall_chest")


def _game(names):
    run = tempfile.mkdtemp(prefix="fk-lablib-")
    game = os.path.join(run, "game")
    os.makedirs(game)
    shutil.copy(CELLS, game)
    for n in names:
        shutil.copy(os.path.join(LIB, f"{n}.fk"), game)
    return run, game


def _box(game, name):
    x, y, w, h = lab.slots(game)[name]
    return x - 2, y - 2, x + 100, y + 100


def lua_read(box):
    """{tick, crafters: [{n, r, pf, st, x, y}], chests: {name: {item: n}}, belt: {item: n},
    labs: [{x, y, st}]} of what stands in box."""
    x0, y0, x1, y1 = box
    return f"""
local s = game.get_surface('lab')
local area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}
local out = {{tick = game.tick, crafters = {{}}, chests = {{}}, belt = {{}}, labs = {{}}}}
for _, a in pairs(s.find_entities_filtered{{area = area, type = {{'assembling-machine', 'furnace'}}}}) do
  local r = a.get_recipe()
  local rn = r and r.name or ''
  if rn == '' and a.type == 'furnace' then
    local ok, p = pcall(function() return a.previous_recipe end)
    if ok and p then
      local n = p.name
      rn = type(n) == 'string' and n or (n and n.name) or ''
    end
  end
  out.crafters[#out.crafters + 1] = {{n = a.name, x = a.position.x, y = a.position.y,
    r = rn, pf = a.products_finished, st = a.status}}
end
for _, c in pairs(s.find_entities_filtered{{area = area, type = {{'container', 'logistic-container'}}}}) do
  local inv = c.get_inventory(defines.inventory.chest)
  local items = out.chests[c.name] or {{}}
  for _, it in pairs(inv.get_contents()) do items[it.name] = (items[it.name] or 0) + it.count end
  out.chests[c.name] = items
end
for _, b in pairs(s.find_entities_filtered{{area = area, type = 'transport-belt'}}) do
  for l = 1, 2 do
    for _, it in pairs(b.get_transport_line(l).get_contents()) do
      out.belt[it.name] = (out.belt[it.name] or 0) + it.count
    end
  end
end
for _, l in pairs(s.find_entities_filtered{{area = area, type = 'lab'}}) do
  out.labs[#out.labs + 1] = {{x = l.position.x, y = l.position.y, st = l.status}}
end
rcon.print(helpers.table_to_json(out))
"""


def _read(r, box):
    got = json.loads(r.lua(lua_read(box)).strip())
    for k in ("crafters", "labs"):
        if isinstance(got.get(k), dict):
            got[k] = []
    for k in ("chests", "belt"):
        if isinstance(got.get(k), list):
            got[k] = {}
    return got


def _clear(box, names=("passive-provider-chest",)):
    x0, y0, x1, y1 = box
    ns = ", ".join(f"'{n}'" for n in names)
    return (f"local s = game.get_surface('lab') for _, c in pairs(s.find_entities_filtered"
            f"{{area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}, name = {{{ns}}}}}) do "
            "c.get_inventory(defines.inventory.chest).clear() end rcon.print(1)")


def _made(a, b):
    """Crafts finished between two reads, per recipe (a crafter matched by its position)."""
    out = {}
    for c in b["crafters"]:
        c0 = next((x for x in a["crafters"] if (x["x"], x["y"]) == (c["x"], c["y"])), None)
        if c0 is not None:
            out[c["r"]] = out.get(c["r"], 0) + c["pf"] - c0["pf"]
    return out


def _model(game, name):
    flat = elaborate_file(os.path.join(game, f"{name}.fk"), CAT)
    return flat, rates.solve(flat)


def _product_rate(flat, model):
    """{item: per min} the model's crafters make (a recipe's main product)."""
    out = {}
    for k, m in flat.machines.items():
        if m.recipe and m.makes:
            for item, v in m.makes.items():
                out[item] = out.get(item, 0.0) + v * model.util.get(k, 0.0) * 60
    return out


def _build(r, game, names, out):
    ok = True
    for name in names:
        t0 = time.time()
        lines = lab.build(r, game, name, cat=CAT)
        good = any(ln.strip().startswith("diff") and " ok " in ln.lower() + " " for ln in lines)
        diff = next((ln.strip() for ln in lines if ln.strip().startswith("diff")), "no diff line")
        out.append(f"built {name} in {time.time() - t0:.0f} s: {diff}")
        if not good:
            out += ["  " + ln for ln in lines]
        ok = ok and good
    return ok


def _recipes_of(flat):
    """The recipe each crafter's product is counted under: {recipe: (item, items a craft)}."""
    out = {}
    for m in flat.machines.values():
        if m.recipe:
            rec = CAT.recipe(m.recipe)
            prod = rec["products"][0]
            out[m.recipe] = (prod["name"], prod["amount"])
    return out


def check_cells(minutes=10, only=None, every=2):
    pairs = [p for p in CELL_PAIRS if not only or set(p) & set(only)]
    names = [n for p in pairs for n in p]
    run, game = _game(names)
    out, reads = [], {n: [] for n in names}
    with LaptopServer("library", scenario="fk-play") as srv:
        with srv.rcon() as r:
            ok = _build(r, game, names, out)
            r.lua("game.tick_paused = true rcon.print(1)")
            boxes = {n: _box(game, n) for n in names}
            now = int(r.lua("rcon.print(game.tick)").strip())
            _run_to(r, now + 2 * 3600)                    # two game minutes to start up
            for n in names:
                r.lua(_clear(boxes[n]))
                r.lua(standin.lua_supply(lab.SURFACE, lab.FORCE, boxes[n]))
                reads[n].append(_read(r, boxes[n]))
            t0 = reads[names[0]][0]["tick"]
            for k in range(1, int(minutes / every) + 1):
                _run_to(r, t0 + k * every * 3600)
                for n in names:
                    reads[n].append(_read(r, boxes[n]))
                    r.lua(_clear(boxes[n]))
                    r.lua(standin.lua_supply(lab.SURFACE, lab.FORCE, boxes[n]))
            prod = r.lua("local o = {} for _, n in pairs({'iron-plate', 'copper-plate', "
                         "'steel-plate', 'stone-brick', 'iron-gear-wheel', 'transport-belt'}) do "
                         "local rc = game.forces.lab.recipes[n] if rc and rc.productivity_bonus > 0 "
                         "then o[#o + 1] = n .. ' +' .. math.floor(rc.productivity_bonus * 100 + "
                         "0.5) .. '%' end end rcon.print(table.concat(o, ', '))").strip()
    out.append("the lab force's recipe productivity: " + (prod or "none"))
    rows = []
    for cell, row in pairs:
        line = []
        for n in (cell, row):
            flat, model = _model(game, n)
            want = _product_rate(flat, model)
            a, b = reads[n][0], reads[n][-1]
            mins = (b["tick"] - a["tick"]) / 3600.0
            made = _made(a, b)
            rec = _recipes_of(flat)
            got = {rec[k][0]: v * rec[k][1] / mins for k, v in made.items() if k in rec}
            item = max(want, key=want.get)
            line.append((n, got.get(item, 0.0), want[item], item))
        (cn, cg, cw, item), (rn, rg, rw, _i) = line
        rows.append(f"{cell} vs {row} ({item}/min over {minutes} game min): cell {cg:.1f} "
                    f"(model {cw:.1f}, {cg / cw * 100:.1f}%), row {rg:.1f} (model {rw:.1f}, "
                    f"{rg / rw * 100:.1f}%); cell/row {cg / rg * 100:.1f}%")
    print("\n".join(out + rows))
    shutil.rmtree(run, True)
    return 0 if ok else 1


#: a research of red and green packs whose progress is held at 0, so the labs never finish it
RESEARCH = "logistics-2"


def check_labs(seconds=60):
    names = [n for p in LAB_PAIRS for n in p]
    run, game = _game(names)
    out = []
    with LaptopServer("library", scenario="fk-play") as srv:
        with srv.rcon() as r:
            ok = _build(r, game, names, out)
            r.lua(f"local f = game.forces.lab f.technologies['{RESEARCH}'].researched = false "
                  f"f.cancel_current_research() f.add_research('{RESEARCH}') "
                  "rcon.print(f.current_research and f.current_research.name or 'none')")
            speed = float(r.lua("local f = game.forces.lab rcon.print(1 + "
                                "f.laboratory_speed_modifier)").strip())
            unit = float(r.lua(f"rcon.print(game.forces.lab.technologies['{RESEARCH}']"
                               ".research_unit_energy / 60)").strip())
            boxes = {n: _box(game, n) for n in names}
            r.lua("game.tick_paused = true rcon.print(1)")
            now = int(r.lua("rcon.print(game.tick)").strip())
            for k in range(1, 7):                       # three game minutes: the belts fill
                _run_to(r, now + k * 1800)
                r.lua("game.forces.lab.research_progress = 0 rcon.print(1)")
                for n in names:
                    r.lua(standin.lua_supply(lab.SURFACE, lab.FORCE, boxes[n]))
            r.lua("game.tick_paused = false game.speed = 1 rcon.print(1)")
            share = {n: {} for n in names}
            t0, samples = time.time(), 0
            while time.time() - t0 < seconds:
                r.lua("game.forces.lab.research_progress = 0 rcon.print(1)")
                for n in names:
                    for l in _read(r, boxes[n])["labs"]:
                        key = (l["x"], l["y"])
                        share[n][key] = share[n].get(key, 0) + (1 if l["st"] == 1 else 0)
                samples += 1
                time.sleep(0.5)
            r.lua("game.tick_paused = true rcon.print(1)")
    per = 60.0 / unit * speed                           # packs of each a lab takes a minute
    out.append(f"research {RESEARCH}: {unit:.0f} s units, lab speed {speed:.2f}: {per:.2f} packs "
               f"of each a minute for a lab that works all the time; {samples} samples")
    for cell, row in LAB_PAIRS:
        res = []
        for n in (cell, row):
            vals = [v / samples for _k, v in sorted(share[n].items(), key=lambda kv: (kv[0][0],
                                                                                    -kv[0][1]))]
            res.append((n, len(vals), sum(vals)))
            out.append(f"{n}: {len(vals)} labs, working share " + " ".join(f"{v:.2f}" for v in vals))
        (cn, ck, cs), (rn, rk, rs) = res
        out.append(f"{cell} vs {row}: {cs * per:.1f} vs {rs * per:.1f} packs of each a minute "
                   f"(full speed {ck * per:.1f} and {rk * per:.1f}); cell/row {cs / rs * 100:.1f}%")
    print("\n".join(out))
    shutil.rmtree(run, True)
    return 0 if ok else 1


def check_acid(minutes=5):
    names = [n for p in ACID_PAIRS for n in p]
    run, game = _game(names)
    out = []
    with LaptopServer("library", scenario="fk-play") as srv:
        with srv.rcon() as r:
            _build(r, game, names, out)
            for n in names:                             # the ore, then built again on it
                out += lab.ore(r, game, n, resource="uranium-ore", area="0,0,30,10",
                               amount=200000)
            ok = _build(r, game, names, out)
            for n in names:
                x0, y0, x1, y1 = _box(game, n)
                got = r.lua(f"local n = 0 for _, e in pairs(game.get_surface('lab')."
                            f"find_entities_filtered{{area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}, "
                            "name = 'infinity-pipe'}) do e.set_infinity_pipe_filter{name = "
                            "'sulfuric-acid', percentage = 1, mode = 'at-least'} n = n + 1 end "
                            "rcon.print(n)").strip()
                out.append(f"{n}: infinity pipes set to sulfuric acid: {got}")
            bonus = float(r.lua("rcon.print(game.forces.lab.mining_drill_productivity_bonus)")
                          .strip())
            r.lua("game.tick_paused = true rcon.print(1)")
            boxes = {n: _box(game, n) for n in names}
            now = int(r.lua("rcon.print(game.tick)").strip())
            _run_to(r, now + 2 * 3600)
            a = {n: _read(r, boxes[n]) for n in names}
            _run_to(r, a[names[0]]["tick"] + minutes * 3600)
            b = {n: _read(r, boxes[n]) for n in names}
    for cell, row in ACID_PAIRS:
        res = []
        for n in (cell, row):
            flat, model = _model(game, n)
            want = sum(m.makes.get("uranium-ore", 0.0) * model.util.get(k, 0.0)
                       for k, m in flat.machines.items() if m.prototype.endswith("mining-drill")) * 60
            ore = lambda rd: (rd["chests"].get("storage-chest") or {}).get("uranium-ore", 0)
            mins = (b[n]["tick"] - a[n]["tick"]) / 3600.0
            got = (ore(b[n]) - ore(a[n])) / mins
            res.append(got)
            out.append(f"{n}: {got:.1f} uranium ore/min into the chest; model {want:.1f}/min, "
                       f"{want * (1 + bonus):.1f} with the lab force's +{bonus * 100:.0f}% mining "
                       f"productivity ({got / (want * (1 + bonus)) * 100:.1f}%)")
        out.append(f"{cell} vs {row}: cell/row {res[0] / res[1] * 100:.1f}%")
    print("\n".join(out))
    shutil.rmtree(run, True)
    return 0 if ok else 1


def check_mall(minutes=30, every=2, names=MALLS):
    run, game = _game(names)
    out, ok = [], True
    reads = {n: [] for n in names}
    with LaptopServer("library", scenario="fk-play") as srv:
        with srv.rcon() as r:
            ok = _build(r, game, names, out)
            r.lua("game.tick_paused = true rcon.print(1)")
            boxes = {n: _box(game, n) for n in names}
            now = int(r.lua("rcon.print(game.tick)").strip())
            _run_to(r, now + 3600)                       # a game minute to fill the loop
            for n in names:
                r.lua(_clear(boxes[n]))
                r.lua(standin.lua_supply(lab.SURFACE, lab.FORCE, boxes[n]))
                reads[n].append(_read(r, boxes[n]))
            t0, w0 = reads[names[0]][0]["tick"], time.time()
            for k in range(1, int(minutes / every) + 1):
                _run_to(r, t0 + k * every * 3600)
                for n in names:
                    reads[n].append(_read(r, boxes[n]))
                    r.lua(_clear(boxes[n]))
                    r.lua(standin.lua_supply(lab.SURFACE, lab.FORCE, boxes[n]))
            took = time.time() - w0
    for n in names:
        flat, model = _model(game, n)
        out.append(f"== {n}: {minutes} game min in {took:.0f} s, {len(reads[n]) - 1} reads")
        out.append("model: " + "; ".join(rates.buffer_lines(model)))
        rs = reads[n]
        a, b = rs[0], rs[-1]
        mins = (b["tick"] - a["tick"]) / 3600.0
        for path in sorted(p for p in flat.insts if p.count("/") == 0
                           and flat.insts[p].kind == "MallCell"):
            m = flat.machines[f"{path}/a/m0"]
            amount = CAT.recipe(m.recipe)["products"][0]["amount"]
            want = sum(m.makes.values()) * model.util[f"{path}/a/m0"] * 60

            def pf(rd, recipe=m.recipe):
                return amount * sum(c["pf"] for c in rd["crafters"] if c["r"] == recipe)
            windows = [(pf(rs[i + 1]) - pf(rs[i])) / every for i in range(len(rs) - 1)]
            got = (pf(b) - pf(a)) / mins
            out.append(f"{path} {m.recipe}: {got:.1f}/min ({got / want * 100:.0f}% of the model's "
                       f"{want:.1f}), the slowest {every}-min window {min(windows):.1f}/min"
                       + ("" if min(windows) > 0 else " (STOPPED in a window)"))
        for name, (item, gate, _rate, _insts) in sorted(getattr(flat, "gates", {}).items()):
            belt = [rd["belt"].get(item, 0) for rd in rs]
            chest = [(rd["chests"].get("steel-chest") or {}).get(item, 0) for rd in rs]
            loop = [p + q for p, q in zip(belt, chest)]
            out.append(f"{item}: the loop held {min(loop)}..{max(loop)} (gate {gate}; on the belt "
                       f"{min(belt)}..{max(belt)}, in the end chest {min(chest)}..{max(chest)})"
                       + (f"; the chest read by read: {' '.join(map(str, chest))}"
                          if max(chest) else ""))
        out.append("status at the end: " + ", ".join(f"{c['r']} {c['st']}" for c in b["crafters"]))
    print("\n".join(out))
    shutil.rmtree(run, True)
    return 0 if ok else 1


def main(argv):
    what = argv[0] if argv and not argv[0].startswith("--") else "all"
    minutes = None
    only = None
    if "--minutes" in argv:
        minutes = float(argv[argv.index("--minutes") + 1])
    if "--only" in argv:
        only = argv[argv.index("--only") + 1].split(",")
    checks = {"cells": lambda: check_cells(minutes or 10, only), "labs": check_labs,
              "acid": lambda: check_acid(minutes or 5),
              "mall": lambda: check_mall(minutes or 30, names=only or MALLS)}
    if what == "all":
        return max(fn() for fn in checks.values())
    return checks[what]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
