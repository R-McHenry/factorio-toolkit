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

The lab is 2048 tiles square, -1024..1024 (a plot past its edge leaves ghosts on out-of-map tiles,
found on 2026-10-22), so slots are 200 tiles each on a 9 x 9 grid inside it; a factory bigger than
a slot (190 x 190) isn't tried here. Every game call is one RCON command with the link's 5 s
timeout, and nothing is registered.
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
SLOT = 200                         # tiles a slot spans
GRID = range(-900, 900, SLOT)      # slot origins: 9 x 9 inside the lab's -1024..1024
FIT = SLOT - 10                    # the biggest factory a slot takes
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
diff            --scope all               # all OK is 1:1
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
    """{name: [x, y]}: the slots the lab builds of this run hold."""
    try:
        with open(_slots_file(game), encoding="utf-8") as fh:
            return dict(json.load(fh))
    except (OSError, ValueError):
        return {}


def slot_of(game, name):
    """NAME's slot origin (x, y), the same each time; a new name takes the first free slot."""
    held = slots(game)
    if name in held:
        return tuple(held[name])
    taken = {tuple(v) for v in held.values()}
    for y in GRID:
        for x in GRID:
            if (x, y) not in taken:
                held[name] = [x, y]
                os.makedirs(os.path.dirname(_slots_file(game)), exist_ok=True)
                with open(_slots_file(game), "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(held, fh, indent=0, sort_keys=True)
                    fh.write("\n")
                return (x, y)
    raise LabError(f"every one of the lab's {len(GRID) ** 2} slots is taken: "
                   "`fk lab NAME --clear` frees one")


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
    if w > FIT or h > FIT:
        raise LabError(f"{name} is {w}x{h}: a lab slot takes {FIT}x{FIT} at most")
    x, y = slot_of(game, name)
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


def _box(x, y):
    return (x - 2, y - 2, x + SLOT - 8, y + SLOT - 8)


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
    measure (the gears example, 2026-10-22). Run again, it tops them up. -> JSON {power,
    stocked, fuel}."""
    x0, y0, x1, y1 = box
    return f"""
local s, f = game.get_surface('{SURFACE}'), '{FORCE}'
local area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}
local out = {{power = nil, stocked = {{}}, fuel = 0}}
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
rcon.print(helpers.table_to_json(out))
"""


def clear(r, game, name):
    """Empty NAME's slot and free it. -> the report lines."""
    held = slots(game)
    if name not in held:
        return [f"lab {name}: no slot (fk lab --list)"]
    x, y = held.pop(name)
    got = r.lua(lua_clear(_box(x, y))).strip()
    with open(_slots_file(game), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(held, fh, indent=0, sort_keys=True)
        fh.write("\n")
    return [f"lab {name}: slot {x},{y} emptied ({got} entities) and freed"]


def build(r, game, name, src=None, size=None, cat=None):
    """NAME on its lab slot: workspace, the slot emptied, the lab flow, then power, the
    requesters' items and burners' first coal. -> the report lines."""
    ws, (x, y, w, h) = prepare(game, name, src, size)
    lines = [f"lab {name}: slot {x},{y} ({w}x{h}) on the lab surface, workspace "
             f"{os.path.relpath(ws, _run_dir(game))} (from {src or 'game'})"]
    gone = r.lua(lua_clear(_box(x, y))).strip()
    lines.append(f"  emptied first: {gone} entities")
    steps = []
    code, ctx = flow.run(os.path.join(ws, "lab.build.fkb"), cat=cat, echo=steps.append, link=r)
    for want in ("elaborate", "route", "report_checks", "apply", "diff"):
        hit = next((s for s in steps if re.search(rf"\]\s+{want}\b", s)), None)
        if hit:
            lines.append("  " + " ".join(hit.split("]", 1)[1].split()))
    if code != 0:
        lines.append(f"  stopped: {steps[-1] if steps else 'the flow'} (out\\*.txt in the workspace)")
        return lines
    got = json.loads(r.lua(lua_supply(_box(x, y))).strip() or "{}")
    stocked = got.get("stocked") or {}
    if isinstance(stocked, list):
        stocked = {}
    lines.append(f"  power: {'an energy interface at ' + got['power'] if got.get('power') not in (None, 'already') else got.get('power') or 'no pole to put an energy interface beside'}"
                 f"; requesters stocked: {', '.join(f'{n} {k}' for n, k in sorted(stocked.items())) or 'none'}"
                 f"; burners given a first load: {got.get('fuel', 0)}")
    lines.append(f"  next: let it run a minute or two, then `fk lab {name} --measure 60`; Rory sees "
                 f"it with /lab at {x + w // 2},{y + h // 2}")
    return lines


def measure_lab(r, game, name, seconds, cat=None):
    """What NAME's machines make on its lab slot over ``seconds``, against the rate model."""
    ws = workspace(game, name)
    if name not in slots(game) or not os.path.exists(os.path.join(ws, "lab.build.fkb")):
        raise LabError(f"{name}: not built in the lab yet (fk lab {name})")
    code, ctx = flow.run(os.path.join(ws, "lab.build.fkb"), to="report_checks", cat=cat,
                         echo=lambda _l: None)
    if code != 0 or ctx.composed is None:
        raise LabError(f"{name}: its lab design didn't lay out again (out\\*.txt in {ws})")
    x, y = slots(game)[name]
    top = json.loads(r.lua(lua_supply(_box(x, y))).strip() or "{}")    # requesters topped up
    stocked = top.get("stocked") if isinstance(top.get("stocked"), dict) else {}
    models = {f: rates.solve(flat) for f, flat in ctx.flats.items()}
    got = measure.measure(r, ctx.composed, ctx.cat, _box(x, y), ctx.flats, models, seconds)
    head = f"lab {name} (slot {x},{y})"
    if stocked:
        head += ", requesters topped up first: " + ", ".join(f"{n} {k}" for n, k in
                                                               sorted(stocked.items()))
    return [head + ":"] + got.lines()
