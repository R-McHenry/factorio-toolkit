"""fkcore.wait and the ``fk wait built`` command against a fake link and an injected clock: no
game, no real sleep (2.0.4 A11)."""
import contextlib
import importlib.util
import io
import os
import unittest
from unittest import mock

from fkcore import __main__ as mainmod
from fkcore import link, wait

GAME = os.path.join(os.path.dirname(__file__), "..", "games", "lab-sense")
AREA = (305, 415, 353, 449)
DESIGN_AREA = (308, 419, 346, 443)          # the look's default area for this game
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location("fk_agent_wait",
                                               os.path.join(ROOT, "agent", "fk.py"))
fk_agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fk_agent)


def row(name, x, y, ghost=True):
    return {"n": name, "t": "transport-belt", "x": x, "y": y, "d": 4, "g": ghost,
            "force": "lab", "box": [x - 0.4, y - 0.4, x + 0.4, y + 0.4]}


def capture(*rows):
    return {"tick": 1, "area": list(AREA), "things": list(rows)}


class Clock:
    """A monotonic clock that moves only when the wait sleeps."""

    def __init__(self):
        self.t = 0.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


class FakeRcon:
    def __init__(self):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def close(self):
        self.closed = True


class WaitTest(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(wait.parse_duration("90s"), 90.0)
        self.assertEqual(wait.parse_duration("5m"), 300.0)
        self.assertEqual(wait.parse_duration("30min"), 1800.0)
        self.assertEqual(wait.parse_duration("1h"), 3600.0)
        self.assertEqual(wait.parse_duration("1.5h"), 5400.0)
        for bad in ("", "soon", "5", "-5m"):
            with self.assertRaises(ValueError, msg=bad):
                wait.parse_duration(bad)

    def test_ghost_counts_by_name_and_the_name_filter(self):
        dump = capture(row("transport-belt", 1, 1), row("transport-belt", 2, 1),
                       row("iron-chest", 3, 1), row("transport-belt", 4, 1, ghost=False))
        self.assertEqual(wait.ghost_counts(dump),
                         {"transport-belt": 2, "iron-chest": 1})
        self.assertEqual(wait.ghost_counts(dump, ["iron-chest"]), {"iron-chest": 1})
        self.assertEqual(wait.ghost_counts(dump, ["assembling-machine-1"]), {})

    def test_the_clear_line_and_the_left_line(self):
        self.assertEqual(wait.clear_line(AREA), "built: no ghosts left in 305,415,353,449")
        self.assertEqual(wait.clear_line(AREA, ["iron-chest"]),
                         "built: no ghosts of iron-chest left in 305,415,353,449")
        self.assertEqual(wait.left_line(AREA, {"iron-chest": 1, "transport-belt": 2}),
                         "wait built: 3 ghosts left in 305,415,353,449 "
                         "(iron-chest 1, transport-belt 2)")
        self.assertEqual(wait.left_line(AREA, {"iron-chest": 1}, ["iron-chest"]),
                         "wait built: 1 ghost of iron-chest left in 305,415,353,449 "
                         "(iron-chest 1)")

    def test_clear_at_once_prints_the_clear_line_and_does_not_sleep(self):
        clock = Clock()
        calls = []

        def snap(_r, surface, area, tag="snap", keep=True):
            calls.append((surface, tuple(area), tag, keep))
            return capture()
        with mock.patch.object(link, "snapshot", snap):
            code, lines = wait.run(object(), "lab", AREA, clock=clock.now, sleep=clock.sleep)
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["built: no ghosts left in 305,415,353,449"])
        self.assertEqual(calls, [("lab", AREA, "wait", False)])
        self.assertEqual(clock.slept, [])

    def test_polls_until_the_ghosts_are_gone(self):
        clock = Clock()
        frames = iter([capture(row("iron-chest", 1, 1)),
                       capture(row("iron-chest", 1, 1), row("transport-belt", 2, 2)),
                       capture()])

        def snap(*_a, **_k):
            return next(frames)
        with mock.patch.object(link, "snapshot", snap):
            code, lines = wait.run(object(), "lab", AREA, clock=clock.now, sleep=clock.sleep,
                                   poll_s=10)
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["built: no ghosts left in 305,415,353,449"])
        self.assertEqual(clock.slept, [10, 10])
        self.assertEqual(clock.t, 20)

    def test_the_bound_expires_with_ghosts_left_by_name(self):
        clock = Clock()

        def snap(*_a, **_k):
            return capture(row("iron-chest", 1, 1), row("transport-belt", 2, 2),
                           row("transport-belt", 3, 2))
        with mock.patch.object(link, "snapshot", snap):
            code, lines = wait.run(object(), "lab", AREA, max_s=12, poll_s=5,
                                   clock=clock.now, sleep=clock.sleep)
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["wait built: 3 ghosts left in 305,415,353,449 "
                                 "(iron-chest 1, transport-belt 2)"])
        self.assertEqual(clock.slept, [5, 5, 2])     # the last sleep stops at the bound

    def test_a_named_entity_is_done_even_when_other_ghosts_remain(self):
        clock = Clock()

        def snap(*_a, **_k):
            return capture(row("transport-belt", 2, 2))
        with mock.patch.object(link, "snapshot", snap):
            code, lines = wait.run(object(), "lab", AREA, ["iron-chest"],
                                   clock=clock.now, sleep=clock.sleep)
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["built: no ghosts of iron-chest left in 305,415,353,449"])
        self.assertEqual(clock.slept, [])

    def test_a_named_ghost_keeps_the_wait_going(self):
        clock = Clock()
        frames = iter([capture(row("iron-chest", 1, 1)),
                       capture(row("iron-chest", 1, 1), row("transport-belt", 2, 2)),
                       capture(row("transport-belt", 2, 2))])

        def snap(*_a, **_k):
            return next(frames)
        with mock.patch.object(link, "snapshot", snap):
            code, lines = wait.run(object(), "lab", AREA, ["iron-chest"], poll_s=5,
                                   clock=clock.now, sleep=clock.sleep)
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["built: no ghosts of iron-chest left in 305,415,353,449"])
        self.assertEqual(clock.slept, [5, 5])

    def test_a_zero_bound_checks_once_and_then_says_what_is_left(self):
        clock = Clock()

        def snap(*_a, **_k):
            return capture(row("iron-chest", 1, 1))
        with mock.patch.object(link, "snapshot", snap):
            code, lines = wait.run(object(), "lab", AREA, max_s=0,
                                   clock=clock.now, sleep=clock.sleep)
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["wait built: 1 ghost left in 305,415,353,449 (iron-chest 1)"])
        self.assertEqual(clock.slept, [])

    def test_a_link_error_stops_the_wait(self):
        clock = Clock()

        def snap(*_a, **_k):
            raise link.LinkError("RCON socket closed")
        with mock.patch.object(link, "snapshot", snap):
            with self.assertRaises(link.LinkError):
                wait.run(object(), "lab", AREA, clock=clock.now, sleep=clock.sleep)
        self.assertEqual(clock.slept, [])


class WaitCliTest(unittest.TestCase):
    def setUp(self):
        self.r = FakeRcon()
        patcher = mock.patch.object(link, "open_from_env", return_value=(self.r, None))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, args, result=(0, ["built: no ghosts left in 305,415,353,449"])):
        seen = {}

        def fake(r, surface, area, names, max_s, poll_s):
            seen.update(r=r, surface=surface, area=tuple(area), names=list(names),
                        max_s=max_s, poll_s=poll_s)
            return result
        from fkcore import wires
        got = wires.Pass(added=2, cut=1, hand=["a red wire between a and b, which the design "
                                                "doesn't have: cut"])

        def pass_(r, s, cat, area, poles=None, tag="wires"):
            seen.update(wires=tuple(area))
            return got
        with mock.patch.object(wait, "run", fake), mock.patch.object(wires, "run", pass_):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = mainmod.main(["wait", GAME, "built"] + args)
        seen["out"] = out.getvalue()
        return code, seen

    def test_without_an_area_the_designs_and_five_minutes(self):
        code, seen = self.run_main([])
        self.assertEqual(code, 0)
        self.assertEqual(seen["surface"], "lab")
        self.assertEqual(seen["area"], DESIGN_AREA)
        self.assertEqual((seen["max_s"], seen["poll_s"]), (300.0, 10.0))
        self.assertEqual(seen["names"], [])
        self.assertIs(seen["r"], self.r)

    def test_then_the_wire_pass_runs_over_the_same_area(self):
        # 2.1: robots built the poles, and a pole joins itself to its neighbours
        code, seen = self.run_main(["--area", "305,415,353,449"])
        self.assertEqual((code, seen["wires"]), (0, AREA))
        self.assertIn("wires: 2 added, 1 cut", seen["out"])
        self.assertIn("by-hand: a red wire between a and b", seen["out"])

    def test_area_names_and_bounds_are_passed(self):
        code, seen = self.run_main(["--area", "305,415,353,449", "--name",
                                    "transport-belt,iron-chest", "--max", "90s",
                                    "--poll", "2s"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["area"], AREA)
        self.assertEqual(seen["names"], ["transport-belt", "iron-chest"])
        self.assertEqual((seen["max_s"], seen["poll_s"]), (90.0, 2.0))

    def test_the_exit_code_of_the_wait_is_the_commands(self):
        code, _seen = self.run_main(["--area", "305,415,353,449"],
                                    result=(1, ["wait built: 2 ghosts left in 305,415,353,449 "
                                                "(iron-chest 2)"]))
        self.assertEqual(code, 1)

    def test_a_bad_duration_is_two_before_any_game_call(self):
        patcher = mock.patch.object(link, "open_from_env", side_effect=AssertionError("no link"))
        patcher.start()
        self.addCleanup(patcher.stop)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = mainmod.main(["wait", GAME, "built", "--max", "soon"])
        self.assertEqual(code, 2)
        self.assertIn("a duration is like 90s, 5m or 1h", err.getvalue())

    def test_a_bad_area_is_two_before_any_game_call(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = mainmod.main(["wait", GAME, "built", "--area", "305,415,305,449"])
        self.assertEqual(code, 2)
        self.assertIn("X1 > X0", err.getvalue())

    def test_a_link_error_is_two(self):
        with mock.patch.object(wait, "run", side_effect=link.LinkError("socket closed")):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = mainmod.main(["wait", GAME, "built", "--area", "305,415,353,449"])
        self.assertEqual(code, 2)
        self.assertIn("LinkError: socket closed", err.getvalue())

    def test_ctrl_c_closes_the_link_and_exits_130(self):
        with mock.patch.object(wait, "run", side_effect=KeyboardInterrupt):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = mainmod.main(["wait", GAME, "built", "--area", "305,415,353,449"])
        self.assertEqual(code, 130)
        self.assertTrue(self.r.closed)
        self.assertIn("interrupted", err.getvalue())

    def test_without_the_link_the_wait_is_two(self):
        with mock.patch.object(link, "open_from_env",
                               return_value=(None, "FK_LINK is not on (test)")):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = mainmod.main(["wait", GAME, "built", "--area", "305,415,353,449"])
        self.assertEqual(code, 2)
        self.assertIn("skipped, no game link", out.getvalue())


class AgentWaitCommandTest(unittest.TestCase):
    def test_the_wrapper_takes_the_area_after_built(self):
        self.assertEqual(fk_agent._wait_args(["built", "305,415,353,449", "--max", "5m"]),
                         ["built", "--area", "305,415,353,449", "--max", "5m"])
        self.assertEqual(fk_agent._wait_args(["built", "-320,-288,256,288"]),
                         ["built", "--area", "-320,-288,256,288"])
        self.assertEqual(fk_agent._wait_args(["built", "--max", "5m"]),
                         ["built", "--max", "5m"])
        self.assertEqual(fk_agent._wait_args(["built", "iron-chest"]), ["built", "iron-chest"])


if __name__ == "__main__":
    unittest.main()
