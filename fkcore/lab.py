"""fkcore.lab: try a design in the lab and measure it (2.0.3).

    python -m fkcore lab GAME_DIR NAME [--from DIR] [--size WxH]     build NAME on its lab slot
    python -m fkcore lab GAME_DIR NAME --measure SECONDS             what it really makes there
    python -m fkcore lab GAME_DIR NAME --clear                       its slot emptied
    python -m fkcore lab GAME_DIR --list                             the slots in use

Rory (2026-10-22): "the lead should be using the lab and planning rather then waiting if there is
seemingly nothing to do" and "the lead can send workers to do most of the lab work too". The lab
is the game's ``lab`` surface on the ``lab`` force (its research done), where fair play doesn't
apply (FAIR-PLAY.md, "The lab"): building is direct and materials are free. Rory watches it with
``/lab``.

``NAME`` is a factory of the game codebase, or of ``--from DIR`` (a stage folder, a scratch copy;
relative to the run folder). Its source goes into a workspace of its own, ``<run>/lab/NAME``
(never ``game/``, whose build script and surface stay the run's), with a surface file that places
it on its own slot of the lab and the lab's build script. The slot is emptied first, the flow
builds it there (an apply in lab mode: the chunks generated, each drill row's ore seeded under
it, the ghosts revived at once), and the lab gives it what it can't get there: power (an electric
energy interface beside one of its poles), the items its requester chests ask for, and a first
load of coal for burners. ``--measure SECONDS`` reads what its machines make over that time
against the rate model (``fkcore.measure``): let it run a minute or two first, or a backlog that
piled up while it started reads as speed.

2.0.12 (Rory, 2026-10-24: "the lab should be allowed to have infinite size"): the lab has no
edge. It was 2048 tiles square, -1024..1024 (a plot past its edge left ghosts on out-of-map tiles,
found on 2026-10-22), with slots of 200 tiles on a 9 x 9 grid and nothing bigger than 190 x 190.
Now each build first takes the edge off the lab surface (``lua_unbounded``: the scenario does it
too, on a save whose script is new enough) and generates the chunks under its slot. A slot is
sized to its factory, in whole cells of 200 tiles with 10 to spare, so a 450 x 300 factory takes
3 x 2 cells. A new one goes to the free cells nearest the middle, ring by ring, and there is no
last one. A factory that has outgrown its slot gets a new one; the old slot is emptied first.
Every game call is one RCON command with the link's 5 s timeout, and nothing is registered.
"""
from __future__ import annotations

import json
import os
import re
import shutil

from . import flow, link, measure, rates
from . import surface as surfacemod

__all__ = ["LabError", "workspace", "slot_of", "prepare", "build", "measure_lab", "clear",
           "slots"]

SURFACE, FORCE = "lab", "lab"
SLOT = 200                         # tiles a cell spans; a slot is one or more cells each way
ORIGIN = -900                      # a cell's corner is ORIGIN + SLOT * i (2.0.3's grid, extended)
SPARE = 10                         # tiles a slot keeps free beyond its factory
DEFAULT_SIZE = (100, 100)          # a factory no surface file places
#: what the workspace copies from the source: the modules, their layouts, Literals' files, models
_COPY = (".fk", ".fkp", ".json", ".py")
_SKIP = ("map.terrain.json",)

SCRIPT = """# lab.build.fkb (fkcore.lab): the default flow on the lab surface; the apply builds at once
read_surface    lab
read_terrain    none
run_models      --stale
elaborate
size
report_rates
place           --keep pinned
route           --only stale --effort normal
cover power     --pole medium-electric-pole
floorplan
report_checks
report_bom      --stock none
write_layout
apply           --scope all               # lab: chunks generated, ore seeded, revived at once
diff --scope all               # all ok is 1:1
stop_on         invariant
"""


class LabError(ValueError):
    pass


def _run_dir(game):
    return os.path.dirname(os.path.abspath(game))


def workspace(game, name):
    """``<run>/lab/NAME``: the workspace of NAME's lab build."""
    return os.path.join(_run_dir(game), "lab", name)


def _slots_file(game):
    return os.path.join(_run_dir(game), "lab", "slots.json")


def slots(game):
    """{name: [x, y, w, h]}: the slots the lab builds of this run hold (origin and span in
    tiles; a 2.0.3 slot, [x, y], spans one cell)."""
    try:
        with open(_slots_file(game), encoding="utf-8") as fh:
            held = dict(json.load(fh))
    except (OSError, ValueError):
        return {}
    return {n: (list(v) + [SLOT, SLOT])[:4] for n, v in held.items()}


def _save(game, held):
    os.makedirs(os.path.dirname(_slots_file(game)), exist_ok=True)
    with open(_slots_file(game), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(held, fh, indent=0, sort_keys=True)
        fh.write("\n")


def cells(w, h):
    """The cells (each way) a w x h factory's slot spans: whole cells, SPARE tiles to spare."""
    return -(-(int(w) + SPARE) // SLOT), -(-(int(h) + SPARE) // SLOT)


def _free(spot, held):
    x, y, w, h = spot
    return all(x + w <= hx or hx + hw <= x or y + h <= hy or hy + hh <= y
               for hx, hy, hw, hh in held)


def _spots(cw, ch):
    """Slot origins for a slot of cw x ch cells, ring by ring outward from the middle; no end."""
    ring = 0
    while True:
        ring_spots = [(i, j) for j in range(-ring, ring + 1) for i in range(-ring, ring + 1)
                      if max(abs(i), abs(j)) == ring]
        for i, j in sorted(ring_spots, key=lambda ij: (ij[1], ij[0])):
            # cell 4 of 2.0.3's grid holds the middle (-100..100): the rings are around it
            yield (ORIGIN + SLOT * (4 + i - (cw - 1) // 2), ORIGIN + SLOT * (4 + j - (ch - 1) // 2),
                   cw * SLOT, ch * SLOT)
        ring += 1


def slot_of(game, name, size=DEFAULT_SIZE):
    """NAME's slot (x, y, w, h) for a factory of ``size``, the same each time while the factory
    fits it; a new name, or one that outgrew its slot, takes the free spot nearest the middle.
    -> (slot, the slot it outgrew or None)."""
    held = slots(game)
    want = cells(*size)
    old = held.get(name)
    if old is not None and old[2] >= want[0] * SLOT and old[3] >= want[1] * SLOT:
        return tuple(old), None
    others = [tuple(v) for n, v in held.items() if n != name]
    spot = next(s for s in _spots(*want) if _free(s, others))
    held[name] = list(spot)
    _save(game, held)
    return spot, (tuple(old) if old else None)


def _source(game, src):
    """The folder NAME's source comes from: game/, or ``src`` relative to the run folder."""
    if not src:
        return os.path.abspath(game)
    path = os.path.normpath(os.path.join(_run_dir(game), src))
    if os.path.commonpath([path, _run_dir(game)]) != _run_dir(game):
        raise LabError(f"--from {src}: a folder inside the run, such as stages\\3 or scratch\\mall")
    if not os.path.isdir(path):
        raise LabError(f"--from {src}: no such folder ({path})")
    return path


def prepare(game, name, src=None, size=None):
    """Write NAME's workspace: its source, a surface file placing it on its slot, the lab build
    script. -> (workspace, (x, y, w, h) of the plot)."""
    source = _source(game, src)
    module, (w, h) = name, size or DEFAULT_SIZE
    try:
        sf = surfacemod.load_game(source)
    except (OSError, surfacemod.SurfaceError):
        sf = None
    if sf is not None and name in sf.places:
        p = sf.places[name]
        module, w, h = p.module, (size or (p.w, p.h))[0], (size or (p.w, p.h))[1]
    if not os.path.exists(os.path.join(source, f"{module}.fk")):
        raise LabError(f"{name}: no {module}.fk in {source}"
                       + ("" if sf is None else f" (its surface places {', '.join(sorted(sf.places))})"))
    (x, y, _sw, _sh), _old = slot_of(game, name, (w, h))
    ws = workspace(game, name)
    if os.path.isdir(ws):
        shutil.rmtree(ws)
    os.makedirs(ws)
    skip = set(_SKIP) | ({f"{sf.name}.fkp"} if sf is not None else set())
    for f in sorted(os.listdir(source)):
        full = os.path.join(source, f)
        if os.path.isfile(full) and f.endswith(_COPY) and f not in skip \
                and not f.endswith((".surface", ".build.fkb")):
            shutil.copy2(full, os.path.join(ws, f))
    with open(os.path.join(ws, "lab.surface"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# lab.surface (fkcore.lab): {name} from {os.path.relpath(source, _run_dir(game))}"
                 f" on its lab slot\nsurface  lab\nmode     lab\nterrain  none\ncatalog  base\n\n"
                 f"place {name} = {module} plot {x},{y} {w}x{h}\n")
    with open(os.path.join(ws, "lab.build.fkb"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(SCRIPT)
    return ws, (x, y, w, h)


def _box(x, y, w=SLOT, h=SLOT):
    return (x - 2, y - 2, x + w - 8, y + h - 8)


def lua_unbounded():
    """Take the lab surface's edge off (2.0.12; the scenario does it too, on a newer script):
    width and height 0 in its map_gen_settings, which the game reads back as 2000000 (2.0.77).
    -> "unbounded" or "was 2048x2048"."""
    return f"""
local s = game.get_surface('{SURFACE}')
if not s then rcon.print('no lab surface') return end
local m = s.map_gen_settings
if (m.width == 0 or m.width >= 2000000) and (m.height == 0 or m.height >= 2000000) then
  rcon.print('unbounded') return
end
local was = m.width .. 'x' .. m.height
m.width, m.height = 0, 0
s.map_gen_settings = m
rcon.print('was ' .. was)
"""


def lua_clear(box):
    x0, y0, x1, y1 = box
    return f"""
local s = game.get_surface('{SURFACE}')
local n = 0
for _, e in pairs(s.find_entities_filtered{{area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}}}) do
  if e.valid and e.type ~= 'character' and e.type ~= 'resource' then e.destroy() n = n + 1 end
end
rcon.print(n)
"""


def lua_supply(box):
    """Power, the requesters' items and burners' first coal for what stands in ``box`` (lab rules:
    free materials). A requester chest is filled with what it asks for, its slots shared among
    the items: a request is about a minute's worth, which the lab's first run used up before a
    measure (the gears example, 2026-10-22). Run again, it tops them up. The paste's item
    requests (2.0.53: a machine's ``modules=``) go straight into their slots, since no robot
    flies there. -> JSON {power, stocked, fuel, modules}."""
    x0, y0, x1, y1 = box
    return f"""
local s, f = game.get_surface('{SURFACE}'), '{FORCE}'
local area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}
local out = {{power = nil, stocked = {{}}, fuel = 0, modules = 0}}
if s.count_entities_filtered{{area = area, name = 'electric-energy-interface'}} == 0 then
  for _, p in pairs(s.find_entities_filtered{{area = area, type = 'electric-pole'}}) do
    for dx = -3, 3 do for dy = -3, 3 do
      if not out.power then
        local pos = {{p.position.x + dx, p.position.y + dy}}
        if s.can_place_entity{{name = 'electric-energy-interface', position = pos, force = f}} then
          local ei = s.create_entity{{name = 'electric-energy-interface', position = pos, force = f}}
          ei.power_production = 2000000
          ei.electric_buffer_size = 2000000
          out.power = ei.position.x .. ',' .. ei.position.y
        end
      end
    end end
  end
else
  out.power = 'already'
end
for _, c in pairs(s.find_entities_filtered{{area = area, name = 'requester-chest'}}) do
  local ok, rp = pcall(function() return c.get_requester_point() end)
  local want = {{}}
  if ok and rp then
    for _, sec in pairs(rp.sections) do
      for _, fl in pairs(sec.filters) do
        local n = fl.value and fl.value.name
        if n and (fl.min or 0) > 0 and prototypes.item[n] then want[#want + 1] = n end
      end
    end
  end
  local inv = c.get_inventory(defines.inventory.chest)
  local share = #want > 0 and math.max(1, math.floor(#inv / #want)) or 0
  for _, n in pairs(want) do
    local full = prototypes.item[n].stack_size * share
    local k = full - inv.get_item_count(n)
    if k > 0 then
      k = c.insert{{name = n, count = k}}
      out.stocked[n] = (out.stocked[n] or 0) + k
    end
  end
end
for _, e in pairs(s.find_entities_filtered{{area = area}}) do
  local ok, inv = pcall(function() return e.get_fuel_inventory() end)
  if ok and inv and inv.is_empty() then
    inv.insert{{name = 'coal', count = 5}}
    out.fuel = out.fuel + 1
  end
end
for _, p in pairs(s.find_entities_filtered{{area = area, name = 'item-request-proxy'}}) do
  local t = p.proxy_target
  if t and t.valid then
    for _, plan in pairs(p.insert_plan or {{}}) do
      for _, at in pairs((plan.items and plan.items.in_inventory) or {{}}) do
        local inv = t.get_inventory(at.inventory)
        local slot = inv and inv[at.stack + 1]
        if slot and slot.set_stack{{name = plan.id.name, count = at.count or 1,
                                   quality = plan.id.quality or 'normal'}} then
          out.modules = out.modules + (at.count or 1)
        end
      end
    end
    p.destroy()
  end
end
rcon.print(helpers.table_to_json(out))
"""


def clear(r, game, name):
    """Empty NAME's slot and free it. -> the report lines."""
    held = slots(game)
    if name not in held:
        return [f"lab {name}: no slot (fk lab --list)"]
    x, y, w, h = held.pop(name)
    got = r.lua(lua_clear(_box(x, y, w, h))).strip()
    _save(game, held)
    return [f"lab {name}: slot {x},{y} emptied ({got} entities) and freed"]


def build(r, game, name, src=None, size=None, cat=None):
    """NAME on its lab slot: workspace, the slot emptied, the lab flow, then power, the
    requesters' items and burners' first coal. -> the report lines."""
    before = slots(game).get(name)
    ws, (x, y, w, h) = prepare(game, name, src, size)
    sx, sy, sw, sh = slots(game)[name]
    lines = [f"lab {name}: slot {x},{y} ({sw}x{sh} tiles for {w}x{h}) on the lab surface, "
             f"workspace {os.path.relpath(ws, _run_dir(game))} (from {src or 'game'})"]
    edge = r.lua(lua_unbounded()).strip()
    if edge.startswith("was"):
        lines.append(f"  the lab has no edge now (it {edge})")
    if before is not None and list(before) != [sx, sy, sw, sh]:
        moved = r.lua(lua_clear(_box(*before))).strip()
        lines.append(f"  it outgrew its slot at {before[0]},{before[1]}: that one emptied "
                     f"({moved} entities)")
    chunks = r.lua(link.lua_generate_area(SURFACE, FORCE, _box(sx, sy, sw, sh))).strip()
    gone = r.lua(lua_clear(_box(sx, sy, sw, sh))).strip()
    lines.append(f"  emptied first: {gone} entities; {chunks} chunks generated under the slot")
    steps = []
    code, ctx = flow.run(os.path.join(ws, "lab.build.fkb"), cat=cat, echo=steps.append, link=r)
    for want in ("elaborate", "route", "report_checks", "apply", "diff"):
        hit = next((s for s in steps if re.search(rf"\]\s+{want}\b", s)), None)
        if hit:
            lines.append("  " + " ".join(hit.split("]", 1)[1].split()))
    if code != 0:
        lines.append(f"  stopped: {steps[-1] if steps else 'the flow'} (out\\*.txt in the workspace)")
        return lines
    got = json.loads(r.lua(lua_supply(_box(sx, sy, sw, sh))).strip() or "{}")
    stocked = got.get("stocked") or {}
    if isinstance(stocked, list):
        stocked = {}
    lines.append(f"  power: {'an energy interface at ' + got['power'] if got.get('power') not in (None, 'already') else got.get('power') or 'no pole to put an energy interface beside'}"
                 f"; requesters stocked: {', '.join(f'{n} {k}' for n, k in sorted(stocked.items())) or 'none'}"
                 f"; burners given a first load: {got.get('fuel', 0)}"
                 + (f"; modules put in: {got['modules']}" if got.get("modules") else ""))
    lines.append(f"  next: let it run a minute or two, then `fk lab {name} --measure 60`; Rory sees "
                 f"it with /lab at {x + w // 2},{y + h // 2}")
    return lines


# -- ore on the lab (2.0.56, PLAN-CELLS step 3) ----------------------------------------------------
#: one game call reads or writes the ore of at most this many tiles each way (5 s a call)
ORE_BATCH = 32
WORLD = "nauvis"


def _rect(text, what):
    """``X0,Y0,X1,Y1`` -> four ints, X0 < X1 and Y0 < Y1."""
    try:
        x0, y0, x1, y1 = (int(float(v)) for v in str(text).split(","))
    except ValueError:
        raise LabError(f"{what}: X0,Y0,X1,Y1 (four numbers), got {text!r}") from None
    if x1 <= x0 or y1 <= y0:
        raise LabError(f"{what}: {text} is empty (X0 < X1 and Y0 < Y1)")
    return x0, y0, x1, y1


def _batches(x0, y0, x1, y1):
    for by in range(y0, y1, ORE_BATCH):
        for bx in range(x0, x1, ORE_BATCH):
            yield bx, by, min(bx + ORE_BATCH, x1), min(by + ORE_BATCH, y1)


def lua_ore_read(surface, area):
    """The resources whose tile is in ``area`` (x0, y0, x1, y1) of ``surface``:
    JSON [[name, x, y, amount], ...], x and y the tile."""
    x0, y0, x1, y1 = area
    return f"""
local s = game.get_surface('{surface}')
local out = {{}}
for _, e in pairs(s.find_entities_filtered{{area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}, type = 'resource'}}) do
  local x, y = math.floor(e.position.x), math.floor(e.position.y)
  if x >= {x0} and x < {x1} and y >= {y0} and y < {y1} then
    out[#out + 1] = {{e.name, x, y, e.amount}}
  end
end
rcon.print(helpers.table_to_json(out))
"""


def lua_ore_clear(area):
    """Take up the lab's resources whose tile is in ``area``. -> how many."""
    x0, y0, x1, y1 = area
    return f"""
local s = game.get_surface('{SURFACE}')
local n = 0
for _, e in pairs(s.find_entities_filtered{{area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}, type = 'resource'}}) do
  local x, y = math.floor(e.position.x), math.floor(e.position.y)
  if x >= {x0} and x < {x1} and y >= {y0} and y < {y1} then e.destroy() n = n + 1 end
end
rcon.print(n)
"""


def lua_ore_put(rows):
    """Put [[name, x, y, amount], ...] on the lab, each on tile x, y. -> how many stood."""
    data = json.dumps(rows, separators=(",", ":"))
    return f"""
local s = game.get_surface('{SURFACE}')
local n = 0
for _, t in pairs(helpers.json_to_table('{data}')) do
  if s.create_entity{{name = t[1], position = {{t[2] + 0.5, t[3] + 0.5}}, amount = t[4]}} then
    n = n + 1
  end
end
rcon.print(n)
"""


def _slot_for_ore(game, name):
    held = slots(game)
    if name not in held:
        raise LabError(f"{name}: no lab slot yet: build it once (fk lab {name}), then lay its ore")
    return held[name]


def ore(r, game, name, resource=None, area=None, amount=100000, copy=None, to=(0, 0),
        clear_ore=False):
    """Ore on NAME's lab slot, in the design's own coordinates (its plot's top-left is 0,0):
    ``resource`` over ``area``; or ``copy``, the resources of a map area of the world, shape and
    amounts, with its top-left at ``to``; or ``clear_ore``, every resource of the slot taken up.
    A rebuild keeps the ore (it empties a slot of everything but resources), and its drills are
    seeded only where no ore is. -> the report lines."""
    sx, sy, sw, sh = _slot_for_ore(game, name)
    box = _box(sx, sy, sw, sh)
    if clear_ore:
        gone = sum(int(r.lua(lua_ore_clear(b)).strip() or 0) for b in _batches(*box))
        return [f"lab {name}: {gone} ore tiles taken up from its slot {sx},{sy}"]
    r.lua(link.lua_generate_area(SURFACE, FORCE, box))
    if copy is not None:
        x0, y0, x1, y1 = _rect(copy, "--copy-ore")
        tx, ty = sx + int(to[0]), sy + int(to[1])
        dest = (tx, ty, tx + x1 - x0, ty + y1 - y0)
        if dest[0] < box[0] or dest[1] < box[1] or dest[2] > box[2] or dest[3] > box[3]:
            raise LabError(f"--copy-ore {copy} at {to[0]},{to[1]} runs past the slot "
                           f"({sw}x{sh} tiles): copy a smaller area, or build NAME bigger")
        gone = sum(int(r.lua(lua_ore_clear(b)).strip() or 0) for b in _batches(*dest))
        put, kinds, total = 0, {}, 0
        for b in _batches(x0, y0, x1, y1):
            rows = json.loads(r.lua(lua_ore_read(WORLD, b)).strip() or "[]")
            if not isinstance(rows, list):
                rows = []
            moved = [[n, x - x0 + tx, y - y0 + ty, a] for n, x, y, a in rows]
            for n, _x, _y, a in moved:
                kinds[n] = kinds.get(n, 0) + 1
                total += a
            if moved:
                put += int(r.lua(lua_ore_put(moved)).strip() or 0)
        what = ", ".join(f"{n} {k} tiles" for n, k in sorted(kinds.items())) or "no ore"
        return [f"lab {name}: copied {copy} of {WORLD} to {to[0]},{to[1]} of its slot: {what}, "
                f"{total} in all; {put} stood ({gone} lab ore tiles taken up first)"]
    if resource is None or area is None:
        raise LabError("--ore RESOURCE --area X0,Y0,X1,Y1, --copy-ore X0,Y0,X1,Y1 or --clear-ore")
    x0, y0, x1, y1 = _rect(area, "--area")
    dest = (sx + x0, sy + y0, sx + x1, sy + y1)
    gone = sum(int(r.lua(lua_ore_clear(b)).strip() or 0) for b in _batches(*dest))
    put = 0
    for b in _batches(*dest):
        rows = [[resource, x, y, int(amount)] for y in range(b[1], b[3]) for x in range(b[0], b[2])]
        put += int(r.lua(lua_ore_put(rows)).strip() or 0)
    return [f"lab {name}: {resource} on {put} tiles of {area} ({int(amount)} each; {gone} ore "
            "tiles there taken up first)"]


def measure_lab(r, game, name, seconds, cat=None):
    """What NAME's machines make on its lab slot over ``seconds``, against the rate model."""
    ws = workspace(game, name)
    if name not in slots(game) or not os.path.exists(os.path.join(ws, "lab.build.fkb")):
        raise LabError(f"{name}: not built in the lab yet (fk lab {name})")
    code, ctx = flow.run(os.path.join(ws, "lab.build.fkb"), to="report_checks", cat=cat,
                         echo=lambda _l: None)
    if code != 0 or ctx.composed is None:
        raise LabError(f"{name}: its lab design didn't lay out again (out\\*.txt in {ws})")
    x, y, w, h = slots(game)[name]
    top = json.loads(r.lua(lua_supply(_box(x, y, w, h))).strip() or "{}")    # requesters topped up
    stocked = top.get("stocked") if isinstance(top.get("stocked"), dict) else {}
    models = {f: rates.solve(flat) for f, flat in ctx.flats.items()}
    got = measure.measure(r, ctx.composed, ctx.cat, _box(x, y, w, h), ctx.flats, models, seconds)
    head = f"lab {name} (slot {x},{y})"
    if stocked:
        head += ", requesters topped up first: " + ", ".join(f"{n} {k}" for n, k in
                                                               sorted(stocked.items()))
    return [head + ":"] + got.lines()
