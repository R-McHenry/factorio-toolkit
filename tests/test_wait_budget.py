"""2.0.12 (Rory, 2026-10-24): `fk wait` is the only allowed wait, with a fixed budget of wait time
and an "are you sure you want to wait" message (agent/fk.py). Offline: the clock and the sleep are
injected, and `fk wait built`'s host call is mocked."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "agent"))
import fk  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkwait-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        p = mock.patch.object(fk, "WAIT_FILE", os.path.join(self.dir, "wait-budget.json"))
        p.start()
        self.addCleanup(p.stop)
        self.clock = Clock()

    def wait(self, *args, **kw):
        with mock.patch("sys.stdout") as out:
            code = fk.wait({"host": "local"}, list(args), clock=self.clock, sleep=self.clock.sleep,
                           **kw)
        return code, "".join(c.args[0] for c in out.write.call_args_list)

    def budget(self):
        with open(fk.WAIT_FILE, encoding="utf-8") as fh:
            return json.load(fh)

    def test_it_asks_first_then_waits_when_asked_again(self):
        code, said = self.wait("90s")
        self.assertEqual(code, 1)
        self.assertIn("Are you sure you want to wait? 30 min of wait budget left. Run it again "
                      "(or add --sure) to wait.", said)
        self.assertEqual(self.clock.t, 1000.0)                    # nothing waited
        code, said = self.wait("90s")
        self.assertEqual(code, 0)
        self.assertEqual(self.clock.t, 1090.0)
        self.assertIn("fk wait: waited 90 s; 28 min of wait budget left", said)
        self.assertEqual(self.budget()["spent_s"], 90.0)

    def test_sure_waits_at_once_and_a_late_repeat_asks_again(self):
        self.assertEqual(self.wait("1m", "--sure")[0], 0)
        self.assertEqual(self.wait("2m")[0], 1)
        self.clock.t += 300                                        # too long after: asks again
        self.assertEqual(self.wait("2m")[0], 1)
        self.assertEqual(self.budget()["spent_s"], 60.0)

    def test_it_waits_at_most_what_is_left_then_refuses(self):
        self.assertEqual(self.wait("1h", "--sure")[0], 0)
        self.assertEqual(self.clock.t, 1000.0 + 1800)             # the 30 min, not the hour
        code, said = self.wait("10s", "--sure")
        self.assertEqual(code, 2)
        self.assertIn("the run's 30 min of wait budget is spent", said)

    def test_the_budget_is_one_number_in_one_place(self):
        with open(fk.WAIT_FILE, "w", encoding="utf-8") as fh:
            json.dump({"budget_min": 5}, fh)
        self.assertIn("5 min of wait budget left", self.wait("10s")[1])
        self.assertEqual(fk.WAIT_BUDGET_MIN, 30)

    def test_a_wait_that_was_cut_off_still_counts(self):
        with open(fk.WAIT_FILE, "w", encoding="utf-8") as fh:
            json.dump({"spent_s": 0, "running": {"since": self.clock.t - 120, "for": 300}}, fh)
        self.assertIn("28 min of wait budget left", self.wait("10s")[1])

    def test_wait_built_waits_on_the_host_at_most_what_is_left(self):
        with open(fk.WAIT_FILE, "w", encoding="utf-8") as fh:
            json.dump({"spent_s": 1700}, fh)                       # 100 s left
        seen = []

        def remote(cfg, args, **kw):
            seen.append(args)
            self.clock.t += 40
            return 0
        with mock.patch.object(fk, "remote", remote), mock.patch.object(fk, "push"), \
                mock.patch.object(fk, "pull"):
            code, said = self.wait("built", "1,2,30,40", "--max", "5m", "--sure")
        self.assertEqual(code, 0)
        self.assertEqual(seen, [["wait", ".", "built", "--area", "1,2,30,40", "--max", "100s"]])
        self.assertIn("waited 40 s; 1 min of wait budget left", said)

    def test_a_command_with_a_cap_is_a_wait(self):
        # 3.0: `fk wait 2m -- COMMAND` in place of `timeout 120 COMMAND`
        code, _said = self.wait("2m", "--", sys.executable, "-c", "raise SystemExit(3)", "--sure")
        self.assertEqual(code, 3)
        code, said = self.wait("1s", "--", sys.executable, "-c", "import time; time.sleep(5)",
                               "--sure")
        self.assertEqual(code, 124)
        self.assertIn("still ran after 1 s; stopped", said)

    def test_wait_build_reads_the_newest_build_in_the_log(self):
        log = os.path.join(self.dir, "build.log")
        with open(log, "w", encoding="utf-8") as fh:
            fh.write("\n== fk build (10:00)\nfk build: done, exit 0\n== fk build (10:05)\nroute\n")
        with mock.patch("sys.stdout"):
            self.assertEqual(fk._wait_build(10, self.clock, self.clock.sleep, log), 1)
        self.assertGreaterEqual(self.clock.t, 1010.0)               # it waited out the cap
        with open(log, "a", encoding="utf-8") as fh:
            fh.write("fk build: done, exit 1\n")
        with mock.patch("sys.stdout"):
            self.assertEqual(fk._wait_build(10, self.clock, self.clock.sleep, log), 1)
            self.assertEqual(fk._wait_build(10, self.clock, self.clock.sleep,
                                            os.path.join(self.dir, "none.log")), 2)

    def test_anything_else_is_no_wait(self):
        self.assertEqual(self.wait("forever")[0], 2)
        self.assertEqual(self.wait()[0], 2)


if __name__ == "__main__":
    unittest.main()
