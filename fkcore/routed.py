"""fkcore.routed: a factory's netlist on its routed layout, through the V2 flow solver (CORE-V2.md).

``solve(flat, lay, cat)`` builds the lane graph of the layout (``fkcore.lanes``) and puts every
netlist machine whose entity the layout holds on it (``fkcore.throughput``):

- a crafter or a drill is a ``Machine``: its needs and products at full speed, times its duty, or
  times its nominal utilization where V1's rate model has it bound by a fluid (pipes are not
  modeled: 2.0's pipes are tanks, Rory), the fluids themselves left out;
- a requester chest is a machine that makes its items at its rate; one without a rate puts on as
  much as the carriers take (the solver's ``BIG``: "unbounded");
- a sink (a provider or storage chest, a lab, a turret) takes what reaches it of the items of the
  nets that feed it, up to its rate split over them, without end when it has none.

``report(routed)`` -> (lines, checks). The lines: per instance its nominal utilization (V1) and
its routed one (mean, and the lowest machine), and what limits it; per net and item what its
consumers asked and got, and its critical connector (the largest required ratio). The checks:
``CAPACITY`` per net and kind of connector that binds (it runs at capacity while more is required
through it): the required flow, what the connector carries, the ratio and the consumers it starves.
Checks warn, never gate. Pure, stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import lanes as lanesmod
from . import rates as ratesmod
from . import throughput as tp
from .elaborate import Check

__all__ = ["Routed", "solve", "report", "TIER_WORD"]

INF = float("inf")
#: what a belt tier is called in a report line
TIER_WORD = {"transport-belt": "yellow", "underground-belt": "yellow", "splitter": "yellow",
             "fast-transport-belt": "red", "fast-underground-belt": "red", "fast-splitter": "red",
             "express-transport-belt": "blue", "express-underground-belt": "blue",
             "express-splitter": "blue", "turbo-transport-belt": "turbo",
             "turbo-underground-belt": "turbo", "turbo-splitter": "turbo"}
_SHOW = 4


@dataclass
class Routed:
    flat: object
    lay: object
    lg: object                    # fkcore.lanes.LaneGraph
    res: object                   # fkcore.throughput.Result
    model: object                 # V1's nominal rates.Model
    machines: dict                # node id -> throughput.Machine
    base: dict                    # machine key -> the share of full speed it was given (duty, fluid)
    net_of: dict                  # node id -> net name (from the layout's net=)

    def util(self, key):
        """A machine's routed utilization (absolute, duty included)."""
        nid = (key, "")
        if nid in self.res.util:
            return self.res.util[nid] * self.base.get(key, 1.0)
        return None


def _fluid_bound(model, key, cat):
    b = model.binding.get(key)
    return b is not None and b[0] in ("in", "out") and b[1] is not None and cat.is_fluid(b[1])


def solve(flat, lay, cat, model=None, hand=1, bulk_hand=1) -> Routed:
    """The netlist ``flat`` on its layout ``lay`` through the flow solver. ``hand``/``bulk_hand``:
    the force's inserter hand sizes (1 = no research)."""
    model = model or ratesmod.solve(flat)
    lg = lanesmod.build(lay, cat, hand=hand, bulk_hand=bulk_hand)
    machines, supply, demand, base = {}, {}, {}, {}
    fed = {}
    for (key, item), nets in flat._in_hold.items():
        fed.setdefault(key, set()).add(item)
    for key, m in flat.machines.items():
        nid = (key, "")
        if key not in lay.entities or nid not in lg.nodes:
            continue
        solid_needs = {i: r for i, r in m.needs.items() if not cat.is_fluid(i)}
        solid_makes = {i: r for i, r in m.makes.items() if not cat.is_fluid(i)}
        if m.sink:
            items = sorted(i for i in fed.get(key, ()) if not cat.is_fluid(i))
            if items:
                each = INF if m.drain is None else m.drain / len(items)
                demand[nid] = {i: each for i in items}
            continue
        if m.source:
            if solid_makes:
                supply[nid] = {i: INF for i in solid_makes}
            continue
        share = m.duty
        if _fluid_bound(model, key, cat):
            share = min(share, model.util.get(key, share))
        base[key] = share
        machines[nid] = tp.Machine({i: r * share for i, r in solid_needs.items()},
                                   {i: r * share for i, r in solid_makes.items()})
    res = tp.solve(lg, supply=supply, demand=demand, machines=machines)
    net_of = {}
    for nid in lg.nodes:
        e = lay.entities.get(nid[0])
        if e is not None and e.attrs.get("net"):
            net_of[nid] = e.attrs["net"]
    return Routed(flat, lay, lg, res, model, machines, base, net_of)


# -- report ---------------------------------------------------------------------------------------
def _word(lg, nid):
    n = lg.nodes[nid]
    if n.kind == "inserter":
        return f"{n.name}s"
    tier = TIER_WORD.get(n.name, n.name)
    return f"{tier} {'splitter ' if n.kind == 'splitter' else ''}lanes"


def _keys(nids):
    names = []
    for key, lane in nids:
        name = f"{key}{'.' + lane if lane else ''}"
        if name not in names:
            names.append(name)
    shown = ", ".join(names[:_SHOW])
    return shown + (f" and {len(names) - _SHOW} more" if len(names) > _SHOW else "")


def _consumers(flat, net):
    return [(key, item) for key, item in flat.nets[net].consumers]


def report(r: Routed, factory=None):
    """-> (report lines, CAPACITY checks)."""
    flat, res, lg = r.flat, r.res, r.lg
    where = f"{factory} " if factory else ""
    lines = [f"routed {factory or flat.name} (V2: the lanes and inserters as laid): "
             f"{len(lg.nodes)} connectors and machines, solved in {res.rounds} rounds"]
    lines.append(f"  {'instance':<18} {'nominal':>7} {'routed':>7} {'lowest':>7}  limited by")
    starved = res.starved()
    for path, inst in flat.insts.items():
        if inst.module is not None or not inst.machines:
            continue
        us = [(k, r.util(k)) for k in inst.machines if r.util(k) is not None]
        if not us:
            continue
        nominal = min(r.model.util[k] for k in inst.machines)
        mean = sum(u for _k, u in us) / len(us)
        low = min(u for _k, u in us)
        why = []
        hungry = sorted({item for k, _u in us for item in starved.get((k, ""), {})})
        if hungry:
            n = sum(1 for k, _u in us if (k, "") in starved)
            why.append(f"{n} of {len(us)} starved of {', '.join(hungry)}")
        blocked = [k for k, _u in us if any(
            res.supplied.get((k, ""), {}).get(i, 0.0) < x - 1e-6
            for i, x in res.supply.get((k, ""), {}).items())]
        if blocked:
            why.append(f"{len(blocked)} of {len(us)} blocked (output backs up)")
        lines.append(f"  {path:<18} {nominal:>7.3f} {mean:>7.3f} {low:>7.3f}  "
                     + ("; ".join(why) if why else ("as nominal" if mean >= nominal - 1e-6
                                                    else "")))
    lines += ["", f"  {'net':<16} {'item':<26} {'asked/s':>8} {'got/s':>8}  critical connector"]
    checks = []
    for net in flat.nets:
        mine = [nid for nid, n in r.net_of.items() if n == net]
        if not mine:
            continue
        cons = _consumers(flat, net)
        for item in flat.nets[net].items:
            asked = sum(res.demand.get((k, ""), {}).get(i, 0.0) for k, i in cons if i == item)
            got = sum(res.delivered.get((k, ""), {}).get(i, 0.0) for k, i in cons if i == item)
            ask = "unbounded" if asked == INF else f"{asked:.3f}"
            lines.append(f"  {net:<16} {item:<26} {ask:>8} {got:>8.3f}  "
                         + _critical(res, lg, mine))
        checks += _capacity(r, net, mine, where)
    return lines, checks


def _critical(res, lg, mine):
    finite = [nid for nid in mine if res.cap.get(nid, INF) not in (0, INF)]
    if not finite:
        return "-"
    nid = max(finite, key=lambda v: (res.required_ratio(v), str(v)))
    req = res.total(nid, res.required)
    if req >= tp.BIG / 2:
        return f"{nid[0]} ({_word(lg, nid)}): unbounded"
    return (f"{nid[0]}{'.' + nid[1] if nid[1] else ''} ({_word(lg, nid)}): "
            f"{req:.3f}/s required of {res.cap[nid]:.3f}/s, ratio {res.required_ratio(nid):.2f}")


def _short(r, net):
    """What the net leaves short of the nominal model: per item it delivers less to its
    consumers than V1's nominal rates -> [text], the net's total first, then the machines below
    their nominal utilization (a sink: what it gets). One machine starved while another takes up
    its share (belt order) costs nothing, and gives nothing."""
    res, flat, model = r.res, r.flat, r.model
    cons = flat.nets[net].consumers
    out = []
    for item in flat.nets[net].items:
        st = model.nets.get((net, item))
        if st is None or st.delivered == INF:
            continue
        got = sum(res.delivered.get((k, ""), {}).get(i, 0.0) for k, i in cons if i == item)
        if got >= st.delivered * (1 - 1e-3) - 1e-6:
            continue
        out.append(f"it delivers {got:.2f}/s of {item}, {st.delivered:.2f}/s nominal")
        for key, i in cons:
            u, nominal = r.util(key), model.util.get(key, 1.0)
            if i != item:
                continue
            if u is None:
                out.append(f"{key} gets {res.delivered.get((key, ''), {}).get(item, 0.0):.2f}/s")
            elif u < nominal - 1e-3:
                out.append(f"{key} runs at {u:.2f}, {nominal:.2f} nominal")
    return out


def _capacity(r, net, mine, where):
    """``CAPACITY`` lines of one net: one per kind of connector that binds on it, when the net
    leaves something short of its nominal rate."""
    res, lg = r.res, r.lg
    short = _short(r, net)
    if not short:
        return []
    binding = [nid for nid in mine if res.binds(nid) and res.total(nid, res.required) < tp.BIG / 2]
    groups = {}
    for nid in binding:
        groups.setdefault(_word(lg, nid), []).append(nid)
    out = []
    for word, nids in sorted(groups.items()):
        nids.sort(key=lambda v: (-res.required_ratio(v), str(v)))
        top = nids[0]
        msg = (f"{res.total(top, res.required):.2f}/s required where its {word} carry "
               f"{res.cap[top]:.2f}/s (ratio {res.required_ratio(top):.2f}): {_keys(nids)}; "
               + "; ".join(short[:_SHOW + 1])
               + (f" and {len(short) - _SHOW - 1} more" if len(short) > _SHOW + 1 else ""))
        out.append(Check("CAPACITY", f"{where}net {net}", msg))
    return out
