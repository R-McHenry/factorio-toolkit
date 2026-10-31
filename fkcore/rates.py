"""fkcore.rates: the nominal rate model of a flat netlist (V1: logical nets, no capacity).

The unit is the net, as in C:\\fk-lead\\repo\\fkc\\flow.py: every net balances, per item, what its
drivers make against what its consumers ask. Here a net is a logical object (CORE.md), so there is
nothing to collapse: a splitter, a side-load or an underground is route, never a node of the model.
That is what closes the "spine undervalued" finding of BASE-MODEL.md by construction.

Every machine runs at a utilization ``u`` (0..1): the smallest of its duty and the **grants** of
its nets, one grant per endpoint. Per net and item:

- **Consumer side.** The drivers can make S = sum of full-speed rate x their potential (what
  everything except this net allows them). The consumers would take A = sum of full-speed need x
  their potential (duty included). If A fits in S, every consumer is granted full speed. If not, the
  net is **short** and is shared **in proportion to appetite** by water-filling: every consumer
  runs at the same fraction L of its duty (its appetite is need x duty), and a consumer limited
  elsewhere below that takes only what it can use, leaving the rest to the others.
  (``share="level"`` drops the duty weighting: every consumer gets the same utilization, so a
  low-duty machine with a big full-speed appetite, a mall cell, takes most of a short net.) A
  machine drawing one item from k nets asks 1/k of its need from each.
- **Producer side, the mirror.** The consumers can take A = sum of full-speed need x their
  potential, plus what the sinks take (a chest, lab or turret takes what is left, up to its
  ``rate``; a sushi sink's rate is split over its items by full-speed supply, except a lab's,
  which caps each pack it is fed). If A < S, the drivers are slowed the same way: the same
  fraction of their duty, water-filled.
- What-if: ``unbounded=[net, ...]`` treats those nets' supply as unlimited (their drivers then run
  at what the consumers take), which is how a hand calc isolates one part of a factory.
- An input with no net, or an output with no net, stops the machine (no-feed / no-taker say so).

Each side is judged against the other side's potential, not its throttled state; judging both
sides by the current state (as flow.py does) has a fixed point at every S = D, so a consumer and
its producer can each blame the other and stay low. The grants are a damped fixed point from
"everything at full speed": deterministic, stdlib only. The result names, per machine, the
endpoint that bound it, and per net and item the supply, demand, what sinks took and the surplus.

**A bus is a pool** (Rory's bus, ``Bus<...>``): what the loads bring is what the taps share. Its
ports pass on what reaches them, so the nets into its loads, its own net and the nets out of its
taps are solved as one net of its item, named as the bus (two buses a net joins are one pool):
every machine that drives one of them drives the pool, every one that takes from one takes from
the pool, shared by appetite like any net. The bus's row is the pool's; each net it absorbed gets
a row of its own from the same utilizations, its ports passing the balance on (a load's net
delivers what its drivers make, a tap's net what its consumers take). No capacity, as everywhere
in V1: the routed rates know what the bus's belts carry.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Model", "solve", "report"]

INF = float("inf")
DAMPING = 0.5


@dataclass
class NetItem:
    net: str
    item: str
    supply: float = 0.0
    demand: float = 0.0
    need_full: float = 0.0
    sink_cap: float = 0.0
    to_sinks: float = 0.0
    delivered: float = 0.0
    full_make: float = 0.0
    unbounded: bool = False
    can_make: float = 0.0              # what the drivers could make at their potential
    can_take: float = 0.0              # what the consumers + sinks would take at their potential
    would_take: float = 0.0            # the same without the sinks (the finite consumers' appetite)


@dataclass
class Model:
    flat: object
    util: dict                         # machine key -> utilization
    binding: dict                      # machine key -> (kind, item, net) or None
    nets: dict                         # (net, item) -> NetItem
    passes: int
    residual: float
    asserts: list = field(default_factory=list)   # [(text, ok, value, target, unit)]
    sink_share: dict = field(default_factory=dict)  # (sink key, net, item) -> its cap there
    pools: dict = field(default_factory=dict)     # (net, item) -> its bus pool's (net, item)
    ends: dict = field(default_factory=dict)      # (net, item) as solved -> drivers, consumers

    def rate(self, key, item):
        """Items/s machine ``key`` makes of ``item``; for a bus port, what passes through it."""
        m = self.flat.machines[key]
        if m.extra.get("port"):
            return self.port_rate(key)
        return m.makes.get(item, 0.0) * self.util[key]

    def port_rate(self, key):
        """Items/s through a bus port: what its net delivers into a load, or out of a tap."""
        m = self.flat.machines[key]
        item = m.extra["item"]
        hold = self.flat._in_hold if m.extra["port"] == "load" else self.flat._out_hold
        nets = [n for n in hold.get((key, item), ()) if n != m.inst]
        return self.nets[(nets[0], item)].delivered if nets else 0.0

    def inst_rate(self, path, item=None):
        inst = self.flat.insts[path]
        if inst.kind == "Bus":                # what passes through the pool
            return self.nets[(path, inst.params.get("item"))].delivered
        item = item or primary(self.flat, inst.machines)
        return sum(self.rate(k, item) for k in inst.machines)


def primary(flat, keys):
    for k in keys:
        makes = flat.machines[k].makes
        if makes:
            return next(iter(makes))
    return None


def _pools(flat):
    """{(net, item): (pool net, item)} for every net a port joins. A port passes on what reaches
    it, so its nets are one: the nets into a bus's loads, the bus's own net, the nets out of its
    taps, any bus a net joins to them, and the two nets of a sealed module's port (2.0.28: the
    inside one and the one outside that names it). The pool is named as its first bus."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    holds = (getattr(flat, "_in_hold", {}), getattr(flat, "_out_hold", {}))
    for key, m in flat.machines.items():
        if not m.extra.get("port"):
            continue
        for item in m.extra.get("items") or [m.extra["item"]]:
            nets = [n for hold in holds for n in hold.get((key, item), ())]
            for n in nets:
                parent[find((n, item))] = find((nets[0], item))
    groups = {}
    for ni in list(parent):
        groups.setdefault(find(ni), []).append(ni)
    out = {}
    for members in groups.values():
        buses = sorted(n for n, _i in members if _is_bus(flat, n))
        name = buses[0] if buses else min(n for n, _i in members)
        for ni in members:
            out[ni] = (name, ni[1])
    return out


def _is_bus(flat, net):
    """A Bus's own net (it is named as the instance)."""
    inst = flat.insts.get(net)
    return inst is not None and inst.kind == "Bus"


def _structure(flat, pools=None):
    """(ends, feeds, outs) as the model solves them: the nets a bus joins are one pool, its
    ports left out (``_pools``)."""
    pools = pools or {}
    ends = {}                          # (net, item) -> {"drivers": [k], "consumers": [k]}
    feeds, outs = {}, {}
    for name, net in flat.nets.items():
        for item in net.items:
            ends.setdefault(pools.get((name, item), (name, item)),
                            {"drivers": [], "consumers": []})
        for side, rows, table in (("drivers", net.drivers, outs),
                                  ("consumers", net.consumers, feeds)):
            for key, item in rows:
                if flat.machines[key].extra.get("port"):
                    continue
                ni = pools.get((name, item), (name, item))
                if ni != (name, item) and key in ends[ni][side]:
                    continue                # on two nets of one pool: in it once
                ends[ni][side].append(key)
                table.setdefault((key, item), []).append(ni[0])
    return ends, feeds, outs


def waterfill(pairs, total):
    """The level L with sum(w * min(cap, L)) == total over ``pairs`` [(w, cap)]; INF if it all fits."""
    if total == INF:
        return INF
    if sum(w * c for w, c in pairs) <= total + 1e-15:
        return INF
    if total <= 0:
        return 0.0
    pairs = sorted(pairs, key=lambda p: p[1])
    rest = sum(w for w, _c in pairs)
    used = 0.0
    for w, cap in pairs:
        level = (total - used) / rest if rest > 0 else INF
        if level <= cap:
            return level
        used += w * cap
        rest -= w
    return INF


def _grant(rows, total, share):
    """Grants when ``total`` is shared over ``rows`` [(full-speed rate, potential, duty)].

    The level is water-filled in units of each row's duty (``share="appetite"``) or of plain
    utilization (``share="level"``); either way a row limited elsewhere keeps only its potential.
    """
    if total == INF or sum(w * c for w, c, _d in rows) <= total + 1e-15:
        return [1.0] * len(rows)
    if share == "level":
        level = min(1.0, waterfill([(w, c) for w, c, _d in rows], total))
        return [level] * len(rows)
    pairs = [(w * d, c / d) for w, c, d in rows if d > 0]
    level = waterfill(pairs, total)
    return [1.0 if level == INF else min(1.0, level * d) for _w, _c, d in rows]


def _lines(flat, pools, ends):
    """{pool: (root net, tree)} for each pool that runs along a Stack's cells (2.1): a belt that
    passes a cell's machines before it crosses into the next cell (a ``stack`` pair's out port,
    ``flat.chain``), so on a short line the cells upstream take what they need and the last ones
    get what is left. Both of the 20261030 run's lab lines (Stacks of FurnacePair) ran their last
    cell at half while the model shared the shortfall over all 24 furnaces (96% each).

    The tree's nodes are the pool's nets, joined through its ports; ``tree[net]`` is (its
    consumers, its children across a chain port, its other children). Only a pool fed at one
    root net, by every driver it has, whose nets form a tree, gets one: any other pool is shared
    by appetite as before."""
    chain = getattr(flat, "chain", set())
    if not chain:
        return {}
    holds = (getattr(flat, "_in_hold", {}), getattr(flat, "_out_hold", {}))
    members = {}
    for ni, pk in pools.items():
        members.setdefault(pk, []).append(ni)
    out = {}
    for pk, nis in members.items():
        item = pk[1]
        names = {n for n, _i in nis}
        if any(_is_bus(flat, n) for n in names):
            continue
        edges, is_chain = [], False
        for key, m in flat.machines.items():
            if not m.extra.get("port") or key not in flat.ports:
                continue
            ins = [n for n in holds[0].get((key, item), ()) if n in names]
            outs = [n for n in holds[1].get((key, item), ()) if n in names]
            c = key in chain and flat.ports[key].dir == "out"
            for a in ins:
                for b in outs:
                    edges.append((a, b, c))
                    is_chain = is_chain or c
        if not is_chain:
            continue
        parent = {}
        for a, b, _c in edges:
            if b in parent:
                parent = None
                break
            parent[b] = a
        if parent is None:
            continue
        roots = names - set(parent)
        if len(roots) != 1:
            continue
        root = roots.pop()
        if not set(ends[pk]["drivers"]) <= {k for k, i in flat.nets[root].drivers if i == item}:
            continue                    # fed along the line too: no order to serve it in
        tree = {n: ([], [], []) for n in names}
        for a, b, c in edges:
            tree[a][1 if c else 2].append(b)
        seen, todo, placed = set(), [root], set()
        while todo:
            n = todo.pop(0)
            if n in seen:
                continue
            seen.add(n)
            for k, i in flat.nets[n].consumers:
                if i == item and k not in placed and not flat.machines[k].extra.get("port"):
                    tree[n][0].append(k)
                    placed.add(k)
            todo += tree[n][1] + tree[n][2]
        if seen != names:
            continue
        out[pk] = (root, tree)
    return out


def _in_order(cons, total, share, line):
    """Grants for ``cons`` [(key, rate, potential, duty)] on a pool that runs along a line
    (``_lines``): at each net its consumers and the branches it feeds share what reaches it by
    appetite, as on any net, and what they leave passes on into the next cell."""
    root, tree = line
    at = {row[0]: i for i, row in enumerate(cons)}
    if any(k not in at for n in tree for k in tree[n][0]) or \
            len(at) != sum(len(t[0]) for t in tree.values()):
        return _grant([r[1:] for r in cons], total, share)
    out = [1.0] * len(cons)
    want = {}

    def appetite(n):
        if n not in want:
            rows, chained, other = tree[n]
            want[n] = sum(cons[at[k]][1] * cons[at[k]][2] for k in rows) + \
                sum(appetite(b) for b in chained + other)
        return want[n]

    def give(n, total):
        if total == INF or total >= appetite(n) - 1e-15:
            return
        rows, chained, other = tree[n]
        level = [cons[at[k]][1:] for k in rows] + [(appetite(b), 1.0, 1.0) for b in other]
        grants = _grant(level, total, share)
        used = 0.0
        for k, g in zip(rows, grants):
            out[at[k]] = g
            used += cons[at[k]][1] * min(g, cons[at[k]][2])
        for b, g in zip(other, grants[len(rows):]):
            got = min(g, 1.0) * appetite(b)
            used += got
            give(b, got)
        left = max(0.0, total - used)
        if len(chained) == 1:
            give(chained[0], left)
        elif chained:
            for b, g in zip(chained, _grant([(appetite(b), 1.0, 1.0) for b in chained], left,
                                            share)):
                give(b, min(g, 1.0) * appetite(b))

    give(root, total)
    return out


def solve(flat, passes=50000, tol=1e-12, share="appetite", unbounded=()) -> Model:
    if share not in ("appetite", "level"):
        raise ValueError(f"share must be appetite or level, got {share!r}")
    unknown = sorted(set(unbounded) - set(flat.nets))
    if unknown:
        raise ValueError("unbounded names no net: " + ", ".join(unknown))
    pools = _pools(flat)
    unbounded = set(unbounded) | {pk[0] for ni, pk in pools.items() if ni[0] in unbounded}
    ends, feeds, outs = _structure(flat, pools)
    machines = flat.machines
    lines = _lines(flat, pools, ends)

    # A sink's rate cap, split over the (net, item) endpoints it sits on by full-speed supply.
    full_make = {}
    for ni, e in ends.items():
        total = 0.0
        for k in e["drivers"]:
            total += machines[k].makes.get(ni[1], 0.0) / len(outs[(k, ni[1])])
        full_make[ni] = total
    sink_share = {}
    for k, m in machines.items():
        if not m.sink:
            continue
        mine = [(n, item) for (kk, item), ns in feeds.items() if kk == k for n in ns]
        if m.drain is None or m.extra.get("each"):
            for ni in mine:
                sink_share[(k,) + ni] = INF if m.drain is None else m.drain
            continue
        weights = [full_make.get(ni, 0.0) for ni in mine]
        finite = [w for w in weights if w != INF]
        total = sum(finite)
        for ni, w in zip(mine, weights):
            if w == INF or total <= 0:
                sink_share[(k,) + ni] = m.drain / len(mine)
            else:
                sink_share[(k,) + ni] = m.drain * w / total

    stats = {ni: NetItem(*ni, full_make=full_make[ni]) for ni in ends}

    # One grant per endpoint: (key, side, net, item) -> level. A missing net is a 0 grant.
    grants, dead = {}, {}
    for k, m in machines.items():
        if m.sink or m.source:
            continue
        for item, need in m.needs.items():
            if need <= 0:
                continue
            nets = feeds.get((k, item))
            if not nets:
                dead[k] = ("in", item, None)
            for n in nets or ():
                grants[(k, "in", n, item)] = 1.0
        for item, rate in m.makes.items():
            if rate <= 0:
                continue
            nets = outs.get((k, item))
            if not nets and k not in dead:
                dead[k] = ("out", item, None)
            for n in nets or ():
                grants[(k, "out", n, item)] = 1.0
    mine = {}
    for g in grants:
        mine.setdefault(g[0], []).append(g)

    #: 2.0.24: a machine's grants on one net travel on one belt, so judging that net must skip
    #: ALL of them, not just the one item being judged. A multi-item requester (`item="iron-ore,
    #: coal"`) driving a sushi net gave each item's grant as the other item's grant (each 2.5/3,
    #: 0.18/3), and the pair decayed geometrically to 0 over 62 passes: the model said the 1133
    #: player's smelter delivered 0.000/min and "coal not taken on feed" while CLOG had already
    #: named the real risk. Key: (machine, side, net) -> the grants on it.
    belt = {}
    for g in grants:
        belt.setdefault((g[0], g[1], g[2]), set()).add(g)

    def potential(k, skip=None):
        """What everything but the grants ``skip`` (a set, or one grant) allows machine ``k``."""
        m = machines[k]
        if m.sink or m.source:
            return 1.0
        if k in dead:
            return 0.0
        skips = skip if isinstance(skip, (set, frozenset)) else ({skip} if skip else set())
        v = m.duty
        for g in mine.get(k, ()):
            if g not in skips and grants[g] < v:
                v = grants[g]
        return v

    def measure():
        for ni, e in ends.items():
            st = stats[ni]
            item = ni[1]
            s, unb = 0.0, False
            for k in e["drivers"]:
                m = machines[k]
                if m.source:
                    unb = True
                    continue
                # 2.0.24: judged like the solver does, on this belt's own grants only (a chest
                # feeding iron-ore and coal on one belt supplies each at its rate; the coal's
                # small appetite must not cap the iron)
                s += (m.makes.get(item, 0.0) / len(outs[(k, item)])
                      * potential(k, belt.get((k, "out", ni[0]), (k, "out", ni[0], item))))
            d = nf = cap = 0.0
            for k in e["consumers"]:
                m = machines[k]
                need = m.needs.get(item, 0.0)
                if need > 0:
                    share = need / len(feeds[(k, item)])
                    d += share * potential(k, belt.get((k, "in", ni[0]), (k, "in", ni[0], item)))
                    nf += share
                elif m.sink:
                    cap += sink_share.get((k,) + ni, 0.0)
            unb = unb or ni[0] in unbounded
            st.supply = INF if unb else s
            st.unbounded = unb
            st.demand, st.need_full, st.sink_cap = d, nf, cap
            finite = min(st.supply, d)
            left = st.supply - finite if st.supply != INF else INF
            st.to_sinks = min(left, cap)
            st.delivered = finite + st.to_sinks

    sink_caps = {}
    for ni, e in ends.items():
        sink_caps[ni] = sum(sink_share.get((k,) + ni, 0.0) for k in e["consumers"]
                            if machines[k].sink and machines[k].needs.get(ni[1], 0.0) <= 0)

    residual, done = INF, 0
    for done in range(1, passes + 1):
        new = {}
        for ni, e in ends.items():
            n, item = ni
            prod, unb = [], n in unbounded
            for k in e["drivers"]:
                m = machines[k]
                if m.source:
                    unb = True
                    continue
                prod.append((k, m.makes.get(item, 0.0) / len(outs[(k, item)]),
                             potential(k, belt.get((k, "out", n), (k, "out", n, item))),
                             m.duty))
            cons = []
            for k in e["consumers"]:
                m = machines[k]
                need = m.needs.get(item, 0.0)
                if need > 0:
                    cons.append((k, need / len(feeds[(k, item)]),
                                 potential(k, belt.get((k, "in", n), (k, "in", n, item))),
                                 m.duty))
            can_make = INF if unb else sum(w * c for _k, w, c, _d in prod)
            would_take = sum(w * c for _k, w, c, _d in cons)
            can_take = would_take + sink_caps[ni]
            stats[ni].can_make, stats[ni].can_take = can_make, can_take
            stats[ni].would_take = would_take
            got = _in_order(cons, can_make, share, lines[ni]) if ni in lines else \
                _grant([r[1:] for r in cons], can_make, share)
            for row, g in zip(cons, got):
                new[(row[0], "in", n, item)] = g
            for row, g in zip(prod, _grant([r[1:] for r in prod], can_take, share)):
                new[(row[0], "out", n, item)] = g
        change = 0.0
        for g, v in new.items():
            nv = grants[g] + (v - grants[g]) * DAMPING
            change = max(change, abs(nv - grants[g]))
            grants[g] = nv
        residual = change
        if change < tol:
            break

    util, binding = {}, {}
    for k, m in machines.items():
        if m.sink or m.source:
            util[k], binding[k] = 1.0, None
            continue
        if k in dead:
            util[k], binding[k] = 0.0, dead[k]
            continue
        v, why = m.duty, (("duty", None, None) if m.duty < 1.0 else None)
        for g in mine.get(k, ()):
            if grants[g] < v - 1e-12:
                v, why = grants[g], (g[1], g[3], g[2])
        util[k], binding[k] = v, (why if v < 1.0 - 1e-9 else None)
    measure()
    nets = {}
    for name, net in flat.nets.items():
        for item in net.items:
            ni = (name, item)
            pk = pools.get(ni, ni)
            if pk == ni:
                nets[ni] = stats[ni]
            elif _is_bus(flat, name):          # a bus another bus's pool took in: the pool's
                nets[ni] = NetItem(**dict(vars(stats[pk]), net=name))
            else:
                nets[ni] = _absorbed(flat, ni, stats[pk], ends[pk], util, feeds, outs,
                                     sink_share, potential, name in unbounded)
    model = Model(flat, util, binding, nets, done, residual, sink_share=sink_share,
                  pools=pools, ends=ends)
    model.asserts = _asserts(model)
    return model


def underfed(model, margin=0.05):
    """[(net, item, can make /s, would take /s)]: a net whose drivers, at what everything else
    lets them run, make less than its consumers would take (by more than ``margin``), so they run
    below speed for it. Only where a shortage starts: a net whose drivers an input of theirs holds
    back is left to that input's own line, so one short ore patch is one line, not one per step
    down the chain. A bus pool is judged as one net.

    2.0.1 (the first lead run, 2026-10-21): copper was the short plate all run, 40/min from 4
    drills against the ~75/min red and green asked, and nothing in the design said so; the lead
    found it from the game's stats."""
    out = []
    for ni, st in sorted(model.nets.items()):
        if model.pools.get(ni, ni) != ni or st.unbounded or st.can_make == INF \
                or st.would_take <= 0 or st.can_make >= st.would_take * (1.0 - margin):
            continue
        drivers = model.ends.get(ni, {}).get("drivers", ())
        if any((model.binding.get(k) or ("",))[0] == "in" for k in drivers):
            continue
        out.append((ni[0], ni[1], st.can_make, st.would_take))
    return out


def carryover(model):
    """[(net, feed, product, sink, consumers)]: a sink at the end of a belt that brings it a
    product and also a **feed**, an item machines on the same belt upstream consume (2.0.48, Rory
    2026-10-26: "the sulfur and blue science are on the same belt which is an issue, and the toolkit
    should have noticed it too"). What those machines don't take of the feed reaches the sink with
    the product, fills it, and the belt stops for the product too. Nets joined through a port or a
    bus are one pool, so a feed that rides a stack's belt from cell to cell is seen at its end. A
    sink fed one item (the rest of a bus into a chest) is no carryover."""
    flat = model.flat
    out = []
    for name in sorted(flat.nets):
        net = flat.nets[name]
        sinks = [k for k, _i in net.consumers if flat.machines[k].sink]
        if not sinks or len(net.items) < 2:
            continue
        feeds, products = {}, set()
        for item in net.items:
            pool = model.pools.get((name, item), (name, item))
            ends = model.ends.get(pool, {})
            takers = [k for k in ends.get("consumers", ())
                      if not flat.machines[k].sink and flat.machines[k].needs.get(item, 0) > 0]
            if takers:
                feeds[item] = takers
            if any(flat.machines[k].makes.get(item, 0) > 0 for k in ends.get("drivers", ())):
                products.add(item)
        for item, takers in sorted(feeds.items()):
            for product in sorted(products - {item}):
                for sink in dict.fromkeys(sinks):
                    if _filtered_out(flat, sink, item):
                        continue          # its hands are filtered: the feed stops at the belt's end
                    row = (name, item, product, sink, takers)
                    if row not in out:
                        out.append(row)
    return out


def _filtered_out(flat, sink, item):
    """Whether a ``set SINK.in: filter=...`` keeps ``item`` out of machine ``sink``."""
    inst = sink.rsplit("/", 1)[0]
    for props, scope in getattr(getattr(flat, "circuit", None), "sets", ()) or ():
        target = f"{scope}/{props.target}" if scope else props.target
        if target != inst or props.side != "in" or "filter" not in props.attrs:
            continue
        allowed = {w.strip() for w in str(props.attrs["filter"]).replace("|", ",").split(",")}
        if item not in allowed and "circuit" not in allowed:
            return True
    return False


def _absorbed(flat, ni, pool, ends, util, feeds, outs, sink_share, potential, unbounded):
    """The row of a net a bus pool absorbed: what its own drivers make and its own consumers take
    at the pool's utilizations, its ports passing the balance on. A load's net delivers all its
    drivers make (the pool took it, or they slowed); an unbounded one what the pool delivers
    beyond the other loads; a tap's net what its consumers take. Its sinks get their share of
    what the pool's sinks took, by their caps (evenly among sinks without a rate, if any)."""
    name, item = ni
    net = flat.nets[name]
    pk = (pool.net, item)
    st = NetItem(name, item)

    def made(key):
        return flat.machines[key].makes.get(item, 0.0) / len(outs[(key, item)]) * util[key]

    s = d = would = 0.0
    unb, into, caps, own = unbounded, False, [], set()
    for key, it in net.drivers:
        m = flat.machines[key]
        if it != item or m.extra.get("port"):
            continue
        own.add(key)
        if m.source:
            unb = True
            continue
        s += made(key)
    for key, it in net.consumers:
        m = flat.machines[key]
        if it != item:
            continue
        if m.extra.get("port"):
            into = into or m.extra["port"] in ("load", "in")
            continue
        need = m.needs.get(item, 0.0)
        if need > 0:
            share = need / len(feeds[(key, item)])
            d += share * util[key]
            would += share * potential(key, (key, "in", pk[0], item))
        elif m.sink:
            caps.append(sink_share.get((key,) + pk, 0.0))
    every = [c for k, c in sink_share.items() if k[1:] == pk]
    if not caps or pool.to_sinks <= 0:
        take = 0.0
    elif INF in every:
        take = pool.to_sinks * caps.count(INF) / every.count(INF)
    else:
        take = pool.to_sinks * sum(caps) / sum(every) if sum(every) > 0 else 0.0
    st.unbounded, st.to_sinks, st.sink_cap = unb, take, sum(caps)
    if into:
        st.supply = INF if unb else s
        flow = s
        if unb and pool.delivered != INF:            # what the others don't bring
            others = sum(made(k) for k in ends["drivers"] if k not in own
                         and not flat.machines[k].source)
            flow = s + max(0.0, pool.delivered - others - s)
        elif unb:
            flow = INF
        st.demand = st.would_take = max(0.0, flow - take)
    else:
        st.supply = INF if unb else max(s, d + take)
        st.demand, st.would_take = d, would
    st.delivered = st.demand + take
    return st


def _asserts(model):
    flat = model.flat
    out = []
    for a, scope in flat.asserts:
        node, keys = flat.resolve_ref(a.ref, scope)
        net_name = "/".join(p for p in (scope, ".".join(a.ref.parts)) if p)
        if node is not None and node.kind == "Bus":
            value = model.inst_rate(node.path)
        elif keys:
            item = primary(flat, keys)
            value = sum(model.rate(k, item) for k in keys)
        elif net_name in flat.nets:
            value = sum(model.nets[(net_name, i)].delivered for i in flat.nets[net_name].items)
        else:
            out.append((f"assert {a.ref}.rate: names nothing", False, 0.0, a.rate, a.op))
            continue
        ok = {">=": value >= a.rate - 1e-9, "<=": value <= a.rate + 1e-9,
              ">": value > a.rate, "<": value < a.rate,
              "==": abs(value - a.rate) <= 1e-9}[a.op]
        out.append((f"{a.ref}.rate {a.op} {a.rate * 60:g}/min", ok, value, a.rate, a.op))
    return out


# -- report ---------------------------------------------------------------------------------------
def _f(v, scale=1.0):
    if v == INF:
        return "unbounded"
    return f"{v * scale:.3f}"


def _why(model, key):
    b = model.binding.get(key)
    m = model.flat.machines[key]
    if m.sink:
        return "sink"
    if m.source:
        return "source"
    if b is None:
        return "full speed"
    kind, item, net = b
    if kind == "duty":
        # 2.0.63: a DNP machine is laid out but not built: it runs at nothing
        return "dnp: not built" if m.extra.get("dnp") else f"duty {m.duty:g}"
    if net is None:
        return f"{'input' if kind == 'in' else 'output'} {item} has no net"
    if kind == "in":
        return f"{item} short on {net}"
    st = model.nets.get((net, item))
    return f"{item}: {net} takes {st.delivered:.2f}/s" if st is not None else f"{item} on {net}"


def chain(model, path, depth=8):
    """The binding chain of an instance: what limits it, then what limits that, ..."""
    flat = model.flat
    out, seen = [], set()
    while path and depth > 0 and path not in seen:
        seen.add(path)
        depth -= 1
        inst = flat.insts[path]
        key = inst.machines[0]
        u = model.util[key]
        out.append(f"{path} {u:.3f} ({_why(model, key)})")
        b = model.binding.get(key)
        if not b or b[0] != "in" or b[2] is None:
            break
        st = model.nets[(b[2], b[1])]
        drivers = [flat.machines[k].inst for k in model.ends[(b[2], b[1])]["drivers"]]
        nxt = None
        for d in drivers:
            dk = flat.insts[d].machines[0]
            if model.binding.get(dk) is not None and d not in seen:
                nxt = d
                break
        out.append(f"  <- {b[2]} {b[1]}: supply {_f(st.supply)}/s, consumers would take "
                   f"{_f(st.would_take)}/s")
        path = nxt
    return out


def _bus_row(model, path):
    """A Bus's instance line: what passes through it, and what its pool's loads bring against
    what its taps would take (the pool's own row, ``fkcore.elaborate._bus_nets``)."""
    inst = model.flat.insts[path]
    item = inst.params.get("item")
    st = model.nets[(path, item)]
    made = f"{item} " + ("unbounded" if st.delivered == INF else f"{st.delivered * 60:.2f}")
    return (f"  {path:<18} {'Bus':<12} {len(inst.machines):>3} {'-':>6}  {made:<38} pool: loads "
            f"bring {_f(st.supply)}/s, taps would take {_f(st.would_take)}/s")


def report(model, title=None) -> str:
    flat = model.flat
    lines = [f"rates {title or flat.name} (nominal V1 model: logical nets, no capacity)",
             f"  solved in {model.passes} passes, last change {model.residual:.1e}", ""]
    lines.append(f"  {'instance':<18} {'kind':<12} {'n':>3} {'util':>6}  {'makes /min':<38} binding")
    for path, inst in flat.insts.items():
        if inst.module is not None:
            continue
        keys = inst.machines
        if not keys:
            continue
        if inst.kind == "Bus":
            lines.append(_bus_row(model, path))
            continue
        us = [model.util[k] for k in keys]
        item = primary(flat, keys)
        made = f"{item} {model.inst_rate(path, item) * 60:.2f}" if item else ""
        if item and model.inst_rate(path, item) == INF:
            made = f"{item} unbounded"
        lines.append(f"  {path:<18} {inst.kind:<12} {len(keys):>3} {min(us):>6.3f}  {made:<38} "
                     f"{_why(model, keys[0])}")
    lines += ["", f"  {'net':<16} {'item':<26} {'supply/s':>9} {'would take':>10} {'taken/s':>8} "
                  f"{'sinks/s':>8} {'surplus/s':>9}"]
    for (net, item), st in model.nets.items():
        surplus = st.supply - st.delivered if st.supply != INF else INF
        lines.append(f"  {net:<16} {item:<26} {_f(st.supply):>9} {_f(st.would_take):>10} "
                     f"{_f(st.demand):>8} {_f(st.to_sinks):>8} {_f(surplus):>9}")
    if model.asserts:
        lines += ["", "  asserts"]
        for text, ok, value, target, op in model.asserts:
            lines.append(f"  {'PASS' if ok else 'rate-not-met'} {text}: {_f(value, 60)}/min")
    return "\n".join(lines)
