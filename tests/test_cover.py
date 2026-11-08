"""Power coverage (CORE-V1.md §4.2 "Coverage", §9): poles on free tiles, every electric entity
in a pole's supply area, every pole on one wire network.

Each case is a small hand-built layout in .fkp text. A medium pole powers the 7x7 tiles around it
(supply 3.5) and wires to poles up to 9 tiles away. :func:`audit` re-checks every result from
scratch, without the module's own geometry.
"""
import inspect
import math
import os
import random
import unittest

from fkcore import fkp
from fkcore.catalog import Catalog
from fkcore.cover import apply_cover, cover_power

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "spm10")
MEDIUM = "medium-electric-pole"


def L(text, size=None, name="t"):
    """A factory layout from ``e`` lines: an ``inst ... Literal`` line per owner is added."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    owners = sorted({l.split()[1].rsplit("/", 1)[0] for l in lines if l.startswith("e ")}
                    - {"power"})
    head = [f"fkp 1 factory {name}"] + ([f"size {size}"] if size else [])
    head += [f"inst {o} Literal at 0,0 rot 0 sig -" for o in owners if not o.startswith("~")]
    return fkp.loads("\n".join(head + lines) + "\n")


def audit(lay, poles, keep_out=(), wires=True):
    """(unpowered keys, wire components) of ``lay`` plus ``poles``, checking that every new pole
    stands on free tiles inside the frame and carries no net. ``wires=False`` skips the wiring."""
    taken = set()
    for e in lay.entities.values():
        taken |= CAT.tiles(e.name, e.x, e.y, e.dir)
    keep_out = set(keep_out)
    for p in poles:
        tiles = CAT.tiles(p.name, p.x, p.y)
        assert not tiles & taken, f"{p.key} stands on an entity"
        assert not tiles & keep_out, f"{p.key} stands on keep-out"
        if lay.size:
            assert all(0 <= x < lay.size[0] and 0 <= y < lay.size[1] for x, y in tiles), p.key
        assert p.net is None and p.attrs == {} and p.dir is None, p.key
        taken |= tiles
    every = [e for e in lay.entities.values() if CAT.kind(e.name) == "electric-pole"] + list(poles)
    # A supply square has whole-tile edges: it powers an entity that shares a tile with it.
    area = []
    for p in every:
        s = CAT.pole_supply(p.name)
        area.append({(x, y) for x in range(math.floor(p.x - s), math.ceil(p.x + s))
                     for y in range(math.floor(p.y - s), math.ceil(p.y + s))})
    unpowered = sorted(k for k, e in lay.entities.items() if CAT.is_electric(e.name)
                       and not any(CAT.tiles(e.name, e.x, e.y, e.dir) & a for a in area))
    if not wires:
        return unpowered
    seen, groups = set(), 0
    for i in range(len(every)):
        if i in seen:
            continue
        groups += 1
        todo = [i]
        seen.add(i)
        while todo:
            a = every[todo.pop()]
            for j, b in enumerate(every):
                reach = min(CAT.pole_reach(a.name), CAT.pole_reach(b.name))
                if j not in seen and math.hypot(a.x - b.x, a.y - b.y) <= reach + 1e-9:
                    seen.add(j)
                    todo.append(j)
    return unpowered, groups


ROW = """
    e r/i0 fast-inserter 1.5,1.5 N net=a
    e r/i1 fast-inserter 4.5,1.5 N net=a
    e r/i2 fast-inserter 7.5,1.5 N net=a
    e r/i3 fast-inserter 10.5,1.5 N net=a
    e r/m0 assembling-machine-1 1.5,3.5 recipe=iron-gear-wheel
    e r/m1 assembling-machine-1 4.5,3.5 recipe=iron-gear-wheel
    e r/m2 assembling-machine-1 7.5,3.5 recipe=iron-gear-wheel
    e r/m3 assembling-machine-1 10.5,3.5 recipe=iron-gear-wheel
    e r/o0 fast-inserter 1.5,5.5 N net=g
    e r/o1 fast-inserter 4.5,5.5 N net=g
    e r/o2 fast-inserter 7.5,5.5 N net=g
    e r/o3 fast-inserter 10.5,5.5 N net=g
""" + "".join(f"e r/a{x} transport-belt {x}.5,0.5 E net=a\n" for x in range(12)) \
    + "".join(f"e r/g{x} transport-belt {x}.5,6.5 W net=g\n" for x in range(12))

# Two assemblers 29 tiles apart in a strip three tiles high: their poles are 23 apart.
GAP = """
    e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel
    e m/b assembling-machine-1 30.5,1.5 recipe=iron-gear-wheel"""


class CoverTest(unittest.TestCase):
    def test_single_machine(self):
        lay = L("e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel", "6x6")
        poles, rep = cover_power(lay, CAT)
        self.assertEqual([(p.key, p.name, p.x, p.y) for p in poles],
                         [("power/p0", MEDIUM, 3.5, 0.5)])       # the most, then north, then west
        self.assertEqual((rep.poles, rep.total, rep.covered, rep.components, rep.uncovered),
                         (["power/p0"], 1, 1, 1, []))
        self.assertEqual((rep.bridges, rep.pruned, rep.existing, rep.checks), (0, 0, 0, []))
        self.assertEqual(audit(lay, poles), ([], 1))
        self.assertEqual(rep.summary(), "cover power power pole=medium-electric-pole: 1 poles "
                         "(0 bridging, 0 existing); 1/1 electric entities covered; "
                         "1 wire component")

    def test_pinned_poles_stay_and_new_ones_only_fill_gaps(self):
        # 1.7 (Rory, 2026-10-21: pin and patch): a rebuild that adds a machine keeps the poles that
        # stand and adds one only where the new machine has none (it used to re-lay all of them)
        lay = L(ROW, "12x7")
        first, _rep = cover_power(lay, CAT)
        grown = L(ROW + "e r/m4 assembling-machine-1 13.5,3.5 recipe=iron-gear-wheel\n", "16x7")
        poles, rep = cover_power(grown, CAT, pinned=first)
        kept = {(p.key, p.x, p.y) for p in first}
        self.assertTrue(kept <= {(p.key, p.x, p.y) for p in poles})
        self.assertEqual(rep.pinned, len(first))
        self.assertEqual(audit(grown, poles), ([], 1))
        new = [p for p in poles if (p.key, p.x, p.y) not in kept]
        self.assertTrue(all(int(p.key.rsplit("p", 1)[1]) >= len(first) for p in new))
        self.assertIn(f"{len(first)} kept where they stand", rep.summary())

    def test_switching_the_pole_kind_lays_the_new_kind_everywhere(self):
        # 3.1 (Rory 11-08: the world never feeds a step): nothing the diff found built reaches
        # the cover, so a pinned pole of another kind is laid again in the new kind (2.0.1 had
        # kept a built medium pole from out/standing.json; what stands is the diff's difference)
        lay = L(ROW, "12x7")
        first, _rep = cover_power(lay, CAT)                       # medium poles
        poles, rep = cover_power(lay, CAT, pole="small-electric-pole", pinned=first)
        self.assertTrue(all(p.name == "small-electric-pole" for p in poles))
        self.assertEqual(rep.pinned, 0)
        self.assertEqual(audit(lay, poles), ([], 1))
        self.assertNotIn("standing", repr(inspect.signature(cover_power)))

    def test_a_pinned_pole_under_a_new_entity_goes(self):
        lay = L("e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel", "6x6")
        first, _rep = cover_power(lay, CAT)                       # power/p0 at 3.5,0.5
        moved = L("e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel\n"
                  "e m/c wooden-chest 3.5,0.5", "6x6")
        poles, rep = cover_power(moved, CAT, pinned=first)
        self.assertEqual(rep.pinned, 0)
        self.assertNotIn((3.5, 0.5), {(p.x, p.y) for p in poles})
        self.assertEqual(audit(moved, poles), ([], 1))

    def test_a_pinned_pole_that_powers_nothing_goes(self):
        far = [fkp.Entity("power/p0", MEDIUM, 3.5, 0.5), fkp.Entity("power/p1", MEDIUM, 20.5, 0.5)]
        lay = L("e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel", "24x6")
        poles, rep = cover_power(lay, CAT, pinned=far)
        self.assertEqual([(p.key, p.x, p.y) for p in poles], [("power/p0", 3.5, 0.5)])
        self.assertEqual((rep.pinned, rep.pruned), (1, 2))        # p1, and the bridge laid to it

    def test_apply_adds_the_poles_and_the_record(self):
        lay = L("e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel", "6x6")
        out = apply_cover(lay, CAT)
        self.assertEqual(fkp.dumps(out, CAT), (
            "fkp 1 factory t\nsize 6x6\ninst m Literal at 0,0 rot 0 sig -\n"
            "cover power power pole=medium-electric-pole\n"
            "e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel\n"
            "e power/p0 medium-electric-pole 3.5,0.5\n"))
        self.assertNotIn("power/p0", lay.entities)                # the input is left alone
        self.assertEqual(lay.covers, {})

    def test_a_row_of_assemblers_with_inserters(self):
        lay = L(ROW, "12x7")
        poles, rep = cover_power(lay, CAT)
        # Rows 0, 2-4 and 6 are full; the inserter rows each need two poles of their own.
        self.assertEqual((len(poles), rep.total, rep.covered, rep.components), (4, 12, 12, 1))
        self.assertEqual(audit(lay, poles), ([], 1))
        self.assertEqual({p.y for p in poles}, {1.5, 5.5})
        self.assertEqual(fkp.invariants(apply_cover(lay, CAT), CAT), [])

    def test_every_pole_prototype(self):
        lay = L("e m/a assembling-machine-1 4.5,4.5 recipe=iron-gear-wheel", "10x10")
        for pole in ("small-electric-pole", MEDIUM, "big-electric-pole", "substation"):
            with self.subTest(pole=pole):
                poles, rep = cover_power(lay, CAT, pole=pole)
                self.assertEqual((len(poles), rep.covered, rep.components), (1, 1, 1))
                self.assertEqual(audit(lay, poles), ([], 1))
                self.assertEqual(fkp.invariants(apply_cover(lay, CAT, pole=pole), CAT), [])

    def test_a_gap_wider_than_the_wire_reach_is_bridged(self):
        lay = L(GAP, "33x3")
        poles, rep = cover_power(lay, CAT)
        # One pole per machine, 23 tiles apart; two bridge poles make three hops of at most 9.
        self.assertEqual((len(poles), rep.bridges, rep.covered, rep.components), (4, 2, 2, 1))
        self.assertEqual(audit(lay, poles), ([], 1))
        self.assertEqual(rep.checks, [])
        xs = sorted(p.x for p in poles)
        self.assertEqual((xs[0], xs[-1]), (3.5, 26.5))
        self.assertTrue(all(b - a <= 9 for a, b in zip(xs, xs[1:])))

    def test_a_gap_nothing_can_bridge_is_reported(self):
        wall = [(x, y) for x in range(10, 21) for y in range(3)]   # 11 keep-out columns
        lay = L(GAP, "33x3")
        poles, rep = cover_power(lay, CAT, keep_out=wall)
        self.assertEqual((len(poles), rep.covered, rep.components), (2, 2, 2))
        self.assertEqual(audit(lay, poles, wall), ([], 2))
        self.assertEqual(rep.splits, [["power/p1"]])
        self.assertEqual(rep.lines(), [
            "power-split cover power: power/p1 (1 pole) cannot be wired to the main grid: no chain "
            "of free spots at most 9 tiles apart joins them"])
        self.assertFalse(rep.ok)
        self.assertEqual(fkp.invariants(apply_cover(lay, CAT, keep_out=wall), CAT), [])

    def test_an_entity_with_every_nearby_tile_taken_is_reported(self):
        ring = "\n".join(f"e b/b{k} transport-belt {x + 0.5},{y + 0.5} E net=a"
                         for k, (x, y) in enumerate((x, y) for y in range(3) for x in range(3)
                                                    if (x, y) != (1, 1)))
        lay = L(ring + "\ne i/x fast-inserter 1.5,1.5 N net=a", "3x3")
        poles, rep = cover_power(lay, CAT)
        self.assertEqual((poles, rep.total, rep.covered, rep.components), ([], 1, 0, 0))
        reason = ("all 49 spots a medium-electric-pole could power it from are taken: 9 on "
                  "entities (b, i); 40 outside the 3x3 frame")
        self.assertEqual(rep.uncovered, [("i/x", reason)])
        self.assertEqual(rep.lines(), ["NO_POWER i/x: " + reason])
        self.assertEqual(fkp.invariants(apply_cover(lay, CAT), CAT), [])

    def test_keep_out_blocks_like_an_entity(self):
        lay = L("""
            e i/x fast-inserter 0.5,0.5 N net=a
            e m/a assembling-machine-1 20.5,1.5 recipe=iron-gear-wheel""")       # no frame
        near = [(x, y) for x in range(-3, 4) for y in range(-3, 4) if (x, y) != (0, 0)]
        poles, rep = cover_power(lay, CAT, keep_out=near)
        self.assertEqual((len(poles), rep.total, rep.covered), (1, 2, 1))
        self.assertEqual(audit(lay, poles, near), (["i/x"], 1))
        self.assertEqual(rep.uncovered, [("i/x", "all 49 spots a medium-electric-pole could power "
                                          "it from are taken: 1 on entities (i); 48 keep-out")])

    def test_a_pick_later_poles_make_redundant_is_pruned(self):
        # Greedy takes x=6 first (four inserters), then x=1 and x=10 for the ends, which power
        # those four as well and wire to each other (9 apart): x=6 goes again.
        lay = L("\n".join(f"e i/x{x} fast-inserter {x}.5,0.5 N net=a" for x in (0, 3, 4, 8, 9, 12)),
                "13x1")
        poles, rep = cover_power(lay, CAT)
        self.assertEqual([(p.x, p.y) for p in poles], [(1.5, 0.5), (10.5, 0.5)])
        self.assertEqual((rep.pruned, rep.covered, rep.components), (1, 6, 1))
        self.assertEqual(audit(lay, poles), ([], 1))


class UnitsTest(unittest.TestCase):
    """2.1.35: poles laid per sealed unit, alike units alike, one last pass joining them."""

    def test_alike_units_take_the_first_ones_poles_and_the_grid_is_one(self):
        from fkcore.cover import cover_power_units
        text = ""
        for k, dx in enumerate((0, 20, 40)):
            for line in ROW.strip().splitlines():
                _e, key, name, pos, *rest = line.split()
                x, y = pos.split(",")
                text += f"e u{k}/{key} {name} {float(x) + dx},{y} {' '.join(rest)}\n"
        lay = L(text, "52x7")
        units = [(f"u{k}", (dx, 0, dx + 12, 7), ("Row", 0)) for k, dx in enumerate((0, 20, 40))]
        poles, rep = cover_power_units(lay, CAT, units)
        self.assertEqual(rep.units, (1, 2))
        self.assertEqual(audit(lay, poles), ([], 1))
        self.assertEqual((rep.covered, rep.total, rep.components), (36, 36, 1))
        inside = [sorted((p.x - dx, p.y) for p in poles if dx <= p.x < dx + 12)
                  for dx in (0, 20, 40)]
        self.assertEqual(inside[0], inside[1])
        self.assertEqual(inside[1], inside[2])
        self.assertEqual(len({p.key for p in poles}), len(poles))
        self.assertTrue(all(p.key.startswith("power/p") for p in poles))


class ExistingPolesTest(unittest.TestCase):
    def test_existing_poles_power_and_anchor_the_grid(self):
        lay = L("""
            e lit/m assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel
            e lit/p0 medium-electric-pole 3.5,0.5
            e m/b assembling-machine-1 20.5,1.5 recipe=iron-gear-wheel""", "23x3")
        poles, rep = cover_power(lay, CAT)
        # m/b's pole stands as near lit/p0 as it can (16.5, 13 tiles off); one pole bridges.
        self.assertEqual((len(poles), rep.bridges, rep.existing), (2, 1, 1))
        self.assertEqual((rep.covered, rep.components), (2, 1))
        self.assertEqual(audit(lay, poles), ([], 1))
        out = apply_cover(lay, CAT)
        self.assertEqual(out.entities["lit/p0"], lay.entities["lit/p0"])

    def test_a_rerun_replaces_its_own_poles_and_keeps_the_rest(self):
        lay = L("""
            e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel
            e m/b assembling-machine-1 1.5,8.5 recipe=iron-gear-wheel
            e power/p0 medium-electric-pole 9.5,9.5
            e power/tie small-electric-pole 4.5,8.5""", "12x12")
        lay.covers["power"] = fkp.Cover("power", "power", {"pole": "small-electric-pole"})
        out = apply_cover(lay, CAT)
        self.assertEqual(fkp.invariants(out, CAT), [])
        self.assertEqual(out.covers["power"].params, {"pole": MEDIUM})
        self.assertIn("power/tie", out.entities)                   # hand-placed: a wire node
        self.assertNotEqual((out.entities["power/p0"].x, out.entities["power/p0"].y), (9.5, 9.5))
        self.assertEqual(audit(L("""
            e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel
            e m/b assembling-machine-1 1.5,8.5 recipe=iron-gear-wheel"""),
            [e for e in out.entities.values() if e.owner == "power"]), ([], 1))
        self.assertEqual(fkp.dumps(apply_cover(out, CAT)), fkp.dumps(out))     # idempotent

    def test_bad_arguments_raise(self):
        lay = L("e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel")
        with self.assertRaises(ValueError):
            cover_power(lay, CAT, pole="assembling-machine-1")
        with self.assertRaises(ValueError):
            cover_power(lay, CAT, owner="m")                     # an inst path
        lay.covers["bots"] = fkp.Cover("bots", "robots", {})
        with self.assertRaises(ValueError):
            cover_power(lay, CAT, owner="bots")


class DeterminismTest(unittest.TestCase):
    def test_the_same_input_gives_the_same_poles(self):
        lay = fkp.load(os.path.join(GAME, "redgreen.fkp"))
        first, rep = cover_power(lay, CAT)
        again, _ = cover_power(lay, CAT)
        self.assertEqual(first, again)
        keys = list(lay.entities)
        random.Random(7).shuffle(keys)
        shuffled = fkp.Layout(lay.level, lay.name, lay.size, dict(lay.insts), dict(lay.covers),
                              entities={k: lay.entities[k] for k in keys})
        self.assertEqual(cover_power(shuffled, CAT)[0], first)    # whatever the entity order
        self.assertEqual(fkp.dumps(apply_cover(shuffled, CAT)), fkp.dumps(apply_cover(lay, CAT)))


class ElectricTest(unittest.TestCase):
    def test_is_electric(self):
        electric = ["assembling-machine-1", "electric-mining-drill", "pumpjack", "big-mining-drill",
                    "electric-furnace", "recycler", "fast-inserter", "long-handed-inserter",
                    "lab", "roboport", "beacon", "radar", "small-lamp", "laser-turret", "pump"]
        burner = ["burner-inserter", "burner-mining-drill", "stone-furnace", "steel-furnace",
                  "boiler", "offshore-pump", "transport-belt", "iron-chest", MEDIUM]
        self.assertEqual([n for n in electric if not CAT.is_electric(n)], [])
        self.assertEqual([n for n in burner if CAT.is_electric(n)], [])

    def test_a_pumpjack_and_an_electric_furnace_get_power(self):
        lay = L("""
            e o/j pumpjack 1.5,1.5 N
            e s/f electric-furnace 12.5,1.5 recipe=iron-plate
            e s/g stone-furnace 20,1 recipe=iron-plate""", "22x3")
        poles, rep = cover_power(lay, CAT)
        self.assertEqual((rep.total, rep.covered, rep.components), (2, 2, 1))
        self.assertEqual(audit(lay, poles), ([], 1))


class RedgreenTest(unittest.TestCase):
    """games/spm10/redgreen.fkp: 14 rows, 566 entities, no routes yet."""

    @classmethod
    def setUpClass(cls):
        cls.lay = fkp.load(os.path.join(GAME, "redgreen.fkp"))
        cls.poles, cls.rep = cover_power(cls.lay, CAT)

    def test_counts(self):
        rep = self.rep
        self.assertEqual((len(self.lay.insts), len(self.lay.entities)), (14, 566))
        self.assertEqual((len(rep.poles), rep.bridges, rep.total, rep.covered, rep.components),
                         (35, 1, 185, 183, 1))
        self.assertEqual(audit(self.lay, self.poles), (["iron_mine/m2", "iron_mine/m3"], 1))
        print(f"\nredgreen covered: {rep.summary()}")

    def test_only_drills_no_free_tile_can_reach_stay_dark(self):
        # The MinerRow sits on the frame's top edge with its drills packed at pitch 3: the two
        # inner north drills have drills, the ore belt and the frame edge on every tile within
        # reach of a medium pole. Every other electric entity has a free spot and gets power.
        reason = ("all 81 spots a medium-electric-pole could power it from are taken: 54 on "
                  "entities (iron_mine); 27 outside the 46x43 frame")
        self.assertEqual(self.rep.uncovered, [("iron_mine/m2", reason), ("iron_mine/m3", reason)])
        self.assertEqual([c.code for c in self.rep.checks], ["NO_POWER", "NO_POWER"])
        free = [(x, y) for x in range(46) for y in range(43)]
        everywhere = [fkp.Entity(f"x/{x}_{y}", MEDIUM, x + 0.5, y + 0.5) for x, y in free]
        taken = set()
        for e in self.lay.entities.values():
            taken |= fkp.tiles_of(CAT, e)
        everywhere = [p for p in everywhere if (int(p.x), int(p.y)) not in taken]
        self.assertEqual(audit(self.lay, everywhere, wires=False),
                         [k for k, _r in self.rep.uncovered])

    def test_apply_cover_keeps_the_layout_well_formed(self):
        out = apply_cover(self.lay, CAT)
        self.assertEqual(fkp.invariants(out, CAT), [])
        self.assertEqual(len(out.entities), 566 + 35)
        self.assertEqual(out.covers["power"], fkp.Cover("power", "power", {"pole": MEDIUM}))
        self.assertEqual(fkp.loads(fkp.dumps(out, CAT)), out)       # the writer takes it


if __name__ == "__main__":
    unittest.main()
