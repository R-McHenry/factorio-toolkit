"""fkcore.robots: robot coverage, the flow's ``cover robots`` step and its surface check (CORE-V1 §4.2).

A logistic chest (requester, provider, storage, buffer) works only inside a roboport's logistic
area, and robots build only inside a construction area of a network that holds the materials. The
V1 rehearsal found it (2026-10-20): a gear factory's requester stood half a tile outside the kit
roboport's square and got nothing.

:func:`cover_robots` puts roboports into a factory so every logistic chest of it is inside some
roboport's logistic square (``logistic_radius`` each way from its centre, catalog), a greedy set
cover over free 4x4 spots of the factory frame: the spot covering the most uncovered chests, ties
to the spot nearest the chests' centre, then north, then west. Roboports already in the layout
that are not the owner's own ``r<k>`` count as coverage and stay, and so do ``served`` squares:
the surface's main network in the factory's frame (:func:`served`, 1.2: the 0534 run's ``boot``
stood inside the kit roboport's square and got a roboport of its own anyway, from a stock of 4).
A factory without logistic chests gets none (building it is the network's job). With ``storage``
(the flow's default, ``storage-chest``) each roboport it places gets a storage chest beside it,
``<owner>/s<k>``, so what robots take up nearby is stored nearby (1.2: the run's rebuilds far
from spawn sent every taken-up item 110 tiles to the kit's chests). Run it before ``cover
power``, so the poles power the roboports too. :func:`apply_robots` returns the layout with them
and ``cover robots robots``. 1.7 (Rory, 2026-10-21: pin and patch): the committed roboports
(``pinned``) stay where they still fit and still reach a chest, so a rebuild adds roboports only
where none reaches and never moves the network that stands.

:func:`check_surface` judges a composed surface: roboports join one logistic network when their
logistic squares meet (centres at most twice the radius apart on both axes); the **main** network
is the one holding a roboport outside every plot (shared infra: the kit's). Each factory's
logistic chests must be inside a square of the main network, and each of its entities inside the
main network's construction area, else a ``no-robots`` check line (never a gate). Pure, stdlib only.
"""
from __future__ import annotations

import copy
import re
from collections import namedtuple

from . import fkp
from .compose import turn
from .cover import _Ground
from .elaborate import Check
from .fkp import Entity, natural_key

__all__ = ["LOGISTIC_CHESTS", "RobotReport", "cover_robots", "apply_robots", "networks",
           "served", "check_surface"]

LOGISTIC_CHESTS = frozenset({"requester-chest", "passive-provider-chest", "active-provider-chest",
                             "storage-chest", "buffer-chest"})
_OWN = re.compile(r"[rs]\d+")          # the cover's own: roboports r<k>, their storage chests s<k>
_Port = namedtuple("_Port", "key name x y plot")


class RobotReport:
    def __init__(self, owner, roboports, chests, covered, uncovered, served=0, storage=(),
                 no_room=0, pinned=0):
        self.owner, self.roboports, self.chests, self.covered, self.uncovered = (
            owner, roboports, chests, covered, uncovered)
        self.served, self.storage, self.no_room = served, list(storage), no_room
        self.pinned = pinned           # of ``roboports``, the committed ones kept where they stand
        self.checks = [Check("no-robots", key, why) for key, why in uncovered]

    def summary(self):
        text = f"cover {self.owner} robots: {len(self.roboports)} roboports"
        if self.pinned:
            text += f" ({self.pinned} kept where they stand)"
        if self.storage or self.no_room:
            text += f", {len(self.storage)} storage chests beside them"
            if self.no_room:
                text += f" ({self.no_room} with no free tile beside it)"
        text += f"; {self.covered}/{self.chests} logistic chests inside a logistic area"
        if self.served:
            text += f" ({self.served} of them in the surface network's)"
        return text


def _radius(cat, name, field):
    row = cat.entity(name)
    return float(row.get(field) or 0)


def _inside(x, y, rx, ry, r):
    return abs(x - rx) <= r and abs(y - ry) <= r


def _is_own(e, owner):
    return e.owner == owner and _OWN.fullmatch(e.key[len(owner) + 1:]) is not None


def cover_robots(lay, cat, owner="robots", keep_out=(), roboport="roboport", served=(),
                 storage=None, pinned=()):
    """-> (new Entities: roboports keyed ``<owner>/r<k>`` and, with ``storage`` (a chest
    prototype), a storage chest beside each keyed ``<owner>/s<k>``; RobotReport). ``served``:
    [(x, y, radius)] logistic squares of the surface's network in this factory's frame.
    ``pinned``: the committed .fkp's own ``r<k>`` / ``s<k>`` (1.7, pin and patch): a roboport
    that still fits and still reaches a chest of the factory stays where it stands, and so does
    its storage chest where that still fits; new roboports go only where no kept one reaches."""
    r = _radius(cat, roboport, "logistic_radius")
    ents = sorted(lay.entities.values(), key=lambda e: natural_key(e.key))
    chests = [e for e in ents if e.name in LOGISTIC_CHESTS and not _is_own(e, owner)]
    existing = [e for e in ents if cat.kind(e.name) == "roboport" and not _is_own(e, owner)]
    outside = [c for c in chests
               if any(_inside(float(c.x), float(c.y), sx, sy, sr) for sx, sy, sr in served)]
    taken = {}
    for e in ents:
        if _is_own(e, owner):
            continue
        for t in fkp.tiles_of(cat, e):
            taken[t] = e.key
    w, h = cat.size(roboport)
    ground = _Ground(taken, set(map(tuple, keep_out)), lay.size, (w, h))
    avoid = _hands_and_fronts(cat, ents) if storage else set()
    old = {e.key[len(owner) + 1:]: e for e in pinned if _is_own(e, owner)}
    kept, kept_chests = [], {}
    for local in sorted((k for k in old if k.startswith("r")), key=natural_key):
        e = old[local]
        try:
            tiles = fkp.tiles_of(cat, e)
        except (KeyError, ValueError):
            continue
        spot = (min(x for x, _y in tiles), min(y for _x, y in tiles))
        if e.name != roboport or not ground.free(spot) or not any(
                _inside(float(c.x), float(c.y), float(e.x), float(e.y), r) for c in chests):
            continue
        ground.place(spot)
        kept.append((int(local[1:]), spot, float(e.x), float(e.y)))
    for k, _spot, _x, _y in kept:
        c = old.get(f"s{k}")
        if c is None or not storage or c.name != storage:
            continue
        try:
            tile = min(fkp.tiles_of(cat, c))
        except (KeyError, ValueError):
            continue
        if _free_tile(ground, tile, avoid):
            ground.placed.add(tile)
            kept_chests[k] = tile
    left = [c for c in chests if c not in outside
            and not any(_inside(float(c.x), float(c.y), float(p.x), float(p.y), r) for p in existing)
            and not any(_inside(float(c.x), float(c.y), x, y, r) for _k, _s, x, y in kept)]
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
        placed.append((spot, px, py))
        left = [c for c in left if not _inside(float(c.x), float(c.y), px, py, r)]
    placed.sort(key=lambda p: (p[2], p[1]))
    top = max([k for k, *_rest in kept] + [-1]) + 1      # new ones are numbered after the kept
    ports = [(k, spot, x, y) for k, spot, x, y in kept] + \
            [(top + k, spot, x, y) for k, (spot, x, y) in enumerate(placed)]
    news = [Entity(f"{owner}/r{k}", roboport, _clean(x), _clean(y), None, {})
            for k, _spot, x, y in ports]
    chests_out, no_room = [], 0
    if storage:
        for k, spot, _x, _y in ports:
            tile = kept_chests.get(k) or _beside(ground, spot, avoid)
            if tile is None:
                no_room += 1
                continue
            ground.placed.add(tile)
            chests_out.append(Entity(f"{owner}/s{k}", storage, tile[0] + 0.5, tile[1] + 0.5,
                                     None, {}))
    uncovered = [(c.key, "no free 4x4 spot inside the factory's frame reaches it") for c in left]
    rep = RobotReport(owner, [e.key for e in news], len(chests), len(chests) - len(left),
                      uncovered, served=len(outside), storage=[e.key for e in chests_out],
                      no_room=no_room, pinned=len(kept))
    return news + chests_out, rep


def _free_tile(ground, t, avoid):
    """True when a 1x1 chest fits on tile ``t``: inside the frame, on no entity, keep-out or
    placed tile, and off ``avoid``."""
    size = ground.size
    if size is not None and not (0 <= t[0] < size[0] and 0 <= t[1] < size[1]):
        return False
    return not (t in ground.taken or t in ground.keep_out or t in ground.placed or t in avoid)


def _hands_and_fronts(cat, ents):
    """Tiles a chest beside a roboport keeps off: where an inserter picks or drops, where a drill
    drops, where a belt points (``fkcore.route``'s ground rules)."""
    from . import route
    return set(route._hand_tiles(cat, ents)) | set(route._belt_fronts(cat, ents))


def _beside(ground, spot, avoid):
    """The first free tile around a roboport's footprint (north row west to east, then the east,
    south and west sides), inside the frame, on no entity, keep-out or placed tile; else None."""
    i, j, w, h = spot[0], spot[1], ground.pw, ground.ph
    ring = ([(x, j - 1) for x in range(i - 1, i + w + 1)]
            + [(i + w, y) for y in range(j, j + h)]
            + [(x, j + h) for x in range(i + w, i - 2, -1)]
            + [(i - 1, y) for y in range(j + h - 1, j - 1, -1)])
    for t in ring:
        if _free_tile(ground, t, avoid):
            return t
    return None


def _clean(v):
    return int(v) if float(v).is_integer() else v


def apply_robots(lay, cat, owner="robots", keep_out=(), roboport="roboport", served=(),
                 storage=None, pinned=()):
    """A new Layout: ``lay`` without ``owner``'s previous roboports and storage chests, with the
    new ones (the pinned ones that stay among them)."""
    news, rep = cover_robots(lay, cat, owner, keep_out, roboport, served, storage, pinned)
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


def served(places, infra, layouts, factory, cat):
    """[(x, y, logistic radius)] in ``factory``'s frame: the roboports of the surface's main
    network (the one holding a roboport outside every plot, as :func:`check_surface` judges it)
    that stand outside ``factory`` and whose logistic square reaches its frame. ``places``:
    {factory: surface.Place}; ``infra``: the surface .fkp's own entities; ``layouts``: {factory:
    Layout} as laid out so far."""
    ports = [_Port(e.key, e.name, float(e.x), float(e.y), None) for e in infra
             if cat.has_entity(e.name) and cat.kind(e.name) == "roboport"]
    for name, lay in sorted(layouts.items()):
        p = places.get(name)
        if p is None or not lay.size:
            continue
        for e in lay.entities.values():
            if cat.has_entity(e.name) and cat.kind(e.name) == "roboport":
                x, y, _d = turn(float(e.x), float(e.y), None, p.rot, lay.size)
                ports.append(_Port(f"{name}/{e.key}", e.name, x + p.x, y + p.y, name))
    main = next((n for n in networks(ports, cat) if any(q.plot is None for q in n)), None)
    me, lay = places.get(factory), layouts.get(factory)
    if main is None or me is None or lay is None or not lay.size:
        return []
    w, h = lay.size
    turned = (h, w) if me.rot % 2 else (w, h)
    out = []
    for q in main:
        if q.plot == factory:
            continue
        fx, fy, _d = turn(q.x - me.x, q.y - me.y, None, (4 - me.rot) % 4, turned)
        r = _radius(cat, q.name, "logistic_radius")
        if fx + r >= 0 and fx - r <= w and fy + r >= 0 and fy - r <= h:
            out.append((fx, fy, r))
    return out


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
            checks.append(Check("no-robots", f"{s.name} {c.key}", "outside every logistic area of "
                                "the main network: robots will not serve it"))
        if out_con:
            checks.append(Check("no-robots", f"{s.name} {plot}", f"{len(out_con)} entities are "
                                "outside the main network's construction area: robots will not "
                                "build them (a roboport within reach first)"))
    return lines, checks
