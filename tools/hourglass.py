"""hourglass: the many-to-many router's bench (DESIGN-M2M.md, "The main test case"). Stdlib only.

    python tools/hourglass.py [--today] [--balancer] [--draw] [--lines] [--only NAME[,NAME]]

A column of producers on the left, a column of consumers on the right, a gap between them, one net
from every producer to every consumer. A producer is a requester chest at a rate (it puts its
items on the net's belt by an inserter), a consumer a provider chest at a rate (it takes them off by
one). Everything is generated here, offline: no game, no committed file.

Per case it prints one row: the net's flow (demand), the max-flow of what was laid, one lane a run
(``fkcore.maxflow``), reach (``fkcore.connect``'s verdict: every producer reaches every consumer, no
SPILL), the waist (the runs crossing the vertical line midway between the columns, and the fewest
across any vertical line of the gap), belts, underground ends, splitters, inserters, the runs the
router added, its belt cost (steiner's costs) and the route time. ``--today`` adds a row per case
routed without ``--m2m`` (the router as it was: one trunk, both lanes by a side-load above one
lane), its max-flow counted on both lanes. ``--balancer`` adds a row per case laid through a
balancer at the waist (``lay_balancer``: Rory's layers of splitters alternating by one).

Keep the table as it is printed: later versions of the router are compared on it.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from fkcore import connect, expand, lang, maxflow, route        # noqa: E402
from fkcore.catalog import Catalog                               # noqa: E402
from fkcore.elaborate import elaborate                           # noqa: E402
from fkcore.steiner import COSTS                                 # noqa: E402

NET = "plates"
SPACING = 2          # tiles between one producer (or consumer) and the next
GAP = 20             # tiles from the producer column to the consumer column
MARGIN = 8           # free tiles around the two columns

#: name -> (producer rates, consumer count, wall); the consumers share the total evenly
CASES = {
    "8to8": ([0.8] * 8, 8, None),
    "16to16": ([1.4] * 16, 16, None),
    "16to4": ([0.55] * 16, 4, None),
    "4to16": ([2.2] * 4, 16, None),
    "uneven": ([2.4, 2.0, 1.6, 1.2, 0.8, 0.4, 0.4, 0.4], 8, None),
    "wall": ([1.0] * 12, 12, "gap"),
}


def source(rates, consumers, gap=GAP):
    """The .fk text of a case: producers p<i> down x=0, consumers c<j> down x=gap."""
    total = sum(rates)
    each = round(total / consumers, 4)
    lines = []
    for i, r in enumerate(rates):
        lines.append(f"p{i} = Chest<requester, item=iron-plate, rate={r:g}/s> @(0, {i * SPACING})")
    for j in range(consumers):
        lines.append(f"c{j} = Chest<provider, rate={each:g}/s> @({gap}, {j * SPACING})")
    lines.append(f"net {NET}: " + ", ".join(f"p{i}" for i in range(len(rates))) + " -> "
                 + ", ".join(f"c{j}" for j in range(consumers)))
    return "\n".join(lines) + "\n"


def build(name, cat, gap=GAP):
    """(flat, layout, bounds, blocked tiles, midline x) of a case."""
    rates, consumers, wall = CASES[name]
    f = lang.parse(source(rates, consumers, gap), f"{name}.fk")
    flat = elaborate(f, dict(f.modules), cat, name)
    lay, _notes = expand.expand_factory(flat, cat)
    height = max(len(rates), consumers) * SPACING
    bounds = (-MARGIN, -MARGIN, gap + 1 + MARGIN, height + MARGIN)
    mid = gap // 2                     # the line between tile columns mid and mid + 1
    blocked = set()
    if wall:
        # a wall three tiles thick across the whole gap's height, with one free tile in the middle
        hole = (height // 2) - 1
        for x in (mid - 1, mid, mid + 1):
            for y in range(bounds[1], bounds[3]):
                if y != hole:
                    blocked.add((x, y))
    return flat, lay, bounds, blocked, mid


def _crossing(g, nodes, x):
    """Edges of the net's carriers that cross the vertical line between tile columns x and x+1."""
    n = 0
    for a in nodes:
        for b, via in g.succ.get(a, ()):
            if b not in nodes or via not in ("belt", "curve", "sideload", "ug"):
                continue
            xa = [t[0] for t in g.nodes[a].tiles]
            xb = [t[0] for t in g.nodes[b].tiles]
            if (max(xa) <= x < min(xb)) or (max(xb) <= x < min(xa)):
                n += 1
    return n


def measure(name, cat, m2m=True, gap=GAP, router=None):
    """One row of the table, as a dict. ``router``: "m2m" (default with ``m2m``), "today" or
    "balancer" (``lay_balancer``)."""
    router = router or ("m2m" if m2m else "today")
    flat, lay, bounds, blocked, mid = build(name, cat, gap)
    t0 = time.time()
    if router == "balancer":
        r = lay_balancer(flat, lay, cat, bounds, blocked, mid)
    else:
        r = route.route_layout(flat, lay, cat, bounds=bounds, blocked=sorted(blocked),
                               m2m=router == "m2m")
    secs = time.time() - t0
    ends = {n: tuple(v) for n, v in connect.endpoints(flat).items()}      # every pair, not dealt
    rep = connect.connect(r.layout, cat, ends)
    nr = rep.nets.get(NET)
    reach = bool(nr and nr.connected and not nr.leaks)
    mine = [e for e in r.layout.entities.values() if e.owner == f"~{NET}"]
    flow = maxflow.of_net(flat, r.layout, cat, NET)
    if router == "today":
        # the router as it was may put the net on both lanes: count both
        from fkcore import lanes as lanesmod
        supply, take = maxflow.rates_of(flat, NET)
        lg_ents = mine + [r.layout.entities[k] for k in set(supply) | set(take)]
        flow = _two_lane(lanesmod, lg_ents, cat, supply, take, flow.demand)
    keys = {e.key for e in mine}
    g = rep.graph
    waist = _crossing(g, keys, mid)
    # the fewest runs across any line of the gap, clear of the two columns' inserters and belts
    narrow = min(_crossing(g, keys, x) for x in range(3, gap - 3))
    count = {"transport-belt": 0, "underground-belt": 0, "splitter": 0, "inserter": 0}
    for e in mine:
        count[e.name if e.name in count else "inserter"] += 1
    cost = (count["transport-belt"] * COSTS["belt"] + count["underground-belt"] / 2 * COSTS["ug"]
            + count["splitter"] * COSTS["split"] + count["inserter"] * COSTS["tap"])
    rates, consumers, _wall = CASES[name]
    how = next((ln for ln in r.lines if ln.startswith(("routed", "FAILED")) and f" {NET}:" in ln),
               "")
    runs = 0
    if "m2m: " in how:
        runs = int(how.split("m2m: ", 1)[1].split()[0])
    if router == "balancer":
        runs = r.width                       # the balancer's belts
    return {"case": name, "router": router, "pc": f"{len(rates)}->{consumers}",
            "demand": flow.demand, "maxflow": flow.value, "reach": reach,
            "failed": NET in r.failed, "waist": waist, "narrow": narrow,
            "belts": count["transport-belt"], "ug": count["underground-belt"],
            "splitters": count["splitter"], "inserters": count["inserter"], "runs": runs,
            "cost": round(cost, 1), "secs": round(secs, 1), "line": how, "lines": r.lines,
            "layout": r.layout, "flat": flat}


# -- the balancer comparison -----------------------------------------------------------------------
def balancer_plan(n, x0, y0, layers=None):
    """A balancer of ``n`` belts heading east, belt k on row y0 + k (Rory, 2026-10-31): an input
    column at x0, then ``layers`` columns of splitters alternating by one, the first pairing belts
    (0, 1), (2, 3) ..., the next (1, 2), (3, 4) ..., then an output column. Default n - 1 layers.
    -> (plan entities, input tiles, output tiles)."""
    layers = n - 1 if layers is None else layers

    def belt(x, y):
        return {"name": "transport-belt", "x": x + 0.5, "y": y + 0.5, "direction": 4}

    plan = [belt(x0, y0 + k) for k in range(n)]
    for j in range(layers):
        x, paired = x0 + 1 + j, set()
        for a in range(j % 2, n - 1, 2):
            plan.append({"name": "splitter", "x": x + 0.5, "y": y0 + a + 1.0, "direction": 4})
            paired |= {a, a + 1}
        plan += [belt(x, y0 + k) for k in range(n) if k not in paired]
    xo = x0 + 1 + layers
    plan += [belt(xo, y0 + k) for k in range(n)]
    return plan, [(x0, y0 + k) for k in range(n)], [(xo, y0 + k) for k in range(n)]


def balancer_reach(n, layers=None):
    """{input: outputs it reaches} through ``balancer_plan``'s splitters alone."""
    layers = n - 1 if layers is None else layers
    out = {}
    for i in range(n):
        at = {i}
        for j in range(layers):
            nxt = set(at)
            for a in range(j % 2, n - 1, 2):
                if a in at or a + 1 in at:
                    nxt |= {a, a + 1}
            at = nxt
        out[i] = at
    return out


def balancer_layers(n):
    """The fewest layers of ``balancer_plan`` that join every input to every output: n - 1 for an
    even n; an odd n needs n (with n - 1 its last input never meets the first layer's pairs)."""
    for layers in range(max(0, n - 1), n + 2):
        if all(len(v) == n for v in balancer_reach(n, layers).values()):
            return layers
    return n


def _groups(rates, n=None, cap=7.5):
    """``rates`` (in column order) in contiguous groups, each at most ``cap``: the fewest, or
    exactly ``n``, balanced (the largest group as small as it can be). -> [[index]] or None."""
    m = len(rates)
    want = range(1, m + 1) if n is None else [n]
    for k in want:
        if k > m:
            return None
        # best[i][j]: the smallest max group sum splitting the first i into j groups
        best = [[float("inf")] * (k + 1) for _ in range(m + 1)]
        cut = [[0] * (k + 1) for _ in range(m + 1)]
        best[0][0] = 0.0
        for i in range(1, m + 1):
            for j in range(1, min(i, k) + 1):
                for s in range(j - 1, i):
                    v = max(best[s][j - 1], sum(rates[s:i]))
                    if v < best[i][j]:
                        best[i][j], cut[i][j] = v, s
        if best[m][k] <= cap + 1e-9:
            out, i = [], m
            for j in range(k, 0, -1):
                s = cut[i][j]
                out.append(list(range(s, i)))
                i = s
            return out[::-1]
    return None


class _Laid:
    def __init__(self, layout, lines, failed, width):
        self.layout, self.lines, self.failed, self.width = layout, lines, failed, width


def lay_balancer(flat, lay, cat, bounds, blocked, mid, limit=60000):
    """The comparison: a balancer of n belts (``balancer_plan``, ``balancer_layers``) laid across
    the waist, n the fewest contiguous producer groups (and consumer groups) of a lane each; each
    producer group merged into one input by a tree laid reversed, each output split to one
    consumer group by a tree. Producers drop on the left lane. Grouping by position, as a
    balancer is fed: the thing the m2m router doesn't need."""
    from fkcore import fkp, m2m as m2mmod
    supply, take = maxflow.rates_of(flat, NET)
    pk = sorted(supply, key=lambda k: lay.entities[k].y)
    ck = sorted(take, key=lambda k: lay.entities[k].y)
    pg, cg = _groups([supply[k] for k in pk]), _groups([take[k] for k in ck])
    if pg is None or cg is None:
        return _Laid(lay.copy(), [f"FAILED    {NET}: a producer or consumer above a lane"],
                     {NET: "above a lane"}, 0)
    n = max(len(pg), len(cg))
    pg, cg = _groups([supply[k] for k in pk], n), _groups([take[k] for k in ck], n)
    layers = balancer_layers(n)
    length = layers + 2
    ys = [e.y for e in lay.entities.values()]
    y0 = int((min(ys) + max(ys)) / 2) - n // 2
    x0 = mid - length // 2
    while any((x, y0 + k) in blocked for x in range(x0 - 1, x0 + length + 1)
              for k in range(n)) and x0 > bounds[0] + 2:
        x0 -= 1                                    # off the wall, towards the producers
    plan, ins, outs = balancer_plan(n, x0, y0, layers)
    ents, count = [], [0]

    def keyed(plans):
        out = []
        for p in plans:
            letter = {"transport-belt": "b", "underground-belt": "u",
                      "splitter": "s"}.get(p["name"], "i")
            attrs = {"net": NET}
            if p.get("belt_to_ground_type"):
                attrs["ug"] = "in" if p["belt_to_ground_type"] == "input" else "out"
            x, y = p["x"], p["y"]
            out.append(fkp.Entity(f"~{NET}/{letter}{count[0]}", p["name"],
                                  int(x) if float(x).is_integer() else x,
                                  int(y) if float(y).is_integer() else y,
                                  int(p["direction"]), attrs))
            count[0] += 1
        return out

    frame = keyed(plan)
    goals = [(x - 1, y) for x, y in ins]           # the tile behind each input belt, heading E
    starts = [(x + 1, y) for x, y in outs]          # the tile each output belt points into
    base = set(blocked)
    for e in lay.entities.values():
        base |= fkp.tiles_of(cat, e)
    lines, failed = [], {}
    jobs = [("in", k, goals[k], [(key, _rect(cat, lay.entities[key])) for key in
                                  (pk[i] for i in pg[k])]) for k in range(n)]
    jobs += [("out", k, starts[k], [(key, _rect(cat, lay.entities[key])) for key in
                                    (ck[i] for i in cg[k])]) for k in range(n)]
    # the trees one at a time, each on the ground the ones before left; a tree that finds no way
    # moves to the front and the pass starts again, as the router does with its nets
    for _pass in range(len(jobs)):
        ents, failed = list(frame), {}
        for job in jobs:
            side, k, tile, machines = job
            own = set(goals) | set(starts)
            occ = base | {t for e in ents for t in fkp.tiles_of(cat, e)} | \
                (set(route._belt_fronts(cat, ents)) | own) - {tile}
            spans = route._ug_spans(cat, ents)
            reverse = side == "in"
            clear = route._belt_tiles(cat, ents)
            grid = route._Bounded(occ, bounds, spans, clear if reverse else None)
            root = (tile[0], tile[1], 3 if reverse else 1, 0)
            res, sinks = route._grow(grid, root, [], machines, limit, sources=reverse,
                                     tap=m2mmod.LeftTap if reverse else route.TapSink)
            if res["problems"]:
                failed[NET] = f"{side} {k}: " + "; ".join(res["problems"][:2])
                jobs = [job] + [j for j in jobs if j is not job]
                break
            ents += keyed(res["tree"].entities(sinks, net=NET, reverse=reverse))
        if not failed:
            break
    new = lay.copy()
    for e in ents:
        new.add(e)
    c = {"transport-belt": 0, "splitter": 0}
    for e in ents:
        if e.name in c:
            c[e.name] += 1
    lines.append((f"FAILED    {NET}: {failed[NET]}; " if failed else f"routed    {NET}: ")
                 + f"balancer of {n} belts, {layers} layers, {c['splitter']} splitters")
    return _Laid(new, lines, failed, n)


def _rect(cat, e):
    from fkcore import fkp
    ts = fkp.tiles_of(cat, e)
    return (min(t[0] for t in ts), min(t[1] for t in ts), max(t[0] for t in ts) + 1,
            max(t[1] for t in ts) + 1)


def _two_lane(lanesmod, ents, cat, supply, take, demand):
    """The max-flow on both lanes of every carrier (the lane graph as it is)."""
    lg = lanesmod.build(ents, cat)
    from collections import deque
    res, adj = {}, {}

    def link(u, v, c):
        if (u, v) not in res:
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, []).append(u)
            res[(u, v)] = 0.0
            res.setdefault((v, u), 0.0)
        res[(u, v)] += c

    for nid, n in lg.nodes.items():
        link((nid, 0), (nid, 1), min(n.cap, 1e9))
    for e in lg.edges():
        link((e.src, 1), (e.dst, 0), min(e.cap, 1e9))
    for k, v in supply.items():
        if (k, "") in lg.nodes:
            link("S", ((k, ""), 0), v)
    for k, v in take.items():
        if (k, "") in lg.nodes:
            link(((k, ""), 1), "T", v)
    total = 0.0
    while True:
        par, todo = {"S": None}, deque(["S"])
        while todo and "T" not in par:
            u = todo.popleft()
            for v in adj.get(u, ()):
                if v not in par and res[(u, v)] > 1e-9:
                    par[v] = u
                    todo.append(v)
        if "T" not in par:
            break
        push, v = float("inf"), "T"
        while par[v] is not None:
            push = min(push, res[(par[v], v)])
            v = par[v]
        v = "T"
        while par[v] is not None:
            res[(par[v], v)] -= push
            res[(v, par[v])] += push
            v = par[v]
        total += push
    return maxflow.Flow(total, demand, 7.5)


def draw(m, cat):
    """The case as laid, in text: belts ^ > v <, splitters S, underground ends U (in) and u
    (out), inserters i, producers P, consumers C, the wall #, the midline : where it is free."""
    from fkcore import fkp
    lay = m["layout"]
    _f, _l, bounds, blocked, mid = build(m["case"], cat)
    grid = {}
    for e in lay.entities.values():
        for t in fkp.tiles_of(cat, e):
            if e.name == "transport-belt":
                c = "^>v<"[int(e.dir or 0) // 4]
            elif e.name == "underground-belt":
                c = "U" if e.attrs.get("ug") == "in" else "u"
            elif e.name == "splitter":
                c = "S"
            elif "inserter" in e.name:
                c = "i"
            elif e.key.startswith("p"):
                c = "P"
            else:
                c = "C"
            grid[t] = c
    rows = []
    for y in range(bounds[1], bounds[3]):
        rows.append("".join(grid.get((x, y), "#" if (x, y) in blocked else
                                      ":" if x == mid else ".")
                            for x in range(bounds[0], bounds[2])))
    return "\n".join(rows)


HEAD = ("case", "router", "P->C", "demand", "maxflow", "reach", "waist", "narrow", "belts", "ug",
        "splitters", "inserters", "runs", "cost", "secs")


def row(m):
    return (m["case"], m["router"], m["pc"], f"{m['demand']:.1f}", f"{m['maxflow']:.1f}",
            ("FAILED" if m["failed"] else "yes" if m["reach"] else "NO"), str(m["waist"]),
            str(m["narrow"]), str(m["belts"]), str(m["ug"]), str(m["splitters"]),
            str(m["inserters"]), str(m["runs"]), f"{m['cost']:.1f}", f"{m['secs']:.1f}")


def table(rows):
    cells = [HEAD] + [row(m) for m in rows]
    w = [max(len(c[i]) for c in cells) for i in range(len(HEAD))]
    out = []
    for k, c in enumerate(cells):
        out.append("  ".join(s.rjust(w[i]) if i >= 2 else s.ljust(w[i]) for i, s in enumerate(c)))
        if k == 0:
            out.append("  ".join("-" * x for x in w))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", default="", help="case names, comma separated")
    ap.add_argument("--today", action="store_true", help="also route each case without --m2m")
    ap.add_argument("--balancer", action="store_true",
                    help="also lay each case through a balancer at the waist")
    ap.add_argument("--gap", type=int, default=GAP)
    ap.add_argument("--lines", action="store_true", help="print each case's route lines")
    ap.add_argument("--draw", action="store_true", help="draw each case as laid")
    a = ap.parse_args(argv)
    cat = Catalog.load()
    names = [n for n in CASES if not a.only or n in a.only.split(",")]
    rows = []
    for name in names:
        routers = ["m2m"] + (["today"] if a.today else []) + (["balancer"] if a.balancer else [])
        for router in routers:
            m = measure(name, cat, gap=a.gap, router=router)
            rows.append(m)
            if a.lines:
                print(f"-- {name} ({m['router']})")
                for ln in m["lines"]:
                    print("  " + ln)
            if a.draw:
                print(f"-- {name} ({m['router']}), the midline at x={build(name, cat)[4]}.5")
                print(draw(m, cat))
    print(table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
