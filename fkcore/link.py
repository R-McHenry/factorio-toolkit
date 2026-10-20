"""fkcore.link: the game link (CORE-V1.md §9): RCON calls that read the game or make a named paste.

Every call is one short RCON command with a 5 s socket timeout (Rory: game calls take seconds).
The Lua sent here only reads, or builds through a blueprint paste, or (lab only) revives ghosts.
**Nothing here registers an event handler or a command** (an RCON-registered handler made every
save unjoinable on 2026-10-18); ``assert_safe`` refuses any Lua that would.

- ``snapshot(surface, area)``: every entity in the area as v4's capture rows (n, t, x, y, d, g,
  dc, force, hp, st, rc, it, ug, u, box) plus ``lu``, its last_user. The rows go through
  ``helpers.write_file`` into script-output and are read back from disk, so a big area never
  overflows an RCON reply; ``fkcore.scene.from_capture`` makes the scene.
- ``paste(surface, force, bp, at)``: a superforced ``build_blueprint`` of a blueprint string from a
  script inventory (the only world write). ``revive(surface, area)``: lab only, builds the area's
  ghosts at once (lab rules: free materials).
- ``decon(surface, force, area)``: marks the area for deconstruction; ``destroy`` (lab only) removes.
- ``produced(force, surface, items)``: the force's production counts (two samples are a measure).
- ``say(text)``: a line in game chat.

The RCON protocol is copied from C:\\fk-lead\\repo\\fk\\rcon.py (d6018d3), with a timeout. Stdlib only.
"""
from __future__ import annotations

import itertools
import json
import os
import re
import socket
import struct

__all__ = ["LinkError", "Rcon", "lua_snapshot", "lua_paste", "lua_revive", "lua_decon",
           "lua_destroy", "lua_produced", "lua_generate", "lua_seed", "assert_safe", "snapshot",
           "paste", "OUT_DIR"]

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


def lua_snapshot(surface, area, tag="snap"):
    return f"""
local s = game.get_surface({_q(surface)})
if not s then rcon.print('no surface') return end
local out = {{}}
for _, e in pairs(s.find_entities_filtered{{area = {_area(area)}}}) do
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


def lua_destroy(surface, area, names=None):
    filt = f", name = {{{', '.join(_q(n) for n in names)}}}" if names else ""
    return f"""
local s = game.get_surface({_q(surface)})
local n = 0
for _, e in pairs(s.find_entities_filtered{{area = {_area(area)}{filt}}}) do
  if e.type ~= 'character' and e.destroy() then n = n + 1 end
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


def snapshot(rcon, surface, area, tag="snap"):
    """Capture ``area``; -> the capture dict (read back from script-output)."""
    n = rcon.lua(lua_snapshot(surface, area, tag))
    path = os.path.join(OUT_DIR, "fk5", f"{tag}.json")
    if not n.strip().isdigit():
        raise LinkError(f"snapshot failed: {n.strip()}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
