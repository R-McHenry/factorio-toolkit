"""fkcore.lanesearch: the lane-state search (PLAN-4.0 N1; docs/DESIGN-LANE-ROUTER.md).

Lanes are the search's resource. A state is ``(x, y, h, ex, L, R)``: steiner's belt state and
what the belt's two lanes hold, as small ids: ``EMPTY`` (0), one of the job's nets (1..k) or
``FOREIGN`` (a standing carrier's passenger). The moves are steiner's step, turn, jump and split
(the table says they keep the lanes) plus the lane moves, every one of them with the effect
``fkcore.lanephys`` gives (no rule is stated here):

- **side-load** into a belt of the net's own tree or of a host: both lanes onto the near lane;
  onto an underground end only the lane on the open side goes through, the other is blocked;
- **stub**: a side-load into a new empty belt with an empty belt behind it (today's join, found
  by the search: a belt fed from one side with nothing behind would turn and keep both lanes);
- **ride** a host's carriers: the state follows the host's chain, its own items on the lane it
  entered, at ``ride`` a tile; a host is a standing carrier (another net's, or a tree laid before
  in the same job) with its lane labels; the ride may leave at the chain's end when only the net
  itself is aboard;
- **drop** from a driver machine: an inserter onto a new belt or onto a belt of the tree or a
  host, filling the lane ``drop_lane`` names, ``turn_drop_lane`` onto a turn;
- **tap** into a consumer: an inserter picking from both lanes, so the net's item must be on one.

Goals are stated in lanes: a ``Fixed`` goal (a belt end) wants ``need`` per lane (an id, EMPTY,
or ANY); a pair's consumer wants A on L and B on R; a wide net itself on both; a port what its
declaration says; a ``Tap`` wants the item on some lane. No join by accident: a belt tile is
entered only by a move the table prices, every entry checks what it would feed downstream (the
other nets' met goals, a lane two items would share, a lane the move blocks), and the tile a
host's chain ends into is entered only from that chain.

The search runs per net of a job (``route``): a tree per net, consumers first, then the other
drivers attached to the stem (the belts upstream of every consumer); each tree becomes a host
for the nets after it, and the job is routed in every order, the cheapest kept. One leg (one A*
from the tree's starts to the nearest goal) runs in the Rust kernel when ``fkroute.lane_astar``
is there, step for step with ``_leg_py`` (FK_NATIVE=check raises on a difference); the Python leg
is the fallback. The lane graph (``fkcore.lanes.reach``) stays the judge of what was laid.
Stdlib only.
"""
from __future__ import annotations

import heapq
import itertools
import os
import time

from . import lanephys as phys
from . import steiner
from .steiner import DX, DY, INF, TapSink, _ent, _fdir, _tap_ent

__all__ = ["EMPTY", "FOREIGN", "ANY", "COSTS", "Fixed", "Tap", "Host", "LaneJob", "LaneTree",
           "Result", "route", "build_hosts", "lanes_ok", "native_on"]

EMPTY, FOREIGN, ANY = 0, 255, -1
#: in a goal's need while a net still has drivers to attach: the net itself, or nothing yet
PENDING = -2
#: steiner's prices, plus a tile ridden on a host and a driver's inserter (``hand``).
COSTS = dict(steiner.COSTS, ride=0.15, hand=steiner.COSTS["tap"])
_VIA = {v: i for i, v in enumerate(phys.VIAS)}
#: the path's move codes (the kernel's too): how a state was reached
STEP, JUMP, STUB, ENTER, RIDE, LEAVE, ATTACH = range(7)
_LI = {"L": 0, "R": 1}


# -- goals, hosts, jobs ---------------------------------------------------------------------------
class Fixed:
    """A belt end: a belt arrives on ``tile`` and leaves it flowing ``edir`` (0-3) holding
    ``need`` = (L, R), each an id that must be there, EMPTY (nothing) or ANY."""

    def __init__(self, name, tile, edir, need):
        self.name, self.tile, self.edir, self.need = name, tuple(tile), int(edir), tuple(need)

    @property
    def nets(self):
        return frozenset(n for n in self.need if n not in (EMPTY, ANY, FOREIGN))

    def h(self, x, y):
        return abs(x - self.tile[0]) + abs(y - self.tile[1])


class Tap:
    """A machine (tile rect) fed by ``k`` inserters of the nets in ``nets``, each picking off a
    belt of the job that holds its item on some lane. ``reject``: ids whose items the machine
    would take but must not get (no lane of the tapped tile may hold one)."""

    def __init__(self, name, rect, nets, k=1, inserters=("inserter", "long-handed-inserter"),
                 reject=()):
        self.name, self.rect, self.nets, self.k = name, tuple(rect), frozenset(nets), int(k)
        self.inserters, self.reject = tuple(inserters), frozenset(reject)
        self._sink = TapSink(name, self.rect, self.k, self.inserters)

    def h(self, x, y):
        return self._sink.h(x, y)


class Host:
    """One tile of a standing carrier: ``kind`` belt | ug_in | ug_out | splitter, its heading
    (0-3), its lanes (L, R) as ids, ``next`` the tiles its items flow on to (its chain), ``feeds``
    [(heading 0-3, (L, R))] every carrier that feeds it, ``leave`` the free tile its chain ends
    into (or None)."""

    def __init__(self, tile, heading, kind, lanes, next=(), feeds=(), leave=None):
        self.tile, self.heading, self.kind = tuple(tile), int(heading), kind
        self.lanes, self.next, self.feeds, self.leave = tuple(lanes), list(next), list(feeds), leave

    def via_of(self, src, extra=()):
        """How a feed moving ``src`` (0-3) enters this carrier, with its feeds and ``extra``."""
        return _entry(self.kind, self.heading, src, [h for h, _ln in self.feeds] + list(extra))


class LaneJob:
    """What one job routes: ``nets`` the net names (ids 1..k by position), ``starts`` {id:
    [(tile, heading, (L, R))]} the driver belt ends with what they carry, ``sources`` {id:
    [(key, rect)]} the driver machines (drops), ``goals`` [Fixed | Tap]."""

    def __init__(self, nets, starts=None, sources=None, goals=()):
        self.nets = list(nets)
        self.starts = {i: list(v) for i, v in (starts or {}).items()}
        self.sources = {i: list(v) for i, v in (sources or {}).items()}
        self.goals = list(goals)

    def ids(self):
        return list(range(1, len(self.nets) + 1))

    def goals_of(self, me):
        return [i for i, g in enumerate(self.goals) if me in g.nets]


def lanes_ok(need, L, R, me):
    """Does a belt holding (L, R) meet ``need`` for net ``me``: an id must be there (another
    job net may still be missing: its lane EMPTY until it is routed), EMPTY must be empty, ANY
    is any, PENDING the net itself or EMPTY (a driver still to attach fills it)."""
    for n, have in ((need[0], L), (need[1], R)):
        if n == ANY:
            continue
        if n == EMPTY:
            if have != EMPTY:
                return False
        elif n == me:
            if have != me:
                return False
        elif n == PENDING:
            if have not in (EMPTY, me):
                return False
        elif have not in (EMPTY, n):
            return False
    return True


def _pending(need, me):
    """``need`` with the net's own lanes PENDING (more of its drivers are still to come)."""
    return tuple(PENDING if n == me else n for n in need)


def _entry(kind, hn, src, feed_headings):
    """lanephys.entry on the router's headings (0-3): how a feed moving ``src`` enters a
    carrier of ``kind`` heading ``hn`` fed from ``feed_headings`` (``src`` among them)."""
    return phys.entry(kind, hn * 4, src * 4, [(h * 4,) for h in feed_headings])


def _step(t, h, k=1):
    return (t[0] + DX[h] * k, t[1] + DY[h] * k)


def _towards(a, b):
    """The heading from tile ``a`` to tile ``b`` (any distance along one axis)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return a[2] if len(a) > 2 else 0
    if abs(dx) >= abs(dy):
        return E_ if dx > 0 else W_
    return S_ if dy > 0 else N_


N_, E_, S_, W_ = 0, 1, 2, 3


def _lane_sets(lanes):
    return {"L": frozenset() if lanes[0] == EMPTY else frozenset((lanes[0],)),
            "R": frozenset() if lanes[1] == EMPTY else frozenset((lanes[1],))}


def _merge(moves, via, src, dst, ug, lanes, content, me):
    """(L, R) after a feed holding ``lanes`` enters a carrier holding ``content`` by move
    ``via`` (the table's codes; ``moves`` {(via, src, dst, ug): (edges, blocked)}): the edges
    move the feed's lanes; None where a lane would hold two ids or ``me`` lands nowhere."""
    edges, _blocked = moves[(via, src, dst, ug)]
    out = list(content)
    mine = False
    for a, b in edges:
        v = lanes[a]
        if v == EMPTY:
            continue
        if out[b] not in (EMPTY, v):
            return None
        out[b] = v
        if v == me:
            mine = True
    return tuple(out) if mine else None


_MOVES = {}


def _moves_of(table=None):
    """{(via, src, dst, ug): (edges, blocked)} of the table (the module's own, cached)."""
    if table is None:
        if not _MOVES:
            _MOVES.update(_moves_of(phys.table()))
        return _MOVES
    return {(via, s, d, ug): (edges, blocked) for via, s, d, ug, edges, blocked in table["moves"]}


def _children(mv):
    """The child states of a move: a split's two, a two-way ride's two, else the one."""
    if mv[0] == "split":
        return mv[2:]
    if mv[0] == "ride2":
        return mv[1:]
    return (mv[1],)


def _ids(sets):
    """{lane: set of ids} -> (L, R) ids, or None where a lane holds two."""
    out = []
    for ln in phys.LANES:
        s = sets.get(ln, frozenset())
        if len(s) > 1:
            return None
        out.append(next(iter(s)) if s else EMPTY)
    return tuple(out)


# -- the tree -------------------------------------------------------------------------------------
class LaneTree:
    """One net's carriers: own states (steiner's 4-tuples: x, y, the heading it arrived with,
    exited an underground) with their outgoing move, ``roots`` (a driver belt end, a drop, a
    stub) with what they put on, ``rides`` (states on a host's tiles, laid by nobody), ``taps``
    and ``drops`` (inserters), and ``lanes`` {state: (L, R)} what each belt holds, from
    ``propagate`` (own states, by the table) or the search (rides). A belt's real heading is its
    ``out_heading``: where its move goes (a step may turn it; a Fixed end turns into its
    consumer)."""

    def __init__(self, grid, me, costs=None, table=None):
        self.grid, self.me, self.costs = grid, me, dict(COSTS, **(costs or {}))
        self.moves = _moves_of(table)
        self.succ = {}        # state -> ("step"|"jump"|"side"|"enter"|"ride", child) | ("split", side, c1, c2)
        self.roots = {}       # state -> ((L, R) initial, ("start", h) | ("drop", q) | ("stub",))
        self.rides = set()    # states on host tiles
        self.ride_edges = {}  # ride state -> (via, src, dst, ug, the host's (L, R)) it is entered by
        self.lanes = {}       # state -> (L, R)
        self.sink_at = {}     # state -> goal index
        self.terminal = {}    # state -> the goal there ends the belt (a Fixed end)
        self.edir_at = {}     # state -> the heading a Fixed end leaves with
        self.taps = []        # (q, name, direction, goal name, arm)
        self.drops = []       # (q, name, facing 0-3, source key, tile)
        self.reserved = set()
        self.blocked_extra = set()   # the job's other trees' inserters: no tile of ours there
        self.lost = False
        self.pending = False  # drivers still to attach: a lane of the net's own may be EMPTY yet
        self._tiles = None

    def copy(self):
        t = LaneTree.__new__(LaneTree)
        t.grid, t.me, t.costs, t.moves = self.grid, self.me, self.costs, self.moves
        t.lost, t._tiles = False, None
        t.pending, t.blocked_extra = self.pending, self.blocked_extra
        t.ride_edges = dict(self.ride_edges)
        t.succ, t.roots, t.rides = dict(self.succ), dict(self.roots), set(self.rides)
        t.lanes, t.sink_at = dict(self.lanes), dict(self.sink_at)
        t.terminal, t.edir_at = dict(self.terminal), dict(self.edir_at)
        t.taps, t.drops, t.reserved = list(self.taps), list(self.drops), set(self.reserved)
        return t

    def states(self):
        """Every state, roots first (sorted), each before its children."""
        out, seen, stack = [], set(), sorted(self.roots, reverse=True)
        while stack:
            s = stack.pop()
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
            mv = self.succ.get(s)
            if mv is None:
                continue
            stack.extend(reversed(_children(mv)))
        return out

    def own(self):
        return [s for s in self.states() if s not in self.rides]

    def tiles(self):
        """tile -> owners (own states, splitter halves, inserters)."""
        if self._tiles is None:
            own = {}
            for s in self.own():
                own.setdefault((s[0], s[1]), []).append(s)
                mv = self.succ.get(s)
                if mv and mv[0] == "split":
                    for t in steiner.Tree.split_tiles(s, mv[1]):
                        own.setdefault(t, []).append(("splitter", s))
            for q, *_r in self.taps + self.drops:
                own.setdefault(q, []).append(("ins", q))
            self._tiles = own
        return self._tiles

    def touch(self):
        self._tiles = None

    def free(self, t):
        return (not self.grid.blocked(t) and t not in self.tiles() and t not in self.reserved
                and t not in self.blocked_extra and t not in getattr(self.grid, "soft", ()))

    def spans(self):
        out = {0: set(), 1: set()}
        for s in self.own():
            mv = self.succ.get(s)
            if mv and mv[0] == "jump":
                c = mv[1]
                k = abs(c[0] - s[0]) + abs(c[1] - s[1])
                out[c[2] % 2] |= {(s[0] + DX[c[2]] * j, s[1] + DY[c[2]] * j) for j in range(k + 1)}
        return out

    def out_heading(self, s):
        """The heading the carrier at ``s`` runs: a step's child heading, a side-load's or
        entry's direction, a Fixed end's ``edir``, else its own."""
        mv = self.succ.get(s)
        if mv is None:
            return self.edir_at.get(s, s[2])
        if mv[0] in ("step", "side", "enter"):
            return _towards(s, mv[1])       # a step's child arrived that way; a driver
        return s[2]                         # attached straight into a tree belt did not

    def preds(self):
        """state -> [(the heading it is fed in, feeder)] over own and ride states."""
        out = {}
        for s, mv in self.succ.items():
            if mv[0] in ("split", "ride2"):
                for c in _children(mv):
                    out.setdefault(c, []).append((s[2], s))
            elif mv[0] in ("jump", "ride"):
                out.setdefault(mv[1], []).append((s[2], s))
            else:                                   # side, enter: pointing at the child's tile
                out.setdefault(mv[1], []).append((_towards(s, mv[1]), s))
        return out

    def carrier(self, s):
        if s[3]:
            return "ug_out"
        mv = self.succ.get(s)
        return "ug_in" if mv and mv[0] == "jump" else "belt"

    def feed_headings(self, s, preds):
        """The headings (0-3) of what feeds own state ``s``: its predecessors and, for a driver
        belt end, the belt behind it."""
        out = [h for h, _p in preds.get(s, ())]
        if s in self.roots and self.roots[s][1][0] == "start":
            out.append(s[2])
        return out

    def is_turn(self, s, preds):
        """Is own belt ``s`` a curve: fed from one side only, nothing behind."""
        hd = self.out_heading(s)
        fs = self.feed_headings(s, preds)
        return self.carrier(s) == "belt" and len(fs) == 1 and fs[0] != hd and \
            _entry("belt", hd, fs[0], fs) == "turn"

    def drop_lane_at(self, s, q, preds):
        """The lane an inserter at ``q`` dropping onto own carrier ``s`` fills (the table)."""
        ddir = _towards(q, s)
        hd = self.out_heading(s) if self.carrier(s) == "belt" else s[2]
        if self.is_turn(s, preds):
            come = self.feed_headings(s, preds)[0]
            return phys.turn_drop_lane(come * 4, hd * 4, ((ddir + 2) % 4) * 4)
        return phys.drop_lane(ddir * 4, hd * 4)

    def propagate(self, extra=()):
        """``lanes`` of every state from the roots by the table: own belts by ``lanephys.fed``,
        ride states by the move that entered them (``ride_edges``); ``extra`` [(state, heading,
        (L, R))] phantom feeds for a trial. -> False when a lane would hold two ids or a feed of
        the net's own items is lost."""
        me = self.me
        preds = self.preds()
        content = {s: self.lanes[s] for s in self.rides if s in self.lanes}
        drops = {}
        for q, _n, _d, _k, tile in self.drops:
            for s in self.tiles().get(tile, ()):
                if isinstance(s, tuple):
                    drops.setdefault(s, []).append(q)
        ok = True
        every = self.states()
        for _round in range(len(every) + 3):
            changed, ok = False, True      # judged at the fixpoint: a state fed before its
            for s in every:                # feeders have content looks lost for a round
                if s in self.rides:
                    edge = self.ride_edges.get(s)
                    ps = preds.get(s, ())
                    if edge is None or len(ps) != 1:
                        continue                      # a drop onto a host: its lanes are its own
                    via, src, dst, ug, host = edge
                    held = content.get(ps[0][1], self.lanes.get(ps[0][1], (EMPTY, EMPTY)))
                    got = _merge(self.moves, via, src, dst, ug, held, host, me)
                    if got is None:
                        ok = False
                        got = content.get(s, self.lanes.get(s, (EMPTY, EMPTY)))
                    if content.get(s) != got:
                        content[s] = got
                        changed = True
                    continue
                kind = self.carrier(s)
                hd = self.out_heading(s) if kind == "belt" else s[2]
                feeds, tunnel = [], []
                for h, p in preds.get(s, ()):
                    held = content.get(p) if p in content else self.lanes.get(p, (EMPTY, EMPTY))
                    if self.succ.get(p, ("",))[0] == "jump":
                        tunnel.append(held)
                    else:
                        feeds.append((h * 4, _lane_sets(held)))
                if s in self.roots and self.roots[s][1][0] == "start":
                    feeds.append((s[2] * 4, _lane_sets(self.roots[s][0])))
                for st, h, ln in extra:
                    if st == s:
                        feeds.append((h * 4, _lane_sets(ln)))
                out, lost = phys.fed(kind, hd * 4, feeds)
                sets = {ln: set(v) for ln, v in out.items()}
                for held in tunnel:
                    for ln, v in phys.carry("tunnel", _lane_sets(held)).items():
                        sets.setdefault(ln, set()).update(v)
                if me in lost:
                    ok = False
                for q in drops.get(s, ()):
                    sets.setdefault(self.drop_lane_at(s, q, preds), set()).add(me)
                ids = _ids({ln: frozenset(v) for ln, v in sets.items()})
                if ids is None:
                    ok = False
                    ids = (EMPTY, EMPTY)
                if content.get(s) != ids:
                    content[s] = ids
                    changed = True
            if not changed:
                break
        for s in every:
            self.lanes[s] = content.get(s, self.lanes.get(s, (EMPTY, EMPTY)))
        self.lost = not ok
        return ok

    def goals_ok(self, goals, strict=False):
        """Every goal met so far still holds on the lanes as propagated (``strict``: as
        declared; else a lane of the net's own may still be EMPTY while drivers are pending)."""
        for s, i in self.sink_at.items():
            g = goals[i]
            L, R = self.lanes.get(s, (EMPTY, EMPTY))
            if isinstance(g, Fixed):
                need = _pending(g.need, self.me) if self.pending and not strict else g.need
                if not lanes_ok(need, L, R, self.me):
                    return False
            elif (self.me not in (L, R) and not (self.pending and not strict)) or {L, R} & g.reject:
                return False
        return True

    def stem(self):
        """The own states upstream of every goal met so far (where a driver may attach)."""
        ends = set(self.sink_at)
        if not ends:
            return set(self.own())
        desc = {}

        def below(s):
            if s in desc:
                return desc[s]
            got, mv = {s}, self.succ.get(s)
            if mv is not None:
                for c in _children(mv):
                    got |= below(c)
            desc[s] = got
            return got
        return {s for s in self.own() if ends <= below(s)}

    # -- views ------------------------------------------------------------------------------------
    def entities(self, net="net"):
        """Plan entities of the tree (steiner's format): own belts, undergrounds, splitters and
        the inserters; rides lay nothing."""
        ents = []
        for s in self.own():
            x, y, d, ex = s
            mv = self.succ.get(s)
            if mv is not None and mv[0] == "jump":
                ents.append(_ent("underground-belt", x, y, d, net, "input"))
                continue
            if mv is not None and mv[0] == "split":
                n, m = steiner.Tree.split_tiles(s, mv[1])
                ents.append({"name": "splitter", "x": (n[0] + m[0]) / 2 + 0.5,
                             "y": (n[1] + m[1]) / 2 + 0.5, "direction": _fdir(d), "role": "spine",
                             "net": net})
            if ex:
                ents.append(_ent("underground-belt", x, y, d, net, "output"))
            else:
                ents.append(_ent("transport-belt", x, y, self.out_heading(s), net))
        for q, name, direction, sink, arm in self.taps:
            ents.append(_tap_ent(name, q, direction, arm, f"{net}~{sink}"))
        for q, name, g, key, _tile in self.drops:
            ents.append(_tap_ent(name, q, _fdir(g), None, f"{key}->{net}"))
        return ents

    def counts(self):
        c = {"belts": 0, "turns": 0, "undergrounds": 0, "splitters": 0, "taps": len(self.taps),
             "drops": len(self.drops), "rides": len(self.rides)}
        for s in self.own():
            mv = self.succ.get(s)
            if s[3]:
                c["undergrounds"] += 1
            if mv is not None and mv[0] == "jump":
                c["undergrounds"] += 1
                continue
            if not s[3]:
                c["belts"] += 1
            if mv is not None and mv[0] == "split":
                c["splitters"] += 1
            elif mv is not None and mv[0] == "step" and mv[1][2] != s[2] and s not in self.roots:
                c["turns"] += 1
        return c

    def cost(self):
        c, k = self.counts(), self.costs
        return round(c["belts"] * k["belt"] + c["turns"] * k["turn"] + c["undergrounds"] / 2 * k["ug"]
                     + c["splitters"] * k["split"] + c["rides"] * k["ride"]
                     + sum(k["long_tap"] if n == "long-handed-inserter" else k["tap"]
                           for _q, n, _d, _s, _a in self.taps)
                     + sum(k["long_tap"] if n == "long-handed-inserter" else k["hand"]
                           for _q, n, _d, _s, _t in self.drops), 3)

    def shared(self):
        """The host tiles the net rides, in flow order (the report's ``shared`` line)."""
        return [(s[0], s[1]) for s in self.states() if s in self.rides]

    def ride_tiles(self):
        return {(s[0], s[1]) for s in self.rides}

    def behind(self):
        """{tile: (heading, (L, R))} the driver belts behind the tree's start roots."""
        return {(s[0], s[1]): (s[2], init) for s, (init, how) in self.roots.items()
                if how[0] == "start"}

    def hosts(self):
        """The own carriers as host items: [(tile, heading, kind, (L, R))]."""
        out = []
        for s in self.own():
            mv = self.succ.get(s)
            if mv is not None and mv[0] == "split":
                for t in steiner.Tree.split_tiles(s, mv[1]):
                    out.append((t, s[2], "splitter", self.lanes.get(s, (EMPTY, EMPTY))))
            kind = self.carrier(s)
            h = self.out_heading(s) if kind == "belt" else s[2]
            out.append(((s[0], s[1]), h, kind, self.lanes.get(s, (EMPTY, EMPTY))))
        return out

    def key(self):
        """Everything that makes this tree, for a parity check."""
        return (sorted(self.succ.items()), sorted(self.roots.items()), sorted(self.rides),
                sorted(self.lanes.items()), sorted(self.sink_at.items()), sorted(self.taps),
                sorted(self.drops), sorted(self.reserved))


# -- hosts ----------------------------------------------------------------------------------------
def build_hosts(items, free, riders=None, behind=None):
    """{tile: Host} from ``items`` [(tile, heading 0-3, kind, (L, R))]: each tile's chain (where
    its items flow on: the belt ahead it feeds, an entrance's exit, both halves' fronts of a
    splitter), its feeds and the free tile its chain ends into (``free(tile)``). ``riders``
    {tile: (L, R)}: what rides there already (a net laid before), over the item's own lanes.
    ``behind`` {tile: (heading, (L, R))}: a belt that is no item feeds the tile from behind (a
    driver's belt end), so the tile is no curve for a side feed to make."""
    at = {tuple(t): (int(h), kind, tuple(lanes)) for t, h, kind, lanes in items}
    if riders:
        for t, ln in riders.items():
            if t in at:
                h, kind, _old = at[t]
                at[t] = (h, kind, tuple(ln))
    hosts = {t: Host(t, h, kind, lanes) for t, (h, kind, lanes) in at.items()}
    for t, (h, lanes) in (behind or {}).items():
        if t in hosts:
            hosts[t].feeds.append((h, tuple(lanes)))
    for t, (h, kind, lanes) in at.items():
        host = hosts[t]
        if kind == "ug_in":
            for k in range(1, 12):
                u = _step(t, h, k)
                if u in at and at[u][0] == h and at[u][1] in ("ug_in", "ug_out"):
                    if at[u][1] == "ug_out":
                        host.next.append(u)
                        hosts[u].feeds.append((h, lanes))
                    break
            continue
        fronts = [_step(t, h)]
        if kind == "splitter":
            for side in (1, 3):
                m = _step(t, (h + side) % 4)
                if m in at and at[m][1] == "splitter" and at[m][0] == h:
                    fronts.append(_step(m, h))
        for k, f in enumerate(fronts):
            if f in at:
                fh, fk, _fl = at[f]
                if _entry(fk, fh, h, [h]) is not None:
                    host.next.append(f)
                    if k == 0:          # the other half's front is fed by that half, once
                        hosts[f].feeds.append((h, lanes))
            elif kind != "splitter" and free(f) and host.leave is None:
                host.leave = f
    return hosts


def _hop_via(host, nh):
    """The move kind of one step of a chain, from ``host`` into ``nh`` (tunnel from an entrance
    to its exit)."""
    if host.kind == "ug_in" and nh.kind == "ug_out":
        return "tunnel"
    return nh.via_of(host.heading)


def _down_ok(hosts, tile, lane, me, goals, met):
    """May ``me`` enter host ``tile`` on ``lane`` (0 L, 1 R): along the chain from there its
    items land on no lane another id holds and break no met goal of another net (``met``
    {tile: goal index}). Where the table blocks a lane the items stop (the entry then serves
    nothing past it, which the goal test finds)."""
    todo, seen = [(tile, lane)], set()
    while todo:
        t, ln = todo.pop()
        if (t, ln) in seen:
            continue
        seen.add((t, ln))
        host = hosts[t]
        if host.lanes[ln] not in (EMPTY, me):
            return False
        if t in met:
            g = goals[met[t]]
            have = list(host.lanes)
            have[ln] = me
            if isinstance(g, Fixed) and not lanes_ok(g.need, have[0], have[1], me):
                return False
            if isinstance(g, Tap) and me in g.reject:
                return False
        for u in host.next:
            nh = hosts[u]
            via = _hop_via(host, nh)
            if via is None:
                return False
            edges, _blocked = phys.moves(via, host.heading * 4, nh.heading * 4,
                                         "in" if nh.kind == "ug_in" else "out")
            for a, b, _r in edges:
                if _LI[a] == ln:
                    todo.append((u, _LI[b]))
    return True


def _host_entries(hosts, me, goals, met, taken):
    """Entries into the hosts: {(tile, src heading): (hn, ex, via, ug, (L, R), down_ok bits,
    kind 1)} for every side of every host tile a belt may enter (an unfed empty belt turns; a
    curve is never entered: a second feed would turn it into a side-load and move the host's
    own items)."""
    out = {}
    for t, host in hosts.items():
        if t in taken or host.kind == "splitter":
            continue
        heads = [h for h, _ln in host.feeds]
        if any(_entry(host.kind, host.heading, h, heads) == "turn" for h in heads):
            continue
        ok = sum(1 << ln for ln in (0, 1) if _down_ok(hosts, t, ln, me, goals, met))
        if not ok:
            continue
        for src in range(4):
            if src == (host.heading + 2) % 4:
                continue
            via = host.via_of(src, [src])
            if via is None:
                continue
            if via == "turn" and host.lanes != (EMPTY, EMPTY):
                continue        # fed by a hand or a drill: a turn would move its drop
            if via == "straight" and host.heading in heads:
                continue        # something is behind it already
            out[(t, src)] = (host.heading, 1 if host.kind == "ug_out" else 0, _VIA[via],
                             0 if host.kind == "ug_in" else 1, host.lanes, ok, 1)
    return out


def _hops(hosts):
    """{tile: [(next, via, hn, ug, ex, (L, R))]} the ride's steps along every chain."""
    out = {}
    for t, host in hosts.items():
        rows = []
        for u in host.next:
            nh = hosts[u]
            via = _hop_via(host, nh)
            if via is None:
                continue
            rows.append((u, _VIA[via], nh.heading, 0 if nh.kind == "ug_in" else 1,
                         1 if nh.kind == "ug_out" else 0, nh.lanes))
        out[t] = rows
    return out


def _tree_entries(tree, goals):
    """Entries into the tree's own stem for a driver attaching: {(tile, src heading): (hn, ex,
    via, ug, (L, R), down_ok bits, kind 0)}; each lane's validity by a trial propagation, one
    per tile and lane, and none where nothing can break: the tree holds the net alone and every
    goal met takes it on either lane (a wide net)."""
    out = {}
    preds = tree.preds()
    me = tree.me
    simple = all(v in (EMPTY, me) for ln in tree.lanes.values() for v in ln) and all(
        (isinstance(goals[i], Fixed) and all(n in (me, ANY, PENDING) for n in goals[i].need))
        or (isinstance(goals[i], Tap) and not goals[i].reject) for i in tree.sink_at.values())
    trials = {}

    def ok_on(s, src, ln):
        key = (s, ln)
        if key not in trials:
            ln_in = [EMPTY, EMPTY]
            ln_in[ln] = me
            trial = tree.copy()
            trials[key] = trial.propagate([(s, src, tuple(ln_in))]) and trial.goals_ok(goals)
        return trials[key]
    for s in tree.stem():
        t = (s[0], s[1])
        kind = tree.carrier(s)
        hn = tree.out_heading(s) if kind == "belt" else s[2]
        heads = tree.feed_headings(s, preds)
        for src in range(4):
            if src == (hn + 2) % 4 or (src == hn and hn in heads):
                continue
            via = _entry(kind, hn, src, heads + [src])
            if via is None:
                continue
            if via == "turn" and tree.lanes.get(s, (EMPTY, EMPTY)) != (EMPTY, EMPTY):
                continue
            ok = 3 if simple else sum(1 << ln for ln in (0, 1) if ok_on(s, src, ln))
            if ok:
                out[(t, src)] = (hn, s[3], _VIA[via], 0 if kind == "ug_in" else 1,
                                 tree.lanes.get(s, (EMPTY, EMPTY)), ok, 0)
    return out


# -- the leg: one A* --------------------------------------------------------------------------------
class _Spec:
    """What one leg searches over: the ground, the tree's own tiles, the hosts' entries and
    hops, the goals, the prices and the table."""

    def __init__(self, tree, hosts, goals, entries, hops, leaves, table, attach, no_turn=(),
                 tapped=None):
        self.tree, self.hosts, self.goals = tree, hosts, goals
        self.entries, self.hops, self.leaves, self.table = entries, hops, leaves, table
        self.me = tree.me
        self.no_turn = set(no_turn)      # start states whose belt heading the lanes depend on
        # a forward leg never rides into a tile the net rides already (its items are there); a
        # driver attaching may (it joins the net's flow there)
        self.taken = set() if attach else tree.ride_tiles()
        # {goal index: tiles} where another net of the job already picks for that machine: a
        # belt there with the item aboard meets the tap with no inserter of its own
        self.tapped = {i: set(ts) for i, ts in (tapped or {}).items()}
        # the heuristic's price of a tile: with a host to ride, a ride's (else it over-estimates)
        self.hscale = min(tree.costs["ride"], tree.costs["belt"]) if any(hops.values()) \
            else tree.costs["belt"]
        # the tile ahead of a belt end is its consumer's own belt
        self.fronts = {_step(g.tile, g.edir) for g in goals if isinstance(g, Fixed)}
        # a Fixed goal's need for this leg: the net's own lanes PENDING while drivers remain
        self.needs = [(_pending(g.need, tree.me) if tree.pending else g.need)
                      if isinstance(g, Fixed) else None for g in goals]
        self.attach_tiles = ({t for t, owners in tree.tiles().items()
                              if any(isinstance(o, tuple) for o in owners)} | tree.ride_tiles()) \
            if attach else set()
        self.extra = set(tree.tiles()) | set(tree.reserved) | set(hosts) | set(leaves) \
            | set(tree.blocked_extra) | self.fronts
        self.tspans = tree.spans()
        self.k = tree.costs
        self.moves = {(via, s, d, ug): (edges, blocked)
                      for via, s, d, ug, edges, blocked in table["moves"]}
        self.host_ok = {t: e[5] for (t, _s), e in entries.items() if e[6] == 1}

    def merge(self, via, src, dst, ug, lanes, content):
        return _merge(self.moves, via, src, dst, ug, lanes, content, self.me)


def _tap_goal(sp, i, path6):
    """The tap goal test (both legs): on a tile another net's inserter already picks from for
    this machine, the item aboard is enough (one inserter picks both lanes); else steiner's pick
    with the lanes: the net's item on a lane of the last tile, nothing rejected there, the
    belt's front no host's tile."""
    g = sp.goals[i]
    x, y, d, ex, L, R = path6[-1]
    if (sp.me not in (L, R) and not sp.tree.pending) or {L, R} & g.reject:
        return False
    if (x, y) in sp.tapped.get(i, ()):
        return True
    front = (x + DX[d], y + DY[d])
    if front in sp.hosts:
        return False
    if ex and sp.tree.grid.blocked(front):
        return False
    path4 = [p[:4] for p in path6]
    return len(g._sink.pick(path4, sp.tree)) >= g.k


def _leg_py(sp, starts, targets, limit):
    """One A* from ``starts`` [(state6, g0)] to the nearest of ``targets`` (goal indices), or
    into the tree (a tile of ``attach_tiles``: a driver attaching) -> ([(state6, the move that
    reached it)], goal index or -1, cost) or None. steiner._astar_py's discipline: heap (f, -g,
    state), strict improvement, moves in a fixed order, costs summed in order; the kernel
    mirrors it."""
    k, grid, me = sp.k, sp.tree.grid, sp.me
    extra, tspans, hops, entries, leaves = sp.extra, sp.tspans, sp.hops, sp.entries, sp.leaves
    soft = getattr(grid, "soft", None) or None
    goals = sp.goals
    fixed_tiles = {goals[i].tile for i in range(len(goals)) if isinstance(goals[i], Fixed)}
    attach_tiles = sp.attach_tiles
    entry_tiles = sorted({t for (t, _s), e in entries.items() if e[6] == 0})

    def blocked(t):
        return grid.blocked(t) or t in extra

    hscale, no_turn = sp.hscale, sp.no_turn

    def hh(x, y):
        best = INF
        for i in targets:
            v = goals[i].h(x, y)
            if v < best:
                best = v
        for t in entry_tiles:
            v = abs(x - t[0]) + abs(y - t[1])
            if v < best:
                best = v
        return float(best) * hscale if best < INF else 0.0

    heap, g, parent = [], {}, {}
    for st, g0 in starts:
        if g0 < g.get(st, INF):
            g[st] = g0
            parent[st] = None
            heapq.heappush(heap, (g0 + hh(st[0], st[1]), -g0, st))
    done = set()
    jumps = range(2, int(k["max_ug"]) + 1)
    while heap:
        _f, ng, st = heapq.heappop(heap)
        gs = -ng
        if st in done or gs > g.get(st, INF):
            continue
        done.add(st)
        if len(done) > limit:
            return None
        x, y, d, ex, L, R = st
        path = None
        if (x, y) in attach_tiles:
            return _trace(parent, st), -1, gs
        came = parent[st][1] if parent[st] is not None else -1
        for i in targets:
            goal = goals[i]
            if isinstance(goal, Fixed):
                hit = (x, y) == goal.tile and d != (goal.edir + 2) % 4 and (not ex or d == goal.edir) \
                    and (came != STUB or d == goal.edir) and lanes_ok(sp.needs[i], L, R, me)
            elif goal.h(x, y) > 0:
                hit = False
            else:
                path = path or _trace(parent, st)
                hit = _tap_goal(sp, i, [p for p, _how in path])
            if hit:
                path = path or _trace(parent, st)
                if _tiles_apart(path):
                    return path, i, gs
        riding = (x, y) in hops
        if riding and hops[(x, y)]:
            for nt, via, hn, ug, nex, content in hops[(x, y)]:
                if nt in sp.taken:
                    continue
                lanes = sp.merge(via, d, hn, ug, (L, R), content)
                if lanes is None:
                    continue
                _push(heap, g, parent, (nt[0], nt[1], hn, nex, lanes[0], lanes[1]), st, RIDE,
                      gs + k["ride"], hh)
            continue
        if riding:
            if L not in (EMPTY, me) or R not in (EMPTY, me):
                continue                            # passengers aboard: the ride ends here
            n = (x + DX[d], y + DY[d])
            if leaves.get(n) == (x, y):
                cost = gs + k["belt"]
                if soft:
                    cost += soft.get(n, 0.0)
                _push(heap, g, parent, (n[0], n[1], d, 0, L, R), st, LEAVE, cost, hh)
            continue
        if (x, y) in fixed_tiles and parent[st] is not None:
            continue   # nothing continues through a port's link tile
        # an exit runs straight on; so does a drop root (its lane hangs on its heading) and a
        # belt a stub side-loads (the stub behind it fixes which way it runs)
        fixed_heading = ex or came == STUB or st in no_turn
        for nd in range(4):
            if fixed_heading and nd != d:
                continue
            if nd == (d + 2) % 4:
                continue
            nx, ny = x + DX[nd], y + DY[nd]
            n = (nx, ny)
            ent = entries.get((n, nd))
            if ent is not None:
                hn, nex, via, ug, content, ok, kind = ent
                lanes = sp.merge(via, nd, hn, ug, (L, R), content)
                if lanes is not None and all(ok >> ln & 1 for ln in (0, 1)
                                             if lanes[ln] == me and content[ln] != me):
                    cost = gs + (0.0 if kind == 0 else k["ride"])
                    _push(heap, g, parent, (nx, ny, hn, nex, lanes[0], lanes[1]), st,
                          ATTACH if kind == 0 else ENTER, cost, hh)
            elif not blocked(n):
                step = k["belt"] + (k["turn"] if nd != d else 0.0)
                cost = gs + step
                if soft:
                    cost += soft.get(n, 0.0)
                _push(heap, g, parent, (nx, ny, nd, 0, L, R), st, STEP, cost, hh)
                # a stub: the next belt across, with an empty belt behind it, so this one
                # side-loads it (both lanes onto the near lane)
                for hn in ((nd + 1) % 4, (nd + 3) % 4):
                    b = (nx - DX[hn], ny - DY[hn])
                    if blocked(b) or b in fixed_tiles:
                        continue
                    lanes = sp.merge(_VIA["side"], nd, hn, 1, (L, R), (EMPTY, EMPTY))
                    if lanes is None:
                        continue
                    cost = gs + 2 * k["belt"]
                    if soft:
                        cost += soft.get(n, 0.0) + soft.get(b, 0.0)
                    _push(heap, g, parent, (nx, ny, hn, 0, lanes[0], lanes[1]), st, STUB, cost, hh)
            if ex or nd != d:
                continue
            seen_block = False
            for j in jumps:
                mx, my = x + DX[d] * (j - 1), y + DY[d] * (j - 1)
                if (mx, my) in fixed_tiles:
                    break
                if blocked((mx, my)):
                    seen_block = True
                tx, ty = x + DX[d] * j, y + DY[d] * j
                span = {(x + DX[d] * q, y + DY[d] * q) for q in range(j + 1)}
                if span & grid.spans[d % 2] or span & tspans[d % 2]:
                    break
                if seen_block and not blocked((tx, ty)):
                    cost = gs + k["ug"]
                    if soft:
                        cost += soft.get((tx, ty), 0.0)
                    _push(heap, g, parent, (tx, ty, d, 1, L, R), st, JUMP, cost, hh)
    return None


def _tiles_apart(path):
    """No two pieces of ``path`` on one tile: its states' tiles and the stubs' (the empty belt
    behind a state a stub side-load reached)."""
    tiles = [(p[0], p[1]) for p, _how in path]
    tiles += [(p[0] - DX[p[2]], p[1] - DY[p[2]]) for p, how in path if how == STUB]
    return len(set(tiles)) == len(tiles)


def _push(heap, g, parent, st, prev, how, cost, hh):
    if cost < g.get(st, INF):
        g[st] = cost
        parent[st] = (prev, how)
        heapq.heappush(heap, (cost + hh(st[0], st[1]), -cost, st))


def _trace(parent, st):
    """[(state, how it was reached)] from the start (how -1) to ``st``."""
    out = []
    while True:
        p = parent[st]
        if p is None:
            out.append((st, -1))
            break
        out.append((st, p[1]))
        st = p[0]
    out.reverse()
    return out


# -- the native kernel (optional) -------------------------------------------------------------------
def native_on():
    """True when the leg runs in fkroute (its ``lane_astar``, and FK_NATIVE is not 0)."""
    return steiner._native is not None and hasattr(steiner._native, "lane_astar") \
        and os.environ.get("FK_NATIVE", "1") != "0"


def _leg_native(sp, starts, targets, limit):
    ng = steiner._native_grid(sp.tree.grid)
    if ng is None:
        return steiner._UNSUPPORTED
    goals = sp.goals
    sinks = []
    for i, gl in enumerate(goals):
        if isinstance(gl, Fixed):
            need = sp.needs[i]
            sinks.append((0, gl.tile[0], gl.tile[1], gl.edir, need[0], need[1]))
        else:
            x0, y0, x1, y1 = gl.rect
            sinks.append((1, x0, y0, x1, y1, 0))
    entries = [(t, s, e[0], e[1], e[2], e[3], e[4][0], e[4][1], e[5], e[6])
               for (t, s), e in sp.entries.items()]
    hops = [(t, u, via, hn, ug, ex, ln[0], ln[1]) for t, rows in sp.hops.items()
            for u, via, hn, ug, ex, ln in rows]
    leaves = list(sp.leaves.items())
    table = [(via, s, d, ug, list(edges), blocked)
             for via, s, d, ug, edges, blocked in sp.table["moves"]]
    k = sp.k

    def tap_goal(i, path):
        return _tap_goal(sp, i, [tuple(p) for p in path])
    got = steiner._native.lane_astar(
        ng, list(sp.extra), list(sp.tspans[0]), list(sp.tspans[1]), list(starts), entries,
        sorted(sp.hops), hops, leaves, sinks, list(targets), sorted(sp.attach_tiles),
        sorted(sp.no_turn), sorted(sp.taken), int(sp.me), table, (float(k["belt"]), float(k["turn"]), float(k["ug"]), float(k["ride"]),
                int(k["max_ug"]), float(sp.hscale)),
        int(limit), tap_goal)
    if got is None:
        return None
    path, i, gs = got
    return [(tuple(p), how) for p, how in path], i, gs


def _leg(sp, starts, targets, limit=60000):
    mode = os.environ.get("FK_NATIVE", "1")
    if native_on():
        try:
            got = _leg_native(sp, starts, targets, limit)
        except (TypeError, OverflowError):
            got = steiner._UNSUPPORTED
        if got is not steiner._UNSUPPORTED:
            if mode == "check":
                py = _leg_py(sp, starts, targets, limit)
                if py != got:
                    raise AssertionError(f"fkroute.lane_astar differs from _leg_py: {got!r} != {py!r}")
            return got
    return _leg_py(sp, starts, targets, limit)


# -- starts and attaching ------------------------------------------------------------------------------
def _ring(rect, r):
    """[(q, g)] the tiles ``r`` away round ``rect`` with the heading g from q into it."""
    x0, y0, x1, y1 = rect
    out = []
    for g in range(4):
        for p in [(x, y) for x in range(x0, x1) for y in range(y0, y1)]:
            q = (p[0] - DX[g] * r, p[1] - DY[g] * r)
            if not (x0 <= q[0] < x1 and y0 <= q[1] < y1) and (q, g) not in out:
                out.append((q, g))
    return out


def _driver_starts(tree, sp, driver, inserters=("inserter", "long-handed-inserter")):
    """The start states of a driver not yet in the tree: a belt end ``("start", tile, h, (L,
    R))`` as it stands, or a machine ``("source", key, rect)``: an inserter on a free tile beside
    it dropping onto a new belt (any heading, the lane the table gives) or onto a belt of the tree
    or a host (the lane by drop_lane or turn_drop_lane; at once an attachment). -> [(state6, g0,
    how)]."""
    k, me = tree.costs, tree.me
    out = []
    if driver[0] == "start":
        _k, tile, h, lanes = driver
        out.append(((tile[0], tile[1], h, 0, lanes[0], lanes[1]), 0.0, ("start", tile, h, lanes)))
        return out
    _k, key, rect = driver
    preds = tree.preds()
    stem = tree.stem() if sp.attach_tiles else set()
    for name in inserters:
        r = 2 if name == "long-handed-inserter" else 1
        hand = k["long_tap"] if r == 2 else k["hand"]
        for q, g in _ring(rect, r):
            if not tree.free(q) or q in sp.hosts or q in sp.leaves:
                continue
            t = (q[0] - DX[g] * r, q[1] - DY[g] * r)
            ddir = (g + 2) % 4
            own = [s for s in tree.tiles().get(t, ()) if isinstance(s, tuple)]
            if own:
                s = own[0]
                if s not in stem:
                    continue
                li = _LI[tree.drop_lane_at(s, q, preds)]
                if tree.lanes.get(s, (EMPTY, EMPTY))[li] not in (EMPTY, me):
                    continue
                trial = tree.copy()
                trial.drops.append((q, name, g, key, t))
                trial.touch()
                if not (trial.propagate() and trial.goals_ok(sp.goals)):
                    continue
                new = trial.lanes[s]
                out.append(((s[0], s[1], s[2], s[3], new[0], new[1]), hand,
                            ("drop_attach", q, name, g, key, t)))
                continue
            host = sp.hosts.get(t)
            if host is not None:
                if host.kind == "splitter" or t not in sp.host_ok:
                    continue
                li = _LI[phys.drop_lane(ddir * 4, host.heading * 4)]
                if host.lanes[li] not in (EMPTY, me) or not sp.host_ok[t] >> li & 1:
                    continue
                new = list(host.lanes)
                new[li] = me
                ex = 1 if host.kind == "ug_out" else 0
                out.append(((t[0], t[1], host.heading, ex, new[0], new[1]), hand + k["ride"],
                            ("drop_host", q, name, g, key, t)))
                continue
            if tree.grid.blocked(t) or t in sp.extra:
                continue
            for h in range(4):
                if (t[0] + DX[h], t[1] + DY[h]) == q:
                    continue
                li = _LI[phys.drop_lane(ddir * 4, h * 4)]
                lanes = [EMPTY, EMPTY]
                lanes[li] = me
                out.append(((t[0], t[1], h, 0, lanes[0], lanes[1]), hand + k["belt"],
                            ("drop", q, name, g, key, t)))
    return out


def _tree_starts(tree):
    """Where the next forward leg may leave the tree: a leaf (own or riding) for free, or a
    splitter cut into a straight own belt (steiner's ``_starts``; a splitter keeps the lanes)."""
    k = tree.costs
    out = []
    side_into = {mv[1] for mv in tree.succ.values() if mv[0] == "side"}
    for s in tree.states():
        mv = tree.succ.get(s)
        ln = tree.lanes.get(s, (EMPTY, EMPTY))
        if mv is None and (s not in tree.sink_at or not tree.terminal.get(s, True)):
            out.append(((s[0], s[1], s[2], s[3], ln[0], ln[1]), 0.0, ("leaf", s)))
        if mv is None or mv[0] != "step" or s in tree.rides:
            continue
        c = mv[1]
        d = c[2]
        cm = tree.succ.get(c)
        if c[3] or cm is None or cm[0] != "step" or cm[1][2] != d or c in tree.sink_at or \
                c in side_into or c in tree.roots or cm[1] in side_into or cm[1] in tree.rides:
            continue
        if s[2] != d:
            continue
        for side in (1, 3):
            n, m = steiner.Tree.split_tiles(s, side)
            o2 = (m[0] + DX[d], m[1] + DY[d])
            if tree.free(m) and tree.free(o2):
                lc = tree.lanes.get(c, ln)
                out.append(((o2[0], o2[1], d, 0, lc[0], lc[1]), k["split"] - k["belt"],
                            ("split", s, side, c)))
    return out


def _attach(tree, path, how, goal_i, goals, entries, tapped=None, hops=None):
    """The tree with ``path`` [(state6, the move that reached it)] laid from ``how`` (a start)
    to its end (goal ``goal_i``, or -1: an attachment into the tree; a tap met on a tile in
    ``tapped`` [goal_i] shares another net's inserter). -> the new tree, or None when the lanes
    as propagated break a goal or lose the net's items."""
    hops = hops or {}
    t = tree.copy()
    first = path[0][0][:4]
    kind = how[0]
    if kind == "split":
        _k, s, side, c = how
        nxt = t.succ.pop(c)
        t.succ[s] = ("split", side, nxt[1], first)
    elif kind == "start":
        t.roots[first] = (tuple(how[3]), ("start", how[2]))
    elif kind == "drop":
        _k, q, name, g, key, tile = how
        li = _LI[phys.drop_lane(((g + 2) % 4) * 4, first[2] * 4)]
        init = [EMPTY, EMPTY]
        init[li] = t.me
        t.roots[first] = (tuple(init), ("drop", q))
        t.drops.append((q, name, g, key, tile))
        t.reserved.add(q)
    elif kind in ("drop_attach", "drop_host"):
        _k, q, name, g, key, tile = how
        t.drops.append((q, name, g, key, tile))
        t.reserved.add(q)
        if kind == "drop_host":            # a ride that begins with a drop: a root of its own
            t.rides.add(first)
            t.lanes[first] = path[0][0][4:]
            t.roots[first] = (path[0][0][4:], ("drop_host", q))
    for (a6, _m), (b6, mv) in zip(path, path[1:]):
        a, b = a6[:4], b6[:4]
        if mv == STEP:
            t.succ[a] = ("step", b)
        elif mv == JUMP:
            t.succ[a] = ("jump", b)
        elif mv == STUB:
            stub = (b[0] - DX[b[2]], b[1] - DY[b[2]], b[2], 0)
            t.roots[stub] = ((EMPTY, EMPTY), ("stub",))
            t.succ[stub] = ("step", b)
            t.succ[a] = ("side", b)
        elif mv == ENTER:
            t.succ[a] = ("enter", b)
            t.rides.add(b)
            t.lanes[b] = b6[4:]
            src = _towards(a, b)
            e = entries[((b[0], b[1]), src)]
            t.ride_edges[b] = (e[2], src, e[0], e[3], e[4])
        elif mv == RIDE:
            was = t.succ.get(a)
            t.succ[a] = ("ride2", was[1], b) if was is not None and was[0] == "ride" \
                and was[1] != b else ("ride", b)
            t.rides.add(b)
            t.lanes[b] = b6[4:]
            hop = next(h for h in hops[(a[0], a[1])] if h[0] == (b[0], b[1]) and h[2] == b[2])
            t.ride_edges[b] = (hop[1], a[2], hop[2], hop[3], hop[5])
        elif mv == LEAVE:
            t.succ[a] = ("step", b)
        elif mv == ATTACH:
            # the tree's own state on that tile (the entry state carries the belt's heading)
            b = next(o for o in t.tiles().get((b[0], b[1]), ()) if isinstance(o, tuple))
            if a in t.rides:
                continue
            e = entries.get(((b[0], b[1]), _towards(a, b)))
            t.succ[a] = ("step", b) if e is not None and e[2] == _VIA["straight"] else ("side", b)
    end = path[-1][0][:4]
    if goal_i >= 0:
        goal = goals[goal_i]
        t.sink_at[end] = goal_i
        t.terminal[end] = isinstance(goal, Fixed)
        if isinstance(goal, Fixed):
            if end not in t.rides:
                t.edir_at[end] = goal.edir
        elif (end[0], end[1]) not in (tapped or {}).get(goal_i, ()):
            got = goal._sink.pick([p[:4] for p, _h in path], t)
            t.touch()
            t.taps += got
            t.reserved |= {g[0] for g in got}
    t.touch()
    if not t.propagate() or not t.goals_ok(goals):
        return None
    return t


# -- the whole job --------------------------------------------------------------------------------------
class Result:
    def __init__(self, trees, order, cost, log, problems, seconds):
        self.trees, self.order, self.cost = trees, order, cost
        self.log, self.problems, self.seconds = log, problems, seconds

    def entities(self, job):
        out = []
        for me, tree in self.trees.items():
            out += tree.entities(net=job.nets[me - 1])
        return out

    def shared(self):
        """[(net id, tiles)] what each net rides."""
        return [(me, tree.shared()) for me, tree in self.trees.items() if tree.shared()]

    def key(self):
        return [(me, t.key()) for me, t in sorted(self.trees.items())]


def _extend_rides(tree, sp, left):
    """Ride states for wherever the net's items flow on along the hosts past its rides (a
    splitter's other output, the chain beyond a goal met mid-way), by the hops' moves; a goal
    in ``left`` they arrive at is met. -> the goals met."""
    met = []
    todo = sorted(tree.rides)
    while todo:
        s = todo.pop()
        held = tree.lanes[s]
        mv = tree.succ.get(s)
        if mv is not None and mv[0] not in ("ride", "ride2"):
            continue                                  # it leaves the host there
        for nt, via, hn, ug, nex, content in sp.hops.get((s[0], s[1]), ()):
            ns = (nt[0], nt[1], hn, nex)
            if ns in tree.rides:
                continue
            got = _merge(tree.moves, via, s[2], hn, ug, held, content, tree.me)
            if got is None:
                continue
            mv = tree.succ.get(s)
            if mv is None:
                tree.succ[s] = ("ride", ns)
            elif mv[0] == "ride":
                tree.succ[s] = ("ride2", mv[1], ns)
            else:
                continue
            tree.rides.add(ns)
            tree.lanes[ns] = got
            tree.ride_edges[ns] = (via, s[2], hn, ug, content)
            todo.append(ns)
            for i in left:
                if i in met:
                    continue
                g = sp.goals[i]
                if isinstance(g, Fixed):
                    hit = nt == g.tile and hn != (g.edir + 2) % 4 and (not nex or hn == g.edir) \
                        and lanes_ok(sp.needs[i], got[0], got[1], tree.me)
                else:
                    hit = nt in sp.tapped.get(i, ()) and tree.me in got and not set(got) & g.reject
                if hit:
                    tree.sink_at[ns] = i
                    tree.terminal[ns] = isinstance(g, Fixed)
                    met.append(i)
    return met


def _spec(tree, hosts, goals, table, attach, met, tapped=None):
    taken = set(tree.tiles()) | tree.ride_tiles()
    entries = _host_entries(hosts, tree.me, goals, met, taken)
    if attach:
        entries.update(_tree_entries(tree, goals))
    leaves = {h.leave: t for t, h in hosts.items() if h.leave is not None and h.leave not in taken}
    return _Spec(tree, hosts, goals, entries, _hops(hosts), leaves, table, attach, (), tapped)


def _route_net(grid, job, me, hosts, met, costs, limit, log, table, blocked=(), tapped=None):
    """One net's tree over ``hosts``: consumers first (forward legs from the first driver), then
    every other driver attached; ``blocked`` the job's other inserters, ``tapped`` {goal: tiles}
    where they pick. -> (tree, problems)."""
    tree = LaneTree(grid, me, costs, table)
    # the job's other inserters, the tile ahead of every belt end (its consumer's own belt), the
    # other nets' belt ends and the ends of the goals this net has no part in
    tree.blocked_extra = set(blocked) | {_step(g.tile, g.edir) for g in job.goals
                                         if isinstance(g, Fixed)}
    tree.blocked_extra |= {t for other, rows in job.starts.items() if other != me
                           for t, _h, _ln in rows}
    tree.blocked_extra |= {g.tile for g in job.goals if isinstance(g, Fixed) and me not in g.nets}
    name = job.nets[me - 1]
    drivers = [("start", t, h, ln) for t, h, ln in job.starts.get(me, ())] + \
        [("source", key, rect) for key, rect in job.sources.get(me, ())]
    # the net's own later drivers' belt ends: theirs until they attach
    tree.blocked_extra |= {d[1] for d in drivers[1:] if d[0] == "start"}
    goals = job.goals
    left = job.goals_of(me)
    problems = []
    if not drivers:
        return tree, [f"{name}: no driver"]
    first = True
    tree.pending = len(drivers) > 1
    while left:
        sp = _spec(tree, hosts, goals, table, False, met, tapped)
        rows = _driver_starts(tree, sp, drivers[0]) if first else _tree_starts(tree)
        starts = [(st, g0) for st, g0, _how in rows]
        hows = {st: how for st, g0, how in rows}
        sp.no_turn = {st for st, _g0, how in rows if how[0] == "drop"}
        if not starts:
            problems.append(f"{name}: nowhere to start from")
            break
        got = _leg(sp, starts, left, limit)
        if got is None:
            problems.append(f"{name}: cannot reach {[goals[i].name for i in left]}")
            log.append(problems[-1])
            break
        path, i, gcost = got
        new = _attach(tree, path, hows[path[0][0]], i, goals, sp.entries, tapped, sp.hops)
        if new is None:
            problems.append(f"{name}: the lanes break at {goals[i].name}")
            log.append(problems[-1])
            break
        tree, first = new, False
        left.remove(i)
        log.append(f"{name}: +{goals[i].name} ({gcost:.2f})")
        for j in _extend_rides(tree, sp, left):
            left.remove(j)
            log.append(f"{name}: +{goals[j].name} (carried on)")
    for n_drv, drv in enumerate(drivers[1:]):
        if first:
            break
        tree.pending = n_drv + 2 < len(drivers)
        if drv[0] == "start":
            tree.blocked_extra = tree.blocked_extra - {drv[1]}
        sp = _spec(tree, hosts, goals, table, True, met, tapped)
        rows = _driver_starts(tree, sp, drv)
        starts = [(st, g0) for st, g0, _how in rows]
        hows = {st: how for st, g0, how in rows}
        sp.no_turn = {st for st, _g0, how in rows if how[0] == "drop"}
        label = drv[1] if drv[0] == "source" else f"the belt at {drv[1][0]},{drv[1][1]}"
        if not starts:
            problems.append(f"{name}: {label} has no way out")
            continue
        got = _leg(sp, starts, job.goals_of(me), limit)
        if got is None:
            problems.append(f"{name}: {label} cannot reach the net")
            log.append(problems[-1])
            continue
        path, i, gcost = got
        new = _attach(tree, path, hows[path[0][0]], i, goals, sp.entries, tapped, sp.hops)
        if new is None:
            problems.append(f"{name}: {label} breaks the lanes")
            continue
        tree = new
        log.append(f"{name}: {label} joins ({gcost:.2f})")
        _extend_rides(tree, sp, [])
    tree.pending = False
    if not first and not tree.goals_ok(goals, strict=True):
        short = [goals[i].name for s, i in tree.sink_at.items()
                 if not tree.copy().goals_ok(goals, strict=True)]
        problems.append(f"{name}: its drivers do not fill the lanes {sorted(set(short))} ask")
    return tree, problems


def route(grid, job, hosts=(), costs=None, limit=60000, orders=None):
    """Route ``job`` on ``grid`` (a steiner Grid: the ground; the hosts' tiles blocked in it or
    not), ``hosts`` [(tile, heading, kind, (L, R))] the standing carriers (their lanes as ids:
    FOREIGN for another design's, the job's ids where a net of the job already stands). Every
    order of the job's nets (``orders``: a list of id tuples to try instead; at most 6), each net
    a tree over the ones before it; the cheapest result with the fewest problems. -> Result."""
    t0 = time.time()
    table = phys.table()
    ids = job.ids()
    if orders is None:
        orders = list(itertools.permutations(ids))[:6]
    best = None
    for order in orders:
        log, problems, trees = [], [], {}
        items = list(hosts)
        met, behind, blocked, tapped = {}, {}, set(), {}
        for me in order:
            hs = build_hosts(items, lambda t: not grid.blocked(t), behind=behind) if items else {}
            tree, probs = _route_net(grid, job, me, hs, met, costs, limit, log, table, blocked,
                                     tapped)
            trees[me] = tree
            problems += probs
            riders = {(s[0], s[1]): tree.lanes.get(s, (EMPTY, EMPTY)) for s in tree.rides}
            items = [(t, h, k, riders.get(t, ln)) for t, h, k, ln in items] + tree.hosts()
            behind.update(tree.behind())
            blocked |= {q for q, *_r in tree.taps + tree.drops}
            for s, i in tree.sink_at.items():
                if isinstance(job.goals[i], Fixed):
                    met[(s[0], s[1])] = i
                else:
                    tapped.setdefault(i, set()).add((s[0], s[1]))
        cost = round(sum(t.cost() for t in trees.values()), 3)
        key = (len(problems), cost)
        if best is None or key < best[0]:
            best = (key, Result(trees, tuple(order), cost, log, problems, 0.0))
    res = best[1]
    res.seconds = round(time.time() - t0, 3)
    return res
