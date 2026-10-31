"""laptop_server: a short-lived Factorio server on the laptop, for what the server's lab can't host.

    from tools.laptop_server import LaptopServer
    with LaptopServer("chat", scenario="fk-play") as srv:      # or save=PATH, or map_gen=PATH
        with srv.rcon() as r:
            ...

It is the laptop's own Factorio (Steam, 2.0.77) as a headless server with its own ``--config``:
write-data under ``v5/out/laptop-server/<name>/`` (never %APPDATA%\\Factorio: the player's client
holds that lock), its own UDP and RCON ports, no autosave, not public. The scenario is copied from
``scenario/`` into its write-data. The server is killed when the block ends, also on an error, so
nothing outlives the script that started it. ``FK_SCRIPT_OUTPUT`` is pointed at its
script-output for snapshots.

Checks it can run on its own (each starts a server, checks, stops it):
    python tools/laptop_server.py chat      the scenario loads, and a chat line reaches storage.fk_chat
    python tools/laptop_server.py own       1.2 through fkcore.apply in play mode: the toolkit's own
                                            dropped rows go (a built assembler, an unbuilt ghost), and a
                                            belt laid under another net with the old net's plates is
                                            ordered out with a fresh ghost on it
    python tools/laptop_server.py ghosts    2.0.4: single ghosts on uncharted ground keep settings
    python tools/laptop_server.py turned    2.0.5: on uncharted ground, belts, undergrounds, an
                                            inserter and a splitter standing turned (or the other
                                            end) on the design's tiles are ordered out and laid
                                            fresh as designed; the next apply finds none
    python tools/laptop_server.py health    2.0.12: the loop's world-line read on a small base:
                                            reactor fuel (with its feeding chest), robots and
                                            items in chests, stalled makers, plates made
    python tools/laptop_server.py capital SAVE.zip
                                            2.0.69: the working capital on a played map, two
                                            reads 30 game seconds apart
"""
from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from fkcore import link  # noqa: E402

EXE = os.environ.get("FK_LAPTOP_FACTORIO",
                     r"C:\Program Files (x86)\Steam\steamapps\common\Factorio\bin\x64\factorio.exe")
BASE = os.path.join(ROOT, "out", "laptop-server")


def _free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LaptopServer:
    def __init__(self, name, scenario=None, save=None, map_gen=None, boot_s=40):
        self.name, self.scenario, self.save, self.map_gen, self.boot_s = (name, scenario, save,
                                                                          map_gen, boot_s)
        self.dir = os.path.join(BASE, name)
        self.write = os.path.join(self.dir, "write")
        self.pw_file = os.path.join(self.dir, "rcon.pw")
        self.port = _free_port(socket.SOCK_DGRAM)
        self.rcon_port = _free_port()
        self.proc = None

    def _files(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        os.makedirs(os.path.join(self.write, "scenarios"))
        if self.scenario:
            shutil.copytree(os.path.join(ROOT, "scenario", self.scenario),
                            os.path.join(self.write, "scenarios", self.scenario))
        with open(os.path.join(self.dir, "config.ini"), "w", encoding="utf-8") as fh:
            fh.write("[path]\nread-data=__PATH__executable__/../../data\n"
                     f"write-data={self.write.replace(os.sep, '/')}\n")
        with open(os.path.join(self.dir, "server-settings.json"), "w", encoding="utf-8") as fh:
            fh.write('{"name": "fk5 laptop test", "description": "short-lived test server", '
                     '"visibility": {"public": false, "lan": false}, '
                     '"require_user_verification": false, "max_players": 0, "auto_pause": false, '
                     '"autosave_interval": 0}')
        with open(self.pw_file, "w", encoding="utf-8") as fh:
            fh.write(secrets.token_hex(12))

    def __enter__(self):
        self._files()
        with open(self.pw_file, encoding="utf-8") as fh:
            pw = fh.read().strip()
        args = [EXE, "--config", os.path.join(self.dir, "config.ini"), "--port", str(self.port),
                "--rcon-bind", f"127.0.0.1:{self.rcon_port}", "--rcon-password", pw,
                "--server-settings", os.path.join(self.dir, "server-settings.json")]
        if self.save:
            args += ["--start-server", self.save]
        else:
            args += ["--start-server-load-scenario", self.scenario or "fk-play"]
        if self.map_gen:
            args += ["--map-gen-settings", self.map_gen]
        self.log = open(os.path.join(self.dir, "server.log"), "w", encoding="utf-8")
        self.proc = subprocess.Popen(args, stdout=self.log, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL)
        os.environ["FK_SCRIPT_OUTPUT"] = os.path.join(self.write, "script-output")
        link.OUT_DIR = os.environ["FK_SCRIPT_OUTPUT"]
        t0 = time.time()
        while time.time() - t0 < self.boot_s:
            if self.proc.poll() is not None:
                raise RuntimeError(f"the server exited ({self.proc.returncode}): see {self.log.name}")
            try:
                with self.rcon() as r:
                    if r.lua("rcon.print(game.tick)").strip().isdigit():
                        return self
            except (OSError, link.LinkError):
                pass
            time.sleep(1)
        self.__exit__(None, None, None)
        raise RuntimeError(f"no RCON answer within {self.boot_s} s: see {self.log.name}")

    def rcon(self):
        return link.Rcon("127.0.0.1", self.rcon_port, self.pw_file)

    def __exit__(self, *exc):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)
        if getattr(self, "log", None):
            self.log.close()
        return False


def check_chat():
    from fkcore import chat
    with LaptopServer("chat", scenario="fk-play") as srv:
        with srv.rcon() as r:
            before = chat.read(r)
            r.call("hello from the laptop test server")       # plain RCON text is console chat
            time.sleep(1.5)
            after = chat.read(r)
            info = r.lua("rcon.print(script.level.level_name .. ' ' .. tostring(game.get_surface('lab') ~= nil)"
                         " .. ' ' .. tostring(game.forces['lab'] ~= nil))").strip()
    print(f"scenario: {info}")
    print(f"journal before: {before['journal']}, {len(before['messages'])} messages")
    print(f"journal after:  {after['journal']}, messages {after['messages']}")
    ok = after["journal"] and any("hello from the laptop" in m.get("message", "")
                                  for m in after["messages"])
    print("chat journal:", "OK" if ok else "NOT recorded")
    return 0 if ok else 1


def check_own():
    """The mini factory (tests/test_fkp.py) pasted on the lab surface under play rules and built
    (revived: test setup), then a chest left as a ghost; then a design that drops the assembler
    m1 and the chest and lays the iron belt row under net cable while belt b2 holds iron plates."""
    from fkcore import apply as applymod, compose, fkp
    from fkcore.catalog import Catalog
    from tests.test_fkp import MINI
    cat, s, f = Catalog.load(), "lab", "lab"
    watch = {"plots": "keep", "sanctioned": "mark 2h", "notify": "off"}

    def composed(text):
        return compose.compose(fkp.loads("fkp 1 surface lab\nplot mini at 10,0 rot 0 size 7x7\n"),
                               {"mini": fkp.loads(text)}, cat)

    def at(r, x, y):
        return r.lua(f"local o = {{}} for _, e in pairs(game.get_surface('{s}').find_entities_filtered"
                     f"{{position = {{{x}, {y}}}, radius = 0.3}}) do o[#o + 1] = (e.type == "
                     "'entity-ghost' and ('ghost:' .. e.ghost_name) or e.name) .. "
                     "(e.to_be_deconstructed() and '(decon)' or '') end "
                     "rcon.print(table.concat(o, ' '))").strip()

    v2 = (MINI.replace("e gears/m1 assembling-machine-1 4.5,3.5 recipe=iron-gear-wheel\n", "")
          .replace("~iron/", "~cable/").replace("net=iron", "net=cable"))
    nets1 = {"mini/iron": ["iron-plate"], "mini/gear": ["iron-gear-wheel"]}
    nets2 = {"mini/cable": ["copper-cable"], "mini/gear": ["iron-gear-wheel"]}
    with LaptopServer("own", scenario="fk-play") as srv:
        with srv.rcon() as r:
            r.lua(link.lua_generate_area(s, f, (-32, -32, 64, 64)))
            rep = applymod.apply(r, composed(MINI), cat, mode="play", force=f, policy=watch,
                                 net_items=nets1)
            r.lua(link.lua_revive(s, (0, -10, 40, 20)))
            rep = applymod.apply(r, composed(MINI + "e extra/c0 wooden-chest 16.5,5.5\n"), cat,
                                 mode="play", force=f, policy=watch, net_items=nets1, own=rep.own)
            ghost = at(r, 26.5, 5.5)
            r.lua(f"local b = game.get_surface('{s}').find_entity('transport-belt', {{14.5, 0.5}}) "
                  "b.get_transport_line(1).insert_at_back({name = 'iron-plate', count = 1}) "
                  "rcon.print('ok')")
            rep = applymod.apply(r, composed(v2), cat, mode="play", force=f, policy=watch,
                                 net_items=nets2, own=rep.own)
            got = {"chest before": ghost, "m1": at(r, 14.5, 3.5), "chest": at(r, 26.5, 5.5),
                   "b2": at(r, 14.5, 0.5)}
    print("\n".join(rep.lines()))
    want = {"chest before": "ghost:wooden-chest", "m1": "assembling-machine-1(decon)",
            "chest": "", "b2": "ghost:transport-belt transport-belt(decon)"}
    for k, v in want.items():
        print(f"{k:<13} {got[k] or '(nothing)':<45} {'OK' if got[k] == v else 'NOT ' + repr(v)}")
    return 0 if got == want and rep.dropped == 2 and len(rep.relaid) == 1 else 1


#: what the ghosts check reads back of each design entity, ghost or built: every read is
#: pcall'd, since a ghost lacks some of them
_READ = r"""
local s = game.get_surface(__SURFACE__)
local out = {}
local function get(fn) local ok, v = pcall(fn) if ok then return v end end
for _, p in ipairs(helpers.json_to_table(__POS__)) do
  for _, e in pairs(s.find_entities_filtered{position = {p[2], p[3]}, radius = 0.3}) do
    local g = e.type == 'entity-ghost'
    if (g and e.ghost_name or e.name) == p[1] then
      local r = {key = p[4], ghost = g, dc = e.to_be_deconstructed(), d = e.direction}
      local rc = get(function() return e.get_recipe() end)
      r.recipe = rc and rc.name
      r.ug = get(function() return e.belt_to_ground_type end)
      local cb = get(function() return e.get_control_behavior() end)
      if cb then
        r.enable = get(function() return cb.circuit_enable_disable end)
        local c = get(function() return cb.circuit_condition end)
        if c and c.first_signal then
          r.cond = c.first_signal.name .. c.comparator .. tostring(c.constant)
        end
        r.read = get(function() return cb.read_contents end)
        r.read_mode = get(function() return cb.read_contents_mode end)
        if (get(function() return cb.sections_count end) or 0) > 0 then
          local f = cb.get_section(1).filters[1]
          r.signals = f and f.value and (f.value.name .. ':' .. tostring(f.min))
        end
      end
      local ls = get(function() return e.get_logistic_sections() end)
      if ls then
        local q = {}
        for _, sec in pairs(ls.sections) do
          for _, f in pairs(sec.filters) do
            if f.value then q[#q + 1] = f.value.name .. ':' .. tostring(f.min) .. '-' .. tostring(f.max) end
          end
        end
        r.requests = table.concat(q, ',')
      end
      r.trash = get(function() return e.get_requester_point().trash_not_requested end)
      r.split = get(function() return e.splitter_input_priority .. '/' .. e.splitter_output_priority end)
      r.split_filter = get(function() return e.splitter_filter.name.name end)
        or get(function() return e.splitter_filter.name end)
      r.plan = get(function()
        local p = g and e.insert_plan or e.item_request_proxy.insert_plan
        return p[1].id.name .. ':' .. p[1].items.in_inventory[1].count
      end)
      r.use_filters = get(function() return e.use_filters end)
      local f1 = get(function() return e.get_filter(1) end)
      r.filter = f1 and (f1.name or (f1.value and f1.value.name)) or nil
      local inv = (not g) and get(function() return e.get_inventory(defines.inventory.chest) end)
      if inv then r.bar = get(function() return inv.get_bar() end) end
      local w = {}
      for _, id in ipairs({1, 2, 5}) do
        local c = get(function() return e.get_wire_connector(id, false) end)
        if c and c.connection_count > 0 then w[#w + 1] = id .. 'x' .. c.connection_count end
      end
      r.wires = table.concat(w, ',')
      out[#out + 1] = r
    end
  end
end
rcon.print(helpers.table_to_json(out))
"""


def check_ghosts():
    """2.0.4 (A1): a play apply on uncharted ground (lab tiles generated for the lab force and
    never charted, as on the 2.0 run's map with no radar and no character) is refused by the
    paste and placed as single ghosts; what each ghost keeps of its settings and wires is read
    back, and again once they are revived (as robots build them). Then the built inserter is
    ordered out (as an order-up for new settings does) and a second apply must lay its ghost."""
    import json
    from fkcore import apply as applymod, compose, fkp
    from fkcore.catalog import Catalog
    cat, s, f = Catalog.load(), "lab", "lab"
    req = json.dumps({"bar": 2, "request_filters": {"trash_not_requested": True, "sections": [
        {"index": 1, "filters": [{"index": 1, "name": "iron-plate", "quality": "normal",
                                  "comparator": "=", "count": 12, "max_count": 10}]}]}},
                     separators=(",", ":"))
    text = ("fkp 1 factory gh\nsize 12x6\nwire w red\n"
            "w w red box/c0 ~n/i0\n"
            "e m/m0 assembling-machine-2 1.5,1.5 recipe=iron-gear-wheel\n"
            f"e box/c0 requester-chest 3.5,0.5 config='{req}'\n"
            "e ~n/i0 inserter 4.5,0.5 E net=n if=iron-plate<5\n"
            "e ~n/i1 fast-inserter 4.5,1.5 E net=n filter=iron-plate|copper-plate\n"
            "e cc/k0 constant-combinator 6.5,0.5 N signals=signal-A:7\n"
            "e ~b/b0 transport-belt 6.5,2.5 E net=b read=hold\n"
            "e ~b/u0 underground-belt 7.5,2.5 E net=b ug=in\n"
            "e ~b/u1 underground-belt 9.5,2.5 E net=b ug=out\n"
            "e power/p0 small-electric-pole 0.5,4.5\n"
            "e power/p1 small-electric-pole 5.5,4.5\n")
    # a ghost has no requester point, so trash_not_requested cannot ride on it: the apply must
    # name that as a setting the ghost would not take (checked below), not lose it silently
    want = {"m/m0": {"recipe": "iron-gear-wheel"},
            "box/c0": {"requests": "iron-plate:10-10", "wires": "1x1"},
            "~n/i0": {"enable": True, "cond": "iron-plate<5", "wires": "1x1"},
            "~n/i1": {"use_filters": True, "filter": "iron-plate"},
            "cc/k0": {"signals": "signal-A:7"},
            "~b/b0": {"read": True, "read_mode": 1},
            "~b/u0": {"ug": "input", "d": 4}, "~b/u1": {"ug": "output", "d": 4},
            "power/p0": {"wires": "5x1"}, "power/p1": {"wires": "5x1"}}
    sur = compose.compose(fkp.loads("fkp 1 surface lab\nplot gh at 320,320 rot 0 size 12x6\n"),
                          {"gh": fkp.loads(text)}, cat)
    rows = applymod.scope_rows(sur)
    pos = json.dumps([[r["name"], float(r["x"]), float(r["y"]), r["src"].split(":gh/")[-1]]
                      for r in rows])
    area = (300, 300, 350, 340)
    ins = "{324.5, 320.5}"                    # ~n/i0

    def read(r, ghost):
        body = _READ.replace("__SURFACE__", link._q(s)).replace("__POS__", link._q(pos))
        reply = r.lua(body).strip()
        got = json.loads(reply) if reply.startswith("[") else []
        return {t["key"]: t for t in got if t["ghost"] == ghost}

    def judge(stage, got, ghost):
        bad = 0
        for key, w in want.items():
            t = got.get(key)
            miss = {k: [t.get(k), v] for k, v in w.items() if t and t.get(k) != v}
            ok = bool(t) and t.get("ghost") == ghost and not miss
            bad += not ok
            print(f"  {stage:<6} {key:<9} {'OK' if ok else 'NOT' if t else 'MISSING'} "
                  f"{'' if ok or not t else 'got, wanted: ' + json.dumps(miss)}")
        return bad

    with LaptopServer("ghosts", scenario="fk-play") as srv:
        with srv.rcon() as r:
            charted = r.lua(f"""
local s, f = game.get_surface('{s}'), game.forces['{f}']
for cx = 9, 10 do for cy = 9, 10 do s.request_to_generate_chunks({{cx * 32 + 16, cy * 32 + 16}}, 0) end end
s.force_generate_chunk_requests()
local c = 0
for cx = 9, 10 do for cy = 9, 10 do if f.is_chunk_charted(s, {{cx, cy}}) then c = c + 1 end end end
rcon.print(c)""").strip()
            print(f"charted chunks under the plot: {charted} of 4")
            rep = applymod.apply(r, sur, cat, area=area, mode="play", force=f)
            print("\n".join(rep.lines()))
            ghosts = read(r, True)
            r.lua(link.lua_revive(s, area))
            built = read(r, False)
            r.lua(f"game.get_surface('{s}').find_entity('inserter', {ins})"
                  f".order_deconstruction('{f}') rcon.print('ok')")
            rep2 = applymod.apply(r, sur, cat, area=area, mode="play", force=f)
            print("\n".join(rep2.lines()))
            again = r.lua(
                f"local o = {{}} for _, e in pairs(game.get_surface('{s}').find_entities_filtered"
                f"{{position = {ins}, radius = 0.3}}) do local g = e.type == 'entity-ghost' "
                "o[#o + 1] = (g and ('ghost:' .. e.ghost_name) or e.name) .. "
                "(e.to_be_deconstructed() and '(decon)' or '') end "
                "rcon.print(table.concat(o, ' '))").strip()
            relaid = read(r, True).get("~n/i0", {})
    bad = judge("ghost", ghosts, True) + judge("built", built, False)
    named = rep.alone_missed.get("request_filters.trash_not_requested")
    print(f"  not takeable on a ghost, named in the report: trash_not_requested x{named}")
    print(f"  inserter ordered out, applied again: {again}; the new ghost's wires "
          f"{relaid.get('wires')!r}, condition {relaid.get('cond')!r}")
    ok = (charted == "0" and rep.pasted == 0 and rep.placed_alone == len(rows) and not bad
          and named == 1 and "ghost:inserter" in again)
    print("single ghosts on uncharted ground:", "OK" if ok else "NOT as designed")
    return 0 if ok else 1


def check_turned():
    """2.0.5 (TURNED): what an old factory left on a new one's tiles under the same names, facing
    the old ways (the 2.0 run's south iron array on the burner iron block), where the paste is
    refused: a play apply orders each out and lays its single ghost as designed; once robots took
    the old ones up and built the ghosts (here: destroyed, revived) every one faces as designed,
    and a second apply turns nothing. The 2.0 run's map refused every paste (uncharted: its
    apply.txt says "0 ghosts placed"), but this server's lab ground takes them even uncharted
    (2026-10-22: the ghosts check's paste placed all 10), so the refusal is simulated (the paste
    places nothing) and all the rest is the game's. Where a paste lands, it turns them itself."""
    import json
    from unittest import mock
    from fkcore import apply as applymod, compose, fkp
    from fkcore.catalog import Catalog
    cat, s, f = Catalog.load(), "lab", "lab"
    text = ("fkp 1 factory tu\nsize 10x3\n"
            "e ~b/b0 transport-belt 0.5,0.5 E net=b\n"
            "e ~b/b1 transport-belt 1.5,0.5 E net=b\n"
            "e ~b/b2 transport-belt 2.5,0.5 E net=b\n"
            "e ~b/u0 underground-belt 3.5,0.5 E net=b ug=in\n"
            "e ~b/u1 underground-belt 6.5,0.5 E net=b ug=out\n"
            "e ~b/b3 transport-belt 7.5,0.5 E net=b\n"
            "e ~b/s0 splitter 8.5,1 E net=b\n"
            "e ~b/i0 inserter 2.5,1.5 N net=b\n")
    sur = compose.compose(fkp.loads("fkp 1 surface lab\nplot tu at 320,320 rot 0 size 10x3\n"),
                          {"tu": fkp.loads(text)}, cat)
    # what stands first: b0 turned round, b1 a quarter turn off, b2 as designed, the two
    # underground ends swapped, b3 as designed, the splitter turned round, the inserter too
    stand = [["transport-belt", 320.5, 320.5, 12, None], ["transport-belt", 321.5, 320.5, 0, None],
             ["transport-belt", 322.5, 320.5, 4, None],
             ["underground-belt", 323.5, 320.5, 4, "output"],
             ["underground-belt", 326.5, 320.5, 4, "input"],
             ["transport-belt", 327.5, 320.5, 4, None], ["splitter", 328.5, 321, 12, None],
             ["inserter", 322.5, 321.5, 8, None]]
    want = {(r["name"], float(r["x"]), float(r["y"])): (r["direction"] or 0,
                                                        {"in": "input", "out": "output"}.get(
                                                            r["attrs"].get("ug")))
            for r in applymod.scope_rows(sur)}
    area = (300, 300, 350, 340)
    read_lua = ("local s = game.get_surface('lab') local o = {} "
                "for _, p in pairs(helpers.json_to_table(__P__)) do "
                "for _, e in pairs(s.find_entities_filtered{position = {p[2], p[3]}, radius = 0.3}) do "
                "local g = e.type == 'entity-ghost' local ug = nil "
                "pcall(function() ug = e.belt_to_ground_type end) "
                "o[#o + 1] = {n = g and e.ghost_name or e.name, x = e.position.x, y = e.position.y, "
                "d = e.direction, g = g, dc = e.to_be_deconstructed(), ug = ug} end end "
                "rcon.print(helpers.table_to_json(o))")
    pts = link._q(json.dumps(stand))

    def read(r):
        reply = r.lua(read_lua.replace("__P__", pts)).strip()
        return json.loads(reply) if reply.startswith("[") else []

    def judge(stage, got, built):
        """Each design tile holds one thing not ordered out (built, when ``built``), as designed."""
        bad = 0
        for (name, x, y), (d, ug) in sorted(want.items()):
            here = [t for t in got if (t["n"], t["x"], t["y"]) == (name, x, y)]
            lay = [t for t in here if not t["dc"] and not (built and t["g"])]
            ok = len(lay) == 1 and lay[0]["d"] == d and (ug is None or lay[0]["ug"] == ug)
            bad += not ok
            print(f"  {stage:<7} {name} {x},{y}: " + " + ".join(
                f"{'ghost ' if t['g'] else ''}d{t['d']}{' ' + t['ug'] if t.get('ug') else ''}"
                f"{' (decon)' if t['dc'] else ''}" for t in here) + f"  {'OK' if ok else 'NOT'}")
        return bad

    with LaptopServer("turned", scenario="fk-play") as srv:
        with srv.rcon() as r:
            charted = r.lua(f"""
local s, f = game.get_surface('{s}'), game.forces['{f}']
for cx = 9, 10 do for cy = 9, 10 do s.request_to_generate_chunks({{cx * 32 + 16, cy * 32 + 16}}, 0) end end
s.force_generate_chunk_requests()
local c = 0
for cx = 9, 10 do for cy = 9, 10 do if f.is_chunk_charted(s, {{cx, cy}}) then c = c + 1 end end end
for _, t in pairs(helpers.json_to_table({pts})) do
  s.create_entity{{name = t[1], position = {{t[2], t[3]}}, direction = t[4], force = f, type = t[5]}}
end
rcon.print(c)""").strip()
            print(f"charted chunks under the plot: {charted} of 4")
            print("as the old factory left them:")
            judge("before", read(r), True)
            with mock.patch.object(link, "paste", lambda *a, **k: "0"):
                rep = applymod.apply(r, sur, cat, area=area, mode="play", force=f)
            print("\n".join(rep.lines()))
            bad = judge("ghosts", read(r), False)
            r.lua(f"""
local s = game.get_surface('{s}')
for _, e in pairs(s.find_entities_filtered{{area = {{{{{area[0]}, {area[1]}}}, {{{area[2]}, {area[3]}}}}}}}) do
  if e.valid and e.type ~= 'entity-ghost' and e.to_be_deconstructed() then e.destroy() end
end
local n = 0
for _, g in pairs(s.find_entities_filtered{{area = {{{{{area[0]}, {area[1]}}}, {{{area[2]}, {area[3]}}}}}, type = 'entity-ghost'}}) do
  local _, e = g.revive() if e then n = n + 1 end
end
rcon.print(n)""")
            bad += judge("built", read(r), True)
            again = applymod.apply(r, sur, cat, area=area, mode="play", force=f)
            print("applied again: " + "; ".join(again.lines()[1:]))
    ok = (charted == "0" and rep.pasted == 0 and len(rep.turned) == 6 and not bad
          and again.turned == [])
    print("turned entities where the paste is refused:", "OK" if ok else "NOT as designed")
    return 0 if ok else 1


def check_health():
    """2.0.12: the loop's world-line read (kickoff/claude_loop.STATUS_LUA) on a small base: a
    reactor with 2 fuel cells and 3 more in the chest its inserter takes from (5 x 8 GJ at 40 MW:
    about 17 minutes, LOW), 5 logistic robots in a storage chest beside an unpowered roboport,
    500 plastic and 401 sulfur in a wooden chest far from it (and the 3 cells: no network reaches
    the reactor's chest), an unpowered assembler, a boiler with no fuel, and 100 iron plates in
    the production statistics."""
    import json
    sys.path.insert(0, os.path.join(ROOT, "kickoff"))
    import claude_loop
    setup = """
local s, f = game.surfaces.nauvis, game.forces.player
s.request_to_generate_chunks({0, 0}, 5)
s.force_generate_chunk_requests()
local tiles = {}
for x = -10, 120 do for y = -10, 120 do tiles[#tiles + 1] = {name = 'landfill', position = {x, y}} end end
s.set_tiles(tiles)
for _, e in pairs(s.find_entities_filtered{area = {{-10, -10}, {120, 120}}}) do
  if e.valid and e.type ~= 'character' then e.destroy() end
end
local r = s.create_entity{name = 'nuclear-reactor', position = {12.5, 12.5}, force = f}
r.get_fuel_inventory().insert{name = 'uranium-fuel-cell', count = 2}
local c = s.create_entity{name = 'iron-chest', position = {16.5, 12.5}, force = f}
c.insert{name = 'uranium-fuel-cell', count = 3}
local i = s.create_entity{name = 'inserter', position = {15.5, 12.5}, force = f, direction = defines.direction.east}
if i.drop_position.x > 15.5 then i.direction = defines.direction.west end
s.create_entity{name = 'roboport', position = {40, 40}, force = f}
local st = s.create_entity{name = 'storage-chest', position = {43.5, 40.5}, force = f}
st.insert{name = 'logistic-robot', count = 5}
local w = s.create_entity{name = 'wooden-chest', position = {110.5, 110.5}, force = f}
w.insert{name = 'plastic-bar', count = 500}
w.insert{name = 'sulfur', count = 401}
local a = s.create_entity{name = 'assembling-machine-2', position = {20.5, 30.5}, force = f}
a.set_recipe('iron-gear-wheel')
s.create_entity{name = 'boiler', position = {30.5, 60}, force = f}
f.get_item_production_statistics(s).on_flow('iron-plate', 100)
rcon.print(string.format('drop %.1f,%.1f pickup %.1f,%.1f', i.drop_position.x, i.drop_position.y,
                         i.pickup_position.x, i.pickup_position.y))
"""
    with LaptopServer("health", scenario="fk-play") as srv:
        with srv.rcon() as r:
            print("setup, the inserter (the reactor west of it, the chest east):",
                  r.lua(setup).strip())
            r.lua("rcon.print(game.tick)")
            t0 = time.time()
            out = r.lua(claude_loop.STATUS_LUA.replace("CURSOR", "0"))
            took = time.time() - t0
            # then a game minute and more with nothing made: the base is dead
            tick = int(r.lua("game.speed = 30 rcon.print(game.tick)").strip())
            while int(r.lua("rcon.print(game.tick)").strip()) < tick + 75 * 60 \
                    and time.time() - t0 < 60:
                time.sleep(0.5)
            r.lua("game.speed = 1 rcon.print(1)")
            later = r.lua(claude_loop.STATUS_LUA.replace("CURSOR", "0"))
    st = json.loads([ln for ln in out.splitlines() if ln.startswith("{")][-1])
    dead_line, dead_key = claude_loop.status_line(
        json.loads([ln for ln in later.splitlines() if ln.startswith("{")][-1]))
    print(f"75 game seconds later: {dead_line}\nkey: {dead_key}")
    h = st.get("health") or {}
    print(f"read in {took:.2f} s; health: {json.dumps(h, sort_keys=True)}")
    line, key = claude_loop.status_line(st)
    print(f"world line: {line}\nkey: {key}")
    reactor = (h.get("fuel") or {}).get("reactor") or {}
    off = h.get("off") or {}
    ok = (not h.get("error") and 15 < (reactor.get("min") or 0) < 18
          and (h.get("robots") or {}).get("logistic") == 5 and off.get("items") == 904
          and (off.get("top") or [{}])[0].get("name") == "plastic-bar"
          and "no_power" in ((h.get("makers") or {}).get("stalled") or {})
          and h["plates"]["iron-plate"]["ever"] == 100
          and "fuel:low" in key and "robots:chest" in key and took < 5
          and "plates:none" in dead_key and dead_line.startswith("BASE DEAD"))
    print("world-line health read:", "OK" if ok else "NOT as designed")
    return 0 if ok else 1


#: check_settings' design: a condition, a filter, a reading on a wire, a request, a slot limit
#: and a constant combinator
SET = """\
fkp 1 factory set
size 12x6
wire w red
e m/m0 assembling-machine-2 1.5,1.5 recipe=iron-gear-wheel read=contents
e m/i0 inserter 4.5,0.5 E logistic=iron-plate<50
e m/i1 inserter 4.5,1.5 E filter=iron-plate|copper-plate
e m/i2 inserter 4.5,2.5 E if=iron-gear-wheel<100
e m/i3 inserter 6.5,0.5 E
e m/c0 requester-chest 8.5,0.5
e m/c1 wooden-chest 8.5,2.5
e m/k0 constant-combinator 10.5,0.5 signals=signal-A:5
w w red m/m0 m/i2
"""


def check_settings():
    """2.0.12: a diff sees settings changed by hand on entities the toolkit placed. The design
    SET is pasted under play rules and built (revived); a diff then finds nothing. Then, by Lua:
    i0's logistic condition, a red wire from i3 to i1, c0's request, m0's recipe and c1's limit
    change. The diff names each, the apply's hand edits too, and after the paste i0's condition and
    c0's request are the design's again; the wire from i3 stays (the design has none)."""
    from fkcore import apply as applymod, codec, compose, fkp
    from fkcore.catalog import Catalog
    cat, s, f = Catalog.load(), "lab", "lab"
    watch = {"plots": "keep", "sanctioned": "mark 2h", "notify": "off"}
    lay = fkp.loads(SET)
    lay.entities["m/c0"].attrs["config"] = codec.config_text({"request_filters": {"sections": [
        {"index": 1, "filters": [{"index": 1, "name": "iron-plate", "quality": "normal",
                                  "comparator": "=", "count": 100}]}]}})
    lay.entities["m/c1"].attrs["config"] = codec.config_text({"bar": 2})
    composed = compose.compose(fkp.loads("fkp 1 surface lab\nplot set at 10,0 rot 0 size 12x6\n"),
                               {"set": lay}, cat)
    area = (8, -2, 24, 8)
    tweak = """
local s = game.get_surface('lab')
local function at(n, x, y) return s.find_entity(n, {x, y}) end
local cb = at('inserter', 14.5, 0.5).get_or_create_control_behavior()
cb.logistic_condition = {first_signal = {type = 'item', name = 'copper-plate'}, comparator = '>', constant = 7}
at('inserter', 16.5, 0.5).get_wire_connector(defines.wire_connector_id.circuit_red, true).connect_to(
  at('inserter', 14.5, 1.5).get_wire_connector(defines.wire_connector_id.circuit_red, true))
at('requester-chest', 18.5, 0.5).get_logistic_sections().get_section(1).set_slot(1, {value = 'copper-plate', min = 5})
at('assembling-machine-2', 11.5, 1.5).set_recipe('copper-cable')
at('wooden-chest', 18.5, 2.5).get_inventory(defines.inventory.chest).set_bar(6)
rcon.print('ok')"""
    after = """
local s = game.get_surface('lab')
local c = s.find_entity('inserter', {14.5, 0.5}).get_control_behavior().logistic_condition
local sl = s.find_entity('requester-chest', {18.5, 0.5}).get_logistic_sections().get_section(1).get_slot(1)
local w = s.find_entity('inserter', {16.5, 0.5}).get_wire_connector(defines.wire_connector_id.circuit_red, true).connection_count
local bar = s.find_entity('wooden-chest', {18.5, 2.5}).get_inventory(defines.inventory.chest).get_bar()
local rc = s.find_entity('assembling-machine-2', {11.5, 1.5}).get_recipe()
rcon.print(c.first_signal.name .. c.comparator .. c.constant .. ' ' .. tostring(sl.value and sl.value.name) .. ' ' .. w
           .. ' ' .. bar .. ' ' .. tostring(rc and rc.name))"""
    with LaptopServer("settings", scenario="fk-play") as srv:
        with srv.rcon() as r:
            r.lua(link.lua_generate_area(s, f, (-32, -32, 64, 64)))
            rep = applymod.apply(r, composed, cat, area=area, mode="play", force=f, policy=watch)
            r.lua(link.lua_revive(s, area))
            clean = applymod.diff(r, composed, cat, area, watch, force=f)
            r.lua(tweak)
            seen = applymod.diff(r, composed, cat, area, watch, force=f)
            rep = applymod.apply(r, composed, cat, area=area, mode="play", force=f, policy=watch,
                                 own=rep.own)
            back = r.lua(after).strip()
    print(f"untouched: {len(clean.settings)} differences {clean.settings_error or ''}")
    for d in clean.settings:
        print("   ", d.line())
    print("after the tweaks:")
    for d in seen.settings:
        print("   ", d.line())
    print("the apply's hand edits:", len(rep.hand))
    print("after the paste (i0's condition, c0's request, red wires on i3, c1's bar, m0's recipe):",
          back)
    keys = sorted(d.key.split("/")[-1] for d in seen.settings)
    ok = (not clean.settings and not clean.settings_error
          and keys == ["c0", "c1", "i0", "i1", "i3", "m0"]
          and len(rep.hand) >= 6 and back.startswith("iron-plate<50 iron-plate 1 "))
    print("settings changed by hand:", "OK" if ok else "NOT as designed")
    return 0 if ok else 1


def check_lab():
    """2.0.12: the lab has no edge. The lab surface is set back to 2048 x 2048 (a save made
    before), 100 slots are taken, then `fk lab` builds the smelting example (TOOLKIT's) as a
    450 x 300 factory: its slot lies past the old edge, the build takes the edge off, generates
    the chunks under it, and the diff after the apply is all OK."""
    import tempfile
    from fkcore import lab
    run = tempfile.mkdtemp(prefix="fklabsize-")
    game = os.path.join(run, "game")
    os.makedirs(game)
    shutil.copy(os.path.join(ROOT, "agent", "docs", "examples", "smelting.fk"), game)
    for name, text in (("nauvis.surface", "surface  nauvis\nmode     play\nterrain  none\n"
                        "catalog  base\n\nplace iron = smelting plot 10,90 26x26\n"),
                       ("nauvis.build.fkb", "read_surface nauvis\n")):
        with open(os.path.join(game, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    for k in range(100):
        lab.slot_of(game, f"f{k}", (150, 150))
    with LaptopServer("lab", scenario="fk-play") as srv:
        with srv.rcon() as r:
            print("a new lab:", r.lua("local m = game.get_surface('lab').map_gen_settings "
                                     "rcon.print(m.width .. 'x' .. m.height)").strip())
            r.lua("local s = game.get_surface('lab') local m = s.map_gen_settings "
                  "m.width, m.height = 2048, 2048 s.map_gen_settings = m rcon.print(1)")
            t0 = time.time()
            lines = lab.build(r, game, "iron", size=(450, 300))
            took = time.time() - t0
            x, y, w, h = lab.slots(game)["iron"]
            far = r.lua(f"local s = game.get_surface('lab') "
                        f"rcon.print(s.get_tile({x + w - 20}, {y + h - 20}).name .. ' ' .. "
                        f"s.count_entities_filtered{{area = {{{{{x}, {y}}}, {{{x + w}, {y + h}}}}}, "
                        f"force = 'lab'}})").strip()
    print("\n".join(lines))
    print(f"slot {x},{y} {w}x{h}; tile and entities there: {far}; {took:.1f} s")
    diff = next((ln for ln in lines if ln.strip().startswith("diff")), "")
    ok = (max(abs(x), abs(y), abs(x + w), abs(y + h)) > 1024 and (w, h) == (600, 400)
          and "the lab has no edge now (it was 2048x2048)" in "\n".join(lines)
          and far.startswith("lab-") and int(far.split()[1]) > 0 and "OK" in diff)
    print("a lab without an edge:", "OK" if ok else "NOT as designed")
    shutil.rmtree(run, True)
    return 0 if ok else 1


def check_capital(save=None):
    """2.0.69: the working capital on a played map (a sim save: ``capital SAVE.zip``), two reads
    30 game seconds apart, each in under 5 s, and the report."""
    import tempfile
    from fkcore import capital
    from fkcore.catalog import Catalog
    save = save or (sys.argv[2] if len(sys.argv) > 2 else None)
    if not save:
        print("capital: give a save (.zip) to read")
        return 2
    cat, game = Catalog.load(), tempfile.mkdtemp(prefix="fk-capital-")
    took = []
    with LaptopServer("capital", save=save) as srv:
        with srv.rcon() as r:
            r.lua("game.tick_paused = false rcon.print(1)")     # a sim save stands still
            for i in range(2):
                t0 = time.time()
                out = capital.run(r, game, cat, "player", "nauvis")
                took.append(time.time() - t0)
                if i == 0:
                    tick = int(r.lua("rcon.print(game.tick)").strip())
                    while int(r.lua("rcon.print(game.tick)").strip()) < tick + 30 * 60:
                        time.sleep(0.5)
    print("\n".join(out))
    print(f"reads took {', '.join(f'{t:.2f}' for t in took)} s")
    shutil.rmtree(game, True)
    return 0 if max(took) < 5 and out[0].startswith("capital nauvis") else 1


#: check_vision's base around games/lab-sense (iron 310,420 20x24, gears 332,420 16x16): power
#: network A (an energy interface, poles, two assemblers, a laser turret, roboport A with robots
#: and a storage chest, a requester), a power switch left open to network B (an assembler with no
#: power), roboport B far east (its own logistic network), ghosts inside A's construction area
#: (robots fly) and two outside every construction area, two gun turrets (one empty), a wall with a
#: gate and a gap, land mines, a nest and a worm, pollution, a water line with a pump and a tank, a
#: crude line, and a chemical plant no pipe meets. Test setup, by Lua.
VISION_SETUP = """
local s, f = game.get_surface('lab'), game.forces['lab']
local function at(name, x, y, extra)
  local t = {name = name, position = {x, y}, force = f}
  for k, v in pairs(extra or {}) do t[k] = v end
  return s.create_entity(t)
end
local function wire(a, b, ida, idb)
  a.get_wire_connector(ida or defines.wire_connector_id.pole_copper, true).connect_to(
    b.get_wire_connector(idb or defines.wire_connector_id.pole_copper, true))
end
local eei = at('electric-energy-interface', 281, 461)
eei.power_production = 1000000
eei.electric_buffer_size = 10000000
local pa = {at('medium-electric-pole', 283.5, 461.5), at('medium-electric-pole', 290.5, 461.5),
            at('medium-electric-pole', 297.5, 461.5), at('medium-electric-pole', 283.5, 468.5),
            at('medium-electric-pole', 283.5, 475.5), at('medium-electric-pole', 290.5, 468.5)}
wire(pa[1], pa[2]) wire(pa[2], pa[3]) wire(pa[1], pa[4]) wire(pa[4], pa[5]) wire(pa[2], pa[6])
at('assembling-machine-2', 288.5, 465.5, {recipe = 'iron-gear-wheel'})
at('assembling-machine-2', 293.5, 465.5, {recipe = 'copper-cable'})
at('laser-turret', 291, 471)
local sw = at('power-switch', 301, 462)
local pb = at('medium-electric-pole', 307.5, 461.5)
wire(pa[3], sw, nil, defines.wire_connector_id.power_switch_left_copper)
wire(pb, sw, nil, defines.wire_connector_id.power_switch_right_copper)
sw.power_switch_state = false
at('assembling-machine-2', 310.5, 465.5, {recipe = 'electronic-circuit'})
local ra = at('roboport', 287, 477)
ra.insert{name = 'construction-robot', count = 10}
ra.insert{name = 'logistic-robot', count = 5}
local st = at('storage-chest', 293.5, 477.5)
st.insert{name = 'wooden-chest', count = 50}
st.insert{name = 'iron-plate', count = 200}
local rq = at('requester-chest', 309.5, 498.5)
rq.get_logistic_sections().get_section(1).set_slot(1, {value = 'iron-plate', min = 200})
for k = 0, 9 do at('entity-ghost', 330.5 + k, 497.5, {inner_name = 'wooden-chest'}) end
at('entity-ghost', 343.5, 492.5, {inner_name = 'wooden-chest'})
at('entity-ghost', 343.5, 493.5, {inner_name = 'wooden-chest'})
local rb = at('roboport', 400, 476)
rb.insert{name = 'construction-robot', count = 2}
local g1 = at('gun-turret', 360, 470)
g1.insert{name = 'firearm-magazine', count = 20}
at('gun-turret', 372, 470)
for x = 350, 390 do
  if x == 370 then at('gate', x + 0.5, 486.5, {direction = defines.direction.east})
  else at('stone-wall', x + 0.5, 486.5) end
end
for k = 0, 2 do at('land-mine', 355.5 + 2 * k, 495.5) end
s.create_entity{name = 'biter-spawner', position = {410, 440}, force = 'enemy'}
s.create_entity{name = 'small-worm-turret', position = {405, 455}, force = 'enemy'}
for x = 320, 327 do at('pipe', x + 0.5, 472.5).insert_fluid{name = 'water', amount = 50} end
at('pump', 329, 472.5, {direction = defines.direction.east})
for x = 330, 335 do at('pipe', x + 0.5, 472.5).insert_fluid{name = 'water', amount = 20} end
local tank = at('storage-tank', 317.5, 473.5)
tank.insert_fluid{name = 'water', amount = 8000}
for x = 320, 326 do at('pipe', x + 0.5, 477.5).insert_fluid{name = 'crude-oil', amount = 40} end
at('chemical-plant', 340.5, 476.5, {recipe = 'plastic-bar'})
game.map_settings.pollution.enabled = true
s.pollute({400, 430}, 200)
s.pollute({300, 470}, 50)
s.pollute({330, 430}, 800)
rcon.print('ok')
"""

#: check_vision's big base: per chunk of the area, nine assemblers, a belt row, inserters and
#: poles (about 60 entities a chunk), laid in batches of chunks.
VISION_BIG = """
local s, f = game.get_surface('lab'), game.forces['lab']
local n = 0
for cx = CX0, CX1 do for cy = CY0, CY1 do
  local x, y = cx * 32, cy * 32
  for i = 0, 2 do for j = 0, 2 do
    if s.create_entity{name = 'assembling-machine-2', position = {x + 2.5 + 4 * i, y + 2.5 + 4 * j}, force = f, recipe = 'iron-gear-wheel'} then n = n + 1 end
  end end
  for i = 0, 31 do
    if s.create_entity{name = 'transport-belt', position = {x + i + 0.5, y + 14.5}, direction = defines.direction.east, force = f} then n = n + 1 end
    if s.create_entity{name = 'transport-belt', position = {x + 20.5, y + i + 0.5}, direction = defines.direction.south, force = f} then n = n + 1 end
  end
  for i = 0, 8 do
    if s.create_entity{name = 'inserter', position = {x + 1.5 + i, y + 13.5}, force = f} then n = n + 1 end
  end
  for i = 0, 3 do
    if s.create_entity{name = 'medium-electric-pole', position = {x + 24.5, y + 0.5 + 8 * i}, force = f} then n = n + 1 end
  end
end end
rcon.print(n)
"""


def check_vision():
    """2.1 vision: a small base around games/lab-sense (VISION_SETUP) looked at with --layers
    all at zoom 1, 4 and 16, as text and as a PNG; then a big base (about 60k entities on 1024
    chunks) looked at zoom 16 and 32 over the whole of it, timed; then fair play on nauvis in play
    mode: a map look draws only the charted chunk. Everything goes to out/vision-check/."""
    import json
    from unittest import mock
    from fkcore import apply as applymod, look, vision
    from fkcore.catalog import Catalog
    cat = Catalog.load()
    out = os.path.join(ROOT, "out", "vision-check")
    game = os.path.join(out, "game")
    shutil.rmtree(game, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "games", "lab-sense"), game)
    play = os.path.join(out, "game-play")
    shutil.rmtree(play, ignore_errors=True)
    os.makedirs(play)
    with open(os.path.join(play, "nauvis.surface"), "w", encoding="utf-8") as fh:
        fh.write("surface  nauvis\nmode     play\nterrain  none\ncatalog  base\n")
    area = (270, 410, 420, 500)
    big = (1024, -512, 2048, 512)
    results, ok = {}, True

    def save(name, lines):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    with LaptopServer("vision", scenario="fk-play") as srv:
        with srv.rcon() as r:
            r.lua(link.lua_generate_area("lab", "lab", (area[0] - 64, area[1] - 64,
                                                        area[2] + 64, area[3] + 64)))
            sf, _lay, _p, s = look.composed(game, cat)
            rep = applymod.apply(r, s, cat, mode="lab", force="lab")
            print("\n".join(rep.lines()[:3]))
            print("setup:", r.lua(VISION_SETUP).strip())
            time.sleep(1)
            for z in (1, 4, 16):
                t0 = time.time()
                lk = look.run(r, game, cat, area, notify="off",
                              view=vision.View(z, vision.LAYERS))
                took = time.time() - t0
                lines = lk.lines()
                save(f"look-z{z}.txt", lines)
                png = os.path.join(out, f"look-z{z}.png")
                lki = look.run(r, game, cat, area, notify="off",
                               view=vision.View(z, vision.LAYERS, png))
                save(f"look-z{z}-image.txt", lki.lines())
                results[f"z{z}"] = (took, len(lines), png)
                print(f"zoom {z}: {len(lines)} lines in {took:.2f} s; {png}")
            cap = link.snapshot(r, "lab", area, "plain", keep=False)
            with mock.patch.object(link, "snapshot", lambda *_a, **_k: cap):
                plain = look.run(r, game, cat, area, notify="off")
                same = plain.lines() == look.run(r, game, cat, area, notify="off",
                                                 view=vision.View()).lines()
            save("look-plain.txt", plain.lines())
            print("zoom 1, no layers: the plain look", "OK" if same else "NOT the same")
            ok = ok and same
            # the big base
            r.lua(link.lua_generate_area("lab", "lab", big))
            laid, t0 = 0, time.time()
            cxs = list(range(big[0] // 32, big[2] // 32))
            for k in range(0, len(cxs), 2):
                lua = (VISION_BIG.replace("CX0", str(cxs[k])).replace("CX1", str(cxs[min(k + 1, len(cxs) - 1)]))
                       .replace("CY0", str(big[1] // 32)).replace("CY1", str(big[3] // 32 - 1)))
                laid += int(r.lua(lua).strip())
            print(f"big base: {laid} entities laid in {time.time() - t0:.1f} s")
            for z, layers in ((32, ()), (16, ()), (16, vision.LAYERS), (8, ())):
                t0 = time.time()
                lk = look.run(r, game, cat, big, notify="off",
                              view=vision.View(z, layers, os.path.join(
                                  out, f"big-z{z}{'-all' if layers else ''}.png")))
                took = time.time() - t0
                save(f"big-z{z}{'-all' if layers else ''}.txt", lk.lines())
                results[f"big z{z}{' all' if layers else ''}"] = (took, max(lk.calls), len(lk.calls))
                print(f"big base, zoom {z}{' layers all' if layers else ''}: {took:.2f} s, "
                      f"{len(lk.calls)} game calls, longest {max(lk.calls):.2f} s")
                ok = ok and max(lk.calls) < 5
            lk = look.run(r, game, cat, big, notify="off", view=vision.View(16))
            save("big-z16.txt", lk.lines())
            # fair play: nauvis in play mode, two chunks built and charted by nobody (a
            # headless server with no player charts nothing, even after force.chart)
            setup = """
local s, f = game.surfaces.nauvis, game.forces.player
s.request_to_generate_chunks({1040, 16}, 2)
s.force_generate_chunk_requests()
local tiles = {}
for x = 1024, 1087 do for y = 0, 31 do tiles[#tiles + 1] = {name = 'landfill', position = {x, y}} end end
s.set_tiles(tiles)
for _, e in pairs(s.find_entities_filtered{area = {{1024, 0}, {1088, 32}}}) do e.destroy() end
f.cancel_charting(s)
for _, c in pairs({{1032.5, 8.5}, {1064.5, 8.5}}) do
  s.create_entity{name = 'assembling-machine-2', position = c, force = f}
end
f.chart(s, {{1024, 0}, {1055, 31}})
rcon.print(tostring(f.is_chunk_charted(s, {32, 0})) .. ' ' .. tostring(f.is_chunk_charted(s, {33, 0})))
"""
            print("play setup (chunk 32,0 and 33,0 charted):", r.lua(setup).strip())
            time.sleep(1)
            pl = look.run(r, play, cat, (1024, 0, 1088, 32), notify="off",
                          view=vision.View(8, ("recipes", "power")))
            save("play-z8.txt", pl.lines())
            rows = [ln for ln in pl.lines() if ln[:5].strip().lstrip("-").isdigit()]
            print("\n".join(pl.lines()))
            fair = bool(rows) and all(r_[17:25] == "        " for r_ in rows) \
                and "recipes: no crafting machine here" in pl.lines()
            print("fair play (uncharted chunks are blank, their machines unread):",
                  "OK" if fair else "NOT")
            ok = ok and fair
    with open(os.path.join(out, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    print("vision:", "OK" if ok else "NOT as designed")
    return 0 if ok else 1


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "chat"
    raise SystemExit({"chat": check_chat, "own": check_own, "ghosts": check_ghosts,
                      "turned": check_turned, "health": check_health,
                      "settings": check_settings, "lab": check_lab,
                      "capital": check_capital, "vision": check_vision}[what]())
