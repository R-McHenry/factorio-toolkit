"""ground_flower.py: write flower_ground.fk, the open flower on real ground (PLAN-ORGANIC T6,
43-territory step 3). The same six rivers and core as flower_open.fk, no corridors, and the
flower's rim ports replaced by **stand-in mines pinned on ore**: one ``Stand`` module per rim
feed, ``@patch(RES)``, its out port feeding the river's in port (a ``A | B`` pair feed gets two
stands and a ``lanes`` line). Crude feeds are ``Well`` stands (a pumpjack, pinned on
``crude-oil``); the water feed is a ``Shore`` stand (an offshore pump) that is not pinned
(water is no patch): it moves like a module.

    python tests/data/flower/ground_flower.py

Then, in a game folder with the flower files and the lab's terrain read east of x 2100
(``fk read-terrain map --area 2100,-600,3100,600``), a surface file
``surface lab`` / ``free`` / ``force lab`` / ``terrain map`` /
``place flower_ground = flower_ground plot 2100,-512 900x1024``, and
``fk layout flower_ground.fk --write``: the pinned stands on their patches, the rivers and the
core tessellated round them, the water as obstacles.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from open_flower import PARTS, ROUTES, module_ports, split_net      # noqa: E402

FLUIDS = {"water", "crude-oil", "sulfuric-acid", "lubricant", "petroleum-gas", "steam"}

STANDS = """\
# a stand-in mine: what a MinerRow on the patch will be, as a sealed module the territory
# placer pins on the ore (its seed the patch's centroid, its cell the patch grown to its need)
module Stand<res> size 40x40 {
  port o : out $res | $res @s20
  src = Chest<requester, item=$res, rate=45/s> @(1, 1)
  net g: src -> o
}
# a stand-in well: a pumpjack on a crude patch
module Well size 20x20 {
  port o : out crude-oil @s10
  pj = Pumpjack<n=1, rate=30/s> @(9, 9)      # the frame is centred on the patch: the jack on its middle site
  net c: pj -> o
}
# a stand-in shore: an offshore pump; water is no patch, so it is placed like a module
module Shore size 12x12 {
  port o : out water @s6
  p = OffshorePump<rate=1200/s> @(5, 0)      # at the frame's north edge: the water is the two rows north of it
  net w: p -> o
}
"""


def main():
    have = {name: module_ports(os.path.join(HERE, f), mod) for name, (mod, f, _s) in PARTS.items()}
    lines = ["# flower_ground.fk: the open flower on real ground, written by ground_flower.py: the",
             "# rivers and the core unplaced, no corridors, every rim feed a stand-in mine pinned on",
             "# its ore (@patch). fk layout flower_ground.fk --write on a surface with a terrain.", ""]
    for name, (mod, f, _s) in PARTS.items():
        lines.append(f'import {mod} from "{f}"')
    lines += ["", STANDS]
    body, feeds = [], []
    for name, (mod, f, side) in PARTS.items():
        body.append(f"{name} = {mod}")
    for name, (mod, f, side) in PARTS.items():
        if side is None:
            continue
        for p, (d, items, pside, pos) in sorted(have[name].items(), key=lambda kv: kv[1][3]):
            if pside != "n" or d != "in":
                continue
            fp = f"{name}_{p}"
            if items[0] == "water":
                body.append(f"{fp} = Shore")
                feeds.append(f"net {fp}_: {fp}.o -> {name}.{p}")
            elif items[0] == "crude-oil":
                body.append(f"{fp} = Well @patch(crude-oil)")
                feeds.append(f"net {fp}_: {fp}.o -> {name}.{p}")
            elif len(items) == 2 and items[0] != items[1]:
                for tag, item in zip("ab", items):
                    body.append(f"{fp}_{tag} = Stand<res={item}> @patch({item})")
                    feeds.append(f"net {fp}__{tag} items {item}: {fp}_{tag}.o -> {name}.{p}")
                feeds.append(f"lanes {fp}__a | {fp}__b")
            else:
                body.append(f"{fp} = Stand<res={items[0]}> @patch({items[0]})")
                feeds.append(f"net {fp}_: {fp}.o -> {name}.{p}")
    nets = []
    for a, pa, b, pb in ROUTES:
        items = have[a][pa][1]
        nets += [l.strip() for l in split_net(f"{a}_{pa}", items, f"{a}.{pa}", f"{b}.{pb}")]
    lines += body + [""] + feeds + [""] + nets + [""]
    out = os.path.join(HERE, "flower_ground.fk")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    stands = sum(1 for l in body if "Stand<" in l or "= Well" in l)
    print(f"wrote {out}: {stands} stand-ins pinned on ore, {len(ROUTES)} routes")


if __name__ == "__main__":
    main()
