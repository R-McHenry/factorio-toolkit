"""fkcore.fragments: the geometry of a template instance, as a Fragment (CORE-V1.md §5).

    Fragment = {kind, params, entities: [FEnt], roles: {name: Role}, size: (w, h), sig}

Every template is authored in a local frame: the row runs east, the top-left tile is (0, 0).
Each input or output belt is a **role**: the belt tiles and the inserters that work it. At
expansion a role is bound to the one net its endpoints sit on, so every carrier gets ``net=``; the
router later lays only the carriers between a role's attach point and the rest of its net.

Geometry is v4's proven stamps (C:\\fk-lead\\repo\\fk\\stamps\\assembler_row.py, miner_row.py,
feed_rows.py lab_row, d6018d3) with every pole removed (power is a coverage step) and fast
inserters throughout. Rows are counterflow: the product belt runs back west, so every attach point
of a row is at its head (x = 0). Input belts carry one net each (a net may be sushi). AsmRow takes
up to three: two north of the machines as in v4, and a third south of the product belt, reached
by long-handed inserters across it (Rory, 2026-10-19; for the inserter, engine and blue recipes).
SmelterRow and LabRow take up to two; more raises FragmentError rather than inventing a layout.
SmelterRow is new geometry in AsmRow's pattern: ore by fast inserter from the near belt, fuel by
long-handed inserter from the far one, at the furnaces' pitch 2.

Machine entities carry what a Literal needs to rebuild them (recipe, resource, fuel, role, rate),
so ``unfold`` can turn any instance into a Literal with the same keys and the same netlist.
Pure, stdlib only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

__all__ = ["FragmentError", "FEnt", "Role", "Fragment", "fragment", "FRAGMENTS"]

E, S, W, N = 4, 8, 12, 0
_INSERTER = "fast-inserter"
_LONG = "long-handed-inserter"


class FragmentError(ValueError):
    pass


@dataclass
class FEnt:
    local: str
    name: str
    x: float
    y: float
    dir: int | None
    role: str | None = None              # the role a carrier works; None for a machine
    attrs: dict = field(default_factory=dict)


@dataclass
class Role:
    name: str
    side: str                            # "in" | "out"
    items: list
    machines: list                       # machine locals it serves
    attach: list                         # [(x, y, dir)] where the route meets it


@dataclass
class Fragment:
    kind: str
    params: dict
    entities: list
    roles: dict
    size: tuple
    sig: str = ""


def _belt(prefix, role, x0, y, n, d=E):
    return [FEnt(f"{prefix}{j}", "transport-belt", x0 + j + 0.5, y + 0.5, d, role)
            for j in range(n)]


def _finish(frag: Fragment) -> Fragment:
    rows = sorted((e.local, e.name, float(e.x), float(e.y), e.dir, e.role) for e in frag.entities)
    roles = sorted((r.name, r.side, sorted(r.machines), r.attach) for r in frag.roles.values())
    blob = json.dumps([frag.kind, rows, roles, list(frag.size)], separators=(",", ":"))
    frag.sig = hashlib.sha1(blob.encode()).hexdigest()[:10]
    return frag


def _inputs(inputs, kind, most=2):
    if not 1 <= len(inputs) <= most:
        raise FragmentError(f"{kind} takes 1 to {most} input belts in V1, got {len(inputs)}: "
                            + "; ".join(", ".join(b) for b in inputs)
                            + " (put two items on one sushi net, or split the row)")
    return inputs


def asm_row(n, recipe, inputs, outputs, machine="assembling-machine-1", counter=True):
    """Rows north to south: in2, in1, feeders, machines (3), output inserters + in3 feeders,
    product belt, in3. Without in2 everything shifts up one; in3 needs in2."""
    inputs = _inputs(inputs, "AsmRow", most=3)
    two, three = len(inputs) >= 2, len(inputs) == 3
    shift = 0 if two else -1
    in2_y, in1_y, feed_y = 0, 1 + shift, 2 + shift
    mach_y, out_ins_y, out_y = 4 + shift, 6 + shift, 7 + shift
    ents = _belt("in1b", "in1", 0, in1_y, 3 * n - 1)
    ents.append(FEnt(f"in1b{3 * n - 1}", "transport-belt", 3 * n - 0.5, in1_y + 0.5, S, "in1"))
    if two:
        ents += _belt("in2b", "in2", 0, in2_y, 3 * n - 1)
    if counter:
        ents += [FEnt(f"outb{j}", "transport-belt", j + 0.5, out_y + 0.5, W, "out")
                 for j in range(3 * n)]
    else:
        ents += _belt("outb", "out", 0, out_y, 3 * n)
    in3_y = out_y + 1
    if three:
        ents += _belt("in3b", "in3", 0, in3_y, 3 * n - 1)    # the last feeder is at x = 3n - 3
    machines = []
    for k in range(n):
        cx = 3 * k + 0.5
        ents.append(FEnt(f"f{k}", _INSERTER, cx, feed_y + 0.5, N, "in1"))
        if two:
            ents.append(FEnt(f"l{k}", _LONG, cx + 1, feed_y + 0.5, N, "in2"))
        ents.append(FEnt(f"m{k}", machine, cx + 1, mach_y + 0.5, None, None, {"recipe": recipe}))
        ents.append(FEnt(f"o{k}", _INSERTER, cx + 1, out_ins_y + 0.5, N, "out"))
        if three:
            # picks two tiles south (in3, over the product belt), drops two north (the machine)
            ents.append(FEnt(f"s{k}", _LONG, cx, out_ins_y + 0.5, S, "in3"))
        machines.append(f"m{k}")
    roles = {"in1": Role("in1", "in", inputs[0], machines, [(0.5, in1_y + 0.5, E)])}
    if two:
        roles["in2"] = Role("in2", "in", inputs[1], machines, [(0.5, in2_y + 0.5, E)])
    if three:
        roles["in3"] = Role("in3", "in", inputs[2], machines, [(0.5, in3_y + 0.5, E)])
    out_at = (0.5, out_y + 0.5, W) if counter else (3 * n - 0.5, out_y + 0.5, E)
    roles["out"] = Role("out", "out", outputs[0] if outputs else [], machines, [out_at])
    return ents, roles, (3 * n, (in3_y if three else out_y) + 1)


def smelter_row(n, recipe, inputs, outputs, machine="stone-furnace", fuel=None):
    inputs = _inputs(inputs, "SmelterRow")
    two = len(inputs) == 2
    shift = 0 if two else -1
    in2_y, in1_y, feed_y = 0, 1 + shift, 2 + shift
    out_y = feed_y + 4
    ents = _belt("in1b", "in1", 0, in1_y, 2 * n - 1)
    ents.append(FEnt(f"in1b{2 * n - 1}", "transport-belt", 2 * n - 0.5, in1_y + 0.5, S, "in1"))
    if two:
        ents += _belt("in2b", "in2", 0, in2_y, 2 * n)          # the last long inserter reaches it
    ents += [FEnt(f"outb{j}", "transport-belt", j + 0.5, out_y + 0.5, W, "out")
             for j in range(2 * n)]
    machines = []
    attrs = {"recipe": recipe}
    if fuel:
        attrs["fuel"] = fuel
    for k in range(n):
        ents.append(FEnt(f"f{k}", _INSERTER, 2 * k + 0.5, feed_y + 0.5, N, "in1"))
        if two:
            ents.append(FEnt(f"l{k}", _LONG, 2 * k + 1.5, feed_y + 0.5, N, "in2"))
        ents.append(FEnt(f"m{k}", machine, 2 * k + 1, feed_y + 2, None, None, dict(attrs)))
        ents.append(FEnt(f"o{k}", _INSERTER, 2 * k + 0.5, feed_y + 3.5, N, "out"))
        machines.append(f"m{k}")
    roles = {"in1": Role("in1", "in", inputs[0], machines, [(0.5, in1_y + 0.5, E)])}
    if two:
        roles["in2"] = Role("in2", "in", inputs[1], machines, [(0.5, in2_y + 0.5, E)])
    roles["out"] = Role("out", "out", outputs[0] if outputs else [], machines,
                        [(0.5, out_y + 0.5, W)])
    return ents, roles, (2 * n, out_y + 1)


def miner_row(n, resource, outputs, drill="electric-mining-drill"):
    north, south = (n + 1) // 2, n // 2
    ents, machines = [], []
    for k in range(north):
        ents.append(FEnt(f"m{k}", drill, 3 * k + 1.5, 1.5, S, None, {"resource": resource}))
    for k in range(south):
        ents.append(FEnt(f"m{north + k}", drill, 3 * k + 1.5, 5.5, N, None,
                         {"resource": resource}))
    machines = [e.local for e in ents]
    belt_end = 3 * north - 1
    ents += _belt("outb", "out", 1, 3, belt_end)
    roles = {"out": Role("out", "out", outputs[0] if outputs else [resource], machines,
                         [(belt_end + 0.5, 3.5, E)])}
    return ents, roles, (3 * north, 7 if south else 4)


def lab_row(n, inputs):
    inputs = _inputs(inputs, "LabRow")
    ents = _belt("in1b", "in1", 0, 0, 3 * n)
    machines = []
    for k in range(n):
        ents.append(FEnt(f"m{k}", "lab", 3 * k + 1.5, 3.5, None))
        ents.append(FEnt(f"f{k}", _INSERTER, 3 * k + 0.5, 1.5, N, "in1"))
        machines.append(f"m{k}")
    roles = {"in1": Role("in1", "in", inputs[0], machines, [(0.5, 0.5, E)])}
    h = 5
    if len(inputs) == 2:
        ents += _belt("in2b", "in2", 0, 6, 3 * n)
        ents += [FEnt(f"g{k}", _INSERTER, 3 * k + 0.5, 5.5, S, "in2") for k in range(n)]
        roles["in2"] = Role("in2", "in", inputs[1], machines, [(0.5, 6.5, E)])
        h = 7
    return ents, roles, (3 * n, h)


#: kind -> how to call the geometry from (params, inputs, outputs)
FRAGMENTS = {
    "AsmRow": lambda p, i, o: asm_row(int(p["n"]), p["recipe"], i, o,
                                      p.get("machine", "assembling-machine-1")),
    "SmelterRow": lambda p, i, o: smelter_row(int(p["n"]), p["_recipe"], i, o,
                                              p.get("machine", "stone-furnace"), p.get("_fuel")),
    "MinerRow": lambda p, i, o: miner_row(int(p["n"]), p["resource"], o,
                                          p.get("drill", "electric-mining-drill")),
    "LabRow": lambda p, i, o: lab_row(int(p["n"]), i),
}


def fragment(kind, params, inputs, outputs) -> Fragment:
    """The Fragment of one instance. ``inputs``/``outputs``: the items of each belt, in order."""
    try:
        fn = FRAGMENTS[kind]
    except KeyError:
        raise FragmentError(f"{kind} has no fragment geometry yet") from None
    ents, roles, size = fn(params, [list(b) for b in inputs], [list(b) for b in outputs])
    return _finish(Fragment(kind, dict(params), ents, roles, size))
