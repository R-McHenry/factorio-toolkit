"""fkcore.apply against a fake game link (no game): scope, anchor, lab correction, play reports."""
import unittest
from unittest import mock

from fkcore import apply as applymod, codec, compose, fkp, link
from fkcore.catalog import Catalog
from tests.test_sense import surface

CAT = Catalog.load()


class FakeRcon:
    """Answers each Lua builder the way the game does; ``ghosts`` is what a snapshot finds."""

    def __init__(self, ghosts):
        self.calls, self.ghosts, self.pastes = [], ghosts, []

    def lua(self, body):
        self.calls.append(body)
        if "build_blueprint" in body:
            at = body.split("position = {", 1)[1].split("}", 1)[0]
            self.pastes.append(tuple(float(v) for v in at.split(",")))
            return str(len(self.ghosts))
        if "g.revive()" in body:
            return f"{len(self.ghosts)} 0"
        if "request_to_generate_chunks" in body:
            return "16"
        if "amount =" in body:
            return "0"
        return "0"


def fake_snapshot(things):
    def snap(r, surface_name, area, tag="snap"):
        return {"tick": 1, "area": list(area),
                "things": [{"n": n, "x": x, "y": y, "g": True} for n, x, y in things]}
    return snap


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.s = surface()
        self.rows = applymod.scope_rows(self.s, keys=["nauvis:mini/"])
        self.want = [(r["name"], float(r["x"]), float(r["y"])) for r in self.rows]

    def run_apply(self, things, mode):
        r = FakeRcon(things)
        with mock.patch.object(link, "snapshot", fake_snapshot(things)):
            rep = applymod.apply(r, self.s, CAT, keys=["nauvis:mini/"], mode=mode)
        return r, rep

    def test_scope_by_plot_keys(self):
        self.assertEqual(len(self.rows), 19)                # the mini factory, not the roboport
        self.assertTrue(all(r["src"].startswith("nauvis:mini/") for r in self.rows))

    def test_lab_paste_where_designed(self):
        r, rep = self.run_apply(self.want, "lab")
        self.assertEqual((rep.design, rep.present, rep.corrected, rep.misplaced), (19, 19, None, 0))
        self.assertEqual(rep.revived, 19)
        self.assertEqual(rep.force, "lab")
        self.assertEqual(len(r.pastes), 1)
        self.assertFalse(any("register" in c or "on_event" in c for c in r.calls))

    def test_lab_shifted_paste_is_measured_and_pasted_again(self):
        shifted = [(n, x + 1, y) for n, x, y in self.want]
        r, rep = self.run_apply(shifted, "lab")
        self.assertEqual(rep.corrected, (1.0, 0.0))
        self.assertEqual(len(r.pastes), 2)
        self.assertEqual(r.pastes[1][0], r.pastes[0][0] - 1)

    def test_play_reports_a_shifted_paste_and_cleans_nothing(self):
        # shifted clear of the design (a 1-tile shift of a belt row lands on its own belts)
        shifted = [(n, x, y + 10) for n, x, y in self.want]
        r, rep = self.run_apply(shifted, "play")
        self.assertEqual((rep.force, rep.misplaced, rep.revived), ("player", 19, 0))
        # (the paste's own script inventory is destroyed; no entity is)
        self.assertFalse(any("e.destroy()" in c or "g.revive()" in c for c in r.calls))
        self.assertIn("not-where-designed 19", "\n".join(rep.lines()))

    def test_lab_seeds_ore_only_without_a_terrain(self):
        # a real terrain (transplanted ore) is under the drills already: nothing is seeded
        lay = fkp.loads("fkp 1 factory d\nsize 3x3\ninst m MinerRow n=1 resource=iron-ore at 0,0 "
                        "rot 0 sig x\ne m/m0 electric-mining-drill 1.5,1.5 S resource=iron-ore\n")
        s = compose.compose(fkp.loads("fkp 1 surface lab\nplot d at 0,0 rot 0 size 3x3\n"),
                            {"d": lay}, CAT)
        want = [("electric-mining-drill", 1.5, 1.5)]
        for seed, seeds in ((True, 1), (False, 0)):
            r = FakeRcon(want)
            with mock.patch.object(link, "snapshot", fake_snapshot(want)):
                rep = applymod.apply(r, s, CAT, mode="lab", seed=seed)
            self.assertEqual(sum("amount =" in c for c in r.calls), seeds)
            gen = next(c for c in r.calls if "request_to_generate_chunks" in c)
            self.assertIn("request_to_generate_chunks({cx * 32 + 16, cy * 32 + 16}, 0)", gen)
        self.assertIn("no ore seeded: the drills stand on the terrain's ore", rep.notes)

    def test_anchor_is_the_tile_box_centre(self):
        x0, y0, x1, y1 = applymod.scope_area(self.rows, CAT, margin=0)
        r, _rep = self.run_apply(self.want, "lab")
        self.assertEqual(r.pastes[0], ((x0 + x1) / 2, (y0 + y1) / 2))

    def test_a_built_entity_ordered_out_still_needs_its_ghost(self):
        # 2026-10-22: an inserter ordered up for a new condition went, so nothing took its place
        cap = {"things": [
            {"n": "assembling-machine-1", "x": 1.5, "y": 1.5, "g": False, "dc": False},
            {"n": "inserter", "x": 2.5, "y": 1.5, "g": False, "dc": True},
            {"n": "transport-belt", "x": 3.5, "y": 1.5, "g": True, "dc": True},
            {"n": "small-electric-pole", "x": 4.5, "y": 1.5, "g": False}]}
        self.assertEqual(applymod._placed(cap),
                         {("assembling-machine-1", 1.5, 1.5),
                          ("transport-belt", 3.5, 1.5),
                          ("small-electric-pole", 4.5, 1.5)})

    def test_single_ghosts_are_the_refused_rows_and_wires_that_touch_them(self):
        rows = [
            {"src": "d/a", "name": "small-electric-pole", "x": 0.5, "y": 0.5,
             "direction": None, "attrs": {}},
            {"src": "d/m", "name": "assembling-machine-1", "x": 2.5, "y": 0.5,
             "direction": None, "attrs": {"recipe": "iron-gear-wheel"}},
            {"src": "d/b", "name": "small-electric-pole", "x": 5.5, "y": 0.5,
             "direction": None, "attrs": {}},
            {"src": "d/c", "name": "small-electric-pole", "x": 20.5, "y": 0.5,
             "direction": None, "attrs": {"wire": "1,d,1"}},
            {"src": "d/d", "name": "small-electric-pole", "x": 24.5, "y": 0.5,
             "direction": None, "attrs": {}}]
        entities, wires = applymod.single_ghosts(rows, self.s, CAT, [1, 2])
        # numbered anew, in refused order: what link.ghosts places, settings and all
        self.assertEqual(entities, [codec.entity_json(rows[1], 1),
                                    codec.entity_json(rows[2], 2)])
        self.assertEqual(entities[0]["recipe"], "iron-gear-wheel")
        # the a-b pole wire has an end among them; the c-d pole wire and the c-d circuit wire do not
        self.assertEqual(wires, [[["small-electric-pole", 0.5, 0.5], codec.POLE_COPPER,
                                  ["small-electric-pole", 5.5, 0.5], codec.POLE_COPPER]])

    def test_alone_missed_is_named_in_the_report(self):
        rep = applymod.ApplyReport("nauvis", "player", "play", (0, 0, 1, 1))
        rep.placed_alone = 2
        rep.alone_missed = {"request_filters.trash_not_requested": 1,
                            "control_behavior.sections": 2}
        lines = rep.lines()
        self.assertIn("2 the paste refused, placed one by one as ghosts",
                      "\n".join(lines))
        self.assertIn("control_behavior.sections x2, "
                      "request_filters.trash_not_requested x1", "\n".join(lines))

    def test_apply_places_a_refused_row_alone_with_its_settings(self):
        things = [{"n": n, "x": x, "y": y, "g": True} for n, x, y in self.want]
        things[0].update(g=False, dc=True)          # built, then ordered out for new settings

        def snap(r, surface_name, area, tag="snap"):
            return {"tick": 1, "area": list(area), "things": things}

        r = FakeRcon(things)
        with mock.patch.object(link, "snapshot", snap), \
                mock.patch.object(link, "ghosts",
                                  return_value={"n": 1, "missed": {"filters": 1}}) as ghosts:
            rep = applymod.apply(r, self.s, CAT, keys=["nauvis:mini/"], mode="play")
        entities, wires = ghosts.call_args.args[3], ghosts.call_args.args[4]
        self.assertEqual(entities, [codec.entity_json(self.rows[0], 1)])
        self.assertEqual(wires, [])
        self.assertEqual((rep.placed_alone, rep.alone_missed), (1, {"filters": 1}))
        self.assertIn("SETTINGS the single ghosts would not take", "\n".join(rep.lines()))
        self.assertIn("filters x1", "\n".join(rep.lines()))


if __name__ == "__main__":
    unittest.main()
