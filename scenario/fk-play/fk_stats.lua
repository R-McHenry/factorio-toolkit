-- fk_stats: the run's stats recorder, an event_handler lib (2.1, Rory 2026-10-31: every new run
-- records its own history from the first minute, whatever the player does).
--
-- Every 5 game minutes it appends one line to script-output/fk-stats/samples.jsonl, on the server
-- only (for_player 0): the force's cumulative counts (items and fluids made and used, power made
-- and used per entity and electric network), the research in progress and its progress, and how
-- many machines stand in each state. It only reads: nothing in the game or in storage changes, so
-- it costs a little CPU every 5 minutes and nothing else. fkcore.runstats reads the file and keeps
-- the change since the last line. The handler is registered here, in scenario code that every
-- joining client runs, never through RCON (the pattern that made saves unjoinable on 2026-10-18).
-- A map made before this file keeps the script it was made with: fkcore.runstats reads the same
-- counts for it over RCON with the same sample function.
local EVERY = 5 * 60 * 60
local FILE = "fk-stats/samples.jsonl"

-- fk_stats sample: begin (the same text as fkcore/runstats.py SAMPLE_LUA)
local function fk_stats_sample(f, s)
  local out = {tick = game.tick, seed = s.map_gen_settings.seed, force = f.name, surface = s.name}
  local types = {}
  local function kind(n)
    if types[n] == nil then
      local p = prototypes.entity[n]
      types[n] = p and p.type or false
    end
  end
  local items = f.get_item_production_statistics(s)
  out.items = {made = items.input_counts, used = items.output_counts}
  local fluids = f.get_fluid_production_statistics(s)
  out.fluids = {made = fluids.input_counts, used = fluids.output_counts}
  local power, seen, at, nets = {}, {}, {}, 0
  for _, p in pairs(s.find_entities_filtered{type = "electric-pole", force = f}) do
    local id = p.electric_network_id
    if id and not seen[id] then
      seen[id] = true
      nets = nets + 1
      local st = p.electric_network_statistics
      -- a network's input is what its machines used, its output what was made, in joules
      power[tostring(id)] = {made = st.output_counts, used = st.input_counts}
      for n in pairs(st.input_counts) do kind(n) end
      for n in pairs(st.output_counts) do kind(n) end
      at[id] = {}
    end
    if id then
      -- 2.1: where its poles stand (doubled, so whole numbers), to tell power domains apart
      local a = at[id]
      a[#a + 1] = math.floor(p.position.x * 2 + 0.5)
      a[#a + 1] = math.floor(p.position.y * 2 + 0.5)
    end
  end
  if nets > 1 then
    for id, a in pairs(at) do power[tostring(id)].at = a end
  end
  out.power = power
  local done = 0
  for _, t in pairs(f.technologies) do
    if t.researched then done = done + 1 end
  end
  local res = f.current_research
  out.research = {researched = done, queue = #(f.research_queue or {})}
  if res then
    local ing = {}
    for _, i in pairs(res.research_unit_ingredients) do ing[#ing + 1] = {i.name, i.amount} end
    out.research.name = res.name
    out.research.level = res.level
    out.research.progress = f.research_progress
    out.research.units = res.research_unit_count
    out.research.ingredients = ing
  end
  local names = {}
  for k, v in pairs(defines.entity_status) do names[v] = k end
  local machines, recipes = {}, {}
  for _, e in pairs(s.find_entities_filtered{type = {"assembling-machine", "furnace",
      "mining-drill", "lab", "rocket-silo"}, force = f}) do
    local st = names[e.status] or "none"
    local m = machines[e.name] or {}
    m[st] = (m[st] or 0) + 1
    machines[e.name] = m
    kind(e.name)
    if e.type ~= "mining-drill" and e.type ~= "lab" then
      local r = e.get_recipe()
      local rn = r and r.name
      if not rn and e.type == "furnace" then
        local ok, pr = pcall(function() return e.previous_recipe end)
        if ok and pr then rn = type(pr.name) == "string" and pr.name or pr.name.name end
      end
      rn = rn or "(no recipe)"
      local q = recipes[rn] or {}
      q[st] = (q[st] or 0) + 1
      recipes[rn] = q
    end
  end
  out.machines, out.recipes = machines, recipes
  local t = {}
  for n, v in pairs(types) do if v then t[n] = v end end
  out.types = t
  return out
end
-- fk_stats sample: end

local stats = {}

stats.on_nth_tick = {
  [EVERY] = function(event)
    if event.tick == 0 then return end
    local f, s = game.forces.player, game.get_surface("nauvis")
    if not (f and s) then return end
    -- a mistake in the read must never stop the game: an error in a handler ends it for everyone
    local ok, sample = pcall(fk_stats_sample, f, s)
    if ok then
      helpers.write_file(FILE, helpers.table_to_json(sample) .. "\n", true, 0)
    end
  end,
}

return stats
