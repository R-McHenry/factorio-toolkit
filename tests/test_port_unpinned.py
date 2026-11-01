"""2.1.19 (the live run's LabArea, ~4480k): a sealed module with several unpinned ports on one
side (`@e`, no position) was left unplaced ("ports b_in and g_in share the tile"), and every port
net said "no driver role is placed". Each now takes a free tile until the build chooses it facing
its partner."""
import os
import shutil
import tempfile
import unittest

from fkcore import flow, lab

GAME = {
    "two.fk": """
module Two size 12x12 {
  port a_in : in iron-plate @w
  port b_in : in copper-plate @w
  port c_in : in iron-plate @w
  g = Assembler<recipe=iron-gear-wheel> @(5, 1)
  k = Assembler<recipe=copper-cable> @(5, 5)
  h = Assembler<recipe=iron-gear-wheel> @(5, 9)
  net a: a_in -> g
  net b: b_in -> k
  net c: c_in -> h
}
""",
    "twolab.fk": """
import Two from "two.fk"
t = Two @(10, 0)
ra = Chest<requester, item=iron-plate, request=50, rate=1/s>   @(2, 1)
rb = Chest<requester, item=copper-plate, request=50, rate=1/s> @(2, 5)
rc = Chest<requester, item=iron-plate, request=50, rate=1/s>   @(2, 9)
net fa: ra -> t.a_in
net fb: rb -> t.b_in
net fc: rc -> t.c_in
""",
}


class UnpinnedPortsTest(unittest.TestCase):
    def test_three_unpinned_ports_on_one_side_are_placed_and_routed(self):
        run = tempfile.mkdtemp(prefix="fkunpinned-")
        self.addCleanup(shutil.rmtree, run, True)
        game = os.path.join(run, "game")
        os.makedirs(game)
        for name, text in GAME.items():
            with open(os.path.join(game, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        ws, _plot = lab.prepare(game, "twolab")
        script = os.path.join(ws, "lab.build.fkb")
        with open(script, encoding="utf-8") as fh:
            text = fh.read()
        with open(script, "w", encoding="utf-8") as fh:      # offline: no apply, no diff
            fh.write("\n".join(ln for ln in text.splitlines()
                               if not ln.startswith(("apply", "diff"))) + "\n")
        code, ctx = flow.run(script, echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        bad = [str(c) for _s, c in ctx.checks if c.code in ("no-route", "no-position")]
        self.assertEqual(bad, [])
        ports = ctx.layouts["twolab"].ports
        ys = {k: p.y for k, p in ports.items() if k.startswith("t.")}
        self.assertEqual(len(set(ys.values())), 3, ys)        # three tiles, not one
        self.assertLess(ys["t.a_in"], ys["t.b_in"])            # each facing its chest
        self.assertLess(ys["t.b_in"], ys["t.c_in"])


if __name__ == "__main__":
    unittest.main()
