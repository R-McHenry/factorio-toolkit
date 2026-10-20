"""python -m fkcore <command> ...  (each command is one contained tool; only the flow's diff and
apply, look --source world, alerts, stats and chart use the game link, and only with FK_LINK=on)

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
"""
from __future__ import annotations

import argparse
import os
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
    from . import scene, sense
    sf, surface_lay, lay_path, s = _composed(a.game, cat)
    with open(a.capture, encoding="utf-8") as fh:
        live = scene.from_capture(json.load(fh))
    area = [int(v) for v in a.area.split(",")]
    rep = sense.sense(s, live, cat, area, sf)
    print("\n".join(rep.lines()))
    if a.write_marks and rep.marks:
        for m in rep.marks:
            surface_lay.marks[m.name] = m
        fkp.save(surface_lay, lay_path, cat)
        print(f"wrote {len(rep.marks)} mark(s) into {os.path.basename(lay_path)}")
    return 0


def _render(lay, cat):
    w, h = lay.size
    surface = fkp.loads(f"fkp 1 surface view\nplot {lay.name} at 0,0 rot 0 size {w}x{h}\n")
    return compose.render(compose.compose(surface, {lay.name: lay}, cat), cat, (0, 0, w, h))


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
    a = ap.parse_args(argv)
    cat = Catalog.load()

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
