"""2.0.12: the player loop's watchdog (kickoff/watchdog.py). The solo run's loop died at 22:40 on
2026-10-22 without a line in play.log, and the game ran 10.6 hours unattended. Offline: no game,
no claude; one test starts a real detached watchdog and stops it with a STOP file."""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "kickoff"))
import claude_loop  # noqa: E402
import watchdog  # noqa: E402

MIN = 60


class RunDir(unittest.TestCase):
    def setUp(self):
        self.run = tempfile.mkdtemp(prefix="fkdog-")
        self.addCleanup(shutil.rmtree, self.run, True)
        os.makedirs(os.path.join(self.run, ".loop"))
        self.write("GOAL.md", "Finish the mall.\n")
        self.write("play.log", "22:40:45    ! Exit code 137\n")
        self.opened, self.said = [], []
        self.dog = watchdog.Watchdog(self.run, opener=self.opened.append,
                                     say=lambda run, text: self.said.append(text) or True)

    def path(self, name):
        return os.path.join(self.run, name)

    def write(self, name, text):
        with open(self.path(name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as fh:
            return fh.read()

    def silent(self, minutes, now=None):
        """play.log last written ``minutes`` before ``now``; -> that time."""
        t = (time.time() if now is None else now) - minutes * MIN
        os.utime(self.path("play.log"), (t, t))
        return t


class LookTest(RunDir):
    def test_a_dead_loop_is_started_again_and_said_so(self):
        went = self.silent(16)
        self.assertEqual(self.dog.look(), "restarted")
        self.assertEqual(self.opened, [self.path("play.cmd")])
        hhmm = f"{datetime.fromtimestamp(went):%H:%M}"
        last = self.read("play.log").splitlines()[-1]
        self.assertRegex(last, r"^\d\d:\d\d:\d\d  watchdog: play.log silent since "
                         + hhmm + " and no loop running: play.cmd started again$")
        self.assertEqual(len(self.said), 1)
        self.assertTrue(self.said[0].startswith(f"watchdog: the player's loop stopped around {hhmm}; "
                                                "started it again at "), self.said[0])
        self.assertIn(f"Your loop stopped around {hhmm} and the watchdog started it again",
                      self.read("INBOX-watchdog.md"))
        self.assertIn("game chat: said", self.read(os.path.join(".loop", "watchdog.log")))

    def test_a_quiet_loop_that_still_runs_is_left_alone(self):
        # a long build, a usage-limit backoff: play.log is quiet, the loop is there
        self.silent(40)
        with mock.patch.object(watchdog, "holder", return_value=4242):
            self.assertIsNone(self.dog.look())
        self.assertEqual(self.opened, [])

    def test_not_before_the_quiet_minutes_nor_with_stop_or_an_empty_goal(self):
        self.silent(14)
        self.assertIsNone(self.dog.look())
        self.silent(60)
        self.write("GOAL.md", "  \n")                  # the loop pauses on an empty goal
        self.assertIsNone(self.dog.look())
        self.write("STOP", "")
        self.assertEqual(self.dog.look(), "stop")
        self.assertEqual(self.opened, [])

    def test_a_restart_the_loop_does_not_come_back_from_doubles_the_wait(self):
        self.silent(16)
        self.assertEqual(self.dog.look(), "restarted")
        mark = os.path.getmtime(self.path("play.log"))     # its own line; the loop wrote nothing
        self.assertIsNone(self.dog.look(now=mark + 16 * MIN))
        self.assertEqual(self.dog.look(now=mark + 31 * MIN), "restarted")
        mark = os.path.getmtime(self.path("play.log"))
        self.assertIsNone(self.dog.look(now=mark + 59 * MIN))
        # the loop came back (it wrote), then died again: 15 minutes again
        os.utime(self.path("play.log"), (mark + 5 * MIN, mark + 5 * MIN))
        self.assertEqual(self.dog.look(now=mark + 21 * MIN), "restarted")
        self.assertEqual(len(self.opened), 3)

    def test_the_waits_stop_growing_at_two_hours(self):
        self.dog.failed, self.dog.mark = 9, self.silent(119)       # nothing since the last one
        self.assertIsNone(self.dog.look())
        self.dog.mark = self.silent(121)
        self.assertEqual(self.dog.look(), "restarted")

    def test_a_failed_chat_line_is_noted_and_the_restart_stands(self):
        def fails(run, text):
            raise subprocess.TimeoutExpired("ssh", 30)
        self.dog.say = fails
        self.silent(20)
        self.assertEqual(self.dog.look(), "restarted")
        self.assertIn("game chat: TimeoutExpired", self.read(os.path.join(".loop", "watchdog.log")))


class HolderTest(RunDir):
    def test_a_lock_names_a_live_python_only_when_it_is_older_than_the_lock(self):
        lock = self.path("claude-loop.lock")
        self.write("claude-loop.lock", str(os.getpid()))
        self.assertEqual(watchdog.holder(lock), os.getpid())       # this test runs in Python
        old = time.time() - 10 * 24 * 3600                          # written before we started:
        os.utime(lock, (old, old))                                  # the pid was given again
        self.assertIsNone(watchdog.holder(lock))
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        gone.wait()
        self.write("claude-loop.lock", str(gone.pid))
        self.assertIsNone(watchdog.holder(lock))
        self.write("claude-loop.lock", "not a pid")
        self.assertIsNone(watchdog.holder(lock))
        self.assertIsNone(watchdog.holder(self.path("no.lock")))


class StartTest(RunDir):
    def test_detach_starts_a_process_of_its_own(self):
        with mock.patch.object(watchdog.subprocess, "Popen") as popen:
            self.assertEqual(watchdog.detach(self.run, 15, 60), 0)
        args, kw = popen.call_args
        self.assertEqual(args[0][1:], [os.path.abspath(watchdog.__file__), self.run, "--quiet",
                                       "15", "--every", "60"])
        if os.name == "nt":
            self.assertTrue(kw["creationflags"] & 0x00000008)      # DETACHED_PROCESS: no console
        self.assertIs(kw["stdin"], subprocess.DEVNULL)

    def test_the_loop_asks_for_one_as_it_starts(self):
        with mock.patch.object(claude_loop.subprocess, "run",
                               return_value=mock.Mock(returncode=0, stderr="")) as run:
            claude_loop.start_watchdog(self.run, lambda _t: None)
        cmd = run.call_args[0][0]
        here = os.path.dirname(os.path.abspath(claude_loop.__file__))
        self.assertEqual(cmd[1:], [os.path.join(here, "watchdog.py"), self.run, "--detach"])

    def test_one_watchdog_per_run(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (other.kill(), other.wait()))
        time.sleep(0.2)
        self.write(os.path.join(".loop", "watchdog.lock"), str(other.pid))
        self.assertEqual(watchdog.main([self.run]), 0)
        self.assertEqual(self.read(os.path.join(".loop", "watchdog.lock")), str(other.pid))

    def test_a_stop_file_ends_it(self):
        self.write("STOP", "")
        with mock.patch.object(ctypes, "windll", mock.MagicMock(), create=True):
            self.assertEqual(watchdog.main([self.run, "--every", "0.01"]), 0)
        self.assertIn("STOP file: the watchdog ends",
                      self.read(os.path.join(".loop", "watchdog.log")))

    def test_a_real_detached_watchdog_outlives_its_starter_and_ends_on_stop(self):
        # GOAL.md empty: it looks, never restarts anything
        self.write("GOAL.md", "")
        lock = self.path(os.path.join(".loop", "watchdog.lock"))
        self.addCleanup(lambda: os.path.exists(self.path("STOP")) or self.write("STOP", ""))
        t0 = time.time()
        r = subprocess.run([sys.executable, watchdog.__file__, self.run, "--detach", "--every",
                            "0.2"], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(time.time() - t0, 15)                 # the starter doesn't wait for it
        pid = None
        while time.time() - t0 < 20 and not pid:
            pid = watchdog.holder(lock)
            time.sleep(0.2)
        self.assertTrue(pid, "no watchdog took the lock")
        self.addCleanup(lambda: watchdog.running(pid) and subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)], capture_output=True))
        self.write("STOP", "")
        t1 = time.time()
        while time.time() - t1 < 20 and watchdog.running(pid):
            time.sleep(0.2)
        self.assertFalse(watchdog.running(pid), "the watchdog did not end on STOP")
        self.assertIn("STOP file: the watchdog ends",
                      self.read(os.path.join(".loop", "watchdog.log")))


if __name__ == "__main__":
    unittest.main()
