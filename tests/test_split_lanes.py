"""2.0.76 (Rory, 2026-10-31: "figure out why we keep getting shared belt jams"): a route inserter
that loads from a chest of several items is filtered to its net's items, and ``net NAME split:``
puts each item on a lane of its own, one filtered inserter per lane, side-loaded together."""
import unittest

from fkcore import codec, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate

CAT = Catalog.load()

BLUE = """
bq   = Chest<requester, item="engine-unit,advanced-circuit,sulfur,plastic-bar"> @(3, 3)
bsc  = Assembler<recipe=chemical-science-pack> @(14, 0)
bsc2 = Assembler<recipe=chemical-science-pack> @(14, 7)
net blue items engine-unit, advanced-circuit, sulfur{split}: bq -> bsc, bsc2
"""
PAIR = """
bq   = Chest<requester, item="engine-unit,sulfur,plastic-bar"> @(3, 3)
bsc  = Assembler<recipe=chemical-science-pack> @(14, 0)
net eng items engine-unit: bq -> bsc
net sul items sulfur: bq -> bsc
lanes eng | sul
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def routed(text):
    flat = flat_of(text)
    lay, _notes = expand.expand_factory(flat, CAT)
    return flat, route.route_layout(flat, lay, CAT)


def loaders(r):
    """{net: [filter]} of the route inserters standing beside the chest at (3, 3)."""
    out = {}
    for e in r.layout.entities.values():
        if "inserter" in e.name and e.owner.startswith("~") and abs(e.x - 3.5) + abs(e.y - 3.5) <= 2:
            out.setdefault(e.attrs["net"], []).append(e.attrs.get("filter"))
    return out


class FilterTest(unittest.TestCase):
    def test_a_sushi_loader_takes_only_its_nets_items(self):
        # unfiltered it put the plastic on the belt too, which no sink on it takes (the 10-29 run)
        _flat, r = routed(BLUE.format(split=""))
        self.assertEqual(loaders(r), {"blue": ["engine-unit|advanced-circuit|sulfur"]})

    def test_a_pair_from_one_chest_gets_one_item_per_lane(self):
        _flat, r = routed(PAIR)
        self.assertEqual(loaders(r), {"eng": ["engine-unit"], "sul": ["sulfur"]})

    def test_a_single_item_source_is_left_unfiltered(self):
        _flat, r = routed("""
fe   = Chest<requester, item=iron-plate> @(3, 3)
gear = Assembler<recipe=iron-gear-wheel> @(14, 0)
net fe: fe -> gear
""")
        self.assertTrue(all("filter" not in e.attrs for e in r.layout.entities.values()))

    def test_the_filter_reaches_the_blueprint(self):
        _flat, r = routed(PAIR)
        text = fkp.dumps(r.layout)
        back = fkp.loads(text)
        ins = [e for e in back.entities.values() if e.attrs.get("filter") == "sulfur"]
        self.assertEqual(len(ins), 1)
        fields = codec.control_behavior(ins[0].attrs)
        self.assertTrue(fields["use_filters"])
        self.assertEqual([f["name"] for f in fields["filters"]], ["sulfur"])

    def test_hands_minimize_keeps_a_filtered_hand_at_a_rung_that_filters(self):
        # FRICTION 11-11 (the bootstrap seed): `hands minimize --allow inserter` lowered the
        # filtered loaders to plain inserters, which can't filter in 2.0, and the seed's chest put
        # wood and stone on its copper belt
        from fkcore import hands
        flat, r = routed(PAIR)
        new, lines, _changed = hands.assign(r.layout, flat, CAT, allow=("inserter",))
        got = {e.attrs["net"]: (e.name, e.attrs.get("filter")) for e in new.entities.values()
               if "inserter" in e.name and e.attrs.get("filter")}
        self.assertEqual(got, {"eng": ("fast-inserter", "engine-unit"),
                               "sul": ("fast-inserter", "sulfur")})
        self.assertIn("2 kept at a rung that filters", lines[0])


class SplitTest(unittest.TestCase):
    def test_parses(self):
        (net,) = lang.parse("net b split: x -> y\n", "t.fk").body.nets
        self.assertTrue(net.split)
        (net,) = lang.parse("net b: x -> y\n", "t.fk").body.nets
        self.assertFalse(net.split)

    def test_one_net_per_item_two_to_a_belt(self):
        flat = flat_of(BLUE.format(split=" split"))
        self.assertEqual(sorted(flat.nets), ["blue_advanced_circuit", "blue_engine_unit",
                                             "blue_sulfur"])
        self.assertEqual(flat.pairs, {"blue_engine_unit|blue_advanced_circuit":
                                      ("blue_engine_unit", "blue_advanced_circuit")})
        self.assertEqual(flat.split["blue"], ["blue_engine_unit", "blue_advanced_circuit",
                                              "blue_sulfur"])
        self.assertEqual([c for c in flat.checks if c.code in ("CLOG", "SUSHI_SINK", "two-nets")],
                         [])
        self.assertEqual(flat._in_hold[("bsc/m0", "sulfur")], ["blue_sulfur"])

    def test_routes_with_a_filtered_loader_per_lane(self):
        _flat, r = routed(BLUE.format(split=" split"))
        self.assertEqual(r.failed, {})
        got = loaders(r)
        self.assertEqual(got["blue_engine_unit"], ["engine-unit"])
        self.assertEqual(got["blue_advanced_circuit"], ["advanced-circuit"])

    def test_clog_names_the_split(self):
        flat = flat_of(BLUE.format(split=""))
        (clog,) = [c for c in flat.checks if c.code == "CLOG"]
        self.assertIn("`net blue split:`", clog.msg)

    def test_one_item_has_nothing_to_split(self):
        flat = flat_of("""
fe   = Chest<requester, item=iron-plate> @(3, 3)
gear = Assembler<recipe=iron-gear-wheel> @(14, 0)
net fe split: fe -> gear
""")
        self.assertIn("split", [c.code for c in flat.checks])
        self.assertIn("fe", flat.nets)

    def test_split_takes_no_width(self):
        with self.assertRaises(ElabError):
            flat_of(BLUE.format(split=" width 2 split"))


class LongHandTest(unittest.TestCase):
    def test_a_filtered_load_tries_fast_inserters_first(self):
        # the chest's west and north sides are free: a fast inserter loads it, never a long one
        _flat, r = routed(BLUE.format(split=""))
        names = {e.name for e in r.layout.entities.values()
                 if e.attrs.get("filter") or e.attrs.get("net") == "blue"
                 and "inserter" in e.name and abs(e.x - 3.5) + abs(e.y - 3.5) <= 2}
        self.assertEqual(names, {"fast-inserter"})

    def test_a_long_handed_loader_says_it_is_unfiltered(self):
        flat = flat_of(BLUE.format(split=""))
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        ins = next(e for e in r.layout.entities.values() if e.attrs.get("filter"))
        ins.name = "inserter"             # a plain inserter, like a long-handed one, takes none
        del ins.attrs["filter"]
        lines = route._filter_loads(flat, r.layout, CAT)
        self.assertTrue(any(ln.startswith("  unfiltered blue:") and "can't filter" in ln
                            for ln in lines), lines)


if __name__ == "__main__":
    unittest.main()
