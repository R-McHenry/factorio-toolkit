"""kickoff/upgrade_run.py: the build script edits an upgrade makes (no run folder, no git)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kickoff"))

import upgrade_run  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "kickoff", "template", "game",
                        "nauvis.build.fkb")
OLD = ("elaborate\nsize\nreport_checks\n"
       "write_layout                              # write the .fkp files (commit them)\n"
       "diff            --scope stale\nreport_bom      --stock live\n"
       "apply           --scope stale\nstop_on         invariant\n")


def steps(text):
    return [line.split("#")[0].split()[0] for line in text.splitlines()
            if line.split("#")[0].split()]


class WriteLastTest(unittest.TestCase):
    """1.7: ``write_layout`` just before ``apply``, so ``fk build --to diff`` writes nothing (the
    players' dry runs had made their design the one the next build kept to)."""

    def test_an_old_script_writes_just_before_the_paste(self):
        new = upgrade_run._write_last(OLD)
        self.assertEqual(steps(new), ["elaborate", "size", "report_checks", "diff", "report_bom",
                                      "write_layout", "apply", "stop_on"])
        self.assertIn("write_layout                              # write the .fkp files", new)
        self.assertIsNone(upgrade_run._write_last(new))

    def test_the_template_is_already_in_that_order(self):
        with open(TEMPLATE, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIsNone(upgrade_run._write_last(text))
        order = steps(text)
        self.assertEqual(order.index("write_layout") + 1, order.index("apply"))

    def test_a_script_without_apply_or_with_it_first_is_left_alone(self):
        self.assertIsNone(upgrade_run._write_last("elaborate\nwrite_layout\ndiff\n"))
        self.assertIsNone(upgrade_run._write_last("diff\napply\nwrite_layout\n"))
        self.assertIsNone(upgrade_run._write_last("write_layout\n\n# a note\napply\n"))


class StopsTest(unittest.TestCase):
    """2.0.12: the template stops on UNROUTED and NO_SINK, so a paste with a net unrouted (the solo
    run's Mall4, 2026-10-23 23:15) doesn't go out; an upgrade adds the stops a script lacks."""

    def test_the_template_stops_on_an_unrouted_net_and_a_maker_without_a_sink(self):
        from fkcore import flow
        with open(TEMPLATE, encoding="utf-8") as fh:
            lines = flow.parse(fh.read(), TEMPLATE)
        codes = {a.upper() for ln in lines if ln.cmd == "stop_on" for a in ln.args}
        self.assertEqual(codes, {"INVARIANT", "UNROUTED", "NO_SINK"})
        with open(TEMPLATE, encoding="utf-8") as fh:
            self.assertIsNone(upgrade_run._stops(fh.read()))

    def test_an_old_script_gets_the_stops_it_lacks(self):
        new = upgrade_run._stops(OLD)
        self.assertEqual(new.splitlines()[-1], "stop_on         UNROUTED NO_SINK          # and no "
                         "paste with a net unrouted, or a maker whose product reaches no sink")
        self.assertIsNone(upgrade_run._stops(new))
        # the solo player's own line (23:15): only NO_SINK comes, after its last stop_on
        solo = OLD.replace("apply ", "stop_on         UNROUTED\napply ")
        new = upgrade_run._stops(solo)
        self.assertEqual(steps(new)[-2:], ["stop_on", "stop_on"])
        self.assertIn("stop_on         NO_SINK ", new)
        self.assertNotIn("UNROUTED NO_SINK", new)
        self.assertIn("stop_on         invariant\nstop_on         NO_SINK", new)


class PolesTest(unittest.TestCase):
    """2.0.14: an upgraded run's coverage step takes the pole the network can build."""

    def test_the_template_names_any_pole(self):
        with open(TEMPLATE, encoding="utf-8") as fh:
            text = fh.read()
        from fkcore import flow
        opts = {ln.cmd: ln.args for ln in flow.parse(text, TEMPLATE)}
        self.assertIn("any", opts["cover_power"])
        # 2.0.51: the template's world is one plot, and the plant's own pole line is in its design,
        # so floorplan has no bridge to lay; `_pole` still upgrades a run that has one
        self.assertEqual(opts["floorplan"], [])

    def test_a_named_pole_becomes_any(self):
        old = ("route           --only stale --effort normal\n"
               "cover power     --pole medium-electric-pole\n"
               "floorplan       --bridge-power\n")
        new = upgrade_run._pole(old)
        self.assertIn("cover power     --pole any\n", new)
        self.assertIn("floorplan       --bridge-power any\n", new)
        self.assertIsNone(upgrade_run._pole(new))
        sized = old.replace("--pole medium-electric-pole", "--pole small-electric-pole")
        self.assertIn("--pole any", upgrade_run._pole(sized))
        self.assertIn("--bridge-power any", upgrade_run._pole(old.replace(
            "--bridge-power", "--bridge-power substation")))
        self.assertTrue(upgrade_run._pole("cover power     --pole any\n"
                                          "floorplan       --bridge-power substation\n")
                        .endswith("--bridge-power any\n"))


class HandsStepTest(unittest.TestCase):
    """2.0.15: an upgraded run gets the hands step, right after its route line."""

    def test_the_template_runs_hands_after_route(self):
        from fkcore import flow
        with open(TEMPLATE, encoding="utf-8") as fh:
            names = [ln.cmd for ln in flow.parse(fh.read(), TEMPLATE)]
        self.assertEqual(names[names.index("route") + 1], "hands")

    def test_an_old_script_gets_the_step(self):
        new = upgrade_run._hands_step(
            "place           --keep pinned\nroute           --only stale --effort normal --hand any\n"
            "tier            minimize\n")
        self.assertIn("route           --only stale --effort normal --hand any\nhands           "
                      "minimize", new)
        self.assertIsNone(upgrade_run._hands_step(new))
        self.assertIsNone(upgrade_run._hands_step("place\nelaborate\n"))


if __name__ == "__main__":
    unittest.main()
