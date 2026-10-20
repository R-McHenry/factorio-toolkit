"""fkcore.route: the router chunk (CORE-V1.md §9): a factory's nets -> keyed route carriers.

Input: the flat netlist, the factory layout (its fragments placed, each role with an attach
point) and the catalog. For every net that has no carriers of its own yet, the router lays the
belts between the attach points: from each driver role's product belt (the route starts on the
tile its belt points into) to each consumer role's input belt (the route ends on the tile behind
its first belt, pointing into it). Output: carriers keyed ``~<net>/b<k>`` (belts), ``u<k>``
(undergrounds) and ``s<k>`` (splitters), ``net=<net>``, plus a report line per net. A net it
can't route is reported with the reason, never raised; nothing else is moved.

The search is ``fkcore.steiner`` (v4's tree router, copied): one net is a tree of belt steps,
underground jumps and splitters. A net with one driver grows forward from it to all consumers,
splitting where it branches. A net with one consumer and several drivers grows from the consumer
to the drivers and is laid reversed, so the splitters become merges (``Tree.entities(reverse)``).
A consumer that is a single machine (a chest, an assembler cell: its role has no attach tile) is
reached by direct insertion: a fast (or long-handed) inserter beside the belt picks into it
(``steiner.TapSink``), keyed ``~<net>/i<k>``. A single machine as a driver (a requester chest
feeding a row) works the same way on a reversed tree, so its inserter turns round to pick from
the machine; that needs exactly one consumer. Several drivers AND several consumers are not
routed yet (reported).

Per net the ground is: every entity tile, every placed instance's whole frame (the empty tiles
inside a row are kept for poles), every other net's start and end tiles, every tile another
net's belt points into, and everything outside ``bounds``. Nets are routed one at a time, each
seeing the ones before it; a net that fails moves to the front and the pass is retried, and
the pass that routes the most nets is kept. ``fkcore.connect`` is the judge: a routed layout is
done when every net is connected with no LEAK. Pure, stdlib only, deterministic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import fkp as fkpmod
from .expand import attach_points, frame_of
from .steiner import FixedSink, Grid, TapSink, grow

__all__ = ["NetJob", "Routed", "jobs", "route_layout"]

_H = {0: 0, 4: 1, 8: 2, 12: 3}
_DX = (0, 1, 0, -1)
_DY = (-1, 0, 1, 0)
_BELTS = ("transport-belt", "underground-belt", "splitter")


@dataclass
class NetJob:
    net: str
    starts: list = field(default_factory=list)     # [(tile, heading)] the tile a driver belt feeds
    goals: list = field(default_factory=list)      # [(tile, heading)] the tile behind a consumer
    taps: list = field(default_factory=list)       # [(machine key, tile rect)] direct insertion
    sources: list = field(default_factory=list)    # [(machine key, tile rect)] a machine driver
    owners: list = field(default_factory=list)     # "<inst>.<role>" per start/goal, for the report
    skip: str | None = None

    def ends(self):
        return [t for t, _h in self.starts] + [t for t, _h in self.goals]

    def consumers(self):
        return len(self.goals) + len(self.taps)


@dataclass
class Routed:
    layout: object                 # the factory Layout with the route carriers added
    lines: list                    # one report line per net
    routed: list                   # net names routed this run
    failed: dict                   # net -> reason
    kept: list                     # nets that already had carriers (pinned)
    passes: int = 1


class _Bounded(Grid):
    """A Grid that is also blocked outside a box, so no search wanders off the factory."""

    def __init__(self, blocked, box, spans=None):
        super().__init__(blocked, (), spans)
        self.box = box

    def blocked(self, t):
        x0, y0, x1, y1 = self.box
        return not (x0 <= t[0] < x1 and y0 <= t[1] < y1) or t in self.occ


def jobs(flat, lay, cat) -> dict:
    """{net: NetJob} from every placed instance's attach points."""
    out = {}
    for path, rec in sorted(lay.insts.items()):
        if rec.kind == "Literal" or path not in flat.insts:
            continue
        for role, side, net, (x, y, d) in attach_points(flat, lay, path, cat):
            if net is None:
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
        drivers = len(job.starts) + len(job.sources)
        if job.skip is not None:
            continue
        if not drivers:
            job.skip = "no driver role is placed"
        elif not job.consumers():
            job.skip = "no consumer role is placed"
        elif drivers > 1 and job.consumers() > 1:
            job.skip = (f"{drivers} drivers and {job.consumers()} consumers: "
                        "merge-then-split trees are not routed yet")
        elif (drivers > 1 or job.sources) and job.taps:
            job.skip = "a machine driver or several drivers into a single machine: not routed yet"
    return out


def _belt_fronts(cat, ents):
    """{tile: net} for every tile a belt, an underground exit or a splitter points into."""
    out = {}
    for e in ents:
        if e.name not in _BELTS or e.dir is None or e.attrs.get("ug") == "in":
            continue
        h = _H.get(int(e.dir))
        if h is None:
            continue
        for tx, ty in fkpmod.tiles_of(cat, e):
            out.setdefault((tx + _DX[h], ty + _DY[h]), e.net)
    return out


def _ug_spans(cat, ents):
    """Grid spans per axis of the undergrounds already laid (no same-axis tunnel may cross one)."""
    spans = {0: set(), 1: set()}
    ugs = [e for e in ents if e.name == "underground-belt" and e.dir is not None]
    outs = {(math.floor(e.x), math.floor(e.y), _H[int(e.dir)]) for e in ugs
            if e.attrs.get("ug") == "out"}
    for e in ugs:
        if e.attrs.get("ug") != "in":
            continue
        h = _H[int(e.dir)]
        x, y = math.floor(e.x), math.floor(e.y)
        for k in range(1, 12):
            if (x + _DX[h] * k, y + _DY[h] * k, h) in outs:
                spans[h % 2] |= {(x + _DX[h] * j, y + _DY[h] * j) for j in range(k + 1)}
                break
    return spans


def _ground(cat, ents, frames, js, net):
    blocked = set(frames)
    for e in ents:
        blocked |= fkpmod.tiles_of(cat, e)
    for tile, owner in _belt_fronts(cat, ents).items():
        if owner != net:
            blocked.add(tile)
    for other, job in js.items():
        if other != net:
            blocked |= set(job.ends())
    return blocked - set(js[net].ends())


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


def _route_one(cat, job, ents, frames, js, box, limit):
    net = job.net
    blocked = _ground(cat, ents, frames, js, net)
    grid = _Bounded(blocked, box, _ug_spans(cat, ents))
    # several drivers, or a machine driver: grow from the one consumer, lay it reversed
    reverse = len(job.starts) + len(job.sources) > 1 or bool(job.sources)
    if reverse:
        (gtile, gh), = job.goals
        root = (gtile[0], gtile[1], (gh + 2) % 4, 0)
        sinks = [FixedSink(f"driver{i}", t, (h + 2) % 4) for i, (t, h) in enumerate(job.starts)]
        machines = job.sources
    else:
        (stile, sh), = job.starts
        root = (stile[0], stile[1], sh, 0)
        sinks = [FixedSink(f"consumer{i}", t, h) for i, (t, h) in enumerate(job.goals)]
        machines = job.taps
    if grid.blocked((root[0], root[1])):
        return None, f"its {'end' if reverse else 'start'} tile {root[0]},{root[1]} is taken"
    # direct insertion: fast inserters (Rory's rule) unless only a long-handed one can reach
    for hands in (("fast-inserter",), ("fast-inserter", "long-handed-inserter")):
        taps = [TapSink(key, rect, 1, hands) for key, rect in machines]
        res = grow(grid, root, sinks + taps, limit=limit)
        if not res["problems"] or not machines:
            break
    sinks = sinks + taps
    if res["problems"]:
        return None, "; ".join(res["problems"][:3])
    tree = res["tree"]
    plan = tree.entities(sinks, net=net, reverse=reverse)
    c = res["counts"]
    how = (f"{c['belts']} belts, {c['undergrounds']} underground ends, {c['splitters']} "
           f"{'merges' if reverse else 'splitters'}" + (f", {c['taps']} inserters" if c["taps"]
                                                         else ""))
    return _carriers(job, plan, net), how


def route_layout(flat, lay, cat, bounds=None, margin=4, retries=None, limit=60000) -> Routed:
    """Route every net of ``flat`` that has no carriers in ``lay`` yet; -> Routed.

    ``bounds`` (x0, y0, x1, y1) limits the search; default: the factory frame plus ``margin``
    tiles east and south (the frame starts at 0, 0)."""
    js = jobs(flat, lay, cat)
    have = {e.owner[1:] for e in lay.entities.values() if e.owner.startswith("~")}
    kept = sorted(n for n in js if n in have)
    todo = [n for n in js if n not in have and js[n].skip is None]
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
            got, why = _route_one(cat, js[net], ents, frames, js, box, limit)
            if got is None:
                failed[net] = why
                continue
            added[net] = got
            how[net] = why
            ents += got
        score = (len(added), -attempt)
        if best is None or score > best[0]:
            best = (score, added, failed, how, attempt + 1)
        if not failed:
            break
        order = [n for n in order if n in failed] + [n for n in order if n not in failed]
    _score, added, failed, how, passes = best
    new = fkpmod.Layout(lay.level, lay.name, lay.size, dict(lay.insts), dict(lay.covers),
                        dict(lay.plots), dict(lay.claims), dict(lay.marks), dict(lay.entities))
    for net in todo:
        for e in added.get(net, ()):
            new.add(e)
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
        elif net in added:
            lines.append(f"routed    {net}: {len(job.starts)} -> {job.consumers()}, {how[net]}")
        else:
            lines.append(f"FAILED    {net}: {failed.get(net)}")
    return Routed(new, lines, sorted(added), failed, kept, passes)
