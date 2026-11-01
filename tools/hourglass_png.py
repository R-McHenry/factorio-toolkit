"""hourglass_png: the hourglass bench's cases as PNG images, and as blueprint strings.

    python tools/hourglass_png.py OUT_DIR [--only NAME[,NAME]] [--scale PX]

Per case one image, three panels side by side: the m2m router, today's router and Rory's balancer
at the waist, each with its row of the bench's table. Belts are drawn with their heading, splitters
as one block across their two tiles, underground ends as U (in) and u (out), inserters as small
squares, producers red, consumers blue, the wall grey, the midline dotted. Each layout is also
written as a blueprint string (``CASE-ROUTER.txt``), for a blueprint renderer. Stdlib only.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import hourglass                                                  # noqa: E402
from fkcore import codec, fkp                                     # noqa: E402
from fkcore.catalog import Catalog                                # noqa: E402
from fkcore.png import Canvas, FONT_H, text_width                 # noqa: E402

BG = (24, 26, 30)
GRID = (34, 37, 42)
BELT = (214, 172, 46)
BELT_DARK = (120, 92, 18)
SPLIT = (232, 112, 40)
UG = (170, 128, 30)
INS = (90, 190, 110)
PROD = (210, 70, 70)
CONS = (70, 130, 220)
WALL = (110, 110, 115)
MID = (90, 90, 140)
TEXT = (225, 225, 225)
DIM = (150, 150, 160)

ROUTERS = ("m2m", "today", "balancer")


def _arrow(cv, x, y, s, d, rgb):
    """A small triangle pointing heading ``d`` (0 N, 1 E, 2 S, 3 W) in the tile at (x, y)."""
    c = s / 2
    for i in range(int(s * 0.35)):
        w = int(s * 0.35) - i
        if d == 0:
            cv.rect(x + c - w, y + s * 0.25 + i, 2 * w, 1, rgb)
        elif d == 2:
            cv.rect(x + c - w, y + s * 0.75 - i, 2 * w, 1, rgb)
        elif d == 1:
            cv.rect(x + s * 0.75 - i, y + c - w, 1, 2 * w, rgb)
        else:
            cv.rect(x + s * 0.25 + i, y + c - w, 1, 2 * w, rgb)


def panel(cv, ox, oy, m, cat, s):
    lay = m["layout"]
    _f, _l, bounds, blocked, mid = hourglass.build(m["case"], cat)
    x0, y0, x1, y1 = bounds
    for y in range(y0, y1):
        for x in range(x0, x1):
            px, py = ox + (x - x0) * s, oy + (y - y0) * s
            cv.rect(px, py, s - 1, s - 1, GRID)
            if (x, y) in blocked:
                cv.rect(px, py, s - 1, s - 1, WALL)
            elif x == mid and y % 2 == 0:
                cv.rect(px + s // 2 - 1, py, 2, s - 1, MID)
    for e in lay.entities.values():
        ts = list(fkp.tiles_of(cat, e))
        tx0, ty0 = min(t[0] for t in ts), min(t[1] for t in ts)
        tx1, ty1 = max(t[0] for t in ts) + 1, max(t[1] for t in ts) + 1
        px, py = ox + (tx0 - x0) * s, oy + (ty0 - y0) * s
        w, h = (tx1 - tx0) * s - 1, (ty1 - ty0) * s - 1
        d = int(e.dir or 0) // 4
        if e.name == "transport-belt":
            cv.rect(px + 1, py + 1, w - 2, h - 2, BELT)
            _arrow(cv, px, py, s, d, BELT_DARK)
        elif e.name == "splitter":
            cv.rect(px, py, w, h, SPLIT)
            cv.outline(px, py, w, h, (255, 190, 120))
            _arrow(cv, px, py, s, d, (90, 40, 10))
            if w > h:
                _arrow(cv, px + s, py, s, d, (90, 40, 10))
            else:
                _arrow(cv, px, py + s, s, d, (90, 40, 10))
        elif e.name == "underground-belt":
            cv.rect(px + 1, py + 1, w - 2, h - 2, UG)
            ch = "U" if e.attrs.get("ug") == "in" else "u"
            cv.text(px + (s - 5) // 2, py + (s - 7) // 2, ch, (30, 20, 0))
        elif "inserter" in e.name:
            q = max(2, s // 3)
            cv.rect(px + (s - q) // 2, py + (s - q) // 2, q, q, INS)
        elif e.key.startswith("p"):
            cv.rect(px, py, w, h, PROD)
        else:
            cv.rect(px, py, w, h, CONS)


def stats(m):
    return (f"{m['router']}: flow {m['maxflow']:.1f}/{m['demand']:.1f}  reach "
            f"{'yes' if m['reach'] and not m['failed'] else 'NO'}  waist {m['waist']}  "
            f"belts {m['belts']}  ug {m['ug']}  splitters {m['splitters']}  cost {m['cost']:.0f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("--only", default="")
    ap.add_argument("--scale", type=int, default=0, help="pixels a tile (12; 20 with --lanes)")
    ap.add_argument("--lanes", action="store_true",
                    help="draw every lane and its load (tools/lanes_png.py): CASE-lanes.png")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    cat = Catalog.load()
    s = a.scale or (20 if a.lanes else 12)
    if a.lanes:
        import lanes_png
    names = [n for n in hourglass.CASES if not a.only or n in a.only.split(",")]
    for name in names:
        ms = [hourglass.measure(name, cat, router=r) for r in ROUTERS]
        _f, _l, bounds, blocked, mid = hourglass.build(name, cat)
        if a.lanes:
            bounds = lanes_png.crop(bounds, [m["layout"] for m in ms], cat)
        pw, ph = (bounds[2] - bounds[0]) * s, (bounds[3] - bounds[1]) * s
        head = 3 * FONT_H + 8
        gap = 24
        width = max(len(ROUTERS) * pw + (len(ROUTERS) - 1) * gap,
                    max(text_width(stats(m)) for m in ms)) + 32
        foot = 2 * FONT_H + 16 if a.lanes else 0
        cv = Canvas(width, ph + head + 2 * FONT_H + 24 + len(ROUTERS) * (FONT_H + 3) + 8 + foot,
                    BG)
        cv.text(16, 8, f"hourglass {name}: {ms[0]['pc']}, demand {ms[0]['demand']:.1f}/s "
                       f"(one lane 7.5/s)", TEXT, scale=2)
        for i, m in enumerate(ms):
            ox = 16 + i * (pw + gap)
            cv.text(ox, head, m["router"], TEXT, scale=2)
            if a.lanes:
                lg, load = lanes_png.solve(m["flat"], m["layout"], cat)
                lanes_png.draw(cv, ox, head + 2 * FONT_H + 6, m["layout"], cat, lg, load, bounds,
                               s, blocked, mid)
            else:
                panel(cv, ox, head + 2 * FONT_H + 6, m, cat, s)
            cv.text(16, head + 2 * FONT_H + 14 + ph + i * (FONT_H + 3), stats(m), DIM)
            bp = codec.blueprint(codec.rows_of(m["layout"]), label=f"hourglass {name} {m['router']}")
            with open(os.path.join(a.out, f"{name}-{m['router']}.txt"), "w") as fh:
                fh.write(bp + "\n")
        if a.lanes:
            lanes_png.legend(cv, 16, head + 2 * FONT_H + 22 + ph + len(ROUTERS) * (FONT_H + 3))
        path = os.path.join(a.out, f"{name}{'-lanes' if a.lanes else ''}.png")
        cv.save(path)
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
