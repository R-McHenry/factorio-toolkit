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
  ``rate``; a sushi sink's rate is split over its items by full-speed supply). If A < S, the
  drivers are slowed the same way: the same fraction of their duty, water-filled.
- What-if: ``unbounded=[net, ...]`` treats those nets' supply as unlimited (their drivers then run
  at what the consumers take), which is how a hand calc isolates one part of a factory.
- An input with no net, or an output with no net, stops the machine (UNFED / UNCONSUMED say so).

Each side is judged against the other side's potential, not its throttled state; judging both
sides by the current state (as flow.py does) has a fixed point at every S = D, so a consumer and
its producer can each blame the other and stay low. The grants are a damped fixed point from
"everything at full speed": deterministic, stdlib only. The result names, per machine, the
endpoint that bound it, and per net and item the supply, demand, what sinks took and the surplus.
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

    def rate(self, key, item):
        """Items/s machine ``key`` makes of ``item``."""
        m = self.flat.machines[key]
        return m.makes.get(item, 0.0) * self.util[key]

    def inst_rate(self, path, item=None):
        inst = self.flat.insts[path]
        item = item or primary(self.flat, inst.machines)
        return sum(self.rate(k, item) for k in inst.machines)


def primary(flat, keys):
    for k in keys:
        makes = flat.machines[k].makes
        if makes:
            return next(iter(makes))
    return None


def _structure(flat):
    ends = {}                          # (net, item) -> {"drivers": [k], "consumers": [k]}
    feeds, outs = {}, {}
    for name, net in flat.nets.items():
        for item in net.items:
            ends[(name, item)] = {"drivers": [], "consumers": []}
        for key, item in net.drivers:
            ends[(name, item)]["drivers"].append(key)
            outs.setdefault((key, item), []).append(name)
        for key, item in net.consumers:
            ends[(name, item)]["consumers"].append(key)
            feeds.setdefault((key, item), []).append(name)
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


def solve(flat, passes=50000, tol=1e-12, share="appetite", unbounded=()) -> Model:
    if share not in ("appetite", "level"):
        raise ValueError(f"share must be appetite or level, got {share!r}")
    unknown = sorted(set(unbounded) - set(flat.nets))
    if unknown:
        raise ValueError("unbounded names no net: " + ", ".join(unknown))
    ends, feeds, outs = _structure(flat)
    machines = flat.machines

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
        if m.drain is None:
            for ni in mine:
                sink_share[(k,) + ni] = INF
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

    def potential(k, skip=None):
        """What everything but grant ``skip`` allows machine ``k``."""
        m = machines[k]
        if m.sink or m.source:
            return 1.0
        if k in dead:
            return 0.0
        v = m.duty
        for g in mine.get(k, ()):
            if g != skip and grants[g] < v:
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
                s += m.makes.get(item, 0.0) / len(outs[(k, item)]) * util[k]
            d = nf = cap = 0.0
            for k in e["consumers"]:
                m = machines[k]
                need = m.needs.get(item, 0.0)
                if need > 0:
                    share = need / len(feeds[(k, item)])
                    d += share * util[k]
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
                             potential(k, (k, "out", n, item)), m.duty))
            cons = []
            for k in e["consumers"]:
                m = machines[k]
                need = m.needs.get(item, 0.0)
                if need > 0:
                    cons.append((k, need / len(feeds[(k, item)]),
                                 potential(k, (k, "in", n, item)), m.duty))
            can_make = INF if unb else sum(w * c for _k, w, c, _d in prod)
            would_take = sum(w * c for _k, w, c, _d in cons)
            can_take = would_take + sink_caps[ni]
            stats[ni].can_make, stats[ni].can_take = can_make, can_take
            stats[ni].would_take = would_take
            for row, g in zip(cons, _grant([r[1:] for r in cons], can_make, share)):
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
    model = Model(flat, util, binding, stats, done, residual)
    model.asserts = _asserts(model)
    return model


def _asserts(model):
    flat = model.flat
    out = []
    for a, scope in flat.asserts:
        node, keys = flat.resolve_ref(a.ref, scope)
        net_name = "/".join(p for p in (scope, ".".join(a.ref.parts)) if p)
        if keys:
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
        return f"duty {m.duty:g}"
    if net is None:
        return f"{'input' if kind == 'in' else 'output'} {item} has no net"
    if kind == "in":
        return f"{item} short on {net}"
    return f"{item} not taken on {net}"


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
        drivers = [flat.machines[k].inst for k, it in flat.nets[b[2]].drivers if it == b[1]]
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
            lines.append(f"  {'PASS' if ok else 'ASSERT'} {text}: {_f(value, 60)}/min")
    return "\n".join(lines)
