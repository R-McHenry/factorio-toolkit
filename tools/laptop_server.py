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
    python tools/laptop_server.py settings  2.1: settings set by hand on what the toolkit placed are
                                            named, and the next apply writes them back in place
                                            (nothing ordered out) and cuts the hand's wire
    python tools/laptop_server.py defaults  2.1: the measurement: a design that sets nothing,
                                            pasted over entities set by hand (wired and not), as
                                            2.0.78's codec wrote it and as 2.1's does
    python tools/laptop_server.py robots    2.1 with robots: a robot-built pole's own wires cut by
                                            the wire pass, upgrades in place, a fresh lay, new
                                            settings written, a hand wire cut
    python tools/laptop_server.py capital SAVE.zip
                                            2.0.69: the working capital on a played map, two
                                            reads 30 game seconds apart
    python tools/laptop_server.py fixes     2.1.3: capture takes its own slot, the REACH read,
                                            fk request (robots bring the ammo), and the scaffold
                                            order (a moved roboport goes; none held without stock)
    python tools/laptop_server.py circuits  2.1 open circuits: a speaker and a display panel (Entity
                                            kinds and raw cb./bp. settings) warn when a chest's
                                            plates run low; the panel's 34-tile wire hops along
                                            poles, read back from the game; raw fields changed by
                                            hand are named by the diff
    python tools/laptop_server.py stats [SAVE.zip]
                                            2.1: run stats on a small base made here: the
                                            scenario's recorder writes a sample every 5 game
                                            minutes, the RCON read gives the same numbers, the
                                            research line's rate and its stall; with a save, the
                                            RCON path and the capital on that map
    python tools/laptop_server.py fluidports
                                            2.1: a Stack of acid drill cells on a copy of a
                                            uranium patch, acid in through a fluid port: acid
                                            in every drill, the ore rate against the model,
                                            the acid an ore takes
    python tools/laptop_server.py bobinserters
                                            3.0: Sea Block's adjustable inserters: robots build
                                            pasted and single ghosts with their vectors, a diff
                                            reads them back unchanged, a hand edit is named
    python tools/laptop_server.py machines
                                            3.0: a player adds a machine. With Space Age on,
                                            fk catalog learn foundry, then fk lab builds three
                                            stacked cells of a wrapped foundry: every net
                                            connected, molten iron in every foundry, the first
                                            one's gears/s against the model (6/s)
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
    def __init__(self, name, scenario=None, save=None, map_gen=None, boot_s=40, mods=None,
                 mod_dir=None):
        self.name, self.scenario, self.save, self.map_gen, self.boot_s = (name, scenario, save,
                                                                          map_gen, boot_s)
        # 3.0 (walker): the built-in mods to enable besides base ("space-age", "quality",
        # "elevated-rails"); None leaves the game's default, () turns them all off
        self.mods = mods
        # 3.0 (machines): a folder of unpacked mods (C:\fk-mods\sb-mods for Sea Block), all
        # enabled; each is linked (a junction) into the server's own mods folder, not copied
        self.mod_dir = mod_dir
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
        if self.mods is not None or self.mod_dir:
            mods_dir = os.path.join(self.write, "mods")
            os.makedirs(mods_dir, exist_ok=True)
            names = ["base", "space-age", "quality", "elevated-rails"]
            on = set(self.mods or ())
            for d in sorted(os.listdir(self.mod_dir)) if self.mod_dir else ():
                src = os.path.join(self.mod_dir, d)
                if os.path.isdir(src):
                    import _winapi
                    _winapi.CreateJunction(src, os.path.join(mods_dir, d))
                    n = d.rsplit("_", 1)[0]
                    names.append(n)
                    on.add(n)
            with open(os.path.join(mods_dir, "mod-list.json"), "w", encoding="utf-8") as fh:
                fh.write('{"mods": [' + ", ".join(
                    f'{{"name": "{n}", "enabled": {"true" if n == "base" or n in on else "false"}}}'
                    for n in names) + "]}")

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


#: check_settings' design: a condition, a filter, a reading on a wire, a request, a slot limit,
#: a storage chest's filter and a constant combinator
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
e m/c2 storage-chest 10.5,2.5
e m/k0 constant-combinator 10.5,0.5 signals=signal-A:5
w w red m/m0 m/i2
"""


def check_settings():
    """2.0.12, and settings changed in place (2.1): the design SET is pasted under play rules and
    built (revived); a diff then finds nothing. Then, by Lua, as a player would: i0's logistic
    condition, a red wire from i3 to i1 and a condition on i3 (which the design leaves unset), c0's
    request, m0's recipe, c1's limit, a filter on the storage chest c2 and k0's signal. The diff
    names each, so do the apply's hand edits. The apply orders nothing out: the paste writes every
    setting back in place and the wire pass cuts the hand's wire; a diff after it finds nothing."""
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
local i3 = at('inserter', 16.5, 0.5)
i3.get_wire_connector(defines.wire_connector_id.circuit_red, true).connect_to(
  at('inserter', 14.5, 1.5).get_wire_connector(defines.wire_connector_id.circuit_red, true))
local c3 = i3.get_or_create_control_behavior()
c3.circuit_enable_disable = true
c3.circuit_condition = {first_signal = {type = 'item', name = 'coal'}, comparator = '>', constant = 1}
at('requester-chest', 18.5, 0.5).get_logistic_sections().get_section(1).set_slot(1, {value = 'copper-plate', min = 5})
at('assembling-machine-2', 11.5, 1.5).set_recipe('copper-cable')
at('wooden-chest', 18.5, 2.5).get_inventory(defines.inventory.chest).set_bar(6)
at('storage-chest', 20.5, 2.5).storage_filter = {name = 'coal', quality = 'normal'}
at('constant-combinator', 20.5, 0.5).get_control_behavior().get_section(1).set_slot(1, {value = {type = 'virtual', name = 'signal-B', quality = 'normal'}, min = 9})
rcon.print('ok')"""
    after = """
local s = game.get_surface('lab')
local function at(n, x, y) return s.find_entity(n, {x, y}) end
local c = at('inserter', 14.5, 0.5).get_control_behavior().logistic_condition
local sl = at('requester-chest', 18.5, 0.5).get_logistic_sections().get_section(1).get_slot(1)
local i3 = at('inserter', 16.5, 0.5)
local w = i3.get_wire_connector(defines.wire_connector_id.circuit_red, true).connection_count
local c3 = i3.get_control_behavior()
local bar = at('wooden-chest', 18.5, 2.5).get_inventory(defines.inventory.chest).get_bar()
local rc = at('assembling-machine-2', 11.5, 1.5).get_recipe()
local sf = at('storage-chest', 20.5, 2.5).storage_filter
local k = at('constant-combinator', 20.5, 0.5).get_control_behavior().get_section(1).get_slot(1)
local n = s.count_entities_filtered{area = {{8, -2}, {24, 8}}, type = 'entity-ghost'}
local dc = s.count_entities_filtered{area = {{8, -2}, {24, 8}}, to_be_deconstructed = true}
rcon.print(c.first_signal.name .. c.comparator .. c.constant .. ' ' .. tostring(sl.value and sl.value.name)
  .. ' ' .. w .. ' ' .. tostring(c3 and c3.circuit_enable_disable) .. ' ' .. bar .. ' '
  .. tostring(rc and rc.name) .. ' ' .. tostring(sf and sf.name and sf.name.name) .. ' '
  .. tostring(k.value and k.value.name) .. ':' .. tostring(k.min) .. ' ghosts=' .. n .. ' decon=' .. dc)"""
    with LaptopServer("settings", scenario="fk-play") as srv:
        with srv.rcon() as r:
            r.lua(link.lua_generate_area(s, f, (-32, -32, 64, 64)))
            rep = applymod.apply(r, composed, cat, area=area, mode="play", force=f, policy=watch)
            r.lua(link.lua_revive(s, area))
            clean = applymod.diff(r, composed, cat, area, watch, force=f)
            print("tweaks:", r.lua(tweak).strip())
            seen = applymod.diff(r, composed, cat, area, watch, force=f)
            rep = applymod.apply(r, composed, cat, area=area, mode="play", force=f, policy=watch,
                                 own=rep.own)
            back = r.lua(after).strip()
            again = applymod.diff(r, composed, cat, area, watch, force=f)
    print(f"untouched: {len(clean.settings)} differences {clean.settings_error or ''}")
    for d in clean.settings:
        print("   ", d.line())
    print("after the tweaks:")
    for d in seen.settings:
        print("   ", d.line())
    print("\n".join(rep.lines()))
    print("after the paste (i0's condition, c0's request, red wires on i3, i3's condition on, c1's "
          "bar, m0's recipe, c2's filter, k0's signal, ghosts, ordered out):", back)
    print(f"a diff after it: {len(again.settings)} differences "
          f"{[d.line() for d in again.settings]}")
    keys = sorted({d.key.split("/")[-1] for d in seen.settings})
    ok = (not clean.settings and not clean.settings_error
          and keys == ["c0", "c1", "c2", "i0", "i1", "i3", "k0", "m0"]
          and len(rep.hand) >= 8 and not rep.resettled and rep.decon == 0
          and back == "iron-plate<50 iron-plate 0 false 3 iron-gear-wheel nil signal-A:5 ghosts=0 "
                      "decon=0"
          and rep.wires is not None and rep.wires.cut == 1 and not again.settings)
    print("settings changed in place:", "OK" if ok else "NOT as designed")
    return 0 if ok else 1


#: check_defaults: entities with settings set by hand: (name, direction, Lua on ``e``, recipe)
_HAND = [
    ("inserter", 4, """local cb = e.get_or_create_control_behavior()
cb.circuit_enable_disable = true
cb.circuit_condition = {first_signal = {type = 'item', name = 'iron-plate'}, comparator = '<', constant = 5}
cb.connect_to_logistic_network = true
cb.logistic_condition = {first_signal = {type = 'item', name = 'iron-plate'}, comparator = '<', constant = 5}
cb.circuit_read_hand_contents = true""", None),
    ("fast-inserter", 4, """local cb = e.get_or_create_control_behavior()
cb.circuit_enable_disable = true
cb.circuit_condition = {first_signal = {type = 'item', name = 'iron-plate'}, comparator = '<', constant = 5}
e.use_filters = true
e.set_filter(1, {name = 'iron-plate'})
e.inserter_filter_mode = 'blacklist'""", None),
    ("assembling-machine-2", None, """e.set_recipe('iron-gear-wheel')
local cb = e.get_or_create_control_behavior()
cb.circuit_enable_disable = true
cb.circuit_condition = {first_signal = {type = 'item', name = 'iron-plate'}, comparator = '<', constant = 5}
cb.circuit_read_contents = true""", "iron-gear-wheel"),
    ("transport-belt", 4, """local cb = e.get_or_create_control_behavior()
cb.circuit_enable_disable = true
cb.circuit_condition = {first_signal = {type = 'item', name = 'iron-plate'}, comparator = '<', constant = 5}
cb.read_contents = true""", None),
    ("electric-furnace", None, """local cb = e.get_or_create_control_behavior()
cb.circuit_enable_disable = true
cb.circuit_condition = {first_signal = {type = 'item', name = 'iron-plate'}, comparator = '<', constant = 5}""", None),
    ("pump", 0, """local cb = e.get_or_create_control_behavior()
cb.circuit_enable_disable = true
cb.circuit_condition = {first_signal = {type = 'item', name = 'iron-plate'}, comparator = '<', constant = 5}""", None),
    ("small-lamp", None, """local cb = e.get_or_create_control_behavior()
cb.circuit_enable_disable = true
cb.circuit_condition = {first_signal = {type = 'item', name = 'iron-plate'}, comparator = '<', constant = 5}""", None),
    ("requester-chest", None, """local sec = e.get_logistic_sections().get_section(1)
sec.set_slot(1, {value = 'iron-plate', min = 10})
e.get_requester_point().trash_not_requested = true
e.request_from_buffers = true
e.get_inventory(defines.inventory.chest).set_bar(5)""", None),
    ("storage-chest", None, """e.storage_filter = {name = 'iron-plate', quality = 'normal'}
e.get_inventory(defines.inventory.chest).set_bar(5)""", None),
    ("wooden-chest", None, "e.get_inventory(defines.inventory.chest).set_bar(3)", None),
    ("constant-combinator", 0, """local cb = e.get_or_create_control_behavior()
cb.enabled = false
cb.get_section(1).set_slot(1, {value = {type = 'virtual', name = 'signal-A', quality = 'normal'}, min = 5})""", None),
    ("decider-combinator", 0, """e.get_or_create_control_behavior().parameters = {
  conditions = {{first_signal = {type = 'virtual', name = 'signal-A'}, comparator = '>', constant = 3}},
  outputs = {{signal = {type = 'virtual', name = 'signal-B'}, copy_count_from_input = false}}}""", None),
    ("electric-mining-drill", 0, """local cb = e.get_or_create_control_behavior()
cb.circuit_enable_disable = true
cb.circuit_condition = {first_signal = {type = 'item', name = 'iron-plate'}, comparator = '<', constant = 5}""", None),
]


def check_defaults():
    """2.1, the measurement behind settings changed in place: each entity of ``_HAND`` stands with
    settings set by hand, once unwired and once with a red wire to a pole; then a design that sets
    nothing on it (but an assembler's recipe) is pasted over it as the codec writes it, once as
    2.0.78 wrote it (no control behaviour) and once as 2.1 does (``codec.RESET_CB`` on a
    machine), and the game's own export is read back (``fkcore.settings``). The design's own
    fields back (nothing set, but the recipe) mean the paste set the whole state; a drill takes
    nothing from a paste, so the apply lays it fresh."""
    import json
    from fkcore import apply as applymod, codec, settings
    from fkcore.catalog import Catalog
    cat, s, f = Catalog.load(), "lab", "lab"
    place = """
local s = game.get_surface('lab')
local e = s.create_entity{name = __N__, position = {__X__, __Y__}, force = 'lab', direction = __D__}
__LUA__
if __WIRED__ then
  local p = s.create_entity{name = 'medium-electric-pole', position = {e.position.x, e.position.y + 4.5}, force = 'lab'}
  e.get_wire_connector(defines.wire_connector_id.circuit_red, true).connect_to(p.get_wire_connector(defines.wire_connector_id.circuit_red, true))
end
rcon.print('ok')"""
    rows = {"2.0.78": [], "2.1": []}
    spots = []
    for k, (name, d, lua, recipe) in enumerate(_HAND):
        for v, version in enumerate(("2.0.78", "2.1")):
            for wired in (False, True):
                x, y = 2.5 + 10 * k, 2.5 + 12 * (2 * v + wired)
                if name in ("pump", "decider-combinator"):        # 1x2: centred on a tile edge
                    y += 0.5
                spots.append((name, d, lua, wired, version, x, y))
                rows[version].append({"src": f"d/{name}-{int(wired)}", "name": name, "x": x, "y": y,
                                      "direction": d,
                                      "attrs": {"recipe": recipe} if recipe else {}})
    bad = 0
    with LaptopServer("settings-defaults", scenario="fk-play") as srv:
        with srv.rcon() as r:
            r.lua(link.lua_generate_area(s, f, (-32, -32, 160, 64)))
            for name, d, lua, wired, _version, x, y in spots:
                got = r.lua(place.replace("__N__", json.dumps(name)).replace("__X__", str(x))
                            .replace("__Y__", str(y)).replace("__D__", "nil" if d is None else str(d))
                            .replace("__LUA__", lua).replace("__WIRED__", str(wired).lower()))
                if got.strip() != "ok":
                    print(f"  {name}: not set up: {got.strip()}")
            before = settings.read(r, s, f, (0, 0, 140, 48), "defaults-before")
            for version, part in rows.items():
                bp = codec.blueprint(part)
                if version == "2.0.78":     # the codec as it was: no reset control behaviour
                    bp = _strip_reset(bp)
                link.paste(r, s, f, bp, applymod._anchor(part, cat))
            after = settings.read(r, s, f, (0, 0, 140, 48), "defaults-after")
    print(f"{'entity':<22} {'wired':<6} {'set by hand':<52} {'2.0.78 paste':<22} 2.1 paste")
    by = {}
    design = {settings._at(row["name"], row["x"], row["y"]): settings._fields(codec.entity_json(row, 1))
              for part in rows.values() for row in part}
    for name, _d, _lua, wired, version, x, y in spots:
        at = settings._at(name, x, y)
        by.setdefault((name, wired), {})[version] = (before.get(at, ({}, set()))[0],
                                                     after.get(at, ({}, set()))[0], design[at])
    for (name, wired), got in by.items():
        hand = settings.describe(got["2.1"][0]) or "?"
        old = settings.describe(got["2.0.78"][1]) or "nothing set"
        new = settings.describe(got["2.1"][1]) or "nothing set"
        skip = codec.entity_type(name) in codec.PASTE_SKIPS
        ok = (got["2.1"][1] == got["2.1"][2]) != skip
        bad += not ok
        print(f"{name:<22} {str(wired):<6} {hand[:52]:<52} {old[:22]:<22} {new}"
              f"{'' if ok else '  NOT as designed'}{'  (laid fresh by the apply)' if skip else ''}")
    if os.environ.get("FK_RAW"):
        for name, _d, _lua, wired, version, x, y in spots:
            print("RAW", version, name, wired, after.get(settings._at(name, x, y)))
    print("a paste of the design's defaults sets the whole state:", "OK" if not bad else "NOT")
    return 0 if not bad else 1


def _strip_reset(bp):
    """The blueprint ``bp`` without ``codec.RESET_CB``: what 2.0.78's codec pasted."""
    import base64
    import json
    import zlib
    from fkcore import codec
    doc = json.loads(zlib.decompress(base64.b64decode(bp[1:])))
    for e in doc["blueprint"]["entities"]:
        if codec.is_reset(e.get("control_behavior")):
            del e["control_behavior"]
    return "0" + base64.b64encode(zlib.compress(json.dumps(doc).encode(), 9)).decode()


#: check_robots: the design before (v1) and after (v2): v2 upgrades i0, c0, m0, b0 and b1 in
#: place, lays i2 fresh (a long-handed inserter is in no inserter's fast-replace group), and sets
#: a condition on i1; three poles stand in each other's reach (two wires in the design)
ROBOTS_V1 = """\
fkp 1 factory rb
size 20x12
wire w red
w w red box/c0 ~n/i0
e power/p0 small-electric-pole 2.5,2.5
e power/p1 small-electric-pole 7.5,2.5
e power/p2 small-electric-pole 5.5,6.5
e box/c0 wooden-chest 10.5,2.5
e ~n/i0 inserter 11.5,2.5 E net=n if=iron-plate<5
e ~n/i1 inserter 11.5,4.5 E net=n
e m/m0 assembling-machine-1 14.5,3.5 recipe=iron-gear-wheel
e ~b/b0 transport-belt 10.5,7.5 E net=b
e ~b/b1 transport-belt 11.5,7.5 E net=b
e ~n/i2 inserter 13.5,7.5 E net=n
"""
ROBOTS_V2 = (ROBOTS_V1.replace("box/c0 wooden-chest", "box/c0 iron-chest")
             .replace("~n/i0 inserter", "~n/i0 fast-inserter")
             .replace("~n/i1 inserter 11.5,4.5 E net=n", "~n/i1 inserter 11.5,4.5 E net=n if=copper-plate>3")
             .replace("assembling-machine-1", "assembling-machine-2")
             .replace("transport-belt", "fast-transport-belt")
             .replace("~n/i2 inserter", "~n/i2 long-handed-inserter"))
_ROBOT_BASE = """
local s, f = game.get_surface('lab'), game.forces['lab']
local eei = s.create_entity{name = 'electric-energy-interface', position = {-20, -20}, force = f}
eei.electric_buffer_size = 1e12
eei.power_production = 1e9
eei.energy = 1e12
s.create_entity{name = 'substation', position = {-17, -20}, force = f}
s.create_entity{name = 'substation', position = {-17, -4}, force = f}
local rp = s.create_entity{name = 'roboport', position = {-12, -10}, force = f}
rp.insert{name = 'construction-robot', count = 30}
local st = s.create_entity{name = 'storage-chest', position = {-8.5, -12.5}, force = f}
for _, n in pairs({'small-electric-pole', 'wooden-chest', 'iron-chest', 'inserter', 'fast-inserter',
    'long-handed-inserter', 'assembling-machine-1', 'assembling-machine-2', 'transport-belt',
    'fast-transport-belt'}) do st.insert{name = n, count = 20} end
-- a pole of the world's own, not the design's, in reach of p0 and p2
s.create_entity{name = 'small-electric-pole', position = {1.5, 8.5}, force = f}
rcon.print('ok')"""


def _robots_wait(r, area, limit=120):
    """Run the game fast until no ghost, no upgrade and no decon order is left in ``area``."""
    a = f"{{{{{area[0]}, {area[1]}}}, {{{area[2]}, {area[3]}}}}}"
    left = (f"local s = game.get_surface('lab') rcon.print("
            f"s.count_entities_filtered{{area = {a}, type = 'entity-ghost'}} + "
            f"s.count_entities_filtered{{area = {a}, to_be_upgraded = true}} + "
            f"s.count_entities_filtered{{area = {a}, to_be_deconstructed = true}})")
    t0, tick0 = time.time(), int(r.lua("game.speed = 16 rcon.print(game.tick)").strip())
    n = int(r.lua(left).strip())
    while n and time.time() - t0 < limit:
        time.sleep(1)
        n = int(r.lua(left).strip())
    tick = int(r.lua("game.speed = 1 rcon.print(game.tick)").strip())
    return n, (tick - tick0) / 60


def check_robots():
    """2.1 in play mode with robots. A roboport on the lab surface builds plot rb (v1), then plot
    pb, applied on its own: its blueprint holds only pb's two poles, and a robot-built pole joins
    itself to the standing poles in its reach, rb's among them, while the design wires the two
    plots once. The wire pass after the build cuts what the design doesn't have (keeping two
    power domains apart will rest on this) and leaves the world's own pole alone. Then 30 plates
    go in the chest and a hand wire joins i1 to pole p1, and v2 is applied: robots swap five
    entities in place (settings, wires and contents stay), lay the long-handed inserter fresh,
    and the paste writes i1's new condition; the wire pass cuts the hand wire. A diff after the
    robots finds everything as designed."""
    import json
    from fkcore import apply as applymod, compose, fkp, wires as wiresmod
    from fkcore.catalog import Catalog
    cat, s, f = Catalog.load(), "lab", "lab"
    watch = {"plots": "keep", "sanctioned": "mark 2h", "notify": "off"}
    plots = ("fkp 1 surface lab\nplot rb at 0,0 rot 0 size 20x12\n"
             "plot pb at 0,12 rot 0 size 20x4\n")
    pb = ("fkp 1 factory pb\nsize 20x4\ne power/q0 small-electric-pole 4.5,0.5\n"
          "e power/q1 small-electric-pole 8.5,0.5\n")

    def composed(text):
        return compose.compose(fkp.loads(plots), {"rb": fkp.loads(text), "pb": fkp.loads(pb)}, cat)
    v1, v2 = composed(ROBOTS_V1), composed(ROBOTS_V2)
    area = (-2, -2, 22, 18)
    poles = """
local s = game.get_surface('lab')
local p = {}
for _, e in pairs(s.find_entities_filtered{area = {{0, 0}, {12, 16}}, name = 'small-electric-pole'}) do
  local w = {}
  for _, c in pairs(e.get_wire_connector(defines.wire_connector_id.pole_copper, true).connections) do
    local o = c.target.owner.position
    w[#w + 1] = o.x .. ',' .. o.y
  end
  table.sort(w)
  p[#p + 1] = e.position.x .. ',' .. e.position.y .. '-' .. table.concat(w, '/')
end
table.sort(p)
rcon.print(table.concat(p, ' '))"""
    read = """
local s = game.get_surface('lab')
local function one(x, y)
  for _, e in pairs(s.find_entities_filtered{position = {x, y}, radius = 0.3}) do
    if e.type ~= 'entity-ghost' and e.type ~= 'electric-pole' then return e end
  end
end
local o = {}
local i0 = one(11.5, 2.5)
local c = i0.get_control_behavior().circuit_condition
o.i0 = i0.name .. ' ' .. c.first_signal.name .. c.comparator .. c.constant .. ' red=' ..
  i0.get_wire_connector(defines.wire_connector_id.circuit_red, true).connection_count
local c0 = one(10.5, 2.5)
o.c0 = c0.name .. ' ' .. c0.get_item_count('iron-plate')
local m0 = one(14.5, 3.5)
o.m0 = m0.name .. ' ' .. tostring(m0.get_recipe() and m0.get_recipe().name)
o.b = one(10.5, 7.5).name .. ',' .. one(11.5, 7.5).name
local i1 = one(11.5, 4.5)
local c1 = i1.get_control_behavior()
o.i1 = i1.name .. ' ' .. (c1 and c1.circuit_enable_disable and c1.circuit_condition.first_signal.name or 'off')
  .. ' red=' .. i1.get_wire_connector(defines.wire_connector_id.circuit_red, true).connection_count
o.i2 = one(13.5, 7.5).name
rcon.print(helpers.table_to_json(o))"""
    with LaptopServer("robots", scenario="fk-play") as srv:
        with srv.rcon() as r:
            r.lua(link.lua_generate_area(s, f, (-64, -64, 64, 64)))
            print("base:", r.lua(_ROBOT_BASE).strip())
            rep1 = applymod.apply(r, v1, cat, mode="play", force=f, policy=watch,
                                  keys=["lab:rb/"])
            print("\n".join(rep1.lines()))
            left, secs = _robots_wait(r, area)
            print(f"robots built rb: {left} left after {secs:.0f} game s")
            print("poles (x,y-wired to), the world's own at 1.5,8.5:", r.lua(poles).strip())
            pass0 = wiresmod.run(r, v1, cat, rep1.area)
            print("the wire pass after rb's build:", pass0.line())
            rep1b = applymod.apply(r, v1, cat, mode="play", force=f, policy=watch,
                                   keys=["lab:pb/"], own=rep1.own)
            print("\n".join(rep1b.lines()))
            left1, secs1 = _robots_wait(r, area)
            print(f"robots built pb: {left1} left after {secs1:.0f} game s")
            joined = r.lua(poles).strip()
            print("poles as robots built pb:", joined)
            pass1 = wiresmod.run(r, v1, cat, rep1b.area)
            print("the wire pass after pb's build (as fk wait built runs it):", pass1.line())
            cut1 = r.lua(poles).strip()
            print("poles after it:", cut1)
            r.lua("local s = game.get_surface('lab') "
                  "s.find_entity('wooden-chest', {10.5, 2.5}).insert{name = 'iron-plate', count = 30} "
                  "s.find_entity('inserter', {11.5, 4.5}).get_wire_connector(defines.wire_connector_id.circuit_red, true)"
                  ".connect_to(s.find_entity('small-electric-pole', {7.5, 2.5}).get_wire_connector(defines.wire_connector_id.circuit_red, true)) "
                  "rcon.print('ok')")
            rep2 = applymod.apply(r, v2, cat, mode="play", force=f, policy=watch, own=rep1b.own)
            print("\n".join(rep2.lines()))
            left2, secs2 = _robots_wait(r, area)
            print(f"robots did v2: {left2} left after {secs2:.0f} game s")
            got = json.loads(r.lua(read).strip())
            print("after v2:", json.dumps(got, sort_keys=True))
            pass2 = wiresmod.run(r, v2, cat, area)
            print("the wire pass after it:", pass2.line(), "; poles:", r.lua(poles).strip())
            final = applymod.diff(r, v2, cat, area, watch, force=f, own=rep2.own)
            verdicts = {}
            for v in final.verdicts:
                verdicts[v.verdict] = verdicts.get(v.verdict, 0) + 1
            print("a diff after it:", verdicts, [d.line() for d in final.settings])
    ups = sorted(k.split("/")[-1] for k, _o, _n in rep2.upgraded)
    ok = (left == 0 and left1 == 0 and left2 == 0 and pass0.line() is None
          and pass1.cut >= 1 and pass1.error is None and "1.5,8.5" in cut1
          and ups == ["b0", "b1", "c0", "i0", "m0"]
          and [k.split("/")[-1] for k, _w in rep2.written] == ["i1"]
          and any(k.endswith("/i2") for k, _w in rep2.fresh)
          and rep2.wires.cut == 1 and pass2.line() is None
          and got["i0"] == "fast-inserter iron-plate<5 red=1"
          and got["c0"] == "iron-chest 30" and got["m0"] == "assembling-machine-2 iron-gear-wheel"
          and got["b"] == "fast-transport-belt,fast-transport-belt"
          and got["i1"] == "inserter copper-plate red=0" and got["i2"] == "long-handed-inserter"
          and not final.settings and verdicts.get("ok") == len(v2.entities))
    print("settings, upgrades and wires with robots:", "OK" if ok else "NOT as designed")
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


def check_fixes():
    """2.1.3, the fixes from the runs, in the game:

    - capture: a slot's blueprint takes only what stands in it (a drill of the next slot whose box
      reaches over the edge stays out);
    - REACH: the read of the roboports that stand with power, and what it leaves out of reach;
    - fk request: an item-request proxy, and robots bring the ammo into the turret; what the
      network doesn't hold is said;
    - scaffold: a roboport the design moved is ordered out, and so is an old one when the
      network holds no roboport for the design's; with stock, an old one is held as before."""
    import json as jsonmod
    from fkcore import apply as applymod, capture, compose, fkp, link as linkmod, robots
    from fkcore.catalog import Catalog
    cat, s, f = Catalog.load(), "lab", "lab"
    watch = {"plots": "revert", "sanctioned": "revert", "notify": "off"}
    results = {}

    def make(r, name, x, y, **kw):
        extra = "".join(f", {k} = {v}" for k, v in kw.items())
        return r.lua(f"local e = game.get_surface('{s}').create_entity{{name = '{name}', "
                     f"position = {{{x}, {y}}}, force = '{f}'{extra}}} "
                     "rcon.print(e and 'ok' or 'no')").strip()

    def at(r, name, x, y):
        return r.lua(f"local o = {{}} for _, e in pairs(game.get_surface('{s}').find_entities_filtered"
                     f"{{position = {{{x}, {y}}}, radius = 0.3}}) do if e.name == '{name}' or "
                     f"(e.type == 'entity-ghost' and e.ghost_name == '{name}') then o[#o + 1] = "
                     "(e.type == 'entity-ghost' and 'ghost' or 'built') .. "
                     "(e.to_be_deconstructed() and '(decon)' or '') end end "
                     "rcon.print(table.concat(o, ' '))").strip()

    def design(plot, x, y, w, h, text):
        return compose.compose(fkp.loads(f"fkp 1 surface lab\nplot {plot} at {x},{y} rot 0 size "
                                         f"{w}x{h}\n"),
                               {plot: fkp.loads(f"fkp 1 factory {plot}\nsize {w}x{h}\n"
                                                "cover robots robots roboport=roboport\n" + text)},
                               cat)

    with LaptopServer("fixes", scenario="fk-play") as srv:
        with srv.rcon() as r:
            r.lua(linkmod.lua_generate_area(s, f, (-32, -32, 400, 64)))
            # -- capture: slot (0,0)-(20,20); a drill of the next slot at 20.5 reaches over the edge
            make(r, "wooden-chest", 5.5, 5.5)
            make(r, "electric-mining-drill", 20.5, 10.5)
            got = capture.from_game(r, s, f, (0, 0, 20, 20))
            results["capture takes its own slot only"] = (got.get("names"), {"wooden-chest": 1})

            # -- a network with stock, power and robots (setup only), x 300..330
            make(r, "roboport", 318, 10)
            make(r, "small-electric-pole", 321.5, 12.5)
            r.lua(f"local e = game.get_surface('{s}').create_entity{{name = 'electric-energy-"
                  f"interface', position = {{323, 12}}, force = '{f}'}} e.power_production = "
                  "2000000 e.electric_buffer_size = 2000000 rcon.print(1)")
            make(r, "storage-chest", 325.5, 10.5)
            r.lua(f"local s = game.get_surface('{s}') "
                  "local c = s.find_entity('storage-chest', {325.5, 10.5}) "
                  "c.insert{name = 'piercing-rounds-magazine', count = 20} "
                  "c.insert{name = 'roboport', count = 5} "
                  "s.find_entity('roboport', {318, 10}).insert{name = 'construction-robot', "
                  "count = 10} rcon.print(1)")
            make(r, "gun-turret", 331, 17)
            time.sleep(2)
            # -- REACH: the read of what stands with power
            tag = f"fixes-ports-{os.getpid()}"
            ports = linkmod.read_output(r, robots.lua_roboports(s, f, tag), tag, "roboports")
            ports = [tuple(p) for p in (ports if isinstance(ports, list) else [])]
            results["roboports read"] = (ports, [(318, 10, 25, 55)])
            rows = [("in", "wooden-chest", 360.5, 10.5), ("out", "wooden-chest", 380.5, 10.5),
                    ("far", "wooden-chest", 410.5, 10.5)]
            results["REACH alone"] = (sorted(row[0] for row in robots.reach(rows, ports, cat)),
                                      ["far", "out"])
            rows.append(("hop", "roboport", 362, 10))
            results["REACH with the paste's roboport"] = (
                [row[0] for row in robots.reach(rows, ports, cat)], [])

            # -- fk request
            def request(pos, item, n, **kw):
                return jsonmod.loads(r.lua(linkmod.lua_request(s, f, pos, item, n, **kw)).strip())
            got = request((331, 17), "piercing-rounds-magazine", 10)
            results["request asks"] = ((got.get("ok"), got.get("asked"), got.get("stock"),
                                       got.get("reach")), (True, 10, 20, True))
            short = request((331, 17), "firearm-magazine", 5)
            results["request says the network is short"] = ((short.get("asked"),
                                                            short.get("stock")), (5, 0))
            proxy = r.lua(f"local p = game.get_surface('{s}').find_entities_filtered{{type = "
                          "'item-request-proxy', position = {331, 17}}[1] rcon.print(p and "
                          "#p.insert_plan or 0)").strip()
            results["one proxy, both requests"] = (proxy, "2")
            t0, ammo = time.time(), "0"
            while time.time() - t0 < 40:
                ammo = r.lua(f"rcon.print(game.get_surface('{s}').find_entity('gun-turret', "
                             "{331, 17}).get_inventory(defines.inventory.turret_ammo)"
                             ".get_item_count('piercing-rounds-magazine'))").strip()
                if ammo == "10":
                    break
                time.sleep(1)
            results["robots bring the ammo"] = (ammo, "10")
            nothing = r.lua(linkmod.lua_request(s, f, (200.5, 40.5), "coal", 5)).strip()
            results["request on empty ground"] = (jsonmod.loads(nothing).get("ok"), False)

            # -- scaffold, no stock: plot sa at 200,0 (40x20)
            v1 = "e robots/r0 roboport 6,6\n"
            area = (200, 0, 240, 20)
            rep = applymod.apply(r, design("sa", 200, 0, 40, 20, v1), cat, area, mode="play",
                                 force=f, policy=watch)
            r.lua(linkmod.lua_revive(s, area))
            make(r, "roboport", 230, 14)              # an old roboport, not the toolkit's
            v2 = "e robots/r0 roboport 18,6\n"
            rep = applymod.apply(r, design("sa", 200, 0, 40, 20, v2), cat, area, mode="play",
                                 force=f, policy=watch, own=rep.own)
            results["moved roboport ordered out"] = (at(r, "roboport", 206, 6), "built(decon)")
            results["old roboport, no stock: ordered out"] = (at(r, "roboport", 230, 14),
                                                              "built(decon)")
            results["the new one laid"] = (at(r, "roboport", 218, 6), "ghost")
            results["report says why"] = (sorted(rep.released), sorted([applymod.MOVED_OUT,
                                                                        applymod.STOCK_OUT]))
            sa_lines = rep.lines()

            # -- scaffold with stock: plot sb at 300,0 (20x20); the network holds 5 roboports
            area = (300, 0, 320, 20)
            rep = applymod.apply(r, design("sb", 300, 0, 20, 20, "e robots/r0 roboport 6,6\n"),
                                 cat, area, mode="play", force=f, policy=watch)
            results["with stock, the old one is held"] = (at(r, "roboport", 318, 10), "built")
            results["held"] = (rep.held, 1)
    bad = 0
    print("\n".join(sa_lines))
    for k, (got, want) in results.items():
        ok = got == want
        bad += not ok
        print(f"{k:<40} {got!s:<50} {'OK' if ok else 'NOT ' + repr(want)}")
    return 1 if bad else 0


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


#: check_stats' base: power from an energy interface and solar panels (always day), an accumulator,
#: two assemblers (one with plates, one without), an electric furnace with ore, two labs (one with
#: red packs) on a queue of red techs, and a second network of its own (a panel and a lamp)
STATS_SETUP = """
local s, f = game.surfaces.nauvis, game.forces.player
s.always_day = true
s.request_to_generate_chunks({0, 0}, 3)
s.force_generate_chunk_requests()
local tiles = {}
for x = -10, 45 do for y = -10, 20 do tiles[#tiles + 1] = {name = 'landfill', position = {x, y}} end end
s.set_tiles(tiles)
for _, e in pairs(s.find_entities_filtered{area = {{-10, -10}, {45, 20}}}) do
  if e.valid and e.type ~= 'character' then e.destroy() end
end
local eei = s.create_entity{name = 'electric-energy-interface', position = {1, 1}, force = f}
eei.power_production = 3000000 / 60
eei.electric_buffer_size = 3000000
s.create_entity{name = 'solar-panel', position = {4.5, 1.5}, force = f}
s.create_entity{name = 'accumulator', position = {8, 1}, force = f}
local a1 = s.create_entity{name = 'assembling-machine-2', position = {11.5, 1.5}, force = f}
a1.set_recipe('iron-gear-wheel')
a1.insert{name = 'iron-plate', count = 400}
local a2 = s.create_entity{name = 'assembling-machine-2', position = {15.5, 1.5}, force = f}
a2.set_recipe('iron-gear-wheel')
local l1 = s.create_entity{name = 'lab', position = {19.5, 1.5}, force = f}
l1.insert{name = 'automation-science-pack', count = 400}
s.create_entity{name = 'lab', position = {23.5, 1.5}, force = f}
local fu = s.create_entity{name = 'electric-furnace', position = {27.5, 1.5}, force = f}
fu.insert{name = 'iron-ore', count = 20}
for _, x in pairs{2.5, 9.5, 16.5, 23.5, 28.5} do
  s.create_entity{name = 'medium-electric-pole', position = {x, -1.5}, force = f}
end
s.create_entity{name = 'solar-panel', position = {38.5, 10.5}, force = f}
s.create_entity{name = 'small-lamp', position = {40.5, 12.5}, force = f}
s.create_entity{name = 'medium-electric-pole', position = {40.5, 10.5}, force = f}
for _, t in pairs{'steam-power', 'electronics', 'automation-science-pack'} do
  f.technologies[t].researched = true
end
for _, t in pairs{'automation', 'logistics', 'steel-processing', 'fast-inserter', 'logistic-science-pack'} do
  f.add_research(t)
end
local ids = {}
for _, p in pairs(s.find_entities_filtered{type = 'electric-pole'}) do ids[p.electric_network_id] = true end
local n = 0
for _ in pairs(ids) do n = n + 1 end
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


def _run_to(r, tick, speed=64, limit=120):
    """Run the paused game to ``tick`` exactly (ticks_to_run), fast, and pause it there."""
    now = int(r.lua("rcon.print(game.tick)").strip())
    if tick > now:
        r.lua(f"game.speed = {speed} game.tick_paused = true game.ticks_to_run = {tick - now} "
              "rcon.print(1)")
    t0 = time.time()
    while int(r.lua("rcon.print(game.tick)").strip()) < tick and time.time() - t0 < limit:
        time.sleep(0.3)
    return int(r.lua("game.speed = 1 rcon.print(game.tick)").strip())


def check_stats(save=None):
    """2.1: the run stats on a laptop server (module docstring)."""
    import json
    import tempfile
    from fkcore import runstats, supply
    from fkcore.catalog import Catalog
    save = save or (sys.argv[2] if len(sys.argv) > 2 else None)
    if save:
        return _check_stats_save(save)
    cat = Catalog.load()
    tmp = tempfile.mkdtemp(prefix="fk-stats-")
    rec, viarcon, empty = (os.path.join(tmp, n) for n in ("rec", "rcon", "empty"))
    os.makedirs(empty)
    took, ok = [], True
    with LaptopServer("stats21", scenario="fk-play") as srv:
        out = os.path.join(srv.write, "script-output")
        with srv.rcon() as r:
            print("setup: electric networks", r.lua(STATS_SETUP).strip())
            r.lua("game.tick_paused = true rcon.print(1)")
            for k in (1, 2, 3):
                # the RCON read at the tick the recorder writes at; the recorder's line is there
                # once that tick has run
                for game, where, now in ((viarcon, empty, True), (rec, out, False)):
                    tick = _run_to(r, k * runstats.EVERY + (game == rec))
                    t0 = time.time()
                    lines = runstats.sample(r, game, cat, "player", "nauvis", now=now,
                                            out_dir=where)
                    took.append(time.time() - t0)
                    print(f"tick {tick} {'recorder' if game == rec else 'rcon'}: "
                          + " | ".join(lines))
            sup = supply.read(r, "player", "nauvis")
            busy = supply.research_line(sup.research)
            r.lua("for _, l in pairs(game.surfaces.nauvis.find_entities_filtered{type = 'lab'}) do "
                  "l.get_inventory(defines.inventory.lab_input).clear() end rcon.print(1)")
            _run_to(r, 3 * runstats.EVERY + 2 * 3600 + 1)
            stalled = supply.research_line(supply.read(r, "player", "nauvis").research)
        recorded = open(os.path.join(out, *runstats.RECORDER.split("/")), encoding="utf-8").read()
    print(f"recorder file: {len(recorded.splitlines())} lines, {len(recorded)} bytes")
    print(f"research line, labs busy: {busy}")
    print(f"research line, packs taken out, 2 game minutes on: {stalled}")
    a, b = runstats.Store(rec), runstats.Store(viarcon)
    worst = 0.0
    for series in ("items", "fluids", "power"):
        ra = {(x["from"], x["tick"]): x for x in runstats.windows(a.read(series))}
        rb = {(x["from"], x["tick"]): x for x in runstats.windows(b.read(series))}
        both = sorted(set(ra) & set(rb))
        print(f"{series}: recorder windows {sorted(ra)}, rcon windows {sorted(rb)}")
        ok = ok and len(both) == 3
        for key in both:
            for side in ("made", "used"):
                da, db = ra[key].get(side) or {}, rb[key].get(side) or {}
                for n in set(da) | set(db):
                    va, vb = float(da.get(n, 0)), float(db.get(n, 0))
                    worst = max(worst, abs(va - vb) / max(1.0, abs(va), abs(vb)))
    print(f"recorder against RCON, the same windows: largest relative difference {worst:.2e}")
    print("\n".join(runstats.history_lines(rec)))
    path = runstats.write_page(rec, "stats21 laptop check")
    print(f"page: {path}, {os.path.getsize(path)} bytes")
    m = runstats.Store(rec).read("machines")[-1]
    print("machines:", json.dumps(m["machines"], sort_keys=True), json.dumps(m["recipes"],
                                                                             sort_keys=True))
    p = runstats.windows(a.read("power"))[-1]
    print("power, the last window:", json.dumps(runstats.power_classes(p)))
    print(f"samples took {', '.join(f'{t:.2f}' for t in took)} s")
    ok = (ok and worst < 1e-6 and max(took) < 5 and len(recorded.splitlines()) == 3
          and busy.startswith("research ") and "packs/min" in busy
          and stalled.startswith("RESEARCH STALLED")
          and "no lab holds automation-science-pack" in stalled)
    print("run stats:", "OK" if ok else "NOT as designed")
    print(f"(the stores are in {tmp})")
    return 0 if ok else 1


def _check_stats_save(save):
    """The RCON path and the capital on a played map: two samples 5 game minutes apart."""
    import tempfile
    from fkcore import runstats, supply
    from fkcore.catalog import Catalog
    cat, game = Catalog.load(), tempfile.mkdtemp(prefix="fk-stats-save-")
    took = []
    with LaptopServer("stats21save", save=save) as srv:
        with srv.rcon() as r:
            r.lua("game.tick_paused = true rcon.print(1)")
            start = int(r.lua("rcon.print(game.tick)").strip())
            for k in (0, 1):
                _run_to(r, start + k * runstats.EVERY)
                t0 = time.time()
                lines = runstats.sample(r, game, cat, "player", "nauvis",
                                        out_dir=os.path.join(srv.write, "script-output"))
                took.append(time.time() - t0)
                print(" | ".join(lines))
            print(supply.research_line(supply.read(r, "player", "nauvis").research))
        recorder = os.path.exists(os.path.join(srv.write, "script-output", "fk-stats"))
    print("\n".join(runstats.history_lines(game)))
    print("the map's own recorder:", "wrote samples" if recorder else "none (read over RCON)")
    path = runstats.write_page(game, os.path.basename(save))
    print(f"page: {path}, {os.path.getsize(path)} bytes; samples took "
          + ", ".join(f"{t:.2f}" for t in took) + " s")
    return 0 if max(took) < 5 else 1


#: 2.1 open circuits: a building the toolkit never modelled, written with Entity kinds of the
#: prelude and raw settings only; the panel's wire is 34 tiles long, so it hops along poles
ALERT_FK = """# a programmable speaker and a display panel warn when the plate chest runs low
size 48x12

box  = Chest<storage>   @(2, 4)
spk  = Alarm<bp.alert_parameters={show_alert: true, show_on_map: true, icon_signal_id: iron-plate,
                                  alert_message: "Iron plates low"}>   @(6, 4)
note = Display<cb.parameters=[{condition: "iron-plate<50", icon: iron-plate, text: "Iron plates low"},
                              {condition: "iron-plate>=50", icon: signal-check, text: "Iron plates OK"}]>  @(40, 4)
set spk: cb.circuit_condition="iron-plate<50"
wire stock red: box -> spk, note
"""


def check_circuits():
    """2.1 open circuits on the lab (``fk lab``): ``ALERT_FK`` built; the wires read back from the
    game (chest - speaker - poles - panel); the chest stocked with 100, 20 and 100 plates, and each
    time what the speaker and the panel see on their wire, whether the speaker's condition holds
    (the game's own ``fulfilled``: its alert sounds and shows while it does) and the panel's shown
    text; then the diff, before and after raw fields are changed by hand."""
    import json
    import tempfile
    from fkcore import flow, lab
    run = tempfile.mkdtemp(prefix="fkcircuits-")
    game = os.path.join(run, "game")
    os.makedirs(game)
    for name, text in (("alert.fk", ALERT_FK),
                       ("nauvis.surface", "surface  nauvis\nmode     play\nterrain  none\n"
                        "catalog  base\n\nplace alert = alert plot 10,10 48x12\n"),
                       ("nauvis.build.fkb", "read_surface nauvis\n")):
        with open(os.path.join(game, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    # AREA is the slot's box, filled in per call (the Lua has % signs of its own)
    probe = ("local s = game.get_surface('lab') local out = {} "
             "local function sig(e) return e.get_signal({type = 'item', name = 'iron-plate'}, "
             "defines.wire_connector_id.circuit_red) end "
             "for _, e in pairs(s.find_entities_filtered{area = AREA, force = 'lab'}) do "
             "if e.name == 'programmable-speaker' then out.speaker = {sees = sig(e), "
             "fulfilled = e.get_control_behavior().circuit_condition.fulfilled} "
             "elseif e.name == 'display-panel' then "
             "out.panel = {sees = sig(e), shows = e.display_panel_text} "
             "elseif e.name == 'storage-chest' then out.chest = e.get_item_count('iron-plate') "
             "end end rcon.print(helpers.table_to_json(out))")
    wires = ("local s = game.get_surface('lab') local rows = {} "
             "for _, e in pairs(s.find_entities_filtered{area = AREA, force = 'lab'}) do "
             "local c = e.get_wire_connectors(false)[defines.wire_connector_id.circuit_red] "
             "if c then for _, w in pairs(c.connections) do local o = w.target.owner "
             "if e.position.x < o.position.x then rows[#rows + 1] = {e.position.x, e.name .. '@' "
             ".. e.position.x .. ',' .. e.position.y .. ' -> ' .. o.name .. '@' .. o.position.x "
             ".. ',' .. o.position.y} end end end end "
             "table.sort(rows, function(a, b) return a[1] < b[1] end) local out = {} "
             "for _, r in ipairs(rows) do out[#out + 1] = r[2] end "
             "rcon.print(helpers.table_to_json(out))")
    stock = ("local c = game.get_surface('lab').find_entities_filtered{area = AREA, "
             "name = 'storage-chest'}[1] local inv = c.get_inventory(defines.inventory.chest) "
             "inv.clear() inv.insert{name = 'iron-plate', count = COUNT} "
             "rcon.print(c.get_item_count('iron-plate'))")
    edit = ("local s = game.get_surface('lab') "
            "local sp = s.find_entities_filtered{area = AREA, name = 'programmable-speaker'}[1] "
            "local p = sp.parameters p.playback_volume = 0.5 sp.parameters = p "
            "local dp = s.find_entities_filtered{area = AREA, name = 'display-panel'}[1] "
            "dp.display_panel_always_show = false rcon.print('edited')")
    ok = True
    with LaptopServer("circuits", scenario="fk-play") as srv:
        with srv.rcon() as r:
            lines = lab.build(r, game, "alert", size=(48, 12))
            print("\n".join(lines))
            x, y, w, h = lab.slots(game)["alert"]
            box = "{{%d, %d}, {%d, %d}}" % (x - 1, y - 1, x + w + 1, y + h + 1)
            chain = json.loads(r.lua(wires.replace("AREA", box)).strip())
            print("red wires read back from the game, west to east:")
            for row in chain:
                print("  ", row)
            names = [row.split("@")[0] for row in chain] + [chain[-1].split(" -> ")[1].split("@")[0]]
            ok &= names == ["storage-chest", "programmable-speaker", "medium-electric-pole",
                            "medium-electric-pole", "medium-electric-pole", "display-panel"]
            for n, holds, shows in ((100, False, "Iron plates OK"), (20, True, "Iron plates low"),
                                    (100, False, "Iron plates OK")):
                r.lua(stock.replace("AREA", box).replace("COUNT", str(n)))
                time.sleep(2)
                got = json.loads(r.lua(probe.replace("AREA", box)).strip())
                print(f"chest {got.get('chest')} plates: the speaker sees {got['speaker']['sees']} "
                      f"and its condition holds: {got['speaker']['fulfilled']}; the panel sees "
                      f"{got['panel']['sees']} and shows {got['panel']['shows']!r}")
                ok &= got["speaker"]["fulfilled"] is holds and got["panel"]["shows"] == shows
                ok &= got["speaker"]["sees"] == n and got["panel"]["sees"] == n
            ws = lab.workspace(game, "alert")
            with open(os.path.join(ws, "lab.build.fkb"), encoding="utf-8") as fh:
                script = [ln for ln in fh.read().splitlines() if not ln.startswith("apply")]
            with open(os.path.join(ws, "check.fkb"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(script) + "\n")

            def hand():
                _code, ctx = flow.run(os.path.join(ws, "check.fkb"), echo=lambda _s: None,
                                      link=r)
                return [c.msg for _step, c in ctx.checks if c.code == "by-hand"]
            before = hand()
            print(f"hand edits after the build: {len(before)}")
            r.lua(edit.replace("AREA", box))
            after = hand()
            print(f"after a hand edit of the speaker's volume and the panel's always_show: "
                  f"{len(after)}")
            for line in after:
                print("  ", line)
            ok &= not before and len(after) == 2
    shutil.rmtree(run, True)
    print("open circuits:", "OK" if ok else "NOT as designed")
    return 0 if ok else 1


#: 2.1 (fluid ports): the lab's acid drill cell: acid in on the west pipe row and through to the
#: east, one electric drill on uranium, its ore onto the cell's through belt; three cells, the acid
#: from an infinity pipe outside the Stack, the ore into a chest.
FLUIDPORTS = """
module AcidDrill size 7x7 {
  port acid_in  : in  sulfuric-acid @w0
  port acid_out : out sulfuric-acid @e0
  port ore_in   : in  uranium-ore   @w6
  port ore_out  : out uranium-ore   @e6
  stack acid_in -> acid_out, ore_in -> ore_out
  d = MinerRow<n=1, resource=uranium-ore> @(0, 1)
  net a: acid_in -> d, acid_out
  net o: ore_in, d -> ore_out
}
acid  = InfinityPipe<fluid=sulfuric-acid, rate=10/s> @(0, 0)
cells = Stack<cell=AcidDrill, n=3> @(2, 0)
box   = Chest<storage> @(30, 6)
net acid: acid -> cells.acid_in
net ore: cells.ore_out -> box
"""


def check_fluidports(seconds=60):
    """2.1, fluid ports: a Stack of three acid drill cells on the lab, on a copy of a uranium patch
    of the server's nauvis, its acid from an infinity pipe outside the Stack. It reads the acid in
    every drill, the ore rate against the model (0.25/s a drill), and the acid an ore takes (the
    infinity pipe shut, the acid held in the slot's pipes and drills before and after)."""
    import json as jsonmod
    import tempfile
    from fkcore import lab
    from fkcore.catalog import Catalog
    cat = Catalog.load()
    run = tempfile.mkdtemp(prefix="fkfluidports-")
    game = os.path.join(run, "game")
    os.makedirs(game)
    for name, text in (("acid.fk", FLUIDPORTS),
                       ("nauvis.surface", "surface  nauvis\nmode     play\nterrain  none\n"
                        "catalog  base\n\nplace acid = acid plot 0,0 34x10\n"),
                       ("nauvis.build.fkb", "read_surface nauvis\n")):
        with open(os.path.join(game, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    out, ok = [], {}

    def tick(r):
        return int(r.lua("rcon.print(game.tick)").strip())

    def wait(r, s):
        t = tick(r)
        while tick(r) < t + s * 60:
            time.sleep(0.5)

    with LaptopServer("fluidports", scenario="fk-play") as srv:
        with srv.rcon() as r:
            # -- a uranium patch on nauvis: the chunks around spawn, wider until one shows
            find = ("local s = game.surfaces.nauvis local e = s.find_entities_filtered{name = "
                    "'uranium-ore', limit = 1}[1] rcon.print(e and (math.floor(e.position.x) .. "
                    "',' .. math.floor(e.position.y)) or '')")
            at, t0 = r.lua(find).strip(), time.time()
            for radius in (8, 12, 16, 24):
                if at:
                    break
                r.lua(f"game.surfaces.nauvis.request_to_generate_chunks({{0, 0}}, {radius}) "
                      "rcon.print(1)")
                t1 = time.time()
                while not at and time.time() - t1 < 60:
                    time.sleep(2)
                    at = r.lua(find).strip()
            if not at:
                print("fluidports: no uranium on the server's nauvis within 24 chunks")
                return 1
            ux, uy = (int(v) for v in at.split(","))
            out.append(f"uranium on nauvis at {ux},{uy} ({time.time() - t0:.0f} s to find)")
            # the patch's middle (the first tile found is on its edge), then the densest 22x7
            # rectangle there, for the three cells' drills (x 2..24, y 0..7 of the design)
            mid = r.lua("local s = game.surfaces.nauvis local n, x, y = 0, 0, 0 "
                        "for _, e in pairs(s.find_entities_filtered{name = 'uranium-ore', "
                        f"position = {{{ux}, {uy}}}, radius = 48}}) do n = n + 1 "
                        "x = x + e.position.x y = y + e.position.y end "
                        "rcon.print(math.floor(x / n) .. ',' .. math.floor(y / n))").strip()
            ux, uy = (int(v) for v in mid.split(","))
            best = jsonmod.loads(r.lua(
                "local s = game.surfaces.nauvis local b = {0, 0, 0} "
                f"for y = {uy - 16}, {uy + 10}, 2 do for x = {ux - 30}, {ux + 8}, 2 do "
                "local n = s.count_entities_filtered{name = 'uranium-ore', area = {{x, y}, "
                "{x + 22, y + 7}}} if n > b[3] then b = {x, y, n} end end end "
                "rcon.print(helpers.table_to_json(b))").strip())
            bx, by, n = best
            out.append(f"densest 22x7 there: {bx},{by}, {n} of 154 tiles uranium")

            # -- the build (a slot), the patch copied under the cells, the build again (a drill
            # finds its ore when it is built), then the infinity pipe set to its fluid: the lab
            # flow leaves that to a fixture (tools/lab_fluids.py start)
            lab.build(r, game, "acid", cat=cat)
            out += lab.ore(r, game, "acid", copy=f"{bx},{by},{bx + 22},{by + 7}", to=(2, 0))
            out += lab.build(r, game, "acid", cat=cat)
            sx, sy, sw, sh = lab.slots(game)["acid"]
            area = f"{{{{{sx - 2}, {sy - 2}}}, {{{sx + 40}, {sy + 14}}}}}"
            got = r.lua(f"local n = 0 for _, e in pairs(game.get_surface('lab')."
                        f"find_entities_filtered{{area = {area}, name = 'infinity-pipe'}}) do "
                        "e.set_infinity_pipe_filter{name = 'sulfuric-acid', percentage = 1, "
                        "mode = 'at-least'} n = n + 1 end rcon.print(n)").strip()
            out.append(f"infinity pipes set to sulfuric-acid: {got}")
            wait(r, 20)

            # -- acid in every drill
            drills = jsonmod.loads(r.lua(
                f"local o = {{}} for _, e in pairs(game.get_surface('lab').find_entities_filtered"
                f"{{area = {area}, name = 'electric-mining-drill'}}) do local f = e.fluidbox[1] "
                "o[#o + 1] = {e.position.x, e.position.y, f and f.name or '', f and f.amount or 0, "
                "e.status} end rcon.print(helpers.table_to_json(o))").strip())
            working = 1        # defines.entity_status.working
            for x, y, fl, amount, status in drills:
                out.append(f"drill at {x},{y}: {fl or 'no fluid'} {amount:.1f}, status {status}"
                           + (" (working)" if status == working else ""))
            ok["acid in every drill"] = (len(drills) == 3 and all(
                fl == "sulfuric-acid" and amount > 0 and status == working
                for _x, _y, fl, amount, status in drills))

            # -- the ore rate against the model: the lab force's mined ore (its production
            # statistics; fk measure reads crafting machines only), and what reaches the chest.
            # The model is full speed (0.25/s a drill); the lab force's mining productivity
            # research adds its bonus on top
            from fkcore.templates import miner_row
            model = sum(s.makes["uranium-ore"] for s in
                        miner_row({"n": 1, "resource": "uranium-ore"}, cat)) * 3
            bonus = float(r.lua("rcon.print(game.forces.lab.mining_drill_productivity_bonus)")
                          .strip())
            mined = ("rcon.print(game.forces.lab.get_item_production_statistics('lab')"
                     ".input_counts['uranium-ore'] or 0)")
            box = (f"local c = game.get_surface('lab').find_entities_filtered{{area = {area}, "
                   "name = 'storage-chest'}[1] rcon.print(c and c.get_item_count('uranium-ore') "
                   "or -1)")
            m0, b0, t0 = int(r.lua(mined).strip()), int(r.lua(box).strip()), tick(r)
            wait(r, seconds)
            m1, b1, t1 = int(r.lua(mined).strip()), int(r.lua(box).strip()), tick(r)
            span = (t1 - t0) / 60
            rate, into = (m1 - m0) / span, (b1 - b0) / span
            want = model * (1 + bonus)
            out.append(f"ore over {span:.0f} s: {m1 - m0} mined, {rate * 60:.1f}/min; "
                       f"{b1 - b0} into the chest, {into * 60:.1f}/min. The model: "
                       f"{model * 60:.1f}/min at full speed, {want * 60:.1f}/min with the lab "
                       f"force's mining productivity +{bonus * 100:.0f}%")
            ok["the ore rate"] = abs(rate / want - 1) <= 0.1 and abs(into / want - 1) <= 0.15

            # -- the acid an ore takes: the lab force's acid used (its fluid statistics) against
            # every ore mined since the build, less the productivity bonus (a bonus ore takes no
            # acid). A drill draws its acid 10 at a time (a draw before its 10 mining cycles),
            # so with one acid an ore the use is the ore mined and at most 10 a drill more
            acid = int(float(r.lua("rcon.print(game.forces.lab.get_fluid_production_statistics("
                                   "'lab').output_counts['sulfuric-acid'] or 0)").strip()))
            ore = int(r.lua(mined).strip())
            cycles = ore / (1 + bonus)
            out.append(f"acid used since the build: {acid}, for {ore} ore mined ({cycles:.0f} "
                       f"mining cycles without the bonus); the model's one acid an ore, drawn 10 "
                       f"at a time a drill, says {cycles:.0f} to {cycles + 30:.0f}")
            ok["one acid an ore"] = cycles > 0 and cycles - 1 <= acid <= cycles + 31
    print("\n".join(out))
    for k, v in ok.items():
        print(f"{k}: {'OK' if v else 'NOT as designed'}")
    shutil.rmtree(run, True)
    return 0 if all(ok.values()) else 1


#: 2.1, power domains: two domains side by side, their poles 4 tiles apart (in each other's reach)
PAIR_FK = """
power a: cover all
power b: cover b1, b2
a1 = Assembler<recipe=iron-gear-wheel> @(0, 1)
a2 = Assembler<recipe=iron-gear-wheel> @(0, 6)
b1 = Assembler<recipe=iron-gear-wheel> @(10, 1)
b2 = Assembler<recipe=iron-gear-wheel> @(10, 6)
"""
_DOMAIN_BASE = """
local s, f = game.get_surface('lab'), game.forces['lab']
local eei = s.create_entity{name = 'electric-energy-interface', position = {-30, -20}, force = f}
eei.electric_buffer_size = 1e12
eei.power_production = 1e9
eei.energy = 1e12
s.create_entity{name = 'substation', position = {-27, -20}, force = f}
local rp = s.create_entity{name = 'roboport', position = {-24, -16}, force = f}
rp.insert{name = 'construction-robot', count = 50}
local st = s.create_entity{name = 'storage-chest', position = {-20.5, -18.5}, force = f}
for _, n in pairs({'medium-electric-pole', 'assembling-machine-1'}) do st.insert{name = n, count = 50} end
rcon.print('ok')"""


def _flow_build(files, name):
    """Build a .fk on paper in a temp dir (the flow up to write_layout): -> its .fkp Layout."""
    import tempfile
    from fkcore import flow, fkp
    d = tempfile.mkdtemp(prefix="fkpower-")
    files = dict(files)
    files.setdefault("nauvis.build.fkb", "read_surface nauvis\nread_terrain none\nelaborate\n"
                     "report_rates\nplace --keep pinned\nroute --only stale\n"
                     "cover power --pole medium-electric-pole\nfloorplan\nreport_checks\n"
                     "write_layout\n")
    for fn, text in files.items():
        with open(os.path.join(d, fn), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    code, ctx = flow.run(os.path.join(d, "nauvis.build.fkb"), echo=lambda _l: None)
    lay = fkp.load(os.path.join(d, f"{name}.fkp"))
    shutil.rmtree(d, True)
    return lay, ctx


def check_domains():
    """2.1, power domains, the paste measurement: two domains side by side (``PAIR_FK``, their
    poles 4 tiles apart), pasted in play mode and built by robots, twice: plot one in one paste,
    plot two its domain a first and domain b in a second paste once a stands (a robot-built pole
    joins the standing poles in its reach). The networks are polled while the robots work, then
    the wire pass runs (as ``fk wait built`` runs it): each plot must come out as two networks.
    It reports how long, in game seconds, the two domains were one network before the pass."""
    from fkcore import apply as applymod, compose, fkp, wires as wiresmod
    from fkcore.catalog import Catalog
    cat, f = Catalog.load(), "lab"
    lay, _ctx = _flow_build({"pair.fk": PAIR_FK, "nauvis.surface":
                             "surface nauvis\nmode play\nterrain none\n"
                             "place pair = pair plot 0,0 16x10\n"}, "pair")
    plots = fkp.loads("fkp 1 surface lab\nplot one at 0,0 rot 0 size 16x10\n"
                      "plot two at 0,20 rot 0 size 16x10\n")
    s = compose.compose(plots, {"one": lay, "two": lay}, cat)
    poles = {k: (float(e.x), float(e.y), e.attrs.get("domain") or "a")
             for k, e in s.entities.items() if e.name == "medium-electric-pole"}
    print("design poles:", ", ".join(f"{k} {x},{y} ({d})" for k, (x, y, d) in sorted(poles.items())))
    probe = ("local s = game.get_surface('lab') local o = {tick = game.tick, ghosts = "
             "s.count_entities_filtered{area = {{-2, -2}, {18, 32}}, type = 'entity-ghost'}, p = {}} "
             "for _, e in pairs(s.find_entities_filtered{area = {{-2, -2}, {18, 32}}, "
             "name = 'medium-electric-pole'}) do o.p[#o.p + 1] = {e.position.x, e.position.y, "
             "e.electric_network_id} end rcon.print(helpers.table_to_json(o))")

    def nets(got, plot):
        """{domain: {network ids}} of the plot's built poles."""
        out = {}
        for x, y, nid in got["p"]:
            for k, (px, py, d) in poles.items():
                if k.startswith(f"lab:{plot}/") and abs(px - x) < 0.01 and abs(py - y) < 0.01:
                    out.setdefault(d, set()).add(nid)
        return out

    def joined(got, plot):
        n = nets(got, plot)
        return bool(n.get("a", set()) & n.get("b", set()))

    def watch(r, plot, limit=90):
        """Run the game at speed 4 until no ghost is left, polling: -> (first tick the plot's two
        domains were one network or None, the tick the robots were done)."""
        r.lua("game.speed = 4 rcon.print(1)")
        first, t0 = None, time.time()
        while time.time() - t0 < limit:
            got = json.loads(r.lua(probe).strip())
            if first is None and joined(got, plot):
                first = got["tick"]
            if got["ghosts"] == 0:
                break
            time.sleep(0.2)
        r.lua("game.speed = 1 rcon.print(1)")
        return first, got["tick"]

    import json
    watchp = {"plots": "keep", "sanctioned": "mark 2h", "notify": "off"}
    ok = True
    with LaptopServer("power", scenario="fk-play") as srv:
        with srv.rcon() as r:
            r.lua(link.lua_generate_area("lab", f, (-64, -64, 64, 64)))
            print("base:", r.lua(_DOMAIN_BASE).strip())
            for plot, steps in (("one", [["lab:one/"]]),
                                ("two", [["lab:two/power/", "lab:two/a1/", "lab:two/a2/"],
                                         ["lab:two/power-b/", "lab:two/b1/", "lab:two/b2/"]])):
                first, own = None, None
                for keys in steps:
                    rep = applymod.apply(r, s, cat, mode="play", force=f, policy=watchp,
                                         keys=keys, own=own)
                    own = rep.own
                    print(f"plot {plot}, apply {' '.join(keys)}: {rep.lines()[0]}"
                          + (f"; {rep.wires.line()}" if rep.wires and rep.wires.line() else ""))
                    j, done = watch(r, plot)
                    first = first if first is not None else j
                    print(f"  robots done at tick {done}; the domains one network from tick "
                          f"{j}" if j is not None else f"  robots done at tick {done}; the "
                          "domains never one network")
                before = nets(json.loads(r.lua(probe).strip()), plot)
                area = (-1, -1 + (20 if plot == "two" else 0), 17, 11 + (20 if plot == "two" else 0))
                t_pass = int(r.lua("rcon.print(game.tick)").strip())
                p = wiresmod.run(r, s, cat, area)
                after = nets(json.loads(r.lua(probe).strip()), plot)
                two = (len(after.get("a", ())) == 1 and len(after.get("b", ())) == 1
                       and after["a"] != after["b"])
                held = (t_pass - first) / 60 if first is not None else 0
                print(f"  networks before the wire pass {sorted((k, sorted(v)) for k, v in before.items())}; "
                      f"the pass: {p.line()}; after {sorted((k, sorted(v)) for k, v in after.items())}: "
                      f"{'two networks' if two else 'NOT two networks'}; one network for "
                      f"{held:.1f} game s before the pass")
                ok &= two
    print("power domains with robots:", "OK" if ok else "NOT as designed")
    return 0 if ok else 1


#: 2.1, power domains: examples\power-shed.fk on the lab. main holds the accumulators, the latch
#: and (by script) the supply; shed is the load, two radars (300 kW each, always on: an idle lab
#: draws nothing), behind the switch. The latch opens the switch below 20% and closes it at 80%.
SHED_FK = """
signal A = signal-A
signal S = signal-S
power main: cover all
power shed: cover r1, r2
acc   = Accumulator<read=A> @(2, 2)
acc2  = Accumulator @(2, 5)
latch = Decider<if="green.A < 20 or (red.S > 0 and green.A < 80)", out="S=1"> @(6, 2)
wire level green: acc -> latch.in
wire hold  red:   latch.out -> latch.in
sw = PowerSwitch @(10, 2) when hold.S = 0
copper feed: main -> sw.left
copper load: sw.right -> shed
r1 = Entity<name=radar> @(20, 1)
r2 = Entity<name=radar> @(20, 5)
"""


def check_powershed():
    """2.1, power domains on the lab (``fk lab``): ``SHED_FK`` built; the lab's own energy
    interface goes, and one beside main's pole is the supply, set by script. The accumulators
    are filled, the supply cut, and the radars run them down: the switch must open below 20%.
    Then the supply comes back, and the switch must close again past 80%. It polls the charge,
    the latch's signals and the switch every few ticks and reports the charge at each change."""
    import json
    import tempfile
    from fkcore import lab
    run = tempfile.mkdtemp(prefix="fkshed-")
    game = os.path.join(run, "game")
    os.makedirs(game)
    for name, text in (("shed.fk", SHED_FK),
                       ("nauvis.surface", "surface  nauvis\nmode     play\nterrain  none\n"
                        "catalog  base\n\nplace shed = shed plot 10,10 30x12\n"),
                       ("nauvis.build.fkb", "read_surface nauvis\n")):
        with open(os.path.join(game, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    ok = {}
    with LaptopServer("power", scenario="fk-play") as srv:
        with srv.rcon() as r:
            lines = lab.build(r, game, "shed", size=(30, 12))
            print("\n".join(lines))
            ws = lab.workspace(game, "shed")
            for fn in ("cover_power.txt", "floorplan.txt", "diff.txt"):
                try:
                    with open(os.path.join(ws, "out", fn), encoding="utf-8") as fh:
                        print("".join(ln for ln in fh if "check" in ln or "domain" in ln
                                      or "copper" in ln or "wires:" in ln or "  " in ln[:4]))
                except OSError:
                    pass
            x, y, w, h = lab.slots(game)["shed"]
            box = "{{%d, %d}, {%d, %d}}" % (x - 1, y - 1, x + w + 1, y + h + 1)
            # the lab's supply goes; ours stands beside main's pole (the one by the accumulators)
            setup = ("local s = game.get_surface('lab') local B = BOX "
                     "for _, e in pairs(s.find_entities_filtered{area = B, name = 'electric-energy-interface'}) do e.destroy() end "
                     "local acc = s.find_entities_filtered{area = B, name = 'accumulator'} "
                     "local p = s.find_entities_filtered{position = acc[1].position, radius = 9, name = 'medium-electric-pole'} "
                     "local pole "
                     "for _, q in pairs(p) do if not pole or q.position.x < pole.position.x then pole = q end end "
                     "local ei "
                     "for dx = -3, 3 do for dy = -3, 3 do if not ei then local pos = {pole.position.x + dx, pole.position.y + dy} "
                     "if s.can_place_entity{name = 'electric-energy-interface', position = pos, force = 'lab'} "
                     "and pos[1] < pole.position.x then ei = s.create_entity{name = 'electric-energy-interface', position = pos, force = 'lab'} end end end end "
                     "ei.electric_buffer_size = 2e6 / 60 ei.power_production = 2e6 / 60 ei.power_usage = 0 "
                     "for _, a in pairs(acc) do a.energy = a.electric_buffer_size end "
                     "rcon.print(ei.position.x .. ',' .. ei.position.y .. ' net ' .. ei.electric_network_id)")
            print("supply:", r.lua(setup.replace("BOX", box)).strip())
            probe = ("local s = game.get_surface('lab') local B = BOX local o = {tick = game.tick} "
                     "local acc = s.find_entities_filtered{area = B, name = 'accumulator'} "
                     "local e, m = 0, 0 for _, a in pairs(acc) do e = e + a.energy m = m + a.electric_buffer_size end "
                     "o.charge = 100 * e / m "
                     "local sw = s.find_entities_filtered{area = B, name = 'power-switch'}[1] "
                     "o.closed = sw.power_switch_state "
                     "local d = s.find_entities_filtered{area = B, name = 'decider-combinator'}[1] "
                     "o.A = d.get_signal({type = 'virtual', name = 'signal-A'}, defines.wire_connector_id.combinator_input_green) "
                     "o.S = sw.get_signal({type = 'virtual', name = 'signal-S'}, defines.wire_connector_id.circuit_red) "
                     "local nets = {} for _, p in pairs(s.find_entities_filtered{area = B, name = 'medium-electric-pole'}) do "
                     "nets[#nets + 1] = p.electric_network_id end table.sort(nets) o.nets = nets "
                     "local names = {} for k, v in pairs(defines.entity_status) do names[v] = k end "
                     "local r = s.find_entities_filtered{area = B, name = 'radar'}[1] o.radar = names[r.status] "
                     "rcon.print(helpers.table_to_json(o))").replace("BOX", box)
            supply = ("local s = game.get_surface('lab') for _, e in pairs(s.find_entities_filtered"
                      "{area = BOX, name = 'electric-energy-interface'}) do e.power_production = W / 60 "
                      "e.electric_buffer_size = math.max(W, 1) / 60 end rcon.print(W)").replace("BOX", box)
            # an accumulator charges only from a primary or secondary source, and an energy
            # interface is tertiary as they are: the charging is done by script, W watts since tick
            # T0, shared among the accumulators
            charge = ("local s = game.get_surface('lab') local acc = s.find_entities_filtered"
                      "{area = BOX, name = 'accumulator'} local j = W * (game.tick - T0) / 60 / #acc "
                      "for _, a in pairs(acc) do a.energy = math.min(a.electric_buffer_size, a.energy + j) end "
                      "rcon.print(1)").replace("BOX", box)
            time.sleep(1)
            got = json.loads(r.lua(probe).strip())
            print(f"start: charge {got['charge']:.1f}%, A={got['A']}, S={got['S']}, switch "
                  f"{'closed' if got['closed'] else 'open'}, pole networks {got['nets']}")
            events = []

            def watch(want_closed, charge_w=0, limit=120):
                last = json.loads(r.lua(probe).strip())
                t0 = time.time()
                while time.time() - t0 < limit:
                    if charge_w:
                        r.lua(charge.replace("W", str(charge_w)).replace("T0", str(last["tick"])))
                    got = json.loads(r.lua(probe).strip())
                    if got["closed"] != last["closed"]:
                        events.append((last, got))
                        print(f"  tick {got['tick']}: the switch {'closes' if got['closed'] else 'opens'}"
                              f" at charge {got['charge']:.1f}% (the tick before {last['charge']:.1f}%, "
                              f"{'closed' if last['closed'] else 'open'}); latch input A={got['A']}, "
                              f"S={got['S']}; radar {got['radar']}")
                        if got["closed"] == want_closed:
                            return got
                    last = got
                    time.sleep(0.02)
                return None
            r.lua("game.speed = 0.5 rcon.print(1)")
            print("the supply cut to 0 W; the radars (600 kW) run the accumulators down")
            r.lua(supply.replace("W", "0"))
            down = watch(False)
            hold = json.loads(r.lua(probe).strip())
            time.sleep(2)
            hold2 = json.loads(r.lua(probe).strip())
            print(f"  open and the supply still 0: charge {hold['charge']:.1f}% -> {hold2['charge']:.1f}% "
                  f"over {(hold2['tick'] - hold['tick']) / 60:.1f} game s; radar {hold2['radar']}; "
                  f"pole networks {hold2['nets']}")
            print("the accumulators charged by script at 1 MW (the energy interface stays at 0)")
            up = watch(True, charge_w=1000000)
            r.lua("game.speed = 1 rcon.print(1)")
            after = json.loads(r.lua(probe).strip())
            print(f"  after: charge {after['charge']:.1f}%, radar {after['radar']}")
            ok["opens below 20%"] = down is not None and down["charge"] < 20 and \
                events[0][0]["charge"] >= 19
            ok["stays open while low"] = abs(hold2["charge"] - hold["charge"]) < 1 and \
                hold2["closed"] is False
            ok["closes past 80%"] = up is not None and up["charge"] >= 79.5 and \
                [e[1]["closed"] for e in events] == [False, True]
            ok["two networks"] = len(set(hold2["nets"])) == 2
    shutil.rmtree(run, True)
    for k, v in ok.items():
        print(f"{k}: {'OK' if v else 'NOT as designed'}")
    return 0 if ok and all(ok.values()) else 1


def check_drops(seconds=20):
    """3.0: what drops its output on a tile, and on which lane of a belt.

    - every prototype's ``vector_to_place_result`` (drills, recyclers): printed as JSON for
      ``fkcore.facts``;
    - an electric drill facing north onto a belt across (east), in line heading away (north) and
      in line heading toward it (south), and one facing east onto a belt across (south): the
      items on each lane after ``seconds``; and a drill dropping straight into a chest."""
    import json as jsonmod
    from fkcore import link as linkmod
    s, f = "lab", "lab"
    ok = {}
    with LaptopServer("drops", scenario="fk-play") as srv:
        with srv.rcon() as r:
            vec = r.lua("local o = {} for name, p in pairs(prototypes.entity) do "
                        "local v = p.vector_to_place_result if v then o[#o + 1] = name .. '=' .. "
                        "(v.x or v[1]) .. ',' .. (v.y or v[2]) .. ',' .. p.tile_width .. 'x' .. "
                        "p.tile_height .. ',' .. p.type end end "
                        "rcon.print(table.concat(o, ';'))").strip()
            vectors = {}
            for row in filter(None, vec.split(";")):
                name, rest = row.split("=", 1)
                vx, vy, size, kind = rest.split(",")
                vectors[name] = {"vector": [float(vx), float(vy)], "size": size, "type": kind}
            print("VECTORS " + jsonmod.dumps(vectors, sort_keys=True))
            r.lua(linkmod.lua_generate_area(s, f, (-40, -40, 80, 40)))
            # drill centre, direction, belt tiles (x, y, direction), or a chest at the drop tile
            cases = {
                "across": ((0.5, 0.5), 0, [(x + 0.5, -1.5, 4) for x in range(0, 4)]),
                "in line, away": ((10.5, 0.5), 0, [(10.5, -y - 0.5, 0) for y in range(1, 5)]),
                "in line, toward": ((20.5, 0.5), 0, [(20.5, -y - 0.5, 8) for y in range(1, 5)]),
                "east, across": ((30.5, 0.5), 4, [(32.5, y + 0.5, 8) for y in range(0, 4)]),
                "chest": ((40.5, 0.5), 0, "chest"),
            }
            lua = [f"local s = game.get_surface('{s}')"]
            for (cx, cy), d, what in cases.values():
                lua.append(f"for x = -2, 2 do for y = -2, 2 do s.create_entity{{name = 'iron-ore', "
                           f"position = {{{cx} + x, {cy} + y}}, amount = 5000}} end end")
                lua.append(f"s.create_entity{{name = 'electric-mining-drill', position = {{{cx}, "
                           f"{cy}}}, direction = {d}, force = '{f}'}}")
                if what == "chest":
                    lua.append(f"s.create_entity{{name = 'wooden-chest', position = {{{cx}, "
                               f"{cy - 2}}}, force = '{f}'}}")
                else:
                    for bx, by, bd in what:
                        lua.append(f"s.create_entity{{name = 'transport-belt', position = "
                                   f"{{{bx}, {by}}}, direction = {bd}, force = '{f}'}}")
            lua.append(f"local e = s.create_entity{{name = 'electric-energy-interface', position = "
                       f"{{20, 6}}, force = '{f}'}} e.power_production = 5000000 "
                       "e.electric_buffer_size = 5000000")
            for x in range(-4, 48, 6):
                lua.append(f"s.create_entity{{name = 'medium-electric-pole', position = {{{x}.5, "
                           f"3.5}}, force = '{f}'}}")
            lua.append("rcon.print(1)")
            r.lua(" ".join(lua))
            time.sleep(seconds)
            got = {}
            for name, ((cx, cy), d, what) in cases.items():
                if what == "chest":
                    got[name] = r.lua(f"local c = game.get_surface('{s}').find_entity('wooden-"
                                      f"chest', {{{cx}, {cy - 2}}}) rcon.print(c and "
                                      "c.get_item_count('iron-ore') or -1)").strip()
                    continue
                q = " ".join(f"local b = s.find_entity('transport-belt', {{{bx}, {by}}}) if b then "
                             "l = l + b.get_transport_line(1).get_item_count() r = r + "
                             "b.get_transport_line(2).get_item_count() end"
                             for bx, by, _bd in what)
                got[name] = r.lua(f"local s = game.get_surface('{s}') local l, r = 0, 0 {q} "
                                  "rcon.print(l .. ' L, ' .. r .. ' R')").strip()
            for name, ((cx, cy), _d, what) in cases.items():
                got[name] += " | " + r.lua(
                    f"local s = game.get_surface('{s}') local d = s.find_entity("
                    f"'electric-mining-drill', {{{cx}, {cy}}}) local n = 0 "
                    + ("" if what == "chest" else " ".join(
                        f"if s.find_entity('transport-belt', {{{bx}, {by}}}) then n = n + 1 end"
                        for bx, by, _bd in what))
                    + " local st = '' if d then for k, v in pairs(defines.entity_status) do if v == "
                    "d.status then st = k end end end rcon.print((d and 'drill ' .. st or 'no drill')"
                    " .. ', ' .. n .. ' belts')").strip()
            for name, v in got.items():
                print(f"{name}: {v}")
            ok["drills mined"] = all(v.split(" | ")[0] not in ("0 L, 0 R", "0", "-1")
                                      for v in got.values())
    for k, v in ok.items():
        print(f"{k}: {'OK' if v else 'NOT as designed'}")
    return 0 if ok and all(ok.values()) else 1


#: check_machines' design: a learned foundry wrapped as a Literal, in a cell, three stacked in a
#: sealed line whose open ports the lab feeds (molten iron in, gears out)
_FOUNDRY_LINE = """
module FoundryCell size 5x8 {
  port g_in   : in  iron-gear-wheel @w0
  port g_out  : out iron-gear-wheel @e0
  port mi_in  : in  molten-iron     @w7
  port mi_out : out molten-iron     @e7
  stack g_in -> g_out, mi_in -> mi_out
  m = Literal<file="foundry.json"> @(0, 2)
  net mi: mi_in -> m.f, mi_out
  net g: g_in, m.f -> g_out
}
module FoundryLine size 17x8 {
  port mi : in  molten-iron     @w7
  port g  : out iron-gear-wheel @e0
  s = Stack<cell=FoundryCell, n=3> @(1, 0)
  net molten: mi -> s.mi_in
  net gears: s.g_out -> g
}
line = FoundryLine @(4, 3)
"""

#: the same cells fed by the design's own InfinityPipe (3.0: it pastes with its fluid set)
_FOUNDRY_PIPED = _FOUNDRY_LINE.split("module FoundryLine")[0] + """
src = InfinityPipe<fluid=molten-iron> @(0, 10)
line = Stack<cell=FoundryCell, n=3> @(4, 3)
box = Chest<provider> @(24, 3)
net molten: src -> line.mi_in
net gears: line.g_out -> box
"""


_LUA_RECIPE_BOXES = r"""
local s = game.surfaces.fkm
if not s then
  s = game.create_surface('fkm', {width = 64, height = 64})
  s.request_to_generate_chunks({0, 0}, 2)
  s.force_generate_chunk_requests()
  local t = {}
  for x = -16, 15 do for y = -16, 15 do t[#t + 1] = {name = 'lab-dark-1', position = {x, y}} end end
  s.set_tiles(t)
  game.forces.player.enable_all_recipes()
end
local out = {}
for _, job in pairs(helpers.json_to_table('__JOBS__')) do
  for _, rec in pairs(job.recipes) do
    local row = {machine = job.machine, recipe = rec, boxes = {}}
    local ok, e = pcall(s.create_entity, {name = job.machine, position = {0, 0}, force = 'player',
                                          recipe = rec})
    if ok and e and not e.get_recipe() then
      -- Space Age: a recipe with surface conditions sets only where they hold
      for _, c in pairs(prototypes.recipe[rec].surface_conditions or {}) do
        local v = c.min
        if not v or v < -1e30 then v = c.max end
        if v and v > -1e30 and v < 1e30 then s.set_property(c.property, v) end
      end
      pcall(e.set_recipe, rec)
    end
    if ok and e and not e.get_recipe() then
      row.error = 'the recipe would not set'
      e.destroy()
    elseif ok and e then
      local fb = e.fluidbox
      for i = 1, #fb do
        local p, idx = fb.get_prototype(i), {}
        if p.object_name then p = {p} end
        for _, q in pairs(p) do idx[#idx + 1] = q.index end
        local f = fb.get_filter(i)
        row.boxes[#row.boxes + 1] = {fluid = f and f.name or '', idx = idx}
      end
      e.destroy()
    else
      row.error = tostring(e)
    end
    out[#out + 1] = row
  end
end
helpers.write_file('fk5/__TAG__.json', helpers.table_to_json({rows = out}), false)
rcon.print(#out)
"""


def _recipe_box_jobs(cat):
    """{machine: [recipe ...]}: every assembling machine with fluid boxes and every recipe of its
    crafting categories that has a fluid."""
    from fkcore import facts
    jobs = {}
    for m, row in sorted((cat._fluid.get("entities") or {}).items()):
        if row.get("type") != "assembling-machine":
            continue
        cats = set((facts.entity(m) or {}).get("crafting_categories") or ())
        recs = [r for r, rec in sorted(cat._recipes.items())
                if (rec.get("category") or "crafting") in cats
                and any(x.get("type") == "fluid" for x in list(rec.get("ingredients") or ())
                        + list(rec.get("products") or ()))]
        if recs:
            jobs[m] = recs
    return jobs


def check_recipe_boxes(which=None):
    """3.0 (machines): each fluid crafter of a game built once with each of its fluid recipes on
    a scratch surface of this test server; the fluid boxes the game makes live (fluid and
    prototype boxes of each) against ``Catalog.fluid_boxes_at``'s recipe rule. ``which``:
    "space-age" (base + the overlay ``fk catalog learn --mod space-age`` makes) or "seablock"
    (FK_PACK=seablock, its mods from C:\\fk-mods\\sb-mods); argv[2], both by default. Writes the
    disagreements to out/laptop-server/recipeboxes-<which>.json."""
    import json as jsonmod
    import tempfile
    from fkcore import learn, learned
    from fkcore.catalog import Catalog
    which = which or (sys.argv[2] if len(sys.argv) > 2 else None)
    pack = "seablock" if which == "seablock" else ""
    if which is None or os.environ.get("FK_PACK", "") != pack:
        # the catalog's pack is fixed when fkcore is imported: each game in its own process
        return max(subprocess.call([sys.executable, os.path.abspath(__file__), "recipeboxes", g],
                                   env=dict(os.environ, FK_PACK="seablock" if g == "seablock"
                                            else ""))
                   for g in ([which] if which else ["space-age", "seablock"]))
    bad = 0
    for game in [which]:
        env = {k: os.environ.get(k) for k in ("FK_PACK", "FK_LEARNED")}
        try:
            if game == "seablock":
                os.environ["FK_PACK"], os.environ["FK_LEARNED"] = "seablock", ""
                srv = LaptopServer("recipeboxes-sb", scenario="fk-play", mods=(),
                                   mod_dir=os.environ.get("FK_SB_MODS", r"C:\fk-mods\sb-mods"),
                                   boot_s=120)
            else:
                os.environ["FK_PACK"] = ""
                srv = LaptopServer("recipeboxes-sa", scenario="fk-play",
                                   mods=("space-age", "quality", "elevated-rails"))
            with srv:
                with srv.rcon() as r:
                    if game == "space-age":
                        ov, _lines = learn.learn(r, mod="space-age")
                        p = os.path.join(tempfile.mkdtemp(prefix="fk-rb-"), learned.NAME)
                        learn.write(ov, p)
                        os.environ["FK_LEARNED"] = p
                    cat = Catalog.load()
                    jobs = _recipe_box_jobs(cat)
                    rows, t0 = [], time.time()
                    for m, recs in jobs.items():
                        for i in range(0, len(recs), 60):
                            tag = f"rb-{os.getpid()}"
                            lua = (_LUA_RECIPE_BOXES.replace("__TAG__", tag).replace(
                                "__JOBS__", jsonmod.dumps([{"machine": m,
                                                           "recipes": recs[i:i + 60]}])))
                            got = link.read_output(r, lua, tag, "recipe boxes", keep=False)
                            rows += got.get("rows") or []
            dt = time.time() - t0
            diff, same, errs, unfiltered = [], 0, [], 0
            for x in rows:
                if x.get("error"):
                    errs.append((x["machine"], x["recipe"], x["error"]))
                    continue
                live = [b for b in (x.get("boxes") or []) if b["fluid"]]
                unfiltered += len(x.get("boxes") or []) - len(live)
                got = sorted((b["fluid"], sorted(b["idx"])) for b in live)
                row = cat._fluid["entities"][x["machine"]]
                want = sorted((f, sorted({bi for bi, _c in mem}))
                              for f, mem in cat._recipe_boxes(x["machine"], row, x["recipe"])
                              or [])
                if got == want:
                    same += 1
                else:
                    diff.append({"machine": x["machine"], "recipe": x["recipe"], "game": got,
                                 "rule": want, "boxes": x.get("boxes")})
            with open(os.path.join(BASE, f"recipeboxes-{game}.json"), "w",
                      encoding="utf-8") as fh:
                jsonmod.dump({"diff": diff, "errors": errs}, fh, indent=1)
            print(f"{game}: {len(jobs)} machines, {len(rows)} recipes measured in {dt:.1f} s: "
                  f"{same} as the rule, {len(diff)} not, {len(errs)} not buildable, "
                  f"{unfiltered} live boxes without a fluid")
            for d in diff[:12]:
                print(f"  {d['machine']} {d['recipe']}: game {d['game']} rule {d['rule']}")
            bad += len(diff)
        finally:
            for k, v in env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return 0 if not bad else 1


def check_machines(seconds=30):
    """3.0 (Rory: the setup a player needs to implement a machine): a Space Age game, ``fk
    catalog learn foundry`` into the game folder's learned.json, then ``fk lab`` builds three
    stacked cells of a foundry wrapped as a Literal. Every net connected, molten iron in every
    foundry, and the first foundry's gears/s against the model (4 crafts/s at speed 4, +50% built
    in: 6/s); the two after it share its gear belt."""
    import json as jsonmod
    import tempfile
    from fkcore import lab, learn, learned
    run = tempfile.mkdtemp(prefix="fk-machines-")
    game = os.path.join(run, "game")
    os.makedirs(game)
    files = {"foundries.fk": _FOUNDRY_LINE, "piped.fk": _FOUNDRY_PIPED,
             "foundry.json": jsonmod.dumps({"entities": [{"name": "foundry", "x": 2.5, "y": 2.5,
                                                         "recipe": "casting-iron-gear-wheel"}],
                                           "names": {"f": 0}}),
             "nauvis.surface": "surface  nauvis\nmode     play\nterrain  none\ncatalog  base\n\n"
                               "place line = foundries plot 0,0 24x12\n"
                               "place piped = piped plot 0,14 28x12\n",
             "nauvis.build.fkb": "read_surface nauvis\n"}
    for name, text in files.items():
        with open(os.path.join(game, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    here = os.getcwd()
    os.chdir(game)                          # fkcore runs in the run's game folder
    try:
        with LaptopServer("machines", scenario="fk-play",
                          mods=("space-age", "quality", "elevated-rails")) as srv:
            with srv.rcon() as r:
                t0 = time.time()
                ov, lines = learn.learn(r, ["foundry"])
                learn.write(ov, os.path.join(game, learned.NAME))
                lines.append(f"learned in {time.time() - t0:.2f} s")
                lines += lab.build(r, game, "line", size=(24, 12))
                lines += lab.build(r, game, "piped", size=(28, 12))
                x, y, w, h = lab.slots(game)["line"]
                q = (f"local o = {{}} for _, e in pairs(game.get_surface('lab').find_entities_filtered"
                     f"{{area = {{{{{x}, {y}}}, {{{x + w}, {y + h}}}}}, name = 'foundry'}}) do "
                     "local b = e.fluidbox[1] o[#o + 1] = {x = e.position.x, made = "
                     "e.products_finished, fluid = b and b.name or 'none'} end "
                     "rcon.print(helpers.table_to_json({tick = game.tick, f = o}))")
                px, py, pw, ph = lab.slots(game)["piped"]
                pq = ("local o = {pipes = {}, f = {}} local s = game.get_surface('lab') "
                      f"local a = {{{{{px}, {py}}}, {{{px + pw}, {py + ph}}}}} "
                      "for _, e in pairs(s.find_entities_filtered{area = a, name = 'infinity-pipe'}) "
                      "do local f = e.get_infinity_pipe_filter() "
                      "o.pipes[#o.pipes + 1] = f and f.name or 'none' end "
                      "for _, e in pairs(s.find_entities_filtered{area = a, name = 'foundry'}) "
                      "do local b = e.fluidbox[1] o.f[#o.f + 1] = b and b.name or 'none' end "
                      "rcon.print(helpers.table_to_json(o))")
                time.sleep(5)                         # the line fills
                a = jsonmod.loads(r.lua(q))
                piped = jsonmod.loads(r.lua(pq))
                time.sleep(seconds)
                b = jsonmod.loads(r.lua(q))
    finally:
        os.chdir(here)
    print("\n".join(lines))
    s = (b["tick"] - a["tick"]) / 60.0
    made = {f["x"]: f["made"] for f in a["f"]}
    rates = sorted((f["x"], (f["made"] - made.get(f["x"], 0)) / s, f["fluid"]) for f in b["f"])
    for fx, rate, fluid in rates:
        print(f"foundry at x={fx}: {rate:.2f} gears/s over {s:.1f} s, box 1 holds {fluid}")
    checks = next((ln for ln in lines if "report_checks" in ln), "")
    got = {"learned": bool(ov) and "4 fluid boxes" in "\n".join(lines),
           "connected": "12 connected, 0 open, 0 unrouted" in checks,
           "three foundries": len(rates) == 3,
           "molten iron in each": all(fl == "molten-iron" for _x, _r, fl in rates),
           "first at the model's 6/s": bool(rates) and abs(rates[0][1] - 6.0) < 0.3,
           "InfinityPipe pasted with its fluid": piped["pipes"] == ["molten-iron"]
           and piped["f"] == ["molten-iron"] * 3}
    print(f"piped: infinity pipes {piped['pipes']}, foundries' box 1 {piped['f']}")
    for k, v in got.items():
        print(f"{k}: {'OK' if v else 'NOT as designed'}")
    shutil.rmtree(run, True)
    return 0 if all(got.values()) else 1


#: 3.0 (Bob's adjustable inserters): a corner inserter (picks north, drops east), a plain
#: inserter reaching 1 west and 2 east (bob-long-inserters-1's range), and one with no vectors
BOBINS = """\
fkp 1 factory bi
size 20x8
e box/a wooden-chest 2.5,2.5
e ~n/i0 inserter 2.5,3.5 N net=n pick=0,-1 drop=1,0
e box/b wooden-chest 3.5,3.5
e box/c wooden-chest 6.5,2.5
e ~n/i1 inserter 7.5,2.5 W net=n pick=-1,0 drop=2,0
e box/d wooden-chest 9.5,2.5
e box/e wooden-chest 12.5,2.5
e ~n/i2 inserter 12.5,3.5 N net=n
e box/f wooden-chest 12.5,4.5
"""
_BOB_BASE = """
local s, f = game.get_surface('lab'), game.forces['lab']
local tiles = {}
for x = -30, 30 do for y = -30, 30 do tiles[#tiles + 1] = {name = 'sand-3', position = {x, y}} end end
s.set_tiles(tiles)
local eei = s.create_entity{name = 'electric-energy-interface', position = {-20, -20}, force = f}
eei.electric_buffer_size = 1e12
eei.power_production = 1e9
eei.energy = 1e12
s.create_entity{name = 'substation', position = {-17, -20}, force = f}
s.create_entity{name = 'substation', position = {-17, -4}, force = f}
local rp = s.create_entity{name = 'roboport', position = {-12, -10}, force = f}
rp.insert{name = 'construction-robot', count = 30}
local st = s.create_entity{name = 'storage-chest', position = {-8.5, -12.5}, force = f}
for _, n in pairs({'wooden-chest', 'inserter'}) do st.insert{name = n, count = 20} end
rcon.print('ok')"""
_BOB_READ = """
local s = game.get_surface('lab')
local o = {}
for _, e in pairs(s.find_entities_filtered{area = {{-2, -2}, {22, 12}}, type = 'inserter'}) do
  local p, q, d = e.pickup_position, e.drop_position, e.position
  o[#o + 1] = string.format('%s %.1f,%.1f dir %d pick %g,%g drop %.2f,%.2f', e.name, d.x, d.y,
    e.direction, p.x - d.x, p.y - d.y, q.x - d.x, q.y - d.y)
end
table.sort(o)
rcon.print(helpers.table_to_json(o))"""


def check_bobinserters():
    """3.0 (Bob's adjustable inserters, PLAN-BOB-INSERTERS): on a Sea Block server (its mods from
    C:\\fk-mods\\sb-mods), robots build a pasted corner inserter, a range-2 plain inserter and a
    plain one, and one single ghost (the refused-paste path) with vectors; each stands with the
    design's vectors, a diff finds all ok and no setting changed, and the area's blueprint reads
    back as the design's ``pick``/``drop``. Then a hand edit of the plain one's drop: the diff
    names it, and a paste of the design sets it back (or says it doesn't)."""
    import json
    from fkcore import apply as applymod, codec, compose, fkp
    from fkcore.catalog import Catalog
    env = {k: os.environ.get(k) for k in ("FK_PACK", "FK_LEARNED")}
    os.environ["FK_PACK"], os.environ["FK_LEARNED"] = "seablock", ""
    try:
        cat, s, f = Catalog.load(), "lab", "lab"
        watch = {"plots": "keep", "sanctioned": "mark 2h", "notify": "off"}
        lay = fkp.loads(BOBINS)
        v1 = compose.compose(fkp.loads("fkp 1 surface lab\nplot bi at 0,0 rot 0 size 20x8\n"),
                             {"bi": lay}, cat)
        area = (-2, -2, 22, 12)
        alone = codec.entity_json({"src": "lab:alone/i3", "name": "inserter", "x": 16.5, "y": 3.5,
                                   "direction": 0, "attrs": {"pick": "0,-1", "drop": "1,0"}}, 1)
        with LaptopServer("bobins", scenario="fk-play", mods=(),
                          mod_dir=os.environ.get("FK_SB_MODS", r"C:\fk-mods\sb-mods"),
                          boot_s=150) as srv:
            with srv.rcon() as r:
                r.lua(link.lua_generate_area(s, f, (-64, -64, 64, 64)))
                print("base:", r.lua(_BOB_BASE).strip())
                rep = applymod.apply(r, v1, cat, mode="play", force=f, policy=watch)
                print("\n".join(rep.lines()))
                print("single ghost:", link.ghosts(r, s, f, [alone]))
                left, secs = _robots_wait(r, area)
                print(f"robots built it: {left} left after {secs:.0f} game s")
                built = json.loads(r.lua(_BOB_READ).strip())
                for line in built:
                    print("  ", line)
                d1 = applymod.diff(r, v1, cat, area, watch, force=f, own=rep.own)
                verdicts = {}
                for v in d1.verdicts:
                    verdicts[v.verdict] = verdicts.get(v.verdict, 0) + 1
                print("a diff after the robots:", verdicts, [x.line() for x in d1.settings])
                bp = r.lua("local s = game.get_surface('lab') local inv = game.create_inventory(1) "
                           "inv.insert{name = 'blueprint'} inv[1].create_blueprint{surface = s, "
                           "force = 'lab', area = {{-2, -2}, {22, 12}}} "
                           "rcon.print(inv[1].export_stack()) inv.destroy()").strip()
                rows, _d, _w = codec.parse_blueprint(bp)
                back = {(r_["x"], r_["y"]): {k: v for k, v in r_["attrs"].items()
                                             if k in ("pick", "drop")}
                        for r_ in rows if r_["name"] == "inserter"}
                print("read back:", back)
                r.lua("local s = game.get_surface('lab') local i = s.find_entity('inserter', {12.5, 3.5}) "
                      "i.drop_position = {13.7, 3.5} rcon.print('ok')")
                d2 = applymod.diff(r, v1, cat, area, watch, force=f, own=rep.own)
                hand = [x.line() for x in d2.settings]
                print("a diff after a hand edit of i2's drop:", hand)
                rep2 = applymod.apply(r, v1, cat, mode="play", force=f, policy=watch, own=rep.own)
                print("\n".join(rep2.lines()))
                _robots_wait(r, area)
                after = json.loads(r.lua(_BOB_READ).strip())
                print("after a paste of the design:", [x for x in after if "12.5,3.5" in x])
    finally:
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    want = {(2.5, 3.5): {"pick": "0,-1", "drop": "1,0"}, (7.5, 2.5): {"pick": "-1,0", "drop": "2,0"},
            (12.5, 3.5): {}, (16.5, 3.5): {"pick": "0,-1", "drop": "1,0"}}
    got = {"built": left == 0,
           "vectors stand": any("2.5,3.5 dir 0 pick 0,-1 drop 1.20,0.00" in x for x in built)
           and any("7.5,2.5 dir 12 pick -1,0 drop 2.20,0.00" in x for x in built)
           and any("16.5,3.5 dir 0 pick 0,-1 drop 1.20,0.00" in x for x in built),
           "diff all ok": verdicts.get("ok") == len(v1.entities) and not d1.settings,
           "read back as designed": back == want,
           "hand edit named": len(hand) == 1 and "vectors" not in hand[0] and "drop=1,0" in hand[0],
           "paste sets it back": any("12.5,3.5 dir 0 pick 0,-1 drop 0.00,1.20" in x for x in after)}
    for k, v in got.items():
        print(f"{k}: {'OK' if v else 'NOT as designed'}")
    return 0 if all(got.values()) else 1


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "chat"
    raise SystemExit({"chat": check_chat, "own": check_own, "ghosts": check_ghosts,
                      "turned": check_turned, "health": check_health,
                      "settings": check_settings, "defaults": check_defaults,
                      "robots": check_robots, "lab": check_lab,
                      "capital": check_capital, "fixes": check_fixes,
                      "vision": check_vision, "stats": check_stats,
                      "circuits": check_circuits,
                      "fluidports": check_fluidports, "domains": check_domains,
                      "powershed": check_powershed, "drops": check_drops,
                      "machines": check_machines,
                      "recipeboxes": check_recipe_boxes,
                      "bobinserters": check_bobinserters}[what]())
