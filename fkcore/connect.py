"""fkcore.connect: the directed carrier graph of a layout, and per net: connected yes/no, LEAK.

:func:`graph` takes an entity list (a factory :class:`fkcore.fkp.Layout`, a composed
:class:`fkcore.compose.Surface`, or any entities with key, name, x, y, dir, attrs) and the catalog.
Every entity is a node; an edge is one way items move from one entity into another:

- ``belt``: a belt, an underground output or a splitter half moves items onto the tile ahead. A
  transport belt there takes them unless it faces back (head-on), an underground input only from
  behind, a splitter only from behind.
- ``curve`` / ``sideload``: the same into the side of a belt. A curve when it is that belt's only
  input (nothing from behind), else a side-load.
- ``ug_sideload``: the same into the side of an underground (either end). Whether items get
  through depends on the lane, and V1 tracks no lanes: the edge counts, and ``UG_SIDELOAD``
  warns on every one (Rory, 2026-10-19).
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

Fluids are a second graph over **fluid boxes** (``Graph.fluid``), one node per live box
(``(key, box)``: a pipe has one, a boiler two, a chemical plant what its recipe makes live), with
the connections as the game makes them (``Catalog.fluid_boxes_at``, read from the game):

- ``pipe``: two normal connections facing each other across a tile edge (each one's target is
  the other's tile) join, whatever entity holds them: pipe to pipe, pipe to machine, machine to
  machine (a boiler straight onto a steam engine). A pipe beside a pipe-to-ground's side does not
  join it: that side has no connection.
- ``pipe_ug``: a pipe-to-ground's underground side pairs within its max distance (10, end to end);
  the first pipe-to-ground on the same axis decides (facing back: its partner; facing the same
  way: none); one at right angles and anything else in between is passed (measured in 2.0.77).

Fluid moves along a join from an output (or input-output) connection into an input (or
input-output) one, and through every box with more than one connection (a boiler's water box
passes water on to the next boiler). A fluid net's endpoint is the box of its machine that holds
the net's fluid.

A **carrier** (belt, underground, splitter, inserter, pipe ..., or anything with ``net=``) belongs
to one net; a **machine** (assembler, furnace, drill, lab, chest ...) is an endpoint, reached but
never passed through (a fluid box of an endpoint passes its fluid on). On a surface a carrier's net
is ``<factory>/<net>``: nets never leave their factory.

:func:`connect` checks every net (CORE-V1.md §4.5). Its drivers and consumers are the netlist's
endpoints (:func:`endpoints`) or, without a netlist, the machines its carriers pick from and drop
into. A net is **connected** when every driver reaches every consumer through the net's own
carriers. Report lines (``elaborate.Check``), never raised: ``UNROUTED`` (no driver reaches a
consumer), ``OPEN`` (some pairs connect, not all), ``UG_SIDELOAD`` (above; a connected net can
depend on one), ``LEAK`` (an edge from one net's carrier into another net's: a belt or side-load
feeding another net's belt, an inserter picking from another net's belt, an underground the game
pairs with another net's; with a netlist also a carrier moving items into a machine that is not
its net's consumer, or out of one that is not its driver). A fluid LEAK is any join between two
nets: a pipe or pipe-to-ground of one fluid net joined to another's, and with a netlist also to a
machine box that is not its endpoint, or two machines' boxes of different nets joined directly.

A **joint** is where one net hands its items to another on purpose: a bus port (Rory's bus,
``fkcore.fragments.bus``), a belt that is a consumer of one net and a driver of the next. A load's
belt is its net's last carrier and feeds the bus's first splitter; the bus's last splitter feeds a
tap's belt, its net's first. With a netlist, an edge between two nets' carriers is no LEAK where
one of its ends is such a port of both nets (a consumer of the net the items leave, a driver of
the one they enter), and a net's consumer that is another net's carrier counts as reached.

A net of contact items (2.0: heat, ``templates.CONTACT``) has no carriers: it is connected when
each driver's tiles touch each consumer's (a reactor beside its heat exchanger).
Pure, stdlib only, deterministic.
"""
from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field

from .elaborate import Check
from .fkp import CARRIER_TYPES, natural_key
from .templates import CONTACT

__all__ = ["Node", "Graph", "Leak", "NetReport", "Report", "graph", "connect", "endpoints",
           "endpoint_box", "one_inserter", "HOLDER_TYPES", "REACH"]

_STEP = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}
_BELTS = frozenset({"transport-belt", "underground-belt", "splitter"})
_FLUID = frozenset({"pipe", "pipe-to-ground", "pump"})
_GIVES_FLUID = frozenset({"output", "input-output"})
_TAKES_FLUID = frozenset({"input", "input-output"})
#: Entity types an inserter drops into or picks from: the machine endpoints.
HOLDER_TYPES = frozenset({"assembling-machine", "furnace", "mining-drill", "lab", "container",
                          "logistic-container", "boiler", "reactor", "ammo-turret", "roboport"})
#: Tiles from an inserter to its pickup and drop tile; every other inserter reaches 1.
REACH = {"long-handed-inserter": 2}
_FLUID_DRILLS = frozenset({"pumpjack"})
_UG_REACH = 5                      # a tier the catalog gives no max_distance
_SHOW = 4
_VERB = {"belt": "feeds", "curve": "feeds", "sideload": "side-loads onto",
         "ug_sideload": "side-loads onto", "ug": "pairs underground with", "drop": "drops onto",
         "mine": "drops onto"}


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
    recipe: str | None = None      # a crafting machine's recipe (it decides its fluid boxes)
    prio: tuple | None = None      # a splitter's (input, output) priority: left, right or None

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
    boxes: dict = field(default_factory=dict)       # (key, box) -> catalog.FluidBox, every live box
    fluid: dict = field(default_factory=dict)       # (key, box) -> [((key, box), via)] fluid moves
    joins: list = field(default_factory=list)       # [((key, box), (key, box), via)] each join once
    fluid_pairs: dict = field(default_factory=dict)  # pipe-to-ground -> its partner, both ways

    @property
    def unpaired(self):
        return [k for k, n in self.nodes.items() if n.kind == "underground-belt"
                and k not in self.pairs]

    def fluid_reach(self, starts, net, owners):
        """Every fluid box reached from ``starts`` (``(key, box)``) along the fluid moves, passing
        only through carriers of ``net`` and boxes ``owners`` gives to ``net`` (a boiler's water
        box passes water on); any other box is reached, never passed through."""
        seen = set(starts)
        todo = deque(sorted(seen, key=lambda b: (natural_key(b[0]), b[1])))
        while todo:
            for nid, _via in self.fluid.get(todo.popleft(), ()):
                if nid in seen:
                    continue
                seen.add(nid)
                n = self.nodes[nid[0]]
                if (n.net == net) if n.carrier else owners.get(nid) == net:
                    todo.append(nid)
        return seen

    def edges(self):
        """Every edge as (from, to, via), in natural key order."""
        for a in self.nodes:
            for b, via in self.succ.get(a, ()):
                yield a, b, via

    def reach(self, starts, net, forward=True, ends=()):
        """Every node reached from ``starts`` along the edges (against them when not
        ``forward``), passing only through carriers of ``net``; a machine is reached, never
        passed through, and so is a node of ``ends`` (a bus port: another net's carrier)."""
        adj = self.succ if forward else self.pred
        seen = set(starts)
        todo = deque(sorted(seen, key=natural_key))
        while todo:
            for k, _via in adj.get(todo.popleft(), ()):
                n = self.nodes[k]
                if k in seen:
                    continue
                if k in ends:
                    seen.add(k)
                    continue
                if n.carrier and n.net != net:
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
    fluid: bool = False            # a fluid net: judged over the fluid boxes
    leaks: list = field(default_factory=list)
    ug_sideloads: list = field(default_factory=list)    # [(belt, underground)]: lane-dependent

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
    checks: list                   # [Check]: per net UNROUTED/OPEN, its LEAKs, its UG_SIDELOADs

    def lines(self):
        return [str(c) for c in self.checks]

    def summary(self):
        count = {s: sum(r.status == s for r in self.nets.values())
                 for s in ("connected", "open", "unrouted")}
        edges = sum(len(v) for v in self.graph.succ.values())
        text = (f"{len(self.nets)} nets: {count['connected']} connected, {count['open']} open, "
                f"{count['unrouted']} unrouted; {len(self.leaks)} LEAK; "
                f"{len(self.graph.nodes)} entities, {edges} edges, "
                f"{len(self.graph.pairs) // 2} underground pairs")
        if self.graph.boxes:
            text += (f"; {len(self.graph.boxes)} fluid boxes, {len(self.graph.joins)} fluid joins, "
                     f"{len(self.graph.fluid_pairs) // 2} pipe-to-ground pairs")
        return text


# -- the graph ------------------------------------------------------------------------------------
def graph(ents, cat) -> Graph:
    """The directed carrier graph of a Layout, a Surface or a list of entities."""
    g = Graph()
    rows = ents.entities.values() if hasattr(ents, "entities") else ents
    for e in sorted(rows, key=lambda e: natural_key(e.key)):
        _add_node(g, e, cat)
    _belt_edges(g)
    _pair_undergrounds(g, cat)
    _fluid_joins(g, cat)
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
    g.nodes[e.key] = Node(e.key, e.name, kind, net, float(e.x), float(e.y), d, tiles, ug,
                          e.attrs.get("recipe"), _priority(e) if kind == "splitter" else None)
    for t in tiles:
        if t in g.at:
            g.problems.append(f"{e.key}: tile {t[0]},{t[1]} is already {g.at[t]}")
        else:
            g.at[t] = e.key


def _priority(e):
    """A splitter's (input, output) priority from its game settings (``config``): "left",
    "right" or None each; None for a splitter without any."""
    try:
        fields = json.loads(e.attrs.get("config") or "{}")
    except ValueError:
        return None
    if not isinstance(fields, dict):
        return None
    got = tuple(fields.get(k) if fields.get(k) in ("left", "right") else None
                for k in ("input_priority", "output_priority"))
    return got if any(got) else None


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
        elif g.nodes[b].kind == "underground-belt":
            via = "ug_sideload"
        elif b not in behind and sides[b] == 1:
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


def _fluid_joins(g, cat):
    """Every live fluid box, and the joins between them as the game makes them."""
    if not hasattr(cat, "fluid_boxes_at"):
        return
    normal, under = {}, {}
    for key, n in g.nodes.items():
        if not cat.has_fluid_boxes(n.name):
            continue
        for b in cat.fluid_boxes_at(n.name, n.x, n.y, n.dir, n.recipe):
            nid = (key, b.box)
            g.boxes[nid] = b
            for c in b.conns:
                table = normal if c.type == "normal" else under
                table.setdefault((c.tile, c.dir), []).append((nid, c))
    done = set()
    for (_tile, d), rows in sorted(normal.items()):
        for nid, c in rows:
            for mid, mc in normal.get((c.target, (d + 8) % 16), ()):
                if mid[0] != nid[0] and set(c.categories) & set(mc.categories):
                    _fluid_join(g, (nid, c.flow), (mid, mc.flow), "pipe", done)
    ends = {}
    for (tile, d), rows in under.items():
        for nid, c in rows:
            ends.setdefault(tile, []).append((d, nid, c))
    for (tile, d), rows in sorted(under.items()):
        step = _STEP.get(d)
        for nid, c in rows:
            for k in range(1, int(c.reach or 0) + 1) if step else ():
                t = (tile[0] + k * step[0], tile[1] + k * step[1])
                hits = [h for h in ends.get(t, ()) if h[0] % 8 == d % 8]
                if not hits:
                    continue                         # passed under it
                md, mid, mc = hits[0]
                if md == (d + 8) % 16 and set(c.categories) & set(mc.categories):
                    g.fluid_pairs[nid[0]], g.fluid_pairs[mid[0]] = mid[0], nid[0]
                    _fluid_join(g, (nid, c.flow), (mid, mc.flow), "pipe_ug", done)
                break
    order = {k: i for i, k in enumerate(g.nodes)}
    for k in g.fluid:
        g.fluid[k].sort(key=lambda kv: (order[kv[0][0]], kv[0][1]))


def _fluid_join(g, a, b, via, done):
    (na, fa), (nb, fb) = sorted((a, b), key=lambda x: (natural_key(x[0][0]), x[0][1]))
    if (na, nb, via) in done:
        return
    done.add((na, nb, via))
    g.joins.append((na, nb, via))
    if fa in _GIVES_FLUID and fb in _TAKES_FLUID:
        g.fluid.setdefault(na, []).append((nb, via))
    if fb in _GIVES_FLUID and fa in _TAKES_FLUID:
        g.fluid.setdefault(nb, []).append((na, via))


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
    for a, b, _via in g.joins:
        if a[0] in parent and b[0] in parent:
            parent[find(a[0])] = find(b[0])
    return len({find(k) for k in keys})


# -- fluid nets -----------------------------------------------------------------------------------
def _with_items(ends):
    return [(e, None) if isinstance(e, str) else (e[0], e[1]) for e in ends]


def _fluid_nets(g, cat, table, items, carried):
    """The nets judged over fluid boxes: every item a fluid, or (no items) pipes as carriers."""
    out = set()
    for name in table:
        named = [i for _k, i in items.get(name, ((), ()))[0] + items.get(name, ((), ()))[1]
                 if i is not None]
        if named:
            if all(cat.is_fluid(i) for i in named):
                out.add(name)
        elif any(g.nodes[k].kind in _FLUID for k in carried.get(name, ())):
            out.add(name)
    return out


def _boxes_by_key(g):
    out = {}
    for nid in g.boxes:
        out.setdefault(nid[0], []).append(nid)
    return out


def endpoint_box(boxes, item, side):
    """The FluidBox of a machine (``boxes``: ``Catalog.fluid_boxes_at``) that is its endpoint for
    fluid ``item`` on ``side`` (out: it drives the net, in: it consumes): the box holding that
    fluid, else the first box with no fixed fluid that can give (or take) it. None if none."""
    for b in boxes:
        if item is not None and b.fluid == item:
            return b
    fits = {"out": _GIVES_FLUID | {"none"}, "in": _TAKES_FLUID | {"none"}}[side]
    return next((b for b in boxes if b.fluid is None and b.production in fits), None)


def _endpoint_boxes(g, mine, key, item, side):
    """The (key, box) of machine ``key`` that holds a fluid net's ``item`` (out: a driver)."""
    nids = mine.get(key, ())
    b = endpoint_box([g.boxes[nid] for nid in nids], item, side)
    return [] if b is None else [(key, b.box)]


def _box_owners(g, fluid, items, inferred):
    """(key, box) -> the fluid net whose endpoint it is. From the netlist's (machine, item); with
    no netlist (``inferred``), a machine box joined to one fluid net's carriers is that net's."""
    owners, mine = {}, _boxes_by_key(g)
    for name in sorted(fluid, key=natural_key):
        drivers, consumers = items.get(name, ((), ()))
        for side, ends in (("out", drivers), ("in", consumers)):
            for key, item in ends:
                for nid in _endpoint_boxes(g, mine, key, item, side):
                    owners.setdefault(nid, name)
    if inferred:
        near = {}
        for a, b, _via in g.joins:
            for x, y in ((a, b), (b, a)):
                nx, ny = g.nodes[x[0]], g.nodes[y[0]]
                if not nx.carrier and ny.carrier and ny.net in fluid and x not in owners:
                    near.setdefault(x, set()).add(ny.net)
        owners.update({nid: next(iter(n)) for nid, n in near.items() if len(n) == 1})
    return owners


def _inferred_fluid(g, fluid, owners):
    """{net: (drivers, consumers)} of the fluid nets from their boxes: an output box drives."""
    out = {}
    for nid, net in owners.items():
        prod = g.boxes[nid].production
        if net in fluid and prod in ("output", "input"):
            out.setdefault(net, (set(), set()))[0 if prod == "output" else 1].add(nid[0])
    return {n: (sorted(d, key=natural_key), sorted(c, key=natural_key))
            for n, (d, c) in out.items()}


def _box_word(g, nid):
    fluid = g.boxes[nid].fluid
    return f"its {fluid} box" if fluid else f"fluid box {nid[1]}"


def _fluid_leaks(g, owners, table):
    """The Leak of every join between two nets (carriers always; boxes with a netlist)."""
    out = []
    for a, b, via in g.joins:
        na, nb = g.nodes[a[0]], g.nodes[b[0]]
        oa = na.net if na.carrier else owners.get(a)
        ob = nb.net if nb.carrier else owners.get(b)
        if oa == ob:
            continue
        verb = "pairs underground with" if via == "pipe_ug" else "joins"
        if na.carrier and nb.carrier:
            out.append(Leak(oa, a[0], b[0], via, f"{a[0]} {verb} {b[0]} ({_net_word(nb)})"))
        elif table is None:
            continue
        elif na.carrier or nb.carrier:
            (c, oc), m = ((a, oa), b) if na.carrier else ((b, ob), a)
            if oc in table:
                out.append(Leak(oc, c[0], m[0], via, f"{c[0]} joins {m[0]} ({_box_word(g, m)}), "
                                                     f"which is not an endpoint of {oc}"))
        else:
            net, other, nid = (oa, b, b) if oa in table else (ob, a, a)
            if net in table:
                there = owners.get(other)
                out.append(Leak(net, a[0], b[0], via, f"{a[0]} joins {b[0]} directly "
                                f"({_box_word(g, nid)}, " + (f"net {there})" if there else
                                                             "no net)")))
    out.sort(key=lambda lk: (natural_key(lk.src), natural_key(lk.dst)))
    return out


def _net_word(n):
    return f"net {n.net}" if n.net else "no net"


def _joint(a, b, na, nb, table):
    """An edge from one net's carrier into another's that is a bus port's: one of its ends is a
    consumer of the net the items leave and a driver of the one they enter."""
    if table is None or na.net not in table or nb.net not in table:
        return False
    return any(k in table[na.net][1] and k in table[nb.net][0] for k in (a, b))


def _leak(g, a, b, via, table):
    """The Leak an edge makes, or None."""
    na, nb = g.nodes[a], g.nodes[b]
    if na.carrier and nb.carrier:
        if na.net == nb.net or _joint(a, b, na, nb, table):
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
    return Check("UNROUTED" if r.reached == 0 else "OPEN", f"net {r.name}", msg)


def one_inserter(ents, cat, nets):
    """The nets of ``nets`` ({net: (drivers, consumers)}, :func:`endpoints`) laid as one inserter
    from source to sink: every carrier of the net an inserter that picks from one of its drivers
    and drops straight into one of its consumers, and every consumer reached that way. -> {net}.

    2.0 (Rory, 2026-10-21): the only route on which a mixed net can't clog. An inserter takes only
    what its sink accepts, but only when the multi-item source and the sink both touch it; a belt
    in between, or a second inserter (a chain, a hub chest), loses that."""
    g = ents if isinstance(ents, Graph) else graph(ents, cat)
    carried = {}
    for key, n in g.nodes.items():
        if n.carrier and n.net is not None:
            carried.setdefault(n.net, []).append(key)
    out = set()
    for net, (drivers, consumers) in nets.items():
        drivers, consumers = set(_keys(drivers)), set(_keys(consumers))
        keys = carried.get(net)
        if not keys or not drivers or not consumers:
            continue
        reached = set()
        for key in keys:
            src = [m for m, via in g.pred.get(key, ()) if via == "pickup"]
            dst = [m for m, via in g.succ.get(key, ()) if via == "drop"]
            if g.nodes[key].kind != "inserter" or len(src) != 1 or len(dst) != 1 \
                    or src[0] not in drivers or dst[0] not in consumers:
                break
            reached.add(dst[0])
        else:
            if reached == consumers:
                out.add(net)
    return out


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
    items = {}
    if nets is None:
        table = _inferred(g, carried)
    else:
        table = {}
        for name, ends in nets.items():
            d, c = (ends.drivers, ends.consumers) if hasattr(ends, "drivers") else ends
            table[name] = (_keys(d), _keys(c))
            items[name] = (_with_items(d), _with_items(c))
    fluid = _fluid_nets(g, cat, table, items, carried)
    owners = _box_owners(g, fluid, items, nets is None)
    if nets is None:
        table.update({n: ends for n, ends in _inferred_fluid(g, fluid, owners).items()})
    leaks = [lk for a, b, via in g.edges()
             if (lk := _leak(g, a, b, via, None if nets is None else table)) is not None]
    leaks += _fluid_leaks(g, owners, None if nets is None else table)
    ug_sides = [(a, b) for a, b, via in g.edges() if via == "ug_sideload"]
    mine_boxes = _boxes_by_key(g)
    reports, checks = {}, []
    for name in sorted(table, key=natural_key):
        drivers, consumers = table[name]
        missing = [k for k in _keys(drivers + consumers) if k not in g.nodes]
        reached, unreached = 0, []
        contact = bool(items.get(name)) and all(
            i in CONTACT for _k, i in items[name][0] + items[name][1] if i is not None)
        for d in drivers:
            if name in fluid:
                starts = [nid for nid in mine_boxes.get(d, ()) if owners.get(nid) == name]
                got = {nid[0] for nid in g.fluid_reach(starts, name, owners)
                       if owners.get(nid) == name}
            elif contact:
                got = {c for c in consumers if d in g.nodes and c in g.nodes
                       and _touch(g.nodes[d], g.nodes[c])}
            else:
                got = g.reach({d}, name, ends=set(consumers)) if d in g.nodes else set()
            for c in consumers:
                if c in got:
                    reached += 1
                else:
                    unreached.append((d, c))
        mine = carried.get(name, [])
        r = NetReport(name, drivers, consumers, missing, len(drivers) * len(consumers), reached,
                      unreached, _segments(g, mine), len(mine),
                      [k for k in mine if (g.nodes[k].kind == "underground-belt"
                                           and k not in g.pairs)
                       or (g.nodes[k].kind == "pipe-to-ground" and k not in g.fluid_pairs)],
                      name in fluid,
                      [lk for lk in leaks if lk.net == name],
                      [(a, b) for a, b in ug_sides if g.nodes[a].net == name])
        reports[name] = r
        if not r.connected:
            checks.append(_status_line(r))
        checks += [Check("LEAK", f"net {name}", lk.text) for lk in r.leaks]
        checks += [_ug_sideload_line(g, a, b) for a, b in r.ug_sideloads]
    checks += [Check("LEAK", f"net {lk.net}" if lk.net else "no net", lk.text)
               for lk in leaks if lk.net not in reports]
    checks += [_ug_sideload_line(g, a, b) for a, b in ug_sides if g.nodes[a].net not in reports]
    return Report(g, reports, leaks, checks)


def _touch(a, b):
    """Two nodes' tiles share an edge (2.0: heat passes by contact)."""
    tiles = set(b.tiles)
    return any((x + dx, y + dy) in tiles for x, y in a.tiles
               for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))


def _ug_sideload_line(g, a, b):
    net = g.nodes[a].net
    return Check("UG_SIDELOAD", f"net {net}" if net else "no net",
                 f"{a} side-loads onto underground {b}: whether items get through depends on "
                 "the lane, and V1 tracks no lanes")
