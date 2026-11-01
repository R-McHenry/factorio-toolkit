-- Dump the running game's prototypes as the toolkit's catalog (fkcore/data/catalog.json and
-- fluidboxes.json), for any mod set. Run it once in the game as /sc (tools/dump_catalog.py sends it):
-- it writes script-output/fk-catalog.json and script-output/fk-fluidboxes.json.
--
-- Entities: every placeable prototype (an item places it) and the robots. Each is also built once
-- on a scratch surface to read what only a live entity shows: its circuit connectors and whether
-- its fluid boxes stay off until it has a fluid recipe. Recipes: all of them, products with their
-- probabilities. Fluid boxes: the static ones per entity; a recipe's live boxes are left to
-- catalog.py's recipe rule (fluids in order, an explicit fluidbox_index first).
local W = 60 -- J/tick to W

local function try(f, ...)
  local ok, v = pcall(f, ...)
  -- JSON has no inf or nan (the energy interface draws without limit)
  if ok and not (type(v) == "number" and (v ~= v or v == math.huge or v == -math.huge)) then return v end
end

local function box(p)
  local b = p.collision_box
  return { b.left_top.x, b.left_top.y, b.right_bottom.x, b.right_bottom.y }
end

local function energy(p)
  local e = {}
  local el = p.electric_energy_source_prototype
  -- a burner generator has both: it is a burner that makes electricity
  if el and not p.burner_prototype then
    e.source = "electric"
    e.usage_w = try(function() return p.get_max_energy_usage() * W end)
    e.drain_w = (el.drain or 0) * W
    e.priority = el.usage_priority
    local out = try(function() return p.get_max_energy_production() end)
    if out and out > 0 then e.output_w = out * W end
  elseif p.burner_prototype then
    e.source = "burner"
    e.usage_w = try(function() return p.get_max_energy_usage() * W end)
    local out = try(function() return p.get_max_energy_production() end)
    if out and out > 0 then e.output_w = out * W end
    e.fuel_categories = try(function() local t = {} for k in pairs(p.burner_prototype.fuel_categories) do t[#t + 1] = k end return t end)
  elseif p.heat_energy_source_prototype then
    e.source = "heat"
    e.usage_w = try(function() return p.get_max_energy_usage() * W end)
  elseif p.fluid_energy_source_prototype then
    e.source = "fluid"
    e.usage_w = try(function() return p.get_max_energy_usage() * W end)
  elseif p.void_energy_source_prototype then
    e.source = "void"
  end
  return e
end

local function keys(t)
  local out = {}
  for k in pairs(t or {}) do out[#out + 1] = k end
  table.sort(out)
  return out
end

local surface = game.surfaces["fk-dump"] or game.create_surface("fk-dump", { width = 256, height = 256 })
surface.always_day = true
surface.request_to_generate_chunks({ 0, 0 }, 2)
surface.force_generate_chunk_requests()
local tiles = {}
for x = -16, 15 do for y = -16, 15 do tiles[#tiles + 1] = { name = "refined-concrete", position = { x, y } } end end
if not prototypes.tile["refined-concrete"] then for _, t in pairs(tiles) do t.name = "landfill" end end
surface.set_tiles(tiles)

-- what only a live entity shows
local function live(p)
  local out = {}
  local e = try(function()
    return surface.create_entity({ name = p.name, position = { 0, 0 }, force = "player", raise_built = false })
  end)
  if not e then return out end
  out.connectors = try(function()
    local c = {}
    for id in pairs(e.get_wire_connectors(true)) do c[#c + 1] = id end
    table.sort(c)
    return c
  end)
  if #p.fluidbox_prototypes > 0 and e.fluidbox then
    local n = 0
    for i = 1, #e.fluidbox do n = n + #e.fluidbox.get_pipe_connections(i) end
    out.boxes_off = (n == 0)
  end
  e.destroy()
  return out
end

local entities, fluid_entities = {}, {}
local ROBOTS = { ["construction-robot"] = true, ["logistic-robot"] = true }
for name, p in pairs(prototypes.entity) do
  local placed = p.items_to_place_this
  if (placed and #placed > 0) or ROBOTS[p.type] then
    local row = {
      name = name, type = p.type, tile_width = p.tile_width, tile_height = p.tile_height,
      collision_box = box(p), energy = energy(p),
      placed_by = {},
    }
    for _, it in pairs(placed or {}) do row.placed_by[#row.placed_by + 1] = it.name end
    if p.crafting_categories then
      row.crafting_speed = try(function() return p.get_crafting_speed() end) or p.crafting_speed
      row.crafting_categories = keys(p.crafting_categories)
    end
    if p.belt_speed then row.belt_speed = p.belt_speed end
    if p.max_underground_distance then row.max_distance = p.max_underground_distance end
    if p.mining_speed then
      row.mining_speed = p.mining_speed
      row.resource_categories = keys(p.resource_categories)
      row.mining_radius = try(function() return p.get_mining_drill_radius() end) or p.mining_drill_radius
    end
    if p.type == "electric-pole" then
      row.supply_area_distance = try(function() return p.get_supply_area_distance() end) or p.supply_area_distance
      row.max_wire_distance = try(function() return p.get_max_wire_distance() end) or p.max_wire_distance
    end
    if p.type == "roboport" then
      row.logistic_radius = p.logistic_radius
      row.construction_radius = p.construction_radius
    end
    if p.type == "inserter" then
      row.rotation_speed = try(function() return p.get_inserter_rotation_speed() end) or p.inserter_rotation_speed
      row.extension_speed = try(function() return p.get_inserter_extension_speed() end) or p.inserter_extension_speed
      row.bulk = p.bulk or false
      row.stack_size_bonus = p.inserter_stack_size_bonus or 0
      row.filter_count = p.filter_count or 0
    end
    if p.module_inventory_size then row.module_slots = p.module_inventory_size end
    local l = live(p)
    row.circuit = { connectors = l.connectors, wire_reach = try(function() return p.get_max_circuit_wire_distance() end) }
    if row.circuit.wire_reach == 0 then row.circuit.wire_reach = nil end
    entities[#entities + 1] = row

    if #p.fluidbox_prototypes > 0 then
      local boxes = {}
      for _, fb in pairs(p.fluidbox_prototypes) do
        local b = { index = fb.index, production = fb.production_type, connections = {} }
        if fb.filter then b.filter = fb.filter.name end
        for _, c in pairs(fb.pipe_connections) do
          local at = {}
          for k = 1, 4 do
            local pos = c.positions and c.positions[k]
            at[k] = pos and { pos.x, pos.y } or { 0, 0 }
          end
          local cats = try(function() return c.connection_category end)
          if type(cats) == "string" then cats = { cats } end
          if cats and #cats == 1 and cats[1] == "default" then cats = nil end
          b.connections[#b.connections + 1] = {
            at = at, dir = c.direction or 0, flow = c.flow_direction, type = c.connection_type,
            max_distance = c.max_underground_distance ~= 0 and c.max_underground_distance or nil,
            categories = cats,
          }
        end
        boxes[#boxes + 1] = b
      end
      table.sort(boxes, function(a, b) return a.index < b.index end)
      local frow = { type = p.type, size = { p.tile_width, p.tile_height }, boxes = boxes }
      if l.boxes_off and p.crafting_categories then frow.boxes_need_fluid_recipe = true end
      fluid_entities[name] = frow
    end
  end
end
table.sort(entities, function(a, b) return a.name < b.name end)

local function stack(list)
  local out = {}
  for _, r in pairs(list or {}) do
    local row = { name = r.name, type = r.type, amount = r.amount }
    if r.amount_min then row.amount_min = r.amount_min; row.amount_max = r.amount_max end
    if r.probability and r.probability ~= 1 then row.probability = r.probability end
    if r.fluidbox_index and r.fluidbox_index ~= 0 then row.fluidbox_index = r.fluidbox_index end
    if r.temperature then row.temperature = r.temperature end
    out[#out + 1] = row
  end
  return out
end

local recipes = {}
local force = game.forces.player
for name, r in pairs(prototypes.recipe) do
  if not r.parameter then
    recipes[#recipes + 1] = {
      name = name, category = r.category, energy = r.energy,
      enabled = force.recipes[name] and force.recipes[name].enabled or false,
      hidden = r.hidden or nil,
      ingredients = stack(r.ingredients), products = stack(r.products),
    }
  end
end
table.sort(recipes, function(a, b) return a.name < b.name end)

-- items the catalog's base-game tables cover by hand (fuel values, stack sizes)
local items = {}
for name, it in pairs(prototypes.item) do
  if not it.parameter then
    local row = { name = name, stack_size = it.stack_size }
    if it.fuel_value and it.fuel_value > 0 then row.fuel_value = it.fuel_value; row.fuel_category = it.fuel_category end
    if it.place_result then row.place_result = it.place_result.name end
    items[#items + 1] = row
  end
end
table.sort(items, function(a, b) return a.name < b.name end)

local mods = {}
for name, v in pairs(script.active_mods) do mods[#mods + 1] = name .. " " .. v end
table.sort(mods)

helpers.write_file("fk-catalog.json", helpers.table_to_json({
  version = script.active_mods.base, mods = mods,
  entities = entities, recipes = recipes, items = items,
}), false)
helpers.write_file("fk-fluidboxes.json", helpers.table_to_json({
  version = script.active_mods.base, mods = mods,
  source = "tools/dump_catalog.lua: prototypes.entity[name].fluidbox_prototypes, static boxes only; recipes' live boxes come from catalog.py's recipe rule",
  notes = {}, checked = "not measured live", entities = fluid_entities, recipes = {},
}), false)
game.delete_surface(surface)
rcon.print("entities " .. #entities .. ", recipes " .. #recipes .. ", items " .. #items)
