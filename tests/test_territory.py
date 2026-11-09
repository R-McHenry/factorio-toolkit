"""41-territory (PLAN-ORGANIC part T, wave 1): the world placer. The power diagram gives every
movable seed a cell within 5 % of its need (or the cap), a fixed seed exactly its frame, nothing
across an obstacle from its seed; the seeds' sweep puts a net's two ports on a shared boundary and
is deterministic; the Rust kernel agrees with the Python reference on random specs; `fk layout`
dispatches a scope of unplaced sealed modules to it, writes out/territories.json and the hints;
the open flower (tests/data/flower) tessellates in under a minute with the kernel."""
import json
import os
import random
import shutil
import tempfile
import time
import unittest

from fkcore import layout, territory
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file
from fkcore.territory import Seed, TNet, TParams, TSpec, _place_seeds_py, place_seeds, voronoi_py

CAT = Catalog.load()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOWER = os.path.join(ROOT, "tests", "data", "flower")

PAIR = """# pair.fk: two sealed modules with nothing placed; fk layout pair.fk Pair gives each a territory
module Maker size 8x8 {
  port o : out iron-gear-wheel @s2
  fe   = Chest<requester, item=iron-plate, rate=2/s> @(1, 1)
  gear = Assembler<recipe=iron-gear-wheel> @(3, 1)
  net f: fe -> gear
  net g: gear -> o
}
module Taker size 8x8 {
  port i : in iron-gear-wheel @n4
  box = Chest<provider, limit=4> @(3, 3)
  net g: i -> box
}
module Pair size 40x40 {
  a = Maker
  b = Taker
  net g: a.o -> b.i
}
pair = Pair @(0, 0)
"""


def within(area, need, tol=5):
    return abs(area - need) * 100 <= tol * need


def random_tspec(seed, n=4, box=48, sweeps=3):
    """Random seeds (some placed, some fixed), ports, nets (some to the box's edge), obstacles."""
    rnd = random.Random(seed)
    seeds, nets = [], []
    for i in range(n):
        w, h = rnd.randint(3, 9), rnd.randint(3, 9)
        at = None
        if rnd.random() < 0.3:
            at = (rnd.randint(0, box - max(w, h) - 1), rnd.randint(0, box - max(w, h) - 1), rnd.randint(0, 3))
        ports = [(f"p{j}", rnd.choice("nesw"), rnd.choice([None, rnd.randint(0, min(w, h) - 1)]))
                 for j in range(rnd.randint(1, 3))]
        seeds.append(Seed(f"s{i}", (w, h), w * h * rnd.randint(1, 3), max(w, h), at,
                          at is None or rnd.random() < 0.5, ports))
    edges = [(f"e{j}", rnd.choice("nesw"), rnd.choice([None, rnd.randint(0, box - 1)]))
             for j in range(rnd.randint(0, 2))]
    for k in range(rnd.randint(1, n + 1)):
        a, b = rnd.sample(range(n), 2)
        terms = [(a, rnd.randrange(len(seeds[a].ports)), True), (b, rnd.randrange(len(seeds[b].ports)), False)]
        if edges and rnd.random() < 0.4:
            terms.append((-1, rnd.randrange(len(edges)), rnd.random() < 0.5))
        if rnd.random() < 0.3:
            c = rnd.randrange(n)
            terms.append((c, rnd.randrange(len(seeds[c].ports)), rnd.random() < 0.5))
        nets.append(TNet(f"n{k}", rnd.randint(1, 3), terms))
    blocked = []
    for _ in range(rnd.randint(0, 3)):
        x, y = rnd.randint(0, box - 6), rnd.randint(0, box - 6)
        blocked.append((x, y, x + rnd.randint(1, 6), y + rnd.randint(1, 6)))
    params = TParams(sweeps=sweeps, steps=(8, 4, 2, 1), cells=(4, 4, 2, 1), final_cell=rnd.choice([1, 2]))
    return TSpec((0, 0, box, box), blocked, seeds, nets, edges, params)


def spread_seeds(rnd, n, box, mind):
    """``n`` seed points (half-tiles) in a ``box``-tile square at least ``mind`` apart."""
    pts = []
    while len(pts) < n:
        p = (rnd.randint(16, 2 * box - 16), rnd.randint(16, 2 * box - 16))
        if all(abs(p[0] - q[0]) + abs(p[1] - q[1]) >= mind for q in pts):
            pts.append(p)
    return pts


class VoronoiTest(unittest.TestCase):
    def test_cells_meet_their_need(self):
        # seeds spread out with needs the box can hold: every cell reaches its need. (Needs a cell
        # cannot reach, a small one far from any wall or neighbour, stop at the cap and are
        # reported `off its need`: a check, never a gate.)
        for s in range(6):
            rnd = random.Random(s)
            pts = spread_seeds(rnd, 4, 100, 70)
            needs = [rnd.randint(600, 1800) for _ in range(4)]
            x, y = rnd.randint(0, 88), rnd.randint(0, 88)
            blocked = [(x, y, x + rnd.randint(2, 12), y + rnd.randint(2, 12))]
            pts = [p for p in pts if not (2 * blocked[0][0] <= p[0] < 2 * blocked[0][2]
                                          and 2 * blocked[0][1] <= p[1] < 2 * blocked[0][3])]
            needs = needs[:len(pts)]
            # the coarse grid is the sweep's working resolution (16-tile cells: 15 %); the
            # territories are cut at 1, where every cell is within 5 %
            for cell, tol in ((4, 15), (1, 5)):
                own, areas, w, (gw, gh) = voronoi_py(pts, needs, (0, 0, 100, 100), blocked, cell)
                self.assertEqual((gw, gh), (100 // cell, 100 // cell))
                for i in range(len(pts)):
                    self.assertTrue(within(areas[i], needs[i], tol), (s, cell, i, areas[i], needs[i]))
                    self.assertEqual(areas[i], sum(cell * cell for o in own if o == i))
                self.assertFalse(any(o == -2 for o in own if o >= 0))

    def test_fixed_seed_is_exactly_its_frame(self):
        frame = (10, 20, 30, 50)
        own, areas, _w, (gw, _gh) = voronoi_py([(100, 100), None], [1000, 0], (0, 0, 80, 80), [], 1,
                                               fixed=[None, frame])
        self.assertEqual(areas[1], 20 * 30)
        for k, o in enumerate(own):
            x, y = k % gw, k // gw
            inside = frame[0] <= x < frame[2] and frame[1] <= y < frame[3]
            self.assertEqual(o == 1, inside, (x, y, o))
        self.assertTrue(within(areas[0], 1000))

    def test_a_wall_keeps_the_far_piece_from_the_seed(self):
        # a wall across the box with a gap; the one seed on the left asks for more than its side
        wall = [(30, 0, 32, 28), (30, 34, 32, 60)]
        own, areas, _w, (gw, _gh) = voronoi_py([(20, 60)], [2400], (0, 0, 60, 60), wall, 1)
        right = [k for k, o in enumerate(own) if o == 0 and k % gw >= 32]
        self.assertTrue(right, "the cell may grow through the gap")
        # every owned tile is 4-connected to the seed's tile: the piece holding it
        tiles = {(k % gw, k // gw) for k, o in enumerate(own) if o == 0}
        seen, todo = {(10, 30)}, [(10, 30)]
        while todo:
            x, y = todo.pop()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) in tiles and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    todo.append((nx, ny))
        self.assertEqual(seen, tiles)
        self.assertFalse(any(o == 0 for k, o in enumerate(own) if 30 <= k % gw < 32 and not 28 <= k // gw < 34))

    def test_deterministic(self):
        pts = [(30, 30), (150, 40), (90, 160), None]
        a = voronoi_py(pts, [900, 700, 1100, 0], (0, 0, 100, 100), [(40, 40, 50, 50)], 2)
        b = voronoi_py(pts, [900, 700, 1100, 0], (0, 0, 100, 100), [(40, 40, 50, 50)], 2)
        self.assertEqual(a, b)

    def test_runs_of_cover_the_cell(self):
        grid = territory.Grid((0, 0, 20, 12), 4)
        own = [-1] * grid.n
        for k in (0, 1, 5, 6, 7):
            own[k] = 3
        runs = territory.runs_of(own, grid, 3)
        self.assertEqual(sum(b - a for _y, a, b in runs), 5 * 16)
        self.assertEqual(runs[0], (0, 0, 8))
        self.assertEqual(runs[4], (4, 0, 12))

    @unittest.skipUnless(territory.native_on(), "no fkroute with voronoi")
    def test_python_and_rust_agree(self):
        for s in range(10):
            rnd = random.Random(1000 + s)
            pts = [None if rnd.random() < 0.1 else (rnd.randint(0, 120), rnd.randint(0, 120)) for _ in range(5)]
            needs = [rnd.randint(50, 800) for _ in range(5)]
            blocked = [(rnd.randint(0, 50), rnd.randint(0, 50), rnd.randint(51, 60), rnd.randint(51, 60))
                       for _ in range(rnd.randint(0, 2))]
            fixed = [None] * 5
            if rnd.random() < 0.5:
                fixed[0] = (2, 2, 12, 10)
            frames = [None] * 5
            if pts[1] is not None and rnd.random() < 0.5:
                frames[1] = (pts[1][0] // 2, pts[1][1] // 2, pts[1][0] // 2 + 4, pts[1][1] // 2 + 3)
            cell = rnd.choice([1, 2, 4, 8])
            py = voronoi_py(pts, needs, (0, 0, 60, 60), blocked, cell, None, fixed, 20, 5, frames)
            rs = territory._native.voronoi(pts, needs, (0, 0, 60, 60), blocked, cell, None, fixed, 20, 5, frames)
            self.assertEqual((list(rs[0]), list(rs[1]), list(rs[2]), tuple(rs[3])), py, s)


class PlaceSeedsTest(unittest.TestCase):
    def two(self, sweeps=12):
        seeds = [Seed("a", (6, 6), 6 * 6 * 2, 6, None, True, [("a/o", "s", 2)]),
                 Seed("b", (6, 6), 6 * 6 * 2, 6, None, True, [("b/i", "n", None)])]
        nets = [TNet("ab", 1, [(0, 0, True), (1, 0, False)])]
        return TSpec((0, 0, 40, 40), [], seeds, nets, [],
                     TParams(sweeps=sweeps, steps=(8, 4, 2, 1), cells=(4, 4, 2, 1)))

    def test_two_modules_share_a_boundary(self):
        spec = self.two()
        res = _place_seeds_py(spec)
        self.assertEqual(res.unreached, [])
        self.assertTrue(all(a is not None for a in res.at))
        for i in range(2):
            self.assertTrue(within(res.areas[i], spec.seeds[i].need), (i, res.areas[i]))
        # the two ports stand on their cells' boundaries facing each other: a walk of a few tiles
        self.assertLessEqual(res.after[0], 4 * territory.MILLI, res.after)
        self.assertLessEqual(res.after[0], res.before[0])
        pa, pb = res.ports[(0, 0)], res.ports[(1, 0)]
        self.assertLessEqual(abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]), 4)
        # every cell is row runs inside the box, no two cells share a tile
        seen = {}
        for i, runs in enumerate(res.cells):
            for y, x0, x1 in runs:
                self.assertTrue(0 <= y < 40 and 0 <= x0 < x1 <= 40)
                for x in range(x0, x1):
                    self.assertNotIn((x, y), seen)
                    seen[(x, y)] = i
        # a seed's declared frame lies inside its cell
        for i in range(2):
            x, y, rot = res.at[i]
            for ty in range(y, y + 6):
                for tx in range(x, x + 6):
                    self.assertEqual(seen.get((tx, ty)), i, (i, tx, ty))

    def test_fixed_seed_keeps_its_place_and_frame(self):
        seeds = [Seed("k", (10, 10), 100, 10, (20, 20, 0), False, [("k/i", "w", 5)]),
                 Seed("m", (6, 6), 6 * 6 * 2, 6, None, True, [("m/o", "e", None)])]
        spec = TSpec((0, 0, 48, 48), [(0, 0, 48, 4)], seeds, [TNet("mk", 2, [(1, 0, True), (0, 0, False)])],
                     [], TParams(sweeps=8, steps=(8, 4, 2, 1), cells=(4, 4, 2, 1)))
        res = _place_seeds_py(spec)
        self.assertEqual(res.at[0], (20, 20, 0))
        self.assertEqual(res.areas[0], 100)
        self.assertEqual(sum(b - a for _y, a, b in res.cells[0]), 100)
        self.assertTrue(all(20 <= y < 30 and a == 20 and b == 30 for y, a, b in res.cells[0]))
        self.assertEqual(res.unreached, [])
        # the fixed frame's west port is where the movable module's belt arrives
        self.assertEqual(res.ports[(0, 0)], (20, 25))
        x, y, _rot = res.at[1]
        self.assertLess(x + 6, 21, "the movable module ends up west of the fixed one")
        self.assertGreaterEqual(y, 4, "off the blocked strip")

    def test_deterministic_on_random_specs(self):
        for s in range(4):
            spec = random_tspec(s)
            a = _place_seeds_py(spec)
            b = _place_seeds_py(spec)
            self.assertEqual(a, b, s)
            for i, sd in enumerate(spec.seeds):
                if a.at[i] is None:
                    continue
                x, y, rot = a.at[i]
                w, h = sd.size if rot % 2 == 0 else sd.size[::-1]
                self.assertTrue(0 <= x and 0 <= y and x + w <= 48 and y + h <= 48, (s, i, a.at[i]))
                for r in spec.blocked:
                    self.assertFalse(x < r[2] and r[0] < x + w and y < r[3] and r[1] < y + h, (s, i))

    @unittest.skipUnless(territory.native_on(), "no fkroute with place_seeds")
    def test_python_and_rust_agree(self):
        for s in range(6):
            spec = random_tspec(s)
            self.assertEqual(territory._place_seeds_native(spec), _place_seeds_py(spec), s)

    @unittest.skipUnless(territory.native_on(), "no fkroute with place_seeds")
    def test_check_mode_runs_both(self):
        os.environ["FK_NATIVE"] = "check"
        try:
            res = place_seeds(self.two(sweeps=4))
            self.assertEqual(res.unreached, [])
        finally:
            del os.environ["FK_NATIVE"]


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="fkterr-")
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_layout_dispatches_writes_territories_and_hints(self):
        path = os.path.join(self.d, "pair.fk")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(PAIR)
        flat = elaborate_file(path, CAT)
        self.assertEqual(territory.world_scope(flat, "Pair"), "pair")
        lines, code = layout.layout_file(path, flat, CAT, module="Pair", sweeps=6)
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("layout pair Pair: 2 modules, 2 placed now, 0 kept, 0 fixed; 1 nets; "
                                            "plot 40x40 (the frame of Pair); territories"), lines[0])
        self.assertTrue(any(l.strip().startswith("a = Maker @(") for l in lines), lines)
        self.assertTrue(any(l.strip().startswith("b = Taker @(") for l in lines), lines)
        self.assertTrue(any(l.startswith("  cell pair/a: ") and "(off its need)" not in l for l in lines), lines)
        self.assertTrue(any("estimated belts" in l and "every net reaches" in l for l in lines), lines)
        self.assertTrue(any(l.startswith("  shared boundary: ") for l in lines), lines)
        tpath = os.path.join(self.d, "out", "territories.json")
        self.assertTrue(os.path.exists(tpath))
        with open(tpath, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(sorted(data["cells"]), ["pair/a", "pair/b"])
        cell = data["cells"]["pair/a"]
        self.assertEqual(cell["need"], 64)
        self.assertTrue(within(cell["area"], 64))
        self.assertEqual(sum(x1 - x0 for _y, x0, x1 in cell["runs"]), cell["area"])
        self.assertIn("pair/a/o", cell["ports"])
        # --write: the hints go in, the file elaborates with both placed, a second run has no work
        lines, code = layout.layout_file(path, flat, CAT, module="Pair", write=True, sweeps=6)
        self.assertTrue(any(l.startswith("  wrote 2 hints") for l in lines), lines)
        flat2 = elaborate_file(path, CAT)
        self.assertTrue(all("at" in flat2.insts[p].hints for p in ("pair/a", "pair/b")))
        self.assertIsNone(territory.world_scope(flat2, "Pair"))

    def test_cli_and_paper_build(self):
        from tests.test_layout import paper_build
        path = os.path.join(self.d, "pair.fk")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(PAIR)
        flat = elaborate_file(path, CAT)
        lines, code = layout.layout_file(path, flat, CAT, module="Pair", write=True, sweeps=6)
        self.assertEqual(code, 0)
        code, summary, carriers = paper_build(self.d, "pair", "40x40")
        self.assertEqual(code, 0, summary)
        self.assertIn(" 0 unrouted", summary)
        self.assertGreater(carriers, 0)


@unittest.skipUnless(territory.native_on(), "the flower needs the kernel")
class FlowerTest(unittest.TestCase):
    """The open flower (six rivers and the core unplaced, no corridors) tessellated in its 900x1024
    box: under a minute, every cell within 5 % of its need, the inter-river ports reported."""

    def test_flower_tessellates(self):
        d = tempfile.mkdtemp(prefix="fkflower-")
        self.addCleanup(shutil.rmtree, d, True)
        for f in os.listdir(FLOWER):
            if f.endswith(".fk"):
                shutil.copy(os.path.join(FLOWER, f), d)
        path = os.path.join(d, "flower_open.fk")
        flat = elaborate_file(path, CAT)
        t0 = time.perf_counter()
        lines, code = layout.layout_file(path, flat, CAT, module="FlowerOpen")
        took = time.perf_counter() - t0
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("layout flower_open FlowerOpen: 7 modules, 7 placed now"), lines[0])
        self.assertLess(took, 60, f"{took:.1f} s: " + "\n".join(lines))
        cells = [l for l in lines if l.startswith("  cell ")]
        self.assertEqual(len(cells), 7)
        self.assertFalse(any("(off its need)" in l for l in cells), "\n".join(cells))
        self.assertTrue(any("every net reaches" in l for l in lines), "\n".join(lines))
        with open(os.path.join(d, "out", "territories.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(len(data["cells"]), 7)
        self.assertTrue(all(c["at"] is not None and c["runs"] for c in data["cells"].values()))


if __name__ == "__main__":
    unittest.main()
