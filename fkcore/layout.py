"""fkcore.layout: routability-driven layout (PLAN-4.0 part P): ``fk layout FILE``.

The router as a potential, not a router. A module's instances move under the gradient of a
routability Lagrangian until the belts between them are short and uncrowded; then the real router
runs as today. For a placement P (each movable instance's origin and rotation) and a price field
lambda over the tiles::

    L(P, lambda) = sum_n w_n * c_n(P, lambda) + sum_t lambda_t * (u_t(P) - 1)+

``c_n`` is the **relaxed** cost of net n: the walk (belt distances with tunnels up to ``reach``,
instances as obstacles, every tile entered priced by lambda) from the net's drivers to its
consumers, the nearest driver per consumer, plus the MST over the drivers when it has several;
``w_n`` is the net's weight in belts from the rate model; ``u_t`` how many relaxed routes (in
belts) pass tile t, traced back along the walk fields. No entity is placed.

A **sweep** offers every movable instance its neighbours' positions (+-s and +-2s tiles along each
axis, the four rotations; overlaps, the plot's edge and a covered attach tile are hard) and takes
the move that lowers L most. After a sweep lambda steps up where routes crowd (``alpha`` per belt
of overuse) and decays elsewhere; the step ``s`` shrinks when a sweep moves nothing; it stops when
no move helps at the smallest step or at the cap. Deterministic: fixed instance order, ties to the
smaller move, then the lower rotation. Every quantity is an integer (milli-tiles), so the Rust
kernel (``fkroute.place``, native/fkroute/src/place.rs) and :func:`_place_py` agree exactly;
FK_NATIVE=0 forces Python, FK_NATIVE=check runs both and raises on a difference.

The command prints one source line per instance it placed, in the file's own syntax, and a
routability report; ``--write`` puts the hints into the file. Nothing else in the build changes:
``place`` still reads the hints. Stdlib only; the kernel is a speed-up.
"""
from __future__ import annotations

import heapq
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field

from .compose import turn

try:
    import fkroute as _native
except ImportError:          # stdlib only: the native kernel is a speed-up, never a dependency
    _native = None

__all__ = ["Spec", "SpecInst", "SpecNet", "Params", "Result", "place", "build_spec",
           "layout_file", "hint_line", "main"]

_DX = (0, 1, 0, -1)
_DY = (-1, 0, 1, 0)
_H = {0: 0, 4: 1, 8: 2, 12: 3}
MILLI = 1000                 # one tile of belt, in the kernel's units

#: the hint on an instance's line: ``@(x, y)`` or ``@(x, y, rot r)``
_HINT = re.compile(r"\s*@\(\s*-?[\d.]+\s*,\s*-?[\d.]+\s*(?:,\s*rot\s+-?\d+\s*)?\)")


# -- the spec --------------------------------------------------------------------------------------
@dataclass
class SpecInst:
    """One instance: ``shapes[rot]`` = (footprint tiles, attach groups) relative to its origin for
    each of the four rotations (a group is the tiles a belt end may use: one tile for a row's belt
    end, the ring round a single machine where its inserter stands); ``at`` its (x, y, rot) or
    None (unplaced: the kernel starts it); ``movable`` whether a sweep may move it."""
    name: str
    shapes: list
    at: tuple | None
    movable: bool


@dataclass
class SpecNet:
    """One net: ``weight`` in belts, ``terms`` [(instance index, group index, driver)]."""
    name: str
    weight: int
    terms: list


@dataclass
class Params:
    sweeps: int = 150       # the cap; a module stops on its own when no move helps
    alpha: int = 500        # milli-tiles of price added per belt of overuse, per sweep
    decay: int = 800        # per mille of a tile's price kept where no route crowds it
    reach: int = 5          # an underground's reach, as the router's walk takes it
    steps: tuple = (2, 1)   # the step sizes, coarse first


@dataclass
class Spec:
    box: tuple              # (x0, y0, x1, y1): the frame the instances stay inside
    blocked: list           # tiles nothing may cover or cross
    insts: list             # [SpecInst]
    nets: list              # [SpecNet]
    params: Params = field(default_factory=Params)


@dataclass
class Result:
    at: list                # per instance: (x, y, rot), or None: it fits nowhere
    before: list            # per net: the relaxed cost in milli-tiles at the start (-1: unreached)
    after: list             # the same at the end, both unpriced
    hot: list               # [((x, y), belts)] tiles more than one belt crosses at the end
    sweeps: int
    unreached: list         # [(net index, term index)] consumer terminals no driver reaches


# -- the Python reference ------------------------------------------------------------------------
class _State:
    """The dense board: ``owner`` per tile (-1 free, -2 blocked, i an instance's footprint),
    ``price`` (lambda, milli-tiles), the instances' positions."""

    def __init__(self, spec):
        self.spec = spec
        x0, y0, x1, y1 = spec.box
        self.x0, self.y0, self.w, self.h = x0, y0, max(0, x1 - x0), max(0, y1 - y0)
        n = self.w * self.h
        self.owner = [-1] * n
        self.price = [0] * n
        self.at = [None] * len(spec.insts)
        for t in spec.blocked:
            i = self.idx(t)
            if i is not None:
                self.owner[i] = -2
        self.pinned = {}           # tile -> instance whose one-tile attach (a belt end, a port) it is:
                                   # no footprint there, and no other one-tile attach on it

    def idx(self, t):
        x, y = t[0] - self.x0, t[1] - self.y0
        if 0 <= x < self.w and 0 <= y < self.h:
            return y * self.w + x
        return None

    def tiles(self, i, at):
        x, y, rot = at
        return [(x + dx, y + dy) for dx, dy in self.spec.insts[i].shapes[rot][0]]

    def groups(self, i, at):
        x, y, rot = at
        return [[(x + dx, y + dy) for dx, dy in g] for g in self.spec.insts[i].shapes[rot][1]]

    def inward(self, i, at, t, step=1):
        """The tile ``step`` nearer instance ``i``'s footprint box than ring tile ``t`` (the
        belt's tile): where its inserter stands. ``step`` -1: the tile beyond ``t``, away from the
        box, where a belt end's belt comes from or goes on to. None when ``t`` is not beside the
        box."""
        tiles = self.spec.insts[i].shapes[at[2]][0]
        if not tiles:
            return None
        x0, x1 = at[0] + min(dx for dx, _dy in tiles), at[0] + max(dx for dx, _dy in tiles) + 1
        y0, y1 = at[1] + min(dy for _dx, dy in tiles), at[1] + max(dy for _dx, dy in tiles) + 1
        tx, ty = t
        if tx < x0:
            return (tx + step, ty)
        if tx >= x1:
            return (tx - step, ty)
        if ty < y0:
            return (tx, ty + step)
        if ty >= y1:
            return (tx, ty - step)
        return None

    def usable(self, i, at, g, t, moving=False):
        """Ring tile ``t`` of group ``g`` (its tiles) of instance ``i`` at ``at`` can take an
        attach: free, and (a ring, not a one-tile belt end) its inward neighbour free too, so an
        inserter can stand between the belt and the machine. ``moving``: the instance's own tiles
        count as free (it is leaving them)."""
        ok = (-1, i) if moving else (-1,)
        k = self.idx(t)
        if k is None or self.owner[k] not in ok:
            return False
        if len(g) == 1:
            # a belt end on another instance's belt end or a port's tile is a zero-length belt the
            # router cannot lay (a pair needs a trunk): leave a tile between; and the tile beyond
            # it, where its belt arrives or goes on, is free and inside the box
            if self.pinned.get(t, i) != i:
                return False
            o = self.inward(i, at, t, -1)
        else:
            o = self.inward(i, at, t)
        if o is not None:
            ko = self.idx(o)
            if ko is None or self.owner[ko] not in ok:
                return False
        return True

    def fits(self, i, at):
        """Inside the box, over free tiles only (its own footprint counts as free), covering no
        other instance's one-tile attach, and every attach group with a usable tile."""
        for t in self.tiles(i, at):
            k = self.idx(t)
            if k is None or self.owner[k] not in (-1, i) or self.pinned.get(t, i) != i:
                return False
        own = set(self.tiles(i, at))
        for g in self.groups(i, at):
            if not any(t not in own and self.usable(i, at, g, t, True) for t in g):
                return False
        return True

    def put(self, i, at):
        """Move instance ``i`` to ``at`` (None: off the board). A tile outside the box (a fixed
        instance placed past the frame) is simply not on the board."""
        if self.at[i] is not None:
            for t in self.tiles(i, self.at[i]):
                k = self.idx(t)
                if k is not None:
                    self.owner[k] = -1
            for g in self.groups(i, self.at[i]):
                if len(g) == 1 and self.pinned.get(g[0]) == i:
                    del self.pinned[g[0]]
        self.at[i] = at
        if at is not None:
            for t in self.tiles(i, at):
                k = self.idx(t)
                if k is not None:
                    self.owner[k] = i
            for g in self.groups(i, at):
                if len(g) == 1:
                    self.pinned[g[0]] = i

    def free_tiles(self, i, g):
        """The free tiles of group ``g`` of instance ``i`` as placed, sorted."""
        if self.at[i] is None:
            return []
        at = self.at[i]
        group = self.groups(i, at)[g]
        out = [t for t in group if self.usable(i, at, group, t)]
        out.sort()
        return out

    def field(self, seeds, priced=True):
        """The priced walk from ``seeds``: (dist, pred) dense over the box, -1 where unreached. A
        step enters the first free tile within ``reach`` along a heading (a tunnel under what
        blocks) at ``MILLI`` per tile of belt plus the price of the tile entered."""
        w, h, owner = self.w, self.h, self.owner
        price = self.price if priced else None
        reach = self.spec.params.reach
        dist = [-1] * (w * h)
        pred = [-1] * (w * h)
        todo = []
        for t in sorted(set(seeds)):
            k = self.idx(t)
            if k is not None and dist[k] != 0:
                dist[k] = 0
                todo.append((0, t[0], t[1]))
        heapq.heapify(todo)
        while todo:
            d, x, y = heapq.heappop(todo)
            k = (y - self.y0) * w + (x - self.x0)
            if d > dist[k]:
                continue
            for hd in range(4):
                for j in range(1, reach + 1):
                    ux, uy = x + _DX[hd] * j, y + _DY[hd] * j
                    lx, ly = ux - self.x0, uy - self.y0
                    if not (0 <= lx < w and 0 <= ly < h):
                        break
                    u = ly * w + lx
                    if owner[u] == -1:
                        nd = d + j * MILLI + (price[u] if price is not None else 0)
                        if dist[u] < 0 or nd < dist[u]:
                            dist[u] = nd
                            pred[u] = k
                            heapq.heappush(todo, (nd, ux, uy))
                        break
        return dist, pred

    def trace(self, pred, k):
        """The tiles from tile index ``k`` back to its seed, ``k`` first."""
        out = []
        while k >= 0:
            out.append(k)
            k = pred[k]
        return out

    def eval_net(self, n, priced=True):
        """-> (cost in milli-tiles, [route tile indexes], [unreached term indexes]) of net ``n``:
        the nearest driver per consumer and the MST over the drivers, traced back."""
        net = self.spec.nets[n]
        drivers = [(ti, self.free_tiles(i, g)) for ti, (i, g, drv) in enumerate(net.terms) if drv
                   and self.at[i] is not None]
        consumers = [(ti, self.free_tiles(i, g)) for ti, (i, g, drv) in enumerate(net.terms)
                     if not drv and self.at[i] is not None]
        drivers = [(ti, ts) for ti, ts in drivers if ts]
        consumers = [(ti, ts) for ti, ts in consumers if ts]
        if not drivers or not consumers:
            return 0, [], []
        cost, routes, unreached = 0, [], []
        dist, pred = self.field([t for _ti, ts in drivers for t in ts], priced)
        for ti, ts in consumers:
            best = None
            for t in ts:
                k = self.idx(t)
                if dist[k] >= 0 and (best is None or dist[k] < best[0]):
                    best = (dist[k], k)
            if best is None:
                unreached.append(ti)
                continue
            cost += best[0]
            routes.append(self.trace(pred, best[1]))
        if len(drivers) > 1:
            fields = [self.field(ts, priced) for _ti, ts in drivers]
            in_tree, edges = {0}, []
            while len(in_tree) < len(drivers):
                best = None
                for a in sorted(in_tree):
                    da, pa = fields[a]
                    for b in range(len(drivers)):
                        if b in in_tree:
                            continue
                        for t in drivers[b][1]:
                            k = self.idx(t)
                            if da[k] >= 0 and (best is None or (da[k], a, b, k) < best):
                                best = (da[k], a, b, k)
                if best is None:
                    for b in range(len(drivers)):
                        if b not in in_tree:
                            unreached.append(drivers[b][0])
                    break
                d, a, b, k = best
                in_tree.add(b)
                cost += d
                routes.append(self.trace(fields[a][1], k))
        return cost, routes, unreached

    def manhattan_start(self, i):
        """Where an unplaced instance starts: the fitting (x, y, rot) nearest (in Manhattan tiles,
        weighted) to its nets' placed partners, or nearest the box's centre when it has none; ties
        to the smaller (y, x, rot)."""
        spec = self.spec
        partners = []        # (weight, [tiles]) per net term of i with a placed partner
        for net in spec.nets:
            mine = [g for (ii, g, _d) in net.terms if ii == i]
            if not mine:
                continue
            tiles = []
            for ii, g, _d in net.terms:
                if ii != i and self.at[ii] is not None:
                    tiles.extend(self.groups(ii, self.at[ii])[g])
            if tiles:
                partners.append((net.weight, mine, tiles))
        cx, cy = self.x0 * 2 + self.w, self.y0 * 2 + self.h      # the centre, doubled
        best = None
        for rot in range(4):
            tiles, groups = spec.insts[i].shapes[rot]
            if not tiles:
                continue
            fw = max(dx for dx, _dy in tiles) + 1
            fh = max(dy for _dx, dy in tiles) + 1
            for y in range(self.y0, self.y0 + self.h - fh + 1):
                for x in range(self.x0, self.x0 + self.w - fw + 1):
                    at = (x, y, rot)
                    if partners:
                        score = 0
                        for wgt, mine, far in partners:
                            near = min(abs(x + dx - fx) + abs(y + dy - fy)
                                       for g in mine for dx, dy in groups[g] for fx, fy in far)
                            score += wgt * near
                    else:
                        score = abs(2 * x + fw - cx) + abs(2 * y + fh - cy)
                    key = (score, y, x, rot)
                    if best is not None and key >= best[0]:
                        continue
                    if self.fits(i, at):
                        best = (key, at)
        return None if best is None else best[1]


def _place_py(spec):
    """The reference loop; :func:`place` runs it, or the kernel's port of it."""
    st = _State(spec)
    p = spec.params
    for i, inst in enumerate(spec.insts):
        if inst.at is not None:
            st.put(i, tuple(inst.at))
    for i, inst in enumerate(spec.insts):
        if inst.at is None:
            at = st.manhattan_start(i)
            if at is not None:
                st.put(i, at)
    nn = len(spec.nets)
    n_tiles = st.w * st.h

    def full(priced=True):
        """Every net evaluated: (costs, routes, u, L, unreached)."""
        costs, routes, unreached = [], [], []
        u = [0] * n_tiles
        for n in range(nn):
            c, rs, un = st.eval_net(n, priced)
            costs.append(c)
            routes.append(rs)
            unreached.extend((n, ti) for ti in un)
            for r in rs:
                for k in r:
                    u[k] += spec.nets[n].weight
        lagr = sum(spec.nets[n].weight * costs[n] for n in range(nn))
        lagr += sum(st.price[k] * (u[k] - 1) for k in range(n_tiles) if u[k] > 1)
        return costs, routes, u, lagr, unreached

    costs0, _r, _u, _l, un0 = full(False)
    before = [-1 if any(k == n for k, _t in un0) else costs0[n] for n in range(nn)]
    movable = [i for i, inst in enumerate(spec.insts) if inst.movable and st.at[i] is not None]
    incident = {i: sorted({n for n, net in enumerate(spec.nets)
                           for (ii, _g, _d) in net.terms if ii == i}) for i in movable}
    costs, routes, u, lagr, _un = full()
    sweeps, step_i = 0, 0
    steps = list(p.steps) or [1]
    while sweeps < p.sweeps:
        s = steps[step_i]
        deltas = [(0, 0)] + [(sx * k, 0) for k in (s, 2 * s) for sx in (-1, 1)]             + [(0, sy * k) for k in (s, 2 * s) for sy in (-1, 1)]
        moved = False
        for i in movable:
            cur = st.at[i]
            mine = incident[i]
            # the other nets' use and penalty, held fixed while this instance tries its moves
            u_base = list(u)
            for n in mine:
                for r in routes[n]:
                    for k in r:
                        u_base[k] -= spec.nets[n].weight
            base = sum(spec.nets[n].weight * costs[n] for n in range(nn) if n not in mine)
            base += sum(st.price[k] * (u_base[k] - 1) for k in range(n_tiles) if u_base[k] > 1)
            best = None
            for rot in range(4):
                for dx, dy in deltas:
                    at = (cur[0] + dx, cur[1] + dy, rot)
                    if at == cur or not st.fits(i, at):
                        continue
                    st.put(i, at)
                    lagr_c, touched = base, []
                    for n in mine:
                        wgt = spec.nets[n].weight
                        c, rs, _un = st.eval_net(n)
                        lagr_c += wgt * c
                        for r in rs:
                            for k in r:
                                old = u_base[k]
                                u_base[k] = old + wgt
                                touched.append((k, wgt))
                                lagr_c += st.price[k] * (max(0, old + wgt - 1) - max(0, old - 1))
                    for k, wgt in touched:
                        u_base[k] -= wgt
                    st.put(i, cur)
                    key = (lagr_c, abs(dx) + abs(dy), rot, dy, dx)
                    if best is None or key < best[0]:
                        best = (key, at)
            if best is not None and best[0][0] < lagr:
                st.put(i, best[1])
                costs, routes, u, lagr, _un = full()
                moved = True
        sweeps += 1
        for k in range(n_tiles):
            if u[k] > 1:
                st.price[k] += p.alpha * (u[k] - 1)
            else:
                st.price[k] = st.price[k] * p.decay // MILLI
        costs, routes, u, lagr, _un = full()
        if not moved:
            if step_i + 1 < len(steps):
                step_i += 1
            else:
                break
    costs1, _routes1, u1, _l, un1 = full(False)
    after = [-1 if any(k == n for k, _t in un1) else costs1[n] for n in range(nn)]
    hot = [((k % st.w + st.x0, k // st.w + st.y0), u1[k]) for k in range(n_tiles) if u1[k] > 1]
    hot.sort(key=lambda e: (-e[1], e[0][1], e[0][0]))
    return Result([st.at[i] for i in range(len(spec.insts))], before, after, hot, sweeps,
                  sorted(un1))


# -- the kernel ------------------------------------------------------------------------------------
def native_on():
    """True when ``place`` runs in fkroute (a kernel with ``place``, and FK_NATIVE is not 0)."""
    return _native is not None and hasattr(_native, "place") \
        and os.environ.get("FK_NATIVE", "1") != "0"


def _flatten(spec):
    insts = [(i.name, [(list(t), [list(g) for g in gs]) for t, gs in i.shapes],
              None if i.at is None else tuple(int(v) for v in i.at), bool(i.movable))
             for i in spec.insts]
    nets = [(n.name, int(n.weight), [(int(a), int(b), bool(c)) for a, b, c in n.terms])
            for n in spec.nets]
    p = spec.params
    return (tuple(int(v) for v in spec.box), [tuple(t) for t in spec.blocked], insts, nets,
            (int(p.sweeps), int(p.alpha), int(p.decay), int(p.reach), [int(s) for s in p.steps]))


def _place_native(spec):
    at, before, after, hot, sweeps, unreached = _native.place(*_flatten(spec))
    return Result([None if a is None else tuple(a) for a in at], list(before), list(after),
                  [(tuple(t), u) for t, u in hot], sweeps, [tuple(e) for e in unreached])


def place(spec) -> Result:
    """The Lagrangian loop over ``spec``: in fkroute when it can (``native_on``), else in Python.
    FK_NATIVE=check runs both and raises if they differ."""
    mode = os.environ.get("FK_NATIVE", "1")
    if native_on():
        got = _place_native(spec)
        if mode == "check":
            py = _place_py(spec)
            if got != py:
                raise AssertionError(f"fkroute.place differs from _place_py:\n  {got}\n  {py}")
        return got
    return _place_py(spec)


def which():
    """'fkroute' or 'python': where ``place`` runs now."""
    return "fkroute" if native_on() else "python"


# -- the spec from a design ----------------------------------------------------------------------
def _ring(w, h):
    """The tiles two steps out from a w x h frame at (0, 0), where a belt stands behind the
    inserter that feeds or empties the machine (the inserter's tile, one step in, must be free
    too: ``_State.usable``). The relaxed route runs belt tile to belt tile over the same free
    ground the router's hub needs."""
    return [(x, -2) for x in range(w)] + [(x, h + 1) for x in range(w)] \
        + [(-2, y) for y in range(h)] + [(w + 1, y) for y in range(h)]


def _shapes(frag):
    """``shapes`` of a fragment: per rotation the turned frame's tiles and its attach groups, with
    the (role name, attach index, side) of each group (the same for every rotation)."""
    shapes, meta = [], []
    for rot in range(4):
        w, h = frag.size if rot % 2 == 0 else frag.size[::-1]
        tiles = [(x, y) for y in range(h) for x in range(w)]
        groups, m = [], []
        for name in sorted(frag.roles):
            role = frag.roles[name]
            for ai, (ax, ay, ad) in enumerate(role.attach):
                if ad is None:
                    groups.append(_ring(w, h))
                else:
                    x, y, d = turn(float(ax), float(ay), ad, rot, frag.size)
                    k = _H[int(d) % 16]
                    sign = 1 if role.side == "out" else -1
                    groups.append([(math.floor(x) + sign * _DX[k], math.floor(y) + sign * _DY[k])])
                m.append((name, ai, role.side))
        shapes.append((tiles, groups))
        meta = m
    return shapes, meta


def _child_attaches(flat, path, cat, scope):
    """[(x, y, d, side, net)]: the directed attach points of module instance ``path``'s placed
    descendants in its own unturned frame (a Stack's cells' belt ends, each at its hint inside the
    stack), on the nets of ``scope`` only (a cell-to-cell net stays inside the body). A turned
    module inside is left out (its frame turns with it; rare in a stack)."""
    from .expand import fragment_of
    from .fragments import FragmentError
    out = []
    for child in flat.scopes.get(path, {}).values():
        hint = child.hints.get("at")
        if hint is None:
            continue
        cx, cy, crot = int(hint[0]), int(hint[1]), int(hint[2]) % 4
        if child.module is not None and child.size is None:
            if crot:
                continue
            out.extend((x + cx, y + cy, d, side, net)
                       for x, y, d, side, net in _child_attaches(flat, child.path, cat, scope))
            continue
        try:
            frag, binding = fragment_of(flat, child.path, cat)
        except FragmentError:
            continue
        for name in sorted(frag.roles):
            role = frag.roles[name]
            net = binding.get(name)
            if net is None or not any(getattr(flat.nets.get(p), "scope", None) == scope
                                      for p in net.split("|")):
                continue
            for ax, ay, ad in role.attach:
                if ad is None:
                    continue
                x, y, d = turn(float(ax), float(ay), ad, crot, frag.size)
                out.append((x + cx, y + cy, d, role.side, net))
    return out


def _rigid_shapes(flat, path, cat, scope):
    """``shapes`` and meta of a module instance without a declared size (a Stack): its frame as
    one footprint, its children's belt ends as one-tile groups. None when its frame is unknown or
    does not start at its origin."""
    from .expand import _own_frame
    frame = _own_frame(flat, path, cat, {})
    if frame is None or frame[0] != 0 or frame[1] != 0 or frame[2] <= 0 or frame[3] <= 0:
        return None, None
    size = (int(frame[2]), int(frame[3]))
    attaches = _child_attaches(flat, path, cat, scope)
    shapes, meta = [], []
    for rot in range(4):
        w, h = size if rot % 2 == 0 else size[::-1]
        tiles = [(x, y) for y in range(h) for x in range(w)]
        groups, m = [], []
        for ax, ay, ad, side, net in attaches:
            x, y, d = turn(float(ax), float(ay), ad, rot, size)
            k = _H[int(d) % 16]
            sign = 1 if side == "out" else -1
            groups.append([(math.floor(x) + sign * _DX[k], math.floor(y) + sign * _DY[k])])
            m.append((net, 0, side))
        shapes.append((tiles, groups))
        meta = m
    return shapes, (meta, size)


def _weights(flat, cat):
    """{net: weight in belts} from the rate model (1 where it has nothing to say)."""
    from . import rates
    out = {}
    try:
        model = rates.solve(flat)
    except Exception:            # the layout is advice; a rates failure is that command's report
        return out
    per = max(1e-9, cat.belt_throughput("transport-belt"))
    for (net, _item), ni in model.nets.items():
        out[net] = out.get(net, 0.0) + max(ni.supply, ni.delivered, ni.to_sinks)
    return {n: max(1, int(math.ceil(r / per - 1e-9))) for n, r in out.items()}


@dataclass
class Built:
    """A spec with what the command needs to print it back: ``paths`` the instance path per spec
    instance (None for a port), ``notes`` the check lines gathered while building it, ``scope``
    the module instance laid out ('' for the file's top level)."""
    spec: Spec
    paths: list
    notes: list
    scope: str
    box_from: str


def build_spec(flat, cat, module=None, all_=False, plot=None, params=None) -> Built:
    """The spec of ``flat``'s top-level instances (or of the first instance of module type
    ``module``, inside its declared frame, its ports as fixed terminals). ``plot`` (w, h) is the
    top level's box when given; else a square with room for three times the instances' area."""
    from .expand import fragment_of, _port_tile, _port_choice, ports_of
    from .fragments import FragmentError
    notes, insts, paths = [], [], []
    scope = ""
    if module:
        scope = next((p for p, i in flat.insts.items() if i.module == module), None)
        if scope is None:
            raise ValueError(f"no instance of module {module} in {flat.name}")
        if flat.insts[scope].size is None:
            raise ValueError(f"{module} declares no size: a module is laid out inside its frame")
        w, h = flat.insts[scope].size
        box, box_from = (0, 0, int(w), int(h)), f"the frame of {module}"
    children = flat.scopes.get(scope, {})
    terms = {}                                   # net -> [(inst index, group, driver)]
    lane_of = getattr(flat, "lane_of", {}) or {}
    area = 0
    for name, inst in children.items():
        path = inst.path
        if "patch" in inst.hints and "at" not in inst.hints:
            notes.append(f"skip {path}: an @patch row is placed on ore by the build")
            continue
        if inst.kind == "Literal":
            if inst.literal is None or "at" not in inst.hints:
                notes.append(f"skip {path}: a Literal is laid where its file puts it")
                continue
            size = tuple(inst.literal[1])
            shapes = [([(x, y) for y in range(size[1] if r % 2 == 0 else size[0])
                        for x in range(size[0] if r % 2 == 0 else size[1])], []) for r in range(4)]
            insts.append(SpecInst(path, shapes, tuple(int(v) for v in inst.hints["at"]), False))
            paths.append(path)
            continue
        if inst.module is not None and inst.size is None:
            # a Stack, or a module whose frame is its children's: one rigid body, its children's
            # belt ends its attach points
            shapes, got = _rigid_shapes(flat, path, cat, scope)
            if shapes is None:
                notes.append(f"skip {path}: a module without a size whose frame is not known")
                continue
            meta, size = got
            binding = {net: net for net, _g, _side in meta}
        else:
            try:
                frag, binding = fragment_of(flat, path, cat)
            except FragmentError as exc:
                notes.append(f"skip {path}: {exc}")
                continue
            shapes, meta = _shapes(frag)
            size = frag.size
        at = inst.hints.get("at")
        at = None if at is None else tuple(int(v) for v in at)
        movable = at is None or all_
        if not any(binding.get(role) for role, _ai, _side in meta) and at is not None:
            movable = False                      # nothing pulls it: it stays where it is
        idx = len(insts)
        insts.append(SpecInst(path, shapes, at, movable))
        paths.append(path)
        area += size[0] * size[1]
        for g, (role, _ai, side) in enumerate(meta):
            net = binding.get(role)
            if net is None:
                continue
            for part in net.split("|"):
                fn = flat.nets.get(part)
                if fn is not None and getattr(fn, "scope", scope) != scope:
                    continue                     # a net inside the body, not the scope's
                # a `lanes A | B` pair rides one belt: one net in the spec (its parts' ends
                # together, so their shared tiles are no crowding)
                terms.setdefault(lane_of.get(part, part), []).append((idx, g, side == "out"))
    if module:
        w, h = flat.insts[scope].size
        for key in ports_of(flat, scope):
            port = flat.ports[key]
            try:
                x, y, _out = _port_tile(port, int(w), int(h), _port_choice(flat, key))
            except FragmentError as exc:
                notes.append(f"skip port {key}: {exc}")
                continue
            idx = len(insts)
            insts.append(SpecInst(key, [([], [[(x, y)]])] * 4, (0, 0, 0), False))
            paths.append(None)
            for net in flat.nets.values():
                name = lane_of.get(net.name, net.name)
                if any(k == key for k, _i in net.drivers):
                    terms.setdefault(name, []).append((idx, 0, True))
                elif any(k == key for k, _i in net.consumers):
                    terms.setdefault(name, []).append((idx, 0, False))
    if not module:
        if plot is not None:
            box, box_from = (0, 0, int(plot[0]), int(plot[1])), "--plot"
        else:
            x1 = y1 = 0
            for si in insts:
                if si.at is not None:
                    tiles = si.shapes[si.at[2]][0]
                    x1 = max(x1, si.at[0] + max((t[0] for t in tiles), default=0) + 1)
                    y1 = max(y1, si.at[1] + max((t[1] for t in tiles), default=0) + 1)
            side = int(math.ceil(math.sqrt(3 * area))) + 2
            box, box_from = (0, 0, max(x1, side), max(y1, side)), "room for the instances"
    weights = _weights(flat, cat)
    for pair in set(lane_of.values()):
        weights[pair] = max(weights.get(p, 1) for p in pair.split("|"))
    nets = [SpecNet(n, weights.get(n, 1), ts) for n, ts in sorted(terms.items())
            if any(d for _i, _g, d in ts) and any(not d for _i, _g, d in ts)]
    spec = Spec(box, [], insts, nets, params or Params())
    return Built(spec, paths, notes, scope, box_from)


# -- source lines ---------------------------------------------------------------------------------
def hint_text(at):
    x, y, rot = at
    return f"@({x}, {y})" if int(rot) % 4 == 0 else f"@({x}, {y}, rot {int(rot) % 4})"


def _kind_end(line):
    """The index just past ``name = Kind<...>`` (or ``name = Kind``) on a source line."""
    m = re.match(r"\s*[A-Za-z_][\w]*\s*=\s*[A-Za-z_][\w]*", line)
    if not m:
        return None
    i = m.end()
    if i < len(line) and line[i] == "<":
        depth, quote = 0, None
        while i < len(line):
            c = line[i]
            if quote:
                if c == quote:
                    quote = None
            elif c in "\"'":
                quote = c
            elif c == "<":
                depth += 1
            elif c == ">":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
    return i


def hint_line(line, at):
    """``line`` (one instance's source line) with its ``@(x, y[, rot r])`` set to ``at``: an
    existing hint replaced in place, else one added after ``Kind<...>``; a trailing comment and
    the line's spacing kept."""
    text = hint_text(at)
    m = _HINT.search(line)
    if m:
        return line[:m.start()] + " " + text + line[m.end():]
    i = _kind_end(line)
    if i is None:
        return line.rstrip("\r\n") + " " + text + ("\n" if line.endswith("\n") else "")
    j = i
    while j < len(line) and line[j] == " ":
        j += 1
    if j < len(line) and line[j] not in "#\r\n":      # another token follows: the hint before it
        return line[:i] + " " + text + line[i:]
    if j < len(line) and line[j] == "#":                # a comment: the hint takes the gap
        return line[:i] + " " + text + " " + line[j:]
    return line[:i] + " " + text + line[j:]


def written_hint(flat, cat, path, corner):
    """The hint to write for instance ``path`` standing at the kernel's ``corner`` (its turned
    frame's top-left): the origin hint (3.0.1, ``expand.origin_hints`` reads a turned instance's
    hint as its origin), the corner itself for an unturned one or a single machine."""
    from . import expand
    x, y, rot = corner
    inst = flat.insts[path]
    if int(rot) % 4 == 0 or expand.turns_in_place(inst):
        return (x, y, 0 if int(rot) % 4 == 0 else rot)
    frame = expand._own_frame(flat, path, cat, {})
    if frame is None:
        return corner
    return expand.origin_hint((x, y, rot), frame)


def _module_file(path, module):
    """The file module ``module`` is written in: ``path`` or the import that brings it."""
    from . import lang, snapshot
    seen, todo = set(), [os.path.abspath(path)]
    while todo:
        p = todo.pop()
        if p in seen or not os.path.exists(p):
            continue
        seen.add(p)
        f = lang.parse(snapshot.read(p), p)
        if module in f.modules:
            return p
        for _names, rel, _line in f.imports:
            todo.append(os.path.abspath(os.path.join(os.path.dirname(p), rel)))
    return None


# -- the command ----------------------------------------------------------------------------------
def _plot_of(path, flat):
    """(w, h) of this module's plot from the surface file beside the design, or None."""
    from . import surface as surfacemod
    folder = os.path.dirname(os.path.abspath(path))
    module = os.path.splitext(os.path.basename(path))[0]
    try:
        sf = surfacemod.load_game(folder)
    except (surfacemod.SurfaceError, OSError):
        return None
    for p in sf.places.values():
        if p.module == module and getattr(p, "lifecycle", None) != "retired":
            return int(p.w), int(p.h)
    return None


def layout_file(path, flat, cat, module=None, all_=False, write=False, sweeps=None, plot=None):
    """-> (the report lines, exit code). The report: a head line, one source line per instance
    placed, the check lines, the routability report, the timing line."""
    if plot is None and not module:
        plot = _plot_of(path, flat)
    params = Params() if sweeps is None else Params(sweeps=int(sweeps))
    try:
        built = build_spec(flat, cat, module, all_, plot, params)
    except ValueError as exc:
        return [f"layout {flat.name}: {exc}"], 2
    spec = built.spec
    t0 = time.perf_counter()
    res = place(spec)
    took = time.perf_counter() - t0
    src = (_module_file(path, module) if module else None) or os.path.abspath(path)
    with open(src, encoding="utf-8") as fh:
        lines = fh.read().splitlines(keepends=True)
    placed, kept, fixed, nofit, changes = [], 0, 0, [], {}
    for k, si in enumerate(spec.insts):
        p = built.paths[k]
        if p is None:
            continue
        inst = flat.insts[p]
        if res.at[k] is None:
            nofit.append(p)
            continue
        if not si.movable:
            fixed += 1
            continue
        if si.at is not None and tuple(res.at[k]) == tuple(si.at):
            kept += 1
            continue
        line_no = inst.line
        old = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        new = hint_line(old, written_hint(flat, cat, p, res.at[k]))
        placed.append((p, new.rstrip("\r\n").strip()))
        changes[line_no] = (old, new)
    x0, y0, x1, y1 = spec.box
    n_inst = len([p for p in built.paths if p is not None])
    out = [f"layout {flat.name}{' ' + module if module else ''}: {n_inst} instances, "
           f"{len(placed)} placed now, {kept} kept, {fixed} fixed; {len(spec.nets)} nets; "
           f"frame {x1 - x0}x{y1 - y0} ({built.box_from})"]
    for _p, text in placed:
        out.append(f"  {text}")
    for p in nofit:
        out.append(f"  no-fit {p}: fits nowhere in the {x1 - x0}x{y1 - y0} frame with what stands")
    for note in built.notes:
        out.append(f"  {note}")
    before = sum(c for c in res.before if c >= 0)
    after = sum(c for c in res.after if c >= 0)
    unreached = sorted({spec.nets[n].name for n, _t in res.unreached})
    reach = "every net reaches its consumers" if not unreached else \
        f"{len(unreached)} nets with an unreached consumer: {', '.join(unreached)}"
    hot = ""
    if res.hot:
        hot = ": " + ", ".join(f"{x},{y} x{u}" for (x, y), u in res.hot[:8]) \
            + (" ..." if len(res.hot) > 8 else "")
    out.append(f"  estimated belts {before // MILLI} -> {after // MILLI} over {len(spec.nets)} "
               f"nets; {reach}; {len(res.hot)} hot tiles{hot}; {res.sweeps} sweeps")
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


def main(a, flat, cat):
    """``fk layout FILE [MODULE] [--all] [--write] [--sweeps N] [--plot WxH]``."""
    plot = None
    if getattr(a, "plot", None):
        try:
            w, h = a.plot.lower().split("x")
            plot = (int(w), int(h))
        except ValueError:
            raise SystemExit("error: --plot WxH")
    lines, code = layout_file(a.file, flat, cat, a.module, a.all, a.write, a.sweeps, plot)
    print("\n".join(lines))
    return code
