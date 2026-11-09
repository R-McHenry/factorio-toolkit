"""open_flower.py: write flower_open.fk, the megabelt flower with nothing placed (PLAN-ORGANIC T6,
wave 1's bar). The six rivers and the core are the same sealed modules the corridor flower
(flower.fk, written by lab-session\\megabelt\\layout.py) places by hand; here none has an ``@``
hint and there are no corridor modules: every belt and pipe between two parts is one direct net,
and ``fk layout flower_open.fk FlowerOpen`` tessellates the 900x1024 box into their territories.

The flower's own rim ports keep the side the plan gives each river's ore (north for Circuit, east
for Fen and Works, south for Mesa, west for Meadow and Ridge) and no tile along it: an unpinned
port is placed facing its partner, as 2.0.41 does inside a module.

    python tests/data/flower/open_flower.py
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 900, 1024

# name: (module, file, the plan's rim side)
PARTS = {
    "circuit": ("RiverCircuit", "river_circuit.fk", "n"),
    "fen":     ("RiverFen",     "river_fen.fk",     "e"),
    "works":   ("RiverWorks",   "river_works.fk",   "e"),
    "mesa":    ("RiverMesa",    "river_mesa.fk",    "s"),
    "meadow":  ("RiverMeadow",  "river_meadow.fk",  "w"),
    "ridge":   ("RiverRidge",   "river_ridge.fk",   "w"),
    "core":    ("Core",         "core.fk",          None),
}

# (from part, port, to part, port): megabelt/layout.py's ROUTES without the corridors
ROUTES = [
    ("circuit", "rp_ridge", "ridge", "rp_in"),
    ("circuit", "g_meadow", "meadow", "g_in"),
    ("circuit", "rg_works", "works", "rg_in"),
    ("fen", "plastic_out1", "circuit", "plastic_in1"),
    ("fen", "plastic_out2", "circuit", "plastic_in2"),
    ("fen", "acid_out", "circuit", "acid_in"),
    ("fen", "plastic_mesa", "mesa", "plastic_in"),
    ("circuit", "pu", "core", "pu"),
    ("circuit", "tap1", "core", "c_tap1"),
    ("circuit", "tap2", "core", "c_tap2"),
    ("fen", "tap", "core", "f_tap"),
    ("fen", "lube_mall", "core", "lube"),
    ("fen", "lube_works", "works", "lube_in"),
    ("fen", "sb_works", "works", "sb_in"),
    ("works", "blue", "core", "blue"),
    ("works", "rf", "core", "rf"),
    ("works", "tap1", "core", "w_tap1"),
    ("works", "tap2", "core", "w_tap2"),
    ("mesa", "lds", "core", "lds"),
    ("mesa", "tap", "core", "s_tap"),
    ("meadow", "red", "core", "red"),
    ("meadow", "green", "core", "green"),
    ("meadow", "tap", "core", "m_tap"),
    ("ridge", "purple", "core", "purple"),
    ("ridge", "tap1", "core", "r_tap1"),
    ("ridge", "tap2", "core", "r_tap2"),
    ("ridge", "tap3", "core", "r_tap3"),
]

PORT = re.compile(r"^\s*port\s+(\w+)\s*:\s*(in|out|inout)\s+([\w-]+(?:\s*\|\s*[\w-]+)?)\s*@([nesw])(\d+)", re.M)


def module_ports(path, module):
    """{port: (dir, items list, side, pos)} of ``module`` in the file at ``path``."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"module\s+%s\b[^{]*\{" % module, text)
    if not m:
        raise SystemExit(f"{path}: no module {module}")
    depth, i = 1, m.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    body = text[m.end():i]
    return {p: (d, [s.strip() for s in items.split("|")], side, int(pos))
            for p, d, items, side, pos in PORT.findall(body)}


def split_net(name, items, a, b):
    if len(items) == 2 and items[0] != items[1]:
        return [f"  net {name}_a items {items[0]}: {a} -> {b}",
                f"  net {name}_b items {items[1]}: {a} -> {b}",
                f"  lanes {name}_a | {name}_b"]
    return [f"  net {name}: {a} -> {b}"]


def main():
    have = {name: module_ports(os.path.join(HERE, f), mod) for name, (mod, f, _s) in PARTS.items()}
    lines = ["# flower_open.fk: the megabelt flower with nothing placed, written by open_flower.py.",
             "# The same rivers and core as flower.fk, no @ hints and no corridors: fk layout",
             "# flower_open.fk FlowerOpen gives each its territory (PLAN-ORGANIC part T).", ""]
    for name, (mod, f, _s) in PARTS.items():
        lines.append(f'import {mod} from "{f}"')
    lines.append("")
    ports, body, rim_nets, nets = [], [], [], []
    for name, (mod, f, side) in PARTS.items():
        body.append(f"  {name} = {mod}")
        if side is None:
            continue
        for p, (d, items, pside, pos) in sorted(have[name].items(), key=lambda kv: kv[1][3]):
            if pside != "n" or d != "in":
                continue
            fp = f"{name}_{p}"
            ports.append(f"  port {fp} : in {' | '.join(items)} @{side}")
            rim_nets += split_net(f"{fp}_", items, fp, f"{name}.{p}")
    for a, pa, b, pb in ROUTES:
        items = have[a][pa][1]
        nets += split_net(f"{a}_{pa}", items, f"{a}.{pa}", f"{b}.{pb}")
    lines += [f"module FlowerOpen size {W}x{H} {{"] + ports + [""] + body + [""] + rim_nets + [""] \
        + nets + ["}", "", "flower = FlowerOpen @(0, 0)", ""]
    out = os.path.join(HERE, "flower_open.fk")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {out}: {len(ports)} rim ports, {len(ROUTES)} routes")


if __name__ == "__main__":
    main()
