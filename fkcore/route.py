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

Two nets that share a belt (``lanes A | B``, 2.0) are one job, ``A|B``: each net from its drivers
to its side of a join, and one route of both lanes from the join to every consumer
(``fkcore.pairs``, which lays it through ``_route_one`` part by part; ``NetJob.parts``).

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
``blocked`` (terrain: water, cliffs) and everything outside ``bounds``. A Bus's frame is not
ground of its own: its belts and splitters are entities, and the empty tiles of its two outer
rows (where its ports meet it) let a route cross it by an underground, as one crosses a main
bus (four belts and those two rows: a yellow tunnel spans the belts).

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
fault (twice at most), else refused with the judge's line.

**A rebuild patches what stands** (2.0, Rory 2026-10-21: "Pin what stands and make patch changes
rather than regenerating the base"). ``route --only stale`` hands the router, as ``patch``, the
committed route of every net none of whose ends moved. The judge reads it against the netlist as
it is now, not by the net's name: a route that joins every driver to every consumer, leaks
nowhere and has no carrier that serves no end stands as it is. Any other keeps what still serves,
loses a dropped end's branch, and gets one branch per new end from the router's own search: a new
consumer off where every standing driver reaches it (a dead-end belt extended, a splitter in
place of a straight belt, an inserter off a belt), a new driver into where it reaches every
consumer (side-loaded onto a belt, into the back of a belt nothing feeds, an inserter onto one).
A lane pair is patched by its two nets, each new driver on its own lane (2.0.2). A patch that
can't be laid or that the judge refuses is routed again as a whole, with the reason.
Pure, stdlib only, deterministic.
"""
from __future__ import annotations

import heapq
import math
import re
from dataclasses import dataclass, field

from . import connect as connectmod
from . import fkp as fkpmod
from .expand import attach_points, frame_of
from .steiner import COSTS, FixedSink, Grid, TapSink, Tree, grow
from .steiner import _astar as _search      # one A* from many start states: grow()'s own step

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
    anchors: dict = field(default_factory=dict)    # "<inst>.<role>" -> what the route is laid to
    parts: tuple = ()                              # two nets on one belt: (A, B, both) jobs

    def ends(self):
        return [t for t, _h in self.starts] + [t for t, _h in self.goals] + list(self.reserved)

    def signature(self):
        """Everything a route of this net is laid to: per role, its start or goal tiles with their
        headings and the tiles of the machines it inserts into or picks from; and the reserved
        tiles. A committed fluid route is kept (``route --only stale``) only while this is the
        same: a chest moved one tile changes no belt end, only its machine's tiles (1.2, the 0534
        run). A belt route is kept or patched while no end moved (``moved_ends``)."""
        return (tuple(sorted((o, tuple(sorted(a))) for o, a in self.anchors.items())),
                tuple(sorted(self.reserved)))

    def moved(self, other):
        """The roles whose anchors differ between this job and ``other`` (the same net, another
        layout), sorted."""
        roles = set(self.anchors) | set(other.anchors)
        return sorted(r for r in roles if sorted(self.anchors.get(r, ())) !=
                      sorted(other.anchors.get(r, ())))

    def moved_ends(self, old):
        """The roles with an end that no longer stands where it stood in ``old`` (the same net on
        the committed layout), sorted: a belt end on another tile or heading, a machine of the
        role on other tiles. A role or a machine only one of the two has is an end added or
        dropped, not moved: the committed route is patched for it (2.0, Rory 2026-10-21: "Pin
        what stands and make patch changes rather than regenerating the base")."""
        out = []
        for role in sorted(set(self.anchors) & set(old.anchors)):
            now, was = self.anchors[role], old.anchors[role]
            rects = {a[1]: a[2] for a in now if len(a) == 3}
            if any(a not in now if len(a) == 2 else rects.get(a[1], a[2]) != a[2] for a in was):
                out.append(role)
        return out

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
    kept: list                     # nets whose carriers stand as they were (pinned)
    passes: int = 1
    patched: dict = field(default_factory=dict)    # net -> what its patch laid and kept
    again: dict = field(default_factory=dict)      # net -> why its committed route was not kept


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
            mine = job.anchors.setdefault(f"{path}.{role}", [])
            if d is None:
                for key in flat.insts[path].machines:
                    if key not in lay.entities:          # an older layout, before the machine
                        continue
                    ts = fkpmod.tiles_of(cat, lay.entities[key])
                    rect = (min(t[0] for t in ts), min(t[1] for t in ts),
                            max(t[0] for t in ts) + 1, max(t[1] for t in ts) + 1)
                    (job.sources if side == "out" else job.taps).append((key, rect))
                    mine.append((side, key, rect))
                job.owners.append(f"{path}.{role}")
                continue
            h = _H[int(d)]
            tile = (math.floor(x), math.floor(y))
            if side == "out":
                job.starts.append(((tile[0] + _DX[h], tile[1] + _DY[h]), h))
                mine.append((side, job.starts[-1]))
            else:
                job.goals.append(((tile[0] - _DX[h], tile[1] - _DY[h]), h))
                mine.append((side, job.goals[-1]))
            job.owners.append(f"{path}.{role}")
    if getattr(flat, "pairs", None):
        from . import pairs
        pairs.merge(flat, out)
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


def _direct_pair(src, dst, grid, taken=()):
    """An inserter from machine rect ``src`` into machine rect ``dst`` on a free tile not in
    ``taken`` (one this plan already holds), if one fits: a short hand first, else a long one."""
    for hands in _HANDS:
        for name in hands:
            r = _REACH[name]
            for x in range(src[0], src[2]):
                for y in range(src[1], src[3]):
                    for g in range(4):           # the inserter faces its pickup side, g
                        q = (x - _DX[g] * r, y - _DY[g] * r)
                        drop = (q[0] - _DX[g] * r, q[1] - _DY[g] * r)
                        if q in taken or grid.blocked(q) or not (dst[0] <= drop[0] < dst[2]
                                                                 and dst[1] <= drop[1] < dst[3]):
                            continue
                        return {"name": name, "x": q[0] + 0.5, "y": q[1] + 0.5,
                                "direction": g * 4, "role": "ins"}
    return None


def _direct(cat, job, grid):
    """One machine driver into one machine: a single inserter between them, if one fits."""
    (_sk, src), = job.sources
    (_tk, dst), = job.taps
    got = _direct_pair(src, dst, grid)
    return [got] if got else None


def _direct_claims(cat, js, todo, ents, frames, box, terrain=()):
    """{net: tiles} for the direct inserters of every net with one machine driver, picked before
    any route is laid, so no other net's tree is laid over them: trees are routed first (by their
    belt ends), and a mall's machine-to-machine nets have none. Greedy, net by net, one inserter
    per tile."""
    taken, out = set(), {}
    for net in sorted(todo):
        pairs = _direct_pairs_of(js[net])
        if not pairs:
            continue
        grid = _Bounded(_ground(cat, ents, frames, js, net, terrain), box)
        mine, ends = set(), set(js[net].ends())
        for src, dst in pairs:
            got = _direct_pair(src, dst, grid, taken | mine | ends)
            if got:
                mine.add((math.floor(got["x"]), math.floor(got["y"])))
        if mine:
            out[net] = mine
            taken |= mine
    return out


def _direct_pairs_of(job):
    """[(driver rect, consumer rect)] a direct inserter may join: one machine driver and each
    consumer machine, or (1.4) each of several machine drivers and one consumer machine (two
    cable assemblers beside one circuit assembler). [] for any other net."""
    if job.starts or job.goals:
        return []
    if len(job.sources) == 1 and job.taps:
        return [(job.sources[0][1], rect) for _k, rect in job.taps]
    if len(job.taps) == 1 and len(job.sources) > 1:
        return [(rect, job.taps[0][1]) for _k, rect in job.sources]
    return []


def _hub_job(cat, job, blocked, spans, clear, box, limit):
    """hub: merge every driver into a trunk, split it to every consumer. -> (plan, how).

    One machine driver (1.3, Rory 2026-10-20: a mall placed with care): every consumer machine
    standing next to it takes from it by an inserter of its own (a yellow belt assembler hands its
    belts to the underground, splitter and red belt assemblers beside it), and only the rest is
    laid as a belt tree from the driver."""
    grid = _Bounded(blocked, box, spans)
    # 1.4.1 (the router review): a direct inserter never stands on the net's own belt ends, and
    # when the belt tree for the consumers left can't get out (the direct inserters and other
    # nets' claims took every side of the driver), the whole net is laid as a tree, as before 1.4
    ends = set(job.ends())
    if len(job.sources) == 1 and not job.starts and job.taps:
        (_sk, src), = job.sources
        taken, direct, rest = set(), [], []
        for key, rect in job.taps:
            got = _direct_pair(src, rect, grid, taken | ends)
            if got:
                direct.append(got)
                taken.add((math.floor(got["x"]), math.floor(got["y"])))
            else:
                rest.append((key, rect))
        if direct:
            n = f"{len(direct)} inserter{'s' if len(direct) > 1 else ''} (direct insertion)"
            if not rest and not job.goals:
                return direct, n
            sub = NetJob(job.net, starts=list(job.starts), goals=list(job.goals), taps=rest,
                         sources=list(job.sources), owners=list(job.owners))
            if sub.mode == "hub":
                plan, how = _hub_search(cat, sub, set(blocked) | taken, spans, clear, box, limit)
            else:
                plan, how = _tree_job(cat, sub, set(blocked) | taken, spans, clear, box, limit)
            if plan is not None:
                return direct + plan, f"{n}, then {how}"
            return _hub_search(cat, job, blocked, spans, clear, box, limit)
    if len(job.taps) == 1 and len(job.sources) > 1 and not job.starts and not job.goals:
        # several machine drivers beside one consumer machine: each hands to it by an inserter
        # of its own (1.4); only the drivers left are laid as a belt tree into it
        (_tk, dst), = job.taps
        taken, direct, rest = set(), [], []
        for key, rect in job.sources:
            got = _direct_pair(rect, dst, grid, taken | ends)
            if got:
                direct.append(got)
                taken.add((math.floor(got["x"]), math.floor(got["y"])))
            else:
                rest.append((key, rect))
        if direct:
            n = f"{len(direct)} inserter{'s' if len(direct) > 1 else ''} (direct insertion)"
            if not rest:
                return direct, n
            sub = NetJob(job.net, taps=list(job.taps), sources=rest, owners=list(job.owners))
            plan, how = _hub_search(cat, sub, set(blocked) | taken, spans, clear, box, limit)
            if plan is not None:
                return direct + plan, f"{n}, then {how}"
            return _hub_search(cat, job, blocked, spans, clear, box, limit)
    return _hub_search(cat, job, blocked, spans, clear, box, limit)


def _hub_search(cat, job, blocked, spans, clear, box, limit):
    """The hub search proper: a trunk from every driver, split to every consumer."""
    grid = _Bounded(blocked, box, spans)
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
def _settle_leaves(cat, laid, ents, also=frozenset(), allow=frozenset()):
    """A tapped belt's last tile points on into whatever stands ahead: turn it (never back at its
    feed) where that is another net's belt, or one of the keys ``also`` (a patch's tapped branch:
    the standing route it branched from). ``allow``: keys it may point into on purpose (a joint: a bus
    port or a sealed module's port carrier, 2.0.36). -> the carriers, or None when no turn is clear."""
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
            return o is not None and o.key not in allow and (o.net != e.net or o.key in also)

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


def _route_one(cat, job, ents, frames, js, box, limit, terrain=(), avoid=(), spans=None,
               allow=frozenset()):
    if job.parts:
        from . import pairs
        return pairs.route(cat, job, ents, frames, js, box, limit, terrain, avoid, spans)
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
    laid = _settle_leaves(cat, _carriers(job, plan, net), ents, allow=allow)
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
        owner = key.rsplit("/", 1)[0] if key in g.nodes else ""
        return owner[1:] if owner.startswith("~") and owner[1:] in mine else None

    for lk in rep.leaks:
        a, b = route_net(lk.src), route_net(lk.dst)
        blame = b if b is not None and (a is None or mine.index(b) > mine.index(a)) else a
        if blame is None:
            continue
        key = lk.dst if blame == b else lk.src
        _reason, tiles = out.setdefault(blame, (f"its route would LEAK: {lk.text}", set()))
        tiles |= set(g.nodes[key].tiles)
    for name in mine:
        rs = [rep.nets[n] for n in fkpmod.net_names(name) if n in rep.nets]   # a pair: both
        if not rs or name in out:
            continue
        placed = set()
        for owner in js[name].owners:
            placed |= set(flat.insts[owner.rsplit(".", 1)[0]].machines)
        apart = [(d, c) for r in rs for d, c in r.unreached if d in placed and c in placed]
        alone = sorted({k for r in rs for k in r.unpaired if k.startswith(f"~{name}/")},
                       key=fkpmod.natural_key)
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


# -- patching a committed route (2.0) -------------------------------------------------------------
_BELTY = frozenset({"transport-belt", "splitter"})    # what a drop or a pickup patch meets


def _placed(flat, job):
    """The machines of the instances the net's job has an end in (``_judge``'s pairs)."""
    out = set()
    for owner in job.owners:
        out |= set(flat.insts[owner.rsplit(".", 1)[0]].machines)
    return out


def _ends_of(flat, table, job, g, routed=True, net=None):
    """(drivers, consumers): the net's endpoint keys that stand in graph ``g``; ``routed``: only
    those of the instances the router lays the net to (a Literal's are laid by hand); ``net``: one
    member of a lane pair's job (its ends are the member's, the pair's name has none)."""
    placed = _placed(flat, job) if routed else None
    drivers, consumers = table.get(net or job.net, ((), ()))
    pick = lambda ends: sorted({k for k, _i in ends if k in g.nodes
                                and (placed is None or k in placed)}, key=fkpmod.natural_key)
    return pick(drivers), pick(consumers)


def _flows(g, net, drivers, consumers):
    """({driver: what it reaches}, {consumer: what reaches it}) through ``net``'s carriers."""
    cons, drvs = set(consumers), set(drivers)
    return ({d: g.reach({d}, net, ends=cons) for d in drivers},
            {c: g.reach({c}, net, forward=False, ends=drvs) for c in consumers})


def _serving(g, net, drivers, consumers, keys):
    """The keys of ``keys`` (route carriers) on some path from a driver to a consumer."""
    fwd, bwd = _flows(g, net, drivers, consumers)
    up = set().union(*fwd.values())
    down = set().union(*bwd.values())
    return {k for k in keys if k in up and k in down}


def _common(sets):
    sets = list(sets)
    return set.intersection(*sets) if sets else set()


def _fresh_keys(laid, owner, used, prefix=""):
    """``laid`` keyed ``~<owner>/<prefix><letter><k>`` after every key in ``used``: a committed
    route's keys, taken-up ones too, never go to another carrier (the diff would read a moved
    belt). ``prefix``: a lane pair's part (``l``: its left net's own, ``r``: its right's)."""
    top = {}
    for k in used:
        m = re.fullmatch(r"([lr]?)([a-z])(\d+)", k.rsplit("/", 1)[1])
        if m:
            top[m[1], m[2]] = max(top.get((m[1], m[2]), -1), int(m[3]))
    out = []
    for e in laid:
        letter = e.key.rsplit("/", 1)[1][0]
        top[prefix, letter] = top.get((prefix, letter), -1) + 1
        out.append(fkpmod.Entity(f"~{owner}/{prefix}{letter}{top[prefix, letter]}", e.name,
                                 e.x, e.y, e.dir, dict(e.attrs)))
    return out


def _new_branch(grid, starts, sink, net, reverse, limit):
    """One branch from the standing route: one A* from every start state at once to ``sink``
    (grow()'s own step). -> (plan entities, the start it left from, path) or None."""
    probe = Tree(grid, (grid.box[0] - 9, grid.box[1] - 9, 0, 0))     # empty: the search's ground
    probe.sink_terminal = {}
    got = _search(probe, starts, [sink], [0], limit)
    if got is None:
        return None
    path, how, _i, _cost = got
    t = Tree(grid, path[0])
    t.sink_terminal = {}
    for a, b in zip(path, path[1:]):
        t.succ[a] = ("jump", b) if b[3] else ("step", b)
    t.sink_at[path[-1]] = 0
    if isinstance(sink, TapSink):
        t.taps = sink.pick(path, probe)          # the choice the search's goal test made
    t.touch()
    return t.entities([sink], net=net, reverse=reverse), how, path


def _branch_words(laid):
    """'12 belts, 2 underground ends, 1 inserter' for a new branch's carriers."""
    belts = sum(e.name == "transport-belt" for e in laid)
    ugs = sum(e.name == "underground-belt" for e in laid)
    ins = sum(e.name not in ("transport-belt", "underground-belt", "splitter") for e in laid)
    words = [f"{belts} belt{'s' if belts != 1 else ''}"]
    if ugs:
        words.append(f"{ugs} underground ends")
    if ins:
        words.append(f"{ins} inserter{'s' if ins != 1 else ''}")
    return ", ".join(words)


class _Patch:
    """One net's patch in the making: its standing carriers, what it adds, and the ground. A lane
    pair (``A|B``, 2.0) is patched by its two member nets: each has its own drivers, consumers and
    reach, and a new carrier's ``net=`` says which lanes it carries."""

    def __init__(self, cat, flat, table, job, ents, kept, frames, js, box, limit, terrain, avoid):
        self.cat, self.flat, self.table, self.job, self.net = cat, flat, table, job, job.net
        self.members = fkpmod.net_names(job.net) or [job.net]
        self.ents, self.kept, self.added, self.replaced = list(ents), list(kept), [], []
        self.frames, self.js, self.box, self.limit = frames, js, box, limit
        self.terrain, self.avoid = terrain, set(avoid)
        self.used = {e.key for e in kept}
        self.refresh()

    def refresh(self):
        """The graph, each member's ends and flows, and the ground with what stands now."""
        cat, net = self.cat, self.net
        allents = self.ents + self.kept + self.added
        self.g = connectmod.graph(allents, cat)
        self.ends, self.fwd, self.bwd = {}, {}, {}
        for m in self.members:
            self.ends[m] = _ends_of(self.flat, self.table, self.job, self.g, net=m)
            self.fwd[m], self.bwd[m] = _flows(self.g, m, *self.ends[m])
        ends = set(self.job.ends())
        self.base = (_ground(cat, allents, self.frames, self.js, net, self.terrain)
                     | (self.avoid - ends))
        self.fronts = {}
        for e in allents:
            if not _is_belt(cat, e) or e.attrs.get("ug") == "in" or _heading(e) is None:
                continue
            h = _heading(e)
            for tx, ty in fkpmod.tiles_of(cat, e):
                self.fronts.setdefault((tx + _DX[h], ty + _DY[h]), []).append(e.key)
        # a new belt never stands where any belt points, the net's own included (it would be fed)
        self.blocked = self.base | (set(self.fronts) - ends)
        self.spans = _ug_spans(cat, allents)
        self.clear = _belt_tiles(cat, allents)

    def route_keys(self):
        return {e.key for e in self.kept + self.added}

    def standing(self, m):
        """(member ``m``'s drivers that reach one of its consumers, its consumers one reaches)."""
        drivers, consumers = self.ends[m]
        cons = set(consumers)
        sd = [d for d in drivers if self.fwd[m][d] & cons]
        sc = [c for c in consumers if any(c in self.fwd[m][d] for d in drivers)]
        return sd, sc

    def grid(self, target, reverse=False):
        """The ground of one new branch, and the tiles it may not start on: the net's other
        free end tiles too, so one new end's branch never takes another's tile (the router lays
        every end of a net in one search; a patch lays them one at a time)."""
        others = set(self.job.ends()) - {target}
        g = _Bounded(self.blocked | others, self.box, self.spans,
                     self.clear if reverse else None)
        return g, others

    def lay(self, laid, nets, replaced=()):
        """Add ``laid`` (plan carriers) carrying ``nets``: belts ``A|B`` for both lanes of a pair,
        inserters ``A+B``; keyed under the job, a pair member's own with its part's prefix."""
        net = "|".join(nets)
        for e in laid:
            lanes = self.cat.has_entity(e.name) and self.cat.kind(e.name) in fkpmod.LANE_TYPES
            e.attrs["net"] = net if lanes else fkpmod.hand_net(net)
        prefix = ""
        if len(self.members) > 1 and len(nets) == 1:
            prefix = "l" if nets[0] == self.members[0] else "r"
        laid = _fresh_keys(laid, self.net, self.used, prefix)
        self.used |= {e.key for e in laid}
        self.kept = [e for e in self.kept if e.key not in replaced]
        self.added = [e for e in self.added if e.key not in replaced] + laid
        self.replaced += list(replaced)
        self.refresh()
        return laid

    # -- a consumer: a branch out of the standing route ------------------------------------------
    def out_starts(self, sources):
        """Start states of a new branch from route carriers ``sources`` (every standing driver
        reaches them): a dead-end belt extended, or a splitter cut into a straight belt. Both
        keep every item on its lane."""
        g, out = self.g, []
        for key in sorted(sources, key=fkpmod.natural_key):
            n = g.nodes[key]
            h = _H.get(n.dir)
            if h is None or n.kind not in ("transport-belt", "underground-belt"):
                continue
            (tx, ty), = n.tiles
            f = (tx + _DX[h], ty + _DY[h])
            if (n.kind == "transport-belt" or n.ug == "out") and f not in g.at \
                    and f not in self.base and self.fronts.get(f) == [key]:
                out.append(((f[0], f[1], h, 0), 0.0, ("leaf", key)))
            if n.kind != "transport-belt":
                continue
            feeds = [(k, via) for k, via in g.pred.get(key, ()) if g.nodes[k].kind in _BELT_KINDS]
            ahead = [(k, via) for k, via in g.succ.get(key, ()) if g.nodes[k].kind in _BELT_KINDS]
            if len(feeds) != 1 or feeds[0][1] != "belt" or len(ahead) != 1 \
                    or ahead[0][1] != "belt" or not set(g.nodes[ahead[0][0]].nets) & set(n.nets):
                continue
            for side in (1, 3):
                sh = (h + side) % 4
                m = (tx + _DX[sh], ty + _DY[sh])
                o2 = (m[0] + _DX[h], m[1] + _DY[h])
                if m in g.at or m in self.base or m in self.fronts or o2 in g.at \
                        or o2 in self.blocked:
                    continue
                out.append(((o2[0], o2[1], h, 0), COSTS["split"] - COSTS["belt"],
                            ("split", key, side)))
        return out

    def add_consumer(self, role, belt, machine, nets):
        """Join one new consumer end of ``nets`` (its members) to the standing route, off the
        carriers that every standing driver of each reaches and that carry none but them (a
        branch of both lanes for both nets of a pair). -> report words, or None."""
        g, mine = self.g, self.route_keys()
        common = mine
        for m in nets:
            common = common & _common(self.fwd[m][d] for d in self.standing(m)[0])
        common = {k for k in common if set(g.nodes[k].nets) <= set(nets)}
        if machine is not None:
            got = self._tap_from(common, machine, nets) or self._direct_from(machine, nets)
            if got:
                return f"{role}: {got}"
        grid, others = self.grid(belt[0] if belt is not None else None)
        starts = [s for s in self.out_starts(common) if (s[0][0], s[0][1]) not in others]
        if not starts:
            return None
        sinks = ([FixedSink(role, belt[0], belt[1])] if belt is not None else
                 [TapSink(machine[0], machine[1], 1, hands) for hands in _HANDS])
        for sink in sinks:
            got = _new_branch(grid, starts, sink, self.net, False, self.limit)
            if got is not None:
                break
        else:
            return None
        plan, how, _path = got
        laid = _carriers(self.job, plan, self.net)
        replaced, words = (), ""
        if how[0] == "split":
            _k, key, side = how
            n = g.nodes[key]
            (tx, ty), = n.tiles
            h = _H[n.dir]
            sh = (h + side) % 4
            laid.append(fkpmod.Entity(f"~{self.net}/s0", "splitter",
                                      _clean(tx + (_DX[sh] + 1) / 2), _clean(ty + (_DY[sh] + 1) / 2),
                                      h * 4, {"net": self.net}))
            replaced, words = (key,), f"a splitter in place of {key}"
        else:
            words = f"{how[1]} extended"
        also = frozenset(mine) if belt is None else frozenset()
        settled = _settle_leaves(self.cat, laid, self.ents + self.kept + self.added, also)
        if settled is None:
            return None
        laid = self.lay(settled, nets, replaced)
        return f"{role}: {words}, {_branch_words([e for e in laid if e.name != 'splitter'])}"

    def _tap_from(self, keys, machine, nets):
        """An inserter from a standing belt the drivers reach straight into a new machine."""
        mkey, rect = machine
        grid, _others = self.grid(None)
        free = lambda q: not grid.blocked(q) and q not in self.g.at
        for hands in _HANDS:
            sink = TapSink(mkey, rect, 1, hands)
            for key in sorted(keys, key=fkpmod.natural_key):
                n = self.g.nodes[key]
                if n.kind not in _BELT_KINDS or (n.kind == "underground-belt" and not n.ug):
                    continue
                for tile in n.tiles:
                    for q, name, direction in sink.taps_at(tile, free):
                        e = fkpmod.Entity(f"~{self.net}/i0", name, q[0] + 0.5, q[1] + 0.5,
                                          direction, {})
                        laid = self.lay([e], nets)
                        return f"an inserter from {key} ({laid[0].key})"
        return None

    def _direct_from(self, machine, nets):
        """A machine-to-machine net: an inserter from every standing driver machine of each of
        ``nets`` straight into the new one, where each fits."""
        rects = dict(self.job.sources)
        drivers = [(d, m) for m in nets for d in self.standing(m)[0]]
        if not drivers or any(d not in rects for d, _m in drivers):
            return None
        grid, _others = self.grid(None)
        plan, taken = [], set()
        for d, m in drivers:
            got = _direct_pair(rects[d], machine[1], grid, taken)
            if got is None:
                return None
            plan.append((got, m))
            taken.add((math.floor(got["x"]), math.floor(got["y"])))
        for got, m in plan:
            self.lay(_carriers(self.job, [got], self.net), [m])
        names = [d for d, _m in drivers]
        return f"{len(plan)} inserter{'s' if len(plan) != 1 else ''} from {', '.join(names)}"

    # -- a driver: a branch into the standing route ----------------------------------------------
    def in_roots(self, targets, m):
        """Root states of a new branch of member ``m``, laid reversed, into route belts
        ``targets`` (they reach every consumer of ``m``): beside a belt, side-loading onto it
        (never a curve, which a second input would straighten), or behind a belt no belt feeds
        yet. Onto a belt of a lane pair, only from the side of ``m``'s lane: a side-load lands on
        the near lane (CORE-V2 "Lane physics")."""
        g, out = self.g, []
        for key in sorted(targets, key=fkpmod.natural_key):
            n = g.nodes[key]
            e = _H.get(n.dir)
            if n.kind != "transport-belt" or e is None or m not in n.nets:
                continue
            (tx, ty), = n.tiles
            vias = [via for k, via in g.pred.get(key, ()) if g.nodes[k].kind in _BELT_KINDS]
            if "curve" in vias:
                continue
            if n.nets == (m,):
                ways = [(s, "side-loaded onto") for s in ((e + 1) % 4, (e + 3) % 4)]
                if not vias:
                    ways.append((e, "into the back of"))
            else:
                lanes = fkpmod.net_lanes(n.net) or {}
                if m in lanes.get("L", ()):
                    ways = [((e + 1) % 4, "side-loaded onto the left lane of")]
                elif m in lanes.get("R", ()):
                    ways = [((e + 3) % 4, "side-loaded onto the right lane of")]
                else:
                    ways = []
            for s, words in ways:
                u = (tx - _DX[s], ty - _DY[s])
                if u in g.at or u in self.blocked:
                    continue
                out.append(((u[0], u[1], (s + 2) % 4, 0), 0.0, (words, key)))
        return out

    def add_driver(self, role, belt, machine, m):
        """Join one new driver end of member ``m`` into the standing route, where it reaches
        every consumer of ``m``. -> report words, or None."""
        common = _common(self.bwd[m][c] for c in self.ends[m][1]) & self.route_keys()
        if machine is not None:
            got = self._drop_onto(common, machine, m) or self._direct_into(machine, m)
            if got:
                return f"{role}: {got}"
        grid, others = self.grid(belt[0] if belt is not None else None, reverse=True)
        roots = [s for s in self.in_roots(common, m) if (s[0][0], s[0][1]) not in others]
        if not roots:
            return None
        sinks = ([FixedSink(role, belt[0], (belt[1] + 2) % 4)] if belt is not None else
                 [TapSink(machine[0], machine[1], 1, hands) for hands in _HANDS])
        for sink in sinks:
            got = _new_branch(grid, roots, sink, m, True, self.limit)
            if got is not None:
                break
        else:
            return None
        plan, how, _path = got
        settled = _settle_leaves(self.cat, _carriers(self.job, plan, m),
                                 self.ents + self.kept + self.added)
        if settled is None:
            return None
        laid = self.lay(settled, [m])
        return f"{role}: {_branch_words(laid)}, {how[0]} {how[1]}"

    def _drop_onto(self, keys, machine, m):
        """An inserter from a new driver machine of ``m`` straight onto a standing belt of ``m``
        alone that reaches every consumer (an inserter drops on a belt's far lane, so never onto
        a pair's belt)."""
        mkey, rect = machine
        grid, _others = self.grid(None)
        for hands in _HANDS:
            for key in sorted(keys, key=fkpmod.natural_key):
                n = self.g.nodes[key]
                if n.nets != (m,) or (n.kind not in _BELTY and not (
                        n.kind == "underground-belt" and n.ug == "in")):
                    continue
                for (tx, ty) in n.tiles:
                    for h in range(4):
                        for name in hands:
                            r = _REACH[name]
                            q = (tx + _DX[h] * r, ty + _DY[h] * r)
                            pick = (q[0] + _DX[h] * r, q[1] + _DY[h] * r)
                            if grid.blocked(q) or q in self.g.at or not (
                                    rect[0] <= pick[0] < rect[2] and rect[1] <= pick[1] < rect[3]):
                                continue
                            e = fkpmod.Entity(f"~{self.net}/i0", name, q[0] + 0.5, q[1] + 0.5,
                                              h * 4, {})
                            laid = self.lay([e], [m])
                            return f"an inserter onto {key} ({laid[0].key})"
        return None

    def _direct_into(self, machine, m):
        """A machine-to-machine net: an inserter from the new driver of ``m`` into every
        consumer machine of ``m``, where each fits."""
        rects = dict(self.job.taps)
        consumers = self.ends[m][1]
        if not consumers or any(c not in rects for c in consumers):
            return None
        grid, _others = self.grid(None)
        plan, taken = [], set()
        for c in consumers:
            got = _direct_pair(machine[1], rects[c], grid, taken)
            if got is None:
                return None
            plan.append(got)
            taken.add((math.floor(got["x"]), math.floor(got["y"])))
        laid = self.lay(_carriers(self.job, plan, m), [m])
        return f"{len(laid)} inserter{'s' if len(laid) != 1 else ''} into {', '.join(consumers)}"


def _role_ends(flat, job, machines, side):
    """[(role, belt end or None, (machine key, rect) or None)]: the ends on ``side`` of the
    net's roles in the instances of ``machines``, one per belt end or machine."""
    machines, out = set(machines), []
    for role, entries in sorted(job.anchors.items()):
        if not machines & set(flat.insts[role.rsplit(".", 1)[0]].machines):
            continue
        for a in entries:
            if a[0] != side:
                continue
            if len(a) == 2:
                out.append((role, a[1], None))
            elif a[1] in machines:
                out.append((role, None, (a[1], a[2])))
    return out


def _patch_net(flat, cat, table, job, old, ents, frames, js, box, limit, terrain=(), avoid=()):
    """Patch one net's committed route ``old`` (carriers) on the layout ``ents``, whose ends all
    still stand where they stood: keep what still serves, take up what serves no end any more (a
    dropped end's branch), and route only each new end into it. -> (carriers, report text) or
    (None, why).

    2.0 (Rory, 2026-10-21): "Pin what stands and make patch changes rather than regenerating the
    base ... routing a new section into the old one, even as a bit of spaghetti, beats ripping
    everything up." The first lead run's players re-laid iron, coal and plates at once for one
    consumer added, and iron stood for 20 minutes. A new consumer branches off where every
    standing driver reaches: a dead-end belt extended, a splitter cut into a straight belt, or an
    inserter straight off a belt (or a driver machine) into it; a new driver joins where it
    reaches every consumer: side-loaded onto a belt, into the back of a belt nothing feeds, or an
    inserter onto it. Each branch is the router's own search (``steiner``), on the router's
    ground, and ``fkcore.connect`` judges the result: every pair joined, no LEAK.

    A lane pair (``A|B``, 2.0.2; the lead's merge of V2 lanes, 2026-10-22, routed a changed pair
    again whole) is patched by its two nets: a new consumer of both branches off the belt of both
    lanes (a splitter or the belt's end, which keep each item on its lane), a new driver of A
    joins A's own belt or the left lane of the pair's, and each net's report is judged."""
    members = fkpmod.net_names(job.net) or [job.net]
    sub = {m: table.get(m, ((), ())) for m in members}
    mine = {e.key for e in old}
    g = connectmod.graph(list(ents) + list(old), cat)
    serve = set()
    for m in members:
        serve |= _serving(g, m, *_ends_of(flat, table, job, g, routed=False, net=m), mine)
    rep = connectmod.connect(g, cat, sub)
    leak = next((lk for lk in rep.leaks if lk.src in serve or lk.dst in serve), None)
    if leak is not None:
        return None, f"what stands of its route would LEAK: {leak.text}"
    kept = [e for e in old if e.key in serve]
    p = _Patch(cat, flat, table, job, ents, kept, frames, js, box, limit, terrain, avoid)
    p.used |= mine
    new_c, new_d = set(), set()
    for m in members:
        sd, sc = p.standing(m)
        if not sd or not sc:
            of = f" of {m}" if len(members) > 1 else ""
            return None, f"nothing of its committed route joins a driver{of} to a consumer now"
        apart = [(d, c) for d in sd for c in sc if c not in p.fwd[m][d]]
        if apart:
            return None, f"its committed route leaves {apart[0][0]} -> {apart[0][1]} apart"
        drivers, consumers = p.ends[m]
        new_c |= {c for c in consumers if c not in sc}
        new_d |= {d for d in drivers if d not in sd}

    def nets_of(role, machine, side):
        """The members whose ends (``side``: 0 drivers, 1 consumers) the role's machine is."""
        keys = {machine[0]} if machine else set(flat.insts[role.rsplit(".", 1)[0]].machines)
        return [m for m in members if keys & set(p.ends[m][side])]

    words = []
    for role, belt, machine in _role_ends(flat, job, new_c, "in"):
        got = p.add_consumer(role, belt, machine, nets_of(role, machine, 1))
        if got is None:
            return None, f"no branch from the standing route reaches {role}"
        words.append(got)
    for role, belt, machine in _role_ends(flat, job, new_d, "out"):
        for m in nets_of(role, machine, 0):
            got = p.add_driver(role, belt, machine, m)
            if got is None:
                return None, f"no branch from {role} reaches the standing route"
            words.append(got)
    rep = connectmod.connect(p.g, cat, sub)
    keys = p.route_keys()
    leak = next((lk for lk in rep.leaks if lk.src in keys or lk.dst in keys), None)
    if leak is not None:
        return None, f"the patch would LEAK: {leak.text}"
    for m in members:
        r = rep.nets.get(m)
        drivers, consumers = p.ends[m]
        apart = [(d, c) for d, c in (r.unreached if r else ()) if d in drivers and c in consumers]
        if apart:
            return None, f"the patch leaves {apart[0][0]} -> {apart[0][1]} apart"
        alone = [k for k in (r.unpaired if r else ()) if k in keys]
        if alone:
            return None, f"the game would pair no exit with {', '.join(alone[:4])}"
    gone = len(old) - len(kept)
    if gone:
        words.append(f"{gone} carrier{'s' if gone != 1 else ''} taken up (no end of the net "
                     f"needs {'them' if gone != 1 else 'it'} now)")
    text = (f"{job.drivers()} -> {job.consumers()}, " + ("; ".join(words) or "nothing new")
            + f"; {len(p.kept)} of {len(old)} carriers kept")
    return p.kept + p.added, text


def _standing(flat, new, cat, js, patch, frames, box, limit, terrain, avoid):
    """The committed routes of ``patch`` ({net: carriers}: nets none of whose ends moved) on
    ``new``, judged against the netlist as it is now (``fkcore.connect``). A route that joins
    every driver of its net to every consumer, leaks nowhere and has no carrier that serves no
    end stands as it is; any other is patched (``_patch_net``), or routed again when it can't
    be. What stands is added to ``new``. -> (nets kept as they were, {net: patch report},
    {net: why it is routed again}).

    2.0: the netlist decides, not the net's name. The first lead run changed a net's sink and
    kept its name (``net packs: X -> lab`` to ``X -> px``): the route stood as it was, the build
    said OK, and the old inserter still fed the lab."""
    table = connectmod.endpoints(flat)
    for net in sorted(patch):
        for e in patch[net]:
            new.add(fkpmod.Entity(e.key, e.name, e.x, e.y, e.dir, dict(e.attrs)))
    g = connectmod.graph(new, cat)
    rep = connectmod.connect(g, cat, table)
    faulty = {}
    for net in sorted(patch):
        keys = {e.key for e in patch[net]}
        leak = next((lk for lk in rep.leaks if lk.src in keys or lk.dst in keys), None)
        # a lane pair (``A|B``, merged with route patching 2026-10-22) is judged by its two nets:
        # the ends and the connect report are theirs, its own name has none
        apart, served = [], set()
        for m in fkpmod.net_names(net):
            drivers, consumers = _ends_of(flat, table, js[net], g, net=m)
            r = rep.nets.get(m)
            apart += [(d, c) for d, c in (r.unreached if r else ())
                      if d in drivers and c in consumers]
            if not js[net].fluid:
                served |= _serving(g, m, *_ends_of(flat, table, js[net], g, routed=False, net=m),
                                   keys)
        idle = [] if js[net].fluid else sorted(keys - served, key=fkpmod.natural_key)
        if leak is not None:
            faulty[net] = f"its committed route would LEAK: {leak.text}"
        elif apart:
            more = len(apart) - 1
            faulty[net] = (f"its committed route does not join {apart[0][0]} -> {apart[0][1]}"
                           + (f" and {more} more pair{'s' if more != 1 else ''}" if more else ""))
        elif idle:
            faulty[net] = (f"{len(idle)} of its committed carriers serve no end of it now "
                           f"({idle[0]} ...)")
        elif js[net].skip:
            faulty[net] = js[net].skip
    for net in faulty:
        for e in patch[net]:
            del new.entities[e.key]
    standing = sorted(n for n in patch if n not in faulty)
    patched, again = {}, {}
    pending = {n: patch[n] for n in faulty}
    for net in sorted(faulty):
        old = pending.pop(net)
        if js[net].fluid or js[net].skip:
            again[net] = faulty[net]
            continue
        # the routes still waiting for their patch stand in the way, as their carriers may stay
        ground = list(new.entities.values()) + [e for ents in pending.values() for e in ents]
        try:
            got, how = _patch_net(flat, cat, table, js[net], old, ground, frames, js, box, limit,
                                  terrain, avoid)
        except Exception as exc:         # noqa: BLE001 - the net is routed again, as before 2.0
            got, how = None, f"{type(exc).__name__}: {exc}"
        if got is None:
            again[net] = f"{faulty[net]}; patching it failed: {how}"
            continue
        for e in got:
            new.add(e)
        patched[net] = how
    return standing, patched, again


def route_layout(flat, lay, cat, bounds=None, margin=4, retries=None, limit=60000,
                 blocked=(), hand=None, patch=None) -> Routed:
    """``_route_layout`` with direct insertion by ``hand`` (a short inserter) instead of the
    fast one; long-handed ones still go where only they reach."""
    global _HANDS
    if not hand or hand == "fast-inserter":
        return _route_layout(flat, lay, cat, bounds, margin, retries, limit, blocked, patch)
    if _REACH.get(hand) != 1:
        raise ValueError(f"hand is a short inserter (inserter, fast-inserter, burner-inserter), "
                         f"got {hand!r}")
    saved, _HANDS = _HANDS, ((hand,), (hand, "long-handed-inserter"))
    try:
        return _route_layout(flat, lay, cat, bounds, margin, retries, limit, blocked, patch)
    finally:
        _HANDS = saved


def _route_layout(flat, lay, cat, bounds=None, margin=4, retries=None, limit=60000,
                  blocked=(), patch=None) -> Routed:
    """Route every net of ``flat`` that has no carriers in ``lay`` yet; -> Routed.

    ``bounds`` (x0, y0, x1, y1) limits the search; default: the factory frame plus ``margin``
    tiles east and south (the frame starts at 0, 0). ``blocked``: ground no carrier may use,
    in the factory frame (terrain: water, cliffs). ``patch``: {net: its committed carriers} for
    nets none of whose ends moved (``route --only stale``): each stands as it is, is patched,
    or is routed again (``_standing``), before the nets with nothing laid are routed."""
    js = jobs(flat, lay, cat)
    terrain = frozenset(tuple(t) for t in blocked)
    have = {e.owner[1:] for e in lay.entities.values() if e.owner.startswith("~")}
    patch = {n: ents for n, ents in (patch or {}).items() if n in js and n not in have}
    todo = [n for n in js if n not in have and n not in patch and js[n].skip is None
            and not js[n].fluid]
    frames = set()
    owned = {}                                   # instance path -> its frame's tiles
    sealed = {}                                  # module path -> its frame, for a sealed module
    for path, rec in lay.insts.items():
        if rec.kind in ("Literal", "Bus") or path not in flat.insts:
            continue
        x0, y0, x1, y1 = frame_of(flat, lay, path, cat)
        mine = {(x, y) for x in range(x0, x1) for y in range(y0, y1)}
        frames |= mine
        owned[path] = mine
        if path in flat.sealed:
            sealed[path] = (x0, y0, x1, y1, mine)
    w, h = lay.size or (0, 0)
    box = bounds or (0, 0, w + margin, h + margin)
    # the joint carriers a route may hand over into: a sealed module's port belts and a bus's load and
    # mouth stubs (2.0.36, PLAN-MODULES phase 3)
    joints = set()
    for path, rec in lay.insts.items():
        if path not in flat.insts:
            continue
        for key in flat.insts[path].machines:
            m = flat.machines.get(key)
            if m is not None and m.extra.get("port") in ("load", "mouth"):
                joints.add(key)
            if m is not None and m.extra.get("mouth"):
                # a mouth is a belt end of the bus itself: its carrier is the bus's own belt
                name = m.extra.get("at") or ""
                if name.startswith("in") and name[2:].isdigit():
                    joints.add(f"{path}/b{int(name[2:])}_0")
        if flat.insts[path].module is not None:
            for k in flat.ports:
                if k.startswith(path + "/") and "/" not in k[len(path) + 1:]:
                    joints.add(f"{path}/port_{flat.ports[k].name}")

    def net_frames(net):
        """The blocked frames for ``net`` and its box: a net inside a sealed module routes in that
        module's frame (bounded by the innermost one); every other net keeps every frame blocked,
        so a crossing can only be a port (PLAN-MODULES phase 3). Only the frames of the modules
        the net is inside are free: a template's frame or a sealed child's inside them stays
        blocked, as it is for a net outside (2.0.40: the child's frame was freed with its
        parent's, and a parent net ran straight across a sealed child)."""
        parts = net.split("/")[:-1]
        inside = []
        for i in range(1, len(parts) + 1):
            pre = "/".join(parts[:i])
            if pre in sealed:
                inside.append(pre)
        if not inside:
            return frames, box
        blocked = set()
        for path, tiles in owned.items():
            if path not in inside:
                blocked |= tiles
        x0, y0, x1, y1, _tiles = sealed[inside[-1]]
        return frozenset(blocked), (x0, y0, x1, y1)
    base = lay.copy()
    standing, patched, again = [], {}, {}
    if patch:
        claims = _direct_claims(cat, js, todo, list(base.entities.values()), frames, box, terrain)
        standing, patched, again = _standing(flat, base, cat, js, patch, frames, box, limit,
                                             terrain, set().union(*claims.values()))
        todo += [n for n in again if js[n].skip is None and not js[n].fluid]
    kept = sorted(n for n in js if n in have or n in standing)
    todo.sort(key=lambda n: (-len(js[n].ends()), n))
    retries = len(todo) if retries is None else retries
    claims = _direct_claims(cat, js, todo, list(base.entities.values()), frames, box, terrain)
    best = None
    order = list(todo)
    for attempt in range(retries + 1):
        ents = list(base.entities.values())
        added, failed, how = {}, {}, {}
        for net in order:
            avoid = set()
            for other, tiles in claims.items():
                if other != net:
                    avoid |= tiles
            fnet, bnet = net_frames(net)
            got, why = _route_one(cat, js[net], ents, fnet, js, bnet, limit, terrain, avoid,
                                  allow=joints)
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
    new = base.copy()
    for net in todo:
        for e in added.get(net, ()):
            new.add(e)
    _repair(flat, new, cat, js, order, added, failed, how, frames, box, limit, terrain)
    for net in sorted(failed):
        guard = _guarded(cat, js[net], list(new.entities.values()), frames, js, box, limit,
                         terrain)
        if guard:
            failed[net] = f"{failed[net]}; {guard}"
    fluid_todo = sorted(n for n in js if js[n].fluid and n not in have and n not in kept
                        and js[n].skip is None)
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
        elif net in patched:
            lines.append(f"patched   {net}: {patched[net]}")
        elif job.skip:
            lines.append(f"skipped   {net}: {job.skip}")
        elif net in added and job.fluid:
            lines.append(f"routed    {net}: {how[net]}")
        elif net in added:
            lines.append(f"routed    {net}: {job.drivers()} -> {job.consumers()}, {how[net]}")
        else:
            lines.append(f"FAILED    {net}: {failed.get(net)}")
    lines += seal_checks(flat, new, cat)
    lines += port_checks(flat, new, cat)
    return Routed(new, lines, sorted(added), failed, kept, passes, patched, again)


def seal_checks(flat, lay, cat):
    """SEAL (PLAN-MODULES phase 3): a net's carrier inside a sealed module's frame that the net does
    not belong to -- a crossing that is not at a port -- or one of the module's own nets' carriers
    outside its frame. One line per carrier at fault; none when every sealed module is sealed.
    FRAME (2.0.40): an entity of the module's own (a machine, a template's belt) outside its frame."""
    out = []
    for path, rec in sorted(lay.insts.items()):
        if path not in flat.insts or path not in flat.sealed:
            continue
        try:
            x0, y0, x1, y1 = frame_of(flat, lay, path, cat)
        except Exception:
            continue
        frame = {(x, y) for x in range(x0, x1) for y in range(y0, y1)}
        ports = {f"{path}/port_{flat.ports[k].name}" for k in flat.ports
                 if k.startswith(path + "/") and "/" not in k[len(path) + 1:]}
        for key, e in lay.entities.items():
            net = e.attrs.get("net")
            tiles = fkpmod.tiles_of(cat, e)
            inside = all(t in frame for t in tiles)
            if key.startswith(path + "/") and not inside:
                # FRAME (2.0.40): the module's own contents past its declared size (2.0.37's rib:
                # a row one tile past the south edge, its port under the assembler)
                out.append(f"FRAME     {key} ({e.name}) is part of sealed module {path} but stands "
                           f"outside its frame {x0},{y0}..{x1 - 1},{y1 - 1}: grow its size or "
                           "move it in")
                continue
            if not net:
                continue
            mine = net == path or net.startswith(path + "/")
            if key in ports:
                continue
            if inside and not mine:
                out.append(f"SEAL      {key} ({net}) stands inside sealed module {path} and is not "
                           "one of its ports")
            elif mine and not inside:
                out.append(f"SEAL      {key} ({net}) belongs to sealed module {path} but stands "
                           "outside its frame")
    return out


def port_checks(flat, lay, cat):
    """PORT (2.0.37, PLAN-MODULES phase 3): the tiles just inside and just outside a sealed module's
    port must be free for the route to meet the port carrier. A machine standing on one of them (the
    rib's assembler under the port, say) loses that entity when the design is built: the route is laid
    through it. One line per taken tile.

    2.0.41 (PLAN-GLOBAL phase A): a committed port record and a pin must agree; the pin wins, since
    the source is what someone decided (the rebuild then records the pinned tile)."""
    out, seen = [], set()
    for key in sorted(getattr(flat, "port_records", ())):
        port = flat.ports.get(key)
        rec = flat.port_records[key]
        if port is None or port.pos is None or port.size is None:
            continue
        w, h = port.size
        if port.side in "ew":
            pin = (w - 1 if port.side == "e" else 0, port.pos - 1)
        else:
            pin = (port.pos - 1, 0 if port.side == "n" else h - 1)
        if (rec.x, rec.y) != pin:
            out.append(f"PORT      {key}: the committed tile {rec.x},{rec.y} and the pin "
                       f"@{port.side}{port.pos} disagree: the pin wins (a rebuild records "
                       f"{pin[0]},{pin[1]})")
    for path, rec in sorted(lay.insts.items()):
        if path not in flat.insts or path not in flat.sealed:
            continue
        occ = {}
        for key, e in lay.entities.items():
            for t in fkpmod.tiles_of(cat, e):
                occ.setdefault(t, key)
        ports = {f"{path}/port_{flat.ports[k].name}" for k in flat.ports
                 if k.startswith(path + "/") and "/" not in k[len(path) + 1:]}
        for role, _side, _net, (x, y, d) in attach_points(flat, lay, path, cat):
            if d is None:
                continue
            k = _H[int(d)]
            tile = (math.floor(x), math.floor(y))
            for sign, where in ((1, "inside"), (-1, "outside")):
                t = (tile[0] + sign * _DX[k], tile[1] + sign * _DY[k])
                other = occ.get(t)
                if other is None or other in ports or other.startswith("~"):
                    continue
                name = f"{path}.{role.rsplit('!', 1)[0]}"
                if (name, t, other) in seen:
                    continue
                seen.add((name, t, other))
                out.append(f"PORT      {name}: its {where} tile {t[0]},{t[1]} is taken by {other}")
    return out


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
