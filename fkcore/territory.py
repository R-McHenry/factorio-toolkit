"""fkcore.territory: the world placer (PLAN-ORGANIC part T, wave 1: T1 to T3).

Where sealed modules are placed, each movable instance is a **seed** with an **area need**; its
territory is its cell in a power diagram (an additively weighted Voronoi tessellation) over the
plot, clipped by the blocked ground, rasterised on a coarse grid of ``cell`` tiles. The weights
adapt in the same call until every cell holds its need (a cell under its need grows its weight,
over it shrinks) or a cap. A tile nearer a blocked region (water, a fixed instance, the plot's
edge) than any seed belongs to no one; a cell an obstacle cuts in two keeps the piece holding its
seed. A fixed instance (one with an ``@`` hint) is a seed that does not move and whose cell is
exactly its frame.

The forces are PLAN-4.0's Lagrangian over seeds (``fkcore.layout``): a sweep offers each movable
seed +-s and +-2s on each axis and the four rotations (its declared frame must fit: inside the
box, off the blocked ground and the other frames); a net's cost is the walk between the two
modules' ports, each port on **its cell's boundary facing its partner** (the 2.0.41 rule applied
to cells: a declared ``@side[pos]`` projected onto the cell, the outermost cell tile in that
column or row; an unpinned port the boundary tile of its side nearest the partner's seed); the
walk runs on the coarse grid inside the terminals' window, a tile inside any cell priced
``trespass`` (the real router keeps out of a sealed frame), a tile several routes cross priced by
lambda as the instance loop does. The step schedule is geometric (32 down to 1) and the grid
follows it (8 tiles a cell for the two coarse steps, 4 after; the territories are cut at 1).

Every quantity is an integer (half-tiles for the seed points, quarter-tile^2 for the weights,
milli-tiles for the costs), so the Rust kernel (``fkroute.voronoi``, ``fkroute.place_seeds``:
native/fkroute/src/territory.rs and place.rs) and the Python here agree exactly; FK_NATIVE=0
forces Python, FK_NATIVE=check runs both and raises on a difference. A territory is a list of
row runs ``[(y, x0, x1)]`` (x1 exclusive), what part H's ``Frame`` reads unchanged. Stdlib only;
the kernel is a speed-up, never a dependency.
"""
from __future__ import annotations

import heapq
import json
import math
import os
import time
from dataclasses import dataclass, field

try:
    import fkroute as _native
except ImportError:          # stdlib only: the native kernel is a speed-up, never a dependency
    _native = None

__all__ = ["Seed", "TNet", "TParams", "TSpec", "TResult", "voronoi", "runs_of", "place_seeds",
           "need_of", "build_tspec", "layout_world", "world_scope"]

MILLI = 1000
ROOM = 3                     # the room factor build_spec gives an unbuilt module's instances
_SIDES = "nesw"
_DX = (0, 1, 0, -1)
_DY = (-1, 0, 1, 0)


# -- the spec --------------------------------------------------------------------------------------
@dataclass
class Seed:
    """One module instance: ``size`` its declared (unturned) frame, the claim inside its cell;
    ``need`` in tiles; ``min_width`` its longest rigid body; ``at`` (x, y, rot) the corner of its
    turned frame or None (unplaced); ``ports`` [(name, side, pos or None)] in its own frame."""
    name: str
    size: tuple
    need: int
    min_width: int
    at: tuple | None
    movable: bool
    ports: list = field(default_factory=list)


@dataclass
class TNet:
    """``terms``: [(seed index, port index, driver)] or, for the scope's own port on the box's
    edge, [(-1, edge index, driver)] into ``TSpec.edges``."""
    name: str
    weight: int
    terms: list


@dataclass
class TParams:
    sweeps: int = 60          # the cap; it stops on its own when no move helps at the smallest step
    alpha: int = 500          # milli-tiles of price added per belt of overuse, per sweep
    decay: int = 800          # per mille kept where no route crowds
    reach: int = 5            # an underground's reach in tiles (tunnels when the cell allows)
    steps: tuple = (32, 16, 8, 4, 2, 1)
    cells: tuple = (8, 8, 4, 4, 4, 4)     # the grid's cell per step
    final_cell: int = 1       # the grid the territories are cut on at the end
    trespass: int = MILLI     # milli-tiles added per tile inside any cell: a belt keeps outside
    iters: int = 40           # weight adaptation rounds per voronoi call
    tol: int = 5              # per cent of its need a cell may miss


@dataclass
class TSpec:
    box: tuple                # (x0, y0, x1, y1): the plot
    blocked: list             # [(x0, y0, x1, y1)] rectangles nothing may cover or cross
    seeds: list               # [Seed]
    nets: list                # [TNet]
    edges: list = field(default_factory=list)   # [(name, side, pos or None)]: the scope's ports
    params: TParams = field(default_factory=TParams)


@dataclass
class TResult:
    at: list                  # per seed: (x, y, rot) corner of the turned frame, or None
    cells: list               # per seed: row runs [(y, x0, x1)]
    areas: list               # per seed: tiles
    weights: list
    ports: dict               # (seed, port) or (-1, edge) -> (x, y) tile, at the end
    before: list              # per net: relaxed cost in milli-tiles at the start (-1 unreached)
    after: list
    hot: list                 # [((x, y), belts)]
    sweeps: int
    unreached: list           # [(net, term)]


# -- the grid --------------------------------------------------------------------------------------
class Grid:
    """A coarse grid of ``c``-tile cells over ``box``; cell (i, j) covers tiles [xa, xb) x
    [ya, yb) (clipped at the box's far edge); its centre in half-tiles is (xa + xb, ya + yb)."""

    def __init__(self, box, c):
        self.x0, self.y0, self.x1, self.y1 = box
        self.c = c
        self.gw = max(0, (self.x1 - self.x0 + c - 1) // c)
        self.gh = max(0, (self.y1 - self.y0 + c - 1) // c)
        self.n = self.gw * self.gh
        self.xa = [self.x0 + i * c for i in range(self.gw)]
        self.xb = [min(self.x0 + (i + 1) * c, self.x1) for i in range(self.gw)]
        self.ya = [self.y0 + j * c for j in range(self.gh)]
        self.yb = [min(self.y0 + (j + 1) * c, self.y1) for j in range(self.gh)]
        self.tiles = [(self.xb[k % self.gw] - self.xa[k % self.gw])
                      * (self.yb[k // self.gw] - self.ya[k // self.gw]) for k in range(self.n)]

    def cell_of(self, x, y):
        """The index of the cell holding tile (x, y), or None."""
        if not (self.x0 <= x < self.x1 and self.y0 <= y < self.y1):
            return None
        return ((y - self.y0) // self.c) * self.gw + (x - self.x0) // self.c

    def centre(self, k):
        i, j = k % self.gw, k // self.gw
        return self.xa[i] + self.xb[i], self.ya[j] + self.yb[j]

    def tile(self, k):
        """The top-left tile of cell ``k``: how a cell is reported."""
        return self.xa[k % self.gw], self.ya[k // self.gw]

    def overlaps(self, rect):
        """The cells a tile rectangle (x0, y0, x1, y1) touches."""
        rx0, ry0, rx1, ry1 = rect
        rx0, ry0 = max(rx0, self.x0), max(ry0, self.y0)
        rx1, ry1 = min(rx1, self.x1), min(ry1, self.y1)
        if rx0 >= rx1 or ry0 >= ry1:
            return []
        i0, i1 = (rx0 - self.x0) // self.c, (rx1 - 1 - self.x0) // self.c
        j0, j1 = (ry0 - self.y0) // self.c, (ry1 - 1 - self.y0) // self.c
        return [j * self.gw + i for j in range(j0, j1 + 1) for i in range(i0, i1 + 1)]

    def inside(self, k, rect):
        """Cell ``k``'s centre lies inside the tile rectangle."""
        cx, cy = self.centre(k)
        return 2 * rect[0] <= cx < 2 * rect[2] and 2 * rect[1] <= cy < 2 * rect[3]


def wall_dist2(grid, wall):
    """Per cell, the squared distance in half-tiles from its centre to the nearest wall cell's
    centre (``wall[k]`` true) or to the ring just outside the grid: Meijster's exact squared
    Euclidean distance transform on the grid padded by one wall ring, times (2c)^2."""
    gw, gh = grid.gw + 2, grid.gh + 2
    inf = gw + gh
    g = [0] * (gw * gh)
    for i in range(gw):
        prev = inf
        for j in range(gh):
            k = j * gw + i
            if i == 0 or j == 0 or i == gw - 1 or j == gh - 1 or wall[(j - 1) * grid.gw + (i - 1)]:
                prev = 0
            else:
                prev = prev + 1 if prev < inf else inf
            g[k] = prev
        prev = inf
        for j in range(gh - 1, -1, -1):
            k = j * gw + i
            if g[k] == 0:
                prev = 0
            else:
                prev = prev + 1 if prev < inf else inf
                if prev < g[k]:
                    g[k] = prev
    out = [0] * grid.n
    s, t = [0] * gw, [0] * gw
    scale = (2 * grid.c) ** 2
    for j in range(1, gh - 1):
        row = j * gw
        gj = g[row:row + gw]
        q = 0
        s[0] = t[0] = 0
        for u in range(1, gw):
            while q >= 0 and (t[q] - s[q]) ** 2 + gj[s[q]] ** 2 > (t[q] - u) ** 2 + gj[u] ** 2:
                q -= 1
            if q < 0:
                q, s[0] = 0, u
            else:
                i = s[q]
                w = 1 + (u * u - i * i + gj[u] ** 2 - gj[i] ** 2) // (2 * (u - i))
                if w < gw:
                    q += 1
                    s[q], t[q] = u, w
        for u in range(gw - 1, -1, -1):
            if 1 <= u <= gw - 2:
                out[(j - 1) * grid.gw + (u - 1)] = ((u - s[q]) ** 2 + gj[s[q]] ** 2) * scale
            if u == t[q]:
                q -= 1
    return out


def seed_point(at, size):
    """The seed's point in half-tiles: the centre of its turned frame at corner ``at``."""
    x, y, rot = at
    w, h = size if rot % 2 == 0 else size[::-1]
    return 2 * x + w, 2 * y + h


def turned_box(at, size):
    x, y, rot = at
    w, h = size if rot % 2 == 0 else size[::-1]
    return x, y, x + w, y + h


def turn_tile(px, py, rot, size):
    """Tile (px, py) of a ``size`` frame turned ``rot`` quarter turns clockwise, in the turned
    frame (``compose.turn`` of the tile's centre, in integers)."""
    w, h = size
    rot %= 4
    if rot == 0:
        return px, py
    if rot == 1:
        return h - 1 - py, px
    if rot == 2:
        return w - 1 - px, h - 1 - py
    return py, w - 1 - px


# -- the power diagram -----------------------------------------------------------------------------
def _assign(grid, points, weights, frames, fixed, wall, wd2, fixed_owner, owner, ks):
    """Owner per cell in ``ks``: the seed whose declared frame holds the cell's centre (its
    claim, outright), else the movable seed of the least power distance when it beats the wall,
    -1 else; a wall or a fixed instance's cell keeps what it has (a fixed seed's cell is its frame
    and it competes for nothing)."""
    for k in ks:
        if wall[k] or fixed_owner[k] >= 0:
            continue
        cx, cy = grid.centre(k)
        who = -1
        for i, rect in enumerate(frames):
            if rect is not None and 2 * rect[0] <= cx < 2 * rect[2] and 2 * rect[1] <= cy < 2 * rect[3]:
                who = i
                break
        if who < 0:
            best = wd2[k]
            for i, (sx, sy) in enumerate(points):
                if sx is None or fixed[i] is not None:
                    continue
                d = (cx - sx) ** 2 + (cy - sy) ** 2 - weights[i]
                if d < best:
                    best, who = d, i
        owner[k] = who


def _prune(grid, owner, i, home):
    """Keep of seed ``i``'s cells the 4-connected piece holding ``home`` (the cell under its
    seed point); the rest is nobody's. -> the area in tiles."""
    if home is None or owner[home] != i:
        for k in range(grid.n):
            if owner[k] == i:
                owner[k] = -1
        return 0
    seen = {home}
    todo = [home]
    area = grid.tiles[home]
    gw = grid.gw
    while todo:
        k = todo.pop()
        x, y = k % gw, k // gw
        for d in range(4):
            nx, ny = x + _DX[d], y + _DY[d]
            if 0 <= nx < gw and 0 <= ny < grid.gh:
                nk = ny * gw + nx
                if nk not in seen and owner[nk] == i:
                    seen.add(nk)
                    area += grid.tiles[nk]
                    todo.append(nk)
    for k in range(grid.n):
        if owner[k] == i and k not in seen:
            owner[k] = -1
    return area


class Diagram:
    """The power diagram of seeds on ``grid``: ``points`` per seed its point in half-tiles or
    None (unplaced), ``frames`` per seed its declared frame as placed (a tile rectangle it owns
    outright) or None, ``fixed`` per seed its frame when it does not move (its cell exactly) or
    None, ``owner`` per cell (-1 nobody, -2 a wall, i a seed), ``areas`` and ``weights``."""

    def __init__(self, grid, blocked, fixed, weights):
        self.grid = grid
        self.n_seeds = len(fixed)
        self.fixed = list(fixed)
        self.points = [None] * self.n_seeds
        self.frames = [None] * self.n_seeds
        self.weights = list(weights)
        self.wall = [False] * grid.n
        for rect in blocked:
            for k in grid.overlaps(rect):
                self.wall[k] = True
        self.fixed_owner = [-1] * grid.n
        self.areas = [0] * self.n_seeds
        for i, rect in enumerate(fixed):
            if rect is None:
                continue
            for k in grid.overlaps(rect):
                if grid.inside(k, rect):
                    self.fixed_owner[k] = i
                    self.areas[i] += grid.tiles[k]
                else:
                    self.wall[k] = True
        self.wd2 = wall_dist2(grid, self.wall)
        self.owner = [-2 if self.wall[k] else self.fixed_owner[k] for k in range(grid.n)]

    def recompute(self, ks=None):
        """Assign the cells in ``ks`` (all when None), prune every movable seed to the piece
        holding its point."""
        grid = self.grid
        pts = [(None, None) if p is None else p for p in self.points]
        _assign(grid, pts, self.weights, self.frames, self.fixed, self.wall, self.wd2,
                self.fixed_owner, self.owner, range(grid.n) if ks is None else ks)
        for i in range(self.n_seeds):
            if self.fixed[i] is not None:
                continue
            if self.points[i] is None:
                self.areas[i] = 0
                continue
            sx, sy = self.points[i]
            self.areas[i] = _prune(grid, self.owner, i, grid.cell_of(sx // 2, sy // 2))

    def adapt(self, needs, iters, tol):
        """Capacity-constrained weights: ``iters`` rounds of recompute and step (a cell under its
        need grows its weight, over it shrinks, by the shortfall over the seed's **rate**, the
        tiles its cell gains per unit of weight as observed on the last step, in 1/256: it starts
        at 1/4, a step that moved the area the wrong way or not at all halves it) until every
        movable cell is within ``tol`` per cent of its need or the cap. -> the rounds run."""
        n = self.n_seeds
        rate = [64] * n
        last_dw = [0] * n
        last_area = [0] * n
        cap = (2 * max(self.grid.x1 - self.grid.x0, self.grid.y1 - self.grid.y0)) ** 2
        rounds = 0
        while True:
            self.recompute()
            rounds += 1
            for i in range(n):
                if last_dw[i]:
                    seen = (self.areas[i] - last_area[i]) * 256 // last_dw[i]
                    rate[i] = max(8, min(4096, (rate[i] + seen) // 2)) if seen > 0 \
                        else min(4096, rate[i] * 2)
                last_dw[i] = 0
            off = [i for i in range(n) if self.fixed[i] is None and self.points[i] is not None
                   and abs(self.areas[i] - needs[i]) * 100 > tol * needs[i]]
            if not off or rounds > iters:
                return rounds
            for i in off:
                diff = needs[i] - self.areas[i]
                dw = diff * 256 // rate[i]
                w = max(-cap, min(cap, self.weights[i] + dw))
                last_dw[i] = w - self.weights[i]
                last_area[i] = self.areas[i]
                self.weights[i] = w
            self.keep_homes(cap)

    def keep_homes(self, cap):
        """No movable seed without a frame loses the cell under its point: there its power
        distance stays below the wall's and every other movable seed's (the weight raised to just
        above that floor). A seed with a frame holds it outright and may shrink to it."""
        grid, n = self.grid, self.n_seeds
        live = [i for i in range(n) if self.fixed[i] is None and self.points[i] is not None]
        for i in live:
            if self.frames[i] is not None:
                continue
            sx, sy = self.points[i]
            home = grid.cell_of(sx // 2, sy // 2)
            if home is None or self.wall[home] or self.fixed_owner[home] >= 0:
                continue
            cx, cy = grid.centre(home)
            d_self = (cx - sx) ** 2 + (cy - sy) ** 2
            floor = d_self - self.wd2[home]
            for j in live:
                if j == i:
                    continue
                tx, ty = self.points[j]
                floor = max(floor, d_self - (cx - tx) ** 2 - (cy - ty) ** 2 + self.weights[j])
            if self.weights[i] <= floor:
                self.weights[i] = min(cap, floor + 1)

    def boundary(self, i, side):
        """The cells of seed ``i`` whose neighbour in direction ``side`` is not its own, sorted."""
        grid, d = self.grid, _SIDES.index(side)
        out = []
        for k in range(grid.n):
            if self.owner[k] != i:
                continue
            x, y = k % grid.gw + _DX[d], k // grid.gw + _DY[d]
            if not (0 <= x < grid.gw and 0 <= y < grid.gh) or self.owner[y * grid.gw + x] != i:
                out.append(k)
        return out


def voronoi_py(seeds, needs, box, blocked, cell, weights=None, fixed=None, iters=40, tol=5,
               frames=None):
    """The reference: ``seeds`` [(x, y) or None] seed points in **half-tiles**, ``needs`` in
    tiles, ``fixed`` per seed a tile rectangle (its cell exactly, it does not compete) or None,
    ``frames`` per seed a tile rectangle it owns outright (the diagram shares out the rest) or
    None, ``blocked`` rectangles. -> (owner per cell, areas, weights, (gw, gh)). The grid is
    ``box`` in ``cell`` tiles, row-major."""
    n = len(seeds)
    grid = Grid(box, cell)
    dia = Diagram(grid, blocked, [None] * n if fixed is None else list(fixed),
                  [0] * n if weights is None else weights)
    dia.points = [None if p is None else (int(p[0]), int(p[1])) for p in seeds]
    if frames is not None:
        dia.frames = [None if r is None else tuple(r) for r in frames]
    dia.adapt(list(needs), iters, tol)
    return list(dia.owner), list(dia.areas), list(dia.weights), (grid.gw, grid.gh)


def native_on():
    return _native is not None and hasattr(_native, "voronoi") \
        and os.environ.get("FK_NATIVE", "1") != "0"


def which():
    return "fkroute" if native_on() else "python"


def voronoi(seeds, needs, box, blocked, cell, weights=None, fixed=None, iters=40, tol=5,
            frames=None):
    """The power diagram with adapted weights: in fkroute when it can, else Python; FK_NATIVE=check
    runs both and raises on a difference. See :func:`voronoi_py`."""
    mode = os.environ.get("FK_NATIVE", "1")
    if native_on():
        rects = lambda rs: None if rs is None else \
            [None if r is None else tuple(int(v) for v in r) for r in rs]            # noqa: E731
        got = _native.voronoi([None if p is None else (int(p[0]), int(p[1])) for p in seeds],
                              [int(v) for v in needs], tuple(int(v) for v in box),
                              [tuple(int(v) for v in r) for r in blocked], int(cell),
                              None if weights is None else [int(w) for w in weights],
                              rects(fixed), int(iters), int(tol), rects(frames))
        got = (list(got[0]), list(got[1]), list(got[2]), tuple(got[3]))
        if mode == "check":
            py = voronoi_py(seeds, needs, box, blocked, cell, weights, fixed, iters, tol, frames)
            if got != py:
                raise AssertionError(f"fkroute.voronoi differs from voronoi_py:\n  {got}\n  {py}")
        return got
    return voronoi_py(seeds, needs, box, blocked, cell, weights, fixed, iters, tol, frames)


def runs_of(owner, grid, i):
    """Seed ``i``'s cells as tile row runs [(y, x0, x1)], x1 exclusive, rows ascending."""
    out = []
    gw = grid.gw
    for j in range(grid.gh):
        row = owner[j * gw:(j + 1) * gw]
        runs = []
        x = 0
        while x < gw:
            if row[x] != i:
                x += 1
                continue
            s = x
            while x < gw and row[x] == i:
                x += 1
            runs.append((grid.xa[s], grid.xb[x - 1]))
        if runs:
            for y in range(grid.ya[j], grid.yb[j]):
                out.extend((y, a, b) for a, b in runs)
    return out


# -- the sweep over seeds ------------------------------------------------------------------------
class _World:
    """The placer's state: the diagram on the current grid, the price per cell, the routes."""

    def __init__(self, spec):
        self.spec = spec
        self.p = spec.params
        self.at = [None if sd.at is None else tuple(sd.at) for sd in spec.seeds]
        self.weights = [0] * len(spec.seeds)
        self.needs = [sd.need for sd in spec.seeds]
        self.grid = None
        self.dia = None
        self.price = []
        self.hard = [tuple(r) for r in spec.blocked]
        # a pinned edge port's tile and the tile inside it: no frame may cover them
        self.edge_tiles = []
        bx0, by0, bx1, by1 = spec.box
        for _name, side, pos in spec.edges:
            if pos is None:
                continue
            d = _SIDES.index(side)
            if side in "ns":
                t = (bx0 + pos, by0 if side == "n" else by1 - 1)
            else:
                t = (bx0 if side == "w" else bx1 - 1, by0 + pos)
            self.edge_tiles.append(t)
            self.edge_tiles.append((t[0] - _DX[d], t[1] - _DY[d]))
        bw, bh = bx1 - bx0, by1 - by0
        self.penalty = 2 * (bw + bh) * MILLI      # a terminal no route reaches costs this

    def set_cell(self, c):
        """The grid at ``c`` tiles a cell; the price carried over by tile."""
        old_grid, old_price = self.grid, self.price
        self.grid = Grid(self.spec.box, c)
        self.price = [0] * self.grid.n
        if old_grid is not None:
            for k in range(self.grid.n):
                x, y = self.grid.tile(k)
                ok = old_grid.cell_of(x, y)
                if ok is not None:
                    self.price[k] = old_price[ok]
        fixed = [turned_box(sd.at, sd.size) if not sd.movable and sd.at is not None else None
                 for sd in self.spec.seeds]
        self.dia = Diagram(self.grid, self.spec.blocked, fixed, self.weights)
        self.dia.points = [None if a is None else seed_point(a, sd.size)
                           for a, sd in zip(self.at, self.spec.seeds)]
        self.dia.frames = [turned_box(a, sd.size) if a is not None and sd.movable else None
                           for a, sd in zip(self.at, self.spec.seeds)]
        self.dia.recompute()

    def fits(self, i, at):
        """The turned frame inside the box, off the blocked rectangles, the other frames and the
        pinned edge ports' tiles; each pinned port's belt has its tile outside the frame free (in
        the box, off the blocked ground and every other frame) and one more tile in the box beyond
        it (a port on a frame edge against another frame or the box is a belt the router cannot
        lay)."""
        sd = self.spec.seeds[i]
        box = turned_box(at, sd.size)
        bx0, by0, bx1, by1 = self.spec.box
        if box[0] < bx0 or box[1] < by0 or box[2] > bx1 or box[3] > by1:
            return False
        for r in self.hard:
            if box[0] < r[2] and r[0] < box[2] and box[1] < r[3] and r[1] < box[3]:
                return False
        others = []
        for j, a in enumerate(self.at):
            if j == i or a is None:
                continue
            o = turned_box(a, self.spec.seeds[j].size)
            if box[0] < o[2] and o[0] < box[2] and box[1] < o[3] and o[1] < box[3]:
                return False
            others.append(o)
        for tx, ty in self.edge_tiles:
            if box[0] <= tx < box[2] and box[1] <= ty < box[3]:
                return False
        w, h = sd.size
        rot = at[2] % 4
        for _name, side, pos in sd.ports:
            if pos is None:
                continue
            if side in "ns":
                px, py = pos, (0 if side == "n" else h - 1)
            else:
                px, py = (0 if side == "w" else w - 1), pos
            tx, ty = turn_tile(px, py, rot, (w, h))
            d = (_SIDES.index(side) + rot) % 4
            ox, oy = at[0] + tx + _DX[d], at[1] + ty + _DY[d]
            fx, fy = ox + _DX[d], oy + _DY[d]
            if not (bx0 <= fx < bx1 and by0 <= fy < by1):
                return False
            for r in self.hard + others:
                if r[0] <= ox < r[2] and r[1] <= oy < r[3]:
                    return False
        return True

    def claims(self):
        """The turned frames of the placed seeds: sealed, so no belt of the scope crosses them."""
        return [turned_box(a, sd.size) for a, sd in zip(self.at, self.spec.seeds) if a is not None]

    def move(self, i, at):
        self.at[i] = at
        sd = self.spec.seeds[i]
        self.dia.points[i] = None if at is None else seed_point(at, sd.size)
        self.dia.frames[i] = None if at is None or not sd.movable else turned_box(at, sd.size)

    # -- terminals
    def term_cell(self, term, partner):
        """The grid cell of a terminal: (seed, port) or (-1, edge). ``partner`` the other end's
        seed point (half-tiles) or None. -> (cell index, off-frame) or (None, False)."""
        grid, dia = self.grid, self.dia
        who, idx, _drv = term
        if who < 0:
            _name, side, pos = self.spec.edges[idx]
            d = _SIDES.index(side)
            if side in "ns":
                y = grid.y0 if side == "n" else grid.y1 - 1
                if pos is not None:
                    return grid.cell_of(grid.x0 + pos, y), False
                ks = [grid.cell_of(grid.xa[ii], y) for ii in range(grid.gw)]
            else:
                x = grid.x0 if side == "w" else grid.x1 - 1
                if pos is not None:
                    return grid.cell_of(x, grid.y0 + pos), False
                ks = [grid.cell_of(x, grid.ya[jj]) for jj in range(grid.gh)]
            ks = [k for k in ks if k is not None and not dia.wall[k]]
            return self._nearest(ks, partner), False
        at = self.at[who]
        if at is None:
            return None, False
        sd = self.spec.seeds[who]
        _name, side, pos = sd.ports[idx]
        rot = at[2] % 4
        tside = _SIDES[(_SIDES.index(side) + rot) % 4]
        if pos is not None:
            w, h = sd.size
            if side in "ns":
                px, py = pos, (0 if side == "n" else h - 1)
            else:
                px, py = (0 if side == "w" else w - 1), pos
            tx, ty = turn_tile(px, py, rot, (w, h))
            tx, ty = at[0] + tx, at[1] + ty
            k = grid.cell_of(tx, ty)
            if k is None:
                return None, True
            ci, cj = k % grid.gw, k // grid.gw
            mine = []
            if tside in "ns":
                mine = [cj2 * grid.gw + ci for cj2 in range(grid.gh) if dia.owner[cj2 * grid.gw + ci] == who]
                if mine:
                    return (min(mine) if tside == "n" else max(mine)), False
            else:
                mine = [cj * grid.gw + ci2 for ci2 in range(grid.gw) if dia.owner[cj * grid.gw + ci2] == who]
                if mine:
                    return (min(mine) if tside == "w" else max(mine)), False
            # the column or row is not the cell's: the nearest boundary tile of that side
            b = dia.boundary(who, tside) or [k2 for k2 in range(grid.n) if dia.owner[k2] == who]
            return self._nearest(b, grid.centre(k)), True
        b = dia.boundary(who, tside)
        if not b:
            b = [k2 for k2 in range(grid.n) if dia.owner[k2] == who]
        return self._nearest(b, partner), False

    def _nearest(self, ks, point):
        """The cell of ``ks`` nearest ``point`` (half-tiles; None: the first), ties (y, x)."""
        if not ks:
            return None
        if point is None:
            return min(ks, key=lambda k: (k // self.grid.gw, k % self.grid.gw))
        px, py = point
        best = None
        for k in ks:
            cx, cy = self.grid.centre(k)
            key = ((cx - px) ** 2 + (cy - py) ** 2, k // self.grid.gw, k % self.grid.gw)
            if best is None or key < best[0]:
                best = (key, k)
        return best[1]

    def edge_point(self, idx, point):
        """Where edge terminal ``idx`` stands for a seed at ``point`` (half-tiles): its pinned
        tile's centre, else the point of its side nearest ``point`` (the side's middle when
        None), in half-tiles."""
        _name, side, pos = self.spec.edges[idx]
        x0, y0, x1, y1 = self.spec.box
        if side in "ns":
            y = 2 * y0 + 1 if side == "n" else 2 * y1 - 1
            if pos is not None:
                return 2 * (x0 + pos) + 1, y
            return (x0 + x1 if point is None else min(max(point[0], 2 * x0 + 1), 2 * x1 - 1)), y
        x = 2 * x0 + 1 if side == "w" else 2 * x1 - 1
        if pos is not None:
            return x, 2 * (y0 + pos) + 1
        return x, (y0 + y1 if point is None else min(max(point[1], 2 * y0 + 1), 2 * y1 - 1))

    def port_point(self, who, idx):
        """Where port ``idx`` of placed seed ``who`` stands, in half-tiles: its pinned tile's
        centre in the turned frame, else the seed's point."""
        at = self.at[who]
        sd = self.spec.seeds[who]
        _name, side, pos = sd.ports[idx]
        if pos is None:
            return seed_point(at, sd.size)
        w, h = sd.size
        if side in "ns":
            px, py = pos, (0 if side == "n" else h - 1)
        else:
            px, py = (0 if side == "w" else w - 1), pos
        tx, ty = turn_tile(px, py, at[2] % 4, (w, h))
        return 2 * (at[0] + tx) + 1, 2 * (at[1] + ty) + 1

    def term_partner(self, net, ti):
        """The point the other ends of ``net`` stand at for terminal ``ti`` (the first placed one,
        drivers first: its pinned port's tile, else its seed; an edge terminal as ``edge_point``
        puts it), in half-tiles, or None."""
        who_me = net.terms[ti][0]
        me = None
        if who_me >= 0 and self.at[who_me] is not None:
            me = self.port_point(who_me, net.terms[ti][1])
        pts = []
        for tj, (who, idx, drv) in enumerate(net.terms):
            if tj == ti:
                continue
            if who >= 0 and self.at[who] is not None:
                pts.append((not drv, tj, self.port_point(who, idx)))
            elif who < 0:
                pts.append((not drv, tj, self.edge_point(idx, me)))
        if not pts:
            return None
        pts.sort()
        return pts[0][2]

    def terminals(self, n):
        """Per term of net ``n``: its cell or None, and whether a pin fell off its cell."""
        net = self.spec.nets[n]
        out = []
        for ti, term in enumerate(net.terms):
            out.append(self.term_cell(term, self.term_partner(net, ti)))
        return out

    # -- the walk
    def field(self, seeds, window, priced=True, goals=()):
        """Dijkstra over the grid's cells inside ``window`` (i0, j0, i1, j1 inclusive), a step
        to the first cell within ``reach`` cells along a heading that is neither a wall nor inside
        a placed seed's frame (sealed: the router keeps out; a ``goals`` cell, a terminal, may be
        entered), at ``c`` milli-tiles a tile plus the cell's price and ``trespass`` when a seed
        owns it. -> ({cell: dist}, {cell: pred})."""
        grid, dia, p = self.grid, self.dia, self.p
        i0, j0, i1, j1 = window
        gw = grid.gw
        reach = max(1, p.reach // grid.c) if grid.c <= p.reach else 1
        step = grid.c * MILLI
        frames = self.claims()
        goals = set(goals)

        def open_(u):
            if dia.owner[u] == -2:
                return False
            if u in goals:
                return True
            cx, cy = grid.centre(u)
            return not any(2 * r[0] <= cx < 2 * r[2] and 2 * r[1] <= cy < 2 * r[3] for r in frames)

        dist, pred = {}, {}
        todo = []
        for k in sorted(set(seeds)):
            dist[k] = 0
            pred[k] = -1
            todo.append((0, k % gw, k // gw))
        heapq.heapify(todo)
        while todo:
            d, x, y = heapq.heappop(todo)
            k = y * gw + x
            if d > dist[k]:
                continue
            for hd in range(4):
                for j in range(1, reach + 1):
                    ux, uy = x + _DX[hd] * j, y + _DY[hd] * j
                    if not (i0 <= ux <= i1 and j0 <= uy <= j1):
                        break
                    u = uy * gw + ux
                    if open_(u):
                        nd = d + j * step
                        if priced:
                            nd += self.price[u] + (p.trespass * grid.c if dia.owner[u] >= 0 else 0)
                        if u not in dist or nd < dist[u]:
                            dist[u] = nd
                            pred[u] = k
                            heapq.heappush(todo, (nd, ux, uy))
                        break
        return dist, pred

    def window(self, ks):
        """The window round cells ``ks``: their bounding box grown by a margin."""
        grid = self.grid
        margin = max(6, (grid.gw + grid.gh) // 12)
        xs = [k % grid.gw for k in ks]
        ys = [k // grid.gw for k in ks]
        return (max(0, min(xs) - margin), max(0, min(ys) - margin),
                min(grid.gw - 1, max(xs) + margin), min(grid.gh - 1, max(ys) + margin))

    @staticmethod
    def trace(pred, k):
        out = []
        while k >= 0:
            out.append(k)
            k = pred.get(k, -1)
        return out

    def eval_net(self, n, priced=True, terms=None):
        """-> (cost, [route cells], [unreached term indexes], [off-frame term indexes])."""
        net = self.spec.nets[n]
        cells = self.terminals(n) if terms is None else terms
        drivers = [(ti, k) for ti, ((k, _off), (_w, _i, drv)) in enumerate(zip(cells, net.terms))
                   if drv and k is not None]
        consumers = [(ti, k) for ti, ((k, _off), (_w, _i, drv)) in enumerate(zip(cells, net.terms))
                     if not drv and k is not None]
        off = [ti for ti, (k, o) in enumerate(cells) if o]
        # a placed seed whose port has no tile (its cell is empty): no partner reaches it
        lost = [ti for ti, ((k, _o), (who, _i, _d)) in enumerate(zip(cells, net.terms))
                if k is None and (who < 0 or self.at[who] is not None)]
        cost = self.penalty * len(lost)          # a terminal no route reaches is dear, never free
        if not drivers or not consumers:
            return cost, [], lost, off
        win = self.window([k for _ti, k in drivers + consumers])
        routes, unreached = [], []
        goals = [k for _ti, k in drivers + consumers]
        dist, pred = self.field([k for _ti, k in drivers], win, priced, goals)
        unreached.extend(lost)
        for ti, k in consumers:
            if k in dist:
                cost += dist[k]
                routes.append(self.trace(pred, k))
            else:
                unreached.append(ti)
                cost += self.penalty
        if len(drivers) > 1:
            fields = [self.field([k], win, priced, goals) for _ti, k in drivers]
            in_tree = {0}
            while len(in_tree) < len(drivers):
                best = None
                for a in sorted(in_tree):
                    da = fields[a][0]
                    for b in range(len(drivers)):
                        if b in in_tree:
                            continue
                        k = drivers[b][1]
                        if k in da and (best is None or (da[k], a, b) < best):
                            best = (da[k], a, b)
                if best is None:
                    far = [b for b in range(len(drivers)) if b not in in_tree]
                    unreached.extend(drivers[b][0] for b in far)
                    cost += self.penalty * len(far)
                    break
                d, a, b = best
                in_tree.add(b)
                cost += d
                routes.append(self.trace(fields[a][1], drivers[b][1]))
        return cost, routes, unreached, off

    def start(self, i):
        """Where an unplaced seed starts: the fitting corner and rotation on the first step's
        lattice nearest (weighted Manhattan between seed points, in half-tiles) its nets' placed
        partners, or nearest the box's centre; ties to the smaller (y, x, rot)."""
        spec = self.spec
        partners = []          # (weight, [points], [sides of unpinned edge ports])
        for net in spec.nets:
            mine = [t for t in net.terms if t[0] == i]
            if not mine:
                continue
            far, sides = [], []
            for who, idx, _drv in net.terms:
                if who == i:
                    continue
                if who >= 0 and self.at[who] is not None:
                    far.append(seed_point(self.at[who], spec.seeds[who].size))
                elif who < 0:
                    if spec.edges[idx][2] is None:
                        sides.append(spec.edges[idx][1])
                    else:
                        far.append(self.edge_point(idx, None))
            if far or sides:
                partners.append((net.weight, far, sides))
        bx0, by0, bx1, by1 = spec.box
        cx, cy = bx0 + bx1, by0 + by1
        lat = self.p.steps[0] if self.p.steps else 8
        while True:
            best = self._start_on(i, lat, partners, cx, cy)
            if best is not None or lat <= 1:
                return best
            lat //= 2           # a lattice too coarse for the box: finer until something fits

    def _start_on(self, i, lat, partners, cx, cy):
        spec = self.spec
        bx0, by0, bx1, by1 = spec.box
        best = None
        for rot in range(4):
            w, h = spec.seeds[i].size if rot % 2 == 0 else spec.seeds[i].size[::-1]
            for y in range(by0, by1 - h + 1, lat):
                for x in range(bx0, bx1 - w + 1, lat):
                    sx, sy = 2 * x + w, 2 * y + h
                    if partners:
                        score = 0
                        for wgt, far, sides in partners:
                            ds = [abs(sx - fx) + abs(sy - fy) for fx, fy in far]
                            ds += [(sy - 2 * by0, 2 * bx1 - sx, 2 * by1 - sy, sx - 2 * bx0)[_SIDES.index(s)]
                                   for s in sides]
                            score += wgt * min(ds)
                    else:
                        score = abs(sx - cx) + abs(sy - cy)
                    key = (score, y, x, rot)
                    if best is not None and key >= best[0]:
                        continue
                    if self.fits(i, (x, y, rot)):
                        best = (key, (x, y, rot))
        return None if best is None else best[1]


def _place_seeds_py(spec):
    """The reference loop; :func:`place_seeds` runs it, or the kernel's port of it."""
    p = spec.params
    st = _World(spec)
    steps = list(p.steps) or [1]
    cells = list(p.cells) or [1]
    st.set_cell(cells[0])
    for i, sd in enumerate(spec.seeds):
        if st.at[i] is None:
            at = st.start(i)
            if at is not None:
                st.move(i, at)
    st.dia.adapt(st.needs, p.iters, p.tol)
    st.weights = st.dia.weights
    nn = len(spec.nets)

    def full(priced=True):
        costs, routes, unreached, off = [], [], [], []
        u = {}
        for n in range(nn):
            c, rs, un, of = st.eval_net(n, priced)
            costs.append(c)
            routes.append(rs)
            unreached.extend((n, ti) for ti in un)
            off.extend((n, ti) for ti in of)
            for r in rs:
                for k in r:
                    u[k] = u.get(k, 0) + spec.nets[n].weight
        lagr = sum(spec.nets[n].weight * costs[n] for n in range(nn))
        lagr += sum(st.price[k] * (v - 1) for k, v in u.items() if v > 1)
        return costs, routes, u, lagr, unreached, off

    costs0, _r, _u, _l, un0, _of = full(False)
    before = [-1 if any(k == n for k, _t in un0) else costs0[n] for n in range(nn)]
    movable = [i for i, sd in enumerate(spec.seeds) if sd.movable and st.at[i] is not None]
    incident = {i: sorted({n for n, net in enumerate(spec.nets) for (w, _i, _d) in net.terms if w == i})
                for i in movable}
    costs, routes, u, lagr, _un, _of = full()
    sweeps, step_i = 0, 0
    while sweeps < p.sweeps:
        s = steps[step_i]
        c = cells[min(step_i, len(cells) - 1)]
        if c != st.grid.c:
            st.set_cell(c)
            st.dia.adapt(st.needs, p.iters, p.tol)
            st.weights = st.dia.weights
            costs, routes, u, lagr, _un, _of = full()
        deltas = [(0, 0)] + [(sx * k, 0) for k in (s, 2 * s) for sx in (-1, 1)] \
            + [(0, sy * k) for k in (s, 2 * s) for sy in (-1, 1)]
        moved = False
        for i in movable:
            cur = st.at[i]
            mine = incident[i]
            u_base = dict(u)
            for n in mine:
                for r in routes[n]:
                    for k in r:
                        u_base[k] -= spec.nets[n].weight
            base = sum(spec.nets[n].weight * costs[n] for n in range(nn) if n not in mine)
            base += sum(st.price[k] * (v - 1) for k, v in u_base.items() if v > 1)
            best = None
            owner0 = list(st.dia.owner)
            areas0 = list(st.dia.areas)
            own_cells = [k for k in range(st.grid.n) if owner0[k] == i]
            for rot in range(4):
                for dx, dy in deltas:
                    at = (cur[0] + dx, cur[1] + dy, rot)
                    if at == cur or not st.fits(i, at):
                        continue
                    st.move(i, at)
                    # the cells of the moved seed and its neighbours: the window round its old
                    # cell and its new frame, grown by the move
                    ks = own_cells + st.grid.overlaps(turned_box(at, spec.seeds[i].size))
                    if ks:
                        i0, j0, i1, j1 = st.window(ks)
                        win = [j * st.grid.gw + ii for j in range(j0, j1 + 1) for ii in range(i0, i1 + 1)]
                    else:
                        win = None
                    st.dia.recompute(win)
                    lagr_c, touched = base, []
                    for n in mine:
                        wgt = spec.nets[n].weight
                        cst, rs, _un, _of = st.eval_net(n)
                        lagr_c += wgt * cst
                        for r in rs:
                            for k in r:
                                old = u_base.get(k, 0)
                                u_base[k] = old + wgt
                                touched.append((k, wgt))
                                lagr_c += st.price[k] * (max(0, old + wgt - 1) - max(0, old - 1))
                    for k, wgt in touched:
                        u_base[k] -= wgt
                    st.move(i, cur)
                    st.dia.owner[:] = owner0
                    st.dia.areas[:] = areas0
                    key = (lagr_c, abs(dx) + abs(dy), rot, dy, dx)
                    if best is None or key < best[0]:
                        best = (key, at)
            if best is not None and best[0][0] < lagr:
                st.move(i, best[1])
                st.dia.recompute()
                costs, routes, u, lagr, _un, _of = full()
                moved = True
        sweeps += 1
        st.dia.adapt(st.needs, p.iters, p.tol)
        st.weights = st.dia.weights
        for k in range(st.grid.n):
            v = u.get(k, 0)
            if v > 1:
                st.price[k] += p.alpha * (v - 1)
            else:
                st.price[k] = st.price[k] * p.decay // MILLI
        costs, routes, u, lagr, _un, _of = full()
        if not moved:
            if step_i + 1 < len(steps):
                step_i += 1
            else:
                break
    # the territories at tile resolution
    if st.grid.c != p.final_cell:
        st.set_cell(p.final_cell)
        st.dia.adapt(st.needs, p.iters, p.tol)
        st.weights = st.dia.weights
    costs1, _r1, u1, _l, un1, off1 = full(False)
    after = [-1 if any(k == n for k, _t in un1) else costs1[n] for n in range(nn)]
    grid = st.grid
    hot = [(grid.tile(k), v) for k, v in u1.items() if v > 1]
    hot.sort(key=lambda e: (-e[1], e[0][1], e[0][0]))
    ports = {}
    for n, net in enumerate(spec.nets):
        for ti, (k, _off) in enumerate(st.terminals(n)):
            if k is not None:
                who, idx, _d = net.terms[ti]
                ports[(who, idx)] = grid.tile(k)
    cells_out = [runs_of(st.dia.owner, grid, i) for i in range(len(spec.seeds))]
    return TResult(list(st.at), cells_out, list(st.dia.areas), list(st.weights), ports, before,
                   after, hot, sweeps, sorted(set(un1)))


def _flatten(spec):
    seeds = [(sd.name, (int(sd.size[0]), int(sd.size[1])), int(sd.need), int(sd.min_width),
              None if sd.at is None else tuple(int(v) for v in sd.at), bool(sd.movable),
              [(n, s, None if p is None else int(p)) for n, s, p in sd.ports]) for sd in spec.seeds]
    nets = [(n.name, int(n.weight), [(int(a), int(b), bool(c)) for a, b, c in n.terms]) for n in spec.nets]
    edges = [(n, s, None if p is None else int(p)) for n, s, p in spec.edges]
    p = spec.params
    return (tuple(int(v) for v in spec.box), [tuple(int(v) for v in r) for r in spec.blocked],
            seeds, nets, edges,
            (int(p.sweeps), int(p.alpha), int(p.decay), int(p.reach), [int(s) for s in p.steps],
             [int(c) for c in p.cells], int(p.final_cell), int(p.trespass), int(p.iters), int(p.tol)))


def _place_seeds_native(spec):
    at, cells, areas, weights, ports, before, after, hot, sweeps, unreached = \
        _native.place_seeds(*_flatten(spec))
    return TResult([None if a is None else tuple(a) for a in at],
                   [[tuple(r) for r in c] for c in cells], list(areas), list(weights),
                   {(a, b): tuple(t) for (a, b), t in ports}, list(before), list(after),
                   [(tuple(t), u) for t, u in hot], sweeps, [tuple(e) for e in unreached])


def place_seeds(spec) -> TResult:
    """The sweep over ``spec``'s seeds: in fkroute when it can, else in Python; FK_NATIVE=check
    runs both and raises if they differ."""
    mode = os.environ.get("FK_NATIVE", "1")
    if _native is not None and hasattr(_native, "place_seeds") and mode != "0":
        got = _place_seeds_native(spec)
        if mode == "check":
            py = _place_seeds_py(spec)
            if got != py:
                raise AssertionError(f"fkroute.place_seeds differs from _place_seeds_py:\n  {got}\n  {py}")
        return got
    return _place_seeds_py(spec)


# -- the spec from a design ----------------------------------------------------------------------
def need_of(flat, cat, path):
    """(need in tiles, minimum width) of module instance ``path`` without building it: its
    declared frame's area when it has one, else the sum of its instances' footprint areas times
    ``ROOM`` (what ``build_spec`` gives them); the minimum width its longest rigid body (a Stack's
    frame, else its largest instance's longer side). A module built alone before has its hull as
    its need exactly (part H, wave 2: ``out/frames.json``); this reads the declaration."""
    from .expand import _own_frame
    inst = flat.insts[path]
    if inst.size is not None:
        w, h = int(inst.size[0]), int(inst.size[1])
        return w * h, min(w, h)
    area, longest = 0, 1
    for child in flat.scopes.get(path, {}).values():
        frame = _own_frame(flat, child.path, cat, {})
        if frame is None:
            continue
        w, h = frame[2] - frame[0], frame[3] - frame[1]
        area += w * h
        longest = max(longest, max(w, h))
    return area * ROOM, longest


def world_scope(flat, module=None):
    """The scope ``fk layout`` lays out ('' or the module's first instance) when it holds sealed
    modules without an ``@`` hint: the world placer's case. None otherwise."""
    scope = ""
    if module:
        scope = next((p for p, i in flat.insts.items() if i.module == module), None)
        if scope is None:
            return None
    for inst in flat.scopes.get(scope, {}).values():
        if inst.module is not None and "at" not in inst.hints and "patch" not in inst.hints:
            return scope
    return None


@dataclass
class BuiltWorld:
    spec: TSpec
    paths: list              # per seed: the instance path
    notes: list
    scope: str
    box_from: str


def build_tspec(flat, cat, scope="", all_=False, plot=None, params=None) -> BuiltWorld:
    """The world spec of ``scope``'s children: every module instance a seed (its declared frame
    the claim, its ports in its own frame), a placed non-module instance a blocked rectangle, the
    scope's own ports edge terminals; the scope's nets between them, weighted in belts."""
    from .expand import _own_frame, ports_of
    from .layout import _weights
    notes, seeds, paths = [], [], []
    blocked = []
    if scope:
        if flat.insts[scope].size is None:
            raise ValueError(f"{flat.insts[scope].module} declares no size: a module is laid out inside its frame")
        w, h = flat.insts[scope].size
        box, box_from = (0, 0, int(w), int(h)), f"the frame of {flat.insts[scope].module}"
    elif plot is not None:
        box, box_from = (0, 0, int(plot[0]), int(plot[1])), "--plot"
    else:
        box, box_from = None, "room for the modules"
    lane_of = getattr(flat, "lane_of", {}) or {}
    index = {}
    for name, inst in flat.scopes.get(scope, {}).items():
        path = inst.path
        at = inst.hints.get("at")
        at = None if at is None else tuple(int(v) for v in at)
        if inst.module is None:
            frame = _own_frame(flat, path, cat, {})
            if at is None or frame is None:
                notes.append(f"skip {path}: the world placer places modules; an instance is laid "
                             "by fk layout on its module")
                continue
            w, h = frame[2] - frame[0], frame[3] - frame[1]
            if at[2] % 2:
                w, h = h, w
            blocked.append((at[0], at[1], at[0] + w, at[1] + h))
            continue
        if inst.size is None:
            frame = _own_frame(flat, path, cat, {})
            if frame is None or frame[2] <= frame[0] or frame[3] <= frame[1]:
                notes.append(f"skip {path}: a module without a size whose frame is not known")
                continue
            size = (int(frame[2] - frame[0]), int(frame[3] - frame[1]))
        else:
            size = (int(inst.size[0]), int(inst.size[1]))
        need, min_w = need_of(flat, cat, path)
        ports = []
        for key in ports_of(flat, path):
            port = flat.ports[key]
            index[key] = (len(seeds), len(ports))
            ports.append((key, port.side, None if port.pos is None else int(port.pos)))
        seeds.append(Seed(path, size, need, min_w, at, at is None or all_, ports))
        paths.append(path)
    edges = []
    if scope:
        for key in ports_of(flat, scope):
            port = flat.ports[key]
            index[key] = (-1, len(edges))
            edges.append((key, port.side, None if port.pos is None else int(port.pos)))
    terms = {}
    for net in flat.nets.values():
        if getattr(net, "scope", "") != scope:
            continue
        name = lane_of.get(net.name, net.name)
        for key, _item in net.drivers:
            if key in index:
                terms.setdefault(name, []).append(index[key] + (True,))
        for key, _item in net.consumers:
            if key in index:
                terms.setdefault(name, []).append(index[key] + (False,))
    weights = _weights(flat, cat)
    for pair in set(lane_of.values()):
        weights[pair] = max(weights.get(p, 1) for p in pair.split("|"))
    nets = []
    for name, ts in sorted(terms.items()):
        ts = sorted(set(ts))
        if any(d for _a, _b, d in ts) and any(not d for _a, _b, d in ts):
            nets.append(TNet(name, weights.get(name, 1), ts))
    if box is None:
        area = sum(sd.need for sd in seeds)
        side = int(math.ceil(math.sqrt(2 * area))) + 2
        x1 = max([side] + [turned_box(sd.at, sd.size)[2] for sd in seeds if sd.at is not None])
        y1 = max([side] + [turned_box(sd.at, sd.size)[3] for sd in seeds if sd.at is not None])
        box = (0, 0, x1, y1)
    spec = TSpec(box, blocked, seeds, nets, edges, params or TParams())
    return BuiltWorld(spec, paths, notes, scope, box_from)


# -- the command ----------------------------------------------------------------------------------
def touching(cells):
    """The pairs (i, j), i < j, of seeds whose cells (row runs) share a boundary: a tile of one
    4-adjacent to a tile of the other."""
    rows = {}
    for i, runs in enumerate(cells):
        for y, x0, x1 in runs:
            rows.setdefault(y, []).append((x0, x1, i))
    pairs = set()
    for y, runs in rows.items():
        runs.sort()
        for (a0, a1, i), (b0, _b1, j) in zip(runs, runs[1:]):
            if a1 == b0 and i != j:
                pairs.add((min(i, j), max(i, j)))
        below = rows.get(y + 1)
        if not below:
            continue
        for a0, a1, i in runs:
            for b0, b1, j in below:
                if i != j and a0 < b1 and b0 < a1:
                    pairs.add((min(i, j), max(i, j)))
    return pairs


def shared_boundary_line(spec, res):
    """The report line on the nets between two modules: how many have their modules' cells
    touching (the ports then stand on a shared boundary), and which do not."""
    pairs = touching(res.cells)
    between, apart = 0, []
    for net in spec.nets:
        who = sorted({w for w, _i, _d in net.terms if w >= 0 and res.at[w] is not None})
        if len(who) < 2:
            continue
        between += 1
        off = [(a, b) for ai, a in enumerate(who) for b in who[ai + 1:] if (a, b) not in pairs]
        if off:
            names = "|".join(sorted({spec.seeds[w].name.rsplit("/", 1)[-1] for ab in off for w in ab}))
            apart.append(f"{net.name.rsplit('/', 1)[-1]} ({names})")
    if not between:
        return "  shared boundary: no net runs between two modules"
    line = f"  shared boundary: {between - len(apart)} of {between} nets between modules have their cells touching"
    if apart:
        line += "; apart: " + ", ".join(apart[:8]) + (" ..." if len(apart) > 8 else "")
    return line


def territories_path(path):
    """``out/territories.json`` beside the design."""
    return os.path.join(os.path.dirname(os.path.abspath(path)), "out", "territories.json")


def write_territories(path, built, res):
    """Each seed's cell as row runs, its position, need and area; the ports' tiles."""
    spec = built.spec
    data = {"design": os.path.basename(path), "scope": built.scope, "box": list(spec.box),
            "cells": {}}
    for i, sd in enumerate(spec.seeds):
        data["cells"][built.paths[i]] = {
            "at": None if res.at[i] is None else list(res.at[i]),
            "size": list(sd.size), "need": sd.need, "min_width": sd.min_width, "area": res.areas[i],
            "runs": [list(r) for r in res.cells[i]],
            "ports": {sd.ports[pi][0]: list(res.ports[(i, pi)]) for pi in range(len(sd.ports))
                      if (i, pi) in res.ports}}
    out = territories_path(path)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1)
    return out


def layout_world(path, flat, cat, scope, all_=False, write=False, sweeps=None, plot=None):
    """``fk layout`` on a scope that holds sealed modules without ``@``: -> (report lines, code).
    One line per module placed, ``name = Kind @(x, y, rot r)``; the territories written to
    ``out/territories.json``; the report: estimated belts before and after, hot tiles, ports no
    partner reaches, each cell's area against its need. ``--write`` writes the hints."""
    from .layout import _module_file, hint_line, written_hint, hint_text
    params = TParams() if sweeps is None else TParams(sweeps=int(sweeps))
    try:
        built = build_tspec(flat, cat, scope, all_, plot, params)
    except ValueError as exc:
        return [f"layout {flat.name}: {exc}"], 2
    spec = built.spec
    t0 = time.perf_counter()
    res = place_seeds(spec)
    took = time.perf_counter() - t0
    module = flat.insts[scope].module if scope else None
    src = (_module_file(path, module) if module else None) or os.path.abspath(path)
    with open(src, encoding="utf-8") as fh:
        lines = fh.read().splitlines(keepends=True)
    placed, kept, fixed, nofit, changes = [], 0, 0, [], {}
    for k, sd in enumerate(spec.seeds):
        p = built.paths[k]
        inst = flat.insts[p]
        if res.at[k] is None:
            nofit.append(p)
            continue
        if not sd.movable:
            fixed += 1
            continue
        if sd.at is not None and tuple(res.at[k]) == tuple(sd.at):
            kept += 1
            continue
        line_no = inst.line
        old = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        new = hint_line(old, written_hint(flat, cat, p, res.at[k]))
        placed.append((p, new.rstrip("\r\n").strip()))
        changes[line_no] = (old, new)
    x0, y0, x1, y1 = spec.box
    out = [f"layout {flat.name}{' ' + module if module else ''}: {len(spec.seeds)} modules, "
           f"{len(placed)} placed now, {kept} kept, {fixed} fixed; {len(spec.nets)} nets; "
           f"plot {x1 - x0}x{y1 - y0} ({built.box_from}); territories ({which()})"]
    for _p, text in placed:
        out.append(f"  {text}")
    for p in nofit:
        out.append(f"  no-fit {p}: fits nowhere in the {x1 - x0}x{y1 - y0} plot with what stands")
    for note in built.notes:
        out.append(f"  {note}")
    for i, sd in enumerate(spec.seeds):
        if res.at[i] is None:
            continue
        pct = (res.areas[i] * 100 // sd.need) if sd.need else 0
        flag = "  (off its need)" if sd.movable and \
            abs(res.areas[i] - sd.need) * 100 > spec.params.tol * sd.need else ""
        out.append(f"  cell {built.paths[i]}: {res.areas[i]} tiles of {sd.need} needed ({pct} %)"
                   f"{flag}")
    before = sum(c for c in res.before if c >= 0)
    after = sum(c for c in res.after if c >= 0)
    unreached = sorted({spec.nets[n].name for n, _t in res.unreached})
    reach = "every net reaches its consumers" if not unreached else \
        f"{len(unreached)} nets with a port no partner reaches: {', '.join(unreached)}"
    hot = ""
    if res.hot:
        hot = ": " + ", ".join(f"{x},{y} x{u}" for (x, y), u in res.hot[:8]) \
            + (" ..." if len(res.hot) > 8 else "")
    out.append(f"  estimated belts {before // MILLI} -> {after // MILLI} over {len(spec.nets)} "
               f"nets; {reach}; {len(res.hot)} hot tiles{hot}; {res.sweeps} sweeps")
    out.append(shared_boundary_line(spec, res))
    tpath = write_territories(path, built, res)
    out.append(f"  territories: {os.path.relpath(tpath, os.path.dirname(os.path.abspath(path)))}")
    out.append(f"  took {took:.1f} s ({which()})")
    if write and changes:
        for line_no, (_old, new) in changes.items():
            lines[line_no - 1] = new
        with open(src, "w", encoding="utf-8", newline="") as fh:
            fh.write("".join(lines))
        out.append(f"  wrote {len(changes)} hints into {src}")
    elif write:
        out.append("  nothing to write")
    return out, 0
