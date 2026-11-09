"""fkcore.placer: the V1 placer's ``@patch`` hint (CORE-V1.md §9 Placer): a MinerRow on real ore.

:func:`place_on_patch` picks a row's origin and rotation inside its factory's plot (the plot in
the factory frame, ``FrameGround.box``) so that

- **every drill stands on ore** of the row's resource: every tile under the drill's body holds it;
- **no row entity is on blocked ground** (water, cliffs) or on a tile something placed already
  holds (``taken``: entity tiles, instance frames and their route ends); the row's frame covers
  nothing taken, and the tiles its routes start or end on are free and inside the plot;
- **no drill's mining area holds a tile of another resource** (PLAN-ORGANIC M1, 3.1: ``other``,
  the tiles of every other resource the drill would mine): a drill over iron and copper puts both
  on the belt. A mixed patch with no clean spot takes the spot where the **fewest drills** touch
  the other resource (``Spot.mixed`` names them), and the caller sets their resource filter or
  leaves them out (``expand._on_patch``);
- among those spots, the drills' **mining areas** (their union: 5x5 per electric drill) hold the
  most ore tiles, then the most ore, then the drill bodies the most ore; ties go north, then
  west, then to the lower rotation. Every rotation is tried, so a row is laid along a patch's
  long axis when that is where it fits.

The candidates are the origins that put the first drill's first tile on ore, so the search is
over the ore, not over the plot. Deterministic, pure, stdlib only. It never changes ``n``: when
no spot holds every drill, :func:`largest_fit` says how many drills of the same row would fit,
and where, for the report. :func:`cover` (M2) is ``n=auto``'s count: the most drills of the row,
within its bounds, with a clean spot on the patch.

**Patches from the design** (PLAN-ORGANIC M3, 43-mines): :func:`patches` reads the terrain file
the design names (``read-terrain``: ``<name>.terrain.json``, ``fkcore.terrain``) and gives every
patch of a resource as an :class:`OrePatch` (its tiles, amount, box and centroid, in the
terrain's own map coordinates), largest first, numbered as the surface file's ``iron-ore#2``
names them; :func:`patch` looks one up by that name and :func:`nearest_patch` picks the nearest
that holds at least ``need`` tiles. The world placer's pins on ore (part T) read these; nothing
here reads the world.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import facts as _facts
from . import terrain as _terrain
from .catalog import MINING_RADIUS
from .compose import turn

__all__ = ["Spot", "shape", "mining_area", "place_on_patch", "largest_fit", "cover", "others",
           "filter_slots", "OrePatch", "patches", "patch", "nearest_patch"]

_H = {0: 0, 4: 1, 8: 2, 12: 3}
_DX = (0, 1, 0, -1)
_DY = (-1, 0, 1, 0)


@dataclass
class Spot:
    x: int
    y: int
    rot: int
    drills: int              # drills with ore under every tile of their body
    under: int               # ore tiles under the drill bodies
    under_amount: int
    reach: int               # ore tiles in the union of the drills' mining areas
    reach_amount: int
    size: tuple              # the turned frame, (w, h)
    mixed: tuple = ()        # (drill index, other resource) per drill whose mining area holds
                             # a tile of another resource (M1); () is a clean spot

    @property
    def clean(self):
        return not self.mixed


@dataclass
class _Shape:
    w: int
    h: int
    ents: frozenset          # every entity tile, relative to the origin
    bodies: list             # [frozenset] one per drill
    areas: list              # [frozenset] one per drill: its mining area
    ends: frozenset          # the tiles the row's routes start or end on (outside its entities)


@dataclass(frozen=True)
class OrePatch:
    """One patch of one resource, as the terrain file holds it (map coordinates)."""
    resource: str
    n: int                   # 1 is the largest patch of the resource: the ``#k`` of ``iron-ore#k``
    tiles: frozenset         # {(x, y)}: every tile of the patch (8-connected, ``terrain.patches``)
    amount: int              # the ore on it
    box: tuple               # (x0, y0, x1, y1), half-open
    centroid: tuple          # (x, y): the mean of the tile centres, floats

    @property
    def name(self):
        return f"{self.resource}#{self.n}"

    @property
    def size(self):
        return self.box[2] - self.box[0], self.box[3] - self.box[1]

    def __len__(self):
        return len(self.tiles)


def _resources(terrain):
    """{resource: {tile: amount}} from what the caller has: a ``terrain.Terrain``, the path of a
    ``.terrain.json``, the file's dict, a ``FrameGround`` (its ``ore``, in the factory frame) or
    that mapping itself."""
    if isinstance(terrain, str):
        terrain = _terrain.load(terrain)
    if isinstance(terrain, _terrain.Terrain):
        return terrain.resources
    if isinstance(terrain, _terrain.FrameGround):
        return terrain.ore
    if isinstance(terrain, dict) and "resources" in terrain and "surface" in terrain:
        return _terrain.from_dict(terrain).resources
    return terrain or {}


def patches(terrain, resource=None):
    """[OrePatch]: every patch of ``resource`` in ``terrain`` (every resource's when None), the
    largest first within a resource and numbered from 1 as ``terrain.patches`` numbers them (the
    ``#k`` a surface file's ``place ... patch iron-ore#2`` and a pin on ore use). ``terrain`` is a
    ``terrain.Terrain``, the path of the ``.terrain.json`` the design names, the file's dict, a
    ``FrameGround`` (then the tiles are in that plot's frame) or a {resource: {tile: amount}}
    mapping. Pure; nothing is read from the world."""
    res = _resources(terrain)
    if resource is not None:
        res = {resource: res[resource]} if resource in res else {}
    out = []
    for name, ps in sorted(_terrain.patches(res).items()):
        for p in ps:
            xs = sum(t[0] + 0.5 for t in p.tiles) / len(p.tiles)
            ys = sum(t[1] + 0.5 for t in p.tiles) / len(p.tiles)
            out.append(OrePatch(name, p.n, p.tiles, p.amount, p.box, (xs, ys)))
    return out


def patch(terrain, name):
    """The OrePatch ``name`` names (``iron-ore#2``; plain ``iron-ore`` is its largest, ``#1``),
    or None when the terrain has no such patch."""
    resource, _hash, k = str(name).partition("#")
    want = int(k) if k.strip().isdigit() else 1
    return next((p for p in patches(terrain, resource) if p.n == want), None)


def nearest_patch(terrain, resource, point, need=0):
    """The patch of ``resource`` whose centroid is nearest ``point`` (x, y) among those with at
    least ``need`` tiles, or None (PLAN-ORGANIC T4: a pin with no ``#k`` takes the nearest patch
    that fits the need). Ties go to the larger patch, then the lower number."""
    fit = [p for p in patches(terrain, resource) if len(p.tiles) >= need]
    if not fit:
        return None
    px, py = float(point[0]), float(point[1])
    return min(fit, key=lambda p: ((p.centroid[0] - px) ** 2 + (p.centroid[1] - py) ** 2,
                                   -len(p.tiles), p.n))


def mining_area(name, x, y):
    """The tiles a drill of ``name`` centred at (x, y) mines (``catalog.MINING_RADIUS``)."""
    r = MINING_RADIUS.get(name, 2.49)
    return frozenset((i, j) for i in range(math.floor(x - r) - 1, math.ceil(x + r) + 1)
                     for j in range(math.floor(y - r) - 1, math.ceil(y + r) + 1)
                     if abs(i + 0.5 - x) <= r and abs(j + 0.5 - y) <= r)


def shape(frag, cat, rot) -> _Shape:
    """The fragment turned ``rot`` quarter turns (as ``expand`` turns it), relative to its origin."""
    w, h = frag.size if rot % 2 == 0 else frag.size[::-1]
    ents, bodies, areas = set(), [], []
    for fe in frag.entities:
        x, y, d = turn(float(fe.x), float(fe.y), fe.dir, rot, frag.size)
        tiles = cat.tiles(fe.name, x, y, d if d is not None else 0)
        ents |= tiles
        if cat.kind(fe.name) == "mining-drill":
            bodies.append(frozenset(tiles))
            areas.append(mining_area(fe.name, x, y))
    ends = set()
    for role in frag.roles.values():
        for ax, ay, ad in role.attach:
            if ad is None:
                continue
            x, y, d = turn(float(ax), float(ay), ad, rot, frag.size)
            k = _H[int(d)]
            tx, ty = math.floor(x), math.floor(y)
            sign = 1 if role.side == "out" else -1
            ends.add((tx + sign * _DX[k], ty + sign * _DY[k]))
    return _Shape(w, h, frozenset(ents), bodies, areas, frozenset(ends - ents))


def others(drill, resource, ore):
    """{tile: other resource}: the tiles of every resource but ``resource`` in ``ore``
    ({resource: {tile: amount}}) that a ``drill`` would mine (its ``resource_categories`` against
    the resource's category, ``facts.json``; a resource the facts don't know counts). Crude oil
    under an electric drill is not another resource: the drill cannot mine it."""
    cats = set(_facts.entity(drill).get("resource_categories") or ())
    table = _facts.load().get("resources", {})
    out = {}
    for res, tiles in ore.items():
        if res == resource:
            continue
        category = (table.get(res) or {}).get("category")
        if cats and category is not None and category not in cats:
            continue
        for t in tiles:
            out[t] = res if t not in out else f"{out[t]}+{res}"
    return out


def filter_slots(drill):
    """How many resource filter slots a drill has: its facts.json row's ``filter_count``
    (``MiningDrillPrototype::filter_count``, which ``tools/read_facts.py`` records for drills
    since 3.1, M1), 0 when the row has none. The 2.0.77 facts predate that read, so every drill
    is 0 until facts.json is re-read on a laptop server (docs/notes-41-mines.md)."""
    return int(_facts.entity(drill).get("filter_count") or 0)


def place_on_patch(frag, cat, ore, blocked, taken, box, other=None):
    """The best :class:`Spot` for ``frag`` (a MinerRow fragment), or None.

    ``ore``: {tile: amount} of the row's resource in the factory frame; ``blocked``: terrain
    tiles; ``taken``: tiles held by what is placed already; ``box``: the plot, (x0, y0, x1, y1);
    ``other``: {tile: resource} of the other resources the drills would mine (:func:`others`).
    A clean spot (no mining area on another resource) beats every mixed one; among mixed spots
    the fewest drills touching wins."""
    if not ore:
        return None
    bx0, by0, bx1, by1 = box
    other = other or {}
    best, best_key = None, None
    for rot in range(4):
        sh = shape(frag, cat, rot)
        if not sh.bodies:
            continue
        first = min(sh.bodies[0], key=lambda t: (t[1], t[0]))
        seen = set()
        for ox, oy in sorted(ore, key=lambda t: (t[1], t[0])):
            ox, oy = ox - first[0], oy - first[1]
            if (ox, oy) in seen:
                continue
            seen.add((ox, oy))
            spot = _judge(sh, ox, oy, rot, ore, blocked, taken, (bx0, by0, bx1, by1), other)
            if spot is None:
                continue
            key = (-len(spot.mixed), spot.reach, spot.reach_amount, spot.under_amount, -oy, -ox,
                   -rot)
            if best_key is None or key > best_key:
                best, best_key = spot, key
    return best


def _judge(sh, ox, oy, rot, ore, blocked, taken, box, other=None):
    bx0, by0, bx1, by1 = box
    if not (bx0 <= ox and by0 <= oy and ox + sh.w <= bx1 and oy + sh.h <= by1):
        return None
    under = amount = 0
    for body in sh.bodies:
        for i, j in body:
            a = ore.get((ox + i, oy + j))
            if a is None:
                return None
            under += 1
            amount += a
    for i, j in sh.ents:
        t = (ox + i, oy + j)
        if t in blocked or t in taken:
            return None
    for i, j in sh.ends:
        t = (ox + i, oy + j)
        if t in blocked or t in taken or not (bx0 <= t[0] < bx1 and by0 <= t[1] < by1):
            return None
    for j in range(oy, oy + sh.h):
        for i in range(ox, ox + sh.w):
            if (i, j) in taken:
                return None
    reach, mixed = set(), []
    for k, area in enumerate(sh.areas):
        tiles = {(ox + i, oy + j) for i, j in area}
        reach |= tiles
        if other:
            touched = sorted({other[t] for t in tiles if t in other})
            if touched:
                mixed.append((k, "+".join(touched)))
    held = [ore[t] for t in reach if t in ore]
    return Spot(ox, oy, rot, len(sh.bodies), under, amount, len(held), sum(held), (sh.w, sh.h),
                tuple(mixed))


def largest_fit(make, n, cat, ore, blocked, taken, box, other=None):
    """(k, Spot) for the largest k < n whose row (``make(k)`` -> its fragment) has a spot, or
    (0, None): the report's 'n=8 does not fit; 6 would'."""
    for k in range(n - 1, 0, -1):
        spot = place_on_patch(make(k), cat, ore, blocked, taken, box, other)
        if spot is not None:
            return k, spot
    return 0, None


def cover(make, lo, hi, cat, ore, blocked, taken, box, other=None):
    """(k, Spot): the most drills ``lo <= k <= hi`` whose row (``make(k)`` -> its fragment) has a
    **clean** spot on the patch (every body on the resource, no mining area on another resource,
    nothing on blocked or taken ground), or (0, None) when not even ``lo`` has one. PLAN-ORGANIC
    M2: ``MinerRow<n=auto> @patch(RES)`` takes its count from the patch.

    ``hi`` is first cut to the rows whose frame fits the ore's bounding box either way round,
    then the count is found by bisection: a shorter row of the same kind stands wherever a longer
    one does (its drills, belt and route end are the longer row's first ones), so fitting is
    monotone in k."""
    if not ore or hi < lo or lo < 1:
        return 0, None
    xs, ys = [t[0] for t in ore], [t[1] for t in ore]
    long_, short = sorted((max(xs) - min(xs) + 1, max(ys) - min(ys) + 1), reverse=True)
    while hi >= lo:
        w, h = make(hi).size
        if max(w, h) <= long_ and min(w, h) <= short:
            break
        hi -= 1
    if hi < lo:
        return 0, None

    def clean(k):
        spot = place_on_patch(make(k), cat, ore, blocked, taken, box, other)
        return spot if spot is not None and spot.clean else None

    top = clean(hi)
    if top is not None:
        return hi, top
    good = clean(lo)
    if good is None:
        return 0, None
    a, b = lo, hi                     # a fits clean, b does not
    while b - a > 1:
        m = (a + b) // 2
        spot = clean(m)
        if spot is not None:
            a, good = m, spot
        else:
            b = m
    return a, good
