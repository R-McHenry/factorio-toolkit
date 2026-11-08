"""measure_lanes: the V2 lane and inserter facts, measured on a laptop test server (3.1: was lab_lanes).

    python tools/measure_lanes.py [TEST ...]    TEST: protos drop sideload ugside splitter drill pickup
                                            rates (default: all of these), and Rory's benchmarks:
                                            balancer stack (about a minute), stackcoal (4 min).
                                            Prints every case and writes out/lab-lanes.json.

CORE-V2.md ("Lane physics", "Inserters") rests on these facts. Each test builds small fixtures on
the lab surface of a short-lived laptop server (tools/laptop_server.py: the laptop's own Factorio,
2.0.77; never the live game), on a force of their own with no research (``v2lab``), lets the game
run fast (``game.speed``) and reads where the items went, lane by lane: the API's transport lines,
1 = the left lane and 2 = the right lane looking along the flow (an underground's 3 and 4 are its
underground halves, a splitter has 8). Nothing registers a handler: build, wait, read.

A case's ``want`` is the rule as CORE-V2.md has it (Rory, 2026-10-20); ``got`` is what the game
did. Lanes are written L (line 1) and R (line 2).
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from fkcore import link  # noqa: E402
from tools.laptop_server import LaptopServer  # noqa: E402

SURF, FORCE = "lab", "v2lab"
SPEED = 10
OUT = os.path.join(ROOT, "out", "lab-lanes.json")
CELL = 24                     # one fixture per CELL x CELL tiles
ROWS = {"drop": 0, "sideload": 1, "ugside": 2, "splitter": 3, "drill": 4, "pickup": 5, "rates": 6,
        "balancer": 7}
BENCH = os.path.join(ROOT, "games", "v2-bench")
STACK_Y = 360                 # the smelter stacks stand from here down (they are 70 tiles tall)

PRELUDE = """
local s = game.get_surface('lab')
local F = '@force@'
local D = defines.direction
local function try(f) local ok, v = pcall(f) if ok then return v end return nil end
local function E(name, x, y, dir, extra)
  local t = {name = name, position = {x, y}, force = F, direction = dir}
  if extra then for k, v in pairs(extra) do t[k] = v end end
  local e = s.create_entity(t)
  if not e then error('cannot place ' .. name .. ' at ' .. x .. ',' .. y) end
  return e
end
local function lanes(e)
  local o = {}
  for i = 1, e.get_max_transport_line_index() do
    local c = {}
    for _, it in pairs(e.get_transport_line(i).get_contents()) do c[it.name] = (c[it.name] or 0) + it.count end
    o[#o + 1] = c
  end
  return o
end
local function fill(e, line, item)
  local l = e.get_transport_line(line)
  local len = try(function() return l.line_length end) or 1
  local n, p = 0, 0
  while p < len do
    if l.can_insert_at(p) and l.insert_at(p, {name = item, count = 1}) then n = n + 1 end
    p = p + 0.25
  end
  return n
end
local function power(x, y)
  local ei = E('electric-energy-interface', x, y)
  ei.power_production = 10000000
  ei.electric_buffer_size = 10000000
  E('substation', x + 2, y)
end
local function inserter(name, x, y, tx, ty)
  for _, d in pairs({D.north, D.east, D.south, D.west}) do
    local e = E(name, x, y, d)
    local p = e.drop_position
    if math.floor(p.x) == tx and math.floor(p.y) == ty then return e end
    e.destroy()
  end
  error('no facing of ' .. name .. ' drops on ' .. tx .. ',' .. ty)
end
local function source(e, item)
  local p = e.pickup_position
  local c = E('infinity-chest', math.floor(p.x) + 0.5, math.floor(p.y) + 0.5)
  c.set_infinity_container_filter(1, {name = item, count = 100, mode = 'at-least'})
  return c
end
local function out(t) rcon.print(helpers.table_to_json(t)) end
"""


def run(r, code, **kw):
    """Run ``code`` after the prelude, @name@ placeholders filled; -> its JSON reply."""
    text = PRELUDE.replace("@force@", FORCE) + code
    for k, v in kw.items():
        text = text.replace(f"@{k}@", str(v))
    got = r.lua(text).strip()
    try:
        return json.loads(got)
    except ValueError:
        raise RuntimeError(f"the game said: {got[:600]}") from None


def origin(test, i):
    return i * CELL, ROWS[test] * CELL + 40


def probe(label, name, x, y):
    return {"label": label, "name": name, "x": x, "y": y}


def read(r, probes):
    """{label: [per transport line {item: count}]} of the entities at the probes (summed per
    label, line by line)."""
    rows = ", ".join("{label = %s, name = %s, x = %s, y = %s}" % (
        json.dumps(p["label"]), json.dumps(p["name"]), p["x"], p["y"]) for p in probes)
    got = run(r, "local P = {" + rows + "} local o = {} for _, p in pairs(P) do "
                 "local e = s.find_entity(p.name, {p.x, p.y}) "
                 "o[#o + 1] = {label = p.label, lanes = e and lanes(e) or 'missing'} end out(o)")
    out = {}
    for row in got:
        lines = row["lanes"]
        if lines == "missing":                       # a probe past the end of a row
            out.setdefault(row["label"], "missing")
            continue
        acc = out.get(row["label"])
        if acc is None or acc == "missing":
            acc = out[row["label"]] = []
        for i, line in enumerate(lines):
            while len(acc) <= i:
                acc.append({})
            for item, n in (line.items() if isinstance(line, dict) else ()):
                acc[i][item] = acc[i].get(item, 0) + n
    return out


def lane_text(lines):
    """'L iron-plate 4; R -' for a belt's two lines (more lines numbered)."""
    if lines == "missing":
        return "missing"
    names = {0: "L", 1: "R"}
    parts = []
    for i, line in enumerate(lines):
        what = ", ".join(f"{k} {v}" for k, v in sorted(line.items())) or "-"
        parts.append(f"{names.get(i, str(i + 1))} {what}")
    return "; ".join(parts)


def where(lines):
    """{item: 'L' | 'R' | 'L+R' | other line numbers} on a belt's lines."""
    if lines == "missing":
        return {}
    out = {}
    for i, line in enumerate(lines):
        for item in line:
            tag = {0: "L", 1: "R"}.get(i, str(i + 1))
            out[item] = tag if item not in out else out[item] + "+" + tag
    return out


# -- protos -------------------------------------------------------------------------------------
def t_protos(r):
    got = run(r, """
local o = {inserters = {}, belts = {}, pumps = {}}
for _, n in pairs({'burner-inserter', 'inserter', 'long-handed-inserter', 'fast-inserter', 'bulk-inserter', 'stack-inserter'}) do
  local p = prototypes.entity[n]
  if p then
    o.inserters[n] = {
      rotation = try(function() return p.get_inserter_rotation_speed() end) or try(function() return p.inserter_rotation_speed end),
      extension = try(function() return p.get_inserter_extension_speed() end) or try(function() return p.inserter_extension_speed end),
      bulk = try(function() return p.bulk end),
      filters = try(function() return p.filter_count end),
      hand_bonus = try(function() return p.inserter_stack_size_bonus end),
      pickup = try(function() return p.inserter_pickup_position end),
      drop = try(function() return p.inserter_drop_position end),
      chases = try(function() return p.inserter_chases_belt_items end),
      belt_stack = try(function() return p.inserter_max_belt_stack_size end)}
  end
end
for _, n in pairs({'transport-belt', 'fast-transport-belt', 'express-transport-belt', 'turbo-transport-belt', 'underground-belt', 'fast-underground-belt', 'express-underground-belt', 'turbo-underground-belt', 'splitter', 'fast-splitter', 'express-splitter', 'turbo-splitter', 'loader', 'fast-loader', 'express-loader', 'turbo-loader', 'loader-1x1'}) do
  local p = prototypes.entity[n]
  if p then o.belts[n] = {speed = try(function() return p.belt_speed end), reach = try(function() return p.max_underground_distance end)} end
end
for _, n in pairs({'pump', 'offshore-pump'}) do
  local p = prototypes.entity[n]
  if p then o.pumps[n] = {speed = try(function() return p.get_pumping_speed() end) or try(function() return p.pumping_speed end)} end
end
for k, f in pairs({fresh = game.forces[F], lab = game.forces['lab']}) do
  o['force_' .. k] = {inserter = try(function() return f.inserter_stack_size_bonus end), bulk = try(function() return f.bulk_inserter_capacity_bonus end), belt_stack = try(function() return f.belt_stack_size_bonus end)}
end
o.mods = script.active_mods
out(o)""")
    rows = []
    for name, p in got["inserters"].items():
        rot = p.get("rotation")
        rows.append({"case": name, "rotation": rot, "extension": p.get("extension"),
                     "bulk": p.get("bulk"), "filters": p.get("filters"),
                     "hand_bonus": p.get("hand_bonus"), "chases": p.get("chases"),
                     "rule_of_thumb_per_s": round(60 * rot, 3) if rot else None})
    return {"raw": got, "rows": rows}


# -- inserter drop lanes --------------------------------------------------------------------------
_VEC = {"east": (1, 0), "north": (0, -1)}
_DIR = {"east": "D.east", "north": "D.north"}


def _side(flow, side):
    fx, fy = _VEC[flow]
    return {"left": (fy, -fx), "right": (-fy, fx), "behind": (-fx, -fy), "ahead": (fx, fy)}[side]


def t_drop(r):
    cases, probes = [], []
    i = 0
    for flow in ("east", "north"):
        for side in ("left", "right", "behind", "ahead"):
            ox, oy = origin("drop", i)
            bx, by = ox + 6, oy + 6
            sx, sy = _side(flow, side)
            want = "L" if side == "right" else "R"
            run(r, """
E('transport-belt', @bx@ + 0.5, @by@ + 0.5, @dir@)
local ins = inserter('fast-inserter', @ix@ + 0.5, @iy@ + 0.5, @bx@, @by@)
source(ins, 'iron-plate')
power(@ox@ + 10, @oy@ + 10)
out({ok = true})""", bx=bx, by=by, dir=_DIR[flow], ix=bx + sx, iy=by + sy, ox=ox, oy=oy)
            label = f"belt {flow}, inserter on its {side}"
            cases.append({"case": label, "want": want})
            probes.append(probe(label, "transport-belt", bx + 0.5, by + 0.5))
            i += 1
    extras = [
        ("onto a turn (fed from its right, nothing behind), inserter on its left", """
E('transport-belt', @bx@ + 0.5, @by@ + 0.5, D.east)
E('transport-belt', @bx@ + 0.5, @by@ + 1.5, D.north)
local ins = inserter('fast-inserter', @bx@ + 0.5, @by@ - 0.5, @bx@, @by@)
source(ins, 'iron-plate')""", "transport-belt", 0.5, 0.5),
        ("onto an underground entrance (east), inserter on its left", """
E('underground-belt', @bx@ + 0.5, @by@ + 0.5, D.east, {type = 'input'})
E('underground-belt', @bx@ + 3.5, @by@ + 0.5, D.east, {type = 'output'})
local ins = inserter('fast-inserter', @bx@ + 0.5, @by@ - 0.5, @bx@, @by@)
source(ins, 'iron-plate')""", "underground-belt", 0.5, 0.5),
        ("onto an underground exit (east), inserter on its left", """
E('underground-belt', @bx@ - 2.5, @by@ + 0.5, D.east, {type = 'input'})
E('underground-belt', @bx@ + 0.5, @by@ + 0.5, D.east, {type = 'output'})
local ins = inserter('fast-inserter', @bx@ + 0.5, @by@ - 0.5, @bx@, @by@)
source(ins, 'iron-plate')""", "underground-belt", 0.5, 0.5),
        ("onto a splitter's left half (east), inserter on its left", """
E('splitter', @bx@ + 0.5, @by@ + 1, D.east)
local ins = inserter('fast-inserter', @bx@ + 0.5, @by@ - 0.5, @bx@, @by@)
source(ins, 'iron-plate')""", "splitter", 0.5, 1.0),
        ("onto an underground entrance (east), inserter behind it (its open half)", """
E('underground-belt', @bx@ + 0.5, @by@ + 0.5, D.east, {type = 'input'})
E('underground-belt', @bx@ + 3.5, @by@ + 0.5, D.east, {type = 'output'})
local ins = inserter('fast-inserter', @bx@ - 0.5, @by@ + 0.5, @bx@, @by@)
source(ins, 'iron-plate')""", "underground-belt", 0.5, 0.5),
        ("onto an underground entrance (east), inserter ahead of it (its hood)", """
E('underground-belt', @bx@ + 0.5, @by@ + 0.5, D.east, {type = 'input'})
E('underground-belt', @bx@ + 3.5, @by@ + 0.5, D.east, {type = 'output'})
local ins = inserter('fast-inserter', @bx@ + 1.5, @by@ + 0.5, @bx@, @by@)
source(ins, 'iron-plate')""", "underground-belt", 0.5, 0.5),
        ("onto an underground exit (east), inserter behind it (its hood)", """
E('underground-belt', @bx@ - 2.5, @by@ + 0.5, D.east, {type = 'input'})
E('underground-belt', @bx@ + 0.5, @by@ + 0.5, D.east, {type = 'output'})
local ins = inserter('fast-inserter', @bx@ - 0.5, @by@ + 0.5, @bx@, @by@)
source(ins, 'iron-plate')""", "underground-belt", 0.5, 0.5),
        ("onto an underground exit (east), inserter ahead of it (its open half)", """
E('underground-belt', @bx@ - 2.5, @by@ + 0.5, D.east, {type = 'input'})
E('underground-belt', @bx@ + 0.5, @by@ + 0.5, D.east, {type = 'output'})
local ins = inserter('fast-inserter', @bx@ + 1.5, @by@ + 0.5, @bx@, @by@)
source(ins, 'iron-plate')""", "underground-belt", 0.5, 0.5),
    ]
    for label, code, name, px, py in extras:
        ox, oy = origin("drop", i)
        bx, by = ox + 6, oy + 6
        run(r, code + " power(@ox@ + 10, @oy@ + 10) out({ok = true})", bx=bx, by=by, ox=ox, oy=oy)
        cases.append({"case": label, "want": None})
        probes.append(probe(label, name, bx + px, by + py))
        i += 1
    return cases, probes


# -- side-loads ---------------------------------------------------------------------------------
_SRC_N = """for y = 2, 7 do local b = E('transport-belt', @ox@ + @sx@ + 0.5, @oy@ + y + 0.5, D.south) fill(b, 1, 'iron-plate') fill(b, 2, 'copper-plate') end"""
_SRC_S = """for y = 9, 14 do local b = E('transport-belt', @ox@ + @sx@ + 0.5, @oy@ + y + 0.5, D.north) fill(b, 1, 'iron-plate') fill(b, 2, 'copper-plate') end"""


def _row(ox, oy, x0, x1, name="transport-belt"):
    return [probe("", name, ox + x + 0.5, oy + 8.5) for x in range(x0, x1 + 1)]


def t_sideload(r):
    """Source belts carry iron-plate on L and copper-plate on R (as the source flows)."""
    cases, probes = [], []
    specs = [
        ("a belt side-loads from the target's left (a belt behind the target)", 3, _SRC_N,
         "both onto L"),
        ("a belt side-loads from the target's right (a belt behind the target)", 3, _SRC_S,
         "both onto R"),
        ("a belt feeds from the left, nothing behind (a turn)", 5, _SRC_N,
         "lanes kept: iron L, copper R"),
    ]
    for i, (label, x0, src, want) in enumerate(specs):
        ox, oy = origin("sideload", i)
        run(r, "for x = @x0@, 8 do E('transport-belt', @ox@ + x + 0.5, @oy@ + 8.5, D.east) end "
               + src + " out({ok = true})", ox=ox, oy=oy, x0=x0, sx=5)
        cases.append({"case": label, "want": want})
        for p in _row(ox, oy, 5, 8):
            p["label"] = label
            probes.append(p)
        sy = 7.5 if src is _SRC_N else 9.5
        probes.append(probe(label + " | source's last tile", "transport-belt", ox + 5.5, oy + sy))
    return cases, probes


def t_ugside(r):
    """A belt side-loads an underground end; the source has iron-plate on L, copper-plate on R."""
    cases, probes = [], []
    specs = [
        ("onto an entrance from its left", 5, 8, 5, _SRC_N, "", "copper passes onto L; iron blocked"),
        ("onto an entrance from its left, a belt behind it", 5, 8, 5, _SRC_N,
         "E('transport-belt', @ox@ + 4.5, @oy@ + 8.5, D.east)", "copper passes onto L; iron blocked"),
        ("onto an exit from its left", 2, 5, 5, _SRC_N, "", "iron passes onto L; copper blocked"),
        ("onto an entrance from its right", 5, 8, 5, _SRC_S, "", "iron passes onto R; copper blocked"),
    ]
    for i, (label, uin, uout, sx, src, extra, want) in enumerate(specs):
        ox, oy = origin("ugside", i)
        run(r, """
E('underground-belt', @ox@ + @uin@ + 0.5, @oy@ + 8.5, D.east, {type = 'input'})
E('underground-belt', @ox@ + @uout@ + 0.5, @oy@ + 8.5, D.east, {type = 'output'})
for x = @uout@ + 1, @uout@ + 4 do E('transport-belt', @ox@ + x + 0.5, @oy@ + 8.5, D.east) end
""" + extra + " " + src + " out({ok = true})", ox=ox, oy=oy, uin=uin, uout=uout, sx=sx)
        cases.append({"case": label, "want": want})
        for p in _row(ox, oy, uout + 1, uout + 4):
            p["label"] = label + " | after the exit"
            probes.append(p)
        sy = 7.5 if src is _SRC_N else 9.5
        probes.append(probe(label + " | source's last tile", "transport-belt", ox + sx + 0.5, oy + sy))
    return cases, probes


def t_splitter(r):
    ox, oy = origin("splitter", 0)
    run(r, """
E('splitter', @ox@ + 5.5, @oy@ + 9, D.east)
for x = 0, 4 do local b = E('transport-belt', @ox@ + x + 0.5, @oy@ + 8.5, D.east) fill(b, 1, 'iron-plate') fill(b, 2, 'copper-plate') end
for x = 0, 4 do E('transport-belt', @ox@ + x + 0.5, @oy@ + 9.5, D.east) end
for x = 6, 10 do E('transport-belt', @ox@ + x + 0.5, @oy@ + 8.5, D.east) E('transport-belt', @ox@ + x + 0.5, @oy@ + 9.5, D.east) end
out({ok = true})""", ox=ox, oy=oy)
    probes = []
    for row, y in (("left output", 8.5), ("right output", 9.5)):
        for x in range(6, 11):
            probes.append(probe(f"splitter, iron L and copper R in | {row}", "transport-belt",
                                ox + x + 0.5, oy + y))
    return [{"case": "splitter, iron L and copper R in", "want": "lanes kept on both outputs"}], \
        probes


def t_drill(r):
    cases, probes = [], []
    specs = [
        ("electric drill facing south onto a belt below it (flowing east)", """
for x = 3, 7 do for y = 3, 7 do s.create_entity{name = 'iron-ore', position = {@ox@ + x + 0.5, @oy@ + y + 0.5}, amount = 5000} end end
E('electric-mining-drill', @ox@ + 5.5, @oy@ + 5.5, D.south)
for x = 3, 9 do E('transport-belt', @ox@ + x + 0.5, @oy@ + 7.5, D.east) end
power(@ox@ + 10, @oy@ + 3)""", 7.5, "L (its near lane)"),
        ("electric drill facing north onto a belt above it (flowing east)", """
for x = 3, 7 do for y = 7, 11 do s.create_entity{name = 'iron-ore', position = {@ox@ + x + 0.5, @oy@ + y + 0.5}, amount = 5000} end end
E('electric-mining-drill', @ox@ + 5.5, @oy@ + 9.5, D.north)
for x = 3, 9 do E('transport-belt', @ox@ + x + 0.5, @oy@ + 7.5, D.east) end
power(@ox@ + 10, @oy@ + 12)""", 7.5, "R (its near lane)"),
        ("burner drill facing south onto a belt below it (flowing east)", """
for x = 4, 5 do for y = 5, 6 do s.create_entity{name = 'iron-ore', position = {@ox@ + x + 0.5, @oy@ + y + 0.5}, amount = 5000} end end
local d = E('burner-mining-drill', @ox@ + 5, @oy@ + 6, D.south)
d.insert{name = 'coal', count = 20}
for x = 2, 8 do E('transport-belt', @ox@ + x + 0.5, @oy@ + 7.5, D.east) end""", 7.5, "L (its near lane)"),
    ]
    for i, (label, code, y, want) in enumerate(specs):
        ox, oy = origin("drill", i)
        run(r, code + " out({ok = true})", ox=ox, oy=oy)
        cases.append({"case": label, "want": want})
        for x in range(2, 10):
            probes.append(probe(label, "transport-belt", ox + x + 0.5, oy + y))
    return cases, probes


# -- pickup from a belt with two items ------------------------------------------------------------
def t_pickup(r):
    """A stopped belt with one item per lane; one fast inserter picks into a furnace (ore and coal),
    an assembler on gears (iron only) and a chest (anything)."""
    specs = [
        ("into a stone furnace from iron-ore L | coal R", "iron-ore", "coal", """
E('stone-furnace', @ox@ + 6, @oy@ + 6)
local ins = inserter('fast-inserter', @ox@ + 5.5, @oy@ + 7.5, @ox@ + 5, @oy@ + 6)""",
         "stone-furnace", 6, 6),
        ("into an assembler on gears from iron-plate L | copper-plate R", "iron-plate",
         "copper-plate", """
E('assembling-machine-1', @ox@ + 5.5, @oy@ + 5.5, nil, {recipe = 'iron-gear-wheel'})
local ins = inserter('fast-inserter', @ox@ + 5.5, @oy@ + 7.5, @ox@ + 5, @oy@ + 6)""",
         "assembling-machine-1", 5.5, 5.5),
        ("into a chest from iron-plate L | copper-plate R", "iron-plate", "copper-plate", """
E('steel-chest', @ox@ + 5.5, @oy@ + 6.5)
local ins = inserter('fast-inserter', @ox@ + 5.5, @oy@ + 7.5, @ox@ + 5, @oy@ + 6)""",
         "steel-chest", 5.5, 6.5),
    ]
    cases = []
    for i, (label, left, right, code, name, mx, my) in enumerate(specs):
        ox, oy = origin("pickup", i)
        run(r, code + """
for x = 2, 9 do local b = E('transport-belt', @ox@ + x + 0.5, @oy@ + 8.5, D.east) fill(b, 1, '@left@') fill(b, 2, '@right@') end
power(@ox@ + 12, @oy@ + 4)
out({ok = true})""", ox=ox, oy=oy, left=left, right=right)
        cases.append({"case": label, "machine": (name, ox + mx, oy + my)})
    return cases


def read_machines(r, cases):
    rows = ", ".join("{label = %s, name = %s, x = %s, y = %s}" % (
        json.dumps(c["case"]), json.dumps(c["machine"][0]), c["machine"][1], c["machine"][2])
        for c in cases)
    return run(r, "local P = {" + rows + "} local o = {} for _, p in pairs(P) do "
                  "local e = s.find_entity(p.name, {p.x, p.y}) local c = {} "
                  "if e then for _, i in pairs({1, 2, 3, 4}) do local inv = try(function() return e.get_inventory(i) end) "
                  "if inv then for _, it in pairs(inv.get_contents()) do c[it.name] = (c[it.name] or 0) + it.count end end end "
                  "local pf = try(function() return e.products_finished end) if pf then c['(crafts)'] = pf end end "
                  "o[#o + 1] = {label = p.label, holds = c} end out(o)")


# -- inserter rates -----------------------------------------------------------------------------
TYPES = ("burner-inserter", "inserter", "long-handed-inserter", "fast-inserter", "bulk-inserter",
         "stack-inserter")


#: a loader faces the way its items move (measured: an output loader takes from the chest behind
#: it, an input loader fills the chest ahead of it; it finds the chest a tick after it is built)
_LINE = """
local function line(x0, y, n, item)
  if item then
    local src = E('infinity-chest', x0 + 0.5, y + 0.5)
    src.set_infinity_container_filter(1, {name = item, count = 100, mode = 'at-least'})
    E('loader-1x1', x0 + 1.5, y + 0.5, D.east, {type = 'output'})
  end
  for x = x0 + 2, x0 + 1 + n do E('transport-belt', x + 0.5, y + 0.5, D.east) end
  local sink = E('steel-chest', x0 + 3.5 + n, y + 0.5)
  E('loader-1x1', x0 + 2.5 + n, y + 0.5, D.east, {type = 'input'})
  return sink
end
"""


def t_rates(r, types):
    """Chest to chest per type; belt to chest and chest to belt on a moving straight belt that
    a loader fills (or not) and a loader drains into a chest; a full belt between two loaders."""
    meters = []
    i = 0
    for name in types:
        ox, oy = origin("rates", i)
        reach = 2 if name == "long-handed-inserter" else 1
        run(r, """
local ins = inserter('@name@', @ox@ + 5.5, @oy@ + 5.5, @tx@, @oy@ + 5)
source(ins, 'iron-plate')
E('steel-chest', @tx@ + 0.5, @oy@ + 5.5)
if '@name@' == 'burner-inserter' then ins.insert{name = 'coal', count = 50} end
power(@ox@ + 10, @oy@ + 10)
out({ok = true})""", name=name, ox=ox, oy=oy, tx=ox + 5 + reach)
        meters.append({"case": f"{name}: chest to chest", "type": name, "kind": "chest",
                       "x": ox + 5 + reach + 0.5, "y": oy + 5.5})
        i += 1
    for name in ("inserter", "fast-inserter", "bulk-inserter"):
        for mode in ("belt to chest", "chest to belt"):
            ox, oy = origin("rates", i)
            full = "true" if mode == "belt to chest" else "false"
            run(r, _LINE + """
local sink = line(@ox@, @oy@ + 6, 12, @full@ and 'iron-plate' or nil)
local ins
if @full@ then ins = inserter('@name@', @ox@ + 7.5, @oy@ + 5.5, @ox@ + 7, @oy@ + 4) E('steel-chest', @ox@ + 7.5, @oy@ + 4.5)
else ins = inserter('@name@', @ox@ + 7.5, @oy@ + 5.5, @ox@ + 7, @oy@ + 6) source(ins, 'iron-plate') end
power(@ox@ + 8, @oy@ + 12)
out({ok = true})""", name=name, ox=ox, oy=oy, full=full)
            if mode == "belt to chest":
                meters.append({"case": f"{name}: {mode} (a full belt, moving)", "type": name,
                               "kind": "chest", "x": ox + 7.5, "y": oy + 4.5})
            else:
                meters.append({"case": f"{name}: {mode} (an empty belt, moving)", "type": name,
                               "kind": "chest", "x": ox + 15.5, "y": oy + 6.5})
            i += 1
    ox, oy = origin("rates", i)
    run(r, _LINE + "line(@ox@, @oy@ + 6, 12, 'iron-plate') out({ok = true})", ox=ox, oy=oy)
    meters.append({"case": "transport-belt: loader to loader, both lanes", "type": None,
                   "kind": "chest", "x": ox + 15.5, "y": oy + 6.5})
    return meters


def read_meters(r, meters):
    rows = []
    for m in meters:
        if m["kind"] == "chest":
            rows.append("{label = %s, kind = 'chest', x = %s, y = %s}" % (
                json.dumps(m["case"]), m["x"], m["y"]))
        else:
            rows.append("{label = %s, kind = 'ring', x0 = %s, y0 = %s, x1 = %s, y1 = %s}" % (
                json.dumps(m["case"]), m["x0"], m["y0"], m["x1"], m["y1"]))
    return run(r, "local P = {" + ", ".join(rows) + "} local o = {tick = game.tick, n = {}} "
                  "for _, p in pairs(P) do local v = -1 "
                  "if p.kind == 'chest' then local c = s.find_entity('steel-chest', {p.x, p.y}) "
                  "if c then v = c.get_item_count('iron-plate') end "
                  "else v = 0 for _, b in pairs(s.find_entities_filtered{area = {{p.x0, p.y0}, "
                  "{p.x1, p.y1}}, type = 'transport-belt', force = F}) do "
                  "v = v + b.get_transport_line(1).get_item_count() + "
                  "b.get_transport_line(2).get_item_count() end end "
                  "o.n[#o.n + 1] = {label = p.label, v = v} end out(o)")


def measure(r, meters, seconds, clear=False):
    if clear:                                       # a lab fixture: empty the sinks first
        rows = ", ".join("{%s, %s}" % (m["x"], m["y"]) for m in meters if m["kind"] == "chest")
        run(r, "for _, p in pairs({" + rows + "}) do local c = s.find_entity('steel-chest', "
               "{p[1], p[2]}) if c then c.clear_items_inside() end end out({ok = true})")
    a = read_meters(r, meters)
    time.sleep(seconds)
    b = read_meters(r, meters)
    ticks = b["tick"] - a["tick"]
    out = {}
    for x, y in zip(a["n"], b["n"]):
        out[x["label"]] = round((y["v"] - x["v"]) / (ticks / 60.0), 3) if ticks else None
    return out, ticks


def bonus(r, inserter, bulk):
    return run(r, "local f = game.forces[F] f.inserter_stack_size_bonus = @i@ "
                  "f.bulk_inserter_capacity_bonus = @b@ out({inserter = f.inserter_stack_size_bonus, "
                  "bulk = f.bulk_inserter_capacity_bonus})", i=inserter, b=bulk)


# -- Rory's benchmarks: the 4-to-4 balancer and the smelter stack ---------------------------------
def _ghosts(name):
    with open(os.path.join(BENCH, name), encoding="utf-8") as fh:
        return json.load(fh)["ghosts"]


def _rows(ghosts):
    """A Lua table of the ghosts: {name, x, y, direction, underground type or false}."""
    return "{" + ", ".join("{%s, %s, %s, %d, %s}" % (
        json.dumps(g["n"]), g["x"], g["y"], g["d"],
        json.dumps(g["ug"]) if g.get("ug") else "false") for g in ghosts) + "}"


_PUT = """
local function put(r, dx, dy)
  local extra = nil
  if r[5] then extra = {type = r[5]} end
  return E(r[1], r[2] + dx, r[3] + dy, r[4], extra)
end
"""

#: (label, inputs fed, outputs taken): inputs and outputs numbered 1 to 4 west to east
BALANCER = (("4 in, 4 out", (1, 2, 3, 4), (1, 2, 3, 4)), ("in 1-3, out 1-3", (1, 2, 3), (1, 2, 3)),
            ("in 1,2,4, out 2-4", (1, 2, 4), (2, 3, 4)), ("in 1, 4 out", (1,), (1, 2, 3, 4)),
            ("4 in, out 1", (1, 2, 3, 4), (1,)), ("4 in, out 1,4", (1, 2, 3, 4), (1, 4)),
            ("in 1,2, out 3,4", (1, 2), (3, 4)))


def t_balancer(r):
    """Rory's balancer, one copy per setup: a loader puts a full belt on each fed input, a loader
    takes each taken output into a chest, the other outputs end."""
    ghosts = _ghosts("balancer-4x4-ghosts.json")
    meters = []
    for i, (label, fed, taken) in enumerate(BALANCER):
        ox, oy = origin("balancer", i)
        dx, dy = ox + 4 - 106, oy + 4 - 118
        run(r, _PUT + """
for _, row in pairs(@rows@) do put(row, @dx@, @dy@) end
for _, k in pairs({@fed@}) do
  local x = 105 + k + @dx@
  local c = E('infinity-chest', x + 0.5, 136.5 + @dy@)
  c.set_infinity_container_filter(1, {name = 'iron-plate', count = 100, mode = 'at-least'})
  E('loader-1x1', x + 0.5, 135.5 + @dy@, D.north, {type = 'output'})
end
for _, k in pairs({@taken@}) do
  local x = 105 + k + @dx@
  E('steel-chest', x + 0.5, 118.5 + @dy@)
  E('loader-1x1', x + 0.5, 119.5 + @dy@, D.north, {type = 'input'})
end
out({ok = true})""", rows=_rows(ghosts), dx=dx, dy=dy, fed=", ".join(map(str, fed)),
            taken=", ".join(map(str, taken)))
        for k in taken:
            meters.append({"case": f"balancer {label}: out {k}", "kind": "chest",
                           "x": 105 + k + dx + 0.5, "y": 118.5 + dy})
    return meters


def t_stack(r, units, bands, x0, coal="loader"):
    """Rory's smelter stack: ``units`` of his unit side by side (x 86..96 of the ghost), each
    ``bands`` bands of 2 furnaces per column; ore by a loader at the bottom of each unit, plates
    into a chest by a loader, coal from the east (a loader: a full belt, or ``coal="inserter"``:
    one fast inserter, 2.5/s on one lane); medium poles on an energy interface."""
    unit = [g for g in _ghosts("smelter-stack-ghosts.json") if 86 <= g["x"] < 97]
    band = [g for g in unit if 108 <= g["y"] < 112 and g["n"] not in ("transport-belt",
                                                                      "underground-belt")]
    dx0, dy = x0 - 86, STACK_Y - 118
    east = dx0 + 11 * (units - 1)
    coal_lua = ("""
local c = E('infinity-chest', 101.5 + @east@, 113.5 + @dy@)
c.set_infinity_container_filter(1, {name = 'coal', count = 100, mode = 'at-least'})
E('loader-1x1', 100.5 + @east@, 113.5 + @dy@, D.west, {type = 'output'})""" if coal == "loader" else """
local ins = inserter('fast-inserter', 100.5 + @east@, 113.5 + @dy@, 99 + @east@, 113 + @dy@)
local c = source(ins, 'coal')
E('medium-electric-pole', 100.5 + @east@, 112.5 + @dy@)""")
    run(r, _PUT + """
for u = 0, @units@ - 1 do
  local dx = @dx0@ + 11 * u
  for _, row in pairs(@unit@) do put(row, dx, @dy@) end
  for b = 1, @bands@ - 1 do
    for _, row in pairs(@band@) do put(row, dx, @dy@ - 4 * b) end
    for y = 108, 111 do
      E('transport-belt', 86.5 + dx, y + 0.5 + @dy@ - 4 * b, D.north)
      E('transport-belt', 91.5 + dx, y + 0.5 + @dy@ - 4 * b, D.south)
      E('transport-belt', 96.5 + dx, y + 0.5 + @dy@ - 4 * b, D.north)
    end
  end
  for b = 0, @bands@ - 1 do
    E('medium-electric-pole', 90.5 + dx, 108.5 + @dy@ - 4 * b)
    E('medium-electric-pole', 95.5 + dx, 108.5 + @dy@ - 4 * b)
  end
  local ore = E('infinity-chest', 89.5 + dx, 119.5 + @dy@)
  ore.set_infinity_container_filter(1, {name = 'iron-ore', count = 100, mode = 'at-least'})
  E('loader-1x1', 89.5 + dx, 118.5 + @dy@, D.north, {type = 'output'})
  E('loader-1x1', 91.5 + dx, 118.5 + @dy@, D.south, {type = 'input'})
  E('steel-chest', 91.5 + dx, 119.5 + @dy@)
end
E('underground-belt', 98.5 + @east@, 113.5 + @dy@, D.west, {type = 'input'})
E('transport-belt', 99.5 + @east@, 113.5 + @dy@, D.west)
""" + coal_lua + """
E('medium-electric-pole', 85.5 + @dx0@, 108.5 + @dy@)
local ei = E('electric-energy-interface', 84 + @dx0@, 111 + @dy@)
ei.power_production = 100000000
ei.electric_buffer_size = 100000000
out({ok = true})""", units=units, bands=bands, unit=_rows(unit), band=_rows(band), dx0=dx0, dy=dy,
        east=east)
    return [{"case": f"stack {units}x{bands} bands, coal by {coal}: unit {u + 1} plates",
             "kind": "chest", "x": 91.5 + dx0 + 11 * u, "y": 119.5 + dy,
             "item": "iron-plate"} for u in range(units)]


def powered(r, x0, y0, x1, y1):
    """How many inserters in the box have no power (an inserter's electric network)."""
    return run(r, "local n, off = 0, 0 for _, e in pairs(s.find_entities_filtered{area = "
                  "{{@x0@, @y0@}, {@x1@, @y1@}}, type = 'inserter', force = F}) do n = n + 1 "
                  "if not e.electric_network_id then off = off + 1 end end "
                  "out({inserters = n, unpowered = off})", x0=x0, y0=y0, x1=x1, y1=y1)


# -- main -----------------------------------------------------------------------------------------
def judge(want, lines):
    if want is None:
        return "(recorded)"
    w = where(lines)
    if want.startswith("both onto"):
        side = want.split()[-1]
        ok = w and all(v == side for v in w.values())
    elif want.startswith("lanes kept: iron L, copper R"):
        ok = w.get("iron-plate") == "L" and w.get("copper-plate") == "R"
    elif want == "lanes kept on both outputs":
        ok = w.get("iron-plate") == "L" and w.get("copper-plate") == "R"
    elif "passes onto" in want:
        item, side = want.split()[0], want.split("onto ")[1].split(";")[0]
        name = {"copper": "copper-plate", "iron": "iron-plate"}[item]
        ok = w == {name: side}
    elif want.startswith(("L", "R")):
        ok = bool(w) and all(v == want[0] for v in w.values())
    else:
        ok = False
    return "OK" if ok else "DIFFERENT"


def main(argv):
    tests = argv or ["protos", "drop", "sideload", "ugside", "splitter", "drill", "pickup", "rates"]
    report = {"tests": tests}
    with LaptopServer("lanes", scenario="fk-play") as srv:
        with srv.rcon() as r:
            r.lua(f"if not game.forces['{FORCE}'] then game.create_force('{FORCE}') end "
                  "rcon.print('ok')")
            r.lua(link.lua_generate_area(SURF, FORCE, (-8, 0, 20 * CELL, STACK_Y + 16)))
            if "protos" in tests:
                report["protos"] = t_protos(r)
                for row in report["protos"]["rows"]:
                    print(f"proto {row['case']:<22} rotation {row['rotation']} extension "
                          f"{row['extension']} bulk {row['bulk']} filters {row['filters']} "
                          f"-> rule of thumb {row['rule_of_thumb_per_s']}/s at hand 1")
            r.lua(f"game.speed = {SPEED} rcon.print('ok')")
            lane_cases, probes = [], []
            for name, fn in (("drop", t_drop), ("sideload", t_sideload), ("ugside", t_ugside),
                             ("splitter", t_splitter), ("drill", t_drill)):
                if name in tests:
                    c, p = fn(r)
                    lane_cases += [dict(x, test=name) for x in c]
                    probes += p
            pick = t_pickup(r) if "pickup" in tests else []
            if lane_cases or pick:
                time.sleep(4)
                got = read(r, probes) if probes else {}
                report["lanes"] = []
                for c in lane_cases:
                    parts = {k: v for k, v in got.items() if k == c["case"]
                             or k.startswith(c["case"] + " |")}
                    main_lines = parts.get(c["case"]) or next(
                        (v for k, v in parts.items() if k.endswith("after the exit")
                         or k.endswith("output")), "missing")
                    if c["case"].startswith("splitter"):
                        main_lines = [{}, {}]
                        for k, v in parts.items():
                            for j, line in enumerate(v[:2] if v != "missing" else []):
                                for item, n in line.items():
                                    main_lines[j][item] = main_lines[j].get(item, 0) + n
                    verdict = judge(c["want"], main_lines)
                    row = {"test": c["test"], "case": c["case"], "want": c["want"],
                           "got": {k: lane_text(v) for k, v in parts.items()},
                           "verdict": verdict}
                    report["lanes"].append(row)
                    print(f"{verdict:<10} {c['test']:<9} {c['case']}")
                    print(f"           want: {c['want']}")
                    for k, v in sorted(parts.items()):
                        print(f"           got:  {k.split(' | ')[-1] if ' | ' in k else 'target'}: "
                              f"{lane_text(v)}")
                if pick:
                    held = read_machines(r, pick)
                    report["pickup"] = held
                    for row in held:
                        print(f"pickup     {row['label']}: holds {row['holds']}")
            if "rates" in tests:
                types = [t for t in TYPES if t in report.get("protos", {}).get("raw", {})
                         .get("inserters", {})] or list(TYPES[:5])
                meters = t_rates(r, types)
                time.sleep(2)
                report["rates"] = []
                for ins_bonus, bulk_bonus in ((0, 0), (1, 1), (2, 3)):
                    set_to = bonus(r, ins_bonus, bulk_bonus)
                    time.sleep(1)
                    got, ticks = measure(r, meters, 3)
                    report["rates"].append({"bonus": set_to, "ticks": ticks, "per_s": got})
                    print(f"rates with force bonus inserter {set_to['inserter']} bulk "
                          f"{set_to['bulk']} over {ticks} ticks:")
                    for k, v in got.items():
                        print(f"           {k:<44} {v}/s")
            if "stackcoal" in tests:
                # scarce coal takes long to settle: furnace fuel slots and belts fill first
                meters = t_stack(r, 3, 12, 100, coal="inserter")
                r.lua("game.speed = 30 rcon.print('ok')")
                report["stackcoal"] = []
                # back to back short windows, each emptying the sinks first, so no plate chest
                # ever fills (a full one stops its furnaces, which then bank coal)
                for window in range(60):
                    got, ticks = measure(r, meters, 3, clear=True)
                    tick = run(r, "out({tick = game.tick})")["tick"]
                    report["stackcoal"].append({"tick": tick, "ticks": ticks, "per_s": got})
                    if window % 6 == 5:
                        print(f"stackcoal at {tick / 60:.0f} s: "
                              + ", ".join(f"{v}/s" for v in got.values()))
            if "balancer" in tests or "stack" in tests:
                meters = []
                if "balancer" in tests:
                    meters += t_balancer(r)
                if "stack" in tests:
                    meters += t_stack(r, 2, 12, 20)
                    meters += t_stack(r, 1, 13, 60)
                    meters += t_stack(r, 3, 12, 100, coal="inserter")
                    report["stack_power"] = powered(r, 0, STACK_Y - 80, 160, STACK_Y + 4)
                    print(f"stack inserters: {report['stack_power']}")
                r.lua(f"game.speed = {SPEED} rcon.print('ok')")
                time.sleep(12)                               # 120 game seconds to fill up
                got, ticks = measure(r, meters, 6)
                report["benchmarks"] = {"ticks": ticks, "per_s": got}
                print(f"benchmarks over {ticks} ticks:")
                for k, v in got.items():
                    print(f"           {k:<52} {v}/s")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
