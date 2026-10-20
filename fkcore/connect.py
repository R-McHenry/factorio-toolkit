"""fkcore.connect: the directed carrier graph of a layout, and per net: connected yes/no, LEAK.

:func:`graph` takes an entity list (a factory :class:`fkcore.fkp.Layout`, a composed
:class:`fkcore.compose.Surface`, or any entities with key, name, x, y, dir, attrs) and the catalog.
Every entity is a node; an edge is one way items move from one entity into another:

- ``belt``: a belt, an underground output or a splitter half moves items onto the tile ahead. A
  transport belt there takes them unless it faces back (head-on), an underground input only from
  behind, a splitter only from behind.
- ``curve`` / ``sideload``: the same into the side of a belt. A curve when it is that belt's only
  input (nothing from behind), else a side-load; into an underground's side, a side-load.
- ``ug``: an underground input to the output the game pairs it with. Both ends face the flow. The
  input looks ahead, up to the prototype's ``max_distance`` (catalog), through any other entity;
  the first underground of the same name facing the same way decides: an output pairs, anything
  else leaves it alone (v4's rule, C:\\fk-lead\\repo\\fk\\sight\\flow.py d6018d3).
- ``pickup`` / ``drop``: an inserter faces the side it picks from (v4 convention) and reaches one
  tile, a long-handed one two (geometry from fk\\lanes.py). It picks from a belt, an underground, a
  splitter or a machine, and drops onto the same, except an underground output: its edge is no
  belt surface (v4 B-120).
- ``mine``: a mining drill drops just past its front edge (the game's vector_to_place_result:
  centred, half a tile to its left on an even width) onto a carrier or straight into a machine.

A **carrier** (belt, underground, splitter, inserter, pipe ..., or anything with ``net=``) belongs
to one net; a **machine** (assembler, furnace, drill, lab, chest ...) is an endpoint, reached but
never passed through. On a surface a carrier's net is ``<factory>/<net>``: nets never leave their
factory.

:func:`connect` checks every net (CORE-V1.md §4.5). Its drivers and consumers are the netlist's
endpoints (:func:`endpoints`) or, without a netlist, the machines its carriers pick from and drop
into. A net is **connected** when every driver reaches every consumer through the net's own
carriers. Report lines (``elaborate.Check``), never raised: ``UNROUTED`` (no driver reaches a
consumer), ``OPEN`` (some pairs connect, not all), ``LEAK`` (an edge from one net's carrier into
another net's: a belt or side-load feeding another net's belt, an inserter picking from another
net's belt, an underground the game pairs with another net's; with a netlist also a carrier
moving items into a machine that is not its net's consumer, or out of one that is not its
driver). Pipes are carriers without edges so far. Pure, stdlib only, deterministic.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from .elaborate import Check
from .fkp import CARRIER_TYPES, natural_key

__all__ = ["Node", "Graph", "Leak", "NetReport", "Report", "graph", "connect", "endpoints",
           "HOLDER_TYPES", "REACH"]

_STEP = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}
_BELTS = frozenset({"transport-belt", "underground-belt", "splitter"})
_FLUID = frozenset({"pipe", "pipe-to-ground", "pump"})
#: Entity types an inserter drops into or picks from: the machine endpoints.
HOLDER_TYPES = frozenset({"assembling-machine", "furnace", "mining-drill", "lab", "container",
                          "logistic-container", "boiler", "reactor", "ammo-turret", "roboport"})
#: Tiles from an inserter to its pickup and drop tile; every other inserter reaches 1.
REACH = {"long-handed-inserter": 2}
_FLUID_DRILLS = frozenset({"pumpjack"})
_UG_REACH = 5                      # a tier the catalog gives no max_distance
_SHOW = 4
_VERB = {"belt": "feeds", "curve": "feeds", "sideload": "side-loads onto",
         "ug": "pairs underground with", "drop": "drops onto", "mine": "drops onto"}


@dataclass
class Node:
    key: str
    name: str
    kind: str                      # the prototype's entity type
    net: str | None                # on a surface: <factory>/<net>
    x: float
    y: float
    dir: int                       # 0..15, N = 0; no direction counts as north
    tiles: tuple
    ug: str | None = None          # "in" | "out" for an underground end

    @property
    def carrier(self):
        return self.kind in CARRIER_TYPES or self.net is not None


@dataclass
class Graph:
    nodes: dict = field(default_factory=dict)       # key -> Node, natural key order
    at: dict = field(default_factory=dict)          # (x, y) -> key
    succ: dict = field(default_factory=dict)        # key -> [(key, via)]
    pred: dict = field(default_factory=dict)        # key -> [(key, via)]
    pairs: dict = field(default_factory=dict)       # underground end -> its partner, both ways
    problems: list = field(default_factory=list)    # entities the graph could not place

    @property
    def unpaired(self):
        return [k for k, n in self.nodes.items() if n.kind == "underground-belt"
                and k not in self.pairs]

    def edges(self):
        """Every edge as (from, to, via), in natural key order."""
        for a in self.nodes:
            for b, via in self.succ.get(a, ()):
                yield a, b, via

    def reach(self, starts, net, forward=True):
        """Every node reached from ``starts`` along the edges (against them when not
        ``forward``), passing only through carriers of ``net``; a machine is reached, never
        passed through."""
        adj = self.succ if forward else self.pred
        seen = set(starts)
        todo = deque(sorted(seen, key=natural_key))
        while todo:
            for k, _via in adj.get(todo.popleft(), ()):
                n = self.nodes[k]
                if k in seen or (n.carrier and n.net != net):
                    continue
                seen.add(k)
                if n.carrier:
                    todo.append(k)
        return seen

    def inserter_tiles(self, key):
        """(pickup tile, drop tile) of an inserter, or None when it faces no cardinal."""
        return _hand(self.nodes[key])


@dataclass
class Leak:
    net: str | None                # the net whose items escape
    src: str
    dst: str
    via: str
    text: str


@dataclass
class NetReport:
    name: str
    drivers: list                  # machine keys
    consumers: list
    missing: list                  # endpoints with no entity in the layout
    pairs: int                     # driver -> consumer pairs
    reached: int                   # of them connected
    unreached: list                # [(driver, consumer)]
    segments: int                  # weakly connected pieces of the net's carriers
    carriers: int
    unpaired: list                 # the net's undergrounds the game leaves alone
    fluid: bool = False            # it has pipes, which are not traced yet
    leaks: list = field(default_factory=list)

    @property
    def connected(self):
        return self.pairs > 0 and self.reached == self.pairs

    @property
    def status(self):
        return "connected" if self.connected else "open" if self.reached else "unrouted"


@dataclass
class Report:
    graph: Graph
    nets: dict                     # name -> NetReport
    leaks: list                    # [Leak]
    checks: list                   # [Check]: per net its UNROUTED/OPEN line, then its LEAKs

    def lines(self):
        return [str(c) for c in self.checks]

    def summary(self):
        count = {s: sum(r.status == s for r in self.nets.values())
                 for s in ("connected", "open", "unrouted")}
        edges = sum(len(v) for v in self.graph.succ.values())
        return (f"{len(self.nets)} nets: {count['connected']} connected, {count['open']} open, "
                f"{count['unrouted']} unrouted; {len(self.leaks)} LEAK; "
                f"{len(self.graph.nodes)} entities, {edges} edges, "
                f"{len(self.graph.pairs) // 2} underground pairs")


# -- the graph ------------------------------------------------------------------------------------
def graph(ents, cat) -> Graph:
    """The directed carrier graph of a Layout, a Surface or a list of entities."""
    g = Graph()
    rows = ents.entities.values() if hasattr(ents, "entities") else ents
    for e in sorted(rows, key=lambda e: natural_key(e.key)):
        _add_node(g, e, cat)
    _belt_edges(g)
    _pair_undergrounds(g, cat)
    for key, n in g.nodes.items():
        if n.kind == "inserter":
            hand = _hand(n)
            if hand is None:
                continue
            src, dst = g.at.get(hand[0]), g.at.get(hand[1])
            if src is not None and _gives(g.nodes[src]):
                _edge(g, src, key, "pickup")
            if dst is not None and _takes(g.nodes[dst]):
                _edge(g, key, dst, "drop")
        elif n.kind == "mining-drill" and n.name not in _FLUID_DRILLS and n.dir in _STEP:
            dst = g.at.get(_drill_drop(n, cat))
            if dst is not None and dst != key and _takes(g.nodes[dst]):
                _edge(g, key, dst, "mine")
    order = {k: i for i, k in enumerate(g.nodes)}
    for adj in (g.succ, g.pred):
        for k in adj:
            adj[k].sort(key=lambda kv: order[kv[0]])
    return g


def _add_node(g, e, cat):
    try:
        kind = cat.kind(e.name)
    except KeyError:
        g.problems.append(f"{e.key}: unknown prototype {e.name}")
        return
    d = int(e.dir or 0) % 16
    try:
        tiles = tuple(sorted(getattr(e, "tiles", None)
                             or cat.tiles(e.name, float(e.x), float(e.y), d)))
    except ValueError as exc:
        g.problems.append(f"{e.key}: {exc}")
        return
    net, plot = e.attrs.get("net"), getattr(e, "plot", None)
    if net is not None and plot:
        net = f"{plot}/{net}"
    ug = None
    if kind == "underground-belt":
        ug = e.attrs.get("ug")
        if ug not in ("in", "out"):
            g.problems.append(f"{e.key}: an underground with no ug=in|out")
            ug = None
    g.nodes[e.key] = Node(e.key, e.name, kind, net, float(e.x), float(e.y), d, tiles, ug)
    for t in tiles:
        if t in g.at:
            g.problems.append(f"{e.key}: tile {t[0]},{t[1]} is already {g.at[t]}")
        else:
            g.at[t] = e.key


def _edge(g, a, b, via):
    if a == b or any(k == b for k, _v in g.succ.get(a, ())):
        return
    g.succ.setdefault(a, []).append((b, via))
    g.pred.setdefault(b, []).append((a, via))


def _entry(m, d):
    """How items moving in direction ``d`` enter ``m``: "straight", "side" or None."""
    if m.kind not in _BELTS or m.dir not in _STEP or (m.kind == "underground-belt" and not m.ug):
        return None
    if m.dir == d:                                   # from behind; an output's back is its hood
        return None if m.ug == "out" else "straight"
    if m.dir == (d + 8) % 16 or m.kind == "splitter":    # head-on; a splitter has no side entry
        return None
    return "side"


def _belt_edges(g):
    raw = []
    for key, n in g.nodes.items():
        step = _STEP.get(n.dir)
        if n.kind not in _BELTS or step is None or (n.kind == "underground-belt" and n.ug != "out"):
            continue
        for tx, ty in n.tiles:
            dst = g.at.get((tx + step[0], ty + step[1]))
            if dst is not None and dst != key:
                rel = _entry(g.nodes[dst], n.dir)
                if rel:
                    raw.append((key, dst, rel))
    behind = {b for _a, b, rel in raw if rel == "straight"}
    sides = {}
    for _a, b, rel in raw:
        if rel == "side":
            sides[b] = sides.get(b, 0) + 1
    for a, b, rel in raw:
        if rel == "straight":
            via = "belt"
        elif g.nodes[b].kind == "transport-belt" and b not in behind and sides[b] == 1:
            via = "curve"
        else:
            via = "sideload"
        _edge(g, a, b, via)


def _pair_undergrounds(g, cat):
    for key, n in g.nodes.items():
        step = _STEP.get(n.dir)
        if n.kind != "underground-belt" or n.ug != "in" or step is None:
            continue
        reach = int(cat.entity(n.name).get("max_distance") or _UG_REACH)
        tx, ty = n.tiles[0]
        for k in range(1, reach + 1):
            other = g.at.get((tx + k * step[0], ty + k * step[1]))
            m = g.nodes.get(other)
            if m is None or m.name != n.name or m.dir != n.dir:
                continue                             # passed through
            if m.ug == "out":
                g.pairs[key], g.pairs[other] = other, key
                _edge(g, key, other, "ug")
            break


def _hand(n):
    step = _STEP.get(n.dir)
    if step is None:
        return None
    r = REACH.get(n.name, 1)
    tx, ty = n.tiles[0]
    return (tx + step[0] * r, ty + step[1] * r), (tx - step[0] * r, ty - step[1] * r)


def _gives(m):
    """An inserter can pick from ``m``."""
    if m.kind in _BELTS:
        return m.kind != "underground-belt" or m.ug is not None
    return m.kind in HOLDER_TYPES and m.kind != "mining-drill"


def _takes(m):
    """An inserter or a drill can drop into ``m``."""
    if m.kind in _BELTS:
        return m.kind != "underground-belt" or m.ug == "in"
    return m.kind in HOLDER_TYPES


def _drill_drop(n, cat):
    w, h = cat.size(n.name)
    vx, vy = (-0.5 if w % 2 == 0 else 0.0), -(h / 2 + 0.3)     # facing north
    for _ in range(n.dir // 4):
        vx, vy = -vy, vx                                       # a quarter turn clockwise
    return math.floor(n.x + vx), math.floor(n.y + vy)


# -- the checks -----------------------------------------------------------------------------------
def endpoints(flat, surface=None, factory=None):
    """{net: (drivers, consumers)} of (machine key, item) from a flat netlist. With ``surface``
    and ``factory``, keys and net names as a composed surface has them (``nauvis:main/red/m0``,
    ``main/gear``)."""
    pre = f"{surface}:{factory}/" if surface and factory else ""
    netpre = f"{factory}/" if surface and factory else ""
    return {netpre + name: ([(pre + k, i) for k, i in n.drivers],
                            [(pre + k, i) for k, i in n.consumers])
            for name, n in flat.nets.items()}


def _keys(ends):
    keys = {e if isinstance(e, str) else e[0] for e in ends}
    return sorted(keys, key=natural_key)


def _inferred(g, carried):
    out = {}
    for net in sorted(carried, key=natural_key):
        drivers, consumers = set(), set()
        for k in carried[net]:
            drivers |= {m for m, _v in g.pred.get(k, ()) if not g.nodes[m].carrier}
            consumers |= {m for m, _v in g.succ.get(k, ()) if not g.nodes[m].carrier}
        out[net] = (sorted(drivers, key=natural_key), sorted(consumers, key=natural_key))
    return out


def _segments(g, keys):
    parent = {k: k for k in keys}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for a in keys:
        for b, _via in g.succ.get(a, ()):
            if b in parent:
                parent[find(a)] = find(b)
    return len({find(k) for k in keys})


def _net_word(n):
    return f"net {n.net}" if n.net else "no net"


def _leak(g, a, b, via, table):
    """The Leak an edge makes, or None."""
    na, nb = g.nodes[a], g.nodes[b]
    if na.carrier and nb.carrier:
        if na.net == nb.net:
            return None
        if via == "pickup":
            return Leak(na.net, a, b, via, f"{b} ({_net_word(nb)}) picks from {a}")
        return Leak(na.net, a, b, via, f"{a} {_VERB[via]} {b} ({_net_word(nb)})")
    if table is None:
        return None
    if na.carrier and na.net in table and b not in table[na.net][1]:
        return Leak(na.net, a, b, via, f"{a} drops into {b}, which is not a consumer of {na.net}")
    if nb.carrier and nb.net in table and a not in table[nb.net][0]:
        if via == "mine":
            return Leak(nb.net, a, b, via, f"{a} drops onto {b}, but does not drive {nb.net}")
        return Leak(nb.net, a, b, via, f"{b} picks from {a}, which does not drive {nb.net}")
    return None


def _status_line(r):
    if r.pairs == 0:
        msg = (f"no driver->consumer pair to connect ({len(r.drivers)} drivers, "
               f"{len(r.consumers)} consumers)")
    else:
        msg = f"{r.reached} of {r.pairs} driver->consumer pairs connected"
    if r.reached and r.unreached:
        shown = ", ".join(f"{d} -> {c}" for d, c in r.unreached[:_SHOW])
        more = len(r.unreached) - _SHOW
        msg += f"; unreached {shown}" + (f" ... {more} more" if more > 0 else "")
    msg += (f"; {r.segments} segment{'s' if r.segments != 1 else ''}, "
            f"{r.carriers} carrier{'s' if r.carriers != 1 else ''}")
    if r.unpaired:
        msg += f"; unpaired {', '.join(r.unpaired)}"
    if r.missing:
        msg += f"; not in the layout: {', '.join(r.missing)}"
    if r.fluid:
        msg += "; pipes are not traced yet"
    return Check("UNROUTED" if r.reached == 0 else "OPEN", f"net {r.name}", msg)


def connect(ents, cat, nets=None) -> Report:
    """Per net: connected yes/no and its LEAKs, over :func:`graph` of ``ents`` (or a Graph).

    ``nets``: {net: (drivers, consumers)} of machine keys or (key, item) pairs (see
    :func:`endpoints`), or a flat netlist; None infers them from the carriers."""
    g = ents if isinstance(ents, Graph) else graph(ents, cat)
    if nets is not None and hasattr(nets, "nets"):
        nets = endpoints(nets)
    carried = {}
    for key, n in g.nodes.items():
        if n.carrier and n.net is not None:
            carried.setdefault(n.net, []).append(key)
    if nets is None:
        table = _inferred(g, carried)
    else:
        table = {}
        for name, ends in nets.items():
            d, c = (ends.drivers, ends.consumers) if hasattr(ends, "drivers") else ends
            table[name] = (_keys(d), _keys(c))
    leaks = [lk for a, b, via in g.edges()
             if (lk := _leak(g, a, b, via, None if nets is None else table)) is not None]
    reports, checks = {}, []
    for name in sorted(table, key=natural_key):
        drivers, consumers = table[name]
        missing = [k for k in _keys(drivers + consumers) if k not in g.nodes]
        reached, unreached = 0, []
        for d in drivers:
            got = g.reach({d}, name) if d in g.nodes else set()
            for c in consumers:
                if c in got:
                    reached += 1
                else:
                    unreached.append((d, c))
        mine = carried.get(name, [])
        r = NetReport(name, drivers, consumers, missing, len(drivers) * len(consumers), reached,
                      unreached, _segments(g, mine), len(mine),
                      [k for k in mine if g.nodes[k].kind == "underground-belt"
                       and k not in g.pairs],
                      any(g.nodes[k].kind in _FLUID for k in mine),
                      [lk for lk in leaks if lk.net == name])
        reports[name] = r
        if not r.connected:
            checks.append(_status_line(r))
        checks += [Check("LEAK", f"net {name}", lk.text) for lk in r.leaks]
    checks += [Check("LEAK", f"net {lk.net}" if lk.net else "no net", lk.text)
               for lk in leaks if lk.net not in reports]
    return Report(g, reports, leaks, checks)
