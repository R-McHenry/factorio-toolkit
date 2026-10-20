"""lab_sense: the in-game checks of the live look, notify and the alert push, on the lab surface.

Run on the game host from a deployed v5 dir, after ``fk build games/lab-sense/lab.build.fkb`` has
applied the game there:  ``python3 tools/lab_sense.py [--steps look,alerts,reads] [--force F]``.
Everything stands in the sensing worker's region of the lab surface (x 300..420, y 400..560);
each build is announced in game chat; every game call is one short RCON command (the link
refuses Lua that registers anything); everything placed is removed again.

Steps:
  look    two foreign belts with no key (one in sanctioned space, one in a plot next to a net),
          then the looks: notify nearby, --watch strict, the surface's policy with
          --write-marks (notify all pushes), and once more (quiet); the belts are removed.
  alerts  on ``--force`` (default lab): a wooden chest under attack (a hit every 3 s) and a
          programmable speaker with an alert (signal-A > 0 from a constant combinator, powered by
          an energy interface). The tracker polls: just built (ALERT x2), 21 s on (REMINDER x2
          with the game's ``remind 20s``), causes removed, 11 s later (CLEARED x2: the game keeps
          an alert about 10 s after its last raise), and once more (quiet). With ``--force
          player`` while the player force's only player is offline, this is the open question of
          CORE-V1 §13: does an offline player's panel get alerts?
  reads   the free reads: stats (1min, and 10min for three items) and chart.

Found with it (2026-10-20): the game drops ``entity_under_attack`` about 10 s after the last hit
and ``entity_destroyed`` after about 30 s; a speaker's ``custom`` alert is raised again every
update while its condition holds (its tick moves) and stays about 10 s after.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from fkcore import alerts, freereads, link, look  # noqa: E402
from fkcore.catalog import Catalog  # noqa: E402

GAME = os.path.join(os.path.dirname(HERE), "games", "lab-sense")
AREA = (305, 415, 353, 449)
SANCTIONED = (307.5, 430.5)
RIG_X, RIG_Y = 380, 530                 # the alert rig: x 380..400, y RIG_Y-2..RIG_Y+8


def say(r, text):
    r.lua(link.lua_say("[fk5 sense] " + text))


def fix_tile(s):
    """A free tile inside a plot next to a route belt: a foreign belt there looks like a fix."""
    for key in sorted(s.entities):
        e = s.entities[key]
        if "/~" not in key or e.name != "transport-belt":
            continue
        for tx, ty in e.tiles:
            for nx, ny in ((tx, ty - 1), (tx, ty + 1), (tx - 1, ty), (tx + 1, ty)):
                if (nx, ny) not in s.tiles and s.whose(nx, ny)[0] == "plot":
                    return nx, ny
    raise SystemExit("no free plot tile next to a route")


def step_look(r, cat, a):
    _sf, _lay, _path, s = look.composed(GAME, cat)
    fx, fy = fix_tile(s)
    belts = [SANCTIONED, (fx + 0.5, fy + 0.5)]
    say(r, f"placing two foreign belts (no key, no player) at {int(SANCTIONED[0])},"
           f"{int(SANCTIONED[1])} (sanctioned) and {fx},{fy} (a plot, next to a route)")
    r.lua("local s = game.get_surface('lab') "
          + " ".join(f"s.create_entity{{name = 'transport-belt', position = {{{x}, {y}}}, "
                     f"direction = defines.direction.{d}, force = 'lab'}}"
                     for (x, y), d in zip(belts, ("east", "south"))) + " rcon.print('ok')")
    try:
        for title, kw in (("notify nearby", {"notify": "nearby"}),
                          ("strict", {"notify": "nearby", "watch": "strict"}),
                          ("the surface's policy, --write-marks", {"write_marks": True}),
                          ("again", {})):
            lk = look.run(r, GAME, cat, AREA, **kw)
            print(f"[look] {title}: {lk.rep.counts()}, {len(lk.rep.changes)} changes, "
                  f"{len(lk.rep.marks)} new marks {[m.name for m in lk.rep.marks]}, "
                  f"{len(lk.pushed)} pushed, {lk.wrote} written")
    finally:
        say(r, "removing the two foreign test belts")
        r.lua("local s = game.get_surface('lab') local n = 0 for _, p in pairs({"
              + ", ".join(f"{{{x}, {y}}}" for x, y in belts)
              + "}) do local b = s.find_entity('transport-belt', p) if b and b.destroy() then "
                "n = n + 1 end end rcon.print(n)")


def _rig_lua(force, y):
    return f"""
local s = game.get_surface('lab')
local F, y = '{force}', {y}
local chest = s.create_entity{{name = 'wooden-chest', position = {{385.5, y + 0.5}}, force = F}}
chest.damage(10, 'enemy')
s.create_entity{{name = 'medium-electric-pole', position = {{390.5, y + 2.5}}, force = F}}
local ei = s.create_entity{{name = 'electric-energy-interface', position = {{393, y + 3}}, force = F}}
ei.power_production = 100000
ei.electric_buffer_size = 100000
local sp = s.create_entity{{name = 'programmable-speaker', position = {{390.5, y + 0.5}}, force = F}}
sp.alert_parameters = {{show_alert = true, show_on_map = true, icon_signal_id = {{type = 'item', name = 'iron-plate'}}, alert_message = '[fk5 sense] speaker test (' .. F .. ' force)'}}
sp.get_or_create_control_behavior().circuit_condition = {{comparator = '>', first_signal = {{type = 'virtual', name = 'signal-A'}}, constant = 0}}
local cc = s.create_entity{{name = 'constant-combinator', position = {{391.5, y + 0.5}}, force = F}}
local cb = cc.get_or_create_control_behavior()
local sec = cb.get_section(1) or cb.add_section()
sec.set_slot(1, {{value = {{type = 'virtual', name = 'signal-A', quality = 'normal'}}, min = 1}})
local wired = cc.get_wire_connector(defines.wire_connector_id.circuit_red, true).connect_to(sp.get_wire_connector(defines.wire_connector_id.circuit_red, true), false)
rcon.print(tostring(wired))
"""


def _clean_rig(r, force, y):
    box = f"{{{{{RIG_X}, {y - 2}}}, {{{RIG_X + 20}, {y + 8}}}}}"
    return r.lua(f"local s = game.get_surface('lab') local n = 0 "
                 f"for _, e in pairs(s.find_entities_filtered{{area = {box}, force = '{force}'}}) "
                 f"do if e.destroy() then n = n + 1 end end "
                 f"for _, e in pairs(s.find_entities_filtered{{area = {box}, type = "
                 f"{{'corpse', 'entity-ghost'}}}}) do if e.destroy() then n = n + 1 end end "
                 f"rcon.print(n)").strip()


def _poll(r, force, title):
    p = alerts.check(r, GAME, force)
    who = ", ".join(f"{q.get('name')} ({'on' if q.get('connected') else 'off'}line)"
                    for q in p.read.players) or "no players"
    print(f"[alerts] {title}: tick {p.read.tick}, {force}: {who}; panel {len(p.read.alerts)}; "
          f"new {len(p.new)}, reminders {len(p.reminders)}, cleared {len(p.cleared)}")
    for line in p.lines:
        print(f"           {line}")
    return p


def step_alerts(r, cat, a):
    force, y = a.force, RIG_Y
    _clean_rig(r, force, y)
    _poll(r, force, "before")
    say(r, f"alert test on the {force} force at 385..394,{y}..{y + 4}: a wooden chest under "
           "attack and a programmable speaker with an alert")
    try:
        r.lua(_rig_lua(force, y))
        time.sleep(1)
        _poll(r, force, "just built")
        t0 = time.time()
        while time.time() - t0 < 21:                   # the attack goes on: a hit every 3 s
            time.sleep(3)
            r.lua(f"local c = game.get_surface('lab').find_entity('wooden-chest', "
                  f"{{385.5, {y + 0.5}}}) if c then c.damage(5, 'enemy') end rcon.print('hit')")
        _poll(r, force, "21 s on")
        say(r, "alert test: removing the causes (the attacked chest, the constant combinator)")
        r.lua(f"local s = game.get_surface('lab') "
              f"for _, n in pairs({{{{'wooden-chest', 385.5}}, {{'constant-combinator', 391.5}}}}) do "
              f"local e = s.find_entity(n[1], {{n[2], {y + 0.5}}}) if e then e.destroy() end end "
              f"rcon.print('ok')")
        _poll(r, force, "causes removed")
        time.sleep(11)
        _poll(r, force, "11 s later")
        _poll(r, force, "once more")
    finally:
        print(f"[alerts] cleaned up {_clean_rig(r, force, y)} entities")


def step_reads(r, cat, a):
    from fkcore import surface as surfacemod
    from fkcore.apply import force_for
    sf = surfacemod.load_game(GAME)
    force = force_for(sf.mode)
    for line in freereads.stats_lines(freereads.stats(r, force, sf.name)):
        print(f"[reads] {line}")
    for line in freereads.stats_lines(freereads.stats(r, force, sf.name, ["iron-plate", "coal",
                                                                          "iron-ore"], "10min")):
        print(f"[reads] {line}")
    for line in freereads.chart_lines(freereads.chart(r, force, sf.name)):
        print(f"[reads] {line}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", default="look,alerts,reads")
    ap.add_argument("--force", default="lab", help="the alert rig's force (lab or player)")
    a = ap.parse_args(argv)
    cat = Catalog.load()
    with link.Rcon() as r:
        for step in a.steps.split(","):
            {"look": step_look, "alerts": step_alerts, "reads": step_reads}[step](r, cat, a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
