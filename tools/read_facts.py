"""read_facts: the game's facts, read over RCON from a laptop server, into fkcore/data.

    python tools/read_facts.py            reads, writes fkcore/data/facts.json and widens
                                          fkcore/data/catalog.json, and prints what it found
    python tools/read_facts.py --dry      reads and prints, writes nothing
    python tools/read_facts.py --products reads only the recipes' products and writes their
                                          probabilities into catalog.json (2.1, fluid ports)

It starts its own laptop server (``tools/laptop_server.py``, name ``facts``: its own ports and
write-data, never the live game) on the fk-play scenario, base + Space Age as the laptop's
Factorio has them. Each game call is one short RCON command that writes its answer to
script-output (``helpers.write_file``), read back from disk: an RCON reply is one packet. Nothing
is registered in the game.

What it reads (2.1.1, "facts into data"):
- every placeable entity (``items_to_place_this``): size, collision box, energy (source, use,
  drain, burner fuel categories), module slots and allowed effects, mining, crafting, belts,
  poles, inserters, steam and heat values, and its wire connectors (each entity is created on a
  surface of its own, ``fk-facts``, and asked ``get_wire_connectors(true)``);
- resources (mining time, category, results), fuels (fuel value, category, burnt result),
  modules (category, tier, effects), fluids (heat capacity, temperatures) and recipes (allowed
  effects, maximum productivity);
- every signal that can go on a wire: one constant combinator is given every item, fluid,
  virtual signal, recipe, entity, quality, space location and asteroid chunk; what it takes is a
  signal, and what it takes but never puts on its wire (read a few ticks later) never transmits.

- every recipe's products, for their ``probability`` (2.1: the catalog had none, so
  ``uranium-processing`` made a whole U-235 a craft, about 140 times too much). A product the
  game gives with a probability below 1 gets it in its catalog row (and a recycler's
  ``extra_count_fraction``), and ``Catalog.recipe_rates`` counts the expected amount.

``facts.json`` holds the machine facts and the signals. ``catalog.json`` keeps every row it has
(the measured fixture's values stay as they are; a value the game disagrees on is printed, not
changed), gains ``placed_by``, ``energy`` and ``circuit`` on every row, and gains a row for every
placeable entity it lacked.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from fkcore import link  # noqa: E402
from tools.laptop_server import LaptopServer  # noqa: E402

DATA = os.path.join(ROOT, "fkcore", "data")
FACTS = os.path.join(DATA, "facts.json")
CATALOG = os.path.join(DATA, "catalog.json")
OUT = "fk-facts"

#: Lua shared by every call: a guarded field read, a guarded method call, a set's keys, the file
_PRELUDE = """
local function g(o, k) local ok, v = pcall(function() return o[k] end) if ok then return v end end
local function m(o, k, ...) local a = {...} local ok, v = pcall(function() return o[k](table.unpack(a)) end) if ok then return v end end
local function keys(t) local out = {} if type(t) == 'table' then for k, v in pairs(t) do if v then out[#out + 1] = k end end end table.sort(out) return out end
local function save(name, t) helpers.write_file('%s/' .. name .. '.json', helpers.table_to_json(t), false) end
""" % OUT

_ENTITIES = _PRELUDE + """
local rows = {}
for name, p in pairs(prototypes.entity) do
  local items = g(p, 'items_to_place_this')
  if items and #items > 0 then
    local cb = p.collision_box
    local r = {name = name, type = p.type, tile_width = p.tile_width, tile_height = p.tile_height,
      collision_box = {cb.left_top.x, cb.left_top.y, cb.right_bottom.x, cb.right_bottom.y},
      order = p.order, hidden = p.hidden}
    local placed = {} for _, it in pairs(items) do placed[#placed + 1] = it.name end
    r.placed_by = placed
    local e = {}
    local es = g(p, 'electric_energy_source_prototype')
    if es then e.source = 'electric' e.priority = g(es, 'usage_priority') e.drain = g(es, 'drain')
      e.buffer = g(es, 'buffer_capacity') end
    local bp = g(p, 'burner_prototype')
    if bp then e.source = 'burner' e.fuel_categories = keys(g(bp, 'fuel_categories'))
      e.effectivity = g(bp, 'effectivity') end
    if g(p, 'heat_energy_source_prototype') then e.source = 'heat' end
    if g(p, 'fluid_energy_source_prototype') then e.source = 'fluid' end
    if g(p, 'void_energy_source_prototype') then e.source = 'void' end
    e.max_usage = m(p, 'get_max_energy_usage') e.usage = g(p, 'energy_usage')
    e.max_production = m(p, 'get_max_energy_production') e.power_output = m(p, 'get_max_power_output')
    r.energy = e
    r.circuit_reach = m(p, 'get_max_circuit_wire_distance')
    r.crafting_speed = m(p, 'get_crafting_speed')
    r.crafting_categories = g(p, 'crafting_categories') and keys(p.crafting_categories)
    r.mining_speed = g(p, 'mining_speed') r.mining_drill_radius = g(p, 'mining_drill_radius')
    if p.type == 'mining-drill' then r.filter_count = g(p, 'filter_count') end
    local dv = g(p, 'vector_to_place_result') if dv then r.drop_vector = {dv.x or dv[1], dv.y or dv[2]} end
    r.resource_categories = g(p, 'resource_categories') and keys(p.resource_categories)
    r.belt_speed = g(p, 'belt_speed') r.max_distance = g(p, 'max_underground_distance')
    if p.type == 'electric-pole' then r.supply_area_distance = m(p, 'get_supply_area_distance')
      r.max_wire_distance = m(p, 'get_max_wire_distance') end
    if p.type == 'inserter' then r.rotation_speed = m(p, 'get_inserter_rotation_speed')
      r.extension_speed = m(p, 'get_inserter_extension_speed') r.bulk = g(p, 'bulk')
      r.stack_size_bonus = g(p, 'inserter_stack_size_bonus') r.filter_count = g(p, 'filter_count') end
    if p.type == 'beacon' then r.distribution_effectivity = g(p, 'distribution_effectivity')
      r.supply_area_distance = m(p, 'get_supply_area_distance') end
    if p.type == 'roboport' then r.logistic_radius = g(p, 'logistic_radius')
      r.construction_radius = g(p, 'construction_radius') end
    r.module_slots = g(p, 'module_inventory_size')
    r.allowed_effects = g(p, 'allowed_effects') and keys(p.allowed_effects)
    r.allowed_module_categories = g(p, 'allowed_module_categories') and keys(p.allowed_module_categories)
    r.target_temperature = g(p, 'target_temperature') r.maximum_temperature = g(p, 'maximum_temperature')
    r.fluid_usage_per_tick = g(p, 'fluid_usage_per_tick') r.neighbour_bonus = g(p, 'neighbour_bonus')
    r.researching_speed = g(p, 'researching_speed')
    rows[#rows + 1] = r
  end
end
save('entities', rows)
rcon.print(#rows)
"""

_THINGS = _PRELUDE + """
local res, fuels, mods, fluids, recipes = {}, {}, {}, {}, {}
for name, p in pairs(prototypes.get_entity_filtered{{filter = 'type', type = 'resource'}}) do
  local mp = p.mineable_properties
  local out = {}
  for _, pr in pairs(mp.products or {}) do out[#out + 1] = {name = pr.name, type = pr.type} end
  res[name] = {mining_time = mp.mining_time, category = g(p, 'resource_category'),
    infinite = g(p, 'infinite_resource'), required_fluid = mp.required_fluid,
    fluid_amount = mp.fluid_amount, results = out, order = p.order}
end
for name, p in pairs(prototypes.item) do
  local fv = g(p, 'fuel_value')
  if fv and fv > 0 then
    fuels[name] = {fuel_value = fv, category = g(p, 'fuel_category'),
      burnt_result = g(p, 'burnt_result') and p.burnt_result.name or nil, order = p.order}
  end
  if p.type == 'module' then
    mods[name] = {category = g(p, 'category'), tier = g(p, 'tier'), effects = g(p, 'module_effects') or {},
      order = p.order}
  end
end
for name, p in pairs(prototypes.fluid) do
  fluids[name] = {heat_capacity = p.heat_capacity, default_temperature = p.default_temperature,
    max_temperature = p.max_temperature, fuel_value = p.fuel_value, hidden = p.hidden}
end
for name, p in pairs(prototypes.recipe) do
  recipes[name] = {effects = keys(g(p, 'allowed_effects')), max_productivity = g(p, 'maximum_productivity'),
    category = p.category, hidden = p.hidden}
end
local wire_ids = {}
for k, v in pairs(defines.wire_connector_id) do wire_ids[k] = v end
save('things', {resources = res, fuels = fuels, modules = mods, fluids = fluids, recipes = recipes,
  mods = script.active_mods, wire_ids = wire_ids})
rcon.print('ok')
"""

#: every recipe's products as the game gives them: amount (or a range), probability
_PRODUCTS = _PRELUDE + """
local out = {}
for name, p in pairs(prototypes.recipe) do
  local rows = {}
  for _, pr in pairs(p.products or {}) do
    rows[#rows + 1] = {name = pr.name, type = pr.type, amount = pr.amount, amount_min = pr.amount_min,
      amount_max = pr.amount_max, probability = pr.probability,
      extra_count_fraction = pr.extra_count_fraction}
  end
  out[name] = rows
end
save('products', out)
rcon.print('ok')
"""

#: one surface of the reader's own, lab tiles, for the entities it creates
_SURFACE = """
local s = game.get_surface('fk-facts') or game.create_surface('fk-facts')
s.generate_with_lab_tiles = true
s.request_to_generate_chunks({160, 192}, %d)
s.force_generate_chunk_requests()
rcon.print(s.name)
"""

_CREATE = _PRELUDE + """
local s = game.get_surface('fk-facts')
local out = {}
for i, name in ipairs(%s) do
  local x, y = %d + (i - 1) %% 16 * 20, %d + math.floor((i - 1) / 16) * 20
  local ok, e = pcall(function() return s.create_entity{name = name, position = {x, y}, force = 'player'} end)
  local r = {name = name, created = ok and e ~= nil}
  if ok and e then
    local got = {}
    local cs = m(e, 'get_wire_connectors', true) or {}
    for id, _ in pairs(cs) do got[#got + 1] = id end
    table.sort(got)
    r.connectors = got
    e.destroy()
  else r.error = tostring(e) end
  out[#out + 1] = r
end
save('%s', out)
rcon.print(#out)
"""

#: every candidate signal into one constant combinator, wired to a pole; returns what it took
_SIGNALS_SET = _PRELUDE + """
local s = game.get_surface('fk-facts')
local cc = s.create_entity{name = 'constant-combinator', position = {-20.5, -20.5}, force = 'player'}
local pole = s.create_entity{name = 'small-electric-pole', position = {-18.5, -20.5}, force = 'player'}
cc.get_wire_connector(defines.wire_connector_id.circuit_red, true).connect_to(
  pole.get_wire_connector(defines.wire_connector_id.circuit_red, true))
local cb = cc.get_or_create_control_behavior()
local sec = cb.get_section(1) or cb.add_section()
local slot, n = 0, 0
local took, refused = {}, {}
local function try(t, name)
  if slot >= 1000 then sec = cb.add_section() slot = 0 end
  local ok = pcall(function() sec.set_slot(slot + 1, {value = {type = t, name = name, quality = 'normal'}, min = 1}) end)
  if ok then slot = slot + 1 n = n + 1 took[#took + 1] = {t, name} else refused[#refused + 1] = {t, name} end
end
local sets = {item = prototypes.item, fluid = prototypes.fluid, virtual = prototypes.virtual_signal,
  recipe = prototypes.recipe, entity = prototypes.entity, quality = prototypes.quality,
  ['space-location'] = prototypes.space_location, ['asteroid-chunk'] = prototypes.asteroid_chunk}
local special = {}
for t, set in pairs(sets) do
  for name, p in pairs(set) do try(t, name) end
end
for name, p in pairs(prototypes.virtual_signal) do if p.special then special[#special + 1] = name end end
save('signals-set', {took = took, refused = refused, special = special, tick = game.tick})
rcon.print(n)
"""

_SIGNALS_READ = _PRELUDE + """
local s = game.get_surface('fk-facts')
local cc = s.find_entity('constant-combinator', {-20.5, -20.5})
local net = cc.get_circuit_network(defines.wire_connector_id.circuit_red)
local seen = {}
for _, sg in pairs(net and net.signals or {}) do
  seen[#seen + 1] = {sg.signal.type or 'item', sg.signal.name, sg.signal.quality or 'normal', sg.count}
end
save('signals-read', {seen = seen, tick = game.tick})
rcon.print(#seen)
"""


class Attached:
    """A server already running (``--attach``, a pack's game: the Sea Block test server on
    computah-ct, run there), in place of a laptop server of the reader's own."""

    def __init__(self, port, pw_file, write):
        self.port, self.pw_file, self.write = port, pw_file, write

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def rcon(self):
        return link.Rcon("127.0.0.1", self.port, self.pw_file, timeout=CALL_S)


#: ``--attach``: the running server to read instead of starting one
SERVER = None
#: the longest one game call may take: a pack has many more signals (Sea Block: one combinator
#: given ~5,000 of them takes over 5 s), and a pack's server is a test server of its own
CALL_S = 5


def _server(name):
    return SERVER or LaptopServer(name, scenario="fk-play")


def _read(srv, name):
    with open(os.path.join(srv.write, "script-output", OUT, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def _call(r, lua):
    t0 = time.time()
    out = r.lua(lua).strip()
    took = time.time() - t0
    if out.startswith("Cannot execute command"):
        raise RuntimeError(out)
    if took > CALL_S:
        raise RuntimeError(f"a game call took {took:.1f} s")
    return out


def _f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


def clean(v):
    """A number as the game means it: an integral float as an int, else the shortest decimal
    that is the same single-precision value (0.039999999105930328 -> 0.04, 0.014000000000000002 ->
    0.014; -0.8984375 stays), if one is that close."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return v
    if v != v or v in (float("inf"), float("-inf")) or abs(v) >= 1e300:
        return None                    # unbounded (an energy interface): JSON has no infinity
    v = float(v)
    if v.is_integer() and abs(v) < 1e15:
        return int(v)
    if abs(v) < 3e38:
        for p in range(1, 10):
            s = float("%.*g" % (p, v))
            if _f32(s) == _f32(v) and abs(s - v) <= 1e-6 * max(1.0, abs(v)):
                return int(s) if s.is_integer() else s
    return v


def watts(per_tick):
    """J per tick -> W, rounded to the mW."""
    if per_tick is None:
        return None
    return clean(round(float(per_tick) * 60, 3))


def _list(v):
    """table_to_json writes an empty Lua table as {}; a list it is."""
    return [] if v == {} or v is None else list(v)


def read_products(name="facts-products"):
    """-> {recipe: [product]} as the game gives them (one short call on a laptop server)."""
    with _server(name) as srv:
        with srv.rcon() as r:
            _call(r, _PRODUCTS)
            return _read(srv, "products")


def apply_probabilities(cat, products):
    """-> (the catalog dict, [changes]): each catalog recipe's products get the game's
    ``probability`` where it is below 1 and its ``extra_count_fraction`` (a recycler's chance of
    one more) where it has one (matched by name and type, in order); every other field is kept.
    A product the game gives as certain loses a ``probability`` it had."""
    changes, rows = [], []
    for rec in cat.get("recipes", []):
        game = _list(products.get(rec["name"]))
        prods = []
        for k, prod in enumerate(rec.get("products") or ()):
            prod = dict(prod)
            same = [g for g in game if g.get("name") == prod["name"]
                    and (g.get("type") or "item") == (prod.get("type") or "item")]
            g = same[0] if len(same) == 1 else (game[k] if k < len(game) else None)
            p = clean(g.get("probability")) if g else None
            old = prod.get("probability")
            x = clean(g.get("extra_count_fraction")) if g else None
            if x and prod.get("extra_count_fraction") != x:
                prod["extra_count_fraction"] = x
                changes.append(f"{rec['name']}: {prod['name']} extra_count_fraction {x}")
            if p is not None and p < 1:
                if old != p:
                    prod["probability"] = p
                    changes.append(f"{rec['name']}: {prod['name']} probability {p}"
                                   + (f" (was {old})" if old is not None else ""))
            elif old is not None and p == 1:
                del prod["probability"]
                changes.append(f"{rec['name']}: {prod['name']} certain (was {old})")
            prods.append(prod)
        rows.append(dict(rec, products=prods) if "products" in rec else dict(rec))
    return dict(cat, recipes=rows), changes


def read_game():
    """-> (entities, things, connectors, signals_set, signals_read) as the game wrote them."""
    with _server("facts") as srv:
        with srv.rcon() as r:
            n = _call(r, _ENTITIES)
            print(f"placeable entities: {n}")
            _call(r, _THINGS)
            ents = _read(srv, "entities")
            things = _read(srv, "things")
            names = sorted(e["name"] for e in ents)
            _call(r, _SURFACE % 8)
            conns = []
            for k in range(0, len(names), 48):
                part = names[k:k + 48]
                lua = _CREATE % (json.dumps(part).replace("[", "{").replace("]", "}"), 0,
                                 (k // 16) * 20, f"conn{k}")
                _call(r, lua)
                conns += _read(srv, f"conn{k}")
            print(f"created: {sum(1 for c in conns if c['created'])} of {len(conns)}")
            n = _call(r, _SIGNALS_SET)
            print(f"signals a combinator takes: {n}")
            time.sleep(1.0)
            n = _call(r, _SIGNALS_READ)
            print(f"signals on its wire: {n}")
            sset, sread = _read(srv, "signals-set"), _read(srv, "signals-read")
    return ents, things, conns, sset, sread


def build_facts(ents, things, conns, sset, sread):
    """-> facts.json's dict."""
    by = {e["name"]: e for e in ents}
    fluids = things["fluids"]
    entities = {}
    for name in sorted(by):
        e = by[name]
        en = e.get("energy") or {}
        row = {"type": e["type"]}
        if en.get("source"):
            row["energy_source"] = en["source"]
        use = en.get("usage") if en.get("usage") is not None else en.get("max_usage")
        if use:
            row["energy_w"] = watts(use)
        if en.get("source") == "electric":
            row["drain_w"] = watts(en.get("drain") or 0)
            row["priority"] = en.get("priority")
            if en.get("buffer"):
                row["buffer_j"] = clean(en["buffer"])
        if en.get("source") == "burner":
            row["burner"] = True
            row["fuel_categories"] = _list(en.get("fuel_categories"))
            row["effectivity"] = clean(en.get("effectivity"))
        if en.get("power_output"):
            row["power_output_w"] = watts(en["power_output"])
        for k in ("mining_speed", "mining_drill_radius", "crafting_speed", "researching_speed",
                  "target_temperature", "maximum_temperature", "neighbour_bonus"):
            if e.get(k) is not None:
                row[k] = clean(e[k])
        if e["type"] == "mining-drill" and e.get("filter_count"):
            # 3.1 (M1): a drill's resource filter slots (MiningDrillPrototype::filter_count,
            # 2.0.7+; the base game's drills set none)
            row["filter_count"] = int(e["filter_count"])
        if e.get("resource_categories") is not None:
            row["resource_categories"] = _list(e["resource_categories"])
        if e.get("crafting_categories") is not None:
            row["crafting_categories"] = _list(e["crafting_categories"])
        if e.get("module_slots"):
            row["module_slots"] = e["module_slots"]
            row["allowed_effects"] = _list(e.get("allowed_effects"))
        if e.get("type") == "beacon":
            # 2.1.33: the beacon's reach and strength; its profile is 1/sqrt(n) (fkcore.elaborate)
            for k in ("distribution_effectivity", "supply_area_distance"):
                if e.get(k) is not None:
                    row[k] = clean(e[k])
        if e.get("fluid_usage_per_tick"):
            row["fluid_per_s"] = clean(e["fluid_usage_per_tick"] * 60)
        if e.get("drop_vector"):
            row["drop_vector"] = [clean(v) for v in e["drop_vector"]]
        entities[name] = row
    # steam: a boiler (or an exchanger) heats water to its target with its energy, at the steam's
    # heat capacity; an engine or a turbine takes its fluid usage
    steam = {}
    water, st = fluids["water"], fluids["steam"]
    for name, row in entities.items():
        e = by[name]
        if e["type"] == "boiler" and e.get("target_temperature"):
            w = row["energy_w"]
            steam[name] = w / ((e["target_temperature"] - water["default_temperature"])
                               * st["heat_capacity"])
        elif e["type"] == "generator" and e.get("fluid_usage_per_tick"):
            steam[name] = clean(e["fluid_usage_per_tick"] * 60)
    heat = {name: row["energy_w"] for name, row in entities.items()
            if by[name]["type"] == "reactor" or (by[name]["type"] == "boiler"
                                                 and row.get("energy_source") == "heat")}
    resources = {}
    for name, r in sorted(things["resources"].items(), key=lambda kv: (kv[1].get("order") or "", kv[0])):
        row = {"mining_time": clean(r["mining_time"]), "category": r.get("category"),
               "results": [x["name"] for x in _list(r.get("results"))],
               "fluid_results": any(x.get("type") == "fluid" for x in _list(r.get("results")))}
        if r.get("infinite"):
            row["infinite"] = True
        if r.get("required_fluid"):
            row["required_fluid"] = r["required_fluid"]
            row["fluid_amount"] = clean(r.get("fluid_amount"))
        resources[name] = row
    fuels = {}
    for name, f in sorted(things["fuels"].items()):
        fuels[name] = {"fuel_value_j": clean(f["fuel_value"]), "category": f.get("category")}
        if f.get("burnt_result"):
            fuels[name]["burnt_result"] = f["burnt_result"]
    modules = {}
    for name, md in sorted(things["modules"].items(), key=lambda kv: (kv[1].get("order") or "", kv[0])):
        modules[name] = {"category": md.get("category"), "tier": md.get("tier"),
                         "effects": {k: clean(v) for k, v in sorted((md.get("effects") or {}).items())}}
    recipes = {}
    for name, r in sorted(things["recipes"].items()):
        recipes[name] = {"effects": _list(r.get("effects"))}
        if r.get("max_productivity") is not None:
            recipes[name]["max_productivity"] = clean(r["max_productivity"])
    fl = {name: {"heat_capacity_j": clean(f["heat_capacity"]),
                 "default_temperature": clean(f["default_temperature"]),
                 "max_temperature": clean(f["max_temperature"])}
          for name, f in sorted(fluids.items())}
    for name, f in fluids.items():
        if f.get("fuel_value"):
            fl[name]["fuel_value_j"] = clean(f["fuel_value"])
    # signals
    took = {}
    for t, name in _list(sset.get("took")):
        took.setdefault(t, set()).add(name)
    seen = {}
    for row in _list(sread.get("seen")):
        seen.setdefault(row[0], set()).add(row[1])
    signals = {t: sorted(seen.get(t, ())) for t in sorted(took)}
    never = {t: sorted(took[t] - seen.get(t, set())) for t in sorted(took)
             if took[t] - seen.get(t, set())}
    refused = {}
    for t, name in _list(sset.get("refused")):
        refused[t] = refused.get(t, 0) + 1
    reach = {}
    for e in ents:
        if e.get("circuit_reach"):
            reach[clean(e["circuit_reach"])] = reach.get(clean(e["circuit_reach"]), 0) + 1
    wire_ids = {}
    for k, v in sorted(things["wire_ids"].items()):
        wire_ids.setdefault(str(v), []).append(k)
    return {
        "version": things["mods"].get("base"),
        "mods": things["mods"],
        "source": ("read from the game over RCON on a laptop server (tools/read_facts.py, "
                   f"Factorio {things['mods'].get('base')}, base + Space Age): prototypes.entity, "
                   ".item, .fluid, .recipe, .virtual_signal, .quality; wire connectors and signals "
                   "from entities created on a surface of the reader's own"),
        "notes": {
            "energy_w": "W: energy_usage (or get_max_energy_usage) x 60 ticks",
            "steam_per_s": "a boiler: energy_w / ((target - water's default temperature) x steam's "
                           "heat capacity); an engine or turbine: fluid_usage_per_tick x 60",
            "heat_w": "a reactor's energy use, and a heat-fed boiler's (heat exchanger)",
            "signals": "what a constant combinator takes and puts on its wire, by signal type",
            "never_transmit": "taken by a constant combinator, never on its wire",
            "refused": "how many prototypes of each type a combinator would not take",
        },
        "entities": entities,
        "resources": resources,
        "fuels": fuels,
        "modules": modules,
        "fluids": fl,
        "recipes": recipes,
        "steam_per_s": dict(sorted(steam.items())),
        "heat_w": dict(sorted(heat.items())),
        "circuit": {"wire_reach": max(reach, key=reach.get) if reach else None,
                    "wire_reach_counts": {str(k): v for k, v in sorted(reach.items())},
                    "connector_ids": dict(sorted(wire_ids.items(), key=lambda kv: int(kv[0])))},
        "signals": signals,
        "special_signals": sorted(_list(sset.get("special"))),
        "never_transmit": never,
        "refused": dict(sorted(refused.items())),
    }


#: what a catalog row holds, by entity type, beside name, type, size and collision box
_TYPE_FIELDS = {
    "assembling-machine": ("crafting_speed",), "furnace": ("crafting_speed",),
    "rocket-silo": ("crafting_speed",), "mining-drill": ("mining_speed",),
    "transport-belt": ("belt_speed",), "underground-belt": ("belt_speed", "max_distance"),
    "splitter": ("belt_speed",), "lane-splitter": ("belt_speed",), "loader": ("belt_speed",),
    "loader-1x1": ("belt_speed",), "linked-belt": ("belt_speed",),
    "electric-pole": ("supply_area_distance", "max_wire_distance"),
    "inserter": ("rotation_speed", "extension_speed", "bulk", "stack_size_bonus", "filter_count"),
    "roboport": ("logistic_radius", "construction_radius"),
}


def catalog_row(e, conns):
    """A catalog row for a placeable entity, as the measured fixture's rows are, plus
    ``placed_by``, ``energy`` and ``circuit``."""
    row = {"name": e["name"], "type": e["type"], "tile_width": e["tile_width"],
           "tile_height": e["tile_height"], "collision_box": [clean(v) for v in e["collision_box"]]}
    for k in _TYPE_FIELDS.get(e["type"], ()):
        if e.get(k) is not None:
            row[k] = clean(e[k])
    return dict(row, **extra_fields(e, conns))


def extra_fields(e, conns):
    en = e.get("energy") or {}
    energy = {"source": en.get("source")}
    use = en.get("usage") if en.get("usage") is not None else en.get("max_usage")
    if use:
        energy["usage_w"] = watts(use)
    if en.get("source") == "electric":
        energy["drain_w"] = watts(en.get("drain") or 0)
        energy["priority"] = en.get("priority")
    if en.get("power_output"):
        energy["output_w"] = watts(en["power_output"])
    c = conns.get(e["name"])
    circuit = {"connectors": sorted(_list(c.get("connectors"))) if c and c["created"] else None}
    if e.get("circuit_reach"):
        circuit["wire_reach"] = clean(e["circuit_reach"])
    return {"placed_by": list(e.get("placed_by") or ()), "energy": energy, "circuit": circuit}


def widen_catalog(cat, ents, conns):
    """-> (the catalog dict, [disagreements]): every row kept as it is, with placed_by/energy/
    circuit (re)written; a row for each placeable entity it lacks, after them, in name order."""
    by = {e["name"]: e for e in ents}
    cmap = {c["name"]: c for c in conns}
    diffs, rows = [], []
    for row in cat["entities"]:
        e = by.get(row["name"])
        base = {k: v for k, v in row.items() if k not in ("placed_by", "energy", "circuit")}
        if e is None:
            diffs.append(f"{row['name']}: not a placeable entity in the game")
            rows.append(base)
            continue
        game = catalog_row(e, cmap)
        for k, v in game.items():
            if k in ("placed_by", "energy", "circuit"):
                continue
            if k not in base:
                if k in _TYPE_FIELDS.get(e["type"], ()):
                    diffs.append(f"{row['name']}: {k} missing (game {v})")
                continue
            old = base[k]
            same = (old == v if not isinstance(v, list) else
                    len(old) == len(v) and all(abs(float(a) - float(b)) < 1e-6 for a, b in zip(old, v)))
            if isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(old, (int, float)):
                same = abs(float(old) - float(v)) < 1e-6
            if not same:
                diffs.append(f"{row['name']}: {k} {old} (game {v})")
        rows.append(dict(base, **extra_fields(e, cmap)))
    have = {r["name"] for r in rows}
    for name in sorted(by):
        if name not in have:
            rows.append(catalog_row(by[name], cmap))
    return dict(cat, entities=rows), diffs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry", action="store_true", help="read and print; write nothing")
    ap.add_argument("--raw", help="also save the game's raw answers to this JSON file")
    ap.add_argument("--products", action="store_true",
                    help="read only the recipes' products; write their probabilities")
    ap.add_argument("--attach", metavar="PORT:PWFILE:WRITEDATA",
                    help="read a server already running on this host (its RCON port, password "
                         "file and write-data dir) and write the pack's facts.json (--pack)")
    ap.add_argument("--pack", help="with --attach: write fkcore/data/packs/PACK/facts.json; "
                                   "the pack's catalog comes from tools/dump_catalog.lua")
    a = ap.parse_args(argv)
    if a.attach:
        global SERVER, CALL_S
        port, pw, write = a.attach.split(":", 2)
        SERVER, CALL_S = Attached(int(port), pw, write), 60
        if not a.pack:
            ap.error("--attach needs --pack")
        return main_pack(a.pack, a.dry)
    if a.products:
        return main_products(a.dry)
    ents, things, conns, sset, sread = read_game()
    if a.raw:
        with open(a.raw, "w", encoding="utf-8") as fh:
            json.dump({"entities": ents, "things": things, "connectors": conns,
                       "signals_set": sset, "signals_read": sread}, fh)
    facts = build_facts(ents, things, conns, sset, sread)
    with open(CATALOG, encoding="utf-8") as fh:
        cat = json.load(fh)
    old_n = len(cat["entities"])
    wide, diffs = widen_catalog(cat, ents, conns)
    wide, changes = apply_probabilities(wide, read_products())
    for c in changes:
        print("  product:", c)
    print(f"facts: {len(facts['entities'])} entities, {len(facts['resources'])} resources, "
          f"{len(facts['fuels'])} fuels, {len(facts['modules'])} modules, "
          f"{len(facts['recipes'])} recipes, signals "
          + ", ".join(f"{t} {len(v)}" for t, v in facts["signals"].items())
          + "; never transmit " + ", ".join(f"{t} {v}" for t, v in facts["never_transmit"].items()))
    print(f"catalog: {old_n} -> {len(wide['entities'])} entities")
    for d in diffs:
        print("  differs:", d)
    if a.dry:
        return 0
    with open(FACTS, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(facts, fh, indent=1, sort_keys=False)
        fh.write("\n")
    with open(CATALOG, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(wide, fh)
    print(f"wrote {FACTS} and {CATALOG}")
    return 0


def main_pack(pack, dry=False):
    """``--attach``: a pack's facts.json from its running game (its catalog is the dump's)."""
    ents, things, conns, sset, sread = read_game()
    facts = build_facts(ents, things, conns, sset, sread)
    facts["source"] = facts["source"].replace("on a laptop server", f"on the {pack} pack's game")
    print(f"facts: {len(facts['entities'])} entities, {len(facts['resources'])} resources, "
          f"{len(facts['fuels'])} fuels, {len(facts['modules'])} modules")
    if dry:
        return 0
    out = os.path.join(DATA, "packs", pack, "facts.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(facts, fh, indent=1, sort_keys=False)
        fh.write("\n")
    print(f"wrote {out}")
    return 0


def main_products(dry=False):
    """``--products``: the probabilities alone, into catalog.json."""
    products = read_products()
    with open(CATALOG, encoding="utf-8") as fh:
        cat = json.load(fh)
    new, changes = apply_probabilities(cat, products)
    missing = sorted(r["name"] for r in cat.get("recipes", []) if r["name"] not in products)
    print(f"recipes: {len(products)} in the game, {len(cat.get('recipes', []))} in the catalog "
          f"({len(missing)} of them not in the game)")
    for c in changes:
        print("  product:", c)
    if dry or not changes:
        return 0
    with open(CATALOG, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(new, fh)
    print(f"wrote {CATALOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
