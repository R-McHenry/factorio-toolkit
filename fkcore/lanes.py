"""fkcore.lanes: the lane graph of a layout (CORE-V2.md), by the lane physics measured in the game.

A **connector** is one lane of one belt, underground or splitter, ``(key, "L")`` / ``(key, "R")``
(L and R looking along the flow: the game's transport lines 1 and 2), or one inserter,
``(key, "")``. A machine (anything an inserter reaches, a drill) is an endpoint node ``(key, "")``.
An edge is one way items move from one node into another, built over ``fkcore.connect``'s
carrier graph (V1's geometry: tiles, underground pairing, inserter reach) with the rules of
docs/LAB-LANES-20261020.md (2.0.77):

- ``straight``: a belt, an underground exit or a splitter onto the next belt, underground
  entrance or splitter from behind; a ``turn`` (V1's ``curve``: fed from one side, nothing
  behind) keeps the lanes too; ``tunnel``: an underground entrance to its exit, lane by lane.
- ``side``: a belt into the side of a belt is a 2-to-1 merge: both of its lanes go onto the
  target's near lane. The lane that enters the target further upstream is served first.
- ``ug_side``: a belt into the side of an underground (either end): only its lane on the open
  side goes through (an entrance is open upstream, an exit downstream), onto the near lane; the
  lane on the closed side is blocked, so it has no edge.
- ``pickup``: an inserter picks from both lanes of a belt tile, or from a machine.
- ``drop``: an inserter across a belt fills the far lane; along it (in line), always the right
  lane. Onto a turn, a splitter half and both underground ends alike: an exit takes drops from
  every side, though V1's connect gives it no drop edge (v4 B-120), so this module adds them.
- ``mine``: a drill drops onto the near lane (in line: the right lane, by the inserter rule;
  not measured).

Capacities, in items/s: a belt or underground lane carries ``belt_speed x 60 x 4`` (yellow 7.5); a
splitter's lane node stands for both halves (twice that); an inserter moves one hand per swing,
a swing taking ``2 x floor(0.5 / rotation speed)`` ticks (measured: the fast inserter makes 2.5 a
hand, not the 2.4 of the rule of thumb), less when it drops onto a belt at hand 3 and up. A
machine has no capacity of its own. Pure, stdlib only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import connect as connectmod

__all__ = ["Node", "Edge", "LaneGraph", "build", "lane_rate", "inserter_rate", "ROTATION",
           "HOLDERS", "INF"]

INF = float("inf")
_BELTS = frozenset({"transport-belt", "underground-belt", "splitter"})
_STEP = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}

#: Turns per tick, read from the game (2.0.77, tools/lab_lanes.py protos): the catalog has none.
ROTATION = {"burner-inserter": 0.013, "inserter": 0.014, "long-handed-inserter": 0.02,
            "fast-inserter": 0.04, "bulk-inserter": 0.04, "stack-inserter": 0.04}
#: A hand's own bonus over the force's (the stack inserter's +4, read from the game).
_OWN_HAND = {"stack-inserter": 4}
_BULK = frozenset({"bulk-inserter", "stack-inserter"})
#: Dropping onto a moving belt, the share of the chest rate a hand of n reaches (measured onto
#: yellow: fast hand 3 0.75, bulk hand 4 0.60; hands 1 and 2 lose nothing worth counting).
_ONTO_BELT = {1: 1.0, 2: 1.0, 3: 0.75, 4: 0.6}
#: Entity types an inserter or a drill reaches: the machines (connect's endpoints, and drills).
HOLDERS = connectmod.HOLDER_TYPES | {"mining-drill"}


def lane_rate(cat, name):
    """Items/s one lane of a belt, underground or splitter of ``name`` carries."""
    return float(cat.entity(name)["belt_speed"]) * 60 * 4


def inserter_rate(name, hand=1, bulk_hand=1, onto_belt=False):
    """Items/s an inserter moves: one hand per swing. ``hand`` is the non-bulk hand size (1 + the
    force's inserter bonus), ``bulk_hand`` the bulk one (1 + the bulk bonus); a stack inserter
    adds its own 4. None for an inserter whose rotation speed is unknown."""
    rot = ROTATION.get(name)
    if rot is None:
        return None
    n = (bulk_hand if name in _BULK else hand) + _OWN_HAND.get(name, 0)
    swing = 2 * math.floor(0.5 / rot + 1e-9)            # ticks per pick-and-drop
    rate = 60.0 / swing * n
    if onto_belt:
        rate *= _ONTO_BELT.get(n, 0.6)
    return rate


@dataclass
class Node:
    id: tuple                      # (key, lane): lane "L" | "R" for a belt carrier, "" otherwise
    kind: str                      # lane | splitter | inserter | machine
    key: str
    lane: str
    cap: float                     # items/s (INF for a machine)
    name: str = ""
    tier: str = ""                 # the carrier's prototype (a belt's tier)


@dataclass
class Edge:
    src: tuple
    dst: tuple
    via: str                       # straight turn tunnel side ug_side pickup drop mine
    rank: int = 0                  # priority at dst: lower is served first


@dataclass
class LaneGraph:
    nodes: dict = field(default_factory=dict)     # id -> Node
    out: dict = field(default_factory=dict)       # id -> [Edge]
    inn: dict = field(default_factory=dict)       # id -> [Edge]
    graph: object = None                          # the connect.Graph under it
    problems: list = field(default_factory=list)

    def edges(self):
        for v in self.nodes:
            yield from self.out.get(v, ())

    def add(self, src, dst, via, rank=0):
        if src not in self.nodes or dst not in self.nodes or src == dst:
            return
        for e in self.out.get(src, ()):
            if e.dst == dst:
                return
        e = Edge(src, dst, via, rank)
        self.out.setdefault(src, []).append(e)
        self.inn.setdefault(dst, []).append(e)


def _left(d):
    """The direction on the left of heading ``d`` (0 N, 4 E, 8 S, 12 W)."""
    return (d + 12) % 16


def _right(d):
    return (d + 4) % 16


def _near(src_dir, dst_dir):
    """The lane of a belt heading ``dst_dir`` nearest to a carrier moving ``src_dir`` into its
    side: from its left side (moving towards its right) the left lane."""
    if src_dir == _right(dst_dir):
        return "L"
    if src_dir == _left(dst_dir):
        return "R"
    return None


def _drop_lane(drop_dir, belt_dir):
    """The lane an inserter dropping in direction ``drop_dir`` fills on a belt heading
    ``belt_dir``: the far lane across it, the right lane in line."""
    if drop_dir % 8 == belt_dir % 8:
        return "R"
    return "R" if drop_dir == _right(belt_dir) else "L"


def build(ents, cat, hand=1, bulk_hand=1) -> LaneGraph:
    """The lane graph of a Layout, a Surface, a list of entities or a ``connect.Graph``."""
    g = ents if isinstance(ents, connectmod.Graph) else connectmod.graph(ents, cat)
    lg = LaneGraph(graph=g, problems=list(g.problems))
    belts = {}
    for key, n in g.nodes.items():
        if n.kind in _BELTS:
            if not cat.entity(n.name).get("belt_speed"):
                lg.problems.append(f"{key}: {n.name} has no belt speed")
                continue
            rate = lane_rate(cat, n.name)
            kind = "splitter" if n.kind == "splitter" else "lane"
            for lane in ("L", "R"):
                lg.nodes[(key, lane)] = Node((key, lane), kind, key, lane,
                                             rate * (2 if kind == "splitter" else 1), n.name, n.name)
            belts[key] = n
        elif n.kind == "inserter":
            onto = any(g.nodes[b].kind in _BELTS for b, via in g.succ.get(key, ()) if via == "drop")
            rate = inserter_rate(n.name, hand, bulk_hand, onto_belt=onto)
            if rate is None:
                lg.problems.append(f"{key}: {n.name} has no known rotation speed")
                rate = INF
            lg.nodes[(key, "")] = Node((key, ""), "inserter", key, "", rate, n.name)
        elif n.kind in HOLDERS:
            lg.nodes[(key, "")] = Node((key, ""), "machine", key, "", INF, n.name)
    drops = set()
    for a, b, via in g.edges():
        na, nb = g.nodes[a], g.nodes[b]
        if via in ("belt", "curve"):
            if a in belts and b in belts:
                for lane in ("L", "R"):
                    lg.add((a, lane), (b, lane), "straight" if via == "belt" else "turn", 0)
        elif via == "ug":
            for lane in ("L", "R"):
                lg.add((a, lane), (b, lane), "tunnel", 0)
        elif via == "sideload":
            near = _near(na.dir, nb.dir)
            if near is None:
                continue
            first = "L" if _left(na.dir) == (nb.dir + 8) % 16 else "R"   # enters further upstream
            lg.add((a, first), (b, near), "side", 1)
            lg.add((a, "R" if first == "L" else "L"), (b, near), "side", 2)
        elif via == "ug_sideload":
            near = _near(na.dir, nb.dir)
            if near is None:
                continue
            open_dir = (nb.dir + 8) % 16 if nb.ug == "in" else nb.dir
            lane = "L" if _left(na.dir) == open_dir else "R"
            lg.add((a, lane), (b, near), "ug_side", 1)
        elif via == "pickup":
            if a in belts:
                for lane in ("L", "R"):
                    lg.add((a, lane), (b, ""), "pickup", 0)
            else:
                lg.add((a, ""), (b, ""), "pickup", 0)
        elif via == "drop":
            drops.add((a, b))
            _drop(lg, g, belts, a, b)
        elif via == "mine":
            if b in belts:
                side = (na.dir + 8) % 16                 # the half of the tile towards the drill
                lane = "L" if side == _left(nb.dir) else "R"
                lg.add((a, ""), (b, lane), "mine", 3)
            else:
                lg.add((a, ""), (b, ""), "mine", 0)
    # an underground exit takes drops too (measured; connect gives it no drop edge)
    for key, n in g.nodes.items():
        if n.kind != "inserter":
            continue
        hand_tiles = g.inserter_tiles(key)
        if hand_tiles is None:
            continue
        b = g.at.get(hand_tiles[1])
        if b is not None and (key, b) not in drops and b in belts \
                and g.nodes[b].kind == "underground-belt" and g.nodes[b].ug == "out":
            _drop(lg, g, belts, key, b)
    return lg


def _drop(lg, g, belts, a, b):
    na, nb = g.nodes[a], g.nodes[b]
    if b in belts:
        lane = _drop_lane((na.dir + 8) % 16, nb.dir)    # an inserter faces its pickup side
        lg.add((a, ""), (b, lane), "drop", 3)
    else:
        lg.add((a, ""), (b, ""), "drop", 0)
