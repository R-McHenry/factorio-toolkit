"""python -m fkcore <command> ...  (each command is one contained tool; nothing touches the game)

    check FILE.fk                         netlist checks (report lines, never a gate)
    rates FILE.fk [--unbounded NET,...] [--share appetite|level] [--chain INST,...]
                                          the nominal rate model and its asserts
    layout FILE.fk [--render]             expand placed instances into FILE.fkp (the writer
                                          refuses a layout that breaks an invariant)
    explain FILE.fk INST                  one instance as a template and as entities and nets
    unfold FILE.fk INST                   INST becomes a Literal; .fk and .fkp rewritten, keys kept
    render FILE.fkp                       ASCII of a factory layout
"""
from __future__ import annotations

import argparse
import os
import sys

from . import compose, expand, fkp, rates
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
    a = ap.parse_args(argv)
    cat = Catalog.load()

    if a.cmd == "render":
        print(_render(fkp.load(a.file), cat))
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
