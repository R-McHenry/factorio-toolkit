"""fkcore.tiers: a belt tier per connector (CORE-V2.md "Tier per connector", Rory).

The tiers come from what the design asks of every lane: the flow solver's required flows with the
machines at V1's nominal rates and no capacities (``fkcore.routed.required``), so a lane that binds
today still shows what it would carry. Every belt, underground pair and splitter on a net gets:

- ``minimize``: the slowest allowed tier whose lane carries its required flow (the fastest allowed
  where none does: ``CAPACITY`` reports it after);
- ``maximize``: the fastest allowed tier, on every one that carries anything;
- ``yellow``: only yellow, what the router lays.

Budgets (``{"red": 10}``): at most that many entities of a tier. Where a mode wants more, the ones
with the highest required ratio keep it and the rest take the next allowed tier down. The flow
peaks between the last driver and the first consumer, so on a line of drills into furnaces the red
belts land in the middle (Rory's test case). An underground pair changes tier as one and counts as
two: its tunnel was laid at yellow's reach, so every tier pairs it the same. A Literal's entities
are pinned and keep theirs; entities on no net (a cover's, a claim's) are not touched. Pure.
"""
from __future__ import annotations

from . import fkp as fkpmod

__all__ = ["TIERS", "FAMILY", "assign", "choose", "tier_of"]

TIERS = ("yellow", "red", "blue", "turbo")
FAMILY = {
    "transport-belt": ("transport-belt", "fast-transport-belt", "express-transport-belt",
                       "turbo-transport-belt"),
    "underground-belt": ("underground-belt", "fast-underground-belt", "express-underground-belt",
                         "turbo-underground-belt"),
    "splitter": ("splitter", "fast-splitter", "express-splitter", "turbo-splitter"),
}
_INDEX = {name: (kind, i) for kind, names in FAMILY.items() for i, name in enumerate(names)}
_EPS = 1e-6


def tier_of(name):
    """(family, tier index) of a belt-type prototype, or None."""
    return _INDEX.get(name)


def _rate(cat, tier):
    return float(cat.entity(FAMILY["transport-belt"][tier])["belt_speed"]) * 60 * 4


def choose(lg, required, cat, entities, mode="minimize", allow=TIERS, budgets=None, fixed=(),
           required_edge=None):
    """The tier of every belt-type entity of ``entities`` ({key: entity}) on a net:
    -> ({key: tier index}, notes). ``required``: the solver's required flows per node
    ({(key, lane): {item: items/s}}); ``required_edge`` per edge, which gives a splitter what one
    of its halves carries (else half its lane's); ``fixed``: keys that keep their tier."""
    if mode not in ("minimize", "maximize", "yellow"):
        raise ValueError(f"tier mode is minimize, maximize or yellow, got {mode!r}")
    allowed = sorted({TIERS.index(t) for t in allow} | {0})
    rates = {t: _rate(cat, t) for t in range(len(TIERS))}
    pair = {}
    g = lg.graph
    for a, b in g.pairs.items():
        pair[a] = b
    need, units, weight = {}, {}, {}
    for key, e in entities.items():
        info = tier_of(e.name)
        if info is None or key in fixed or not e.attrs.get("net"):
            continue
        if info[0] == "splitter" and required_edge is not None:
            lanes = [sum(required_edge.get((e.src, e.dst), {}).values())
                     for lane in ("L", "R") for e in lg.inn.get((key, lane), []) +
                     lg.out.get((key, lane), []) if e.cap != float("inf")] or [0.0]
        else:
            halves = 2 if info[0] == "splitter" else 1
            lanes = [sum(required.get((key, lane), {}).values()) / halves for lane in ("L", "R")]
        need[key] = max(lanes)
    for key in need:
        unit = tuple(sorted({key, pair[key]} & set(need))) if key in pair else (key,)
        units[unit] = max(need[k] for k in unit)
        weight[unit] = len(unit)
    want, notes = {}, []
    over = []
    for unit, n in units.items():
        if mode == "yellow":
            want[unit] = 0
        elif mode == "maximize":
            want[unit] = allowed[-1] if n > _EPS else 0
        else:
            fits = [t for t in allowed if rates[t] >= n - _EPS]
            want[unit] = fits[0] if fits else allowed[-1]
            if not fits:
                over.append(unit)
    if over:
        top = max(units[u] for u in over)
        notes.append(f"{sum(weight[u] for u in over)} entities need more than "
                     f"{TIERS[allowed[-1]]} carries (up to {top:.2f}/s a lane): "
                     + ", ".join(k for u in sorted(over, key=lambda u: -units[u])[:4] for k in u))
    budgets = {TIERS.index(t): n for t, n in (budgets or {}).items()}
    for t in sorted(allowed, reverse=True):
        if t not in budgets:
            continue
        mine = sorted((u for u in units if want[u] == t),
                      key=lambda u: (-units[u], u))
        used, kept = 0, 0
        lower = max([x for x in allowed if x < t] or [0])
        for unit in mine:
            if used + weight[unit] <= budgets[t]:
                used += weight[unit]
                kept += 1
            else:
                want[unit] = lower
        if kept < len(mine):
            notes.append(f"the {TIERS[t]} budget ({budgets[t]}) takes {used} of the "
                         f"{sum(weight[u] for u in mine)} entities that want {TIERS[t]}: the rest "
                         f"are {TIERS[lower]}")
    out = {}
    for unit, t in want.items():
        for key in unit:
            out[key] = t
    return out, notes


def assign(flat, lay, cat, mode="minimize", allow=TIERS, budgets=None, hand=1, bulk_hand=1):
    """-> (new layout, report lines, {key: (old name, new name)})."""
    from . import routed
    lg, res = routed.required(flat, lay, cat, hand=hand, bulk_hand=bulk_hand)
    fixed = {k for k, e in lay.entities.items()
             if e.owner in flat.insts and flat.insts[e.owner].kind == "Literal"}
    tiers, notes = choose(lg, res.required, cat, lay.entities, mode, allow, budgets, fixed,
                          res.required_edge)
    new = fkpmod.Layout(lay.level, lay.name, lay.size, dict(lay.insts), dict(lay.covers),
                        dict(lay.plots), dict(lay.claims), dict(lay.marks), dict(lay.entities))
    changed, count = {}, {}
    for key, t in sorted(tiers.items()):
        e = lay.entities[key]
        family, _now = tier_of(e.name)
        name = FAMILY[family][t]
        count[TIERS[t]] = count.get(TIERS[t], 0) + 1
        if name != e.name:
            changed[key] = (e.name, name)
            new.entities[key] = fkpmod.Entity(e.key, name, e.x, e.y, e.dir, dict(e.attrs))
    head = (f"tier {mode} (allowed: {', '.join(t for t in TIERS if t in allow or t == 'yellow')}"
            + (f"; budgets {', '.join(f'{t} {n}' for t, n in budgets.items())}" if budgets else "")
            + f"): {len(tiers)} belts, undergrounds and splitters on nets; "
            + ", ".join(f"{count[t]} {t}" for t in TIERS if t in count)
            + f"; {len(changed)} changed")
    lines = [head] + [f"  {n}" for n in notes]
    by_net = {}
    for key, (_old, name) in changed.items():
        net = lay.entities[key].attrs.get("net")
        by_net.setdefault(net, []).append((key, name))
    for net, rows in sorted(by_net.items()):
        tiers_ = sorted({tier_of(n)[1] for _k, n in rows})
        lines.append(f"  {net}: {len(rows)} to {', '.join(TIERS[t] for t in tiers_)} ("
                     + ", ".join(k for k, _n in sorted(rows, key=lambda r: fkpmod.natural_key(r[0]))[:4])
                     + (f" and {len(rows) - 4} more" if len(rows) > 4 else "") + ")")
    return new, lines, changed
