import math
import os
import unittest

from fkcore import codec, compose, expand, fkp, lang, rates
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate, elaborate_file
from fkcore.fragments import FragmentError, fragment
from fkcore.templates import machines as template_machines

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "spm10")
REDGREEN = os.path.join(GAME, "redgreen.fk")

_REACH = {"fast-inserter": 1, "inserter": 1, "long-handed-inserter": 2}
_DIRV = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}


def cases():
    """(kind, params, inputs, outputs) for every fragment shape V1 has."""
    out = []
    for n in (1, 2, 3, 5):
        out.append(("AsmRow", {"n": n, "recipe": "pipe"}, [["iron-plate"]], [["pipe"]]))
        out.append(("AsmRow", {"n": n, "recipe": "transport-belt"},
                    [["iron-plate"], ["iron-gear-wheel"]], [["transport-belt"]]))
        out.append(("SmelterRow", {"n": n, "_recipe": "iron-plate", "_fuel": "coal"},
                    [["iron-ore"], ["coal"]], [["iron-plate"]]))
        out.append(("SmelterRow", {"n": n, "_recipe": "iron-plate", "_fuel": "coal"},
                    [["iron-ore", "coal"]], [["iron-plate"]]))
        out.append(("MinerRow", {"n": n, "resource": "iron-ore"}, [], [["iron-ore"]]))
        out.append(("LabRow", {"n": n}, [["automation-science-pack"]], []))
        out.append(("LabRow", {"n": n}, [["automation-science-pack"], ["chemical-science-pack"]],
                    []))
    return out


def index(frag):
    tiles = {}
    for e in frag.entities:
        for t in CAT.tiles(e.name, float(e.x), float(e.y), e.dir or 0):
            tiles[t] = e
    return tiles


class FragmentTest(unittest.TestCase):
    def test_machines_match_the_template(self):
        for kind, params, ins, outs in cases():
            frag = fragment(kind, params, ins, outs)
            p = {k: v for k, v in params.items() if not k.startswith("_")}
            if kind == "SmelterRow":
                p["recipe"] = params["_recipe"]
            logical = [(m.local, m.prototype) for m in template_machines(kind, p, CAT)]
            geometric = [(e.local, e.name) for e in frag.entities if e.role is None]
            self.assertEqual(sorted(logical), sorted(geometric), (kind, params))

    def test_every_inserter_works_its_role(self):
        for kind, params, ins, outs in cases():
            frag = fragment(kind, params, ins, outs)
            at = index(frag)
            for e in frag.entities:
                if e.name not in _REACH:
                    continue
                r = _REACH[e.name]
                dx, dy = _DIRV[e.dir]                  # v4 convention: the side it picks from
                tx, ty = math.floor(e.x), math.floor(e.y)
                pick, drop = at.get((tx + dx * r, ty + dy * r)), at.get((tx - dx * r, ty - dy * r))
                role = frag.roles[e.role]
                belt, machine = (pick, drop) if role.side == "in" else (drop, pick)
                where = f"{kind} {params} {e.local}"
                self.assertIsNotNone(belt, where)
                self.assertEqual((belt.name, belt.role), ("transport-belt", e.role), where)
                self.assertIsNotNone(machine, where)
                self.assertIsNone(machine.role, where)
                self.assertIn(machine.local, role.machines, where)

    def test_drills_drop_on_the_belt(self):
        frag = fragment("MinerRow", {"n": 5, "resource": "coal"}, [], [["coal"]])
        at = index(frag)
        for e in frag.entities:
            if e.role is None:
                dx, dy = _DIRV[e.dir]
                t = (math.floor(e.x + dx * 2), math.floor(e.y + dy * 2))
                self.assertEqual((at[t].name, at[t].role), ("transport-belt", "out"), e.local)

    def test_no_overlap_in_any_rotation(self):
        for kind, params, ins, outs in cases():
            frag = fragment(kind, params, ins, outs)
            for rot in range(4):
                lay = fkp.Layout("factory", "t", frag.size if rot % 2 == 0 else frag.size[::-1])
                lay.insts["x"] = fkp.Inst("x", kind, {}, 0, 0, rot, frag.sig)
                for e in frag.entities:
                    x, y, d = compose.turn(float(e.x), float(e.y), e.dir, rot, frag.size)
                    lay.add(fkp.Entity(f"x/{e.local}", e.name, x, y, d,
                                       {"net": e.role} if e.role else {}))
                self.assertEqual(fkp.invariants(lay, CAT), [], (kind, params, rot))

    def test_a_third_input_belt_is_refused(self):
        with self.assertRaises(FragmentError) as cm:
            fragment("AsmRow", {"n": 1, "recipe": "inserter"},
                     [["iron-plate"], ["iron-gear-wheel"], ["electronic-circuit"]], [["inserter"]])
        self.assertIn("one or two input belts", str(cm.exception))

    def test_signature_follows_the_footprint(self):
        a = fragment("AsmRow", {"n": 2, "recipe": "pipe"}, [["iron-plate"]], [["pipe"]])
        b = fragment("AsmRow", {"n": 2, "recipe": "iron-stick"}, [["iron-plate"]], [["iron-stick"]])
        c = fragment("AsmRow", {"n": 3, "recipe": "pipe"}, [["iron-plate"]], [["pipe"]])
        self.assertEqual(a.sig, b.sig)            # a recipe swap is a trivial change
        self.assertNotEqual(a.sig, c.sig)         # a new machine is not


class ExpandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flat = elaborate_file(REDGREEN, CAT)
        cls.lay, cls.notes = expand.expand_factory(cls.flat, CAT)

    def test_redgreen_expands_cleanly(self):
        self.assertEqual(fkp.invariants(self.lay, CAT), [])
        self.assertEqual(len(self.lay.entities), 551)
        self.assertEqual(self.lay.size, (46, 43))
        self.assertEqual(len(self.notes), 1)
        self.assertTrue(self.notes[0].startswith("ins: AsmRow takes one or two input belts"))

    def test_every_carrier_names_a_net_of_the_factory(self):
        for key, e in self.lay.entities.items():
            if CAT.kind(e.name) in fkp.CARRIER_TYPES:
                self.assertIn(e.net, self.flat.nets, key)
        self.assertEqual(fkp.invariants(self.lay, CAT, nets=self.flat.nets), [])

    def test_machine_keys_are_the_netlist_keys(self):
        placed = {k for k, e in self.lay.entities.items()
                  if CAT.kind(e.name) not in fkp.CARRIER_TYPES}
        expected = {k for k, m in self.flat.machines.items() if m.inst != "ins"}
        self.assertEqual(placed, expected)

    def test_rotated_instance(self):
        rec = self.lay.insts["coal_copper"]
        self.assertEqual((rec.x, rec.y, rec.rot), (30, 0, 1))
        m0 = self.lay.entities["coal_copper/m0"]
        self.assertEqual((m0.x, m0.y, m0.dir), (32.5, 1.5, 12))   # was facing S, now W

    def test_blueprint_round_trip(self):
        text = fkp.dumps(self.lay, CAT)
        self.assertEqual(fkp.dumps(codec.blueprint_to_fkp(codec.fkp_to_blueprint(self.lay))), text)

    def test_committed_fkp_is_current(self):
        with open(os.path.join(GAME, "redgreen.fkp"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), fkp.dumps(self.lay, CAT))

    def test_explain(self):
        text = expand.explain(self.flat, self.lay, "red", CAT)
        self.assertIn("red = AsmRow<n=5, recipe=automation-science-pack> at 0,28 rot 0", text)
        self.assertIn("net copper", text)
        self.assertIn("net gear", text)
        self.assertIn("net packs", text)
        self.assertIn("attach 0.5,35.5 W", text)


class UnfoldTest(unittest.TestCase):
    def test_unfold_keeps_every_key_line_and_rate(self):
        with open(REDGREEN, encoding="utf-8") as fh:
            src = fh.read()
        flat = elaborate_file(REDGREEN, CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        before = fkp.dumps(lay, CAT)
        for path in ("red", "iron_smelt", "iron_mine", "labs"):
            src, lay = expand.unfold(src, flat, lay, path)
            f = lang.parse(src, REDGREEN)
            flat2 = elaborate(f, dict(f.modules), CAT, "redgreen", layout=lay)
            self.assertEqual(flat2.insts[path].kind, "Literal")
            # the .fkp: every entity line identical, only the inst record says Literal now
            after = fkp.dumps(lay, CAT)
            self.assertEqual([l for l in after.splitlines() if l.startswith("e ")],
                             [l for l in before.splitlines() if l.startswith("e ")])
            self.assertIn(f"inst {path} Literal from=", after)
            # the netlist: same machines, same endpoints, same nets
            for key, m in flat.machines.items():
                m2 = flat2.machines[key]
                self.assertEqual((m2.prototype, m2.recipe, m2.needs, m2.makes, m2.sink),
                                 (m.prototype, m.recipe, m.needs, m.makes, m.sink), key)
            self.assertEqual({n: (x.items, x.drivers, x.consumers) for n, x in flat.nets.items()},
                             {n: (x.items, x.drivers, x.consumers) for n, x in flat2.nets.items()})
            # and a re-expansion keeps the pinned entities where they are
            lay2, _ = expand.expand_factory(flat2, CAT, previous=lay)
            self.assertEqual(fkp.dumps(lay2, CAT), after)
            flat = flat2
        self.assertEqual(rates.solve(flat).util, rates.solve(elaborate_file(REDGREEN, CAT)).util)
        self.assertIn("red   = Literal   # unfolded from AsmRow<n=5, recipe=automation-science-pack>",
                      src.replace("  @(0, 28)", ""))


if __name__ == "__main__":
    unittest.main()
