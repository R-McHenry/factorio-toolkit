"""check_buffers: the 2.1 buffer designs built alone on a laptop server's lab surface and measured
(PLAN-2.1 G; 3.1: was lab_buffers).

    python tools/check_buffers.py [line|one|loop|all]

Each check starts a laptop server ("buffers", scenario fk-play), builds its design with ``fk lab``
(``fkcore.lab.build``: ``fkcore.alone`` on the free lab surface, then the stand-ins power and stock), runs the
game fast for a stretch of game time (``ticks_to_run``, paused between reads) and compares what
the game did with what the rate model says (``rates.solve``, its ``BUFFER`` lines):

- ``line``: a drill line into a Buffer (filling), and the same line drained by electric furnaces
  that take more than the drills bring (draining, the buffer filled first by hand: lab rules);
- ``one``: one assembler with a chest end buffer and three sources, each gated on what the buffer
  holds of its item (a wire from the buffer, ``when bw.ITEM < N``);
- ``loop``: four assemblers on a sushi loop of one belt, an end buffer at its end feeding back
  onto its head, three sources gated on what the loop holds (the belt read ``hold-all`` plus the
  end buffer, on one wire), run an hour of game time: the belt never stops. The loop is a Literal
  whose file names its assemblers, so the products leave on routes the router lays to them.

Every game call is one RCON command with the link's 5 s timeout, and nothing is registered.
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

from fkcore import codec, lab, rates, standin  # noqa: E402
from fkcore.catalog import Catalog  # noqa: E402
from fkcore.elaborate import elaborate_file  # noqa: E402
from laptop_server import LaptopServer, _run_to  # noqa: E402

CAT = Catalog.load()

FILL = """\
# line, filling: two electric drills into a Buffer
ore = MinerRow<n=2, resource=iron-ore> @(2, 2, rot 2)
b   = Buffer                           @(4, 9)
net ore_: ore -> b
"""
DRAIN = """\
# line, draining: the same two drills, and three electric furnaces that take more than they bring
ore   = MinerRow<n=2, resource=iron-ore>                         @(2, 2, rot 2)
b     = Buffer                                                  @(4, 9)
smelt = SmelterRow<n=3, ore=iron-ore, machine=electric-furnace> @(10, 12)
box   = Chest<provider>                                         @(6, 22)
net ore_: ore -> b
net feed: b -> smelt
net plates: smelt -> box
"""
ONE = """\
# one machine, a chest end buffer, three sources each gated on what the buffer holds of its item
fe  = Chest<requester, item=iron-plate>          @(0, 0)
gw  = Chest<requester, item=iron-gear-wheel>     @(0, 4)
ec  = Chest<requester, item=electronic-circuit>  @(0, 8)
e   = Buffer                                     @(8, 4)
drill = Assembler<recipe=electric-mining-drill>  @(12, 3)
box = Chest<provider>                            @(18, 4)
wire bw red: e
net s_fe: fe -> e when bw.iron-plate < 40
net s_gw: gw -> e when bw.iron-gear-wheel < 20
net s_ec: ec -> e when bw.electronic-circuit < 12
net feed limited "one inserter from the buffer into the machine takes only what it uses": e -> drill
net done: drill -> box
"""


def _game(files):
    run = tempfile.mkdtemp(prefix="fk-labbuf-")
    game = os.path.join(run, "game")
    os.makedirs(game)
    for name, text in files.items():
        with open(os.path.join(game, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text if isinstance(text, str) else json.dumps(text, indent=1))
    return run, game


def _model(game, name):
    flat = elaborate_file(os.path.join(game, f"{name}.fk"), CAT)
    return flat, rates.solve(flat)


def _box(game, name):
    x, y, w, h = lab.slots(game)[name]
    return x - 2, y - 2, x + w, y + h


def lua_read(box, chests=("steel-chest",)):
    """{tick, chests: [{n, x, y, items}], crafters: [{n, r, pf, st}], belts: count of items}."""
    x0, y0, x1, y1 = box
    names = ", ".join(f"'{n}'" for n in chests)
    return f"""
local s = game.get_surface('lab')
local area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}
local out = {{tick = game.tick, chests = {{}}, crafters = {{}}, belt = {{}}}}
for _, c in pairs(s.find_entities_filtered{{area = area, name = {{{names}}}}}) do
  local inv = c.get_inventory(defines.inventory.chest)
  local items = {{}}
  for _, it in pairs(inv.get_contents()) do items[it.name] = (items[it.name] or 0) + it.count end
  out.chests[#out.chests + 1] = {{n = c.name, x = c.position.x, y = c.position.y, items = items}}
end
for _, a in pairs(s.find_entities_filtered{{area = area, type = {{'assembling-machine', 'furnace'}}}}) do
  local r = a.get_recipe()
  out.crafters[#out.crafters + 1] = {{n = a.name, x = a.position.x, y = a.position.y,
    r = r and r.name or '', pf = a.products_finished, st = a.status}}
end
for _, b in pairs(s.find_entities_filtered{{area = area, type = 'transport-belt'}}) do
  for l = 1, 2 do
    for _, it in pairs(b.get_transport_line(l).get_contents()) do
      out.belt[it.name] = (out.belt[it.name] or 0) + it.count
    end
  end
end
rcon.print(helpers.table_to_json(out))
"""


def _read(r, box, chests=("steel-chest",)):
    return json.loads(r.lua(lua_read(box, chests)).strip())


def _items(read, name="steel-chest"):
    got = {}
    for c in read["chests"]:
        if c["n"] == name:
            for k, v in (c["items"] or {}).items():
                got[k] = got.get(k, 0) + v
    return got


def _per_min(a, b, key_a, key_b):
    ticks = b["tick"] - a["tick"]
    return (key_b - key_a) / (ticks / 3600.0) if ticks else 0.0


def _build(r, game, name, out):
    lines = lab.build(r, game, name, cat=CAT)
    out += lines
    ok = any(ln.strip().startswith("diff") and " ok " in ln.lower() + " " for ln in lines)
    if not ok:
        out.append(f"  {name}: the build did not finish as designed (see the lines above)")
    return ok


def check_line():
    """A drill line into a buffer, filling; then drained by a line that takes more than it gets."""
    run, game = _game({"fill.fk": FILL, "drain.fk": DRAIN})
    out, ok = [], True
    with LaptopServer("buffers", scenario="fk-play") as srv:
        with srv.rcon() as r:
            for name in ("fill", "drain"):
                ok = _build(r, game, name, out) and ok
            r.lua("game.tick_paused = true rcon.print(1)")
            # the drain's buffer gets a stock to drain (lab rules: free materials)
            bx = _box(game, "drain")
            r.lua(f"local s = game.get_surface('lab') for _, c in pairs(s.find_entities_filtered"
                  f"{{area = {{{{{bx[0]}, {bx[1]}}}, {{{bx[2]}, {bx[3]}}}}}, name = 'steel-chest'}}) "
                  "do c.insert{name = 'iron-ore', count = 3000} end rcon.print(1)")
            now = int(r.lua("rcon.print(game.tick)").strip())
            _run_to(r, now + 60 * 60)                       # a game minute to start up
            a = {n: _read(r, _box(game, n)) for n in ("fill", "drain")}
            _run_to(r, a["fill"]["tick"] + 5 * 3600)        # five game minutes measured
            b = {n: _read(r, _box(game, n)) for n in ("fill", "drain")}
            prod = float(r.lua("rcon.print(game.forces.lab.mining_drill_productivity_bonus)").strip())
    out.append(f"the lab force's mining productivity: +{prod * 100:.0f}% (all research done; the "
               "model takes a drill's base rate, so it is given beside it)")
    for name in ("fill", "drain"):
        flat, model = _model(game, name)
        out.append(f"{name}: model " + "; ".join(rates.buffer_lines(model)))
        before, after = _items(a[name]).get("iron-ore", 0), _items(b[name]).get("iron-ore", 0)
        meas = _per_min(a[name], b[name], before, after)
        (got, gave), = model.buffers["b"].values()
        want = (got - gave) * 60
        adj = (got * (1 + prod) - gave) * 60
        out.append(f"{name}: measured {meas:+.1f}/min iron-ore in the buffer ({before} -> {after} "
                   f"over {(b[name]['tick'] - a[name]['tick']) / 60:.0f} game s); model "
                   f"{want:+.1f}/min, {adj:+.1f}/min with the drills' productivity "
                   f"({abs(meas - adj) / max(abs(adj), 1e-9) * 100:.0f}% apart)")
        crafted = {c["r"]: 0 for c in b[name]["crafters"]}
        for c in b[name]["crafters"]:
            c0 = next((x for x in a[name]["crafters"] if (x["x"], x["y"]) == (c["x"], c["y"])), None)
            if c0 is not None:
                crafted[c["r"]] += c["pf"] - c0["pf"]
        if crafted:
            mins = (b[name]["tick"] - a[name]["tick"]) / 3600.0
            out.append(f"{name}: furnaces made " + ", ".join(f"{k} {v / mins:.1f}/min"
                                                             for k, v in crafted.items())
                       + f" (model {model.inst_rate('smelt') * 60:.1f}/min)")
    print("\n".join(out))
    shutil.rmtree(run, True)
    return 0 if ok else 1


def check_one():
    """One assembler, a chest end buffer, three sources gated on what it holds."""
    run, game = _game({"one.fk": ONE})
    out, ok = [], True
    with LaptopServer("buffers", scenario="fk-play") as srv:
        with srv.rcon() as r:
            ok = _build(r, game, "one", out)
            r.lua("game.tick_paused = true rcon.print(1)")
            box = _box(game, "one")
            now = int(r.lua("rcon.print(game.tick)").strip())
            _run_to(r, now + 60 * 60)
            a = _read(r, box)
            reads = []
            for k in range(1, 11):                      # ten game minutes, a read each
                _run_to(r, a["tick"] + k * 3600)
                r.lua(standin.lua_supply(lab.SURFACE, lab.FORCE, box))              # the requesters topped up
                reads.append(_read(r, box))
    flat, model = _model(game, "one")
    out.append("model: " + "; ".join(rates.buffer_lines(model)))
    out.append(f"model: drill {model.inst_rate('drill') * 60:.2f}/min, util "
               f"{model.util['drill/m0']:.2f}")
    b = reads[-1]
    mins = (b["tick"] - a["tick"]) / 3600.0
    made = sum(c["pf"] for c in b["crafters"]) - sum(c["pf"] for c in a["crafters"])
    out.append(f"measured: drill {made / mins:.2f}/min over {mins:.0f} game min")
    held = [_items(x) for x in reads]
    for item, top in (("iron-plate", 40), ("iron-gear-wheel", 20), ("electronic-circuit", 12)):
        vals = [h.get(item, 0) for h in held]
        out.append(f"measured: the buffer held {item} {min(vals)}..{max(vals)} (gate {top})")
    print("\n".join(out))
    shutil.rmtree(run, True)
    return 0 if ok else 1


# -- the sushi loop ---------------------------------------------------------------------------------
#: four AM1s on one loop of fast belt: (recipe, x of the machine's centre, items a craft makes).
#: Ingredients per second at speed 0.5: gears 2 iron, cable 1 copper, belts 1 iron + 1 gear,
#: pipe 1 iron: 4 iron, 1 copper and 1 gear a second in all.
LOOP_MACHINES = (("iron-gear-wheel", 4.5, 1), ("copper-cable", 8.5, 2), ("transport-belt", 12.5, 2),
                 ("pipe", 16.5, 1))
#: each source's item and how much of it the loop (belt and end buffer) may hold; a source is a
#: bulk inserter (a fast one brings iron at about 2/s, half what the machines take)
LOOP_GATES = (("iron-plate", 80), ("copper-plate", 40), ("iron-gear-wheel", 40))


def loop_literal():
    """The loop as a Literal file's content: ``{"bp": ..., "names": {"asm1": i, ...}}``.

    The belt runs east along y=5.5 (x 0..20), its end into the end buffer (a steel chest at
    22.5,5.5, filled by an inserter at 21.5,5.5), the buffer emptied by an inserter at 22.5,6.5
    onto the return belt (y=7.5, west), which curves north at x=0.5 into the head: one transport
    line, read ``hold-all`` (at 19.5,5.5). The three sources (infinity chests at y=9.5, x 13.5 to
    19.5) load the return belt through inserters at y=8.5, each enabled while the wire (the belt
    and the end buffer, chained since a wire reaches 9 tiles) holds less than its amount. The four assemblers stand north of the belt, each fed by an inserter at
    y=4.5; their tops stay free for the router's output inserters."""
    rows = []

    def add(name, x, y, d=None, **attrs):
        rows.append({"name": name, "x": x, "y": y, "direction": d, "attrs": dict(attrs)})
        return len(rows) - 1
    E, W, N, S = 4, 12, 0, 8                         # an inserter's direction is its pickup side
    reader = None
    for x in range(0, 21):
        i = add("fast-transport-belt", x + 0.5, 5.5, E)
        if x == 19:
            reader = i
            rows[i]["attrs"]["read"] = "hold-all"
    add("fast-inserter", 21.5, 5.5, W)              # the belt's end -> the end buffer
    end = add("steel-chest", 22.5, 5.5)
    add("fast-inserter", 22.5, 6.5, N)              # the end buffer -> the return belt
    for x in range(22, 0, -1):
        add("fast-transport-belt", x + 0.5, 7.5, W)
    add("fast-transport-belt", 0.5, 7.5, N)
    add("fast-transport-belt", 0.5, 6.5, N)         # up into the head (a curve)
    gates = []
    for k, (item, top) in enumerate(LOOP_GATES):
        sx = 13.5 + 3 * k
        src = add("infinity-chest", sx, 9.5)
        rows[src]["attrs"]["config"] = json.dumps({"infinity_settings": {
            "filters": [{"index": 1, "name": item, "count": 100, "mode": "exactly",
                         "quality": "normal"}], "remove_unfiltered_items": False}},
            sort_keys=True, separators=(",", ":"))
        gates.append(add("bulk-inserter", sx, 8.5, S, **{"if": f"{item}<{top}"}))
    names = {}
    for k, (recipe, x, _n) in enumerate(LOOP_MACHINES, 1):
        names[f"asm{k}"] = add("assembling-machine-1", x, 2.5, recipe=recipe)
        add("fast-inserter", x, 4.5, S)             # from the belt up into the machine
    red = codec.connector("red")
    # a red wire reaches 9 tiles: a chain from the reader belt by the end buffer to the sources
    chain = [reader, end] + gates[::-1]
    links = [(a, red, b, red) for a, b in zip(chain, chain[1:])]
    return {"bp": codec.blueprint(rows, label="sushi loop", links=links), "names": names}


LOOP_FK = """\
# the sushi loop, built as a Literal: four assemblers on one belt, an end buffer, gated sources.
# Each machine's products go to a chest of their own, above it (one belt into one chest would
# take fewer than the six items a second they make).
loop = Literal<file="loop.json"> @(0, 4)
b1 = Chest<provider> @(4, 2)
b2 = Chest<provider> @(8, 2)
b3 = Chest<provider> @(12, 2)
b4 = Chest<provider> @(16, 2)
net d1: loop.asm1 -> b1
net d2: loop.asm2 -> b2
net d3: loop.asm3 -> b3
net d4: loop.asm4 -> b4
"""
LOOP_MODEL = """\
# the sushi loop as the model sees it: the gated sources fill the end buffer e, which feeds
# the loop (in the game the gates read the loop's belt too)
fe = Chest<requester, item=iron-plate>
cu = Chest<requester, item=copper-plate>
gw = Chest<requester, item=iron-gear-wheel>
e  = Buffer
m1 = Assembler<recipe=iron-gear-wheel>
m2 = Assembler<recipe=copper-cable>
m3 = Assembler<recipe=transport-belt>
m4 = Assembler<recipe=pipe>
b1 = Chest<provider>
b2 = Chest<provider>
b3 = Chest<provider>
b4 = Chest<provider>
wire lw red: e
net s_fe: fe -> e when lw.iron-plate < 80
net s_cu: cu -> e when lw.copper-plate < 40
net s_gw: gw -> e when lw.iron-gear-wheel < 40
net loop limited "the end buffer takes what passed every machine and feeds it back": e -> m1, m2, m3, m4
net d1: m1 -> b1
net d2: m2 -> b2
net d3: m3 -> b3
net d4: m4 -> b4
"""


def _clear(box, name):
    """Lua: empty every NAME chest in box (the products' chest, so the machines never back up)."""
    x0, y0, x1, y1 = box
    return (f"local s = game.get_surface('lab') for _, c in pairs(s.find_entities_filtered"
            f"{{area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}, name = '{name}'}}) do "
            "c.get_inventory(defines.inventory.chest).clear() end rcon.print(1)")


def check_loop(hours=1.0, every=2):
    """Four assemblers on a sushi loop, an end buffer, three gated sources: an hour of game time,
    a read every ``every`` game minutes (the products' chest emptied at each)."""
    run, game = _game({"loop.fk": LOOP_FK, "loop.json": loop_literal(), "model.fk": LOOP_MODEL})
    out, ok = [], True
    reads = []
    with LaptopServer("buffers", scenario="fk-play") as srv:
        with srv.rcon() as r:
            ok = _build(r, game, "loop", out)
            r.lua("game.tick_paused = true rcon.print(1)")
            box = _box(game, "loop")
            now = int(r.lua("rcon.print(game.tick)").strip())
            _run_to(r, now + 60 * 60)                   # a game minute to fill the loop
            r.lua(_clear(box, "passive-provider-chest"))
            reads.append(_read(r, box))
            t0 = time.time()
            for k in range(1, int(hours * 60 / every) + 1):
                _run_to(r, reads[0]["tick"] + k * every * 3600)
                reads.append(_read(r, box))
                r.lua(_clear(box, "passive-provider-chest"))
            took = time.time() - t0
    flat, model = _model(game, "model")
    out.append("model: " + "; ".join(rates.buffer_lines(model)))
    a, b = reads[0], reads[-1]
    mins = (b["tick"] - a["tick"]) / 3600.0
    out.append(f"ran {mins:.0f} game min in {took:.0f} s, {len(reads) - 1} reads")
    for k, (recipe, x, n) in enumerate(LOOP_MACHINES, 1):
        def pf(rd):
            return n * next(c["pf"] for c in rd["crafters"] if c["r"] == recipe)
        made = [pf(reads[i + 1]) - pf(reads[i]) for i in range(len(reads) - 1)]
        want = model.inst_rate(f"m{k}") * 60
        got = (pf(b) - pf(a)) / mins
        out.append(f"asm{k} {recipe}: measured {got:.1f}/min ({got / want * 100:.0f}% of the "
                   f"model's {want:.1f}/min), the slowest {every}-min window "
                   f"{min(made) / every:.1f}/min")
    for item, top in LOOP_GATES:
        belt = [rd["belt"].get(item, 0) for rd in reads]
        held = [_items(rd).get(item, 0) for rd in reads]
        loop = [p + q for p, q in zip(belt, held)]
        out.append(f"{item}: the loop held {min(loop)}..{max(loop)} (gate {top}; on the belt "
                   f"{min(belt)}..{max(belt)}, in the end buffer {min(held)}..{max(held)})")
    out.append("machine status at the end: " + ", ".join(f"{c['r']} {c['st']}"
                                                          for c in b["crafters"]))
    print("\n".join(out))
    shutil.rmtree(run, True)
    return 0 if ok else 1


def main(what):
    checks = {"line": check_line, "one": check_one, "loop": check_loop}
    if what == "all":
        return max(fn() for fn in checks.values())
    return checks[what]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "all"))
