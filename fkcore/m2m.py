"""fkcore.m2m: the many-to-many router, version 1 (the baseline of DESIGN-M2M.md; ``route --m2m``).

Rory, 2026-10-31: no trunk rule and no pinch point. The constraints are lane reach (every producer
reaches every consumer), capacity (a max-flow, one lane a run) and the ground; the objective is
belt cost. A net with two or more drivers and two or more consumers whose flow is above one lane
(or whose ``width`` above 2 asks for that many lanes) is laid here, when the route step is given
``--m2m``; every other net routes as before.

1. **The hub, without side-loads** (``fkcore.route._hub_search``): every driver merges into a
   trunk at splitters and inserter drops, the trunk splits to every consumer. Reach holds from
   the start. A driver's inserter stands on the belt's right, looking downstream, so it drops on
   the left lane (``LeftTap``); if no hub routes that way, the hub's own taps are kept.
2. **Measure** (``fkcore.maxflow``): the max-flow over the net's runs and splitters, one lane a
   run, against the demand; and the two sides of the cut where it binds.
3. **Augment** while it falls short: one A* (steiner's own step, ``_astar``) from every start at
   once to every target at once: a start is a straight belt of the net upstream of the cut (it
   becomes a splitter; the new run leaves from its spare half) or a driver with items to spare
   (a new inserter drops onto the run's first belt, on the run's right); a target is a straight
   belt downstream of the cut (it becomes a merge splitter; the run feeds its spare half) or a
   consumer that can take more (a new inserter picks from the run). A run is kept only when the
   max-flow rises. Adding runs never removes a path, so reach still holds.
4. **Improve**: each added run that no later run leans on is ripped up and searched again (or
   dropped, when the rest meets the demand without it) while that lowers the cost.

No grouping rule: which drivers share a run comes out of the search. A net whose flow fits a lane
is not laid here. Out of version 1: side-loads, both lanes, lane balancing, and the even split of
a splitter (a real network can carry less than its max-flow). Pure, stdlib only, deterministic.
"""
from __future__ import annotations

import math
import time

from . import fkp as fkpmod
from . import maxflow as mfmod
from .steiner import COSTS, DX, DY, FixedSink, TapSink, Tree, _astar

__all__ = ["LeftTap", "route", "spec_of", "report"]

_RUNS = 24         # runs added at most
_TRIES = 6         # searches per run when a found run overlaps its own start or end
_ROUNDS = 3        # improve rounds
_BELT_NAMES = ("transport-belt", "underground-belt", "splitter")


class LeftTap(TapSink):
    """A driver machine's tap on a tree laid reversed (the hub's merge tree): the inserter stands
    on the belt's right, looking downstream, so it drops on the left lane. Reversed, a state
    heading ``d`` is a belt running ``d + 2``, whose right is ``d + 3``."""

    def pick(self, path, tree, taken=()):
        on = {(s[0], s[1]) for s in path}
        tunnels = {path[i] for i in range(len(path) - 1) if path[i + 1][3]} \
            if tree.grid.drop_taps else ()
        got = []
        for s in reversed(path[-6:]):
            if s in tunnels:
                continue
            h = (s[2] + 3) % 4
            used = {g[0] for g in got}
            for name in self.inserters:
                r = 2 if name == "long-handed-inserter" else 1
                q = (s[0] + DX[h] * r, s[1] + DY[h] * r)
                if tree.free(q) and q not in on and q not in used and q not in taken and \
                        self.inside((q[0] + DX[h] * r, q[1] + DY[h] * r)):
                    got.append((q, name, ((h + 2) % 4) * 4, self.name))
                    break
            if len(got) >= self.k:
                break
        return got


class _EndTap(TapSink):
    """A consumer at the end of a new run: an inserter picks from it, and the run's last belt
    points into no belt (it would side-load its items there)."""

    def __init__(self, name, rect, inserters, belts):
        super().__init__(name, rect, 1, inserters)
        self.belts = belts

    def goal(self, state, tree, path=None, taken=()):
        x, y, d, _ex = state
        if (x + DX[d], y + DY[d]) in self.belts:
            return False
        return super().goal(state, tree, path, taken)


# -- the spec: what a net carries, per end -------------------------------------------------------
def spec_of(flat, cat, fn, job, lane):
    """{"supply", "take", "demand", "lanes"} of an m2m job: per driver end what it puts on (a
    machine's key, or ("start", tile) for a belt end), per consumer end what it takes (a machine's
    key, or ("goal", tile): one lane), the demand, and the lanes ``width`` asks for (None)."""
    from . import route as rt
    from .lanes import inserter_rate
    supply, take = {}, {}
    for entry, path in job.drv:
        key = entry[0] if isinstance(entry[0], str) else ("start", tuple(entry[0]))
        supply[key] = supply.get(key, 0.0) + rt._driver_rate(flat, fn, entry, path)
    for key, _rect in job.taps:
        m = flat.machines.get(key)
        r = inserter_rate("fast-inserter")
        if m is not None:
            mine = [m.needs[i] for i in fn.items if i in m.needs]
            if mine:
                r = sum(mine)
            elif m.drain is not None:
                r = m.drain
            elif m.extra.get("port"):
                r = lane
        take[key] = take.get(key, 0.0) + r
    for tile, _h in job.goals:
        take[("goal", tuple(tile))] = lane
    demand = min(sum(supply.values()), sum(take.values()), rt._flow(flat, fn))
    return {"supply": supply, "take": take, "demand": demand,
            "lanes": fn.width if fn.width > 2 else None}


# -- the net as laid: plan entities by id ---------------------------------------------------------
class _Run:
    """A laid run: its own entities by id, the belts it turned into splitters ({id: (old,
    new)}), its cost and its two ends."""

    def __init__(self, plans, swaps, cost, start, end):
        self.plans, self.swaps, self.cost, self.start, self.end = plans, swaps, cost, start, end

    @property
    def ids(self):
        return list(self.plans)


class _Net:
    """The net's plan entities (steiner's dicts) by id, with the carriers they make."""

    def __init__(self, cat, net, plan):
        self.cat, self.net = cat, net
        self.items, self.next = {}, 0
        for p in plan:
            self.add(p)

    def add(self, p):
        i = self.next
        self.next += 1
        self.items[i] = p
        return i

    def key(self, i):
        return f"~{self.net}/m{i}"

    def entity(self, i):
        p = self.items[i]
        attrs = {"net": self.net}
        if p.get("belt_to_ground_type"):
            attrs["ug"] = "in" if p["belt_to_ground_type"] == "input" else "out"
        x, y = p["x"], p["y"]
        return fkpmod.Entity(self.key(i), p["name"], _clean(x), _clean(y), int(p["direction"]),
                             attrs)

    def entities(self):
        return [self.entity(i) for i in sorted(self.items)]

    def plan(self):
        return [self.items[i] for i in sorted(self.items)]

    def at(self):
        """{tile: id} of every tile the net takes."""
        out = {}
        for i in sorted(self.items):
            for t in fkpmod.tiles_of(self.cat, self.entity(i)):
                out[t] = i
        return out

    def cost(self):
        c = 0.0
        for p in self.items.values():
            n = p["name"]
            c += {"transport-belt": COSTS["belt"], "underground-belt": COSTS["ug"] / 2,
                  "splitter": COSTS["split"]}.get(n, COSTS["long_tap"] if "long" in n
                                                  else COSTS["tap"])
        return round(c, 3)


def _clean(v):
    return int(v) if float(v).is_integer() else v


def _tile(p):
    return (math.floor(p["x"]), math.floor(p["y"]))


def _head(p):
    return int(p["direction"]) // 4 % 4


def _straights(net):
    """[(id, tile, heading)] of the net's belts a splitter may replace: a plain belt fed from
    behind by a carrier heading the same way, running on into one that takes from behind."""
    at = net.at()
    out = []
    for i in sorted(net.items):
        p = net.items[i]
        if p["name"] != "transport-belt":
            continue
        n, d = _tile(p), _head(p)
        b = at.get((n[0] - DX[d], n[1] - DY[d]))
        a = at.get((n[0] + DX[d], n[1] + DY[d]))
        if a is None or b is None:
            continue
        pb, pa = net.items[b], net.items[a]
        if pb["name"] not in _BELT_NAMES or _head(pb) != d or \
                pb.get("belt_to_ground_type") == "input":
            continue
        if pa["name"] not in _BELT_NAMES or _head(pa) != d or \
                pa.get("belt_to_ground_type") == "output":
            continue
        out.append((i, n, d))
    return out


def _splitter(n, m, d):
    return {"name": "splitter", "x": (n[0] + m[0]) / 2 + 0.5, "y": (n[1] + m[1]) / 2 + 0.5,
            "direction": d * 4, "role": "spine"}


def _belt(t, d, ug=None):
    p = {"name": "underground-belt" if ug else "transport-belt", "x": t[0] + 0.5,
         "y": t[1] + 0.5, "direction": d * 4, "role": "spine"}
    if ug:
        p["belt_to_ground_type"] = ug
    return p


def _path_plan(path, last_head):
    """Plan entities of a forward path (steiner states), its last belt heading ``last_head``."""
    out = []
    for j, s in enumerate(path):
        x, y, d, ex = s
        nxt = path[j + 1] if j + 1 < len(path) else None
        if nxt is not None and nxt[3]:
            out.append(_belt((x, y), d, "input"))
            continue
        if ex:
            out.append(_belt((x, y), d, "output"))
            continue
        out.append(_belt((x, y), nxt[2] if nxt is not None else last_head))
    return out


# -- the router -----------------------------------------------------------------------------------
class _Ctx:
    def __init__(self, cat, job, blocked, spans, clear, box, limit, ents, spec):
        self.cat, self.job, self.blocked, self.spans = cat, job, blocked, spans
        self.clear, self.box, self.limit, self.spec = clear, box, limit, spec
        keys = {k for k, _r in list(job.sources) + list(job.taps)}
        self.machines = [e for e in ents if e.key in keys]
        self.rects = {k: r for k, r in list(job.sources) + list(job.taps)}
        self.drivers = [k for k, _r in job.sources]
        self.consumers = [k for k, _r in job.taps]

    def flow(self, net, unbounded=False):
        at = net.at()
        supply, take = {}, {}
        for k, r in self.spec["supply"].items():
            key = net.key(at[k[1]]) if isinstance(k, tuple) and k[1] in at else k
            supply[key] = supply.get(key, 0.0) + r
        for k, r in self.spec["take"].items():
            key = net.key(at[k[1]]) if isinstance(k, tuple) and k[1] in at else k
            take[key] = take.get(key, 0.0) + r
        return mfmod.solve(net.entities() + self.machines, self.cat, supply, take,
                           demand=self.spec["demand"], unbounded=unbounded)

    def need(self, net):
        """(the flow to raise, unbounded?) or None when the net meets its demand and its lanes."""
        f = self.flow(net)
        if not f.met:
            return f, False
        if self.spec["lanes"]:
            u = self.flow(net, unbounded=True)
            if u.value < self.spec["lanes"] * u.lane - 1e-6:
                return u, True
        return None

    def grid(self, net):
        from . import route as rt
        at = net.at()
        mine = net.entities()
        fronts = set(rt._belt_fronts(self.cat, mine))
        spans = rt._ug_spans(self.cat, mine)
        g = rt._Bounded(set(self.blocked) | set(at) | fronts, self.box,
                        {a: set(self.spans[a]) | spans[a] for a in (0, 1)})
        return g, at

    def search(self, net, f, banned=()):
        """One new run from the source side of ``f``'s cut to its sink side, or None."""
        from . import route as rt
        grid, at = self.grid(net)
        anchor = next(iter(sorted(at)))
        tree = Tree(grid, (anchor[0], anchor[1], 0, 0))
        tree.sink_terminal = {}
        belts = set(self.clear) | set(at)
        k = COSTS
        starts, sinks, ends = [], [], []
        straights = _straights(net)
        for i, n, d in straights:
            if (net.key(i), 0) not in f.S:
                continue
            for side in (1, 3):
                sh = (d + side) % 4
                m = (n[0] + DX[sh], n[1] + DY[sh])
                o2 = (m[0] + DX[d], m[1] + DY[d])
                how = ("split", i, side)
                if how not in banned and tree.free(m) and tree.free(o2):
                    starts.append(((o2[0], o2[1], d, 0), k["split"] - k["belt"], how, (m,)))
        for key in self.drivers:
            if (key, 1) not in f.S:
                continue
            for q in rt._beside(grid, self.rects[key]):
                r = _away(self.rects[key], q)
                b = (q[0] + DX[r], q[1] + DY[r])
                h = (r + 1) % 4              # the inserter on the belt's right: the left lane
                c = (b[0] + DX[h], b[1] + DY[h])
                how = ("src", key, q, b, h, r)
                if how not in banned and tree.free(q) and tree.free(b) and tree.free(c):
                    starts.append(((c[0], c[1], h, 0), k["tap"] + k["belt"], how, (q, b)))
        hands = rt._HANDS[0]
        for i, n, d in straights:
            if (net.key(i), 1) not in f.T:
                continue
            for side in (1, 3):
                sh = (d + side) % 4
                m = (n[0] + DX[sh], n[1] + DY[sh])
                a = (m[0] - DX[d], m[1] - DY[d])
                spare = (m[0] + DX[d], m[1] + DY[d])
                if tree.free(m) and tree.free(a) and spare not in belts:
                    sinks.append(FixedSink(f"merge{i}.{side}", a, d))
                    ends.append(("merge", i, side, m))
        for key in self.consumers:
            if (key, 0) in f.T:
                sinks.append(_EndTap(key, self.rects[key], hands, belts))
                ends.append(("tap", key))
        if not starts or not sinks:
            return None, "no start or no target"
        targets = [j for j in range(len(sinks))]
        for _try in range(_TRIES):
            got = _astar(tree, starts, sinks, targets, self.limit)
            if got is None:
                return None, "no run reaches the sink side"
            path, how, j, gcost = got
            run = self._run(net, tree, path, how, sinks[j], ends[j], gcost)
            if run is not None:
                return run, None
            starts = [s for s in starts if s[2] != how]
            if not starts:
                break
        return None, "every run found overlaps its own ends"

    def _run(self, net, tree, path, how, sink, end, gcost):
        """The plan of a found run, checked: (adds, swaps, cost, start, end) or None when its
        start or end overlaps it."""
        adds, swaps, taken = [], [], set()
        tiles = [(s[0], s[1]) for s in path]
        if how[0] == "split":
            _k, i, side = how
            p = net.items[i]
            n, d = _tile(p), _head(p)
            sh = (d + side) % 4
            m = (n[0] + DX[sh], n[1] + DY[sh])
            swaps.append((i, _splitter(n, m, d)))
            taken |= {m}
        else:
            _k, key, q, b, h, r = how
            adds.append({"name": rt_hand(), "x": q[0] + 0.5, "y": q[1] + 0.5,
                         "direction": ((r + 2) % 4) * 4, "role": "ins"})
            adds.append(_belt(b, h))
            taken |= {q, b}
        cost = gcost
        if end[0] == "merge":
            _k, i, side, m = end
            if any(sw[0] == i for sw in swaps):
                return None
            p = net.items[i]
            n, d = _tile(p), _head(p)
            swaps.append((i, _splitter(n, m, d)))
            adds += _path_plan(path, d)
            taken |= {m}
            cost += COSTS["split"] - COSTS["belt"]
        else:
            got = sink.pick(path, tree, taken)
            if not got:
                return None
            adds += _path_plan(path, path[-1][2])
            for q, name, direction, _s in got:
                adds.append({"name": name, "x": q[0] + 0.5, "y": q[1] + 0.5,
                             "direction": direction, "role": "ins"})
                taken |= {q}
                cost += COSTS["tap"]
        if len(set(tiles)) != len(tiles) or set(tiles) & taken:
            return None
        return adds, swaps, round(cost, 3), how, end

    def lay(self, net, found):
        adds, swaps, cost, start, end = found
        plans = {net.add(p): p for p in adds}
        sw = {}
        for i, p in swaps:
            sw[i] = (net.items[i], p)
            net.items[i] = p
        return _Run(plans, sw, cost, start, end)

    def rip(self, net, run):
        for i in run.plans:
            net.items.pop(i, None)
        for i, (old, _new) in run.swaps.items():
            net.items[i] = old

    def relay(self, net, run):
        """Put a ripped run back as it was (the same ids)."""
        for i, p in run.plans.items():
            net.items[i] = p
        for i, (_old, new) in run.swaps.items():
            net.items[i] = new


def rt_hand():
    from . import route as rt
    return rt._HANDS[0][0]


def _away(rect, q):
    """The heading from a machine's rectangle out to the tile ``q`` beside it."""
    x0, y0, x1, y1 = rect
    if q[1] < y0:
        return 0
    if q[0] >= x1:
        return 1
    if q[1] >= y1:
        return 2
    return 3


def route(cat, job, blocked, spans, clear, box, limit, ents):
    """An m2m job's plan: the hub without side-loads, then augmenting runs, then improved.
    -> (plan entities, report text) or (None, reason)."""
    from . import route as rt
    from .lanes import inserter_rate
    t0 = time.time()
    slow = inserter_rate("long-handed-inserter")
    rate = job.m2m["supply"]

    def tap(key, rect, k, hands):
        # a driver that makes more than a long-handed inserter moves gets a fast one
        if rate.get(key, 0.0) > slow + 1e-9:
            hands = tuple(h for h in hands if h != "long-handed-inserter") or hands
        return LeftTap(key, rect, k, hands)

    plan, how = rt._hub_search(cat, job, blocked, spans, clear, box, limit, tap=tap)
    left = True
    if plan is None:
        plan, how = rt._hub_search(cat, job, blocked, spans, clear, box, limit)
        left = False
        if plan is None:
            return None, how
    hub = how.rsplit(", hub ", 1)[-1] if ", hub " in how else "?"
    ctx = _Ctx(cat, job, blocked, spans, clear, box, limit, ents, job.m2m)
    net = _Net(cat, job.net, plan)
    runs, why, before = [], None, ctx.flow(net)
    for _n in range(_RUNS):
        want = ctx.need(net)
        if want is None:
            break
        f, unb = want
        found, why = ctx.search(net, f)
        if found is None:
            break
        run = ctx.lay(net, found)
        g = ctx.flow(net, unbounded=unb)
        if g.value <= f.value + 1e-6:
            ctx.rip(net, run)
            why = "a run that raises the flow was not found"
            break
        runs.append(run)
    _improve(ctx, net, runs)
    after = ctx.flow(net)
    c = {"transport-belt": 0, "underground-belt": 0, "splitter": 0, "ins": 0}
    for p in net.items.values():
        c[p["name"] if p["name"] in c else "ins"] += 1
    text = (f"{c['transport-belt']} belts, {c['underground-belt']} underground ends, "
            f"{c['splitter']} splitters, {c['ins']} inserters, hub {hub}; m2m: "
            f"{len(runs)} run{'s' if len(runs) != 1 else ''} added, max-flow "
            f"{_num(before.value)} -> {_num(after.value)} of {_num(after.demand)}/s"
            + ("" if left else "; drivers on either lane (no hub with left-lane taps)")
            + (f"; short: {why}" if not after.met and why else "")
            + f" ({time.time() - t0:.1f} s)")
    return net.plan(), text


def report(cat, job, laid, ents):
    """The ``MAXFLOW`` line of an m2m net as laid (``laid``: its carriers; ``ents``: the layout)
    -> (line, why it falls short or None)."""
    keys = {k for k, _r in list(job.sources) + list(job.taps)}
    machines = [e for e in ents if e.key in keys]
    at = {}
    for e in laid:
        if e.name in _BELT_NAMES:
            for t in fkpmod.tiles_of(cat, e):
                at[t] = e.key
    spec = job.m2m

    def keyed(table):
        out = {}
        for k, r in table.items():
            key = at.get(k[1], k) if isinstance(k, tuple) else k
            out[key] = out.get(key, 0.0) + r
        return out

    supply, take = keyed(spec["supply"]), keyed(spec["take"])
    f = mfmod.solve(list(laid) + machines, cat, supply, take, demand=spec["demand"])
    u = mfmod.solve(list(laid) + machines, cat, supply, take, unbounded=True)
    lanes = u.value / u.lane if u.lane and u.value != float("inf") else 0.0
    text = (f"MAXFLOW   {job.net}: {_num(f.value)} of {_num(f.demand)}/s, the narrowest cut "
            f"{lanes:g} lane{'s' if lanes != 1 else ''}")
    short = None
    if not f.met:
        short = (f"its laid carriers move {_num(f.value)} of the {_num(f.demand)}/s its drivers "
                 f"and consumers ask, short {_num(f.short)}/s; the cut binds at "
                 + ", ".join(f.cut[:6]) + (" ..." if len(f.cut) > 6 else ""))
        text += f"; short {_num(f.short)}/s at " + ", ".join(f.cut[:4]) + \
            (" ..." if len(f.cut) > 4 else "")
    if spec["lanes"] and lanes < spec["lanes"] - 1e-6:
        why = f"width {spec['lanes']} asks for {spec['lanes']} lanes, the narrowest cut has " \
              f"{lanes:g}"
        short = f"{short}; {why}" if short else why
        text += f"; {why}"
    return text, short


def _num(v):
    return f"{v:.1f}" if v != float("inf") else "inf"


def _improve(ctx, net, runs):
    """Rip up each added run no other run leans on (none split or merged on its belts) and
    search it again, or drop it when the rest meets the demand without it, while that lowers
    the cost; the flow never drops below what it was."""
    for _round in range(_ROUNDS):
        better = False
        for idx in range(len(runs) - 1, -1, -1):
            run = runs[idx]
            mine = set(run.plans)
            if any(o is not run and mine & set(o.swaps) for o in runs if o is not None):
                continue
            was = ctx.flow(net).value, (ctx.flow(net, unbounded=True).value
                                        if ctx.spec["lanes"] else 0.0)
            ctx.rip(net, run)
            want = ctx.need(net)
            if want is None:
                runs[idx] = None             # the rest meets the demand without it
                better = True
                continue
            found, _why = ctx.search(net, want[0])
            if found is not None and found[2] < run.cost - 1e-9:
                new = ctx.lay(net, found)
                now = ctx.flow(net).value, (ctx.flow(net, unbounded=True).value
                                            if ctx.spec["lanes"] else 0.0)
                if now[0] >= was[0] - 1e-6 and now[1] >= was[1] - 1e-6:
                    runs[idx] = new
                    better = True
                    continue
                ctx.rip(net, new)
            ctx.relay(net, run)
        runs[:] = [r for r in runs if r is not None]
        if not better:
            break
