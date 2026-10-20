"""python -m fkcore <command> ...  (each command is one contained tool; nothing touches the game)

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
    sense GAME_DIR CAPTURE.json --area X0,Y0,X1,Y1 [--write-marks]
                                          the layout vs a captured scene inside the area only
    split-to-chest GAME_DIR FACTORY NET NAME --at X,Y [--requester --item I [--rate R]]
                                          a chest joins NET as one more endpoint; only NET
                                          is re-routed by the next build

  with the game link (FK_LINK=on, on the game host):
    chat GAME_DIR [--all]                 the chat lines since the last read (--all: the journal)
    say TEXT...                           one line in the game chat, as [agent]
    poll GAME_DIR                         what every agent command ends with: new chat lines, and
                                          the game's new and still-open alerts once fkcore.alerts
                                          is built
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


def _look(a, cat):
    if a.source == "world":
        print("look --source world reads the game; this toolkit is offline", file=sys.stderr)
        return 2
    surfaces = [f for f in sorted(os.listdir(a.game)) if f.endswith(".surface")]
    if not surfaces:
        print(f"error: no .surface file in {a.game}", file=sys.stderr)
        return 2
    sf = surfacemod.load(os.path.join(a.game, surfaces[0]))
    lay_path = os.path.join(a.game, f"{sf.name}.fkp")
    surface_lay = fkp.load(lay_path) if os.path.exists(lay_path) else surfacemod.floorplan(sf)
    factories = {}
    for p in sf.places.values():
        path = os.path.join(a.game, f"{p.module}.fkp")
        if os.path.exists(path):
            lay = fkp.load(path)
            lay.name = p.factory
            factories[p.factory] = lay
    s = compose.compose(surface_lay, factories, cat)
    box = tuple(int(v) for v in a.area.split(",")) if a.area else None
    print(f"look {sf.name} --source design: {len(s.plots)} plots, {len(s.entities)} entities, "
          f"{len(s.problems)} invariant problems (. plot, : claim, ! mark, blank sanctioned)")
    print(compose.render(s, cat, box))
    return 0


def _composed(game, cat):
    surfaces = [f for f in sorted(os.listdir(game)) if f.endswith(".surface")]
    if not surfaces:
        raise SystemExit(f"error: no .surface file in {game}")
    sf = surfacemod.load(os.path.join(game, surfaces[0]))
    lay_path = os.path.join(game, f"{sf.name}.fkp")
    surface_lay = fkp.load(lay_path) if os.path.exists(lay_path) else surfacemod.floorplan(sf)
    factories = {}
    for p in sf.places.values():
        path = os.path.join(game, f"{p.module}.fkp")
        if os.path.exists(path):
            lay = fkp.load(path)
            lay.name = p.factory
            factories[p.factory] = lay
    return sf, surface_lay, lay_path, compose.compose(surface_lay, factories, cat)


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


def _game_link():
    """The game link for a command that needs it: only with FK_LINK=on (as the flow)."""
    from . import link
    if os.environ.get("FK_LINK", "off").lower() != "on":
        print("this command uses the game link: run it on the game host with FK_LINK=on",
              file=sys.stderr)
        return None
    try:
        return link.Rcon()
    except (OSError, link.LinkError) as exc:
        print(f"no game link: {exc}", file=sys.stderr)
        return None


def _talk(a):
    from . import chat
    r = _game_link()
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
            try:
                from . import alerts
            except ImportError:
                alerts = None
            if alerts is not None and hasattr(alerts, "poll"):
                lines = alerts.poll(r, a.game) + lines
        print("\n".join(lines) if lines else ("chat: nothing new" if a.cmd == "chat" else ""),
              end="\n" if lines or a.cmd == "chat" else "")
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
    ch = sub.add_parser("chat")
    ch.add_argument("game")
    ch.add_argument("--all", action="store_true")
    sy = sub.add_parser("say")
    sy.add_argument("text", nargs="+")
    po = sub.add_parser("poll")
    po.add_argument("game")
    a = ap.parse_args(argv)
    if a.cmd in ("chat", "say", "poll"):
        return _talk(a)
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
