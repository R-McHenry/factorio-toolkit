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
so ``unfold`` can turn any row into a Literal with the same keys and the same netlist.

The ``Bus`` (Rory's 4-belt bus, 2026-10-21) is no row: its belts and splitters are the bus's own
net (role ``pool``), and each load and tap is a port, one belt beside the bus (its stub) whose
role is the net a ``.fk`` net binds to it, with one attach point where the router meets it. Its
staircases are Rory's exactly: at his parameters the template is his demo's 210 bus entities, the
splitters' priorities in ``config`` (the codec writes them into the paste). Pure, stdlib only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

__all__ = ["FragmentError", "FEnt", "Role", "Fragment", "fragment", "FRAGMENTS", "bus",
           "bus_ports", "bus_check", "bus_side"]

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


def burner_miner_row(n, resource, inputs, outputs, drill="burner-mining-drill"):
    """A row of 2x2 burner drills (Rory's kit, 2026-10-21: burner drills mine on the kit's coal
    before there are plates for electric ones). One-sided: the fuel belt north (in1), one fast
    inserter into each drill, the drills facing south onto the product belt (counterflow, west),
    which runs under every drill (facing south, a burner drill drops below its east half).
    ``MinerRow<n, resource, drill=burner-mining-drill, fuel=coal>``; the fuel net binds to in1."""
    inputs = _inputs(inputs, "MinerRow (burner)", most=1)
    ents = _belt("in1b", "in1", 0, 0, 2 * n)
    machines = []
    for k in range(n):
        ents.append(FEnt(f"f{k}", _INSERTER, 2 * k + 0.5, 1.5, N, "in1"))
        ents.append(FEnt(f"m{k}", drill, 2 * k + 1, 3, S, None, {"resource": resource}))
        machines.append(f"m{k}")
    ents += [FEnt(f"outb{j}", "transport-belt", j + 0.5, 4.5, W, "out") for j in range(2 * n)]
    roles = {"in1": Role("in1", "in", inputs[0], machines, [(0.5, 0.5, E)]),
             "out": Role("out", "out", outputs[0] if outputs else [resource], machines,
                         [(0.5, 4.5, W)])}
    return ents, roles, (2 * n, 5)


def lab_row(n, inputs):
    """Labs west to east. in1 north (inserters), in2 south. A third belt (1.1, from the 0534
    player's own patch) runs north of in1: long-handed inserters reach over in1 to it, and
    everything else shifts down one."""
    inputs = _inputs(inputs, "LabRow", most=3)
    three = len(inputs) == 3
    d = 1 if three else 0
    ents = _belt("in1b", "in1", 0, d, 3 * n)
    if three:
        ents += _belt("in3b", "in3", 0, 0, 3 * n)
    machines = []
    for k in range(n):
        ents.append(FEnt(f"m{k}", "lab", 3 * k + 1.5, 3.5 + d, None))
        ents.append(FEnt(f"f{k}", _INSERTER, 3 * k + 0.5, 1.5 + d, N, "in1"))
        if three:
            ents.append(FEnt(f"t{k}", _LONG, 3 * k + 1.5, 1.5 + d, N, "in3"))
        machines.append(f"m{k}")
    roles = {"in1": Role("in1", "in", inputs[0], machines, [(0.5, 0.5 + d, E)])}
    if three:
        roles["in3"] = Role("in3", "in", inputs[2], machines, [(0.5, 0.5, E)])
    h = 5 + d
    if len(inputs) >= 2:
        ents += _belt("in2b", "in2", 0, 6 + d, 3 * n)
        ents += [FEnt(f"g{k}", _INSERTER, 3 * k + 0.5, 5.5 + d, S, "in2") for k in range(n)]
        roles["in2"] = Role("in2", "in", inputs[1], machines, [(0.5, 6.5 + d, E)])
        h = 7 + d
    return ents, roles, (3 * n, h)


# -- the bus (Rory's 4-belt bus, 2026-10-21: agent/docs/examples/bus4.json) ----------------------
#: a port's staircase climbs across the bus from the side its stream comes from to the side it goes
#: to: input priority on the first, output priority toward the second (the game's splitter fields)
_STAIR = {"s": {"input_priority": "right", "output_priority": "left"},     # climbs north
          "n": {"input_priority": "left", "output_priority": "right"}}     # climbs south
_SIDES = "nesw"


def bus_ports(params):
    """(belts, length, item, loads, taps) of ``Bus<belts=4, length, item, load=, tap=>``; a port
    is (side, position): the side a compass letter as written, the position the tile along the bus
    (from its head, x at rot 0) where its belt meets the bus. Raises FragmentError."""
    sizes = []
    for key, v in (("belts", params.get("belts", 4)), ("length", params.get("length"))):
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise FragmentError(f"needs {key}= a positive whole number, got {v!r}")
        sizes.append(v)
    belts, length = sizes
    item = params.get("item")
    if not isinstance(item, str):
        raise FragmentError(f"needs item= one item, got {item!r}")
    out = []
    for kind in ("load", "tap"):
        raw = params.get(kind, [])
        ports = []
        for word in raw if isinstance(raw, list) else [raw]:
            text = str(word)
            if not isinstance(word, str) or len(text) < 2 or text[0] not in _SIDES \
                    or not text[1:].isdigit():
                raise FragmentError(f"{kind}={text}: a port is a side (n, e, s or w) and its tile "
                                    "along the bus, e.g. s11")
            ports.append((text[0], int(text[1:])))
        out.append(ports)
    loads, taps = out
    if len({_SIDES.index(s) % 2 for s, _x in loads + taps}) > 1:
        raise FragmentError("a bus has two sides: n and s where it runs east or west, e and w "
                            "where it runs south or north")
    return belts, length, item, loads, taps


def _port_tiles(belts, kind, side, x):
    """(the staircase's rows per splitter, its tiles, the stub's tile, the tile it keeps empty) of
    a port in the bus's own frame (it runs east; side n is row 0, s is row belts + 1, the belts are
    rows 1..belts). A load keeps one tile empty: its first splitter's dead end, so all it takes
    goes up the staircase."""
    b = belts
    if kind == "load":
        rows = [(b - j, b + 1 - j) if side == "s" else (j, j + 1) for j in range(b)]
        first, edge = x + 1, (b + 1 if side == "s" else 0)
        stub, empty = (x, edge), (x + 2, edge)
    else:
        rows = [(b - 1 - j, b - j) if side == "n" else (1 + j, 2 + j) for j in range(b)]
        first = x - b
        stub, empty = (x, 0 if side == "n" else b + 1), None
    cells = [(first + j, r) for j, pair in enumerate(rows) for r in pair]
    return rows, cells, stub, empty


def bus_check(belts, length, loads, taps):
    """Every port's staircase inside the bus and clear of every other port's. Sides as written,
    n or e read as the bus's own north: turned, everything mirrors alike, so the rot can't make
    two ports collide or part. Raises FragmentError."""
    owner = {}
    for kind, ports in (("load", loads), ("tap", taps)):
        for side, x in ports:
            local = "n" if side in "ne" else "s"
            _rows, cells, stub, empty = _port_tiles(belts, kind, local, x)
            name = f"{kind} {side}{x}"
            mine = cells + [stub] + ([empty] if empty else [])
            span = sorted({t[0] for t in mine})
            if span[0] < 0 or span[-1] >= length:
                raise FragmentError(f"{name}: its staircase of {belts} splitter"
                                    f"{'s' if belts > 1 else ''} takes the tiles {span[0]}.."
                                    f"{span[-1]} along the bus, which runs 0..{length - 1}")
            for t in mine:
                if owner.get(t, name) != name:
                    raise FragmentError(f"{owner[t]} and {name} overlap: {name} takes the tiles "
                                        f"{span[0]}..{span[-1]} along the bus (its belt and its "
                                        "staircase), and no two ports share a tile")
                owner[t] = name


def bus(belts, length, item, loads, taps, used=None):
    """Rory's bus (agent/docs/examples/bus4.json), in its own frame: ``belts`` belts of ``item``
    run east (rows 1..belts) for ``length`` tiles; row 0 (north) and row belts + 1 (south) are
    where its loads come in and its taps go out. ``loads``/``taps``: [(side, x)], side n or s in
    this frame.

    A load at x: its belt (the stub, beside the bus at x) turns east into a staircase of one
    splitter per belt at x + 1 .. x + belts, climbing from its side to the far one with input
    priority on the feeder's side and output priority toward the far side, so it fills the far
    belt first, then the next. A tap at x: a staircase at x - belts .. x - 1 climbing toward its
    side, its last splitter putting out onto the stub at x first, so the tap takes from the far
    belt first. Each used port is a role with one attach point beside the bus, where the router
    meets its stub; ``used`` (port names, None for all) leaves the other stubs out and keeps their
    staircases. The belts and splitters are role ``pool``, the bus's own net.
    -> (entities, roles, size)."""
    bus_check(belts, length, loads, taps)
    b = belts
    ents, taken = [], set()
    roles = {"pool": Role("pool", "pool", [item], [], [])}
    for kind, ports in (("load", loads), ("tap", taps)):
        for k, (side, x) in enumerate(ports, 1):
            name = f"{kind}{k}"
            rows, cells, stub, _empty = _port_tiles(b, kind, side, x)
            climb = side if kind == "load" else ("s" if side == "n" else "n")
            for j, (r0, _r1) in enumerate(rows):
                ents.append(FEnt(f"{name}s{j}", "splitter", cells[2 * j][0] + 0.5, r0 + 1, E,
                                 "pool", {"config": _config_text(_STAIR[climb])}))
            taken |= set(cells)
            if used is not None and name not in used:
                continue
            sx, sy = stub
            d = E if kind == "load" else (N if side == "n" else S)
            into = (N if side == "s" else S) if kind == "load" else d
            ents.append(FEnt(name, "transport-belt", sx + 0.5, sy + 0.5, d, name))
            roles[name] = Role(name, "in" if kind == "load" else "out", [item], [name],
                               [(sx + 0.5, sy + 0.5, into)])
    for c in range(length):
        for r in range(1, b + 1):
            if (c, r) not in taken:
                ents.append(FEnt(f"b{r}_{c}", "transport-belt", c + 0.5, r + 0.5, E, "pool"))
    return ents, roles, (length, b + 2)


def _config_text(fields):
    """Game fields as the ``config`` attr the codec writes (``codec.config_text``'s form)."""
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


_RUNS = ("east", "south", "west", "north")


def bus_side(side, rot):
    """A port's side as written (a compass letter, in the frame the bus is placed in) -> n or s
    in the bus's own frame, for a bus turned ``rot`` quarter turns (rot 0 runs east). Raises
    FragmentError for a side along the bus."""
    rot %= 4
    local = (_SIDES.index(side) - rot) % 4
    if local % 2:
        raise FragmentError(f"the bus runs {_RUNS[rot]} (rot {rot}): its ports go on its "
                            f"{_SIDES[rot]} and {_SIDES[(rot + 2) % 4]} sides, not {side}")
    return "n" if local == 0 else "s"


def _bus(params):
    """``fragment("Bus", ...)``: the sides turned by ``_rot`` (the instance's own), the stubs of
    the ports in ``_used`` only (None: all)."""
    belts, length, item, loads, taps = bus_ports(params)
    rot = int(params.get("_rot", 0))
    loads = [(bus_side(s, rot), x) for s, x in loads]
    taps = [(bus_side(s, rot), x) for s, x in taps]
    return bus(belts, length, item, loads, taps, params.get("_used"))


#: kind -> how to call the geometry from (params, inputs, outputs)
FRAGMENTS = {
    "AsmRow": lambda p, i, o: asm_row(int(p["n"]), p["recipe"], i, o,
                                      p.get("machine", "assembling-machine-1")),
    "SmelterRow": lambda p, i, o: smelter_row(int(p["n"]), p["_recipe"], i, o,
                                              p.get("machine", "stone-furnace"), p.get("_fuel")),
    "MinerRow": lambda p, i, o: (
        burner_miner_row(int(p["n"]), p["resource"], i, o, p["drill"])
        if str(p.get("drill", "")).startswith("burner") else
        miner_row(int(p["n"]), p["resource"], o, p.get("drill", "electric-mining-drill"))),
    "LabRow": lambda p, i, o: lab_row(int(p["n"]), i),
    "Bus": lambda p, i, o: _bus(p),
}


def fragment(kind, params, inputs, outputs) -> Fragment:
    """The Fragment of one instance. ``inputs``/``outputs``: the items of each belt, in order."""
    try:
        fn = FRAGMENTS[kind]
    except KeyError:
        raise FragmentError(f"{kind} has no fragment geometry yet") from None
    ents, roles, size = fn(params, [list(b) for b in inputs], [list(b) for b in outputs])
    # the common ``inserter=`` parameter (templates.COMMON_PARAMS): the row's inserters, in place
    # of the fast ones (1.1, from the 0534 player's own patch: the start has 48 plain inserters,
    # 20 fast ones and the fast recipe locked)
    if params.get("inserter"):
        for e in ents:
            if e.name == _INSERTER:
                e.name = str(params["inserter"])
    return _finish(Fragment(kind, dict(params), ents, roles, size))
