"""fkcore.route: the router chunk (CORE-V1.md §9): a factory's nets -> keyed route carriers.

Input: the flat netlist, the factory layout (its fragments placed, each role with an attach
point) and the catalog. For every net that has no carriers of its own yet, the router lays the
belts between the attach points: from each driver role's product belt (the route starts on the
tile its belt points into) to each consumer role's input belt (the route ends on the tile behind
its first belt, pointing into it). Output: carriers keyed ``~<net>/b<k>`` (belts), ``u<k>``
(undergrounds) and ``s<k>`` (splitters), ``net=<net>``, plus a report line per net. A net it
can't route is reported with the reason, never raised; nothing else is moved.

The search is ``fkcore.steiner`` (v4's tree router, copied): one net is a tree of belt steps,
underground jumps and splitters. Every driver must reach every consumer (CORE: a route is any
connected graph joining every driver to every consumer); a net is laid in one of three shapes:

- **forward** (one driver belt): the tree grows from it to all consumers, splitting where it
  branches.
- **reverse** (one consumer belt): the tree grows from the consumer to all drivers and is laid
  reversed, so the splitters become merges (``Tree.entities(reverse)``).
- **hub** (everything else: several drivers and several consumers, a machine driver into a
  machine, a machine driver into several consumers, several drivers into one machine): every
  driver merges into one trunk, which then splits to every consumer. The trunk is a hub of two
  tiles, H and F = H + f: a reversed tree from H to the drivers (laid as merges, H's belt pointing
  into F) and a forward tree from F to the consumers, grown on the ground the first one left.
  Merge-then-split is the shape that joins every driver to every consumer with the fewest
  splitters: each driver joins once and each consumer leaves once (k - 1 merges, m - 1
  splitters), where pairwise trees would need k * m paths and a crossbar of splitters; the trunk
  carries everything, which V1 does not rate (throughput is V2). The hub is searched: free tiles
  ranked by the belt distance (around obstacles, tunnels included) from every driver to H and
  from F to every consumer, 3 tiles apart, tried in order; the cheapest pair of trees of the
  first three that route wins. A hub within 2 tiles of an end, on a side with several ends,
  ranks last: a tree whose first branch ends at once has no straight belt left to cut its next
  splitter into. One machine driver into one machine: a single inserter, where one reaches.

A consumer that is a single machine (a chest, an assembler cell: its role has no attach tile) is
reached by direct insertion: a fast (or long-handed) inserter beside the belt picks into it
(``steiner.TapSink``), keyed ``~<net>/i<k>``. A single machine as a driver works the same way on a
reversed tree, so its inserter turns round to pick from the machine.

A **fluid net** (every item a fluid) is not a belt job: it goes to the fluid plug-in,
``fkcore.fluid_route.route(flat, lay, cat, nets, blocked, box, limit) -> (added, how, failed)``
(``{net: [Entity]}``, ``{net: report text}``, ``{net: reason}``), called after the belt nets
with the belts already laid. Its job carries the plug-in's ``reserved`` tiles (its machines'
connection tiles, an offshore pump's water), which are among its ends, so no belt takes them, and
the plug-in's ``why_not`` as its skip reason. Without the plug-in a fluid net is reported, not
routed.

Per net the ground is: every entity tile, every placed instance's whole frame (the empty tiles
inside a row are kept for poles), every other net's start and end tiles, every tile another
net's belt points into (any belt tier; an underground of unknown type counts as an exit), every
tile another net's inserter picks from or drops onto and every tile a drill drops onto,
``blocked`` (terrain: water, cliffs) and everything outside ``bounds``.

**The underground guard.** The game pairs an underground entrance with the nearest end of the same
name facing the same way within its reach (``fkcore.connect`` has the same rule). So no new
tunnel may hide another same-axis underground end, and no new end may sit in another tunnel:
``_ug_spans`` gives the search, per axis, every underground end of the layout (any tier; paired,
alone, or of unknown type as a Literal imported from an entity list has them) and the hidden
tiles of every tunnel, paired as the game pairs them; ``steiner`` refuses a jump whose span
touches one, and its own tree's spans likewise. A net that only the guard stops is refused with
the tiles it protects. Laid reversed, a merge splitter's spare output may not point at a belt
(``Grid.keep_clear``) and a tapped belt never starts a tunnel (``Grid.drop_taps``: reversed it is
an exit, which takes no drop); a tapped belt's last tile never points into another net's belt.

Nets are routed one at a time, each seeing the ones before it; a net that fails moves to the
front and the pass is retried, and the pass that routes the most nets is kept. ``fkcore.connect``
is the judge: a routed layout is done when every net is connected with no LEAK. The router runs it
on its own result: a net whose route leaks or does not connect is re-routed around the tiles at
fault (twice at most), else refused with the judge's line. Pure, stdlib only, deterministic.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from . import connect as connectmod
from . import fkp as fkpmod
from .expand import attach_points, frame_of
from .steiner import FixedSink, Grid, TapSink, grow

__all__ = ["NetJob", "Routed", "jobs", "route_layout", "fluid_nets"]

_H = {0: 0, 4: 1, 8: 2, 12: 3}
_DX = (0, 1, 0, -1)
_DY = (-1, 0, 1, 0)
_BELT_KINDS = frozenset({"transport-belt", "underground-belt", "splitter"})
#: direct insertion: fast inserters (Rory's rule) unless only a long-handed one can reach; the
#: route step's ``--hand`` picks another short hand (1.1, from the 0534 player's own patch: plain
#: inserters while fast ones were short and locked)
_HANDS = (("fast-inserter",), ("fast-inserter", "long-handed-inserter"))
_REACH = {"fast-inserter": 1, "inserter": 1, "burner-inserter": 1, "long-handed-inserter": 2}
_HUBS = 8          # hub candidates tried at most
_HUB_WINS = 3      # stop after this many hubs that route
_REPAIRS = 2       # judge-and-reroute rounds before a leaking net is refused


@dataclass
class NetJob:
    net: str
    starts: list = field(default_factory=list)     # [(tile, heading)] the tile a driver belt feeds
    goals: list = field(default_factory=list)      # [(tile, heading)] the tile behind a consumer
    taps: list = field(default_factory=list)       # [(machine key, tile rect)] direct insertion
    sources: list = field(default_factory=list)    # [(machine key, tile rect)] a machine driver
    owners: list = field(default_factory=list)     # "<inst>.<role>" per start/goal, for the report
    skip: str | None = None
    fluid: bool = False                            # a fluid net: the fluid plug-in routes it
    reserved: list = field(default_factory=list)   # tiles a fluid net's connections need

    def ends(self):
        return [t for t, _h in self.starts] + [t for t, _h in self.goals] + list(self.reserved)

    def drivers(self):
        return len(self.starts) + len(self.sources)

    def consumers(self):
        return len(self.goals) + len(self.taps)

    @property
    def mode(self):
        """forward (one driver belt) | reverse (one consumer belt) | hub (the rest)."""
        if len(self.starts) == 1 and not self.sources:
            return "forward"
        if len(self.goals) == 1 and not self.taps:
            return "reverse"
        return "hub"


@dataclass
class Routed:
    layout: object                 # the factory Layout with the route carriers added
    lines: list                    # one report line per net
    routed: list                   # net names routed this run
    failed: dict                   # net -> reason
    kept: list                     # nets that already had carriers (pinned)
    passes: int = 1


class _Bounded(Grid):
    """A Grid that is also blocked outside a box, so no search wanders off the factory.
    ``belts`` (the tiles belts stand on) makes it the ground of a tree laid reversed: no merge's
    spare output may point at one, and taps drop onto their belt."""

    def __init__(self, blocked, box, spans=None, belts=None):
        super().__init__(blocked, (), spans)
        self.box = box
        if belts is not None:
            self.keep_clear = set(belts)
            self.drop_taps = True

    def blocked(self, t):
        x0, y0, x1, y1 = self.box
        return not (x0 <= t[0] < x1 and y0 <= t[1] < y1) or t in self.occ


def fluid_nets(flat, cat) -> set:
    """The nets whose items are all fluids (pipes, not belts)."""
    return {name for name, net in flat.nets.items()
            if net.items and all(cat.is_fluid(i) for i in net.items)}


def _fluid_plugin():
    try:
        from . import fluid_route
    except ImportError:
        return None
    return fluid_route


def jobs(flat, lay, cat) -> dict:
    """{net: NetJob} from every placed instance's attach points (a fluid net: flagged only)."""
    out = {}
    fluids = fluid_nets(flat, cat)
    plugin = _fluid_plugin() if fluids else None
    for name in sorted(fluids):
        if plugin is None:
            out[name] = NetJob(name, fluid=True, skip="a fluid net: pipes are routed by the fluid "
                                                       "plug-in, not built yet")
        else:
            out[name] = NetJob(name, fluid=True, skip=plugin.why_not(flat, lay, cat, name),
                               reserved=plugin.reserved(flat, lay, cat, name))
    for path, rec in sorted(lay.insts.items()):
        if rec.kind == "Literal" or path not in flat.insts:
            continue
        for role, side, net, (x, y, d) in attach_points(flat, lay, path, cat):
            if net is None or net in fluids:
                continue
            job = out.setdefault(net, NetJob(net))
            if d is None:
                for key in flat.insts[path].machines:
                    ts = fkpmod.tiles_of(cat, lay.entities[key])
                    rect = (min(t[0] for t in ts), min(t[1] for t in ts),
                            max(t[0] for t in ts) + 1, max(t[1] for t in ts) + 1)
                    (job.sources if side == "out" else job.taps).append((key, rect))
                job.owners.append(f"{path}.{role}")
                continue
            h = _H[int(d)]
            tile = (math.floor(x), math.floor(y))
            if side == "out":
                job.starts.append(((tile[0] + _DX[h], tile[1] + _DY[h]), h))
            else:
                job.goals.append(((tile[0] - _DX[h], tile[1] - _DY[h]), h))
            job.owners.append(f"{path}.{role}")
    for net, job in out.items():
        if job.skip is not None or job.fluid:
            continue
        if not job.drivers():
            job.skip = "no driver role is placed"
        elif not job.consumers():
            job.skip = "no consumer role is placed"
    return out


# -- the ground -----------------------------------------------------------------------------------
def _heading(e):
    """N E S W = 0..3 of a directed entity (no direction counts as north, as in connect)."""
    return _H.get(int(e.dir or 0) % 16)


def _is_belt(cat, e):
    return cat.has_entity(e.name) and cat.kind(e.name) in _BELT_KINDS


def _belt_fronts(cat, ents):
    """{tile: net} for every tile a belt, an underground exit or a splitter points into (any
    tier; an underground of unknown type counts as an exit)."""
    out = {}
    for e in ents:
        if not _is_belt(cat, e) or e.attrs.get("ug") == "in":
            continue
        h = _heading(e)
        if h is None:
            continue
        for tx, ty in fkpmod.tiles_of(cat, e):
            out.setdefault((tx + _DX[h], ty + _DY[h]), e.net)
    return out


def _hand_tiles(cat, ents):
    """{tile: net} for every tile an inserter picks from or drops onto, and every tile a drill
    drops onto (net None): another net's belt there would be picked from or fed."""
    out = {}
    for e in ents:
        if not cat.has_entity(e.name):
            continue
        kind = cat.kind(e.name)
        if kind == "inserter":
            h = _heading(e)
            if h is None:
                continue
            r = connectmod.REACH.get(e.name, 1)
            (tx, ty), = fkpmod.tiles_of(cat, e)
            for s in (r, -r):
                out.setdefault((tx + _DX[h] * s, ty + _DY[h] * s), e.net)
        elif kind == "mining-drill" and e.name != "pumpjack" and _heading(e) is not None:
            # the game's vector_to_place_result, as fkcore.connect has it
            w, hh = cat.size(e.name)
            vx, vy = (-0.5 if w % 2 == 0 else 0.0), -(hh / 2 + 0.3)
            for _ in range(_heading(e)):
                vx, vy = -vy, vx
            out.setdefault((math.floor(float(e.x) + vx), math.floor(float(e.y) + vy)), None)
    return out


def _ug_spans(cat, ents):
    """Per axis, the tiles no new same-axis tunnel may cover (the game would pair it wrong):
    every underground end (any tier, paired or alone; ``ug`` known or not) and the hidden tiles of
    every tunnel. A tunnel is paired as the game pairs it: an entrance looks ahead, up to its
    tier's reach, for the first end of the same name facing the same way; an exit there makes the
    tunnel. An end of unknown type counts as an entrance, and as an exit when one looks for it."""
    spans = {0: set(), 1: set()}
    ugs = {}
    for e in ents:
        if not cat.has_entity(e.name) or cat.kind(e.name) != "underground-belt":
            continue
        h = _heading(e)
        if h is None:
            continue
        t = (math.floor(e.x), math.floor(e.y))
        ugs[t] = (e, h)
        spans[h % 2].add(t)
    for (x, y), (e, h) in ugs.items():
        if e.attrs.get("ug") == "out":
            continue
        reach = int(cat.entity(e.name).get("max_distance") or 5)
        for k in range(1, reach + 1):
            o = ugs.get((x + _DX[h] * k, y + _DY[h] * k))
            if o is None or o[0].name != e.name or o[1] != h:
                continue                                  # passed through
            if o[0].attrs.get("ug") != "in":
                spans[h % 2] |= {(x + _DX[h] * j, y + _DY[h] * j) for j in range(k + 1)}
            break
    return spans


def _ground(cat, ents, frames, js, net, terrain=()):
    blocked = set(frames) | set(terrain)
    for e in ents:
        blocked |= fkpmod.tiles_of(cat, e)
    for tile, owner in _belt_fronts(cat, ents).items():
        if owner != net:
            blocked.add(tile)
    for tile, owner in _hand_tiles(cat, ents).items():
        if owner != net:
            blocked.add(tile)
    for other, job in js.items():
        if other != net:
            blocked |= set(job.ends())
    return blocked - set(js[net].ends())


def _belt_tiles(cat, ents):
    """Every tile a belt, an underground or a splitter stands on (a merge must not feed one)."""
    out = set()
    for e in ents:
        if _is_belt(cat, e):
            out |= fkpmod.tiles_of(cat, e)
    return out


# -- trees ----------------------------------------------------------------------------------------
def _carriers(job, tree_ents, net):
    """The tree's plan entities as keyed .fkp entities, in the tree's own order."""
    count = {"b": 0, "u": 0, "s": 0, "i": 0}
    out = []
    for p in tree_ents:
        letter = {"transport-belt": "b", "underground-belt": "u", "splitter": "s"}.get(p["name"], "i")
        key = f"~{net}/{letter}{count[letter]}"
        count[letter] += 1
        attrs = {"net": net}
        if p.get("belt_to_ground_type"):
            attrs["ug"] = "in" if p["belt_to_ground_type"] == "input" else "out"
        x, y = p["x"], p["y"]
        out.append(fkpmod.Entity(key, p["name"], _clean(x), _clean(y), int(p["direction"]), attrs))
    return out


def _clean(v):
    return int(v) if float(v).is_integer() else v


def _grow(grid, root, fixed, machines, limit):
    """grow() towards ``fixed`` sinks and ``machines`` [(key, rect)] by direct insertion: fast
    inserters, or long-handed ones where only those reach. -> (result, sinks)."""
    for hands in _HANDS:
        sinks = fixed + [TapSink(key, rect, 1, hands) for key, rect in machines]
        res = grow(grid, root, sinks, limit=limit)
        if not res["problems"] or not machines:
            break
    return res, sinks


def _tree_job(cat, job, blocked, spans, clear, box, limit):
    """forward or reverse: one tree. -> (plan entities, report text) or (None, reason)."""
    reverse = job.mode == "reverse"
    grid = _Bounded(blocked, box, spans, clear if reverse else None)
    if reverse:
        (gtile, gh), = job.goals
        root = (gtile[0], gtile[1], (gh + 2) % 4, 0)
        fixed = [FixedSink(f"driver{i}", t, (h + 2) % 4) for i, (t, h) in enumerate(job.starts)]
        machines = job.sources
    else:
        (stile, sh), = job.starts
        root = (stile[0], stile[1], sh, 0)
        fixed = [FixedSink(f"consumer{i}", t, h) for i, (t, h) in enumerate(job.goals)]
        machines = job.taps
    if grid.blocked((root[0], root[1])):
        return None, f"its {'end' if reverse else 'start'} tile {root[0]},{root[1]} is taken"
    res, sinks = _grow(grid, root, fixed, machines, limit)
    if res["problems"]:
        return None, "; ".join(res["problems"][:3])
    c = res["counts"]
    how = (f"{c['belts']} belts, {c['undergrounds']} underground ends, {c['splitters']} "
           f"{'merges' if reverse else 'splitters'}" + (f", {c['taps']} inserters" if c["taps"]
                                                         else ""))
    return res["tree"].entities(sinks, net=job.net, reverse=reverse), how


# -- the hub --------------------------------------------------------------------------------------
def _walk(grid, seeds, reach=5):
    """Belt distance over free ground from ``seeds``: a step to a free tile, or a tunnel under
    whatever blocks it to the first free tile within ``reach`` (as the search may jump)."""
    dist = {s: 0 for s in seeds}
    todo = [(0, s) for s in sorted(dist)]
    while todo:
        d, t = heapq.heappop(todo)
        if d > dist[t]:
            continue
        for h in range(4):
            for j in range(1, reach + 1):
                u = (t[0] + _DX[h] * j, t[1] + _DY[h] * j)
                if not grid.blocked(u):
                    if d + j < dist.get(u, d + j + 1):
                        dist[u] = d + j
                        heapq.heappush(todo, (d + j, u))
                    break
                if not grid.box[0] <= u[0] < grid.box[2] or not grid.box[1] <= u[1] < grid.box[3]:
                    break
    return dist


def _beside(grid, rect):
    """The free tiles beside a machine's rectangle (where its inserter could stand)."""
    x0, y0, x1, y1 = rect
    ring = [(x, y0 - 1) for x in range(x0, x1)] + [(x, y1) for x in range(x0, x1)] + \
           [(x0 - 1, y) for y in range(y0, y1)] + [(x1, y) for y in range(y0, y1)]
    return [t for t in ring if not grid.blocked(t)]


def _hubs(grid, job, most=_HUBS):
    """[(H, f)] hub candidates, best first: H and F = H + f free, reached from every end; ranked
    by the summed walking distance from every driver to H and from F to every consumer; a hub
    within 2 tiles of an end on a side with several ends ranks last; picked 3 tiles apart."""
    ends = set(job.ends())
    near_d = [[t] for t, _h in job.starts] + [_beside(grid, r) for _k, r in job.sources]
    near_c = [[t] for t, _h in job.goals] + [_beside(grid, r) for _k, r in job.taps]
    dd = [_walk(grid, s) for s in near_d]
    dc = [_walk(grid, s) for s in near_c]
    if not dd or not dc:
        return []
    common = set.intersection(*(set(d) for d in dd + dc)) - ends
    rows = []
    for t in common:
        a = [d[t] for d in dd]
        for f in range(4):
            u = (t[0] + _DX[f], t[1] + _DY[f])
            if u not in common:
                continue
            b = [d[u] for d in dc]
            short = (len(a) > 1 and min(a) < 3) or (len(b) > 1 and min(b) < 3)
            rows.append((short, sum(a) + sum(b), t[1], t[0], f))
    rows.sort()
    out = []
    for _short, _score, y, x, f in rows:
        if any(abs(x - o[0]) + abs(y - o[1]) < 3 for o, _f in out):
            continue
        out.append(((x, y), f))
        if len(out) >= most:
            break
    return out


def _hub_trees(cat, job, blocked, spans, clear, box, limit, hub, f):
    """The reversed tree from H to every driver, then the forward tree from F = H + f to every
    consumer on what is left. -> (cost, plan, counts, counts) or a reason."""
    net = job.net
    fx, fy = hub[0] + _DX[f], hub[1] + _DY[f]
    rgrid = _Bounded(set(blocked) | {(fx, fy)}, box, spans, clear)
    fixed = [FixedSink(f"driver{i}", t, (h + 2) % 4) for i, (t, h) in enumerate(job.starts)]
    rres, rsinks = _grow(rgrid, (hub[0], hub[1], (f + 2) % 4, 0), fixed, job.sources, limit)
    if rres["problems"]:
        return "drivers: " + "; ".join(rres["problems"][:2])
    rtree = rres["tree"]
    rplan = rtree.entities(rsinks, net=net, reverse=True)
    laid = _carriers(job, rplan, net)
    fb = set(blocked) | set(rtree.tiles())
    for e in laid:
        fb |= fkpmod.tiles_of(cat, e)
    fb |= set(_belt_fronts(cat, laid)) - {(fx, fy)}
    rs = rtree.spans()
    fgrid = _Bounded(fb, box, {a: set(spans[a]) | rs[a] for a in (0, 1)})
    fixed = [FixedSink(f"consumer{i}", t, h) for i, (t, h) in enumerate(job.goals)]
    fres, fsinks = _grow(fgrid, (fx, fy, f, 0), fixed, job.taps, limit)
    if fres["problems"]:
        return "consumers: " + "; ".join(fres["problems"][:2])
    ftree = fres["tree"]
    plan = rplan + ftree.entities(fsinks, net=net)
    return rtree.cost() + ftree.cost(), plan, rres["counts"], fres["counts"]


def _direct(cat, job, grid):
    """One machine driver into one machine: a single inserter between them, if one fits."""
    (_sk, src), = job.sources
    (_tk, dst), = job.taps
    for hands in _HANDS:
        for name in hands:
            r = _REACH[name]
            for x in range(src[0], src[2]):
                for y in range(src[1], src[3]):
                    for g in range(4):           # the inserter faces its pickup side, g
                        q = (x - _DX[g] * r, y - _DY[g] * r)
                        drop = (q[0] - _DX[g] * r, q[1] - _DY[g] * r)
                        if grid.blocked(q) or not (dst[0] <= drop[0] < dst[2]
                                                   and dst[1] <= drop[1] < dst[3]):
                            continue
                        return [{"name": name, "x": q[0] + 0.5, "y": q[1] + 0.5,
                                 "direction": g * 4, "role": "ins"}]
    return None


def _hub_job(cat, job, blocked, spans, clear, box, limit):
    """hub: merge every driver into a trunk, split it to every consumer. -> (plan, how)."""
    grid = _Bounded(blocked, box, spans)
    if len(job.sources) == 1 and len(job.taps) == 1 and not job.starts and not job.goals:
        plan = _direct(cat, job, grid)
        if plan:
            return plan, "1 inserter (direct insertion)"
    cands = _hubs(grid, job)
    if not cands:
        return None, "no free tile is reached from every driver and consumer (no hub)"
    best, why, wins = None, None, 0
    for hub, f in cands:
        got = _hub_trees(cat, job, blocked, spans, clear, box, limit, hub, f)
        if isinstance(got, str):
            why = why or f"hub {hub[0]},{hub[1]}: {got}"
            continue
        if best is None or got[0] < best[0][0] - 1e-9:
            best = (got, hub, f)
        wins += 1
        if wins >= _HUB_WINS:
            break
    if best is None:
        return None, f"none of {len(cands)} hubs routes; first: {why}"
    (_cost, plan, cr, cf), hub, f = best
    taps = cr["taps"] + cf["taps"]
    how = (f"{cr['belts'] + cf['belts']} belts, {cr['undergrounds'] + cf['undergrounds']} "
           f"underground ends, {cr['splitters']} merges, {cf['splitters']} splitters"
           + (f", {taps} inserters" if taps else "")
           + f", hub {hub[0]},{hub[1]} {'NESW'[f]}")
    return plan, how


# -- one net --------------------------------------------------------------------------------------
def _settle_leaves(cat, laid, ents):
    """A tapped belt's last tile points on into whatever stands ahead: turn it (never back at its
    feed) where that is another net's belt. -> the carriers, or None when no turn is clear."""
    occ = {}
    for e in ents:
        if _is_belt(cat, e):
            for t in fkpmod.tiles_of(cat, e):
                occ[t] = e
    mine = {}
    for e in laid:
        for t in fkpmod.tiles_of(cat, e):
            mine[t] = e
    out = []
    for e in laid:
        h = _heading(e)
        if e.name != "transport-belt" or h is None:
            out.append(e)
            continue
        (tx, ty), = fkpmod.tiles_of(cat, e)

        def bad(d):
            ahead = (tx + _DX[d], ty + _DY[d])
            o = occ.get(ahead)
            return o is not None and o.net != e.net

        if not bad(h):
            out.append(e)
            continue
        behind = (tx - _DX[h], ty - _DY[h])
        turns = [d for d in ((h + 1) % 4, (h + 3) % 4) if not bad(d)
                 and (tx + _DX[d], ty + _DY[d]) not in mine]
        if behind not in mine or not turns:
            return None
        out.append(fkpmod.Entity(e.key, e.name, e.x, e.y, turns[0] * 4, dict(e.attrs)))
    return out


def _route_one(cat, job, ents, frames, js, box, limit, terrain=(), avoid=(), spans=None):
    net = job.net
    blocked = _ground(cat, ents, frames, js, net, terrain) | (set(avoid) - set(job.ends()))
    spans = _ug_spans(cat, ents) if spans is None else spans
    clear = _belt_tiles(cat, ents)
    if job.mode == "hub":
        plan, how = _hub_job(cat, job, blocked, spans, clear, box, limit)
    else:
        plan, how = _tree_job(cat, job, blocked, spans, clear, box, limit)
    if plan is None:
        return None, how
    laid = _settle_leaves(cat, _carriers(job, plan, net), ents)
    if laid is None:
        return None, "a tapped belt's last tile points into another net's belt"
    return laid, how


def _guarded(cat, job, ents, frames, js, box, limit, terrain):
    """Why a net failed, when the underground guard is the cause: without it the search routes,
    and its tunnels cover these tiles of other undergrounds on the same axis. None otherwise."""
    got, _how = _route_one(cat, job, ents, frames, js, box, limit, terrain,
                           spans={0: set(), 1: set()})
    if got is None:
        return None
    mine, theirs = _ug_spans(cat, got), _ug_spans(cat, ents)
    hit = sorted((mine[0] & theirs[0]) | (mine[1] & theirs[1]))
    if not hit:
        return None
    return ("the only ways in tunnel past another underground on the same axis, which the game "
            "would pair wrong: " + " ".join(f"{x},{y}" for x, y in hit[:4]))


# -- the judge ------------------------------------------------------------------------------------
def _judge(flat, lay, cat, mine, js):
    """{net: (reason, tiles at fault)} for the nets in ``mine`` (routed this run, in routing
    order) whose route leaks, or leaves a pair of its placed ends apart, by ``fkcore.connect``. A
    LEAK between two routes is the later one's fault."""
    rep = connectmod.connect(lay, cat, connectmod.endpoints(flat))
    g = rep.graph
    out = {}

    def route_net(key):
        n = g.nodes.get(key)
        return n.net if n is not None and n.net in mine and key.startswith(f"~{n.net}/") else None

    for lk in rep.leaks:
        a, b = route_net(lk.src), route_net(lk.dst)
        blame = b if b is not None and (a is None or mine.index(b) > mine.index(a)) else a
        if blame is None:
            continue
        key = lk.dst if blame == b else lk.src
        _reason, tiles = out.setdefault(blame, (f"its route would LEAK: {lk.text}", set()))
        tiles |= set(g.nodes[key].tiles)
    for name in mine:
        r = rep.nets.get(name)
        if r is None or name in out:
            continue
        placed = set()
        for owner in js[name].owners:
            placed |= set(flat.insts[owner.rsplit(".", 1)[0]].machines)
        apart = [(d, c) for d, c in r.unreached if d in placed and c in placed]
        alone = [k for k in r.unpaired if k.startswith(f"~{name}/")]
        if not apart and not alone:
            continue
        reason = f"its route does not connect {len(apart)} driver->consumer pairs"
        if alone:
            reason += f"; the game pairs no exit with {', '.join(alone[:4])}"
        tiles = set()
        for key in alone:
            tiles |= set(g.nodes[key].tiles)
        out[name] = (reason, tiles)
    return out


def route_layout(flat, lay, cat, bounds=None, margin=4, retries=None, limit=60000,
                 blocked=(), hand=None) -> Routed:
    """``_route_layout`` with direct insertion by ``hand`` (a short inserter) instead of the
    fast one; long-handed ones still go where only they reach."""
    global _HANDS
    if not hand or hand == "fast-inserter":
        return _route_layout(flat, lay, cat, bounds, margin, retries, limit, blocked)
    if _REACH.get(hand) != 1:
        raise ValueError(f"hand is a short inserter (inserter, fast-inserter, burner-inserter), "
                         f"got {hand!r}")
    saved, _HANDS = _HANDS, ((hand,), (hand, "long-handed-inserter"))
    try:
        return _route_layout(flat, lay, cat, bounds, margin, retries, limit, blocked)
    finally:
        _HANDS = saved


def _route_layout(flat, lay, cat, bounds=None, margin=4, retries=None, limit=60000,
                  blocked=()) -> Routed:
    """Route every net of ``flat`` that has no carriers in ``lay`` yet; -> Routed.

    ``bounds`` (x0, y0, x1, y1) limits the search; default: the factory frame plus ``margin``
    tiles east and south (the frame starts at 0, 0). ``blocked``: ground no carrier may use,
    in the factory frame (terrain: water, cliffs)."""
    js = jobs(flat, lay, cat)
    terrain = frozenset(tuple(t) for t in blocked)
    have = {e.owner[1:] for e in lay.entities.values() if e.owner.startswith("~")}
    kept = sorted(n for n in js if n in have)
    todo = [n for n in js if n not in have and js[n].skip is None and not js[n].fluid]
    todo.sort(key=lambda n: (-len(js[n].ends()), n))
    frames = set()
    for path, rec in lay.insts.items():
        if rec.kind == "Literal" or path not in flat.insts:
            continue
        x0, y0, x1, y1 = frame_of(flat, lay, path, cat)
        frames |= {(x, y) for x in range(x0, x1) for y in range(y0, y1)}
    w, h = lay.size or (0, 0)
    box = bounds or (0, 0, w + margin, h + margin)
    retries = len(todo) if retries is None else retries
    best = None
    order = list(todo)
    for attempt in range(retries + 1):
        ents = list(lay.entities.values())
        added, failed, how = {}, {}, {}
        for net in order:
            got, why = _route_one(cat, js[net], ents, frames, js, box, limit, terrain)
            if got is None:
                failed[net] = why
                continue
            added[net] = got
            how[net] = why
            ents += got
        score = (len(added), -attempt)
        if best is None or score > best[0]:
            best = (score, added, failed, how, attempt + 1, list(order))
        if not failed:
            break
        order = [n for n in order if n in failed] + [n for n in order if n not in failed]
    _score, added, failed, how, passes, order = best
    added, failed, how = dict(added), dict(failed), dict(how)
    new = fkpmod.Layout(lay.level, lay.name, lay.size, dict(lay.insts), dict(lay.covers),
                        dict(lay.plots), dict(lay.claims), dict(lay.marks), dict(lay.entities))
    for net in todo:
        for e in added.get(net, ()):
            new.add(e)
    _repair(flat, new, cat, js, order, added, failed, how, frames, box, limit, terrain)
    for net in sorted(failed):
        guard = _guarded(cat, js[net], list(new.entities.values()), frames, js, box, limit,
                         terrain)
        if guard:
            failed[net] = f"{failed[net]}; {guard}"
    fluid_todo = sorted(n for n in js if js[n].fluid and n not in have and js[n].skip is None)
    plugin = _fluid_plugin() if fluid_todo else None
    if plugin is not None:
        f_added, f_how, f_failed = plugin.route(flat, new, cat, fluid_todo, terrain, box, limit)
        for net in fluid_todo:
            for e in f_added.get(net, ()):
                new.add(e)
        added.update(f_added)
        how.update(f_how)
        failed.update(f_failed)
    xs = [t[0] + 1 for e in new.entities.values() for t in fkpmod.tiles_of(cat, e)]
    ys = [t[1] + 1 for e in new.entities.values() for t in fkpmod.tiles_of(cat, e)]
    new.size = (max(xs + [w]), max(ys + [h]))
    lines = []
    for net in sorted(js, key=fkpmod.natural_key):
        job = js[net]
        if net in kept:
            lines.append(f"kept      {net}: its carriers are already laid (pinned)")
        elif job.skip:
            lines.append(f"skipped   {net}: {job.skip}")
        elif net in added and job.fluid:
            lines.append(f"routed    {net}: {how[net]}")
        elif net in added:
            lines.append(f"routed    {net}: {job.drivers()} -> {job.consumers()}, {how[net]}")
        else:
            lines.append(f"FAILED    {net}: {failed.get(net)}")
    return Routed(new, lines, sorted(added), failed, kept, passes)


def _repair(flat, new, cat, js, order, added, failed, how, frames, box, limit, terrain):
    """Judge the belt routes laid this run; re-route a net that leaks or does not connect around
    the tiles at fault, else refuse it (its carriers go, the judge's line is the reason)."""
    avoid = {}
    for round_ in range(_REPAIRS + 1):
        mine = [n for n in order if n in added]
        bad = _judge(flat, new, cat, mine, js)
        if not bad:
            return
        for net in sorted(bad, key=order.index):
            reason, tiles = bad[net]
            for e in added.pop(net):
                del new.entities[e.key]
            how.pop(net, None)
            if round_ == _REPAIRS or not tiles:
                failed[net] = reason
                continue
            avoid.setdefault(net, set()).update(tiles)
            got, why = _route_one(cat, js[net], list(new.entities.values()), frames, js, box,
                                  limit, terrain, avoid[net])
            if got is None:
                failed[net] = f"{reason}; re-routed around it: {why}"
                continue
            added[net] = got
            how[net] = why
            for e in got:
                new.add(e)
