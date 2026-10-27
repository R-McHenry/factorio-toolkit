"""The router's guard against what the game would pair or feed wrong (route.py: the underground
guard, a merge's spare output, a tapped belt's last tile, other inserters' hands, a tapped belt
that would start a tunnel), on adversarial layouts. Each is judged by fkcore.connect, whose
underground pairing is the game's (the first end of the same name facing the same way, within
reach), and by an oracle that pairs ends by geometry alone, so a Literal's ends of unknown type
(an entity-list import carries no ug=) count too. Done: 0 SPILL and connected, or refused with a
reason.

Most cases: a drill row whose belt starts at 3,3 heading east, a chest at 20,3, and a Literal
``wall`` (pinned entities, written here with any attrs) or a pinned route in the way.
"""
import math
import unittest

from fkcore import connect, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()
_DX, _DY = (0, 1, 0, -1), (-1, 0, 1, 0)

ONE = """
mine = MinerRow<n=1, resource=iron-ore> @(0, 0)
dst  = Chest<provider>                  @(20, 3)
wall = Literal                          @(0, 0)
net p: mine -> dst
"""
BOX = (0, 0, 22, 7)


def build(text, pinned):
    prev = fkp.loads("fkp 1 factory t\n" + "\n".join(l.strip() for l in pinned.splitlines()))
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t", layout=prev)
    lay, notes = expand.expand_factory(flat, CAT, prev)
    for e in prev.entities.values():
        if e.owner.startswith("~"):                         # a pinned route
            lay.add(fkp.Entity(e.key, e.name, e.x, e.y, e.dir, dict(e.attrs)))
    return flat, lay


def wall(*rows):
    """A Literal 'wall' from (name, x, y, dir, attrs) rows, tile coordinates."""
    out = ["inst wall Literal at 0,0 rot 0 sig x"]
    for i, (name, x, y, d, attrs) in enumerate(rows):
        out.append(f"e wall/e{i} {name} {x + 0.5},{y + 0.5} {d} net=wall {attrs}".rstrip())
    return "\n".join(out)


def column(x, y0, y1, d="N"):
    return [("transport-belt", x, y, d, "") for y in range(y0, y1)]


def ends(lay):
    """[(key, tile, heading, name)] of every underground end."""
    out = []
    for k, e in lay.entities.items():
        if CAT.kind(e.name) == "underground-belt":
            out.append((k, (math.floor(e.x), math.floor(e.y)), (e.dir or 0) // 4, e.name))
    return out


def tunnels(lay, mine):
    """{key: span tiles} of the tunnels whose entrance key passes ``mine``, paired by geometry:
    from each end, the nearest end ahead of the same name facing the same way within reach."""
    out = {}
    all_ends = ends(lay)
    at = {t: (k, h, n) for k, t, h, n in all_ends}
    for k, t, h, n in all_ends:
        if not mine(k) or lay.entities[k].attrs.get("ug") == "out":
            continue
        reach = int(CAT.entity(n).get("max_distance") or 5)
        for j in range(1, reach + 1):
            u = (t[0] + _DX[h] * j, t[1] + _DY[h] * j)
            if u in at and at[u][1] == h and at[u][2] == n:
                out[k] = {(t[0] + _DX[h] * i, t[1] + _DY[h] * i) for i in range(j + 1)}
                break
    return out


class GuardCase(unittest.TestCase):
    def route(self, text, pinned, box=BOX):
        flat, lay = build(text, pinned)
        r = route.route_layout(flat, lay, CAT, bounds=box)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        return flat, r, rep

    def assert_sound(self, r, rep, nets=("p",)):
        """Routed, connected, no SPILL; no route tunnel hides another end on its axis, and no
        route end stands in another tunnel on its axis."""
        self.assertEqual(r.failed, {}, r.lines)
        self.assertEqual(rep.leaks, [], rep.lines())
        for n in nets:
            self.assertEqual(rep.nets[n].status, "connected", rep.lines())
            self.assertEqual(rep.nets[n].unpaired, [])
        lay = r.layout
        is_route = lambda k: k.startswith("~") and k.split("/")[0][1:] in r.routed
        mine, theirs = tunnels(lay, is_route), tunnels(lay, lambda k: not is_route(k))
        for k, t, h, _n in ends(lay):
            for key, span in mine.items():
                ax = (lay.entities[key].dir or 0) // 4 % 2
                if not is_route(k) and h % 2 == ax:
                    self.assertNotIn(t, span, f"{key}'s tunnel hides {k}")
            for key, span in theirs.items():
                ax = (lay.entities[key].dir or 0) // 4 % 2
                if is_route(k) and h % 2 == ax:
                    self.assertNotIn(t, span, f"{k} stands in {key}'s tunnel")


class UndergroundGuardTest(GuardCase):
    def test_a_lone_exit_past_a_wall(self):
        # one long tunnel over the wall and the exit is the cheap move: the game would pair
        # ours with the Literal's exit (a LEAK). The old router did exactly that.
        _f, r, rep = self.route(ONE, wall(*column(10, 0, 7),
                                          ("underground-belt", 12, 3, "E", "ug=out")))
        self.assert_sound(r, rep)

    def test_a_lone_entrance_past_a_wall(self):
        # ours would meet the Literal's entrance first and pair with nothing (the old router)
        _f, r, rep = self.route(ONE, wall(*column(10, 0, 7),
                                          ("underground-belt", 12, 3, "E", "ug=in")))
        self.assert_sound(r, rep)

    def test_an_end_of_unknown_type(self):
        # a Literal from an entity list has no ug=: either way the game pairs it wrong
        _f, r, rep = self.route(ONE, wall(*column(10, 0, 7),
                                          ("underground-belt", 12, 3, "E", "")))
        self.assert_sound(r, rep)

    def test_another_tier(self):
        # the game passes another tier (connect too); the guard steers clear of it anyway
        _f, r, rep = self.route(ONE, wall(*column(10, 0, 7),
                                          ("fast-underground-belt", 12, 3, "E", "ug=out")))
        self.assert_sound(r, rep)

    def test_the_only_crossing_inside_a_tunnel_of_unknown_type_is_refused(self):
        # the wall is 5 thick except on row 3, where a Literal tunnel (types unknown) runs: any
        # crossing nests in it. The old router nested two tunnels there (all four ends unpaired).
        thick = [row for x in range(10, 15) for row in column(x, 0, 3) + column(x, 4, 7, "S")]
        _f, r, rep = self.route(ONE, wall(*thick, ("transport-belt", 12, 3, "N", ""),
                                          ("transport-belt", 7, 3, "E", ""),
                                          ("underground-belt", 8, 3, "E", ""),
                                          ("underground-belt", 13, 3, "E", "")))
        self.assertEqual(r.routed, [])
        self.assertIn("the only ways in tunnel past another underground on the same axis",
                      r.failed["p"])
        self.assertEqual([k for k in r.layout.entities if k.startswith("~p/")], [])
        self.assertEqual(rep.leaks, [])

    def test_a_pinned_route_tunnel(self):
        # q is pinned with a tunnel under the wall right above p's straight line
        pinned = wall(*column(10, 0, 7)) + "\n" + "\n".join([
            "e ~q/i0 fast-inserter 6.5,0.5 W net=q", "e ~q/b0 transport-belt 7.5,0.5 S net=q",
            "e ~q/b1 transport-belt 7.5,1.5 S net=q", "e ~q/b2 transport-belt 7.5,2.5 E net=q",
            "e ~q/u0 underground-belt 8.5,2.5 E net=q ug=in",
            "e ~q/u1 underground-belt 13.5,2.5 E net=q ug=out",
            "e ~q/b3 transport-belt 14.5,2.5 N net=q", "e ~q/b4 transport-belt 14.5,1.5 N net=q",
            "e ~q/b5 transport-belt 14.5,0.5 E net=q", "e ~q/b6 transport-belt 15.5,0.5 E net=q",
            "e ~q/b7 transport-belt 16.5,0.5 E net=q", "e ~q/i1 fast-inserter 17.5,0.5 W net=q"])
        _f, r, rep = self.route(ONE + """
            q0 = Chest<requester, item=copper-plate> @(5, 0)
            q1 = Chest<provider>                     @(18, 0)
            net q: q0 -> q1
        """, pinned)
        self.assertEqual(r.kept, ["q"])
        self.assert_sound(r, rep, nets=("p", "q"))

    def test_nested_in_a_pinned_tunnel(self):
        # q's pinned tunnel runs under a free corridor; p comes down the corridor and the cheap
        # way east starts its own tunnel inside q's
        pinned = wall(("iron-chest", 11, 2, "", ""), ("iron-chest", 11, 4, "", "")) + "\n" + \
            "\n".join(["e ~q/i0 fast-inserter 3.5,3.5 W net=q",
                       "e ~q/b0 transport-belt 4.5,3.5 E net=q",
                       "e ~q/u0 underground-belt 5.5,3.5 E net=q ug=in",     # hides 6..9
                       "e ~q/u1 underground-belt 10.5,3.5 E net=q ug=out",
                       "e ~q/b1 transport-belt 11.5,3.5 E net=q",
                       "e ~q/b2 transport-belt 12.5,3.5 S net=q",
                       "e ~q/b3 transport-belt 12.5,4.5 S net=q",
                       "e ~q/i1 fast-inserter 12.5,5.5 N net=q"])
        _f, r, rep = self.route("""
            src  = Chest<requester, item=iron-plate>   @(8, 0)
            dst  = Chest<provider>                     @(20, 3)
            q0   = Chest<requester, item=copper-plate> @(2, 3)
            q1   = Chest<provider>                     @(12, 6)
            wall = Literal @(0, 0)
            net p: src -> dst
            net q: q0 -> q1
        """, pinned, box=(0, 0, 22, 8))
        self.assertEqual(r.kept, ["q"])
        self.assert_sound(r, rep, nets=("p", "q"))

    def test_parallel_tunnels_through_one_wall(self):
        # two drill rows, one wall: each tunnels; the old router's second tapped belt ended
        # pointing into the first net's belt (a side-load, a LEAK)
        _f, r, rep = self.route("""
            mine = MinerRow<n=1, resource=iron-ore>   @(0, 0)
            cu   = MinerRow<n=1, resource=copper-ore> @(0, 4)
            dst  = Chest<provider>                    @(20, 3)
            dst2 = Chest<provider>                    @(20, 4)
            wall = Literal                            @(0, 0)
            net p: mine -> dst
            net q: cu -> dst2
        """, wall(*column(10, 0, 9)), box=(0, 0, 22, 9))
        self.assert_sound(r, rep, nets=("p", "q"))


class FeedGuardTest(GuardCase):
    def test_a_merge_spare_output_beside_a_foreign_belt(self):
        # two drill rows into one smelter row: the merge's free output would feed the Literal's
        # belt at 5,7 (the old router: ~ore/s0 feeds wall/e1)
        _f, r, rep = self.route("""
            m1    = MinerRow<n=1, resource=iron-ore>    @(0, 0)
            m2    = MinerRow<n=1, resource=iron-ore>    @(0, 8)
            smelt = SmelterRow<n=1, recipe=iron-plate>  @(14, 6)
            wall  = Literal @(0, 0)
            net ore: m1, m2 -> smelt
        """, wall(("iron-chest", 21, 13, "", ""), ("transport-belt", 5, 7, "S", "")),
            box=(0, 0, 22, 14))
        self.assert_sound(r, rep, nets=("ore",))
        self.assertIn("1 merges", r.lines[0])

    def test_a_tapped_belt_end_before_a_foreign_belt(self):
        _f, r, rep = self.route(ONE.replace("@(20, 3)", "@(8, 5)"),
                                wall(("transport-belt", 9, 3, "N", ""),
                                     ("transport-belt", 9, 2, "N", "")))
        self.assert_sound(r, rep)

    def test_another_inserter_picks_from_the_straight_line(self):
        # the Literal's inserter at 7,4 picks from 7,3: a belt there would be robbed (a LEAK)
        _f, r, rep = self.route(ONE, wall(("fast-inserter", 7, 4, "N", ""),
                                          ("iron-chest", 7, 5, "", "")))
        self.assert_sound(r, rep)
        self.assertNotIn((7, 3), {t for k, e in r.layout.entities.items() if k.startswith("~p/")
                                  and e.name == "transport-belt" for t in fkp.tiles_of(CAT, e)})

    def test_a_tapped_belt_never_starts_a_tunnel_when_laid_reversed(self):
        # two chests into one row: the second is reached past the first's tap, over a wall; the
        # old router started the tunnel on the tapped belt, which reversed is an exit and takes
        # no drop (chest a cut off)
        _f, r, rep = self.route("""
            a    = Chest<requester, item=iron-plate> @(7, 3)
            b    = Chest<requester, item=iron-plate> @(1, 3)
            gear = AsmRow<n=1, recipe=iron-gear-wheel> @(12, 5)
            wall = Literal @(0, 0)
            net plate: a, b -> gear
        """, wall(*[("iron-chest", x, y, "", "") for x in (4, 5, 6) for y in (4, 5, 6)]),
            box=(0, 0, 18, 9))
        self.assert_sound(r, rep, nets=("plate",))

    def test_a_root_that_turns_is_never_split(self):
        # three cells into a row just below them: the old tree split at its turning root and
        # laid the merge beside the turn, fed from its side (unrouted)
        flat, r, rep = self.route("""
            g1  = Assembler<recipe=iron-gear-wheel> @(2, 2)
            g2  = Assembler<recipe=iron-gear-wheel> @(10, 2)
            g3  = Assembler<recipe=iron-gear-wheel> @(18, 2)
            red = AsmRow<n=1, recipe=automation-science-pack> @(10, 8)
            wall = Literal @(0, 0)
            net gear: g1, g2, g3 -> red
        """, wall(("iron-chest", 24, 24, "", "")), box=(0, 0, 25, 25))
        self.assert_sound(r, rep, nets=("gear",))


class SpansTest(unittest.TestCase):
    def test_every_end_and_every_tunnel(self):
        lay = fkp.loads("fkp 1 factory t\n" + "\n".join([
            "e a/u0 underground-belt 0.5,0.5 E net=a ug=in",       # a tunnel 0..4 on axis 1
            "e a/u1 underground-belt 4.5,0.5 E net=a ug=out",
            "e b/u0 underground-belt 8.5,0.5 E net=b ug=out",      # a lone exit
            "e c/u0 underground-belt 0.5,3.5 S net=c",             # unknown types, axis 0
            "e c/u1 underground-belt 0.5,6.5 S net=c",
            "e d/u0 underground-belt 3.5,3.5 E net=d ug=in",       # out of reach: alone
            "e d/u1 underground-belt 9.5,3.5 E net=d ug=out",
            "e f/u0 fast-underground-belt 3.5,5.5 W net=f ug=in",  # another tier, reach 7
            "e f/u1 fast-underground-belt 0.5,5.5 W net=f ug=out"]))
        spans = route._ug_spans(CAT, list(lay.entities.values()))
        self.assertEqual(spans[1], {(x, 0) for x in range(5)} | {(8, 0), (3, 3), (9, 3)}
                         | {(x, 5) for x in range(4)})
        self.assertEqual(spans[0], {(0, y) for y in range(3, 7)})


if __name__ == "__main__":
    unittest.main()
