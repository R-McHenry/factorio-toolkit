"""lanes_png: a layout drawn lane by lane, with its turns, tunnels and the flow on every lane.

Used by ``tools/hourglass_png.py --lanes``. Every belt, underground and splitter shows its two lanes
(left and right looking along the flow) as two strips, each coloured by its load in the routed flow
solver (``fkcore.routed``: what the lane carries over what it can carry): grey when empty, green to
yellow to red at capacity. A turn bends both strips round the corner, the outer lane the longer
one; an underground's lanes stop at its entrance and start again at its exit, a dashed line between
them; a splitter is two belt halves in one frame; a side-load is a white bar where it enters.
Inserters are small squares, producers red, consumers blue. Stdlib only.
"""
from __future__ import annotations

from fkcore import fkp, lanes as lanesmod, routed

BELT_BASE = {"transport-belt": (58, 50, 28), "underground-belt": (58, 50, 28),
             "splitter": (74, 46, 26)}
EMPTY = (128, 132, 146)
PROD = (210, 70, 70)
CONS = (70, 130, 220)
INS = (150, 150, 160)
WALL = (110, 110, 115)
GRID = (34, 37, 42)
MID = (90, 90, 140)
FRAME = (240, 170, 110)
SIDE = (250, 250, 250)
ARROW = (235, 235, 240)

_V = {0: (0, -1), 1: (1, 0), 2: (0, 1), 3: (-1, 0)}


def load_rgb(r):
    """Grey for an empty lane, then green, yellow and red at capacity."""
    if r <= 1e-6:
        return EMPTY
    r = min(1.0, r)
    if r < 0.5:
        t = r / 0.5
        a, b = (60, 170, 90), (235, 205, 60)
    else:
        t = (r - 0.5) / 0.5
        a, b = (235, 205, 60), (230, 60, 50)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _left(v):
    return (v[1], -v[0])


def _off(v, lane):
    lx, ly = _left(v)
    k = 0.25 if lane == "L" else -0.25
    return (lx * k, ly * k)


class _Pen:
    def __init__(self, cv, ox, oy, x0, y0, s):
        self.cv, self.ox, self.oy, self.x0, self.y0, self.s = cv, ox, oy, x0, y0, s

    def px(self, p):
        return self.ox + (p[0] - self.x0) * self.s, self.oy + (p[1] - self.y0) * self.s

    def seg(self, p0, p1, rgb, w):
        """An axis-aligned strip from p0 to p1 (tile units), ``w`` tiles wide."""
        (a, b), (c, d) = self.px(p0), self.px(p1)
        h = w * self.s / 2
        x0, x1 = min(a, c) - h, max(a, c) + h
        y0, y1 = min(b, d) - h, max(b, d) + h
        self.cv.rect(int(round(x0)), int(round(y0)), max(1, int(round(x1 - x0))),
                     max(1, int(round(y1 - y0))), rgb)

    def box(self, x, y, w, h, rgb, inset=0.0):
        a, b = self.px((x + inset, y + inset))
        self.cv.rect(int(a), int(b), max(1, int((w - 2 * inset) * self.s)),
                     max(1, int((h - 2 * inset) * self.s)), rgb)

    def frame(self, x, y, w, h, rgb):
        a, b = self.px((x, y))
        self.cv.outline(int(a), int(b), int(w * self.s), int(h * self.s), rgb)

    def dashed(self, p0, p1, rgb):
        (a, b), (c, d) = self.px(p0), self.px(p1)
        n = int(max(abs(c - a), abs(d - b)) // 4)
        for i in range(0, n, 2):
            t0, t1 = i / max(n, 1), min(1.0, (i + 1) / max(n, 1))
            self.cv.line(int(a + (c - a) * t0), int(b + (d - b) * t0),
                         int(a + (c - a) * t1), int(b + (d - b) * t1), rgb)

    def arrow(self, c, v, rgb, size=0.12):
        """A small chevron at tile point ``c`` pointing along ``v``, ``size`` tiles long."""
        (cx, cy) = self.px(c)
        k = max(2, int(self.s * size))
        for i in range(k):
            w = k - i
            if v == (0, -1):
                self.cv.rect(int(cx - w), int(cy - k / 2 + i), 2 * w, 1, rgb)
            elif v == (0, 1):
                self.cv.rect(int(cx - w), int(cy + k / 2 - i), 2 * w, 1, rgb)
            elif v == (1, 0):
                self.cv.rect(int(cx + k / 2 - i), int(cy - w), 1, 2 * w, rgb)
            else:
                self.cv.rect(int(cx - k / 2 + i), int(cy - w), 1, 2 * w, rgb)


def solve(flat, lay, cat):
    """The routed flow solver on ``lay``: -> (lane graph, {node id: load 0..1})."""
    r = routed.solve(flat, lay, cat)
    load = {}
    for nid in r.lg.nodes:
        cap = r.res.cap.get(nid)
        if cap and cap != lanesmod.INF:
            load[nid] = r.res.total(nid) / cap
    return r.lg, load


def crop(bounds, lays, cat, margin=2):
    """``bounds`` cut to the tiles the layouts ``lays`` use, plus ``margin`` tiles each side."""
    ts = [t for lay in lays for e in lay.entities.values() for t in fkp.tiles_of(cat, e)]
    if not ts:
        return bounds
    x0, y0, x1, y1 = bounds
    return (max(x0, min(t[0] for t in ts) - margin), max(y0, min(t[1] for t in ts) - margin),
            min(x1, max(t[0] for t in ts) + 1 + margin), min(y1, max(t[1] for t in ts) + 1 + margin))


def draw(cv, ox, oy, lay, cat, lg, load, bounds, s, blocked=(), mid=None, owner=None):
    """The layout ``lay`` within ``bounds`` (x0, y0, x1, y1 tiles) at ``s`` pixels a tile."""
    x0, y0, x1, y1 = bounds
    pen = _Pen(cv, ox, oy, x0, y0, s)
    blocked = set(blocked)
    for y in range(y0, y1):
        for x in range(x0, x1):
            if (x, y) in blocked:
                pen.box(x, y, 1, 1, WALL)
            else:
                pen.box(x, y, 1, 1, GRID, inset=0.03)
                if mid is not None and x == mid and y % 2 == 0:
                    pen.box(x + 0.45, y, 0.1, 1, MID)
    turn_from, side_in, tunnel = {}, [], []
    for e in lg.edges():
        if e.via == "turn":
            turn_from[e.dst[0]] = e.src[0]
        elif e.via in ("side", "ug_side"):
            side_in.append((e.src[0], e.dst[0]))
        elif e.via == "tunnel" and e.src[1] == "L":
            tunnel.append((e.src[0], e.dst[0]))
    ents = lay.entities
    w = 0.26

    def centre(e):
        ts = list(fkp.tiles_of(cat, e))
        return (sum(t[0] for t in ts) / len(ts) + 0.5, sum(t[1] for t in ts) / len(ts) + 0.5)

    for e in ents.values():
        if owner and e.owner != owner and e.name in BELT_BASE:
            continue
        ts = list(fkp.tiles_of(cat, e))
        tx0, ty0 = min(t[0] for t in ts), min(t[1] for t in ts)
        tw, th = max(t[0] for t in ts) + 1 - tx0, max(t[1] for t in ts) + 1 - ty0
        v = _V[int(e.dir or 0) // 4]
        if e.name not in BELT_BASE:
            if "inserter" in e.name:
                pen.box(tx0, ty0, 1, 1, INS, inset=0.33)
            elif e.key.startswith("p"):
                pen.box(tx0, ty0, tw, th, PROD, inset=0.08)
            else:
                pen.box(tx0, ty0, tw, th, CONS, inset=0.08)
            continue
        pen.box(tx0, ty0, tw, th, BELT_BASE[e.name], inset=0.06)
        if e.name == "splitter":
            c = centre(e)
            p = (abs(v[1]), abs(v[0]))            # across the flow
            halves = [(c[0] - p[0] * 0.5, c[1] - p[1] * 0.5), (c[0] + p[0] * 0.5, c[1] + p[1] * 0.5)]
            for hc in halves:
                for lane in "LR":
                    o = _off(v, lane)
                    rgb = load_rgb(load.get((e.key, lane), 0.0))
                    pen.seg((hc[0] - v[0] * 0.5 + o[0], hc[1] - v[1] * 0.5 + o[1]),
                            (hc[0] + v[0] * 0.5 + o[0], hc[1] + v[1] * 0.5 + o[1]), rgb, w)
                pen.arrow(hc, v, ARROW, 0.2)
            pen.frame(tx0, ty0, tw, th, FRAME)
            continue
        c = (tx0 + 0.5, ty0 + 0.5)
        ug = e.attrs.get("ug") if e.name == "underground-belt" else None
        src = turn_from.get(e.key)
        a = v
        if src is not None and src in ents:
            sc = centre(ents[src])
            a = (int(round(c[0] - sc[0])), int(round(c[1] - sc[1])))
            if a not in _V.values():
                a = v
        for lane in "LR":
            rgb = load_rgb(load.get((e.key, lane), 0.0))
            od = _off(v, lane)
            if ug == "in":
                pen.seg((c[0] - v[0] * 0.5 + od[0], c[1] - v[1] * 0.5 + od[1]),
                        (c[0] + od[0], c[1] + od[1]), rgb, w)
            elif ug == "out":
                pen.seg((c[0] + od[0], c[1] + od[1]),
                        (c[0] + v[0] * 0.5 + od[0], c[1] + v[1] * 0.5 + od[1]), rgb, w)
            elif a != v:
                oa = _off(a, lane)
                entry = (c[0] - a[0] * 0.5 + oa[0], c[1] - a[1] * 0.5 + oa[1])
                corner = (c[0] + oa[0] + od[0], c[1] + oa[1] + od[1])
                exit_ = (c[0] + v[0] * 0.5 + od[0], c[1] + v[1] * 0.5 + od[1])
                pen.seg(entry, corner, rgb, w)
                pen.seg(corner, exit_, rgb, w)
            else:
                pen.seg((c[0] - v[0] * 0.5 + od[0], c[1] - v[1] * 0.5 + od[1]),
                        (c[0] + v[0] * 0.5 + od[0], c[1] + v[1] * 0.5 + od[1]), rgb, w)
        if ug:
            # the hood: a bar across the closed end
            back = (-v[0], -v[1]) if ug == "out" else v
            pen.seg((c[0] + back[0] * 0.05 - v[1] * 0.4, c[1] + back[1] * 0.05 - v[0] * 0.4),
                    (c[0] + back[0] * 0.05 + v[1] * 0.4, c[1] + back[1] * 0.05 + v[0] * 0.4),
                    (30, 24, 12), 0.12)
        else:
            pen.arrow(c, v, ARROW, 0.2)
    for a, b in tunnel:
        if a in ents and b in ents:
            ea, eb = ents[a], ents[b]
            v = _V[int(ea.dir or 0) // 4]
            ca, cb = centre(ea), centre(eb)
            for lane in "LR":
                o = _off(v, lane)
                rgb = load_rgb(load.get((a, lane), 0.0))
                pen.dashed((ca[0] + o[0], ca[1] + o[1]), (cb[0] + o[0], cb[1] + o[1]), rgb)
    for a, b in side_in:
        if a in ents and b in ents:
            ca, cb = centre(ents[a]), centre(ents[b])
            m = ((ca[0] + cb[0]) / 2, (ca[1] + cb[1]) / 2)
            d = (cb[0] - ca[0], cb[1] - ca[1])
            p = (abs(d[1]) * 0.35, abs(d[0]) * 0.35)
            pen.seg((m[0] - p[0], m[1] - p[1]), (m[0] + p[0], m[1] + p[1]), SIDE, 0.08)


def legend(cv, x, y, s=14):
    """The load colour scale and the symbols, at (x, y) pixels."""
    from fkcore.png import FONT_H
    cv.text(x, y, "lane load:", (225, 225, 225))
    bx = x + 72
    cv.rect(bx, y - 1, s, FONT_H + 2, EMPTY)
    cv.text(bx + s + 4, y, "empty", (180, 180, 190))
    bx += s + 48
    for i in range(100):
        cv.rect(bx + i, y - 1, 1, FONT_H + 2, load_rgb((i + 1) / 100))
    cv.text(bx + 104, y, "0 -> 100% of the lane", (180, 180, 190))
    cv.text(x, y + FONT_H + 6, "two strips per belt: left and right lane looking along the flow (the "
                               "arrow); dashed: an underground's tunnel; white bar: a side-load",
            (180, 180, 190))
