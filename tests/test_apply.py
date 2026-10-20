"""fkcore.apply against a fake game link (no game): scope, anchor, lab correction, play reports."""
import unittest
from unittest import mock

from fkcore import apply as applymod, compose, fkp, link
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
        self.assertIn("MISPLACED 19", "\n".join(rep.lines()))

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


if __name__ == "__main__":
    unittest.main()
