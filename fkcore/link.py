"""fkcore.link: the game link (CORE-V1.md §9): RCON calls that read the game or make a named paste.

Every call is one short RCON command with a 5 s socket timeout (Rory: game calls take seconds).
The Lua sent here only reads, or builds through a blueprint paste, or (lab only) revives ghosts.
**Nothing here registers an event handler or a command** (an RCON-registered handler made every
save unjoinable on 2026-10-18); ``assert_safe`` refuses any Lua that would.

- ``snapshot(surface, area)``: every entity in the area as v4's capture rows (n, t, x, y, d, g,
  dc, force, hp, st, rc, it, ug, u, box) plus ``lu``, its last_user (``it``: what a belt or chest
  holds, and the fluid in a pipe or pump, 1.2); not the ground (resources:
  the terrain read has those), characters, corpses, items on the ground or effects, which no
  design owns and the diff never judges. The rows go through
  ``helpers.write_file`` into script-output and are read back from disk, so a big area never
  overflows an RCON reply; ``fkcore.scene.from_capture`` makes the scene.
- ``paste(surface, force, bp, at)``: a superforced ``build_blueprint`` of a blueprint string from a
  script inventory (the only world write). ``revive(surface, area)``: lab only, builds the area's
  ghosts at once (lab rules: free materials).
- ``decon(surface, force, area)``: marks the area for deconstruction; ``decon_list`` marks given
  entities (name + position); ``destroy`` (lab only) removes.
- ``produced(force, surface, items)``: the force's production counts (two samples are a measure).
- ``say(text)``: a line in game chat.
- ``alerts(force)``: the game's alert panel of every player of the force, connected or not (the
  game keeps alerts per player; ``LuaForce`` has no ``get_alerts``), plus every force's player
  count; ``fkcore.alerts`` normalises, dedupes and tracks them (the only pushed alerts).
- ``stats(force, surface, items, window)`` and ``chart(force, surface)``: the free reads of
  decision 11 (production flow counts, charted chunks); ``fkcore.freereads`` prints them, and
  nothing ever turns them into an alert.

Big replies (snapshot, alerts, stats) go through ``helpers.write_file`` and are read back from
script-output (``read_output``): an RCON reply is one packet. The link is used only with
``FK_LINK=on`` (``enabled``, ``open_from_env``), so a paper run on the game host never touches the
game by accident. The RCON protocol is copied from C:\\fk-lead\\repo\\fk\\rcon.py (d6018d3), with a
timeout. Stdlib only.
"""
from __future__ import annotations

import itertools
import json
import math
import os
import re
import socket
import struct

__all__ = ["LinkError", "Rcon", "lua_snapshot", "lua_paste", "lua_revive", "lua_decon",
           "lua_decon_list", "lua_rip_load", "lua_stuck_hands", "lua_destroy", "lua_produced", "lua_generate", "lua_generate_area",
           "lua_seed", "lua_ghosts", "lua_say", "lua_alerts", "lua_stats", "lua_chart", "assert_safe",
           "snapshot", "paste", "alerts", "stats", "chart", "read_output", "enabled",
           "open_from_env", "OUT_DIR", "WINDOWS"]

HOST = os.environ.get("FK_RCON_HOST", "127.0.0.1")
PORT = int(os.environ.get("FK_RCON_PORT", "27015"))
PW_FILE = os.environ.get("FK_RCON_PW_FILE", "/home/computah/factorio/instance/rcon.pw")
#: script-output of the server (write-data/script-output); snapshot files land in OUT_DIR/fk5/.
OUT_DIR = os.environ.get("FK_SCRIPT_OUTPUT", "/home/computah/factorio/server/factorio/script-output")
TIMEOUT = 5.0

_FORBIDDEN = re.compile(r"\b(script\s*\.\s*on_\w+|commands\s*\.\s*add_command|remote\s*\.\s*add_interface"
                        r"|script\s*\.\s*register_\w+)")


class LinkError(RuntimeError):
    pass


def enabled():
    """True when ``FK_LINK=on``: the only way any tool here talks to the game."""
    return os.environ.get("FK_LINK", "off").lower() == "on"


def open_from_env():
    """-> (Rcon, None), or (None, why) when the link is off or the game can't be reached."""
    if not enabled():
        return None, "FK_LINK is not on (FK_LINK=on uses the game link)"
    try:
        return Rcon(), None
    except (OSError, LinkError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def assert_safe(lua):
    """Refuse Lua that would register a handler, a command or an interface in the save."""
    m = _FORBIDDEN.search(lua)
    if m:
        raise LinkError(f"refusing to send Lua that registers something: {m.group(0)}")
    return lua


class Rcon:
    """One RCON connection; ``call(cmd)`` -> the reply text."""

    def __init__(self, host=HOST, port=PORT, pw_file=PW_FILE, timeout=TIMEOUT):
        self.ids = itertools.count(1)
        with open(pw_file) as fh:
            pw = fh.read().strip()
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self._send(3, pw)
        while True:
            rid, typ, _ = self._recv()
            if typ == 2:
                if rid == -1:
                    raise LinkError("RCON auth failed")
                break

    def _send(self, typ, body):
        rid = next(self.ids)
        payload = struct.pack("<ii", rid, typ) + body.encode() + b"\x00\x00"
        self.sock.sendall(struct.pack("<i", len(payload)) + payload)
        return rid

    def _readn(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise LinkError("RCON socket closed")
            buf += chunk
        return buf

    def _recv(self):
        (ln,) = struct.unpack("<i", self._readn(4))
        data = self._readn(ln)
        rid, typ = struct.unpack("<ii", data[:8])
        return rid, typ, data[8:-2].decode("utf-8", "replace")

    def call(self, cmd):
        if cmd.startswith("/sc ") or cmd.startswith("/silent-command "):
            assert_safe(cmd)
        self._send(2, cmd)
        return self._recv()[2]

    def lua(self, body):
        """Run Lua silently; its rcon.print output is the reply."""
        return self.call("/sc " + " ".join(line.strip() for line in body.splitlines()
                                            if line.strip() and not line.strip().startswith("--")))

    def close(self):
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _q(s):
    return json.dumps(str(s))


def _area(area):
    x0, y0, x1, y1 = area
    return f"{{{{{x0},{y0}}},{{{x1},{y1}}}}}"


#: entity types a snapshot leaves out: the ground, the player's body, and what is not built
_SKIP = "{" + ", ".join(f"'{t}'" for t in (
    "resource", "fish", "character", "corpse", "character-corpse", "item-entity", "item-request-proxy",
    "construction-robot", "logistic-robot", "combat-robot",
    "highlight-box", "speech-bubble", "explosion", "smoke-with-trigger", "particle-source",
    "projectile", "beam", "stream", "sticker", "fire", "deconstructible-tile-proxy",
    "tile-ghost")) + "}"


def lua_snapshot(surface, area, tag="snap"):
    return f"""
local s = game.get_surface({_q(surface)})
if not s then rcon.print('no surface') return end
local out = {{}}
for _, e in pairs(s.find_entities_filtered{{area = {_area(area)}, type = {_SKIP}, invert = true}}) do
  local g = e.type == 'entity-ghost'
  local t = g and e.ghost_type or e.type
  local row = {{n = g and e.ghost_name or e.name, t = t, x = e.position.x, y = e.position.y,
    d = e.direction, g = g, dc = e.to_be_deconstructed(), force = e.force.name,
    u = e.unit_number}}
  local bb = e.bounding_box
  row.box = {{bb.left_top.x, bb.left_top.y, bb.right_bottom.x, bb.right_bottom.y}}
  if e.last_user then row.lu = e.last_user.name end
  if e.health and e.max_health and e.max_health > 0 then row.hp = e.health / e.max_health end
  if t == 'assembling-machine' or t == 'furnace' then
    local ok, r = pcall(e.get_recipe)
    if ok and r then row.rc = r.name end
  end
  if t == 'underground-belt' then row.ug = e.belt_to_ground_type end
  if not g and (t == 'transport-belt' or t == 'underground-belt' or t == 'splitter') then
    local it = {{}}
    for i = 1, e.get_max_transport_line_index() do
      for _, c in pairs(e.get_transport_line(i).get_contents()) do
        it[c.name] = (it[c.name] or 0) + c.count
      end
    end
    if next(it) then row.it = it end
  end
  if not g and (t == 'container' or t == 'logistic-container' or t == 'infinity-container') then
    local inv = e.get_inventory(defines.inventory.chest)
    if inv then
      local it = {{}}
      for _, c in pairs(inv.get_contents()) do it[c.name] = (it[c.name] or 0) + c.count end
      if next(it) then row.it = it end
    end
  end
  if not g and (t == 'pipe' or t == 'pipe-to-ground' or t == 'pump') then
    local it = {{}}
    for i = 1, #e.fluidbox do
      local f = e.fluidbox[i]
      if f then it[f.name] = (it[f.name] or 0) + f.amount end
    end
    if next(it) then row.it = it end
  end
  out[#out + 1] = row
end
helpers.write_file('fk5/{tag}.json', helpers.table_to_json({{tick = game.tick, area = {{{area[0]},{area[1]},{area[2]},{area[3]}}}, things = out}}), false)
rcon.print(#out)
"""


def lua_paste(surface, force, bp, at):
    return f"""
local s = game.get_surface({_q(surface)})
local inv = game.create_inventory(1)
inv.insert{{name = 'blueprint'}}
local stack = inv[1]
local r = stack.import_stack({_q(bp)})
if r ~= 0 then inv.destroy() rcon.print('import failed ' .. r) return end
local built = stack.build_blueprint{{surface = s, force = {_q(force)}, position = {{{at[0]},{at[1]}}},
  build_mode = defines.build_mode.superforced, skip_fog_of_war = false}}
inv.destroy()
rcon.print(#built)
"""


def lua_revive(surface, area):
    return f"""
local s = game.get_surface({_q(surface)})
local n, failed = 0, 0
for _, g in pairs(s.find_entities_filtered{{area = {_area(area)}, type = 'entity-ghost'}}) do
  local _, e = g.revive()
  if e then n = n + 1 else failed = failed + 1 end
end
rcon.print(n .. ' ' .. failed)
"""


def lua_decon(surface, force, area):
    return f"""
local s = game.get_surface({_q(surface)})
s.deconstruct_area{{area = {_area(area)}, force = {_q(force)}}}
local n = 0
for _, e in pairs(s.find_entities_filtered{{area = {_area(area)}}}) do
  if e.to_be_deconstructed() then n = n + 1 end
end
rcon.print(n)
"""


def lua_decon_list(surface, force, things):
    """Order deconstruction of the given entities [(name, x, y)] (found by name and position).
    With no entity of that name there, a ghost of it at that position is ordered out instead:
    the game removes a ghost ordered for deconstruction at once (checked on a laptop test server,
    Factorio 2.0.77, 2026-10-20). A diff names a ghost by the entity it stands for, so before 1.2
    an emptied factory's ghosts were never found and stayed."""
    data = json.dumps([[n, float(x), float(y)] for n, x, y in things])
    return f"""
local s = game.get_surface({_q(surface)})
local n = 0
for _, t in pairs(helpers.json_to_table({_q(data)})) do
  local e = s.find_entity(t[1], {{t[2], t[3]}})
  if not e then
    for _, g in pairs(s.find_entities_filtered{{type = 'entity-ghost', ghost_name = t[1], position = {{t[2], t[3]}}, radius = 0.5}}) do
      if g.position.x == t[2] and g.position.y == t[3] then e = g break end
    end
  end
  if e and e.order_deconstruction({_q(force)}) then n = n + 1 end
end
rcon.print(n)
"""


def lua_stock_and_ghosts(surface, force, names):
    """For each entity name: the items of it in the force's logistic networks on ``surface`` and
    its ghosts waiting there. {name: [stock, ghosts]} as JSON (a free read; ``fk fresh`` warns
    when what it takes up may not come back to the same spot)."""
    return f"""
local s = game.get_surface({_q(surface)})
local f = game.forces[{_q(force)}]
local out = {{}}
for _, n in pairs(helpers.json_to_table({_q(json.dumps(sorted(set(names))))})) do
  local stock = 0
  for _, net in pairs((f.logistic_networks or {{}})[s.name] or {{}}) do stock = stock + net.get_item_count(n) end
  local ghosts = s.count_entities_filtered{{type = 'entity-ghost', ghost_name = n, force = f}}
  out[n] = {{stock, ghosts}}
end
rcon.print(helpers.table_to_json(out))
"""


def lua_stuck_hands(surface, area):
    """The inserters in ``area`` that hold an item the assembling machine they feed doesn't use
    (left in the hand by a recipe switch): [[name, x, y, item]] as JSON (1.1.1, a free read)."""
    return f"""
local s = game.get_surface({_q(surface)})
local out = {{}}
for _, e in pairs(s.find_entities_filtered{{area = {_area(area)}, type = "inserter"}}) do
  local h = e.held_stack
  local t = e.drop_target
  if h and h.valid_for_read and t and t.valid and t.type == "assembling-machine" then
    local r = t.get_recipe()
    local used = false
    if r then
      for _, ing in pairs(r.ingredients) do
        if ing.name == h.name then used = true break end
      end
    end
    if not used then out[#out + 1] = {{e.name, e.position.x, e.position.y, h.name}} end
  end
end
rcon.print(#out > 0 and helpers.table_to_json(out) or "[]")
"""


def lua_stale_crafters(surface, area):
    """A recipe switch's leftovers in ``area`` (1.7, Rory 2026-10-21: ``fk fresh`` also deals with
    a one-off crafter whose output slot is full of the old product): an assembling machine whose
    output holds an item its recipe doesn't make, and a chest that holds an item none of the
    machines whose inserters drop into it makes now (the 2005 player's shop: a 1-slot provider
    full of stone furnaces after its crafter went on to labs). [[name, x, y, kind, items]] as JSON,
    kind ``crafter`` or ``chest`` (a free read)."""
    return f"""
local s = game.get_surface({_q(surface)})
local function makes(m)
  local ok, r = pcall(m.get_recipe)
  local out = {{}}
  if ok and r then for _, p in pairs(r.products) do out[p.name] = true end end
  return out, ok and r ~= nil
end
local out, feeds, other = {{}}, {{}}, {{}}
for _, m in pairs(s.find_entities_filtered{{area = {_area(area)}, type = "assembling-machine"}}) do
  local made, has = makes(m)
  local inv = m.get_output_inventory()
  if has and inv then
    local odd = {{}}
    for _, c in pairs(inv.get_contents()) do
      if not made[c.name] then odd[#odd + 1] = c.name end
    end
    if #odd > 0 then out[#out + 1] = {{m.name, m.position.x, m.position.y, "crafter", odd}} end
  end
end
for _, i in pairs(s.find_entities_filtered{{area = {_area(area)}, type = "inserter"}}) do
  local src, dst = i.pickup_target, i.drop_target
  if dst and dst.valid and (dst.type == "container" or dst.type == "logistic-container") then
    local key = dst.unit_number
    if src and src.valid and src.type == "assembling-machine" then
      feeds[key] = feeds[key] or {{chest = dst, made = {{}}}}
      for name in pairs((makes(src))) do feeds[key].made[name] = true end
    else
      other[key] = true          -- fed from a belt or a chest too: what belongs there is unknown
    end
  end
end
for key, f in pairs(feeds) do
  local c = f.chest
  local inv = not other[key] and c.get_inventory(defines.inventory.chest)
  local odd = {{}}
  if inv then
    for _, it in pairs(inv.get_contents()) do
      if not f.made[it.name] then odd[#odd + 1] = it.name end
    end
  end
  if #odd > 0 then out[#out + 1] = {{c.name, c.position.x, c.position.y, "chest", odd}} end
end
rcon.print(#out > 0 and helpers.table_to_json(out) or "[]")
"""


def lua_rip_load(surface, force, points):
    """What taking up the entities at ``points`` [(x, y)] costs the robots (1.1, a free read): how
    many there are and the items they hold (inventories, belt lines, inserter hands), the
    construction robots of the network there, how far its nearest storage is, and a robot's speed
    (tiles/s) and cargo. JSON."""
    data = json.dumps([[float(x), float(y)] for x, y in points])
    return f"""
local s, f = game.get_surface({_q(surface)}), game.forces[{_q(force)}]
local skip = {{["entity-ghost"] = true, ["tile-ghost"] = true, resource = true, character = true,
  ["construction-robot"] = true, ["logistic-robot"] = true, fish = true, corpse = true}}
local belts = {{["transport-belt"] = true, ["underground-belt"] = true, splitter = true,
  loader = true, ["loader-1x1"] = true}}
local seen, n, items, sx, sy = {{}}, 0, 0, 0, 0
for _, t in pairs(helpers.json_to_table({_q(data)})) do
  for _, e in pairs(s.find_entities_filtered{{position = {{t[1], t[2]}}, radius = 0.5}}) do
    local id = e.name .. "@" .. e.position.x .. "," .. e.position.y
    if not skip[e.type] and not seen[id] then
      seen[id] = true
      n, sx, sy = n + 1, sx + e.position.x, sy + e.position.y
      for i = 1, e.get_max_inventory_index() do
        local inv = e.get_inventory(i)
        if inv then items = items + inv.get_item_count() end
      end
      if belts[e.type] then
        for i = 1, e.get_max_transport_line_index() do
          items = items + e.get_transport_line(i).get_item_count()
        end
      end
      if e.type == "inserter" and e.held_stack.valid_for_read then
        items = items + e.held_stack.count
      end
    end
  end
end
local out = {{n = n, items = items}}
if n > 0 then
  local c = {{sx / n, sy / n}}
  local net = s.find_logistic_network_by_position(c, f)
  if net then
    out.robots, out.idle = net.all_construction_robots, net.available_construction_robots
    local best
    for _, st in pairs(net.storages) do
      local d = math.sqrt((st.position.x - c[1]) ^ 2 + (st.position.y - c[2]) ^ 2)
      if not best or d < best then best = d end
    end
    out.dist = best
  end
  local p = prototypes.entity["construction-robot"]
  out.speed = p.speed * 60 * (1 + f.worker_robots_speed_modifier)
  out.cargo = (p.max_payload_size or 1) + f.worker_robots_storage_bonus
end
rcon.print(helpers.table_to_json(out))
"""


def lua_ghosts(surface, force, rows):
    """One ghost per row, placed on its own: for what a blueprint paste refuses (an offshore
    pump: the kickoff found it, 2026-10-18; v5 again, 2026-10-20). rows: codec rows."""
    data = json.dumps([[r["name"], float(r["x"]), float(r["y"]), int(r.get("direction") or 0),
                        r.get("src", "")] for r in rows])
    return f"""
local s = game.get_surface({_q(surface)})
local n = 0
for _, t in pairs(helpers.json_to_table({_q(data)})) do
  local g = s.create_entity{{name = 'entity-ghost', inner_name = t[1], position = {{t[2], t[3]}},
    direction = t[4], force = {_q(force)}}}
  if g then n = n + 1 if t[5] ~= '' then g.tags = {{src = t[5]}} end end
end
rcon.print(n)
"""


def lua_say(text):
    return f"game.print({_q(text)}) rcon.print('ok')"


def lua_destroy(surface, area, names=None, players=False):
    """Lab only: remove the area's entities (never characters). What a player placed (it has a
    ``last_user``: Rory's editor power on the lab, 2026-10-20) stays unless ``players``: a tool
    clearing its own test area never takes a person's change with it."""
    filt = f", name = {{{', '.join(_q(n) for n in names)}}}" if names else ""
    keep = "" if players else " and not e.last_user"
    return f"""
local s = game.get_surface({_q(surface)})
local n = 0
for _, e in pairs(s.find_entities_filtered{{area = {_area(area)}{filt}}}) do
  if e.type ~= 'character'{keep} and e.destroy() then n = n + 1 end
end
rcon.print(n)
"""


def lua_generate(surface, force, center, radius_chunks):
    """Generate (and chart for ``force``) the chunks around ``center``: a paste can only build on
    generated ground, and a new surface has almost none."""
    return f"""
local s = game.get_surface({_q(surface)})
s.request_to_generate_chunks({{{center[0]}, {center[1]}}}, {radius_chunks})
s.force_generate_chunk_requests()
local r = {radius_chunks} * 32
game.forces[{_q(force)}].chart(s, {{{{{center[0]} - r, {center[1]} - r}}, {{{center[0]} + r, {center[1]} + r}}}})
local n = 0
for _ in s.get_chunks() do n = n + 1 end
rcon.print(n)
"""


def lua_generate_area(surface, force, area):
    """Generate (and chart for ``force``) exactly the chunks under ``area`` and no others, so a
    paste in a lab region generates nothing outside it; prints how many of them are generated."""
    x0, y0, x1, y1 = (int(math.floor(v)) for v in area)
    return f"""
local s = game.get_surface({_q(surface)})
local n = 0
for cx = math.floor({x0} / 32), math.floor(({x1} - 1) / 32) do
  for cy = math.floor({y0} / 32), math.floor(({y1} - 1) / 32) do
    if not s.is_chunk_generated({{cx, cy}}) then s.request_to_generate_chunks({{cx * 32 + 16, cy * 32 + 16}}, 0) end
  end
end
s.force_generate_chunk_requests()
game.forces[{_q(force)}].chart(s, {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}})
for cx = math.floor({x0} / 32), math.floor(({x1} - 1) / 32) do
  for cy = math.floor({y0} / 32), math.floor(({y1} - 1) / 32) do
    if s.is_chunk_generated({{cx, cy}}) then n = n + 1 end
  end
end
rcon.print(n)
"""


def lua_seed(surface, tiles, amount=100000):
    """Lab only: put resource ``name`` under the given tiles {name: [(x, y)]} (lab terrain: a
    drill can only be placed on ore)."""
    data = json.dumps({k: [[int(x), int(y)] for x, y in v] for k, v in tiles.items()})
    return f"""
local s = game.get_surface({_q(surface)})
local n = 0
for name, ts in pairs(helpers.json_to_table({_q(data)})) do
  for _, t in pairs(ts) do
    if s.create_entity{{name = name, position = {{t[1] + 0.5, t[2] + 0.5}}, amount = {amount}}} then n = n + 1 end
  end
end
rcon.print(n)
"""


def lua_grid(surface, area):
    """'<poles> <poles with a copper wire> <electric networks>' in the area."""
    return f"""
local s = game.get_surface({_q(surface)})
local wired, nets, n = 0, {{}}, 0
for _, p in pairs(s.find_entities_filtered{{area = {_area(area)}, type = 'electric-pole'}}) do
  n = n + 1
  local c = p.get_wire_connector(defines.wire_connector_id.pole_copper, false)
  if c and c.connection_count > 0 then wired = wired + 1 end
  if p.electric_network_id then nets[p.electric_network_id] = true end
end
local k = 0
for _ in pairs(nets) do k = k + 1 end
rcon.print(n .. ' ' .. wired .. ' ' .. k)
"""


def lua_alerts(force, tag="alerts"):
    """The alert panel of every player of ``force``, connected or not: one row per alert and
    player (type name, surface, tick, target or prototype name, position; message and icon for a
    custom alert), and every force's player count. Written to script-output; the reply is the
    number of rows."""
    return f"""
local f = game.forces[{_q(force)}]
if not f then rcon.print('no force ' .. {_q(force)}) return end
local names = {{}}
for k, v in pairs(defines.alert_type) do names[v] = k end
local forces = {{}}
for _, g in pairs(game.forces) do forces[g.name] = {{players = #g.players, connected = #g.connected_players}} end
local rows, players = {{}}, {{}}
for _, p in pairs(f.players) do
  local n = 0
  for si, by_type in pairs(p.get_alerts{{}}) do
    local surface = game.get_surface(si)
    for t, list in pairs(by_type) do
      for _, a in pairs(list) do
        n = n + 1
        local row = {{type = names[t] or tostring(t), surface = surface and surface.name or tostring(si), tick = a.tick, player = p.name}}
        local target = a.target
        if target and target.valid then
          if target.type == 'entity-ghost' then row.target = target.ghost_name row.ghost = true else row.target = target.name end
        elseif a.prototype then row.target = a.prototype.name end
        local pos = a.position
        if not pos and target and target.valid then pos = target.position end
        if pos then row.x = pos.x row.y = pos.y end
        if a.message then row.message = a.message end
        if a.icon then row.icon = (a.icon.type or 'item') .. '/' .. a.icon.name end
        rows[#rows + 1] = row
      end
    end
  end
  players[#players + 1] = {{name = p.name, connected = p.connected, alerts = n}}
end
helpers.write_file('fk5/{tag}.json', helpers.table_to_json({{tick = game.tick, force = f.name, players = players, forces = forces, alerts = rows}}), false)
rcon.print(#rows)
"""


#: Statistics windows -> defines.flow_precision_index names.
WINDOWS = {"5s": "five_seconds", "1min": "one_minute", "10min": "ten_minutes",
           "1h": "one_hour", "10h": "ten_hours", "50h": "fifty_hours",
           "250h": "two_hundred_fifty_hours", "1000h": "one_thousand_hours"}


def lua_stats(force, surface, items=None, window="1min", tag="stats"):
    """The force's item production statistics on ``surface``: per item, the flow counts of
    ``get_item_production_statistics(surface)`` over ``window`` (per minute and as a count) and
    the totals; every item with a total when ``items`` is None. Written to script-output."""
    want = "nil" if not items else "{" + ", ".join(_q(i) for i in items) + "}"
    return f"""
local f = game.forces[{_q(force)}]
local s = game.get_surface({_q(surface)})
if not f or not s then rcon.print('no force or surface') return end
local st = f.get_item_production_statistics(s)
local p = defines.flow_precision_index[{_q(WINDOWS[window])}]
local names, want = {{}}, {want}
if want then for _, n in pairs(want) do names[n] = true end else
  for n in pairs(st.input_counts) do names[n] = true end
  for n in pairs(st.output_counts) do names[n] = true end
end
local rows = {{}}
for n in pairs(names) do
  if prototypes.item[n] then
    local function flow(c, count) return st.get_flow_count{{name = n, category = c, precision_index = p, count = count}} end
    rows[#rows + 1] = {{name = n, made_total = st.get_input_count(n), used_total = st.get_output_count(n), made_per_min = flow('input', false), used_per_min = flow('output', false), made = flow('input', true), used = flow('output', true)}}
  else
    rows[#rows + 1] = {{name = n, unknown = true}}
  end
end
helpers.write_file('fk5/{tag}.json', helpers.table_to_json({{tick = game.tick, force = f.name, surface = s.name, window = {_q(window)}, items = rows}}), false)
rcon.print(#rows)
"""


def lua_chart(force, surface):
    """How many of the surface's generated chunks ``force`` has charted, and their chunk box."""
    return f"""
local f = game.forces[{_q(force)}]
local s = game.get_surface({_q(surface)})
if not f or not s then rcon.print('no force or surface') return end
local n, total, x0, y0, x1, y1 = 0, 0, nil, nil, nil, nil
for c in s.get_chunks() do
  total = total + 1
  if f.is_chunk_charted(s, {{c.x, c.y}}) then
    n = n + 1
    if not x0 or c.x < x0 then x0 = c.x end
    if not y0 or c.y < y0 then y0 = c.y end
    if not x1 or c.x > x1 then x1 = c.x end
    if not y1 or c.y > y1 then y1 = c.y end
  end
end
rcon.print(helpers.table_to_json({{tick = game.tick, force = f.name, surface = s.name, charted = n, chunks = total, box = x0 and {{x0, y0, x1, y1}} or nil}}))
"""


def lua_produced(force, surface, items):
    names = ", ".join(_q(i) for i in items)
    return f"""
local st = game.forces[{_q(force)}].get_item_production_statistics({_q(surface)})
local out = {{tick = game.tick}}
for _, n in pairs({{{names}}}) do out[n] = st.get_input_count(n) end
rcon.print(helpers.table_to_json(out))
"""


CHUNK = 3000


def paste(rcon, surface, force, bp, at, chunk=CHUNK):
    """A named paste of any size: a long blueprint string travels in RCON-sized chunks into
    ``storage.fk5_bp`` (save data only; nothing is registered), then one superforced build reads
    it and clears it. -> the reply of the build (the number of entities placed)."""
    if len(bp) <= chunk:
        return rcon.lua(lua_paste(surface, force, bp, at))
    parts = [bp[i:i + chunk] for i in range(0, len(bp), chunk)]
    rcon.lua(f"storage.fk5_bp = {_q(parts[0])} rcon.print(#storage.fk5_bp)")
    for p in parts[1:]:
        rcon.lua(f"storage.fk5_bp = storage.fk5_bp .. {_q(p)} rcon.print(#storage.fk5_bp)")
    got = rcon.lua("rcon.print(#storage.fk5_bp)").strip()
    if got != str(len(bp)):
        rcon.lua("storage.fk5_bp = nil rcon.print('cleared')")
        raise LinkError(f"blueprint arrived with {got} of {len(bp)} characters")
    body = lua_paste(surface, force, "__BP__", at).replace(_q("__BP__"), "storage.fk5_bp")
    reply = rcon.lua(body)
    rcon.lua("storage.fk5_bp = nil rcon.print('cleared')")
    return reply


def read_output(rcon, lua, tag, what, keep=True):
    """Run Lua that writes ``fk5/<tag>.json`` into script-output and replies with a count; ->
    the file's JSON. ``keep=False`` removes the file once read (best effort: the game server's
    user owns it), for reads made on every agent command, like the alert panel."""
    n = rcon.lua(lua)
    if not n.strip().isdigit():
        raise LinkError(f"{what} failed: {n.strip()[:300]}")
    path = os.path.join(OUT_DIR, "fk5", f"{tag}.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not keep:
        try:
            os.remove(path)
        except OSError:
            pass
    return data


def snapshot(rcon, surface, area, tag="snap", keep=True):
    """Capture ``area``; -> the capture dict (read back from script-output). The file name
    carries the process id, so several tools can snapshot at once; ``keep=False`` removes it
    once read (a look, made on every agent command)."""
    tag = f"{tag}-{os.getpid()}"
    return read_output(rcon, lua_snapshot(surface, area, tag), tag, "snapshot", keep)


def alerts(rcon, force, tag="alerts"):
    """The raw alert panel read of ``force`` (``lua_alerts``); ``fkcore.alerts.normalise`` it."""
    tag = f"{tag}-{os.getpid()}"
    return read_output(rcon, lua_alerts(force, tag), tag, "alerts", keep=False)


def stats(rcon, force, surface, items=None, window="1min", tag="stats"):
    """The raw production statistics read (``lua_stats``)."""
    if window not in WINDOWS:
        raise LinkError(f"a statistics window is one of {', '.join(WINDOWS)}, got {window!r}")
    tag = f"{tag}-{os.getpid()}"
    return read_output(rcon, lua_stats(force, surface, items, window, tag), tag, "stats",
                       keep=False)


def chart(rcon, force, surface):
    """The raw chart read (``lua_chart``): a small reply, no file."""
    text = rcon.lua(lua_chart(force, surface)).strip()
    try:
        return json.loads(text)
    except ValueError:
        raise LinkError(f"chart failed: {text[:300]}") from None
