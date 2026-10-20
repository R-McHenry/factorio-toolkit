"""transplant: put a piece of a real terrain onto the lab surface, to build on it live (lab only).

Run on the game host from a deployed v5 dir:

    python3 tools/transplant.py SRC.terrain.json --area X0,Y0,X1,Y1 --offset DX,DY \
        --region RX0,RY0,RX1,RY1 [--say "what it is"]
    python3 tools/transplant.py --clear X0,Y0,X1,Y1 --region RX0,RY0,RX1,RY1

(A negative first corner needs the = form: --area=-168,64,-24,204.)

The source area of a terrain file (``fkcore.terrain``: a ``read-terrain`` of nauvis) lands at
``area + offset`` on the ``lab`` surface: its resources with their amounts (``create_entity``), its
water (``set_tiles``, as ``water``) and its cliffs with their orientation. Trees and rocks are not
copied: they are removable, not terrain. First the target is cleared (every entity in it but
characters destroyed, every tile that is not a lab tile set back to the lab's checkerboard) and
its chunks are generated (exactly those chunks). ``--clear`` only clears.

Guards: the surface is always ``lab``; the target area must lie inside ``--region`` (the lab
region this worker owns) and so must every chunk it touches, so nothing outside the region is
generated or changed; the offset is a multiple of 4 (the cliff grid). Every game call is one
RCON command of at most a few kilobytes (the link's 5 s timeout); nothing is registered.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from fkcore import link, terrain  # noqa: E402

SURF, FORCE = "lab", "lab"
BATCH = 2400                     # characters of JSON data per RCON command


def _box(text):
    v = tuple(int(p) for p in text.split(","))
    if len(v) != 4 or v[2] <= v[0] or v[3] <= v[1]:
        raise SystemExit(f"expected X0,Y0,X1,Y1 with X1 > X0 and Y1 > Y0, got {text}")
    return v


def check_target(area, region):
    """Refuse a target whose chunks are not all inside the region."""
    x0, y0, x1, y1 = area
    cx0, cy0 = (x0 // 32) * 32, (y0 // 32) * 32
    cx1, cy1 = -((-x1) // 32) * 32, -((-y1) // 32) * 32
    rx0, ry0, rx1, ry1 = region
    if not (rx0 <= cx0 and ry0 <= cy0 and cx1 <= rx1 and cy1 <= ry1):
        raise SystemExit(f"refusing: the target {area} touches chunks {cx0},{cy0}..{cx1},{cy1} "
                         f"outside the region {region}")


def runs(tiles):
    """[[y, x0, x1], ...]: the tiles as row runs (inclusive), the compact form for set_tiles."""
    out = []
    for x, y in sorted(tiles, key=lambda t: (t[1], t[0])):
        if out and out[-1][0] == y and out[-1][2] == x - 1:
            out[-1][2] = x
        else:
            out.append([y, x, x])
    return out


def batches(rows):
    """Split a list of JSON-able rows into pieces of at most BATCH characters."""
    out, cur, size = [], [], 2
    for r in rows:
        n = len(json.dumps(r, separators=(",", ":"))) + 1
        if cur and size + n > BATCH:
            out.append(cur)
            cur, size = [], 2
        cur.append(r)
        size += n
    if cur:
        out.append(cur)
    return out


def _data(rows):
    return json.dumps(json.dumps(rows, separators=(",", ":")))


def lua_clear(area):
    x0, y0, x1, y1 = area
    return f"""
local s = game.get_surface('{SURF}')
local A = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}
local n = 0
for _, e in pairs(s.find_entities_filtered{{area = A}}) do
  if e.valid and e.type ~= 'character' and e.destroy() then n = n + 1 end
end
local tiles = {{}}
for _, t in pairs(s.find_tiles_filtered{{area = A, name = {{'lab-dark-1', 'lab-dark-2'}}, invert = true}}) do
  local p = t.position
  tiles[#tiles + 1] = {{name = ((p.x + p.y) % 2 == 0) and 'lab-dark-1' or 'lab-dark-2', position = p}}
end
if #tiles > 0 then s.set_tiles(tiles, false) end
rcon.print(n .. ' ' .. #tiles)
"""


def lua_water(rows):
    return f"""
local s = game.get_surface('{SURF}')
local tiles = {{}}
for _, r in pairs(helpers.json_to_table({_data(rows)})) do
  for x = r[2], r[3] do tiles[#tiles + 1] = {{name = 'water', position = {{x, r[1]}}}} end
end
s.set_tiles(tiles, false)
rcon.print(#tiles)
"""


def lua_resources(name, rows):
    return f"""
local s = game.get_surface('{SURF}')
local n = 0
for _, r in pairs(helpers.json_to_table({_data(rows)})) do
  if s.create_entity{{name = {json.dumps(name)}, position = {{r[1] + 0.5, r[2] + 0.5}}, amount = r[3]}} then n = n + 1 end
end
rcon.print(n)
"""


def lua_cliffs(rows):
    return f"""
local s = game.get_surface('{SURF}')
local n = 0
for _, c in pairs(helpers.json_to_table({_data(rows)})) do
  if s.create_entity{{name = c[1], position = {{c[2], c[3]}}, cliff_orientation = c[4]}} then n = n + 1 end
end
rcon.print(n)
"""


def lua_count(area):
    x0, y0, x1, y1 = area
    return f"""
local s = game.get_surface('{SURF}')
local A = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}
local res = {{}}
for _, e in pairs(s.find_entities_filtered{{area = A, type = 'resource'}}) do
  res[e.name] = (res[e.name] or 0) + 1
end
rcon.print(helpers.table_to_json({{resources = res,
  water = s.count_tiles_filtered{{area = A, collision_mask = 'water_tile'}},
  cliffs = s.count_entities_filtered{{area = A, type = 'cliff'}},
  entities = s.count_entities_filtered{{area = A}}}}))
"""


def call(r, lua):
    reply = r.lua(link.assert_safe(lua)).strip()
    if reply.startswith("Cannot execute") or reply.startswith("Error"):
        raise link.LinkError(reply[:300])
    return reply


def piece(t, area, offset):
    """The source area of terrain ``t``, moved by ``offset``: (water, {name: rows}, cliffs)."""
    x0, y0, x1, y1 = area
    dx, dy = offset

    def inside(x, y):
        return x0 <= x < x1 and y0 <= y < y1

    water = [(x + dx, y + dy) for x, y in t.water if inside(x, y)]
    res = {name: [[x + dx, y + dy, a] for (x, y), a in sorted(tiles.items()) if inside(x, y)]
           for name, tiles in sorted(t.resources.items())}
    cliffs = [[c.name, c.x + dx, c.y + dy, c.orientation] for c in t.cliffs if inside(c.x, c.y)]
    return water, {n: rows for n, rows in res.items() if rows}, cliffs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", nargs="?")
    ap.add_argument("--area")
    ap.add_argument("--offset")
    ap.add_argument("--region", required=True)
    ap.add_argument("--clear")
    ap.add_argument("--say", default="")
    a = ap.parse_args(argv)
    region = _box(a.region)
    with link.Rcon() as r:
        if a.clear:
            target = _box(a.clear)
            check_target(target, region)
            got = call(r, lua_clear(target)).split()
            print(f"cleared lab {target}: {got[0]} entities destroyed, {got[1]} tiles set back")
            if a.say:
                r.lua(link.lua_say(f"[fk5 terrain] {a.say}"))
            return 0
        if not (a.source and a.area and a.offset):
            ap.error("a transplant needs SOURCE, --area and --offset")
        area = _box(a.area)
        dx, dy = (int(v) for v in a.offset.split(","))
        if dx % 4 or dy % 4:
            raise SystemExit("the offset must be a multiple of 4 (the cliff grid)")
        target = (area[0] + dx, area[1] + dy, area[2] + dx, area[3] + dy)
        check_target(target, region)
        t = terrain.load(a.source)
        water, res, cliffs = piece(t, area, (dx, dy))
        cx, cy = (target[0] + target[2]) // 2, (target[1] + target[3]) // 2
        r.lua(link.lua_say(f"[fk5 terrain] transplanting {t.surface} {area[0]},{area[1]}.."
                           f"{area[2]},{area[3]} to lab [gps={cx},{cy},lab] (offset {dx},{dy})"
                           + (f": {a.say}" if a.say else "")))
        chunks = call(r, link.lua_generate_area(SURF, FORCE, target))
        got = call(r, lua_clear(target)).split()
        done = {"chunks": int(chunks), "cleared": int(got[0]), "tiles_reset": int(got[1]),
                "water": 0, "resources": {}, "cliffs": 0}
        for part in batches(runs(water)):
            done["water"] += int(call(r, lua_water(part)))
        for name, rows in res.items():
            for part in batches(rows):
                done["resources"][name] = done["resources"].get(name, 0) + int(
                    call(r, lua_resources(name, part)))
        for part in batches(cliffs):
            done["cliffs"] += int(call(r, lua_cliffs(part)))
        live = json.loads(call(r, lua_count(target)))
        want = {"water": len(water), "resources": {n: len(v) for n, v in res.items()},
                "cliffs": len(cliffs)}
        print(json.dumps({"source": [t.surface] + list(area), "target": list(target),
                          "offset": [dx, dy], "sent": want, "done": done, "live": live},
                         indent=1))
        ok = (live.get("water") == len(water) and live.get("cliffs") == len(cliffs)
              and (live.get("resources") or {}) == want["resources"])
        r.lua(link.lua_say(f"[fk5 terrain] transplant {'done' if ok else 'INCOMPLETE'}: "
                           f"{len(water)} water tiles, "
                           + ", ".join(f"{n} {k} tiles" for k, n in want["resources"].items())
                           + f", {len(cliffs)} cliffs"))
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
