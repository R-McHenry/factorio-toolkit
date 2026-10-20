"""fkcore.alerts against fixture reads and a fake link (no game): normalise, track, poll, push."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import alerts, freereads, link

ATTACK = {"type": "entity_under_attack", "surface": "lab", "tick": 4990, "target": "wooden-chest",
          "x": 385.5, "y": 520.5}
SPEAKER = {"type": "custom", "surface": "lab", "tick": 4000, "target": "programmable-speaker",
           "x": 390.5, "y": 520.5, "message": "fk5 sense: speaker test", "icon": "item/iron-plate"}


def raw(tick, *rows, players=("Rory_618", "agent")):
    """A raw read as link.alerts returns it: each player of the force sees every alert."""
    return {"tick": tick, "force": "lab",
            "players": [{"name": p, "connected": p == "Rory_618", "alerts": len(rows)}
                        for p in players],
            "forces": {"lab": {"players": len(players), "connected": 1},
                       "player": {"players": 0, "connected": 0}},
            "alerts": [dict(r, player=p) for p in players for r in rows]}


REMIND = 20 * 60                    # remind 20s


class TrackTest(unittest.TestCase):
    def step(self, state, tick, *rows):
        """One poll: track, then the state goes through JSON as out/alerts.json does."""
        new, rem, cleared, state = alerts.track(state, alerts.normalise(raw(tick, *rows)), tick,
                                                REMIND)
        return [e["alert"]["type"] for e in new], [e["alert"]["type"] for e in rem], \
            [e["alert"]["type"] for e in cleared], json.loads(json.dumps(state))

    def test_normalise_dedupes_across_players(self):
        rd = alerts.normalise(raw(5000, ATTACK, SPEAKER))
        self.assertEqual(len(rd.alerts), 2)                       # 4 rows, 2 players
        self.assertEqual([p["name"] for p in rd.players], ["Rory_618", "agent"])
        self.assertEqual(rd.forces["player"]["players"], 0)
        speaker = next(a for a in rd.alerts if a["type"] == "custom")
        self.assertEqual((speaker["message"], speaker["icon"], speaker["tick"]),
                         ("fk5 sense: speaker test", "item/iron-plate", 4000))
        # Lua's empty table comes back as {}; a LocalisedString is joined
        empty = alerts.normalise({"tick": 1, "force": "player", "players": {}, "alerts": {},
                                  "forces": {}})
        self.assertEqual((empty.alerts, empty.players), ((), ()))
        loc = alerts.normalise(raw(1, dict(SPEAKER, message=["", "low ", "iron"])))
        self.assertEqual(loc.alerts[0]["message"], "low iron")

    def test_new_once_reminded_every_cadence_cleared_once(self):
        new, rem, cleared, st = self.step(None, 5000, ATTACK, SPEAKER)
        self.assertEqual((sorted(new), rem, cleared), (["custom", "entity_under_attack"], [], []))
        new, rem, cleared, st = self.step(st, 5600, ATTACK, SPEAKER)          # 10 s later
        self.assertEqual((new, rem, cleared), ([], [], []))
        new, rem, cleared, st = self.step(st, 6200, ATTACK, SPEAKER)          # 20 s
        self.assertEqual((new, sorted(rem), cleared), ([], ["custom", "entity_under_attack"], []))
        new, rem, cleared, st = self.step(st, 6800, ATTACK, SPEAKER)
        self.assertEqual((new, rem, cleared), ([], [], []))
        new, rem, cleared, st = self.step(st, 7400, ATTACK, SPEAKER)          # 40 s
        self.assertEqual(len(rem), 2)
        new, rem, cleared, st = self.step(st, 7500, SPEAKER)                  # the chest is gone
        self.assertEqual((new, rem, cleared), ([], [], ["entity_under_attack"]))
        new, rem, cleared, st = self.step(st, 7600)                           # the speaker too
        self.assertEqual((new, rem, cleared), ([], [], ["custom"]))
        new, rem, cleared, st = self.step(st, 7700)
        self.assertEqual((new, rem, cleared, st["alerts"]), ([], [], [], {}))

    def test_an_attack_that_goes_on_is_the_same_alert(self):
        _n, _r, _c, st = self.step(None, 5000, ATTACK)
        new, rem, cleared, st = self.step(st, 5300, dict(ATTACK, tick=5290))  # the game moved it
        self.assertEqual((new, rem, cleared), ([], [], []))
        new, _r, cleared, _st = self.step(st, 5400, dict(ATTACK, x=386.5))    # another chest
        self.assertEqual((new, cleared), (["entity_under_attack"], ["entity_under_attack"]))

    def test_no_cadence_never_reminds_and_an_older_save_restarts_it(self):
        rd = alerts.normalise(raw(5000, ATTACK))
        _n, _r, _c, st = alerts.track(None, rd, 5000, None)
        _n, rem, _c, st = alerts.track(st, rd, 500000, None)
        self.assertEqual(rem, [])
        _n, rem, _c, st = alerts.track(st, rd, 100, REMIND)                   # the clock went back
        self.assertEqual((rem, st["alerts"][alerts.key(rd.alerts[0])]["pushed"]), ([], 100))
        _n, rem, _c, st = alerts.track(st, rd, 100 + REMIND, REMIND)
        self.assertEqual(len(rem), 1)

    def test_lines(self):
        rd = alerts.normalise(raw(5000, ATTACK, SPEAKER))
        new, _r, _c, st = alerts.track(None, rd, 5000, REMIND)
        self.assertEqual(alerts.lines(new, [], [], 5000), [
            'ALERT custom "fk5 sense: speaker test" [item/iron-plate]: programmable-speaker at '
            'lab 390.5,520.5 (raised at tick 4000)',
            "ALERT entity_under_attack: wooden-chest at lab 385.5,520.5 (raised at tick 4990)"])
        _n, rem, _c, st = alerts.track(st, rd, 5000 + REMIND, REMIND)
        self.assertIn("still there, first seen 20s ago (tick 5000)",
                      alerts.lines([], rem, [], 5000 + REMIND)[0])
        _n, _r, cleared, _st = alerts.track(st, alerts.normalise(raw(9000)), 9000, REMIND)
        self.assertEqual(alerts.lines([], [], cleared, 9000)[1],
                         "CLEARED entity_under_attack: wooden-chest at lab 385.5,520.5 "
                         "(seen for 1min 6s)")
        self.assertEqual([alerts.age(t) for t in (59, 3600, 7260, 216000, 219600)],
                         ["0s", "1min", "2min 1s", "1h", "1h 1min"])


STATS = {"tick": 5000, "force": "lab", "surface": "lab", "window": "1min",
         "items": [{"name": "iron-plate", "made_per_min": 0, "used_per_min": 60, "made": 0,
                    "used": 60, "made_total": 900, "used_total": 960}]}


class FreeReadsNeverAlertTest(unittest.TestCase):
    """CORE-V1 decision 11: statistics and the chart are free to read and never become alerts."""

    def test_track_takes_only_an_alert_panel_read(self):
        stopped = freereads.stats_from(STATS)                     # production stopped
        chart = freereads.chart_from({"tick": 5000, "force": "lab", "surface": "lab",
                                      "charted": 0, "chunks": 576})
        shaped = {"force": "lab", "tick": 5000, "alerts": [ATTACK]}  # even if shaped like one
        for read in (stopped, chart, shaped, STATS):
            with self.assertRaises(TypeError):
                alerts.track(None, read, 5000, REMIND)

    def test_poll_reads_only_the_alert_panel(self):
        game = tempfile.mkdtemp(prefix="fkalerts-")
        try:
            with open(os.path.join(game, "lab.surface"), "w", encoding="utf-8") as fh:
                fh.write("surface lab\nmode lab\nnotify nearby\n")
            calls = []
            with mock.patch.object(link, "alerts", lambda r, f, tag="a": calls.append(f) or
                                   raw(5000)), \
                    mock.patch.object(link, "stats", lambda *a, **k: self.fail("stats read")), \
                    mock.patch.object(link, "chart", lambda *a, **k: self.fail("chart read")):
                self.assertEqual(alerts.poll(FakeRcon(), game), [])
            self.assertEqual(calls, ["lab"])
        finally:
            shutil.rmtree(game, ignore_errors=True)


class FakeRcon:
    def __init__(self):
        self.calls = []

    def lua(self, body):
        self.calls.append(body)
        return "ok"

    def said(self):
        return [c for c in self.calls if "game.print" in c]


class PollTest(unittest.TestCase):
    def setUp(self):
        self.game = tempfile.mkdtemp(prefix="fkalerts-")
        self.write_surface("all")

    def tearDown(self):
        shutil.rmtree(self.game, ignore_errors=True)

    def write_surface(self, notify):
        with open(os.path.join(self.game, "lab.surface"), "w", encoding="utf-8") as fh:
            fh.write(f"surface lab\nmode lab\nnotify {notify}\nremind 20s\n")

    def poll(self, reply, force=None):
        r = FakeRcon()
        with mock.patch.object(link, "alerts", lambda _r, f, tag="a": dict(reply, force=f)):
            return r, alerts.check(r, self.game, force)

    def test_poll_tracks_in_out_and_pushes_when_notify_is_all(self):
        r, p = self.poll(raw(5000, ATTACK, SPEAKER))
        self.assertEqual((len(p.new), len(p.lines), len(r.said())), (2, 2, 2))
        self.assertTrue(all("[fk lab] ALERT " in c for c in r.said()))
        with open(os.path.join(self.game, "out", "inbox.txt"), encoding="utf-8") as fh:
            self.assertTrue(fh.read().startswith("5000 alert: ALERT custom"))
        with open(alerts.state_path(self.game), encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)["lab"]["alerts"]), 2)
        r, p = self.poll(raw(5100, ATTACK, SPEAKER))              # nothing new
        self.assertEqual((p.lines, r.said()), ([], []))
        r, p = self.poll(raw(6300, ATTACK, SPEAKER))              # remind 20s
        self.assertEqual((len(p.reminders), len(r.said())), (2, 2))
        self.write_surface("nearby")
        r, p = self.poll(raw(6400))
        self.assertEqual((len(p.cleared), r.said()), (2, []))     # reported, not chatted
        report = "\n".join(p.report())
        self.assertIn("players of lab: 2 (1 connected): Rory_618 (connected) 0 alerts", report)
        self.assertIn("player 0 player(s) (0 connected)", report)

    def test_states_are_per_force_and_a_force_without_players_says_so(self):
        _r, p = self.poll(raw(5000, ATTACK))
        _r, q = self.poll(raw(5000, players=()), force="player")
        self.assertEqual((len(p.new), q.new), (1, []))
        self.assertIn("players of player: 0: no alert panel to read", "\n".join(q.report()))
        with open(alerts.state_path(self.game), encoding="utf-8") as fh:
            self.assertEqual(sorted(json.load(fh)), ["lab", "player"])

    def test_poll_never_raises(self):
        def broken(*_a, **_k):
            raise link.LinkError("RCON socket closed")
        with mock.patch.object(link, "alerts", broken):
            self.assertEqual(alerts.poll(FakeRcon(), self.game),
                             ["alerts: not read (LinkError: RCON socket closed)"])
        self.assertEqual(alerts.poll(FakeRcon(), os.path.join(self.game, "nowhere"))[0][:17],
                         "alerts: not read ")


if __name__ == "__main__":
    unittest.main()
