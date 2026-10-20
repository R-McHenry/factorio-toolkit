"""python -m fkcore <command> ...  (each command is one contained tool; only the flow's diff and
apply, look --source world, alerts, stats, chart, read-terrain and the game-link commands below
use the game link, and only with FK_LINK=on)

    check FILE.fk                         netlist checks (report lines, never a gate)
    rates FILE.fk [--unbounded NET,...] [--share appetite|level] [--chain INST,...]
                                          the nominal rate model and its asserts
    layout FILE.fk [--render]             expand placed instances into FILE.fkp (the writer
                                          refuses a layout that breaks an invariant)
    explain FILE.fk INST                  one instance as a template and as entities and nets
    unfold FILE.fk INST                   INST becomes a Literal; .fk and .fkp rewritten, keys kept
    render FILE.fkp                       ASCII of a factory layout
    build SCRIPT.fkb [--from STEP] [--to STEP]
                                          run the flow; reports in out/, checkpoints out/<step>/
    look GAME_DIR [--source design] [--area X0,Y0,X1,Y1]
                                          the composed surface of a game codebase, as designed
    look GAME_DIR --source world [--area X0,Y0,X1,Y1] [--notify nearby|all|off]
         [--watch ACTION] [--write-marks]
                                          the layout vs the game inside the area: verdicts,
                                          changes here, design and live renders; notify all
                                          pushes the changes to chat and out/inbox.txt
    sense GAME_DIR CAPTURE.json --area X0,Y0,X1,Y1 [--write-marks]
                                          the layout vs a captured scene inside the area only
    alerts GAME_DIR [--force F]           the game's alert panel: new alerts, reminders (the
                                          surface file's remind), cleared ones; state in
                                          out/alerts.json; pushed to chat when notify is all
    stats GAME_DIR [--items A,B] [--window 1min|10min|1h] [--force F]
                                          production and consumption per item on the surface
                                          (a free read, never an alert)
    chart GAME_DIR [--force F]            the surface's charted chunks: count and bounding box
                                          (a free read, never an alert)
    split-to-chest GAME_DIR FACTORY NET NAME --at X,Y [--requester --item I [--rate R]]
                                          a chest joins NET as one more endpoint; only NET
                                          is re-routed by the next build

    merge GAME_DIR A,B --into C           two factories become one (source, layout, plots)
    insert GAME_DIR COMPONENT_DIR NAME --into C --at X,Y
                                          a component copied into a factory
    chests-to-net GAME_DIR FACTORY PROVIDER REQUESTER [--net link]
                                          a robot link (two chests) becomes one net
    net-to-chests GAME_DIR FACTORY NET --provider P --requester R
                                          a net becomes a robot link (a full decouple)

  with the game link (FK_LINK=on, on the game host):
    measure GAME_DIR --area X0,Y0,X1,Y1 [--seconds 30]
                                          what the machines there make, against the model
    fresh GAME_DIR --area X0,Y0,X1,Y1     belts there that carry items their net doesn't are
                                          taken up by robots; the next build lays them fresh
    adopt GAME_DIR X,Y[;X,Y...] --into FACTORY/NET
                                          carriers placed by hand become part of a net's route
    chat GAME_DIR [--all]                 the chat lines since the last read (--all: the journal)
    say TEXT...                           one line in the game chat, as [agent]
    poll GAME_DIR                         what every agent command ends with: the game's alerts
                                          (new, reminders, cleared; grouped), new chat lines and
                                          the research state (loud when nothing researches)
    lua GAME_DIR CODE | --file F          run a Lua chunk in the game (RCON); its rcon.print is the
                                          reply. For reading and investigating; the link refuses
                                          Lua that registers handlers or commands (unjoinable saves)
    research GAME_DIR [TECH...]           queue research; without a name, what can be researched
                                          now and its cost (a free read)
    tech GAME_DIR NAME...                 a technology, or what unlocks a recipe or item: cost or
                                          trigger, prerequisites (a free read)
    recipes GAME_DIR [NAME...] [--enabled]
                                          the locked recipes (or the enabled ones) and what
                                          unlocks each (a free read)
    read-terrain GAME_DIR --surface S --area X0,Y0,X1,Y1 [--name map]
                                          a free read of the bare world (ore, water, cliffs;
                                          trees and rocks counted) into GAME_DIR/<name>.terrain.json
"""
from __future__ import annotations

import argparse
import os
import re
import sys

from . import compose, expand, fkp, flow, rates
from . import surface as surfacemod
from .catalog import Catalog
from .elaborate import ElabError, elaborate_file
from .lang import FkSyntaxError


def _fkp_path(path):
    return os.path.splitext(path)[0] + ".fkp"


def _flat(path, layout=None):
    if layout is None and os.path.exists(_fkp_path(path)):
        layout = fkp.load(_fkp_path(path))
    try:
        return elaborate_file(path, Catalog.load(), layout=layout)
    except (FkSyntaxError, ElabError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _area(text):
    if not text:
        return None
    parts = [int(v) for v in text.split(",")]
    if len(parts) != 4 or parts[2] <= parts[0] or parts[3] <= parts[1]:
        raise SystemExit(f"error: an area is X0,Y0,X1,Y1 with X1 > X0 and Y1 > Y0, got {text}")
    return tuple(parts)


def _game_link(what):
    """The game link, or None after saying why (it is used only with FK_LINK=on)."""
    from . import link
    r, why = link.open_from_env()
    if r is None:
        print(f"{what}: skipped, no game link ({why})")
    return r


def _world(a, cat, what, body):
    """Run ``body(r)`` -> lines with the game link open; errors are one line, never a trace."""
    from . import link, look
    r = _game_link(what)
    if r is None:
        return 2
    try:
        with r:
            lines = body(r)
    except (look.LookError, surfacemod.SurfaceError, link.LinkError, OSError) as exc:
        print(f"error: {what}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0


def _look_world(a, cat):
    from . import look
    area = _area(a.area)
    return _world(a, cat, "look --source world", lambda r: look.run(
        r, a.game, cat, area, a.notify, a.watch, a.write_marks).lines())


def _alerts(a, cat):
    from . import alerts
    return _world(a, cat, "alerts", lambda r: alerts.check(r, a.game, a.force).report())


def _free_read(a, cat):
    from . import freereads
    from .apply import force_for
    try:
        sf = surfacemod.load_game(a.game)
    except (surfacemod.SurfaceError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    force = a.force or force_for(sf.mode)
    if a.cmd == "chart":
        return _world(a, cat, "chart", lambda r: freereads.chart_lines(
            freereads.chart(r, force, sf.name)))
    if a.window not in freereads.WINDOWS:
        print(f"error: --window is one of {', '.join(freereads.WINDOWS)}", file=sys.stderr)
        return 2
    items = [i for i in (a.items or "").split(",") if i] or None
    return _world(a, cat, "stats", lambda r: freereads.stats_lines(
        freereads.stats(r, force, sf.name, items, a.window)))


def _look(a, cat):
    if a.source == "world":
        return _look_world(a, cat)
    from . import look
    try:
        sf, _lay, _path, s = look.composed(a.game, cat)
    except surfacemod.SurfaceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    box = _area(a.area)
    print(f"look {sf.name} --source design: {len(s.plots)} plots, {len(s.entities)} entities, "
          f"{len(s.problems)} invariant problems (. plot, : claim, ! mark, blank sanctioned)")
    print(compose.render(s, cat, box))
    return 0


def _composed(game, cat):
    from . import look
    try:
        return look.composed(game, cat)
    except surfacemod.SurfaceError as exc:
        raise SystemExit(f"error: {exc}") from None


def _sense(a, cat):
    import json
    from . import own, scene, sense
    sf, surface_lay, lay_path, s = _composed(a.game, cat)
    with open(a.capture, encoding="utf-8") as fh:
        live = scene.from_capture(json.load(fh))
    area = [int(v) for v in a.area.split(",")]
    rep = sense.sense(s, live, cat, area, sf, own=own.load(a.game, sf.name))
    print("\n".join(rep.lines()))
    if a.write_marks and rep.marks:
        for m in rep.marks:
            surface_lay.marks[m.name] = m
        fkp.save(surface_lay, lay_path, cat)
        print(f"wrote {len(rep.marks)} mark(s) into {os.path.basename(lay_path)}")
    return 0


def _talk(a):
    from . import chat
    r = _game_link(a.cmd)
    if r is None:
        return 2
    with r:
        if a.cmd == "say":
            chat.say(r, " ".join(a.text))
            return 0
        if a.cmd == "chat" and a.all:
            got = chat.read(r, 0)
            lines = [f"chat {m.get('name') or '?'}: {m.get('message', '')}" for m in got["messages"]]
        else:
            lines = chat.new_lines(r, a.game)
        if a.cmd == "poll":
            from . import alerts
            lines = alerts.poll(r, a.game) + lines + [_research_footer(r, a.game)]
        print("\n".join(lines) if lines else ("chat: nothing new" if a.cmd == "chat" else ""),
              end="\n" if lines or a.cmd == "chat" else "")
    return 0


def _force_surface(game):
    from .apply import force_for
    sf = surfacemod.load_game(game)
    return getattr(sf, "force", None) or force_for(sf.mode), sf.name


def _research_footer(r, game):
    """The research bar a player always sees (a free read): one line, loud when nothing moves."""
    from . import supply
    try:
        force, surface = _force_surface(game)
        return supply.research_line(supply.read(r, force, surface).research)
    except Exception as exc:          # a footnote must never break the command that asked
        return f"research: not read ({type(exc).__name__}: {exc})"


def _lua(a):
    """A Lua chunk through the link: the player's own probe (Rory, 2026-10-20: the player may write
    code and read the game with Lua to investigate). The link still refuses Lua that registers a
    handler, a command or an interface: that made every save unjoinable on 2026-10-18.
    ``--file -`` reads the chunk from stdin (agent/fk.py sends it that way, 1.2)."""
    from . import link
    code = a.code
    if a.file == "-":
        code = sys.stdin.buffer.read().decode("utf-8")
    elif a.file:
        with open(a.file, encoding="utf-8") as fh:
            code = fh.read()
    if not code or not code.strip():
        print("error: lua needs CODE or --file F", file=sys.stderr)
        return 2
    r = _game_link("lua")
    if r is None:
        return 2
    with r:
        try:
            print(r.lua(code))
        except link.LinkError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    return 0


def _research(a):
    """research / tech / recipes: the research screen and the tech tree (v4's research, tech and
    recipes, through fkcore.supply)."""
    from . import supply
    r = _game_link(a.cmd)
    if r is None:
        return 2
    force, surface = _force_surface(a.game)
    with r:
        if a.cmd == "research" and a.techs:
            got = supply.add_research(r, force, surface, a.techs)
            added = list(got.get("added") or [])
            failed = list(got.get("failed") or [])
            if isinstance(got.get("added"), dict):
                added = list(got["added"].values())
            if isinstance(got.get("failed"), dict):
                failed = list(got["failed"].values())
            lines = [f"research: queued {', '.join(added) or 'nothing'}"]
            lines += [f"  not queued: {f}" for f in failed]
            if added:
                lines.append(supply.research_line(got.get("research")))
        elif a.cmd == "research":
            lines = supply.available_lines(supply.available(r, force, surface))
        elif a.cmd == "tech":
            lines = supply.tech_lines(supply.tech(r, force, a.names))
        else:
            lines = supply.recipe_lines(supply.recipes(r, force, a.names), a.enabled)
    print("\n".join(lines))
    return 0


def _rewire(a):
    from . import merge
    try:
        if a.cmd == "merge":
            ch = merge.merge(a.game, a.names.split(","), a.into)
        elif a.cmd == "insert":
            ch = merge.insert(a.game, a.component_dir, a.name, a.into,
                              tuple(int(v) for v in a.at.split(",")))
        elif a.cmd == "chests-to-net":
            ch = merge.chests_to_net(a.game, a.factory, a.provider, a.requester, a.net)
        else:
            ch = merge.net_to_chests(a.game, a.factory, a.net, a.provider, a.requester)
    except merge.MergeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(ch)
    return 0


def _flats_and_models(game, sf, cat):
    flats, models = {}, {}
    for p in sf.places.values():
        path = os.path.join(game, f"{p.module}.fk")
        lay_path = os.path.join(game, f"{p.module}.fkp")
        if not os.path.exists(path):
            continue
        flat = elaborate_file(path, cat, name=p.module,
                              layout=fkp.load(lay_path) if os.path.exists(lay_path) else None)
        flats[p.factory] = flat
        models[p.factory] = rates.solve(flat)
    return flats, models


def _measure(a, cat):
    from . import measure
    r = _game_link("measure")
    if r is None:
        return 2
    sf, _surface_lay, _lay_path, s = _composed(a.game, cat)
    flats, models = _flats_and_models(a.game, sf, cat)
    area = tuple(int(v) for v in a.area.split(","))
    with r:
        got = measure.measure(r, s, cat, area, flats, models, a.seconds)
    print("\n".join(got.lines()))
    return 0


def _adopt(a, cat):
    import math
    from . import adopt, link, scene
    factory, _, net = a.into.partition("/")
    if not net:
        print("error: --into FACTORY/NET", file=sys.stderr)
        return 2
    tiles = [tuple(int(float(v)) for v in t.split(",")) for t in a.tiles.replace(";", " ").split()]
    sf, surface_lay, lay_path, s = _composed(a.game, cat)
    place = next((p for p in sf.places.values() if p.factory == factory), None)
    if place is None or factory not in surface_lay.plots:
        print(f"error: no factory {factory} on {sf.name}", file=sys.stderr)
        return 2
    r = _game_link("adopt")
    if r is None:
        return 2
    xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
    with r:
        live = scene.from_capture(link.snapshot(r, sf.name, (min(xs) - 1, min(ys) - 1,
                                                            max(xs) + 2, max(ys) + 2), "adopt"))
    things = [t for t in live["things"] if (math.floor(t["x"]), math.floor(t["y"])) in set(tiles)
              and not t["ghost"]]
    if len(things) != len(tiles):
        print(f"error: found {len(things)} built entities on {len(tiles)} tiles", file=sys.stderr)
        return 2
    fpath = os.path.join(a.game, f"{place.module}.fkp")
    lay = fkp.load(fpath)
    try:
        keys, covered = adopt.adopt(lay, surface_lay.plots[factory], things, net, cat,
                                    surface_lay.marks)
    except adopt.AdoptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    fkp.save(lay, fpath, cat)
    for name in covered:
        surface_lay.marks.pop(name, None)
    fkp.save(surface_lay, lay_path, cat)
    print(f"adopted into {factory}/{net}: {', '.join(keys)}"
          + (f"; marks cleared: {', '.join(covered)}" if covered else ""))
    return 0


def _read_terrain(a):
    """Read the bare world through the game link (FK_LINK=on) into <name>.terrain.json."""
    from . import link, terrain
    if os.environ.get("FK_LINK", "off").lower() != "on":
        print("read-terrain: skipped, FK_LINK is not on (FK_LINK=on uses the game link)",
              file=sys.stderr)
        return 2
    area = tuple(int(v) for v in a.area.split(","))
    if len(area) != 4 or area[2] <= area[0] or area[3] <= area[1]:
        print(f"error: --area X0,Y0,X1,Y1 with X1 > X0 and Y1 > Y0, got {a.area}", file=sys.stderr)
        return 2
    try:
        with link.Rcon() as r:
            data = terrain.read(r, a.surface, area)
    except (OSError, link.LinkError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    os.makedirs(a.game, exist_ok=True)
    path = os.path.join(a.game, f"{a.name}.terrain.json")
    terrain.save(data, path)
    print("\n".join(terrain.summary(terrain.from_dict(data), a.name)))
    print(f"wrote {path}")
    return 0


def _render(lay, cat):
    w, h = lay.size
    surface = fkp.loads(f"fkp 1 surface view\nplot {lay.name} at 0,0 rot 0 size {w}x{h}\n")
    return compose.render(compose.compose(surface, {lay.name: lay}, cat), cat, (0, 0, w, h))


def _glue(argv):
    """argparse reads ``--area -320,-288,256,288`` as two options: glue a coordinate list that
    starts with a minus to its flag (``--area=-320,...``)."""
    out, i = [], 0
    while i < len(argv):
        if argv[i] in ("--area", "--at") and i + 1 < len(argv) \
                and re.fullmatch(r"-\d+(,-?\d+)+", argv[i + 1]):
            out.append(f"{argv[i]}={argv[i + 1]}")
            i += 2
        else:
            out.append(argv[i])
            i += 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m fkcore", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("file")
    r = sub.add_parser("rates")
    r.add_argument("file")
    r.add_argument("--unbounded", default="")
    r.add_argument("--share", default="appetite", choices=("appetite", "level"))
    r.add_argument("--chain", default="")
    lo = sub.add_parser("layout")
    lo.add_argument("file")
    lo.add_argument("--render", action="store_true")
    for name in ("explain", "unfold"):
        p = sub.add_parser(name)
        p.add_argument("file")
        p.add_argument("inst")
    rd = sub.add_parser("render")
    rd.add_argument("file")
    b = sub.add_parser("build")
    b.add_argument("script")
    b.add_argument("--from", dest="frm")
    b.add_argument("--to")
    lk = sub.add_parser("look")
    lk.add_argument("game")
    lk.add_argument("--source", default="design", choices=("design", "world"))
    lk.add_argument("--area")
    lk.add_argument("--notify", choices=("nearby", "all", "off"))
    lk.add_argument("--watch", help="strict | keep | revert | mark DUR, or plots=A,sanctioned=B")
    lk.add_argument("--write-marks", action="store_true")
    fr = sub.add_parser("fresh")
    fr.add_argument("game")
    fr.add_argument("--area", required=True)
    al = sub.add_parser("alerts")
    al.add_argument("game")
    al.add_argument("--force")
    st = sub.add_parser("stats")
    st.add_argument("game")
    st.add_argument("--items")
    st.add_argument("--window", default="1min")
    st.add_argument("--force")
    ch = sub.add_parser("chart")
    ch.add_argument("game")
    ch.add_argument("--force")
    se = sub.add_parser("sense")
    se.add_argument("game")
    se.add_argument("capture")
    se.add_argument("--area", required=True)
    se.add_argument("--write-marks", action="store_true")
    sp = sub.add_parser("split-to-chest")
    sp.add_argument("game")
    sp.add_argument("factory")
    sp.add_argument("net")
    sp.add_argument("name")
    sp.add_argument("--at", required=True)
    sp.add_argument("--requester", action="store_true")
    sp.add_argument("--item")
    sp.add_argument("--rate")
    mg = sub.add_parser("merge")
    mg.add_argument("game")
    mg.add_argument("names")
    mg.add_argument("--into", required=True)
    ins = sub.add_parser("insert")
    ins.add_argument("game")
    ins.add_argument("component_dir")
    ins.add_argument("name")
    ins.add_argument("--into", required=True)
    ins.add_argument("--at", required=True)
    c2n = sub.add_parser("chests-to-net")
    c2n.add_argument("game")
    c2n.add_argument("factory")
    c2n.add_argument("provider")
    c2n.add_argument("requester")
    c2n.add_argument("--net", default="link")
    n2c = sub.add_parser("net-to-chests")
    n2c.add_argument("game")
    n2c.add_argument("factory")
    n2c.add_argument("net")
    n2c.add_argument("--provider", required=True)
    n2c.add_argument("--requester", required=True)
    me = sub.add_parser("measure")
    me.add_argument("game")
    me.add_argument("--area", required=True)
    me.add_argument("--seconds", type=float, default=30.0)
    ad = sub.add_parser("adopt")
    ad.add_argument("game")
    ad.add_argument("tiles")
    ad.add_argument("--into", required=True)
    ch = sub.add_parser("chat")
    ch.add_argument("game")
    ch.add_argument("--all", action="store_true")
    sy = sub.add_parser("say")
    sy.add_argument("text", nargs="+")
    po = sub.add_parser("poll")
    po.add_argument("game")
    lu = sub.add_parser("lua")
    lu.add_argument("game")
    lu.add_argument("code", nargs="?")
    lu.add_argument("--file")
    rs = sub.add_parser("research")
    rs.add_argument("game")
    rs.add_argument("techs", nargs="*")
    th = sub.add_parser("tech")
    th.add_argument("game")
    th.add_argument("names", nargs="+")
    rc = sub.add_parser("recipes")
    rc.add_argument("game")
    rc.add_argument("names", nargs="*")
    rc.add_argument("--enabled", action="store_true")
    rt = sub.add_parser("read-terrain")
    rt.add_argument("game")
    rt.add_argument("--surface", required=True)
    rt.add_argument("--area", required=True)
    rt.add_argument("--name", default="map")
    a = ap.parse_args(_glue(sys.argv[1:] if argv is None else list(argv)))
    if a.cmd in ("chat", "say", "poll"):
        return _talk(a)
    if a.cmd in ("research", "tech", "recipes"):
        return _research(a)
    if a.cmd == "lua":
        return _lua(a)
    if a.cmd == "read-terrain":
        return _read_terrain(a)
    cat = Catalog.load()
    if a.cmd in ("merge", "insert", "chests-to-net", "net-to-chests"):
        return _rewire(a)
    if a.cmd == "measure":
        return _measure(a, cat)
    if a.cmd == "adopt":
        return _adopt(a, cat)

    if a.cmd == "render":
        print(_render(fkp.load(a.file), cat))
        return 0
    if a.cmd == "build":
        try:
            code, _ctx = flow.run(a.script, a.frm, a.to, cat)
        except (flow.FlowError, surfacemod.SurfaceError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return code
    if a.cmd == "look":
        return _look(a, cat)
    if a.cmd == "alerts":
        return _alerts(a, cat)
    if a.cmd == "fresh":
        from . import fresh
        return _world(a, cat, "fresh", lambda r: fresh.run(r, a.game, cat, _area(a.area)))
    if a.cmd in ("stats", "chart"):
        return _free_read(a, cat)
    if a.cmd == "sense":
        return _sense(a, cat)
    if a.cmd == "split-to-chest":
        from . import merge
        at = tuple(int(v) for v in a.at.split(","))
        try:
            ch = merge.split_to_chest(a.game, a.factory, a.net, a.name, at,
                                      "requester" if a.requester else "provider", a.item, a.rate)
        except merge.MergeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(ch)
        return 0
    flat = _flat(a.file)
    if a.cmd in ("layout", "explain", "unfold"):
        previous = fkp.load(_fkp_path(a.file)) if os.path.exists(_fkp_path(a.file)) else None
        lay, notes = expand.expand_factory(flat, cat, previous)
        if a.cmd == "layout":
            try:
                fkp.save(lay, _fkp_path(a.file), cat)
            except fkp.InvariantError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"layout {flat.name}: {len(lay.insts)} instances, {len(lay.entities)} "
                  f"entities, {lay.size[0]}x{lay.size[1]}, 0 invariant failures -> "
                  f"{_fkp_path(a.file)}")
            for note in notes:
                print(f"  note {note}")
            if a.render:
                print(_render(lay, cat))
            return 0
        if a.inst not in flat.insts:
            print(f"error: no instance {a.inst}", file=sys.stderr)
            return 2
        if a.cmd == "explain":
            print(expand.explain(flat, lay, a.inst, cat))
            return 0
        with open(a.file, encoding="utf-8") as fh:
            src = fh.read()
        new_src, new_lay = expand.unfold(src, flat, lay, a.inst)
        fkp.save(new_lay, _fkp_path(a.file), cat)
        with open(a.file, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_src)
        print(f"unfold {a.inst}: now a Literal; {sum(1 for e in new_lay.entities.values() if e.owner == a.inst)} "
              "entities pinned, every key kept")
        return 0
    if a.cmd == "check":
        print(f"check {flat.name}: {len(flat.machines)} machines, {len(flat.nets)} nets, "
              f"{len(flat.checks)} check lines")
        for line in flat.checks:
            print(f"  {line}")
        return 0
    unbounded = [n for n in a.unbounded.split(",") if n]
    try:
        model = rates.solve(flat, share=a.share, unbounded=unbounded)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    title = flat.name + (f" (unbounded: {', '.join(unbounded)})" if unbounded else "")
    print(rates.report(model, title))
    for path in [p for p in a.chain.split(",") if p]:
        if path not in flat.insts:
            print(f"error: no instance {path}", file=sys.stderr)
            return 2
        print()
        print("\n".join("  " + line for line in rates.chain(model, path)))
    if flat.checks:
        print("\n  checks")
        for line in flat.checks:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
