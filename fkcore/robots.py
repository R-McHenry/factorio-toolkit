"""fkcore.robots: robot coverage, the flow's ``cover robots`` step and its surface check (CORE-V1 §4.2).

A logistic chest (requester, provider, storage, buffer) works only inside a roboport's logistic
area, and robots build only inside a construction area of a network that holds the materials. The
V1 rehearsal found it (2026-10-20): a gear factory's requester stood half a tile outside the kit
roboport's square and got nothing.

:func:`cover_robots` puts roboports into a factory so every logistic chest of it is inside some
roboport's logistic square (``logistic_radius`` each way from its centre, catalog), a greedy set
cover over free 4x4 spots of the factory frame: the spot covering the most uncovered chests, ties
to the spot nearest the chests' centre, then north, then west. Roboports already in the layout
that are not the owner's own ``r<k>`` count as coverage and stay. A factory without logistic chests
gets none (building it is the network's job). Run it before ``cover power``, so the poles power the
roboports too. :func:`apply_robots` returns the layout with them and ``cover robots robots``.

:func:`check_surface` judges a composed surface: roboports join one logistic network when their
logistic squares meet (centres at most twice the radius apart on both axes); the **main** network
is the one holding a roboport outside every plot (shared infra: the kit's). Each factory's
logistic chests must be inside a square of the main network, and each of its entities inside the
main network's construction area, else a ``NO_ROBOTS`` check line (never a gate). Pure, stdlib only.
"""
from __future__ import annotations

import copy
import re

from . import fkp
from .cover import _Ground
from .elaborate import Check
from .fkp import Entity, natural_key

__all__ = ["LOGISTIC_CHESTS", "RobotReport", "cover_robots", "apply_robots", "networks",
           "check_surface"]

LOGISTIC_CHESTS = frozenset({"requester-chest", "passive-provider-chest", "active-provider-chest",
                             "storage-chest", "buffer-chest"})
_OWN = re.compile(r"r\d+")


class RobotReport:
    def __init__(self, owner, roboports, chests, covered, uncovered):
        self.owner, self.roboports, self.chests, self.covered, self.uncovered = (
            owner, roboports, chests, covered, uncovered)
        self.checks = [Check("NO_ROBOTS", key, why) for key, why in uncovered]

    def summary(self):
        return (f"cover {self.owner} robots: {len(self.roboports)} roboports; {self.covered}/"
                f"{self.chests} logistic chests inside a logistic area")


def _radius(cat, name, field):
    row = cat.entity(name)
    return float(row.get(field) or 0)


def _inside(x, y, rx, ry, r):
    return abs(x - rx) <= r and abs(y - ry) <= r


def _is_own(e, owner):
    return e.owner == owner and _OWN.fullmatch(e.key[len(owner) + 1:]) is not None


def cover_robots(lay, cat, owner="robots", keep_out=(), roboport="roboport"):
    """-> (new roboport Entities keyed ``<owner>/r<k>``, RobotReport)."""
    r = _radius(cat, roboport, "logistic_radius")
    ents = sorted(lay.entities.values(), key=lambda e: natural_key(e.key))
    chests = [e for e in ents if e.name in LOGISTIC_CHESTS]
    existing = [e for e in ents if cat.kind(e.name) == "roboport" and not _is_own(e, owner)]
    taken = {}
    for e in ents:
        if _is_own(e, owner):
            continue
        for t in fkp.tiles_of(cat, e):
            taken[t] = e.key
    w, h = cat.size(roboport)
    ground = _Ground(taken, set(map(tuple, keep_out)), lay.size, (w, h))
    left = [c for c in chests
            if not any(_inside(float(c.x), float(c.y), float(p.x), float(p.y), r) for p in existing)]
    placed = []
    if left:
        cx = sum(float(c.x) for c in left) / len(left)
        cy = sum(float(c.y) for c in left) / len(left)
    while left:
        best = None
        x0 = int(min(float(c.x) for c in left) - r - w) - 1
        x1 = int(max(float(c.x) for c in left) + r) + 1
        y0 = int(min(float(c.y) for c in left) - r - h) - 1
        y1 = int(max(float(c.y) for c in left) + r) + 1
        for j in range(y0, y1 + 1):
            for i in range(x0, x1 + 1):
                if not ground.free((i, j)):
                    continue
                px, py = ground.centre((i, j))
                n = sum(1 for c in left if _inside(float(c.x), float(c.y), px, py, r))
                if not n:
                    continue
                score = (-n, (px - cx) ** 2 + (py - cy) ** 2, j, i)
                if best is None or score < best[0]:
                    best = (score, (i, j))
        if best is None:
            break
        spot = best[1]
        ground.place(spot)
        px, py = ground.centre(spot)
        placed.append((px, py))
        left = [c for c in left if not _inside(float(c.x), float(c.y), px, py, r)]
    placed.sort(key=lambda p: (p[1], p[0]))
    news = [Entity(f"{owner}/r{k}", roboport, _clean(x), _clean(y), None, {})
            for k, (x, y) in enumerate(placed)]
    uncovered = [(c.key, "no free 4x4 spot inside the factory's frame reaches it") for c in left]
    rep = RobotReport(owner, [e.key for e in news], len(chests), len(chests) - len(left),
                      uncovered)
    return news, rep


def _clean(v):
    return int(v) if float(v).is_integer() else v


def apply_robots(lay, cat, owner="robots", keep_out=(), roboport="roboport"):
    """A new Layout: ``lay`` without ``owner``'s previous roboports, with the new ones."""
    news, rep = cover_robots(lay, cat, owner, keep_out, roboport)
    out = copy.deepcopy(lay)
    out.entities = {k: e for k, e in out.entities.items() if not _is_own(e, owner)}
    if news or owner in out.covers:
        old = out.covers.get(owner)
        params = dict(old.params) if old is not None else {}
        params["roboport"] = roboport
        out.covers[owner] = fkp.Cover(owner, "robots", params)
    for e in news:
        out.add(e)
    return out, rep


def networks(ents, cat):
    """Logistic networks of roboports: [[keys]], joined when their logistic squares meet."""
    ports = sorted((e for e in ents if cat.kind(e.name) == "roboport"), key=lambda e: natural_key(e.key))
    parent = list(range(len(ports)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, a in enumerate(ports):
        ra = _radius(cat, a.name, "logistic_radius")
        for j in range(i + 1, len(ports)):
            b = ports[j]
            reach = ra + _radius(cat, b.name, "logistic_radius")
            if abs(float(a.x) - float(b.x)) <= reach and abs(float(a.y) - float(b.y)) <= reach:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    groups = {}
    for i, p in enumerate(ports):
        groups.setdefault(find(i), []).append(p)
    return [groups[k] for k in sorted(groups)]


def check_surface(s, cat):
    """(lines, checks) for a composed surface: every factory's chests and entities against the
    main logistic network (the one holding a roboport outside every plot)."""
    nets = networks(list(s.entities.values()), cat)
    main = next((n for n in nets if any(p.plot is None for p in n)), None)
    if main is None:
        return ["robots: no roboport outside the plots (the kit's): nothing to judge against"], []
    lines = [f"robots: {len(nets)} logistic network{'s' if len(nets) != 1 else ''}; the main one "
             f"has {len(main)} roboports"]
    checks = []
    for plot in sorted(s.plots):
        mine = [e for e in s.entities.values() if e.plot == plot]
        chests = [e for e in mine if e.name in LOGISTIC_CHESTS]
        out_log = [c for c in chests if not any(
            _inside(float(c.x), float(c.y), float(p.x), float(p.y),
                    _radius(cat, p.name, "logistic_radius")) for p in main)]
        out_con = [e for e in mine if not any(
            _inside(float(e.x), float(e.y), float(p.x), float(p.y),
                    _radius(cat, p.name, "construction_radius")) for p in main)]
        lines.append(f"  {plot}: {len(chests) - len(out_log)}/{len(chests)} logistic chests in the "
                     f"main network, {len(mine) - len(out_con)}/{len(mine)} entities in its "
                     "construction area")
        for c in out_log:
            checks.append(Check("NO_ROBOTS", f"{s.name} {c.key}", "outside every logistic area of "
                                "the main network: robots will not serve it"))
        if out_con:
            checks.append(Check("NO_ROBOTS", f"{s.name} {plot}", f"{len(out_con)} entities are "
                                "outside the main network's construction area: robots will not "
                                "build them (a roboport within reach first)"))
    return lines, checks
