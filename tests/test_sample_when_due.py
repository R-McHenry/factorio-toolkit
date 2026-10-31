"""2.1.4: a run with no loop samples its stats after a command, at most every 5 minutes."""
import importlib.util
import os
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("fk_agent_sample", os.path.join(ROOT, "agent", "fk.py"))
fk_agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fk_agent)


class SampleWhenDue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.marker = os.path.join(self.tmp.name, ".stats-sampled")
        self.calls = []
        self.patches = [mock.patch.object(fk_agent, "SAMPLED", self.marker),
                        mock.patch.object(fk_agent, "_config", lambda: {"host": "local"}),
                        mock.patch.object(fk_agent, "remote",
                                          lambda cfg, args, footer=True: self.calls.append(
                                              (args, footer)) or 0)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_first_command_samples_quietly(self):
        fk_agent.sample_when_due(["look", "0,0,10,10"])
        self.assertEqual(self.calls, [(["stats", ".", "--sample"], False)])
        self.assertTrue(os.path.exists(self.marker))

    def test_not_again_within_five_minutes(self):
        fk_agent.sample_when_due(["look"])
        fk_agent.sample_when_due(["build"])
        self.assertEqual(len(self.calls), 1)

    def test_again_once_due(self):
        fk_agent.sample_when_due(["look"])
        old = time.time() - fk_agent.SAMPLE_EVERY - 1
        os.utime(self.marker, (old, old))
        fk_agent.sample_when_due(["look"])
        self.assertEqual(len(self.calls), 2)

    def test_stats_and_help_never_sample(self):
        for argv in ([], ["--help"], ["stats", "--history"]):
            fk_agent.sample_when_due(argv)
        self.assertEqual(self.calls, [])

    def test_a_failure_stays_quiet(self):
        def boom(*a, **k):
            raise OSError("no host")
        with mock.patch.object(fk_agent, "remote", boom):
            fk_agent.sample_when_due(["look"])     # no exception


if __name__ == "__main__":
    unittest.main()
