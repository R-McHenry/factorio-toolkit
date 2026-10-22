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


if __name__ == "__main__":
    unittest.main()
